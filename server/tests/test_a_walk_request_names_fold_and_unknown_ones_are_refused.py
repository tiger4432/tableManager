# -*- coding: utf-8 -*-
"""총괄 17b6337e4 — every name a walk request brings goes through ONE seat
(`trace_router._declared_or_refused`): folded by `bare_name`, because a saved board or a bookmark
still says `x@1`, and refused by name when the picked worlds do not declare it - never answered
with an empty walk.

  field        old spelling                      unknown name
  collect      wafer@1 -> wafer                  422 node_type_not_declared
  follow       processed_with@1:wafer -> bare    422 predicate_not_declared
  expand       <id>|processed_with@1|outgoing    422 predicate_not_declared
  seed_type    wafer@1 -> wafer                  422 seed_type_not_declared
  group_by     inspected@1 -> inspected          422 value_name_not_declared
  measure      sum:inspected@1 kept as asked     422 value_name_not_declared
  type (key-values)                              422 node_type_not_declared
"""
import os
import shutil
import sys

import pytest
from fastapi import HTTPException

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import paths                                                             # noqa: E402
from ledger import explorer, trace_router                                # noqa: E402
from ledger_api import ledger_subgraph                                   # noqa: E402

SAMPLE = os.path.join(SERVER_DIR, "config", "sample")
SEED = explorer.entity_id("wafer", {"wafer": "W1"})


@pytest.fixture(name="asked")
def fixture_asked(tmp_path, monkeypatch):
    """The shipped sample (old spelling) as the operating world's file, and what the route hands
    the walk, captured instead of walked."""
    config = tmp_path / "config"
    (config / "ontology").mkdir(parents=True)
    shutil.copy(os.path.join(SAMPLE, "table_config.json.sample"), config / "table_config.json")
    shutil.copy(os.path.join(SAMPLE, "ledger_config.json.sample"),
                config / "ontology" / "ledger_config.json")
    monkeypatch.setattr(paths, "CONFIG_DIR", str(config))
    seen = {}

    def walk(_connection, **kwargs):
        seen.update(kwargs)
        return {}
    monkeypatch.setattr(trace_router, "_evidence_graph", walk)

    class _Db:
        def connection(self):
            return None

    def ask(**arguments):
        seen.clear()
        trace_router.evidence_subgraph(**{
            "node_id": None if "seed_type" in arguments else SEED, "world": None, "hops": 2,
            "direction": "both", "node_limit": 100, "edge_limit": 200, "positive": None,
            "negative": None, "follow": None, "collect": None, "db": _Db(), **arguments})
        return seen
    return ask


def test_an_old_spelling_reaches_the_walk_bare(asked):
    assert asked(collect=["wafer@1"])["collect"] == ["wafer"]
    walked = asked(follow=["processed_with@1:wafer"])
    assert (walked["follow"], walked["follow_keys"]) == (["processed_with"], {"processed_with": ("wafer",)})
    assert asked(follow=["processed_with@1"])["follow"] == asked(follow=["processed_with"])["follow"]
    assert asked(expand=["%s|processed_with@1|outgoing" % SEED])["expand"] == [
        "%s|processed_with|outgoing" % SEED]
    assert asked(seed_type="wafer@1")["seed_type"] == "wafer"
    assert asked(group_by="inspected@1")["group_by"] == "inspected"


def test_a_measure_is_answered_under_the_string_asked():
    """A saved board looks its number up by its own string, so the key stays as asked and the
    name it reads is bare: sum:x@1 == sum:x."""
    nodes = [{"id": "n1", "type": "die", "predicates": [{"predicate": "inspected", "count": 2}]},
             {"id": "n2", "type": "die", "predicates": [{"predicate": "inspected", "count": 3}]}]
    (group,) = ledger_subgraph.group_nodes(nodes, "type", ["sum:inspected@1", "sum:inspected"])
    assert group["value"] == {"sum:inspected@1": 5.0, "sum:inspected": 5.0}


def test_a_measure_named_in_the_old_spelling_is_not_refused(asked):
    assert asked(measure=["sum:inspected@1"])["measure"] == ["sum:inspected@1"]


@pytest.mark.parametrize("arguments,reason,argument", [
    ({"collect": ["nosuch"]}, "node_type_not_declared", "collect"),
    ({"follow": ["nosuch"]}, "predicate_not_declared", "follow"),
    ({"expand": ["%s|nosuch|outgoing" % SEED]}, "predicate_not_declared", "expand"),
    ({"seed_type": "nosuch"}, "seed_type_not_declared", "seed_type"),
    ({"group_by": "nosuch"}, "value_name_not_declared", "group_by"),
    ({"measure": ["sum:nosuch"]}, "value_name_not_declared", "measure"),
], ids=["collect", "follow", "expand", "seed_type", "group_by", "measure"])
def test_an_undeclared_name_is_refused_by_name_in_every_field(asked, arguments, reason, argument):
    with pytest.raises(HTTPException) as refused:
        asked(**arguments)
    detail = refused.value.detail
    assert refused.value.status_code == 422
    assert (detail["reason"], detail["argument"], detail["unknown"]) == (reason, argument, ["nosuch"])
    assert detail["declared"], "the refusal says what IS declared"


def test_group_by_takes_a_declared_key_name(asked):
    """총괄 a588e5d80 — `wafer` is a key of `wafer@1`/`dtwafer@1`, not an attribute."""
    assert asked(group_by="wafer")["group_by"] == "wafer"
    nodes = [ledger_subgraph._entity_node("wafer", {"wafer": "W1"}),
             ledger_subgraph._entity_node("wafer", {"wafer": "W2"}),
             ledger_subgraph._entity_node("dtwafer", {"wafer": "W1"}),
             ledger_subgraph._entity_node("die", {"mat_id": "M1", "x": 1, "y": 2})]
    groups = ledger_subgraph.group_nodes(nodes, "wafer", ["count"])
    assert [(group["key"], group["n"]) for group in groups] == [("W1", 2), ("W2", 1)]


def test_a_key_another_source_also_answers_on_one_node_is_refused():
    """One rule (판정 336): one node, one source. A key and an attribute cannot share a name
    (the declaration refuses it); a key and a predicate on one node are refused here."""
    node = {"id": "n1", "type": "wafer", "keys": {"wafer": "W1"},
            "predicates": [{"predicate": "wafer", "count": 2}]}
    with pytest.raises(ledger_subgraph.AggregateRefused) as refused:
        ledger_subgraph.group_nodes([node], "wafer", ["count"])
    assert refused.value.code == "ambiguous_value_name"
    assert "keys and predicates" in refused.value.detail


def test_the_key_values_type_is_refused_by_the_same_seat(asked):
    with pytest.raises(HTTPException) as refused:
        trace_router.ledger_key_values(type="nosuch", key=None, limit=10, world=None, db=None)
    detail = refused.value.detail
    assert (detail["reason"], detail["argument"], detail["unknown"]) == (
        "node_type_not_declared", "type", ["nosuch"])
