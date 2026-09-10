# -*- coding: utf-8 -*-
"""`cardinality: one` 은 「이 주어에 이 술어의 목적어는 «지금» 하나」 (S-133 ②, 판정 256).

🔴 THE WORD HAD NO READER AT ALL. The grammar accepted it, the authoring form offered it,
`setup_bundle` validated it - and `predicate_claim` returned only `{emit, roles}`, so it
never reached the compiler. Step zero put it on `PredicateDescriptor`; this is the first
thing that acts on it.

⛔ ACROSS BATCHES A NEW OBJECT REPLACES THE OLD ONE - the value CHANGED, and arrival order
says which is current. WITHIN one batch there is no such order: two objects for one subject
leave nobody able to say which is now true, so the molecule is refused by name, counted, and
skipped. Refusing is the only answer that does not invent an order.

⚠️ INERT ON EVERY SHIPPED DECLARATION. `many` is the default and the shipped sample says
`many`, so nothing changes until somebody declares `one`.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import runtime_v2                                        # noqa: E402
from ledger.setup_bundle import DEFAULT_CARDINALITY                  # noqa: E402


class _Predicate:
    def __init__(self, cardinality):
        self.cardinality = cardinality


class _Snapshot:
    def __init__(self, vocabulary):
        self.vocabulary = vocabulary


class _Atom:
    def __init__(self, predicate, keys, payload, subject_type="thing@1"):
        self.predicate = predicate
        self.subject_type = subject_type
        self.subject_keys = keys
        self.object_payload = payload


def _snapshot(**cardinalities):
    return _Snapshot({name: _Predicate(value) for name, value in cardinalities.items()})


def test_only_predicates_declared_one_are_watched():
    snapshot = _snapshot(**{"holds@1": "one", "observed@1": "many"})

    assert runtime_v2._one_cardinality_predicates(snapshot) == frozenset({"holds@1"})


def test_a_predicate_that_declares_nothing_is_many():
    """⚠️ THE DEFAULT IS WHAT EVERY DECLARATION ON DISK MEANS, so an absent word must not
    quietly start refusing molecules that have always been written."""
    class _Bare:
        pass

    assert DEFAULT_CARDINALITY == "many"
    assert runtime_v2._one_cardinality_predicates(_Snapshot({"p@1": _Bare()})) == frozenset()


def test_two_objects_for_one_subject_in_one_batch_are_a_conflict():
    snapshot = _snapshot(**{"holds@1": "one"})
    batch = [
        [_Atom("holds@1", {"id": "W1"}, {"value": "A"})],
        [_Atom("holds@1", {"id": "W1"}, {"value": "B"})],
    ]

    conflicts = runtime_v2._conflicting_subjects(snapshot, batch)

    assert len(conflicts) == 1
    assert runtime_v2._atom_subject(batch[0][0]) in conflicts


def test_the_same_object_twice_is_not_a_conflict():
    """⛔ TWO ROWS SAYING THE SAME THING ARE NOT AMBIGUOUS. A source that repeats itself in
    one batch still leaves exactly one answer to 「what is it now」, so refusing it would
    turn a harmless duplicate into lost data."""
    snapshot = _snapshot(**{"holds@1": "one"})
    batch = [
        [_Atom("holds@1", {"id": "W1"}, {"value": "A"})],
        [_Atom("holds@1", {"id": "W1"}, {"value": "A"})],
    ]

    assert runtime_v2._conflicting_subjects(snapshot, batch) == set()


def test_key_order_does_not_make_two_subjects_out_of_one():
    """Two dicts spelling one identity in a different order are one subject - which is why
    the keys are canonicalised rather than compared as dicts."""
    snapshot = _snapshot(**{"holds@1": "one"})
    batch = [
        [_Atom("holds@1", {"lot": "L", "slot": "1"}, {"value": "A"})],
        [_Atom("holds@1", {"slot": "1", "lot": "L"}, {"value": "B"})],
    ]

    assert len(runtime_v2._conflicting_subjects(snapshot, batch)) == 1


def test_different_subjects_are_not_a_conflict_however_many_they_are():
    snapshot = _snapshot(**{"holds@1": "one"})
    batch = [[_Atom("holds@1", {"id": f"W{i}"}, {"value": str(i)}) for i in range(50)]]

    assert runtime_v2._conflicting_subjects(snapshot, batch) == set()


def test_a_many_predicate_may_say_as_much_as_it_likes():
    """③ - `many` is untouched, which is every predicate that ships today."""
    snapshot = _snapshot(**{"observed@1": "many"})
    batch = [
        [_Atom("observed@1", {"id": "W1"}, {"value": "A"})],
        [_Atom("observed@1", {"id": "W1"}, {"value": "B"})],
    ]

    assert runtime_v2._conflicting_subjects(snapshot, batch) == set()


def test_a_declaration_with_no_one_predicate_costs_no_scan():
    """⚠️ THOUSANDS OF ROWS PER TRANSACTION IS THE PRODUCTION SHAPE, so the batch must not
    be walked to discover there was nothing to look for."""
    import inspect

    body = inspect.getsource(runtime_v2._conflicting_subjects)

    assert "if not one_predicates:" in body, body[:600]
    assert body.index("if not one_predicates:") < body.index("for atoms in event_atoms:")


def test_the_screen_refuses_by_name_counts_and_skips():
    """🔴 THE SEAT IS `gate.refuse` INSIDE `building_molecule`, which counts and then
    raises - that is what stops a caller from counting a refusal and writing the molecule
    anyway. A per-molecule screen could not do this: the other object is in another
    molecule by definition."""
    import inspect

    body = inspect.getsource(runtime_v2._screened_atoms)

    assert '"cardinality_one_violated"' in body, body
    assert "gate.refuse(" in body
    assert "_conflicting_subjects(snapshot, event_atoms)" in body
    assert body.index("_conflicting_subjects") < body.index("for result, atoms in zip")
