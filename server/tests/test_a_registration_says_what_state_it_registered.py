# -*- coding: utf-8 -*-
"""S-52 Ⓔ (판정 127 · 128) — 등록의 «존재»와 «상태»는 다른 물음이고, 함수도 둘이다.

🔴 왜 하나로 못 접나 — «실측»이다. 등록 probe(`backfill._registration_subjects`)는 원자가 아니라
«소스 관계»를 읽는다: 선언된 identity 컬럼에서 키를 뽑을 뿐이고 «속성값이 그 자리에 없다».
그래서 필터가 (키 + 속성 지문) 토큰을 «키만 든» probe 집합에 견주면 아무것도 안 맞고,
모든 엔티티가 «매 실행마다» 재등록된다.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ledger.envelope import (                                          # noqa: E402
    registration_fingerprint,
    registration_token,
)


def _payload(**qualifiers):
    return {"kind": "none", "qualifiers": dict(qualifiers)} if qualifiers else None


def test_the_existence_token_is_keys_only_because_the_probe_can_make_nothing_else():
    """probe 가 «만들 수 있는 유일한» 철자다. 여기에 속성이 들어가면 probe 집합과 영원히 안 맞는다."""
    assert (registration_token("wafer@1", {"wafer": "W1"})
            == registration_token("wafer@1", {"wafer": "W1"}))
    assert (registration_token("wafer@1", {"wafer": "W1"})
            != registration_token("wafer@1", {"wafer": "W2"}))
    assert (registration_token("wafer@1", {"wafer": "W1"})
            != registration_token("lot@1", {"wafer": "W1"}))
    # 🔴 그리고 «두 인자뿐»이다 — 속성을 받을 자리가 없다는 것이 이 함수의 계약이다.
    assert len(registration_token("wafer@1", {"wafer": "W1"})) == 2


def test_the_fingerprint_is_empty_when_a_registration_says_nothing():
    """빈 지문 = 「이 축이 있기 «전»과 같다」. ㉥ 무회귀가 이 한 값에 걸려 있다."""
    assert registration_fingerprint(None) == ""
    assert registration_fingerprint({"kind": "none"}) == ""
    assert registration_fingerprint({"kind": "none", "qualifiers": {}}) == ""


def test_two_registrations_of_different_states_have_different_fingerprints():
    assert (registration_fingerprint(_payload(product="A"))
            != registration_fingerprint(_payload(product="B")))
    assert (registration_fingerprint(_payload(product="A"))
            == registration_fingerprint(_payload(product="A")))


def test_the_fingerprint_does_not_depend_on_the_order_the_attributes_were_written():
    """선언이 두 이름의 순서를 바꿨다고 «다른 상태»가 되면, 재번역이 원장을 두 배로 만든다."""
    assert (registration_fingerprint(_payload(product="A", grade="B"))
            == registration_fingerprint(_payload(grade="B", product="A")))


def test_the_two_functions_are_not_folded_into_one():
    """㉤ 판별식. 존재 토큰이 지문을 «품기 시작하면» probe 의 집합이 무의미해진다 —
    그 순간은 조용하다(오류 0, 그냥 «전부 재등록»)."""
    plain = registration_token("wafer@1", {"wafer": "W1"})
    assert registration_fingerprint(_payload(product="A")) not in plain, (
        "the existence token must not carry state, or the probe's set never matches")


# ---------------------------------------------------------------------------
# ㉣ 필터의 «행동» — 위는 토큰 «값»을 쟀고, 이 절은 그 값이 실제로 무엇을 «거르나»를 잰다.
# (첫 판은 이 절이 없었고, 「known 스킵을 옛 철자로 되돌리는」 변이가 «살아남았다».)
# ---------------------------------------------------------------------------

class _Result:
    def __init__(self, atoms):
        from ledger.ledger_frame import ledger_frame_from_atoms
        self.ledger_frame = ledger_frame_from_atoms(atoms)


def _register(keys, when, **qualifiers):
    from datetime import datetime, timezone
    from ledger.envelope import Atom
    atom = Atom(
        id=None, subject_type="wafer@1", subject_keys=dict(keys),
        predicate="register", object_kind="none",
        object_payload=_payload(**qualifiers) or {"kind": "none"},
        occurred_at=datetime(2026, 9, 8, when, 0, tzinfo=timezone.utc),
        source_translator_ver="v1", source_raw_ref="raw-%d" % when,
        source_who="test-source", molecule_ref="mol-%d" % when,
        derivation="first_sight")
    atom.ensure_id()
    atom.ensure_source_event_identity()
    return atom


def _kept(atoms, known):
    from ledger.runtime_v2 import _filtered_event_atoms
    filtered = _filtered_event_atoms((_Result(atoms),), tuple(known))
    return list(filtered[0])


KNOWN_W1 = [registration_token("wafer@1", {"wafer": "W1"})]


def test_a_bare_registration_of_a_known_entity_is_still_skipped():
    """㉥ 무회귀. 아무 말도 안 하는 등록은 «오늘과 동일»하게 걸러진다."""
    assert _kept([_register({"wafer": "W1"}, 1)], KNOWN_W1) == []


def test_a_registration_that_says_something_is_not_skipped_by_the_probes_token():
    """🔴 이 절의 핵심. probe 는 «속성을 본 적이 없다** — 그 집합으로 상태를 든 등록을 거르면
    운영자가 적은 값이 «조용히» 사라진다. 중복은 «원자 id»가 가른다(저장이 접는다)."""
    kept = _kept([_register({"wafer": "W1"}, 1, product="A")], KNOWN_W1)

    assert len(kept) == 1
    assert kept[0].object_payload["qualifiers"] == {"product": "A"}


def test_two_registrations_of_different_states_both_land_in_one_batch():
    """㉣ 「최신이 이긴다」는 «걷기»의 규칙이지 «쓰기»의 필터가 아니다 — 쓰기는 다른 사실을 안 버린다."""
    kept = _kept([_register({"wafer": "W1"}, 1, product="A"),
                  _register({"wafer": "W1"}, 2, product="B")], [])

    assert {atom.object_payload["qualifiers"]["product"] for atom in kept} == {"A", "B"}


def test_two_registrations_of_the_same_state_collapse_to_one():
    kept = _kept([_register({"wafer": "W1"}, 1, product="A"),
                  _register({"wafer": "W1"}, 2, product="A")], [])

    assert len(kept) == 1
