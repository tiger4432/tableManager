# -*- coding: utf-8 -*-
"""레이어 승자의 이름이 «하나»로 남는가.

🔴 왜 이 파일이 있나: 같은 값에 철자가 «셋»이었다 — `top_source` · `revealed_source` ·
   `winning_source`. 셋 다 `compute_priority_value` 의 둘째 반환값을 담았고, 다른 것은
   «그 값이 사는 dict» 뿐이었다. 그릇이 「누구에 대한 답인가」를 이미 말하므로 이름이 그것을
   다시 말할 필요가 없다 — 이름은 «출처»만 말한다 (총괄 판정 40·41).

🔴 그리고 그 셋은 «단언이 없어서» 생겼다. 접어 놓고 이 시험을 안 두면 넷째가 생기고,
   그때도 아무도 안 깨진다 — 오늘 밤 `_bare`(넷)와 `escapeHtml`(셋)이 그렇게 갈렸다.

⚠️ 여기서 «텍스트»는 대리가 아니라 «주어»다. 재는 것이 「이 값이 어떻게 도나」가 아니라
   「이 저장소가 이 값을 몇 가지로 «부르나»」이므로, 소스를 읽는 것이 곧 그 질문이다
   (CLAUDE.md 「텍스트가 «대상»인 하니스는 이 규칙 밖」).
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

#: 은퇴한 철자. 「역할」에서 온 이름이라 그릇이 늘 때마다 하나씩 늘어난다.
RETIRED = ("revealed_source", "winning_source")

#: 이 값의 «유일한» 이름. 헬퍼가 돌려주는 이름이라 그릇이 몇 개든 하나로 버틴다.
LIVE = "top_source"


def _sources():
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs
                   if d not in (".git", "__pycache__", ".tmp", "node_modules")]
        for name in files:
            if name.endswith(".py") and name != os.path.basename(__file__):
                yield os.path.join(base, name)


def test_the_retired_spellings_do_not_come_back():
    """🔴 판별식: 은퇴한 이름이 «코드»에 다시 나타나면 빨개진다. 주석의 설명은 세지 않는다."""
    offenders = []
    for path in _sources():
        with open(path, encoding="utf-8", errors="replace") as fh:
            for lineno, line in enumerate(fh, 1):
                if line.lstrip().startswith("#"):
                    continue                      # 왜 은퇴했는지 «적는» 줄은 위반이 아니다
                for dead in RETIRED:
                    if dead in line:
                        offenders.append("%s:%d %s" % (
                            os.path.relpath(path, ROOT), lineno, dead))
    assert not offenders, (
        "레이어 승자에 철자가 다시 둘 이상이다 — 그릇이 주어를 나르므로 이름은 «출처»만 "
        "말한다 (판정 40·41): %r" % (offenders,))


def test_the_live_spelling_is_actually_used():
    """🔴 위 시험이 «공허»해지지 않게. 살아 있는 이름이 0이면 위 단언은 아무것도 안 지킨다."""
    hits = 0
    for path in _sources():
        with open(path, encoding="utf-8", errors="replace") as fh:
            hits += sum(1 for line in fh
                        if not line.lstrip().startswith("#") and LIVE in line)
    assert hits >= 3, "살아 있는 철자가 %d 번뿐이다 — 위 단언이 공허하다" % hits
