# -*- coding: utf-8 -*-
"""총괄 03bc94b6b (소유자 10-06 「그래프에는 의미 없는 키로만 떠서 불편, 속성이 보여야 함」): an
entity declares `label` - the key or attribute names a node is shown by. One seat builds the name
(`ledger_subgraph._node_label`); the declaration refuses a name the entity does not carry; the
cell is compiled nowhere, so no source's fingerprint moves."""
import copy
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import validation                                                  # noqa: E402
from ledger import setup_bundle                                    # noqa: E402
from ledger_api import ledger_subgraph                             # noqa: E402

SAMPLE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", "sample"))
ORDER = {"proc": ["proc_id"], "pair": ["a", "b"]}
LABELS = {"proc": ["step", "recipe", "proc_id"], "pair": ["note"]}
AT = datetime(2026, 9, 1, 1, tzinfo=timezone.utc)


def _problems(entity):
    problems = validation.Problems()
    setup_bundle._validate_entities({"proc": entity}, problems)
    return [issue.to_mapping() for issue in problems.finish()]


def test_a_name_the_entity_does_not_carry_is_refused_by_name():
    entity = {"keys": ["proc_id"], "attributes": ["step"]}
    assert _problems(dict(entity, label=["step", "proc_id"])) == []       # canary: both kinds pass
    assert _problems(dict(entity, label=[])) == []                        # empty is the keys
    [issue] = _problems(dict(entity, label=["step", "stepp"]))
    assert (issue["code"], issue["path"]) == ("unknown_id", "bundle.entities.proc.label")
    assert "'stepp'" in issue["message"]
    [issue] = _problems(dict(entity, label="step"))
    assert (issue["code"], issue["path"]) == ("invalid_type", "bundle.entities.proc.label")


@pytest.fixture(autouse=True)
def declaration():
    fake = "test:entity-label"
    token = ledger_subgraph._WALK_DECLARATION.set(fake)
    ledger_subgraph._declaration_facts[fake] = (ORDER, {}, {}, {}, LABELS)
    try:
        yield
    finally:
        ledger_subgraph._declaration_facts.pop(fake, None)
        ledger_subgraph._WALK_DECLARATION.reset(token)


def _walked(entity_type, keys, attributes):
    """The node as the walk builds it, then as it stands once its attributes are read."""
    node = ledger_subgraph._entity_node(entity_type, keys)
    before = node["label"]
    seen = {name: [(AT, value, "w1", "src", ledger_subgraph._instant(AT))]
            for name, value in attributes.items()}
    ledger_subgraph._apply_registrations({node["id"]: node}, {node["id"]: seen} if seen else {})
    return before, node["label"]


def test_the_label_shows_an_attribute_and_a_key_in_the_declared_order():
    assert _walked("proc", {"proc_id": "P1"}, {"step": "S1", "recipe": "R1"}) == (
        "P1", "S1 · R1 · P1")


def test_a_name_with_no_value_is_left_out():
    assert _walked("proc", {"proc_id": "P1"}, {"step": "S1", "recipe": " "}) == ("P1", "S1 · P1")
    assert _walked("proc", {"proc_id": "P1"}, {"step": ["S1", "", "S2"]}) == ("P1", "S1, S2 · P1")


def test_no_named_value_is_the_key_label_of_today():
    assert _walked("pair", {"b": "B", "a": "A"}, {"other": "x"}) == ("A / B", "A / B")
    assert _walked("pair", {"b": "B", "a": "A"}, {}) == ("A / B", "A / B")
    assert _walked("lot", {"lot": "L1", "site": 2.0}, {"note": "n"}) == ("L1 / 2.0", "L1 / 2.0")


def _stamps(document, catalog):
    from ledger.setup import load_setup
    from ledger.setup_registry import cursor_translator_version

    root = tempfile.mkdtemp(prefix="label_")
    try:
        with open(os.path.join(root, "ledger_config.json"), "w", encoding="utf-8") as fh:
            json.dump(document, fh)
        setup = load_setup(root, catalog=catalog)
        return {source: cursor_translator_version(setup.snapshot, source)
                for source, plan in setup.snapshot.source_plans.items() if plan.runs}
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a_label_moves_no_source_fingerprint():
    """Walk-only, like `inverse_of`: compiled nowhere, so no cursor stops and nothing re-runs."""
    catalog = setup_bundle.load_physical_catalog(os.path.join(SAMPLE, "table_config.json.sample"))
    with open(os.path.join(SAMPLE, "ledger_config.json.sample"), encoding="utf-8") as fh:
        document = json.load(fh)
    before = _stamps(document, catalog)
    labelled = copy.deepcopy(document)
    labelled["entities"]["die@1"]["label"] = ["mat_id", "x"]
    labelled["entities"]["dtjob@1"]["label"] = ["dt_eqp", "dt_job"]
    reordered = copy.deepcopy(document)
    reordered["entities"]["die@1"]["keys"].reverse()
    assert "die_inspection" in before and _stamps(reordered, catalog) != before   # canary
    assert _stamps(labelled, catalog) == before
