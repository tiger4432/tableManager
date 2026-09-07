# -*- coding: utf-8 -*-
"""[Spec MAP_ALIGNMENT_SPEC 0.1/0.2] 계획(층 9)이 확정(층 8)을 읽는다 — **M2 표면에서**.

사슬은 계획에서 끝난다. 그 canonical 프레임 — 다른 모든 원천이 «그 위로» 정렬되는, 즉
N-ary 통합 결정 그 자체 — 는 종전 `CANONICAL_FRAME_ROLES` 라는 기록도 버전도 원천 목록도
없는 config 순서 튜플이 골랐다. 이 파일이 못 박는 것은 그것이 «확정 기록»으로 바뀌었다는
사실이고, 그 사실은 M1 이 은퇴해도 참이어야 한다.

🔴 [S-15 ①-a · 판정 103] 그래서 세계가 M1(`/api/bonding-plan/core-summary`, `bdp_env`)에서
   **M2**(`/api/transfer-plan/source-summary`, `tp_env`)로 옮겨졌다. 재는 사실은 «같고»
   표면만 바뀐다 — M1 이 은퇴하는 커밋에서 이 파일이 같이 죽으면 「확정이 프레임을 고른다」를
   «아무도 안 재게» 된다.

⚠️ 옮길 수 있게 된 것은 S-40(판정 106) 덕이다. 그 전에는 M2 코어 답이 자기 프레임 fail 을
   «정렬하지 않아» 아래 「마커 뒤집힘」이 관측되지 않았다(실측: 전/후 바이트 동일).

옮기면서 «죽은» 것 — 그리고 왜:
    · `PRE_EXISTING_KEYS` 가드   M1 «자기» 키 집합에 대한 라운드 가드다. M2 로 다시 쓰면
      그건 «다른 가드»이고, 판정 103 이 「M1 과 같이 죽는다」로 정했다
    · 「약한 확정 → 중간 등급」·「전부 서열 → 등급 없음」
      `test_a_core_answer_says_what_its_frame_stood_on.py` 가 M2 에서 «이미» 잰다.
      옮겨 오면 두 파일이 같은 사실을 재고, 그것이 시험 쪽의 기준 ④ 다

[격리] 표 이름 접두 `tp_test_*` — `test_transfer_plan.py` 와 공유하는 그 세계다.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import bonding_plan                                              # noqa: E402
import config_resolve_report                                     # noqa: E402
import frame_confirmation as fc                                  # noqa: E402
from test_transfer_plan import _seed_scenario, tp_env            # noqa: F401,E402

CORE_TABLE = "tp_test_core_defect_map"
EDS_TABLE = "tp_test_eds_fail_map"
MAP_ID = "CORE-A_01"

#: 확정은 «단위»에 쓰인다. M2 의 코어 답에서 그 단위는 코어 자신 `(lot, slot)` 이다 —
#: 컬럼 이름을 여기 적으면 그것이 결정 단위의 둘째 철자가 된다.
RULE = {"name": "core_frame_attribution",
        "derived_table": "eqp_frame_attribution",
        "decision_key": ["lot", "slot"],
        "target_fields": ["core_frame"]}


def _contrib(role, table, map_id, source_name, **kw):
    d = {"role": role, "source_table": table, "map_id": map_id,
         "source_name": source_name, "applied_frame": "rot0_front",
         "shift_dx": 0, "shift_dy": 0}
    d.update(kw)
    return d


def _confirm(db, contributors, reference=None, frames=None):
    return fc.record_confirmation(
        db, RULE, {"lot": "CORE-A", "slot": "01"}, contributors,
        confirmed_by="tester", frames=frames or {"core_frame": "rot0_front"},
        reference=reference)


def _summary(client, lot="CORE-A", slot="01", **params):
    """M2 의 코어 답. 종전 이 헬퍼는 M1 라우트를 쳤다.

    ⚠️ 응답 «모양»이 다른 자리는 «여기서» 번역한다 — 시험 본문이 각자 번역하면 그 번역이
       열 곳에 생긴다(판정 83 이 「번역은 헬퍼 안」이라 적은 이유).
    """
    res = client.get("/api/transfer-plan/source-summary",
                     params=dict(stage="dt", lot=lot, slot=slot, **params))
    assert res.status_code == 200, res.text
    body = res.json()
    chips = body.get("chips") or {}
    # M1 은 감산 종류를 chips 의 «형제 칸»으로 냈고 M2 는 `fail_breakdown` 안에 낸다.
    body["chips"] = dict(chips, **(chips.get("fail_breakdown") or {}))
    return body


# ---------------------------------------------------------------------------
# 1. 물러남 — 같은 답이되 «조용하지» 않다
# ---------------------------------------------------------------------------

def test_the_fallback_names_itself_rather_than_looking_identical(tp_env, client):
    """「확정 없음」은 payload 에서 «읽혀야» 한다 — 부재에서 «추론»되는 것이 아니라."""
    _seed_scenario(tp_env)
    basis = _summary(client)["frame_basis"]

    assert basis["kind"] == bonding_plan.BASIS_ROLE_ORDER
    assert basis["reason"] == config_resolve_report.REASON_NOT_DECLARED
    # 그리고 «무엇이» 정했는지 — 물러난 그 퇴화 규칙을 이름 댄다.
    assert basis["roles"] == list(bonding_plan.CANONICAL_FRAME_ROLES)
    assert "confirmation_uid" not in basis


# ---------------------------------------------------------------------------
# 2. 확정이 이긴다 — «어긋나게» 해서 증명한다
# ---------------------------------------------------------------------------

def test_the_confirmation_picks_the_frame_and_the_role_tuple_is_not_consulted(
        tp_env, client):
    """🔴 THE 시험. 역할 순서는 코어 맵(rot0)을, 확정은 EDS 맵(rot180)을 가리키게 만든다.

    확정을 «읽기만» 하고 튜플이 여전히 결정한다면 아래 마커가 «그대로»일 것이고 이 시험은
    깨진 코드에서도 통과한다. 그래서 둘을 어긋나게 하고 정렬 마커가 «뒤집혀야» 한다:
    보정이 필요 없던 쪽이 180 을 받고, 받던 쪽이 필요 없어진다.
    """
    _seed_scenario(tp_env)
    before = _summary(client)["sources"]
    assert before["defect"] == "connected", before
    assert before["eds_fail"] == "connected(aligned:180)", before

    _confirm(tp_env,
             [_contrib("total_chips", CORE_TABLE, MAP_ID, "user"),
              _contrib("defect", CORE_TABLE, MAP_ID, "chain_ingestion")],
             reference={"table": EDS_TABLE, "map_id": MAP_ID})
    tp_env.commit()

    after = _summary(client)
    assert after["frame_basis"]["kind"] == bonding_plan.BASIS_CONFIRMATION
    assert after["frame_basis"]["reference"] == {"table": EDS_TABLE, "map_id": MAP_ID}
    # 🔴 뒤집힘. 기준이 EDS 로 옮겨졌으므로 이제 «코어 쪽»이 보정을 받는다.
    assert after["sources"]["defect"] == "connected(aligned:180)", after["sources"]
    assert after["sources"]["eds_fail"] == "connected", after["sources"]


def test_a_superseded_confirmation_does_not_decide(tp_env, client):
    """봉인된 판은 답이 아니다. 한 단위에 판이 둘이면 «살아 있는» 것만 읽힌다."""
    _seed_scenario(tp_env)
    contributors = [_contrib("total_chips", CORE_TABLE, MAP_ID, "user"),
                    _contrib("defect", CORE_TABLE, MAP_ID, "chain_ingestion")]
    _confirm(tp_env, contributors, reference={"table": EDS_TABLE, "map_id": MAP_ID})
    # 같은 단위의 v2 가 v1 을 봉인하고 코어 맵을 가리킨다.
    _confirm(tp_env, contributors, reference={"table": CORE_TABLE, "map_id": MAP_ID})
    tp_env.commit()

    body = _summary(client)
    assert body["frame_basis"]["version"] == 2
    assert body["frame_basis"]["reference"] == {"table": CORE_TABLE, "map_id": MAP_ID}
    # v1 의 180° 바닥은 사라져야 한다 — 확정 전 마커로 되돌아온다.
    assert body["sources"]["eds_fail"] == "connected(aligned:180)", body["sources"]
    assert body["sources"]["defect"] == "connected", body["sources"]


def test_an_excluded_contributor_cannot_claim_the_confirmation(tp_env, client):
    """거절당한 원천은 «아무것에도» 정렬된 적이 없다.

    기록에는 남는다(안 그러면 「없음」과 「거절됨」이 구별되지 않는다). 다만 「이 계획의
    좌표계가 확정됐나」에 «예»라고 답할 수는 없다.
    """
    _seed_scenario(tp_env)
    _confirm(tp_env,
             [_contrib("total_chips", CORE_TABLE, MAP_ID, "user",
                       excluded_reason="meta_missing"),
              _contrib("defect", "some_other_table", "OTHER", "chain_ingestion")],
             reference={"table": EDS_TABLE, "map_id": MAP_ID})
    tp_env.commit()

    body = _summary(client)
    assert body["frame_basis"]["kind"] == bonding_plan.BASIS_ROLE_ORDER
    # 확정이 «안 섰으므로» 마커도 확정 전 그대로다.
    assert body["sources"]["eds_fail"] == "connected(aligned:180)", body["sources"]


# ---------------------------------------------------------------------------
# 3. 중간 등급 — 이 파일이 재는 것은 «다른 칸과 안 섞인다»는 사실이다
#    (등급 «자체»는 test_a_core_answer_says_what_its_frame_stood_on.py 가 M2 에서 잰다)
# ---------------------------------------------------------------------------

def test_the_middle_rung_does_not_fire_the_inactive_subtractions_footnote(tp_env, client):
    """`inactive_subtractions` 는 「이 감산이 «안 돌았다»」다. 약하게 보증된 defect 집계는
    «돌았다». 둘은 낱말을 공유하지만 칸을 공유해서는 안 된다."""
    _seed_scenario(tp_env)
    _confirm(tp_env,
             [_contrib("total_chips", CORE_TABLE, MAP_ID, "user"),
              _contrib("defect", CORE_TABLE, MAP_ID, "trace_fixture_dt_log.csv")],
             reference={"table": CORE_TABLE, "map_id": MAP_ID})
    tp_env.commit()

    body = _summary(client)
    assert "not_declared" in body["sources"]["defect"], body["sources"]
    # 재는 것은 「중간 등급이 «defect 를» 그 목록에 넣지 않는다」이다.
    assert "defect" not in (body.get("inactive_subtractions") or []), body
    assert body["chips"]["remaining"] is not None, "여전히 «수»다 — 아무것도 빠지지 않았다"


def test_the_middle_rung_is_not_a_sixth_token():
    """닫힌 어휘에 낱말을 더하는 것은 계약 변경이다. 등급을 정본 철자에 못 박아,
    상류에서 개명해도 둘째 철자가 남지 않게 한다."""
    assert fc.WARRANT_NOT_DECLARED == config_resolve_report.REASON_NOT_DECLARED
    assert bonding_plan.STATUS_NOT_DECLARED == config_resolve_report.REASON_NOT_DECLARED
    assert bonding_plan.BINDING_MAPPING_UNAVAILABLE == \
        config_resolve_report.REASON_MAPPING_UNAVAILABLE


# ---------------------------------------------------------------------------
# 4. 바닥을 못 주는 확정
# ---------------------------------------------------------------------------

def test_a_confirmation_with_no_reference_falls_back_but_still_names_itself(tp_env, client):
    """`map_alignment.REFERENCE_ABSENT` 는 흔하다. 공통 바닥 없이 채점된 판은 계획에 바닥을
    줄 수 없지만, 계획은 «어느 판이» 못 줬는지를 말해야 한다."""
    _seed_scenario(tp_env)
    h = _confirm(tp_env, [_contrib("total_chips", CORE_TABLE, MAP_ID, "user")],
                 reference=None)
    tp_env.commit()

    basis = _summary(client)["frame_basis"]
    assert basis["kind"] == bonding_plan.BASIS_ROLE_ORDER
    assert basis["reason"] == config_resolve_report.REASON_NOT_DECLARED
    assert basis["confirmation_uid"] == h.confirmation_uid


def test_an_unreadable_reference_is_mapping_unavailable_not_not_declared(tp_env, client):
    """수리가 둘이면 낱말도 둘이다. 「바닥을 선언한 적이 없다」는 선언하러 보내고,
    「선언한 바닥이 안 읽힌다」는 메타가 없는 그 맵으로 보낸다. 접으면 틀린 수리를 부른다."""
    _seed_scenario(tp_env)
    _confirm(tp_env, [_contrib("total_chips", CORE_TABLE, MAP_ID, "user")],
             reference={"table": CORE_TABLE, "map_id": "NO_SUCH_MAP"})
    tp_env.commit()

    basis = _summary(client)["frame_basis"]
    assert basis["kind"] == bonding_plan.BASIS_ROLE_ORDER
    assert basis["reason"] == config_resolve_report.REASON_MAPPING_UNAVAILABLE
    assert basis["reference"] == {"table": CORE_TABLE, "map_id": "NO_SUCH_MAP"}


# ---------------------------------------------------------------------------
# 5. 한 철자, 두 소비자 — M2 가 층 8 을 «정말로» 지나는가
# ---------------------------------------------------------------------------

def test_the_core_answer_reaches_layer_eight(tp_env, client, monkeypatch):
    """M2 가 확정을 «안 읽고» 답하면 같은 웨이퍼가 두 수를 보고한다.

    종전 이 시험은 M1 의 config 를 «어댑터»로 지어 내부 함수를 직접 불렀다. 이제
    «라우트를 통해» 잰다 — 어댑터는 시험이 지은 물건이고 라우트는 «운영이 지나는» 길이다.
    """
    _seed_scenario(tp_env)
    seen = []
    real = bonding_plan.canonical_basis

    def spy(db, config, map_pairs, meta_cache=None):
        seen.append(list(map_pairs))
        return real(db, config, map_pairs, meta_cache)

    monkeypatch.setattr(bonding_plan, "canonical_basis", spy)
    _summary(client)

    assert seen, "the core answer resolved a frame without consulting layer 8"
    assert (CORE_TABLE, MAP_ID) in seen[0], seen[0]
