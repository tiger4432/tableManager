# -*- coding: utf-8 -*-
"""걷기가 «지금 참인 것»을 그린다 (S-141, 응용 D-3 발견 ①).

⚰️ MY OWN S-133 ④ GATE PROVED THE WRONG THING. It called `ledger_trace.live_claims`
DIRECTLY from a test and asserted the replaced atom was dropped - which proved the FILTER
and not the WIRING. `live_claims` had zero product callers, so the walk fetched
`supersedes`, carried it, and drew the superseded edge and its replacement side by side.
착지는 배선이 아니다, and a gate that calls the function under test bypasses exactly the
question 「does anything call it」.

⛔ ONE FILTER. The walk does not build its own - two places deciding 「which claim is
current」 do not error when they disagree; one of them just starts drawing a fact that was
replaced.

⚠️ AND THE REMOVAL IS COUNTED, NOT HIDDEN - the same discipline truncation follows.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger_api import ledger_subgraph                               # noqa: E402


class _Atom:
    def __init__(self, atom_id, supersedes=None):
        self.id = atom_id
        self.supersedes = supersedes


def test_the_replaced_atom_is_dropped_and_the_replacement_is_named():
    live, replaced_by = ledger_subgraph._split_superseded(
        [_Atom("A"), _Atom("B", supersedes="A")])

    assert [a.id for a in live] == ["B"]
    assert replaced_by == {"A": "B"}


def test_a_set_with_nothing_superseded_is_returned_untouched():
    """⚠️ 기존 무변 — supersedes 가 없는 원자는 수 0 이고 아무것도 안 빠진다."""
    atoms = [_Atom("A"), _Atom("B")]

    live, replaced_by = ledger_subgraph._split_superseded(atoms)

    assert live == atoms
    assert replaced_by == {}


def test_the_walk_calls_the_shared_filter_rather_than_its_own():
    """🔴 THE WIRING, WHICH IS WHAT S-133 ④ FAILED TO CHECK."""
    import inspect

    helper = inspect.getsource(ledger_subgraph._split_superseded)
    # 🪦 [S-211 packaging] the walk reaches it as `from ledger import trace`.
    assert "trace.live_claims(" in helper

    body = inspect.getsource(ledger_subgraph.subgraph)
    assert "_split_superseded(batch)" in body, "the fetch path must pass through it"
    assert "superseded_dropped += " in body


def test_the_response_always_says_how_many_it_left_out():
    """⚠️ ALWAYS PRESENT, INCLUDING ZERO. 「이 걷기는 대체된 것을 만나지 않았다」 also is a
    fact, and a key that appears only sometimes trains a reader to ignore it."""
    import inspect

    body = inspect.getsource(ledger_subgraph.subgraph)

    assert '"superseded_dropped": superseded_dropped,' in body


def test_including_them_marks_the_edge_rather_than_drawing_it_plain():
    """「보인다」와 「현재다」는 다른 사실이라, 일부러 그린 것에는 표지가 붙는다."""
    import inspect

    body = inspect.getsource(ledger_subgraph.subgraph)

    assert 'edge["superseded_by"] = replaced' in body
    assert "if not include_superseded:" in body


def test_the_route_offers_it_and_defaults_to_current_only():
    import inspect

    from ledger import trace_router

    params = inspect.signature(trace_router.evidence_subgraph).parameters
    assert "include_superseded" in params

    body = inspect.getsource(trace_router)
    assert "include_superseded=include_superseded" in body, "착지는 배선이 아니다"
