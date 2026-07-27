"""Report physical schema that ``table_config.json`` no longer declares.

Why this exists
---------------
Declaring a table is a one-way door. The config watcher turns a new declaration
into a physical ``CREATE TABLE`` within about a second, and adding a column to an
existing declaration turns into ``ALTER TABLE ... ADD COLUMN``. **Nothing in the
system ever drops either one.** Reverting the declaration therefore leaves the
physical object behind, declared nowhere, invisible to every screen -- and
invisible to ``git``, because ``server/config/`` is not tracked.

That is not hypothetical. On 2026-07-27 a ``map_band_registry`` declaration was
installed into the live ``table_config.json`` while an abandoned model was being
built. The watcher created the table. The declaration was then reverted cleanly.
The empty table is still there.

So a rollback needs an answer to "what did the forward deploy leave in the
database". This script is that answer. It is **read-only**: it issues SELECTs
against catalogs, never DDL. It prints the ``DROP`` statements an operator may
choose to run, and deliberately does not run them -- dropping a table that turns
out to hold the only copy of something is not a decision a script should make at
2am.

What it reports
---------------
``UNDECLARED TABLE``
    A physical table that is neither declared in ``table_config.json`` nor one of
    the product's own system tables. Row count separates the two causes that
    matter: an **empty** one is almost certainly a reverted declaration (nothing
    ever wrote to it), while a **populated** one is far more likely to be a legacy
    table from before the config existed -- do not drop that one on a hunch.

``UNDECLARED COLUMN``
    A physical column on a still-declared table that the declaration no longer
    mentions. This is where a rolled-back column addition accumulates. Ingestion
    drops values for undeclared columns and the grid never shows them, so the
    column is inert -- but it is still in the row, and it is still NOT NULL-free
    space no one can account for.

``DECLARED BUT MISSING``
    The inverse: declared in config, absent from the database. Usually means a
    declaration landed while nothing reloaded (an atomic temp+rename write does
    not fire the config watcher). ``POST /admin/reload-configs`` or a restart
    creates it.

Usage
-----
    conda run -n assy_manager python server/scripts/list_undeclared_tables.py
    conda run -n assy_manager python server/scripts/list_undeclared_tables.py --db-url postgresql://...
    conda run -n assy_manager python server/scripts/list_undeclared_tables.py --schema public

Honours ``DATABASE_URL`` and ``ASSY_DATA_ROOT`` exactly like every other entry
point, so pointing it at the isolated environment is a matter of environment, not
of flags.

Exit codes: ``0`` nothing undeclared | ``1`` residue found | ``2`` error.
"""
import argparse
import json
import os
import sys

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import paths  # noqa: E402


def declared_tables(config_path):
    """Table names declared in table_config.json.

    A missing or unreadable file returns None rather than an empty set: "the
    config declares nothing" and "I could not read the config" must not produce
    the same report, because the first would list every table in the database as
    residue.
    """
    if not os.path.exists(config_path):
        return None
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return None
    if not isinstance(cfg, dict):
        return None
    return set(cfg.keys())


def build_models(config_path):
    """Build the dynamic ORM models from the config on disk, and return them.

    The declaration -> model step is the system's own (``init_dynamic_models``),
    so this report is answering "what does the running system expect" rather than
    "what does this script think the JSON means".
    """
    from database import models
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    models.init_dynamic_models(cfg)
    return models


def system_tables(models):
    """Product-owned tables that exist independently of table_config.json.

    Derived, not hardcoded: everything registered on ``Base.metadata`` minus the
    dynamic (config-driven) models. A system table added to models.py six months
    from now is therefore covered without editing this script.
    """
    return set(models.Base.metadata.tables.keys()) - set(models.DYNAMIC_TABLES.keys())


def physical_tables(conn, schema):
    from sqlalchemy import text
    rows = conn.execute(text(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = :s AND table_type = 'BASE TABLE' "
        "ORDER BY table_name"
    ), {"s": schema}).fetchall()
    return [r[0] for r in rows]


def approximate_rows(conn, schema, table):
    """(estimate, is_exact). Never a full COUNT(*) on a large table.

    ``reltuples`` is the planner's estimate and costs nothing; on a table that has
    never been analysed it is -1. The only thing this report actually needs to
    decide is "empty or not", so an unknown estimate falls back to a LIMIT 1
    existence probe, which is O(1) regardless of table size.
    """
    from sqlalchemy import text
    est = conn.execute(text(
        "SELECT c.reltuples::bigint FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = :s AND c.relname = :t"
    ), {"s": schema, "t": table}).scalar()
    if est is not None and est > 0:
        return est, False
    has_any = conn.execute(text(f'SELECT 1 FROM "{table}" LIMIT 1')).first() is not None
    return (None if has_any else 0), True


def physical_columns(conn, schema, table):
    from sqlalchemy import text
    rows = conn.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = :s AND table_name = :t ORDER BY ordinal_position"
    ), {"s": schema, "t": table}).fetchall()
    return [r[0] for r in rows]


def modelled_columns(table):
    """Columns the running system expects on a declared table, lowercased.

    Read off the built ORM model rather than re-derived from the JSON. The model
    is what ``init_dynamic_models`` actually produces -- declared ``column_types``
    plus the seven bookkeeping columns every dynamic table carries (``row_id``,
    ``business_key_val``, ``created_at``, ``updated_at``, ``is_graph_synced``,
    ``needs_graph_rollback``, ``graph_synced_at``). Reimplementing that list here
    would put a second copy of the rule in the tree, and the first version of this
    script proved the point by reporting the graph bookkeeping columns as residue
    on all 21 tables. Anything physical and outside this set is residue.
    """
    from database import models
    model = models.DYNAMIC_TABLES.get(table)
    if model is None:
        return None
    return {c.name.lower() for c in model.__table__.columns}


def run(db_url=None, schema="public", out=None):
    out = out if out is not None else sys.stdout
    if db_url:
        os.environ["DATABASE_URL"] = db_url

    config_path = paths.config_path("table_config.json")
    declared = declared_tables(config_path)
    if declared is None:
        print(f"error: cannot read {config_path} -- refusing to report, because an "
              f"unreadable config would make every table look undeclared.", file=out)
        return 2

    from database.database import engine

    try:
        system = system_tables(build_models(config_path))
    except Exception as err:
        print(f"error: could not enumerate the product's system tables: {err}", file=out)
        return 2

    lines = []
    lines.append("assyManager -- undeclared physical schema report  [READ ONLY]")
    lines.append("")
    lines.append(f"  config   : {config_path}  ({len(declared)} table(s) declared)")
    lines.append(f"  data root: {paths.DATA_ROOT}   isolated={paths.IS_ISOLATED}")
    lines.append("")

    undeclared, missing, col_residue = [], [], []

    with engine.connect() as conn:
        lines.append(f"  database : {conn.execute(_text()).scalar()}  schema={schema}")
        lines.append("")
        present = physical_tables(conn, schema)
        present_set = set(present)

        for t in present:
            if t in declared or t in system:
                continue
            est, exact = approximate_rows(conn, schema, t)
            undeclared.append((t, est, exact))

        for t in sorted(declared):
            if t not in present_set:
                missing.append(t)

        for t in sorted(declared & present_set):
            expected = modelled_columns(t)
            if expected is None:
                continue  # declared but the model failed to build - not a column question
            phys = physical_columns(conn, schema, t)
            extra = [c for c in phys if c.lower() not in expected]
            if extra:
                col_residue.append((t, extra))

    if undeclared:
        lines.append(f"  UNDECLARED TABLE(S) -- {len(undeclared)} found")
        lines.append("")
        for t, est, exact in undeclared:
            if est == 0:
                verdict = "EMPTY -- consistent with a declaration that was created and then reverted"
            elif est is None:
                verdict = "has rows (count unknown -- never analysed). Treat as REAL DATA."
            else:
                verdict = f"~{est:,} rows (planner estimate). Treat as REAL DATA."
            lines.append(f"    {t}")
            lines.append(f"        {verdict}")
        lines.append("")
        lines.append("    Nothing here is dropped by this script. If -- and only if -- you have")
        lines.append("    confirmed a table is residue, the statement is:")
        lines.append("")
        for t, est, _ in undeclared:
            mark = "" if est == 0 else "    -- NOT EMPTY: confirm before running"
            lines.append(f'        DROP TABLE "{t}";{mark}')
        lines.append("")
    else:
        lines.append("  UNDECLARED TABLE(S) -- none")
        lines.append("")

    if col_residue:
        lines.append(f"  UNDECLARED COLUMN(S) -- on {len(col_residue)} declared table(s)")
        lines.append("    A column added by a config change and left behind when the change was")
        lines.append("    reverted. Ingestion drops values for it and the grid never renders it.")
        lines.append("")
        for t, cols in col_residue:
            lines.append(f"    {t}: {', '.join(cols)}")
            for c in cols:
                lines.append(f'        ALTER TABLE "{t}" DROP COLUMN "{c}";')
        lines.append("")
    else:
        lines.append("  UNDECLARED COLUMN(S) -- none")
        lines.append("")

    if missing:
        lines.append(f"  DECLARED BUT MISSING -- {len(missing)}")
        lines.append("    Declared in config, absent from the database. Usually a declaration that")
        lines.append("    landed without firing the config watcher (an atomic temp+rename write does")
        lines.append("    not fire it). POST /admin/reload-configs, or restart, creates them.")
        lines.append("")
        for t in missing:
            lines.append(f"    {t}")
        lines.append("")

    print("\n".join(lines), file=out)
    return 1 if (undeclared or col_residue or missing) else 0


def _text():
    from sqlalchemy import text
    return text("SELECT current_database()")


def main(argv=None):
    try:
        sys.stdout.reconfigure(errors="backslashreplace")
    except Exception:
        pass
    p = argparse.ArgumentParser(
        description="Report physical tables/columns that table_config.json no longer declares (read-only).")
    p.add_argument("--db-url", help="override DATABASE_URL for this run")
    p.add_argument("--schema", default="public")
    args = p.parse_args(argv)
    try:
        return run(db_url=args.db_url, schema=args.schema)
    except Exception as err:
        print(f"error: {err}", file=sys.stdout)
        return 2


if __name__ == "__main__":
    sys.exit(main())
