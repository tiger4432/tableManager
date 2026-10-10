# -*- coding: utf-8 -*-
"""Entity ids as the server spells them (server/ledger/explorer.py entity_id), for keys given in the order a form types
them (lead 10-10: a typed composite key reached the server in the form's order and was refused «entity id is not in
canonical spelling»).

Regenerate (conda env assy_manager), from the repository root:
    python client2/tests/fixtures/capture_entity_ids.py

Writes server_entity_ids.json beside this file. Nothing is read from or written to a database.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "server"))

from ledger.explorer import entity_id  # noqa: E402

# The keys in the order the walk page's cells type them (the declaration's order), as the form holds them (text) and as
# the ledger holds them (numbers).
CASES = [
    ("die", {"mat_id": "M-1", "x": "3", "y": "12", "mat_type": "core"}),
    ("die", {"mat_id": "M-1", "x": 3, "y": 12, "mat_type": "core"}),
    ("lot_slot", {"lot": "LOT-7", "slot": "02"}),
]

out = [{"type": kind, "keys": keys, "id": entity_id(kind, keys)} for kind, keys in CASES]
with open(os.path.join(HERE, "server_entity_ids.json"), "w", encoding="utf-8", newline="\n") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=2)
    fh.write("\n")
print(len(out), "ids")
