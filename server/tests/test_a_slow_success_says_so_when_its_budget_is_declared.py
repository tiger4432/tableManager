# -*- coding: utf-8 -*-
"""세 경로가 `elapsed_ms` «만» 냈다 — 운영자는 「얼마나」는 보고 「왜」는 못 봤다 (S-7 ②).

🔴 세 상태이고, 「부재」가 그중 «첫째»다:
```
선언 «없음»   -> 응답에 `slow_reason` «키 없음»    「이 경로는 «안 잰다»」
선언 있음     -> `None`                            「재 봤는데 «안 느리다»」
선언 있음     -> 문장                              「예산을 «넘었다»」
```
⚠️ 부재를 `None` 으로 접으면 「안 쟀다」가 「안 느리다」로 «거짓말»한다. 그리고 그 구별이
규칙에 키를 «잘못 적었을 때»도 값을 낸다 — 그 경로는 「안 잰다」로 보이고, 조용히 「안 느리다」로
말하지 않는다. 키 열거가 없는 선언을 견디는 것이 이 세 상태다.

⛔ 정의는 «시계»다: 「측정한 비용이 «선언된 예산»을 넘었다」. 상한에 닿은 사실은 `truncated`
가 이미 말하고, 그것을 「느리다」라 부르면 한 사실에 철자가 둘이 된다.
"""
import inspect
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import dt_map_derivation                                         # noqa: E402
import map_alignment as ma                                       # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SAMPLE = os.path.join(ROOT, "server", "config", "sample", "map_overlay_config.json.sample")


def _score(**kw):
    """빈 채점 — 이 파일이 재는 것은 «칸의 세 상태»이지 채점 결과가 아니다."""
    _c, _e, _r, stats = ma.score_candidates([], [], {}, **kw)
    return stats


# ============================================ 1. 세 상태 — «응답»에서

def test_no_declaration_means_the_column_is_absent():
    """🔴 `None` 이 «아니다». 부재는 「안 잰다」이고 None 은 「안 느리다」는 주장이다."""
    assert "slow_reason" not in _score()


def test_a_declared_budget_within_reach_says_so_with_a_value():
    stats = _score(slow_warn_ms=10 ** 9)
    assert "slow_reason" in stats and stats["slow_reason"] is None


def test_a_declared_budget_exceeded_carries_the_sentence():
    #: 🔴 «강제된» 초과다. 빈 채점은 0.0ms 로 끝날 수 있어 0 을 예산으로 줘도 «안 넘는다» —
    #:    이 단언이 재는 것은 「얼마나 느린가」가 아니라 「넘었을 때 «문장»이 오나」이므로
    #:    어떤 실행도 넘는 값을 준다. (선언에서는 음수가 «거절»된다 — 자세는 리더가 든다.)
    stats = _score(slow_warn_ms=-1.0)
    assert isinstance(stats["slow_reason"], str)
    assert "ms" in stats["slow_reason"]


def test_the_number_beside_it_did_not_move():
    """무회귀 — 이 라운드는 «말하기»이지 «바꾸기»가 아니다. `elapsed_ms` 는 그대로 온다."""
    for kw in ({}, {"slow_warn_ms": 10 ** 9}):
        assert isinstance(_score(**kw)["elapsed_ms"], float)


# ============================================ 2. 세 자리 «전부» 그 인자를 받는다

def test_every_route_takes_the_budget_as_a_parameter():
    """⚠️ 함수가 config 를 «직접» 읽지 않는다 — 선언을 읽는 것은 «cfg/rule 을 쥔 호출자»이고,
    그 순수성은 계약이 기대는 성질이다(S-15 ④ 가 지킨 그것)."""
    for fn in (ma.score_candidates, dt_map_derivation.derive_cells,
               dt_map_derivation.plan_retraction):
        params = inspect.signature(fn).parameters
        assert "slow_warn_ms" in params, fn.__name__
        assert params["slow_warn_ms"].default is None, fn.__name__


def test_the_scorer_still_needs_no_session():
    """그 순수성이 이 라운드로 깨지지 않았다 — db 없이 돈다."""
    assert _score(slow_warn_ms=10 ** 9)["elapsed_ms"] >= 0


# ============================================ 3. 철자 하나 · 출하 선언

def test_slow_has_one_spelling_in_the_repository():
    out = subprocess.run(["git", "ls-files", "server"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    other = []
    for rel in out.splitlines():
        if not rel.endswith(".py"):
            continue
        try:
            src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        except OSError:
            continue
        #: ⚠️ «필드 철자»를 찾는다. `slowness` 같은 영어 낱말은 산문에 있고 그건 철자가
        #:    아니다 — 인용은 발신이 아니다. 그래서 «따옴표 안»만 센다.
        #: ⛔ 맨 `"slow"` 는 «안» 센다 — 진단 스크립트의 «분류 라벨»로 살아 있고 그건 다른
        #:    주어다. 재는 것은 「같은 사실에 붙는 «둘째 필드 이름»」이다.
        for spelling in ('"slow_note"', '"slow_message"', '"is_slow"', '"slowness"',
                         '"slow_ms"', '"slow_warning"'):
            if spelling in src:
                other.append((rel.replace("\\", "/"), spelling))
    assert other == [], "a second spelling of 'slow': %s" % other


def test_the_shipped_alignment_block_declares_a_budget_with_its_reason():
    """🔴 값은 «템플릿»이다 — 이 저장소에서 «잰» 수가 아니고, 근거가 그 옆에 있어야 한다."""
    cfg = json.load(open(SAMPLE, encoding="utf-8"))
    block = cfg["alignment"]
    assert isinstance(block.get("slow_warn_ms"), int) and block["slow_warn_ms"] > 0
    assert block.get("_slow_warn_ms"), "the template value ships without its reason"
    assert ma.alignment_slow_warn_ms(cfg) == block["slow_warn_ms"]
