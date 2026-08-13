"""The drift check has to fire at boot, and it has to stay harmless while it does.

WHAT THIS PROTECTS
    Three outages on 2026-08-05 had one shape: a model gained a column, the
    migration did not run on production, and the first report was a screen
    erroring. `server/scripts/check_schema_drift.py` answered that question from
    the day it was written and was never in the deployment path, so it prevented
    nothing. It is now called from two boot paths - the launcher pre-flight and
    the web server's startup_event.

HOW A STARTUP PATH GETS TESTED WITHOUT RESTARTING ANYTHING
    Three layers, because no single one covers it:

    1. `run_at_startup` is called directly against a purpose-built SQLite database
       whose schema is deliberately narrowed. That is the exact function both boot
       paths call, executing its real lines, with no process involved.
    2. The two call sites themselves cannot run without a boot, so their ORDER is
       asserted against the source - the same technique
       test_duplicate_launcher.py already uses for the port guard, and for the
       same reason: ordering is the whole fix.
    3. `--preflight-only` runs the REAL launcher, in a real process, executing the
       real pre-flight against the real database - and starts nothing. That is a
       startup path genuinely exercised end to end without a restart.
"""
import os
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, text

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SERVER = os.path.join(ROOT, "server")

# Imported from `server/`, the way the boot paths do it - NOT from server/scripts.
# Importing the CLI here would put server/scripts on this suite's sys.path and
# hide exactly the defect test_prod_import_env.py exists to catch.
import schema_drift as drift  # noqa: E402


# The column this test removes. Any mapped table with a plain nullable column
# would do; this is the one that took a table down this morning, so the test
# reproduces the reported failure rather than a scenario resembling it.
DRIFT_TABLE = "frame_confirmation"


@pytest.fixture
def narrowed_db(tmp_path):
    """A database that carries every mapped table EXCEPT one column of one table.

    Built by creating that one table by hand, narrow, BEFORE `create_all` runs:
    `create_all` skips a table that already exists, which is the very property
    that causes the production failure. So the fixture reproduces the mechanism
    rather than simulating its result.
    """
    from database.database import Base
    import database.models  # noqa: F401

    url = f"sqlite:///{tmp_path / 'narrowed.db'}"
    engine = create_engine(url)
    declared = Base.metadata.tables[DRIFT_TABLE]
    keep = [c.name for c in declared.columns][:2]
    assert len(keep) == 2, "fixture needs at least two columns to build a narrow table"
    with engine.connect() as conn:
        conn.execute(text(f'CREATE TABLE "{DRIFT_TABLE}" '
                          f'({keep[0]} INTEGER PRIMARY KEY, {keep[1]} TEXT)'))
        conn.commit()
    Base.metadata.create_all(bind=engine)
    dropped = [c.name for c in declared.columns if c.name not in keep]
    assert dropped, "the fixture did not actually remove anything"
    return engine, dropped


# A config-declared (dynamic) table, and one whose declaration carries an
# UPPERCASE column name. Both come from conftest's fixture config rather than the
# operator's gitignored one, so these tests say the same thing on a box that has
# no table_config.json - which is every worktree.
DYN_TABLE = "inventory_master"
DYN_MIXED_CASE_TABLE = "raw_table_1"
DYN_MIXED_CASE_COLUMN = "EQP_ID"


def _narrow_copy(engine, table_name, drop):
    """Create `table_name` physically, minus `drop`, then let create_all skip it.

    The mechanism, not a simulation of its result: `create_all` does not ALTER a
    table that already exists, which is the entire reason a declared column can be
    absent from a database that boots cleanly.
    """
    from database.database import Base

    declared = Base.metadata.tables[table_name]
    keep = [c.name for c in declared.columns if c.name not in drop]
    assert len(keep) >= 2, f"{table_name} is too narrow to build a partial copy from"
    body = ", ".join(f'"{n}" VARCHAR' for n in keep)
    with engine.connect() as conn:
        conn.execute(text(f'CREATE TABLE "{table_name}" ({body})'))
        conn.commit()
    Base.metadata.create_all(bind=engine)


@pytest.fixture
def drifted_dynamic_db(db_session, tmp_path):
    """The 2026-08-13 false alarm: a dynamic table missing columns its config declares.

    `db_session` is requested for its side effect - it calls `init_dynamic_models`
    with conftest's fixture config, so DYNAMIC_TABLES is known here instead of
    being whatever the operator's on-disk config happens to hold.
    """
    from database import models
    from database.database import Base

    assert DYN_TABLE in models.DYNAMIC_TABLES, (
        f"{DYN_TABLE} is not a dynamic table in this process, so this fixture "
        f"cannot exercise the self-healing path at all")
    declared = Base.metadata.tables[DYN_TABLE]
    drop = [c.name for c in declared.columns][-2:]
    engine = create_engine(f"sqlite:///{tmp_path / 'dyn.db'}")
    _narrow_copy(engine, DYN_TABLE, drop)
    return engine, drop


@pytest.fixture
def case_folded_db(db_session, tmp_path):
    """A dynamic table whose column differs from the declaration ONLY in case.

    This is drift the sync can never repair and never even complains about: it
    compares `column.name.lower()` against lowercased catalog names, so it sees the
    column as present and issues nothing, forever. `check` compares exactly, so it
    reports the column as missing - correctly. The gap between those two
    comparisons is the reason `_sync_repairs` lowercases before it answers.
    """
    from database import models
    from database.database import Base

    assert DYN_MIXED_CASE_TABLE in models.DYNAMIC_TABLES
    declared = Base.metadata.tables[DYN_MIXED_CASE_TABLE]
    names = [c.name for c in declared.columns]
    assert DYN_MIXED_CASE_COLUMN in names, (
        f"{DYN_MIXED_CASE_TABLE} no longer declares {DYN_MIXED_CASE_COLUMN}; this "
        f"fixture needs a declaration whose case differs from what it creates")
    keep = [n for n in names if n != DYN_MIXED_CASE_COLUMN]
    body = ", ".join(f'"{n}" VARCHAR' for n in keep)
    engine = create_engine(f"sqlite:///{tmp_path / 'fold.db'}")
    with engine.connect() as conn:
        # The declared name, lowercased. Same column to a human, a different
        # string to `check` and the same string to the sync.
        conn.execute(text(f'CREATE TABLE "{DYN_MIXED_CASE_TABLE}" '
                          f'({body}, "{DYN_MIXED_CASE_COLUMN.lower()}" VARCHAR)'))
        conn.commit()
    Base.metadata.create_all(bind=engine)
    return engine


# --------------------------------------------------------------- the fixture bites

def test_the_fixture_actually_creates_the_failure_it_claims_to(narrowed_db):
    """Assertion first. A green result below is only worth something if the
    drifted column is genuinely absent from the database - otherwise every test
    in this file passes against a healthy schema and proves nothing."""
    engine, dropped = narrowed_db
    from sqlalchemy import inspect
    present = {c["name"] for c in inspect(engine).get_columns(DRIFT_TABLE)}
    assert not (present & set(dropped)), \
        "the narrow table carries the columns the fixture says it dropped"


# ------------------------------------------------------------------ what it finds

def test_drift_is_reported_as_table_down_not_as_a_missing_attribute(narrowed_db):
    """The severity carries the operator's decision. A missing column on a mapped
    table is not "one feature is off" - the ORM names it in every full-entity
    SELECT and every INSERT, so the table is unusable whole."""
    engine, dropped = narrowed_db
    findings = drift.check(engine)
    hits = [f for f in findings
            if f["table"] == DRIFT_TABLE and f["column"] in dropped]
    assert hits, f"no finding for the removed columns {dropped}"
    assert all(f["severity"] == "TABLE-DOWN" for f in hits)
    assert all("EVERY full-entity SELECT" in f["breaks"] for f in hits)


def test_a_clean_database_produces_no_finding():
    """The control. Without this, a check that reported drift unconditionally
    would pass every test above."""
    from database.database import Base
    import database.models  # noqa: F401
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    assert [f for f in drift.check(engine) if f["severity"] != "INFO"] == []


# ----------------------------------------------------------------- what it prints

def test_the_banner_names_the_migration_and_does_not_summarise_it(narrowed_db):
    """The whole value is actionability. A startup path that condensed the
    remedy to "schema drift detected" would hand over a symptom and keep the
    answer, which is what the operator already had."""
    engine, _ = narrowed_db
    findings = drift.check(engine)
    text_out = "\n".join(t for _lvl, t in drift.banner_lines(findings, "target-db"))

    assert "SCHEMA DRIFT" in text_out
    assert DRIFT_TABLE in text_out
    # Every blocking finding's remedy survives into the banner intact.
    for f in findings:
        if f["severity"] == "INFO":
            continue
        for line in f["remedy"].splitlines():
            assert line.strip() in text_out, f"remedy line dropped: {line.strip()!r}"
    # And it points at the full report for anything the banner had to shorten.
    assert "check_schema_drift.py" in text_out


def test_the_banner_says_it_is_starting_anyway_and_says_why(narrowed_db):
    """An operator who sees a loud red block and then a working server must not
    have to wonder whether the check refused something."""
    engine, _ = narrowed_db
    out = "\n".join(t for _l, t in drift.banner_lines(drift.check(engine), "t"))
    assert "Starting anyway ON PURPOSE" in out
    assert "[HOW TO FIX]" in out, "the launcher's bilingual remedy precedent was dropped"


def test_a_clean_check_is_one_quiet_line_and_never_a_banner():
    """A banner that prints on a healthy boot is wallpaper within a week, and the
    next real one gets scrolled past."""
    lines = drift.banner_lines([], "target-db")
    assert len(lines) == 1
    assert lines[0][0] == "info"
    assert "=====" not in lines[0][1]


def test_harmless_drift_does_not_raise_the_banner():
    """A column the database has and the code no longer maps breaks nothing.
    Escalating it would train the operator to ignore the thing that does."""
    info_only = [{"severity": "INFO", "table": "t", "column": "old_col",
                  "breaks": "nothing", "remedy": "harmless"}]
    lines = drift.banner_lines(info_only, "target-db")
    assert all(lvl == "info" for lvl, _t in lines)
    assert not any("SCHEMA DRIFT" in t for _l, t in lines)


# ============================================================================
# The false alarm of 2026-08-13, and the line between it and a real outage.
#
# The launcher printed the full red block for `dt_map.dt_lot` and `dt_map.dt_slot`
# - "EVERY full-entity SELECT ... fails", "add a migration under
# server/migrations/" - and the same startup then added both columns. The product
# owner restarted and it was gone. The check was right about the STATE and wrong
# about the CONSEQUENCE: `run_watcher.py`, `run_chain_worker.py`,
# `run_graph_sync.py` and the web server each call
# `models.sync_dynamic_tables_schema` on their own boot, and the launcher checks
# BEFORE it spawns them.
#
# Everything below divides into two halves and they are not equally important.
# The false-alarm half is the bug. The stuck half is the REGRESSION - if a change
# here ever makes a real outage read as self-healing, it is worse than the noise
# it replaced, so those tests are written to fail loudly and are injected against.
# ============================================================================

def test_the_fixture_reproduces_the_false_alarm_before_anything_is_asserted(drifted_dynamic_db):
    """Assertion first. Without this the tests below could be green against a
    healthy database and prove nothing about the reported failure."""
    from sqlalchemy import inspect
    engine, dropped = drifted_dynamic_db
    present = {c["name"] for c in inspect(engine).get_columns(DYN_TABLE)}
    assert present, f"{DYN_TABLE} does not exist - the sync would skip it entirely"
    assert not (present & set(dropped)), "the columns the fixture says it dropped are there"


def test_a_declared_dynamic_column_is_not_the_operators_problem(drifted_dynamic_db):
    """The bug, at the level the classification is made."""
    engine, dropped = drifted_dynamic_db
    hits = [f for f in drift.check(engine)
            if f["table"] == DYN_TABLE and f["column"] in dropped]
    assert len(hits) == len(dropped), f"expected a finding per dropped column, got {hits}"
    assert all(f["severity"] == "SELF-HEALING" for f in hits), \
        f"a column the boot adds by itself is still reported as an outage: {hits}"


def test_the_false_alarm_no_longer_opens_the_red_block(drifted_dynamic_db):
    """What the operator sees. The three sentences that were wrong, named one by
    one so a rewrite that reintroduces any of them fails here."""
    engine, _ = drifted_dynamic_db
    lines = drift.banner_lines(drift.check(engine), "target-db")
    out = "\n".join(t for _l, t in lines)

    assert "SCHEMA DRIFT" not in out, "the red headline still fires on a self-healing column"
    assert "=====" not in out, "the red rule still fires"
    assert "this build requires" not in out
    assert "Every screen that touches" not in out, \
        "it still claims the table is down when it is not"
    assert "add one under server/migrations/" not in out, \
        "it still sends the operator to write a migration for a column the boot owns"
    assert not any(lvl == "error" for lvl, _t in lines), \
        "a condition that resolves itself is still logged at error level"


def test_the_self_healing_verdict_is_still_on_the_record(drifted_dynamic_db):
    """Not quiet - just not red. The table, the column and the escalation path all
    survive, because a SECOND sighting after a restart is the real signal and it
    needs a first one to be second to."""
    engine, dropped = drifted_dynamic_db
    out = "\n".join(t for _l, t in drift.banner_lines(drift.check(engine), "target-db"))

    assert DYN_TABLE in out
    for col in dropped:
        assert col in out, f"{col} was dropped from the verdict entirely"
    assert "SELF-HEALING" in out
    assert "after a full restart" in out, \
        "nothing tells the operator what a second sighting means"
    assert "[Schema Sync] Failed to add column" in out, \
        "the log line that distinguishes a failed ALTER from a pending one is missing"
    assert "ALTER TABLE" in out, "the manual remedy was dropped, not just demoted"


def test_the_prediction_is_scored_against_what_the_sync_actually_does(drifted_dynamic_db):
    """The predicate is one function's reading of another function's source, and a
    reading goes stale in silence. So this does not re-read it - it runs the
    repairer and compares the outcome against the prediction.

    This is the test that catches `sync_dynamic_tables_schema` changing under us.
    """
    from sqlalchemy import inspect
    from database import models

    engine, dropped = drifted_dynamic_db
    predicted = {f["column"] for f in drift.check(engine)
                 if f["table"] == DYN_TABLE and f["severity"] == "SELF-HEALING"}
    assert predicted, "nothing was predicted self-healing, so this proves nothing"

    models.sync_dynamic_tables_schema(engine)

    present = {c["name"] for c in inspect(engine).get_columns(DYN_TABLE)}
    assert predicted <= present, (
        f"predicted self-healing but the sync did not add: {sorted(predicted - present)}. "
        f"The banner is now telling operators to wait for a repair that never comes.")
    assert not [f for f in drift.check(engine) if f["table"] == DYN_TABLE], \
        "the drift survived the very sync that was supposed to own it"


# ------------------------------------------------- the regression that matters

def test_a_system_table_column_is_never_called_self_healing(narrowed_db):
    """The 2026-08-05 incident shape. `frame_confirmation` is declared as an ORM
    class, so it is not in DYNAMIC_TABLES and no boot path ALTERs it - the operator
    must run a migration. This is the case that must not be softened."""
    engine, dropped = narrowed_db
    hits = [f for f in drift.check(engine)
            if f["table"] == DRIFT_TABLE and f["column"] in dropped]
    assert hits
    assert all(f["severity"] == "TABLE-DOWN" for f in hits), \
        f"a system-table column was classified as self-healing: {hits}"

    out = "\n".join(t for _l, t in drift.banner_lines(drift.check(engine), "t"))
    assert "SCHEMA DRIFT" in out and "=====" in out
    assert "Every screen that touches" in out


def test_a_case_only_mismatch_the_sync_skips_forever_stays_table_down(case_folded_db):
    """Detected drift the sync will never repair, and never even complain about.

    The sync compares `column.name.lower()` against lowercased catalog names, so a
    declared `EQP_ID` against a stored `eqp_id` looks present to it and it issues
    nothing - no ALTER, no failure line, no second chance. `check` compares
    exactly and is right that the mapped name is absent. Only the lowercasing
    inside `_sync_repairs` keeps this out of the self-healing bucket, and the proof
    is below: the sync runs and the column is still not there.
    """
    from sqlalchemy import inspect
    from database import models

    hits = [f for f in drift.check(case_folded_db)
            if f["table"] == DYN_MIXED_CASE_TABLE
            and f["column"] == DYN_MIXED_CASE_COLUMN]
    assert hits, f"{DYN_MIXED_CASE_COLUMN} was not reported missing at all"
    assert all(f["severity"] == "TABLE-DOWN" for f in hits), (
        f"a dynamic-table column the sync silently skips was called self-healing: "
        f"{hits}. The operator would wait through restart after restart.")

    models.sync_dynamic_tables_schema(case_folded_db)
    present = {c["name"] for c in inspect(case_folded_db).get_columns(DYN_MIXED_CASE_TABLE)}
    assert DYN_MIXED_CASE_COLUMN not in present, (
        "the sync repaired a case-only mismatch after all - if this is now true, "
        "`_sync_repairs` may drop its lowercasing and this test is stale")


def test_a_missing_dynamic_table_is_not_self_healing(db_session, tmp_path):
    """`sync_dynamic_tables_schema` opens with `if not inspector.has_table(...):
    continue`. It ALTERs; it does not CREATE. A dynamic table that is absent whole
    therefore keeps its own severity and its own remedy.

    WHAT KEEPS THIS TRUE IS NOT THE CLASSIFIER, and the injection run said so: this
    test stays GREEN when `_sync_repairs` is forced to return True for everything.
    `check` reports an absent table and `continue`s before the column loop, so the
    classifier is never consulted about one. The property is worth pinning anyway -
    a later refactor that routes MISSING-TABLE through the classifier would land
    here - but it is not evidence about `_sync_repairs`. That evidence is
    `test_sync_repairs_answers_the_three_gates_in_the_sync`, which is the only
    thing covering gate 2.
    """
    from database.database import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'notable.db'}")
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        conn.execute(text(f'DROP TABLE "{DYN_TABLE}"'))
        conn.commit()

    hits = [f for f in drift.check(engine) if f["table"] == DYN_TABLE]
    assert hits, "a dropped dynamic table produced no finding"
    assert all(f["severity"] == "MISSING-TABLE" for f in hits), \
        f"an absent table was classified as a column the sync adds: {hits}"


def test_a_drift_kind_nobody_has_classified_yet_is_loud(drifted_dynamic_db):
    """Forward cover, and the reason `banner_lines` whitelists what is quiet
    instead of listing what is loud.

    A type mismatch is the obvious next drift kind (see the gap pinned below), and
    the failure to avoid is that it arrives, lands in neither named bucket, and is
    printed as harmless. Only SELF-HEALING and INFO may be quiet; a severity nobody
    has argued about yet opens the red block.
    """
    engine, _ = drifted_dynamic_db
    findings = drift.check(engine) + [{
        "severity": "TYPE-MISMATCH", "table": "dt_map", "column": "dt_x",
        "breaks": "the column exists with the wrong type",
        "remedy": "ALTER TABLE dt_map ALTER COLUMN dt_x TYPE double precision",
    }]
    lines = drift.banner_lines(findings, "t")
    out = "\n".join(t for _l, t in lines)

    assert "SCHEMA DRIFT" in out, "an unclassified drift kind was printed as harmless"
    assert "missing 1 thing(s)" in out, \
        "an unclassified drift kind was left out of the count"
    assert any(lvl == "error" for lvl, _t in lines)
    assert "ALTER COLUMN dt_x TYPE" in out, "its remedy was dropped"


def test_a_mixed_verdict_counts_only_the_stuck_but_prints_both(narrowed_db, drifted_dynamic_db):
    """One database's worth of each. The headline count is what an operator acts
    on, so it must be the stuck ones only - and the self-healing ones must still
    appear, below the sentence that says the tables above are down."""
    stuck_engine, stuck_cols = narrowed_db
    heal_engine, heal_cols = drifted_dynamic_db
    findings = drift.check(stuck_engine) + drift.check(heal_engine)

    n_stuck = len([f for f in findings if f["severity"] == "TABLE-DOWN"])
    assert n_stuck and len([f for f in findings if f["severity"] == "SELF-HEALING"])

    out = "\n".join(t for _l, t in drift.banner_lines(findings, "t"))
    assert f"missing {n_stuck} thing(s)" in out, \
        "self-healing columns are being counted as things the build requires"
    assert "NOT counted above" in out
    for col in heal_cols:
        assert col in out, "the self-healing findings vanished from a mixed verdict"
    # Ordering: the claim "the table(s) above fail" must not have self-healing
    # entries above it.
    assert out.index("Every screen that touches") < out.index("[SELF-HEALING]"), \
        "a self-healing column sits under a sentence that says the table is down"


# ------------------------------------------------------------------ the predicate

def test_sync_repairs_answers_the_three_gates_in_the_sync():
    """The predicate on its own, with no database, one case per gate of
    `models.sync_dynamic_tables_schema`. These are what the injections aim at."""
    dyn = {"dt_map"}
    # (1) in DYNAMIC_TABLES, (2) table present, (3) name absent case-insensitively
    assert drift._sync_repairs("dt_map", "dt_lot", {"row_id"}, dyn) is True
    # (1) fails - a system table has no boot-time ALTER path at all
    assert drift._sync_repairs("cell_sources", "confirmation_uid", {"row_id"}, dyn) is False
    # (2) fails - the sync `continue`s past a table that does not exist
    assert drift._sync_repairs("dt_map", "dt_lot", None, dyn) is False
    # (3) fails - the sync sees `dt_lot` as present and issues nothing, forever
    assert drift._sync_repairs("dt_map", "DT_LOT", {"dt_lot"}, dyn) is False


def test_the_predicate_reads_the_dict_the_repairer_iterates(db_session):
    """Not a copy of table_config. `sync_dynamic_tables_schema` loops over
    `models.DYNAMIC_TABLES`, so that is what decides - the config on disk and this
    dict can disagree inside one process, and the repairer is the one that matters."""
    from database import models
    assert drift._dynamic_table_names() == set(models.DYNAMIC_TABLES)
    assert DYN_TABLE in drift._dynamic_table_names()
    assert DRIFT_TABLE not in drift._dynamic_table_names(), \
        f"{DRIFT_TABLE} is a system table and must not be in the repairer's scope"


# ------------------------------------------------------------------- the gap

def test_the_check_still_cannot_see_a_type_mismatch_at_all():
    """A LIMITATION, pinned so it is not mistaken for coverage.

    The brief for this round assumed a type mismatch produces the full-severity
    banner. It does not, and it did not before this change either: `check` compares
    NAMES only, so a column that exists with the wrong type reads as healthy and
    nothing is printed. That is stated in the module docstring and is asserted here
    because the assumption is easy to make and expensive.

    Nothing about the self-healing classification touched this. If type comparison
    is ever added, `test_a_drift_kind_nobody_has_classified_yet_is_loud` above is
    the one that says the new severity arrives loud.
    """
    from database.database import Base
    engine = create_engine(f"sqlite://")
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        conn.execute(text('DROP TABLE "interaction_effort_logs"'))
        # Every declared name, all of them the wrong type.
        cols = ", ".join(
            f'"{c.name}" BLOB'
            for c in Base.metadata.tables["interaction_effort_logs"].columns)
        conn.execute(text(f'CREATE TABLE "interaction_effort_logs" ({cols})'))
        conn.commit()

    # The fixture bites: without this the test passes against a healthy table and
    # asserts nothing about types at all.
    from sqlalchemy import inspect
    types = {str(c["type"]).upper() for c in inspect(engine).get_columns(
        "interaction_effort_logs")}
    assert types == {"BLOB"}, f"the fixture did not change any type: {types}"

    findings = [f for f in drift.check(engine)
                if f["table"] == "interaction_effort_logs"]
    assert findings == [], (
        "the check has learned to see type drift. That is an improvement - but "
        "confirm the new severity is not SELF-HEALING and not INFO, because the "
        "sync only ever issues ADD COLUMN and can never repair a type.")


# ------------------------------------------------------- it names the migration

@pytest.mark.parametrize("table,column,expected", [
    # The two that took tables down on 2026-08-05. Both are added by a migration
    # that is sitting in the tree, and both reported "no migration is recorded"
    # while the hand-maintained map was the only source of truth.
    ("frame_confirmation", "geometry_assumed", "add_frame_confirmation.py"),
    ("frame_confirmation_source", "geometry_basis", "add_frame_confirmation.py"),
    ("cell_sources", "confirmation_uid", "add_frame_confirmation.py"),
    ("interaction_effort_logs", "nav_preserved_count", "setup_db_performance.py"),
])
def test_the_remedy_is_found_in_the_tree_not_remembered_in_a_dict(table, column, expected):
    """The check's whole value is naming the fix. Deriving it means a migration
    added next month is named without anyone updating this file."""
    owner = drift._owner_from_sources(table, column)
    assert owner and expected in owner, \
        f"{table}.{column}: expected {expected}, got {owner!r}"


def test_a_column_no_migration_adds_is_reported_as_unrecorded_not_guessed():
    """The control. Without it, a matcher that returned the first file it read
    would pass every case above."""
    assert drift._owner_from_sources("frame_confirmation", "no_such_column_xyz") is None


def test_boot_applied_columns_keep_their_non_file_remedy():
    """Two outbox columns are applied by the web server's own startup, not by a
    file anybody runs. Pointing an operator at a script for those would send them
    to run something that does not exist."""
    for col in ("processed_chain", "broadcast_at"):
        assert "web-server boot" in drift.MIGRATION_OWNER[("database_outbox", col)]


# ------------------------------------------------- it cannot become the outage

def test_run_at_startup_never_raises_even_when_the_database_is_gone():
    """This runs inside a boot sequence whose job is to bring the product up. A
    check meant to prevent an outage must not be able to cause one."""
    engine = create_engine("postgresql://nobody:nobody@127.0.0.1:1/nonexistent")
    emitted = []
    result = drift.run_at_startup(engine, lambda lvl, t: emitted.append((lvl, t)),
                                 target="unreachable")
    assert result is None
    assert emitted, "it failed silently - the operator learns nothing"
    assert any("could not run" in t for _l, t in emitted)


def test_run_at_startup_emits_through_the_callers_logger(narrowed_db):
    """Both boot paths pass their own logger, so the verdict lands wherever that
    process already writes and the two cannot drift into different formats."""
    engine, _ = narrowed_db
    emitted = []
    drift.run_at_startup(engine, lambda lvl, t: emitted.append((lvl, t)), target="t")
    assert any(lvl == "error" and "SCHEMA DRIFT" in t for lvl, t in emitted)


# --------------------------------------------------------- the landmine it avoids

def test_the_check_does_not_leave_TESTING_set_in_the_calling_process():
    """`_declared` sets TESTING to keep import side effects off the wire when it
    runs as a bare script. Leaving it set is not a tidiness issue: the launcher
    hands `os.environ.copy()` to all five children, TESTING makes the web server
    refuse its own boot-time DDL, and it makes the workers skip their work. A
    leak here would have turned a diagnostic into a silent full outage.

    Run in a subprocess because the branch only exists when `database.models` has
    NOT been imported yet, which is never true inside this suite's process.
    """
    probe = (
        "import os, sys;"
        f"sys.path.insert(0, r'{SERVER}');"
        "os.environ.pop('TESTING', None);"
        "import schema_drift as d;"
        "assert 'database.models' not in sys.modules;"
        "d._declared();"
        "print('TESTING=' + repr(os.environ.get('TESTING')))"
    )
    res = subprocess.run([sys.executable, "-c", probe], cwd=ROOT,
                         capture_output=True, timeout=300,
                         env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    out = (res.stdout + res.stderr).decode("utf-8", "replace")
    assert "TESTING=None" in out, \
        f"the check leaked TESTING into the process environment:\n{out}"


def test_dynamic_tables_are_in_scope_of_the_check():
    """The config-driven tables are most of the schema and every operator screen
    sits on one. `import database.models` registers the SYSTEM tables only - the
    rest arrive through `init_dynamic_models`, which every entry point calls for
    itself. A check that stopped at the import reported on the minority and called
    the rest healthy.

    Subprocess, and that is the whole point: inside this suite conftest has
    already mapped dynamic models, so an in-process assertion would hold whether
    or not the check does its own registration - it would pass against the bug.
    Only a process where nobody has initialised them can tell the two apart.
    """
    probe = (
        "import os, sys;"
        f"sys.path.insert(0, r'{SERVER}');"
        "import schema_drift as d;"
        "assert 'database.models' not in sys.modules;"
        "decl = d._declared();"
        "from database import models;"
        "dyn = set(models.DYNAMIC_TABLES);"
        "print('DYN=%d MISSING=%r' % (len(dyn), sorted(dyn - set(decl))))"
    )
    res = subprocess.run([sys.executable, "-c", probe], cwd=ROOT,
                         capture_output=True, timeout=300,
                         env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    out = (res.stdout + res.stderr).decode("utf-8", "replace")
    assert "MISSING=[]" in out, f"dynamic tables are invisible to the check:\n{out}"
    count = int(out.split("DYN=")[1].split(" ")[0])
    assert count > 0, (
        "no dynamic tables were mapped at all, so this test cannot tell a check "
        f"that sees them from one that does not:\n{out}")


def test_the_check_does_not_redefine_models_a_process_already_mapped():
    """`init_dynamic_models` mutates shared global state and hot-swaps columns
    onto live mappings. Loading the on-disk config over a process that chose a
    different one would redefine tables out from under whatever is running."""
    from database import models
    before = dict(models.DYNAMIC_TABLES)
    before_meta = set(models.Base.metadata.tables)
    drift._declared()
    assert dict(models.DYNAMIC_TABLES) == before, "the check remapped dynamic models"
    assert set(models.Base.metadata.tables) == before_meta, "the check altered metadata"


# ------------------------------------------------------------------ the wiring

def _source(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return f.read()


def test_neither_boot_path_reaches_into_server_scripts():
    """The split is the wiring, not a tidiness preference.

    The first version of this work imported the CLI from `server/scripts` and
    appended that directory to sys.path inside `startup_event`.
    test_prod_import_env.py caught it. That test covers the property globally;
    this one names the two call sites, so a future reader who reintroduces the
    append gets told which change did it and why the module exists.
    """
    for path in (os.path.join("server", "main.py"), "run_decoupled_app.py"):
        src = _source(path)
        assert "import schema_drift" in src, f"{path} does not use the runtime module"
        # The IMPORT, not the name: both call sites legitimately mention the CLI
        # by path in the message they print when the check cannot run.
        assert "import check_schema_drift" not in src, \
            f"{path} imports the CLI; runtime code may not reach into server/scripts"
        assert "server\", \"scripts\"" not in src.replace("'", '"'), \
            f"{path} puts server/scripts on sys.path"


def test_the_cli_is_a_wrapper_and_not_a_second_copy_of_the_logic():
    """Two copies drift, and the one in the boot path is the one nobody reads."""
    cli = _source(os.path.join("server", "scripts", "check_schema_drift.py"))
    assert "from schema_drift import" in cli
    for owned in ("def check(", "def banner_lines(", "def run_at_startup("):
        assert owned not in cli, f"the CLI redefines {owned.strip('def (')}"


def test_the_web_server_checks_after_its_own_migrations_and_before_it_serves():
    """Ordering, asserted against source because the alternative is a restart.

    Checked BEFORE startup_event's inline outbox migrations, a database that is
    about to be corrected reads as broken - two of the columns in MIGRATION_OWNER
    are applied right there. Checked after the DECOUPLED return it would never
    run in the only mode production uses.
    """
    src = _source(os.path.join("server", "main.py"))
    call = src.index("schema_drift.run_at_startup")
    assert src.index("broadcast_at migration/backfill failed") < call, \
        "the drift check runs before the boot applies its own migrations"
    assert call < src.index('os.getenv("DECOUPLED") == "True"'), \
        "the drift check is behind the DECOUPLED return, so production never runs it"


def test_the_launcher_checks_before_it_spawns_anything():
    """A signal that a migration must run is worth most before the restart.

    Searched from `def main(` onward, deliberately. `def report_schema_drift():`
    contains the call string as a substring, so a plain `src.index` is satisfied
    by the DEFINITION and stays green after the call site is deleted - measured,
    not hypothetical: the first version of this test did exactly that.
    """
    src = _source("run_decoupled_app.py")
    body = src[src.index("def main("):]
    assert "report_schema_drift()" in body, \
        "the launcher defines the schema pre-flight but never calls it"
    assert body.index("report_schema_drift()") < body.index("supervisor.start_all"), \
        "the launcher spawns children before it looks at the schema"


def test_the_launcher_reports_drift_but_never_refuses_over_it():
    """Deliberate split. A held port cannot work at all; drift means the product
    runs minus the tables that drifted. Refusing would hand an unattended restart
    the power to keep everything down over one column."""
    src = _source("run_decoupled_app.py")
    body = src[src.index("def report_schema_drift"):src.index("def refuse_if_arguments")]
    assert "sys.exit" not in body, "the drift reporter can stop the launcher"
    assert "raise" not in body, "the drift reporter can escape into the boot"


def test_the_real_launcher_runs_the_real_check_and_still_starts_nothing(tmp_path):
    """The end-to-end layer: a genuine launcher process, executing the genuine
    pre-flight against the genuine database, with nothing restarted.

    `--preflight-only` is what makes that safe - no child is spawned whatever the
    guards decide. Free ports, so the port guard passes and the schema pre-flight
    is actually reached; exit 0 either way, because drift must never be able to
    turn a restart into a refusal.
    """
    from test_duplicate_launcher import free_port

    env = dict(os.environ)
    env["ASSY_DATA_ROOT"] = str(tmp_path)
    env["ASSY_API_PORT"] = str(free_port())
    env["ASSY_API_HOST"] = "127.0.0.1"
    env["GRAPH_SYNC_PORT"] = str(free_port())
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("TESTING", None)

    res = subprocess.run(
        [sys.executable, os.path.join(ROOT, "run_decoupled_app.py"),
         "--server-only", "--preflight-only"],
        cwd=ROOT, env=env, capture_output=True, timeout=300)
    out = (res.stdout + res.stderr).decode("utf-8", "replace")

    assert res.returncode == 0, f"drift turned a pre-flight into a refusal:\n{out}"
    # It ran, and it said something either way - a silent pre-flight is the
    # state we are leaving behind.
    assert ("SCHEMA DRIFT" in out or "no drift" in out or
            "drift check unavailable" in out), \
        f"the launcher pre-flight said nothing about the schema:\n{out}"
    # And whatever it said is on the record, not only on a scrolled console.
    log = tmp_path / "launcher.log"
    assert log.exists()
    body = log.read_text(encoding="utf-8", errors="replace")
    assert ("SCHEMA DRIFT" in body or "no drift" in body or
            "drift check unavailable" in body)
