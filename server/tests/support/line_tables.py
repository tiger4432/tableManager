"""The cell-source overhaul's line tables for the read share's tests (lead 11-10 안 1): built by C's
`lines.ensure_line_table` (t stays the current-values table with `won_by`; history is t__lines - owner/lead 11-11),
lines and audit batches written by hand until the write share writes them.

`build(engine, table)` makes them for a declared table (its entry in crud.TABLE_CONFIG); `line(conn, table, ...)`
writes one line with its bits; `now(conn, table, ...)` writes t's row and its won_by; `audit_batch(conn, ...)` one
batch."""
from datetime import datetime, timezone

from sqlalchemy import MetaData, Table, text
from sqlalchemy.orm import Session

from database import crud, lines, models

#: table -> its shape as `lines.ensure_line_table` made it - a line's values go in as text (`crud.line_text`), t's
#: typed
_BUILT = {}


def build(engine, table):
    """`table` (its model's table, emptied) with `won_by` and its line table. -> {column: bit}"""
    models.DYNAMIC_TABLES[table].__table__.create(bind=engine, checkfirst=True)
    with engine.begin() as conn:
        conn.execute(text('DELETE FROM "%s"' % table))
        if conn.dialect.name == "postgresql":         # the key's unique index ensure_line_table asks for (C)
            import migrations.add_business_key_unique_index as bk

            conn.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS "%s" ON "%s" (business_key_val)'
                              % (bk.unique_index_name(table), table)))
    with Session(bind=engine) as session:
        shape = lines.ensure_line_table(session, table, crud.TABLE_CONFIG[table])
        session.commit()
    _BUILT[table] = shape
    return dict(shape["bits"])


def bits_of(table) -> dict:
    """{column: bit} of `table` as `build` made it."""
    return dict(_BUILT[table]["bits"])


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
    types = lines.value_types(Session(bind=conn), table)        # the write's own types (C 1986aa74b)
    row.update({name: crud.line_text(value, types.get(name, "string")) for name, value in values.items()})
    return conn.execute(shape["lines"].insert().values(row)).inserted_primary_key[0]


def now(conn, table, row_id, business_key, values=None, won_by=None):
    """t's row `row_id` - its values and won_by {column: line_id}."""
    row = dict({"row_id": row_id, "business_key_val": business_key}, **(values or {}))
    row["won_by"] = won_by or {}
    conn.execute(Table(table, MetaData(), autoload_with=conn).insert().values(row))


def audit_batch(conn, transaction_id, table, *, written_by="probe", kind="edit", at=None):
    """One audit batch (lines.AuditBatch - a write statement's record). -> its id"""
    return conn.execute(lines.AuditBatch.__table__.insert().values(
        transaction_id=transaction_id, table_name=table, written_by=written_by, work_kind=kind,
        at=at or datetime.now(timezone.utc))).inserted_primary_key[0]
