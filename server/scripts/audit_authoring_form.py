"""Audit the setup form for the shapes the owner named (2026-08-21).

    "드롭다운이 있어야하는데 없는거, trivial한 값을 쓰는거, 틀이 있어야하는데 없는거
     다 조사해. 기계를 만들든 해서"
    "만약 틀이 있어야하는데 없다, trivial한 값을 쓴다 할 경우
     그 선언이 정말 필요한 것인지도 조사해"

The form is drawn from `ledger_skeleton.json` and answered by
`config_authoring.authoring_plan`.  Every defect in this family is a DISAGREEMENT
between the two: the plan knows something the drawn control does not use, or the
control asks for something the plan has already settled.

The fourth question is the owner's standing ruling -- a declaration code cannot
reach is not a contract, it is a copy -- so every square in classes 2 and 3 is
also asked how many files outside the validator actually READ that key.  A reader
count of zero is the evidence for DELETING the square rather than filling it.

Read-only: writes no config and reads no database rows, only the catalog file.

    python scripts/audit_authoring_form.py
    python scripts/audit_authoring_form.py --root <ontology root>
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.dirname(HERE)
sys.path.insert(0, SERVER)

from ledger import config_authoring, setup_bundle  # noqa: E402

SKELETON = os.path.join(SERVER, "ledger", "ledger_skeleton.json")

#: Files that DEFINE or VALIDATE the declaration vocabulary.  A key mentioned only
#: in these is declared and never consumed, which is precisely the question asked.
DECLARING = ("config_authoring.py", "setup_bundle.py", "config_explorer.py",
             "config_explorer_service.py", "config_drafts.py",
             "audit_authoring_form.py")


def _skeleton_node(skeleton, segments):
    """Resolve a plan path to the skeleton node that DRAWS it.

    A `map` node's members are named by the operator, so any segment matches one and
    the walk descends into `of`.  Returns None when the skeleton draws no such path
    -- that is a finding, not an error.
    """
    node = dict(skeleton.get("root") or {})
    for raw_segment in segments:
        segment = raw_segment.split("[")[0]
        kind = node.get("kind")
        if kind == "record":
            found = next((f for f in node.get("fields", ())
                          if f.get("key") == segment), None)
            if found is None:
                return None
            node = dict(found.get("node") or {}, _required=found.get("required", False))
        elif kind == "map":
            node = dict(node.get("of") or {}, _required=False)
        else:
            return None
        if node.get("use"):
            node = dict((skeleton.get("defs") or {}).get(node["use"], node))
    return node


def _reader_counts(keys):
    """How many files OUTSIDE the declaring set mention each declaration key."""
    counts = {key: 0 for key in keys}
    patterns = {key: re.compile(r"[\"'.]" + re.escape(key) + r"[\"'\s).,\]]")
                for key in keys}
    seen = set()
    for base, dirs, files in os.walk(SERVER):
        dirs[:] = [d for d in dirs
                   if d not in ("__pycache__", "tests", "config") and not d.startswith(".")]
        for name in files:
            if not name.endswith(".py") or name in DECLARING:
                continue
            path = os.path.join(base, name)
            if path in seen:
                continue
            seen.add(path)
            try:
                text = open(path, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            for key, pattern in patterns.items():
                if pattern.search(text):
                    counts[key] += 1
    return counts


def _skeleton_leaves(skeleton, node, prefix, document, out, depth=0):
    """Every leaf the form would DRAW for what the document actually holds.

    The client draws a candidate list whenever the plan row carries one
    (`ontology_explorer_view.js:1062`) and folds a row whose list has exactly one
    entry (`:975`).  So "the skeleton says hint=free" no longer means "the person
    types it" -- the real question is which drawn leaves the PLAN never answers,
    because those arrive with no list, no default and no fold.
    """
    if depth > 12 or not isinstance(node, dict):
        return
    if node.get("use"):
        node = (skeleton.get("defs") or {}).get(node["use"], node)
    kind = node.get("kind")
    if kind == "leaf":
        out.append((prefix, node))
        return
    if kind == "record":
        for field in node.get("fields") or ():
            key = field.get("key")
            when = field.get("when")
            if when and isinstance(document, dict):
                if document.get(when.get("field")) != when.get("is"):
                    continue        # the form hides it; not a hole
            child = document.get(key) if isinstance(document, dict) else None
            _skeleton_leaves(skeleton, field.get("node") or {},
                             prefix + "." + str(key), child, out, depth + 1)
        return
    if kind == "map":
        members = (document if isinstance(document, dict)
                   else dict(enumerate(document)) if isinstance(document, list) else {})
        for name, child in members.items():
            _skeleton_leaves(skeleton, node.get("of") or {},
                             prefix + "." + str(name), child, out, depth + 1)
        return


def unanswered_leaves(document, plan, skeleton):
    """Drawn leaves the plan never speaks for -- no candidates, no default, no fold."""
    answered = {row["path"] for row in plan["fields"]}
    prefixed = set()
    for path in answered:
        parts = path.split(".")
        for index in range(len(parts)):
            prefixed.add(".".join(parts[:index + 1]))
    leaves = []
    _skeleton_leaves(skeleton, skeleton.get("root") or {}, "bundle", document, leaves)
    holes = []
    for path, node in leaves:
        parts = path.split(".")
        # A list member is not a hole when the plan speaks for the LIST: the person
        # picks members from the parent's candidates, so the member has no box of
        # its own to be empty.  Only a leaf with no answered ancestor is on its own.
        if any(".".join(parts[:index + 1]) in answered for index in range(len(parts))):
            continue
        holes.append((path, node.get("hint") or node.get("kind"),
                      parts[2] if len(parts) > 2 else parts[-1]))
    return leaves, holes


def audit(root, catalog_path):
    document = json.load(open(os.path.join(root, "ledger_config.json"), encoding="utf-8"))
    catalog = setup_bundle.load_physical_catalog(catalog_path)
    plan = config_authoring.authoring_plan(document, catalog)
    skeleton = json.load(open(SKELETON, encoding="utf-8"))

    findings = defaultdict(list)
    suspect_keys = set()
    for row in plan["fields"]:
        path = row["path"]
        node = _skeleton_node(skeleton, path.split(".")[1:])
        hint = (node or {}).get("hint")
        kind = (node or {}).get("kind")
        candidates = row.get("candidates") or []
        state, tier = row.get("state"), row.get("tier")
        leaf = path.split(".")[-1].split("[")[0]

        if len(candidates) > 1 and kind == "leaf" and hint == "free":
            findings["dropdown_missing"].append((path, len(candidates), state))
        elif len(candidates) > 1 and node is None:
            findings["dropdown_undrawn"].append((path, len(candidates), state))

        if len(candidates) == 1 and state != "derived":
            findings["single_candidate"].append((path, str(candidates[0])[:30], state))
            suspect_keys.add(leaf)
        if state == "derived" and row.get("conflicts"):
            findings["derived_conflicts"].append(
                (path, str(row.get("value"))[:32], str(row.get("declared"))[:32]))
            suspect_keys.add(leaf)

        if state in ("missing", "unanswered"):
            findings["no_scaffold"].append((path, state, kind or "-",
                                            (row.get("ground") or {}).get("rule")))
            suspect_keys.add(leaf)
        if node is None:
            findings["not_in_skeleton"].append((path, state, tier))
            suspect_keys.add(leaf)

    leaves, holes = unanswered_leaves(document, plan, skeleton)
    for path, hint, where in holes:
        findings["plan_silent"].append((path, hint, where))
        suspect_keys.add(path.split(".")[-1].split("[")[0])
    findings["_leaf_total"] = [(len(leaves),)]
    return plan, findings, _reader_counts(sorted(suspect_keys))


TITLES = (
    ("dropdown_missing",  "1.  HAS candidates, form draws FREE TEXT"),
    ("dropdown_undrawn",  "1b. HAS candidates, skeleton draws NOTHING"),
    ("single_candidate",  "2.  exactly ONE candidate, still asked"),
    ("derived_conflicts", "2b. derived value DISAGREES with what is declared"),
    ("no_scaffold",       "3.  missing / unanswered - no shape laid out"),
    ("not_in_skeleton",   "3b. plan answers a path the skeleton does not draw"),
    ("plan_silent",       "0.  DRAWN leaf the plan never speaks for  <- the real hole"),
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=os.path.join(SERVER, "config", "ontology"))
    parser.add_argument("--catalog",
                        default=os.path.join(SERVER, "config", "table_config.json"))
    args = parser.parse_args(argv)

    plan, findings, readers = audit(args.root, args.catalog)
    rows = plan["fields"]
    # 🔴 THE TOTAL IS ONLY COMPARABLE ACROSS RUNS THAT SAW THE SAME SOURCES.  Each
    # source contributes its own copy of every family, so adding a half-built source
    # raises the count without a single new defect -- and the implementer hit exactly
    # that comparing their run to the lead's baseline while the owner had two
    # unfinished sources in the file.  Print the subjects with the number.
    document = json.load(open(os.path.join(args.root, "ledger_config.json"),
                              encoding="utf-8"))
    print("sources seen ({}): {}".format(
        len(document.get("sources") or {}), ", ".join(sorted(document.get("sources") or {}))))
    print("plan rows: {}   state={}   tier={}".format(
        len(rows),
        dict(Counter(r.get("state") for r in rows)),
        dict(Counter(r.get("tier") for r in rows))))

    total = 0
    for key, title in TITLES:
        hits = findings.get(key) or []
        total += len(hits)
        print("\n=== {}   [{}]".format(title, len(hits)))
        for hit in hits[:40]:
            print("    " + "   ".join(str(part) for part in hit))
        if len(hits) > 40:
            print("    ... {} more".format(len(hits) - 40))

    print("\n=== 4.  is the declaration NEEDED?"
          "  (files outside the validator that read the key)")
    for key in sorted(readers, key=lambda k: (readers[k], k)):
        mark = "   <- nobody reads it" if readers[key] == 0 else ""
        print("    {:34s} readers={}{}".format(key, readers[key], mark))

    families = Counter()
    for path, _hint, _where in findings.get("plan_silent") or ():
        parts = path.split(".")
        families[parts[3] if parts[1] == "sources" and len(parts) > 3
                 else parts[1]] += 1
    print("\n=== 0 by family (compare THESE across runs, not the total)")
    for name, count in sorted(families.items(), key=lambda item: (-item[1], item[0])):
        print("    {:34s} {}".format(name, count))

    print("\nTOTAL findings: {}".format(total))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
