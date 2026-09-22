# -*- coding: utf-8 -*-
"""18:00 (2) — the three names the product ships: do they ALL resolve through the mapper door?

🔴 [판정 600] THE NAMES ARE READ FROM THE CONSTANTS, NOT TYPED HERE. This file used to spell
`builtin:join` / `builtin:join_into` / `builtin:auto_confirm`, so the day the values changed
it would have reported REFUSED for all three and named the rename as a breakage. A probe that
carries its own copy of what it measures goes stale with it.

⚠️ AND THE RETIRED NAMES ARE A CONTROL GROUP. They must REFUSE - if an old name still
resolves, the rename left a second name standing, which is the thing 600 exists to prevent.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "server"))
os.chdir(os.path.join(HERE, "..", "server"))

from chain import dynamic_mappers, rule_run, join_into  # noqa: E402
from chain import enrichment  # noqa: E402
import mapper_sdk  # noqa: E402

mapper_sdk.discover()
print("templates:", tuple(sorted(dynamic_mappers.TEMPLATES)))

# ⚰️ [판정 652 3걸음] 이 파일 «이름»의 「three」는 이제 둘입니다. 셋째는
# `legacy_join_declaration.JOIN_MAPPER` 였고 그 모듈이 문법과 같이 걷혔습니다. 이름은
# 안 바꿉니다 — 총괄 채널이 이 파일을 「게이트 ①의 탐침」으로 «이름으로» 가리키고 있고,
# 채널은 다시 쓰지 않습니다.
#
# 🔴 그리고 그 셋째는 «사라진 게 아니라 대조군으로 내려갔습니다». 이 파일의 규율이
# 그것입니다 — 은퇴한 이름은 REFUSE 해야 하고, 아직 풀리면 개명이 둘째 이름을 세워 둔
# 것입니다. 상수를 못 읽어 «값»을 적는 것은 RETIRED 의 원래 모양 그대로입니다(지워진
# 모듈에는 읽을 상수가 없습니다).
SHIPPED = (join_into.JOIN_INTO_MAPPER,
           enrichment.config.AUTO_CONFIRM_MAPPER)
RETIRED = ("builtin:join", "builtin:join_into", "builtin:auto_confirm",
           "declared:virtual_join")


def ask(name):
    try:
        r = rule_run.resolve({"name": "probe", "mapper": name})
        fn = getattr(r, "call", None)
        return "%s.%s" % (getattr(fn, "__module__", "?"), getattr(fn, "__name__", fn))
    except Exception as e:
        return "REFUSED %s" % type(e).__name__


print("shipped (must ALL resolve):")
for name in SHIPPED:
    print("  %-24s -> %s" % (name, ask(name)))
print("retired (must ALL refuse):")
for name in RETIRED:
    print("  %-24s -> %s" % (name, ask(name)))
