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


def test_a_permanent_failure_is_not_in_the_queue(client, db_session):
    """⚰️ 이 줄은 «정반대»를 재고 있었다 — 「실패가 큐에 있나」. 제가 실패가 기본 모집단에서
    빠지는 것을 찾아 합집합에 넣었고, 소유자가 무르셨다:

    > 「대기열에 failed 는 띄우지 마. «앞으로 돌 것만» 띄워」

    제 발견(실패가 `processed_chain=true` 라 기본 모집단에서 빠진다)은 «맞았고», 그것이
    이 화면의 물음이 아니라는 것이 판단이다. 실패를 보는 자리는 `/admin/outbox/failed` 다.

    🔴 이 박스에 failed 가 298 건 있다(총괄 실측) — 그래서 이 단언은 «공허하지 않다».
    """
    r = row(db_session, status="FAILED", processed_chain=True)
    _body, by_id = rows_of(client)
    assert r.id not in by_id, "실패 행이 「앞으로 돌 것」 목록에 있다"


def test_a_retrying_row_stays_because_it_will_run_again(client, db_session):
    """⚠️ 대조군 — 실패를 빼면서 «다시 돌 것»까지 빼면 화면의 주어가 또 틀어진다.
    RETRYING 은 `processed_chain=false` 라 그대로 든다."""
    r = row(db_session, status="RETRYING", processed_chain=False)
    _body, by_id = rows_of(client)
    assert r.id in by_id, "다시 돌 행인데 목록에서 빠졌다"


def test_the_header_says_the_population_it_actually_read(client, db_session):
    """🔴 그 문자열이 «화면 머리»에 그대로 나간다. 모집단을 바꾸고 이 줄을 안 고치면
    화면이 「failed 도 본다」고 말하면서 안 본다 — 말이 기제보다 오래 산다."""
    body = client.get(URL).json()
    assert "failed" not in body["population"], body["population"]
    assert "undelivered" in body["population"]


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
    """게이트 ⑨.

    ⚠️ 커서를 «내 행 바로 앞»에서 시작한다. 오름차순이라 목록의 머리는 «제일 오래된» 행이고,
       그건 다른 시험이 넣은 행이다. 앞 판(내림차순)에서는 방금 넣은 행이 머리라 이 시험이
       그냥 통과했는데, 그건 정렬 덕분이지 이 시험이 자기 모집단을 잡아서가 아니었다.
    """
    made = [row(db_session, table_name="t").id for _ in range(5)]
    start = made[0] - 1

    first = client.get(URL, params={"limit": 2, "cursor": start}).json()
    seen = [r["outbox_id"] for r in first["rows"]]
    cursor = first["listed"]["next_cursor"]
    assert cursor is not None, "잘렸는데 커서를 «안» 줬다"

    second = client.get(URL, params={"limit": 2, "cursor": cursor}).json()
    seen += [r["outbox_id"] for r in second["rows"]]

    assert seen == made[:4], "두 쪽이 내 다섯 행의 앞 넷과 «순서까지» 같아야 한다: %r" % (seen,)
    assert len(seen) == len(set(seen)), "페이지 사이에 행이 «겹쳤다»"

    # 🔴 「잘렸다」는 «서버 상한»에 대한 말이다. 5행짜리 큐를 2씩 넘기는 동안 한 번도
    #    참이면 안 된다 — 참이면 화면이 «없는 누락»을 그린다.
    assert first["listed"]["capped"] is False
    assert second["listed"]["capped"] is False


def test_the_head_of_the_list_is_the_oldest_waiting_row(client, db_session):
    """🔴 [총괄 판정] 이 화면을 여는 이유가 「무엇이 막혔나」라 가장 오래 기다린 행이
    «머리»에 와야 한다. 그리고 목록의 머리가 곧 그 행이므로 「가장 오래된 행」을 «별도
    질의»로 둘 이유가 없다 — 두 수가 다른 순간에서 나오는 틈이 구조적으로 없다.

    ⚠️ 대조군이 «먼저 넣은 행»이다. 뒤에 넣은 행이 머리에 오면 이 줄이 운다."""
    oldest = row(db_session, table_name="t")
    newer = row(db_session, table_name="t")

    body = client.get(URL, params={"limit": 200, "cursor": oldest.id - 1}).json()
    ids = [r["outbox_id"] for r in body["rows"]]
    assert oldest.id in ids and newer.id in ids, "픽스처 두 행이 다 안 보인다"
    assert ids.index(oldest.id) < ids.index(newer.id), (
        "나중에 들어온 행이 «머리»에 있다 — 막힌 것을 찾으려면 스크롤해야 한다")


def test_a_switched_off_rule_survives_the_real_loader(client, db_session, monkeypatch,
                                                      tmp_path):
    """🔴 앞 시험은 로더를 «대신»해서 꺼진 규칙을 건네준다 — 그건 「라우트가 그린다」이지
    「로더가 건넨다」가 아니다. 한 시간 전에 이 게이트의 «바닥»이 비어 있는 걸 찾았으니
    같은 모양을 또 두지 않는다. 실제 `load_chain_rules()` 로 잰다.

    ⚠️ 파일에 적힌 선언은 `enabled: false` 여도 로더가 «들고 온다»(`kept` 루프에 enabled
       검사가 없다). 그래서 운영자가 꺼 둔 규칙이 화면에서 «사라지지» 않는다.
    """
    import json as _json

    from chain import ingestion_worker as w

    path = tmp_path / "chain_rules.json"
    path.write_text(_json.dumps({"rules": [
        {"name": "off_on_disk", "trigger_table": "t", "enabled": False,
         "mapper_module": "mappers.x", "mapper_function": "build"},
    ]}), encoding="utf-8")
    monkeypatch.setattr(w, "RULES_PATH", str(path))

    assert "off_on_disk" in {r.get("name") for r in w.load_chain_rules()}, \
        "로더가 꺼진 선언을 «버렸다» — 그러면 화면의 why_not 은 영원히 안 나온다"

    body = client.get(URL).json()
    assert "off_on_disk" in body["rules_known"]


# ---------------------------------------------------------------------------
# 상태 함수 자체 — 「빈 칸」이 없다
# ---------------------------------------------------------------------------

def test_every_combination_of_the_two_columns_gets_an_answer():
    """⚠️ 빈 칸은 빼지 말고 «단언»한다 — 빠진 칸은 「통과」로 읽힌다."""
    for processed in (False, True):
        for status in ("PENDING", "RETRYING", "SUCCESS", "FAILED", "WAT", None):
            state, _detail = event_constants.chain_state_of(processed, status)
            assert state in event_constants.CHAIN_STATES, (processed, status)


def test_a_population_that_is_exactly_the_page_says_there_is_no_more(client, db_session):
    """🔴 [Q-201 QA] 「더 있나」를 «쪽이 꽉 찼나»로 가늠하면 인구가 정확히 그만큼일 때
    빠진 것이 «없는데도» 「더 있다/잘렸다」가 된다. 첫 수리는 그 거짓 양성의 «경계»만
    옮겼고 부류는 같았다 — 한 행 더 읽어야 재는 것이 된다.

    ⚠️ 대조군이 두 줄이다: 인구 «딱 3» 이면 커서가 없고, 하나 더 있으면 커서가 나온다.
       아래 줄이 없으면 「커서는 늘 None」으로도 이 시험이 통과한다."""
    made = [row(db_session, table_name="t").id for _ in range(3)]
    start = made[0] - 1

    exact = client.get(URL, params={"limit": 3, "cursor": start}).json()
    assert [r["outbox_id"] for r in exact["rows"]] == made
    assert exact["listed"]["next_cursor"] is None, (
        "인구가 딱 한 쪽인데 «더 있다»고 말한다")
    assert exact["listed"]["capped"] is False

    row(db_session, table_name="t")
    more = client.get(URL, params={"limit": 3, "cursor": start}).json()
    assert more["listed"]["next_cursor"] is not None, (
        "넷째 행이 있는데 «더 없다»고 말한다 — 대조군이 무너졌다")


def test_capped_is_about_the_request_not_the_list(client, db_session):
    """⚠️ `capped` 는 「네가 물은 수를 서버가 깎았나」다. 한 칸이 두 물음에 답하지 않는다."""
    row(db_session, table_name="t")
    assert client.get(URL, params={"limit": 5}).json()["listed"]["capped"] is False
    assert client.get(URL, params={"limit": 9999}).json()["listed"]["capped"] is True
