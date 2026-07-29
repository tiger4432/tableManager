"""[Ontology slice 1 / INV-O-2] event_time_column declaration + strict key validation.

Two things are pinned here, and they are the same defect class seen from two sides:

1. **`event_time_column`** — graph edges must carry the time the event *happened*, not the
   time the row was *ingested*. Live measurement on 2026-07-29: `EXECUTED_BY` edges were off
   by up to **+89.6h** because `event_time` came from the outbox payload timestamp
   (incremental path) or the row's `updated_at` (resync path). Both answer "when was this
   loaded". Resolution happens in `extract_graph_items`, the single point both paths share,
   so the two paths cannot drift apart.

2. **Unknown keys are rejected, not ignored** — `_validate_table_mapping` used to build a
   fixed dict and silently drop everything else, so writing a new declaration into the JSON
   did *nothing*. That is why `node_class` has never had any effect. A declaration that dies
   silently is worse than one that fails loudly: the operator believes it took.

[Isolation] Table names use the `ontoet_` prefix — they cannot exist in a real user config.
conftest claims the live config at import time on a shared sqlite (see the lessons file), so a
colliding name would silently test the wrong table.
"""
import json
from datetime import datetime

import pytest

import enrichment_config
import ontology_config
import graph_materializer
from database import crud, models, schemas
from database.models import DatabaseOutbox, GraphEdge


ET_TABLES = {
    "ontoet_proc": {
        "business_key": "proc_id",
        "column_types": {
            "proc_id": "string",
            "lot": "string",
            "slot": "string",
            "eqp_id": "string",
            "start_time": "string",
            "knobs": "string",
        },
    },
}

# start_time is the real event time; the ingestion timestamp will be "now" and therefore differ.
ET_MAPPING = {
    "ontoet_proc": {
        "description": "wafer가 전공정 설비에서 단위 공정을 수행한 이벤트 로그",
        "event_time_column": "start_time",
        "node": {
            "label": "OntoetProcessEvent",
            "identity": "proc_id",
            "node_class": "dynamic",
            "props": ["eqp_id", "start_time"],
        },
        "edges": [
            {
                "type": "ONTOET_EXECUTED_BY",
                "target_label": "OntoetEqp",
                "target_identity_from": ["eqp_id"],
                "description": "이 공정 이벤트를 실행한 설비",
            },
        ],
    },
}

REAL_EVENT_TIME = "2026-07-25 08:50"


@pytest.fixture()
def et_env(db_session, tmp_path, monkeypatch):
    models.init_dynamic_models(ET_TABLES)
    crud.TABLE_CONFIG.update(ET_TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())

    mapping_path = tmp_path / "ontology_mapping.json"
    mapping_path.write_text(json.dumps(ET_MAPPING), encoding="utf-8")
    monkeypatch.setattr(ontology_config, "ONTOLOGY_PATH", str(mapping_path))

    rules_path = tmp_path / "enrichment_rules.json"
    rules_path.write_text(json.dumps({}), encoding="utf-8")
    monkeypatch.setattr(enrichment_config, "ENRICHMENT_RULES_PATH", str(rules_path))
    return db_session


def _write_mapping(tmp_path, monkeypatch, mapping):
    path = tmp_path / "mapping_variant.json"
    path.write_text(json.dumps(mapping), encoding="utf-8")
    monkeypatch.setattr(ontology_config, "ONTOLOGY_PATH", str(path))
    return ontology_config.load_ontology_mappings(
        known_tables=crud.TABLE_CONFIG, include_enrichment=False
    )


def _seed(db, rows, tx_id):
    updates = [
        schemas.GeneralUpdateItem(
            updates=dict(r), source_name="pipeline_parser", updated_by="tester",
            business_key_val=str(r["proc_id"]),
        )
        for r in rows
    ]
    crud.apply_batch_updates(db, "ontoet_proc", schemas.GeneralUpdateBatch(
        updates=updates, transaction_id=tx_id, silent=True,
    ))


def _row(proc_id="P1", start_time=REAL_EVENT_TIME, eqp="EQP-01"):
    return {"proc_id": proc_id, "lot": "LOT-A", "slot": "05",
            "eqp_id": eqp, "start_time": start_time, "knobs": '{"dose_mj": 28}'}


def _events(db):
    return db.query(DatabaseOutbox).filter(
        DatabaseOutbox.table_name == "ontoet_proc"
    ).order_by(DatabaseOutbox.id.asc()).all()


def _edge_times(db):
    return {
        e.source_row_ref: e.event_time
        for e in db.query(GraphEdge).filter(GraphEdge.type == "ONTOET_EXECUTED_BY").all()
    }


# ---------------------------------------------------------------------------
# 1) event_time_column — the correction itself
# ---------------------------------------------------------------------------

def test_incremental_uses_declared_event_time(et_env):
    """증분 경로: 엣지 event_time이 인제션 시각이 아니라 선언된 실 사건 시각이다."""
    db = et_env
    _seed(db, [_row()], "tx-inc")
    mappings = ontology_config.load_ontology_mappings(known_tables=crud.TABLE_CONFIG)
    graph_materializer.materialize_events(db, _events(db), mappings)
    db.commit()

    times = list(_edge_times(db).values())
    assert len(times) == 1
    assert times[0] == datetime.fromisoformat(REAL_EVENT_TIME)


def test_resync_uses_declared_event_time(et_env):
    """재동기화 경로도 같은 값을 산출한다 — 경로 동등성이 시간축까지 확장."""
    db = et_env
    _seed(db, [_row()], "tx-res")
    mappings = ontology_config.load_ontology_mappings(known_tables=crud.TABLE_CONFIG)
    graph_materializer.resync_table(db, "ontoet_proc", mappings)

    times = list(_edge_times(db).values())
    assert len(times) == 1
    assert times[0] == datetime.fromisoformat(REAL_EVENT_TIME)


def test_path_equivalence_incremental_vs_resync(et_env):
    """같은 로우에 대해 두 경로가 **같은** event_time을 낸다.

    선언 이전에는 증분이 outbox timestamp를, 재동기화가 updated_at을 썼으므로 서로 달랐다.
    """
    db = et_env
    _seed(db, [_row()], "tx-eq")
    mappings = ontology_config.load_ontology_mappings(known_tables=crud.TABLE_CONFIG)

    graph_materializer.materialize_events(db, _events(db), mappings)
    db.commit()
    incremental = _edge_times(db)

    graph_materializer.resync_table(db, "ontoet_proc", mappings)
    resynced = _edge_times(db)

    assert incremental == resynced
    assert set(incremental.values()) == {datetime.fromisoformat(REAL_EVENT_TIME)}


def test_undeclared_table_keeps_ingestion_time(et_env, tmp_path, monkeypatch):
    """미선언이면 현행 동작 유지 — 이 변경은 가산적이다(선언한 테이블만 바뀐다)."""
    db = et_env
    _seed(db, [_row()], "tx-undecl")

    without = json.loads(json.dumps(ET_MAPPING))
    without["ontoet_proc"].pop("event_time_column")
    mappings = _write_mapping(tmp_path, monkeypatch, without)

    graph_materializer.materialize_events(db, _events(db), mappings)
    db.commit()

    times = list(_edge_times(db).values())
    assert len(times) == 1
    # 인제션 시각이므로 실 사건 시각과 달라야 한다 — 이것이 교정 전의 결함 상태다.
    assert times[0] != datetime.fromisoformat(REAL_EVENT_TIME)


def test_unparseable_declared_value_yields_null_not_ingestion_time(et_env):
    """해석 불가 → NULL(시각 미상). 인제션 시각으로 **되돌리지 않는다**.

    되돌리면 한 필드에 '언제 일어났나'와 '언제 적재됐나'가 섞여 구분 불가해진다.
    """
    db = et_env
    _seed(db, [_row(start_time="not-a-timestamp")], "tx-bad")
    mappings = ontology_config.load_ontology_mappings(known_tables=crud.TABLE_CONFIG)
    graph_materializer.materialize_events(db, _events(db), mappings)
    db.commit()

    times = list(_edge_times(db).values())
    assert len(times) == 1
    assert times[0] is None


def test_unparseable_value_is_logged_not_silent(et_env, caplog):
    """무음 금지 — 선언은 있는데 값이 안 잡히면 운영자가 알아야 한다."""
    db = et_env
    _seed(db, [_row(start_time="")], "tx-log")
    mappings = ontology_config.load_ontology_mappings(known_tables=crud.TABLE_CONFIG)
    with caplog.at_level("WARNING", logger="GraphMaterializer"):
        graph_materializer.materialize_events(db, _events(db), mappings)
    db.commit()
    assert any("event_time_column" in r.message and "unresolved" in r.message
               for r in caplog.records)


def test_declared_column_must_exist_in_table_config(et_env, tmp_path, monkeypatch):
    """존재하지 않는 컬럼을 선언하면 그 테이블 매핑이 스킵된다(조용히 무시 금지)."""
    bad = json.loads(json.dumps(ET_MAPPING))
    bad["ontoet_proc"]["event_time_column"] = "no_such_column"
    assert "ontoet_proc" not in _write_mapping(tmp_path, monkeypatch, bad)


def test_declared_column_must_be_non_empty_string(et_env, tmp_path, monkeypatch):
    bad = json.loads(json.dumps(ET_MAPPING))
    bad["ontoet_proc"]["event_time_column"] = "   "
    assert "ontoet_proc" not in _write_mapping(tmp_path, monkeypatch, bad)


# ---------------------------------------------------------------------------
# 2) Unknown keys are rejected — the defect class, not just this slice
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("where,mutate", [
    ("table", lambda m: m["ontoet_proc"].update({"evnt_time_column": "start_time"})),
    ("node", lambda m: m["ontoet_proc"]["node"].update({"node_clas": "dynamic"})),
    ("edge", lambda m: m["ontoet_proc"]["edges"][0].update({"target_lable": "X"})),
    ("prop", lambda m: m["ontoet_proc"]["node"].update(
        {"props": [{"col": "eqp_id", "spatal": {}}]})),
    ("spatial", lambda m: m["ontoet_proc"]["node"].update(
        {"props": [{"col": "eqp_id",
                    "spatial": {"coord_system": "g", "axis": "x", "unit": "mm"}}]})),
])
def test_unknown_key_rejects_table(et_env, tmp_path, monkeypatch, where, mutate):
    """오타 한 글자가 조용한 무동작이 아니라 명시적 스킵이 된다 — 5개 층 전부."""
    bad = json.loads(json.dumps(ET_MAPPING))
    mutate(bad)
    assert "ontoet_proc" not in _write_mapping(tmp_path, monkeypatch, bad), (
        f"unknown key at {where} was silently accepted"
    )


def test_unknown_key_reason_names_the_key(et_env, tmp_path, monkeypatch, caplog):
    """스킵 사유에 문제의 키 이름이 나와야 고칠 수 있다."""
    bad = json.loads(json.dumps(ET_MAPPING))
    bad["ontoet_proc"]["node"]["node_clas"] = "dynamic"
    with caplog.at_level("WARNING", logger="OntologyConfig"):
        _write_mapping(tmp_path, monkeypatch, bad)
    assert any("node_clas" in r.message for r in caplog.records)


def test_double_underscore_keys_allowed_everywhere(et_env, tmp_path, monkeypatch):
    """주석 규약(`__`)은 어느 층에서든 통과한다 — 기존 config가 실제로 쓰는 형태."""
    ok = json.loads(json.dumps(ET_MAPPING))
    ok["ontoet_proc"]["__note"] = "table level"
    ok["ontoet_proc"]["node"]["__note"] = "node level"
    ok["ontoet_proc"]["edges"][0]["__note"] = "edge level"
    assert "ontoet_proc" in _write_mapping(tmp_path, monkeypatch, ok)


# ---------------------------------------------------------------------------
# 3) node_class — parsed and preserved, deliberately NOT enforced
# ---------------------------------------------------------------------------

def test_node_class_is_preserved(et_env):
    """스펙 §3 예시를 그대로 쓴 config가 거부되지 않고, 값이 보존된다."""
    mappings = ontology_config.load_ontology_mappings(
        known_tables=crud.TABLE_CONFIG, include_enrichment=False
    )
    assert mappings["ontoet_proc"]["node"]["node_class"] == "dynamic"


def test_node_class_vocabulary_is_closed(et_env, tmp_path, monkeypatch):
    bad = json.loads(json.dumps(ET_MAPPING))
    bad["ontoet_proc"]["node"]["node_class"] = "semi-static"
    assert "ontoet_proc" not in _write_mapping(tmp_path, monkeypatch, bad)


def test_node_class_is_optional(et_env, tmp_path, monkeypatch):
    ok = json.loads(json.dumps(ET_MAPPING))
    ok["ontoet_proc"]["node"].pop("node_class")
    mappings = _write_mapping(tmp_path, monkeypatch, ok)
    assert mappings["ontoet_proc"]["node"]["node_class"] is None


def test_node_class_does_not_change_traversal_yet(et_env):
    """정직성 고정: node_class를 선언해도 순회/물화 동작은 **바뀌지 않는다**(정책 엔진은 G2.5).

    이 테스트가 깨지는 날은 정책 엔진이 들어온 날이며, 그때 이 단언을 지우는 것이 옳다.
    """
    db = et_env
    _seed(db, [_row()], "tx-nc")
    mappings = ontology_config.load_ontology_mappings(known_tables=crud.TABLE_CONFIG)
    with_class = graph_materializer.materialize_events(db, _events(db), mappings)
    db.commit()

    stripped = json.loads(json.dumps(ET_MAPPING))
    stripped["ontoet_proc"]["node"].pop("node_class")
    m2 = ontology_config.validate_ontology_mapping(stripped, known_tables=crud.TABLE_CONFIG)
    without_class = graph_materializer.materialize_events(db, _events(db), m2)
    db.commit()

    assert with_class["nodes"] == without_class["nodes"]
    assert with_class["edges"] == without_class["edges"]
