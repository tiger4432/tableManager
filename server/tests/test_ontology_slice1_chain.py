"""[Ontology slice 1] Label separation + the knob -> process -> core -> DT -> tape chain.

Pins the two contracts the slice exists to establish:

**Identity scheme is one per label (issue #15).** `Wafer` = `wafer_id`, `Core` =
`core_lot|core_slot`, `Tape` = `tape_lot|tape_slot`. These are three disjoint value spaces;
mixing them into one label makes them un-joinable and makes defect back-tracing name the
wrong object. Measured on 2026-07-29, the live `Wafer` label held 87 composite and 16 plain
identities under one roof.

**The DT bridge is a join, not a transform.** Core frame and tape frame are connected only by
recorded correspondences in `dt_log` (spec §7.5b). There is no geometric conversion, so the
chain has to exist as edges or it does not exist at all.

INV-O-5 is pinned too: a row with no knob produces **no** edge, not an edge to a placeholder.

[Isolation] `ontos1_` prefix - cannot collide with a real user table on the shared sqlite.
"""
import json

import pytest

import enrichment_config
import ontology_config
import graph_materializer
from database import crud, models, schemas
from database.models import DatabaseOutbox, GraphNode, GraphEdge


S1_TABLES = {
    "ontos1_proc": {
        "business_key": "proc_id",
        "column_types": {"proc_id": "string", "lot": "string", "slot": "string",
                         "eqp_id": "string", "start_time": "string", "knobs": "string"},
    },
    "ontos1_dt": {
        "business_key": "dt_id",
        "column_types": {"dt_id": "string", "eventtime": "string",
                         "tape_lot": "string", "tape_slot": "string",
                         "core_lot": "string", "core_slot": "string", "dt_eqp": "string"},
    },
    "ontos1_coremap": {
        "business_key": "core_key",
        "composite_key_source": ["core_lot", "core_slot"],
        "composite_key_separator": "_",
        "column_types": {"core_key": "string", "core_lot": "string", "core_slot": "string",
                         "wafer_id": "string", "eventtime": "string"},
    },
}

S1_MAPPING = {
    "ontos1_proc": {
        "description": "wafer가 전공정 설비에서 단위 공정을 수행한 이벤트 로그",
        "event_time_column": "start_time",
        "node": {"label": "Ontos1ProcessEvent", "identity": "proc_id",
                 "props": ["eqp_id", "knobs"]},
        "edges": [
            {"type": "PERFORMED_ON", "target_label": "Ontos1Core",
             "target_identity_from": ["lot", "slot"],
             "description": "이 공정 이벤트가 수행된 대상 코어"},
            {"type": "USED_KNOB", "target_label": "Ontos1Knob",
             "target_identity_from": ["knobs"],
             "description": "이 공정 이벤트가 사용한 knob 조건"},
        ],
    },
    "ontos1_dt": {
        "description": "DT 공정 로그 — 코어 프레임과 테이프 프레임을 잇는 유일한 다리",
        "event_time_column": "eventtime",
        "node": {"label": "Ontos1DTEvent", "identity": "dt_id", "props": ["dt_eqp"]},
        "edges": [
            {"type": "ONTO_TAPE", "target_label": "Ontos1Tape",
             "target_identity_from": ["tape_lot", "tape_slot"],
             "description": "칩이 옮겨진 대상 테이프"},
            {"type": "TRANSFERRED_FROM", "target_label": "Ontos1Core",
             "target_identity_from": ["core_lot", "core_slot"],
             "description": "칩이 잘려 나온 원판 코어"},
        ],
    },
    "ontos1_coremap": {
        "description": "코어 lot/slot 표기를 실제 wafer_id로 해석한 사람 교정 결과",
        "event_time_column": "eventtime",
        "node": {"label": "Ontos1Core", "identity": ["core_lot", "core_slot"], "props": []},
        "edges": [
            {"type": "RESOLVED_AS", "target_label": "Ontos1Wafer",
             "target_identity_from": ["wafer_id"],
             "description": "이 코어의 실 wafer_id", "source_override": "user"},
        ],
    },
}

KNOB = '{"dose_mj": 28, "focus": 0.02}'


@pytest.fixture()
def s1_env(db_session, tmp_path, monkeypatch):
    models.init_dynamic_models(S1_TABLES)
    crud.TABLE_CONFIG.update(S1_TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())

    p = tmp_path / "ontology_mapping.json"
    p.write_text(json.dumps(S1_MAPPING), encoding="utf-8")
    monkeypatch.setattr(ontology_config, "ONTOLOGY_PATH", str(p))
    r = tmp_path / "enrichment_rules.json"
    r.write_text(json.dumps({}), encoding="utf-8")
    monkeypatch.setattr(enrichment_config, "ENRICHMENT_RULES_PATH", str(r))
    return db_session


def _seed(db, table, rows, tx):
    cfg = crud.TABLE_CONFIG[table]
    composite = bool(cfg.get("composite_key_source"))
    key = cfg.get("business_key")
    updates = [
        schemas.GeneralUpdateItem(
            updates=dict(r), source_name="pipeline_parser", updated_by="tester",
            business_key_val=(None if composite else str(r[key])),
        ) for r in rows
    ]
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(
        updates=updates, transaction_id=tx, silent=True))


def _materialize_all(db):
    mappings = ontology_config.load_ontology_mappings(known_tables=crud.TABLE_CONFIG)
    events = db.query(DatabaseOutbox).order_by(DatabaseOutbox.id.asc()).all()
    graph_materializer.materialize_events(db, events, mappings)
    db.commit()


def _ids(db, label):
    return {n.identity_key for n in db.query(GraphNode).filter(GraphNode.label == label)}


def _hop(db, from_label, from_ident, edge_type, to_label):
    """Follow one declared edge and return the identities reached — traversal, not SQL join."""
    src = db.query(GraphNode).filter(
        GraphNode.label == from_label, GraphNode.identity_key == from_ident).one()
    out = set()
    for e in db.query(GraphEdge).filter(GraphEdge.type == edge_type):
        for near, far in ((e.from_node, e.to_node), (e.to_node, e.from_node)):
            if near == src.id:
                n = db.query(GraphNode).get(far)
                if n is not None and n.label == to_label:
                    out.add(n.identity_key)
    return out


@pytest.fixture()
def seeded(s1_env):
    db = s1_env
    _seed(db, "ontos1_proc", [
        {"proc_id": "WP-1", "lot": "LOT-A", "slot": "05", "eqp_id": "EQP-01",
         "start_time": "2026-07-25 08:50", "knobs": KNOB},
        {"proc_id": "WP-2", "lot": "LOT-A", "slot": "05", "eqp_id": "EQP-02",
         "start_time": "2026-07-25 10:15", "knobs": KNOB},
        # no knob at all -> INV-O-5: no edge, no placeholder node
        {"proc_id": "WP-3", "lot": "LOT-B", "slot": "01", "eqp_id": "EQP-01",
         "start_time": "2026-07-25 11:00"},
    ], "tx-p")
    _seed(db, "ontos1_dt", [
        {"dt_id": "DT-1", "eventtime": "2026-07-26 10:35:13", "tape_lot": "TAPE-A",
         "tape_slot": "01", "core_lot": "LOT-A", "core_slot": "05", "dt_eqp": "DT-02"},
    ], "tx-d")
    _seed(db, "ontos1_coremap", [
        {"core_lot": "LOT-A", "core_slot": "05", "wafer_id": "WF-A-05",
         "eventtime": "2026-07-27 01:00"},
    ], "tx-c")
    _materialize_all(db)
    return db


# ---------------------------------------------------------------------------
# Identity scheme: one per label (issue #15)
# ---------------------------------------------------------------------------

def test_core_and_wafer_are_different_labels(seeded):
    """`LOT-A|05`(코어)와 `WF-A-05`(웨이퍼)가 같은 label에 공존하지 않는다."""
    cores, wafers = _ids(seeded, "Ontos1Core"), _ids(seeded, "Ontos1Wafer")
    assert cores == {"LOT-A|05", "LOT-B|01"}
    assert wafers == {"WF-A-05"}
    assert not (cores & wafers)


def test_tape_namespace_is_separate_from_core(seeded):
    """테이프는 코어와 다른 값 공간이며 다른 label이다 — 섞이면 조인 자체가 성립하지 않는다."""
    assert _ids(seeded, "Ontos1Tape") == {"TAPE-A|01"}
    assert not (_ids(seeded, "Ontos1Tape") & _ids(seeded, "Ontos1Core"))


def test_resolved_as_is_a_cross_link_not_a_self_edge(seeded):
    """Core -> Wafer 교차 링크. 한 label에 두 정체가 있으면 이건 자기 자신을 가리키는 엣지가 된다."""
    assert _hop(seeded, "Ontos1Core", "LOT-A|05", "RESOLVED_AS", "Ontos1Wafer") == {"WF-A-05"}


# ---------------------------------------------------------------------------
# INV-O-3: the chain is walkable by edges alone
# ---------------------------------------------------------------------------

def test_knob_reaches_process_history_by_traversal(seeded):
    assert _hop(seeded, "Ontos1Knob", KNOB, "USED_KNOB", "Ontos1ProcessEvent") == {"WP-1", "WP-2"}


def test_knob_reaches_dt_history_by_traversal(seeded):
    """목표 문장 그대로: knob -> 공정 -> 코어 -> DT -> 테이프가 **엣지만으로** 이어진다."""
    procs = _hop(seeded, "Ontos1Knob", KNOB, "USED_KNOB", "Ontos1ProcessEvent")
    cores = set()
    for p in procs:
        cores |= _hop(seeded, "Ontos1ProcessEvent", p, "PERFORMED_ON", "Ontos1Core")
    dts = set()
    for c in cores:
        dts |= _hop(seeded, "Ontos1Core", c, "TRANSFERRED_FROM", "Ontos1DTEvent")
    tapes = set()
    for d in dts:
        tapes |= _hop(seeded, "Ontos1DTEvent", d, "ONTO_TAPE", "Ontos1Tape")

    assert cores == {"LOT-A|05"}
    assert dts == {"DT-1"}
    assert tapes == {"TAPE-A|01"}


def test_knob_reaches_real_wafer_via_enrichment(seeded):
    """DT와 별개로, 같은 코어에서 사람 교정 결과(실 wafer_id)에도 닿는다."""
    cores = _hop(seeded, "Ontos1ProcessEvent", "WP-1", "PERFORMED_ON", "Ontos1Core")
    assert cores == {"LOT-A|05"}
    assert _hop(seeded, "Ontos1Core", "LOT-A|05", "RESOLVED_AS", "Ontos1Wafer") == {"WF-A-05"}


# ---------------------------------------------------------------------------
# INV-O-5: no guessed edges
# ---------------------------------------------------------------------------

def test_missing_knob_produces_no_edge_and_no_placeholder(seeded):
    """knob이 없는 로우는 엣지를 만들지 않는다 — '미상'을 노드로 만들면 안 된다.

    빈 값에 placeholder 노드를 세우면 '관측 안 함'과 '값이 이것임'이 구분 불가해지고,
    공장 전체 결측 수만큼의 차수를 가진 슈퍼허브가 생긴다.
    """
    db = seeded
    assert _ids(db, "Ontos1Knob") == {KNOB}
    used = db.query(GraphEdge).filter(GraphEdge.type == "USED_KNOB").all()
    assert len(used) == 2                       # WP-1, WP-2 only
    assert not any(k in _ids(db, "Ontos1Knob") for k in ("", "null", "None", "unknown"))
    # WP-3 exists as a node and keeps its other edge - it is not dropped, just not guessed at
    assert "WP-3" in _ids(db, "Ontos1ProcessEvent")
    assert _hop(db, "Ontos1ProcessEvent", "WP-3", "PERFORMED_ON", "Ontos1Core") == {"LOT-B|01"}


def test_declared_event_time_survives_the_whole_chain(seeded):
    """체인 위 모든 엣지가 인제션 시각이 아니라 실 사건 시각을 갖는다(INV-O-2 + 슬라이스 결합)."""
    from datetime import datetime
    db = seeded
    by_type = {}
    for e in db.query(GraphEdge).all():
        by_type.setdefault(e.type, []).append(e.event_time)
    assert datetime.fromisoformat("2026-07-25 08:50") in by_type["USED_KNOB"]
    assert by_type["ONTO_TAPE"] == [datetime.fromisoformat("2026-07-26 10:35:13")]
    assert by_type["RESOLVED_AS"] == [datetime.fromisoformat("2026-07-27 01:00")]
