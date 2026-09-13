# -*- coding: utf-8 -*-
"""S-150. Three constants left every edge, because nothing ever read them.

🔴 THE `key_types` CLASS (판정 165, applied by 판정 340). `_edge()` put `witnesses: 1`,
`rank: None` and `sources: []` on every edge of every walk and no layer consumed any of
them — a slot with no reader is not a contract, it is a copy. Filling them instead is the
work of the round that gains a caller, and inventing that caller here would be the same
mistake in the other direction.

⚠️ `basis` AND `qualifiers` STAY, and that is the same measurement rather than a different
opinion: both are FILLED from the atom further down, so they are initialised here rather
than constant.

⚠️ AND THE NAME IS NOT THE THING. `ledger_explorer` counts a real `witnesses` on its own
rows (`row["witnesses"] += 1`), and a node's `rank` is the propagation layer. Neither is
this key on this object — which is why the measurement was per-object rather than by word.
"""
import os
import sys
import uuid
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import explorer                                             # noqa: E402
from ledger_api import ledger_subgraph                             # noqa: E402

NOW = datetime(2026, 9, 13, 3, 0, tzinfo=timezone.utc)
SEED = explorer.entity_id("wafer", {"wid": "W0"})

RETIRED = ("witnesses", "rank", "sources")


def _atom(number, predicate, kind=None, payload=None):
    return ledger_subgraph.EvidenceAtom(
        id=str(uuid.UUID(int=number)), subject_type="wafer", subject_keys={"wid": "W0"},
        predicate=predicate, object_kind=kind, object_payload=payload, occurred_at=NOW,
        source_who="w", source_translator_ver="v1", source_raw_ref="row:%d" % number,
        supersedes=None, source_event_id=str(uuid.UUID(int=900 + number)),
        source_event_state="source_molecule")


def _walk():
    return ledger_subgraph.subgraph(
        SEED, ledger_subgraph.InMemoryEvidenceLookup([
            _atom(10, "inspected", kind="entity_ref",
                  payload={"type": "die", "keys": {"d": "D0"}})]), hops=2)


@pytest.mark.parametrize("key", RETIRED)
def test_no_edge_carries_the_retired_constant(key):
    body = _walk()

    assert body["edges"], "the fixture must actually draw an edge"
    for edge in body["edges"]:
        assert key not in edge, edge


def test_the_builder_does_not_write_them_either():
    """⛔ SCORED ON THE BUILT EDGE, not on the source — a constant re-added anywhere else
    would still reach the wire."""
    edge = ledger_subgraph._edge("inspected", "a", "b")

    for key in RETIRED:
        assert key not in edge


def test_what_gets_FILLED_stays_INITIALISED():
    """🔴 THE OTHER HALF OF THE SAME MEASUREMENT — and scored on the BUILDER, which is the
    only place it can be seen. An edge drawn from an atom has `basis` assigned afterwards,
    so a walk-level assertion passes even if the initialisation is gone (measured: cutting
    it reds nothing there). What breaks is the edge nothing fills — a synthesised one —
    which would then LACK the key while its neighbour has it: one cell, two shapes,
    depending on the data.
    """
    edge = ledger_subgraph._edge("inspected", "a", "b")

    assert "basis" in edge and edge["basis"] is None
    assert "qualifiers" in edge


def test_an_edge_that_is_filled_still_carries_its_value():
    body = _walk()
    drawn = [edge for edge in body["edges"] if edge.get("basis")]

    assert drawn, "an edge drawn from an atom carries its `basis`"
    assert all("qualifiers" in edge for edge in body["edges"])


def test_a_name_that_survives_elsewhere_is_a_different_object():
    """⚠️ THE MEASUREMENT WAS PER-OBJECT, NOT PER-WORD. `ledger_explorer` keeps a real
    `witnesses` counter on its own rows; retiring the edge's constant must not have touched
    it, and a word-level sweep would have."""
    import inspect

    source = inspect.getsource(explorer)

    assert 'row["witnesses"] += 1' in source, (
        "the live counter elsewhere was removed along with the constant")
