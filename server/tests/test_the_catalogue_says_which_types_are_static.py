# -*- coding: utf-8 -*-
"""The route list offered walks the walk refuses.

A step from a static type to a dynamic one is refused (`_static_step_predicates`), and a
client deriving paths from the declaration's TYPE GRAPH alone cannot know that - so
`wafer → quantity → defect_kind → defect` appeared in the list and came back with the
seed and nothing else, while the ordinary route returned a full graph.

The server already knew: `_static_types()` reads `class: "static"` from the declaration.
The catalogue simply did not publish it, so the only way for a client to know was to
hardcode the three names - which would be the next defect rather than a fix.

⚠️ AN ENTITY WITH NO DECLARED CLASS PUBLISHES `None`. "I was not told" and "I was told
dynamic" are different facts, and filling the first with the second would let a reader
draw a path the walk may still refuse while believing it checked.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import ledger_trace_router                                        # noqa: E402


def catalogue():
    return ledger_trace_router.ledger_declaration_catalog()


def test_every_entity_carries_the_key_even_when_it_is_empty():
    """🔴 THE KEY IS ALWAYS THERE. An absent key would make "no class declared"
    indistinguishable from "this server does not publish classes" - the same shape the
    field exists to remove one layer up."""
    entities = catalogue()["entities"]
    assert entities, "the declaration produced no entities; this proves nothing"
    assert all("class" in item for item in entities)


def test_the_static_types_match_what_the_walk_uses():
    """🔴 GATE ②, THE REAL ONE. Not "three" - the same three the walk itself reads. A
    count would pass while the two lists named different types."""
    published = {item["type"].split("@", 1)[0]
                 for item in catalogue()["entities"] if item["class"] == "static"}
    assert published == ledger_trace_router._static_types()
    assert published, "no static type is declared; the assertion above is vacuous"


def test_an_entity_without_a_class_publishes_none_rather_than_dynamic(monkeypatch):
    """⛔ THE STOP CONDITION, AS AN ASSERTION. Defaulting the blank to "dynamic" is the
    one thing the order forbade, and it is invisible without this."""
    from ledger import config as _config

    monkeypatch.setattr(_config, "load", lambda: {
        "entities": {"told@1": {"keys": ["k"], "class": "static"},
                     "untold@1": {"keys": ["k"]}},
        "vocabulary": {}})
    by_type = {item["type"]: item["class"] for item in catalogue()["entities"]}
    assert by_type["told@1"] == "static"
    assert by_type["untold@1"] is None, "a blank class was filled in"


def test_the_value_follows_the_declaration(monkeypatch):
    """🔴 GATE ②. Changing the declaration changes the answer, which is what "read, not
    restated" means - a list held in this file would not move."""
    from ledger import config as _config

    monkeypatch.setattr(_config, "load", lambda: {
        "entities": {"wafer@1": {"keys": ["w"], "class": "dynamic"}},
        "vocabulary": {}})
    assert catalogue()["entities"][0]["class"] == "dynamic"

    monkeypatch.setattr(_config, "load", lambda: {
        "entities": {"wafer@1": {"keys": ["w"], "class": "static"}},
        "vocabulary": {}})
    assert catalogue()["entities"][0]["class"] == "static"


def test_nothing_in_this_route_decides_the_class():
    """The route carries the word; it must not define it. A literal here would be a second
    author for a fact the declaration owns."""
    # 🔴 THE CODE, NOT THE PROSE. The comment beside the change explains why a blank is
    # not "dynamic" and therefore CONTAINS the word; scoring raw source would make this
    # assertion answer "what does it say" when it means to ask "what does it do".
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(
        ledger_trace_router.ledger_declaration_catalog).lstrip())
    function = tree.body[0]
    if (function.body and isinstance(function.body[0], ast.Expr)
            and isinstance(function.body[0].value, ast.Constant)):
        function.body = function.body[1:]
    code = ast.unparse(function)
    for decided in ("'dynamic'", '"dynamic"'):
        assert decided not in code, "the route names a class value it does not read"


# ------------------------------------------- the authoring form says which value matters

def test_the_class_field_label_names_the_value_the_code_reads():
    """🔴 THE FORM ASKED FOR A VALUE WITHOUT SAYING WHICH VALUES EXIST. `class` is a free
    text box labelled 「노드 분류」, and the only value any code looks at is the one
    `_static_types()` compares against - so an operator had to read the server to know
    what to type.

    ⛔ NOT CLOSED INTO A LIST. The skeleton's leaf grammar offers `free` (shows nothing)
    or `choice` (shows them and closes the list), and closing the declaration's own
    vocabulary is the failure this repository spent the night removing. The label is the
    one affordance the existing grammar has, so the label carries it.
    """
    import json
    import os

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    skeleton = json.load(open(os.path.join(here, "ledger", "ledger_skeleton.json"),
                              encoding="utf-8"))

    def find(node):
        if isinstance(node, dict):
            if node.get("key") == "class":
                return node
            for value in node.values():
                got = find(value)
                if got:
                    return got
        elif isinstance(node, list):
            for value in node:
                got = find(value)
                if got:
                    return got
        return None

    field = find(skeleton)
    assert field, "the class field left the skeleton"
    assert "static" in field["label"], \
        "the label does not name the one value the walk actually reads"
    # ⛔ Still open, deliberately: showing the value must not become closing the list.
    assert field["node"]["hint"] == "free"


# --------------------------------------------- the key list: which values may seed a walk

def test_an_undeclared_type_is_refused_by_name():
    """Same door as `follow` and `collect`: a name nobody declared can never match, so an
    empty list would be indistinguishable from "this key has no values"."""
    with pytest.raises(Exception) as raised:
        ledger_trace_router.ledger_key_values(type="not_a_type", key="k", limit=10, db=None)
    detail = raised.value.detail
    assert detail["reason"] == "node_type_not_declared"
    assert detail["declared"], "the refusal must say what IS available"


def test_a_key_the_type_did_not_declare_is_refused_by_name(monkeypatch):
    """🔴 THE SECOND DOOR. A declared type with an undeclared key would otherwise scan for
    a JSON field that cannot exist and report "no values", which reads as a fact."""
    from ledger import config as _config

    monkeypatch.setattr(_config, "load", lambda: {
        "entities": {"wafer@1": {"keys": ["wafer_id"]}}, "vocabulary": {}})
    with pytest.raises(Exception) as raised:
        ledger_trace_router.ledger_key_values(type="wafer", key="nope", limit=10, db=None)
    detail = raised.value.detail
    assert detail["reason"] == "key_not_declared"
    assert detail["declared"] == ["wafer_id"]
    assert detail["type"] == "wafer"


def test_the_declared_keys_come_from_the_declaration(monkeypatch):
    """Read, not restated - adding a key to the declaration must widen this without an
    edit here, which is the only way the catalogue and this route stay one answer."""
    from ledger import config as _config

    monkeypatch.setattr(_config, "load", lambda: {
        "entities": {"wafer@1": {"keys": ["a", "b"]}}, "vocabulary": {}})
    assert ledger_trace_router._declared_keys("wafer") == {"a", "b"}
    monkeypatch.setattr(_config, "load", lambda: {
        "entities": {"wafer@1": {"keys": ["a"]}}, "vocabulary": {}})
    assert ledger_trace_router._declared_keys("wafer") == {"a"}


def test_the_scan_is_bounded_and_the_grouping_is_not_the_bound():
    """🔴 THE ONE PROPERTY THAT KEEPS THIS OFF THE GRADE-5 LIST. The window is taken with
    a LIMIT and grouped afterwards; a GROUP BY over the whole subject_type would visit
    every row that type has."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(ledger_trace_router.ledger_key_values).lstrip())
    function = tree.body[0]
    if (function.body and isinstance(function.body[0], ast.Expr)
            and isinstance(function.body[0].value, ast.Constant)):
        function.body = function.body[1:]
    code = ast.unparse(function)
    assert "LIMIT %(scan)s" in code, "the scan window lost its bound"
    assert code.index("LIMIT %(scan)s") < code.index("GROUP BY"), \
        "the grouping happens before the window is cut - that is the full scan"


def test_the_two_truncations_are_separate_facts():
    """⛔ NOT ONE FLAG. "I stopped reading" and "there are more values" are different, and
    folding them makes "this key has three values" and "I saw three" one answer."""
    import inspect

    body = inspect.getsource(ledger_trace_router.ledger_key_values)
    assert '"scan_truncated"' in body and '"values_truncated"' in body
    # limit + 1 / scan + 1 is how each one can be KNOWN rather than guessed.
    assert '"limit": limit + 1' in body
    assert "KEY_VALUE_SCAN_ROWS + 1" in body


def test_the_order_is_stated_in_the_answer():
    """If nobody writes the order down, the query picks it and it changes with the plan."""
    import inspect

    body = inspect.getsource(ledger_trace_router.ledger_key_values)
    assert "ORDER BY n DESC, " in body
    assert '"order": "count_desc_then_value_asc"' in body


class _Recorder:
    """The one call this route makes, captured: `exec_driver_sql(sql, params)`."""

    def __init__(self, rows):
        self.rows = rows
        self.sql = None
        self.params = None

    def exec_driver_sql(self, sql, params):
        self.sql, self.params = sql, params
        return self

    def fetchall(self):
        return self.rows


def _run(monkeypatch, *, keys, rows, entity="die", key=None, limit=50):
    """Drive the real handler against a recorded connection."""
    from ledger import config as _config

    monkeypatch.setattr(_config, "load", lambda: {
        "entities": {entity + "@1": {"keys": list(keys)}}, "vocabulary": {}})
    monkeypatch.setattr(ledger_trace_router.ledger_trace, "relation_exists",
                        lambda *a, **k: True)
    recorder = _Recorder(rows)
    db = type("Db", (), {"connection": lambda self: recorder})()
    answer = ledger_trace_router.ledger_key_values(
        type=entity, key=key, limit=limit, db=db)
    answer["_sql"], answer["_params"] = recorder.sql, recorder.params
    return answer


def test_a_composite_type_is_grouped_by_every_declared_key(monkeypatch):
    """🔴 THE WHOLE ROUND. Asked per key, a two-key type answers with one list per axis,
    and a screen pairing them offers the CROSS PRODUCT - 144 pairs against 128 dies that
    exist. Every one of the 16 extra builds a seed the walk answers emptily, and an empty
    answer reads as "nothing there" rather than "you asked for a die never made"."""
    import inspect

    from ledger import config as _config

    monkeypatch.setattr(_config, "load", lambda: {
        "entities": {"die@1": {"keys": ["x", "y"]}}, "vocabulary": {}})
    assert ledger_trace_router._declared_keys("die") == {"x", "y"}

    # 🔴 RUN IT, DO NOT READ IT. A source match passed while the grouping was truncated to
    # `sorted(declared_keys)[:1]` - the mutated line still CONTAINED the asserted text.
    # Measured 2026-09-06, and it is the same vacuous shape as a one-typed collect fixture.
    # 🔴 THE VALUES ARE NUMBERS HERE ON PURPOSE. The ledger stores 0.0, the text
    # extractor returned "0.0", and the canonical seed id writes those two differently -
    # so every composite seed came back empty. The route must hand back what the ledger
    # holds, not a rendering of it.
    answer = _run(monkeypatch, keys=["x", "y"],
                  rows=[(0.0, 5.0, 5), (3.0, 4.0, 1)])
    assert answer["keys"] == ["x", "y"], "the subject was grouped by one axis"
    assert answer["subjects"][0]["keys"] == {"x": 0.0, "y": 5.0}, \
        "a subject must carry every key, or the caller has to pair them again"
    assert answer["covers_declared_keys"] is True
    assert "->>" not in answer["_sql"], \
        "the text extractor is back; it stringifies the ledger's numbers"
    assert "subject_keys -> " in answer["_sql"]


def test_one_axis_of_a_composite_key_says_it_is_not_a_seed(monkeypatch):
    """⚠️ SAID, NOT INFERRED. Leaving the caller to compare `keys` against the declaration
    is exactly the inference that produced the cross product."""
    asked = _run(monkeypatch, keys=["x", "y"], rows=[(0.0, 5)], key="x")
    assert asked["keys"] == ["x"]
    # ⚠️ THE NAME IS THE POINT. `seedable` claimed the walk would answer, which this
    # route never checked and which was false for every composite subject while the
    # values came back as text. What a set comparison can know is coverage.
    assert asked["covers_declared_keys"] is False
    assert "seedable" not in asked, "an unmeasured claim came back"


def test_the_key_argument_is_optional_now():
    """A single-key type must answer the same as before, so `key` cannot be required."""
    import inspect

    signature = inspect.signature(ledger_trace_router.ledger_key_values)
    assert signature.parameters["key"].default is not inspect.Parameter.empty
