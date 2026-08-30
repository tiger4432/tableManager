"""Chain Replay R1 (re-application) + R2 (stale source withdrawal).

Each safety property is proved by INJECTION, not by assertion:
- the self-write guard: disable it and the same replay walks its own output,
- the user layer: a human's value survives an apply and the display never moves,
- the replay order: a producer/consumer pair is ordered, a cross-table cycle is
  refused by name,
- the withdrawal: it reveals the NEXT source rather than leaving a hole, refuses
  `user` outright, and refuses a source a human pinned.

[Isolation] `crep_test_` prefix (server-pm memory: the bonding_log trap).
"""
import sys
import types

import pytest

import chain_replay
from database import crud, models, schemas

REP_TABLES = {
    "crep_test_trigger": {
        "business_key": "src_key",
        "column_types": {"src_key": "string", "part_no": "string", "qty": "number"},
    },
    "crep_test_target": {
        "business_key": "part_no",
        "column_types": {"part_no": "string", "reserved": "number", "note": "string"},
    },
    "crep_test_self": {
        "business_key": "self_key",
        "column_types": {"self_key": "string", "seq": "number", "spawned": "string"},
    },
}


# --------------------------------------------------------------------------
# A test mapper module, registered in sys.modules so the REAL
# `execute_custom_mapper` (importlib) resolves it exactly as it resolves
# mappers.production_mapper. Mappers are pure functions of the payload - that is
# the property replay depends on, so the fake must have it too.
# --------------------------------------------------------------------------
MAPPER_MODULE = "crep_test_mapper"


def _install_mapper_module():
    mod = types.ModuleType(MAPPER_MODULE)

    def map_reserve(db, payloads, rule=None):
        updates = []
        for p in payloads:
            data = p.get("data") or {}
            part = (data.get("part_no") or {}).get("value")
            qty = (data.get("qty") or {}).get("value") or 0
            updates.append({"business_key_val": part,
                            "updates": {"part_no": part, "reserved": float(qty) * 2}})
        return {"updates": updates}

    def map_blank_note(db, payloads, rule=None):
        """Produces NO value for `note` - the shape R1 must refuse to write."""
        updates = []
        for p in payloads:
            part = ((p.get("data") or {}).get("part_no") or {}).get("value")
            updates.append({"business_key_val": part,
                            "updates": {"part_no": part, "note": ""}})
        return {"updates": updates}

    def map_spawn(db, payloads, rule=None):
        """Self-triggering: every input row produces a NEW row in the SAME table.
        Without the snapshot bound the scan meets its own output forever."""
        updates = []
        for p in payloads:
            data = p.get("data") or {}
            key = (data.get("self_key") or {}).get("value")
            seq = float((data.get("seq") or {}).get("value") or 0)
            updates.append({"business_key_val": f"{key}_x",
                            "updates": {"self_key": f"{key}_x", "seq": seq + 1,
                                        "spawned": "yes"}})
        return {"updates": updates}

    mod.map_reserve = map_reserve
    mod.map_blank_note = map_blank_note
    mod.map_spawn = map_spawn
    sys.modules[MAPPER_MODULE] = mod


RULE_RESERVE = {
    "name": "crep_reserve", "trigger_table": "crep_test_trigger",
    "target_table": "crep_test_target", "mapper_module": MAPPER_MODULE,
    "mapper_function": "map_reserve", "is_batch": True, "enabled": True,
}
RULE_BLANK = dict(RULE_RESERVE, name="crep_blank", mapper_function="map_blank_note")
RULE_SELF = {
    "name": "crep_self", "trigger_table": "crep_test_self",
    "target_table": "crep_test_self", "mapper_module": MAPPER_MODULE,
    "mapper_function": "map_spawn", "is_batch": True, "enabled": True,
}


@pytest.fixture()
def rep_env(db_session):
    models.init_dynamic_models(REP_TABLES)
    crud.TABLE_CONFIG.update(REP_TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    _install_mapper_module()
    yield db_session
    sys.modules.pop(MAPPER_MODULE, None)


def _bk(table, row):
    """Business key the way crud assembles it.

    Passing `business_key_val` explicitly is NOT optional for a table with a
    plain `business_key` and no `composite_key_source`: omitting it makes
    `apply_batch_updates` insert a SECOND row carrying the same business key
    instead of matching the existing one (measured, 2026-07-30 - reported as an
    observation). Every seed here therefore states the key.
    """
    cfg = crud.TABLE_CONFIG[table]
    comp = cfg.get("composite_key_source")
    if comp:
        sep = cfg.get("composite_key_separator", "_")
        return sep.join(crud.clean_str_value(row.get(c)) for c in comp)
    return crud.clean_str_value(row.get(cfg["business_key"]))


def _seed(db, table, rows, source_name="pipeline_parser", tx_id="seed"):
    items = [schemas.GeneralUpdateItem(business_key_val=_bk(table, r), updates=dict(r),
                                       source_name=source_name, updated_by="test")
             for r in rows]
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(
        updates=items, transaction_id=tx_id, silent=True))


def _target(db, bk):
    m = models.DYNAMIC_TABLES["crep_test_target"]
    return db.query(m).filter(m.business_key_val == bk).first()


def _sources(db, table, row_id, col):
    return {s.source_name: s.value for s in db.query(models.CellSource).filter(
        models.CellSource.table_name == table,
        models.CellSource.row_id == row_id,
        models.CellSource.column_name == col).all()}


# ---------------------------------------------------------------------------
# R1 — rule re-application
# ---------------------------------------------------------------------------

def test_r1_dry_run_reports_without_writing(rep_env):
    _seed(rep_env, "crep_test_trigger",
          [{"src_key": "s1", "part_no": "P1", "qty": 5}])
    stats = chain_replay.replay_rule(rep_env, RULE_RESERVE, apply=False, log=lambda *_: None)
    assert stats["mode"] == "dry-run"
    assert stats["rows_scanned"] == 1
    assert stats["cells_proposed"] == 2      # part_no + reserved
    assert stats["cells_written"] == 0
    assert _target(rep_env, "P1") is None, "a dry-run must create nothing"


def test_r1_apply_writes_through_the_real_layering_path(rep_env):
    _seed(rep_env, "crep_test_trigger",
          [{"src_key": "s1", "part_no": "P1", "qty": 5},
           {"src_key": "s2", "part_no": "P2", "qty": 3}])
    stats = chain_replay.replay_rule(rep_env, RULE_RESERVE, apply=True, log=lambda *_: None)
    assert stats["rows_created"] == 2
    assert float(_target(rep_env, "P1").reserved) == 10.0
    # Provenance is the SAME layer the live worker writes - replay is not a new layer.
    row = _target(rep_env, "P1")
    assert set(_sources(rep_env, "crep_test_target", row.row_id, "reserved")) == \
        {chain_replay.R1_SOURCE_NAME}


def test_r1_is_idempotent(rep_env):
    _seed(rep_env, "crep_test_trigger", [{"src_key": "s1", "part_no": "P1", "qty": 5}])
    chain_replay.replay_rule(rep_env, RULE_RESERVE, apply=True, log=lambda *_: None)
    second = chain_replay.replay_rule(rep_env, RULE_RESERVE, apply=True, log=lambda *_: None)
    assert second["rows_created"] == 0
    assert float(_target(rep_env, "P1").reserved) == 10.0


def test_r1_cannot_overwrite_a_human_value(rep_env):
    """THE safety property. A human sets `reserved`; the replay writes its own
    layer underneath and the displayed value never moves."""
    _seed(rep_env, "crep_test_trigger", [{"src_key": "s1", "part_no": "P1", "qty": 5}])
    _seed(rep_env, "crep_test_target", [{"part_no": "P1", "reserved": 999}],
          source_name="user", tx_id="human")
    assert float(_target(rep_env, "P1").reserved) == 999.0

    chain_replay.replay_rule(rep_env, RULE_RESERVE, apply=True, log=lambda *_: None)
    row = _target(rep_env, "P1")
    assert float(row.reserved) == 999.0, "replay must never outrank a human's value"
    # Both layers exist; the human's simply wins.
    srcs = _sources(rep_env, "crep_test_target", row.row_id, "reserved")
    assert set(srcs) == {"user", chain_replay.R1_SOURCE_NAME}
    assert float(srcs[chain_replay.R1_SOURCE_NAME]) == 10.0


def test_r1_dry_run_counts_user_protected_cells(rep_env):
    _seed(rep_env, "crep_test_trigger", [{"src_key": "s1", "part_no": "P1", "qty": 5}])
    _seed(rep_env, "crep_test_target", [{"part_no": "P1", "reserved": 999}],
          source_name="user", tx_id="human")
    stats = chain_replay.replay_rule(rep_env, RULE_RESERVE, apply=False, log=lambda *_: None)
    assert stats["user_protected_cells"] >= 1, \
        "the dry-run must state the safety property in numbers, not only in prose"


def test_r1_never_writes_a_blank_and_reports_it_as_an_r2_candidate(rep_env):
    """ABSENCE IS NOT ZERO. 'the rule produces nothing here' is R2's statement."""
    _seed(rep_env, "crep_test_trigger", [{"src_key": "s1", "part_no": "P1", "qty": 5}])
    _seed(rep_env, "crep_test_target", [{"part_no": "P1", "note": "OLD"}], tx_id="pre")
    stats = chain_replay.replay_rule(rep_env, RULE_BLANK, apply=True, log=lambda *_: None)
    assert stats["skipped_blank_cells"] == 1
    assert stats["withdrawal_candidates"], "a vanished value must be reported, not written"
    assert stats["withdrawal_candidates"][0]["column"] == "note"
    assert _target(rep_env, "P1").note == "OLD", "R1 must not blank an existing value"


# ---------------------------------------------------------------------------
# R1 — the loop guard, proved by removing it
# ---------------------------------------------------------------------------

def test_r1_self_triggering_scan_is_bounded_by_the_snapshot(rep_env):
    _seed(rep_env, "crep_test_self",
          [{"self_key": f"k{i}", "seq": i} for i in range(1, 4)])
    stats = chain_replay.replay_rule(rep_env, RULE_SELF, apply=True, log=lambda *_: None)
    assert stats["self_triggering"] is True
    assert stats["rows_scanned"] == 3, \
        "the scan must see only the rows that existed when it started"


def test_r1_without_the_snapshot_guard_the_scan_eats_its_own_output(rep_env, monkeypatch):
    """INJECTED DEFECT: disable the self-write detection. The same replay now
    walks rows it created itself, which is precisely the runaway the guard
    prevents. Bounded with `limit` so a failure cannot hang the suite."""
    _seed(rep_env, "crep_test_self",
          [{"self_key": f"k{i}", "seq": i} for i in range(1, 4)])
    monkeypatch.setattr(chain_replay, "is_self_triggering", lambda rule: False)
    stats = chain_replay.replay_rule(rep_env, RULE_SELF, apply=True, limit=40,
                                     chunk_size=3, log=lambda *_: None)
    assert stats["rows_scanned"] > 3, \
        "without the guard the scan must be observed consuming its own writes"


def test_r1_replay_order_puts_the_producer_first(rep_env):
    consumer = dict(RULE_RESERVE, name="consumer", trigger_table="crep_test_target",
                    target_table="crep_test_self")
    producer = dict(RULE_RESERVE, name="producer", trigger_table="crep_test_trigger",
                    target_table="crep_test_target")
    order = [r["name"] for r in chain_replay.order_rules([consumer, producer])]
    assert order.index("producer") < order.index("consumer")


def test_r1_self_edge_is_not_treated_as_a_cycle(rep_env):
    order = [r["name"] for r in chain_replay.order_rules([RULE_SELF, RULE_RESERVE])]
    assert set(order) == {"crep_self", "crep_reserve"}


def test_r1_cross_table_cycle_is_refused_by_name(rep_env):
    a = dict(RULE_RESERVE, name="a", trigger_table="t1", target_table="t2")
    b = dict(RULE_RESERVE, name="b", trigger_table="t2", target_table="t1")
    with pytest.raises(chain_replay.ReplayRefused) as e:
        chain_replay.order_rules([a, b])
    assert "cycle" in str(e.value)


def test_r1_refuses_an_unknown_rule_with_the_available_list(rep_env):
    with pytest.raises(chain_replay.ReplayRefused) as e:
        chain_replay.find_rule("no_such_rule", [RULE_RESERVE])
    assert "crep_reserve" in str(e.value)


# ---------------------------------------------------------------------------
# R2 — stale source withdrawal
# ---------------------------------------------------------------------------

def _two_layer_cell(db):
    """A cell claimed by two machine sources: pipeline_parser (priority 2, wins)
    over custom_script (priority 3)."""
    _seed(db, "crep_test_target", [{"part_no": "P1", "note": "FROM_SCRIPT"}],
          source_name="custom_script", tx_id="s1")
    _seed(db, "crep_test_target", [{"part_no": "P1", "note": "FROM_PARSER"}],
          source_name="pipeline_parser", tx_id="s2")
    row = _target(db, "P1")
    assert row.note == "FROM_PARSER"
    return row


def test_r2_withdrawal_reveals_the_next_source_not_a_hole(rep_env):
    row = _two_layer_cell(rep_env)
    stats = chain_replay.withdraw_source(rep_env, "crep_test_target", "pipeline_parser",
                                         columns=["note"], apply=True, log=lambda *_: None)
    assert stats["cells_withdrawn"] == 1
    assert stats["revealed"] == 1
    assert stats["emptied"] == 0
    rep_env.refresh(row)
    assert row.note == "FROM_SCRIPT", "the layer underneath must become visible"
    assert set(_sources(rep_env, "crep_test_target", row.row_id, "note")) == {"custom_script"}


def test_r2_refuses_to_withdraw_the_user_layer(rep_env):
    _seed(rep_env, "crep_test_target", [{"part_no": "P1", "note": "HUMAN"}],
          source_name="user", tx_id="h")
    with pytest.raises(chain_replay.ReplayRefused) as e:
        chain_replay.withdraw_source(rep_env, "crep_test_target", "user", apply=True,
                                     log=lambda *_: None)
    assert "human" in str(e.value).lower()
    assert _target(rep_env, "P1").note == "HUMAN"


def test_r2_cannot_remove_a_human_value_when_withdrawing_a_machine_source(rep_env):
    """The T1 question, answered by test: withdrawing a machine layer under a
    human's value changes nothing the human can see, and leaves their cell_source
    row intact."""
    _seed(rep_env, "crep_test_target", [{"part_no": "P1", "note": "FROM_PARSER"}],
          source_name="pipeline_parser", tx_id="s1")
    _seed(rep_env, "crep_test_target", [{"part_no": "P1", "note": "HUMAN"}],
          source_name="user", tx_id="h")
    row = _target(rep_env, "P1")
    assert row.note == "HUMAN"

    chain_replay.withdraw_source(rep_env, "crep_test_target", "pipeline_parser",
                                 apply=True, log=lambda *_: None)
    rep_env.refresh(row)
    assert row.note == "HUMAN"
    assert set(_sources(rep_env, "crep_test_target", row.row_id, "note")) == {"user"}


def test_r2_skips_a_source_a_human_pinned(rep_env):
    """INJECTED: the operator pinned the very source being withdrawn. The pin is
    a human choice, so the withdrawal must decline and say so."""
    row = _two_layer_cell(rep_env)
    ow = models.CellOverwrite(table_name="crep_test_target", row_id=row.row_id,
                              column_name="note", is_overwrite=True, updated_by="tester",
                              manual_priority_source="pipeline_parser")
    rep_env.add(ow)
    rep_env.commit()

    stats = chain_replay.withdraw_source(rep_env, "crep_test_target", "pipeline_parser",
                                         columns=["note"], apply=True, log=lambda *_: None)
    assert stats["pinned_skipped"] == 1
    assert stats["cells_withdrawn"] == 0
    assert "pinned" in stats["samples"][0]["why"]
    assert "pipeline_parser" in _sources(rep_env, "crep_test_target", row.row_id, "note")


def test_r2_empty_stack_is_reported_as_emptied_not_revealed(rep_env):
    _seed(rep_env, "crep_test_target", [{"part_no": "P1", "note": "ONLY"}],
          source_name="custom_script", tx_id="s1")
    row = _target(rep_env, "P1")
    stats = chain_replay.withdraw_source(rep_env, "crep_test_target", "custom_script",
                                         columns=["note"], apply=True, log=lambda *_: None)
    assert stats["emptied"] == 1
    assert stats["revealed"] == 0
    rep_env.refresh(row)
    assert row.note is None


def test_r2_writes_an_audit_entry_naming_the_withdrawn_source(rep_env):
    """A cell that changes must not change silently: the existing cell-history
    timeline is where an operator asks 'why does this say this'."""
    row = _two_layer_cell(rep_env)
    chain_replay.withdraw_source(rep_env, "crep_test_target", "pipeline_parser",
                                 columns=["note"], apply=True, log=lambda *_: None)
    logs = rep_env.query(models.AuditLog).filter(
        models.AuditLog.table_name == "crep_test_target",
        models.AuditLog.row_id == row.row_id,
        models.AuditLog.column_name == "note").all()
    assert logs, "a withdrawal that changes a visible value must leave a trail"
    entry = logs[-1]
    assert entry.source_name == chain_replay.R2_AUDIT_SOURCE
    assert "pipeline_parser" in (entry.updated_by or "")
    assert entry.old_value == "FROM_PARSER"
    assert entry.new_value == "FROM_SCRIPT"


def test_r2_dry_run_changes_nothing(rep_env):
    row = _two_layer_cell(rep_env)
    stats = chain_replay.withdraw_source(rep_env, "crep_test_target", "pipeline_parser",
                                         columns=["note"], apply=False, log=lambda *_: None)
    assert stats["cells_withdrawn"] == 1     # it reports what it WOULD do
    rep_env.refresh(row)
    assert row.note == "FROM_PARSER"
    assert "pipeline_parser" in _sources(rep_env, "crep_test_target", row.row_id, "note")


def test_r2_column_scope_is_respected(rep_env):
    _seed(rep_env, "crep_test_target", [{"part_no": "P1", "note": "N", "reserved": 7}],
          source_name="custom_script", tx_id="s1")
    row = _target(rep_env, "P1")
    chain_replay.withdraw_source(rep_env, "crep_test_target", "custom_script",
                                 columns=["note"], apply=True, log=lambda *_: None)
    rep_env.refresh(row)
    assert row.note is None
    assert float(row.reserved) == 7.0, "an out-of-scope column must be untouched"


def test_r2_unknown_column_is_refused(rep_env):
    with pytest.raises(chain_replay.ReplayRefused):
        chain_replay.withdraw_source(rep_env, "crep_test_target", "custom_script",
                                     columns=["nope"], log=lambda *_: None)


# --------------------------------------------------------------------------
# R2 cost contract: the index that bounds `_claimed_filter`.
#
# The index itself is a PostgreSQL artifact and this suite runs on sqlite, so
# nothing here can prove a plan - `setup_db_performance.py` Step 3.11 does that,
# against real data, by EXPLAINing the statement. What CAN drift silently is the
# pairing, and it drifts in two directions that a comment saying "fix both
# places" does not catch:
#   1. the definition exists in models.py AND in the builder script (create_all
#      never adds an index to an existing table, so both are load-bearing),
#   2. the predicate `_claimed_filter` builds must stay a PREFIX of that index -
#      add one more filtered column and the index quietly stops bounding it while
#      every test still passes.
# --------------------------------------------------------------------------

WITHDRAW_INDEX = "idx_sources_by_source"


def _withdraw_index_columns():
    idx = [i for i in models.CellSource.__table__.indexes if i.name == WITHDRAW_INDEX]
    assert idx, f"{WITHDRAW_INDEX} is not declared on models.CellSource"
    return [c.name for c in idx[0].expressions]


def test_withdraw_index_definition_matches_the_builder_script():
    import os
    import re

    cols = _withdraw_index_columns()
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "scripts", "setup_db_performance.py")
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    m = re.search(r'\("%s",\s*\n?\s*"cell_sources",\s*\n?\s*"\(([^)]*)\)"' % WITHDRAW_INDEX,
                  src)
    assert m, (f"{WITHDRAW_INDEX} is declared in models.py but the builder script "
               f"does not create it - an existing database would never get it, "
               f"because create_all only builds indices for NEW tables")
    script_cols = [c.strip() for c in m.group(1).split(",")]
    assert script_cols == cols, (
        f"index definition drifted: models.py has {cols}, "
        f"setup_db_performance.py has {script_cols}")


def test_claimed_filter_stays_a_prefix_of_the_withdraw_index():
    """Every column `_claimed_filter` can filter on must be an index prefix.

    This is the assertion that would have caught the original defect: the
    predicate was (table_name, source_name) while the only composite index put
    `source_name` last, so the planner fell back to a Seq Scan of the whole
    table. Nothing failed - it was just slow.
    """
    cols = _withdraw_index_columns()

    def _referenced(conds):
        names = []
        for c in conds:
            col = getattr(c, "left", None)
            assert col is not None and getattr(col, "name", None), \
                f"unrecognised predicate shape: {c!r}"
            names.append(col.name)
        return names

    # Unscoped: (table_name, source_name) - must be the leading two keys, in order.
    assert _referenced(chain_replay._claimed_filter("t", "s")) == cols[:2]
    # Column-scoped: adds column_name - must be the third key, so the IN list is
    # part of the Index Cond rather than an in-index filter.
    assert _referenced(chain_replay._claimed_filter("t", "s", ["a", "b"])) == cols[:3]


# ---------------------------------------------------------------------------
# R2's OUTBOX LABEL - the loop filter
#
# A withdrawal reveals a layer by `setattr`, so the global `before_flush` staged
# its events under the context DEFAULTS - `source_name="user"`, one uuid4 each -
# and the live rule set could not tell an operator's withdrawal from a human
# typing in the grid. Measured on assy_qa (isolated): withdrawing 4 cells staged 4
# events with 4 distinct transaction ids, all 4 downstream target tables were
# woken, and a REAL WebSocket client received 4 `batch_row_upsert` messages for
# `dt_job_attribution` - a table nobody withdrew anything from.
#
# R2 IS NOT R3 AND THE HAZARD IS NOT THE SAME HAZARD. R3 creates no layer; R2
# DELETES one, which is its whole job. So the question here is whether the label
# can reach the deletion predicate or either refusal. It cannot - they are built
# from the `source_name` PARAMETER - and `test_withdraw_deletes_the_same_layers_
# whatever_the_outbox_label` is the measurement rather than the argument.
# ---------------------------------------------------------------------------

import chain_ingestion_worker as chain_worker  # noqa: E402

W_BLOCKED = {"name": "blocked", "trigger_table": "crep_test_target",
             "target_table": "crep_blocked_target", "enabled": True}
W_OPTED_IN = {"name": "opted_in", "trigger_table": "crep_test_target",
              "target_table": "crep_optin_target", "enabled": True,
              "allow_chain_trigger": True}


def _outbox_since(db, marker):
    return db.query(models.DatabaseOutbox).filter(
        models.DatabaseOutbox.id > marker).order_by(models.DatabaseOutbox.id).all()


def _outbox_marker(db):
    return db.query(models.DatabaseOutbox.id).order_by(
        models.DatabaseOutbox.id.desc()).limit(1).scalar() or 0


def _all_layers(db, table="crep_test_target"):
    """Every stored layer in the table. The WHOLE set, because the hazard is a
    deletion that takes the wrong row - which an assertion scoped to one cell of
    one row would not see."""
    return sorted(
        (s.row_id, s.column_name, s.source_name, str(s.value))
        for s in db.query(models.CellSource).filter(
            models.CellSource.table_name == table).all())


def _withdraw(db, source="pipeline_parser", **kw):
    return chain_replay.withdraw_source(db, "crep_test_target", source,
                                        columns=["note"], apply=True,
                                        log=lambda *_: None, **kw)


def test_r2_events_are_labelled_so_the_loop_filter_can_see_them(rep_env):
    """GUARD W1 - THE LABEL, put to the REAL filter rather than asserted as a string."""
    _two_layer_cell(rep_env)
    marker = _outbox_marker(rep_env)
    assert _withdraw(rep_env)["cells_withdrawn"] == 1

    events = _outbox_since(rep_env, marker)
    assert len(events) == 1, "one revealed row stages exactly one EDIT event"
    payload = chain_worker.get_payload_dict(events[0])
    assert payload["source_name"] == "chain_ingestion"
    assert payload["updated_by"] == chain_replay.R2_AUDIT_SOURCE
    assert not chain_worker._rule_accepts_event(W_BLOCKED, events[0]), \
        "a rule that never opted in must not be woken by an operator's withdrawal"
    assert chain_worker._group_target_tables(events, [W_BLOCKED]) == set()


def test_a_rule_that_opted_in_still_consumes_a_withdrawal_event(rep_env):
    """GUARD W2 - OPT-IN, NOT SUPPRESSION.

    A 'fix' that dropped R2's events, or stopped staging them, leaves W1 green and
    kills this. `allow_chain_trigger` must still mean yes.
    """
    _two_layer_cell(rep_env)
    marker = _outbox_marker(rep_env)
    _withdraw(rep_env)

    events = _outbox_since(rep_env, marker)
    assert events, "the withdrawal must still emit an event for anyone who wants it"
    assert chain_worker._rule_accepts_event(W_OPTED_IN, events[0])
    assert chain_worker._group_target_tables(events, [W_BLOCKED, W_OPTED_IN]) == \
        {"crep_optin_target"}


def test_r2_stages_one_transaction_id_for_the_whole_run(rep_env):
    """GUARD W3 - THE GROUPING. One uuid4 per event made N revealed rows into N
    serialised worker groups. `chunk_size=1` forces a page and a commit per row,
    which is what would expose a context scoped to a page instead of the run."""
    for i in range(3):
        _seed(rep_env, "crep_test_target", [{"part_no": f"P{i}", "note": "FROM_SCRIPT"}],
              source_name="custom_script", tx_id=f"s{i}a")
        _seed(rep_env, "crep_test_target", [{"part_no": f"P{i}", "note": "FROM_PARSER"}],
              source_name="pipeline_parser", tx_id=f"s{i}b")
    marker = _outbox_marker(rep_env)
    stats = _withdraw(rep_env, chunk_size=1)
    assert stats["cells_withdrawn"] == 3

    events = _outbox_since(rep_env, marker)
    assert len(events) == 3
    tx_ids = {chain_worker.get_payload_dict(e)["transaction_id"] for e in events}
    assert len(tx_ids) == 1, f"one group per run, got {len(tx_ids)}: {sorted(tx_ids)}"
    assert tx_ids.pop().startswith(chain_replay.R2_AUDIT_SOURCE)


def test_withdraw_deletes_the_same_layers_whatever_the_outbox_label(rep_env,
                                                                    monkeypatch):
    """GUARD W4 - THE DELETION IS UNCHANGED, and this is R2's version of the
    layering hazard.

    R2's whole job is to delete one `cell_sources` row, so "does the label reach
    the predicate that picks it" is a real question - and a different one from R3,
    which creates no layer at all. The deletion is built from the `source_name`
    PARAMETER (`_claimed_filter`, and the delete's own
    `CellSource.source_name == source_name`), never from `request_source`.

    Proved by running the SAME fixture twice - once with `transaction_context`
    no-oped, which is exactly the pre-fix state - and comparing the FULL surviving
    layer set, plus both refusals. On assy_qa the same comparison on a 5-cell
    fixture gave an identical survivor sha256 (fecb0b25...) either way.
    """
    import contextlib

    def _run():
        _two_layer_cell(rep_env)
        pinned = _target(rep_env, "P1")
        # A second cell the operator pinned TO the source being withdrawn: it must
        # be skipped, and it must be skipped identically in both modes.
        _seed(rep_env, "crep_test_target", [{"part_no": "P2", "note": "FROM_SCRIPT"}],
              source_name="custom_script", tx_id="p1")
        _seed(rep_env, "crep_test_target", [{"part_no": "P2", "note": "FROM_PARSER"}],
              source_name="pipeline_parser", tx_id="p2")
        crud.set_cell_manual_priority_batch(
            rep_env, "crep_test_target",
            [{"row_id": _target(rep_env, "P2").row_id, "column_name": "note"}],
            "pipeline_parser")
        before = _all_layers(rep_env)
        stats = _withdraw(rep_env)
        with pytest.raises(chain_replay.ReplayRefused):
            chain_replay.withdraw_source(rep_env, "crep_test_target", "user",
                                         apply=True, log=lambda *_: None)
        return before, _all_layers(rep_env), stats, pinned

    # Pass 1: the shipped code.
    fixed_before, fixed_after, fixed_stats, _ = _run()

    # Reset the table so pass 2 starts from the same place.
    rep_env.query(models.CellSource).delete()
    rep_env.query(models.CellOverwrite).delete()
    rep_env.query(models.DYNAMIC_TABLES["crep_test_target"]).delete()
    rep_env.commit()

    # Pass 2: PRE-FIX. No-oping `transaction_context` is precisely what the old
    # code did - set no context, let `_outbox_envelope` fall back to its defaults.
    monkeypatch.setattr(crud, "transaction_context",
                        lambda *a, **k: contextlib.nullcontext())
    plain_before, plain_after, plain_stats, _ = _run()
    monkeypatch.undo()

    def _norm(layers):
        # row_ids are fresh uuid7s per pass, so key on the business-key-bearing
        # value instead. (Learned the hard way: an un-normalised digest reported a
        # difference that was the harness's per-run nonce, not the product's.)
        return sorted((c, s, v) for _r, c, s, v in layers)

    assert _norm(fixed_before) == _norm(plain_before), "the two fixtures must match"
    assert _norm(fixed_after) == _norm(plain_after), \
        "the outbox label changed WHICH layers survived a withdrawal"
    for k in ("cells_withdrawn", "revealed", "emptied", "pinned_skipped",
              "value_unchanged", "cells_matched"):
        assert fixed_stats[k] == plain_stats[k], f"the label changed '{k}'"

    # 🔴 THE ABSOLUTE OUTCOME, not only the differential - and this half is here
    # because the differential half FAILED TO CATCH ITS OWN MUTATION. Pointing the
    # delete at `request_source` instead of the parameter breaks BOTH passes
    # equally (each deletes a source name that the fixture does not have), so the
    # two arms still agree and a purely comparative assertion stays green. A
    # differential test is blind to any mutation that moves both arms the same way.
    assert _norm(fixed_after) == [("note", "custom_script", "FROM_SCRIPT"),
                                  ("note", "custom_script", "FROM_SCRIPT"),
                                  ("note", "pipeline_parser", "FROM_PARSER"),
                                  ("part_no", "custom_script", "P1"),
                                  ("part_no", "custom_script", "P2"),
                                  ("part_no", "pipeline_parser", "P1"),
                                  ("part_no", "pipeline_parser", "P2")], \
        "the withdrawal must remove exactly the victim layer on the unpinned cell"
    assert fixed_stats["pinned_skipped"] == 1, \
        "the human pin must be honoured (and the fixture must actually exercise it)"
    assert fixed_stats["cells_withdrawn"] == 1 and fixed_stats["revealed"] == 1


def test_an_empty_row_selection_is_refused_rather_than_read_as_no_filter(rep_env):
    """🔴 EMPTY MEANS "REPLAY EVERYTHING" IF NOBODY STOPS IT, which is the opposite of the ask.

    A caller who passes a selection has decided to narrow; an empty one is a mistake
    upstream - a filter that matched nothing, a blank field - and treating it as "no filter"
    replays the whole rule. The refusal names the two ways out so the caller can pick the
    one they meant.
    """
    rule = {"name": "x", "trigger_table": "crep_test_trigger",
            "target_table": "crep_test_target"}
    with pytest.raises(chain_replay.ReplayRefused) as caught:
        chain_replay.replay_rule(rep_env, rule, apply=False, business_keys=[])
    assert "empty" in str(caught.value)
    # ...and it says what to do instead, or the operator only learns they were refused.
    assert "Omit it" in str(caught.value)


def test_a_cancel_stops_between_batches_keeps_what_it_wrote_and_can_be_resumed(rep_env):
    """🔴 THIS IS THE WHOLE REASON THE CANCEL EXISTS: 「백필만 못꺼서 서버 재기동」.

    So all four halves are asserted together, because any three of them without the fourth
    is a different, worse feature:

        stops       the loop ends at a BATCH BOUNDARY, not wherever it happened to be
        keeps       what was committed before the stop is still there - a cancel is not a
                    rollback, and treating it as one would make operators afraid to press it
        resumes     running it again finishes the rest, which is what makes stopping cheap
        survives    the call RETURNS. The process stays up and goes on to do other work -
                    the one thing killing it could never give you

    Batches are forced with `chunk_size=1` because the longest real ledger job on this box
    finishes in one batch, and a cancel has nowhere to land when there is no boundary.
    """
    _seed(rep_env, "crep_test_trigger",
          [{"src_key": "s1", "part_no": "P1", "qty": 5},
           {"src_key": "s2", "part_no": "P2", "qty": 3},
           {"src_key": "s3", "part_no": "P3", "qty": 7}])

    seen = []

    def stop_after_the_first_page(processed=None, total=None):
        seen.append(processed)
        return len(seen) > 1          # let one page through, then ask it to stop

    stopped = chain_replay.replay_rule(rep_env, RULE_RESERVE, apply=True, chunk_size=1,
                                       log=lambda *_: None,
                                       checkpoint=stop_after_the_first_page)

    assert stopped["stopped"] is True
    assert stopped["pages"] == 1, "it stopped at a boundary, not mid-page"
    # KEEPS: the first page's work is committed and visible.
    assert _target(rep_env, "P1") is not None
    # ...and the pages it never reached did not happen.
    assert _target(rep_env, "P2") is None and _target(rep_env, "P3") is None

    # RESUMES: the same job again finishes the rest, without redoing the first.
    finished = chain_replay.replay_rule(rep_env, RULE_RESERVE, apply=True,
                                        log=lambda *_: None)
    assert finished.get("stopped") is not True
    assert _target(rep_env, "P2") is not None and _target(rep_env, "P3") is not None
    assert float(_target(rep_env, "P1").reserved) == 10.0, "the resume did not disturb it"

    # SURVIVES: both calls returned - nothing was killed to make the stop happen. The
    # assertions above only ran because the process was still here to run them.
