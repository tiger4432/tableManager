"""체인 워커 created_logs 무절단 전송 결함 수정 회귀 테스트 (C-5 계약 확장, 2026-07-25 인시던트)
=================================================================================================
- 체인 워커 broadcast 메시지의 created_logs가 500건(MAX_NOTIFY_CREATED_LOGS)으로 절단되고
  total_log_count(절단 전 실제 총 건수)가 동봉되는지 — batch_row_upsert / batch_refresh_required 양 분기.
- /internal/events/broadcast 수신부가 total_log_count를 audit_cache total_count에 우선 반영하는지
  (필드 부재 시 len(created_logs) 폴백 — 구버전 호환).
- 상한 상수가 워처와 단일 공용 정의(event_constants)를 공유하는지.

테스트 테이블명은 사용자 config에 실존 불가능한 `chtrunc_test_*` 접두를 사용한다.
"""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from database.models import DatabaseOutbox
from event_constants import MAX_NOTIFY_CREATED_LOGS


# ---------------------------------------------------------------------------
# 공용 상수 단일 정의 검증
# ---------------------------------------------------------------------------

def test_truncation_constant_is_shared_single_definition():
    """워처·체인 워커가 동일한 공용 상수(event_constants.MAX_NOTIFY_CREATED_LOGS=500)를 써야 한다."""
    import directory_watcher
    import chain_ingestion_worker

    assert MAX_NOTIFY_CREATED_LOGS == 500
    assert directory_watcher.MAX_NOTIFY_CREATED_LOGS == MAX_NOTIFY_CREATED_LOGS
    assert chain_ingestion_worker.MAX_NOTIFY_CREATED_LOGS == MAX_NOTIFY_CREATED_LOGS


# ---------------------------------------------------------------------------
# 체인 워커: broadcast 메시지 구성 절단
# ---------------------------------------------------------------------------

# process_chain_transaction_group이 rule 설정으로 동적 import하는 테스트용 매퍼.
def chtrunc_mapper_single(db, payload):
    return {"updates": [{"business_key_val": "K1", "updates": {"v": 1}, "source_name": "chain_ingestion"}]}


def chtrunc_mapper_many(db, payload):
    return {
        "updates": [
            {"business_key_val": f"K{i}", "updates": {"v": i}, "source_name": "chain_ingestion"}
            for i in range(101)
        ]
    }


def _make_trigger_event(tx_id):
    return DatabaseOutbox(
        event_uuid=str(uuid.uuid4()),
        event_type="CREATE",
        table_name="chtrunc_test_trigger",
        payload={"source_name": "user", "transaction_id": tx_id, "data": {"k": "v"}},
    )


def _make_rule(func_name):
    return {
        "name": "chtrunc_test_rule",
        "trigger_table": "chtrunc_test_trigger",
        "target_table": "chtrunc_test_target",
        "mapper_module": "tests.test_chain_created_logs_truncation",
        "mapper_function": func_name,
        "enabled": True,
        "is_batch": False,
    }


def _patch_apply_batch_updates(monkeypatch, num_rows, num_logs):
    """crud.apply_batch_updates를 가짜로 대체 — num_rows개 행 결과 + num_logs건 created_logs 반환."""
    from database import crud

    results = [
        (SimpleNamespace(row_id=f"r{i}", created_at=None, updated_at=None), True)
        for i in range(num_rows)
    ]
    created_logs = [
        {
            "row_id": f"r{i % max(num_rows, 1)}",
            "table_name": "chtrunc_test_target",
            "column_name": "v",
            "timestamp": datetime(2026, 7, 25, 12, 0, 0, tzinfo=timezone.utc),
        }
        for i in range(num_logs)
    ]

    def fake_apply(db, table_name, batch_obj):
        return results, [("r0", "v")], created_logs, []

    monkeypatch.setattr(crud, "apply_batch_updates", fake_apply)


@pytest.mark.anyio
async def test_chain_broadcast_upsert_branch_truncates_created_logs(monkeypatch):
    """batch_row_upsert 분기(≤100 items): created_logs 501건 -> 500건 절단 + total_log_count=501."""
    from chain_ingestion_worker import process_chain_transaction_group

    _patch_apply_batch_updates(monkeypatch, num_rows=1, num_logs=501)

    tx_id = "tx_chtrunc_upsert"
    success, error, msgs = await process_chain_transaction_group(
        tx_id, [_make_trigger_event(tx_id)], MagicMock(), [_make_rule("chtrunc_mapper_single")]
    )
    assert success is True and error is None

    upserts = [m for m in msgs if m.get("event") == "batch_row_upsert"]
    assert len(upserts) == 1, f"batch_row_upsert 메시지가 1건이어야 함: {[m.get('event') for m in msgs]}"
    msg = upserts[0]
    assert len(msg["created_logs"]) == MAX_NOTIFY_CREATED_LOGS == 500
    assert msg["total_log_count"] == 501
    # 직렬화(타임스탬프 isoformat)는 절단 후 항목에만 수행되고 형태는 기존과 동일해야 한다.
    assert all(isinstance(log["timestamp"], str) for log in msg["created_logs"])
    # 기존 계약 필드 불변
    assert msg["table_name"] == "chtrunc_test_target"
    assert msg["transaction_id"] == f"chain_{tx_id}"
    assert len(msg["items"]) == 1


@pytest.mark.anyio
async def test_chain_broadcast_refresh_branch_truncates_created_logs(monkeypatch):
    """batch_refresh_required 분기(>100 items): 동일하게 500건 절단 + total_log_count 동봉."""
    from chain_ingestion_worker import process_chain_transaction_group

    _patch_apply_batch_updates(monkeypatch, num_rows=101, num_logs=501)

    tx_id = "tx_chtrunc_refresh"
    success, error, msgs = await process_chain_transaction_group(
        tx_id, [_make_trigger_event(tx_id)], MagicMock(), [_make_rule("chtrunc_mapper_many")]
    )
    assert success is True and error is None

    refreshes = [m for m in msgs if m.get("event") == "batch_refresh_required"]
    assert len(refreshes) == 1, f"batch_refresh_required 메시지가 1건이어야 함: {[m.get('event') for m in msgs]}"
    msg = refreshes[0]
    assert len(msg["created_logs"]) == MAX_NOTIFY_CREATED_LOGS == 500
    assert msg["total_log_count"] == 501
    assert msg["change_count"] == 101


# ---------------------------------------------------------------------------
# 수신부: /internal/events/broadcast의 total_log_count 존중
# ---------------------------------------------------------------------------

def _make_audit_log_dict(tx_id, i):
    """audit_cache의 pydantic 검증(AuditLogResponse)을 통과하는 유효 로그 dict."""
    return {
        "id": i + 1,
        "table_name": "chtrunc_test_target",
        "row_id": f"r{i}",
        "column_name": "v",
        "old_value": None,
        "new_value": str(i),
        "source_name": "chain_ingestion",
        "updated_by": "chain_worker",
        "transaction_id": tx_id,
        "timestamp": "2026-07-25T12:00:00+00:00",
    }


@pytest.fixture
def loaded_audit_cache(monkeypatch):
    """audit_cache를 '로드 완료·빈 상태'로 격리한다 (테스트 간 오염 방지)."""
    from audit_cache import audit_cache

    monkeypatch.setattr(audit_cache, "is_loaded", True)
    monkeypatch.setattr(audit_cache, "groups", [])
    return audit_cache


def test_internal_broadcast_respects_total_log_count(client, loaded_audit_cache):
    """total_log_count가 있으면 audit_cache의 total_count가 절단 후에도 실건수를 유지해야 한다."""
    tx_id = "chain_tx_chtrunc_total"
    res = client.post(
        "/internal/events/broadcast",
        json={
            "event": "batch_refresh_required",
            "table_name": "chtrunc_test_target",
            "change_count": 65000,
            "transaction_id": tx_id,
            "created_logs": [_make_audit_log_dict(tx_id, i) for i in range(3)],
            "total_log_count": 65000,
        },
    )
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

    groups = [g for g in loaded_audit_cache.groups if g["transaction_id"] == tx_id]
    assert len(groups) == 1
    assert groups[0]["total_count"] == 65000, "절단 전 실건수(total_log_count)가 total_count에 반영돼야 한다"
    assert len(groups[0]["logs"]) == 3


def test_internal_broadcast_falls_back_to_len_without_total_log_count(client, loaded_audit_cache):
    """구버전 호환: total_log_count 부재 시 기존처럼 len(created_logs)를 총계로 쓴다."""
    tx_id = "chain_tx_chtrunc_legacy"
    res = client.post(
        "/internal/events/broadcast",
        json={
            "event": "batch_row_upsert",
            "table_name": "chtrunc_test_target",
            "items": [],
            "updated_by": "chain_worker",
            "transaction_id": tx_id,
            "created_logs": [_make_audit_log_dict(tx_id, i) for i in range(2)],
        },
    )
    assert res.status_code == 200

    groups = [g for g in loaded_audit_cache.groups if g["transaction_id"] == tx_id]
    assert len(groups) == 1
    assert groups[0]["total_count"] == 2
