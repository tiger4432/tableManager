# Adds `basis` to the ledger-trace CAPTURES, which predate the field.
#
# Run:  conda run -n assy_manager python client2/tests/fixtures/backfill_basis.py
# Idempotent: a second run recomputes and VERIFIES, and prints `verified` instead
# of `wrote`. It touches no database.
#
# 🔴 WHY A RECONSTRUCTION IS EXACT HERE, AND WHERE IT WOULD NOT BE. `basis`
# (server 5bacdfc) and the `reason` suffix are two reports of the SAME two calls
# on the SAME winning claim:
#
#     _basis_label(winner)  ->  `convention:<name>` | `basis=<name>` | None
#     hop_basis(winner)     ->  {kind: convention|measured, name} | None
#
# both branching on `claim_basis(winner)` and `is_convention_backed(winner)`. So
# the suffix determines the field, totally and without a guess. What is NOT
# recoverable that way is the LOSERS' bases, which the sentence also names inline
# — and that is exactly the read that inverted once. The suffix is therefore taken
# ANCHORED AT THE END, the same anchor the client uses, and a reason that carries
# `convention:` only inline yields `null` rather than a convention.
#
# ⚠️ These files stay CAPTURES of the walk; only this one derived field is
# reconstructed, and each file now says so in its own `_basis` note. Re-capturing
# them properly needs the `assy_qa` ledger, which this lane may not touch.
import json
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                "..", "..", "..")))

from server.ledger_trace import BASIS_CONVENTION, BASIS_MEASURED  # noqa: E402

HERE = os.path.dirname(__file__)

#: The same anchor `ledger_trace_core.js` reads with. Inline labels are always
#: followed by ` · 1순위 …`, so they cannot reach `$`.
BASIS_SUFFIX = re.compile(r"\s·\s(convention:|basis=)([^\s·()]+)$")

NOTE = ("`basis` is RECONSTRUCTED from each reason's anchored suffix by "
        "`backfill_basis.py`, not captured — this file predates the field "
        "(server 5bacdfc). The walk, states and sentences are the original "
        "capture. The reconstruction is exact: the suffix and the field are two "
        "reports of the same `claim_basis`/`is_convention_backed` pair on the "
        "same winning claim.")


def basis_of(reason):
    m = BASIS_SUFFIX.search(str(reason or ""))
    if not m:
        return None
    kind = BASIS_CONVENTION if m.group(1) == "convention:" else BASIS_MEASURED
    return {"kind": kind, "name": m.group(2)}


def walk_traces(doc):
    """Every trace object in a fixture, whichever shape the file has."""
    if isinstance(doc, dict) and isinstance(doc.get("hops"), list):
        yield doc
        return
    if isinstance(doc, dict):
        for value in doc.values():
            if isinstance(value, dict) and isinstance(value.get("hops"), list):
                yield value


def main():
    changed = []
    for name in ("ledger_trace_live.json", "ledger_trace_probe.json",
                 "ledger_trace_nothings.json"):
        path = os.path.join(HERE, name)
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
        dirty = False
        for trace in walk_traces(doc):
            for hop in trace["hops"]:
                want = basis_of(hop.get("reason"))
                if "basis" in hop and hop["basis"] != want:
                    raise SystemExit(
                        f"{name}: hop `{hop.get('predicate')}` carries "
                        f"{hop['basis']!r} but its sentence says {want!r} — the "
                        f"capture and the field disagree, which this script may "
                        f"not paper over")
                if "basis" not in hop:
                    hop["basis"] = want
                    dirty = True
        if doc.get("_basis") != NOTE:
            doc["_basis"] = NOTE
            dirty = True
        if dirty:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(doc, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
            changed.append(name)
        counts = {}
        for trace in walk_traces(doc):
            for hop in trace["hops"]:
                key = (hop["basis"] or {}).get("kind", "none")
                counts[key] = counts.get(key, 0) + 1
        print(f"{'wrote  ' if dirty else 'verified'} {name}  {counts}")
    if not changed:
        print("nothing to write — every capture already agrees with its sentences")


if __name__ == "__main__":
    main()
