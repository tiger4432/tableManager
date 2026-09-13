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
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from maps import frame_confirmation as fc                                  # noqa: E402
from test_transfer_plan import _seed_scenario, tp_env            # noqa: F401,E402

CORE_MAP = "tp_test_core_defect_map"
CORE_MAP_ID = "CORE-A_01"
#: 확정 기록은 «단위»에 쓴다. 이 시험의 단위는 코어 자신이다.
RULE = {"name": "core_frame_attribution", "derived_table": "eqp_frame_attribution",
        "decision_key": ["lot", "slot"], "target_fields": ["core_frame"]}


def _contrib(role, source_name, **kw):
    d = {"role": role, "source_table": CORE_MAP, "map_id": CORE_MAP_ID,
         "source_name": source_name, "applied_frame": "rot0_front",
         "shift_dx": 0, "shift_dy": 0}
    d.update(kw)
    return d


def _confirm(db, contributors, reference=None):
    return fc.record_confirmation(
        db, RULE, {"lot": "CORE-A", "slot": "01"}, contributors,
        confirmed_by="tester", frames={"core_frame": "rot0_front"},
        reference=reference or {"table": CORE_MAP, "map_id": CORE_MAP_ID})

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
    # [S-40] eds 맵은 rot180 이라 이제 좌표를 «옴겨서» 세고 그 사실을 말한다.
    #    위  는 그대로다 — 회전은 «위치»를 바꾸지 «개수»를 안 바꿔다.
    assert body["sources"]["eds_fail"] == "connected(aligned:180)"


# ---------------------------------------------------------------------------
# ㈟ [정정 · 판정 103] 확정이 있는 코어는 「확정으로 골랐다」고 말한다
# — 종전 이 갈래는 «도달 불가»였고, 그래서 첫 게이트가 «상수를 상수라» 단언했다.
# ---------------------------------------------------------------------------

def test_a_confirmed_core_says_confirmation_not_role_order(tp_env, client):
    """🔴 이 라운드의 판별식. 이것이 «새 갈래»이고, 종전엔 들어갈 수가 없었다.

    종전 자리는 `frame == "origin"` 원천만 모으는 함수를 물었고, 코어 단계는 그런
    원천을 선언하지 않는다 — 그래서 확정을 아무리 기록해도 답이 role_order 였다.
    """
    _seed_scenario(tp_env)
    _confirm(tp_env, [_contrib("total_chips", "user"),
                      _contrib("defect", "chain_ingestion")])
    tp_env.commit()

    basis = _core(client)["frame_basis"]
    assert basis["kind"] == "confirmation", basis
    assert basis["confirmation_uid"], basis
    assert basis["reference"] == {"table": CORE_MAP, "map_id": CORE_MAP_ID}, basis
    # 그리고 «보증»이 같이 온다 — ①-a-1 이 그것을 읽는다.
    assert "warrant" in basis, basis


def test_an_unconfirmed_core_still_falls_back_and_says_so(tp_env, client):
    """㈞ 확정이 없으면 종전과 «같은» 답 — 이 라운드가 바꾸는 것은 그 갈래가 아니다."""
    _seed_scenario(tp_env)
    basis = _core(client)["frame_basis"]
    assert basis["kind"] == "role_order", basis
    assert basis["reason"] == "not_declared", basis


def test_the_tape_answer_did_not_move(tp_env, client):
    """㈡ 테이프 답은 «바이트 동일» — 이 정정은 코어 갈래만 건드렸다."""
    _seed_scenario(tp_env)
    tape = _tape(client)
    assert "frame_basis" not in tape, sorted(tape)
    assert tape["by_core"][0]["frame_basis"]["kind"] == "role_order"


def test_a_confirmation_reached_only_through_a_fail_source_still_counts(tp_env, client):
    """🔴 목록이 «어느 원천까지» 세는지의 판별식.

    앞 시험의 확정은 `total_chips` 와 «같은 표»(core_defect_map)에 걸려 있어, 목록에서
    fail 원천을 빼도 여전히 찾아진다 — 즉 그 변이를 «못 가른다**(실측 2026-09-07: 살아 나옴).
    이 확정은 eds 맵에만 걸린다. 자기 프레임의 fail 원천이 목록에서 빠지면 «못 찾는다**.
    """
    _seed_scenario(tp_env)
    eds = "tp_test_eds_fail_map"
    _confirm(tp_env,
             [_contrib("eds_fail", "user", source_table=eds),
              _contrib("defect", "chain_ingestion", source_table=eds)],
             reference={"table": eds, "map_id": CORE_MAP_ID})
    tp_env.commit()

    basis = _core(client)["frame_basis"]
    assert basis["kind"] == "confirmation", basis
    assert basis["reference"]["table"] == eds, basis


# ---------------------------------------------------------------------------
# ①-a-1 [판정 102] 「정렬은 됐는데 근거가 약하다」 — 그 중간 등급이 M2 에도 온다
# ---------------------------------------------------------------------------

def test_a_weakly_warranted_core_wears_the_middle_rung(tp_env, client):
    """🔴 M1 만 말하던 등급. `warrant` 는 M2 에 «한 번도» 안 나오던 낱말이었다(실측 0회).

    최약 기여자가 서열 미등재면 그 판은 자기가 이름 댄 프레임을 «보증하지 못한다** —
    그런데 변환은 «됐으므로** `align_unavailable` 도 거짓이다. 그 사이의 등급이다.
    """
    _seed_scenario(tp_env)
    _confirm(tp_env, [_contrib("total_chips", "user"),
                      _contrib("defect", "trace_fixture_dt_log.csv")])   # 서열 미등재
    tp_env.commit()

    body = _core(client)
    assert body["frame_basis"]["kind"] == "confirmation", body["frame_basis"]
    assert body["frame_basis"]["warrant"] == "not_declared", body["frame_basis"]
    # 어느 끝도 아니다: 맨 `connected` 도, `align_unavailable` 도 아니다.
    assert body["sources"]["total_chips"] == "connected(not_declared)", body["sources"]
    assert "align_unavailable" not in json.dumps(body["sources"])


def test_a_fully_ranked_core_does_not_wear_it(tp_env, client):
    """등급은 «벌어야» 한다. 기여자가 전부 서열에 있으면 맨 상태가 그대로 선다."""
    _seed_scenario(tp_env)
    _confirm(tp_env, [_contrib("total_chips", "user"),
                      _contrib("defect", "chain_ingestion")])
    tp_env.commit()

    sources = _core(client)["sources"]
    assert sources["total_chips"] == "connected", sources
    # ⚠️ «완화»의 not_declared 는 여기서 세지 않는다 — 다른 주어고 자리도 다르다.
    #    마커가 닿는 것은  상태뿐이다.
    marked = {k: v for k, v in sources.items() if str(v).startswith("connected")}
    assert "not_declared" not in json.dumps(marked), marked


def test_the_relaxations_own_not_declared_is_untouched(tp_env, client):
    """🔴 «같은 낱말, 다른 주어». 완화 규칙의 `not_declared` 는 「config 키가 아예 없다」이고
    중간 등급은 「확정은 있는데 보증할 서열이 없다」다 — 이 라운드가 앞엣것을 «안 건드린다**.

    선언이 없는 역할은 마커 «없이** 맨 `not_declared` 로 남는다(자리가 다르다: 저것은 상태
    «전체**, 이것은 `connected(...)` 안의 마커).
    """
    _seed_scenario(tp_env)
    sources = _core(client)["sources"]
    # dt 단계는 origin_log 를 선언하지 않는다 -> 완화의 not_declared
    assert sources.get("origin_log") == "not_declared", sources
    assert not sources["origin_log"].startswith("connected"), sources


def test_the_tape_answer_takes_the_weakest_core(tp_env, client):
    """합쳐진 것은 «최약 기여자»를 따라간다(스펙 §0.2 ⑨). 강한 쪽을 따르면 화면이
    「믿어도 된다」를 과하게 말한다."""
    _seed_scenario(tp_env)
    sources = _tape(client)["sources"]
    # 이 픽스처의 테이프는 확정이 없다 -> 보증 물음 자체가 없다 -> 마커 없음.
    assert "not_declared" not in json.dumps(
        {k: v for k, v in sources.items() if str(v).startswith("connected")}), sources
