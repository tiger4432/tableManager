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
NONE, CONVERT, NOT_DONE = "none", "convert", "not done"
#: The declared types a text column is converted into, and the type the model compiles each to (`models.sql_type_of`).
CONVERTS_TO = {"number": "double precision"}
#: The declared type a text column keeps in the file until its conversion is done.
HELD = "string"
#: A text value a number column takes - `crud`'s write path reads it with float() and refuses nan/inf, so neither is here.
NUMBER_TEXT = r"^\s*[-+]?([0-9]+\.?[0-9]*|\.[0-9]+)([eE][-+]?[0-9]+)?\s*$"
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


def verdict(declared, physical, values=None):
    """THE judgment: the declared type, the database's family, and - once read - the values' (count, sample) that the
    declared type cannot take -> (NONE | CONVERT | NOT_DONE | "refused", sentence or None)."""
    if physical is None or physical == declared or declared not in ("number", "datetime"):
        return NONE, None
    if physical != "text":
        return NONE, None
    if declared not in CONVERTS_TO:
        return NOT_DONE, "a text column is not converted to %s - only to %s" % (declared, ", ".join(CONVERTS_TO))
    if values and values[0]:
        count, sample = values
        return "refused", ("%d value(s) are not numbers, e.g. %s - correct them in the table (or declare the column "
                           "string again), then save the declaration" % (count, ", ".join(repr(v) for v in sample)))
    return CONVERT, None


def hold(engine, table, declaration):
    """-> (the declaration to write, [(column, held type, declared type)]): each column the save would convert has the
    database's type kept in its place."""
    held, out = [], declaration
    for column, declared in sorted(((declaration or {}).get("column_types") or {}).items()):
        if verdict(declared, family(engine, table, column))[0] == CONVERT:
            if out is declaration:
                out = copy.deepcopy(declaration)
            out["column_types"][column] = HELD
            held.append((column, HELD, declared))
    return out, held


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


def bad_values(db, table, column):
    """-> (count, up to SAMPLE distinct values) the column holds that a number column does not take - one statement."""
    from sqlalchemy import and_, column as sql_column, func, select, table as sql_table
    from sqlalchemy.dialects import postgresql
    from database import crud

    c = sql_table(table, sql_column(column)).c[column]
    bad = and_(crud.not_blank_sql_condition(c), c.op("!~")(NUMBER_TEXT))
    some = select(c).where(bad).distinct().limit(SAMPLE).subquery()
    query = select(func.count().filter(bad), select(func.array_agg(some.c[column])).scalar_subquery())
    count, sample = db.execute(text(str(query.compile(dialect=postgresql.dialect(),
                                                      compile_kwargs={"literal_binds": True})))).one()
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
    from sqlalchemy.dialects import postgresql
    from admin.retroactive import RetroactiveRefused
    from database import crud, models
    from ledger import admin as ledger_admin
    import db_safety

    out = {"table": table, "column": column, "type": declared, "converted": False, "indexes_rebuilt": []}
    physical = family(db.get_bind(), table, column)
    if physical != declared:
        do, said = verdict(declared, physical, bad_values(db, table, column) if physical == "text" else None)
        if do != CONVERT:
            raise RetroactiveRefused("%s.%s stays %s: %s" % (table, column, physical, said or "nothing to convert"))
        models.init_dynamic_models(model_config(table, column, declared))
        rebuilt, refused = index_plan(db, table, column, product_ddls(db, table))
        if refused:
            raise RetroactiveRefused(
                "%s.%s stays text: index(es) %s read it and the product does not build them - drop them, then save "
                "the declaration again" % (table, column, ", ".join(refused)))
        out["estimated_lock_seconds"] = lock_estimate(db, table)
        log("[Retype] %s.%s text -> %s: rebuilding %s, est. lock %s s (box rate)"
            % (table, column, declared, ", ".join(rebuilt) or "no index", out["estimated_lock_seconds"]))
        c = sql_table(table, sql_column(column)).c[column]
        using = str(crud.blank_to_null(c).compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        began = time.monotonic()
        try:
            db.execute(text("SET LOCAL lock_timeout = '%s'" % db_safety.DDL_LOCK_TIMEOUT))
            for name in rebuilt:
                db.execute(text("DROP INDEX %s" % _quoted(name)))
            db.execute(text("ALTER TABLE %s ALTER COLUMN %s TYPE %s USING (%s)::%s" % (
                _quoted(table), _quoted(column), CONVERTS_TO[declared], using, CONVERTS_TO[declared])))
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
