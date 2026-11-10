"""The cell-source overhaul's line tables, built by hand for the read share's tests (lead 11-10 안 1) - until
`lines.ensure_line_table` lands, then this calls it. Names from docs/design/CELL_SOURCE_OVERHAUL.md «물리 이름 고정»:
`t__now` (t's columns + won_by), `t__lines` (the line columns + t's columns), `line_columns` (table · column · bit),
and the name t as a view over `t__now`. Both dialects.

`build(engine, table)` makes them for a declared table (its model in models.DYNAMIC_TABLES); `line(conn, table, ...)`
writes one line with its bits from `line_columns`; `now(conn, table, ...)` writes a current line."""
from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, Boolean, Column, DateTime, Integer, MetaData, String, Table, text

from database import lines, models

LINE_COLUMNS = "line_columns"
BITS = 64
#: table -> (its t__now Table, its t__lines Table) as `build` made them - lines go in typed, as the write path's do
#: (sqlite keeps a datetime as text in the column type's own form)
_BUILT = {}


def _line_columns(metadata):
    return Table(LINE_COLUMNS, metadata, Column("table_name", String, primary_key=True),
                 Column("bit", Integer, primary_key=True), Column("column_name", String, nullable=False),
                 Column("retired_at", DateTime(timezone=True)))


def build(engine, table, schema=None):
    """`table`'s two tables, its bit map (every declared column, in model order) and the view t - t itself dropped
    first when it is a table. -> {column: bit}"""
    model = models.DYNAMIC_TABLES[table]
    own = [c for c in model.__table__.columns]
    metadata = MetaData(schema=schema)
    now = Table(lines.now_relation(table), metadata,
                *[Column(c.name, c.type, primary_key=c.name == "row_id",
                         unique=c.name == "business_key_val") for c in own],
                Column("won_by", JSON))
    data = [c for c in own if c.name not in ("row_id", "business_key_val", "created_at", "updated_at")]
    chunks = max(1, -(-len(data) // BITS))
    bits_columns = [Column("%s_%d" % (kind, n), BigInteger, nullable=False, default=0)
                    for n in range(chunks) for kind in ("written", "head", "withdrawn")]
    line_table = Table(lines.lines_relation(table), metadata,
                       Column("line_id", Integer, primary_key=True, autoincrement=True),
                       Column("line_kind", String, nullable=False), Column("source_name", String),
                       Column("at", DateTime(timezone=True), nullable=False), Column("written_by", String),
                       Column("batch", String), Column("input_row", String), Column("owner_rule", String),
                       Column("owner_key", String), Column("confirmed", Boolean), *bits_columns,
                       *[Column(c.name, c.type) for c in own])
    catalog = _line_columns(metadata)
    qualified = (lambda name: '"%s"."%s"' % (schema, name)) if schema else (lambda name: '"%s"' % name)
    with engine.begin() as conn:
        conn.execute(text("DROP VIEW IF EXISTS %s" % qualified(table)))
        conn.execute(text("DROP TABLE IF EXISTS %s" % qualified(table)))
        metadata.create_all(conn)
        conn.execute(text("CREATE INDEX IF NOT EXISTS %s ON %s (row_id, at)" % (
            '"ix_%s_row_at"' % table, qualified(line_table.name))))
        conn.execute(text("CREATE INDEX IF NOT EXISTS %s ON %s (batch)" % (
            '"ix_%s_batch"' % table, qualified(line_table.name))))
        conn.execute(text("CREATE VIEW %s AS SELECT %s FROM %s" % (
            qualified(table), ", ".join('"%s"' % c.name for c in own), qualified(now.name))))
        conn.execute(text("DELETE FROM %s WHERE table_name = :t" % qualified(LINE_COLUMNS)), {"t": table})
        bits = {c.name: n for n, c in enumerate(data)}
        _BUILT[table] = (now, line_table)
        conn.execute(catalog.insert(), [{"table_name": table, "column_name": name, "bit": bit}
                                        for name, bit in bits.items()])
    return bits


def drop(engine, table, schema=None):
    qualified = (lambda name: '"%s"."%s"' % (schema, name)) if schema else (lambda name: '"%s"' % name)
    with engine.begin() as conn:
        conn.execute(text("DROP VIEW IF EXISTS %s" % qualified(table)))
        for name in (lines.lines_relation(table), lines.now_relation(table)):
            conn.execute(text("DROP TABLE IF EXISTS %s" % qualified(name)))
        conn.execute(text("DELETE FROM %s WHERE table_name = :t" % qualified(LINE_COLUMNS)), {"t": table})


def _mask(columns, bits):
    out = {}
    for name in columns:
        bit = bits[name]
        chunk, place = divmod(bit, BITS)
        value = out.get(chunk, 0) | (1 << place)
        out[chunk] = value - (1 << BITS) if value >= 1 << (BITS - 1) else value     # a signed bigint
    return out


def line(conn, table, bits, row_id, *, kind="write", source="probe.csv", at=None, written_by="probe", batch=None,
         values=None, withdrawn=(), head=True, business_key=None, input_row=None, owner_rule=None):
    """One line of `table` - `values` {column: value} said (written bits), `withdrawn` columns said empty. -> line_id"""
    values = dict(values or {})
    written = _mask(list(values) + [c for c in withdrawn if c not in values], bits) if kind in ("write", "withdraw") \
        else {}
    gone = _mask(withdrawn, bits) if withdrawn else {}
    row = {"line_kind": kind, "source_name": source, "at": at or datetime.now(timezone.utc), "written_by": written_by,
           "batch": batch, "input_row": input_row, "owner_rule": owner_rule, "row_id": row_id,
           "business_key_val": business_key}
    for chunk in range(max(1, -(-len(bits) // BITS))):
        row["written_%d" % chunk] = written.get(chunk, 0)
        row["head_%d" % chunk] = written.get(chunk, 0) if head else 0
        row["withdrawn_%d" % chunk] = gone.get(chunk, 0)
    row.update(values)
    return conn.execute(_BUILT[table][1].insert().values(row)).inserted_primary_key[0]


def now(conn, table, row_id, business_key, values=None, won_by=None):
    """The current line of `row_id` - its values and won_by {column: line_id}."""
    row = dict({"row_id": row_id, "business_key_val": business_key}, **(values or {}))
    row["won_by"] = won_by or {}
    conn.execute(_BUILT[table][0].insert().values(row))
