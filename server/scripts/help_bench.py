# -*- coding: utf-8 -*-
"""The admin help's answer table (소유자 10-23, 총괄 e33713863): every example question of the catalog asked of the
model the server is set to (config/llm_config.json), as the help asks it (`admin.help.pick`) - how many name their
own tool, which do not, and the gateway's seconds per ask. Reads and writes nothing in the database.

    python server/scripts/help_bench.py [--tool <name>] [--limit N] [--part tools|declarations|both]

A question whose ask fails (the gateway, an answer that is not JSON twice) is a miss with its sentence - the bench
goes on. The declaration part (owner 10-29) asks help_declaration_bench.json's questions as the help does - the tool
pick, then the guides' answer - and counts the answers citing their right section and the checks that passed. A right
section the guides no longer hold is said first, not scored as a miss.
"""
import argparse
import json
import os
import statistics
import sys

_SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)


def _failed(e):
    """A failed ask as its miss's sentence - its type and where it broke."""
    from error_said import told

    return "%s: %s" % (type(e).__name__, told(e))


def bench(ask_json=None, tools=None, limit=None):
    """-> {"asked", "hit", "misses": [(tool, question, picked or the refusal)], "seconds": [per ask]} - the first
    `limit` questions when given."""
    from admin import help as admin_help

    catalog = admin_help.catalog()
    said = {"asked": 0, "hit": 0, "misses": [], "seconds": []}
    asks = [(tool, question) for tool in tools or sorted(catalog) for question in catalog[tool]["examples"]]
    for tool, question in asks[:limit]:
        try:
            got = admin_help.pick(question, ask_json)
        except Exception as e:                                          # noqa: BLE001 - the question's miss
            got = {"op": None, "refused": _failed(e), "seconds": []}
        said["asked"] += 1
        said["seconds"] += got["seconds"]
        if got["op"] == tool:
            said["hit"] += 1
        else:
            said["misses"].append((tool, question, got["op"] or got["refused"]))
    return said


DECLARATIONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "help_declaration_bench.json")


def bench_declarations(ask_json=None, limit=None):
    """-> {"asked", "cited", "ok", "refused", "not_checked", "absent": [(question, section)], "misses": [(question,
    what)]} over help_declaration_bench.json's first `limit` questions."""
    from admin import help as admin_help
    from admin import help_guides
    from utils import llm

    with open(DECLARATIONS, encoding="utf-8") as handle:
        asks = json.load(handle)["questions"][:limit]
    pieces = help_guides.index().pieces
    said = {"asked": 0, "cited": 0, "ok": 0, "refused": 0, "not_checked": 0, "absent": [], "misses": []}
    for ask in asks:
        right = {p["name"] for p in pieces if ask["section"] in p["name"] or ask["section"] in p["text"]}
        if not right:
            said["absent"].append((ask["question"], ask["section"]))
            continue
        said["asked"] += 1
        try:
            got = admin_help.pick(ask["question"], ask_json)
            if got["op"] != admin_help.DECLARATION:
                said["misses"].append((ask["question"], "picked %s" % (got["op"] or got["refused"])))
                continue
            answer = help_guides.answer(ask["question"], got.get("search"), ask_json or llm.ask_json)
        except Exception as e:                                          # noqa: BLE001 - the question's miss
            said["misses"].append((ask["question"], _failed(e)))
            continue
        check = answer["check"]
        said["ok"] += check.get("ok") is True
        said["refused"] += check.get("ok") is False
        said["not_checked"] += "not_checked" in check
        if right & set(answer["sections"]):
            said["cited"] += 1
        else:
            said["misses"].append((ask["question"], "cited %s" % (answer["sections"] or answer.get("refused"))))
    return said


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--tool", action="append", help="only this tool's questions (repeatable)")
    parser.add_argument("--limit", type=int, help="ask only the first N questions")
    parser.add_argument("--part", choices=("tools", "declarations", "both"), default="both")
    args = parser.parse_args(argv)
    whole = True
    if args.part in ("tools", "both"):
        said = bench(tools=args.tool, limit=args.limit)
        for tool, question, picked in said["misses"]:
            print("MISS  %-28s %s  ->  %s" % (tool, question, picked))
        seconds = said["seconds"]
        print("named their own tool: %d of %d" % (said["hit"], said["asked"]))
        if seconds:
            print("gateway seconds per ask: median %.2f · max %.2f · %d asks"
                  % (statistics.median(seconds), max(seconds), len(seconds)))
        whole = said["hit"] == said["asked"]
    if args.part in ("declarations", "both"):
        said = bench_declarations(limit=args.limit)
        for question, section in said["absent"]:
            print("NO RIGHT SECTION IN THE GUIDES  %s  ->  %s" % (question, section))
        for question, what in said["misses"]:
            print("MISS  %s  ->  %s" % (question, what))
        print("declarations: right section cited %d of %d · checked ok %d · refused %d · not checked %d"
              % (said["cited"], said["asked"], said["ok"], said["refused"], said["not_checked"]))
        whole = whole and not said["absent"] and said["cited"] == said["asked"]
    return 0 if whole else 1


if __name__ == "__main__":
    sys.exit(main())
