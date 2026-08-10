"""Row/cell audit history paging - the ceiling on `/history` fetches.

WHAT WAS WRONG
    `GET /tables/{t}/rows/{id}/history` and its `/cells/{col}/history` sibling
    both ended in `.order_by(timestamp.desc()).all()`. No LIMIT. One row click
    loaded that row's ENTIRE audit history and modelled all of it through
    pydantic, so the cost of a click grew with everything ever ingested.

    Measured on the isolated `assy_qa` database (2026-08-11), one row inflated to
    300,019 audit entries inside a 1,131,008-row `audit_logs`:

        row  history, no LIMIT : 300,019 rows, ~54 MB of column text, 3,462 ms
                                 to fetch, plan sorted on disk (53 MB temp)
        cell history, no LIMIT :  12,000 rows, ~2.2 MB, 218 ms

    Both figures are BEFORE pydantic sees a single row.

WHAT THIS MODULE IS
    The paging primitive both endpoints share: config-driven page size, a
    `(timestamp, id)` keyset cursor, and a response that SAYS it was truncated.

WHY KEYSET AND NOT OFFSET
    Ruled out by the proposal, and measured here. With the supporting index in
    place, page 51 costs:

        keyset  (timestamp, id) < (?, ?)  ->  18 buffers, 0.114 ms
        OFFSET 10000                      ->  2,311 buffers, 3.447 ms

    and OFFSET degrades linearly from there while keyset does not. The
    correctness argument is the stronger one though: `audit_logs` grows at the
    head while a user pages down it, so ingestion during paging makes OFFSET
    hand out rows twice and skip others. A cursor is immune - it names a
    position in the data, not a count of rows someone already saw.

WHY THE PREDICATE IS A ROW-VALUE COMPARISON AND NOT THE `OR` EXPANSION
    They are logically identical and they do NOT plan the same. Same page, same
    index, measured:

        (timestamp, id) < (ts, id)                   Index Cond,    18 buffers, 0.114 ms
        timestamp < ts OR (timestamp = ts AND ...)   Filter,     2,311 buffers, 4.949 ms

    Expanded to OR, PostgreSQL can no longer push the bound into the btree, so
    it re-walks every entry from the top of the row's history and throws away
    the ones already seen - which is precisely the cost this change exists to
    remove. Do not "simplify" `sa.tuple_` away.

WHY `id` IS IN THE SORT KEY AT ALL
    `timestamp` alone is not a stable order and ties are the NORMAL case here,
    not an edge one: a batch write stamps every audit row in the transaction
    from the same `now()`. Under an unstable sort a cursor cannot say where it
    stopped, so the next page would repeat and drop rows inside the tie group.

TRUNCATION IS ALWAYS SPOKEN
    Same invariant `value_suggest` states as INV-F3-1, and the same word for it
    (`truncated`). A capped list that looks exactly like a complete one is a
    silent wrong answer: the timeline would show 200 entries and the reader
    would conclude that is the row's whole history. So the response is an
    envelope, not a bare list, and it carries `truncated` + `next_cursor`.
"""
import base64
import binascii
import json
import logging
from datetime import datetime

import sqlalchemy as sa

import paths

logger = logging.getLogger(__name__)

CONFIG_PATH = paths.config_path("audit_history_config.json")

# Every knob below is a DEFAULT; audit_history_config.json overrides it. A
# missing config file is normal operation - these values are the shipped policy.
DEFAULTS = {
    # Page size when the caller names none. The proposal's figure. Chosen to be
    # a screenful several times over (the timeline sidebar shows ~15 at a time)
    # so that "더 보기" is rare in practice, while still being ~1,500x smaller
    # than the deep row measured above.
    "default_limit": 200,
    # Ceiling on what a caller may ask for. A cap the client can raise without
    # bound is not a cap: `?limit=1000000` would restore exactly the unbounded
    # fetch this module was written to remove.
    "max_limit": 1000,
}


class CursorError(ValueError):
    """A cursor that cannot be decoded -> 400, never a silent restart.

    Silently ignoring a bad cursor is worse than refusing it: the endpoint would
    answer with page 1 while the client believes it received page 2, and a
    "더 보기" loop would append the same rows forever without anything failing.
    """


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config(path: str = None) -> dict:
    """Load audit_history_config.json. Missing file -> {} (all defaults apply)."""
    p = path or CONFIG_PATH
    try:
        with open(p, "r", encoding="utf-8-sig") as f:
            raw = json.load(f)
        return raw if isinstance(raw, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.warning("[AuditHistory] failed to load config %s: %s", p, e)
        return {}


def resolve_settings(config: dict = None) -> dict:
    """Resolved settings - always every key, always usable.

    A malformed knob falls back to its default with a warning. Folding a typo
    into a number silently is how a config file starts lying about what is in
    force; taking the endpoint down over one is worse.
    """
    declared = config if isinstance(config, dict) else {}
    resolved = dict(DEFAULTS)
    for k, default in DEFAULTS.items():
        if k not in declared:
            continue
        v = declared[k]
        # bool is a subclass of int - True must not silently become 1.
        if isinstance(v, bool) or not isinstance(v, int) or v <= 0:
            logger.warning("[AuditHistory] '%s' must be a positive integer (got %r); using %s.",
                           k, v, default)
            continue
        resolved[k] = v
    if resolved["default_limit"] > resolved["max_limit"]:
        logger.warning("[AuditHistory] default_limit (%s) > max_limit (%s); clamping.",
                       resolved["default_limit"], resolved["max_limit"])
        resolved["default_limit"] = resolved["max_limit"]
    return resolved


def resolve_limit(requested, settings: dict = None) -> int:
    """The page size in force for one request. Out-of-range is CLAMPED, not refused.

    A limit is a safety ceiling, not an assertion about the caller's intent, so
    a client that asks for 5,000 gets `max_limit` rows and a `truncated: true`
    telling it there is more - it does not get a 400 that breaks the sidebar.
    A cursor is the opposite (see `CursorError`): there, guessing is unsafe.
    """
    s = settings if settings is not None else resolve_settings(load_config())
    if requested is None:
        return s["default_limit"]
    try:
        n = int(requested)
    except (TypeError, ValueError):
        return s["default_limit"]
    if n <= 0:
        return s["default_limit"]
    return min(n, s["max_limit"])


# ---------------------------------------------------------------------------
# Cursor
# ---------------------------------------------------------------------------
#
# Opaque to the caller, base64url so it survives a query string untouched
# (a bare ISO timestamp carries `+`, which decodes to a space).
#
# The timestamp is round-tripped through `isoformat()` VERBATIM, preserving
# whether it was tz-aware. That is deliberate and it is not cosmetic: PostgreSQL
# hands back aware datetimes for this `DateTime(timezone=True)` column and SQLite
# hands back naive ones, and the decoded value is bound straight back into a
# comparison against that same column. Normalising to UTC here would bind an
# aware value against SQLite's naive storage and compare two different things.

def encode_cursor(timestamp: datetime, log_id: int) -> str:
    """Position of the last row on a page, as an opaque token."""
    raw = f"{timestamp.isoformat()}|{int(log_id)}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def decode_cursor(token: str):
    """`(timestamp, id)` from a cursor, or raise CursorError."""
    if not isinstance(token, str) or not token:
        raise CursorError("cursor must be a non-empty string")
    pad = "=" * (-len(token) % 4)
    try:
        raw = base64.urlsafe_b64decode(token + pad).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError) as e:
        raise CursorError(f"cursor is not valid base64url ({e})")
    ts_str, sep, id_str = raw.rpartition("|")
    if not sep:
        raise CursorError("cursor is missing its 'timestamp|id' separator")
    try:
        return datetime.fromisoformat(ts_str), int(id_str)
    except ValueError as e:
        raise CursorError(f"cursor does not carry a 'timestamp|id' pair ({e})")


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------

def order_desc(model):
    """The ONE sort order for history. Both endpoints and the cursor share it."""
    return (model.timestamp.desc(), model.id.desc())


def apply_cursor(query, model, cursor: str):
    """Restrict `query` to rows strictly after `cursor` in `order_desc` order.

    `None` and `""` both mean "no cursor - give me the first page", and that is
    a decision, not an oversight: `?cursor=` is what a client that has no cursor
    yet produces when it interpolates an empty variable into the URL. It cannot
    be a LOST position, because `next_cursor` is either a real token or null and
    is never the empty string. Anything else that fails to decode IS a lost
    position and raises (see CursorError).
    """
    if not cursor:
        return query
    ts, log_id = decode_cursor(cursor)
    # Row-value comparison, NOT the OR expansion - see the module docstring.
    return query.filter(sa.tuple_(model.timestamp, model.id) < sa.tuple_(ts, log_id))


def fetch_page(query, model, limit: int, cursor: str = None):
    """One page of history, newest first.

    Returns `(rows, truncated, next_cursor)`.

    Asks the database for `limit + 1` rows and keeps `limit`. The extra row is
    the whole has-more mechanism: it costs one more index entry and it answers
    "is there more?" exactly, where `count(*)` would re-walk the entire history
    - the O(depth) scan this change exists to remove.
    """
    query = apply_cursor(query, model, cursor).order_by(*order_desc(model))
    rows = query.limit(limit + 1).all()
    truncated = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor(rows[-1].timestamp, rows[-1].id) if (truncated and rows) else None
    return rows, truncated, next_cursor
