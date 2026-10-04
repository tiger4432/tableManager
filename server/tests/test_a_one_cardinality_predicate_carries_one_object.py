# -*- coding: utf-8 -*-
"""`cardinality: one` 은 「이 주어에 이 술어의 목적어는 «지금» 하나」 - 그 «지금»은 가장 늦은
occurred_at 이고 걷기가 그렇게 읽는다 (총괄 22ebdd153, 판정 256 뒤집음). 이 파일은 엣지가 그
선언을 «싣는» 것만 잰다; 읽기 규칙은 `test_the_walk_draws_what_is_current` · `test_ledger_trace_pg`.

⚰️ The write-time stamp, the batch refusal, the store lookup and `live_claims` retired, and
their tests with them.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_an_edge_carries_the_declared_cardinality():
    from ledger_api import ledger_subgraph

    edge = ledger_subgraph._edge("holds", "a", "b", cardinality="one")

    assert edge["cardinality"] == "one"


def test_an_undeclared_predicate_says_nothing_rather_than_many():
    """⚠️ `None` MEANS 「the declaration did not say」. A synthesised edge and an undeclared
    predicate both land here, and telling a reader `many` about either would be inventing
    an answer the declaration never gave."""
    from ledger_api import ledger_subgraph

    assert ledger_subgraph._edge("holds", "a", "b")["cardinality"] is None


def test_the_router_reads_cardinality_from_the_same_declaration_as_its_siblings():
    """🔴 ONE SOURCE. `_static_types` and `_static_step_predicates` already read the
    declaration for the same walk; a second reader with its own idea of what is declared is
    how two answers about one predicate appear."""
    import inspect

    from ledger import trace_router

    body = inspect.getsource(trace_router._predicate_cardinalities)

    assert "_declaration(world)" in body          # the one reader its siblings ask (092a6f9e5)
    assert '(declared.get("vocabulary") or {})' in body
    # Keyed by the unversioned name, which is the spelling the edges use.
    assert 'str(key).split("@", 1)[0]' in body


def test_a_declaration_that_cannot_be_read_still_draws_the_graph():
    """A walk must answer even when the declaration is unreadable; it simply says nothing
    about cardinality rather than refusing to draw."""
    import inspect

    from ledger import trace_router

    body = inspect.getsource(trace_router._predicate_cardinalities)

    assert "except Exception:" in body
    assert body.rstrip().endswith("return cardinalities")
