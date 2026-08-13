"""The ledger lineage resolver and walk — `server/ledger_trace.py`.

Every test here runs on plain Python objects through `InMemoryClaimLookup`, so
the resolver is scored WITHOUT a database. The database half (the recursive CTE,
and the proof that swapping the lookup does not change the answer) is
`test_ledger_trace_pg.py`, which needs an isolated PostgreSQL.

Three of these tests carry a MUTANT of the thing they guard, in the shape
`test_cell_value_resolution.py` established: the broken implementation is
injected back into the file and the same scenario is run through it, so the test
proves it can tell the two apart. A guard that has never been shown to go red is
a guard nobody has tested.
"""

import os
import random
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import ledger_trace as lt
from database import crud


#: Fixtures carry a REAL +09:00 offset, not UTC. Fab timestamps are local
#: Asia/Seoul, and a suite whose every instant was UTC could not tell a
#: correct implementation from one that silently normalises to UTC - the
#: two agree on exactly the inputs a UTC fixture provides.
KST = timezone(timedelta(hours=9))
T0 = datetime(2026, 8, 1, 12, 0, 0, tzinfo=KST)


def claim(id, lot, predicate, payload, occurred_at=T0, who="lot_event",
          supersedes=None, subject_type="Lot", derivation=None):
    """One atom. `derivation` stamps the translator's `#<derivation>` suffix.

    That suffix is the ONLY place the derivation lives — `claim_basis` reads it
    and `hop_basis` reports it — so a fixture that wants a convention-backed atom
    stamps it here rather than setting a field the envelope does not have.
    """
    ver = "lot_event/1" + (f"#{derivation}" if derivation else "")
    return lt.Claim(
        id=id, subject_type=subject_type, subject_keys={"lot": lot},
        predicate=predicate, object_kind="entity", object_payload=payload,
        occurred_at=occurred_at, source_who=who,
        source_translator_ver=ver, source_raw_ref=f"lot_event:{id}",
        supersedes=supersedes)


def chain(lots, slots=None, wafers=None, who="lot_event"):
    """A straight lineage `lots[0] -> lots[1] -> ...` (child first).

    `lots[i]` is `derived_from` `lots[i+1]`, position carried by `slot_map`,
    wafer named by `has_wafer`.
    """
    atoms = []
    for i, lot in enumerate(lots):
        atoms.append(claim(f"reg-{lot}", lot, "register", {}, who=who))
        if slots is not None and wafers is not None:
            atoms.append(claim(f"hw-{lot}", lot, "has_wafer",
                               {"slot": slots[i], "wafer": wafers[i]}, who=who))
        if i + 1 < len(lots):
            parent = lots[i + 1]
            atoms.append(claim(f"df-{lot}", lot, "derived_from",
                               {"lot": parent}, who=who))
            if slots is not None:
                atoms.append(claim(f"sm-{lot}", lot, "slot_map",
                                   {"lot": parent, "from": slots[i],
                                    "to": slots[i + 1]}, who=who))
    return atoms


def run(atoms, lot, slot=None, max_depth=lt.DEFAULT_MAX_DEPTH):
    return lt.trace(lot, slot, lookup=lt.InMemoryClaimLookup(atoms),
                    config=lt.DEFAULT_RESOLVER_CONFIG, max_depth=max_depth)


def states(answer, predicate=None):
    return [(h["predicate"], h["state"]) for h in answer["hops"]
            if predicate is None or h["predicate"] == predicate]


# ---------------------------------------------------------------------------
# The forbidden answer
# ---------------------------------------------------------------------------

def test_empty_ledger_still_answers():
    """🔴 An empty result is the one thing this screen may never return.

    Brief §3-2: "빈 결과 금지 — 어느 홉에서 왜 끊겼는지가 이 화면의 존재 이유다."
    With NOTHING in the ledger the answer still names the lot and says the
    ledger has no atoms about it.
    """
    answer = run([], "L-NOTHING", "3")
    assert answer["hops"], "an empty hop list is the forbidden answer"
    assert len(answer["hops"]) == 1
    hop = answer["hops"][0]
    assert hop["state"] == "unresolvable"
    assert hop["from"] == {"type": "Lot", "keys": {"lot": "L-NOTHING"}, "slot": "3"}
    assert hop["to"] is None
    assert "L-NOTHING" in hop["reason"]
    assert "unknown_subject" in answer["terminal_reason"]
    assert "L-NOTHING" in answer["terminal_reason"]


def test_every_terminal_path_produces_hops_and_a_reason():
    """The invariant across all five ways a walk can end."""
    cases = {
        "unknown_subject": ([], "L-X"),
        "root": (chain(["L-A"]), "L-A"),
        "dead_end": ([claim("hw", "L-A", "has_wafer", {"slot": "1", "wafer": "W"})],
                     "L-A"),
        "cycle": ([claim("d1", "L-A", "derived_from", {"lot": "L-B"}),
                   claim("d2", "L-B", "derived_from", {"lot": "L-A"}),
                   claim("r1", "L-A", "register", {}),
                   claim("r2", "L-B", "register", {})], "L-A"),
        "depth_cap": (chain([f"L-{i}" for i in range(8)]), "L-0"),
    }
    for expected, (atoms, lot) in cases.items():
        answer = run(atoms, lot, max_depth=3)
        assert answer["hops"], f"{expected}: empty hops"
        assert answer["terminal_reason"], f"{expected}: no terminal reason"
        assert expected in answer["terminal_reason"], (
            f"{expected}: got {answer['terminal_reason']!r}")


# ---------------------------------------------------------------------------
# The broken chain — the acceptance criterion
# ---------------------------------------------------------------------------

def test_deleting_a_has_wafer_atom_names_the_hop_and_the_reason():
    """🔴 THE acceptance criterion (brief §7): break the chain, get told where.

    The lineage is unaffected — the lot chain still walks to its root — and the
    ONE question that lost its atom is the one hop that comes back
    `unresolvable`, naming the lot and the slot.
    """
    atoms = chain(["L-C", "L-B", "L-A"], slots=["3", "5", "9"],
                  wafers=["W-3", "W-5", "W-9"])
    whole = run(atoms, "L-C", "3")
    assert all(h["state"] == "resolved" for h in whole["hops"]
               if h["predicate"] == "has_wafer")

    broken = [a for a in atoms if a.id != "hw-L-B"]
    answer = run(broken, "L-C", "3")

    wafer_hops = [h for h in answer["hops"] if h["predicate"] == "has_wafer"]
    assert [h["state"] for h in wafer_hops] == ["resolved", "unresolvable", "resolved"]

    bad = wafer_hops[1]
    assert bad["from"]["keys"]["lot"] == "L-B"
    assert bad["from"]["slot"] == "5"
    assert bad["to"] is None
    assert bad["rank"] is None and bad["n"] is None
    assert "no_claim" in bad["reason"]
    assert "has_wafer" in bad["reason"]
    assert "L-B" in bad["reason"] and "slot=5" in bad["reason"]

    # The chain itself did NOT break: the walk still reached the root.
    assert "root" in answer["terminal_reason"] and "L-A" in answer["terminal_reason"]
    assert [h["state"] for h in answer["hops"] if h["predicate"] == "derived_from"] \
        == ["resolved", "resolved", "unresolvable"]


def test_deleting_a_derived_from_atom_breaks_the_walk_at_that_lot():
    atoms = chain(["L-C", "L-B", "L-A"], slots=["3", "5", "9"],
                  wafers=["W-3", "W-5", "W-9"])
    answer = run([a for a in atoms if a.id != "df-L-B"], "L-C", "3")
    last = answer["hops"][-1]
    assert last["predicate"] == "derived_from"
    assert last["state"] == "unresolvable"
    assert "L-B" in last["reason"] and "register 있음" in last["reason"]
    assert "root" in answer["terminal_reason"]


def test_a_lot_with_no_register_reads_as_dead_end_not_as_root():
    """`register` is what tells "the chain ends here" from "the ledger never
    heard of this lot" — which is the whole reason it is in the v0 vocabulary."""
    atoms = chain(["L-B", "L-A"])
    rooted = run(atoms, "L-B")
    assert "root" in rooted["terminal_reason"]

    orphan = run([a for a in atoms if a.id != "reg-L-A"], "L-B")
    assert "unknown_subject" in orphan["terminal_reason"]


# ---------------------------------------------------------------------------
# candidate(rank, n)
# ---------------------------------------------------------------------------

def test_candidate_reports_rank_and_n_when_answers_compete():
    atoms = [
        claim("reg", "L-C", "register", {}),
        claim("d1", "L-C", "derived_from", {"lot": "L-P1"}, occurred_at=T0),
        claim("d2", "L-C", "derived_from", {"lot": "L-P2"},
              occurred_at=T0 + timedelta(hours=1)),
        claim("d3", "L-C", "derived_from", {"lot": "L-P3"},
              occurred_at=T0 + timedelta(hours=2)),
    ]
    answer = run(atoms, "L-C")
    hop = [h for h in answer["hops"] if h["predicate"] == "derived_from"][0]
    assert hop["state"] == "candidate"
    assert hop["rank"] == 1
    assert hop["n"] == 3, "three competing parents, reported as three"
    # newest wins inside the class, so the followed answer is L-P3
    assert hop["to"]["keys"]["lot"] == "L-P3"
    assert hop["event_id"] == "d3"
    for lot in ("L-P1", "L-P2", "L-P3"):
        assert lot in hop["reason"]


def test_agreeing_witnesses_are_not_a_contest():
    """Three atoms naming the SAME parent is agreement. Calling it `candidate`
    would teach the screen to cry wolf, and a screen that cries wolf is read as
    noise on the day it is right."""
    atoms = [
        claim("reg", "L-C", "register", {}),
        claim("d1", "L-C", "derived_from", {"lot": "L-P"}, occurred_at=T0),
        claim("d2", "L-C", "derived_from", {"lot": "L-P"},
              occurred_at=T0 + timedelta(hours=1)),
        claim("d3", "L-C", "derived_from", {"lot": "L-P"},
              occurred_at=T0 + timedelta(hours=2)),
    ]
    hop = [h for h in run(atoms, "L-C")["hops"]
           if h["predicate"] == "derived_from"][0]
    assert hop["state"] == "resolved"
    assert (hop["rank"], hop["n"]) == (1, 1)
    assert "agreed" in hop["reason"] and "3건" in hop["reason"]


def test_a_disagreeing_lower_class_makes_the_hop_contested():
    """🔴 The class decides WHICH answer is followed. It does not decide whether
    a disagreement happened, and the screen must report the disagreement.

    The confirmed claim still wins outright — that part is never in doubt — but
    two other claims named different parents, and a hop that rendered `resolved`
    would hide exactly what an investigator opened this screen to see.

    The word is `contested` as of R-2026-08-13-B week 2: the class DECLARED this
    winner and the dispute survived it. That is a different state from "k answers
    at one authority and only a tiebreak between them", which keeps `candidate`.
    """
    atoms = [
        claim("reg", "L-C", "register", {}),
        claim("c1", "L-C", "derived_from", {"lot": "L-TRUE", "confirmed": True}),
        claim("o1", "L-C", "derived_from", {"lot": "L-WRONG1"},
              occurred_at=T0 + timedelta(days=9)),
        claim("o2", "L-C", "derived_from", {"lot": "L-WRONG2"},
              occurred_at=T0 + timedelta(days=9), who="user"),
    ]
    hop = [h for h in run(atoms, "L-C")["hops"]
           if h["predicate"] == "derived_from"][0]
    assert hop["to"]["keys"]["lot"] == "L-TRUE", "the ranking must not move"
    assert hop["state"] == lt.STATE_CONTESTED
    assert hop["n"] == 3, "three distinct answers were in contention"
    assert "하위 계급 반대 2종" in hop["reason"]
    assert "L-WRONG1" in hop["reason"] and "L-WRONG2" in hop["reason"]


def test_a_lower_class_that_AGREES_is_not_a_contest():
    """Agreement across classes stays `resolved`. A screen that cries wolf is
    read as noise on the day it is right."""
    atoms = [
        claim("reg", "L-C", "register", {}),
        claim("c1", "L-C", "derived_from", {"lot": "L-TRUE", "confirmed": True}),
        claim("o1", "L-C", "derived_from", {"lot": "L-TRUE"},
              occurred_at=T0 + timedelta(days=9)),
    ]
    hop = [h for h in run(atoms, "L-C")["hops"]
           if h["predicate"] == "derived_from"][0]
    assert hop["state"] == "resolved"
    assert hop["n"] == 1
    assert "class_wins" in hop["reason"] and "같은 답" in hop["reason"]


# ---------------------------------------------------------------------------
# contested vs candidate — R-2026-08-13-B week 2
# ---------------------------------------------------------------------------
#
# 🔴 THE CONDITION THAT ENDS HERE. `candidate` was allowed as an umbrella for
# slice 1 ONLY because `reason` carried the real distinction. It now lives in the
# `state` field, because a client acting differently on the two is the whole
# point and no client should have to read Korean to do it.
#
#     contested   the class DECLARED a winner; a lower class still disagrees
#     candidate   the top class is split k ways; only a tiebreak separates them


def _derived_from_hop(atoms, lot="L-C"):
    return [h for h in run(atoms, lot)["hops"]
            if h["predicate"] == "derived_from"][0]


REGISTER = claim("reg", "L-C", "register", {})


def test_contested_and_candidate_are_two_states_not_one():
    """The split, driven from both sides in one test so the pair is visible.

    Same `n`, same rank, same winner-is-followed guarantee — and different
    states, because the AUTHORITY behind the winner differs. That is the fact a
    consumer branches on: `contested` has a declared winner with a live
    contradiction under it; `candidate` has no declared winner at all.
    """
    contested = _derived_from_hop([
        REGISTER,
        claim("c1", "L-C", "derived_from", {"lot": "L-TRUE", "confirmed": True}),
        claim("o1", "L-C", "derived_from", {"lot": "L-OTHER"},
              occurred_at=T0 + timedelta(days=9)),
    ])
    candidate = _derived_from_hop([
        REGISTER,
        claim("o1", "L-C", "derived_from", {"lot": "L-P1"}, occurred_at=T0),
        claim("o2", "L-C", "derived_from", {"lot": "L-P2"},
              occurred_at=T0 + timedelta(hours=1)),
    ])

    assert contested["state"] == lt.STATE_CONTESTED
    assert candidate["state"] == lt.STATE_CANDIDATE
    assert contested["state"] != candidate["state"], (
        "the two collapsed back into one word - R-2026-08-13-B week 2 undone")
    # Everything the old umbrella carried is unchanged: both report a rank, a
    # count, and a followed answer. Only the word got more precise.
    assert (contested["rank"], contested["n"]) == (1, 2)
    assert (candidate["rank"], candidate["n"]) == (1, 2)
    assert contested["to"]["keys"]["lot"] == "L-TRUE"
    assert candidate["to"]["keys"]["lot"] == "L-P2"
    # 🔴 The `[tag]` follows the state, so the prose and the field cannot drift.
    assert contested["reason"].startswith("[contested]")
    assert candidate["reason"].startswith("[candidate]")


def test_a_split_top_class_reads_candidate_even_when_a_lower_class_also_dissents():
    """🔴 BOTH conditions at once, and the WEAKER word wins.

    `contested` asserts "a winner was DECLARED". A top class that disagrees with
    itself declared nothing — the tiebreak levels did — so claiming `contested`
    here would overstate the authority behind the answer. The lower-class dissent
    does not disappear: it is still named in `reason` and still counted in `n`.
    """
    hop = _derived_from_hop([
        REGISTER,
        # two class-1 claims that do NOT agree: nothing declared a winner
        claim("c1", "L-C", "derived_from", {"lot": "L-A", "confirmed": True},
              occurred_at=T0 + timedelta(hours=1)),
        claim("c2", "L-C", "derived_from", {"lot": "L-B", "confirmed": True},
              occurred_at=T0),
        # and a class-2 claim naming a third answer
        claim("o1", "L-C", "derived_from", {"lot": "L-C-OBS"},
              occurred_at=T0 + timedelta(days=9)),
    ])
    assert hop["state"] == lt.STATE_CANDIDATE, (
        "a split top class must not be reported as a DECLARED winner")
    assert hop["n"] == 3, "all three answers were in contention"
    assert "내 답 2종" in hop["reason"], hop["reason"]
    assert "하위 계급 반대 1종" in hop["reason"], (
        f"gaining the word lost the fact: {hop['reason']}")
    assert "L-C-OBS" in hop["reason"]


def test_the_state_split_goes_red_on_a_resolver_that_still_uses_one_word():
    """MUTANT: the pre-split behaviour, run through the same two scenarios.

    Without this, the split above could be passing because the scenarios are
    toothless rather than because the resolver tells them apart.
    """
    def one_word(hop):
        return lt.STATE_CANDIDATE if hop["state"] in (
            lt.STATE_CONTESTED, lt.STATE_CANDIDATE) else hop["state"]

    contested = _derived_from_hop([
        REGISTER,
        claim("c1", "L-C", "derived_from", {"lot": "L-TRUE", "confirmed": True}),
        claim("o1", "L-C", "derived_from", {"lot": "L-OTHER"},
              occurred_at=T0 + timedelta(days=9)),
    ])
    candidate = _derived_from_hop([
        REGISTER,
        claim("o1", "L-C", "derived_from", {"lot": "L-P1"}, occurred_at=T0),
        claim("o2", "L-C", "derived_from", {"lot": "L-P2"},
              occurred_at=T0 + timedelta(hours=1)),
    ])
    assert one_word(contested) == one_word(candidate), (
        "the mutant is supposed to be blind to the distinction")
    assert contested["state"] != candidate["state"], "the real resolver is not"


# ---------------------------------------------------------------------------
# basis: {kind, name} — R-2026-08-13-C
# ---------------------------------------------------------------------------
#
# 🔴 WHY THIS FIELD EXISTS, IN ONE SENTENCE: the enrich graft may never pre-mark
# a row confirmed off a hop that rests on an assumption, and a safety rule cannot
# be regexed out of Korean prose. That read already INVERTED once.


def _convention_pair(observed_slot, convention_slot):
    """A `slot_map` decided by a MEASUREMENT that overrules a CONVENTION.

    The convention atom rests on `slot_preserving` (class 3, an assumption); the
    observation stamps a derivation the source uttered (class 2). The observation
    wins automatically, which is the ruling's whole consequence.
    """
    return [
        claim("reg", "L-B", "register", {}),
        claim("reg-a", "L-A", "register", {}),
        claim("df", "L-B", "derived_from", {"lot": "L-A"}),
        claim("sm-conv", "L-B", "slot_map",
              {"lot": "L-A", "from": "07", "to": convention_slot},
              derivation="slot_preserving"),
        claim("sm-obs", "L-B", "slot_map",
              {"lot": "L-A", "from": "07", "to": observed_slot},
              derivation="pair_field"),
    ]


def test_basis_is_a_field_and_it_describes_the_WINNER_not_the_losers():
    """🔴 THE INVERSION, closed.

    A measurement overrules an assumption. The hop's WINNER is the measurement,
    so `basis.kind` must be `measured` — even though the word `convention:` is
    sitting right there in `reason`, describing the claim that LOST.

    This is precisely the case the client's anchored regex was written to survive
    and that a naive `reason.includes('convention:')` gets backwards. With the
    fact in a field, no reading of the sentence can get it wrong.
    """
    hop = [h for h in run(_convention_pair("21", "07"), "L-B", "07")["hops"]
           if h["predicate"] == "slot_map"][0]

    assert hop["to"]["slot"] == "21", "the measurement must win"
    assert hop["state"] == lt.STATE_CONTESTED
    assert hop["basis"] == {"kind": lt.BASIS_MEASURED, "name": "pair_field"}
    # The trap, still in the prose - and now harmless.
    assert "convention:slot_preserving" in hop["reason"], hop["reason"]
    assert hop["basis"]["kind"] != lt.BASIS_CONVENTION, (
        "the hop where an assumption was OVERRULED was labelled an assumption")


def test_basis_says_convention_when_the_winner_really_rests_on_one():
    """The other direction: no measurement, so the assumption IS the answer.

    This is the hop the graft must never pre-mark confirmed, and `basis.kind` is
    the whole of how it knows.
    """
    atoms = [a for a in _convention_pair("21", "07") if a.id != "sm-obs"]
    hop = [h for h in run(atoms, "L-B", "07")["hops"]
           if h["predicate"] == "slot_map"][0]

    assert hop["state"] == "resolved", "nothing disagreed with it"
    assert hop["basis"] == {"kind": lt.BASIS_CONVENTION, "name": "slot_preserving"}


def test_basis_is_none_when_there_is_no_derivation_and_when_there_is_no_winner():
    """Both causes of None, asserted together because they must render alike.

    Neither is a convention, so a consumer that treats None as "not
    convention-backed" is correct in both — which is what makes None a safe
    default rather than a hole in the safety rule.
    """
    answer = run(chain(["L-C", "L-B"], slots=["3", "5"], wafers=["W-3", "W-5"]),
                 "L-C", "3")
    plain = [h for h in answer["hops"] if h["state"] != "unresolvable"]
    assert plain, "the fixture must produce at least one hop with a winner"
    for hop in plain:
        assert hop["basis"] is None, (
            f"`lot_event/1` carries no `#derivation`: {hop['reason']}")

    unresolvable = [h for h in run([], "L-NOTHING", "3")["hops"]]
    assert unresolvable and unresolvable[0]["basis"] is None


def test_basis_kind_is_the_class_3_convention_branch_and_not_a_second_register():
    """🔴 `kind` is decided by the SAME list that decides the CLASS.

    If `basis.kind` were computed from anything else it would become a second,
    softer place to classify a derivation — and a derivation could then read
    `measured` on the screen while resolving at class 3, or the reverse. The two
    are asserted to be the same judgement, claim by claim.
    """
    cfg = lt.DEFAULT_RESOLVER_CONFIG
    for derivation in ("slot_preserving", "pair_field", "positional_row", None):
        c = claim("x", "L-C", "slot_map", {"lot": "L-P", "from": "1", "to": "2"},
                  derivation=derivation)
        basis = lt.hop_basis(c, cfg)
        if derivation is None:
            assert basis is None
            continue
        assert basis["name"] == derivation, "the name is reported VERBATIM"
        assert ((basis["kind"] == lt.BASIS_CONVENTION)
                == lt.is_convention_backed(c, cfg)
                == (lt.claim_class(c, cfg) == lt.CLASS_INFERENCE)), (
            f"{derivation}: basis.kind disagrees with the resolver's class")


# ---------------------------------------------------------------------------
# §6 — the class boundary, with its mutant
# ---------------------------------------------------------------------------

def _class_blind_rank_key(claim_, config=None):
    """MUTANT: §6's class demoted below the registration priority.

    This is the defect the class boundary exists to prevent — a level that was
    supposed to break a tie WITHIN a class instead promoting a lower class over
    a higher one. It is injected here so the guard below is shown to discriminate.
    """
    cfg = config or lt.DEFAULT_RESOLVER_CONFIG
    ts = lt._occurred_epoch(claim_)
    return (
        lt._registration_priority(claim_.source_who),   # <-- swapped with class
        lt.claim_class(claim_, cfg),
        0 if ts is not None else 1,
        -ts if ts is not None else 0.0,
        str(claim_.id),
    )


CLASS_BOUNDARY_CLAIMS = [
    # class 1, WORST possible tiebreaks: unregistered source, oldest, last id
    claim("z-confirmed", "L-C", "derived_from",
          {"lot": "L-CONFIRMED", "confirmed": True},
          occurred_at=T0 - timedelta(days=365), who="some_file_2019.csv"),
    # class 2, BEST possible tiebreaks: priority-0 source, newest, first id
    claim("a-observed", "L-C", "derived_from", {"lot": "L-OBSERVED"},
          occurred_at=T0 + timedelta(days=365), who="user"),
]


def test_class_2_may_never_outrank_class_1():
    """🔴 §6: "2·3층은 계급을 넘지 못한다."

    The class-2 observation wins EVERY inner level — a priority-0 registered
    source against an unregistered filename, a year newer, and an earlier event
    id — and still loses, because the class is the outermost element of the
    tuple. That is the property, stated as an experiment where every other force
    pushes the wrong way.
    """
    winner = min(CLASS_BOUNDARY_CLAIMS,
                 key=lambda c: lt.claim_rank_key(c, lt.DEFAULT_RESOLVER_CONFIG))
    assert winner.id == "z-confirmed"

    hop = [h for h in run(CLASS_BOUNDARY_CLAIMS + [claim("reg", "L-C", "register", {})],
                          "L-C")["hops"] if h["predicate"] == "derived_from"][0]
    assert hop["to"]["keys"]["lot"] == "L-CONFIRMED"
    # The two name different parents, so the hop honestly reports a contest —
    # but the ANSWER is the class-1 claim's, which is the property under test.
    assert hop["state"] == lt.STATE_CONTESTED
    assert hop["event_id"] == "z-confirmed"


def test_the_class_boundary_guard_goes_red_on_a_class_blind_resolver():
    """The mutant above is run through the SAME scenario and gets it wrong.

    Without this, `test_class_2_may_never_outrank_class_1` could be passing
    because the scenario is toothless rather than because the resolver is right.
    """
    mutant_winner = min(CLASS_BOUNDARY_CLAIMS, key=_class_blind_rank_key)
    assert mutant_winner.id == "a-observed", (
        "the mutant did not even reach the wrong answer - the scenario does not "
        "discriminate and the guard above proves nothing")
    real_winner = min(CLASS_BOUNDARY_CLAIMS, key=lt.claim_rank_key)
    assert real_winner.id != mutant_winner.id


def test_a_pin_outranks_a_confirmed_claim():
    atoms = [
        claim("reg", "L-C", "register", {}),
        claim("c", "L-C", "derived_from", {"lot": "L-CONFIRMED", "confirmed": True},
              occurred_at=T0 + timedelta(days=1), who="user"),
        claim("p", "L-C", "pin", {"lot": "L-PINNED"},
              occurred_at=T0 - timedelta(days=1), who="zz_unregistered"),
    ]
    ranked = sorted([atoms[1], atoms[2]], key=lt.claim_rank_key)
    assert ranked[0].id == "p"
    assert lt.claim_class(atoms[2], lt.DEFAULT_RESOLVER_CONFIG) == lt.CLASS_PIN


def test_inference_loses_to_observation():
    obs = claim("z", "L-C", "derived_from", {"lot": "L-O"},
                occurred_at=T0 - timedelta(days=30), who="zz_file.csv")
    inf = claim("a", "L-C", "derived_from", {"lot": "L-I", "inferred": True},
                occurred_at=T0, who="user")
    assert min([obs, inf], key=lt.claim_rank_key).id == "z"


# ---------------------------------------------------------------------------
# §6 — totality
# ---------------------------------------------------------------------------

def test_order_is_total_when_everything_but_the_event_id_ties():
    """🔴 Two claims equal on class, registration priority AND `occurred_at`.

    This is not a contrived case: one source event translates to nine atoms and
    they all inherit one `event_time`, so ties at level 2 are the NORM. The only
    thing left is the event id, and if it did not decide, the answer would fall
    back to whatever order the rows arrived in — heap order, the exact defect
    measured on `assy_qa` 2026-08-11 where a VACUUM FULL could change a displayed
    value with no write and no audit entry.
    """
    a = claim("00000000-0000-7000-8000-00000000000a", "L-C", "derived_from",
              {"lot": "L-P-A"}, occurred_at=T0, who="lot_event")
    b = claim("00000000-0000-7000-8000-00000000000b", "L-C", "derived_from",
              {"lot": "L-P-B"}, occurred_at=T0, who="lot_event")
    key_a = lt.claim_rank_key(a, lt.DEFAULT_RESOLVER_CONFIG)
    key_b = lt.claim_rank_key(b, lt.DEFAULT_RESOLVER_CONFIG)
    assert key_a[:4] == key_b[:4], "the scenario must tie on every level but the last"
    assert key_a != key_b, "and the last level must break it"

    reg = claim("reg", "L-C", "register", {})
    answers = set()
    rng = random.Random(20260813)
    for _ in range(50):
        atoms = [a, b, reg]
        rng.shuffle(atoms)
        hop = [h for h in run(atoms, "L-C")["hops"]
               if h["predicate"] == "derived_from"][0]
        answers.add((hop["to"]["keys"]["lot"], hop["event_id"], hop["state"], hop["n"]))
    assert answers == {("L-P-A", a.id, "candidate", 2)}, (
        f"the answer moved with input order: {answers}")


def test_totality_guard_goes_red_without_the_event_id_level():
    """MUTANT: drop level 3 and the answer follows input order again."""
    def no_total_order(c):
        return lt.claim_rank_key(c, lt.DEFAULT_RESOLVER_CONFIG)[:4]

    a = claim("aaa", "L-C", "derived_from", {"lot": "L-P-A"}, occurred_at=T0)
    b = claim("bbb", "L-C", "derived_from", {"lot": "L-P-B"}, occurred_at=T0)
    # `min`/`sorted` are stable, so with level 3 gone the winner is whichever
    # was handed in first - i.e. the answer is a property of the SELECT.
    assert min([a, b], key=no_total_order).id == "aaa"
    assert min([b, a], key=no_total_order).id == "bbb"
    # The real key does not have that property.
    assert min([a, b], key=lt.claim_rank_key).id == "aaa"
    assert min([b, a], key=lt.claim_rank_key).id == "aaa"


# ---------------------------------------------------------------------------
# The reused primitive
# ---------------------------------------------------------------------------

def test_rank_key_reuses_cruds_priority_map_rather_than_a_second_one():
    """Level 1 IS `crud.SOURCE_PRIORITY`. A second ranking map is the "서열
    이원화" that `crud.resolve_priority_map` was written to prevent."""
    for name, expected in crud.SOURCE_PRIORITY.items():
        c = claim("x", "L", "derived_from", {"lot": "P"}, who=name)
        assert lt.claim_rank_key(c, lt.DEFAULT_RESOLVER_CONFIG)[1] == expected
    unregistered = claim("x", "L", "derived_from", {"lot": "P"}, who="a_file.csv")
    assert lt.claim_rank_key(unregistered, lt.DEFAULT_RESOLVER_CONFIG)[1] == 99


def test_rank_key_matches_crud_tuple_shape():
    """🔴 The correspondence pin — the two resolvers must not drift into two
    spellings of one rule.

    `crud.compute_priority_value` ranks cell source layers by
    `(declared priority, dated-beats-undated, newest first, name)`.
    `claim_rank_key` ranks ledger claims by the same four levels with §6's class
    prepended. Given the SAME three-level question — one class, layers that
    differ only in priority / timestamp / name — the two must pick the same one.
    """
    scenarios = [
        # (source_who, occurred_at) triples; id is derived from the name so that
        # crud's level-3 (name) and the ledger's level-3 (event id) sort alike.
        [("user", T0), ("pipeline_parser", T0 + timedelta(days=1))],   # priority
        [("a_file.csv", T0), ("b_file.csv", T0 + timedelta(days=1))],  # timestamp
        [("a_file.csv", T0), ("b_file.csv", T0)],                      # name/id
        [("a_file.csv", None), ("b_file.csv", T0)],                    # undated
        [("collision_merge", T0 + timedelta(days=5)), ("user", T0)],   # priority again
    ]
    for layers in scenarios:
        claims = [claim(f"e-{who}", "L-C", "derived_from", {"lot": f"P-{who}"},
                        occurred_at=ts, who=who) for who, ts in layers]
        mine = min(claims, key=lt.claim_rank_key).source_who

        sources = {who: {"value": f"P-{who}", "ingested_at": ts}
                   for who, ts in layers}
        _, theirs = crud.compute_priority_value(sources)

        assert mine == theirs, (
            f"the ledger resolver and crud.compute_priority_value disagree on "
            f"{layers}: {mine!r} vs {theirs!r}")


# ---------------------------------------------------------------------------
# Ledger semantics the walk depends on
# ---------------------------------------------------------------------------

def test_a_superseded_claim_is_retired():
    """§3: 정정·철회 = 새 원자. The correction is older and from a worse source
    and still wins, because the atom it corrects is no longer in play at all."""
    atoms = [
        claim("reg", "L-C", "register", {}),
        claim("wrong", "L-C", "derived_from", {"lot": "L-WRONG"},
              occurred_at=T0 + timedelta(days=10), who="user"),
        claim("fix", "L-C", "derived_from", {"lot": "L-RIGHT"},
              occurred_at=T0, who="zz_file.csv", supersedes="wrong"),
    ]
    hop = [h for h in run(atoms, "L-C")["hops"]
           if h["predicate"] == "derived_from"][0]
    assert hop["to"]["keys"]["lot"] == "L-RIGHT"
    assert hop["state"] == "resolved"
    assert hop["n"] == 1, "a retired claim must not be counted as a candidate"


def test_supersedes_guard_goes_red_without_retirement():
    """MUTANT: skip `live_claims` and the corrected atom wins again."""
    atoms = [
        claim("wrong", "L-C", "derived_from", {"lot": "L-WRONG"},
              occurred_at=T0 + timedelta(days=10), who="user"),
        claim("fix", "L-C", "derived_from", {"lot": "L-RIGHT"},
              occurred_at=T0, who="zz_file.csv", supersedes="wrong"),
    ]
    assert min(atoms, key=lt.claim_rank_key).id == "wrong", (
        "without retirement the corrected atom wins - which is what "
        "live_claims() exists to prevent")
    assert [c.id for c in lt.live_claims(atoms)] == ["fix"]


def test_slot_map_carries_the_position_across_a_hop():
    atoms = chain(["L-C", "L-B", "L-A"], slots=["3", "5", "9"],
                  wafers=["W-3", "W-5", "W-9"])
    answer = run(atoms, "L-C", "3")
    sm = [h for h in answer["hops"] if h["predicate"] == "slot_map"]
    assert [(h["from"]["slot"], h["to"]["slot"]) for h in sm] == [("3", "5"), ("5", "9")]
    hw = [h for h in answer["hops"] if h["predicate"] == "has_wafer"]
    assert [h["to"]["keys"]["wafer"] for h in hw] == ["W-3", "W-5", "W-9"]


def test_slot_map_read_in_the_opposite_direction_still_resolves():
    """§4.2 does not pin which side `from` names, so an atom written
    parent-as-subject is read by its SUBJECT, not by a guess."""
    atoms = [
        claim("reg-c", "L-C", "register", {}),
        claim("reg-p", "L-P", "register", {}),
        claim("df", "L-C", "derived_from", {"lot": "L-P"}),
        # subject is the PARENT: from = parent slot, to = child slot
        claim("sm", "L-P", "slot_map", {"lot": "L-C", "from": "9", "to": "3"}),
        claim("hw", "L-P", "has_wafer", {"slot": "9", "wafer": "W-9"}),
    ]
    answer = run(atoms, "L-C", "3")
    sm = [h for h in answer["hops"] if h["predicate"] == "slot_map"][0]
    assert sm["state"] == "resolved"
    assert sm["to"]["slot"] == "9"


def test_a_missing_slot_map_says_so_and_the_lot_chain_survives():
    atoms = chain(["L-C", "L-B", "L-A"], slots=["3", "5", "9"],
                  wafers=["W-3", "W-5", "W-9"])
    answer = run([a for a in atoms if a.id != "sm-L-C"], "L-C", "3")
    sm = [h for h in answer["hops"] if h["predicate"] == "slot_map"][0]
    assert sm["state"] == "unresolvable"
    assert "no_slot_map" in sm["reason"]
    assert "L-C→L-B" in sm["reason"]
    # position lost, lineage intact
    assert [h["state"] for h in answer["hops"] if h["predicate"] == "derived_from"] \
        == ["resolved", "resolved", "unresolvable"]


def test_slot_is_compared_as_normalised_text():
    """`3`, `"3"` and `"03"` arrive from three sources. A chain that reads as
    broken because `3 != "3"` is a false report, and a false break on this screen
    is worse than no screen."""
    atoms = [
        claim("reg", "L-C", "register", {}),
        claim("hw", "L-C", "has_wafer", {"slot": 3, "wafer": "W-3"}),
    ]
    for asked in ("3", 3, "03", " 3 "):
        answer = run(atoms, "L-C", asked)
        hw = [h for h in answer["hops"] if h["predicate"] == "has_wafer"][0]
        assert hw["state"] == "resolved", f"slot {asked!r} read as missing"


def test_a_cycle_is_reported_as_a_cycle_not_as_a_depth_cap():
    atoms = [
        claim("r1", "L-A", "register", {}), claim("r2", "L-B", "register", {}),
        claim("d1", "L-A", "derived_from", {"lot": "L-B"}),
        claim("d2", "L-B", "derived_from", {"lot": "L-A"}),
    ]
    answer = run(atoms, "L-A", max_depth=lt.DEFAULT_MAX_DEPTH)
    assert "cycle" in answer["terminal_reason"]
    assert "depth_cap" not in answer["terminal_reason"]


# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------

#: 🔴 THE HOP CONTRACT, AS A SET RATHER THAN AS A FLOOR. Asserted with `==`, so a
#: field cannot arrive here unnoticed — which is exactly how `basis` was supposed
#: to arrive and did not, spending a round living in Korean prose instead.
#: Anything added to this set is a route-contract change and an escalation.
PINNED_HOP_KEYS = {"from", "to", "predicate", "state", "rank", "n", "reason",
                   "basis", "occurred_at", "event_id"}


def test_response_shape_is_the_pinned_one():
    answer = run(chain(["L-C", "L-B"], slots=["3", "5"], wafers=["W-3", "W-5"]),
                 "L-C", "3")
    assert set(answer) == {"hops", "terminal_reason", "generated_at"}
    for hop in answer["hops"]:
        # 🔴 EXACT. Not "at least these" — a fourth field must turn this red.
        assert set(hop) == PINNED_HOP_KEYS, (
            f"hop key set moved: missing {PINNED_HOP_KEYS - set(hop)}, "
            f"unexpected {set(hop) - PINNED_HOP_KEYS}. This is the route "
            f"contract; adding to it is an escalation, not an edit.")
        assert hop["state"] in lt.HOP_STATES
        assert (hop["rank"] is None) == (hop["state"] == lt.STATE_UNRESOLVABLE)
        assert (hop["n"] is None) == (hop["state"] == lt.STATE_UNRESOLVABLE)
        # `basis` is ALWAYS present and is either None or the two-key shape.
        # A key that appeared only sometimes would make every consumer guess
        # whether its absence meant "no basis" or "an older server".
        assert hop["basis"] is None or set(hop["basis"]) == {"kind", "name"}
        if hop["basis"] is not None:
            assert hop["basis"]["kind"] in lt.BASIS_KINDS
    datetime.fromisoformat(answer["generated_at"])


def test_the_key_set_pin_goes_red_when_a_field_arrives_unnoticed():
    """The guard above, shown to discriminate.

    A pin written as "at least these keys" — the shape this test file carried
    until `basis` landed — passes happily while a new field ships unreviewed.
    This drives that difference rather than trusting it.
    """
    hop = dict.fromkeys(PINNED_HOP_KEYS)
    assert set(hop) == PINNED_HOP_KEYS                    # the real shape passes
    hop["confidence"] = 0.9                               # a fourth field arrives
    assert not PINNED_HOP_KEYS - set(hop), "a floor-style pin would still pass"
    assert set(hop) != PINNED_HOP_KEYS, "the exact pin must catch it"


def test_times_keep_their_own_offset_and_are_never_normalised_to_utc():
    """🔴 Fab timestamps are local Asia/Seoul. ISO 8601 with `T` and an OFFSET.

    Converting an instant to UTC for display would put a time on the screen that
    no operator's clock ever showed, and invite a nine-hour subtraction by eye.
    The offset an atom arrives with is the offset that leaves.
    """
    atoms = [
        claim("reg", "L-C", "register", {}),
        claim("hw", "L-C", "has_wafer", {"slot": "3", "wafer": "W-3"},
              occurred_at=datetime(2026, 5, 3, 2, 17, tzinfo=KST)),
    ]
    hop = [h for h in run(atoms, "L-C", "3")["hops"]
           if h["predicate"] == "has_wafer"][0]
    assert hop["occurred_at"] == "2026-05-03T02:17:00+09:00", hop["occurred_at"]
    assert "T" in hop["occurred_at"]
    assert not hop["occurred_at"].endswith("Z")
    assert "+00:00" not in hop["occurred_at"]


def test_generated_at_carries_an_offset_rather_than_a_bare_or_utc_stamp():
    answer = run(chain(["L-A"]), "L-A")
    parsed = datetime.fromisoformat(answer["generated_at"])
    assert parsed.tzinfo is not None, "a stamp with no offset is not an instant"
    assert parsed.utcoffset() == datetime.now().astimezone().utcoffset(), (
        "generated_at is not in this machine's local zone")


def test_trace_refuses_to_invent_its_own_lookup():
    """Resolution and lookup are separate on purpose; a default lookup would be
    the seam quietly growing back shut."""
    with pytest.raises(ValueError):
        lt.trace("L-A", "3")


def test_sql_lookup_refuses_a_relation_that_is_not_an_identifier():
    lt.SqlClaimLookup(None, relation="ledger_events")
    lt.SqlClaimLookup(None, relation="ledger_trace_lot_closure")
    for bad in ("ledger_events; DROP TABLE x", "public.ledger_events", "", None):
        with pytest.raises(ValueError):
            lt.SqlClaimLookup(None, relation=bad)


def test_resolver_config_refuses_unknown_keys():
    """Brief §3-1 gate discipline: a config that is not understood is refused at
    the door, not half-applied."""
    import json
    import tempfile
    import paths

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, lt.RESOLVER_CONFIG_FILENAME)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"pin_predicates": ["pin"], "typo_predicates": []}, fh)
        original = paths.config_path
        try:
            paths.config_path = lambda *p: os.path.join(tmp, *p)
            lt._config_cache = None
            with pytest.raises(lt.ResolverConfigError):
                lt.load_resolver_config(force_reload=True)
        finally:
            paths.config_path = original
            lt.set_resolver_config(None)
