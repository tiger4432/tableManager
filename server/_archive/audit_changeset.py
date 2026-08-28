"""The CHANGESET shape of an audit row: one row per WRITE, not one per COLUMN.

PARKED - NOT WIRED, ZERO PRODUCTION CALLERS
    Nothing imports this module except its own test file. The lane that was to
    adopt it was deliberately halted on 2026-08-12: the `crud.py` / `main.py` /
    `schemas.py` hunks were REVERTED, and this file plus its test were left
    behind (they became tracked later only by an unrelated pathless `git add`).
    `server/tests/test_audit_changeset.py` is skipped in full for that reason.

    THEREFORE: DO NOT READ THIS DOCSTRING AS THE LIVE AUDIT SHAPE. The write
    path (`crud.py`) and the read path (`server/main.py`) both still run the
    original pre-refactor encoding described under WHAT CHANGED AND WHY below -
    the rendered sentence, with all five losses intact. This module is the
    PROPOSED replacement, and everything past this banner is written in the
    voice of a change that landed. It did not.

    The five defects are real and still open against the live machine-write
    path; the loss is confined to audit HISTORY, live cell values are correct.
    Ruling and revert record: `docs/process/PROJECT_STATUS.md:1560-1568`.

WHAT CHANGED AND WHY
    `audit_logs` used to be written two different ways by the same function.
    A human write (`source_name == 'user'`) emitted ONE ROW PER CHANGED COLUMN.
    Every other writer emitted ONE ROW PER ROW-WRITE whose `column_name` was the
    literal `ROW_UPDATE` and whose value was a RENDERED SENTENCE
    (`f"{col}: {val}"` joined on ", ", NULL written as the Korean word 비어있음).

    Measured on the isolated `assy_qa` copy, 2026-08-11, 239,801 audit rows:
        ROW_UPDATE (machine)        225,591   94.07%
        per-column, source='user'    12,736    5.31%
        per-column, machine           1,474    0.61%   (chain_replay - see below)
    Like-for-like on the same 16-column `dt_log` write, the two encodings cost
    1,008.6 B and 7,760.0 B respectively - 7.69x, or 10.12x fully indexed.

    The product owner ruled that the human path may stop writing one row per
    column. THE RENDERED SENTENCE IS NOT THE SHAPE TO CONVERGE ON. It is smaller
    than the per-column rows, but it is smaller because it has THROWN DATA AWAY,
    and adopting it would have spread five losses to the remaining 5.31% of the
    table while emptying the last cell-history tab that still worked:

    1. NOT CELL-ADDRESSABLE. `get_cell_history` filters `column_name == col`, and
       a summary is stored under the literal `ROW_UPDATE`, so it never matches.
       225,101 rows on `assy_qa` have machine history and an EMPTY CELL TAB.
    2. TYPED VALUES BECOME TEXT. `str(0)` and `str("0")` are the same characters,
       so integer 0 and string "0" become indistinguishable once written.
    3. NULL BECOMES A KOREAN WORD. `"비어있음" if v is None else str(v)` makes a
       NULL and a cell whose value IS that word identical. 81,523 rows on
       `assy_qa` contain that word today and nothing can say which are NULLs.
    4. DELIMITER AMBIGUITY. Joined on ", ", read back by splitting on ": ",
       nothing escaped. A live `wafer_map_metadata` row reads
       `grid_metadata: {"grid_cols": 2, "grid_rows": 2, ...}`, so a reader
       splitting it invents a column named `"grid_rows"`.
    5. TRUNCATION GRANULARITY. The 4,096-char cap applied to the WHOLE
       concatenation, so one long cell deleted every column after it.

    Items 2-5 are consequences of the ENCODING, not of summarising. This module
    keeps the row count of the summary and the fidelity of the per-column rows:
    ONE audit row per write whose `old_value`/`new_value` are JSON OBJECTS
    `{column: value}` rather than sentences.

WHY THE EXISTING COLUMNS AND NOT A NEW ONE
    `audit_logs.old_value` / `new_value` are already `Column(JSON)` - PostgreSQL
    `json`, verified against `assy_qa`'s catalogue. Storing an object in them
    needs NO migration and NO new column, which matters twice over: nothing has
    to be backfilled, and `create_all` never ALTERs an existing table, so a new
    column would have been a boot-order hazard for every process that reads
    audit rows (see the server-pm lesson about UndefinedColumn 500s).

    Using BOTH existing columns - old object and new object - rather than one
    `{col: [old, new]}` blob also keeps `AuditLogResponse` exactly the shape the
    client already consumes. `{col: [old, new]}` is recoverable by zipping them.

WHY `column_name` IS STILL THE LITERAL `ROW_UPDATE`
    Considered and rejected: a new sentinel (`ROW_CHANGESET`) so the shape would
    be self-describing in an INDEXED column. Rejected because the discriminator
    is already exact without it - a legacy summary is always a JSON *string* and
    a changeset is always a JSON *object*, and `jsonb_typeof(...) = 'object'`
    decides that in the database - while a new literal would silently break the
    two places `client2/src/timeline.js` branches on `ROW_UPDATE` (lines 227 and
    577), which this lane is not allowed to touch. Keeping the literal means the
    row timeline renders exactly as it does today.

READING BOTH SHAPES - HISTORY IS APPEND-ONLY
    Existing rows are NOT migrated and NOT rewritten. Every reader here accepts
    both and the test suite pins both:
        legacy per-column   `column_name == 'dt_lot'`, scalar value  -> unchanged
        legacy summary      `column_name == 'ROW_UPDATE'`, STRING    -> rendered
                                                                        already;
                                                                        not
                                                                        column-
                                                                        addressable,
                                                                        and it
                                                                        never
                                                                        will be
        changeset (new)     `column_name == 'ROW_UPDATE'`, OBJECT    -> projected
    `is_changeset()` is the ONE predicate that decides which, and it is a type
    test on the payload, never a parse of it.

    🔴 THE STRING SHAPE IS NEVER PARSED BACK INTO DATA. That is what loss 4
    makes impossible to do correctly, and a confidently wrong history is worse
    than an absent one. Old summaries stay strings and are shown as strings.

WHAT THIS DOES NOT TOUCH
    `chain_replay`'s two writers (`chain_replay_withdraw`, `resolution_recompute`
    - 1,474 rows, 0.61%) already write per-column rows and are already
    cell-addressable, so they are LEFT ALONE. They are machine paths, which is
    why "human vs machine" was never the right axis for this change: the axis is
    "one write touching many columns" vs "one decision about one cell".
"""
import json
import logging

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

try:
    from event_constants import truncate_audit_value
except ImportError:  # pragma: no cover - imported without server/ on sys.path
    import os
    import sys
    sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
    from event_constants import truncate_audit_value

logger = logging.getLogger(__name__)

#: The `column_name` a row-level audit entry is stored under. NOT a real column;
#: no table may declare one by this name. Unchanged from the legacy summary on
#: purpose - see the module docstring.
ROW_CHANGESET_COLUMN = "ROW_UPDATE"

#: How a NULL is DISPLAYED. Read-time only. It used to be what was STORED, which
#: is loss 3: 81,523 rows on `assy_qa` carry this word and no reader can tell
#: which of them were NULLs and which were cells containing the word.
RENDER_NULL = "비어있음"

#: Prefix the legacy renderer put on a creation's summary. Reproduced verbatim so
#: the row timeline is byte-identical to what it showed before this change.
RENDER_CREATE_PREFIX = "신규 데이터 생성: "


# ---------------------------------------------------------------------------
# Shape test
# ---------------------------------------------------------------------------

def is_changeset(value) -> bool:
    """True when an audit payload is the structured shape.

    A TYPE TEST, never a parse. Legacy summaries are JSON strings and legacy
    per-column values can be anything a cell holds - including an object, which
    is why callers must pair this with `column_name == ROW_CHANGESET_COLUMN`
    before concluding a payload is a changeset. `wafer_map_metadata.grid_metadata`
    is a live per-column value that IS an object.
    """
    return isinstance(value, dict)


# ---------------------------------------------------------------------------
# Write side
# ---------------------------------------------------------------------------

def build(changed_cols, old_snapshot, row, is_new: bool = False):
    """`(old_changeset, new_changeset)` for one row-write.

    Returns `(None, None)` when there is nothing worth recording, and the caller
    must then write NO audit row at all.

    TRUNCATION IS PER VALUE, which is loss 5 closed. The cap used to be applied
    to the whole concatenated sentence, so one oversized cell silently deleted
    every column after it from the record. Here each value is capped on its own
    and its neighbours are unaffected; `truncate_audit_value` marks the value it
    cut, so a truncated value still says so.

    COLUMNS WHOSE OLD AND NEW ARE BOTH NULL ARE OMITTED. On a row creation the
    `has_changed` guard is skipped, so `changed_cols` carries every column in the
    write including the ones the user left blank - 4,290 such null->null rows
    were measured on the live catalogue. They are not changes, `get_recorrection_stats`
    already excluded them from its denominator explicitly, and dropping them here
    means the payload contains only real changes and no reader needs that guard.
    Row CREATION itself is still recorded: it has its own audit row under
    `column_name == 'CREATE'` (crud.py), so an empty changeset loses nothing.

    `old_changeset` is None for a creation - there is no previous state, and that
    is also how the legacy summary said it (`old_summary = None`), so
    `old_value IS NULL` keeps meaning "this write created the row".
    """
    new_cs = {}
    old_cs = None if is_new else {}
    truncated = False

    for col in changed_cols:
        new_val = getattr(row, col, None)
        old_val = None if is_new else old_snapshot.get(col)
        if old_val is None and new_val is None:
            continue
        new_val, t1 = truncate_audit_value(new_val)
        new_cs[col] = new_val
        truncated = truncated or t1
        if old_cs is not None:
            old_val, t2 = truncate_audit_value(old_val)
            old_cs[col] = old_val
            truncated = truncated or t2

    if not new_cs:
        return None, None
    return old_cs, new_cs


# ---------------------------------------------------------------------------
# Read side - rendering (presentation derived from data, never the reverse)
# ---------------------------------------------------------------------------

def render(changeset, is_create: bool = False) -> str:
    """A changeset as the sentence the legacy summary used to STORE.

    Deliberately reproduces the old format exactly - `", ".join(f"{col}: {val}")`,
    NULL as 비어있음, `신규 데이터 생성: ` on a creation - so that a client which
    has not been updated renders a row-level entry precisely as it did before.

    This direction is fine and the other one is not: presentation computed from
    data is a choice, data reconstructed from presentation is a guess.
    """
    if not is_changeset(changeset):
        return changeset if isinstance(changeset, str) else json.dumps(
            changeset, ensure_ascii=False, default=str)
    parts = [f"{col}: {RENDER_NULL if v is None else v}" for col, v in changeset.items()]
    body = ", ".join(parts)
    return (RENDER_CREATE_PREFIX + body) if is_create else body


def render_pair(old_value, new_value):
    """`(old_display, new_display)` for a row-level entry, capped for the wire.

    The cap here is on the RENDERED string only. The stored objects keep every
    value, so crossing it no longer deletes trailing columns from the record -
    it shortens one rendering of them.
    """
    is_create = old_value is None
    new_disp = render(new_value, is_create=is_create)
    old_disp = None if is_create else render(old_value)
    new_disp, _ = truncate_audit_value(new_disp)
    if old_disp is not None:
        old_disp, _ = truncate_audit_value(old_disp)
    return old_disp, new_disp


# ---------------------------------------------------------------------------
# Read side - projection (this is what makes a cell tab work again)
# ---------------------------------------------------------------------------

def render_log_dicts(logs):
    """Render row-level changesets inside a list of RAW log dicts, for the wire.

    `created_logs` travels over the WebSocket and `client2/src/websocket.js`
    appends each entry straight into the timeline, which prints `new_value`. The
    REST routes render; this keeps the pushed copy identical to the fetched one,
    so a live entry and the same entry after a reload do not look different.

    Returns NEW dicts - the caller's list (and `audit_cache`) keeps the objects.
    Non-changeset entries are passed through by reference, unchanged.
    """
    out = []
    for l in logs or ():
        if (l.get("column_name") != ROW_CHANGESET_COLUMN
                or not is_changeset(l.get("new_value"))):
            out.append(l)
            continue
        old = l.get("old_value") if is_changeset(l.get("old_value")) else {}
        c = dict(l)
        c["changes"] = {col: [old.get(col), new] for col, new in l["new_value"].items()}
        c["old_value"], c["new_value"] = render_pair(l.get("old_value"), l["new_value"])
        out.append(c)
    return out


def project(old_value, new_value, col_name):
    """`(old, new)` for ONE column of a changeset, or None if it is not in it.

    Typed values come back TYPED - integer 0 stays `0` and string "0" stays
    `"0"` (loss 2), a NULL comes back as `None` and never as a Korean word
    (loss 3), and nothing is split on a delimiter (loss 4).

    Absence and a null value are different answers: a column that is not in the
    changeset returns None (the caller drops the entry), a column present with a
    JSON null returns `(old, None)`.
    """
    if not is_changeset(new_value) or col_name not in new_value:
        return None
    old = old_value.get(col_name) if is_changeset(old_value) else None
    return old, new_value[col_name]


def columns_of(new_value):
    """The column names a payload names, or [] if it names none.

    `summary_columns` in the transaction timeline is built from this. Before the
    changeset it was built from `column_name`, so every machine transaction
    listed one column called `ROW_UPDATE`; now the header lists the real columns
    for machine writes too.
    """
    return list(new_value.keys()) if is_changeset(new_value) else []


def summary_columns_for(log) -> list:
    """The column names ONE audit entry contributes to a transaction's header.

    Duck-typed on `.column_name` / `.new_value` so it serves both an ORM row and
    an `AuditLogResponse` from the in-memory cache.

    A legacy RENDERED summary falls through to `['ROW_UPDATE']` - the literal,
    exactly as the header showed it before - because the only way to get real
    column names out of that shape is to split the sentence, which is loss 4.
    """
    if getattr(log, "column_name", None) == ROW_CHANGESET_COLUMN:
        cols = columns_of(getattr(log, "new_value", None))
        if cols:
            return cols
    c = getattr(log, "column_name", None)
    return [c] if c else []


# ---------------------------------------------------------------------------
# Read side - the FIND predicate
# ---------------------------------------------------------------------------

def _dialect_is_sqlite(session) -> bool:
    try:
        return session.get_bind().dialect.name == "sqlite"
    except Exception:  # pragma: no cover - defensive; PG is the production path
        return False


def has_column_filter(session, model, col_name):
    """SQL predicate: this audit row is a CHANGESET that names `col_name`.

    ⚠️ THE OBJECT-TYPE GUARD IS LOAD-BEARING ON POSTGRESQL, not decoration.
    `jsonb`'s `?` operator applied to a STRING tests whether the string equals
    the key, so `'"dt_lot"'::jsonb ? 'dt_lot'` is TRUE. Without the guard a
    legacy row whose rendered value happened to be exactly a column name would
    be served as that cell's history. Probed on `assy_qa` 2026-08-11: with the
    guard such a row is correctly excluded, without it, it matches.

    ⚠️ CALLERS MUST STILL AND THIS WITH `column_name == ROW_CHANGESET_COLUMN`.
    A per-column row can hold an object too - `wafer_map_metadata.grid_metadata`
    is `{"grid_cols": 2, "grid_rows": 2, ...}` in production - and without the
    sentinel guard, asking for column `grid_rows` would match the `grid_metadata`
    cell's own history. Probed: it does.

    SQLite spelling is `json_type(x, '$."k"')`, which is NULL for an absent path
    and the string 'null' for a key that exists holding null - so a key present
    with a null value matches on BOTH dialects, same as `?` does.
    """
    col = model.new_value
    if _dialect_is_sqlite(session):
        return sa.func.json_type(col, "$." + json.dumps(col_name)).isnot(None)
    return sa.and_(
        sa.func.jsonb_typeof(sa.cast(col, JSONB)) == "object",
        sa.cast(col, JSONB).has_key(col_name),
    )


def cell_history_filter(session, model, col_name):
    """The whole `column_name` predicate for a cell tab, covering BOTH shapes.

    A legacy per-column row (`column_name == col`) OR a changeset row that names
    the column. Legacy RENDERED summaries match neither, on purpose: they cannot
    be column-addressed without parsing presentation back into data, and the
    honest answer for them is the `row_history_total` disclosure the response
    already carries - not a guess.
    """
    return sa.or_(
        model.column_name == col_name,
        sa.and_(
            model.column_name == ROW_CHANGESET_COLUMN,
            has_column_filter(session, model, col_name),
        ),
    )


# ---------------------------------------------------------------------------
# Read side - key expansion (the re-correction metric)
# ---------------------------------------------------------------------------
#
# ⚠️ `json_each(col)` IN THE FROM CLAUSE IS NOT PORTABLE. SQLite takes it; on
# PostgreSQL a `json` column reaches the function as a scalar and it fails with
# "cannot be reduced to a scalar" (probed 2026-08-11). PostgreSQL's spelling is
# a set-returning function in the TARGET list. Hence the split below - it is a
# dialect difference, not a preference.

def changeset_cell_keys(session, model, base_filter):
    """A subquery of `(table_name, row_id, column, transaction_id)` for changesets.

    One output row per COLUMN NAMED BY a changeset, so a caller that used to
    group by `column_name` keeps counting CELLS rather than silently starting to
    count ROWS. See `crud.get_recorrection_stats` for why that distinction is the
    whole meaning of the metric it feeds.
    """
    if _dialect_is_sqlite(session):
        je = sa.func.json_each(model.new_value).table_valued(
            "key", joins_implicitly=True)
        return (
            sa.select(model.table_name.label("t"), model.row_id.label("r"),
                      je.c.key.label("c"), model.transaction_id.label("tx"))
            .select_from(model).select_from(je)
            .where(base_filter,
                   model.column_name == ROW_CHANGESET_COLUMN,
                   je.c.key.isnot(None))
        )
    return (
        sa.select(
            model.table_name.label("t"), model.row_id.label("r"),
            sa.func.jsonb_object_keys(sa.cast(model.new_value, JSONB)).label("c"),
            model.transaction_id.label("tx"))
        .where(base_filter,
               model.column_name == ROW_CHANGESET_COLUMN,
               sa.func.jsonb_typeof(sa.cast(model.new_value, JSONB)) == "object")
    )
