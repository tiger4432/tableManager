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





# ---------------------------------------------------------------------------
# The broken chain — the acceptance criterion
# ---------------------------------------------------------------------------







# ---------------------------------------------------------------------------
# candidate(rank, n)
# ---------------------------------------------------------------------------









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












# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------

#: 🔴 THE HOP CONTRACT, AS A SET RATHER THAN AS A FLOOR. Asserted with `==`, so a
#: field cannot arrive here unnoticed — which is exactly how `basis` was supposed
#: to arrive and did not, spending a round living in Korean prose instead.
#: Anything added to this set is a route-contract change and an escalation.
PINNED_HOP_KEYS = {"from", "to", "predicate", "state", "rank", "n", "reason",
                   "basis", "occurred_at", "event_id"}




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
