"""THE CROSS-TABLE LOOKUP MAPPER SAMPLE, RUN.

`server/mappers/cross_table_lookup_mapper.py.sample` is a reference implementation
somebody will copy. A sample that is only read is a sample that drifts from the worker
it claims to describe, so this file loads that exact `.sample` text and drives it
through `chain_ingestion_worker.execute_custom_mapper` - the real entry point, with the
real payloads taken out of the real outbox rows that `database.stage_event` wrote.

WHAT IS ASSERTED, AND WHY EACH ONE HAS TO BE HERE
  * the sample is importable and the worker's signature probe passes it the rule
  * the reference read is ONE statement per chunk of distinct keys, not one per row
  * the trigger table is never re-read
  * the mapper commits and rolls back nothing
  * absence and unreadability are distinguished, and the derived row says which
  * a FAILED reference read leaves the caller's session alive - and the SAVEPOINT is
    what does it, proved by removing the savepoint and watching the session die

[Isolation] Table names carry the `xlk_test_` prefix. A collision with a table in the
user's gitignored `table_config.json` lets import-time `init_dynamic_models` pin a real
schema into the shared in-memory sqlite, after which `create_all(checkfirst)` skips and
the suite fails with `no such column` (this happened once already, with `bonding_log`).
"""
import importlib.machinery
import importlib.util
import os
import sys

import pytest
from sqlalchemy import Column, Float, String, event, text
from sqlalchemy.orm import declarative_base

from database import crud, models, schemas

SAMPLE_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "mappers", "cross_table_lookup_mapper.py.sample"))

# The name the chain rule declares. `execute_custom_mapper` calls
# `importlib.import_module` on it, which returns a pre-registered `sys.modules` entry
# without touching the filesystem - so the tracked `.sample` can be exercised without
# creating a live mapper beside it.
MODULE_NAME = "mappers.xlk_sample_under_test"

TABLES = {
    "xlk_test_trigger": {
        "business_key": "log_id",
        "column_types": {"log_id": "string", "part_no": "string"},
    },
    "xlk_test_ref": {
        "business_key": "part_no",
        "column_types": {
            "part_no": "string",
            "unit_weight": "number",
            # Declared `string` on purpose: an operator declaring a numeric quantity as
            # text is normal, and it is the only way a reference value can be present,
            # non-blank and still unusable - which is the case that separates
            # `mapping_unavailable` from `not_declared`.
            "pack_size": "string",
        },
    },
    "xlk_test_target": {
        "business_key": "part_no",
        "column_types": {
            "part_no": "string",
            "pack_weight": "number",
            "unit_weight_used": "number",
            "pack_size_used": "string",
            "lookup_status": "string",
        },
    },
}

# A model that exists with NO PHYSICAL TABLE behind it. Not a contrivance: this is a
# recorded failure mode of this system - `sync_dynamic_tables_schema` only ALTERs
# tables that already exist, so a declaration whose CREATE never ran leaves exactly
# this shape, and every read through it is a failed statement.
#
# It hangs off its OWN declarative base so that `Base.metadata.create_all` - which
# conftest's `db_session` fixture runs on every test, by which time this module's
# tables are already registered - can never accidentally bring it into being.
_Detached = declarative_base()


class _PhantomRef(_Detached):
    __tablename__ = "xlk_test_phantom"

    row_id = Column(String, primary_key=True)
    part_no = Column(String)
    unit_weight = Column(Float)
    pack_size = Column(String)

RULE = {
    "name": "xlk_test_rule",
    "trigger_table": "xlk_test_trigger",
    "target_table": "xlk_test_target",
    "lookup_table": "xlk_test_ref",
    "lookup_key": [{"left": "part_no", "right": "part_no"}],
    "mapper_module": MODULE_NAME,
    "mapper_function": "build_pack_weight_batch",
    "is_batch": True,
    "enabled": True,
}


def _load_sample():
    # An explicit loader is required: `.sample` is not a recognised source suffix, so
    # `spec_from_file_location` alone returns None for it.
    loader = importlib.machinery.SourceFileLoader(MODULE_NAME, SAMPLE_PATH)
    spec = importlib.util.spec_from_file_location(MODULE_NAME, SAMPLE_PATH,
                                                  loader=loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


def _seed(db, table, rows):
    items = [schemas.GeneralUpdateItem(updates=dict(r), source_name="pipeline_parser",
                                       updated_by="test") for r in rows]
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(
        updates=items, transaction_id=f"seed_{table}", silent=True))


@pytest.fixture()
def env(db_session):
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    from database.database import Base

    Base.metadata.create_all(bind=db_session.get_bind())
    # Declared to the chain machinery, absent from the database.
    models.DYNAMIC_TABLES["xlk_test_phantom"] = _PhantomRef

    _seed(db_session, "xlk_test_ref", [
        {"part_no": "P-COMPLETE", "unit_weight": "2.5", "pack_size": "4"},
        # present, both value cells blank -> the reference exists but says nothing
        {"part_no": "P-BLANK"},
        # present and NOT blank, but not a number this rule can multiply
        {"part_no": "P-UNUSABLE", "unit_weight": "1.5", "pack_size": "n/a"},
    ])
    db_session.commit()

    module = _load_sample()
    yield db_session, module
    sys.modules.pop(MODULE_NAME, None)
    models.DYNAMIC_TABLES.pop("xlk_test_phantom", None)
    for name in TABLES:
        crud.TABLE_CONFIG.pop(name, None)


def _trigger_payloads(db, rows):
    """Seed the trigger table and hand back what the OUTBOX actually recorded.

    Hand-written payload dicts would test this file's idea of the contract. These come
    from `database.stage_event`, so a change to the payload shape breaks this test
    rather than sailing past it.
    """
    from utils.payload_helper import get_payload_dict
    from database.models import DatabaseOutbox

    _seed(db, "xlk_test_trigger", rows)
    db.commit()
    events = (db.query(DatabaseOutbox)
              .filter(DatabaseOutbox.table_name == "xlk_test_trigger")
              .order_by(DatabaseOutbox.id.asc()).all())
    payloads = [get_payload_dict(e) for e in events]
    assert payloads, "no outbox rows were written for the trigger table"
    return payloads


def _run(db, payloads, rule=None):
    """Through the worker's own dispatcher, not by calling the function directly."""
    import chain_ingestion_worker as worker

    return worker.execute_custom_mapper(
        MODULE_NAME, RULE["mapper_function"], db, payloads, rule=rule or RULE)


def _by_key(result):
    return {item["business_key_val"]: item["updates"] for item in result["updates"]}


# ---------------------------------------------------------------------------
# The contract
# ---------------------------------------------------------------------------

def test_the_worker_passes_the_rule_to_this_mapper(env):
    """`execute_custom_mapper` only forwards `rule` when the function declares it.

    A sample whose signature failed this probe would be called `f(db, payload)`, every
    declaration would fall back to its default, and the failure would look like a
    config that is being ignored."""
    import chain_ingestion_worker as worker

    _db, module = env
    assert worker._mapper_accepts_rule(module.build_pack_weight_batch) is True


def test_a_reference_value_is_computed_and_frozen_next_to_what_it_produced(env):
    db, _module = env
    payloads = _trigger_payloads(db, [{"log_id": "L1", "part_no": "P-COMPLETE"}])

    cells = _by_key(_run(db, payloads))["P-COMPLETE"]

    assert cells["pack_weight"] == pytest.approx(10.0)
    # The frozen inputs travel WITH the number they produced. Without them a later
    # correction on xlk_test_ref leaves a stored 10.0 that nobody can audit.
    assert cells["unit_weight_used"] == pytest.approx(2.5)
    assert str(cells["pack_size_used"]) == "4"
    assert "lookup_status" not in cells


def test_absence_and_unreadability_are_different_words(env):
    """Both are honest degradations and they are DIFFERENT REPAIRS.

    Folding them into one sends the operator to create a reference row that already
    exists. The words come from `config_resolve_report.REASONS`, the closed set the
    rest of the system already speaks."""
    import config_resolve_report as vocab

    db, _module = env
    payloads = _trigger_payloads(db, [
        {"log_id": "L1", "part_no": "P-COMPLETE"},
        {"log_id": "L2", "part_no": "P-MISSING"},    # no reference row at all
        {"log_id": "L3", "part_no": "P-BLANK"},      # reference row, blank values
        {"log_id": "L4", "part_no": "P-UNUSABLE"},   # reference row, unusable value
    ])

    cells = _by_key(_run(db, payloads))

    assert cells["P-MISSING"]["lookup_status"] == vocab.REASON_NOT_DECLARED
    assert cells["P-BLANK"]["lookup_status"] == vocab.REASON_NOT_DECLARED
    assert cells["P-UNUSABLE"]["lookup_status"] == vocab.REASON_MAPPING_UNAVAILABLE

    # Absence is a VALUE, not a dropped row: every trigger row produced a derived row,
    # and the ones that could not be computed carry no invented number.
    assert set(cells) == {"P-COMPLETE", "P-MISSING", "P-BLANK", "P-UNUSABLE"}
    for key in ("P-MISSING", "P-BLANK", "P-UNUSABLE"):
        assert "pack_weight" not in cells[key]
        assert "unit_weight_used" not in cells[key]


def test_a_status_column_the_target_cannot_store_is_refused_not_dropped(env):
    """`apply_batch_updates` DROPS an undeclared column and the write still succeeds.

    For the status column that is the worst possible outcome: the derived row lands
    carrying everything the mapper knew and nothing about what it did not, and it looks
    complete. So the refusal happens before anything is built."""
    db, _module = env
    payloads = _trigger_payloads(db, [{"log_id": "L1", "part_no": "P-MISSING"}])

    rule = dict(RULE, status_column="not_a_declared_column")
    assert _run(db, payloads, rule) == {"updates": []}


def test_a_frozen_column_list_that_does_not_pair_up_is_refused(env):
    """`zip` truncates in silence, so a rule that freezes some of its inputs and not
    others would produce a row that looks fully audited and is not."""
    db, _module = env
    payloads = _trigger_payloads(db, [{"log_id": "L1", "part_no": "P-COMPLETE"}])

    rule = dict(RULE, frozen_columns=["unit_weight_used"])
    assert _run(db, payloads, rule) == {"updates": []}


def test_a_single_payload_is_accepted_and_warned_about(env, caplog):
    """`is_batch: false` hands over one dict. Both shapes are legal per the worker, but
    that setting makes the per-row read structural, so it is named in the log."""
    db, _module = env
    payloads = _trigger_payloads(db, [{"log_id": "L1", "part_no": "P-COMPLETE"}])

    with caplog.at_level("WARNING"):
        result = _run(db, payloads[0])

    assert _by_key(result)["P-COMPLETE"]["pack_weight"] == pytest.approx(10.0)
    assert any("is_batch" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# Shape: what the mapper is and is not allowed to do to the worker's session
# ---------------------------------------------------------------------------

class _Traffic:
    def __init__(self):
        self.statements, self.commits, self.rollbacks = [], 0, 0

    def selects_naming(self, table):
        return [s for s in self.statements
                if s.lstrip().upper().startswith("SELECT") and table in s]


@pytest.fixture()
def traffic(env):
    db, _module = env
    bind = db.get_bind()
    seen = _Traffic()

    def _before(conn, cursor, statement, parameters, context, executemany):
        seen.statements.append(statement)

    def _commit(conn):
        seen.commits += 1

    def _rollback(conn):
        seen.rollbacks += 1

    hooks = (("before_cursor_execute", _before), ("commit", _commit),
             ("rollback", _rollback))
    for name, fn in hooks:
        event.listen(bind, name, fn)
    try:
        yield seen
    finally:
        for name, fn in hooks:
            event.remove(bind, name, fn)


def test_the_lookup_is_one_statement_per_chunk_and_the_trigger_row_is_not_reread(env, traffic):
    """Both halves of the query budget, asserted on the same run.

    More trigger rows than distinct keys, so a per-row lookup and a per-key lookup are
    both visibly wrong: the batched form issues one statement for the whole set."""
    db, _module = env
    payloads = _trigger_payloads(db, [
        {"log_id": "L1", "part_no": "P-COMPLETE"},
        {"log_id": "L2", "part_no": "P-COMPLETE"},
        {"log_id": "L3", "part_no": "P-BLANK"},
        {"log_id": "L4", "part_no": "P-BLANK"},
        {"log_id": "L5", "part_no": "P-UNUSABLE"},
        {"log_id": "L6", "part_no": "P-UNUSABLE"},
    ])

    del traffic.statements[:]
    traffic.commits = traffic.rollbacks = 0
    result = _run(db, payloads)

    assert len(result["updates"]) == len(payloads)
    assert len(traffic.selects_naming("xlk_test_ref")) == 1
    # RULE E. The payload already carries the committed row; re-reading it costs a
    # statement and risks picking up a newer version of the same row.
    assert traffic.selects_naming("xlk_test_trigger") == []


def test_the_mapper_neither_commits_nor_rolls_back(env, traffic):
    """RULE A. The session belongs to the worker.

    A commit here escapes the failure path's rollback, so a group that later fails is
    retried with part of its work already durable; and it expires every ORM object the
    worker is holding, including the outbox rows it is about to stamp."""
    db, _module = env
    payloads = _trigger_payloads(db, [{"log_id": "L1", "part_no": "P-COMPLETE"}])

    del traffic.statements[:]
    traffic.commits = traffic.rollbacks = 0
    _run(db, payloads)

    assert traffic.commits == 0
    assert traffic.rollbacks == 0

    # Guard on the guard, inline, because a zero is only evidence if the instrument
    # can reach one. The connection-level events are the right instrument here and the
    # session-level ones are not: `SessionEvents.after_commit` also fires when
    # `begin_nested()` releases its SAVEPOINT, so a suite built on it would read this
    # mapper's containment as a commit and score the defect green.
    db.execute(text("SELECT 1")).scalar()
    db.commit()
    assert traffic.commits == 1
    db.execute(text("SELECT 1")).scalar()
    db.rollback()
    assert traffic.rollbacks == 1


# ---------------------------------------------------------------------------
# The savepoint, and the proof that it is what is doing the work
# ---------------------------------------------------------------------------

class _AbortedTransaction(Exception):
    """Stand-in for psycopg2's InFailedSqlTransaction."""


@pytest.fixture()
def pg_abort_semantics(env):
    """Impose PostgreSQL's transaction-abort rule on the SQLite test engine.

    Borrowed verbatim in shape from `test_enrichment_candidates.pg_abort_semantics`,
    for the reason recorded there: the suite is pinned to `sqlite:///:memory:` on
    purpose, pysqlite has no abort rule, and a Postgres-only test would SKIP in the
    default suite - a skipped test certifies nothing. Only the abort POLICY is
    injected. The failing statement, the SAVEPOINT and the ROLLBACK TO SAVEPOINT are
    all real."""
    db, _module = env
    bind = db.get_bind()
    state = {"aborted": False}

    def _on_error(ctx):
        state["aborted"] = True

    def _on_rollback(conn):
        state["aborted"] = False

    def _before(conn, cursor, statement, parameters, context, executemany):
        head = statement.lstrip().upper()
        if head.startswith("ROLLBACK"):          # incl. ROLLBACK TO SAVEPOINT
            state["aborted"] = False
            return
        if head.startswith(("SAVEPOINT", "RELEASE", "COMMIT", "BEGIN")):
            return
        if state["aborted"]:
            raise _AbortedTransaction(
                "current transaction is aborted, commands ignored until end of "
                "transaction block")

    hooks = (("handle_error", _on_error), ("rollback", _on_rollback),
             ("before_cursor_execute", _before))
    for name, fn in hooks:
        event.listen(bind, name, fn)
    try:
        yield state
    finally:
        for name, fn in hooks:
            event.remove(bind, name, fn)
        db.rollback()


def test_the_abort_injection_actually_bites(env, pg_abort_semantics):
    """Guard on the guard. If the injector did nothing, the two tests below would pass
    on a defect - which is how a suite comes to certify a refusal production cannot
    reach."""
    db, _module = env

    with pytest.raises(Exception):
        db.execute(text("SELECT unit_weight FROM xlk_test_phantom")).fetchall()
    assert pg_abort_semantics["aborted"] is True
    with pytest.raises(_AbortedTransaction):
        db.execute(text("SELECT 1")).fetchall()
    db.rollback()
    assert db.execute(text("SELECT 1")).scalar() == 1


def test_a_failed_reference_read_leaves_the_session_alive(env, pg_abort_semantics):
    """THE assertion this whole sample exists for.

    `bonding_plan.py` catches a failed lookup and degrades honestly but never rolls
    back, so on PostgreSQL the caller dies one query later with an error naming the
    wrong statement. Here the read fails, the row says `mapping_unavailable`, and the
    session the WORKER owns is still usable."""
    import config_resolve_report as vocab

    db, _module = env
    payloads = _trigger_payloads(db, [{"log_id": "L1", "part_no": "P-COMPLETE"}])

    result = _run(db, payloads, dict(RULE, lookup_table="xlk_test_phantom"))

    cells = _by_key(result)["P-COMPLETE"]
    assert cells["lookup_status"] == vocab.REASON_MAPPING_UNAVAILABLE
    assert "pack_weight" not in cells
    # Alive. Not "the exception was caught" - the next statement actually runs.
    assert pg_abort_semantics["aborted"] is False
    assert db.execute(text("SELECT 1")).scalar() == 1


def test_the_savepoint_is_what_keeps_the_session_alive(env, pg_abort_semantics, monkeypatch):
    """Mutation check: remove the SAVEPOINT, keep the try/except, watch the session die.

    Without this, the test above is green whether or not `_isolated_fetch` opens a
    savepoint, and the reader cannot tell which line is load-bearing."""
    db, module = env
    payloads = _trigger_payloads(db, [{"log_id": "L1", "part_no": "P-COMPLETE"}])

    def _bare_fetch(session, query):
        return query.all()          # the defect: caught upstream, contained nowhere

    monkeypatch.setattr(module, "_isolated_fetch", _bare_fetch)
    module.build_pack_weight_batch(
        db, payloads, rule=dict(RULE, lookup_table="xlk_test_phantom"))

    assert pg_abort_semantics["aborted"] is True
    with pytest.raises(_AbortedTransaction):
        db.execute(text("SELECT 1")).fetchall()
