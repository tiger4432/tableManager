"""The cell-source overhaul's line tables for the read share's tests (lead 11-10 안 1): built by C's
`lines.ensure_line_table` (t__now · t__lines · the view t), lines and audit batches written by hand until the write
share writes them.

`build(engine, table)` makes them for a declared table (its entry in crud.TABLE_CONFIG); `line(conn, table, ...)`
writes one line with its bits; `now(conn, table, ...)` writes a current line; `audit_batch(conn, ...)` one batch."""
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from database import crud, lines

#: table -> its shape as `lines.ensure_line_table` made it - lines go in typed, as the write path's do (SQLite keeps a
#: datetime as text in the column type's own form)
_BUILT = {}


def build(engine, table):
    """`table`'s line tables and its view - t itself dropped first when it is a table. -> {column: bit}"""
    with engine.begin() as conn:
        if conn.dialect.name == "postgresql":
            kind = conn.execute(text("SELECT c.relkind FROM pg_class c WHERE c.oid = to_regclass(:t)"),
                                {"t": table}).scalar()
        else:
            kind = conn.execute(text("SELECT type FROM sqlite_master WHERE name = :t"), {"t": table}).scalar()
        if kind in ("r", "table"):
            conn.execute(text('DROP TABLE "%s"' % table))
    with Session(bind=engine) as session:
        shape = lines.ensure_line_table(session, table, crud.TABLE_CONFIG[table])
        session.commit()
    _BUILT[table] = shape
    return dict(shape["bits"])


def drop(engine, table):
    with Session(bind=engine) as session:
        lines.drop_line_table(session, table)
        session.commit()
    _BUILT.pop(table, None)


def _mask(columns, bits):
    out = {}
    for name in columns:
        chunk, place = divmod(bits[name], lines.BITS_PER_CHUNK)
        value = out.get(chunk, 0) | (1 << place)
        out[chunk] = value - (1 << 64) if value >= 1 << 63 else value      # a signed bigint
    return out


def line(conn, table, bits, row_id, *, kind="write", source="probe.csv", at=None, written_by="probe", batch=None,
         values=None, withdrawn=(), head=True, business_key=None, input_row=None, owner_rule=None):
    """One line of `table` - `values` {column: value} said (written bits), `withdrawn` columns said empty. -> line_id"""
    shape = _BUILT[table]
    values = dict(values or {})
    written = _mask(list(values) + [c for c in withdrawn if c not in values], bits) if kind in ("write", "withdraw") \
        else {}
    gone = _mask(withdrawn, bits) if withdrawn else {}
    row = {"line_kind": kind, "source_name": source, "at": at or datetime.now(timezone.utc), "written_by": written_by,
           "batch": batch, "input_row": None if input_row is None else str(input_row), "owner_rule": owner_rule,
           "row_id": row_id, "business_key_val": business_key}
    for chunk in range(shape["chunks"]):
        row["written_%d" % chunk] = written.get(chunk, 0)
        row["head_%d" % chunk] = written.get(chunk, 0) if head else 0
        row["withdrawn_%d" % chunk] = gone.get(chunk, 0)
    row.update(values)
    return conn.execute(shape["lines"].insert().values(row)).inserted_primary_key[0]


def now(conn, table, row_id, business_key, values=None, won_by=None):
    """The current line of `row_id` - its values and won_by {column: line_id}."""
    row = dict({"row_id": row_id, "business_key_val": business_key}, **(values or {}))
    row["won_by"] = won_by or {}
    conn.execute(_BUILT[table]["now"].insert().values(row))


def audit_batch(conn, transaction_id, table, *, written_by="probe", kind="edit", at=None):
    """One audit batch (lines.AuditBatch - a write statement's record). -> its id"""
    return conn.execute(lines.AuditBatch.__table__.insert().values(
        transaction_id=transaction_id, table_name=table, written_by=written_by, work_kind=kind,
        at=at or datetime.now(timezone.utc))).inserted_primary_key[0]
