"""A chain may not emit a row whose key columns are not filled — ONE gate, on the funnel.

WHAT THIS PINS
--------------
A mapper that cannot resolve an identity for a row used to emit the row anyway. The write
path then did exactly what `818c9c0` ruled it must — a blank key column writes nothing —
so the row landed with `business_key_val` NULL. Nothing can address such a row, so the
next delivery of the same data created ANOTHER one, and one of them made the alignment
worklist answer 500 for a whole request (`c4a3159`).

🔴 A figure of "~170,000" used to sit in this paragraph and it was the wrong predicate —
that is `duplicate_census`'s `surplus`, counted `WHERE business_key_val IS NOT NULL`, i.e.
rows that were KEYED and duplicated. The keyless count is a different field and its
production value is not recorded anywhere tracked. Do not re-add a number here.

Three of the four places that compose a unit key already guarded this by hand. The gate
under test is deliberately NOT a fourth copy: `server/mappers/*.py` is gitignored by
design, so a guard written into a mapper never reaches a deployment. `chain_key_gate`
is tracked and sits on the two funnels every chain-emitted row already passes through
(`chain_ingestion_worker`'s `write_batches` loop, `chain_replay._apply_replay_batch`).

THE BEFORE-STATE IS RUN, NOT ASSERTED FROM A DOCSTRING
------------------------------------------------------
`test_without_the_gate_...` neutralises the gate and shows the keyless row REACHING the
database through the real worker on the real write path. A test that only shows the fixed
behaviour cannot tell a working guard from a guard that never fires.

MUTATION SCORING
Every test names the guard whose removal turns it red. The three shapes are scored
separately — no refusal, partial refusal, whole-batch refusal — because a gate exercised
only on the case that already worked proves nothing.
"""
import asyncio
import os
import sys
import types
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

import chain_key_gate
import chain_ingestion_worker as worker
import chain_replay
from database.database import Base
from database import crud, models, schemas
from database.models import DatabaseOutbox


#: Prefixes that cannot exist in the user's own (gitignored) `table_config.json`. A
#: collision lets `init_dynamic_models` win the race for the shared in-memory sqlite
#: schema and the suite fails with `no such column` — the `bonding_log` incident.
TRIGGER = "ckgate_test_trigger"
CELLS = "ckgate_test_cells"        # composite key, the map shape
UNITS = "ckgate_test_units"        # plain single-column business key
FREE = "ckgate_test_free"          # declares NO business key at all

TEST_TABLE_CONFIG = {
    TRIGGER: {
        "business_key": "src_key",
        "column_types": {"src_key": "string", "job": "string"},
    },
    CELLS: {
        "business_key": "cell_key",
        "composite_key_source": ["job", "x", "y"],
        "composite_key_separator": "_",
        "column_types": {"cell_key": "string", "job": "string", "x": "number",
                         "y": "number", "grade": "string"},
    },
    UNITS: {
        "business_key": "job",
        "column_types": {"job": "string", "frame": "string"},
    },
    FREE: {
        "column_types": {"anything": "string"},
    },
}


@pytest.fixture(name="db")
def fixture_db():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    models.init_dynamic_models(TEST_TABLE_CONFIG)
    crud.TABLE_CONFIG.update(TEST_TABLE_CONFIG)

    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)

    chain_key_gate.reset_counters()
    session = Session()
    yield session
    session.close()
    chain_key_gate.reset_counters()
    Base.metadata.drop_all(bind=engine)


def _item(**kw):
    kw.setdefault("updates", {})
    kw.setdefault("source_name", "chain_ingestion")
    kw.setdefault("updated_by", "chain_worker")
    return schemas.GeneralUpdateItem(**kw)


def _rows(db, table):
    return db.query(models.DYNAMIC_TABLES[table]).all()


def _keyless(db, table):
    return [r for r in _rows(db, table) if not r.business_key_val]


# ---------------------------------------------------------------------------
# Driving the REAL worker funnel
# ---------------------------------------------------------------------------

def _event(table=TRIGGER):
    return DatabaseOutbox(event_uuid="ckgate-event", event_type="CREATE",
                          table_name=table, payload={"source_name": "user", "data": {}})


def _rule(target, **kw):
    base = {"name": "ckgate_rule", "trigger_table": TRIGGER, "target_table": target,
            "mapper_module": "unused", "mapper_function": "unused",
            "is_batch": True, "enabled": True}
    base.update(kw)
    return base


def _run_chain(db, monkeypatch, rules, mapper_result, tx="ckgate-tx"):
    """Drive `process_chain_transaction_group` — the production funnel — for real.

    Only the two things a unit test cannot supply are faked: the outbox expansion and
    the mapper. The batch construction, the gate, `crud.apply_batch_updates` and the
    broadcast build are all the shipped code.
    """
    event = _event()
    monkeypatch.setattr(worker.outbox_expand, "expand_events",
                        lambda _db, events: {worker.outbox_expand.event_key(e): [{"data": {}}]
                                             for e in events})
    monkeypatch.setattr(worker, "execute_custom_mapper",
                        lambda _m, _f, _db, _payload, rule=None: mapper_result)
    return asyncio.run(worker.process_chain_transaction_group(tx, [event], db, rules))


# ---------------------------------------------------------------------------
# 1. The predicate — asked with the system's own blank predicate, read from config
# ---------------------------------------------------------------------------

def test_a_complete_composite_key_is_accepted(db):
    """KILLS: any gate that refuses on absence of `business_key_val` alone.

    Nothing here carries a `business_key_val`; the key is ASSEMBLED from the payload's
    own columns, which is how every map push addresses a cell.
    """
    assert crud.unfilled_key_columns(CELLS, _item(updates={"job": "J1", "x": 3, "y": 7})) == []


def test_a_zero_coordinate_is_a_value_and_not_a_blank(db):
    """KILLS: replacing `is_blank_value` with a truthiness test.

    `0` is the origin die. A gate that reads falsy as blank refuses the centre of every
    map — the exact shape of "a guard worse than the defect".
    """
    assert crud.unfilled_key_columns(CELLS, _item(updates={"job": "J1", "x": 0, "y": 0})) == []
    assert crud.unfilled_key_columns(CELLS, _item(updates={"job": "0", "x": 0, "y": 0})) == []


@pytest.mark.parametrize("updates,expected", [
    ({"job": "", "x": 1, "y": 2}, ["job"]),
    ({"job": "   ", "x": 1, "y": 2}, ["job"]),
    ({"job": "J1", "x": 1, "y": None}, ["y"]),
    ({"job": "J1", "x": 1}, ["y"]),
    ({"job": "", "x": None}, ["job", "x", "y"]),
])
def test_an_unfilled_key_column_is_named_not_merely_counted(db, updates, expected):
    """KILLS: returning a bool instead of the column names.

    The operator's next move is to open that column, and "some key is missing" makes the
    whole derived table the search space (the reasoning `c4a3159` recorded).
    """
    assert crud.unfilled_key_columns(CELLS, _item(updates=updates)) == expected


def test_an_item_that_already_has_an_identity_is_never_judged(db):
    """KILLS: dropping the `row_id` / `business_key_val` early-outs.

    Such an item resolves onto an existing row, so refusing it would refuse an UPDATE —
    turning a gate against fabricating rows into one that blocks correcting them.
    """
    assert crud.unfilled_key_columns(CELLS, _item(row_id="r1", updates={"grade": "A"})) == []
    assert crud.unfilled_key_columns(
        CELLS, _item(business_key_val="J1_1_2", updates={"grade": "A"})) == []


def test_a_plain_business_key_is_read_from_the_declaration_not_a_literal(db):
    """KILLS: hardcoding a key column name.

    Today's incident was caused by a hardcoded `dt_job` where production's column is
    `dt_job_id`. This table's key column is `job` only because `table_config` says so.
    """
    assert crud.unfilled_key_columns(UNITS, _item(business_key_val="J1")) == []
    assert crud.unfilled_key_columns(UNITS, _item(updates={"job": "J1"})) == []
    assert crud.unfilled_key_columns(UNITS, _item(business_key_val="", updates={})) == ["job"]
    assert crud.unfilled_key_columns(UNITS, _item(updates={"frame": "{}"})) == ["job"]


def test_a_table_that_declares_no_key_is_not_judged(db):
    """KILLS: refusing whenever no key can be found.

    A table with no declared identity has no rule to break, and inventing one here would
    be a policy change for tables that never asked for it.
    """
    assert crud.unfilled_key_columns(FREE, _item(updates={"anything": "x"})) == []
    assert crud.unfilled_key_columns("ckgate_not_a_table", _item(updates={"a": 1})) == []


def test_the_gate_and_the_key_assembler_answer_the_same_question(db):
    """KILLS: re-deriving the completeness rule instead of sharing
    `_unfilled_composite_parts`.

    Two spellings of "is this key buildable?" would let the gate refuse rows the writer
    would have keyed, or pass rows it will not. Scored by running BOTH over the same
    payloads and requiring exact agreement.
    """
    payloads = [{"job": "J1", "x": 1, "y": 2}, {"job": "J1", "x": 0, "y": 0},
                {"job": "", "x": 1, "y": 2}, {"job": "J1", "x": 1},
                {"job": "J1", "x": 1, "y": ""}, {"job": " ", "x": " ", "y": " "}]
    for payload in payloads:
        gate_accepts = not crud.unfilled_key_columns(CELLS, _item(updates=dict(payload)))
        probe = _item(updates=dict(payload))
        assembler_built = crud.assemble_composite_business_key(CELLS, probe)
        assert gate_accepts == assembler_built, payload


def test_the_gate_never_mutates_the_payload_it_judges(db):
    """KILLS: implementing the gate by calling `assemble_composite_business_key`.

    🔴 That function writes the computed key back into `updates[key_col]`, and doing so
    BEFORE `derive_replace_map_scope` runs would narrow a whole-map purge down to a single
    die (its own ordering constraint). The gate must be able to ask at any point.
    """
    item = _item(updates={"job": "J1", "x": 1, "y": 2})
    before = dict(item.updates)
    crud.unfilled_key_columns(CELLS, item)
    assert item.updates == before
    assert item.business_key_val is None and item.row_id is None


# ---------------------------------------------------------------------------
# 2. The gate is ON the live worker funnel — before-state RUN
# ---------------------------------------------------------------------------

def test_without_the_gate_the_worker_writes_a_row_with_no_business_key(db, monkeypatch):
    """THE BEFORE-STATE, reproduced through the shipped worker and write path.

    The gate is neutralised to a pass-through; nothing else changes. Three rows in, three
    rows out, and one of them carries `business_key_val` NULL — unaddressable by any
    upsert, so the next delivery of the same data adds another.
    """
    monkeypatch.setattr(chain_key_gate, "screen",
                        lambda table, items, rule_names=(), transaction_id=None: (
                            list(items), {"refused_rows": 0, "by_column": {}, "rules": []}))

    ok, err, _msgs = _run_chain(db, monkeypatch, [_rule(CELLS)], {"updates": [
        {"updates": {"job": "J1", "x": 1, "y": 1, "grade": "A"}},
        {"updates": {"job": "J1", "x": 2, "y": 2, "grade": "B"}},
        {"updates": {"job": "", "x": 3, "y": 3, "grade": "C"}},
    ]})

    assert ok and err is None
    assert len(_rows(db, CELLS)) == 3
    assert len(_keyless(db, CELLS)) == 1, "the defect must be reachable, or the fix proves nothing"

    # And it compounds: the same delivery again cannot address the keyless row.
    _run_chain(db, monkeypatch, [_rule(CELLS)], {"updates": [
        {"updates": {"job": "", "x": 3, "y": 3, "grade": "C"}},
    ]}, tx="ckgate-tx2")
    assert len(_keyless(db, CELLS)) == 2, "a keyless row is duplicated by every re-delivery"


def test_the_worker_refuses_the_unkeyed_row_and_writes_the_healthy_ones(db, monkeypatch):
    """KILLS: removing the `chain_key_gate.screen` call from the `write_batches` loop.

    Partial refusal, not whole-batch: `c4a3159` ruled that one bad row must not take the
    healthy ones down with it, and that ruling applies here too.
    """
    ok, err, _msgs = _run_chain(db, monkeypatch, [_rule(CELLS)], {"updates": [
        {"updates": {"job": "J1", "x": 1, "y": 1, "grade": "A"}},
        {"updates": {"job": "J1", "x": 2, "y": 2, "grade": "B"}},
        {"updates": {"job": "", "x": 3, "y": 3, "grade": "C"}},
    ]})

    assert ok and err is None
    rows = _rows(db, CELLS)
    assert len(rows) == 2, "the two healthy rows must still land"
    assert _keyless(db, CELLS) == []
    assert sorted(r.business_key_val for r in rows) == ["J1_1_1", "J1_2_2"]


def test_a_healthy_chain_write_is_unchanged_and_refuses_nothing(db, monkeypatch):
    """KILLS: any gate that refuses rows which are fine today.

    A guard that turns working ingestion into refusals is worse than the defect, so the
    zero case is scored as its own test rather than assumed.
    """
    ok, err, _msgs = _run_chain(db, monkeypatch, [_rule(CELLS)], {"updates": [
        {"updates": {"job": "J1", "x": x, "y": 0, "grade": "A"}} for x in range(25)
    ]})

    assert ok and err is None
    assert len(_rows(db, CELLS)) == 25
    assert _keyless(db, CELLS) == []
    assert chain_key_gate.refusals() == {}
    assert chain_key_gate.note() is None, "a clean run must leave the heartbeat unchanged"


def test_the_plain_key_target_is_gated_too(db, monkeypatch):
    """KILLS: gating only tables that declare `composite_key_source`.

    `dt_inventory` — the table the incident landed in — has a plain `business_key` and no
    composite source, so a composite-only gate would have missed the actual defect.
    """
    ok, _err, _msgs = _run_chain(db, monkeypatch, [_rule(UNITS)], {"updates": [
        {"business_key_val": "J1", "updates": {"job": "J1", "frame": "{}"}},
        {"business_key_val": "", "updates": {"frame": "{}"}},
        {"updates": {"frame": "{}"}},
    ]})

    assert ok
    rows = _rows(db, UNITS)
    assert [r.business_key_val for r in rows] == ["J1"]
    assert chain_key_gate.refused_rows() == {UNITS: 2}


# ---------------------------------------------------------------------------
# 3. A refusal must never become a deletion
# ---------------------------------------------------------------------------

def test_a_replace_map_whose_every_row_is_refused_does_not_purge_the_map(db, monkeypatch):
    """KILLS: removing the `if not kept: continue` arm in the worker.

    🔴 THE ONE WAY THIS GATE COULD DESTROY DATA. A `replace_map` batch purges its scope
    and then writes the payload. Filtering every row out and proceeding would purge the
    map and write nothing — turning a refusal into a deletion. A DECLARED empty replace
    is untouched by this arm, because it is only reached when the GATE emptied the list.
    """
    seeded = _run_chain(db, monkeypatch,
                        [_rule(CELLS, allow_replace_map=True)],
                        {"updates": [], "batches": [{
                            "target_table": CELLS, "replace_map": True,
                            "scope": {"job": "J1"},
                            "updates": [{"updates": {"job": "J1", "x": x, "y": 0, "grade": "A"}}
                                        for x in range(4)]}]})
    assert seeded[0] and len(_rows(db, CELLS)) == 4

    ok, err, _msgs = _run_chain(db, monkeypatch,
                                [_rule(CELLS, allow_replace_map=True)],
                                {"updates": [], "batches": [{
                                    "target_table": CELLS, "replace_map": True,
                                    "scope": {"job": "J1"},
                                    "updates": [{"updates": {"job": "", "x": x, "y": 0}}
                                                for x in range(4)]}]},
                                tx="ckgate-replace-2")

    assert ok and err is None
    assert len(_rows(db, CELLS)) == 4, "refusing must not delete what is already there"
    assert _keyless(db, CELLS) == []


def test_an_existing_row_is_updated_not_refused_when_the_payload_repeats_its_key(db, monkeypatch):
    """KILLS: a gate placed after identity resolution, or one that judges stored values.

    The gate judges what the CHAIN SENT. A second delivery carrying the same complete key
    must update the same row — no refusal, no second row.
    """
    payload = {"updates": [{"updates": {"job": "J1", "x": 1, "y": 1, "grade": "A"}}]}
    _run_chain(db, monkeypatch, [_rule(CELLS)], payload)
    payload2 = {"updates": [{"updates": {"job": "J1", "x": 1, "y": 1, "grade": "B"}}]}
    _run_chain(db, monkeypatch, [_rule(CELLS)], payload2, tx="ckgate-tx2")

    rows = _rows(db, CELLS)
    assert len(rows) == 1 and rows[0].grade == "B"
    assert chain_key_gate.refusals() == {}


# ---------------------------------------------------------------------------
# 4. Refusing is LOUD — countable and attributable
# ---------------------------------------------------------------------------

def test_a_refusal_names_the_rule_the_table_the_column_and_the_count(db):
    """KILLS: reducing the report to a bare count.

    A silent skip is the same class of defect as a bad write; today cost a full day
    precisely because the drop was invisible.
    """
    kept, report = chain_key_gate.screen(CELLS, [
        _item(updates={"job": "J1", "x": 1, "y": 1}),
        _item(updates={"job": "", "x": 2, "y": 2}),
        _item(updates={"job": "J1", "x": 3, "y": None}),
    ], rule_names=["ckgate_rule"], transaction_id="tx-loud")

    assert len(kept) == 1
    assert report["table"] == CELLS
    assert report["reason"] == chain_key_gate.REFUSAL_UNKEYED_ROW
    assert report["rules"] == ["ckgate_rule"]
    assert report["transaction_id"] == "tx-loud"
    assert report["refused_rows"] == 2
    assert report["by_column"] == {"job": 1, "y": 1}
    assert [r["unfilled"] for r in report["rows"]] == [["job"], ["y"]]


def test_a_refusal_from_the_live_worker_names_the_RULE_an_operator_must_fix(db, monkeypatch, caplog):
    """KILLS: dropping `rules_by_target` and passing no rule names from the worker.

    Found by mutation: every other test here passed with the attribution removed, because
    they all read the report rather than the operator's channel. `table_updates`
    aggregates several rules onto one target, so the rule cannot be recovered after the
    fact — it has to be recorded where the rule is bound to its target.
    """
    with caplog.at_level("INFO", logger="chain_key_gate"):
        _run_chain(db, monkeypatch,
                   [_rule(CELLS, name="ckgate_named_rule")],
                   {"updates": [{"updates": {"job": "", "x": 1, "y": 1}}]})

    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "ckgate_named_rule" in text, "the refusal must name the rule"
    assert CELLS in text and "job" in text


def test_the_refusal_count_reaches_another_process_through_the_heartbeat(db, monkeypatch):
    """KILLS: removing `chain_key_gate.note()` from `_worker_note`.

    The refusals happen in the chain worker; the question they raise has to be answerable
    from the web server, which is a different process. The heartbeat note is the
    cross-process channel `/health` already reads for `undeclared_column_drops()`, so no
    third channel is built.
    """
    assert worker._worker_note() is None, "a clean worker's beat must stay byte-identical"

    _run_chain(db, monkeypatch, [_rule(CELLS)], {"updates": [
        {"updates": {"job": "", "x": 1, "y": 1}},
        {"updates": {"job": "J1", "x": 2, "y": None}},
    ]})

    note = worker._worker_note()
    assert note is not None
    assert "rows=2" in note
    assert f"{CELLS}.job=1" in note and f"{CELLS}.y=1" in note


def test_the_report_states_what_it_withheld_rather_than_ending_silently(db):
    """KILLS: capping the detail without saying so.

    Every row id and column name in the report comes from a PAYLOAD, so a malformed
    source must not grow it without limit — but a total that silently stops adding up is
    how the original defect hid.
    """
    items = [_item(updates={"job": "", "x": i, "y": 0}) for i in range(60)]
    _kept, report = chain_key_gate.screen(CELLS, items, rule_names=["r"], transaction_id="t")

    assert report["refused_rows"] == 60, "counts are never capped"
    assert len(report["rows"]) == chain_key_gate.MAX_REFUSAL_ROWS
    assert report["rows_omitted"] == 60 - chain_key_gate.MAX_REFUSAL_ROWS


# ---------------------------------------------------------------------------
# 5. The second funnel — replay runs the same mappers
# ---------------------------------------------------------------------------

def test_replay_cannot_recreate_in_bulk_what_the_live_worker_refuses(db):
    """KILLS: wiring the gate into the worker only.

    `chain_replay` re-runs the same mappers over a table's whole current contents, so a
    gate on the live path alone would leave the bulk path able to manufacture exactly the
    rows the incident is about. Note also that replay's own `SKIP_BLANK` strips a blank
    key column from `updates`, which is what makes such an item unkeyable here.
    """
    stats = {"cells_written": 0, "rows_created": 0, "rows_updated": 0,
             "unkeyed_rows_refused": 0, "unkeyed_key_columns": {}}
    chain_replay._apply_replay_batch(
        db, schemas, crud, CELLS,
        [_item(updates={"job": "J1", "x": 1, "y": 1, "grade": "A"}),
         _item(updates={"x": 2, "y": 2, "grade": "B"})],
        "run1", stats, 1, rule_name="ckgate_rule")

    assert stats["unkeyed_rows_refused"] == 1
    assert stats["unkeyed_key_columns"] == {"job": 1}
    assert stats["rows_created"] == 1
    assert _keyless(db, CELLS) == []


def test_replay_does_not_purge_a_map_it_refused_whole(db):
    """KILLS: removing the `if not kept: return` arm in `_apply_replay_batch`."""
    seed = {"cells_written": 0, "rows_created": 0, "rows_updated": 0,
            "unkeyed_rows_refused": 0, "unkeyed_key_columns": {}}
    chain_replay._apply_replay_batch(
        db, schemas, crud, CELLS,
        [_item(updates={"job": "J1", "x": x, "y": 0, "grade": "A"}) for x in range(3)],
        "run1", seed, 1, rule_name="ckgate_rule")
    assert len(_rows(db, CELLS)) == 3

    stats = dict(seed, unkeyed_rows_refused=0, unkeyed_key_columns={})
    chain_replay._apply_replay_batch(
        db, schemas, crud, CELLS,
        [_item(updates={"job": "", "x": x, "y": 0}) for x in range(3)],
        "run2", stats, 2, replace_map=True, scope={"job": "J1"}, rule_name="ckgate_rule")

    assert stats["unkeyed_rows_refused"] == 3
    assert len(_rows(db, CELLS)) == 3, "a whole-batch refusal must not become a purge"
