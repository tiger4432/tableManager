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
    """Load audit_history_config.json. Missing file -> {} (all defaults apply) - held until it changes, a broken one
    said once (`config_watcher.json_object`)."""
    from database import config_watcher

    return config_watcher.json_object(path or CONFIG_PATH, "utf-8-sig")


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


#: Ceiling on the row-total probe below. A MODULE CONSTANT and not a config knob
#: on purpose: it changes nothing an operator tunes - only whether a disclosure
#: reads "15건" or "1,000건 이상" - and every config key is a surface someone has
#: to be told about. `default_limit`/`max_limit` are policy; this is a safety bound.
ROW_TOTAL_PROBE_CAP = 1000


def count_row_history(query, cap: int = None):
    """How many audit entries a row has, as `(count, is_floor)`.

    Same trick `fetch_page` uses for `truncated`: ask for `cap + 1` and let the
    answer's own size say whether it is exact. An honest disclosure must not cost
    an O(depth) scan - this project has already measured a single row inflated to
    300,019 audit entries - so past the cap the caller is told "at least `cap`"
    and `is_floor` is True. Bounded either way.

    Measured on the isolated `assy_qa` copy 2026-08-11 against `idx_audit_row_history`
    `(table_name, row_id, timestamp DESC, id DESC)`: the capped probe is an Index
    Only Scan costing the SAME as the exact count on a real row (0.32 ms vs
    0.39 ms over 5 calls), so the bound buys safety at no measurable price.

    `cap` is read from the module at CALL time, not bound as a default argument -
    a default is frozen at def time and would make the constant untestable.
    """
    cap = ROW_TOTAL_PROBE_CAP if cap is None else cap
    rows = query.with_entities(sa.literal(1)).limit(cap + 1).all()
    n = len(rows)
    return (cap, True) if n > cap else (n, False)


# ---------------------------------------------------------------------------
# Lines (cell-source overhaul, docs/design/CELL_SOURCE_OVERHAUL.md «읽기 — D 분야»)
# ---------------------------------------------------------------------------

#: The kinds a history shows: a write, a withdrawal, a row deleted. A «mark» line (a pin, a rank re-merge) says no
#: column and stays out of the history pages - the audit navigation reaches it.
HISTORY_KINDS = ("write", "withdraw", "deleted", "created")
LINE_BITS = 64


def entry_id(line_id, column):
    """One history entry's id - a line and the column it said. The broadcast builds its lines with this too, so one
    record is the same id on both (client2 compares them with ===)."""
    return "%d:%s" % (int(line_id), column)


def line_bits(db, table_name) -> dict:
    """{column: bit} of `table_name`'s live columns (`lines.bit_map`), in bit order - a line says its columns so."""
    from database import lines

    return dict(sorted(lines.bit_map(db, table_name).items(), key=lambda kv: kv[1]))


def line_table(table_name, bits):
    """t__lines as Core: its value cells are text whatever the column's type (C b9f242763) - read one with
    `line_cell`."""
    from database import lines

    chunks = max(bits.values(), default=0) // LINE_BITS + 1
    return sa.Table(lines.lines_relation(table_name), sa.MetaData(),
                    sa.Column("line_id", sa.Integer), sa.Column("line_kind", sa.String),
                    sa.Column("source_name", sa.String), sa.Column("at", sa.DateTime(timezone=True)),
                    sa.Column("written_by", sa.String), sa.Column("batch", sa.String),
                    sa.Column("row_id", sa.String), sa.Column("business_key_val", sa.String),
                    *[sa.Column("%s_%d" % (kind, n), sa.BigInteger) for n in range(chunks)
                      for kind in ("written", "head", "withdrawn")],
                    *[sa.Column(lines.value_column(name), sa.Text) for name in bits])


def line_cell(types, row, name):
    """A line's value of `name` as its table holds it - `types` is `lines.value_types` (t's physical types, the
    write's own, C 1986aa74b), read once a request - through `crud.line_value`, the one read-side cast."""
    from database import crud, lines

    return crud.line_value(getattr(row, lines.value_column(name)), types.get(name, "string"))


def bit_said(row, bit, kind="written"):
    chunk, place = divmod(bit, LINE_BITS)
    return bool((int(getattr(row, "%s_%d" % (kind, chunk)) or 0) >> place) & 1)


def line_page(db, table_name, row_id, limit, cursor=None, column=None):
    """One page of `row_id`'s lines, newest first by (at, line_id) - the (row_id, at) index - with `column`, the lines
    that said it and the row's deletion. -> (rows, bits, truncated, next_cursor); a page counts lines, not entries.
    A table whose lines are not built (`lines.has_lines`) has none; a bad cursor is refused first, whatever the table."""
    from database import lines

    after = decode_cursor(cursor) if cursor else None
    if not lines.has_lines(db, table_name):
        return [], {}, False, None
    bits = line_bits(db, table_name)
    t = line_table(table_name, bits)
    query = sa.select(t).where(t.c.row_id == row_id, t.c.line_kind.in_(HISTORY_KINDS))
    if column is not None:
        if column not in bits:
            return [], bits, False, None
        chunk, place = divmod(bits[column], LINE_BITS)
        mask = 1 << place
        mask = mask - (1 << LINE_BITS) if mask >= 1 << (LINE_BITS - 1) else mask      # a signed bigint
        query = query.where(sa.or_(t.c["written_%d" % chunk].op("&")(mask) != 0, t.c.line_kind == "deleted"))
    if after:
        query = query.where(sa.tuple_(t.c.at, t.c.line_id) < sa.tuple_(*after))
    rows = db.execute(query.order_by(t.c.at.desc(), t.c.line_id.desc()).limit(limit + 1)).fetchall()
    truncated = len(rows) > limit
    rows = rows[:limit]
    return rows, bits, truncated, (encode_cursor(rows[-1].at, rows[-1].line_id) if truncated and rows else None)


def line_entries(table_name, row, bits, types, column=None, business_key=None, row_deleted=False):
    """A line as today's history entries (schemas.AuditLogResponse fields): one per column it said - withdrawn: no
    value -, or the row-deletion entry (crud.ROW_DELETION_COLUMN, «row deleted», system), or the row-creation entry
    (crud.ROW_CREATION_COLUMN, «row created», system)."""
    from database import crud

    base = {"table_name": table_name, "row_id": row.row_id, "updated_by": row.written_by,
            "transaction_id": row.batch, "business_key": row.business_key_val or business_key,
            "timestamp": row.at, "is_row_deleted": row_deleted}
    if row.line_kind == "deleted":
        return [dict(base, id=entry_id(row.line_id, crud.ROW_DELETION_COLUMN), column_name=crud.ROW_DELETION_COLUMN,
                     new_value="row deleted", source_name="system")]
    if row.line_kind == "created":                 # the grid's «add row» - the row's history begins here (A 11-11)
        return [dict(base, id=entry_id(row.line_id, crud.ROW_CREATION_COLUMN), column_name=crud.ROW_CREATION_COLUMN,
                     new_value="row created", source_name="system")]
    return [dict(base, id=entry_id(row.line_id, name), column_name=name, source_name=row.source_name,
                 new_value=None if bit_said(row, bit, "withdrawn") else line_cell(types, row, name))
            for name, bit in bits.items() if (column is None or name == column) and bit_said(row, bit)]


def count_row_lines(db, table_name, row_id, cap: int = None):
    """How many history lines a row has, as `(count, is_floor)` - `count_row_history`'s bound, over the lines."""
    cap = ROW_TOTAL_PROBE_CAP if cap is None else cap
    from database import lines

    if not lines.has_lines(db, table_name):
        return 0, False
    t = line_table(table_name, {})
    n = len(db.execute(sa.select(sa.literal(1)).select_from(t).where(
        t.c.row_id == row_id, t.c.line_kind.in_(HISTORY_KINDS)).limit(cap + 1)).fetchall())
    return (cap, True) if n > cap else (n, False)


def line_keys(db, table_name, row_ids) -> dict:
    """{row_id: its business key} - the newest line of each row that names one: a deleted row's key, its history's."""
    from database import lines

    if not lines.has_lines(db, table_name):
        return {}
    t = line_table(table_name, {})
    ids, out = list(dict.fromkeys(str(r) for r in row_ids or () if r)), {}
    for i in range(0, len(ids), 1000):
        for row_id, key in db.execute(sa.select(t.c.row_id, t.c.business_key_val).where(
                t.c.row_id.in_(ids[i:i + 1000]), t.c.business_key_val.isnot(None))
                .order_by(t.c.at.asc(), t.c.line_id.asc())).fetchall():
            out[row_id] = str(key)
    return out


def deleted_line_rows(db, table_name, row_ids) -> set:
    """The rows among `row_ids` with a «deleted» line - gone, not unreadable."""
    from database import lines

    if not lines.has_lines(db, table_name):
        return set()
    t = line_table(table_name, {})
    ids, found = list(dict.fromkeys(str(r) for r in row_ids or () if r)), set()
    for i in range(0, len(ids), 1000):
        found.update(r for (r,) in db.execute(sa.select(t.c.row_id).where(
            t.c.row_id.in_(ids[i:i + 1000]), t.c.line_kind == "deleted").distinct()).fetchall())
    return found


def changed_rows(db, table_name, group) -> int:
    """How many rows history group `group` changed in `table_name` - its lines' distinct rows (the (batch) index;
    owner 11-10 «바뀐 행수», counted, never stored)."""
    from admin.audit_cache import in_group

    t = line_table(table_name, {})
    return db.execute(sa.select(sa.func.count(sa.distinct(t.c.row_id))).where(in_group(t.c.batch, group))).scalar()


def group_line_rows(table_name, group):
    """The rows history group `group` wrote lines of in `table_name`, as a statement of row_ids (the grid's
    transaction filter)."""
    from admin.audit_cache import in_group

    t = line_table(table_name, {})
    return sa.select(t.c.row_id).where(in_group(t.c.batch, group))


def group_rows(db, table_name, group, limit) -> list:
    """The rows history group `group` changed in `table_name`, the first written first (its first line's line_id -
    C 11-10), each with that line - who wrote it and when (GET /audit_logs/transaction/{tx_id}; a row, no column, no
    value: owner 11-10 «바뀐 행 네비»). -> [entry fields]"""
    from admin.audit_cache import in_group

    t = line_table(table_name, {})
    first = sa.func.min(t.c.line_id)
    picked = db.execute(sa.select(t.c.row_id, first).where(in_group(t.c.batch, group))
                        .group_by(t.c.row_id).order_by(first.asc()).limit(limit)).fetchall()
    if not picked:
        return []
    said = {row.line_id: row for row in db.execute(sa.select(
        t.c.line_id, t.c.source_name, t.c.written_by, t.c.at, t.c.batch, t.c.business_key_val).where(
        t.c.line_id.in_([line_id for _row, line_id in picked]))).fetchall()}
    return [{"id": str(line_id), "table_name": table_name, "row_id": row_id,
             "source_name": said[line_id].source_name, "updated_by": said[line_id].written_by,
             "timestamp": said[line_id].at, "transaction_id": said[line_id].batch,
             "business_key": said[line_id].business_key_val} for row_id, line_id in picked]


def winners(db, table_name, row_ids) -> dict:
    """{(row_id, column): {"source", "written_by", "at"}} of the line its current line names - `won_by` of t
    (the merge at write time, pins included), each line by its id: what a grid cell's colour and writer ask, no
    ranking read again. cell_overwrites.updated_by is who set a pin, not who wrote (C ㄱ 11-10). A table whose lines
    are not built (`lines.has_lines` - a shipped table, a view, a table ensure refused) has no won_by: none."""
    from database import lines

    if not lines.has_lines(db, table_name):
        return {}
    ids = list(dict.fromkeys(str(r) for r in row_ids or () if r))
    now = sa.Table(table_name, sa.MetaData(), sa.Column("row_id", sa.String),
                   sa.Column("won_by", sa.JSON))
    won = {}
    for i in range(0, len(ids), 1000):
        for row_id, by in db.execute(sa.select(now.c.row_id, now.c.won_by).where(now.c.row_id.in_(ids[i:i + 1000]))):
            for column, line_id in (by or {}).items():
                won[(row_id, column)] = int(line_id)
    t = line_table(table_name, {})
    named = sorted(set(won.values()))
    line = {}
    for i in range(0, len(named), 1000):
        for line_id, source, written_by, at in db.execute(sa.select(
                t.c.line_id, t.c.source_name, t.c.written_by, t.c.at).where(t.c.line_id.in_(named[i:i + 1000]))):
            line[line_id] = {"source": source, "written_by": written_by, "at": at}
    return {cell: line[line_id] for cell, line_id in won.items() if line_id in line}


def head_lines(db, table_name, row_ids, columns=None) -> dict:
    """{(row_id, column): {source: {"value", "at", "written_by"}}} - each source's newest line of the cell (its head
    bit), a withdrawn one left out (the source says nothing): the layers a Sources window shows. The head index -
    (row_id, source_name) WHERE a head bit is set. A table whose lines are not built (`lines.has_lines`) has none."""
    from database import lines

    if not lines.has_lines(db, table_name):
        return {}
    bits = line_bits(db, table_name)
    if columns is not None:
        bits = {name: bit for name, bit in bits.items() if name in set(columns)}
    t = line_table(table_name, bits)
    types = lines.value_types(db, table_name)
    heads = [t.c[name] != 0 for name in t.c.keys() if name.startswith("head_")]
    ids = list(dict.fromkeys(str(r) for r in row_ids or () if r))
    out = {}
    for i in range(0, len(ids), 1000):
        for row in db.execute(sa.select(t).where(t.c.row_id.in_(ids[i:i + 1000]), sa.or_(*heads))):
            for name, bit in bits.items():
                if bit_said(row, bit, "head") and not bit_said(row, bit, "withdrawn"):
                    out.setdefault((row.row_id, name), {})[row.source_name] = {
                        "value": line_cell(types, row, name), "at": row.at, "written_by": row.written_by}
    return out

