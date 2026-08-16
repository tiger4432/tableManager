"""Deterministic composite-CHIP transfer fixture (SYN-* only).

Dry-run by default.  ``--apply`` writes additive ledger atoms through ``LedgerStore``;
the unique atom index makes reruns idempotent.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger.envelope import Atom


SOURCE = "syn_composite_chip"
TRANSLATOR = "syn_composite_chip/1/rules:composite-dag1"
DERIVATION = "transfer_log"
FINAL_CHIPS = ("SYN-CHIP-DEFECT-001", "SYN-CHIP-REFERENCE-001")
LAYERS = 12
CORE_TYPES = ("LOGIC", "MEMORY", "SENSOR")
DT_LOTS = ("SYN-CDT-A", "SYN-CDT-B", "SYN-CDT-C", "SYN-CDT-D")
BASE_TIME = datetime(2026, 8, 14, tzinfo=timezone(timedelta(hours=9)))


def place(kind, keys, position):
    return {"type": kind, "keys": dict(keys), "position": dict(position)}


def build_atoms():
    atoms = []
    for chip_index, final_chip_id in enumerate(FINAL_CHIPS):
        for layer in range(1, LAYERS + 1):
            core_type = CORE_TYPES[(layer - 1) % len(CORE_TYPES)]
            core_wafer = f"SYN-CORE-{chip_index + 1:02d}-{(layer - 1) % 6 + 1:02d}"
            component_id = f"{final_chip_id}:L{layer:02d}"
            state = "unresolvable" if layer == 3 else "candidate" if layer == 7 else "resolved"
            meta = {
                "final_chip_id": final_chip_id, "component_id": component_id,
                "core_type": core_type, "role": f"stack_layer_{layer:02d}",
                "bond_layer": layer, "bond_position": {"chip_x": 0, "chip_y": 0},
                "core_lot": f"SYN-CORE-LOT-{(layer - 1) % 5 + 1:02d}",
                "core_slot": None if state == "unresolvable" else f"{layer:02d}",
                "state": state,
            }
            origin = place("wafer_grid", {"wafer": core_wafer},
                           {"x": layer * 2, "y": chip_index})
            first_lot = DT_LOTS[(layer - 1) % len(DT_LOTS)]
            first_dt = place("dt_slot", {"dt_lot": first_lot,
                                          "dt_slot": f"{layer:02d}"},
                             {"x": layer + 10, "y": chip_index + 1})
            path = [(origin, first_dt)]
            # Different components have different ordered paths; these visit a second DT.
            if layer in (2, 6, 10):
                second_lot = DT_LOTS[layer % len(DT_LOTS)]
                second_dt = place("dt_slot", {"dt_lot": second_lot,
                                               "dt_slot": f"{layer + 20:02d}"},
                                  {"x": layer + 20, "y": chip_index + 2})
                path.append((first_dt, second_dt))
                pick_from = second_dt
            else:
                pick_from = first_dt
            bond = place("bond_layer", {"final_chip_id": final_chip_id,
                                         "layer": layer},
                         {"chip_x": 0, "chip_y": 0, "layer": layer})
            path.append((pick_from, bond))

            for sequence, (source, target) in enumerate(path):
                atoms.append(Atom(
                    subject_type="Wafer", subject_keys={"wafer": core_wafer},
                    predicate="transferred", object_kind="value",
                    object_payload={"from": source, "to": target, "qty": 1,
                                    "sequence": sequence, "component": meta},
                    occurred_at=BASE_TIME + timedelta(days=chip_index,
                                                       minutes=layer * 10 + sequence),
                    source_who=SOURCE, source_translator_ver=TRANSLATOR,
                    source_raw_ref=f"{SOURCE}:{component_id}:{sequence}",
                    derivation=DERIVATION, molecule_ref=component_id))
    return atoms


def validate(atoms):
    by_component = {}
    for atom in atoms:
        component = atom.object_payload["component"]["component_id"]
        by_component.setdefault(component, []).append(atom)
    for component, events in by_component.items():
        events.sort(key=lambda atom: atom.object_payload["sequence"])
        for previous, current in zip(events, events[1:]):
            assert previous.object_payload["to"] == current.object_payload["from"], component
    per_chip = {}
    for events in by_component.values():
        meta = events[0].object_payload["component"]
        row = per_chip.setdefault(meta["final_chip_id"], {"components": 0, "dt": set(),
                                                           "types": set()})
        row["components"] += 1
        row["types"].add(meta["core_type"])
        for event in events:
            for end in (event.object_payload["from"], event.object_payload["to"]):
                if end["type"] == "dt_slot":
                    row["dt"].add((end["keys"]["dt_lot"], end["keys"]["dt_slot"]))
    return per_chip


def apply(atoms):
    from database.database import engine
    from ledger.store import LedgerStore
    from ledger import gate

    accepted = []
    groups = {}
    for atom in atoms:
        groups.setdefault(atom.molecule_ref, []).append(atom)
    for component_id, members in groups.items():
        with gate.building_molecule(SOURCE):
            screened, _ = gate.screen_molecule(
                SOURCE, members, {DERIVATION}, {"Wafer"}, molecule_ref=component_id)
        accepted.extend(screened)
    store = LedgerStore(engine, who=SOURCE)
    store.ensure_schema()
    return store.write_batch(SOURCE, TRANSLATOR, accepted,
                             cursor_value={"fixture": "complete"},
                             molecules=len(groups), refused=0, incomplete=0, reasons={})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    atoms = build_atoms()
    summary = validate(atoms)
    for chip, row in sorted(summary.items()):
        print(chip, "components", row["components"], "DT", len(row["dt"]),
              "types", sorted(row["types"]))
    print("atoms", len(atoms))
    if args.apply:
        print(apply(atoms))
    else:
        print("DRY RUN: pass --apply to write SYN-* atoms")


if __name__ == "__main__":
    main()
