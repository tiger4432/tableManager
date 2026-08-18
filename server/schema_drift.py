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
    over the same code. This is the split `chain_replay.py` /
    `scripts/chain_replay_cli.py` uses, and the one
    `server/tests/test_prod_import_env.py` requires - a runtime module may never
    import from `server/scripts`.

WHAT IT DOES
    Walks every table SQLAlchemy has mapped - system tables and the dynamic tables
    built from table_config.json alike - and compares declared tables and columns
    against the database catalog. For each drift it reports what breaks and which
    migration to run.

    It compares NAMES and TYPES. Names first, because a missing name takes the
    table down; types second, at INFO, because one kind of type drift takes the
    table down just as hard and nothing anywhere reported it. On 2026-08-18 an
    ordinary query against `dt_log` returned

        sqlalchemy.exc.InvalidRequestError: Unknown PG numeric type: 1043

    - OID 1043 is `varchar`, the column was declared `number`, and the table had
    been in that state for an unknown length of time while this check called it
    healthy. A sweep of all 26 declared tables then found three more breaking
    columns (`bonding_log.core_slot`, `bonding_log.dt_slot`, `dt_map.dt_slot`) and
    one that merely lied (`lot_event.event_time`, declared `datetime` over
    varchar). See `_type_findings` for the two buckets and why they are ranked.

WHAT IT DOES NOT DO
    It never writes. No DDL, no DML, no transaction that could leave anything
    changed: the only statements issued are catalog reads. Remedies are REPORTED
    for a human to run, deliberately - the whole point is a check that is safe to
    run against production at any moment, including while something is already
    broken. `run_at_startup` additionally never raises and never refuses; see the
    call sites in `server/main.py` and `run_decoupled_app.py` for why.

    It never REPAIRS a type, and never proposes a cast. That is a ruling with a
    measurement behind it, not an omission - see `_sync_repairs`.

WHAT IT IS ALLOWED TO CALL HARMLESS
    One drift kind repairs itself, and saying otherwise cost an operator a restart
    on 2026-08-13. See `_sync_repairs` for the predicate and where it comes from.
    Everything else keeps the full-severity banner, including every drift kind this
    module cannot see - the classification is a whitelist of one condition, so a
    finding it does not recognise is loud by construction rather than by intent.
"""
import glob
import os
import sys

from sqlalchemy import inspect
from sqlalchemy import types as sqltypes


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
#
# `*.sql` added 2026-08-13, and it is the SAME failure the comment above records,
# one file extension over. `add_ingestion_ledger_path_stat.sql` adds two columns
# to `file_ingestion_checkpoints`; without this line the banner said "no
# migration is recorded for this column - add one" while the migration that owns
# them sat in the tree. It went unnoticed until now because every earlier `.sql`
# migration here creates INDEXES, and this check does not look at indexes at all,
# so a `.sql` file had never owned a finding before.
_MIGRATION_GLOBS = (
    os.path.join("server", "migrations", "*.py"),
    os.path.join("server", "migrations", "*.sql"),
    os.path.join("server", "scripts", "setup_*.py"),
    os.path.join("server", "scripts", "*migrate*.py"),
)
_SOURCE_CACHE = None

SEVERITY_ORDER = {"TABLE-DOWN": 0, "MISSING-TABLE": 1, "SELF-HEALING": 2, "INFO": 3}

# Rank INSIDE a severity. Everything INFO is quiet, but the three INFO kinds are
# not equally urgent - see the sort in `check`. Anything without a `kind` gets 0,
# which is why the severities that have no kinds keep their previous order.
_KIND_ORDER = {"type-breaking": 1, "type-mismatch": 2, "unmapped-column": 3}
TYPE_KINDS = ("type-breaking", "type-mismatch")


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


def _dynamic_table_names():
    """The exact dict `sync_dynamic_tables_schema` loops over, read - not copied.

    Deliberately `models.DYNAMIC_TABLES` and not `table_config.json`. The config is
    the DECLARATION; this dict is what the repairer actually iterates, and the two
    can differ inside one process (a config the watcher has not picked up, a test
    process that mapped a fixture config instead of the file on disk). Reading the
    repairer's own input is the only way the classification cannot be wrong about
    the repairer.

    `_declared` has already imported the models and registered the dynamic ones by
    the time `check` gets here, so this costs an attribute lookup.

    An empty answer on failure is the SAFE direction and that is why the except is
    this broad: nothing is then classified as self-healing and every finding keeps
    today's full severity. A classifier that cannot see the repairer must not get
    to call anything harmless.
    """
    try:
        from database import models
        return set(getattr(models, "DYNAMIC_TABLES", None) or ())
    except Exception:
        return set()


def _sync_repairs(table, column_name, actual_columns, dynamic_names):
    """Will `models.sync_dynamic_tables_schema` add this column by itself?

    WHY THIS QUESTION HAS TO BE ASKED AT ALL
        The launcher checks for drift BEFORE it spawns the children, and two of
        those children - run_watcher.py and run_chain_worker.py -
        call `sync_dynamic_tables_schema(engine)` on their own boot, as does the
        web server through `bootstrap_database_schema`. So the launcher reports a
        state that the startup it is beginning then repairs, seconds later. That is
        a cross-process ordering, not a bug in either half, and it is not fixable by
        moving the check: the value of a pre-flight is that it runs before the
        restart. What was fixable is the banner, which told the operator that every
        screen touching the table failed until they wrote a migration - when nothing
        was required of them and the column existed by the time they read the line.

    THE PREDICATE, TAKEN FROM THE REPAIRER'S SOURCE
        `models.sync_dynamic_tables_schema` is a loop of three gates, and each
        condition below is one of them, in order:

            for table_name, model_class in DYNAMIC_TABLES.items():   -> (1)
                if not inspector.has_table(table_name): continue     -> (2)
                db_cols = {c["name"].lower() for c in ...}
                for column in table_obj.columns:
                    if column.name.lower() not in db_cols:            -> (3)
                        ALTER TABLE ... ADD COLUMN ...

        (1) The table is in DYNAMIC_TABLES. A system table - one declared as an ORM
            class in database/models.py - is not in that dict and no boot path
            ALTERs it. That is the 2026-08-05 incident shape and it stays loud.
        (2) The table already exists physically. The sync `continue`s past a table
            that does not, so a MISSING-TABLE finding is never self-healing here.
            MEASURED NOTE: this gate is currently unreachable from `check`, which
            has its own `continue` for an absent table several lines earlier and so
            never asks about one. It is kept because it is what makes this function
            correct on its own - it is a statement about the repairer, not about
            its one caller - and because the day that early `continue` moves, this
            is the line that stops a missing table being called self-healing. It is
            covered by the unit test and by nothing else; an injection that removes
            it leaves every database-level test green.
        (3) The name is absent CASE-INSENSITIVELY. This one matters and is not
            pedantry: `check` compares names exactly, the sync compares them
            lowercased. A column declared `Foo` against a database holding `foo` is
            therefore reported by this module and skipped forever by the sync. It is
            permanently stuck, it never even logs a failure, and only this third
            condition keeps it out of the self-healing bucket.

    WHAT THIS DELIBERATELY DOES NOT CLAIM
        Only that the sync will ISSUE the ALTER - not that it will succeed. The
        statement can still fail on a lock, a privilege, or a type that will not
        compile, and `sync_dynamic_tables_schema` swallows that into a printed
        `[Schema Sync] Failed to add column`. No catalog read can predict it, so the
        remedy text says so and tells the operator what a second sighting means.
        That is the one thing the check cannot tell, stated instead of guessed.

    WHY IT ONLY EVER ISSUES ADD COLUMN, AND WHY THAT IS RIGHT
        The sync never alters a type and never drops, so no other drift kind can
        reach this bucket - `_type_findings` detects type drift and proposes no
        repair for it at all. That asymmetry is a ruling, taken 2026-08-19 after
        the owner asked why an automatic `ALTER TYPE` was not simply added, and it
        is recorded here because this function is where the next person will ask.

        The answer is not "casts are risky in general". It is these three
        measurements, taken on the live database against the columns that were
        actually mismatched:

            dt_log.core_slot    4,567 rows are not numeric   e.g. C14, C23, C19
            dt_log.dt_slot      4,567 rows are not numeric   e.g. S18, S25, S13
            lot_event.event_time  0 rows fail to parse - but 3 distinct formats
                                  (20-char, 19-char, 21,150 other) and 522 NULLs

        `core_slot` and `dt_slot` are PREFIXED IDENTIFIERS, not numbers wearing a
        letter. `C14` is a core slot, and a cast either refuses the whole
        statement or - depending on how it is written - strips the prefix and
        stores `14`, silently destroying the distinction between `C14` and `S14`
        on 4,567 rows. There is no automatic reading of that column that is both
        successful and correct.

        `event_time` is the worse one, because it is the case that LOOKS safe: it
        parses cleanly, so a cast would succeed, report success, and be wrong. The
        three formats do not share a timezone basis, so converting them to
        timestamptz in one statement leaves a subset of the values sitting hours
        away from the instant they describe - and nothing downstream would ever
        raise about it.

        A column that is merely absent has exactly one correct repair, which is
        why the sync may make it. A column that is present with the wrong type has
        a repair that depends on what the values MEAN, and that is a decision, not
        a migration. So this module reports and names the declaration site, and
        stops there.
    """
    if table not in dynamic_names:
        return False
    if actual_columns is None:
        return False
    return column_name.lower() not in {c.lower() for c in actual_columns}


def _actual(engine):
    """Catalog state as ``{table: {column name: reflected type}}``.

    `inspect` reads information_schema on PostgreSQL and the equivalent pragma on
    SQLite, so one code path covers production and a simulated database built for
    testing.

    `get_multi_columns` answers for every table in one statement. The per-table
    loop it replaces issued one round trip per table, which is the whole cost of
    this check and the reason it was affordable as a script but worth trimming now
    that it runs on every boot. The loop stays as a fallback for any dialect whose
    inspector does not implement the batch form.

    THE TYPE COMES FROM THE SAME READ. It used to return a set of names and the
    type was discarded, so `_type_findings` would have cost a second sweep of the
    catalog on every boot to recover something already in hand. Callers that only
    want names iterate the dict, which yields exactly the old set.
    """
    insp = inspect(engine)
    if hasattr(insp, "get_multi_columns"):
        try:
            # Keys are (schema, table); the default schema is the only one mapped.
            return {key[1]: {c["name"]: c.get("type") for c in cols}
                    for key, cols in insp.get_multi_columns().items()}
        except Exception:
            pass
    return {t: {c["name"]: c.get("type") for c in insp.get_columns(t)}
            for t in insp.get_table_names()}


def _type_family(t):
    """The coarse class of a column type, or None when this module cannot tell.

    Deliberately coarse. `String(50)` against `varchar(120)`, `TIMESTAMP` against
    `TIMESTAMP WITH TIME ZONE`, `Float` against `numeric(10,2)` - all real
    differences, none of them the failure this exists to catch, and a check that
    printed them daily would be scrolled past within a week along with the one
    that matters. Four families, and everything else answers None.

    NONE MEANS "NO OPINION", NOT "MATCHES". A type this does not recognise -
    jsonb, bytea, an array, a PG domain, anything the inspector hands back as
    NullType - produces no finding rather than a guess. That is the safe direction
    for an INFO-severity check whose whole value is that its findings are real:
    the one exception is the numeric case below, which is breaking whatever the
    other side turns out to be, so it tests for numeric POSITIVELY instead.
    """
    if t is None:
        return None
    try:
        if isinstance(t, sqltypes.NullType):
            return None
        # Boolean first: it is not an Integer subclass here, but ordering the test
        # this way survives a dialect where it is.
        if isinstance(t, sqltypes.Boolean):
            return "boolean"
        if isinstance(t, (sqltypes.Numeric, sqltypes.Integer)):
            return "number"
        if isinstance(t, (sqltypes.DateTime, sqltypes.Date, sqltypes.Time)):
            return "datetime"
        # Text and Enum are String subclasses; JSON, Uuid and LargeBinary are not.
        if isinstance(t, sqltypes.String):
            return "text"
    except Exception:
        return None
    return None


# What a `column_types` entry in table_config.json has to say to produce each
# family. Read off `models.init_dynamic_models`, which is a three-way branch:
# "number" -> Float, "datetime" -> DateTime(timezone=True), anything else ->
# String. So the remedy can name the exact edit for a dynamic table.
_CONFIG_WORD = {"number": '"number"', "datetime": '"datetime"',
                "text": 'anything other than "number"/"datetime"',
                "boolean": 'anything other than "number"/"datetime"'}


def _type_findings(table, columns, actual_types, dynamic_names):
    """Columns that exist under a type the declaration does not describe.

    TWO BUCKETS, BECAUSE THEY LEAD TO DIFFERENT ACTIONS.

    (a) BREAKING - `number` declared over a column that is not numeric. This is
        not "one column reads oddly": SQLAlchemy names every mapped column in
        every full-entity SELECT, and psycopg2's numeric result processor
        (`sqlalchemy/dialects/postgresql/_psycopg_common.py`, `_PsycopgNumeric`,
        which `Float` inherits through `_PsycopgFloat`) has no reader for an OID
        outside float/decimal/int - it raises `InvalidRequestError: Unknown PG
        numeric type: <oid>`. So EVERY query of the table dies, including code
        that predates the column. That is what `dt_log` did on 2026-08-18, and
        why this bucket is ranked above the other one.

        Tested by asking whether the DATABASE side is numeric, not by asking
        which family it belongs to. A numeric declaration over jsonb or bytea
        raises in exactly the same place, and `_type_family` has no opinion about
        either - a family comparison would have called those healthy.

    (b) MERELY WRONG - any other family disagreement between two families this
        module recognises, e.g. `datetime` declared over varchar. Queries work;
        the declaration lies, and everything downstream that trusts the
        declaration (ordering, range filters, the ledger's own planning) is
        reasoning about a type the data does not have. Reported, ranked below (a).

    BOTH AT INFO, ON PURPOSE. The severity is a deploy decision, and the remedy
    for these is never automatic (see `_sync_repairs`), so a gate that went red
    on them would stay red until a human made a judgement call that may take
    days. What was actually missing was not a refusal - it was that nothing
    printed the fact at all, on any boot, ever. INFO is printed daily by both
    boot paths and changes no exit code.
    """
    out = []
    for name, col in sorted(columns.items()):
        actual = actual_types.get(name)
        if actual is None:
            continue                        # absent, or a type the driver did not reflect
        declared_family = _type_family(col.type)
        actual_family = _type_family(actual)
        if declared_family is None:
            continue
        if declared_family == "number" and actual_family != "number":
            out.append({
                "severity": "INFO", "kind": "type-breaking",
                "table": table, "column": name,
                "breaks": (f"EVERY query that SELECTs {table} raises "
                           f"sqlalchemy.exc.InvalidRequestError 'Unknown PG numeric "
                           f"type' - {name} is declared numeric and the database "
                           f"holds {actual}. Not only code that reads {name}."),
                "remedy": _type_remedy(table, name, "number", actual, dynamic_names),
            })
            continue
        if actual_family is not None and actual_family != declared_family:
            out.append({
                "severity": "INFO", "kind": "type-mismatch",
                "table": table, "column": name,
                "breaks": (f"nothing today - queries work. The declaration is wrong: "
                           f"{name} is declared {declared_family} and the database "
                           f"holds {actual}."),
                "remedy": _type_remedy(table, name, declared_family, actual, dynamic_names),
            })
    return out


def _type_remedy(table, column, declared_family, actual, dynamic_names):
    """What to do about a type mismatch, which is never "run this ALTER".

    See `_sync_repairs` for the measurement that forbids the cast. This names the
    declaration site instead, because that is the edit that is safe to make
    without looking at 4,567 rows first.
    """
    if table in dynamic_names:
        site = (f'table_config.json -> "{table}".column_types."{column}" is '
                f'{_CONFIG_WORD.get(declared_family, declared_family)}')
    else:
        site = (f"the mapped column {table}.{column} in server/database/models.py "
                f"declares {declared_family}")
    return (f"decide which side is wrong; do NOT cast the column blind.\n"
            f"        {site}, the database holds {actual}.\n"
            f"        Usually the DECLARATION is what is wrong - correcting it is "
            f"reversible and touches no rows.\n"
            f"        Read the values before you consider the other direction: "
            f'SELECT DISTINCT "{column}" FROM "{table}" LIMIT 50')


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
    dynamic_names = _dynamic_table_names()
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
            if _sync_repairs(table, col.name, actual[table], dynamic_names):
                # Reported, never hidden - the operator gets the table and the
                # column, and a second sighting after a restart is the signal that
                # the ALTER is failing. What changes is the two sentences that were
                # wrong: it does not claim the table is down, and it does not send
                # anyone to write a migration for a column the boot owns.
                findings.append({
                    "severity": "SELF-HEALING", "table": table, "column": col.name,
                    "breaks": (f"nothing that needs you: {table} is a config-declared "
                               f"(dynamic) table, so the boot-time schema sync ADDs "
                               f"this column when a server process starts. This check "
                               f"runs BEFORE those processes do."),
                    "remedy": ("nothing, and do NOT write a migration - "
                               "models.sync_dynamic_tables_schema owns this column.\n"
                               "        if it is STILL reported after a full restart the "
                               "ALTER is failing and the table really is down:\n"
                               "        grep the logs for '[Schema Sync] Failed to add "
                               "column', then run\n"
                               "        " + _add_column_ddl(table, col, dialect)),
                })
                continue
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

        # Columns that ARE there, under a type the declaration does not describe.
        # Only the present ones - a name the loop above already reported missing
        # has no type to disagree with.
        findings += _type_findings(table, columns, actual[table], dynamic_names)

        extra = sorted(set(actual[table]) - set(columns))
        if extra:
            findings.append({
                "severity": "INFO", "kind": "unmapped-column",
                "table": table, "column": ", ".join(extra),
                "breaks": "nothing - the database carries columns the code does not map",
                "remedy": "harmless. Worth a look if one of these was meant to be dropped.",
            })

    # Within a severity, rank by kind before table. All of INFO is quiet, but a
    # numeric declaration over varchar takes its table down and an unmapped
    # column does not, so the one an operator has to act on must not be sorted
    # into the middle of the ones they do not. Findings with no `kind` keep a
    # single rank, so ordering inside every other severity is unchanged.
    findings.sort(key=lambda f: (SEVERITY_ORDER[f["severity"]],
                                 _KIND_ORDER.get(f.get("kind"), 0),
                                 f["table"], f["column"] or ""))
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

    TYPE FINDINGS ARE PRINTED THOUGH, and that is the whole point of adding them.
    They are INFO, so they never open the red block and never move an exit code;
    but "INFO" used to mean "never printed at boot", and a detector nobody sees
    is the state `dt_log` sat in. They get their own section, after everything
    above, at `warning` when one of them is breaking and `info` otherwise.

    SELF-HEALING FINDINGS ARE PRINTED, NEVER COUNTED. They are real - the column is
    genuinely absent at the moment this runs - and hiding them would cost the paper
    trail that makes a SECOND sighting readable. But they are not the operator's, so
    they are excluded from the headline count and from "fails until the column
    exists", and when they are the ONLY drift the red block does not open at all.
    The softening is confined to the one classification `_sync_repairs` can defend;
    anything else, including any drift kind this module cannot yet see, still gets
    the block below.
    """
    # QUIET IS THE WHITELIST, and it has to be this way round. Written as
    # `stuck = severity in ("TABLE-DOWN", "MISSING-TABLE")` a severity nobody has
    # invented yet would fall through to neither bucket and be printed as
    # harmless. Two named quiet kinds and "everything else is loud" cannot fail
    # that way: a future finding is noisy until somebody argues it should not be.
    #
    # It was written for the type mismatch, which was then "the first drift kind
    # this module cannot see" and is now the section below. That did not make the
    # argument stale - it made it the precedent. Type findings are quiet because
    # somebody argued they should be (INFO, ruled 2026-08-19); the NEXT unseen
    # kind still arrives loud.
    _QUIET = ("SELF-HEALING", "INFO")
    healing = [f for f in findings if f["severity"] == "SELF-HEALING"]
    stuck = [f for f in findings if f["severity"] not in _QUIET]
    types = [f for f in findings if f.get("kind") in TYPE_KINDS]
    extra = len(findings) - len(stuck) - len(healing) - len(types)
    if not stuck and not healing:
        detail = f" ({extra} unmapped column group(s), harmless)" if extra else ""
        # "no drift in names" keeps the substring an operator and the launcher's
        # end-to-end test both look for, without the headline claiming a clean
        # schema over a section that says otherwise two lines down.
        head = "no drift" if not types else "no drift in names"
        return [("info", f"[Schema] {head} - the database carries every table and "
                         f"column the code maps{detail}.")] + _type_section(types)

    if not stuck:
        # The false alarm of 2026-08-13, as it should have read. Visible, on the
        # record, and not a red block - because a red block that resolves itself
        # before the operator finishes reading it is what turns the next real one
        # into wallpaper.
        out = [("warning", f"[Schema] {len(healing)} column(s) are missing that the "
                           f"boot-time schema sync adds by itself. Nothing to do."),
               ("warning", f"  target: {target}")]
        out += _finding_lines(healing, "warning")
        out += [
            ("warning", "  이 컬럼들은 서버 프로세스가 기동하면서 자동으로 추가됩니다. "
                        "마이그레이션을 작성하지 마십시오."),
            ("warning", "  재기동 후에도 같은 줄이 다시 뜨면 그때는 실제 장애입니다 - "
                        "위 do: 를 따르십시오."),
        ]
        return out + _type_section(types)

    out = [("error", _RULE),
           ("error", f"SCHEMA DRIFT: the database is missing {len(stuck)} thing(s) "
                     f"this build requires."),
           ("error", f"  target: {target}")]
    out += _finding_lines(stuck, "error")
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
    ]
    if healing:
        # BELOW the sentences above on purpose: "the table(s) above" has to keep
        # meaning the stuck ones. Listed rather than dropped so a second sighting
        # after a restart has something to be a second sighting OF.
        out += [
            ("error", "  ---"),
            ("error", f"  Separately - {len(healing)} column(s) the boot-time sync adds "
                      f"by itself. NOT counted above, and no migration:"),
        ]
        out += _finding_lines(healing, "error")
    out.append(("error", _RULE))
    # OUTSIDE the rule, and last. The red block is about names, and its closing
    # sentences ("until the column exists", "run the migration") are not the
    # remedy for a type - printing these inside it would attach the wrong fix to
    # the wrong finding.
    return out + _type_section(types)


def _type_section(types):
    """The type findings as their own block, or nothing at all.

    A SEPARATE SECTION, NOT A SEVERITY. These are INFO - they change no exit code
    and open no red block - but INFO had until now meant "computed and never
    shown", which is the exact condition that let a `number`-over-varchar column
    sit in `dt_log` unreported for an unknown length of time.

    The two kinds are printed apart because they lead to different actions: the
    breaking ones mean that table is unusable RIGHT NOW, the others mean the
    declaration is lying about data that queries fine. `check` has already sorted
    breaking first, so the split here is a header and a level, not a re-sort.
    """
    if not types:
        return []
    breaking = [f for f in types if f["kind"] == "type-breaking"]
    level = "warning" if breaking else "info"
    head = f"[Schema] {len(types)} column(s) exist with a type the code does not declare"
    if breaking:
        head += (f" - {len(breaking)} of them BREAKING: every query of that table "
                 f"raises until it is fixed")
    out = [(level, head + "."),
           (level, "  Not blocking, and no migration will repair it by itself - "
                   "a type is never altered automatically here (see _sync_repairs).")]
    out += _finding_lines(breaking, "warning")
    out += _finding_lines([f for f in types if f["kind"] != "type-breaking"], "info")
    return out


def finding_label(f):
    """The bracketed tag a finding is printed under, here and in the CLI.

    The severity alone is not enough once one severity carries kinds that lead to
    different actions: three INFO findings in a row, one of which means the table
    is unusable, read as three of the same thing. Findings with no `kind` print
    exactly what they printed before, which is what keeps `[SELF-HEALING]` and
    `[TABLE-DOWN]` greppable in logs and in the tests that assert on them.
    """
    kind = f.get("kind")
    return f"{f['severity']} {kind}" if kind else f["severity"]


def _finding_lines(findings, level):
    """One finding as the banner prints it. Shared so the two shapes cannot drift.

    THE REMEDY IS COPIED, NOT SUMMARISED - that property is asserted by the tests
    and it is why this walks `splitlines()` instead of taking the first line.
    """
    out = []
    for f in findings:
        name = f"{f['table']}.{f['column']}" if f["column"] else f["table"]
        out.append((level, f"  [{finding_label(f)}] {name}"))
        out.append((level, f"      breaks: {f['breaks']}"))
        for i, line in enumerate(f["remedy"].splitlines()):
            out.append((level, f"      do:     {line}" if i == 0 else f"  {line}"))
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
