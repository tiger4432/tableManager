# -*- coding: utf-8 -*-
"""코어 답만 「기준을 무엇으로 골랐나」를 말하지 않았다 (S-15 ①-a-0 · 판정 101).

S-9b 가 테이프 답의 `by_core[].frame_basis` 를 지었다 — 코어마다 확정으로 골랐는지 역할
순서로 물러났는지를 «말하게» 한 것이다. 그런데 «코어 자신»이 주어인 답에는 그 칸이 없었고,
그래서 그 화면에서는 「확정으로 골랐다」와 「이 서버는 그 말을 안 한다」가 «같은 침묵»이었다.

🔴 재료는 «이미 있었다** — `_canonical_origin_meta` 의 `basis_out` 폴백(판정 96)이 그 답을
   만든다. 없던 것은 «나르개**다. S-36(대기열 payload)·S-39(문지기 사유)와 같은 부류다.

⚠️ `by_core` 는 «만들지 않는다**. 「코어 답엔 by_core 가 없다」는 기존 계약이고
   (`test_transfer_plan` 이 못 박는다), 여기서 물을 코어는 «자기 자신» 하나뿐이다.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from test_transfer_plan import _seed_scenario, tp_env            # noqa: F401,E402

BASIS_KEYS = {"kind", "reason", "roles"}


def _core(client, lot="CORE-A", slot="01"):
    res = client.get("/api/transfer-plan/source-summary",
                     params={"stage": "dt", "lot": lot, "slot": slot})
    assert res.status_code == 200, res.text
    return res.json()


def _tape(client):
    res = client.get("/api/transfer-plan/source-summary",
                     params={"stage": "bonding", "lot": "TAPE-X", "slot": "01"})
    assert res.status_code == 200, res.text
    return res.json()


def test_a_core_answer_carries_its_own_basis(tp_env, client):
    """🔴 결함 그 자체. 이 칸이 없으면 화면은 「확정」과 「말 안 함」을 구별 못 한다."""
    _seed_scenario(tp_env)
    body = _core(client)
    assert body["source_kind"] == "core", "fixture lost its axis"
    assert "frame_basis" in body, sorted(body)
    basis = body["frame_basis"]
    assert basis is not None, "a silent None is the state this round removes"
    assert basis["kind"] == "role_order", basis
    assert basis["reason"] == "not_declared", basis
    assert basis["roles"], "roles must name the order it fell back to"


def test_the_two_answers_speak_the_same_shape(tp_env, client):
    """🔴 «같은 함수»에서 나온다. 두 답이 같은 사실을 다른 모양으로 말하면 화면이 독자를
    둘 들게 되고, 그 둘은 갈라져도 오류를 안 낸다(기준 ④)."""
    _seed_scenario(tp_env)
    core_basis = _core(client)["frame_basis"]
    tape_basis = _tape(client)["by_core"][0]["frame_basis"]

    assert BASIS_KEYS <= set(core_basis), core_basis
    assert BASIS_KEYS <= set(tape_basis), tape_basis
    assert set(core_basis) == set(tape_basis), (core_basis, tape_basis)
    assert core_basis["kind"] == tape_basis["kind"]
    assert core_basis["roles"] == tape_basis["roles"], "the declared order is one list"


def test_the_core_answer_still_has_no_by_core(tp_env, client):
    """⚠️ 이 라운드가 «안 한» 것. 코어 답에 by_core 를 만들면 「코어 하나의 답」이
    「코어 목록의 답」인 척한다 — 기존 계약을 되돌리지 않았다."""
    _seed_scenario(tp_env)
    body = _core(client)
    assert "by_core" not in body, sorted(body)
    assert "by_core_origin" not in body and "by_core_truncated" not in body


def test_no_other_key_moved(tp_env, client):
    """㉡ 기존 키 «바이트 동일». 더한 것은 `frame_basis` «하나»다."""
    _seed_scenario(tp_env)
    body = _core(client)
    before = {"chips", "history", "identity", "inactive_subtractions",
              "source_kind", "sources", "stage", "warnings"}
    assert set(body) - before == {"frame_basis"}, sorted(set(body) - before)
    # 그리고 그 값들은 이 라운드 «앞»의 그것 그대로다.
    assert body["chips"] == {
        "total": 36,
        "fail_breakdown": {"defect": 2, "eds_fail": 1},
        "transferred": 0,
        "remaining": 33,
        "remaining_reliable": True,
    }
    assert body["sources"]["transfer_log"] == "connected"
    assert body["sources"]["eds_fail"] == "connected"
