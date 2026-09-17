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
#: 🪦 [S-211 packaging] inside `chain/` these are bare module names; the virtual-join pair
#: is reached through its package. The property asserted is unchanged.
FORBIDDEN = ("synthesis", "ingestion_worker", "replay", "chain_bindings")


def _imports(module_name):
    """Every module named, at module level AND inside a `def`."""
    path = os.path.join(SERVER_DIR, *(module_name.split("/"))) + ".py"
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                found.add(a.name.split(".")[0])
                found.add(a.name)                       # `import enrichment.config`
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            found.add(node.module.split(".")[0])
            found.add(node.module)
            # 🔴 AND THE NAMES TAKEN OUT OF THE PACKAGE. After S-211 a module is reached as
            # `from chain import cell_layer`, so recording only the package head would make
            # every one of these assertions answer about `chain` rather than about the
            # module being asked after.
            for a in node.names:
                found.add(a.name)
                found.add("%s.%s" % (node.module, a.name))
    return found


@pytest.mark.parametrize("forbidden", FORBIDDEN)
def test_the_cell_layer_names_none_of_the_ring(forbidden):
    assert forbidden not in _imports("chain/cell_layer")


def test_the_executor_reaches_the_operation_without_reaching_replay():
    """🔴 THE EDGE THAT WAS CUT. The executor still retracts; what it no longer does is reach
    through `chain_replay` to do it."""
    names = _imports("chain/legacy_materialized_join")

    assert "chain.cell_layer" in names
    assert "replay" not in names


def test_replay_reads_the_operation_rather_than_carrying_a_second_one():
    """⛔ ONE BODY. `chain_replay` kept twenty `raise ReplayRefused` and three helper calls, so
    it READS these names - that is an import, not a re-export, and there is one definition."""
    assert "chain.cell_layer" in _imports("chain/replay")

    from chain import cell_layer
    from chain import replay

    for name in ("withdraw_source", "ReplayRefused", "PROTECTED_SOURCES",
                 "_claimed_filter", "_load_cell_state", "_resolve_cell"):
        assert getattr(replay, name) is getattr(cell_layer, name), name


def test_the_operation_still_refuses_to_withdraw_a_humans_layer():
    """⚠️ THE MOVE MUST NOT HAVE MOVED THE REFUSAL. `user` is the layer that means 「a human
    typed this」, and withdrawing it is data loss with extra steps."""
    from chain import cell_layer

    with pytest.raises(cell_layer.ReplayRefused):
        cell_layer.withdraw_source(None, "any_table", "user")
