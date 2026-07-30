"""[Ontology G1.x] The three holes that let a retired declaration keep minting.

Round context (2026-07-30). A mapping edit + a resync left the materializer loop
running the PREVIOUS declaration for 40 minutes, because the loop replaces its
in-memory copy only when a SYSTEM_RELOAD event appears in an outbox batch and
nothing published one. Behind it, two more:

  (1) `execute_manual_sync` now publishes SYSTEM_RELOAD. "I applied a config and
      resynced" must not be able to leave the loop stale.
  (2) the orphan sweep runs on the auto-update scheduler tick, per label, with its
      budget guard intact - because `_retarget_stale_edges` deletes edges and
      nothing deletes the node an edge left behind, so every identity edit leaks
      a node (live: 12,761 degree-zero nodes).
  (3) `/graph/mapping-summary` reports REJECTED mappings and why. The loader's
      contract is "log and skip", so renaming a column used to delete a table's
      ontology wholesale with one log line and no number on any surface.

[격리] 테이블/라벨 이름은 사용자 실 config에 실존 불가능한 sweep_test_/Sweep 접두를
쓴다 (conftest가 import 시점에 실 config를 선점하는 공유 sqlite 함정 — 교훈 파일).
"""
import asyncio
import json
import logging

import pytest
from sqlalchemy.orm import sessionmaker

import enrichment_config
import graph_orphans
import graph_sync_worker
import ontology_config
from database import crud, models
from database.models import DatabaseOutbox, GraphEdge, GraphNode

SWEEP_TABLES = {
    "sweep_test_bonding": {
        "business_key": "log_id",
        "column_types": {
            "log_id": "string",
            "core_lot": "string",
            "core_slot": "string",
            "base_id": "string",
        },
    },
}

MAPPING = {
    "sweep_test_bonding": {
        "description": "본딩 로그 — 스윕 검증용 픽스처",
        "node": {"label": "SweepCell", "identity": "log_id", "node_class": "dynamic"},
        "edges": [
            {
                "type": "FROM_CORE",
                "target_label": "SweepCore",
                "target_identity_from": ["core_lot", "core_slot"],
                "description": "이 셀이 속한 코어",
            },
        ],
    },
}


@pytest.fixture()
def onto_files(tmp_path, monkeypatch):
    """매핑/enrichment 선언 파일을 격리 경로로 갈아끼운다.

    enrichment 경로까지 반드시 갈아끼운다 — 안 하면 로더가 **사용자의 실 규칙 파일**을
    읽어 테스트가 그 파일 상태에 따라 흔들린다(그리고 rejected 목록에 실 사이트의
    사유가 섞여 들어온다).
    """
    mapping_path = tmp_path / "ontology_mapping.json"
    mapping_path.write_text(json.dumps(MAPPING), encoding="utf-8")
    monkeypatch.setattr(ontology_config, "ONTOLOGY_PATH", str(mapping_path))

    rules_path = tmp_path / "enrichment_rules.json"
    rules_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(enrichment_config, "ENRICHMENT_RULES_PATH", str(rules_path))

    def rewrite(mapping_obj):
        mapping_path.write_text(json.dumps(mapping_obj), encoding="utf-8")

    return rewrite


@pytest.fixture()
def sweep_env(db_session, onto_files, monkeypatch):
    """스윕 대상 동적 테이블 + 그래프 테이블을 같은 in-memory DB에 올린다."""
    models.init_dynamic_models(SWEEP_TABLES)
    crud.TABLE_CONFIG.update(SWEEP_TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())

    # run_scheduled / publish_system_reload은 자기 세션을 연다 — 테스트 DB로 향하게 한다.
    import database.database as dbmod
    bind = db_session.get_bind()
    monkeypatch.setattr(dbmod, "SessionLocal", sessionmaker(bind=bind))
    monkeypatch.setattr(dbmod, "engine", bind)
    return db_session


def _node(db, label, identity_key, props=None):
    n = GraphNode(label=label, identity_key=identity_key, props=props or {})
    db.add(n)
    db.flush()
    return n


def _edge(db, from_n, to_n, edge_type="FROM_CORE"):
    e = GraphEdge(type=edge_type, from_node=from_n.id, to_node=to_n.id,
                  source_name="pipeline_parser")
    db.add(e)
    db.flush()
    return e


def _row(db, log_id, core_lot="LOT-A", core_slot="05", base_id="BASE-01"):
    model = models.DYNAMIC_TABLES["sweep_test_bonding"]
    r = model(row_id=f"row_{log_id}", business_key_val=log_id, log_id=log_id,
              core_lot=core_lot, core_slot=core_slot, base_id=base_id)
    db.add(r)
    db.flush()
    return r


def _mappings():
    return ontology_config.load_ontology_mappings(known_tables=crud.TABLE_CONFIG)


def _labels_present(db):
    return sorted({label for (label,) in db.query(GraphNode.label).distinct().all()})


# ---------------------------------------------------------------------------
# 1) orphan definition - producibility is the safety condition
# ---------------------------------------------------------------------------

def test_a_producible_node_with_zero_edges_is_not_an_orphan(sweep_env):
    """"Zero edges" alone is NOT an orphan. The DOE vocabulary lives on this."""
    db = sweep_env
    _row(db, "LOG1")
    _node(db, "SweepCell", "LOG1")          # producible by sweep_test_bonding
    _node(db, "SweepCore", "LOT-A|05")      # producible as an edge target (stub)
    db.commit()

    orphans, _ = graph_orphans.find_orphans(db, _mappings())
    assert orphans == [], (
        "a node the mapping can still mint was reported as an orphan — the edge "
        "target stub path is the one that gets forgotten"
    )


def test_a_node_no_mapping_can_produce_is_an_orphan(sweep_env):
    db = sweep_env
    _row(db, "LOG1")
    _node(db, "SweepCell", "LOG1")
    _node(db, "SweepRetired", "GONE-1")
    db.commit()

    orphans, _ = graph_orphans.find_orphans(db, _mappings())
    assert [(label, ident) for _, label, ident in orphans] == [("SweepRetired", "GONE-1")]


def test_a_node_with_an_edge_is_never_a_candidate(sweep_env):
    """Even an unproducible node is left alone while something points at it."""
    db = sweep_env
    a = _node(db, "SweepRetired", "GONE-1")
    b = _node(db, "SweepRetired", "GONE-2")
    _edge(db, a, b)
    db.commit()

    orphans, _ = graph_orphans.find_orphans(db, _mappings())
    assert orphans == []


# ---------------------------------------------------------------------------
# 2) budget guard - per label, and it still refuses
# ---------------------------------------------------------------------------

def test_guard_declines_a_label_it_would_empty(sweep_env):
    """The live first run refused because Chip was 100% of its label. Still does."""
    db = sweep_env
    for i in range(20):
        _node(db, "SweepRetired", f"GONE-{i}")
    db.commit()

    plan = graph_orphans.plan_sweep(db, _mappings())
    assert "SweepRetired" in plan["declined"]
    assert plan["declined"]["SweepRetired"]["fraction"] == 1.0
    assert plan["delete_ids"] == [], "a declined label must contribute nothing to the delete set"
    assert plan["sweepable"] == {}


def test_guard_declines_one_label_and_sweeps_another_in_the_same_run(sweep_env):
    """All-or-nothing would let 12,468 retired Chip nodes hold the per-edit leak hostage."""
    db = sweep_env
    for i in range(20):
        _node(db, "SweepRetired", f"GONE-{i}")            # 20/20 = 100% -> declined
    for i in range(20):                                    # 2/20 = 10%  -> swept
        n = _node(db, "SweepCell", f"LOG{i}")
        if i >= 2:
            _row(db, f"LOG{i}")
        if i >= 2:
            _edge(db, n, n)
    db.commit()

    plan = graph_orphans.plan_sweep(db, _mappings())
    assert sorted(plan["declined"]) == ["SweepRetired"]
    assert sorted(plan["sweepable"]) == ["SweepCell"]
    assert len(plan["delete_ids"]) == 2

    deleted = graph_orphans.apply_sweep(db, plan)
    assert deleted == 2
    assert db.query(GraphNode).filter(GraphNode.label == "SweepRetired").count() == 20, \
        "the declined label was deleted anyway"


def test_small_label_is_exempt_from_the_fraction_test(sweep_env):
    """A 3-node label is 100% of itself; the fraction test says nothing there."""
    db = sweep_env
    for i in range(3):
        _node(db, "SweepTiny", f"T-{i}")
    db.commit()

    plan = graph_orphans.plan_sweep(db, _mappings())
    assert plan["declined"] == {}
    assert len(plan["delete_ids"]) == 3

    strict = graph_orphans.plan_sweep(db, _mappings(), min_population=1)
    assert "SweepTiny" in strict["declined"], "min_population must be the only exemption"


def test_max_fraction_override_lets_a_retired_label_go(sweep_env):
    db = sweep_env
    for i in range(20):
        _node(db, "SweepRetired", f"GONE-{i}")
    db.commit()

    plan = graph_orphans.plan_sweep(db, _mappings(), max_fraction=1.0)
    assert plan["declined"] == {}
    assert len(plan["delete_ids"]) == 20


# ---------------------------------------------------------------------------
# 3) the log line - a sweep whose skipped set is invisible reads as "nothing to do"
# ---------------------------------------------------------------------------

def test_summary_names_both_what_it_took_and_what_it_declined(sweep_env):
    db = sweep_env
    for i in range(20):
        _node(db, "SweepRetired", f"GONE-{i}")
    for i in range(3):
        _node(db, "SweepTiny", f"T-{i}")
    db.commit()

    line = graph_orphans.format_plan_summary(graph_orphans.plan_sweep(db, _mappings()))
    assert "SweepTiny=3/3" in line
    assert "DECLINED" in line and "SweepRetired=20/20(100%)" in line


def test_summary_of_a_refusal_says_refused_and_why(sweep_env):
    line = graph_orphans.format_plan_summary(None, blockers=["mapping 'x' was rejected: y"])
    assert line.startswith("[GraphOrphans] REFUSED")
    assert "mapping 'x' was rejected: y" in line


# ---------------------------------------------------------------------------
# 4) the compound failure: a rejected mapping must disqualify the whole judgement
# ---------------------------------------------------------------------------

def test_a_rejected_mapping_blocks_the_scheduled_sweep(sweep_env, onto_files, caplog):
    """A renamed column silently drops a table's mapping (that is the loader's
    documented contract). Every label that table produced then looks unproducible.
    The fraction guard catches the big labels; it does NOT catch a label under
    min_population - so the declaration itself has to be the gate.

    Defect injection: deleting the `declaration_blockers` check from run_scheduled
    makes this test delete SweepCell and fail on the count below.
    """
    db = sweep_env
    for i in range(3):                       # small label: exempt from the fraction guard
        _node(db, "SweepCell", f"LOG{i}")
        _row(db, f"LOG{i}")
    db.commit()

    broken = json.loads(json.dumps(MAPPING))
    broken["sweep_test_bonding"]["node"]["identity"] = "log_id_renamed"
    onto_files(broken)

    with caplog.at_level(logging.ERROR):
        out = graph_orphans.run_scheduled(known_tables=crud.TABLE_CONFIG)

    assert out["status"] == "refused"
    assert out["applied"] is None
    assert any("log_id_renamed" in b for b in out["blockers"]), out["blockers"]
    assert db.query(GraphNode).filter(GraphNode.label == "SweepCell").count() == 3, \
        "a rejected mapping made producible nodes look unproducible and they were swept"
    assert "REFUSED" in caplog.text


def test_an_empty_declaration_blocks_the_sweep(sweep_env, onto_files):
    db = sweep_env
    _node(db, "SweepCell", "LOG1")
    db.commit()
    onto_files({})

    out = graph_orphans.run_scheduled(known_tables=crud.TABLE_CONFIG)
    assert out["status"] == "refused"
    assert db.query(GraphNode).count() == 1


def test_a_clean_declaration_does_not_block(sweep_env):
    mappings, rejections = graph_orphans.load_declaration(crud.TABLE_CONFIG)
    assert rejections == [], rejections
    assert graph_orphans.declaration_blockers(mappings, rejections) == []


# ---------------------------------------------------------------------------
# 5) the scheduled entry point
# ---------------------------------------------------------------------------

def test_scheduled_run_applies_and_logs_both_sets(sweep_env, caplog):
    db = sweep_env
    for i in range(20):
        _node(db, "SweepRetired", f"GONE-{i}")
    for i in range(3):
        _node(db, "SweepTiny", f"T-{i}")
    db.commit()

    with caplog.at_level(logging.INFO):
        out = graph_orphans.run_scheduled(known_tables=crud.TABLE_CONFIG)

    assert out["status"] == "ok"
    assert out["applied"] == 3
    assert _labels_present(db) == ["SweepRetired"]
    assert "SweepTiny=3/3" in caplog.text
    assert "DECLINED" in caplog.text and "SweepRetired" in caplog.text


def test_scheduled_run_logs_even_when_there_is_nothing_to_do(sweep_env, caplog):
    with caplog.at_level(logging.INFO):
        out = graph_orphans.run_scheduled(known_tables=crud.TABLE_CONFIG)
    assert out["status"] == "ok"
    assert out["applied"] == 0
    assert "[GraphOrphans]" in caplog.text, "a silent cycle is indistinguishable from a dead one"


def test_off_switch_stops_the_sweep(sweep_env, monkeypatch):
    db = sweep_env
    for i in range(3):
        _node(db, "SweepTiny", f"T-{i}")
    db.commit()

    monkeypatch.setenv(graph_orphans.ENABLE_ENV, "false")
    out = graph_orphans.run_scheduled(known_tables=crud.TABLE_CONFIG)
    assert out["status"] == "disabled"
    assert db.query(GraphNode).count() == 3


def test_due_runs_on_the_first_tick_then_waits_the_interval():
    assert graph_orphans.due(0.0, 10.0) is True
    assert graph_orphans.due(10.0, 10.0 + 5) is False
    assert graph_orphans.due(10.0, 10.0 + graph_orphans.SWEEP_INTERVAL_SEC) is True


def test_scheduler_tick_sweeps_once_per_interval(monkeypatch, tmp_path):
    """The 5 s tick must not turn the sweep into a hot loop."""
    import run_auto_update

    calls = []
    monkeypatch.setattr(graph_orphans, "run_scheduled",
                        lambda *a, **k: calls.append(1) or {"status": "ok"})
    sched = run_auto_update.MultiDiscoveryScheduler(server_dir=str(tmp_path))

    sched.maybe_sweep_graph_orphans()
    for _ in range(5):
        sched.maybe_sweep_graph_orphans()
    assert len(calls) == 1

    # the check throttle expired, but the sweep interval has not
    sched._last_orphan_check = 0.0
    sched.maybe_sweep_graph_orphans()
    assert len(calls) == 1

    sched._last_orphan_check = 0.0
    sched._last_orphan_sweep -= graph_orphans.SWEEP_INTERVAL_SEC
    sched.maybe_sweep_graph_orphans()
    assert len(calls) == 2


def test_scheduler_tick_survives_a_raising_sweep(monkeypatch, tmp_path):
    import run_auto_update

    def boom(*a, **k):
        raise RuntimeError("graph unreachable")

    monkeypatch.setattr(graph_orphans, "run_scheduled", boom)
    sched = run_auto_update.MultiDiscoveryScheduler(server_dir=str(tmp_path))
    assert sched.maybe_sweep_graph_orphans() is None  # logged, not raised


# ---------------------------------------------------------------------------
# 6) item (1) - a resync announces the declaration it just used
# ---------------------------------------------------------------------------

def _reload_events(db):
    return db.query(DatabaseOutbox).filter(
        DatabaseOutbox.event_type == "SYSTEM_RELOAD"
    ).all()


def test_publish_system_reload_writes_one_outbox_row(sweep_env):
    db = sweep_env
    assert graph_sync_worker.publish_system_reload("unit test") is True

    events = _reload_events(db)
    assert len(events) == 1
    assert events[0].table_name == "system"
    payload = events[0].safe_payload or {}
    assert payload.get("trigger") == "graph_resync"
    assert "unit test" in payload.get("msg", "")


def test_resync_publishes_the_reload(sweep_env, monkeypatch):
    """Defect injection: remove the `_announce` call after the resync and this fails.

    This is the sequence that bit us on live - mapping edited, resync run, and the
    materializer loop kept the previous declaration because nothing told it.
    """
    db = sweep_env
    _row(db, "LOG1")
    db.commit()

    asyncio.run(graph_sync_worker.execute_manual_sync("sweep_test_bonding", []))

    assert len(_reload_events(db)) == 1
    assert db.query(GraphNode).filter(GraphNode.label == "SweepCell").count() == 1


def test_resync_of_an_unmapped_table_still_publishes(sweep_env):
    """Deleting a table's mapping and resyncing it lands here, and it is the same
    staleness: the loop would keep minting the declaration that was removed."""
    db = sweep_env
    res = asyncio.run(graph_sync_worker.execute_manual_sync("raw_table_1", []))
    assert res["mode"] == "no_mapping"
    assert len(_reload_events(db)) == 1


def test_resync_of_an_unknown_table_publishes_nothing(sweep_env):
    from fastapi import HTTPException

    db = sweep_env
    with pytest.raises(HTTPException):
        asyncio.run(graph_sync_worker.execute_manual_sync("no_such_table_at_all", []))
    assert _reload_events(db) == [], \
        "a rejected request read nothing into effect and must announce nothing"


def test_reload_entry_point_rereads_the_file_from_disk(sweep_env, onto_files, monkeypatch):
    """The other half of item (1): what the loop does when it sees that row.

    The loop's own branch is one line (`any(e.event_type == "SYSTEM_RELOAD" ...)`)
    inside a closure; this covers the function that branch calls, and the live
    drill covers the two together.

    `_reload_graph_worker_configs` also re-reads table_config from disk (issue #7's
    shared entry point), which would drop this fixture's synthetic table — pin that
    half so the assertion is about the ontology reload and nothing else.
    """
    monkeypatch.setattr(crud, "load_table_config", lambda *a, **k: dict(SWEEP_TABLES))

    before = graph_sync_worker._load_graph_mappings()
    assert before["sweep_test_bonding"]["node"]["label"] == "SweepCell"

    renamed = json.loads(json.dumps(MAPPING))
    renamed["sweep_test_bonding"]["node"]["label"] = "SweepCellV2"
    onto_files(renamed)

    after = graph_sync_worker._reload_graph_worker_configs()
    assert after["sweep_test_bonding"]["node"]["label"] == "SweepCellV2"


# ---------------------------------------------------------------------------
# 7) item (3) - rejected mappings are on a surface, not only in a log
# ---------------------------------------------------------------------------

def test_mapping_summary_lists_the_loaded_tables(client, sweep_env):
    body = client.get("/graph/mapping-summary").json()
    entry = next(t for t in body["tables"] if t["table"] == "sweep_test_bonding")
    assert entry == {
        "table": "sweep_test_bonding",
        "node_label": "SweepCell",
        "identity_columns": ["log_id"],
    }
    assert body["rejected"] == [] and body["rejected_count"] == 0, \
        "a healthy file must report NO rejections, or the list gets ignored"
    assert body["source"]["exists"] is True


def test_mapping_summary_reports_a_renamed_column_with_its_reason(client, sweep_env, onto_files):
    """The exact silent failure: `ontology_config` logs and skips, and the success
    count merely stops growing."""
    broken = json.loads(json.dumps(MAPPING))
    broken["sweep_test_bonding"]["edges"][0]["target_identity_from"] = ["core_lot", "slot_renamed"]
    onto_files(broken)

    body = client.get("/graph/mapping-summary").json()
    assert all(t["table"] != "sweep_test_bonding" for t in body["tables"])
    assert body["rejected_count"] == 1
    r = body["rejected"][0]
    assert r["scope"] == "table" and r["table"] == "sweep_test_bonding"
    assert "slot_renamed" in r["reason"]


def test_mapping_summary_reports_an_unreadable_file(client, sweep_env, tmp_path, monkeypatch):
    bad = tmp_path / "broken.json"
    bad.write_text("{ this is not json", encoding="utf-8")
    monkeypatch.setattr(ontology_config, "ONTOLOGY_PATH", str(bad))

    body = client.get("/graph/mapping-summary").json()
    assert body["tables"] == []
    assert [r["scope"] for r in body["rejected"]] == ["file"]
    assert "could not read" in body["rejected"][0]["reason"]


def test_mapping_summary_reports_a_v1_format_file(client, sweep_env, onto_files):
    """A v1 file yields zero v2 mappings — identical to an empty file on a surface
    that only counts successes."""
    onto_files({"default": {"node_label": "Row"}, "tables": {"x": {"node_label": "X"}}})

    body = client.get("/graph/mapping-summary").json()
    assert body["tables"] == []
    assert body["rejected_count"] == 2
    assert {r["table"] for r in body["rejected"]} == {"default", "tables"}


def test_mapping_summary_reports_a_missing_file_as_absence_not_rejection(
        client, sweep_env, tmp_path, monkeypatch):
    monkeypatch.setattr(ontology_config, "ONTOLOGY_PATH", str(tmp_path / "nope.json"))
    body = client.get("/graph/mapping-summary").json()
    assert body["source"]["exists"] is False
    assert body["rejected"] == [], "'nothing declared' is not 'declared and refused'"


def test_the_loader_without_a_collector_is_unchanged(sweep_env, onto_files):
    """Every other caller passes no collector and must keep its exact behaviour."""
    broken = json.loads(json.dumps(MAPPING))
    del broken["sweep_test_bonding"]["description"]
    onto_files(broken)

    mappings = ontology_config.load_ontology_mappings(
        known_tables=crud.TABLE_CONFIG, include_enrichment=False
    )
    assert mappings == {}
