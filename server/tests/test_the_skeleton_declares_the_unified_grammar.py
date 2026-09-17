# -*- coding: utf-8 -*-
"""S-241 · 판정 407. 스켈레톤이 «통합 문법»도 낸다 — 폼이 새 모양을 그릴 수 있게.

🔴 `chain_bindings.skeleton()` 은 `routing_keys()`(옛 «평면» 키)에서만 생성됐다. 그래서 이
제품이 «더한» 문법을 로더는 읽는데 화면은 «그릴 수 없었다» — 문법이 한쪽에만 있는 상태.

🔴 [판정 407] AND THE VOCABULARY COULD NOT SAY 「PICK ONE」. The client measured it: kind =
record|map|leaf, six hints, `oneOf/anyOf/variants` = 0 - and `hint: choice` picks a VALUE,
not a SHAPE. Drawing 「one of three derive kinds」 would have meant the form hand-drawing
what the grammar already knows, which is how a screen comes to disagree with a loader.

⚠️ 낱말은 «생성»이다. 가지의 칸은 `rule_shape`·`join_into` 의 상수에서 나온다 — 폼이 칸
이름을 «적는» 순간 그것이 두 번째 저자가 되고, 문법이 칸 하나를 얻는 날 조용히 갈린다.
"""
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import chain_bindings                                              # noqa: E402
from chain import join_into, rule_shape                            # noqa: E402


def _unified():
    return chain_bindings.skeleton()["unified_root"]


def _field(root, key):
    return next(f for f in root["fields"] if f["key"] == key)


# ---------------------------------------------------------------------------
# 🔴 ⓐ — the words are generated, not written
# ---------------------------------------------------------------------------

def test_the_derive_branches_are_the_declared_kinds():
    """🔴 GATE ①. The form offers exactly the kinds the grammar has - no more (a branch
    nothing runs), no fewer (a kind nobody can write)."""
    derive = _field(_unified(), "derive")["node"]

    assert derive["kind"] == "oneOf"
    assert sorted(derive["branches"]) == sorted(rule_shape.DECLARED_KINDS)


def test_the_join_branch_carries_the_join_cells_the_product_reads():
    """⚠️ FROM `join_into.JOIN_CELLS`, which is the list the runner itself consults."""
    join = _field(_unified(), "derive")["node"]["branches"]["join"]

    assert [f["key"] for f in join["fields"]] == list(join_into.JOIN_CELLS)


def test_the_decide_branch_carries_the_decide_cells():
    decide = _field(_unified(), "derive")["node"]["branches"]["decide"]

    assert [f["key"] for f in decide["fields"]] == list(rule_shape.DECIDE_CELLS)


def test_into_is_a_pick_one_of_writing_or_reading():
    """🔴 [S-251] THE TWO ARE EXCLUSIVE AND THE FORM HAS TO SAY SO. `into.table` writes;
    `into.read` answers at read time. A form that let both be filled would offer a
    declaration the loader sends down two different roads."""
    into = _field(_unified(), "into")["node"]

    assert into["kind"] == "oneOf"
    assert sorted(into["branches"]) == sorted(rule_shape.INTO_KINDS)
    # [S-241-b, 판정 411] the branch node lives UNDER the key: `into: {"table": "dt_x"}`
    # is a name, `into: {"read": true}` is a flag - neither is a record wrapping itself.
    assert into["branches"]["table"]["kind"] == "leaf"
    assert into["branches"]["read"] == {"kind": "leaf", "hint": "flag"}


def test_the_key_and_limit_cells_come_from_their_own_lists():
    root = _unified()

    assert [f["key"] for f in _field(root, "key")["node"]["fields"]] == \
        list(rule_shape.KEY_CELLS)
    assert [f["key"] for f in _field(root, "limits")["node"]["fields"]] == \
        list(rule_shape._LIMIT_KEYS)


# ---------------------------------------------------------------------------
# 🔴 ⓐ-bis — [S-241-b, 판정 411] a branch node is what lives UNDER the branch key
# ---------------------------------------------------------------------------

#: What a real declaration puts at each branch, taken from the shapes this repository
#: actually commits. The KEY is already the cell - so `into: {"table": "dt_x"}` means the
#: `table` branch is the table NAME, not a record containing a `table` field.
DECLARED_AT_BRANCH = {
    ("derive", "join"): {"right_table": "r", "on": [], "take": []},
    ("derive", "decide"): {"key": ["a"], "fields": ["b"]},
    # 🔴 [판정 536 ⑥] THIS ENTRY SAID `"mappers.x.y"` AND THE LOADER CANNOT READ THAT.
    #   Measured 2026-09-17: `as_chain_rule` does `out.update(derive.get("mapper") or {})`,
    #   so a string raises `ValueError: dictionary update sequence element #0 has length 1`.
    #   The entry is described as 「the shapes this repository actually commits」 - and what
    #   the repository commits is a dict (`to_declaration` produces one, and the loader and
    #   namespace fixtures both write one). So this gate was pinning the skeleton to a
    #   declaration the product REFUSES: 「a screen that cannot produce a declaration the
    #   loader accepts」, which is the very defect it exists to catch, pointing the other way.
    ("derive", "mapper"): {"mapper_module": "mappers.x", "mapper_function": "y",
                           "params": {"an_argument": 1}},
    ("into", "table"): "dt_x",
    ("into", "read"): True,
}


@pytest.mark.parametrize("where,branch", sorted(DECLARED_AT_BRANCH))
def test_a_branch_node_matches_what_a_declaration_puts_there(where, branch):
    """🔴 MY FIRST CUT WRAPPED THREE OF THE FIVE ONE LAYER TOO DEEP, and the client
    caught it by putting the server's JSON beside the committed declaration fixtures before
    building against it (`fedf6a15`). A form built on the wrapped shape would have asked for
    `into: {"table": {"table": "dt_x"}}` - a screen that cannot produce a declaration the
    loader accepts, which is the two-authors defect arriving through a schema instead of
    through prose.

    ⚠️ `join` AND `decide` WERE ALREADY RIGHT, and that is the tell: their cell IS a
    record. `mapper`, `table` and `read` are a name, a name and a flag."""
    node = _field(_unified(), where)["node"]["branches"][branch]
    declared = DECLARED_AT_BRANCH[(where, branch)]

    if isinstance(declared, dict):
        assert node["kind"] == "record", (where, branch, node)
        drawn = {f["key"] for f in node["fields"]}
        assert set(declared) <= drawn, (where, branch, sorted(set(declared) - drawn))
    else:
        assert node["kind"] == "leaf", (where, branch, node)


# ---------------------------------------------------------------------------
# ⛔ ⓑ — what this round must not break or invent
# ---------------------------------------------------------------------------

def test_the_flat_shape_is_untouched():
    """⛔ GATE ②. Every rule in production is written flat; a form that stopped drawing it
    would be this round breaking the grammar it was extending."""
    root = chain_bindings.skeleton()["root"]

    assert [f["key"] for f in root["fields"]] == list(chain_bindings.routing_keys())


def test_no_branch_names_a_closed_list_nobody_serves():
    """🔴 THE BLANK THIS ROUND FOUND, AND THE SIDE IT CHOSE. 판정 407's node also carries a
    `list` naming a closed list - and nothing serves closed lists on the chain side
    (`chain_rule_raw_view` publishes none; the only `closed_lists()` belongs to the ledger
    authoring screen). A name pointing at nothing is 「the form draws it and nothing reads
    it」, which is the defect three of this week's rounds removed. The branch KEYS are the
    list, so the values keep one author.

    ⚠️ AND THE CHOICE IS THE REVERSIBLE ONE: adding a `lists` cell later is additive;
    removing a dangling name from a shipped contract is not."""
    for key in ("derive", "into"):
        node = _field(_unified(), key)["node"]
        assert "list" not in node, (key, node)
        assert node["branches"], key


def test_a_rule_says_which_grammar_it_is_written_in():
    """⚠️ GATE ③. The two shapes ride together, so the screen has to know which to draw -
    and that is a fact the file states (`derive`), not one the form should re-derive."""
    import json
    import tempfile

    from ledger import admin

    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "chain_rules.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"rules": [
                {"name": "flat_one", "trigger_table": "t", "target_table": "t"},
                {"name": "unified_one", "on": {"table": "t"},
                 "derive": {"kind": "mapper", "mapper": "m"},
                 "into": {"table": "t"}}]}, handle)

        original = admin.chain_rules_path
        admin.chain_rules_path = lambda: path
        try:
            assert admin.chain_rule_raw_view("flat_one")["grammar"] == "flat"
            assert admin.chain_rule_raw_view("unified_one")["grammar"] == "unified"
        finally:
            admin.chain_rules_path = original


def _map_nodes(node, trail=()):
    """Every `kind: map` in the skeleton, with the path it sits at."""
    if isinstance(node, dict):
        if node.get("kind") == "map":
            yield trail, node
        for key, value in node.items():
            for found in _map_nodes(value, trail + (str(key),)):
                yield found
    elif isinstance(node, list):
        for index, value in enumerate(node):
            for found in _map_nodes(value, trail + (str(index),)):
                yield found


def test_every_map_node_is_spelled_the_way_the_reader_reads_it():
    """🔴 [판정 557] 한 종류, 두 철자 — 그리고 읽는 쪽은 «하나»만 압니다.

    `client2/src/ontology_skeleton.js` descends a map through `node.of` and documents its
    vocabulary at its own line 16: `{ keyed_by: 'name' | 'index', member, of }`. Its note
    says 「DESCENT HAS ONE AUTHOR」 - and it was true of the AUTHOR while being false of the
    SPELLINGS: the ledger's map nodes say `of`, the chain's said `node`, and
    `shapeAt(['derive','mapper','params', <any>])` therefore came back NULL. The form had a
    place for a mapper argument and no shape to draw in it.

    ⚠️ MEASURED THROUGH THE READER ITSELF (imported, never sliced) before this was written;
    this assertion is how the next person gets that measurement without running node -
    「사람이 재서 초록인 것은 다음 사람에게 초록이 아닙니다」 (판정 558 ①).

    ⛔ THE FIX BELONGS ON THIS SIDE. Teaching the reader a second spelling would make the
    split permanent and would put the ledger's thirty-two map nodes at risk for the chain's
    two.
    """
    skeleton = chain_bindings.skeleton()
    found = list(_map_nodes(skeleton))

    assert found, "no map node in the skeleton, so this gate asserts nothing"
    for trail, node in found:
        where = ".".join(trail) or "<root>"
        assert "of" in node, (
            "the map at %s does not say `of`, so the reader cannot descend into a member "
            "of it - and a form drawing that cell has no shape to draw" % where)
        assert node.get("keyed_by") in ("name", "index"), (
            "the map at %s is keyed by %r, which is outside the reader's vocabulary "
            "('name' | 'index') - it works only by falling through" % (where, node.get("keyed_by")))
