r"""Fill `mechanism_edge` from the declared mechanism models, one row per declared edge.

The models are the source: three of them, 18 + 3 + 1 = 22 edges between 23 quantities.
Nothing here is derived from data - a mechanism edge is an ASSERTION somebody reviewed, and
that is exactly why it belongs in a table the ledger can translate rather than in a config
only the walk reads.

🔴 `to_quantity` KEEPS `void` AND `delam` AS THEY ARE. Those are the two models' targets and
they are spelled the same as the `defect_kind@1` keys already in the ledger, so the edge
lands on the node that is there. Renaming them would be the whole point of this round,
undone.

🔴 `asserted_at` COMES FROM THE MODEL'S OWN `validity`, NOT FROM THE CLOCK. Two models say
"owner-reviewed 2026-08-14" and get that date. `void_observation_bias` states no review date
at all - its row gets NULL. A load time is when a row was written; it is not when a person
asserted the edge, and writing today's date would claim a review that did not happen.

USAGE - dry run by default:

    python scripts/load_mechanism_edge_rows.py
    python scripts/load_mechanism_edge_rows.py --apply --i-accept-writing-to-owner-database
"""
import argparse
import datetime
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SERVER = os.path.dirname(_HERE)
for _p in (_SERVER, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from sqlalchemy import text                                          # noqa: E402
from database import database as db                                 # noqa: E402
from ledger import uuid7                                            # noqa: E402

TABLE = "mechanism_edge"
MODELS = ("void_formation", "delam_formation", "void_observation_bias")
REVIEWED = re.compile(r"owner-reviewed (\d{4}-\d{2}-\d{2})")


def _config_path():
    try:
        import paths
        return os.path.join(paths.CONFIG_DIR, "mechanism_models.json")
    except Exception:                                              # pragma: no cover
        return os.path.join(_SERVER, "config", "mechanism_models.json")


def build_rows():
    with open(_config_path(), "r", encoding="utf-8") as handle:
        declared = json.load(handle)
    rows = []
    for model in MODELS:
        spec = declared.get(model) or {}
        found = REVIEWED.search(str(spec.get("validity") or ""))
        asserted = (datetime.datetime.strptime(found.group(1), "%Y-%m-%d")
                    .replace(tzinfo=datetime.timezone(datetime.timedelta(hours=9)))
                    if found else None)
        for edge in spec.get("edges") or []:
            edge_id = "%s:%s:%s" % (model, edge["from"], edge["to"])
            rows.append({
                "row_id": str(uuid7.uuid7()), "business_key_val": edge_id,
                "edge_id": edge_id, "model": model,
                "from_quantity": edge["from"], "to_quantity": edge["to"],
                "dir": edge.get("dir"), "asserted_at": asserted,
            })
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--i-accept-writing-to-owner-database", dest="allow_owner",
                    action="store_true")
    args = ap.parse_args(argv)

    rows = build_rows()
    quantities = {r["from_quantity"] for r in rows} | {r["to_quantity"] for r in rows}
    dated = sum(1 for r in rows if r["asserted_at"])
    with db.engine.connect() as c:
        existing = c.execute(text(f"SELECT count(*) FROM {TABLE}")).scalar()
    print("   %-32s %s" % ("existing rows", existing))
    print("   %-32s %s" % ("edges built", len(rows)))
    print("   %-32s %s" % ("distinct quantities (from∪to)", len(quantities)))
    print("   %-32s %s" % ("edge_id distinct", len({r["edge_id"] for r in rows})))
    print("   %-32s %s" % ("asserted_at set / NULL", "%d / %d" % (dated, len(rows) - dated)))
    print("   %-32s %s" % ("to_quantity void|delam kept",
                           sum(1 for r in rows if r["to_quantity"] in ("void", "delam"))))
    if len({r["edge_id"] for r in rows}) != len(rows):
        print("\n   REFUSED: edge_id is not unique.")
        return 1
    if not (args.apply and args.allow_owner):
        print("")
        print("   DRY RUN - nothing written.")
        return 0
    if existing:
        print("")
        print("   REFUSED: %s already holds %d rows." % (TABLE, existing))
        return 1

    columns = ("row_id", "business_key_val", "edge_id", "model", "from_quantity",
               "to_quantity", "dir", "asserted_at")
    with db.engine.begin() as c:
        c.execute(text('INSERT INTO %s (%s) VALUES (%s)'
                       % (TABLE, ", ".join('"%s"' % n for n in columns),
                          ", ".join(":" + n for n in columns))), rows)
    with db.engine.connect() as c:
        after = c.execute(text(f"SELECT count(*) FROM {TABLE}")).scalar()
    print("")
    print("   rows now %s" % after)
    return 0 if after == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
