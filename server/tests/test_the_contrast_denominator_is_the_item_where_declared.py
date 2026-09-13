# -*- coding: utf-8 -*-
"""S-147-b. A control that could not be asked leaves the denominator.

🔴 THE TYPE DENOMINATOR COUNTED THE WRONG THING, and `_propagation`'s own note said so: a
control that measured sixteen quantities reaches `quantity`, so an item it never measured
still read 0/2 and looked like a real difference.

🔴 WHAT TELLS THOSE APART IS WHETHER THE QUESTION WAS DECIDABLE for that control — which is
the verdict S-149 already folded onto every node. So this READS rather than re-derives:
`parents` could answer it too, and counting one fact two ways is a place for the two to
disagree.

⚠️ `unknown` LEAVES THE DENOMINATOR, and that is the whole of the fix. 0/2 becomes 0/0, and
0/0 does not read as a difference.

⚠️ A PREDICATE WITH NO DECLARED CONFIRMER FALLS BACK TO THE TYPE, unchanged. Dropping such a
candidate from the ranking instead would be a folding rule, and folding is the owner's
(판정 332 ①).

⚠️ AND 「does the number change in this box」 IS NOT THE CRITERION. Nothing in the shipped
declaration names a confirmer, so these cases declare their own.
"""
import json
import os
import sys
import uuid
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import explorer                                             # noqa: E402
from ledger_api import ledger_subgraph                             # noqa: E402

NOW = datetime(2026, 9, 13, 3, 0, tzinfo=timezone.utc)

PREDICATE = {"status": "active", "subjects": ["wafer@1"],
             "object": {"kind": "none", "qualifiers": {"required": [], "optional": []}}}


@pytest.fixture
def declared(tmp_path, monkeypatch, request):
    def declare(vocabulary):
        root = tmp_path / "ontology"
        root.mkdir(exist_ok=True)
        (root / "ledger_config.json").write_text(json.dumps({
            "entities": {"wafer@1": {"keys": ["wid"]}},
            "vocabulary": vocabulary}), encoding="utf-8")

        import paths

        monkeypatch.setattr(paths, "config_path",
                            lambda *parts: str(tmp_path.joinpath(*parts)))
        ledger_subgraph.reset_declaration_cache()
    request.addfinalizer(ledger_subgraph.reset_declaration_cache)
    return declare


CONFIRMED = {"inspected@1": dict(PREDICATE),
             "observed@1": dict(PREDICATE, absence_confirmed_by="inspected@1")}
UNCONFIRMED = {"inspected@1": dict(PREDICATE), "observed@1": dict(PREDICATE)}


def _atom(number, wid, predicate, target=None):
    payload = ({"type": "defect", "keys": {"d": target}} if target
               else {"qualifiers": {"product": "A"}})
    return ledger_subgraph.EvidenceAtom(
        id=str(uuid.UUID(int=number)), subject_type="wafer", subject_keys={"wid": wid},
        predicate=predicate, object_kind="entity_ref" if target else None,
        object_payload=payload, occurred_at=NOW, source_who="w",
        source_translator_ver="v1", source_raw_ref="row:%d" % number, supersedes=None,
        source_event_id=str(uuid.UUID(int=700 + number)),
        source_event_state="source_molecule")


def _world(control_examined, control_reaches_type=True):
    """Two cases that found a defect, and one control that may or may not have LOOKED.

    🔴 THE CONTROL REACHES THE TYPE EITHER WAY, and building that is the whole point —
    otherwise the two denominators agree and the case proves nothing. Measured while writing
    this: my first fixture gave the control NO path to `defect` unless it inspected, so the
    type denominator was 0 as well and the test compared two zeros.

    So when it is not examined it still arrives at the same defect by another predicate,
    which is exactly 「a control that measured sixteen quantities reaches `quantity`」: in the
    walk, counted by type, and never actually asked about this item.
    """
    atoms = [_atom(10 + i, "W%d" % i, "register") for i in range(3)]
    atoms += [_atom(20, "W0", "observed", "VOID"), _atom(21, "W1", "observed", "VOID")]
    atoms += [_atom(22, "W0", "inspected", "VOID"), _atom(23, "W1", "inspected", "VOID")]
    if control_examined:
        atoms.append(_atom(24, "W2", "inspected", "VOID"))
    elif control_reaches_type:
        atoms.append(_atom(25, "W2", "related_to", "VOID"))
    return atoms


def _contrast(atoms):
    control = explorer.entity_id("wafer", {"wid": "W2"})
    body = ledger_subgraph.subgraph(
        {"positive": [], "negative": [control]},
        ledger_subgraph.InMemoryEvidenceLookup(atoms), hops=2, seed_type="wafer")
    ranked = body["propagation"].get("ranked") or []
    return body, next((row for row in ranked if row["type"] == "defect"), None)


# ---------------------------------------------------------------------------
# 🔴 declared: the denominator is the item
# ---------------------------------------------------------------------------

def test_a_control_that_was_not_examined_leaves_the_denominator(declared):
    """🔴 THE ROUND. The control REACHED `defect` — it is in the walk, by another predicate —
    but it was never inspected, so its verdict is `unknown` and it cannot be counted against
    the cases."""
    declared(CONFIRMED)

    body, row = _contrast(_world(control_examined=False))

    assert row is not None
    control = explorer.entity_id("wafer", {"wid": "W2"})
    assert any(node["id"] == control for node in body["nodes"]), "the control is in the walk"
    assert row["reachable"][1] == 0, "an unexamined control must not sit in the denominator"


def test_a_control_that_WAS_examined_stays_in_the_denominator(declared):
    """⚠️ THE OTHER HALF. Leaving every control out would make the contrast vacuous — what
    leaves is only the one that could not be asked."""
    declared(CONFIRMED)

    _body, row = _contrast(_world(control_examined=True))

    assert row["reachable"][1] == 1, "an examined control is a real control"


def test_the_cases_still_count_on_their_own_side(declared):
    declared(CONFIRMED)

    _body, row = _contrast(_world(control_examined=False))

    assert row["reachable"][0] == 2, "both cases were examined and found it"
    assert row["reach"][0] == 2


# ---------------------------------------------------------------------------
# ⚠️ undeclared: today's denominator, unchanged
# ---------------------------------------------------------------------------

def test_without_a_declared_confirmer_the_type_denominator_stands(declared):
    """⚠️ NO SILENT CHANGE FOR ANYTHING NOBODY DECLARED. The fallback is the behaviour that
    shipped, and dropping the candidate instead would be a folding rule (판정 332 ①)."""
    declared(UNCONFIRMED)

    _body, row = _contrast(_world(control_examined=True))

    assert row["reachable"][1] == 1, (
        "the control reached the type, which is what the old denominator counts")


def test_the_two_branches_differ_only_where_the_declaration_does(declared):
    """🔴 THE SAME WORLD, TWO DECLARATIONS — so the difference is the DECLARATION and not
    the data. An unexamined control counts under the type denominator and does not count
    under the item one."""
    world = _world(control_examined=False)

    declared(UNCONFIRMED)
    _body, without = _contrast(world)
    declared(CONFIRMED)
    _body, with_cell = _contrast(world)

    assert without["reachable"][1] == 1
    assert with_cell["reachable"][1] == 0


# ---------------------------------------------------------------------------
# ⛔ it reads, it does not re-derive
# ---------------------------------------------------------------------------

def test_the_denominator_reads_the_verdict_rather_than_walking_again():
    """⛔ SCORED ON THE SOURCE. `parents` can answer this too, and a second computation of
    one fact is a place for the two to disagree — which is the argument that chose this
    shape over the one the brief first named."""
    import inspect

    body = inspect.getsource(ledger_subgraph._propagation)
    start = body.index("def _reachable(")
    seat = body[start:body.index("collected = [", start)]

    assert "absence" in seat and "verdict" in seat, seat
    for rederived in ("adjacency", "claims_for_entities", "_reach("):
        assert rederived not in seat, (
            "the denominator walks again instead of reading the verdict: %s" % rederived)
