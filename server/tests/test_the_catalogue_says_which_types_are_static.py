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
