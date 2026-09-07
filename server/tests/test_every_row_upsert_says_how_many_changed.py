# -*- coding: utf-8 -*-
"""한 발신자«만» 「몇 칸을 바꿨나」를 안 실었다 — 그래서 그 경로에서만 답이 «없었다».

🔴 이건 새 계약이 아니다. `event_constants.py` 가 이미 적어 두었다:
「`change_count` IS ALWAYS PRESENT, INCLUDING WHEN IT IS 0 … `{change_count: 0}` 과
 «키 부재»는 다르다」. 여섯 발신자 중 «다섯»이 지키고 있었고 체인 워커 하나가 안 지켰다.

⚠️ 그래서 이 파일은 «그 한 자리»를 재지 않는다 — «부류»를 잰다. 낱개로 고치면 다음 발신자가
같은 자리에서 같은 것을 빠뜨리고, 그때도 «오류가 안 난다». 빠진 칸은 화면에서 0 으로 읽힌다.

🔵 읽는 쪽 «수»: 이 필드(«웹소켓» 쪽)의 클라 독자는 «0» 이다 — `client2/src` 의 `change_count`
히트 넷은 전부 HTTP 응답 본문이고 `websocket.js` 는 그 이름을 안 읽는다. 그러므로 이 라운드는
「화면이 바뀐다」가 아니라 «계약을 어긴 자리를 맞춘다»이다.
"""
import ast
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import event_constants                                           # noqa: E402

SERVER = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
#: 이 이벤트를 «내는» 모듈. 새 모듈이 생기면 여기 한 줄이고, 그 한 줄이 곧 「누가 발신자인가」다.
EMITTERS = ("main.py", "chain_ingestion_worker.py", "chain_replay.py", "run_watcher.py")


def _upsert_dicts():
    """`{"event": "batch_row_upsert", ...}` 리터럴 전부 → (파일, 줄, 키집합).

    🔴 리터럴 문자열이 아니라 «키 집합»으로 찾는다. `grep "change_count"` 는 주석에도 걸리고
       (인용은 발신이 아니다), 키가 «없는» 것을 세지 못한다."""
    found = []
    for name in EMITTERS:
        path = os.path.join(SERVER, name)
        if not os.path.exists(path):
            continue
        for node in ast.walk(ast.parse(open(path, encoding="utf-8").read())):
            if not isinstance(node, ast.Dict):
                continue
            keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
            event = next((v.value for k, v in zip(node.keys, node.values)
                          if isinstance(k, ast.Constant) and k.value == "event"
                          and isinstance(v, ast.Constant)), None)
            if event == "batch_row_upsert":
                found.append((name, node.lineno, keys))
    return found


# ============================================ 1. 부류 — «모든» 발신자가 싣는다

def test_every_emitter_carries_the_count():
    emitters = _upsert_dicts()
    assert len(emitters) >= 6, "the census found fewer emitters than exist: %d" % len(emitters)
    missing = [(n, ln) for n, ln, keys in emitters if "change_count" not in keys]
    assert missing == [], "these emitters say nothing about how many changed: %s" % missing


def test_the_chain_worker_is_one_of_them():
    """그 하나가 «이 줄의 주어»였다. 부류 단언이 6 을 세는 한 이 단언은 중복처럼 보이지만,
    발신자가 «줄어드는» 날 부류 단언은 여전히 초록이고 이것만 빨개진다."""
    workers = [(ln, keys) for n, ln, keys in _upsert_dicts()
               if n == "chain_ingestion_worker.py"]
    assert workers, "the chain worker stopped emitting this event at all"
    for _ln, keys in workers:
        assert "change_count" in keys


def test_the_count_is_what_this_message_carries():
    """🔴 `len(results)` 가 아니라 «실린 항목 수»다. 지금은 둘이 같지만(그 자리 불변 주석),
    불변이 깨지는 날 이 수는 메시지에 대해 계속 참이고 `len(results)` 는 과대가 된다."""
    src = open(os.path.join(SERVER, "chain_ingestion_worker.py"), encoding="utf-8").read()
    assert '"change_count": len(msg_items),' in src
    assert '"items": msg_items,' in src, "the count and the payload came apart"


# ============================================ 2. 계약 — 「0 과 부재는 다르다」

def test_zero_is_a_value_not_an_absence():
    """⚠️ 이 규칙이 이 라운드의 «근거»다. 키가 없으면 화면은 0 으로 읽고, 그건 「안 바뀌었다」와
    「말하지 않았다」를 같은 픽셀로 만든다."""
    msg = event_constants.batch_refresh_message("t", 0)
    assert "change_count" in msg
    assert msg["change_count"] == 0


def test_the_rule_is_written_where_the_message_is_built():
    """다음 사람이 그 규칙을 «다시 유도»하지 않도록, 규칙이 헬퍼 옆에 있는지 잰다."""
    src = open(os.path.join(SERVER, "event_constants.py"), encoding="utf-8").read()
    assert "ALWAYS PRESENT" in src and "change_count" in src
