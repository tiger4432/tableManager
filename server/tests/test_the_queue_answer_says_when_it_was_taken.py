# -*- coding: utf-8 -*-
"""큐 패널의 수들이 «언제» 것인지를 응답이 말하지 않았다 — 발신이 «아예» 없었다.

🔴 이 라우트는 「씹히는 것 같다」를 수로 바꾸는 자리인데, 새로 고치지 않은 화면은 그 수를
«현재형»으로 말한다. 같아 보이는 0 들 중 「지나가는 중이라서」가 정확히 이 부류다.
정본은 걷기 응답의 같은 키(`generated_at`, `4f51c3c2`)이고, 다른 것은 «라우트»뿐이다.

🔴 그리고 이 라운드는 「칸 하나 추가」가 아니었다. 이 핸들러는 「지금」을 «두 번» 말하고
있었다 — `oldest_seconds` 가 자기 `now()` 를, 그 아래 `_age()` 가 또 하나를 잡았다.
거기에 셋째를 더하면 이 칸은 「그 수를 만든 시각」이 아니라 «그 줄을 실행한 시각»이 된다.
그래서 응답의 「지금」을 «하나»로 모으고 그것을 낸다.
⚠️ 오늘 그 차이는 «마이크로초»라 안 보인다. 보이는 날은 이 라우트에 캐시가 생기는 날이고,
   판정 45 의 게이트 ①이 겨냥한 것이 정확히 그날이다. 그래서 «값»과 «모양»을 둘 다 잰다.

⚠️ 이 DB 는 다른 시험의 대기 행을 들고 있다. 그래서 「큐가 비었을 때」를 픽스처로 못 만든다 —
   비우려면 남의 행을 건드려야 한다. 그 물음(「성공에도 오나」)은 «모양»으로 답한다.
"""
import ast
import datetime as _dt
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import models                                      # noqa: E402

TX = "tx-generated-at-probe"
#: 고정 과거 시각. naive 로 넣는다 — 두 dialect 다 이 컬럼에 UTC 를 넣고, 핸들러가
#: naive 를 UTC 로 읽는다. 그 규약이 참이어야 아래 나이 계산이 성립한다.
PLANTED = _dt.datetime(2026, 1, 1, 0, 0, 0)

MAIN_PY = os.path.join(os.path.dirname(__file__), "..", "main.py")


def _headers():
    return {"X-Admin-Token": os.environ.get("ADMIN_TOKEN", "")}


def _queue(client):
    return client.get("/admin/chain/queue", headers=_headers()).json()


def _plant(db, created_at=PLANTED):
    db.add(models.DatabaseOutbox(
        event_uuid=str(uuid.uuid4()), table_name="dt_map", event_type="ROW_UPDATED",
        payload=json.dumps({"transaction_id": TX}), processed_chain=False,
        created_at=created_at))
    db.flush()


def _handler():
    tree = ast.parse(open(MAIN_PY, encoding="utf-8").read())
    return next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == "get_chain_queue_depth")


def _handler_code():
    """🔴 인용은 호출이 아니다 — 주석과 docstring 을 «먼저» 걷어낸다."""
    lines = open(MAIN_PY, encoding="utf-8").read().splitlines()
    fn = _handler()
    doc = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            doc.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    return "\n".join(lines[n - 1] for n in range(fn.lineno, (fn.end_lineno or fn.lineno) + 1)
                     if n not in doc and not lines[n - 1].lstrip().startswith("#"))


# ============================================ 1. 실린다, 그리고 «있음»이 아니라 «값»이다

def test_the_response_carries_a_parsable_instant(client):
    """⛔ 키만 재면 `null` 도 통과한다."""
    body = _queue(client)
    assert "generated_at" in body, "the route still has no sender"
    stamped = _dt.datetime.fromisoformat(body["generated_at"])
    assert stamped.tzinfo is not None, "an instant without a zone is two instants"
    assert stamped.utcoffset() == _dt.timedelta(0), "the envelope is UTC"


def test_it_is_not_conditional_on_there_being_rows():
    """🔴 「이 칸이 «성공에도» 오나」 — 와야 화면에서 그 칸의 «없음»이 「옛 서버」 하나만 뜻한다.
    반환이 «하나»이고 이 칸이 그 dict 의 «직접 키»면 「행이 있을 때만」이 성립할 수 없다."""
    #: 중첩 def(`_age`)의 return 은 빼고 «핸들러 자신»의 것만 센다 — 그 함수의 return 은
    #: 나이 하나이지 «응답»이 아니다. 안 빼면 이 단언이 3 을 세고 뜻이 사라진다.
    fn = _handler()
    nested = {n for d in ast.walk(fn) if isinstance(d, ast.FunctionDef) and d is not fn
              for n in ast.walk(d)}
    returns = [n for n in ast.walk(fn)
               if isinstance(n, ast.Return) and n not in nested]
    assert len(returns) == 1, "a second return is a path that answers without this column"
    keys = [k.value for k in returns[0].value.keys if isinstance(k, ast.Constant)]
    assert "generated_at" in keys, "the column is not a direct key of the one response"


# ============ 2. 「그 수를 «만든» 시각」이지 「이 줄을 «실행한» 시각」이 아니다 — 이 라운드의 판별식

def test_the_instant_is_the_one_the_ages_were_taken_at(client, db_session):
    """심은 행의 나이와 이 칸이 «같은 순간»에서 나와야 「기준 시각」이 옆의 수들을 설명한다.
    ⛔ 「있고 파싱된다」로는 이것을 증명하지 못한다 — 둘째 `now()` 를 넣어도 그 단언은 초록이고
       값만 «항상 신선»해진다."""
    _plant(db_session)
    body = _queue(client)

    group = next(g for g in body["waiting_transactions"] if g["transaction_id"] == TX)
    stamped = _dt.datetime.fromisoformat(body["generated_at"])
    planted = PLANTED.replace(tzinfo=_dt.timezone.utc)

    assert (stamped - planted).total_seconds() == group["waiting_seconds"], \
        "generated_at and the ages came from DIFFERENT instants"


def test_the_handler_reads_the_clock_exactly_once():
    """⚠️ 값 단언만으로는 두 `now()` 사이가 «시계 한 틱보다 짧을 때» 빠져나간다. 그래서 모양도
    못 박는다 — 이 응답의 「지금」은 «하나»이고, 그것이 `oldest_seconds` 자리까지 덮는다."""
    code = _handler_code()
    assert code.count("datetime.now(") == 1, \
        "the response says 'now' more than once; generated_at then explains only itself"
    assert '"generated_at": now_utc.isoformat()' in code, \
        "the field no longer rides the instant the ages were taken at"


# ============================================================ 3. 철자 «하나»

def test_no_second_spelling_reached_this_route(client):
    """⛔ 후보 넷에서 «어울리는 것»을 고르면 한 뜻에 철자가 둘이 된다(판정 45).
    `last_updated` 는 특히 — `/admin/auto-update/status` 의 칸이라 이미 «다른 뜻»으로 산다."""
    body = _queue(client)
    code = _handler_code()
    for spelling in ("as_of", "checked_at", "last_updated"):
        assert spelling not in body, "a second spelling of the same fact: %s" % spelling
        assert spelling not in code


# ============================================================ 4. 무회귀

def test_every_column_this_route_already_had_is_still_there(client, db_session):
    """이 라운드는 «말하기»이지 «바꾸기»가 아니다."""
    _plant(db_session)
    body = _queue(client)
    for key in ("waiting", "running", "loop_in_this_process", "log_filename",
                "loop_uptime_seconds", "mapper_reload_age_seconds", "waiting_by_owner",
                "oldest_waiting_seconds", "oldest_waiting_at", "retried_among_waiting",
                "waiting_transactions", "listed", "not_measured"):
        assert key in body, "the round dropped an existing column: %s" % key
    #: ⚠️ 절대 수를 못 박지 않는다 — 남의 대기 행이 생기는 날 «이 시험»이 빨개진다.
    assert body["waiting"] >= 1
    assert any(g["transaction_id"] == TX for g in body["waiting_transactions"])
    assert body["listed"]["capped"] is False
