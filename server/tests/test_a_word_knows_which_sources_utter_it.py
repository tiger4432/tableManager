# -*- coding: utf-8 -*-
"""S-143. Which sources name this vocabulary word or entity — read from the declaration.

🔴 THE QUESTION A COST PREVIEW ASKS. Editing one source costs one source's re-translation;
editing a PREDICATE re-runs every source that utters it, and nothing answered that. The three
functions that looked close are each on another axis — `followup.sources_for_table` is
TABLE → sources, `config.declared_derivations` is SOURCE → derivations, and
`ledger_trace_router._declared_entities` is a name list. Measured before building
(판정 322), which is why this exists rather than a fourth near-miss being used.

⚠️ AN EMPTY ANSWER IS AN ANSWER. No source utters this word is a FACT; it is not the same as
「there is a number and this seat did not pay for it」, and the caller keeps them apart with
two different absence words.
"""
import io
import json
import os
import sys

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from ledger import config as ledger_config                            # noqa: E402

SAMPLE = os.path.join(server_dir, "config", "sample", "ledger_config.json.sample")

#: One source that utters a predicate and binds two entity types.
CFG = {
    "sources": {
        "__comment": "annotation keys are not sources",
        "b_measures": {"bind": {"mappings": {"m": {
            "predicate": "measures@1",
            "bind": {"subject": {"kind": "entity", "entity_type": "wafer@1",
                                 "keys": {"w": {"kind": "column", "column": "wid"}}},
                     "target": {"kind": "entity", "entity_type": "quantity@1",
                                "keys": {"q": {"kind": "column", "column": "p"}}},
                     "value": {"kind": "column", "column": "v"}}}}}},
        "a_transfers": {"bind": {"mappings": {"t": {
            "predicate": "transfer@1",
            "bind": {"subject": {"kind": "entity", "entity_type": "wafer@1",
                                 "keys": {"w": {"kind": "column", "column": "wid"}}}}}}}},
        "c_silent": {"bind": {"mappings": {}}},
    }
}


def test_a_predicate_names_only_the_sources_that_utter_it():
    assert ledger_config.sources_binding(CFG, "measures@1") == ("b_measures",)
    assert ledger_config.sources_binding(CFG, "transfer@1") == ("a_transfers",)


def test_an_entity_is_found_through_the_bind_leaves_not_just_the_predicate():
    """🔴 THE HALF THAT WOULD HAVE BEEN MISSED. Reading only `predicate` answers for
    vocabulary and says 「no sources」 for every entity — an absence indistinguishable from a
    fact, which is the failure this whole report exists to avoid."""
    assert ledger_config.sources_binding(CFG, "wafer@1") == ("a_transfers", "b_measures")
    assert ledger_config.sources_binding(CFG, "quantity@1") == ("b_measures",)


def test_the_version_does_not_have_to_be_spelled():
    """⚠️ AS `_collectable_types` STRIPS IT. A caller should not have to know whether the
    declaration happens to write `wafer` or `wafer@1`."""
    assert (ledger_config.sources_binding(CFG, "wafer")
            == ledger_config.sources_binding(CFG, "wafer@1"))


def test_a_word_nobody_utters_is_an_empty_tuple_and_that_is_a_fact():
    """🔴 THIS EMPTY IS `truly_none`, NOT 「not counted here」. Two different empties, and the
    caller must not render them the same: one says nothing re-runs, the other says something
    does and this seat declined to count it."""
    assert ledger_config.sources_binding(CFG, "no_such_word") == ()
    assert ledger_config.sources_binding(CFG, "") == ()


def test_an_annotation_key_is_not_a_source():
    assert "__comment" not in ledger_config.sources_binding(CFG, "measures@1")


def test_the_answer_is_sorted_so_a_diff_between_two_runs_means_something():
    """⚠️ AN UNORDERED ANSWER MAKES EVERY RE-READ LOOK LIKE A CHANGE, and a screen comparing
    two previews would show movement that is only dictionary order."""
    assert list(ledger_config.sources_binding(CFG, "wafer@1")) == sorted(
        ledger_config.sources_binding(CFG, "wafer@1"))


def test_it_answers_on_the_shipped_declaration_too():
    """⚠️ THE FIXTURE ABOVE IS MINE; this one is what the product ships. A walker that only
    ever met its own fixture has not met the shape it will be asked about."""
    with io.open(SAMPLE, encoding="utf-8") as handle:
        shipped = json.load(handle)

    utterers = ledger_config.sources_binding(shipped, "measures@1")
    assert utterers, "the shipped declaration utters `measures@1` somewhere"
    for name in utterers:
        assert not name.startswith("__")

    wafer = ledger_config.sources_binding(shipped, "wafer")
    assert len(wafer) > len(utterers), (
        "an entity is bound by more sources than one predicate is uttered by; if this "
        "flips, the entity leaves are no longer being walked")


def test_it_reads_the_declaration_and_walks_no_graph():
    """🔴 SCORED ON THE SOURCE. `chain_graph` walks the runtime graph for a different
    question; a second walker here would be two answers to 「what does this word touch」."""
    import inspect

    body = inspect.getsource(ledger_config.sources_binding)
    doc = inspect.getdoc(ledger_config.sources_binding)
    if doc:
        for line in doc.splitlines():
            body = body.replace(line, "")

    for forbidden in ("chain_graph", "snapshot", "session", "db"):
        assert forbidden not in body, forbidden
