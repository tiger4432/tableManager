"""The cell-source overhaul's table shape - ONE author (docs/design/CELL_SOURCE_OVERHAUL.md).

Every declared table t is two plain tables: `t__now` (one current line per entity, merged at write time) and
`t__lines` (one line per write - the history). The name t is a view over `t__now` that refuses writes. Names, the
column -> bit map and every DDL on the three go through here; nothing else spells «__now» or «__lines».
"""
import contextlib
import contextvars
import math

from sqlalchemy import (BigInteger, Column, DateTime, Index, Integer, MetaData, String, Table, UniqueConstraint,
                        func, select, text)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON

from .database import Base

MAX_NAME_BYTES = 63                                  # PostgreSQL's identifier limit
NOW_SUFFIX, LINES_SUFFIX = "__now", "__lines"
LINE_KINDS = ("write", "withdraw", "deleted", "mark")
BIT_FAMILIES = ("written", "head", "withdrawn")
BITS_PER_CHUNK = 64
REFUSAL = "a write to the view {view} is refused - write through database.lines (write_lines)"
#: «A person wrote this line» in SQL - the same answer as crud.layer_writer(source_name) == "user" (the key merge
#: backup «user (old_exist_…)» included). A partial index below carries this exact text; a query must repeat it.
HUMAN_SOURCE_SQL = "(source_name = 'user' OR source_name LIKE 'user (%')"

#: The columns every data table carries before its declared ones (today's framework columns, same types).
FRAMEWORK = (("row_id", String), ("business_key_val", String), ("created_at", DateTime(timezone=True)),
             ("updated_at", DateTime(timezone=True)))


class LineColumn(Base):
    """Column -> bit slot of a table's lines. Append-only: a dropped column keeps its row (retired_at set) and its
    slot is never handed out again - an old line's bit would otherwise name another column."""

    __tablename__ = "line_columns"

    table_name = Column(String, primary_key=True)
    bit = Column(Integer, primary_key=True)
    column_name = Column(String, nullable=False)
    retired_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("uq_line_columns_live", "table_name", "column_name", unique=True,
                            postgresql_where=text("retired_at IS NULL"), sqlite_where=text("retired_at IS NULL"),
                            info={"purpose": "one live bit slot per column of a table",
                                  "serves": "lines.bit_map / assign_bits"}),)


class AuditBatch(Base):
    """The audit log: one row per (transaction, table, work kind). No values - «changed rows» is counted from the
    table's lines by batch."""

    __tablename__ = "audit_batches"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    transaction_id = Column(String, nullable=False)
    table_name = Column(String, nullable=False)
    written_by = Column(String)
    work_kind = Column(String, nullable=False)
    at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (Index("ix_audit_batches_table_at", "table_name", "at",
                            info={"purpose": "audit rows of one table, newest first",
                                  "serves": "audit panel filtered by table"}),
                      Index("ix_audit_batches_transaction", "transaction_id",
                            postgresql_ops={"transaction_id": "text_pattern_ops"},
                            info={"purpose": "audit rows of one transaction or history group «label·…»",
                                  "serves": "audit_cache.in_group: GET /audit_logs/recent, "
                                            "GET /audit_logs/transaction/{tx_id}"}),
                      Index("ix_audit_batches_at_id", "at", "id",
                            info={"purpose": "audit rows of every table, newest first",
                                  "serves": "GET /audit_logs/recent (at, id)"}))


_SEEDING = contextvars.ContextVar("lines_seeding", default=False)


@contextlib.contextmanager
def seeding():
    """Tests' ORM writes (add · attribute set · session.delete) on a line table are taken only inside this; the
    flush hook refuses them elsewhere."""
    token = _SEEDING.set(True)
    try:
        yield
    finally:
        _SEEDING.reset(token)


def is_seeding() -> bool:
    return _SEEDING.get()


def _checked(name: str) -> str:
    if '"' in name or "$" in name:
        raise ValueError(f"relation name {name!r} carries a quote or a dollar sign")
    if len(name.encode("utf-8")) > MAX_NAME_BYTES:
        raise ValueError(f"relation name {name!r} is longer than {MAX_NAME_BYTES} bytes")
    return name


def now_relation(table_name: str) -> str:
    """The physical table holding t's current lines - what a catalogue, plan or index question names."""
    return _checked(table_name + NOW_SUFFIX)


def lines_relation(table_name: str) -> str:
    """The physical table holding t's lines."""
    return _checked(table_name + LINES_SUFFIX)


def stored_relation(table_name: str, table_cfg) -> str:
    """The physical relation an index, plan or catalogue question about t names: `t__now` for a declared data
    table, the name itself for an operator view (kind: view) or a system table (no table_cfg)."""
    from ledger.setup_bundle import catalog_kind

    if not table_cfg or catalog_kind(table_cfg) == "view":
        return table_name
    return now_relation(table_name)


def declared_of(relation: str, tables: dict):
    """stored_relation read backwards: the declared table (of {name: table_cfg}) whose relation this is, or None."""
    for name, cfg in tables.items():
        if stored_relation(name, cfg) == relation:
            return name
    return None


def bit_map(db, table_name: str) -> dict:
    """{column: bit} of t's live columns."""
    rows = db.execute(select(LineColumn.column_name, LineColumn.bit).where(
        LineColumn.table_name == table_name, LineColumn.retired_at.is_(None))).all()
    return {name: bit for name, bit in rows}


def has_lines(db, table_name: str) -> bool:
    """Whether t keeps lines (has slots in line_columns) - an audit row of a relation without lines has no
    countable «changed rows»."""
    return db.execute(select(LineColumn.bit).where(LineColumn.table_name == table_name).limit(1)).first() is not None


def assign_bits(db, table_name: str, columns) -> dict:
    """Give each column without a live slot the next slot after every slot t ever had; -> the live map."""
    live = bit_map(db, table_name)
    top = db.execute(select(func.max(LineColumn.bit)).where(LineColumn.table_name == table_name)).scalar()
    nxt = -1 if top is None else top
    for name in columns:
        if name not in live:
            nxt += 1
            db.add(LineColumn(table_name=table_name, bit=nxt, column_name=name))
            live[name] = nxt
    db.flush()
    return live


def retire_bits(db, table_name: str, columns) -> None:
    """Mark dropped columns' slots retired; the slots stay taken."""
    db.query(LineColumn).filter(LineColumn.table_name == table_name, LineColumn.column_name.in_(list(columns)),
                                LineColumn.retired_at.is_(None)).update({LineColumn.retired_at: func.now()},
                                                                        synchronize_session=False)


def chunk_count(db, table_name: str) -> int:
    """How many bigint chunks each bit family takes - from every slot t ever had, retired ones included."""
    top = db.execute(select(func.max(LineColumn.bit)).where(LineColumn.table_name == table_name)).scalar()
    return max(1, math.ceil(((top if top is not None else -1) + 1) / BITS_PER_CHUNK))


def bit_columns(family: str, chunks: int) -> list:
    return [f"{family}_{i}" for i in range(chunks)]


def _data_columns(table_cfg: dict, sql_type_of, row_id_key: bool) -> list:
    columns = [Column(name, type_, primary_key=(row_id_key and name == "row_id")) for name, type_ in FRAMEWORK]
    framework = {name for name, _ in FRAMEWORK}
    for name, type_str in (table_cfg.get("column_types") or {}).items():
        if name not in framework:
            columns.append(Column(name, sql_type_of(type_str)))
    return columns


#: The longest name derived from t is `t__lines_ra` - so a declared table name is at most 53 bytes.
INDEX_SUFFIXES = {"ra": "(row_id, at)", "b": "batch", "p": "person lines by at", "h": "head lines"}


def index_name(table_name: str, suffix: str) -> str:
    """`t__lines_<suffix>` - the short, checked name of a line-table index (row-at · batch · person · head)."""
    return _checked(f"{lines_relation(table_name)}_{suffix}")


def shape(db, table_name: str, table_cfg: dict) -> dict:
    """t's two tables as Core Table objects on a private MetaData, with the names and the bit map they were built
    from. Assigns slots to new declared columns (the caller commits)."""
    from .models import sql_type_of

    declared = [name for name in (table_cfg.get("column_types") or {}) if name not in {n for n, _ in FRAMEWORK}]
    bits = assign_bits(db, table_name, declared)
    chunks = chunk_count(db, table_name)
    meta = MetaData()
    now = Table(now_relation(table_name), meta, *_data_columns(table_cfg, sql_type_of, row_id_key=True),
                Column("won_by", JSON().with_variant(JSONB, "postgresql")))
    now.append_constraint(UniqueConstraint("business_key_val", name=_checked(f"{now.name}_bk")))
    line_cols = [Column("line_id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True),
                 Column("line_kind", String, nullable=False), Column("source_name", String), Column("at", DateTime(timezone=True)),
                 Column("written_by", String), Column("batch", String), Column("input_row", String),
                 Column("owner_rule", String), Column("owner_key", String), Column("confirmed", String)]
    for family in BIT_FAMILIES:
        line_cols += [Column(name, BigInteger, nullable=False, server_default=text("0"))
                      for name in bit_columns(family, chunks)]
    data = [c for c in _data_columns(table_cfg, sql_type_of, row_id_key=False) if c.name != "row_id"]
    lines = Table(lines_relation(table_name), meta, *line_cols, Column("row_id", String, nullable=False), *data)
    head_any = " OR ".join(f"{name} <> 0" for name in bit_columns("head", chunks))
    Index(index_name(table_name, "ra"), lines.c.row_id, lines.c.at)
    Index(index_name(table_name, "b"), lines.c.batch, postgresql_ops={"batch": "text_pattern_ops"})
    Index(index_name(table_name, "p"), lines.c.at, postgresql_include=["row_id", "batch"],
          postgresql_where=text(HUMAN_SOURCE_SQL), sqlite_where=text(HUMAN_SOURCE_SQL))
    Index(index_name(table_name, "h"), lines.c.row_id, lines.c.source_name,
          postgresql_where=text(head_any), sqlite_where=text(head_any))
    return {"now": now, "lines": lines, "view": table_name, "bits": bits, "chunks": chunks,
            "view_columns": [c.name for c in now.columns if c.name != "won_by"]}


def _view_ddl(dialect: str, s: dict) -> list:
    view, now = s["view"], s["now"].name
    cols = ", ".join(f'"{c}"' for c in s["view_columns"])
    msg = REFUSAL.format(view=view).replace("'", "''")
    out = [f'CREATE VIEW "{view}" AS SELECT {cols} FROM "{now}"']
    if dialect == "postgresql":
        fn = _checked(f"refuse_{view}"[:MAX_NAME_BYTES])
        out += [f"CREATE OR REPLACE FUNCTION \"{fn}\"() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
                f"RAISE EXCEPTION '{msg}'; END $$",
                f'CREATE TRIGGER "{view}_refuse" INSTEAD OF INSERT OR UPDATE OR DELETE ON "{view}" '
                f'FOR EACH ROW EXECUTE FUNCTION "{fn}"()']
    else:
        out += [f'CREATE TRIGGER "{view}_refuse_{op.lower()}" INSTEAD OF {op} ON "{view}" '
                f"BEGIN SELECT RAISE(ABORT, '{msg}'); END" for op in ("INSERT", "UPDATE", "DELETE")]
    return out


def _drop_view_ddl(dialect: str, view: str) -> list:
    out = [f'DROP VIEW IF EXISTS "{view}"']
    if dialect == "postgresql":
        out.append(f'DROP FUNCTION IF EXISTS "{f"refuse_{view}"[:MAX_NAME_BYTES]}"()')
    return out                                   # sqlite drops a view's triggers with the view


def ensure_line_table(db, table_name: str, table_cfg: dict) -> dict:
    """Create t's two tables, their indexes, and the view t with its refusing trigger - what is missing only.
    -> the shape."""
    s = shape(db, table_name, table_cfg)
    conn = db.connection()
    s["now"].metadata.create_all(conn, checkfirst=True)
    from sqlalchemy import inspect

    if table_name not in inspect(conn).get_view_names():
        for stmt in _view_ddl(conn.dialect.name, s):
            conn.exec_driver_sql(stmt)
    return s


def drop_line_table(db, table_name: str) -> None:
    """Drop the view t, both tables, and a migration's `t__old` if there is one. The slots stay retired-or-live in
    line_columns (a table re-created under the same name keeps its slot numbering)."""
    conn = db.connection()
    for stmt in _drop_view_ddl(conn.dialect.name, table_name):
        conn.exec_driver_sql(stmt)
    for name in (lines_relation(table_name), now_relation(table_name), _checked(table_name + "__old")):
        conn.exec_driver_sql(f'DROP TABLE IF EXISTS "{name}"')


def _built_chunks(conn, table_name: str) -> int:
    from sqlalchemy import inspect

    names = {c["name"] for c in inspect(conn).get_columns(lines_relation(table_name))}
    return sum(1 for i in range(len(names)) if f"head_{i}" in names)


def alter_columns(db, table_name: str, table_cfg: dict, add=(), drop=(), retype=None) -> list:
    """Column DDL on both tables in the caller's transaction: drop the view, change `t__now` and `t__lines` alike,
    re-create the view. add: column names in table_cfg's column_types (the cfg AFTER the change); drop: column
    names; retype: {column: USING expression} from admin/retype.using - the cast has one author there, and sqlite
    skips it as today's retype does. A rename is a drop + a new column (a new bit).
    -> the statements run (the same text an operator is shown)."""
    from .models import sql_type_of

    conn = db.connection()
    dialect = conn.dialect.name
    types = table_cfg.get("column_types") or {}
    statements = list(_drop_view_ddl(dialect, table_name))
    before = _built_chunks(conn, table_name)
    if add:
        assign_bits(db, table_name, list(add))
    if drop:
        retire_bits(db, table_name, list(drop))
    after = chunk_count(db, table_name)
    for rel in (now_relation(table_name), lines_relation(table_name)):
        for name in add:
            type_sql = sql_type_of(types[name]).compile(dialect=conn.dialect)
            statements.append(f'ALTER TABLE "{rel}" ADD COLUMN "{name}" {type_sql}')
        for name in drop:
            statements.append(f'ALTER TABLE "{rel}" DROP COLUMN "{name}"')
        for name, using in (retype or {}).items():
            if dialect == "postgresql":
                type_sql = sql_type_of(types[name]).compile(dialect=conn.dialect)
                statements.append(f'ALTER TABLE "{rel}" ALTER COLUMN "{name}" TYPE {type_sql} USING {using}')
    for family in BIT_FAMILIES:
        for name in bit_columns(family, after)[before:]:
            statements.append(f'ALTER TABLE "{lines_relation(table_name)}" ADD COLUMN "{name}" BIGINT NOT NULL DEFAULT 0')
    if after > before:                           # the head index's WHERE names every head chunk
        statements.append(f'DROP INDEX IF EXISTS "{index_name(table_name, "h")}"')
    for stmt in statements:
        conn.exec_driver_sql(stmt)
    s = shape(db, table_name, table_cfg)
    if after > before:
        head = next(i for i in s["lines"].indexes if i.name == index_name(table_name, "h"))
        head.create(conn)
        statements.append(f"CREATE INDEX {head.name} (head chunks 0..{after - 1})")
    view_statements = _view_ddl(dialect, s)
    for stmt in view_statements:
        conn.exec_driver_sql(stmt)
    return statements + view_statements
