"""Unique-value lookup (F3) — the primitive every input suggestion sits on.

WHAT IT ANSWERS
    (table, column, prefix) -> the DISTINCT stored values of that column that
    begin with that prefix, plus **whether the list was cut short**.

WHY IT IS NOT `SELECT DISTINCT col WHERE col LIKE 'p%'`
    Two independent traps, both measured on the live 1.75M-row `bonding_map`
    (PostgreSQL 18, `datcollate = Korean_Korea.949`):

    1. **A plain btree cannot serve `LIKE 'prefix%'` outside the C collation.**
       The planner will still *pick* the index and then throw every entry away
       in a Filter:

           Index Only Scan using idx_bonding_map_base
             Index Cond: (base IS NOT NULL)
             Filter: ((base)::text ~~ 'C%'::text)
             Rows Removed by Filter: 1755308        -- 232 ms for 3 values

       The fix is an index whose ordering IS byte order, so the prefix becomes
       a real range: `(lower(col) COLLATE "C", col COLLATE "C")`. Same query,
       same data: `Index Cond: (lower(base) >= 'c' AND lower(base) < 'd')`,
       0.2 ms. This module owns that index's definition; the graph node search
       (`/graph/nodes/search`, the second consumer) uses the same predicate.

    2. **DISTINCT costs O(rows scanned to fill the page), not O(answers).**
       Even with the right index, filling 51 rows means walking until 51 are
       found — and when the matches are SPARSE that is most of the table:
       `leg` (342 distinct over 1.75M rows) takes 161 ms, and `base LIKE 'C%'`
       (3 matches) takes 144 ms. Those are exactly the queries a dropdown makes.

       So this module does a **loose index scan** ("skip scan"): seek the first
       value, then repeatedly seek the *next value strictly greater than the
       last one*. Cost is one index seek per value RETURNED, independent of
       table size and of cardinality. Measured end to end through
       `suggest_values` (median of 7, 51 values): 33 ms for `leg`, 32 ms for
       `base`, 37 ms for the 1.75M-distinct `pkg_id`.

       The flat ~33 ms is the point, not the size of the win: the naive query
       ranges from 0.3 ms (`base`, empty prefix — dense matches, 51 found
       immediately) to 3.4 s (`pkg_id`). A dropdown cannot be built on a
       primitive whose cost swings by four orders of magnitude with the data.

DECLARATION IS THE AUTHORITY (INV-F3-3)
    `table` and `column` arrive from the client. They are matched against
    `crud.TABLE_CONFIG` (`column_types`) and then resolved to real SQLAlchemy
    Column objects — no caller string ever reaches SQL text. An undeclared
    table or column is a 400, never a query.

CANONICAL VALUES ARE NOT RE-INVENTED (INV-F3-4)
    A `number`-declared column is physically Float, so the stored 1 reads back
    as 1.0. Suggestions go through `map_overlay.canonical_key_value`, the
    project's ONE key normaliser (1.0 -> '1', '01' -> '1'). The *prefix* is
    canonicalised the same way, so typing `01` finds `1`. Do NOT write a second
    normalisation here.

CASE-INSENSITIVITY IS THE DATABASE'S, NOT PYTHON'S
    The index key is `lower(col)` as PostgreSQL computes it, so the prefix is
    folded by the same `lower()` (`db_fold`) and the seek loop re-tests against
    the `lower(col)` the query already returned. Folding in Python instead made
    the range and the index two different functions — on this database
    `lower()` leaves U+00C4 alone while Python lowercases it — and stored values
    were dropped from answers with `truncated: false`. ASCII prefixes skip the
    round trip because A-Z -> a-z is the one mapping every implementation
    shares. Consequence worth stating plainly: two values are the "same" here
    exactly when the DATABASE folds them together, no more and no less.

TRUNCATION IS ALWAYS SPOKEN (INV-F3-1)
    A silently cut list tells the dropdown "this is all of them". Every path
    that stops early — limit reached, probe budget exhausted — sets
    `truncated`. A path that cannot answer at all sets `unavailable_reason`
    and returns NO values (same shape as the dashboard's degraded stats: an
    empty list that looks normal is a wrong answer, not a missing one).

COST IS ALWAYS SPOKEN TOO (F7, 2026-07-30)
    Truncation and unavailability were both reported, and a third state was not:
    an answer that is complete, correct, and far too expensive. Every diagnostic
    in this module ran on a FAILURE path, so `wafer_process` — 10.4k rows, past
    `index_min_rows`, builder never re-run — answered `wafer_process.knobs` in
    247 ms with `truncated: false` and `unavailable_reason: null`. Nothing about
    that response was false. It simply did not carry the one fact that was wrong.

    So every response now carries:
        `elapsed_ms`  — measured cost, on every path including the failed ones.
                        THIS is the signal: precise, always present, comparable.
        `slow_reason` — None, or a named cause when the cost exceeded
                        `slow_warn_ms`. The VALUES REMAIN VALID; this is not a
                        degradation, it is a correct answer with a receipt.
                        A COARSE ALARM, not a detector — healthy columns spike into
                        the same range occasionally (see `slow_warn_ms`), so its
                        threshold is set to "structurally wrong", not "slower than
                        usual". `classify_seek_plan` is the precise instrument.

    Why a field and not a log line: the caller cannot read logs. A client that
    wants to back off, or an operator diffing two deployments, needs the number
    in the response. `slow_reason` is what makes it actionable without one —
    it names the missing index and what to run, reusing the same
    `_index_advice` the timeout path uses.

    Running the index builder fixes today's table. It does not fix the CLASS:
    the next table to cross `index_min_rows` reproduces this exactly, and these
    two fields are the only reason anyone would notice.
"""
import json
import logging
import math
import re
import time

import sqlalchemy as sa

import paths

logger = logging.getLogger(__name__)

CONFIG_PATH = paths.config_path("suggest_config.json")

# Every knob below is a DEFAULT; suggest_config.json overrides it. A missing
# config file is normal operation (these defaults are the shipped policy).
DEFAULTS = {
    # How many values one response may carry, and the ceiling a caller may ask for.
    "default_limit": 50,
    "max_limit": 200,
    # 0 = an empty prefix is allowed. It is SAFE here (the loose scan makes it
    # O(limit) seeks, not O(rows)) - the knob exists so an operator can force
    # "type at least N characters" as a policy, not as a performance crutch.
    "min_prefix_length": 0,
    # Hard cap on index seeks per request. Binds only on numeric columns, where
    # a probe can land on a value that fails the exact prefix test.
    "max_probe_values": 400,
    # Per-request statement_timeout AND the wall-clock deadline of the seek loop.
    # Exceeding it degrades honestly instead of hanging the dropdown.
    #
    # NOT A LATENCY BOUND — see `_stop_reason`. The loop tests the clock BEFORE
    # issuing a probe, so a probe started just under the deadline may still run for
    # a full `statement_timeout`. The real bound is `2 * timeout_ms`; measured
    # worst case on the live database was 1901 ms against 1500 (1.27x). `elapsed_ms`
    # in every response is what makes the ACTUAL cost knowable rather than assumed.
    "timeout_ms": 1500,
    # Above this measured cost a SUCCESSFUL answer still reports `slow_reason`.
    #
    # This is the knob that closes the silent-slowness band (F7). Everything else
    # here only fires on the FAILURE path, so a correct-looking, complete-looking
    # answer that cost 20x its budget reached the caller with no signal at all:
    # `wafer_process.knobs` answered in 247 ms with `truncated: false` and
    # `unavailable_reason: null` because the table crossed `index_min_rows` and the
    # builder had not been re-run. Nothing was wrong with the answer — only with
    # what it cost, and cost was the one thing the response did not carry.
    #
    # 200 ms, and the number is measured — including the part that argues against a
    # tighter one. Healthy indexed columns (2026-07-30, 21 reps each, live):
    #     median 17-23 ms, p95 18-26 ms  ...  but MAX 148 ms.
    # Unindexed columns over `index_min_rows` measured 51.8 ms median, 302 ms worst.
    # So the two distributions OVERLAP in the tail, and no single latency threshold
    # separates them: 50 ms was tried first and fired twice on healthy, correctly
    # indexed columns in one 168-request run.
    #
    # 200 ms therefore means "structurally wrong", not "this request was unlucky".
    # It sits above every healthy sample observed and still caught 6 of the 14
    # `wafer_process` columns when they had no index — and catching SIX columns of a
    # broken table is enough, because the repair (`setup_db_performance.py`) fixes
    # the whole table at once. A threshold that cries wolf gets switched off, which
    # would cost more than the columns it would have caught.
    #
    # The precise instrument is elsewhere and deliberately so: `elapsed_ms` is
    # always present for anyone who wants the real number, and `classify_seek_plan`
    # answers the categorical question ("is this index a RANGE?") that latency can
    # only hint at. This knob is the loud alarm, not the measurement.
    "slow_warn_ms": 200,
    # A table at least this large gets suggestion indexes built for its
    # string-declared columns (setup_db_performance.py). Smaller tables scan
    # fine without one, and indexing them all would cost disk for nothing.
    "index_min_rows": 10000,
}

# Per-table overrides, validated separately (dict of table -> list[column]).
#   index_columns : force EXACTLY these columns (ignores index_min_rows)
#   index_exclude : never index these columns
LIST_MAP_KEYS = ("index_columns", "index_exclude")

# Columns outside `table_config` that need the same prefix index. Kept here so
# the index NAME has exactly one derivation, shared by the builder script and
# by the "why did this fail" diagnosis below.
SYSTEM_PREFIX_INDEX_TARGETS = (("graph_nodes", "identity_key"),)

INDEX_PREFIX = "idx_suggest_"
_MAX_IDENTIFIER = 63  # PostgreSQL NAMEDATALEN - 1

_DIGITS_RE = re.compile(r"^\d+$")
_DECIMAL_RE = re.compile(r"^\d+\.\d+$")
# Largest ENUMERATED magnitude for an integer prefix: '9' also matches 90..99,
# 900..999, ... Each magnitude is one range, and an empty range costs exactly one
# probe, so enumerating every double magnitude (up to 1e308) would spend the
# whole probe budget proving nothing. Past this point the walk stops enumerating
# and the top range is left OPEN above instead — a value at 1e20 is then still
# reachable (the Python test filters the non-matches) rather than silently
# absent, which is what a closed top range made it.
_MAX_MAGNITUDE = 15


class SuggestValidationError(Exception):
    """Caller asked for something undeclared/unsupported -> 4xx, not a query."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config(path: str = None) -> dict:
    """Load suggest_config.json. Missing file -> {} (all defaults apply)."""
    p = path or CONFIG_PATH
    try:
        with open(p, "r", encoding="utf-8-sig") as f:
            raw = json.load(f)
        return raw if isinstance(raw, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.warning("[Suggest] failed to load config %s: %s", p, e)
        return {}


def resolve_settings(config: dict = None) -> dict:
    """Return RESOLVED settings — always every key, always usable.

    A malformed knob falls back to its default with a warning rather than
    taking the endpoint down or, worse, silently applying a nonsense bound
    (a negative limit would make every response an empty list that looks fine).
    """
    declared = config if isinstance(config, dict) else {}
    resolved = dict(DEFAULTS)
    for k, default in DEFAULTS.items():
        if k not in declared:
            continue
        v = declared[k]
        # bool is a subclass of int - True must not silently become 1.
        if isinstance(v, bool) or not isinstance(v, int):
            logger.warning("[Suggest] '%s' must be an integer (got %r); using %s.", k, v, default)
            continue
        if v < 0:
            logger.warning("[Suggest] '%s' must be >= 0 (got %r); using %s.", k, v, default)
            continue
        # `slow_warn_ms` is here too: 0 would mark EVERY answer slow, and a reason
        # attached to every response is not a signal. `elapsed_ms` is the always-on
        # channel for operators who want the cost unconditionally; raise this knob
        # to effectively disable the named warning instead of zeroing it.
        if k in ("default_limit", "max_limit", "max_probe_values", "timeout_ms",
                 "slow_warn_ms") and v == 0:
            logger.warning("[Suggest] '%s' must be > 0 (got 0); using %s.", k, default)
            continue
        resolved[k] = v

    if resolved["default_limit"] > resolved["max_limit"]:
        logger.warning("[Suggest] default_limit (%s) > max_limit (%s); clamping.",
                       resolved["default_limit"], resolved["max_limit"])
        resolved["default_limit"] = resolved["max_limit"]

    for k in LIST_MAP_KEYS:
        resolved[k] = _resolve_column_map(declared.get(k), k)
    return resolved


def _resolve_column_map(value, key) -> dict:
    """{table: [column, ...]} with every malformed entry REJECTED and logged.

    A silently kept malformed entry reads as "declared" in the file while doing
    nothing — the config and the behaviour would disagree with nothing saying so.
    """
    if value is None:
        return {}
    if not isinstance(value, dict):
        logger.warning("[Suggest] '%s' must be an object {table: [column,...]}; ignoring.", key)
        return {}
    out = {}
    for table, cols in value.items():
        if not isinstance(table, str) or not table.strip():
            logger.warning("[Suggest] '%s' has a non-string table key %r; ignoring it.", key, table)
            continue
        if not isinstance(cols, list) or not all(isinstance(c, str) and c.strip() for c in cols):
            logger.warning("[Suggest] '%s[%s]' must be a list of column names; ignoring it.", key, table)
            continue
        out[table.strip()] = [c.strip() for c in cols]
    return out


# ---------------------------------------------------------------------------
# The shared prefix predicate — consumer #1 (this module) and #2 (graph search)
# ---------------------------------------------------------------------------

_MAX_CODE_POINT = 0x10FFFF


def prefix_upper_bound(prefix: str):
    """Exclusive upper bound of the byte-order range starting at `prefix`.

    `LIKE 'ab%'` is `>= 'ab' AND < 'ac'` in byte order. UTF-8 preserves code
    point order, so the bound is the successor of the last code point that HAS
    one (skipping the surrogate block, which UTF-8 cannot encode).

    "the last code point that has one" — not simply the last one. Incrementing
    only the final character gives up as soon as that character is U+10FFFF, and
    the old code then returned None for `'L\\U0010FFFF'`, leaving the caller with
    a lower bound that matches EVERYTHING at or above the term. `/graph/nodes/
    search` has no second filter behind it, so that query really did return every
    node from `MEAS` onward (measured; the old `ILIKE` returned 0 rows). The real
    bound there is `'M'` — carry into the earlier character, exactly like
    incrementing a number. Trailing U+10FFFF characters are the digits that roll
    over.

    None therefore means ONE thing now: the prefix is entirely U+10FFFF, and
    then every string `>= prefix` provably starts with it (its first character
    can be nothing lower), so the lower bound alone is already exact. There is no
    longer a case where a caller is handed a filter it cannot keep.
    """
    i = len(prefix) - 1
    while i >= 0:
        nxt = ord(prefix[i]) + 1
        if 0xD800 <= nxt <= 0xDFFF:
            nxt = 0xE000
        if nxt <= _MAX_CODE_POINT:
            return prefix[:i] + chr(nxt)
        i -= 1  # this character rolled over; carry into the one before it
    return None


def byte_order(expr, is_postgres: bool):
    """Decorate `expr` so comparisons are BYTE order, matching the index.

    PostgreSQL: `COLLATE "C"`. SQLite: BINARY is already byte order and the
    `"C"` collation does not exist there, so the expression is returned as is —
    the two backends therefore agree on ordering without a second code path.
    """
    return expr.collate("C") if is_postgres else expr


def db_fold(db, prefix: str) -> str:
    """Fold `prefix` with THE DATABASE'S OWN `lower()` — the one in the index.

    The index key is `lower(col)`, evaluated by PostgreSQL. Folding the prefix
    with Python's `str.lower()` instead makes the range and the index two
    DIFFERENT functions, and they disagree on this database (`Korean_Korea.949`,
    server_encoding UTF8):

        lower(U+00C4 + 'BC')  ->  PG  U+00C4 + 'bc'
                              ->  Python  U+00E4 + 'bc'

    So a stored U+00C4 value is indexed under U+00C4, while typing either case
    produced a range starting at U+00E4 — which sorts ABOVE it. The value was
    dropped with
    `truncated: false`: a silent miss, the one thing INV-F3-1/6 exist to
    prevent. PG folds some non-ASCII (Cyrillic) and not other non-ASCII
    (Latin-1 supplement), so no Python-side rule reproduces it — the only way
    the two agree is to stop having two.

    ASCII prefixes skip the round trip: A-Z -> a-z is the one mapping every
    `lower()` implementation shares (PostgreSQL, SQLite, Python), so the fast
    path is provably identical and the overwhelmingly common case pays nothing.
    """
    if not prefix:
        return ""
    if all(ord(ch) < 128 for ch in prefix):
        return prefix.lower()
    return db.execute(
        sa.select(sa.func.lower(sa.literal(prefix, sa.Text())))
    ).scalar() or ""


def prefix_conditions(col, folded: str, is_postgres: bool) -> list:
    """Case-insensitive prefix filter an `(lower(col) COLLATE "C", ...)` index serves.

    `folded` MUST already have been through `db_fold` — this takes the folded
    form, not the raw prefix, precisely so no caller can quietly reintroduce a
    second folding implementation (see `db_fold`).

    Case-INsensitive is deliberate: the live data is upper-case codes
    (`CDIE`, `BASE-29`) and a dropdown that ignores what a user typed in lower
    case is a dropdown nobody uses. It also keeps `/graph/nodes/search`'s
    existing ILIKE semantics intact while making it index-backed.

    The returned range is EXACT, not merely a narrowing superset:
    `f <= lower(col) < succ(f)` is equivalent to `lower(col).startswith(f)` in
    byte order, and `prefix_upper_bound` returns None only where the lower bound
    is exact on its own. That matters because consumer #2
    (`/graph/nodes/search`) has no second filter behind this one — a predicate
    that is only a superset would leak rows there, which is exactly what a
    missing upper bound used to do.
    """
    if not folded:
        return []
    lk = byte_order(sa.func.lower(col), is_postgres)
    conds = [lk >= folded]
    upper = prefix_upper_bound(folded)
    if upper is not None:
        conds.append(lk < upper)
    return conds


def _short_hash(table: str, column: str) -> str:
    import hashlib
    return hashlib.md5(f"{table}.{column}".encode("utf-8")).hexdigest()[:8]


def suggest_index_name(table: str, column: str) -> str:
    """`idx_suggest_<table>_<column>`, always a name PostgreSQL will keep verbatim.

    LOWER CASED on purpose. PostgreSQL folds unquoted identifiers, so
    `CREATE INDEX idx_suggest_inventory_master_MAX` creates `..._max` — and then
    the orphan report and the "is the index there?" diagnosis both disagree with
    the catalog about a name they themselves produced (found by the orphan
    report on the first live run). The hash suffix is what stops a `MAX` column
    and a `max` column from claiming the same index once the case is folded.

    Also hashed down when it would exceed the 63-char identifier limit.
    """
    raw = f"{INDEX_PREFIX}{table}_{column}"
    name = raw.lower()
    if name != raw:
        name = f"{name}_{_short_hash(table, column)}"
    if len(name) <= _MAX_IDENTIFIER:
        return name
    digest = _short_hash(table, column)
    keep = _MAX_IDENTIFIER - len(INDEX_PREFIX) - len(digest) - 1
    return f"{INDEX_PREFIX}{f'{table}_{column}'.lower()[:keep]}_{digest}"


def suggest_index_definition(column: str, declared=None) -> str:
    """The index body. ONE definition, shared by the builder and the docs.

    TEXT — two keys, not one: the first makes the case-insensitive prefix a
    range, the second makes the loose scan's cursor
    `(lower(col), col) > (last_lower, last_value)` an index seek AND keeps case
    variants as distinct values instead of collapsing them.

    NUMBER — a plain btree. The column is physically double precision, so the
    walk is `col >= lo AND col < hi ORDER BY col LIMIT 1`: ordinary numeric
    comparison, no collation involved. It still needs the index, and it needed
    it for a reason that only showed up on the live database: without one, a
    `number` column times out and the degradation message names an index the
    builder was never going to create — a dead-end instruction to whoever
    reads it.
    """
    if declared == "number":
        return f'("{column}")'
    return f'(lower("{column}") COLLATE "C", "{column}" COLLATE "C")'


# ---------------------------------------------------------------------------
# Numeric prefixes — a superset of ranges, then the exact test in Python
# ---------------------------------------------------------------------------

def _mirror_negative(ranges):
    """Mirror ascending `[lo, hi)` ranges onto the negative axis, ASCENDING.

    Negating a half-open `[lo, hi)` gives `(-hi, -lo]` — closed on the RIGHT.
    The consumer (`_numeric_values`) applies every range as `col >= lo AND
    col < hi`, so a literal mirror silently drops `-lo` itself, and `-lo` is
    exactly `-d * 10^k`: the roundest, likeliest values there are. Live proof
    before this fix — `bonding_map.y` stores `-9.0`, and `prefix=-9` answered
    `values: [], truncated: false, unavailable_reason: null` while `prefix=-`
    happily returned `-9`. A hole, not the "harmless overlap" the old comment
    claimed, and the authoritative Python test at the bottom of the seek loop
    could not rescue it because the row was never selected in the first place.

    So the mirrored upper bound is widened by ONE ULP. Ranges only have to be a
    superset — `canonical_key_value` decides membership — so a bound that is one
    float too wide costs at most one probe, while one too narrow loses values.
    """
    out = []
    for lo, hi in ranges:
        m_lo = None if hi is None else -hi
        m_hi = None if lo is None else math.nextafter(-lo, math.inf)
        out.append((m_lo, m_hi))
    # An unbounded low end IS the most negative range; -inf sorts it there
    # without None ever reaching a comparison.
    return sorted(out, key=lambda r: -math.inf if r[0] is None else r[0])


def numeric_prefix_ranges(prefix: str):
    """Ascending [lo, hi) ranges that CONTAIN every number whose canonical
    string starts with `prefix`. `None` bound = unbounded on that side.

    Returning a superset is the point: the ranges only exist to keep the seek
    loop off values it can never want. `[]` means "no number can start with
    this" (e.g. 'abc') — a legitimately empty answer, not a failure.

    '9' is not one range: 9, 90..99, 900..999 all start with '9'. Walking
    upward from 9 instead would burn the whole probe budget on 10..89.
    """
    p = (prefix or "").strip()
    if not p:
        return [(None, None)]
    if p == "-":
        return [(None, 0.0)]
    negative = p.startswith("-")
    body = p[1:] if negative else p

    if _DIGITS_RE.match(body):
        d = int(body)
        if d == 0:
            # Canonical integers never carry a leading zero, so '0' can only
            # start '0' itself or '0.xxx'.
            ranges = [(0.0, 1.0)]
        else:
            ranges = []
            top = max(0, _MAX_MAGNITUDE - len(body))
            for k in range(0, top + 1):
                scale = 10 ** k
                # The last magnitude is left OPEN above (see _MAX_MAGNITUDE):
                # closing it made every value past it unreachable in exactly the
                # way the negative mirror below used to drop its endpoints.
                hi = None if k == top else float((d + 1) * scale)
                ranges.append((float(d * scale), hi))
        if not negative:
            return ranges
        return _mirror_negative(ranges)

    if _DECIMAL_RE.match(body):
        decimals = len(body.split(".")[1])
        lo = float(body)
        hi = lo + (10.0 ** -decimals)
        return _mirror_negative([(lo, hi)]) if negative else [(lo, hi)]

    # Not a possible start of any canonical number ('abc', '1e5', '1.2.3').
    return []


# ---------------------------------------------------------------------------
# The lookup
# ---------------------------------------------------------------------------

def _resolve_target(table: str, column: str):
    """Declaration check (INV-F3-3) -> (Column, declared type).

    `table_config` is the authority, not the physical schema: a column that
    exists in the database but is undeclared is not a suggestible column.
    """
    from database import crud, models

    table = (table or "").strip()
    column = (column or "").strip()
    cfg = crud.TABLE_CONFIG.get(table)
    if not isinstance(cfg, dict):
        raise SuggestValidationError(404, f"선언되지 않은 테이블입니다: {table!r}")
    col_types = cfg.get("column_types")
    if not isinstance(col_types, dict) or column not in col_types:
        raise SuggestValidationError(
            400, f"'{table}'에 선언되지 않은 컬럼입니다: {column!r}")

    # The DECLARED type decides before the physical schema does: a datetime
    # column is refused for being a datetime, not for happening to be missing.
    declared = col_types.get(column)
    if declared == "datetime":
        # Refuse instead of inventing a datetime canonicalisation - that would
        # be the second normalisation INV-F3-4 exists to prevent.
        raise SuggestValidationError(
            400, f"날짜/시간 컬럼은 값 제안을 지원하지 않습니다: {table}.{column}")

    model = models.DYNAMIC_TABLES.get(table)
    if model is None:
        raise SuggestValidationError(404, f"모델이 준비되지 않은 테이블입니다: {table!r}")
    col = model.__table__.c.get(column)
    if col is None:
        raise SuggestValidationError(
            400, f"'{table}' 물리 테이블에 아직 없는 컬럼입니다: {column!r} (스키마 동기화 필요)")
    return col, declared


def _canonical(value, declared):
    from map_overlay import canonical_key_value
    out = canonical_key_value(value, declared)
    return "" if out is None else out


# Why the seek loop stopped. The distinction is the whole difference between
# "here are the first N of more" and "I could not answer".
STOP_BUDGET = "budget"      # probe cap reached - the values so far ARE the first N
STOP_DEADLINE = "deadline"  # ran out of time - the list would misrepresent


def _stop_reason(probes, budget, deadline):
    """Why the loop should stop, or None to keep going.

    `deadline` IS NOT A LATENCY BOUND, and the name of the knob behind it
    (`timeout_ms`) reads like one. The clock is tested HERE, before a probe is
    issued — so a probe that starts one microsecond under the deadline still runs to
    completion, bounded only by the session `statement_timeout` (also `timeout_ms`).
    The true worst case is therefore `2 * timeout_ms`; measured 1901 ms against a
    declared 1500 (1.27x, live, 2026-07-30).

    Left as it is on purpose. Bounding total latency to `timeout_ms` means setting
    `statement_timeout` to the REMAINING budget before every probe, which is one
    extra round trip per probe on the hot path — 21 of them in a typical 20-value
    answer. That taxes every healthy request to tighten a worst case that only
    occurs when the system is already degraded. The honest fix was to stop implying
    a bound that does not exist and to report the measured cost instead:
    `elapsed_ms` is in every response, so a caller never has to trust this number.
    """
    if time.monotonic() > deadline:
        return STOP_DEADLINE
    if probes >= budget:
        return STOP_BUDGET
    return None


def text_seek_query(col, folded: str, is_pg: bool, cursor=None):
    """THE seek statement — one definition, issued by `_text_values` AND explained
    by the builder's plan check.

    Public and factored out for exactly one reason: a plan check that rebuilds the
    query itself is checking a query nobody runs. The `COLLATE "C"` lesson is what
    that costs — an index can exist, be chosen by the planner, and still be linear
    in the table size, and the only evidence is the plan of THIS statement. If the
    two drifted apart, the check would keep passing while the endpoint kept
    degrading.

    `col != ''` NARROWS the walk; it is not the guarantee. It cannot be:
    whitespace-only values are non-empty in SQL and still canonicalise to ''.
    `not canon` in the caller is what actually keeps blanks out of the answer.
    """
    lk_expr = byte_order(sa.func.lower(col), is_pg)
    cv_expr = byte_order(col, is_pg)
    q = sa.select(sa.func.lower(col).label("lk"), col.label("v")).where(
        col.isnot(None), col != "", *prefix_conditions(col, folded, is_pg))
    if cursor is not None:
        q = q.where(sa.tuple_(lk_expr, cv_expr) >
                    sa.tuple_(sa.literal(cursor[0]), sa.literal(cursor[1])))
    return q.order_by(lk_expr, cv_expr).limit(1)


def _text_values(db, col, declared, prefix, want, budget, deadline, is_pg):
    """Loose index scan over the DISTINCT text values of `col`.

    One seek per value returned: `(lower(col), col) > (last_lower, last_value)`
    ordered by the same pair is a single index descent on the suggestion index.
    """
    folded = db_fold(db, prefix or "")

    values, seen = [], set()
    cursor = None
    probes = 0
    stop = None
    while len(values) < want:
        stop = _stop_reason(probes, budget, deadline)
        if stop:
            break
        row = db.execute(text_seek_query(col, folded, is_pg, cursor)).first()
        probes += 1
        if row is None:
            break
        cursor = (row.lk, row.v)
        canon = _canonical(row.v, declared)
        # `row.lk` is the DATABASE's lower(col) — the very value the range was
        # compared against and the index was built on. Re-testing with Python's
        # `canon.lower()` instead would re-introduce the second folding
        # implementation `db_fold` exists to remove, and would then REJECT rows
        # the range correctly selected (a stored U+00C4 matches the range and
        # fails a Python-folded startswith). Blank-rejection stays on `canon`:
        # that is a question about the VALUE, not about the fold.
        if not canon or not row.lk.startswith(folded) or canon in seen:
            continue
        seen.add(canon)
        values.append(canon)
    return values, stop


def _numeric_values(db, col, declared, prefix, want, budget, deadline, is_pg):
    """Loose index scan over the DISTINCT numeric values of `col`.

    Physically Float, so the prefix cannot be a text range; the ranges from
    `numeric_prefix_ranges` narrow the walk and `canonical_key_value` decides
    every membership question.
    """
    canon_prefix = _canonical(prefix, "number") if prefix else ""
    ranges = numeric_prefix_ranges(canon_prefix)

    values, seen = [], set()
    probes = 0
    for lo, hi in ranges:
        if len(values) >= want:
            break
        cursor = None
        while len(values) < want:
            stop = _stop_reason(probes, budget, deadline)
            if stop:
                return values, stop
            conds = [col.isnot(None)]
            if lo is not None:
                conds.append(col >= lo)
            if hi is not None:
                conds.append(col < hi)
            if cursor is not None:
                conds.append(col > cursor)
            row = db.execute(
                sa.select(col.label("v")).where(*conds).order_by(col.asc()).limit(1)
            ).first()
            probes += 1
            if row is None:
                break  # this range is exhausted; move to the next magnitude
            cursor = row.v
            canon = _canonical(row.v, declared)
            if not canon or not canon.startswith(canon_prefix) or canon in seen:
                continue
            seen.add(canon)
            values.append(canon)
    # Every range ran to exhaustion -> the list is complete (the caller still
    # trims a (limit + 1)-th value and reports that as truncated).
    return values, None


def suggest_values(db, table: str, column: str, prefix: str = "", limit=None,
                   settings: dict = None) -> dict:
    """(table, column, prefix) -> distinct values + whether the list was cut.

    Raises SuggestValidationError for anything the caller got wrong. Anything
    the DATABASE cannot deliver comes back as `unavailable_reason` with no
    values — never as a plausible-looking short list.
    """
    # One config snapshot per request: hot reload applies from the next request,
    # and nothing can shift underneath a single answer.
    if settings is None:
        settings = resolve_settings(load_config())

    col, declared = _resolve_target(table, column)
    prefix = "" if prefix is None else str(prefix)

    min_len = settings["min_prefix_length"]
    if len(prefix) < min_len:
        raise SuggestValidationError(
            400, f"제안을 받으려면 최소 {min_len}자를 입력해야 합니다 (입력 {len(prefix)}자).")

    try:
        limit = settings["default_limit"] if limit is None else int(limit)
    except (TypeError, ValueError):
        raise SuggestValidationError(400, f"limit은 정수여야 합니다: {limit!r}")
    limit = max(1, min(limit, settings["max_limit"]))

    result = {
        "table": table, "column": column, "prefix": prefix,
        "values": [], "truncated": False, "limit": limit,
        "unavailable_reason": None,
        # THE SUCCESS PATH REPORTS ITS OWN COST (F7). Set on every exit, including
        # the unavailable ones - a caller that wants to back off needs the number
        # whether the answer arrived or not.
        "elapsed_ms": 0,
        # None = the answer cost what it should. Set = the answer is CORRECT but
        # cost more than `slow_warn_ms`, and this names why. Deliberately a second
        # field rather than a flag on `unavailable_reason`: the values are good and
        # the caller must still use them.
        "slow_reason": None,
    }
    # `perf_counter`, NOT `monotonic`, and the two are used side by side on purpose:
    #   - `deadline` below stays on `monotonic` — it is a wall-clock cut-off, and
    #     15 ms of coarseness against a 1500 ms budget is 1%.
    #   - `elapsed_ms` is a MEASUREMENT compared against a 50 ms threshold, and
    #     `time.monotonic()` on Windows resolves to 15.625 ms (verified via
    #     `get_clock_info`). Quantising the measurement in 16 ms steps would put
    #     ~31% noise on the one comparison this field exists to make, so a 60 ms
    #     answer could report 48 and stay silent. `perf_counter` resolves to 100 ns.
    started = time.perf_counter()

    is_pg = bool(db.bind is not None and db.bind.dialect.name == "postgresql")
    timeout_ms = settings["timeout_ms"]
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    # One extra value is what proves truncation: if a (limit + 1)-th distinct
    # value exists, the list the caller sees is NOT all of them.
    want = limit + 1
    # The declared budget is respected even when it is below `want`: an operator
    # who caps probes lower than the limit gets fewer values AND `truncated`,
    # not a quietly raised cap.
    budget = max(1, settings["max_probe_values"])

    try:
        if is_pg:
            # SET LOCAL dies with this transaction (get_db closes the session),
            # so it cannot leak into another request on a pooled connection.
            db.execute(sa.text(f"SET LOCAL statement_timeout = {int(timeout_ms)}"))
        runner = _numeric_values if declared == "number" else _text_values
        values, stop = runner(db, col, declared, prefix,
                              want, budget, deadline, is_pg)
    except Exception as e:
        # A statement timeout poisons the transaction - without this rollback
        # every later query on the session fails too.
        try:
            db.rollback()
        except Exception:
            pass
        result["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
        result["unavailable_reason"] = _diagnose(
            db, table, column, e, timeout_ms, is_pg, settings=settings)
        logger.warning("[Suggest] %s.%s unavailable: %s", table, column, e)
        return result

    # STOP_DEADLINE is not truncation. Running out of TIME is the shape a
    # missing prefix index takes: each seek degrades to a sequential scan, the
    # loop dies after a handful of them, and what is left looks like a short but
    # complete pick list. That is the "wrong list served as normal" INV-F3-6
    # forbids - so it degrades to a named reason with NO values, exactly like a
    # hard failure. STOP_BUDGET is different: those values are genuinely the
    # first N, so they are kept and flagged.
    if stop == STOP_DEADLINE:
        result["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
        result["unavailable_reason"] = _diagnose(
            db, table, column, TimeoutError("seek loop deadline exceeded"),
            timeout_ms, is_pg, timed_out=True, settings=settings)
        logger.warning("[Suggest] %s.%s hit the %sms deadline after %s value(s).",
                       table, column, timeout_ms, len(values))
        return result

    truncated = stop == STOP_BUDGET
    if len(values) > limit:
        values = values[:limit]
        truncated = True
    result["values"] = values
    result["truncated"] = bool(truncated)

    # A CORRECT answer that cost too much is still a defect, and until now it was
    # the ONE defect this module could not report: every diagnostic above runs on a
    # failure path. `wafer_process` sat 20x over budget answering
    # `unavailable_reason: null, truncated: false` for as long as nobody re-ran the
    # index builder, and the next table to cross `index_min_rows` would have
    # reproduced it silently. So the success path measures itself.
    result["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
    warn_ms = settings["slow_warn_ms"]
    if result["elapsed_ms"] > warn_ms:
        result["slow_reason"] = _slow_reason(
            db, table, column, result["elapsed_ms"], warn_ms, is_pg, settings)
    return result


# One WARNING per (table, column) per process. The condition is a property of the
# COLUMN, not of the keystroke: a client types 17 characters and issues 17 requests,
# so per-request warnings would bury the actionable message under 16 copies of
# itself. Bounded by the number of declared columns (~50 on the live database).
_slow_warned = set()


def _slow_reason(db, table, column, elapsed_ms, warn_ms, is_pg, settings) -> str:
    """Name the cost of a SUCCESSFUL answer, and what to do about it.

    Runs only when the answer was already slow, so the catalog reads it performs
    are a small fraction of a cost that has already been paid — the per-request
    price of the fast path stays exactly zero.
    """
    msg = f"응답이 {elapsed_ms}ms 걸렸습니다 (예산 {warn_ms}ms)"
    if is_pg:
        try:
            _, advice = _index_advice(db, table, column, settings)
            msg = f"{msg} — {advice}"
        except Exception as e:
            # Diagnosis is the bonus, not the signal. Losing it must not cost the
            # measurement, which is the part the caller actually branches on.
            logger.warning("[Suggest] slow-path diagnosis failed for %s.%s: %s",
                           table, column, e)
    key = (table, column)
    if key in _slow_warned:
        logger.debug("[Suggest] %s.%s slow again: %s", table, column, msg)
    else:
        _slow_warned.add(key)
        logger.warning("[Suggest] %s.%s %s", table, column, msg)
    return msg


def _diagnose(db, table, column, exc, timeout_ms, is_pg, timed_out=False,
              settings=None) -> str:
    """Name the ACTUAL cause.

    Same rule the dashboard's degraded stats learned the hard way: a message
    that blames the index unconditionally sends whoever is on call to tune an
    index that was never the problem. The index is only named when it is
    genuinely absent — and "absent" here means "not USABLE", because an INVALID
    index is worse than a missing one (see `_index_state`).

    A named cause is only half of it: the message also has to leave the reader
    somewhere they can act (`_why_not_a_target`).
    """
    detail = (str(exc).strip().splitlines() or [""])[0][:200]
    lowered = detail.lower()
    if timed_out or (is_pg and ("timeout" in lowered or "canceling statement" in lowered)):
        if not is_pg:
            # No catalog to consult - do not name an index that may not be the
            # story on this backend.
            return f"조회 시간 초과 ({timeout_ms}ms) — [{type(exc).__name__}] {detail}"
        state, advice = _index_advice(db, table, column, settings)
        if state == _INDEX_USABLE:
            # The index is fine, so the exception detail IS the story.
            return f"조회 시간 초과 ({timeout_ms}ms) — {advice} [{type(exc).__name__}] {detail}"
        return f"조회 시간 초과 ({timeout_ms}ms) — {advice}"
    return f"값 조회 실패 — [{type(exc).__name__}] {detail or '상세 없음'}"


def _index_advice(db, table, column, settings) -> tuple:
    """(index_state, WHAT TO DO ABOUT IT). PostgreSQL only; catalog reads.

    Split out of `_diagnose` so the SLOW-BUT-SUCCESSFUL path can reach the same
    advice without borrowing the timeout path's framing. That framing was the
    reason the advice was unreachable: every sentence here began "조회 시간 초과",
    which is false for an answer that arrived — so a slow success either had to lie
    about timing out or say nothing, and it said nothing. Same words, one caller
    supplying the prefix.
    """
    idx = suggest_index_name(table, column)
    state = _index_state(db, idx)
    if state == _INDEX_INVALID:
        # to_regclass resolves an INVALID index perfectly well, so a name check
        # alone reports this one as healthy while the planner refuses to use it
        # forever. `CREATE INDEX CONCURRENTLY` leaves exactly this behind when it
        # is cancelled - and the guide warns that a worker sitting `idle in
        # transaction` makes that step look hung, so it is the cancel people
        # actually perform. Worse, the builder's `IF NOT EXISTS` then skips the
        # name, so re-running it fixes nothing. Say the repair out loud.
        return state, (
            f"인덱스 {idx} 가 INVALID 상태입니다(CONCURRENTLY 생성이 중단된 흔적). "
            f"플래너가 사용하지 않으며 setup_db_performance.py 를 다시 돌려도 이름이 "
            f"있어 건너뜁니다. REINDEX INDEX CONCURRENTLY {idx}; 또는 "
            f"DROP INDEX CONCURRENTLY {idx}; 후 재실행하세요.")
    if state == _INDEX_ABSENT:
        return state, (f"접두 인덱스 {idx} 가 없습니다. "
                       + _why_not_a_target(db, table, column, settings))
    return state, f"인덱스 {idx} 는 존재합니다."


def _why_not_a_target(db, table, column, settings) -> str:
    """The ACTIONABLE half of a missing-index message.

    "run setup_db_performance.py" is a dead end whenever the builder was never
    going to create this index: an `index_exclude` entry, an `index_columns`
    list this column is not in, or a table under `index_min_rows` (the live
    database has 15 such tables). Telling an operator to re-run a script that
    will skip the column again is the same failure the `number`-column fix
    already hit once - that fix covered one CASE, this covers the RULE, by
    asking `index_targets` itself, the single owner of the policy.
    """
    settings = settings if isinstance(settings, dict) else resolve_settings(load_config())
    try:
        from database import crud
        cfg = crud.TABLE_CONFIG.get(table)
        # The row count is the ONLY part that needs the catalog, and it decides
        # exactly one of the four answers. Losing it must not cost the other
        # three - they are pure config questions.
        rows = _approx_row_count(db, table)
        targets = index_targets({table: cfg}, settings, {table: rows or 0})
        if any(t == table and c == column for t, c, _, _ in targets):
            return "server/scripts/setup_db_performance.py 를 실행하세요."
        if column in set((settings.get("index_exclude") or {}).get(table) or ()):
            return (f"이 컬럼은 suggest_config.json 의 index_exclude['{table}'] 에 "
                    f"제외되어 있어 빌더가 만들지 않습니다. 제외를 풀고 재실행하세요.")
        if table in (settings.get("index_columns") or {}):
            return (f"suggest_config.json 의 index_columns['{table}'] 목록에 이 컬럼이 "
                    f"없어 빌더가 만들지 않습니다. 목록에 추가하고 재실행하세요.")
        min_rows = settings.get("index_min_rows", DEFAULTS["index_min_rows"])
        size = f"약 {rows}행으로" if rows is not None else "행 수를 확인하지 못했으나"
        return (f"이 테이블은 {size} index_min_rows({min_rows}) 미만이라 "
                f"자동 대상이 아닙니다. suggest_config.json 의 "
                f"index_columns['{table}'] 에 이 컬럼을 선언하고 재실행하세요.")
    except Exception as e:
        logger.warning("[Suggest] target diagnosis failed for %s.%s: %s", table, column, e)
        return ("server/scripts/setup_db_performance.py 를 실행하세요 "
                "(대상 여부는 suggest_config.json 의 index_columns / index_exclude / "
                "index_min_rows 확인).")


def _approx_row_count(db, table):
    """pg_class.reltuples, or None when it cannot be read. Never counts rows.

    This runs on the timeout path, where a real `count(*)` would be a second
    way to hang the same request.
    """
    try:
        n = db.execute(
            sa.text("SELECT reltuples::bigint FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'public' AND c.relname = :t"), {"t": table}
        ).scalar()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        return None
    return None if n is None else max(0, int(n))


_INDEX_USABLE = "usable"
_INDEX_INVALID = "invalid"
_INDEX_ABSENT = "absent"


def _index_state(db, index_name: str):
    """Catalog check, used ONLY on the failure path (never per request).

    `indisvalid AND indisready` is the question, not existence. An index the
    planner will never touch is not an index, and reporting it as present sends
    the reader off to look for a different cause than the one they have.
    """
    try:
        row = db.execute(
            sa.text("SELECT i.indisvalid AND i.indisready FROM pg_index i "
                    "JOIN pg_class ci ON ci.oid = i.indexrelid "
                    "JOIN pg_namespace n ON n.oid = ci.relnamespace "
                    "WHERE n.nspname = 'public' AND ci.relname = :n"),
            {"n": index_name},
        ).scalar()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        return _INDEX_ABSENT
    if row is None:
        return _INDEX_ABSENT
    return _INDEX_USABLE if row else _INDEX_INVALID


# ---------------------------------------------------------------------------
# Plan shape — "the index exists" is NOT the property that matters
# ---------------------------------------------------------------------------

# WHY THIS READS `Index Cond` / `Filter` / `Rows Removed by Filter` AND NOT THE
# NODE TYPE. A checker that records "was it an index scan?" passes the worst plan
# this module has ever measured. Live `bonding_map.base` WITHOUT the `COLLATE "C"`
# decoration:
#
#     Index Only Scan using idx_bonding_map_base        <-- an index scan!
#       Index Cond: (base IS NOT NULL)                  <-- the prefix is NOT here
#       Filter: ((base)::text ~~ 'C%'::text)            <-- it is here instead
#       Rows Removed by Filter: 548300                  <-- so the cost is O(n)
#                                                           569 ms for 3 values
#
# The planner chose the index and then walked the whole thing. The node type is
# identical to the healthy plan's; the three lines above are what differ. Note also
# that a `Filter` line by itself proves NOTHING — the HEALTHY plan has one too
# (`base <> ''`), discarding 0 rows. It is the DISCARD COUNT and the absence of the
# prefix bounds from `Index Cond` that separate them.
PLAN_OK = "ok"
PLAN_NO_INDEX_COND = "no_index_cond"            # Seq Scan, or a bitmap/sort path
PLAN_PREFIX_NOT_A_RANGE = "prefix_not_a_range"  # index chosen, prefix left to Filter
PLAN_FILTER_DISCARDS = "filter_discards"        # cost is linear in the table

_RE_INDEX_COND = re.compile(r"^\s*Index Cond:\s*(.*)$")
_RE_FILTER = re.compile(r"^\s*(?:Filter|Index Recheck):\s*(.*)$")
_RE_REMOVED = re.compile(r"Rows Removed by (?:Filter|Index Recheck):\s*(\d+)")

# A range-shaped seek discards O(1) rows. This tolerance is deliberately small: a
# LIMIT 1 seek can only discard rows it WALKED PAST, so a large count means the walk
# really was long — which is the defect, not a false positive, even when the index
# is being used as a range.
_MAX_DISCARDED = 100


def classify_seek_plan(plan_text, expect_range: bool = True,
                       max_discarded: int = _MAX_DISCARDED) -> tuple:
    """(verdict, reasons, discarded) for one `EXPLAIN ANALYZE` of `text_seek_query`.

    `plan_text` is the raw EXPLAIN output — a string or an iterable of lines.
    `expect_range` is False for the empty-prefix probe, where there is no prefix to
    turn into a range and only the discard count is meaningful.

    Pure text in, verdict out: no database, so the failing plans above are
    regression fixtures rather than something that needs 1.7M rows to reproduce.
    """
    lines = plan_text.splitlines() if isinstance(plan_text, str) else list(plan_text)
    index_conds, discarded = [], 0
    for line in lines:
        m = _RE_INDEX_COND.match(line)
        if m:
            index_conds.append(m.group(1))
        m = _RE_REMOVED.search(line)
        if m:
            discarded += int(m.group(1))

    reasons = []
    if not index_conds:
        reasons.append(PLAN_NO_INDEX_COND)
    elif expect_range and not any(">=" in c or "<" in c for c in index_conds):
        # The index WAS used, but only for `IS NOT NULL` — the prefix comparison got
        # pushed to a Filter, so every entry is read and thrown away. This is the
        # missing-`COLLATE "C"` signature, and it is invisible to a node-type check.
        reasons.append(PLAN_PREFIX_NOT_A_RANGE)
    if discarded > max_discarded:
        reasons.append(PLAN_FILTER_DISCARDS)
    return (PLAN_OK if not reasons else "bad"), reasons, discarded


# ---------------------------------------------------------------------------
# Index targets — consumed by server/scripts/setup_db_performance.py
# ---------------------------------------------------------------------------

def index_targets(table_config: dict, settings: dict, row_counts: dict) -> list:
    """[(table, column, index_name, definition)] that SHOULD have an index.

    Policy, in order:
      - `index_columns[table]` declared -> exactly those columns (size ignored;
        an explicit declaration outranks the heuristic).
      - otherwise -> every suggestible column, but only once the table is at
        least `index_min_rows` rows. Small tables scan fine and paying disk for
        them buys nothing.
      - `index_exclude[table]` always wins.

    "Suggestible" is every declared column EXCEPT datetime, which the endpoint
    refuses outright. That deliberately includes `number`: the endpoint answers
    for those, so if the builder skipped them they would answer by timing out.

    `row_counts` is supplied by the caller (the builder script reads pg_class)
    so this stays a pure function and is testable without a database.
    """
    forced = settings.get("index_columns") or {}
    excluded = settings.get("index_exclude") or {}
    min_rows = settings.get("index_min_rows", DEFAULTS["index_min_rows"])

    targets = []
    for table, cfg in sorted((table_config or {}).items()):
        if not isinstance(cfg, dict):
            continue
        col_types = cfg.get("column_types")
        if not isinstance(col_types, dict):
            continue
        # Physically absent tables have no row count entry - nothing to index.
        if table not in row_counts:
            continue
        suggestible = {c: t for c, t in col_types.items() if t != "datetime"}
        if table in forced:
            wanted = [c for c in forced[table] if c in suggestible]
            # A forced column that is undeclared or datetime CANNOT be indexed,
            # but dropping it in silence leaves the operator reading their own
            # `index_columns` entry as if it were in effect - the same
            # config-says-one-thing-behaviour-says-another that
            # `_resolve_column_map` refuses to allow.
            for c in forced[table]:
                if c not in suggestible:
                    logger.warning(
                        "[Suggest] index_columns['%s'] names %r, which is not a "
                        "suggestible column (undeclared, or declared datetime); "
                        "no index will be built for it.", table, c)
        elif row_counts.get(table, 0) >= min_rows:
            wanted = list(suggestible)
        else:
            wanted = []
        skip = set(excluded.get(table) or ())
        for column in wanted:
            if column in skip:
                continue
            targets.append((table, column, suggest_index_name(table, column),
                            suggest_index_definition(column, suggestible[column])))

    for table, column in SYSTEM_PREFIX_INDEX_TARGETS:
        if table in row_counts and column not in set(excluded.get(table) or ()):
            targets.append((table, column, suggest_index_name(table, column),
                            suggest_index_definition(column)))
    return targets
