# -*- coding: utf-8 -*-
"""A table declaration that names a column a type the database does not hold yet (owner 10-21 «문자 타입에서 숫자
타입으로 테이블 선언 바꾸니 numeric pg 에러», lead aa8ff1af5 ㄱ).

The save keeps the database's type in the file and queues a conversion (`retype_column` on the retroactive queue). The
conversion checks the values, converts the column with the indexes that read it in one transaction, then writes the
declared type into the file - so every process's model, which follows the file, never names a type the database does
not hold. Measured before: declared number over varchar, every SELECT of the table raised «Unknown PG numeric type».
"""
import copy
import time

from sqlalchemy import text

#: What a declared type asks of a column: nothing · a conversion · a conversion this product does not make.
NONE, CONVERT, NOT_DONE, REFUSED = "none", "convert", "not done", "refused"
#: The family a declared type is in the database (`schema_drift._type_family`'s words).
FAMILY = {"number": "number", "datetime": "datetime", "string": "text"}
#: THE cells - (the database's family, the declared type) -> the type the column becomes, the declared type the file
#: keeps until it has, and what its values must read as (None: every value does). Any other pair is NOT_DONE.
CELLS = {
    ("text", "number"): {"to": "double precision", "held": "string", "reads": "numbers"},
    ("text", "datetime"): {"to": "timestamp with time zone", "held": "string", "reads": "times"},
    ("datetime", "string"): {"to": "character varying", "held": "datetime", "reads": None},
}
#: A pair the database already takes as it is: a number column declared string reads and writes (lead aa8ff1af5).
TAKEN = {("number", "string")}
#: A text value a number column takes - `crud`'s write path reads it with float() and refuses nan/inf, so neither is here.
NUMBER_TEXT = r"^\s*[-+]?([0-9]+\.?[0-9]*|\.[0-9]+)([eE][-+]?[0-9]+)?\s*$"
#: What `assy_key_instant` hands back for a text it reads as a time (ISO, T, the zone's offset); a text it does not
#: read comes back as it was. The reading is `expression._wall`'s - the file read's, the key's (b3a6e64f7).
INSTANT_TEXT = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{6})?[+-][0-9]{2}:[0-9]{2}$"
#: The values a refusal shows.
SAMPLE = 5
#: Seconds of lock per GB of the table and its indexes - box measured 10-22: assy_test, 1,000,000 rows of a two-column
#: table with one join index, 9.8 s. A box number, said as an estimate.
LOCK_SECONDS_PER_GB = None


def family(engine, table, column):
    """The column's type family in the database - `schema_drift._type_family`'s words - or None (no such table or
    column, or a type it has no opinion on). PostgreSQL only: elsewhere None, and nothing is held or converted."""
    from sqlalchemy import inspect
    from admin import schema_drift

    if engine.dialect.name != "postgresql":
        return None
    try:
        columns = inspect(engine).get_columns(table)
    except Exception:                                           # noqa: BLE001 - a table not made yet
        return None
    found = [c for c in columns if c["name"] == column]
    return schema_drift._type_family(found[0]["type"]) if found else None


def verdict(declared, physical, values=None, key_uses=()):
    """THE judgment: the declared type, the database's family, where the column is a key, and - once read - the
    values' (count, sample) it cannot take -> (NONE | CONVERT | NOT_DONE | REFUSED, sentence or None)."""
    if physical is None or FAMILY.get(declared) in (None, physical) or (physical, declared) in TAKEN:
        return NONE, None
    cell = CELLS.get((physical, declared))
    if cell is None:
        return NOT_DONE, "a %s column is not converted to %s" % (physical, declared)
    if key_uses and cell["reads"]:
        return REFUSED, ("it is a key - %s - and a key's text changes with its type; keep it %s and fill a new column "
                         "through the chain" % (", ".join(key_uses), cell["held"]))
    if values and values[0]:
        count, sample = values
        return REFUSED, ("%d value(s) are not %s, e.g. %s - correct them in the table (or declare the column %s again), "
                         "then save the declaration" % (count, cell["reads"], ", ".join(repr(v) for v in sample),
                                                        cell["held"]))
    return CONVERT, None


def key_uses(table, column):
    """Where `table.column` is a key - each seat asked, none listed again here (lead 10-22 ㄱ): the row's key
    (`cell_layer.key_columns`), the map key, a decide rule's decision key, a join's key on either side."""
    from chain import cell_layer, enrich_declarations, synthesis
    from database import crud

    uses = []
    if column in cell_layer.key_columns(table):
        uses.append("the row key")
    if column in ((crud.TABLE_CONFIG.get(table) or {}).get("map_key_columns") or ()):
        uses.append("the map key")
    for rule in enrich_declarations.declarations(known_tables=crud.TABLE_CONFIG):
        if rule.get("source_table") == table and column in (rule.get("decision_key") or ()):
            uses.append("decide %s" % rule.get("name"))
    rules = list(synthesis._live_stood_rules())
    for name, t_, columns, _folds, skip, _kind in synthesis.declared_unique_targets(rules):
        if t_ == table and column in columns:
            uses.append("join %s" % name)
    for t_, columns, _folds in synthesis.declared_lookup_targets(rules):
        if t_ == table and column in columns:
            uses.append("a join's lookup")
    return list(dict.fromkeys(uses))


def hold(engine, table, declaration):
    """-> (the declaration to write, [(column, held type, declared type)]): each column the save would convert has the
    database's type kept in its place. A key column the conversion would change raises the refusal."""
    held, out = [], declaration
    for column, declared in sorted(((declaration or {}).get("column_types") or {}).items()):
        physical = family(engine, table, column)
        do, said = verdict(declared, physical)
        if do == CONVERT:
            do, said = verdict(declared, physical, key_uses=key_uses(table, column))
        if do == REFUSED:
            raise RetypeRefused(column, "%s stays %s: %s" % (column, physical, said))
        if do == CONVERT:
            if out is declaration:
                out = copy.deepcopy(declaration)
            cell = CELLS[(physical, declared)]
            out["column_types"][column] = cell["held"]
            held.append((column, cell["held"], declared))
    return out, held


class RetypeRefused(Exception):
    """A save the judgment refuses - the column and the sentence."""

    def __init__(self, column, sentence):
        super().__init__(sentence)
        self.column = column


def queue(table, column, held, declared):
    """The held column's conversion on the retroactive queue - the one already waiting or running for it, or a new run.
    -> what the save says about it."""
    import json
    from admin import retroactive
    from database import models
    from database.database import SessionLocal

    params = {"table": table, "column": column, "type": declared}
    db = SessionLocal()
    try:
        waiting = [run.run_id for run in db.query(models.RetroactiveRun).filter(
            models.RetroactiveRun.op == OP, models.RetroactiveRun.state.in_(
                (retroactive.RUN_QUEUED, retroactive.RUN_RUNNING))) if json.loads(run.params or "{}") == params]
        run_id = waiting[0] if waiting else retroactive.publish(db, OP, params)["run_id"]
        seconds = lock_estimate(db, table)
    finally:
        db.close()
    return {"column": column, "from": held, "to": declared, "run_id": run_id, "estimated_lock_seconds": seconds,
            "said": "%s: %s → %s queued, run %s, est. lock %s s - values are checked by the conversion - see the queue"
                    % (column, held, declared, run_id, seconds)}


#: The retroactive operation that converts a held column.
OP = "retype_column"


def _quoted(name):
    return '"%s"' % str(name).replace('"', '""')


def _sql(element, dialect):
    """`element` as SQL text in the CONNECTED dialect - an unconnected one assumes backslash escapes and doubles every
    backslash of a literal (probe 10-22: the regex then matched nothing it should)."""
    return str(element.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))


def _instant(c):
    """`c` through `assy_key_instant` on the operating zone - the key's own reading and spelling (b3a6e64f7)."""
    from sqlalchemy import func
    import expression
    import notation_norm

    return getattr(func, notation_norm.KEY_INSTANT_FUNCTION)(c, expression.time_zone().key)


def using(c, cell, dialect):
    """What `c` becomes in the cell's type: text -> number its blanks NULL (`crud.blank_to_null`) then cast; text ->
    time read by `assy_key_instant` then cast (its ISO carries the offset, so no session zone reads it); time -> text
    the key's spelling, not PostgreSQL's ::text."""
    from sqlalchemy import cast, literal_column
    from database import crud

    if cell["to"] == "character varying":
        return _sql(_instant(c), dialect)
    inner = crud.blank_to_null(c) if cell["reads"] == "numbers" else _instant(crud.blank_to_null(c))
    return "(%s)::%s" % (_sql(inner, dialect), cell["to"])


def bad_values(db, table, column, cell):
    """-> (count, up to SAMPLE distinct values) the column holds that the cell's type does not take - one statement."""
    from sqlalchemy import and_, column as sql_column, func, select, table as sql_table
    from database import crud

    c = sql_table(table, sql_column(column)).c[column]
    if not cell["reads"]:
        return 0, []
    bad = and_(crud.not_blank_sql_condition(c), c.op("!~")(NUMBER_TEXT) if cell["reads"] == "numbers"
               else _instant(c).op("!~")(INSTANT_TEXT))
    some = select(c).where(bad).distinct().limit(SAMPLE).subquery()
    query = select(func.count().filter(bad), select(func.array_agg(some.c[column])).scalar_subquery())
    count, sample = db.execute(query).one()
    return count or 0, sorted(sample or ())


def index_plan(db, table, column, ddls):
    """-> (rebuilt {name: (CREATE, comment)}, refused [name]) - the indexes reading the column that the conversion
    cannot keep: an expression or a non-btree over it (PostgreSQL refuses the ALTER under those, box measured 10-22).
    Each is built again by the product's own statement for its name, its comment kept (an automatic index's says why);
    an index the product does not build is refused by name."""
    rows = db.execute(text(
        "SELECT c.relname, (a.amname = 'btree' AND i.indexprs IS NULL AND i.indpred IS NULL) AS kept, "
        "obj_description(c.oid, 'pg_class') "
        "FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid JOIN pg_am a ON a.oid = c.relam "
        "JOIN pg_attribute t ON t.attrelid = i.indrelid AND t.attname = :column "
        "WHERE i.indrelid = CAST(:table AS regclass) AND NOT i.indisprimary AND EXISTS ("
        "  SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_class'::regclass AND d.objid = i.indexrelid"
        "     AND d.refobjid = i.indrelid AND d.refobjsubid = t.attnum)"),
        {"table": _quoted(table), "column": column}).fetchall()
    rebuilt, refused = {}, []
    for name, kept, said in rows:
        if kept:
            continue
        if name in ddls:
            rebuilt[name] = (ddls[name].replace("CONCURRENTLY ", "", 1).rstrip().rstrip(";"), said)
        else:
            refused.append(name)
    return rebuilt, refused


def model_config(table, column, declared):
    """This process's catalogue with `table.column` declared `declared` and nothing else changed - what the conversion
    builds its model from, so the product's index statements take the column's new type (`join_key_index`'s
    column_is_text reads the model). Only the conversion's own process: every other one follows the file."""
    from database import crud

    config = copy.deepcopy(crud.TABLE_CONFIG)
    config[table].setdefault("column_types", {})[column] = declared
    return config


def lock_estimate(db, table):
    """Seconds the conversion is estimated to hold the table - its size on disk at the box's rate."""
    size = db.execute(text("SELECT pg_total_relation_size(CAST(:table AS regclass))"), {"table": _quoted(table)}).scalar()
    return round((size or 0) / 1e9 * LOCK_SECONDS_PER_GB, 1)


def convert(db, table, column, declared, log):
    """The queued conversion: the values checked, the column converted with the indexes that read it - one transaction,
    the table locked for it - then the declared type written into the file. A refusal changes nothing."""
    from sqlalchemy import column as sql_column, table as sql_table
    from admin.retroactive import RetroactiveRefused
    from database import models
    from ledger import admin as ledger_admin
    import db_safety

    out = {"table": table, "column": column, "type": declared, "converted": False, "indexes_rebuilt": []}
    physical = family(db.get_bind(), table, column)
    cell = CELLS.get((physical, declared))
    if verdict(declared, physical)[0] != NONE:
        do, said = verdict(declared, physical, bad_values(db, table, column, cell) if cell else None,
                           key_uses(table, column))
        if do != CONVERT:
            raise RetroactiveRefused("%s.%s stays %s: %s" % (table, column, physical, said or "nothing to convert"))
        models.init_dynamic_models(model_config(table, column, declared))
        rebuilt, refused = index_plan(db, table, column, product_ddls(db, table))
        if refused:
            raise RetroactiveRefused(
                "%s.%s stays text: index(es) %s read it and the product does not build them - drop them, then save "
                "the declaration again" % (table, column, ", ".join(refused)))
        out["estimated_lock_seconds"] = lock_estimate(db, table)
        log("[Retype] %s.%s %s -> %s: rebuilding %s, est. lock %s s (box rate)"
            % (table, column, physical, declared, ", ".join(rebuilt) or "no index", out["estimated_lock_seconds"]))
        c = sql_table(table, sql_column(column)).c[column]
        began = time.monotonic()
        try:
            db.execute(text("SET LOCAL lock_timeout = '%s'" % db_safety.DDL_LOCK_TIMEOUT))
            for name in rebuilt:
                db.execute(text("DROP INDEX %s" % _quoted(name)))
            db.execute(text("ALTER TABLE %s ALTER COLUMN %s TYPE %s USING %s" % (
                _quoted(table), _quoted(column), cell["to"], using(c, cell, db.get_bind().dialect))))
            for name, (ddl, said) in rebuilt.items():
                db.execute(text(ddl))
                if said:
                    db.execute(text("COMMENT ON INDEX %s IS :said" % _quoted(name)), {"said": said})
            db.commit()
        except Exception as error:
            db.rollback()
            if db_safety.waited_past_the_lock_timeout(error):
                raise RetroactiveRefused(
                    "%s.%s stays text: another session held %s past %s - save the declaration again"
                    % (table, column, table, db_safety.DDL_LOCK_TIMEOUT)) from None
            raise
        out.update(converted=True, indexes_rebuilt=sorted(rebuilt), lock_seconds=round(time.monotonic() - began, 2))
    ledger_admin.set_column_type(table, column, declared)
    log("[Retype] %s.%s is %s - declared in table_config.json" % (table, column, declared))
    return out


def product_ddls(db, table):
    """{index name: CREATE} of every index the product builds on `table` from what this process's model says - the
    table's declared ones, its automatic ones, the joins' unique and lookup ones. Names are the identity."""
    from chain import join_key_index as vjc, synthesis
    from database import crud, models

    out = {name: models.table_index_ddl(dict(shape, name=name, table=t))
           for t, name, shape in models.table_declared_indexes({table: crud.TABLE_CONFIG.get(table) or {}})}
    # an automatic index: its columns from the catalogue (`index_states`' own read), why from its comment
    for name, said, columns, search in db.execute(text(
            "SELECT c.relname, obj_description(c.oid, 'pg_class'), "
            "ARRAY(SELECT a.attname FROM unnest(i.indkey::int2[]) WITH ORDINALITY AS k(attnum, n) "
            "      JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum "
            "      WHERE a.attname <> 'row_id' ORDER BY k.n), " + models._TRIGRAM_READS.format(x="i") +
            " FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
            "WHERE i.indrelid = CAST(:table AS regclass) AND c.relname LIKE :prefix"),
            {"table": _quoted(table), "prefix": models.AUTO_INDEX_PREFIX + "%"}):
        why = models.auto_index_why(said)
        columns = list(search or columns or ())
        if models.auto_index_name(table, columns, why) == name:
            out[name] = models.auto_index_ddl(table, columns, why)
    rules = list(synthesis._live_stood_rules())
    for _rule, t, columns, folds, skip, _kind in synthesis.declared_unique_targets(rules):
        if t == table and not skip:
            out[vjc.required_index_name(t, columns, folds)] = vjc.required_index_ddl(t, columns, folds)
    for t, columns, folds in synthesis.declared_lookup_targets(rules):
        if t == table:
            out[vjc.required_index_name(t, columns, folds, vjc.LOOKUP_PREFIX)] = \
                vjc.required_index_ddl(t, columns, folds, unique=False)
    return out
