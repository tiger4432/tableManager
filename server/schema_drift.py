"""Does this database carry the schema this build expects?

WHY THIS EXISTS
    Adding a column to a mapped model is a schema change, and `create_all` will not
    apply it to a table that already exists. On a database where the migration has
    not run, SQLAlchemy still names that column in every SELECT and every INSERT it
    generates for the table - so the table goes down entirely, including code paths
    that predate the column and never read it. That failure is invisible on any box
    where the migration HAS run, which is every box we develop and test on. The only
    place it shows up is production, on a screen, in front of an operator.

    The outages on 2026-08-05 had exactly this shape.

WHY IT IS A RUNTIME MODULE AND NOT ONLY A SCRIPT
    Because as a script it prevented nothing. It answered this question from the
    day it was written and was in no boot path, so the product owner still found
    the outages by using the product. The logic lives here so the web server and
    the launcher can call it; `server/scripts/check_schema_drift.py` is the CLI
    over the same code. That is the split `graph_orphans.py` /
    `scripts/graph_orphan_sweep.py` already uses, and the one
    `server/tests/test_prod_import_env.py` requires - a runtime module may never
    import from `server/scripts`.

WHAT IT DOES
    Walks every table SQLAlchemy has mapped - system tables and the dynamic tables
    built from table_config.json alike - and compares declared tables and columns
    against the database catalog. For each drift it reports what breaks and which
    migration to run.

WHAT IT DOES NOT DO
    It never writes. No DDL, no DML, no transaction that could leave anything
    changed: the only statements issued are catalog reads. Remedies are REPORTED
    for a human to run, deliberately - the whole point is a check that is safe to
    run against production at any moment, including while something is already
    broken. `run_at_startup` additionally never raises and never refuses; see the
    call sites in `server/main.py` and `run_decoupled_app.py` for why.

    It compares NAMES, not types. A column that exists with the wrong type is real
    drift and this will call it healthy. Name drift is what takes a table down.
"""
import glob
import os
import sys

from sqlalchemy import inspect


# Overrides, for remedies that are NOT a file anyone can run. Everything that IS
# a file is derived instead - see `_owner_from_sources`.
#
# This map used to be the only answer, and it went stale exactly the way a
# hand-maintained map does: `add_frame_confirmation.py` adds columns the map never
# recorded, so columns that took tables down on 2026-08-05 reported
# "no migration is recorded" while the migration that owns them sat in the tree.
# A check whose whole value is naming the fix cannot depend on somebody
# remembering to describe the fix here.
MIGRATION_OWNER = {
    ("database_outbox", "processed_chain"): "applied at web-server boot (main.py startup_event)",
    ("database_outbox", "broadcast_at"): "applied at web-server boot (main.py startup_event)",
}

# Where a runnable remedy can live. Read once per process, not per finding.
_MIGRATION_GLOBS = (
    os.path.join("server", "migrations", "*.py"),
    os.path.join("server", "scripts", "setup_*.py"),
    os.path.join("server", "scripts", "*migrate*.py"),
)
_SOURCE_CACHE = None

SEVERITY_ORDER = {"TABLE-DOWN": 0, "MISSING-TABLE": 1, "INFO": 2}


def _migration_sources():
    """Every file that could carry an ADD COLUMN, as {relative path: text}."""
    global _SOURCE_CACHE
    if _SOURCE_CACHE is None:
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        _SOURCE_CACHE = {}
        for pattern in _MIGRATION_GLOBS:
            for path in glob.glob(os.path.join(repo, pattern)):
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        _SOURCE_CACHE[os.path.relpath(path, repo).replace("\\", "/")] = f.read()
                except OSError:
                    continue
    return _SOURCE_CACHE


def _owner_from_sources(table, column):
    """Which file in the tree adds this column, found rather than remembered.

    Deliberately a shallow match - a file that says ADD COLUMN, names the column,
    and names the table. It does not parse SQL, because the statements it has to
    find are assembled from string fragments split across lines, and a parser that
    handled that would be a bigger thing to keep correct than the map it replaces.

    A wrong guess is cheap: the operator is pointed at a file to read, and the
    exact ALTER is printed underneath either way. Silence is what was expensive.
    """
    hits = [path for path, src in _migration_sources().items()
            if "ADD COLUMN" in src and column in src and table in src]
    if not hits:
        return None
    return " or ".join(sorted(hits))


def _declared():
    """Every table the running code has mapped, with its declared column names.

    Two things this has to get right, both of them measured rather than assumed.

    IT MUST NOT LEAVE `TESTING` BEHIND. The setdefault below keeps import side
    effects off the wire when this runs as a standalone script and nothing has
    imported the models yet. In a live server process the models are ALREADY
    imported, so the flag would buy nothing - and it is read all over the codebase
    to mean "this is a test process", so setting it inside a booting web server
    would quietly change behaviour far from here. It is therefore set only when it
    can still matter, and unset again either way.

    IT MUST SEE THE DYNAMIC TABLES. Importing `database.models` registers the
    system tables only; the config-driven ones arrive through
    `init_dynamic_models`, which every entry point calls for itself. Without this
    step the check reported on the system tables and silently ignored every table
    an operator actually has screens for - which is most of them, and exactly the
    tables a config edit can drift. Already-initialised is the normal case in a
    server process and this is then a no-op.
    """
    already_imported = "database.models" in sys.modules
    prior_testing = os.environ.get("TESTING")
    if not already_imported:
        os.environ.setdefault("TESTING", "True")
    try:
        from database.database import Base
        import database.models as _models  # noqa: F401  (registers mappings onto Base)
        _register_dynamic_models(_models)
        return {name: {c.name: c for c in table.columns}
                for name, table in Base.metadata.tables.items()}
    finally:
        if not already_imported:
            if prior_testing is None:
                os.environ.pop("TESTING", None)
            else:
                os.environ["TESTING"] = prior_testing


def _register_dynamic_models(models):
    """Build the config-driven models, but ONLY if nobody in this process has.

    The declaration -> model step is the system's own (`init_dynamic_models`), so
    what gets compared is what the running system expects rather than this
    script's reading of the JSON.

    THE GUARD IS THE POINT. `init_dynamic_models` mutates shared global state -
    `DYNAMIC_TABLES` and `Base.metadata` - and hot-swaps columns onto models that
    are already mapped. Every process that needs these tables already calls it
    with the config IT means: the web server with the live one, the test suite
    with its fixture. Loading the on-disk config over the top of a process that
    made a different choice would redefine tables out from under whatever is
    running. An empty registry means nobody has chosen yet, which is true only in
    a bare script - and that is precisely the case this exists to cover.

    A failure is reported and swallowed: a check that cannot see the dynamic
    tables is still worth running over the system ones.
    """
    if getattr(models, "DYNAMIC_TABLES", None):
        return
    try:
        from database import crud
        models.init_dynamic_models(crud.load_table_config_or_raise())
    except Exception as e:
        print(f"[drift] dynamic tables could not be loaded, checking system tables "
              f"only: {type(e).__name__}: {e}")


def _actual(engine):
    """Catalog state. `inspect` reads information_schema on PostgreSQL and the
    equivalent pragma on SQLite, so one code path covers production and a simulated
    database built for testing.

    `get_multi_columns` answers for every table in one statement. The per-table
    loop it replaces issued one round trip per table, which is the whole cost of
    this check and the reason it was affordable as a script but worth trimming now
    that it runs on every boot. The loop stays as a fallback for any dialect whose
    inspector does not implement the batch form.
    """
    insp = inspect(engine)
    if hasattr(insp, "get_multi_columns"):
        try:
            # Keys are (schema, table); the default schema is the only one mapped.
            return {key[1]: {c["name"] for c in cols}
                    for key, cols in insp.get_multi_columns().items()}
        except Exception:
            pass
    return {t: {c["name"] for c in insp.get_columns(t)} for t in insp.get_table_names()}


def _add_column_ddl(table, col, dialect):
    """The statement a human should run. Printed, never executed."""
    try:
        type_sql = col.type.compile(dialect)
    except Exception:
        type_sql = "<declare the type by hand - it did not compile for this dialect>"
    stmt = f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS "{col.name}" {type_sql}'
    if not col.nullable:
        return (stmt + " /* declared NOT NULL - a table with rows in it needs a "
                       "DEFAULT or a backfill, so do not paste this unedited */")
    return stmt


def check(engine):
    declared, actual = _declared(), _actual(engine)
    dialect = engine.dialect
    findings = []

    for table, columns in sorted(declared.items()):
        if table not in actual:
            findings.append({
                "severity": "MISSING-TABLE", "table": table, "column": None,
                "breaks": "every query against this table fails",
                "remedy": ("boot the web server once - Base.metadata.create_all builds a "
                           "missing table whole. If it stays missing after a boot, the "
                           "mapping is registered somewhere create_all does not reach."),
            })
            continue

        missing = [c for name, c in columns.items() if name not in actual[table]]
        for col in missing:
            owner = (MIGRATION_OWNER.get((table, col.name))
                     or _owner_from_sources(table, col.name))
            findings.append({
                "severity": "TABLE-DOWN", "table": table, "column": col.name,
                "breaks": (f"EVERY full-entity SELECT and EVERY ORM INSERT on {table} "
                           f"fails, not only code that reads {col.name}"),
                # The old sentence here told the reader to record the new migration in
                # MIGRATION_OWNER by hand. That instruction is stale: owners are DERIVED by
                # scanning server/migrations/ and scripts/setup_*.py, and the hand-maintained
                # table is only a fallback for what the scan cannot see. Telling someone to
                # hand-register a migration the scan would have found is how the table went
                # stale in the first place - it listed nothing for two columns whose migration
                # was sitting in the tree, and this check then printed "no migration is
                # recorded" about a migration that existed.
                "remedy": (f"run {owner}" if owner else
                           "no migration is recorded for this column - add one under "
                           "server/migrations/ and it will be found here automatically")
                          + "\n        or: " + _add_column_ddl(table, col, dialect),
            })

        extra = sorted(actual[table] - set(columns))
        if extra:
            findings.append({
                "severity": "INFO", "table": table, "column": ", ".join(extra),
                "breaks": "nothing - the database carries columns the code does not map",
                "remedy": "harmless. Worth a look if one of these was meant to be dropped.",
            })

    findings.sort(key=lambda f: (SEVERITY_ORDER[f["severity"]], f["table"], f["column"] or ""))
    return findings


_RULE = "=" * 68


def banner_lines(findings, target):
    """The verdict as an operator should read it, as ``(level, text)`` pairs.

    Shaped after the launcher's port-conflict verdict rather than invented fresh:
    a rule line, what is wrong, what it breaks, what to run, and a Korean
    [HOW TO FIX] line. Two properties matter and both are asserted by the tests.

    THE REMEDY IS COPIED, NOT SUMMARISED. `check` already works out which
    migration owns each column; a startup path that condensed that to "schema
    drift detected" would hand the operator a symptom and keep the answer.

    A CLEAN CHECK IS ONE QUIET LINE. The banner has to mean "something is broken"
    or it becomes wallpaper, so INFO findings - columns the database has and the
    code does not map, which break nothing - never raise it.
    """
    blocking = [f for f in findings if f["severity"] != "INFO"]
    extra = len(findings) - len(blocking)
    if not blocking:
        detail = f" ({extra} unmapped column group(s), harmless)" if extra else ""
        return [("info", f"[Schema] no drift - the database carries every table and "
                         f"column the code maps{detail}.")]

    out = [("error", _RULE),
           ("error", f"SCHEMA DRIFT: the database is missing {len(blocking)} thing(s) "
                     f"this build requires."),
           ("error", f"  target: {target}")]
    for f in blocking:
        name = f"{f['table']}.{f['column']}" if f["column"] else f["table"]
        out.append(("error", f"  [{f['severity']}] {name}"))
        out.append(("error", f"      breaks: {f['breaks']}"))
        for i, line in enumerate(f["remedy"].splitlines()):
            out.append(("error", f"      do:     {line}" if i == 0 else f"  {line}"))
    out += [
        ("error", "  Every screen that touches the table(s) above fails until the "
                  "column exists."),
        # Says why it did not refuse, so nobody reads a start as "the check passed
        # and something else is wrong".
        ("error", "  Starting anyway ON PURPOSE: the rest of the product works, and "
                  "refusing here would"),
        ("error", "  turn one broken table into a dead stack - including on an "
                  "unattended restart."),
        ("error", "  [HOW TO FIX] 위 마이그레이션을 실행한 뒤 서버를 재기동하십시오. "
                  "실행 전까지 해당 테이블을"),
        ("error", "  쓰는 화면은 계속 실패합니다. 전체 점검: "
                  "python server/scripts/check_schema_drift.py"),
        ("error", _RULE),
    ]
    return out


def run_at_startup(engine, emit, target=None):
    """Report drift into a running process's log. Never raises, never blocks.

    `emit(level, text)` is the caller's own logger, so the verdict lands wherever
    that process already writes - console for the operator standing there, file
    for the one reading it afterwards. The web server and the launcher pass their
    own and therefore cannot drift into two different formats.

    NEVER RAISES is load-bearing. This runs inside a boot sequence whose job is to
    bring the product up. A check meant to prevent an outage must not be able to
    cause one, so every failure here degrades to a warning and the boot continues.

    Returns the findings, or None when the check could not run.
    """
    try:
        findings = check(engine)
    except Exception as e:
        emit("error", f"[Schema] drift check could not run ({type(e).__name__}: {e}). "
                      f"Starting anyway - run "
                      f"'python server/scripts/check_schema_drift.py' by hand.")
        return None
    for level, text in banner_lines(findings, target or str(engine.url)):
        emit(level, text)
    return findings
