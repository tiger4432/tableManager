# -*- coding: utf-8 -*-
"""18:00 (2) - the three names the product ships: do they ALL resolve through the mapper door?"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "server"))
os.chdir(os.path.join(HERE, "..", "server"))

from chain import dynamic_mappers, rule_run  # noqa: E402
import mapper_sdk  # noqa: E402

mapper_sdk.discover()
print("templates:", tuple(sorted(dynamic_mappers.TEMPLATES)))
for name in ("builtin:join", "builtin:join_into", "builtin:auto_confirm"):
    try:
        r = rule_run.resolve({"name": "probe", "mapper": name})
        fn = getattr(r, "call", None)
        print("  %-24s -> %s.%s" % (name, getattr(fn, "__module__", "?"), getattr(fn, "__name__", fn)))
    except Exception as e:
        print("  %-24s -> REFUSED %s" % (name, type(e).__name__))
