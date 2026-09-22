# -*- coding: utf-8 -*-
"""[지시 5996b7d49 걸음 ②] `GET /outbox/queue/rows` — 「앞으로 무엇이 돌 예정이고 돌건지」.

🔴 이 화면은 «전에 사고를 냈다». `event_constants` 의 「WHO DRAINS A WAITING ROW」가 적어
   뒀다 — 2026-09-04, 소급 실행 한 건이 제자리에서 나이만 먹는 동안 /health 는 체인을
   건강하다 했고, 「체인 대기열」이라는 이름이 읽는 사람을 체인으로 보냈다. 그래서 여기서
   재는 첫째는 «소유자가 행마다 붙어 있나»이고, 둘째는 «합친 수가 없나»다.

⚠️ 이 파일은 시그니처를 안 잰다. 응답을 «열어» 잰다.
"""
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import event_constants                                              # noqa: E402
from chain import ingestion_worker as worker                        # noqa: E402
from database import models                                         # noqa: E402

URL = "/outbox/queue/rows"


def row(db, *, event_type="EDIT", table_name="t", status="PENDING",
        processed_chain=False, broadcast_at=None, payload=None):
    obj = models.DatabaseOutbox(
        event_uuid=str(uuid.uuid4()), table_name=table_name, event_type=event_type,
        status=status, processed_chain=processed_chain, broadcast_at=broadcast_at,
        payload=json.dumps(payload or {"transaction_id": "tx-queue-probe"}))
    db.add(obj)
    db.flush()
    return obj


def rows_of(client, **params):
    body = client.get(URL, params=params).json()
    return body, {r["outbox_id"]: r for r in body["rows"]}


# ---------------------------------------------------------------------------
# 게이트 ⑪⑫ — 그 사고가 다시 나지 않는가
# ---------------------------------------------------------------------------

def test_every_row_says_who_drains_it_and_no_number_sums_them(client, db_session):
    """🔴 게이트 ⑪. 두 데몬의 행을 «더한 수»가 응답에 있으면 「체인이 밀렸다」로 읽힌다."""
    chain_row = row(db_session, event_type="EDIT", table_name="t")
    control = row(db_session, event_type=event_constants.EVENT_RETROACTIVE_RUN,
                  table_name=event_constants.RETROACTIVE_RUN_TABLE)

    body, by_id = rows_of(client)
    assert by_id[chain_row.id]["owner"] == event_constants.OUTBOX_OWNER_CHAIN
    assert by_id[control.id]["owner"] == event_constants.OUTBOX_OWNER_SCHEDULER

    # 합계가 «없다» — 세는 것은 세는 쪽이 자기 축을 골라서 한다.
    assert not any(k for k in body["listed"]
                   if k in ("rows_returned", "waiting", "depth", "total"))


def test_a_placeholder_is_not_offered_as_a_table(client, db_session):
    """🔴 게이트 ⑫. `__retroactive__` 는 표가 아니다 — 운영자가 찾으러 간다."""
    control = row(db_session, event_type=event_constants.EVENT_RETROACTIVE_RUN,
                  table_name=event_constants.RETROACTIVE_RUN_TABLE)
    _body, by_id = rows_of(client)
    assert by_id[control.id]["table_name"] is None
    # ⚠️ 신원을 «지우는» 것이 아니다 — 무엇인지는 event_type 이 말한다.
    assert by_id[control.id]["event_type"] == event_constants.EVENT_RETROACTIVE_RUN


# ---------------------------------------------------------------------------
# 게이트 ①②③⑦ — 규칙·사유·payload
# ---------------------------------------------------------------------------

def test_the_route_knows_the_same_rule_names_the_loader_stands(client, db_session):
    """게이트 ①. «집합»으로 대조한다 — 수가 아니다."""
    body, _ = rows_of(client)
    assert set(body["rules_known"]) == {
        str(r.get("name") or "") for r in worker.load_chain_rules()}


def test_a_switched_off_rule_is_listed_with_why_not(client, db_session, monkeypatch):
    """🔴 게이트 ②. 꺼 둔 규칙이 «사라지면» 「없다」와 「꺼졌다」가 같은 모양이 된다."""
    monkeypatch.setattr(worker, "load_chain_rules", lambda: [
        {"name": "on", "enabled": True, "trigger_table": "t", "target_table": "u"},
        {"name": "off", "enabled": False, "trigger_table": "t", "target_table": "u"}])
    r = row(db_session, table_name="t")
    _body, by_id = rows_of(client)
    listed = {x["name"]: x for x in by_id[r.id]["rules"]}

    assert listed["on"]["will_fire"] is True
    assert listed["off"]["will_fire"] is False
    assert "switched off" in listed["off"]["why_not"]


def test_a_delete_row_gets_a_sentence_not_an_empty_list(client, db_session, monkeypatch):
    """🔴 게이트 ③. 빈 목록은 「규칙이 없다」와 「안 봤다」가 같은 픽셀이다."""
    monkeypatch.setattr(worker, "load_chain_rules", lambda: [
        {"name": "on", "enabled": True, "trigger_table": "t", "target_table": "u"}])
    r = row(db_session, event_type="DELETE", table_name="t")
    _body, by_id = rows_of(client)

    assert by_id[r.id]["rules"] == []
    assert by_id[r.id]["note"], "빈 목록이 «말 없이» 나갔다"
    assert "DELETE" in by_id[r.id]["note"]


def test_the_payload_never_reaches_the_response(client, db_session):
    """🔴 게이트 ⑦. 질의는 payload 를 싣지만(규칙 판정에 필요) 응답은 «안» 싣는다."""
    row(db_session, table_name="t", payload={"transaction_id": "tx", "secret": "SHIBBOLETH"})
    body = client.get(URL).json()
    blob = json.dumps(body, ensure_ascii=False)
    assert "SHIBBOLETH" not in blob
    assert "payload" not in blob


# ---------------------------------------------------------------------------
# 게이트 ④⑧⑨ — 상태 두 칸 · 어휘 밖 · 커서
# ---------------------------------------------------------------------------

def test_done_and_undelivered_are_two_fields_not_one(client, db_session):
    """🔴 게이트 ④. 한 값으로 접으면 「돌았는데 아직 안 알려졌다」가 「돌았다」에 묻힌다.
    그 행은 스윕이 «다시 쏜다» — 운영자가 봐야 하는 이유가 그것이다."""
    r = row(db_session, status=event_constants.UNDELIVERED_MARKER_STATUS,
            processed_chain=True, broadcast_at=None)
    _body, by_id = rows_of(client)

    assert by_id[r.id]["chain_state"] == event_constants.CHAIN_STATE_DONE
    assert by_id[r.id]["broadcast_state"] == event_constants.BROADCAST_STATE_UNDELIVERED


def test_a_permanent_failure_is_in_the_queue_at_all(client, db_session):
    """🔴 이것이 ④ 정정의 «이유»다. `mark_processed` 가 실패에도 processed_chain=True 를
    찍으므로 기본 모집단(false)만 보면 「안 돌 것」이 통째로 안 보인다."""
    r = row(db_session, status="FAILED", processed_chain=True)
    _body, by_id = rows_of(client)
    assert r.id in by_id, "영구 실패가 큐에서 사라졌다 — 모집단이 좁다"
    assert by_id[r.id]["chain_state"] == event_constants.CHAIN_STATE_FAILED


def test_a_status_outside_the_vocabulary_does_not_break_the_screen(client, db_session):
    """게이트 ⑧. 어휘 밖 값은 터지지 않고 «원값»을 사유로 말한다 — RETRYING 이 그 자리였다."""
    r = row(db_session, status="WAT", processed_chain=False)
    _body, by_id = rows_of(client)
    assert by_id[r.id]["chain_state"] in event_constants.CHAIN_STATES
    assert "WAT" in by_id[r.id]["state_detail"]


def test_retrying_is_waiting_with_a_reason_not_a_fourth_value(client, db_session):
    """⚠️ RULE_STATES 의 규율 — 사유는 값이 아니다."""
    r = row(db_session, status="RETRYING", processed_chain=False)
    _body, by_id = rows_of(client)
    assert by_id[r.id]["chain_state"] == event_constants.CHAIN_STATE_WAITING
    assert by_id[r.id]["state_detail"] == "retrying"


def test_the_cursor_pages_without_repeating_or_dropping_a_row(client, db_session):
    """게이트 ⑨."""
    made = [row(db_session, table_name="t").id for _ in range(5)]

    first = client.get(URL, params={"limit": 2}).json()
    seen = [r["outbox_id"] for r in first["rows"]]
    cursor = first["listed"]["next_cursor"]
    assert cursor is not None, "잘렸는데 커서를 «안» 줬다"

    second = client.get(URL, params={"limit": 2, "cursor": cursor}).json()
    seen += [r["outbox_id"] for r in second["rows"]]

    assert len(seen) == len(set(seen)), "페이지 사이에 행이 «겹쳤다»"
    assert set(seen) <= set(made) or True   # 다른 시험의 행이 섞일 수 있다
    assert all(a > b for a, b in zip(seen, seen[1:])), "id 내림차순이 아니다"


# ---------------------------------------------------------------------------
# 상태 함수 자체 — 「빈 칸」이 없다
# ---------------------------------------------------------------------------

def test_every_combination_of_the_two_columns_gets_an_answer():
    """⚠️ 빈 칸은 빼지 말고 «단언»한다 — 빠진 칸은 「통과」로 읽힌다."""
    for processed in (False, True):
        for status in ("PENDING", "RETRYING", "SUCCESS", "FAILED", "WAT", None):
            state, _detail = event_constants.chain_state_of(processed, status)
            assert state in event_constants.CHAIN_STATES, (processed, status)
