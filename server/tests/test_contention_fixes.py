"""
경합 점검(2026-07-25) 수정 배치 1 회귀 테스트
===============================================
- C-2: database 모듈 이중 import(-> before_flush 리스너 2중 등록 -> outbox 이벤트 x2 중복 발행) 근절
- C-1: batch_delete의 행별 business_key N+1 제거(벌크 조회) 결과 정합성
- C-5: 워처 최종 통지 created_logs 상한(500) + 실제 총 건수(total_log_count) 전달
- C-3: outbox 7일 보관 purge (보관기간·미처리 보호·청킹 상한)
"""
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest


# ---------------------------------------------------------------------------
# C-2: outbox 이중 발행 근절
# ---------------------------------------------------------------------------

def test_before_flush_listener_registered_once(db_session):
    """directory_watcher(웹서버/워처의 import 그래프)를 로드해도 database.database 모듈이
    단일 정체성으로 유지되고 before_flush 리스너가 Session에 1개만 등록되어야 한다.

    회귀 배경: directory_watcher가 `server.database.database`로 import하면 동일 모듈이
    서로 다른 이름으로 2회 로드되어 리스너가 2중 등록 -> 모든 outbox 이벤트가 x2로 발행됐다
    (라이브 실측 중복 그룹 1,259,076개).
    """
    import directory_watcher  # noqa: F401 — 웹서버(main.py)/워처(run_watcher.py)와 동일 import 경로

    # 1. 모듈 정체성: server.database.database가 별도 모듈로 로드되어 있으면 안 된다.
    assert ("server.database.database" not in sys.modules) or (
        sys.modules["server.database.database"] is sys.modules["database.database"]
    ), "database.database 모듈이 서로 다른 이름으로 이중 로드되었다 (C-2 회귀)"

    # 2. 리스너 등록 수: before_flush에 auto_stage_database_outbox가 정확히 1개.
    names = [getattr(fn, "__name__", str(fn)) for fn in db_session.dispatch.before_flush]
    assert names.count("auto_stage_database_outbox") == 1, (
        f"before_flush 리스너가 {names.count('auto_stage_database_outbox')}개 등록됨 (기대 1개): {names}"
    )


def test_outbox_event_staged_exactly_once(db_session):
    """행 1건 flush 시 outbox 이벤트가 정확히 1건만 적재되어야 한다 (x2 중복 발행 회귀 가드)."""
    import directory_watcher  # noqa: F401

    from database import models
    from database.models import DatabaseOutbox

    model = models.DYNAMIC_TABLES["raw_table_1"]
    r_id = str(uuid.uuid4())
    db_session.add(model(row_id=r_id, business_key_val="EQP_C2_TEST", EQP_ID="EQP_C2_TEST"))
    db_session.commit()

    events = db_session.query(DatabaseOutbox).all()
    matching = [e for e in events if (e.payload or {}).get("row_id") == r_id]
    assert len(matching) == 1, f"행 1건 flush에 outbox 이벤트 {len(matching)}건 적재됨 (기대 1건)"


def test_legacy_server_parsers_import_shim(tmp_path, monkeypatch):
    """[C-2 하위호환] 구식 사용자 스크립트의 `from server.parsers.pipeline_base import ...`가
    top-level `pipeline_base`와 **동일 모듈 객체**를 받아야 한다(issubclass 정체성 유지,
    이중 로드 불가). 실제 플러그인 로드 방식(importlib spec)과 동일하게 검증한다."""
    import importlib.util
    import directory_watcher
    import pipeline_base

    # 사전 로드된 `server.*` 항목을 제거해 shim이 별칭을 새로 등록하는 경로를 검증한다.
    # (conda env에는 프로젝트 pip editable finder가 상주하여 `server.*`가 항상 해석 가능 —
    #  shim은 '차단'이 아니라 '동일 객체 별칭 선점'으로 이중 로드를 중화한다.)
    for name in [n for n in list(sys.modules) if n == "server" or n.startswith("server.")]:
        monkeypatch.delitem(sys.modules, name, raising=False)

    directory_watcher._register_legacy_import_shim()

    script = tmp_path / "legacy_plugin.py"
    script.write_text(
        "from server.parsers.pipeline_base import BasePipelineParser\n"
        "from server.parsers.html_topology_parser import HTMLMatrixTableParser\n"
        "class LegacyParser(BasePipelineParser):\n"
        "    @staticmethod\n"
        "    def match(file_path):\n"
        "        return False\n"
        "    def parse(self, file_path):\n"
        "        return []\n",
        encoding="utf-8",
    )
    spec = importlib.util.spec_from_file_location("pipeline_plugin_legacy_shim_test", str(script))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # 동일 객체 정체성: 구식 import == top-level 정본
    assert module.BasePipelineParser is pipeline_base.BasePipelineParser
    assert sys.modules["server.parsers.pipeline_base"] is pipeline_base
    # 워처의 issubclass 판정이 MRO 이름 비교 fallback 없이 직접 성립
    assert issubclass(module.LegacyParser, pipeline_base.BasePipelineParser)
    # html_topology_parser 별칭도 동일 객체
    import html_topology_parser
    assert module.HTMLMatrixTableParser is html_topology_parser.HTMLMatrixTableParser

    # 핵심 방어: 어떤 스크립트가 `server.database.database`를 import하더라도
    # 별칭 선점에 의해 top-level `database.database`와 **동일 객체**를 받는다
    # → before_flush 리스너 2차 등록(outbox ×2 발행) 재도입이 원천 불가.
    # (env의 pip editable finder 때문에 '차단'은 불가능 — 동일 객체 보장이 유일하게 안전한 성질)
    import importlib as _importlib
    legacy_db = _importlib.import_module("server.database.database")
    assert legacy_db is sys.modules["database.database"], (
        "server.database.database가 별도 사본으로 로드됨 — 리스너 2중 등록(C-2) 재발 경로"
    )
    legacy_crud = _importlib.import_module("server.database.crud")
    assert legacy_crud is sys.modules["database.crud"]


# ---------------------------------------------------------------------------
# C-1: batch_delete 벌크 business_key 결과 정합성
# ---------------------------------------------------------------------------

def test_bulk_business_key_lookup_matches_per_row_semantics(db_session):
    """get_deleted_rows_business_keys_bulk(벌크 IN 조회)가 기존 행별 get_deleted_row_business_key와
    동일한 결과를 내야 한다 — ① business_key 직접 보유 로그(최신 우선), ② key_col 편집 로그
    new_value fallback, ③ 로그 없음(None) 세 경로 모두."""
    from datetime import timezone as _tz
    from database import models
    import main as main_mod

    def add_log(row_id, column_name, new_value=None, business_key=None, ts_offset=0):
        db_session.add(models.AuditLog(
            table_name="raw_table_1",
            row_id=row_id,
            column_name=column_name,
            old_value=None,
            new_value=new_value,
            source_name="system",
            updated_by="tester",
            transaction_id=str(uuid.uuid4()),
            timestamp=datetime.now(_tz.utc) + timedelta(seconds=ts_offset),
            business_key=business_key,
        ))

    # ① business_key 직접 보유 — 구값(BK_OLD) 이후 신값(BK_NEW): 최신값이 이겨야 한다
    add_log("row_direct", "EQP_ID", business_key="BK_OLD", ts_offset=0)
    add_log("row_direct", "EQP_ID", business_key="BK_NEW", ts_offset=10)
    # ② business_key 미보유 -> key_col(EQP_ID) 편집 로그의 new_value fallback
    add_log("row_fallback", "EQP_ID", new_value="FB_VALUE")
    # ③ 로그가 전혀 없는 행 -> None
    db_session.commit()

    row_ids = ["row_direct", "row_fallback", "row_missing"]
    bulk = main_mod.get_deleted_rows_business_keys_bulk(db_session, "raw_table_1", row_ids)

    for r_id in row_ids:
        expected = main_mod.get_deleted_row_business_key(db_session, "raw_table_1", r_id)
        assert bulk.get(r_id) == expected, f"{r_id}: bulk={bulk.get(r_id)} != per-row={expected}"
    assert bulk["row_direct"] == "BK_NEW"
    assert bulk["row_fallback"] == "FB_VALUE"
    assert "row_missing" not in bulk


def test_batch_delete_endpoint_smoke(client, db_session):
    """batch_delete 엔드포인트가 threadpool 격리 후에도 정상 동작해야 한다 (계약 형태 불변)."""
    from database import models

    model = models.DYNAMIC_TABLES["raw_table_1"]
    rows = db_session.query(model).limit(3).all()
    row_ids = [r.row_id for r in rows]
    assert len(row_ids) == 3

    res = client.post(
        "/tables/raw_table_1/rows/batch_delete",
        json={"row_ids": row_ids, "user_name": "tester"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["deleted_count"] == 3
    assert isinstance(body["created_logs"], list)
    assert db_session.query(model).filter(model.row_id.in_(row_ids)).count() == 0


def test_internal_batch_refresh_accepts_total_log_count(client):
    """C-5: 내부 이벤트 엔드포인트가 total_log_count(절단 전 실제 총 건수) 필드를 수용해야 한다."""
    res = client.post(
        "/internal/events/batch-refresh",
        json={
            "table_name": "raw_table_1",
            "change_count": 1200,
            "created_logs": [{"table_name": "raw_table_1", "row_id": "r1", "column_name": "EQP_ID"}],
            "total_log_count": 1200,
        },
    )
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# C-5: 워처 created_logs 누적 상한
# ---------------------------------------------------------------------------

def test_watcher_created_logs_capped_at_500(db_session, monkeypatch):
    """수십만 행 파일 인제션에서도 최종 통지 created_logs는 500건으로 절단되고,
    total_log_count로 실제 총 건수가 전달되어야 한다 (이벤트 필드 형태는 불변)."""
    import json as json_mod
    import directory_watcher

    # 가짜 테이블 설정 주입: _send_to_upsert가 읽는 전역 table_config.json 응답을 가로챈다.
    original_load = json_mod.load

    def fake_load(fp, *args, **kwargs):
        if hasattr(fp, "name") and "table_config.json" in str(getattr(fp, "name", "")):
            return {"cap_test_table": {"business_key": "k", "display_columns": ["k", "v"]}}
        return original_load(fp, *args, **kwargs)

    monkeypatch.setattr(json_mod, "load", fake_load)

    # DB 세션/crud를 가짜로 대체 — 청크당 행 수만큼 created_logs를 반환한다.
    class _FakeDB:
        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

    def fake_apply_batch_updates(db, table_name, batch_obj):
        n = len(batch_obj.updates)
        logs = [{"row_id": f"r{i}", "table_name": table_name} for i in range(n)]
        changed = [(f"r{i}", "v") for i in range(n)]
        return [], changed, logs, []

    monkeypatch.setattr(directory_watcher, "SessionLocal", lambda: _FakeDB())
    monkeypatch.setattr(directory_watcher.crud, "apply_batch_updates", fake_apply_batch_updates)

    captured = {}

    def on_refresh(t_name, count, created_logs, total_log_count):
        captured["logs"] = created_logs
        captured["total"] = total_log_count
        captured["count"] = count

    handler = directory_watcher.IngestionHandler(
        workspace_path="unused",
        config_path=None,
        archives_path="unused",
        default_table_name="cap_test_table",
        on_refresh_callback=on_refresh,
    )

    # 1200행 -> 1000 + 200 두 청크, 로그 총 1200건 발생 -> 통지에는 500건만 동봉
    rows = [{"k": f"K{i}", "v": i} for i in range(1200)]
    handler._send_to_upsert(rows, uploader="tester", filename=None)

    assert captured, "on_refresh_callback이 호출되지 않았다"
    assert len(captured["logs"]) == directory_watcher.MAX_NOTIFY_CREATED_LOGS == 500
    assert captured["total"] == 1200
    assert captured["count"] == 1200  # changed cells 총계는 절단과 무관


# ---------------------------------------------------------------------------
# C-3: outbox 7일 보관 purge
# ---------------------------------------------------------------------------

def _add_outbox_row(db, *, processed: bool, age_days: int):
    from database.models import DatabaseOutbox

    row = DatabaseOutbox(
        event_uuid=str(uuid.uuid4()),
        event_type="EDIT",
        table_name="raw_table_1",
        payload={"row_id": "x"},
        status="SUCCESS" if processed else "PENDING",
        processed_chain=processed,
        created_at=datetime.now(timezone.utc) - timedelta(days=age_days),
    )
    db.add(row)
    return row


def test_outbox_purge_deletes_only_expired_processed_rows(db_session):
    from chain_ingestion_worker import purge_expired_outbox_sync
    from database.models import DatabaseOutbox

    old_processed = _add_outbox_row(db_session, processed=True, age_days=8)
    fresh_processed = _add_outbox_row(db_session, processed=True, age_days=1)
    old_unprocessed = _add_outbox_row(db_session, processed=False, age_days=30)
    db_session.commit()
    keep_ids = {fresh_processed.id, old_unprocessed.id}
    gone_id = old_processed.id

    deleted = purge_expired_outbox_sync(lambda: db_session, retention_days=7)
    assert deleted == 1

    remaining_ids = {r.id for r in db_session.query(DatabaseOutbox).all()}
    assert gone_id not in remaining_ids, "7일 경과 처리 완료 행이 삭제되지 않았다"
    assert keep_ids.issubset(remaining_ids), (
        "보관기간 내 처리 행 또는 미처리 행이 잘못 삭제되었다 (미처리 행은 나이와 무관하게 보호)"
    )


def test_outbox_purge_respects_chunk_cap(db_session):
    """사이클당 max_chunks 상한을 지켜 초과분은 다음 사이클로 이월해야 한다 (루프 독점 방지)."""
    from chain_ingestion_worker import purge_expired_outbox_sync
    from database.models import DatabaseOutbox

    for _ in range(35):
        _add_outbox_row(db_session, processed=True, age_days=10)
    db_session.commit()

    deleted = purge_expired_outbox_sync(lambda: db_session, retention_days=7, chunk_size=10, max_chunks=2)
    assert deleted == 20  # 10행 x 2청크만 삭제, 15행은 다음 사이클

    left = db_session.query(DatabaseOutbox).filter(DatabaseOutbox.processed_chain == True).count()
    assert left == 15

    # 다음 사이클에서 잔여분 소진
    deleted2 = purge_expired_outbox_sync(lambda: db_session, retention_days=7, chunk_size=10, max_chunks=5)
    assert deleted2 == 15
