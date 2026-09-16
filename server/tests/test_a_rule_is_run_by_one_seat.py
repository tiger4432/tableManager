# -*- coding: utf-8 -*-
"""S-279 · 판정 420 ㉡. A chain rule is RUN by one function, and asking which door it goes
through is that function's question.

🔴 WHY A TEXT ORACLE. The census this was built from (판정 419 ①) counted ONE judgement -
「is this rule a builtin」 - written in SEVEN spellings across 20 sites. A string grep can only
find the spelling you already thought of, so this reads the AST: a call to either door is a
call whatever the module was aliased to and whatever the variable holding it was renamed to.
📎 This is the drift-oracle exception in CLAUDE.md, not the forbidden kind: the TEXT is the
subject here (「who calls the doors」), not a stand-in for behaviour. The behaviour is gated
separately in `test_the_seat_runs_both_doors_the_same_way.py`.

⚠️ THE MEMBERS ARE PINNED, NOT THE COUNT. A count passes while one legitimate caller moves in
and one illegitimate one moves out. What is pinned below is the list of functions that still
call a door directly, measured off the AST at S-279, and it is expected to become EMPTY in
㉡-2 - the same commit that rewires them has to shorten this list, which is the point.
"""
import ast
import os
import sys

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import rule_run                                            # noqa: E402

#: The two doors. A rule is EXECUTED by calling one of these; everything else about a rule
#: (loading it, ordering it, naming its kind) is a different question with its own seats.
DOORS = ("run_builtin", "execute_custom_mapper")

#: The one seat allowed to call them, plus the modules that DEFINE them.
SEAT = "chain/rule_run.py"
DEFINERS = ("chain/builtins.py", "chain/mapper_call.py")

#: 🔴 `.py.sample` IS IN THE POPULATION. It is the shape every live mapper on an operator's
#: box was copied from, and a template that teaches 「call the door yourself」 is how the next
#: copy gets it. (Measured at S-279: zero samples call a door - this keeps it that way.)
SUFFIXES = (".py", ".py.sample")

#: ⚠️ MEASURED AT S-279, EXPECTED TO EMPTY IN ㉡-2. These three functions were counted off the
#: AST on 2026-09-16, before the seat had a single caller; the lead split the round so the
#: seat could be built while part one was still in a worktree touching the same file. Each
#: line is a rewiring that has not happened yet, NOT a site that is allowed to stay.
NOT_YET_MOVED = {
    "chain/ingestion_worker.py::_process_chain_transaction_group_sync",
    "chain/ingestion_worker.py::_run_builtin_followups",
    "chain/replay.py::replay_rule",
}


def _files():
    for folder, dirs, files in os.walk(SERVER_DIR):
        dirs[:] = [d for d in dirs if d not in (".tmp", "__pycache__", "tests")]
        for name in sorted(files):
            if name.endswith(SUFFIXES):
                yield os.path.join(folder, name)


def _door_callers(path):
    """Functions in `path` that call a door, read off the AST.

    Both `builtins.run_builtin(...)` and a bare `run_builtin(...)` after a from-import are the
    same call and both are counted - the second spelling is the one `ingestion_worker` uses
    for one door and not the other.
    """
    with open(path, encoding="utf-8") as handle:
        try:
            tree = ast.parse(handle.read(), path)
        except SyntaxError:                                            # pragma: no cover
            return []
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for call in ast.walk(node):
            if not isinstance(call, ast.Call):
                continue
            named = getattr(call.func, "attr", None) or getattr(call.func, "id", None)
            if named in DOORS:
                out.append(node.name)
                break
    return out


def _sites():
    found = set()
    for path in _files():
        rel = os.path.relpath(path, SERVER_DIR).replace("\\", "/")
        if rel == SEAT or rel in DEFINERS:
            continue
        for function in _door_callers(path):
            found.add("%s::%s" % (rel, function))
    return found


def test_no_new_seat_starts_running_rules_behind_the_one_that_does():
    """🔴 THE GATE. A site that runs a rule outside `run_rule` is red the day it appears.

    The pinned set is what S-279 measured, so this fails on an ADDITION immediately and on a
    REMOVAL too - a rewiring that lands without shortening the list leaves a false sentence in
    this file, and a false sentence about what is left to do is how 「간다」 gets reported as
    「돈다」.
    """
    found = _sites()

    appeared = sorted(found - NOT_YET_MOVED)
    assert appeared == [], (
        "these run a chain rule without going through %s, and the seat exists so that "
        "nothing has to ask which door a rule takes: %s" % (SEAT, appeared))

    vanished = sorted(NOT_YET_MOVED - found)
    assert vanished == [], (
        "these no longer call a door directly - move them out of NOT_YET_MOVED in this file, "
        "in the commit that rewired them: %s" % (vanished,))


def test_the_seat_is_the_one_that_asks_which_door():
    """The question itself, not only the call. `builtin_kind` is where 「is this a builtin」 is
    answered, so a caller that needs the answer WITHOUT running (replay reports it in its
    stats) has somewhere to ask that is not a second copy of the comparison."""
    assert callable(rule_run.builtin_kind)
    assert rule_run.builtin_kind({"mapper": "definitely_not_a_registered_kind"}) is None
    assert rule_run.builtin_kind({}) is None
    assert rule_run.builtin_kind(None) is None
