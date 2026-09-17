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
#:
#: 🔴 [판정 495·496] `builtin_kind` JOINS THEM, BECAUSE ASKING IS HOW THE BRANCH CAME
#: BACK. The call was gated from S-279 and the QUESTION was not, so `ingestion_worker` asked
#: and then branched — a second door wearing the seat's clothes, standing under a green gate
#: for two rounds. A caller that asks in order to act has made the distinction whether or not
#: it called a door, so the two belong in one predicate.
#:
#: ⚠️ AND 「builtin」 IS NOT A KIND OF RULE (판정 496). It is one of THREE ways a rule names
#: its code — `MAPPER_REGISTRY`, `import_module`, `BUILTIN_KINDS` — and the first two are
#: already one seat with one `if` inside it (`mapper_call.py:32-46`). Only the third was let
#: outside, which is the whole of what 「the builtin door」 means.
DOORS = ("run_builtin", "execute_custom_mapper")
ASKING = ("builtin_kind",)

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
#: 🪦 EMPTY SINCE ㉡-2ⓑ, and every name that was here left in the commit that rewired it:
#:    `chain/replay.py::replay_rule` (ⓐ, 판정 421), then
#:    `chain/ingestion_worker.py::_process_chain_transaction_group_sync` and
#:    `::_run_builtin_followups` (ⓑ, 판정 423). An empty set is the gate's real shape - from
#:    here on, ANY site that runs a rule outside the seat is red the day it appears.
#:
#: 🔴 [판정 495·496] `replay_rule` IS BACK, AND IT IS A DEBT RATHER THAN A PERMISSION.
#: It left this list at 판정 421 when it stopped calling a door; it returns because the
#: predicate widened to the QUESTION, which it still asks. My first draft of this gate put it
#: in a separate 「allowed, and here is the good reason」 list, and the lead withdrew that
#: shape: a list of blessed exceptions makes the code DECLARE the split legitimate, which is
#: the opposite of closing it. The line above holds for this entry too — 「a rewiring that has
#: not happened yet, NOT a site that is allowed to stay」.
#:
#: What it still GETS by asking, so whoever moves it knows what has to survive the move: a
#: retroactive run must know BEFORE applying anything whether this rule's result can be seen
#: without being performed. A proposing kind returns `updates` a dry run can count; a
#: self-writing kind has no output until it writes, so the dry run reports what it would be
#: HANDED instead, and it isolates a throwing page (판정 403). That is content, unlike the
#: live-lap branch 495 deleted — which is why this one is owed rather than simply removed.
NOT_YET_MOVED = {"chain/replay.py::replay_rule"}


def _files():
    for folder, dirs, files in os.walk(SERVER_DIR):
        dirs[:] = [d for d in dirs if d not in (".tmp", "__pycache__", "tests")]
        for name in sorted(files):
            if name.endswith(SUFFIXES):
                yield os.path.join(folder, name)


def _door_callers(path):
    """Functions in `path` that call a door OR ask which door, read off the AST.

    Both `builtins.run_builtin(...)` and a bare `run_builtin(...)` after a from-import are the
    same call and both are counted - the second spelling is the one `ingestion_worker` uses
    for one door and not the other.

    🔴 ASKING COUNTS AS MAKING THE DISTINCTION (판정 495). `rule_run.builtin_kind(rule)`
    followed by a branch is the same defect as calling a door directly, and it is the cheaper
    one to write - so a gate watching only calls was watching the more expensive half.
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
            if named in DOORS or named in ASKING:
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
        "these run a chain rule outside %s, or ask which door it takes in order to act on "
        "the answer - the seat exists so nothing else has to make that distinction: %s"
        % (SEAT, appeared))

    vanished = sorted(NOT_YET_MOVED - found)
    assert vanished == [], (
        "these no longer call a door directly - move them out of NOT_YET_MOVED in this file, "
        "in the commit that rewired them: %s" % (vanished,))


def test_the_seat_is_the_one_that_asks_which_door():
    """The question itself, not only the call. `builtin_kind` is where 「is this a builtin」 is
    answered, so nobody has to spell the comparison a second time.

    ⚰️ [판정 495] THIS USED TO END 「so a caller that needs the answer WITHOUT running has
    somewhere to ask」, AND THAT SENTENCE WAS A PERMISSION SLIP. Having one place to ask is
    not a licence to ask from anywhere: `ingestion_worker` asked and then BRANCHED. Who still
    asks is pinned in `NOT_YET_MOVED` above, as debt."""
    assert callable(rule_run.builtin_kind)
    assert rule_run.builtin_kind({"mapper": "definitely_not_a_registered_kind"}) is None
    assert rule_run.builtin_kind({}) is None
    assert rule_run.builtin_kind(None) is None
