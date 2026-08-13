"""The seam between the translator (L1) and the trace query (L2).

🔴 **THIS FILE EXISTS BECAUSE THE REST OF THE SUITE WAS GREEN WHILE THE
INTEGRATION WAS BROKEN.** Every fixture in `test_ledger_trace.py` and
`test_ledger_trace_pg.py` was written by this lane, so they all spelled the
object payload the way this lane assumed it: flat, `{"lot": ...}`. The translator
actually emits `envelope.entity_ref` — `{"type", "keys": {...}, "qualifiers":
{...}}` — and against a real atom every payload reader here returned `None`, so
every hop would have come back `[unusable_payload]` on the first real query. Two
lanes agreeing with themselves is not agreement.

So the fixtures here are NOT written by hand. They are built by calling the
translator's own `entity_ref`, and the atoms are produced by driving
`LotEventTranslator` over `lot_event`-shaped rows with the shipped config. When
L1 changes the payload shape, the direction of an edge or the name of a
qualifier, this file goes red — which is the only way this lane finds out.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import ledger_trace as lt

ledger_pkg = pytest.importorskip(
    "ledger", reason="the ledger translator package (L1) is not present")
from ledger import config as ledger_config          # noqa: E402
from ledger import vocabulary                       # noqa: E402
from ledger.envelope import Atom, entity_ref        # noqa: E402
from ledger.lot_event_translator import (           # noqa: E402
    LotEventTranslator, group_molecules)


CONFIG_SAMPLE = os.path.join(os.path.dirname(__file__), "..", "config",
                             "ledger_config.json.sample")


# ---------------------------------------------------------------------------
# The vocabulary this lane reads must be the vocabulary that lane declares
# ---------------------------------------------------------------------------

def test_every_predicate_the_walk_asks_for_is_declared_and_active():
    for predicate in lt.LINEAGE_PREDICATES:
        assert predicate in vocabulary.PREDICATES, (
            f"the walk asks for {predicate!r}, which the vocabulary does not "
            f"declare - undeclared vocabulary is a gate refusal, not a query")
        assert vocabulary.PREDICATES[predicate]["status"] == "active", (
            f"{predicate!r} is not active in the vocabulary")


def test_the_qualifier_names_the_walk_reads_are_the_ones_declared():
    """`from`/`to`/`slot` are read by name. If the vocabulary renames one, the
    walk goes silently blind rather than loudly wrong — a hop would come back
    `unresolvable` and read as a broken chain in the data."""
    assert set(vocabulary.PREDICATES["slot_map"]["qualifiers"]) >= {"from", "to"}
    assert "slot" in vocabulary.PREDICATES["has_wafer"]["qualifiers"]


def test_the_payload_readers_read_the_translators_own_entity_ref():
    """Built with the translator's function, not with this lane's idea of it."""
    df = lt.Claim(id="a", subject_type="Lot", subject_keys={"lot": "CHILD"},
                  predicate="derived_from", object_kind="entity_ref",
                  object_payload=entity_ref("Lot", {"lot": "PARENT"}))
    assert lt._payload_lot(df) == "PARENT"

    hw = lt.Claim(id="b", subject_type="Lot", subject_keys={"lot": "L"},
                  predicate="has_wafer", object_kind="entity_ref",
                  object_payload=entity_ref("Wafer", {"wafer": "WF.01"}, slot="07"))
    assert lt._payload_wafer(hw) == "WF.01"
    assert lt._payload_slot(hw) == "7"

    sm = lt.Claim(id="c", subject_type="Lot", subject_keys={"lot": "PARENT"},
                  predicate="slot_map", object_kind="entity_ref",
                  object_payload=entity_ref("Lot", {"lot": "CHILD"},
                                            **{"from": "10", "to": "02",
                                               "wafer": "WF.01"}))
    assert lt._payload_lot(sm) == "CHILD"
    assert lt._slot_map_pair(sm) == ("10", "2")


def test_a_slot_is_not_mistaken_for_part_of_the_wafers_identity():
    """`entity_ref` keeps identity in `keys` and everything said about it in
    `qualifiers`, and its docstring names the exact confusion that separation
    prevents. The readers here must honour it: `slot` is never an identity key."""
    hw = lt.Claim(id="b", subject_type="Lot", subject_keys={"lot": "L"},
                  predicate="has_wafer", object_kind="entity_ref",
                  object_payload=entity_ref("Wafer", {"wafer": "WF.01"}, slot="07"))
    assert lt._object_key(hw, "slot") is None, "slot read as wafer identity"
    assert lt._object_qualifier(hw, "wafer") is None or \
        lt._object_key(hw, "wafer") == "WF.01"


# ---------------------------------------------------------------------------
# Atoms from the real translator, traced
# ---------------------------------------------------------------------------

def _translator():
    cfg = ledger_config.load(os.path.abspath(CONFIG_SAMPLE))
    src = ledger_config.source_config(cfg, "lot_event")
    return LotEventTranslator(
        src, ledger_config.translator_version(cfg, "lot_event"),
        ledger_config.declared_derivations(cfg, "lot_event"))


def _row(lot, event_type, parent, child, slots, wafers, when):
    """A source row in the CANONICAL column names `backfill.fetch_page` aliases to.

    Not the physical `lot_event` column names: the `columns` block of the config
    is applied in the SQL projection (`slot_numbers AS slots`), so by the time the
    translator sees a row the mapping has already happened. Building the wrong one
    of those two shapes is how the first version of this file failed.
    """
    return {"row_identity": f"{lot}|{event_type}|{when}", "lot": lot,
            "event_type": event_type, "parent_lot": parent, "child_lot": child,
            "slots": slots, "wafers": wafers, "event_time": when}


def _split_pair(parent, child, parent_slots, parent_wafers,
                child_slots, child_wafers, when):
    """One SPLIT as the source delivers it: two rows, matched into one molecule."""
    return [_row(parent, "split", "", child, parent_slots, parent_wafers, when),
            _row(child, "split", parent, "", child_slots, child_wafers, when)]


def _atoms_to_claims(atoms):
    """`Atom` -> `Claim`. Only the eleven contract columns cross; `molecule_ref`
    and `derivation` are explicitly NOT envelope fields and must not leak in."""
    claims = []
    for i, a in enumerate(atoms):
        assert isinstance(a, Atom)
        claims.append(lt.Claim(
            id=f"{i:032d}", subject_type=a.subject_type,
            subject_keys=a.subject_keys, predicate=a.predicate,
            object_kind=a.object_kind, object_payload=a.object_payload,
            occurred_at=a.occurred_at, source_who=a.source_who,
            source_translator_ver=a.source_translator_ver,
            source_raw_ref=a.source_raw_ref, supersedes=a.supersedes))
    return claims


def _translate(rows):
    tr = _translator()
    atoms = []
    for molecule in group_molecules(rows):
        produced, _report = tr.translate(molecule)
        atoms.extend(produced or [])
    return _atoms_to_claims(atoms)


def test_a_two_hop_chain_from_the_real_translator_traces_end_to_end():
    """🔴 The integration, on atoms this lane did not write.

    Two SPLITs: L-A -> L-B -> L-C. `slot_preserving` is the declared pairing for
    a split, so slot 07 stays slot 07 all the way up.
    """
    rows = []
    rows += _split_pair("L-A", "L-B", "07:01", "WF.07:WF.01",
                        "07:08", "WF.07:WF.08", "2026-05-01 00:00:00")
    rows += _split_pair("L-B", "L-C", "08", "WF.08",
                        "07", "WF.07", "2026-05-02 00:00:00")
    claims = _translate(rows)
    assert claims, "the translator produced nothing - the fixture is wrong"

    answer = lt.trace("L-C", "07", lookup=lt.InMemoryClaimLookup(claims),
                      config=lt.DEFAULT_RESOLVER_CONFIG)

    kinds = [(h["predicate"], h["state"]) for h in answer["hops"]]
    assert ("has_wafer", "unresolvable") not in kinds, (
        f"a real atom read as missing - the payload readers are wrong: {kinds}")
    assert ("derived_from", "resolved") in kinds

    lineage = [h["to"]["keys"]["lot"] for h in answer["hops"]
               if h["predicate"] == "derived_from" and h["to"]]
    assert lineage == ["L-B", "L-A"], f"lineage walked wrong: {lineage}"

    wafers = [h["to"]["keys"]["wafer"] for h in answer["hops"]
              if h["predicate"] == "has_wafer" and h["to"]]
    assert wafers == ["WF.07", "WF.07", "WF.07"], wafers

    slot_hops = [h for h in answer["hops"] if h["predicate"] == "slot_map"]
    assert [h["state"] for h in slot_hops] == ["resolved", "resolved"], (
        f"slot_map direction misread: "
        f"{[(h['state'], h['reason']) for h in slot_hops]}")
    assert [h["to"]["slot"] for h in slot_hops] == ["7", "7"]
    assert "root" in answer["terminal_reason"] and "L-A" in answer["terminal_reason"]


def test_the_slot_map_direction_is_read_from_the_subject_not_guessed():
    """The translator makes the PARENT the subject of `slot_map` and the CHILD the
    object, with `from` on the parent side. The walk goes child -> parent, so it
    meets every one of those atoms "backwards"; if it assumed subject == child it
    would find no pairing and report an unbroken chain as broken."""
    rows = _split_pair("L-P", "L-K", "01", "WF.01", "05", "WF.05",
                       "2026-05-01 00:00:00")
    claims = _translate(rows)
    sm = [c for c in claims if c.predicate == "slot_map"]
    assert sm, "no slot_map atoms produced"
    for c in sm:
        assert c.subject_keys["lot"] == "L-P", "subject is no longer the parent"
        assert lt._payload_lot(c) == "L-K", "object is no longer the child"

    answer = lt.trace("L-K", "05", lookup=lt.InMemoryClaimLookup(claims),
                      config=lt.DEFAULT_RESOLVER_CONFIG)
    hop = [h for h in answer["hops"] if h["predicate"] == "slot_map"][0]
    assert hop["state"] == "resolved", hop["reason"]
    assert hop["to"]["slot"] == "5"


def test_a_merge_pairs_slots_by_shared_wafer_and_the_walk_follows_it():
    """A merge declares `shared_wafer`, so `from` and `to` genuinely differ —
    the case where reading the direction backwards produces a WRONG slot rather
    than no slot, which no `unresolvable` would warn about."""
    rows = [
        _row("L-SRC", "merge", "", "L-DST", "10", "WF.99", "2026-05-03 00:00:00"),
        _row("L-DST", "merge", "L-SRC", "", "02", "WF.99", "2026-05-03 00:00:00"),
    ]
    claims = _translate(rows)
    sm = [c for c in claims if c.predicate == "slot_map"]
    assert len(sm) == 1, [c.object_payload for c in sm]
    assert lt._slot_map_pair(sm[0]) == ("10", "2")

    answer = lt.trace("L-DST", "02", lookup=lt.InMemoryClaimLookup(claims),
                      config=lt.DEFAULT_RESOLVER_CONFIG)
    hop = [h for h in answer["hops"] if h["predicate"] == "slot_map"][0]
    assert hop["state"] == "resolved", hop["reason"]
    assert hop["to"]["slot"] == "10", (
        "the walk carried the position to the wrong slot - the direction was "
        "read backwards and nothing would have told anyone")


def test_a_hop_reports_the_derivation_the_translator_stamped_on_the_atom():
    """🔴 The basis of a hop, from the column that already carries it.

    A SPLIT's `slot_map` atoms exist only because the operator DECLARED
    `slot_preserving` — the source never uttered the pairing. The translator
    records that in `source_translator_ver` as a `#<derivation>` suffix, and the
    hop's reason surfaces it, so an investigator can tell a convention from an
    observation without a twelfth column and without leaving the screen.
    """
    rows = _split_pair("L-A", "L-B", "07:01", "WF.07:WF.01",
                       "07:08", "WF.07:WF.08", "2026-05-01 00:00:00")
    claims = _translate(rows)

    sm = [c for c in claims if c.predicate == "slot_map"][0]
    assert "#" in sm.source_translator_ver, sm.source_translator_ver
    assert lt.claim_basis(sm) == "slot_preserving"

    answer = lt.trace("L-B", "07", lookup=lt.InMemoryClaimLookup(claims),
                      config=lt.DEFAULT_RESOLVER_CONFIG)
    hop = [h for h in answer["hops"] if h["predicate"] == "slot_map"][0]
    assert "convention:slot_preserving" in hop["reason"], hop["reason"]
    assert "class=3 inference" in hop["reason"], (
        "a convention-backed atom must resolve at class 3, not class 2")

    hw = [h for h in answer["hops"] if h["predicate"] == "has_wafer"][0]
    assert "basis=positional_row" in hw["reason"], hw["reason"]


def test_every_declared_derivation_is_explicitly_classified():
    """🔴 THE STANDING RULE, as a test — ontology owner, 2026-08-13.

    Every derivation the translator config can stamp on an atom must be a
    derivation this resolver has explicitly placed as either an ASSUMPTION
    (class 3) or an UTTERANCE (class 2). A new one that nobody classifies would
    default to observation, which is precisely the inversion the ruling exists to
    prevent — so it fails here instead, at the moment it is added.

    This is what stops `inference_derivations` being a list that quietly falls
    behind the translator.
    """
    cfg = ledger_config.load(os.path.abspath(CONFIG_SAMPLE))
    declared = set(ledger_config.declared_derivations(cfg, "lot_event"))
    assert declared, "the config declares no derivations - the check is vacuous"

    assumptions = set(lt.DEFAULT_RESOLVER_CONFIG["inference_derivations"])
    utterances = set(UTTERED_DERIVATIONS)

    unclassified = declared - assumptions - utterances
    assert not unclassified, (
        f"derivation(s) {sorted(unclassified)} are declared by the translator but "
        f"this resolver has not placed them. Decide for each one: does the atom's "
        f"content depend on a config-declared ASSUMPTION not present in the source "
        f"row? Yes -> add to DEFAULT_RESOLVER_CONFIG['inference_derivations'] "
        f"(class 3). No -> add to UTTERED_DERIVATIONS here (class 2).")
    assert not (assumptions & utterances), "a derivation classified both ways"


#: Derivations this lane has judged to be UTTERANCES — the source said it, the
#: translator only reshaped it. Held here rather than in `ledger_trace.py` on
#: purpose: the resolver needs to know its assumptions, but the complete
#: enumeration is a TEST concern, and putting it in the module would make the
#: module claim to know every derivation that will ever exist.
UTTERED_DERIVATIONS = {
    "positional_row",   # slots and wafers are paired by the source's own ordering
    "pair_field",       # parent_lot / child_lot are columns the source filled in
    "shared_wafer",     # the same wafer id is uttered on BOTH rows of a merge
    "first_sight",      # a register atom - the entity appeared, no rule applied
}


def test_an_observation_overrides_a_convention_with_nobody_unpinning_anything():
    """🔴 The consequence that decided the ruling, demonstrated.

    A `slot_map` produced under `slot_preserving` says the position stayed at 07.
    A later real observation says it moved to 21. The observation MUST win — and
    win automatically, with no human retracting anything — because a config
    assumption may never outrank measured reality.

    The hop is `candidate`, not `resolved`: the operator is told an assumption
    was overruled and by what, and the convention is NAMED in the reason.
    """
    rows = _split_pair("L-A", "L-B", "07:01", "WF.07:WF.01",
                       "07:08", "WF.07:WF.08", "2026-05-01 00:00:00")
    claims = _translate(rows)
    convention = [c for c in claims if c.predicate == "slot_map"
                  and lt._slot_map_pair(c) == ("7", "7")]
    assert convention, [lt._slot_map_pair(c) for c in claims
                        if c.predicate == "slot_map"]
    assert lt.claim_class(convention[0],
                          lt.DEFAULT_RESOLVER_CONFIG) == lt.CLASS_INFERENCE

    # An observed mapping for the same pair, from a source that stamps no
    # derivation at all - so it is class 2 on the strength of being uttered.
    observed = lt.Claim(
        id="00000000-0000-7000-8000-0000000000ff", subject_type="Lot",
        subject_keys={"lot": "L-A"}, predicate="slot_map",
        object_kind="entity_ref",
        object_payload=entity_ref("Lot", {"lot": "L-B"},
                                  **{"from": "21", "to": "07", "wafer": "WF.07"}),
        occurred_at=convention[0].occurred_at, source_who="bonding_log",
        source_translator_ver="bonding_log/1", source_raw_ref="bonding_log:1")

    answer = lt.trace("L-B", "07",
                      lookup=lt.InMemoryClaimLookup(claims + [observed]),
                      config=lt.DEFAULT_RESOLVER_CONFIG)
    hop = [h for h in answer["hops"] if h["predicate"] == "slot_map"][0]

    assert hop["to"]["slot"] == "21", (
        "the convention outranked a measurement - the exact inversion the "
        "layering value exists to prevent")
    assert hop["event_id"] == observed.id
    assert hop["state"] == "candidate"
    assert hop["n"] == 2
    assert "convention:slot_preserving" in hop["reason"], hop["reason"]


def test_a_merge_hop_reports_the_uttered_derivation_not_the_convention():
    """The counterpart: a merge's pairing IS uttered by the source, so its atoms
    carry a different derivation. If both read the same, the screen could not
    tell a judgement from a fact and the field would be decoration."""
    rows = [
        _row("L-SRC", "merge", "", "L-DST", "10", "WF.99", "2026-05-03 00:00:00"),
        _row("L-DST", "merge", "L-SRC", "", "02", "WF.99", "2026-05-03 00:00:00"),
    ]
    claims = _translate(rows)
    sm = [c for c in claims if c.predicate == "slot_map"][0]
    assert lt.claim_basis(sm) == "shared_wafer"

    answer = lt.trace("L-DST", "02", lookup=lt.InMemoryClaimLookup(claims),
                      config=lt.DEFAULT_RESOLVER_CONFIG)
    hop = [h for h in answer["hops"] if h["predicate"] == "slot_map"][0]
    assert "basis=shared_wafer" in hop["reason"]
    assert "slot_preserving" not in hop["reason"]


def test_a_blank_wafer_makes_no_atom_and_the_walk_says_so_rather_than_lying():
    """The translator refuses to mint `has_wafer` for a blank wafer id — "there is
    a wafer here, I do not know which" is not a claim. The screen must then say
    the position is unknown, not invent one.

    The lists still have EQUAL LENGTH (`03:04` against `:WF.04`): an unequal pair
    is an atomicity refusal that kills the whole molecule, which would test the
    gate rather than this.
    """
    rows = _split_pair("L-A", "L-B", "01", "WF.01", "03:04", ":WF.04",
                       "2026-05-01 00:00:00")
    claims = _translate(rows)
    b_wafers = [c for c in claims
                if c.predicate == "has_wafer" and c.subject_keys["lot"] == "L-B"]
    assert [lt._payload_slot(c) for c in b_wafers] == ["4"], (
        "the blank position minted an atom, or the filled one did not")

    answer = lt.trace("L-B", "03", lookup=lt.InMemoryClaimLookup(claims),
                      config=lt.DEFAULT_RESOLVER_CONFIG)
    hw = [h for h in answer["hops"] if h["predicate"] == "has_wafer"][0]
    assert hw["state"] == "unresolvable"
    assert "no_claim" in hw["reason"] and "L-B" in hw["reason"]
    assert answer["hops"], "the forbidden empty answer"


def test_a_split_that_moved_a_wafer_off_the_parents_row_reads_as_unknown():
    """🔴 A real limit of the source, and the screen must state it rather than
    paper over it.

    Both rows of a SPLIT are POST-event snapshots (the shipped config says so in
    its own words), so a wafer that moved to the child is no longer uttered on the
    parent's row. Walking up the chain therefore reaches a lot where `has_wafer`
    for that position genuinely does not exist — and the honest answer is
    `unresolvable` with a reason, not a guess and not a shorter chain.

    The LINEAGE is unaffected: the walk still reaches the root.
    """
    rows = _split_pair("L-A", "L-B", "01:02", "WF.01:WF.02",
                       "07", "WF.07", "2026-05-01 00:00:00")
    claims = _translate(rows)
    answer = lt.trace("L-B", "07", lookup=lt.InMemoryClaimLookup(claims),
                      config=lt.DEFAULT_RESOLVER_CONFIG)

    wafer_hops = [h for h in answer["hops"] if h["predicate"] == "has_wafer"]
    assert [h["state"] for h in wafer_hops] == ["resolved", "unresolvable"]
    assert wafer_hops[0]["to"]["keys"]["wafer"] == "WF.07"
    assert "lot=L-A" in wafer_hops[1]["reason"]
    assert [h["state"] for h in answer["hops"]
            if h["predicate"] == "derived_from"] == ["resolved", "unresolvable"]
    assert "root" in answer["terminal_reason"]
