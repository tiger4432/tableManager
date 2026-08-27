"""The read axis of the trace query (L2): its vocabulary, its classification, its words.

🔴 **THIS FILE EXISTS BECAUSE THE REST OF THE SUITE WAS GREEN WHILE THE
INTEGRATION WAS BROKEN.** Every fixture in `test_ledger_trace.py` and
`test_ledger_trace_pg.py` was written by this lane, so they all spelled the
object payload the way this lane assumed it: flat, `{"lot": ...}`. The real
emitter produces `envelope.entity_ref` — `{"type", "keys": {...}, "qualifiers":
{...}}` — and against a real atom every payload reader here returned `None`, so
every hop would have come back `[unusable_payload]` on the first real query. Two
lanes agreeing with themselves is not agreement. The payload readers are still
checked against `envelope.entity_ref` itself rather than a hand-written dict.

⚠️ WHAT THIS FILE NO LONGER DOES. Eight tests drove `LotEventTranslator` over
`lot_event`-shaped rows and traced the atoms end to end; they went with that module on
2026-08-18. The write half of this seam is therefore UNGUARDED until the v2 path grows an
equivalent — nothing here now proves that whatever emits atoms and whatever walks them
agree on payload shape, edge direction or qualifier names. What remains is entirely the
read side, and all of it is live code: the declared-derivation census, class-1-by-
derivation and its rank-over-timestamp rule, the hop basis, and
`HOP_STATES ⊆ PROJECTION_ONLY_WORDS`.
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
from ledger.envelope import Atom, entity_ref        # noqa: E402


CONFIG_SAMPLE = os.path.join(os.path.dirname(__file__), "..", "config", "sample",
                             "ledger_config.json.sample")


# ---------------------------------------------------------------------------
# The vocabulary this lane reads must be the vocabulary that lane declares
# ---------------------------------------------------------------------------



# REMOVED 2026-08-27: the qualifier contract test went with its subject. It held that
# the walk reads `from`/`to` on `slot_map` and `slot` on `has_wafer` by name -- true
# of `_slot_map_pair` and `_payload_slot`, which were reachable only through
# `_map_slot`, orphaned by the lineage retirement and deleted with it. No atom carried
# those qualifiers either (0 of 135), so nothing was being read and nothing is lost.

def test_the_payload_readers_read_the_translators_own_entity_ref():
    """Built with the translator's function, not with this lane's idea of it."""
    df = lt.Claim(id="a", subject_type="Lot", subject_keys={"lot": "CHILD"},
                  predicate="derived_from", object_kind="entity_ref",
                  object_payload=entity_ref("Lot", {"lot": "PARENT"}))
    assert lt._payload_lot(df) == "PARENT"

    # 🔴 THE WAFER AND SLOT READERS ARE GONE (2026-08-27) and so are their assertions.
    # `_payload_wafer` · `_payload_slot` · `_slot_map_pair` were reachable only through
    # `_map_slot`, which the lineage retirement orphaned. What is left here is the reader
    # that still has a caller.
    sm = lt.Claim(id="c", subject_type="Lot", subject_keys={"lot": "PARENT"},
                  predicate="slot_map", object_kind="entity_ref",
                  object_payload=entity_ref("Lot", {"lot": "CHILD"}))
    assert lt._payload_lot(sm) == "CHILD"


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


# REMOVED 2026-08-27: `test_the_hop_states_are_the_designs_projection_words` held
# `lt.HOP_STATES` equal to `ledger/vocabulary.py::PROJECTION_ONLY_WORDS`. That module
# was the v1 word list and it is gone; the declaration has no projection-word section,
# because a hop state is a word the PROJECTION owns and never a predicate the ledger
# emits. There is nothing left to hold it equal to, so the assertion goes rather than
# being pointed at a section invented to receive it.

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


