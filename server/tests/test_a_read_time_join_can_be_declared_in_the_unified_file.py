# -*- coding: utf-8 -*-
"""S-251. `into: {read: true}` 를 통합 파일에 적으면 «읽기 시점 조인»이 선다.

🔴 문법엔 있고 «읽는 쪽이 없었다» — 이 저장소의 그 부류. `rule_shape.from_join_rule` 은
가상 조인 선언을 `into.read` 내부 표현으로 «바꾸지만», 그 모양을 다시 «세우는» 쪽이 아무도
없었다. 읽기 조인은 오늘까지 `virtual_join_rules.json` 에서만 살 수 있었다.

⛔ AND IT WAS WORSE THAN SILENT. Written in `chain_rules.json`, such a declaration came out
of `expand_declaration` as a rule with NO mapper cell and the loader dropped it as
`unresolvable_mapper` - a correct declaration reported to the operator as a typo.

⚠️ 「같은 검증·같은 이름공간·같은 부팅 줄」 IS THE WHOLE POINT. A second validator would be a
second answer to 「is this join runnable」, and where you wrote it must not change what it
means.
"""
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import virtual_join.config as vjc                                   # noqa: E402
from chain import ingestion_worker, rule_shape                      # noqa: E402

KNOWN = {
    "left_t": {"column_types": {"k": "string", "frame": "string"}},
    "right_t": {"column_types": {"k": "string", "frame": "string"}},
}

OLD_SHAPE = {"left_table": "left_t", "right_table": "right_t",
             "join_key": [{"left": "k", "right": "k"}], "expose": ["frame"]}

UNIFIED = {
    "name": "u_read", "enabled": True,
    "on": {"table": "left_t"},
    "into": {"read": True},
    "derive": {"kind": "join", "join": dict(OLD_SHAPE, left_table=None)},
}
UNIFIED["derive"]["join"].pop("left_table")


@pytest.fixture(name="declared")
def fixture_declared(monkeypatch):
    """What the unified file says this round, without touching the live one."""
    def _install(*raws):
        monkeypatch.setattr(ingestion_worker, "read_rules_document",
                            lambda path=None: {"rules": list(raws), "document": {},
                                               "path": "x", "exists": True,
                                               "error": None})
    return _install


# ---------------------------------------------------------------------------
# 🔴 ⓐ — the same join, wherever it was written
# ---------------------------------------------------------------------------

def test_a_unified_read_declaration_stands_as_a_virtual_join(declared):
    """🔴 THE ROUND. It joins the SAME list, so it gets the same validation, the same
    namespace, the same uniqueness gate (S-235) and the same retraction (S-248)."""
    declared(UNIFIED)

    rules = vjc.load_virtual_join_rules(known_tables=KNOWN)

    mine = [r for r in rules if r["name"] == "u_read"]
    assert len(mine) == 1, [r["name"] for r in rules]
    assert (mine[0]["left_table"], mine[0]["right_table"]) == ("left_t", "right_t")
    assert mine[0]["origin"] == "decl"


def test_the_two_files_describe_the_same_join_cell_for_cell(declared):
    """🔴 GATE ① — 「같은 검증」 MEANS THE SAME ANSWER, not a similar one. Every cell but the
    name has to match what the old file produces, or the unified grammar would be a second
    dialect wearing the same words."""
    declared(UNIFIED)
    from_unified = [r for r in vjc.load_virtual_join_rules(known_tables=KNOWN)
                    if r["name"] == "u_read"][0]

    from_old = vjc.validate_virtual_join_rules({"o_read": OLD_SHAPE},
                                               known_tables=KNOWN)[0]

    ignore = {"name", "origin", "required_index", "required_index_ddl"}
    assert {k: v for k, v in from_unified.items() if k not in ignore} == \
           {k: v for k, v in from_old.items() if k not in ignore}


def test_the_old_file_is_still_read(declared):
    """⚠️ 소유자: 「가상 조인은 그대로 두고」. This round ADDS a place to write one."""
    declared()

    rules = vjc.validate_virtual_join_rules({"o_read": OLD_SHAPE}, known_tables=KNOWN)

    assert [r["name"] for r in rules] == ["o_read"]


# ---------------------------------------------------------------------------
# ⛔ ⓑ — and it is not a chain rule
# ---------------------------------------------------------------------------

def test_a_read_declaration_stands_no_chain_rule_and_that_is_not_a_refusal(declared):
    """⛔ GATE ②. It writes nothing, has no trigger and runs no mapper - so standing one
    would put a rule on the loader that can never do anything. Before this it stood WITHOUT
    a mapper and was dropped as `unresolvable_mapper`: right declaration, wrong sentence."""
    stood, refusal, notes = rule_shape.expand_declaration(UNIFIED, KNOWN)

    assert stood == []
    assert refusal is None, refusal
    assert any("into.read" in note for note in notes), notes


def test_a_writing_join_still_stands_two_chain_rules(declared):
    """⚠️ THE CONTROL. `into.table` is the WRITE-time join and is untouched - the two are
    told apart by which `into` the declaration carries, which is the distinction the
    internal shape already made."""
    writing = dict(UNIFIED, name="u_write", into={"table": "left_t"})

    stood, refusal, _notes = rule_shape.expand_declaration(writing, KNOWN)

    assert refusal is None and len(stood) == 2


# ---------------------------------------------------------------------------
# ⚠️ ⓒ — one name, one join
# ---------------------------------------------------------------------------

def test_the_same_name_in_both_files_is_refused_once_by_name(declared):
    """⛔ GATE ③. Two declarations claiming one identity; picking either silently would
    make the other file a lie. Named once, through the collector every other refusal uses."""
    declared(dict(UNIFIED, name="dup"))
    rejections = []

    # ⚠️ ASKED OF THE SEAT THAT DECIDES IT. Driving this through the full loader would
    # need the LIVE `virtual_join_rules.json` to contain the name - which makes the test a
    # statement about this box's file rather than about the rule.
    picked = vjc._read_time_joins_from_unified({"dup"}, KNOWN, rejections)

    assert picked == []
    said = [r for r in rejections if r.get("subject") == "dup"]
    assert len(said) == 1, rejections
    assert "one name is one join" in said[0]["detail"]


def test_a_switched_off_read_declaration_is_not_validated_at_all(declared):
    """⛔ 판정 399 ③′. Off is off: not validated, not counted, not complained about."""
    declared(dict(UNIFIED, name="u_off", enabled=False))
    rejections = []

    rules = vjc.load_virtual_join_rules(known_tables=KNOWN, rejections=rejections)

    assert all(r["name"] != "u_off" for r in rules)
    assert all(r.get("subject") != "u_off" for r in rejections), rejections


def test_a_partial_read_does_not_pick_up_the_unified_half(declared):
    """⚠️ A CALLER PASSING `path` IS READING A SUBSET ON PURPOSE - a report, a test - and
    handing it the unified half would make 「what this file declares」 mean two things. The
    same reason the retraction refuses to run off a partial list (S-248)."""
    declared(UNIFIED)

    rules = vjc.load_virtual_join_rules(path=vjc.VIRTUAL_JOIN_RULES_PATH,
                                        known_tables=KNOWN)

    assert all(r["name"] != "u_read" for r in rules)
