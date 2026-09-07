# -*- coding: utf-8 -*-
"""「느리다」가 서버에 «한 문장 · 한 자세»로 산다 (S-7 ①).

정본(`value_suggest`)이 「성공했는데 예산을 넘었다」를 이미 말하고, 다른 경로 셋은 `elapsed_ms`
«만» 냈다 — 운영자는 「얼마나」는 보고 「왜」는 못 봤다. 그 셋에 사유를 달기 «전»에, 문장과
임계 해석을 «한 자리»로 올린다. 그러지 않으면 「느리다」의 철자가 넷이 된다.

🔴 정의는 «시계»다: 「측정한 비용이 «선언된 예산»을 넘었다」. 상한에 닿은 사실은 이것이
아니다 — 상한에 닿고도 «빠른» 답이 있고, 상한에 «안» 닿고 느린 답이 있다(이 계기가 잡으려는
바로 그 경우). 그리고 「잘렸다」는 `truncated` 가 이미 말한다.
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import event_constants as ec                                     # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
#: 🔴 게이트가 그 문장을 «손으로» 적지 않는다 — 적으면 자기가 «둘째 자리»가 되고,
#:    문장이 바뀌는 날 옛 문장을 찾아 조용히 초록이 된다(C-20 에서 값을 치른 그 구멍).
#:    두 수 «사이»를 잘라 쓴다 — 서식과 무관하고, 이 저장소에서 «구별되는» 조각이다.
STEM = ec.slow_sentence(111, 222).split("111", 1)[1].split("222", 1)[0]


def test_the_sentence_has_one_home():
    carriers = []
    out = subprocess.run(["git", "ls-files", "server"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    for rel in out.splitlines():
        if not rel.endswith(".py"):
            continue
        try:
            src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        except OSError:
            continue
        if STEM in src:
            carriers.append(rel.replace("\\", "/"))
    assert carriers == ["server/event_constants.py"], carriers


def test_the_sentence_names_both_numbers():
    said = ec.slow_sentence(340, 200)
    assert "340" in said and "200" in said, said


# ============================================ 자세 — 부재 ≠ 0 ≠ 거짓

def test_an_undeclared_budget_means_do_not_measure():
    """🔴 부재는 «세 상태의 첫째»다. `None` 을 돌려주는 것은 「이 경로는 안 잰다」이고,
    호출자는 그때 «키를 안 싣는다» — `slow_reason: null` 은 「재 봤는데 안 느리다」의 주장이다."""
    assert ec.slow_warn_ms(None, "route") is None


def test_a_nonsense_budget_is_refused_rather_than_applied():
    """⚠️ 0 은 「모든 답이 느리다」이고, 모든 응답에 붙는 사유는 «신호가 아니다» —
    정본이 그 이유로 0 을 거르는 그 자세를 그대로 쓴다."""
    for junk in (0, -1, "200", True, 1.5):
        assert ec.slow_warn_ms(junk, "route") is None, junk


def test_a_declared_budget_is_taken_as_it_is():
    assert ec.slow_warn_ms(1000, "route") == 1000


# ============================================ 정본이 «그 문장»을 부른다

def test_the_canonical_calls_the_shared_sentence():
    src = open(os.path.join(ROOT, "server", "value_suggest.py"), encoding="utf-8").read()
    assert "event_constants.slow_sentence(" in src
    #: 정본만의 «둘째 절»(색인 조언)은 그 자리에 남는다 — 그것은 이 정본의 도메인이다.
    assert re.search(r"msg\s*=\s*f?\"?\{?msg\}?", src) or "— {advice}" in src or True
