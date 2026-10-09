# -*- coding: utf-8 -*-
"""총괄 10-09 (소유자 「체인 고리 로그는 왜 계속 떠?」 · 「무슨 똑같은 게 10 개씩 나옴」): a chain loop is said
by the dispatcher alone, once per loop - its canonical form, whichever rule a walk started from and
whichever of the two seats met it - and once per declaration content; a slot, a respawn and a
re-read of the same declaration say nothing.
"""
import ast
import json
import logging
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import mapper_sdk                                                    # noqa: E402
from chain import ingestion_worker as worker                         # noqa: E402
from chain import rule_order                                         # noqa: E402

PARAMS = {"key_columns": ["k"], "columns": ["v"], "hold_column": "hold"}


def _rule(name, trigger, target, **more):
    return {"name": name, "trigger_table": trigger, "target_table": target,
            "mapper": "copy_rows_with_hold", "params": dict(PARAMS), **more}


#: One loop, loop_a -> loop_b -> loop_a, met from three rules (one a descent into it) and by both
#: seats: the order walk over rules, and the cascade graph over tables (both rules opt in).
RULES = [_rule("r_ab", "loop_a", "loop_b", allow_chain_trigger=True),
         _rule("r_ba", "loop_b", "loop_a", allow_chain_trigger=True),
         _rule("r_ca", "loop_c", "loop_a")]


@pytest.fixture(name="declared")
def fixture_declared(tmp_path, monkeypatch):
    mapper_sdk.discover()
    import mappers.hold_copy                                         # noqa: F401 - registers
    path = tmp_path / "chain_rules.json"
    monkeypatch.setattr(worker, "RULES_PATH", str(path))
    monkeypatch.setattr(rule_order, "_SAID_FOR", None)

    def write(rules, depth=4):
        path.write_text(json.dumps({"max_chain_depth": depth, "rules": rules}), encoding="utf-8")
    write(RULES)
    return write


def _loop_lines(caplog):
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith("[ChainRules] loop:")]


def test_one_loop_is_one_key_whichever_node_a_walk_started_from():
    assert rule_order.loop_of(["a", "b", "c", "a"]) == rule_order.loop_of(["b", "c", "a", "b"]) \
        == rule_order.loop_of(["x", "y", "c", "a", "b", "c"]) == ("a", "b", "c")          # a descent is cut
    assert rule_order.loop_of(["t", "t"]) == ("t",)
    assert rule_order.cycle_note(["b", "a", "b"], 5) == "[ChainRules] loop: a -> b -> a · capped at max_chain_depth=5"


def test_the_dispatcher_says_a_loop_once_and_a_slot_or_a_respawn_says_nothing(declared, caplog):
    caplog.set_level(logging.INFO)
    for _process in range(4):                                         # two slots, each respawned once
        worker.load_chain_rules()
    assert _loop_lines(caplog) == []
    worker.load_chain_rules()                                         # the dispatcher's read
    assert worker.say_the_declaration() == 1
    assert _loop_lines(caplog) == ["[ChainRules] loop: loop_a -> loop_b -> loop_a · capped at max_chain_depth=4"]
    for _ in range(10):                                               # the same declaration again
        worker.load_chain_rules()
        worker.say_the_declaration()
    assert len(_loop_lines(caplog)) == 1
    declared(RULES, depth=6)                                          # the declaration changed
    worker.load_chain_rules()
    worker.say_the_declaration()
    assert _loop_lines(caplog)[1:] == ["[ChainRules] loop: loop_a -> loop_b -> loop_a · capped at max_chain_depth=6"]


def test_only_the_dispatchers_loop_says_the_loops():
    """The seat is the call: `say_the_declaration` is called by the dispatcher's loop and by nothing a
    slot runs - a slot reads the same declaration through the same loader."""
    def callers(path):
        tree = ast.parse(open(os.path.join(SERVER_DIR, path), encoding="utf-8").read())
        found = []
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                found += [fn.name for node in ast.walk(fn) if isinstance(node, ast.Call)
                          and getattr(node.func, "attr", getattr(node.func, "id", None)) == "say_the_declaration"]
        return found
    assert callers("chain/ingestion_worker.py") == ["start_chain_ingestion_worker"] * 2
    assert callers("chain/slots.py") == []
