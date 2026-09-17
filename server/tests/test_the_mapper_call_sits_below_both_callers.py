# -*- coding: utf-8 -*-
"""S-214. The place a mapper is called from belongs to neither caller.

🔴 THERE WAS NEVER A SECOND EXECUTOR. `execute_custom_mapper` had one definition in
this repository, and its own docstring said it was 「the only place every custom mapper is
called through」. What was wrong was its ADDRESS: it lived inside the worker, so replay had to
import the worker to run a mapper. That is a shared primitive in one caller's house - letter
for letter the shape S-211 ① fixed for `withdraw_source`, pointing the other way.

⚰️ [판정 498] THE EXECUTOR ITSELF IS GONE, AND THE PROPERTY OUTLIVED IT. It was one of TWO
places that turned a rule's name into something to call, so it folded into `rule_run.run_rule`
along with the builtin door. The subject below is therefore the SEAT: whoever runs a rule must
reach it in its own house and never through another caller's. That is the same sentence with a
new address, which is why this file was retargeted rather than deleted - the edge S-214 removed
is the edge that would come back.

⚠️ THE TRANSACTION SHAPES DID NOT MOVE AND MUST NOT. Replay commits per chunk, the worker
runs a group in one transaction, and both of those live OUTSIDE the executor. What moved is
「how a mapper is called」, nothing beside it.
"""
import ast
import io
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

HOME = os.path.join(SERVER_DIR, "chain", "mapper_call.py")


def _imports(relative):
    tree = ast.parse(io.open(os.path.join(SERVER_DIR, relative), encoding="utf-8").read())
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            found.add(node.module)
            found.update("%s.%s" % (node.module, a.name) for a in node.names)
    return found


@pytest.mark.parametrize("caller", ("chain/ingestion_worker.py", "chain/replay.py"))
def test_the_house_does_not_import_its_callers(caller):
    """⛔ THE PROPERTY THAT KEEPS IT NEUTRAL. The day this module imports the worker or
    replay it has taken a side, and the edge it was built to remove comes back."""
    named = _imports("chain/mapper_call.py")
    module = caller.replace("/", ".")[:-3]

    assert not any(n == module or n.startswith(module + ".") for n in named), named


def _modules_calling(symbol):
    """Every module under `server/` that CALLS `symbol`, read off the AST.

    🔴 COMPUTED, NOT LISTED (S-279). This was a parametrized list of two callers - a proxy for
    the property, and the proxy went red the day replay stopped calling the executor directly
    and started asking `chain.rule_run` to run the rule. The property was not weakened by
    that; it was strengthened. A hand-typed list cannot tell those two apart, so the
    population is measured instead - and it survived the executor being deleted under it,
    which a list would not have.
    """
    out = []
    for base, dirs, files in os.walk(SERVER_DIR):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".tmp", "tests")]
        for name in sorted(files):
            if not name.endswith(".py"):
                continue
            path = os.path.join(base, name)
            try:
                tree = ast.parse(io.open(path, encoding="utf-8").read(), path)
            except SyntaxError:                                        # pragma: no cover
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                named = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
                if named == symbol:
                    out.append(os.path.relpath(path, SERVER_DIR).replace(os.sep, "/"))
                    break
    return out


def test_whoever_runs_a_rule_imports_the_seat_from_its_own_home():
    """⛔ THE PROPERTY, FOR WHOEVER THE CALLERS TURN OUT TO BE. What must never come back is a
    module reaching the place that runs a rule through another CALLER's house; which modules
    call it is allowed to change, and did - twice now.

    ⚰️ [판정 498] THE SYMBOL MOVED FROM `execute_custom_mapper` TO `run_rule`. The executor was
    deleted, so a gate still naming it would have measured an empty population and read that
    as 「nobody reaches through a caller's house」 - a green that means the query resolved
    nothing. The assertion below refuses an empty population for exactly that reason."""
    callers = _modules_calling("run_rule")
    assert callers, "nobody runs a rule - either the seat died or this query resolved nothing"

    for caller in callers:
        named = _imports(caller)
        assert any("rule_run" in n for n in named), (caller, sorted(named))
        # ⚠️ NAMED PRECISELY, BECAUSE ONE CALLER IMPORTS THE WORKER ON PURPOSE. Replay reads
        #    `load_chain_rules` from it (판정 358: moving the loader was withdrawn, since the rule
        #    set it returns is produced by `chain.builtins`). 「imports the worker at all」 would
        #    therefore forbid a decision already taken; what must never come back is reaching
        #    the SEAT'S NAME through that house.
        assert "chain.ingestion_worker.run_rule" not in named, (
            "%s reaches the seat through a caller's house" % caller)


def test_replay_no_longer_imports_the_worker_for_the_executor():
    """🔴 THE EDGE THIS ROUND REMOVED - and only this one.

    ⚠️ REPLAY STILL READS THE WORKER, for `load_chain_rules`, and that is deliberate: moving
    the rule loader was withdrawn (판정 358) because the rule set it returns is produced by
    `chain.builtins`, so a light module would relocate the dependency rather than remove it.
    So this asserts what actually changed instead of a clean slate that is not true.

    🔵 [S-279, 판정 420 ㉡-2ⓐ] AND REPLAY NOW REACHES A MAPPER THROUGH NEITHER DOOR. It asks
    `chain.rule_run` to run the rule, and the seat imports the executor from its own home - so
    the edge S-214 removed is not merely absent, there is no longer a place for it to be.
    """
    replay = io.open(os.path.join(SERVER_DIR, "chain", "replay.py"), encoding="utf-8").read()

    assert "from chain.ingestion_worker import execute_custom_mapper" not in replay
    assert any("rule_run" in n for n in _imports("chain/replay.py"))
    # 🔴 THE SEAT STILL LIVES IN ITS OWN HOUSE. `mapper_call` kept the two pieces that are
    #    genuinely about calling a FILE mapper - the signature convention and the stage clock -
    #    so the seat importing it is the neutral-house shape, not a leftover edge.
    assert any("mapper_call" in n for n in _imports("chain/rule_run.py"))


def test_one_definition_of_the_seat_in_the_whole_repository():
    """🔴 WHAT THE RULING'S PREMISE GOT WRONG, pinned so it cannot quietly become true. If a
    second `def run_rule` ever appears, the two will answer 「which function is this rule's
    code」 differently, which is the defect the single seat exists to prevent."""
    # ⛔ THE FILESYSTEM, NOT `git grep`. A tracked-file sweep answers differently before and
    # after a commit - measured here: this very module was untracked when the gate first ran,
    # so the search found ZERO definitions and called that a failure of the product.
    defining = []
    for base, dirs, files in os.walk(SERVER_DIR):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".tmp")]
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(base, name)
            if any(line.startswith("def run_rule")
                   for line in io.open(path, encoding="utf-8", errors="replace")):
                defining.append(os.path.relpath(path, SERVER_DIR).replace(os.sep, "/"))

    assert defining == ["chain/rule_run.py"], defining
