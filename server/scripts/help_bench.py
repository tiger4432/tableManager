# -*- coding: utf-8 -*-
"""The admin help's answer table (소유자 10-23, 총괄 e33713863): every example question of the catalog asked of the
model the server is set to (config/llm_config.json), as the help asks it (`admin.help.pick`) - how many name their
own tool, which do not, and the gateway's seconds per ask. Reads and writes nothing in the database.

    python server/scripts/help_bench.py [--tool <name>]
"""
import argparse
import os
import statistics
import sys

_SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)


def bench(ask_json=None, tools=None):
    """-> {"asked", "hit", "misses": [(tool, question, picked or the refusal)], "seconds": [per ask]}."""
    from admin import help as admin_help

    catalog = admin_help.catalog()
    said = {"asked": 0, "hit": 0, "misses": [], "seconds": []}
    for tool in tools or sorted(catalog):
        for question in catalog[tool]["examples"]:
            got = admin_help.pick(question, ask_json)
            said["asked"] += 1
            said["seconds"] += got["seconds"]
            if got["op"] == tool:
                said["hit"] += 1
            else:
                said["misses"].append((tool, question, got["op"] or got["refused"]))
    return said


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--tool", action="append", help="only this tool's questions (repeatable)")
    args = parser.parse_args(argv)
    said = bench(tools=args.tool)
    for tool, question, picked in said["misses"]:
        print("MISS  %-28s %s  ->  %s" % (tool, question, picked))
    seconds = said["seconds"]
    print("named their own tool: %d of %d" % (said["hit"], said["asked"]))
    if seconds:
        print("gateway seconds per ask: median %.2f · max %.2f · %d asks"
              % (statistics.median(seconds), max(seconds), len(seconds)))
    return 0 if said["hit"] == said["asked"] else 1


if __name__ == "__main__":
    sys.exit(main())
