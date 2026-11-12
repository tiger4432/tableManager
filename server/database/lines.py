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
#: a declared column's value cell in t__lines is v_<column>: the line's own columns (at, source_name, batch,
#: head_0 ...) are the line table's names, and an operator's column may carry any of them (A 11-11, rq_memory.at)
VALUE_PREFIX = "v_"
WON_BY = "won_by"
#: won_by's word for «the column's formula shows» - a formula holds no line (lead 10-28 ㄴ, A 11-11)
FORMULA_WON = 0
LINE_KINDS = ("write", "withdraw", "deleted", "mark")
BIT_FAMILIES = ("written", "head", "withdrawn")
BITS_PER_CHUNK = 64
#: tables a stamped_by statement asks (a UNION ALL arm each) - under sqlite's 500 compound terms
STAMPED_ARMS = 400
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
    refill this table only. `copy_of`: the name a key merge's copy was made of - the merge stamps it, the rank puts
    the copy behind the row's own layers (lead 11-12 ㄴ); None for every other name."""

    __tablename__ = "line_sources"

    source_name = Column(String, primary_key=True)
    ranks_as = Column(String, nullable=False)
    copy_of = Column(String, nullable=True)


def note_sources(db, names, copies=None) -> None:
    """Give each source name not yet in line_sources its row - write_lines and the migration call this before they
    write lines. A name two writers meet at once lands once (insert or ignore). `copies`: {copy's name: the name it
    copies} - a key merge's (lead 11-12 ㄴ)."""
    from sqlalchemy import insert

    from . import crud

    names = {str(n) for n in names if n is not None}
    if not names:
        return
    known = set(db.execute(select(LineSource.source_name).where(LineSource.source_name.in_(names))).scalars())
    copies = copies or {}
    fresh = [{"source_name": n, "ranks_as": crud.layer_ranks_as(n), "copy_of": copies.get(n)}
             for n in sorted(names - known)]
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
    """None when t's name can carry line tables; else «reason - action» - the name half of `build_refusal`."""
    if '"' in table_name or "$" in table_name:
        return "its name carries a quote or a dollar sign - declare it under a plain name"
    size = len(table_name.encode("utf-8"))
    if size <= MAX_TABLE_NAME_BYTES:
        return None
    return (f"its name is {size} bytes; line tables need {MAX_TABLE_NAME_BYTES} or fewer - declare it under a "
            f"shorter name (a non-ASCII character takes 3 bytes)")


def lines_relation(table_name: str) -> str:
    """The physical table holding t's lines."""
    return _checked(table_name + LINES_SUFFIX)


def sets_at_once(db) -> bool:
    """A step's rows in one set statement (write_lines, line_migration.copy_page's won_by): PostgreSQL (psycopg2 sends an UPDATE's parameter sets one round trip each,
    lead 11-12 ㄴ); sqlite keeps the parameter sets - no round trips there, and no bit_or."""
    return db.get_bind().dialect.name == "postgresql"


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
    return bit_maps(db, [table_name]).get(table_name, {})


def bit_maps(db, table_names) -> dict:
    """{table: {column: bit}} of these tables' live columns - one read for any number of tables."""
    out = {}
    for name, column, bit in db.execute(select(LineColumn.table_name, LineColumn.column_name, LineColumn.bit).where(
            LineColumn.table_name.in_(list(table_names)), LineColumn.retired_at.is_(None))).all():
        out.setdefault(name, {})[column] = bit
    return out


def has_lines(db, table_name: str) -> bool:
    """Whether t's lines are BUILT - t__lines exists AND t carries won_by - THE answer every read of won_by or
    t__lines asks (`_catalogue`). keeps_lines answers whether t SHOULD be built; the two differ while ensure refuses
    a table (an orphaned t__lines, a lock not had). Not the slots: those are assigned before building and outlive
    drop_line_table."""
    return table_name in _catalogue(db, [table_name])


def _catalogue(db, table_names) -> dict:
    """{table: its t__lines' head chunks} of the tables whose lines are BUILT - THE predicate has_lines asks, read
    for any number of tables at once: a walk over every declared table (cells_stamped_by None, 1,183 on the box)
    paid three catalogue reads a table (C board 11-11: 24 ms a table, 28.5 s a lap)."""
    from sqlalchemy import inspect

    names = [n for n in dict.fromkeys(table_names) if not table_name_refusal(n)]
    if not names:
        return {}
    rels = names + [lines_relation(n) for n in names]
    conn = db.connection()
    if conn.dialect.name == "postgresql":
        rows = conn.execute(text(
            "SELECT c.relname, a.attname FROM pg_class c JOIN pg_attribute a ON a.attrelid = c.oid "
            "WHERE c.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = current_schema()) "
            "AND c.relkind IN ('r', 'p') AND c.relname = ANY(:rels) AND a.attnum > 0 AND NOT a.attisdropped "
            "AND (a.attname = :won OR a.attname LIKE 'head\\_%')"), {"rels": rels, "won": WON_BY}).all()
    else:
        insp = inspect(conn)
        rows = [(rel, c["name"]) for rel in rels if insp.has_table(rel) for c in insp.get_columns(rel)]
    held = {}
    for rel, column in rows:
        held.setdefault(rel, set()).add(column)
    return {n: sum(1 for i in range(len(held[lines_relation(n)])) if f"head_{i}" in held[lines_relation(n)])
            for n in names if WON_BY in held.get(n, ()) and lines_relation(n) in held}


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


def head_index_name(table_name: str, chunks: int) -> str:
    """The head index's name for `chunks` head chunks - its WHERE names every one, so a new chunk is a new index
    (`head_index`); one chunk keeps the first name, `t__lines_h`."""
    return index_name(table_name, "h" if chunks <= 1 else f"h{chunks}")


def line_indexes(engine, table_name: str, table_cfg: dict, say=None, only=None) -> dict:
    """PostgreSQL: every index t__lines declares (`shape` - ra, b, p, the head, i), or those named in `only`, that is
    not there and valid, built outside any transaction by the one CONCURRENTLY builder (`models._ensure_one_index_once`
    - its INVALID repair, its waits, its cut): writes are never held. The head index takes the earlier chunks' head
    indexes as its leftovers, away first (lead 11-11 - a 65th column). ensure_declared asks it for every line table at
    each start, so an index found missing - dropped by hand, or by a copy that stopped - is built before anything
    starts (owner 11-11 «the launcher builds everything or starts nothing», lead 11-12). sqlite: create_all and
    alter_columns build them. -> {index name: the builder's answer}."""
    import logging
    import time

    from sqlalchemy.orm import Session
    from sqlalchemy.schema import CreateIndex

    from . import models

    say = say or logging.getLogger(__name__).info
    with Session(engine) as db:
        s = shape(db, table_name, table_cfg)
        db.rollback()
    head = head_index_name(table_name, s["chunks"])
    out = {}
    for index in sorted(s["lines"].indexes, key=lambda i: i.name):
        if only is not None and index.name not in only:
            continue
        ddl = str(CreateIndex(index).compile(dialect=engine.dialect))
        began = time.perf_counter()
        out[index.name] = models._ensure_one_index_once(
            engine, index.name, ddl.replace("CREATE INDEX", "CREATE INDEX CONCURRENTLY IF NOT EXISTS", 1),
            "line head" if index.name == head else "line", say=say, table=lines_relation(table_name),
            leftovers=[head_index_name(table_name, n) for n in range(1, s["chunks"])] if index.name == head else ())
        if out[index.name] == models.INDEX_BUILT:
            say("[Indexes] line index '%s' built in %.1f s" % (index.name, time.perf_counter() - began))
    return out


def head_index(engine, table_name: str, table_cfg: dict, say=None) -> str:
    """t__lines' head index for its chunks as they stand (`line_indexes`' head case). -> the builder's answer."""
    with __import__("sqlalchemy.orm", fromlist=["Session"]).Session(engine) as db:
        name = head_index_name(table_name, chunk_count(db, table_name))
        db.rollback()
    return line_indexes(engine, table_name, table_cfg, say=say, only={name})[name]


def shape(db, table_name: str, table_cfg: dict) -> dict:
    """t's line table as a Core Table on a private MetaData, with the bit map it was built from. A column t already
    holds is typed as STORED (the stored kind is what line_text reads). Assigns slots to new declared columns (the
    caller commits)."""
    from .models import sql_type_of

    table_cfg = _as_stored(db, table_name, table_cfg)
    types = table_cfg["column_types"]
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
    data = [c if c.name in framework else Column(value_column(c.name), String)
            for c in _data_columns(table_cfg, sql_type_of, row_id_key=False) if c.name != "row_id"]
    lines = Table(lines_relation(table_name), meta, *line_cols, Column("row_id", String, nullable=False), *data)
    head_any = " OR ".join(f"{name} <> 0" for name in bit_columns("head", chunks))
    Index(index_name(table_name, "ra"), lines.c.row_id, lines.c.at)
    Index(index_name(table_name, "b"), lines.c.batch, postgresql_ops={"batch": "text_pattern_ops"})
    Index(index_name(table_name, "p"), lines.c.at, postgresql_include=["row_id", "batch"],
          postgresql_where=text(HUMAN_SOURCE_SQL), sqlite_where=text(HUMAN_SOURCE_SQL))
    Index(head_index_name(table_name, chunks), lines.c.row_id, lines.c.source_name,
          postgresql_where=text(head_any), sqlite_where=text(head_any))
    # «the cells these source rows fed» (cells_stamped_by) - only a line that carries its source row is in it
    Index(index_name(table_name, "i"), lines.c.input_row,
          postgresql_where=text("input_row IS NOT NULL"), sqlite_where=text("input_row IS NOT NULL"))
    table = current_table(db, table_name, table_cfg, won_by=True, stored=True)
    columns = [c.name for c in table.columns if c.name != WON_BY]
    # kinds: t's columns as stored - value_types' answer, already read by _as_stored (A 11-11: one read a write)
    return {"lines": lines, "bits": bits, "chunks": chunks, "table": table, "columns": columns, "kinds": types}


def _as_stored(db, table_name: str, table_cfg: dict) -> dict:
    """table_cfg as t is BUILT: once t exists, its columns are the ones it holds, typed as stored (the stored kind is
    what line_text reads) - a declared column t does not hold yet is left out until the schema sync adds it (a
    statement naming it would fail, A 11-11); before t exists, the declaration."""
    from sqlalchemy import inspect

    if not inspect(db.connection()).has_table(table_name):
        return table_cfg
    return {**table_cfg, "column_types": physical_kinds(db, table_name)}


def current_table(db, table_name: str, table_cfg: dict, won_by=None, stored=False):
    """t itself as a Core Table on its own MetaData - framework and declared columns typed as stored, plus won_by
    when t carries it (won_by None: has_lines asks). THE answer to «t's columns and types»: shape and write_lines
    (a table without lines too - no slots, no t__lines) bind to it. `stored`: table_cfg is _as_stored's answer
    already (shape - A 11-11: the stored kinds were read twice a write)."""
    from .models import sql_type_of

    if won_by is None:
        won_by = has_lines(db, table_name)
    cols = _data_columns(table_cfg if stored else _as_stored(db, table_name, table_cfg), sql_type_of, row_id_key=True)
    return Table(table_name, MetaData(), *cols, *([Column(WON_BY, won_by_type())] if won_by else []))


def value_column(name: str) -> str:
    """t's column `name` -> its value cell in t__lines. THE spelling - every read and write of a line's value asks
    it. A name that would pass PostgreSQL's 63 bytes with the prefix is refused."""
    out = VALUE_PREFIX + name
    if len(out.encode("utf-8")) > 63:
        raise ValueError(f"column {name!r}: its line cell {out!r} would pass 63 bytes - shorten the column name")
    return out


def won_by_type():
    return JSON().with_variant(JSONB, "postgresql")


def ensure_line_table(db, table_name: str, table_cfg: dict) -> dict:
    """Give the existing table t its `won_by` column (no default - PostgreSQL rewrites nothing) and create
    `t__lines` with its indexes - what is missing only. -> the shape."""
    from sqlalchemy import inspect

    conn = db.connection()
    if conn.dialect.name != "postgresql":        # sqlite: no index builder, no concurrency - built here, same name
        import migrations.add_business_key_unique_index as bk

        conn.exec_driver_sql(f'CREATE UNIQUE INDEX IF NOT EXISTS "{bk.unique_index_name(table_name)}" '
                             f'ON "{_checked(table_name)}" (business_key_val)')
    said = build_refusal(conn, table_name)
    if said:
        raise ValueError(said)
    s = shape(db, table_name, table_cfg)
    if WON_BY not in {c["name"] for c in inspect(conn).get_columns(table_name)}:
        conn.exec_driver_sql(f'ALTER TABLE "{_checked(table_name)}" ADD COLUMN "{WON_BY}" '
                             f'{won_by_type().compile(dialect=conn.dialect)}')
    s["lines"].metadata.create_all(conn, checkfirst=True)
    return s


#: t was dropped and built again while its t__lines stayed: attaching it would show the old table's history as
#: the new one's (lead 11-11) - refused, the operator decides
ORPHAN_REFUSAL = ("%(lines)s still holds the history of an earlier %(t)s, which was dropped and made again - "
                  "rename %(lines)s or drop it (its history goes with it), then start or save again")


class LineTablesRefused(Exception):
    """Every declared table whose lines were not built, at once (lead 11-11 ㄴ): the schema sync raises it - a boot
    stops on it, a reload refuses the declaration. .refused: {table: «reason - action»}."""

    def __init__(self, refused: dict):
        self.refused = dict(refused)
        super().__init__("\n".join(f"{t}: line table not built - {why}" for t, why in self.refused.items()))


def build_refusal(conn, table_name: str):
    """«reason - action» when t's lines would be refused, else None - THE judge the build (`ensure_declared`,
    `ensure_line_table`) and the declaration save ask (lead 11-11). A lock is not judged here: only trying tells."""
    from sqlalchemy import inspect

    said = table_name_refusal(table_name)
    if said:
        return said
    insp = inspect(conn)
    if table_name in insp.get_view_names():
        return "it is a view - declare it kind: view"
    if insp.has_table(table_name) and insp.has_table(lines_relation(table_name)) and \
            WON_BY not in {c["name"] for c in insp.get_columns(table_name)}:
        return ORPHAN_REFUSAL % {"t": table_name, "lines": lines_relation(table_name)}
    return None


def drop_every_line_table(engine) -> list:
    """Drop every t__lines - what a whole-schema reset (setup/reset_db, the test fixtures' drop_all) does beside
    Base.metadata.drop_all, which never sees them (each lives on shape's own MetaData). -> the names dropped."""
    from sqlalchemy import inspect

    names = [n for n in inspect(engine).get_table_names() if n.endswith(LINES_SUFFIX)]
    with engine.begin() as conn:
        for name in names:
            conn.exec_driver_sql(f'DROP TABLE IF EXISTS "{_checked(name)}"')
    return names


def key_index_standing(conn, table_name: str) -> bool:
    """Does a VALID unique index on exactly (business_key_val) stand on t - what INSERT ... ON CONFLICT
    (business_key_val) needs. The catalogue only, so a write may ask it every call (A 11-11). THE seat:
    write_lines' claim and the rules list ask this. Lines do not need it - they are bound to row_id (owner 11-11)."""
    if conn.dialect.name == "postgresql":
        import migrations.add_business_key_unique_index as bk

        found = bk.existing_unique_index(conn, table_name)
        return bool(found and found[1])
    for _seq, name, unique, _origin, partial in conn.exec_driver_sql(
            f'PRAGMA index_list("{_checked(table_name)}")').all():
        if unique and not partial and [c[2] for c in conn.exec_driver_sql(
                f'PRAGMA index_info("{_checked(name)}")').all()] == ["business_key_val"]:
            return True
    return False


def key_index_next(tables) -> str:
    """The rules list's word for tables a rule writes whose business key has no valid unique index: what it means
    (KEY_RACE) and the next action - the scheduler builds it; keys held twice wait for Fold duplicate rows."""
    return f"{KEY_RACE}: " + "; ".join(
        f"{t} (no unique index on business_key_val) - the scheduler builds it at start or a Reload; if it cannot, "
        f"auto_update.log says why (keys held by more than one row: in the Retroactive tab run Fold duplicate rows "
        f"on {t})" for t in tables)


#: what a table without the index means (owner 11-11 «비즈니스키는 업서트 용»): its new keys are taken today's way
KEY_RACE = "two writes of one new key at the same moment can make two rows"


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
    from sqlalchemy import inspect

    for rel in (_checked(table_name), lines_relation(table_name)):
        present = {c["name"] for c in inspect(conn).get_columns(rel)} if add else set()
        cell = (lambda n: n) if rel == table_name else value_column
        for name in add:
            if cell(name) in present:            # t already has it (the schema sync added it first)
                continue
            type_sql = (sql_type_of(types[name]) if rel == table_name else String()).compile(
                dialect=conn.dialect)
            statements.append(f'ALTER TABLE "{rel}" ADD COLUMN "{cell(name)}" {type_sql}')
        for name in drop:
            statements.append(f'ALTER TABLE "{rel}" DROP COLUMN "{cell(name)}"')
        for name, using in (retype or {}).items():
            if dialect == "postgresql" and rel == table_name:
                type_sql = sql_type_of(types[name]).compile(dialect=conn.dialect)
                statements.append(f'ALTER TABLE "{rel}" ALTER COLUMN "{name}" TYPE {type_sql} USING {using}')
    for family in BIT_FAMILIES:
        for name in bit_columns(family, after)[before:]:
            statements.append(f'ALTER TABLE "{lines_relation(table_name)}" ADD COLUMN "{name}" BIGINT NOT NULL DEFAULT 0')
    rebuild = after > before and dialect != "postgresql"     # PostgreSQL: head_index, outside this transaction
    if rebuild:                                  # the head index's WHERE names every head chunk
        statements += [f'DROP INDEX IF EXISTS "{head_index_name(table_name, n)}"' for n in range(1, after)]
    for stmt in statements:
        conn.exec_driver_sql(stmt)
    s = shape(db, table_name, table_cfg)
    if rebuild:
        head = next(i for i in s["lines"].indexes if i.name == head_index_name(table_name, after))
        from sqlalchemy.schema import CreateIndex

        ddl = str(CreateIndex(head).compile(dialect=conn.dialect))
        conn.exec_driver_sql(ddl)
        statements.append(ddl)
    return statements


def _mask(bit: int) -> int:
    """The signed bigint mask of a column's bit in its chunk (bit 63 is the sign bit)."""
    m = 1 << (bit % BITS_PER_CHUNK)
    return m - (1 << 64) if m >= 1 << 63 else m


def spoken(db, table_name: str, row_ids, s: dict = None) -> dict:
    """{row_id: columns some line of that row has spoken in} - written OR withdrawn, any source. Read from the head
    lines (the head index): every column a source ever wrote or withdrew keeps that source's head bit, so the OR of
    head bits is the OR of written bits. A column NOT here keeps t's value (owner 11-11 «끊음»). `s`: the shape the
    caller holds (a write - A 11-11), else the built table and its slots are read here."""
    row_ids = list(row_ids)
    if not row_ids:
        return {}
    chunks = s["chunks"] if s is not None else _built_chunks(db.connection(), table_name)
    heads = bit_columns("head", chunks)
    by_bit = {bit: col for col, bit in (s["bits"] if s is not None else bit_map(db, table_name)).items()}
    lt = Table(lines_relation(table_name), MetaData(), Column("row_id", String), *[Column(h, BigInteger) for h in heads])
    from sqlalchemy import or_

    rows = db.execute(select(lt.c.row_id, *[lt.c[h] for h in heads])
                      .where(lt.c.row_id.in_(row_ids), or_(*[lt.c[h] != 0 for h in heads]))).all()
    out = {}
    for row in rows:
        out.setdefault(row[0], set()).update(_columns_of(row[1:], by_bit))
    return out


def _columns_of(chunk_values, by_bit) -> set:
    """The column names whose bits are set in one bit family's chunks (bigint, bit 63 the sign)."""
    cols = set()
    for chunk, value in enumerate(chunk_values):
        value = (value or 0) & ((1 << 64) - 1)
        while value:
            low = value & -value
            bit = chunk * BITS_PER_CHUNK + low.bit_length() - 1
            if bit in by_bit:
                cols.add(by_bit[bit])
            value ^= low
    return cols


def layers(db, table_name: str, row_ids, columns=None, s: dict = None) -> dict:
    """{(row_id, column): {source_name: {"value", "ingested_at", "updated_by", "origin_row_id", "line_id",
    "owner_rule", "owner_key", "copy_of"}}} - each source's standing word on each cell: its head line, unless that line withdrew
    the column. THE layer read after the overhaul (lead 11-11): what cell_sources answered, in the same shape, from
    t__lines; values read back as t's stored kind. Reads only - no slots, no shape: `s` is the shape a write already
    holds (A 11-11), else the built table, its slots and kinds are read here."""
    from sqlalchemy import inspect, or_

    from . import crud

    row_ids = list(dict.fromkeys(str(r) for r in row_ids or () if r))
    if not row_ids or (s is None and not has_lines(db, table_name)):
        return {}
    built = ({c.name for c in s["lines"].c} if s is not None else                         # one catalogue read
             {c["name"] for c in inspect(db.connection()).get_columns(lines_relation(table_name))})
    chunks = sum(1 for i in range(len(built)) if f"head_{i}" in built)
    by_bit = {bit: col for col, bit in (s["bits"] if s is not None else bit_map(db, table_name)).items()
              if columns is None or col in columns}
    cells = [c for c in by_bit.values() if value_column(c) in built]
    heads, gone = bit_columns("head", chunks), bit_columns("withdrawn", chunks)
    own = ("line_id", "source_name", "at", "written_by", "owner_rule", "owner_key", "input_row")
    lt = Table(lines_relation(table_name), MetaData(), Column("row_id", String),
               *[Column(n, BigInteger if n in ("line_id",) else (DateTime(timezone=True) if n == "at" else String))
                 for n in own],
               *[Column(n, BigInteger) for n in heads + gone], *[Column(value_column(c), String) for c in cells])
    kinds = s["kinds"] if s is not None else value_types(db, table_name)
    src = LineSource.__table__
    out = {}
    for i in range(0, len(row_ids), 1000):
        for r in db.execute(select(lt, src.c.copy_of).select_from(lt.outerjoin(src, src.c.source_name == lt.c.source_name))
                            .where(lt.c.row_id.in_(row_ids[i:i + 1000]), or_(*[lt.c[h] != 0 for h in heads]))).mappings():
            said = _columns_of([r[h] for h in heads], by_bit) - _columns_of([r[g] for g in gone], by_bit)
            for col in said:
                if col not in cells:
                    continue
                out.setdefault((r["row_id"], col), {})[r["source_name"]] = {
                    "value": crud.line_value(r[value_column(col)], kinds.get(col, "string")),
                    "ingested_at": r["at"], "updated_by": r["written_by"], "origin_row_id": r["input_row"],
                    "line_id": r["line_id"], "owner_rule": r["owner_rule"], "owner_key": r["owner_key"],
                    "copy_of": r["copy_of"]}
    return out


def rank(line, terms, unowned) -> tuple:
    """A line's place in `crud.rank_terms`' order - the line {ranks_as, copy_of, owner_rule, source_name, at, line_id}. THE one
    walk of the terms: lines.merge and crud.compute_priority_value (write_lines._others, file_layer_fold, a formula's
    candidate) rank here, so a line's owner_rule ranks alike in every one (lead 11-12 ㄴ)."""
    return tuple(term(line, unowned) for term in terms)


def chain_unowned(lines_) -> bool:
    """Does a chain line no rule owns sit on the cell (rank term 1d asks)."""
    from . import crud

    return any(ln["ranks_as"] == crud.CHAIN_SOURCE and ln["owner_rule"] is None for ln in lines_)


def merge(db, table_name: str, table_cfg: dict, row_ids, exclude_source: str = None, s: dict = None) -> dict:
    """{row_id: {column: (value, line_id)}} for the columns whose shown value the lines decide:
       a column no line spoke in is absent (t keeps its value - «끊음»);
       a pinned column whose pinned source has no head line is absent (t keeps its value - lead 11-11);
       a spoken column with no candidate left (all withdrawn, or `exclude_source` - R2's «what shows once this source
       is gone» - was the only one) is (None, None).
    The head lines are read once (1,000 rows a statement) and ranked here by crud.rank_terms - the one order
    compute_priority_value walks (C board 2 11-11: the ranking in SQL was 1.0 s for 1,000 rows x 30 columns). «An
    unowned chain layer sits on the cell» counts the head lines that say it, pinned or excluded or not. Values read
    back as t's stored kind (crud.line_value). `s`: the shape the caller already holds (a write - A 11-11)."""
    from sqlalchemy import or_

    from . import crud
    from .models import CellOverwrite

    row_ids = list(dict.fromkeys(row_ids))
    if not row_ids:
        return {}
    s = s if s is not None else shape(db, table_name, table_cfg)
    lt, kinds, chunks = s["lines"], s["kinds"], s["chunks"]
    by_bit = {bit: c for c, bit in s["bits"].items() if value_column(c) in lt.c and bit // BITS_PER_CHUNK < chunks}
    heads, gone = bit_columns("head", chunks), bit_columns("withdrawn", chunks)
    src, ov = LineSource.__table__, CellOverwrite.__table__
    terms = crud.rank_terms(table_name)
    out = {}
    for i in range(0, len(row_ids), 1000):
        part = row_ids[i:i + 1000]
        pins = {(r, c): p for r, c, p in db.execute(
            select(ov.c.row_id, ov.c.column_name, ov.c.manual_priority_source)
            .where(ov.c.table_name == table_name, ov.c.row_id.in_(part), ov.c.manual_priority_source.isnot(None)))}
        cells = {}                                                     # (row, col) -> [(line, says, value)]
        for r in db.execute(select(lt.c.row_id, lt.c.line_id, lt.c.source_name, lt.c.owner_rule, lt.c.at,
                                   src.c.ranks_as, src.c.copy_of, *[lt.c[n] for n in heads + gone],
                                   *[lt.c[value_column(c)] for c in by_bit.values()])
                            .select_from(lt.outerjoin(src, src.c.source_name == lt.c.source_name))
                            .where(lt.c.row_id.in_(part), or_(*[lt.c[h] != 0 for h in heads]))).mappings():
            line = {"ranks_as": r["ranks_as"], "copy_of": r["copy_of"], "owner_rule": r["owner_rule"],
                    "source_name": r["source_name"],
                    "at": crud.resolution_ingested_at({"ingested_at": r["at"]}), "line_id": r["line_id"]}
            withdrawn = _columns_of([r[g] for g in gone], by_bit)
            for col in _columns_of([r[h] for h in heads], by_bit):
                cells.setdefault((r["row_id"], col), []).append((line, col not in withdrawn, r[value_column(col)]))
        for (row, col), said in cells.items():
            pin = pins.get((row, col))
            unowned = chain_unowned([ln for ln, ok, _ in said if ok])
            left = [(ln, v) for ln, ok, v in said if ok and (pin is None or ln["source_name"] == pin)
                    and ln["source_name"] != exclude_source]
            if left:
                ln, value = min(left, key=lambda c: rank(c[0], terms, unowned))
                out.setdefault(row, {})[col] = (crud.line_value(value, kinds.get(col, "string")), ln["line_id"])
            elif pin is None:
                out.setdefault(row, {})[col] = (None, None)
    return out


def ensure_declared(engine, tables=None) -> dict:
    """Every declared table that keeps lines gets them: t__lines + won_by where missing (empty - old rows are not
    copied, «끊음»), and t__lines catches up with columns t was given. ONE function: the schema sync calls it for all
    declared tables, the index line for a table whose business key index it just built (lead 11-11 ㄱ), the test
    fixtures after building tables. A built table costs reads only, no DDL. The DDL waits for its lock as every
    runtime DDL does (db_safety.short_ddl - lock_timeout, then the holder named). Every table is tried; ->
    {table: «reason - action»} of every one refused - its name, an old t__lines (`build_refusal`), t not in the
    database, a lock not had, any other error - which the schema sync raises as one LineTablesRefused."""
    import logging

    from sqlalchemy import inspect
    from sqlalchemy.orm import Session

    import db_safety
    from error_said import told

    from . import crud, models

    log = logging.getLogger(__name__)
    refused = {}
    for name in list(tables if tables is not None else models.DYNAMIC_TABLES):
        cfg = crud.TABLE_CONFIG.get(name)
        if not isinstance(cfg, dict) or not keeps_lines(name, cfg):
            continue
        with Session(engine) as db:
            insp = inspect(db.connection())
            said = build_refusal(db.connection(), name) or (
                None if insp.has_table(name) else "it is declared but the database has no such table - start the "
                                                  "server or save the declaration again; both make it")
            built = not said and has_lines(db, name)
            have = {c["name"] for c in insp.get_columns(lines_relation(name))} if built else set()
            missing = [c for c in (cfg.get("column_types") or {})          # a framework name is t__lines' own column
                       if c not in {n for n, _ in FRAMEWORK} and value_column(c) not in have] if built else []
        if said:
            refused[name] = said
            log.error("[Lines] %s: %s", name, said)
            continue

        def work(conn, name=name, cfg=cfg, built=built, missing=missing):
            for model in (LineColumn, AuditBatch, LineSource):    # the launcher builds before any create_all made them
                model.__table__.create(bind=conn, checkfirst=True)
            db = Session(bind=conn)
            if built:
                alter_columns(db, name, cfg, add=missing)
            else:
                ensure_line_table(db, name, cfg)
            db.flush()

        try:
            if not built or missing:
                db_safety.short_ddl(engine, name, work, "lines")
        except ValueError as err:
            refused[name] = str(err)
            log.error("[Lines] %s: %s", name, err)
            continue
        except Exception as err:                             # noqa: BLE001 - said; the sync raises it with the rest
            held = getattr(err, "ddl_holders", None)
            refused[name] = (f"its lock was not had (held by {held}) - end that session or wait for it, then start "
                             f"or save again" if held else f"{told(err)} - fix what it names, then start or save again")
            log.error("[Lines] %s: %s", name, refused[name], exc_info=None if held else err)
            continue
        if engine.dialect.name != "postgresql":
            continue
        try:
            answers = line_indexes(engine, name, cfg, say=log.info)
        except Exception as err:                             # noqa: BLE001 - said; the sync raises it with the rest
            answers = {lines_relation(name): "%s%s" % (models.INDEX_FAILED_SAID, told(err))}
        unbuilt = sorted(n for n, a in answers.items() if a not in (models.INDEX_BUILT, models.INDEX_PRESENT))
        if unbuilt:
            refused[name] = ("index %s not built (%s) - the line above says why; start again once it is free"
                             % (", ".join(unbuilt), ", ".join(str(answers[n]) for n in unbuilt)))
            log.error("[Lines] %s: %s", name, refused[name])
    return refused


def stamped_by(db, table_names, origin_row_ids) -> list:
    """[(table, row_id, column, source_name, input_row)] - the cells of these tables these source rows feed now: each
    line carrying one of them as its input_row, its head columns it did not withdraw (the index t__lines_i). The
    catalogue and the slots are read once for all the tables (`_catalogue`, `bit_maps`), and the tables' lines in
    ONE statement - a UNION ALL arm a table, STAMPED_ARMS arms a statement (C board 2 11-11: a statement a table
    was 11 s for 1,183 tables). Reads only."""
    import json

    ids = list(dict.fromkeys(str(i) for i in origin_row_ids or () if i))
    if not ids:
        return []
    built = _catalogue(db, table_names)
    maps = bit_maps(db, list(built))
    postgres = db.get_bind().dialect.name == "postgresql"
    tables = [t for t in dict.fromkeys(table_names) if t in built]
    out = []
    for at in range(0, len(tables), STAMPED_ARMS):
        group = tables[at:at + STAMPED_ARMS]
        width = max(built[t] for t in group)
        heads, gone = bit_columns("head", width), bit_columns("withdrawn", width)
        arms, names = [], {}
        for k, table_name in enumerate(group):
            names[f"t{k}"] = table_name
            have = bit_columns("head", built[table_name])
            picked = ", ".join([f"CAST(:t{k} AS varchar) AS t", "s.row_id", "s.source_name", "s.input_row",
                                *[f"s.{n}" if int(n.rsplit("_", 1)[1]) < built[table_name] else f"0 AS {n}"
                                  for n in heads + gone]])
            said = " OR ".join(f"s.{h} <> 0" for h in have)
            # 🔴 PG: each origin through t__lines_i on its own (총괄 d28171060 - one IN (1,000) under a low n_distinct
            #    belief read the whole table: 370 ms vs 10 ms on 3M rows); OFFSET 0 keeps the LATERAL unfolded
            arms.append(f'SELECT {picked} FROM o CROSS JOIN LATERAL (SELECT * FROM "{lines_relation(table_name)}" s '
                        f"WHERE s.input_row = o.id AND ({said}) OFFSET 0) s" if postgres else
                        f'SELECT {picked} FROM "{lines_relation(table_name)}" s '
                        f"WHERE s.input_row IN (SELECT id FROM o) AND ({said})")
        origins = ("WITH o(id) AS (SELECT unnest(CAST(:ids AS varchar[]))) " if postgres else
                   "WITH o(id) AS (SELECT value FROM json_each(:ids)) ")
        for i in range(0, len(ids), 1000):
            part = ids[i:i + 1000]
            for r in db.execute(text(origins + " UNION ALL ".join(arms)),
                                {"ids": part if postgres else json.dumps(part), **names}).mappings():
                by_bit = {bit: col for col, bit in maps.get(r["t"], {}).items()}
                cols = _columns_of([r[h] for h in heads], by_bit) - _columns_of([r[g] for g in gone], by_bit)
                out.extend((r["t"], r["row_id"], col, r["source_name"], r["input_row"]) for col in sorted(cols))
    return out


def built_lines(db, table_name: str):
    """(t__lines as BUILT - a Core Table of the columns it holds, column -> bit) for a reader: no slots assigned,
    nothing written (shape assigns slots to new declared columns - a write)."""
    from sqlalchemy import inspect

    types = {"at": DateTime(timezone=True), "line_id": BigInteger()}
    cols = [Column(c["name"], types.get(c["name"], BigInteger() if c["name"].split("_")[0] in BIT_FAMILIES
                                        and c["name"].rsplit("_", 1)[-1].isdigit() else String()))
            for c in inspect(db.connection()).get_columns(lines_relation(table_name))]
    built = {c.name for c in cols}
    bits = {col: bit for col, bit in bit_map(db, table_name).items() if value_column(col) in built}
    return Table(lines_relation(table_name), MetaData(), *cols), bits
