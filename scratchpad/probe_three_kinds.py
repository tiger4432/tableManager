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

from chain import dynamic_mappers, rule_run, join_into, legacy_join_declaration  # noqa: E402
from chain import enrichment  # noqa: E402
import mapper_sdk  # noqa: E402

mapper_sdk.discover()
print("templates:", tuple(sorted(dynamic_mappers.TEMPLATES)))

SHIPPED = (join_into.JOIN_INTO_MAPPER,
           legacy_join_declaration.JOIN_MAPPER,
           enrichment.config.AUTO_CONFIRM_MAPPER)
RETIRED = ("builtin:join", "builtin:join_into", "builtin:auto_confirm")


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
