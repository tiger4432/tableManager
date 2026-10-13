"""Decide aggregations as expressions (lead 5667ea0fe, owner 93b0c7a4b «수식 바꾸고 기존 수식 마이그레이션 할 수 있게»).

Preview by default: every decide rule's aggregations in chain_rules.json - the expression an old record becomes
(`chain.enrichment.config.aggregation_record`, the reader's own fold), or why it stays a record (min/max over a text
column, unique_concat with another separator - they run the old SQL). The reader already runs an old record as its
expression, so writing the file changes nothing that runs.

`--apply` writes the expressions (through `ledger.admin`'s atomic writer, which keeps a backup). Running it twice is
safe: an expression is left as it is.
`--compare N` reads N keys of each rule's source table and compares the cell the old record gives with the cell its
expression gives (the database DATABASE_URL names - read only).

Usage:
    python -m scripts.migrate_decide_aggregations [--apply] [--compare N]
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                               # noqa: BLE001 - a redirected stream
    pass


def _rules(document):
    rules = document.get("rules", document) if isinstance(document, dict) else document
    return [r for r in (rules.values() if isinstance(rules, dict) else rules or []) if isinstance(r, dict)]


def _decide(rule):
    derive = rule.get("derive")
    decide = derive.get("decide") if isinstance(derive, dict) else None
    return decide if isinstance(decide, dict) else None


def plan(document, tables):
    """(the document with every old record that has an expression written as it, [one finding per aggregation]).
    A finding: {rule, name, was, becomes | stays (why) | as_written}."""
    from chain.enrichment.config import aggregation_record

    document = copy.deepcopy(document)
    found = []
    for rule in _rules(document):
        decide = _decide(rule)
        named = (decide or {}).get("aggregations")
        if not isinstance(named, dict):
            continue
        source = (rule.get("on") or {}).get("table") if isinstance(rule.get("on"), dict) else None
        types = (tables.get(source) or {}).get("column_types")
        for name, spec in named.items():
            folded, why = aggregation_record(spec, types)
            finding = {"rule": rule.get("name"), "name": name, "was": spec, "source": source,
                       "key": list(decide.get("key") or [])}
            if why:
                finding["stays"] = why
            elif isinstance(folded, str) and folded != spec:
                finding["becomes"] = folded
                named[name] = folded
            else:
                finding["as_written"] = True
            found.append(finding)
    return document, found


def compare(db, finding, keys=500):
    """{same, different: [(key, old, new)…], keys} - the old record and its expression over `keys` keys of the source."""
    from chain.enrichment.config import AGGREGATION_SEPARATOR_DEFAULTS
    from chain.enrichment.mapper import _aggregate_affected_keys
    from database import crud, models

    model = models.DYNAMIC_TABLES[finding["source"]]
    columns = [getattr(model, k) for k in finding["key"]]
    raws = {}
    for row in db.query(*columns).distinct().limit(keys):
        clean = tuple(crud.clean_str_value(v) for v in row)
        if any(clean):
            raws.setdefault(clean, tuple(None if c == "" else v for c, v in zip(clean, row)))
    old = dict(finding["was"]) if isinstance(finding["was"], dict) else {"fn": finding["was"]}
    if old.get("fn") in AGGREGATION_SEPARATOR_DEFAULTS:
        old.setdefault("separator", AGGREGATION_SEPARATOR_DEFAULTS[old["fn"]])
    if old.get("fn") == "count":                                # the same SQL count either way
        return {"same": len(raws), "different": [], "keys": len(raws)}
    was = _aggregate_affected_keys(db, finding["source"], finding["key"], raws, {"x": old})
    now = _aggregate_affected_keys(db, finding["source"], finding["key"], raws, {"x": {"expression": finding["becomes"]}})
    different = [(key, was[key]["x"], now[key]["x"]) for key in raws if was[key]["x"] != now[key]["x"]]
    return {"same": len(raws) - len(different), "different": different, "keys": len(raws)}


def say(found):
    lines = []
    for f in found:
        head = "%s · %s: %s" % (f["rule"], f["name"], json.dumps(f["was"], ensure_ascii=False))
        if "becomes" in f:
            lines.append("%s -> %s" % (head, f["becomes"]))
        elif "stays" in f:
            lines.append("%s stays (cannot move: %s)" % (head, f["stays"]))
        else:
            lines.append("%s as written" % head)
    moved = sum("becomes" in f for f in found)
    kept = sum("stays" in f for f in found)
    lines.append("%d aggregation(s): %d become expressions, %d stay records, %d as written"
                 % (len(found), moved, kept, len(found) - moved - kept))
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true", help="write the expressions into chain_rules.json")
    parser.add_argument("--compare", type=int, default=0, metavar="N", help="compare old and new over N keys")
    args = parser.parse_args(argv)

    from database import crud
    from ledger import admin

    path = admin.chain_rules_path()
    with open(path, encoding="utf-8") as handle:
        document = json.load(handle)
    tables = crud.load_table_config()
    written, found = plan(document, tables)
    print(path)
    for line in say(found):
        print("  " + line)
    if args.compare:
        from database import models
        from database.database import SessionLocal

        models.init_dynamic_models(tables)
        crud.TABLE_CONFIG.update(tables)
        db = SessionLocal()
        try:
            for f in (f for f in found if "becomes" in f):
                out = compare(db, f, args.compare)
                print("  compare %s · %s: %d of %d keys the same" % (f["rule"], f["name"], out["same"], out["keys"]))
                for key, old, new in out["different"][:5]:
                    print("    %s: old %r, new %r" % (key, old, new))
        finally:
            db.close()
    if args.apply and any("becomes" in f for f in found):
        backup = admin._atomic_write(path, written)
        print("written - backup %s" % (backup or "(none)"))
    elif args.apply:
        print("nothing to write")
    else:
        print("preview only - --apply writes it")


if __name__ == "__main__":
    main()
