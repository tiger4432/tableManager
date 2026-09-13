# -*- coding: utf-8 -*-
"""S-211 ①. `cell_layer` is light, and that is the whole of what it has to be.

🔴 THE RING WAS A SIMPLE FOUR-CYCLE and one call closed it: `virtual_join_executor` imported
`chain_replay.withdraw_source` from inside `retract_rows`. Retraction is not replay's
BEHAVIOUR - it is an operation both of them use - so it moved below both, and the ring
dissolved entirely rather than shrinking by one (판정 358).

⛔ THE PROPERTY THAT KEEPS IT DISSOLVED IS 「LIGHT」, and lightness is not a comment. The day
this module imports the worker, the executor or replay, the ring is back and nothing else
here would notice: every existing test would stay green, because a cycle in Python is silent
until an import order happens to expose it.

⚠️ A DEFERRED IMPORT COUNTS. Putting one inside a function is how the ring stayed invisible in
the first place, so this reads both places.
"""
import ast
import io
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

#: The four that were the ring, plus anything that would put us back inside it.
FORBIDDEN = ("chain_builtins", "chain_ingestion_worker", "chain_replay",
             "virtual_join_executor", "virtual_join_config", "chain_bindings")


def _imports(module_name):
    """Every module named, at module level AND inside a `def`."""
    path = os.path.join(SERVER_DIR, module_name + ".py")
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            found.add(node.module.split(".")[0])
    return found


@pytest.mark.parametrize("forbidden", FORBIDDEN)
def test_the_cell_layer_names_none_of_the_ring(forbidden):
    assert forbidden not in _imports("cell_layer")


def test_the_executor_reaches_the_operation_without_reaching_replay():
    """🔴 THE EDGE THAT WAS CUT. The executor still retracts; what it no longer does is reach
    through `chain_replay` to do it."""
    names = _imports("virtual_join_executor")

    assert "cell_layer" in names
    assert "chain_replay" not in names


def test_replay_reads_the_operation_rather_than_carrying_a_second_one():
    """⛔ ONE BODY. `chain_replay` kept twenty `raise ReplayRefused` and three helper calls, so
    it READS these names - that is an import, not a re-export, and there is one definition."""
    assert "cell_layer" in _imports("chain_replay")

    import cell_layer
    import chain_replay

    for name in ("withdraw_source", "ReplayRefused", "PROTECTED_SOURCES",
                 "_claimed_filter", "_load_cell_state", "_resolve_cell"):
        assert getattr(chain_replay, name) is getattr(cell_layer, name), name


def test_the_operation_still_refuses_to_withdraw_a_humans_layer():
    """⚠️ THE MOVE MUST NOT HAVE MOVED THE REFUSAL. `user` is the layer that means 「a human
    typed this」, and withdrawing it is data loss with extra steps."""
    import cell_layer

    with pytest.raises(cell_layer.ReplayRefused):
        cell_layer.withdraw_source(None, "any_table", "user")
