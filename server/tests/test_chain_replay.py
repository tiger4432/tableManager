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
