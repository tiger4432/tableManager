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

from datetime import datetime, timezone             # noqa: E402

import ledger_trace as lt

ledger_pkg = pytest.importorskip(
    "ledger", reason="the ledger translator package (L1) is not present")
from ledger import config as ledger_config          # noqa: E402
from ledger import gate                             # noqa: E402
from ledger import vocabulary                       # noqa: E402
from ledger.envelope import Atom, entity_ref        # noqa: E402
from ledger.lot_event_translator import (           # noqa: E402
    LotEventTranslator, group_molecules)


CONFIG_SAMPLE = os.path.join(os.path.dirname(__file__), "..", "config", "sample",
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
        # The molecule scope belongs to whatever drives the translator (ruling R-H-bis
        # 3); in production that is `backfill.run`, and here it is this loop.
        with gate.building_molecule("lot_event"):
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


def _declared_configs():
    """Every ledger config on this box — `.sample` AND the operator's live file.

    🔴 SCORING ONLY `.sample` WAS HALF THE HOLE. `.sample` is what ships; the LIVE file is
    what an operator edits, and since 2026-08-15 it is what the ADMIN SCREEN writes. A
    derivation that arrives by somebody turning on a rule at 4pm would never have been
    seen by a check that reads the shipped file.
    """
    out = []
    for path in (os.path.abspath(CONFIG_SAMPLE),
                 os.path.abspath(os.path.join(os.path.dirname(CONFIG_SAMPLE),
                                              "ledger_config.json"))):
        if os.path.exists(path):
            out.append((os.path.basename(path), ledger_config.load(path)))
    return out


def _every_declared_derivation():
    """`{derivation: {"<file>:<source>", …}}` across EVERY source of EVERY config."""
    found = {}
    for filename, cfg in _declared_configs():
        for source in sorted(s for s in (cfg.get("sources") or {})
                             if not str(s).startswith("__")):
            for derivation in ledger_config.declared_derivations(cfg, source):
                found.setdefault(derivation, set()).add(f"{filename}:{source}")
    return found


def test_every_declared_derivation_is_explicitly_classified():
    """🔴 THE STANDING RULE, as a test — ontology owner, 2026-08-13.

    Every derivation the translator config can stamp on an atom must be a derivation this
    resolver has explicitly placed as either an ASSUMPTION (class 3) or an UTTERANCE
    (class 2). A new one that nobody classifies would default to observation, which is
    precisely the inversion the ruling exists to prevent — so it fails here instead, at the
    moment it is added.

    🔴 WIDENED 2026-08-15 FROM ONE SOURCE TO ALL OF THEM, AND THE REASON IS THE `declared`
    GRAMMAR. Until now this scored `lot_event` alone, so the observation and transfer
    grammars' derivations were never scored at all — and, far worse, neither would any rule
    an OPERATOR turns on from the admin screen, where each `emit` rule's name becomes a
    derivation. The whole point of that grammar is that no developer is in the loop, and
    the classification rule is exactly the thing a non-developer would not know exists. A
    rule that survives only by someone remembering holds until the first busy afternoon,
    and its failure mode is an inference-grade claim wearing observation grade, which the
    resolution order then trusts over a real measurement.

    This is what stops `inference_derivations` being a list that quietly falls behind the
    translator.
    """
    declared_by = _every_declared_derivation()
    declared = set(declared_by)
    assert declared, "the config declares no derivations - the check is vacuous"
    # The widening must actually be wide: if this ever reads one source again, the guard is
    # back to where it was and the message above is a lie.
    assert len({site for sites in declared_by.values() for site in sites}) > 1, (
        "only one source was scored - the widening regressed")

    # 🔴 THE DECLARATION IS PART OF THE ANSWER NOW. A `declared`-grammar `emit` rule states
    # its own class, so a rule an operator turned on this afternoon classifies ITSELF - no
    # developer in the loop, which is the whole point of that grammar. The code-side list
    # still covers the three hand-written translators, whose derivations are minted in
    # Python and reviewed there.
    assumptions = set(lt.DEFAULT_RESOLVER_CONFIG["inference_derivations"])
    declared_c3, declared_c2 = set(), set()
    for _filename, cfg in _declared_configs():
        declared_c3 |= set(ledger_config.declared_inference_derivations(cfg))
        for source, declaration in (cfg.get("sources") or {}).items():
            if str(source).startswith("__") or not isinstance(declaration, dict):
                continue
            if declaration.get("kind") != ledger_config.SOURCE_KIND_DECLARED:
                continue
            for rule in declaration.get("emit") or []:
                if isinstance(rule, dict) and \
                        rule.get("class") == ledger_config.EMIT_CLASS_OBSERVATION:
                    declared_c2.add(str(rule.get("rule") or "").strip())
    assumptions |= declared_c3
    utterances = set(UTTERED_DERIVATIONS) | declared_c2
    confirmed = set(lt.DEFAULT_RESOLVER_CONFIG["confirmed_derivations"])

    unclassified = (declared - assumptions - utterances - confirmed
                    - set(AWAITING_CLASSIFICATION))
    assert not unclassified, (
        "derivation(s) "
        + ", ".join(f"{d} (declared by {', '.join(sorted(declared_by[d]))})"
                    for d in sorted(unclassified))
        + " are declared by the translator but this resolver has not placed them. "
          "Decide for each one: does the atom's content depend on a config-declared "
          "ASSUMPTION not present in the source row? Yes -> add to "
          "DEFAULT_RESOLVER_CONFIG['inference_derivations'] (class 3). No -> add to "
          "UTTERED_DERIVATIONS here (class 2). 🔴 If this derivation arrived from an "
          "`emit` rule an operator declared in the admin screen, do NOT guess: the rule's "
          "author knows whether the atom's content came from the row or from a convention, "
          "and picking a label for them is how an assumption ends up outranking a "
          "measurement.")
    assert not (assumptions & utterances), "a derivation classified both ways"
    assert not (confirmed & (assumptions | utterances)), (
        "a derivation is both confirmed (class 1) and classified as 2 or 3")
    assert not (set(AWAITING_CLASSIFICATION) & (assumptions | utterances | confirmed)), (
        "a derivation is both awaiting classification and classified")

    # 🔴 AND `basis.name` IS NOT A SOFTER PLACE TO PUT ONE. The hop's structured
    # basis reports the derivation VERBATIM, so a new one shows up there whether
    # or not anybody classified it — which would be a way for an unclassified
    # derivation to reach the screen looking legitimate. It cannot become a
    # second register, because `kind` is decided by the same list the CLASS is:
    # every declared derivation must map to `convention` iff it is an assumption.
    #
    # 🔴 ANYTHING STILL AWAITING A RULING IS EXCLUDED FROM THIS LOOP ON PURPOSE.
    # `hop_basis` reports anything not in `inference_derivations` as MEASURED, so asserting
    # over an unclassified derivation here would have this test CERTIFY it as measured —
    # the very default the ruling exists to prevent, laundered through an assertion. The
    # quarantine is empty today; the exclusion stays, because the next unclassified
    # derivation must meet the same refusal to score rather than a convenient answer.
    for derivation in sorted(declared - set(AWAITING_CLASSIFICATION)):
        c = lt.Claim(
            id="00000000-0000-7000-8000-00000000000d", subject_type="Lot",
            subject_keys={"lot": "L-A"}, predicate="slot_map",
            object_kind="entity_ref",
            object_payload=entity_ref("Lot", {"lot": "L-B"},
                                      **{"from": "1", "to": "2"}),
            occurred_at=None, source_who="lot_event",
            source_translator_ver=f"lot_event/1#{derivation}",
            source_raw_ref="lot_event:1")
        basis = lt.hop_basis(c, lt.DEFAULT_RESOLVER_CONFIG)
        assert basis == {"kind": (lt.BASIS_CONVENTION if derivation in assumptions
                                  else lt.BASIS_MEASURED),
                         "name": derivation}, (
            f"{derivation}: the hop's basis field disagrees with the "
            f"classification this test just forced")


def _dt_log_claim(derivation, occurred_at, atom_id, to_keys, to_type):
    """A `transferred` claim shaped like the real `dt_log` atoms, both derivations."""
    return lt.Claim(
        id=atom_id, subject_type="Wafer", subject_keys={"wafer": "WF.010120"},
        predicate="transferred", object_kind="value",
        object_payload={"to": {"type": to_type, "keys": to_keys},
                        "from": {"type": "wafer_grid",
                                 "keys": {"wafer": "WF.010120"}},
                        "qty": 1,
                        "container_recorded": [{"dt_lot": "DT-2601-001",
                                                "dt_slot": "01"}]},
        occurred_at=occurred_at, source_who="dt_log",
        source_translator_ver=f"dt_log/1/rules:889599a1#{derivation}",
        source_raw_ref="dt_log:{}")


def test_a_confirmed_container_is_class_1_and_an_unconfirmed_job_is_class_2():
    """🔴 CLASS 1'S FIRST USE, ranked rather than merely declared (ruling 2026-08-15)."""
    cfg = lt.DEFAULT_RESOLVER_CONFIG
    confirmed = _dt_log_claim("job_run_to_confirmed_container",
                              datetime(2026, 5, 11, tzinfo=timezone.utc),
                              "00000000-0000-7000-8000-00000000000a",
                              {"dt_lot": "DT_LOT", "dt_slot": "1"}, "dt_slot")
    job = _dt_log_claim("job_run_to_job",
                        datetime(2026, 5, 11, tzinfo=timezone.utc),
                        "00000000-0000-7000-8000-00000000000b",
                        {"dt_job": "DT-EQP-01_20260511T0000_T01"}, "dt_job")

    assert lt.claim_class(confirmed, cfg) == lt.CLASS_CONFIRMED == 1
    assert lt.claim_class(job, cfg) == lt.CLASS_OBSERVATION == 2
    assert lt.CLASS_NAMES[lt.claim_class(confirmed, cfg)] == "confirmed"


def test_the_confirmed_container_WINS_by_rank_and_not_by_timestamp():
    """🔴 THE POINT OF PUTTING IT ON A DIFFERENT RUNG, and the gap it closes.

    Under equal class 2 the tiebreak is `occurred_at` DESC then id, so a wafer carrying
    both would resolve by whichever happened to be stamped later — arbitrary, and wrong
    about half the time. The test therefore gives the LOSER every tiebreak advantage: the
    unconfirmed job claim is NEWER and its id sorts FIRST. It must still lose, because
    §6 says 「2·3층은 계급을 넘지 못한다」 and class 1 is above both.
    """
    cfg = lt.DEFAULT_RESOLVER_CONFIG
    confirmed = _dt_log_claim("job_run_to_confirmed_container",
                              datetime(2026, 5, 11, tzinfo=timezone.utc),
                              "00000000-0000-7000-8000-0000000000ff",
                              {"dt_lot": "DT_LOT", "dt_slot": "1"}, "dt_slot")
    newer_job = _dt_log_claim("job_run_to_job",
                              datetime(2026, 8, 15, tzinfo=timezone.utc),   # NEWER
                              "00000000-0000-7000-8000-00000000000a",       # sorts FIRST
                              {"dt_job": "DT-EQP-01_20260511T0000_T01"}, "dt_job")

    winner = min([newer_job, confirmed], key=lambda c: lt.claim_rank_key(c, cfg))
    assert winner is confirmed, (
        "the unconfirmed job claim won on recency - class 1 is not being ranked, so the "
        "rung is declared and unconsumed")
    assert lt.claim_rank_key(confirmed, cfg)[0] < lt.claim_rank_key(newer_job, cfg)[0], (
        "the class element of the rank tuple does not separate them")


def test_what_the_hop_basis_reports_for_a_class_1_claim():
    """⚠️ Reported so it is a known limit rather than a discovered one.

    `basis.kind` is decided by `is_convention_backed` alone, so class 1 and class 2 BOTH
    report `measured` and this field cannot tell them apart. Widening `BASIS_KINDS` is a
    response-shape change for every consumer that switches on `kind` — a product owner's
    decision, not a side effect of a classification ruling. Pinned here so that if anyone
    later widens it, they do it deliberately and this test is the conversation.
    """
    cfg = lt.DEFAULT_RESOLVER_CONFIG
    confirmed = _dt_log_claim("job_run_to_confirmed_container",
                              datetime(2026, 5, 11, tzinfo=timezone.utc),
                              "00000000-0000-7000-8000-00000000000a",
                              {"dt_lot": "DT_LOT", "dt_slot": "1"}, "dt_slot")
    basis = lt.hop_basis(confirmed, cfg)
    assert basis == {"kind": lt.BASIS_MEASURED,
                     "name": "job_run_to_confirmed_container"}
    assert lt.BASIS_KINDS == (lt.BASIS_CONVENTION, lt.BASIS_MEASURED), (
        "the basis enum widened - if that was deliberate, this test is where the class-1 "
        "distinction should now be asserted instead")


def test_the_hop_states_are_the_designs_projection_words():
    """🔴 The route's state enum against the design's own vocabulary.

    `ledger/vocabulary.py::PROJECTION_ONLY_WORDS` declared `contested` before
    this route emitted it — it is design §4.2's projection vocabulary, and the
    gate uses it to REFUSE those words as predicates. `ledger_trace.py`
    deliberately does not import that module (the web server must not import the
    translator package), so the two spellings are held equal here instead.

    That is what stops the route inventing a fifth state word under a private
    spelling: a new hop state has to be a word the design already owns.
    """
    stray = set(lt.HOP_STATES) - vocabulary.PROJECTION_ONLY_WORDS
    assert not stray, (
        f"hop state(s) {sorted(stray)} are not in the design's projection "
        f"vocabulary. Add them to `PROJECTION_ONLY_WORDS` (and to the design) "
        f"before the route emits them.")
    assert lt.STATE_CONTESTED in vocabulary.PROJECTION_ONLY_WORDS


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
    # 🔴 RULED 2026-08-15, ontology owner. Surfaced by widening this test past
    # `lot_event`; 114,483 atoms whose class was CORRECT and UNSTATED (reached by
    # `claim_class`'s fall-through rather than by anybody deciding). Every field of the
    # atom is a column of the row and nothing was added the row did not utter.
    "observation_row",
    # 🔴 RULED 2026-08-15, and this one was the argument. Its sibling took the
    # destination identity from a declared confirmation relation; THIS one could not
    # confirm, so it names the acquisition job and asserts LESS - `container_recorded`
    # is present on the atom and deliberately not used as identity. Class 3 was the
    # tempting answer and it is wrong: a convention means content the row never uttered
    # was ADDED, and here available content was WITHHELD. Withholding is not inferring,
    # and ranking careful restraint as a guess would punish exactly the behaviour this
    # ledger is built to reward.
    "job_run_to_job",
}

#: 🔴 CLASS 1 — 「확정된 체인 주장」. Ruled 2026-08-15; the FIRST use of this rung for
#: anything but `frame_confirmed`, and the reason it is a rung rather than a good class 2
#: is on the atom: its `to` identity comes from the declared confirmation relation and
#: MEASURED it DISAGREES with `container_recorded`, the row's own written-down value kept
#: beside it as evidence. A claim that may override what the source row said does not
#: compete with observations as an equal. Held here beside the other two so the complete
#: enumeration stays in one place - the resolver owns the LIST it ranks by
#: (`confirmed_derivations`), this file owns the CENSUS.
CONFIRMED_DERIVATIONS = {"job_run_to_confirmed_container"}

#: 🔴 DERIVATIONS THAT ARRIVED WITHOUT A CLASSIFICATION, AND ARE AWAITING A RULING.
#:
#: These three were surfaced the moment the test above widened past `lot_event`
#: (2026-08-15). They are NOT a backlog of chores: each one has been stamped on real atoms
#: for as long as its grammar has existed, and none of them was ever placed as an assumption
#: or an utterance. They are quarantined here — named, counted, and excluded from the basis
#: assertion — rather than labelled, because picking a label for convenience is exactly the
#: failure this whole check exists to prevent, and the difference between class 2 and class
#: 3 decides which claim wins when two disagree.
#:
#: ⚠️ WHY QUARANTINE AND NOT A FAILING TEST: a red test in the tree gets muted or deleted.
#: A named list keeps the guard LIVE for every future derivation — including every rule an
#: operator declares from the admin screen — while making the open question impossible to
#: lose. Membership is pinned below, so nothing can join this list quietly.
#:
#: 🔴 THE OPEN QUESTION FOR EACH, stated so the ruling does not have to rediscover it:
#:   `observation_row`                  one source row, uttered as it stands. The
#:                                      translator reshapes and does not infer — but no
#:                                      one has said so on the record.
#:   `job_run_to_confirmed_container`   the destination's identity came from the DECLARED
#:                                      confirmation relation, i.e. the data confirmed it.
#:   `job_run_to_job`                   the destination could NOT be confirmed, so the atom
#:                                      names the acquisition job instead. This is the one
#:                                      that genuinely reads both ways: it is an honest
#:                                      weaker utterance, not a convention — and yet what it
#:                                      asserts about location is less than what a confirmed
#:                                      container asserts. Whichever way it goes, the two
#:                                      transfer derivations should probably not land in the
#:                                      same class, and that is the point of asking.
AWAITING_CLASSIFICATION = ()


def test_the_quarantine_is_empty():
    """✅ All three were ruled on 2026-08-15 and the quarantine emptied the same day.

    The tuple stays — with this test — because the mechanism is what has value, not the
    names that were briefly in it. Its danger was always that it becomes a comfortable
    place to park the next unclassified derivation, at which point the widened check above
    is decorative. Empty and asserted empty, adding a name is a deliberate edit that shows
    up in a diff beside this docstring, and it should carry a date and a reason for asking.
    """
    assert AWAITING_CLASSIFICATION == (), (
        f"{sorted(AWAITING_CLASSIFICATION)} are parked without a classification. That is "
        f"legitimate only while a ruling is genuinely pending - name the ruling here.")


def test_the_confirmed_derivations_are_ranked_by_the_resolver_not_just_listed():
    """🔴 The condition attached to ruling class 1: a rank that does not rank is a
    declaration with nothing reading it, and this repo has shipped three of those today.

    So this asserts the CENSUS in this file and the LIST the resolver ranks by are the same
    set. If `confirmed_derivations` were dropped from the resolver config, the name would
    still sit in `CONFIRMED_DERIVATIONS` looking authoritative and every such atom would
    silently fall back to class 2.
    """
    assert CONFIRMED_DERIVATIONS == set(
        lt.DEFAULT_RESOLVER_CONFIG["confirmed_derivations"])
    assert CONFIRMED_DERIVATIONS <= set(_every_declared_derivation()), (
        "a confirmed derivation is no longer declared by any config")


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
    # The class DECLARED this winner (class 2 over class 3) and the assumption
    # still disagrees — `contested`, not `candidate`. R-2026-08-13-B week 2.
    assert hop["state"] == lt.STATE_CONTESTED
    assert hop["n"] == 2
    assert "convention:slot_preserving" in hop["reason"], hop["reason"]

    # 🔴 AND THE STRUCTURED FIELD DESCRIBES THE WINNER, WHICH IS THE MEASUREMENT.
    # `bonding_log/1` carries no `#derivation`, so the winner has no declared
    # basis at all — while the word `convention:` sits in the same sentence,
    # belonging to the claim that lost. A consumer reading the prose gets this
    # backwards; a consumer reading the field cannot.
    assert hop["basis"] is None, (
        f"the losing convention leaked into the winner's basis: {hop['basis']}")


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
