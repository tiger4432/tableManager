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
        "target_fields", "list_columns", "reference_views", "queue_filters",
        "keyed_queue_filters", "alignment",
    }
    # 이 픽스처 규칙은 정렬을 선언하지 않았다 → false. 키는 **항상** 있다: 없으면 클라가
    # 「서버가 이 필드를 모른다」와 「이 규칙은 정렬 대상이 아니다」를 가르려고 버전 검사를
    # 하게 되고, 그 검사는 자기가 대신하려던 서버보다 오래 산다.
    assert rule["alignment"] is False
    assert rule["name"] == "bonding_wafer_attribution"
    assert rule["derived_table"] == "enrich_test_derived"
    assert rule["decision_key"] == ["equipment", "event_time"]
    assert rule["target_fields"] == ["wafer_id"]
    # 큐 진입 조건의 단일 조성 = target blank **뿐**이다 (사용자 재정 2026-08-04, N36).
    # 판단키 notBlank가 여기 들어 있으면 진행률 분모(무필터 전체 행)와 다른 모집단을
    # 세게 되어, 판단키가 빈 행이 「답한 것」으로 계산된다.
    assert rule["queue_filters"] == {"wafer_id": {"type": "blank"}}
    # 판단키 술어는 사라진 것이 아니라 **이름을 얻었다** — 쓰기 경로(자동확정 스윕)는
    # 여전히 이쪽만 본다. 두 total의 차가 「판단키 없음 N건」이다.
    assert rule["keyed_queue_filters"] == {
        "equipment": {"type": "notBlank"},
        "event_time": {"type": "notBlank"},
        "wafer_id": {"type": "blank"},
    }
    # 참조뷰는 label + candidate_for만 노출 — 쿼리 본문/limit은 절대 노출 금지.
    # `candidate_for`는 2026-07-30 [F9] 총괄 승인으로 추가된 **가산적** 필드다. 노출되는
    # 값은 뷰 결과 **컬럼명**이고, 그 컬럼명은 `/references/{i}` 응답의 헤더로 이미
    # 나타난다 → 신규 노출 0. 이 필드가 없으면 클라이언트는 「어느 뷰가 후보 원천인가」를
    # 스스로 유도해야 하고, 유도는 맵 오버레이에서 라이브 DECOY를 만들어낸 실패 계급이다.
    assert rule["reference_views"] == [
        {"label": "chips on equipment", "candidate_for": {}}
    ]
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




# ---------------------------------------------------------------------------
# 5. The queue predicate - numerator and denominator count ONE population
#    (N36, user ruling 2026-08-04). Written in English because these assertion
#    messages are read on a cp949 console.
# ---------------------------------------------------------------------------

def _seed_blank_key_rows(db):
    """Create the two derived rows that carry NO decision key.

    Both shapes were observed in the `1fefd12` investigation: a grid empty-row
    add, and a hand edit that fills a neighbouring cell only. The chain mapper
    skips blank decision keys, so ingestion never produces these.
    """
    crud.create_empty_rows_batch(db, "enrich_test_derived", 1)
    crud.apply_batch_updates(db, "enrich_test_derived", schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(business_key_val="orphan_1",
                                  updates={"job_id": "orphan_1", "lot_hint": "LOT_X"},
                                  source_name="user", updated_by="tester")
    ], silent=True))


def _total(client, filters=None):
    """One `total` from `/tables/{t}/data` - the same call the client counts with."""
    import main
    main.TABLE_COUNT_CACHE.clear()  # the 5s count cache must not blend measurements
    params = {"skip": 0, "limit": 1}
    if filters is not None:
        params["filters"] = json.dumps(filters)
    res = client.get("/tables/enrich_test_derived/data", params=params)
    assert res.status_code == 200
    return res.json()["total"]


def test_progress_numerator_and_denominator_count_one_population(client, enrich_env):
    """N36 reproduction: the bar read 100% while work remained.

    The denominator (`enrichment.js fetchTotalAll`) filters NOTHING - it is every
    derived row. The remainder used `queue_filters`, which also demanded every
    decision key non-blank. Two different populations, so a row with a blank
    decision key sat in the denominator and outside the remainder: counted as
    ANSWERED. This rebuilds exactly that state - two rows, both targets blank,
    nothing answered - and the bar must read 0%.
    """
    db = enrich_env
    _seed_blank_key_rows(db)
    rule = client.get("/enrichment/rules").json()["rules"][0]

    total_all = _total(client)                          # denominator: no filter
    remaining = _total(client, rule["queue_filters"])   # remainder

    assert total_all == 2, "fixture premise: 2 derived rows"
    assert remaining == 2, (
        f"the remainder counted {remaining} of {total_all} rows while 0 are answered - "
        f"the two numbers are not counting the same population")
    # updateHeaderStats(): filled = totalAll - remaining, pct = filled / totalAll
    pct = round((total_all - remaining) / total_all * 100)
    assert pct == 0, f"progress reads {pct}% with every row unanswered"


def test_blank_key_rows_are_in_the_worklist_and_named_separately(client, enrich_env):
    """Blank-key rows now APPEAR in the worklist, and are named as their own count.

    User ruling 2026-08-04: hiding them is worse - a missing decision key is an
    upstream defect and an invisible defect is never fixed. They are still
    unjudgeable (a reference view is queried WITH the key's value, so an empty
    value finds no evidence), so `keyed_queue_filters` separates them. The
    difference of the two totals IS the named aggregate.
    """
    db = enrich_env
    tx = f"tx_{uuid.uuid4().hex[:8]}"
    _seed_source(db, [{"equipment": "EQP1", "event_time": "T1", "chip_id": "C1"}], tx)
    _run_chain_for_tx(db, tx)
    _seed_blank_key_rows(db)

    rule = client.get("/enrichment/rules").json()["rules"][0]
    assert "keyed_queue_filters" in rule, (
        "the public rule carries no NAMED key predicate, so the client has no way to "
        "count the blank-key rows it is now showing")

    queue = _total(client, rule["queue_filters"])
    keyed = _total(client, rule["keyed_queue_filters"])
    blank_key = queue - keyed

    assert queue == 3, "the 2 blank-key rows are still excluded from the queue"
    assert keyed == 1, "exactly 1 queue entry carries its decision keys"
    assert blank_key == 2, f"the named aggregate must carry a non-zero count (got {blank_key})"

    # Counting them is not enough - they must be REACHABLE on the worklist page.
    import main
    main.TABLE_COUNT_CACHE.clear()
    page = client.get("/tables/enrich_test_derived/data",
                      params={"filters": json.dumps(rule["queue_filters"]),
                              "order_by": "row_id", "order_desc": False}).json()
    assert len(page["data"]) == 3
    keyless = [r for r in page["data"]
               if crud.clean_str_value(r["data"]["equipment"]["value"]) == ""]
    assert len(keyless) == 2, "blank-key rows are not in the worklist response"


def test_rule_without_blank_key_rows_is_unchanged(client, enrich_env):
    """The negative: with no blank-key rows, behaviour is exactly as before.

    Both predicates return the same total, the same rows and the same order, and
    the named aggregate is 0. Nothing about healthy data moved - the only thing
    this change alters is the visibility of blank-key rows.
    """
    db = enrich_env
    tx = f"tx_{uuid.uuid4().hex[:8]}"
    _seed_source(db, [
        {"equipment": "EQP1", "event_time": "T1", "chip_id": "C1"},
        {"equipment": "EQP2", "event_time": "T2", "chip_id": "C2"},
    ], tx)
    _run_chain_for_tx(db, tx)

    rule = client.get("/enrichment/rules").json()["rules"][0]
    assert _total(client, rule["queue_filters"]) == 2
    assert _total(client, rule["keyed_queue_filters"]) == 2

    import main
    args = {"order_by": "row_id", "order_desc": False}
    main.TABLE_COUNT_CACHE.clear()
    a = client.get("/tables/enrich_test_derived/data",
                   params={**args, "filters": json.dumps(rule["queue_filters"])}).json()
    main.TABLE_COUNT_CACHE.clear()
    b = client.get("/tables/enrich_test_derived/data",
                   params={**args, "filters": json.dumps(rule["keyed_queue_filters"])}).json()
    assert a == b, "no blank-key rows exist, yet the two predicates return different pages"


# ---------------------------------------------------------------------------
# The alignment marker: DECLARED, never inferred
# ---------------------------------------------------------------------------
# Nothing used to say which rules the map-alignment screen can work with, so the client
# listed all of them and proposed the first - which live is `dt_job_lot_slot_attribution`,
# a rule that cannot align anything. The fix is a marker the site declares, NOT a name
# pattern: selecting rules whose target fields contain "frame" is exactly the inference this
# screen refuses everywhere else, and it is I4 (a plausible default impersonating a
# declaration) with a regex on top.

def _decl(**kw):
    return _base_rule(**kw)


def _one(raw):
    rules = enrichment_config.validate_enrichment_rules({"r": raw}, known_tables=KNOWN)
    assert len(rules) == 1, "the fixture rule must be valid apart from the marker"
    return rules[0]


def test_a_rule_that_declares_alignment_is_marked():
    assert _one(_decl(alignment=True))["alignment"] is True


def test_a_rule_that_never_declared_it_is_not_marked():
    """Absent is not a default; it is the fact that nobody ever claimed this rule aligns."""
    assert _one(_decl())["alignment"] is False


def test_the_marker_is_strict_so_a_config_typo_cannot_claim_it():
    """Same discipline as `map_push_ok`: only the JSON boolean counts. A truthy string is a
    typo, and a typo must not enrol a rule into a screen that writes coordinate systems."""
    for typo in ("true", "True", 1, "yes", [1], {"a": 1}):
        assert _one(_decl(alignment=typo))["alignment"] is False, typo
    for falsey in (False, "false", 0, None, ""):
        assert _one(_decl(alignment=falsey))["alignment"] is False, falsey


def test_the_marker_is_not_inferred_from_frame_shaped_target_fields():
    """The exact inference the ruling forbids. A rule whose targets are named `core_frame`
    and `dt_frame` - the live alignment rule's own field names - and which declares nothing
    stays unmarked. Reading the names would be I4 with a regex on top."""
    import copy
    known = copy.deepcopy(KNOWN)
    known["enrich_test_derived"]["column_types"].update(
        {"core_frame": "string", "dt_frame": "string"})
    raw = {"r": _base_rule(target_fields=["core_frame", "dt_frame"],
                           list_columns=[], aggregations={})}
    rules = enrichment_config.validate_enrichment_rules(raw, known_tables=known)
    assert len(rules) == 1
    assert rules[0]["alignment"] is False


def test_the_marker_survives_to_the_public_shape():
    import enrichment_config
    marked = enrichment_config.to_public_rule(_one(_decl(alignment=True)))
    unmarked = enrichment_config.to_public_rule(_one(_decl()))
    assert marked["alignment"] is True
    assert unmarked["alignment"] is False


def test_the_live_declaration_is_read_rather_than_backfilled():
    """`server/config/` is gitignored, so this asks the REAL files what they say instead of
    asserting a value into them. Whether any rule is marked is the product owner's decision;
    what is pinned here is that the served value equals the declared one, per rule.

    🔴 It loads the live table config on purpose. Going through `crud.TABLE_CONFIG` as it
    stands inside the suite returns the TEST tables, every live rule is then rejected for
    unknown columns, and the test skips - proving nothing while looking green.
    """
    import os
    if not os.path.exists(enrichment_config.ENRICHMENT_RULES_PATH):
        pytest.skip("live enrichment_rules.json absent (gitignored; fresh checkout)")
    with open(enrichment_config.ENRICHMENT_RULES_PATH, encoding="utf-8") as f:
        declared = json.load(f)
    live_tables = crud.load_table_config_or_raise()
    rules = enrichment_config.validate_enrichment_rules(declared, known_tables=live_tables)
    assert rules, "the live rule file parsed to nothing - the check below would be vacuous"
    for r in rules:
        want = declared[r["name"]].get("alignment") is True
        assert r["alignment"] is want, r["name"]
        assert enrichment_config.to_public_rule(r)["alignment"] is want, r["name"]
