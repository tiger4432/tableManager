# Generates `ledger_trace_contested.json` — REAL output of the shipped resolver,
# produced WITHOUT a database.
#
# Run:  conda run -n assy_manager python client2/tests/fixtures/gen_ledger_trace_contested.py
#
# 🔴 WHY THIS FILE EXISTS RATHER THAN A CAPTURE. `contested` (server commit
# 5bacdfc) needs a CROSS-CLASS disagreement: the top class unanimous and a LOWER
# class naming a different answer. The server lane measured the natural ledger and
# found ZERO such hops in 16 lots / 278 hops — `assy_qa` has one translator with no
# class-1 claims — so the state had to be produced in a throwaway schema to be seen
# at all. This box's databases are development copies and must not be touched, so
# the atoms are declared here and fed to `ledger_trace.trace()` through
# `InMemoryClaimLookup`. **The resolver, the reason grammar, the state word and the
# `basis` field are all the server's own** — the only invented thing is the atoms,
# which is the same thing the throwaway schema invented.
#
# 🔴 WHAT THE FIXTURE IS FOR, and every atom below is here for one of these:
#
#   1. A `contested` hop whose WINNER IS A MEASUREMENT and whose LOSER IS A
#      CONVENTION. Its `reason` therefore contains `convention:` inline and ends
#      `basis=pair_field` — the inversion trap, now in the state the trap was
#      never demonstrated in.
#   2. A `resolved` hop whose winner IS a convention, sitting in the same chain.
#      `resolved` + `convention` and `resolved` + `measured` are the same STATE
#      word, which is the whole reason `basis` cannot be inferred from `state`.
#   3. A chain whose ONLY lineage step is the contested one, terminating `[root]`.
#      A client keyed on `state === 'resolved'` calls that "등재됐으나 혈통 주장
#      없음" — a chain that really walked, announced as having no parentage.
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                "..", "..", "..")))

from server import ledger_trace as lt  # noqa: E402

KST = timezone(timedelta(hours=9))
T0 = datetime(2026, 5, 3, 2, 17, 0, tzinfo=KST)

CHILD = "CT-2601-009-A4"
PARENT = "CT-2601-009"
DISSENTING_PARENT = "CT-2601-009-XX"
WAFER = "WF.CT0904"
SLOT = "02"


def claim(id, lot, predicate, payload, minutes=0, who="lot_event", derivation=None):
    """One atom. `derivation` stamps the `#<derivation>` suffix that decides BOTH
    the class and `basis.kind` — `is_convention_backed` reads it for both, which
    is what keeps `basis` from being a second, softer register (server docstring
    on `hop_basis`)."""
    ver = "lot_event/1" + (f"#{derivation}" if derivation else "")
    return lt.Claim(
        id=id, subject_type="Lot", subject_keys={"lot": lot},
        predicate=predicate, object_kind="entity", object_payload=payload,
        occurred_at=T0 + timedelta(minutes=minutes), source_who=who,
        source_translator_ver=ver, source_raw_ref=f"lot_event:{id}")


ATOMS = [
    claim("reg-child", CHILD, "register", {}, 0),
    claim("reg-parent", PARENT, "register", {}, 1),
    claim("hw-child", CHILD, "has_wafer", {"slot": SLOT, "wafer": WAFER}, 2,
          derivation="positional_row"),
    # (1) the contested pair. The observation wins on class; the convention-backed
    #     atom naming a different parent is the live dissent that survives it.
    claim("df-child", CHILD, "derived_from", {"lot": PARENT}, 3,
          derivation="pair_field"),
    claim("df-child-dissent", CHILD, "derived_from", {"lot": DISSENTING_PARENT}, 4,
          derivation="slot_preserving"),
    # (2) undisputed, convention-backed. Reads `resolved`, exactly like hop 0.
    claim("sm-child", CHILD, "slot_map",
          {"lot": PARENT, "from": SLOT, "to": SLOT}, 5,
          derivation="slot_preserving"),
    claim("hw-parent", PARENT, "has_wafer", {"slot": SLOT, "wafer": WAFER}, 6,
          derivation="positional_row"),
    # (3) PARENT carries no `derived_from`, so the walk ends `[root]` and the only
    #     lineage step in the whole chain is the contested one.
]


def main():
    answer = lt.trace(CHILD, SLOT, lookup=lt.InMemoryClaimLookup(ATOMS),
                      config=lt.DEFAULT_RESOLVER_CONFIG)
    out = {
        "_what": ("REAL `ledger_trace.trace()` output over declared atoms and "
                  "`InMemoryClaimLookup` — no database was read. Regenerate with "
                  "`conda run -n assy_manager python "
                  "client2/tests/fixtures/gen_ledger_trace_contested.py`."),
        "_why": ("`contested` needs a cross-class disagreement and the natural "
                 "ledger has none (server 5bacdfc measured 0 in 278 hops). The "
                 "resolver, the reason grammar, the state word and `basis` are "
                 "the server's; only the atoms are declared."),
        "_pins": [
            "hop 1 — contested, winner MEASURED, loser CONVENTION (the inversion "
            "trap in the state it was never shown in)",
            "hop 2 — resolved, winner CONVENTION (same state word as hop 0, whose "
            "winner is measured: `basis` cannot be inferred from `state`)",
            "the only lineage step is hop 1, and the chain still ends [root]",
        ],
        "trace": answer,
    }
    path = os.path.join(os.path.dirname(__file__), "ledger_trace_contested.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    for i, hop in enumerate(answer["hops"]):
        print(i, hop["predicate"], hop["state"], "n=", hop["n"],
              "basis=", hop["basis"])
        print("   ", hop["reason"])
    print("terminal:", answer["terminal_reason"])
    print("wrote", path)


if __name__ == "__main__":
    main()
