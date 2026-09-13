# -*- coding: utf-8 -*-
"""소급 행은 자기가 «무엇인지» 이미 적어 두는데 대기열이 그것을 버렸다 (S-36).

`retroactive.publish` 는 아웃박스 행의 payload 에 `{run_id, op, params, requested_by}` 를
쓴다. 그런데 `/admin/chain/queue` 는 그 payload 에서 `transaction_id` «하나»만 읽었고,
소급 행에는 그 키가 없어서 화면에 이렇게 나갔다:

    (no tx · outbox#12) · 표 «없음»(자리표는 옳게 빠졌다) · event_type 하나

즉 「누가 · 무슨 op · 어느 인자로」가 «그 행 안에 있는데» 응답에 자리가 없었다. 없는 사실을
만드는 라운드가 아니라, 이미 있는 사실을 «싣는» 라운드다 — 형제 시험
`test_a_control_event_names_no_table.py` 와 같은 부류(읽는 쪽이 고쳐진다)다.

🔴 세 상태를 «응답»에서 단언한다:
    소급 행이 안 섞임        -> `retroactive` 키 «없음»   (해당 없음)
    섞였고 아무도 안 적음    -> `requested_by` 가 `None`  (물었는데 답이 없다)
    섞였고 적음              -> 그 이름
앞 둘을 접으면 「소급이 아니다」와 「소급인데 요청자가 없다」가 같은 픽셀이 된다.
"""
import json
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import event_constants                                           # noqa: E402
from admin import retroactive                                               # noqa: E402
from database import models                                      # noqa: E402


def _outbox(db, *, event_type, table_name, payload):
    db.add(models.DatabaseOutbox(
        event_uuid=str(uuid.uuid4()), table_name=table_name, event_type=event_type,
        payload=json.dumps(payload, ensure_ascii=False), processed_chain=False))
    db.flush()


def _groups(client):
    body = client.get("/admin/chain/queue",
                      headers={"X-Admin-Token": os.environ.get("ADMIN_TOKEN", "")}).json()
    return body.get("waiting_transactions", [])


def _mine(client, run_id="abc123def456"):
    """이 스위트는 공유 세션을 쓰고 다른 픽스처의 대기 행이 같이 눈다 —
    «하나»를 가정하면 그 가정이 답을 정한다. 내 행을 `run_id` 로 골라 집는다."""
    hits = [g for g in _groups(client)
            if any(r.get("run_id") == run_id for r in g.get("retroactive", []))]
    assert len(hits) == 1, [g["transaction_id"] for g in _groups(client)]
    return hits[0]


def _plain(client, tx):
    hits = [g for g in _groups(client) if g["transaction_id"] == tx]
    assert len(hits) == 1, [g["transaction_id"] for g in _groups(client)]
    return hits[0]


PAYLOAD = {"run_id": "abc123def456", "op": "withdraw",
           "params": {"table": "dt_map", "source": "pipeline_parser"},
           "requested_by": "kim"}


def test_the_waiting_row_carries_the_four_facts_its_payload_already_holds(client, db_session):
    """🔴 결함 그 자체. 넷 다 payload 에 «있었고» 응답에 «없었다»."""
    _outbox(db_session, event_type=retroactive.RUN_EVENT_TYPE,
            table_name=retroactive.RUN_EVENT_TABLE, payload=PAYLOAD)

    g = _mine(client)
    assert "retroactive" in g, g
    assert len(g["retroactive"]) == 1, g["retroactive"]
    got = g["retroactive"][0]
    assert got["run_id"] == "abc123def456", got
    assert got["op"] == "withdraw", got
    assert got["requested_by"] == "kim", got
    assert got["params"] == {"table": "dt_map", "source": "pipeline_parser"}, got


def test_an_unrequested_run_says_none_rather_than_inventing_an_author(client, db_session):
    """`publish` 는 「admin」을 «지어내지 않는다** — 그 정직함이 여기까지 와야 한다."""
    _outbox(db_session, event_type=retroactive.RUN_EVENT_TYPE,
            table_name=retroactive.RUN_EVENT_TABLE,
            payload=dict(PAYLOAD, requested_by=None))

    got = _mine(client)["retroactive"][0]
    assert got["requested_by"] is None, got
    # 나머지 셋은 그대로 실린다 — 한 칸이 비었다고 묶음이 빠지지 않는다.
    assert got["op"] == "withdraw" and got["run_id"] == "abc123def456", got


def test_a_non_retroactive_row_has_no_such_key_at_all(client, db_session):
    """키 «부재»가 「소급이 아니다」의 철자다. `None` 이면 「소급인데 못 읽었다」와 겹친다."""
    _outbox(db_session, event_type="CREATE", table_name="dt_map",
            payload={"transaction_id": "tx-plain"})

    g = _plain(client, "tx-plain")
    assert "retroactive" not in g, g
    # ㉡ 이벤트 행은 «그대로**: 표 이름이 곧 트리거 표이고 그 자리는 안 건드렸다.
    assert g["tables"] == ["dt_map"], g
    assert g["transaction_id"] == "tx-plain", g


def test_the_placeholder_still_never_reaches_the_table_list(client, db_session):
    """㉢ 자리표는 그대로 «안 실린다** — 이 라운드가 그 규율을 되돌리지 않았다."""
    _outbox(db_session, event_type=retroactive.RUN_EVENT_TYPE,
            table_name=retroactive.RUN_EVENT_TABLE, payload=PAYLOAD)

    g = _mine(client)
    assert g["tables"] == [], g
    assert event_constants.RETROACTIVE_RUN_TABLE not in g["tables"]
    # 신원은 여전히 event_type 이 말한다.
    assert retroactive.RUN_EVENT_TYPE in g["event_types"], g
