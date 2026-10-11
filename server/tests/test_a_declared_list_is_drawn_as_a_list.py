"""A cell the chain skeleton calls ONE VALUE, holding a list, an object or a flag, is drawn as
a blank box. The owner saw it on 09-22: a unified join's `on` and `take` came back empty in the
declaration window, and a rule saved from it carried a table name where a pair list belonged.

The census below is the lead's measurement made reproducible: walk the skeleton and a
declaration together and name every cell where the shape and the value disagree. It runs on
committed declarations only - the 9 the lead counted came from this box's live, gitignored
rules file, which says nothing about production.

Gates (order 980633383):
  (a) 0 over the committed sample and over a fixture that puts a value in EVERY named cell,
      so a cell cannot pass by being absent;
  (b) turning any one named node back into a value is caught at exactly that cell;
  (c) the browser's copy is the one the route builds in-process, checked the same way.
"""
import copy
import io
import json
import os

import pytest

import chain_bindings
from chain import join_into, rule_shape

SAMPLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "config", "sample", "chain_rules.json.sample")


def blank_boxes(node, value, path=()):
    """Every path where the skeleton's shape and the declaration's value disagree."""
    if node is None or value is None:
        return []
    kind, here = node.get("kind"), ".".join(path)
    if kind == "leaf":
        wrong = isinstance(value, (list, dict)) or (
            isinstance(value, bool) and node.get("hint") != "flag")
        return [here] if wrong else []
    if kind in ("record", "oneOf") and not isinstance(value, dict):
        return [here]
    if kind == "record":
        children = [(f["key"], f["node"]) for f in node["fields"]]
    elif kind == "oneOf":
        children = list(node["branches"].items())
    elif kind == "map":
        by_index = node.get("keyed_by") == "index"
        if not isinstance(value, list if by_index else dict):
            return [here]
        items = enumerate(value) if by_index else value.items()
        return [p for key, item in items
                for p in blank_boxes(node["of"], item, path + (str(key),))]
    else:
        return ["%s (unknown kind %r)" % (here, kind)]
    return [p for key, child in children if key in value
            for p in blank_boxes(child, value[key], path + (key,))]


def census(skeleton, declaration):
    """The declaration as the route hands it to the form - an aggregation as its record (총괄 8b487d2e6)."""
    declaration = rule_shape.with_aggregation_records(declaration)
    unified = isinstance(declaration.get("derive"), dict)
    return blank_boxes(skeleton["unified_root" if unified else "root"], declaration)


#: One value in every cell the order named - a cell left out here would pass by absence.
FIXTURE = [
    {"name": "joins", "enabled": True,
     "on": {"table": "left_t", "columns": ["a", "b"]},
     "derive": {"kind": "join", "join": {"right_table": "right_t",
                                         "on": [{"left": "a", "right": "x"}],
                                         "take": ["x", "y"]}},
     "into": {"table": "left_t"},
     "key": {"unique": True},
     "reads": ["other_t"]},
    {"name": "decides", "enabled": True,
     "on": {"table": "src_t"},
     "derive": {"kind": "decide", "decide": {
         "key": ["eq", "at"], "fields": ["wafer"], "list_columns": ["n"],
         "aggregations": {"n": "count", "hi": {"fn": "max", "column": "t"},
                          "names": {"fn": "unique_concat", "column": "w", "separator": "/"}},
         "reference_views": [{"label": "v", "query": "SELECT 1", "limit": 5,
                              "reads": ["src_t"], "candidate_for": {"wafer": "w"}}],
         "auto_confirm": True, "alignment": True}},
     "into": {"table": "derived_t"}},
    {"name": "flat", "trigger_table": "t", "trigger_columns": ["c"], "target_table": "t",
     "mapper": "m", "reads": ["u"], "reference": {"table": "u"}},
]

#: The cells the order named (and the two the lead added), by the root they sit under.
NAMED = [("unified", ("derive", "join", cell)) for cell in ("on", "take")] + [
    ("unified", ("derive", "decide", cell)) for cell in (
        "key", "fields", "list_columns", "aggregations", "reference_views",
        "auto_confirm", "alignment")] + [
    ("unified", ("key", "unique")), ("unified", ("on", "columns")), ("unified", ("reads",)),
    ("flat", ("reference",)), ("flat", ("reads",)), ("flat", ("trigger_columns",))]


def _child(node, key):
    if node["kind"] == "oneOf":
        return node["branches"], key
    return next(f for f in node["fields"] if f["key"] == key), "node"


def _node_at(root, segments):
    node = root
    for key in segments:
        holder, slot = _child(node, key)
        node = holder[slot]
    return node


def _set_at(root, segments, replacement):
    node = _node_at(root, segments[:-1])
    holder, slot = _child(node, segments[-1])
    holder[slot] = replacement


def _root(skeleton, which):
    return skeleton["unified_root" if which == "unified" else "root"]


def test_a_value_in_every_named_cell_draws_no_blank_box():
    skeleton = chain_bindings.skeleton()
    found = {rule["name"]: census(skeleton, rule) for rule in FIXTURE}
    assert not any(found.values()), found


def test_the_committed_sample_draws_no_blank_box():
    rules = [r for r in json.load(io.open(SAMPLE, encoding="utf-8"))["rules"]
             if isinstance(r, dict)]
    assert any(isinstance(r.get("derive"), dict) for r in rules), \
        "canary: the sample carries unified declarations"
    skeleton = chain_bindings.skeleton()
    found = {r.get("name"): census(skeleton, r) for r in rules}
    assert not any(found.values()), found


@pytest.mark.parametrize("which,segments", NAMED, ids=[".".join(s) for _w, s in NAMED])
def test_turning_a_named_cell_back_into_a_value_is_caught_there(which, segments):
    skeleton = copy.deepcopy(chain_bindings.skeleton())
    _set_at(_root(skeleton, which), segments, {"kind": "leaf", "hint": "free"})

    found = [p for rule in FIXTURE for p in census(skeleton, rule)]

    assert ".".join(segments) in found, found


def test_aggregations_spelled_as_a_list_is_caught():
    """The order first put `aggregations` in the list line; the reader refuses anything that
    is not an object, so a list-shaped node would have the form write what the loader drops."""
    skeleton = copy.deepcopy(chain_bindings.skeleton())
    _node_at(skeleton["unified_root"], ("derive", "decide", "aggregations"))["keyed_by"] = "index"

    assert "derive.decide.aggregations" in census(skeleton, FIXTURE[1])


def test_the_shapes_are_the_ones_beside_the_readers():
    """One author: the skeleton carries the shape the reading module declares, unchanged."""
    unified = chain_bindings.skeleton()["unified_root"]
    for branch, shapes in (("join", join_into.JOIN_CELL_SHAPES),
                           ("decide", rule_shape.DECIDE_CELL_SHAPES)):
        for cell, shape in shapes.items():
            assert _node_at(unified, ("derive", branch, cell)) == shape, (branch, cell)
    for cell, shape in rule_shape.KEY_CELL_SHAPES.items():
        assert _node_at(unified, ("key", cell)) == shape, cell


def test_the_route_hands_the_browser_these_shapes():
    """The declaration window gets its skeleton from this call - measured in-process, no token."""
    from ledger import admin

    skeleton = admin.chain_rule_raw_view()["skeleton"]
    found = {rule["name"]: census(skeleton, rule) for rule in FIXTURE}
    assert not any(found.values()), found
