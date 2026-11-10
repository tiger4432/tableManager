"""The cell-source overhaul's table shape - ONE author (docs/design/CELL_SOURCE_OVERHAUL.md).

A declared table t stays what it is - the current values (owner 11-11) - plus one column `won_by` (column ->
winning line_id). Its history is `t__lines` (one line per write). The line-table name, the column -> bit map and
every DDL on the pair go through here; nothing else spells «__lines».
"""
import contextlib
import contextvars
import math

from sqlalchemy import (BigInteger, Column, DateTime, Index, Integer, MetaData, String, Table,
                        func, select, text)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON

from .database import Base

MAX_NAME_BYTES = 63                                  # PostgreSQL's identifier limit
LINES_SUFFIX = "__lines"
WON_BY = "won_by"
LINE_KINDS = ("write", "withdraw", "deleted", "mark")
BIT_FAMILIES = ("written", "head", "withdrawn")
BITS_PER_CHUNK = 64
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


class LineSource(Base):
    """Source name -> the name it ranks as (crud.layer_ranks_as) - one row per distinct source name, not one per line,
    so the rank's first term is a plain CASE in both dialects (lead 11-11 ㄷ). Rules for splitting a name change ->
    refill this table only."""

    __tablename__ = "line_sources"

    source_name = Column(String, primary_key=True)
    ranks_as = Column(String, nullable=False)


def note_sources(db, names) -> None:
    """Give each source name not yet in line_sources its row - write_lines and the migration call this before they
    write lines. A name two writers meet at once lands once (insert or ignore)."""
    from sqlalchemy import insert

    from . import crud

    names = {str(n) for n in names if n is not None}
    if not names:
        return
    known = set(db.execute(select(LineSource.source_name).where(LineSource.source_name.in_(names))).scalars())
    fresh = [{"source_name": n, "ranks_as": crud.layer_ranks_as(n)} for n in sorted(names - known)]
    if not fresh:
        return
    stmt = insert(LineSource).values(fresh)
    dialect = db.connection().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        stmt = pg_insert(LineSource).values(fresh).on_conflict_do_nothing(index_elements=["source_name"])
    else:
        stmt = stmt.prefix_with("OR IGNORE")
    db.execute(stmt)


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


#: The longest name derived from a declared table: `t__lines_ra`.
MAX_TABLE_NAME_BYTES = MAX_NAME_BYTES - len(LINES_SUFFIX + "_ra")


def table_name_refusal(table_name: str):
    """None when t can carry line tables; else the operator sentence (which table, how many bytes, what to do) -
    the migration's pre-check says it before any DDL."""
    if '"' in table_name or "$" in table_name:
        return f"table {table_name!r} carries a quote or a dollar sign - declare it under a plain name and migrate again"
    size = len(table_name.encode("utf-8"))
    if size <= MAX_TABLE_NAME_BYTES:
        return None
    return (f"table {table_name!r} is {size} bytes long; line tables need {MAX_TABLE_NAME_BYTES} or fewer - "
            f"declare it under a shorter name (a non-ASCII character takes 3 bytes) and migrate again")


def lines_relation(table_name: str) -> str:
    """The physical table holding t's lines."""
    return _checked(table_name + LINES_SUFFIX)


def keeps_lines(table_name: str, table_cfg) -> bool:
    """Does t keep lines (`won_by` + `t__lines`) - THE answer the copy job, the catalogue and the report ask: an
    operator-declared table (kind table). Not a view, not a table the product ships (system tables), and not an
    undeclared relation - the ledger's own tables are already append-only history and are left as they are."""
    import shipped
    from ledger.setup_bundle import catalog_kind

    return bool(table_cfg) and catalog_kind(table_cfg) != "view" and table_name not in shipped.tables()


def value_types(db, table_name: str) -> dict:
    """{column: "number" | "datetime" | "string"} by the PHYSICAL type of t - the type crud.line_text /
    line_value take. A column declared datetime but stored as text stays text (its value is the written text, as
    today), so a line never respells what the table holds. Framework columns are left out."""
    return physical_kinds(db, table_name)


def physical_kinds(db, relation: str) -> dict:
    """{column: "number" | "datetime" | "string"} of a relation's stored columns, framework columns left out."""
    from sqlalchemy import inspect
    from sqlalchemy.types import DateTime as _DateTime, Float, Integer as _Integer, Numeric

    framework = {n for n, _ in FRAMEWORK}
    out = {}
    for col in inspect(db.connection()).get_columns(relation):
        if col["name"] in framework or col["name"] == WON_BY:
            continue
        kind = col["type"]
        out[col["name"]] = ("number" if isinstance(kind, (Float, Numeric, _Integer)) else
                            "datetime" if isinstance(kind, _DateTime) else "string")
    return out


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
    """t's line table as a Core Table on a private MetaData, with the bit map it was built from. A column t already
    holds is typed as STORED (the stored kind is what line_text reads). Assigns slots to new declared columns (the
    caller commits)."""
    from sqlalchemy import inspect

    from .models import sql_type_of

    stored = physical_kinds(db, table_name) if inspect(db.connection()).has_table(table_name) else {}
    types = dict(table_cfg.get("column_types") or {})
    types.update(stored)
    table_cfg = {**table_cfg, "column_types": types}
    declared = [name for name in types if name not in {n for n, _ in FRAMEWORK}]
    bits = assign_bits(db, table_name, declared)
    chunks = chunk_count(db, table_name)
    meta = MetaData()
    line_cols = [Column("line_id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True),
                 Column("line_kind", String, nullable=False), Column("source_name", String),
                 Column("at", DateTime(timezone=True)), Column("written_by", String), Column("batch", String),
                 Column("input_row", String), Column("owner_rule", String), Column("owner_key", String),
                 Column("confirmed", String)]
    for family in BIT_FAMILIES:
        line_cols += [Column(name, BigInteger, nullable=False, server_default=text("0"))
                      for name in bit_columns(family, chunks)]
    # a line's value cells are text whatever the declared type (crud.line_text) - retyping touches t only
    framework = {n for n, _ in FRAMEWORK}
    data = [c if c.name in framework else Column(c.name, String)
            for c in _data_columns(table_cfg, sql_type_of, row_id_key=False) if c.name != "row_id"]
    lines = Table(lines_relation(table_name), meta, *line_cols, Column("row_id", String, nullable=False), *data)
    head_any = " OR ".join(f"{name} <> 0" for name in bit_columns("head", chunks))
    Index(index_name(table_name, "ra"), lines.c.row_id, lines.c.at)
    Index(index_name(table_name, "b"), lines.c.batch, postgresql_ops={"batch": "text_pattern_ops"})
    Index(index_name(table_name, "p"), lines.c.at, postgresql_include=["row_id", "batch"],
          postgresql_where=text(HUMAN_SOURCE_SQL), sqlite_where=text(HUMAN_SOURCE_SQL))
    Index(index_name(table_name, "h"), lines.c.row_id, lines.c.source_name,
          postgresql_where=text(head_any), sqlite_where=text(head_any))
    # t itself on its own MetaData (ensure creates the lines only): declared columns typed as stored, plus won_by
    table = Table(table_name, MetaData(), *_data_columns(table_cfg, sql_type_of, row_id_key=True),
                  Column(WON_BY, won_by_type()))
    columns = [c.name for c in table.columns if c.name != WON_BY]
    return {"lines": lines, "bits": bits, "chunks": chunks, "table": table, "columns": columns}


def won_by_type():
    return JSON().with_variant(JSONB, "postgresql")


def ensure_line_table(db, table_name: str, table_cfg: dict) -> dict:
    """Give the existing table t its `won_by` column (no default - PostgreSQL rewrites nothing) and create
    `t__lines` with its indexes - what is missing only. -> the shape."""
    from sqlalchemy import inspect

    conn = db.connection()
    if conn.dialect.name == "postgresql":
        refused = key_index_refusal(conn, table_name)
        if refused:
            raise ValueError(refused)
    s = shape(db, table_name, table_cfg)
    if WON_BY not in {c["name"] for c in inspect(conn).get_columns(table_name)}:
        conn.exec_driver_sql(f'ALTER TABLE "{_checked(table_name)}" ADD COLUMN "{WON_BY}" '
                             f'{won_by_type().compile(dialect=conn.dialect)}')
    s["lines"].metadata.create_all(conn, checkfirst=True)
    return s


def key_index_missing(conn, table_name: str):
    """None when t's business_key_val carries a valid unique index - what write_lines' claim (INSERT ... ON CONFLICT
    (business_key_val)) needs; else why not, in operator words. The index is built by the one command that builds it
    (migrations/add_business_key_unique_index - CONCURRENTLY, so never inside this transaction)."""
    import migrations.add_business_key_unique_index as bk

    verdict = bk.plan_table(conn, table_name)
    if verdict.get("verdict") == bk.OK_ALREADY:
        return None
    dups = verdict.get("dup_keys") or 0
    return f"{dups} business keys appear more than once" if dups else "no unique index on business_key_val"


def key_index_command(table_names) -> str:
    """The command that builds the missing indexes - it names the duplicates to clean first."""
    return ("python server/migrations/add_business_key_unique_index.py --apply "
            + " ".join(f"--table {t}" for t in table_names))


def key_index_refusal(conn, table_name: str):
    why = key_index_missing(conn, table_name)
    return None if why is None else (f"table {table_name!r}: {why} - first run {key_index_command([table_name])}, "
                                     f"then keep lines again")


def drop_line_table(db, table_name: str) -> None:
    """Drop `t__lines` and t's `won_by` - the old code runs on as before (cell_sources was never touched). The slots
    stay in line_columns (a table re-created under the same name keeps its slot numbering)."""
    from sqlalchemy import inspect

    conn = db.connection()
    conn.exec_driver_sql(f'DROP TABLE IF EXISTS "{lines_relation(table_name)}"')
    if inspect(conn).has_table(table_name) and WON_BY in {c["name"] for c in inspect(conn).get_columns(table_name)}:
        conn.exec_driver_sql(f'ALTER TABLE "{_checked(table_name)}" DROP COLUMN "{WON_BY}"')


def _built_chunks(conn, table_name: str) -> int:
    from sqlalchemy import inspect

    names = {c["name"] for c in inspect(conn).get_columns(lines_relation(table_name))}
    return sum(1 for i in range(len(names)) if f"head_{i}" in names)


def alter_columns(db, table_name: str, table_cfg: dict, add=(), drop=(), retype=None) -> list:
    """Column DDL in the caller's transaction: t and `t__lines` get the same column names in the same order.
    `t__lines` value cells are text, so retype changes t only.
    add: column names in table_cfg's column_types (the cfg AFTER the change); drop: column names; retype: {column:
    USING expression} from admin/retype.using - the cast has one author there, and sqlite skips it as today's
    retype does. A rename is a drop + a new column (a new bit).
    -> the statements run (the same text an operator is shown)."""
    from .models import sql_type_of

    conn = db.connection()
    dialect = conn.dialect.name
    types = table_cfg.get("column_types") or {}
    for name in [*add, *drop, *(retype or {})]:
        _checked(name)
    statements = []
    before = _built_chunks(conn, table_name)
    if add:
        assign_bits(db, table_name, list(add))
    if drop:
        retire_bits(db, table_name, list(drop))
    after = chunk_count(db, table_name)
    for rel in (_checked(table_name), lines_relation(table_name)):
        for name in add:
            type_sql = (sql_type_of(types[name]) if rel == table_name else String()).compile(
                dialect=conn.dialect)
            statements.append(f'ALTER TABLE "{rel}" ADD COLUMN "{name}" {type_sql}')
        for name in drop:
            statements.append(f'ALTER TABLE "{rel}" DROP COLUMN "{name}"')
        for name, using in (retype or {}).items():
            if dialect == "postgresql" and rel == table_name:
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
        from sqlalchemy.schema import CreateIndex

        ddl = str(CreateIndex(head).compile(dialect=conn.dialect))
        conn.exec_driver_sql(ddl)
        statements.append(ddl)
    return statements
