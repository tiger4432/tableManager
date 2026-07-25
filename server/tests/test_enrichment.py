"""Enrichment Queue 서버측 구현 검증 (docs/spec/ENRICHMENT_QUEUE_SPEC.md).

검증 범위:
- 규칙 로더/검증기 (enrichment_config)
- dedup mapper — 신규 키 insert / 기존 키 target 보존 / 증분·멱등 / blank 키 스킵
  (체인 워커 실경로 process_chain_transaction_group을 통해 E2E로 검증 — 배선 포함)
- 신규 API 2종 — 응답 형태(경계 계약)·params 검증·LIMIT 강제·404/400
- 기존 blank 필터 + 배치 업서트 경로가 파생 테이블에서 무변경으로 동작(#재사용 계약)
"""
import json
import uuid

import anyio
import pytest

import enrichment_config
from database import crud, models, schemas

# ---------------------------------------------------------------------------
# 테스트 픽스처: 파생/원본 테이블 + 규칙 파일
#
# [격리] 테이블명은 반드시 사용자 실 config(table_config.json)에 실존 불가능한 이름이어야
# 한다. conftest가 import 시점에 실 config로 init_dynamic_models를 수행하므로, 실존
# 테이블명(예: bonding_log)과 겹치면 공유 in-memory sqlite(StaticPool)에 실 스키마가
# 선점되어 create_all(checkfirst)이 스킵된다 → "no such column" 격리 실패.
# ---------------------------------------------------------------------------

ENRICH_TABLES = {
    "enrich_test_src": {
        "business_key": "log_key",
        "composite_key_source": ["equipment", "event_time", "chip_id"],
        "composite_key_separator": "_",
        "column_types": {
            "log_key": "string",
            "equipment": "string",
            "event_time": "string",
            "chip_id": "string",
            "lot_hint": "string",
        },
    },
    "enrich_test_derived": {
        "business_key": "job_id",
        "composite_key_source": ["equipment", "event_time"],
        "composite_key_separator": "_",
        "column_types": {
            "job_id": "string",
            "equipment": "string",
            "event_time": "string",
            "wafer_id": "string",
            "chip_count": "number",
            "lot_hint": "string",
        },
    },
}

RULES_FILE = {
    "bonding_wafer_attribution": {
        "source_table": "enrich_test_src",
        "derived_table": "enrich_test_derived",
        "decision_key": ["equipment", "event_time"],
        "target_fields": ["wafer_id"],
        "list_columns": ["chip_count", "lot_hint"],
        "aggregations": {"chip_count": "count"},
        "reference_views": [
            {
                "label": "chips on equipment",
                "query": "SELECT chip_id, lot_hint FROM enrich_test_src WHERE equipment = :equipment ORDER BY chip_id",
                "limit": 2,
            }
        ],
    }
}


@pytest.fixture()
def enrich_env(db_session, tmp_path, monkeypatch):
    """conftest의 기본 테이블에 enrichment용 원본/파생 테이블과 규칙 파일을 추가한다."""
    models.init_dynamic_models(ENRICH_TABLES)
    crud.TABLE_CONFIG.update(ENRICH_TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())

    rules_path = tmp_path / "enrichment_rules.json"
    rules_path.write_text(json.dumps(RULES_FILE), encoding="utf-8")
    monkeypatch.setattr(enrichment_config, "ENRICHMENT_RULES_PATH", str(rules_path))

    import main
    main.TABLE_COUNT_CACHE.clear()
    return db_session


def _seed_source(db, rows, tx_id, source_name="pipeline_parser"):
    """원본(enrich_test_src)에 행을 인제션한다 — outbox 이벤트가 자동 적재된다."""
    updates = [
        schemas.GeneralUpdateItem(updates=dict(row), source_name=source_name, updated_by="watcher")
        for row in rows
    ]
    batch = schemas.GeneralUpdateBatch(updates=updates, transaction_id=tx_id, silent=True)
    crud.apply_batch_updates(db, "enrich_test_src", batch)


def _run_chain_for_tx(db, tx_id):
    """체인 워커 실경로(process_chain_transaction_group)로 해당 tx의 outbox 이벤트를 처리한다."""
    from chain_ingestion_worker import process_chain_transaction_group
    from database.models import DatabaseOutbox

    rules = enrichment_config.load_enrichment_chain_rules(known_tables=crud.TABLE_CONFIG)
    assert rules, "enrichment chain rules must be synthesized"

    events = db.query(DatabaseOutbox).filter(
        DatabaseOutbox.table_name == "enrich_test_src",
        DatabaseOutbox.processed_chain == False,  # noqa: E712
    ).order_by(DatabaseOutbox.id.asc()).all()
    evs = [e for e in events if (e.payload or {}).get("transaction_id") == tx_id]
    assert evs, f"no pending outbox events for tx {tx_id}"

    async def run():
        ok, err, msgs = await process_chain_transaction_group(tx_id, evs, db, rules)
        assert ok, f"chain group failed: {err}"
        for e in evs:
            e.processed_chain = True
        db.commit()
        return msgs

    return anyio.run(run)


def _derived_rows(db):
    model = models.DYNAMIC_TABLES["enrich_test_derived"]
    return db.query(model).order_by(model.business_key_val.asc()).all()


# ---------------------------------------------------------------------------
# 1. 규칙 로더 / 검증기
# ---------------------------------------------------------------------------

KNOWN = ENRICH_TABLES


def _base_rule(**overrides):
    rule = {
        "source_table": "enrich_test_src",
        "derived_table": "enrich_test_derived",
        "decision_key": ["equipment", "event_time"],
        "target_fields": ["wafer_id"],
        "list_columns": ["chip_count", "lot_hint"],
        "aggregations": {"chip_count": "count"},
        "reference_views": [],
    }
    rule.update(overrides)
    return rule


def test_loader_valid_rule_normalized():
    raw = {"r1": _base_rule(reference_views=[
        {"label": "v1", "query": "SELECT chip_id FROM enrich_test_src WHERE equipment = :equipment"},
        {"label": "v2", "query": "SELECT chip_id FROM enrich_test_src", "limit": 5000},
    ])}
    rules = enrichment_config.validate_enrichment_rules(raw, known_tables=KNOWN)
    assert len(rules) == 1
    r = rules[0]
    assert r["name"] == "r1"
    assert r["decision_key"] == ["equipment", "event_time"]
    assert r["aggregations"] == {"chip_count": "count"}
    # LIMIT 기본값 200 + 상한 1000 클램프
    assert r["reference_views"][0]["limit"] == enrichment_config.DEFAULT_REFERENCE_LIMIT
    assert r["reference_views"][1]["limit"] == enrichment_config.MAX_REFERENCE_LIMIT


def test_loader_missing_required_fields_skipped():
    raw = {
        "no_derived": {k: v for k, v in _base_rule().items() if k != "derived_table"},
        "no_key": _base_rule(decision_key=[]),
        "no_target": _base_rule(target_fields=[]),
    }
    assert enrichment_config.validate_enrichment_rules(raw, known_tables=KNOWN) == []


def test_loader_decision_target_overlap_skipped():
    raw = {"r": _base_rule(target_fields=["equipment"])}
    assert enrichment_config.validate_enrichment_rules(raw, known_tables=KNOWN) == []


def test_loader_unknown_tables_or_columns_skipped():
    assert enrichment_config.validate_enrichment_rules(
        {"r": _base_rule(source_table="nope")}, known_tables=KNOWN) == []
    assert enrichment_config.validate_enrichment_rules(
        {"r": _base_rule(derived_table="nope")}, known_tables=KNOWN) == []
    assert enrichment_config.validate_enrichment_rules(
        {"r": _base_rule(decision_key=["equipment", "ghost_col"])}, known_tables=KNOWN) == []
    assert enrichment_config.validate_enrichment_rules(
        {"r": _base_rule(target_fields=["ghost_col"])}, known_tables=KNOWN) == []


def test_loader_derived_key_contract_enforced():
    """파생 테이블 키 계약: composite_key_source ⊆ decision_key 또는 business_key ∈ decision_key."""
    bad_known = {
        "enrich_test_src": ENRICH_TABLES["enrich_test_src"],
        # composite가 decision_key 밖의 컬럼을 포함 → 규칙 스킵
        "enrich_test_derived": {
            "business_key": "job_id",
            "composite_key_source": ["equipment", "wafer_id"],
            "column_types": ENRICH_TABLES["enrich_test_derived"]["column_types"],
        },
    }
    assert enrichment_config.validate_enrichment_rules({"r": _base_rule()}, known_tables=bad_known) == []


def test_loader_reference_view_safety():
    views = [
        {"label": "bad_insert", "query": "INSERT INTO enrich_test_src VALUES (1)"},
        {"label": "bad_multi", "query": "SELECT 1; DROP TABLE enrich_test_src"},
        {"label": "bad_bind", "query": "SELECT 1 FROM enrich_test_src WHERE chip_id = :chip_id"},
        {"label": "bad_ref", "query_ref": "../evil"},
        {"label": "good", "query": "SELECT chip_id FROM enrich_test_src WHERE equipment = :equipment"},
    ]
    rules = enrichment_config.validate_enrichment_rules(
        {"r": _base_rule(reference_views=views)}, known_tables=KNOWN)
    assert len(rules) == 1
    # 무효 뷰는 로드 시점에 제거되어 /rules 목록과 /references 인덱스가 항상 정합
    labels = [v["label"] for v in rules[0]["reference_views"]]
    assert labels == ["good"]


def test_loader_disabled_rule_and_missing_file(tmp_path):
    raw = {"r": _base_rule(enabled=False)}
    assert enrichment_config.validate_enrichment_rules(raw, known_tables=KNOWN) == []
    # 파일 없음 → 빈 목록 (오류 아님)
    assert enrichment_config.load_enrichment_rules(path=str(tmp_path / "none.json")) == []


def test_loader_synthesized_chain_rule_shape(tmp_path):
    rules_path = tmp_path / "enrichment_rules.json"
    rules_path.write_text(json.dumps(RULES_FILE), encoding="utf-8")
    chain_rules = enrichment_config.load_enrichment_chain_rules(
        path=str(rules_path), known_tables=KNOWN)
    assert len(chain_rules) == 1
    cr = chain_rules[0]
    assert cr["trigger_table"] == "enrich_test_src"
    assert cr["target_table"] == "enrich_test_derived"
    assert cr["mapper_module"] == "enrichment_mapper"
    assert cr["mapper_function"] == "map_enrichment_dedup"
    assert cr["is_batch"] is True and cr["enabled"] is True
    assert cr["enrichment"]["name"] == "bonding_wafer_attribution"


# ---------------------------------------------------------------------------
# 2. dedup mapper (체인 워커 실경로 E2E)
# ---------------------------------------------------------------------------

def test_dedup_new_keys_inserted(enrich_env):
    db = enrich_env
    tx = f"tx_{uuid.uuid4().hex[:8]}"
    _seed_source(db, [
        {"equipment": "EQP1", "event_time": "T1", "chip_id": "C1", "lot_hint": "LOT_A"},
        {"equipment": "EQP1", "event_time": "T1", "chip_id": "C2", "lot_hint": "LOT_A"},
        {"equipment": "EQP1", "event_time": "T1", "chip_id": "C3"},
        {"equipment": "EQP2", "event_time": "T2", "chip_id": "C4", "lot_hint": "LOT_B"},
        {"equipment": "EQP2", "event_time": "T2", "chip_id": "C5", "lot_hint": "LOT_B"},
    ], tx)
    _run_chain_for_tx(db, tx)

    rows = _derived_rows(db)
    assert len(rows) == 2, "유니크 판단키당 정확히 1행"
    r1, r2 = rows
    assert r1.business_key_val == "EQP1_T1" and r2.business_key_val == "EQP2_T2"
    assert r1.job_id == "EQP1_T1"
    assert r1.equipment == "EQP1" and r1.event_time == "T1"
    assert r1.chip_count == 3 and r2.chip_count == 2
    assert r1.lot_hint == "LOT_A" and r2.lot_hint == "LOT_B"
    # 신규 키의 target은 미설정(NULL) — 결손 상태로 워크리스트에 잡힌다
    assert r1.wafer_id is None and r2.wafer_id is None


def test_dedup_preserves_user_target_on_reingestion(enrich_env):
    db = enrich_env
    tx1 = f"tx_{uuid.uuid4().hex[:8]}"
    _seed_source(db, [
        {"equipment": "EQP1", "event_time": "T1", "chip_id": "C1"},
        {"equipment": "EQP1", "event_time": "T1", "chip_id": "C2"},
    ], tx1)
    _run_chain_for_tx(db, tx1)

    # 사람이 target(wafer_id)을 채운다 — source=user(priority 0)
    row = _derived_rows(db)[0]
    crud.apply_batch_updates(db, "enrich_test_derived", schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(row_id=row.row_id, updates={"wafer_id": "W123"},
                                  source_name="user", updated_by="tester")
    ], silent=True))

    # 같은 판단키로 추가 인제션 → 기존 키: 집계(chip_count)만 갱신, 사람값은 절대 덮지 않음
    tx2 = f"tx_{uuid.uuid4().hex[:8]}"
    _seed_source(db, [
        {"equipment": "EQP1", "event_time": "T1", "chip_id": "C3"},
        {"equipment": "EQP1", "event_time": "T1", "chip_id": "C4"},
    ], tx2)
    _run_chain_for_tx(db, tx2)

    rows = _derived_rows(db)
    assert len(rows) == 1
    assert rows[0].wafer_id == "W123", "재인제션이 사람이 채운 target을 덮으면 안 된다"
    assert rows[0].chip_count == 4, "기존 키는 집계 메타만 갱신"
    # 레이어링 2차 방어 확인: chain_ingestion 소스가 wafer_id 셀에 아예 기록되지 않았다(1차 방어)
    src = db.query(models.CellSource).filter(
        models.CellSource.table_name == "enrich_test_derived",
        models.CellSource.row_id == rows[0].row_id,
        models.CellSource.column_name == "wafer_id",
        models.CellSource.source_name == "chain_ingestion",
    ).first()
    assert src is None, "mapper는 target_fields를 updates에 포함하지 않아야 한다"


def test_dedup_idempotent_reingestion(enrich_env):
    """동일 원본 재인제션(EDIT 이벤트)에도 count가 이중 가산되지 않는다(영향 키 한정 재계산)."""
    db = enrich_env
    rows = [
        {"equipment": "EQP1", "event_time": "T1", "chip_id": "C1"},
        {"equipment": "EQP1", "event_time": "T1", "chip_id": "C2"},
    ]
    tx1 = f"tx_{uuid.uuid4().hex[:8]}"
    _seed_source(db, rows, tx1)
    _run_chain_for_tx(db, tx1)
    assert _derived_rows(db)[0].chip_count == 2

    # 동일 business key 재인제션(값 일부 변경 → EDIT 이벤트 발생, 행 수는 불변)
    tx2 = f"tx_{uuid.uuid4().hex[:8]}"
    _seed_source(db, [dict(r, lot_hint="LOT_NEW") for r in rows], tx2)
    _run_chain_for_tx(db, tx2)

    derived = _derived_rows(db)
    assert len(derived) == 1
    assert derived[0].chip_count == 2, "재인제션 시 count 이중 가산 금지(멱등)"
    assert derived[0].lot_hint == "LOT_NEW"


def test_dedup_skips_blank_decision_key(enrich_env):
    db = enrich_env
    tx = f"tx_{uuid.uuid4().hex[:8]}"
    _seed_source(db, [
        {"equipment": "EQP1", "event_time": "T1", "chip_id": "C1"},
        {"equipment": "", "event_time": "T9", "chip_id": "C9"},  # 판단키 blank → 스킵
    ], tx)
    _run_chain_for_tx(db, tx)
    rows = _derived_rows(db)
    assert len(rows) == 1
    assert rows[0].business_key_val == "EQP1_T1"


# ---------------------------------------------------------------------------
# 3. 신규 API 2종 (경계 계약 형태)
# ---------------------------------------------------------------------------

def test_enrichment_rules_api_contract_shape(client, enrich_env):
    res = client.get("/enrichment/rules")
    assert res.status_code == 200
    body = res.json()
    assert set(body.keys()) == {"rules"}
    assert len(body["rules"]) == 1
    rule = body["rules"][0]
    assert set(rule.keys()) == {
        "name", "source_table", "derived_table", "decision_key",
        "target_fields", "list_columns", "reference_views",
    }
    assert rule["name"] == "bonding_wafer_attribution"
    assert rule["derived_table"] == "enrich_test_derived"
    assert rule["decision_key"] == ["equipment", "event_time"]
    assert rule["target_fields"] == ["wafer_id"]
    # 참조뷰는 label만 노출 — 쿼리 본문/limit 절대 노출 금지
    assert rule["reference_views"] == [{"label": "chips on equipment"}]
    assert "query" not in res.text and "SELECT" not in res.text


def test_enrichment_reference_api_execution_and_limit(client, enrich_env):
    db = enrich_env
    tx = f"tx_{uuid.uuid4().hex[:8]}"
    _seed_source(db, [
        {"equipment": "EQP1", "event_time": "T1", "chip_id": "C1", "lot_hint": "LOT_A"},
        {"equipment": "EQP1", "event_time": "T1", "chip_id": "C2", "lot_hint": "LOT_A"},
        {"equipment": "EQP1", "event_time": "T2", "chip_id": "C3", "lot_hint": "LOT_B"},
        {"equipment": "EQP9", "event_time": "T9", "chip_id": "C9", "lot_hint": "LOT_X"},
    ], tx)

    res = client.get(
        "/enrichment/rules/bonding_wafer_attribution/references/0",
        params={"params": json.dumps({"equipment": "EQP1"})},
    )
    assert res.status_code == 200
    body = res.json()
    assert set(body.keys()) == {"label", "columns", "rows"}
    assert body["label"] == "chips on equipment"
    assert body["columns"] == ["chip_id", "lot_hint"]
    # EQP1 매치는 3행이지만 뷰 limit=2가 서버에서 강제된다
    assert len(body["rows"]) == 2
    assert body["rows"][0] == ["C1", "LOT_A"]


def test_enrichment_reference_api_validation(client, enrich_env):
    # decision_key 외 파라미터 → 400
    res = client.get(
        "/enrichment/rules/bonding_wafer_attribution/references/0",
        params={"params": json.dumps({"chip_id": "C1"})},
    )
    assert res.status_code == 400
    # 잘못된 JSON → 400
    res = client.get(
        "/enrichment/rules/bonding_wafer_attribution/references/0",
        params={"params": "not-json"},
    )
    assert res.status_code == 400
    # 규칙 미존재 → 404
    res = client.get("/enrichment/rules/ghost_rule/references/0")
    assert res.status_code == 404
    # 인덱스 범위 밖 → 404
    res = client.get("/enrichment/rules/bonding_wafer_attribution/references/5")
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# 4. 기존 경로 재사용 확인 (blank 필터 워크리스트 + 사용자 저장) — 무변경 계약
# ---------------------------------------------------------------------------

def test_worklist_blank_filter_and_user_fill(client, enrich_env):
    db = enrich_env
    tx = f"tx_{uuid.uuid4().hex[:8]}"
    _seed_source(db, [
        {"equipment": "EQP1", "event_time": "T1", "chip_id": "C1"},
        {"equipment": "EQP2", "event_time": "T2", "chip_id": "C2"},
    ], tx)
    _run_chain_for_tx(db, tx)

    import main
    blank_filter = json.dumps({"wafer_id": {"type": "blank"}})

    # 결손 워크리스트: target blank 필터로 2건
    res = client.get("/tables/enrich_test_derived/data",
                     params={"filters": blank_filter, "order_by": "row_id"})
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 2 and len(body["data"]) == 2
    # 셀 계약 유지: data[col] = {value, ...}
    first = body["data"][0]
    assert isinstance(first["data"]["equipment"], dict) and "value" in first["data"]["equipment"]

    # 기존 배치 업서트 계약으로 사용자 입력 저장
    target_row_id = first["row_id"]
    res = client.put("/tables/enrich_test_derived/data/updates", json={
        "updates": [{"row_id": target_row_id, "updates": {"wafer_id": "W777"},
                     "source_name": "user", "updated_by": "tester"}],
        "silent": True,
    })
    assert res.status_code == 200
    assert res.json()["updated_count"] == 1

    # 채워진 키는 결손 필터에서 빠진다 (5초 count 캐시는 테스트에서 무효화)
    main.TABLE_COUNT_CACHE.clear()
    res = client.get("/tables/enrich_test_derived/data",
                     params={"filters": blank_filter, "order_by": "row_id"})
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 1 and len(body["data"]) == 1
    assert body["data"][0]["row_id"] != target_row_id
    # 채워진 셀은 user 소스로 표시된다(레이어링 계약)
    res = client.get("/tables/enrich_test_derived/data", params={"order_by": "row_id"})
    filled = next(r for r in res.json()["data"] if r["row_id"] == target_row_id)
    assert filled["data"]["wafer_id"]["value"] == "W777"
