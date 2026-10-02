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

from ledger import trace_router                                        # noqa: E402


def catalogue():
    return trace_router.ledger_declaration_catalog()


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
                 for item in catalogue()["entities"] if "static" in (item["class"] or ())}
    assert published == trace_router._static_types()
    assert published, "no static type is declared; the assertion above is vacuous"


def test_an_entity_without_a_class_publishes_none_rather_than_dynamic(monkeypatch):
    """⛔ THE STOP CONDITION, AS AN ASSERTION. Defaulting the blank to "dynamic" is the
    one thing the order forbade, and it is invisible without this."""
    from ledger import config as _config

    monkeypatch.setattr(_config, "load", lambda *_args, **_kwargs: {
        "entities": {"told@1": {"keys": ["k"], "class": "static"},
                     "untold@1": {"keys": ["k"]}},
        "vocabulary": {}})
    by_type = {item["type"]: item["class"] for item in catalogue()["entities"]}
    assert by_type["told@1"] == ["static"], "one word reads as a one-word list"
    assert by_type["untold@1"] is None, "a blank class was filled in"


def test_the_value_follows_the_declaration(monkeypatch):
    """🔴 GATE ②. Changing the declaration changes the answer, which is what "read, not
    restated" means - a list held in this file would not move."""
    from ledger import config as _config

    monkeypatch.setattr(_config, "load", lambda *_args, **_kwargs: {
        "entities": {"wafer@1": {"keys": ["w"], "class": "dynamic"}},
        "vocabulary": {}})
    assert catalogue()["entities"][0]["class"] == ["dynamic"]

    monkeypatch.setattr(_config, "load", lambda *_args, **_kwargs: {
        "entities": {"wafer@1": {"keys": ["w"], "class": "static"}},
        "vocabulary": {}})
    assert catalogue()["entities"][0]["class"] == ["static"]


def test_nothing_in_this_route_decides_the_class():
    """The route carries the word; it must not define it. A literal here would be a second
    author for a fact the declaration owns."""
    # 🔴 THE CODE, NOT THE PROSE. The comment beside the change explains why a blank is
    # not "dynamic" and therefore CONTAINS the word; scoring raw source would make this
    # assertion answer "what does it say" when it means to ask "what does it do".
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(
        trace_router.ledger_declaration_catalog).lstrip())
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
    #    A list of free words since lead 07889c83d - one word or several.
    assert field["node"]["kind"] == "map" and field["node"]["of"]["hint"] == "free"


# --------------------------------------------- the key list: which values may seed a walk

def test_an_undeclared_type_is_refused_by_name():
    """Same door as `follow` and `collect`: a name nobody declared can never match, so an
    empty list would be indistinguishable from "this key has no values"."""
    with pytest.raises(Exception) as raised:
        trace_router.ledger_key_values(type="not_a_type", key="k", limit=10, db=None)
    detail = raised.value.detail
    assert detail["reason"] == "node_type_not_declared"
    assert detail["declared"], "the refusal must say what IS available"


def test_a_key_the_type_did_not_declare_is_refused_by_name(monkeypatch):
    """🔴 THE SECOND DOOR. A declared type with an undeclared key would otherwise scan for
    a JSON field that cannot exist and report "no values", which reads as a fact."""
    from ledger import config as _config

    monkeypatch.setattr(_config, "load", lambda *_args, **_kwargs: {
        "entities": {"wafer@1": {"keys": ["wafer_id"]}}, "vocabulary": {}})
    with pytest.raises(Exception) as raised:
        trace_router.ledger_key_values(type="wafer", key="nope", limit=10, db=None)
    detail = raised.value.detail
    assert detail["reason"] == "key_not_declared"
    assert detail["declared"] == ["wafer_id"]
    assert detail["type"] == "wafer"


def test_the_declared_keys_come_from_the_declaration(monkeypatch):
    """Read, not restated - adding a key to the declaration must widen this without an
    edit here, which is the only way the catalogue and this route stay one answer."""
    from ledger import config as _config

    monkeypatch.setattr(_config, "load", lambda *_args, **_kwargs: {
        "entities": {"wafer@1": {"keys": ["a", "b"]}}, "vocabulary": {}})
    assert trace_router._declared_keys("wafer") == {"a", "b"}
    monkeypatch.setattr(_config, "load", lambda *_args, **_kwargs: {
        "entities": {"wafer@1": {"keys": ["a"]}}, "vocabulary": {}})
    assert trace_router._declared_keys("wafer") == {"a"}


def test_the_key_argument_is_optional_now():
    """A single-key type must answer the same as before, so `key` cannot be required."""
    import inspect

    signature = inspect.signature(trace_router.ledger_key_values)
    assert signature.parameters["key"].default is not inspect.Parameter.empty


# ---------------------------------------------------------------------------
# S-52 ④  선언이 «속성 이름»을 발행한다 — 화면이 그 이름을 «적지 않게**
#
# 🔴 걷기 표의 노드 열이 곧 그 이름들이고, 「어떤 이름이 있나」의 유일한 권위는 «선언»이다.
# 클라가 자기 목록을 들면 운영자가 하나 «더하는 날»까지만 맞고, 그다음부터 조용히 «짧다».
# ---------------------------------------------------------------------------

def test_the_catalogue_publishes_an_entitys_attribute_names(monkeypatch):
    from ledger import config as _config

    monkeypatch.setattr(_config, "load", lambda *_args, **_kwargs: {
        "entities": {"wafer@1": {"keys": ["wafer"], "attributes": ["product", "grade"]}},
        "vocabulary": {}})
    entity, = catalogue()["entities"]

    assert entity["attributes"] == ["product", "grade"]


def test_a_type_that_declares_none_publishes_no_key_rather_than_an_empty_list(monkeypatch):
    """㉥ 「값을 안 든다」와 「이 배포는 이 축보다 먼저다」를 «구별할 수 있게**.
    빈 목록을 내면 그 둘이 같은 픽셀이 된다 — 오늘 밤 내내 잡은 그 부류."""
    from ledger import config as _config

    monkeypatch.setattr(_config, "load", lambda *_args, **_kwargs: {
        "entities": {"wafer@1": {"keys": ["wafer"]}},
        "vocabulary": {}})
    entity, = catalogue()["entities"]

    assert "attributes" not in entity
    # 그리고 나머지 칸은 «그대로**여야 한다(무회귀).
    assert entity["keys"] == ["wafer"] and entity["class"] is None
