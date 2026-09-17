# -*- coding: utf-8 -*-
"""S-279 · 판정 420 ㉡ · 495 · 496 · 497 · 498. A chain rule is RUN by one function, and every
question about WHICH code it runs is that function's question.

🔴 WHY A TEXT ORACLE. The census this was built from (판정 419 ①) counted ONE judgement -
「is this rule a builtin」 - written in SEVEN spellings across 20 sites. A string grep can only
find the spelling you already thought of, so this reads the AST.
📎 This is the drift-oracle exception in CLAUDE.md, not the forbidden kind: the TEXT is the
subject here (「who asks」), not a stand-in for behaviour. The behaviour is gated separately in
`test_the_seat_runs_both_doors_the_same_way.py`.

🔴 WHY NUMBERS AND NOT A LIST OF SITES (판정 497). Four rounds closed 「문 가르기」 correctly
and none of them closed it, because each was satisfiable by writing a second copy: S-246 fixed
「a builtin does not appear in the chain queue」 by adding a SECOND `activity.running` call -
correct, landed, and it made the split one layer thicker. What is asserted below cannot be
satisfied that way. A second copy makes the count go UP.

⚠️ AND 「builtin」 IS NOT A KIND OF RULE (판정 496). It is one of THREE ways a rule names its
code — `MAPPER_REGISTRY`, `import_module`, `BUILTIN_KINDS` — and the first two were already
one seat with one `if` inside them. Only the third was let outside, which is the whole of what
「the builtin door」 ever meant.
"""
import ast
import os
import sys

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import builtins                                            # noqa: E402
from chain import rule_run                                            # noqa: E402

#: The one seat. It resolves a name, registers the run, calls it, and answers in one shape.
SEAT = "chain/rule_run.py"

#: The modules that DEFINE the tables a name can be found in. They are allowed to touch their
#: own contents; everybody else asks the seat.
DEFINERS = ("chain/builtins.py", "mapper_sdk.py")

#: 🔴 `.py.sample` IS IN THE POPULATION. It is the shape every live mapper on an operator's
#: box was copied from, and a template that teaches 「resolve it yourself」 is how the next
#: copy gets it. (Measured at S-279: zero samples do - this keeps it that way.)
SUFFIXES = (".py", ".py.sample")

#: The two tables a rule name is looked up in.
TABLES = ("BUILTIN_KINDS", "MAPPER_REGISTRY")

#: Names whose only purpose is to say WHICH kind a rule is. Comparing against one of these is
#: the kind question in another spelling, and 판정 498 ④ found sites that a census of function
#: CALLS had missed entirely: `rule_shape` decided join/decide/mapper by comparing imported
#: constants, and `ingestion_worker` filtered the follow-up lap with `in BUILTIN_KINDS`.
#: Neither is a call to `builtin_kind`; both are the same question.
KIND_NAMES = ("JOIN_MAPPER", "JOIN_INTO_MAPPER", "AUTO_CONFIRM_MAPPER",
              "BUILTIN_KINDS", "SELF_WRITING_KINDS", "BUILTIN_LABELS")

#: ⚠️ EMPTY, AND THAT IS THE ASSERTION (판정 498 ⑤). Each line would be a rewiring that has
#: NOT happened yet, never a site that is allowed to stay - my first draft of this gate had a
#: separate 「allowed, and here is the good reason」 list and the lead withdrew that shape: a
#: list of blessed exceptions makes the code DECLARE the split legitimate.
#: 🪦 Every name that was ever here left in the commit that rewired it:
#:    `chain/replay.py::replay_rule` (판정 421, and again at 498 — it asked the kind to learn
#:    whether a result can be SEEN without being applied, which is now a registered fact it
#:    reads off `resolve`), `chain/ingestion_worker.py::_process_chain_transaction_group_sync`
#:    and `::_run_the_follow_up_pass` (판정 423, then 495).
NOT_YET_MOVED = set()


def _files():
    for folder, dirs, files in os.walk(SERVER_DIR):
        dirs[:] = [d for d in dirs if d not in (".tmp", "__pycache__", "tests")]
        for name in sorted(files):
            if name.endswith(SUFFIXES):
                yield os.path.join(folder, name)


def _rel(path):
    return os.path.relpath(path, SERVER_DIR).replace("\\", "/")


def _parsed(path):
    with open(path, encoding="utf-8") as handle:
        try:
            return ast.parse(handle.read(), path)
        except SyntaxError:                                            # pragma: no cover
            return None


def _sites(predicate, skip_definers=True):
    """Every `file::function` outside the seat where `predicate` holds of some node."""
    found = set()
    for path in _files():
        rel = _rel(path)
        if rel == SEAT or (skip_definers and rel in DEFINERS):
            continue
        tree = _parsed(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for inner in ast.walk(node):
                if predicate(inner):
                    found.add("%s::%s" % (rel, node.name))
                    break
    return found


def _holder(node):
    return getattr(node, "attr", None) or getattr(node, "id", None)


def _turns_a_name_into_a_callable(node):
    """`TABLE[name]` or `TABLE.get(name)` — resolution.

    ⚠️ NOT `.pop` / `.clear` / iteration. The dev bench removes a mapper it registered for one
    request, which is MAINTAINING the table rather than reading an answer out of it, and a
    predicate that could not tell those apart would be asking for the wrong repair.
    """
    if isinstance(node, ast.Subscript):
        return _holder(node.value) in TABLES
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return node.func.attr == "get" and _holder(node.func.value) in TABLES
    return False


def _asks_which_kind(node):
    """The CALL and the CONSTANT COMPARISON both count (판정 498 ④)."""
    if isinstance(node, ast.Call) and _holder(node.func) == "builtin_kind":
        return True
    if isinstance(node, ast.Compare):
        for part in ast.walk(node):
            if _holder(part) in KIND_NAMES:
                return True
    return False


def _registers_a_run(node):
    return (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "running"
            and getattr(node.func.value, "id", None) == "activity")


def test_one_place_turns_a_rule_name_into_something_to_call():
    """CLOSING NUMBER ① — two tables, ONE reader.

    A rule may name its code in the decorator registry or in the builtin table, and three
    places used to look: the seat, the config report's 「can this run」 check, and the dev
    bench. Three readers of two tables is how a name comes to be runnable in one place and
    unknown in another, and that was not hypothetical - the report asked only
    `MAPPER_REGISTRY`, so a `builtin:` name the loader runs happily was shown to the operator
    as unresolvable.
    """
    found = _sites(_turns_a_name_into_a_callable)

    assert found == set(), (
        "these turn a rule name into a callable outside %s - ask `rule_run.runnable` (for a "
        "name) or `rule_run.resolve` (for a whole rule) instead: %s" % (SEAT, sorted(found)))


def test_one_place_registers_that_a_rule_is_running():
    """CLOSING NUMBER ② — `activity.running` is called from ONE seat.

    🔴 THIS IS THE ONE A SECOND COPY SATISFIED. 소유자 2026-09-15: 「체인 대기열에서 안 뜨고
    돌고 있었네」. The repair wrote the registration a second time, in the other door. The
    queue view is fed by one writer now, so two rules cannot report their run differently.
    """
    found = _sites(_registers_a_run, skip_definers=False)

    assert found == set(), (
        "these register a chain run outside %s, so the queue view has two writers and the "
        "rules that go through each can drift apart: %s" % (SEAT, sorted(found)))


def test_the_kind_question_is_asked_in_one_place_however_it_is_spelled():
    """CLOSING NUMBER ④ — the CALL and the CONSTANT COMPARISON, both.

    🔴 A GATE THAT WATCHED ONLY CALLS WATCHED THE MORE EXPENSIVE HALF, and this gate was that
    gate for two rounds: `ingestion_worker` asked `builtin_kind` and then BRANCHED under a
    green line here (판정 495), while `rule_shape` made the same judgement with `==` against
    imported constants and was never counted at all. A kind registered tomorrow would have
    been labelled 「mapper」 on screen and skipped by the follow-up lap, with nothing red.
    """
    found = _sites(_asks_which_kind)

    appeared = sorted(found - NOT_YET_MOVED)
    assert appeared == [], (
        "these decide what kind of code a rule runs, outside %s - ask the seat "
        "(`resolve` · `rule_label` · `runnable`) rather than spelling the judgement again: %s"
        % (SEAT, appeared))

    vanished = sorted(NOT_YET_MOVED - found)
    assert vanished == [], (
        "these no longer ask - shorten NOT_YET_MOVED in the commit that rewires them, or this "
        "file keeps a false sentence about what is left to do: %s" % (vanished,))


#: Every log tag the chain package writes, and what each one NAMES. 🔴 [판정 499] MEMBERS,
#: NOT A COUNT, and a literal is a member: the first version of this gate watched the
#: `mapper@` CONSTANT only, so three `[ChainBuiltin]` lines spelled straight into their
#: format strings survived 498 untouched - and that tag names a KIND, which is the one thing
#: a tag may not do here.
#:
#: ⚠️ A TAG THAT NAMES A SUBSYSTEM OR A STAGE IS FINE; that is what all of these do. What is
#: forbidden is a tag that says what KIND of rule ran, because then an operator has to know
#: the kind before they can pick the words - 판정 498 ③ in one sentence.
CHAIN_LOG_TAGS = {
    "%s": "the seat's own line, composed from RULE_LOG_TAG",
    "Chain": "the group step",
    "Chain Depth": "the hop ceiling",
    "Chain Worker": "the process",
    "ChainKeyGate": "the business-key gate",
    "ChainRetract": "withdrawal when a trigger row is deleted",
    "ChainRules": "the loader and the synthesis halves",
    # ⚠️ [판정 507] WAS `HOL Guard` UNTIL 09-17, and the description below was always the
    #: plain sentence - the tag was the only part an operator could not read. Re-adding the
    #: old spelling turns this gate red, because it would not be a member here.
    "ChainWaiting": "a blocked group making later groups wait",
    # 🔴 [판정 562] THE STAGE IS NEW AND SO IS THE MEMBER. Templates are built from the
    #: declaration and registered at import; if that install dies the chain must still be
    #: importable, so the failure is a LOG rather than an exception - and a log nobody can
    #: grep is the half-measure this gate exists to refuse.
    "DynamicMappers": "installing the mappers built from the declaration",
    "LayerHealth": "the layering check",
    "Ledger": "the ledger follow-up",
    "LedgerCensus": "the retroactive census",
    "LedgerFollowUp": "the ledger's own lap",
    "Reload": "the config reload",
    "VirtualJoin": "the legacy join declaration",
    "VirtualJoin:%s": "the legacy join declaration, named",
    "Warmup": "process start",
}

#: Log methods a tag can ride on.
LOG_CALLS = ("info", "warning", "error", "debug", "log", "exception")


def test_one_vocabulary_says_that_a_rule_ran():
    """CLOSING NUMBER ③ — one execution-log tag, not two.

    An operator grepping 「did this rule run」 had to know the kind before they could pick the
    words: a self-writing run was `[ChainRule] ... written=` and a file-mapper run
    `[mapper@<logfile>] ... rows_out=`, START/END/RAISED under a second tag. A third,
    `[ChainBuiltin]`, said the follow-up lap's half.

    🔴 [판정 499] AND THE LAP'S TAG WAS MADE FALSE BY THIS VERY ROUND. The lap used to select
    `rule.get("mapper") in BUILTIN_KINDS`, so 「builtin」 was true of everything it logged;
    it selects `rule_run.writes_itself` now - a registered property - so a FILE mapper that
    registers it would be logged as a builtin. Today no kind does, which is exactly why this
    had to be a gate rather than a reading: 「가드는 도달 가능해지는 날 틀린다」.

    ⚠️ ASSERTED ON WHAT IS BUILT, NOT ON THE CHARACTERS. The retired tags still appear in
    prose - in this repository the note explaining a retired mechanism is kept on purpose -
    so a test that forbade the letters would be asking for those notes to be deleted, which
    is the cheapest way to turn a gate green and lose the reason.
    """
    built = {}
    unknown = {}
    for path in _files():
        tree = _parsed(path)
        if tree is None:
            continue
        rel = _rel(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value.startswith("mapper@"):
                    built.setdefault("%s:%d" % (rel, node.lineno), node.value)
            # A tag spelled into a log call's format string - the spelling that survived 498.
            if not (isinstance(node, ast.Call) and rel.startswith("chain/")):
                continue
            if (getattr(node.func, "attr", None) or "") not in LOG_CALLS:
                continue
            for arg in node.args:
                if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
                    continue
                if arg.value.startswith("[") and "]" in arg.value:
                    tag = arg.value[1:arg.value.index("]")]
                    if tag not in CHAIN_LOG_TAGS:
                        unknown["%s:%d" % (rel, node.lineno)] = tag
                break

    assert built == {}, (
        "a second execution-log vocabulary is being constructed here: %s" % (sorted(built),))

    assert unknown == {}, (
        "these chain log lines carry a tag this file does not know: %s\n"
        "If the line reports a RULE RUNNING, use `rule_run.RULE_LOG_TAG` - there is one "
        "vocabulary for that and a second one is what 판정 498 ③ closed. If it names a "
        "subsystem or a stage, add it to CHAIN_LOG_TAGS above with what it names."
        % (sorted(unknown.items()),))


def test_the_seat_answers_the_name_question_it_took_over():
    """The question itself, not only the call. `runnable` is where a NAME is answered for -
    the half the report and the dev bench used to do by hand.

    ⚰️ [판정 495 · 562] THIS ALSO ASKED `builtin_kind` — 「is this a builtin」. That question
    was an ADDRESS question and the table behind it is deleted; what is left is 「does this
    name resolve」, which is one question with one answer.
    """
    assert rule_run.runnable("definitely_not_a_registered_kind") is None
    assert rule_run.runnable(None) is None
    from chain import dynamic_mappers

    assert dynamic_mappers.TEMPLATES, "nothing is registered, so this asserts nothing"
    for name in dynamic_mappers.TEMPLATES:
        assert rule_run.runnable(name) is not None, (
            "%r is registered but the seat cannot resolve it by name, so the two halves of "
            "「can this run」 disagree" % name)


def test_the_two_facts_the_seat_reads_come_off_the_registration():
    """🔴 [판정 497 ⓒ · 498 ①] `writes_itself` and the screen label are REGISTERED, not
    inferred from 「is this a builtin」.

    That inference is a fact about where code LIVES standing in for a fact about what it DOES,
    and it is what let a dry run and a live lap grow separate branches off one word. A kind
    that PROPOSED its rows would be handled by every seat in the product without one of them
    being edited - which is the property this pins, by registering exactly such a kind.

    ⚠️ AND THE CALL SHAPE IS NOT THAT FACT. My first build of the seat chose between
    `(db, rule, row_ids=)` and `(db, payload)` on `writes_itself`, so this probe went down the
    proposing arm and was called `(db, row_id)`. `hands` says how it is called; `writes_itself`
    says only whether its result can be seen without being applied.
    """
    # ⚰️ [판정 562 · 508] THE LABEL TABLE WENT AND THE FACT DID NOT. Every mapper the product
    #   builds from a declaration must carry a screen label, or `rule_label` calls it 「mapper」
    #   in silence - so the population is the templates and the fact lives beside them.
    from chain import dynamic_mappers

    assert dynamic_mappers.TEMPLATES, "nothing is registered - the registry is the subject"
    for name in dynamic_mappers.TEMPLATES:
        assert dynamic_mappers.label_for(name), (
            "%r registered an implementation but no screen label, so `rule_label` calls it "
            "「mapper」 in silence" % name)

    probe = "declared:s498_probe"
    seen = {}

    def _probe(db, payload, rule=None):
        seen["payload"] = payload
        return {}

    # ⚠️ [판정 509 · 562] `hands` IS GONE - there is one calling convention, so a probe does
    #   not declare how it is called. What it still declares is the fact about its WORK:
    #   whether the caller has to write what it produced.
    import mapper_sdk

    mapper_sdk.register(probe, _probe)
    dynamic_mappers.TEMPLATE_FACTS[probe] = {"label": "decide", "stamps_origin": False,
                                             "writes_itself": False, "params": None}
    try:
        bound = rule_run.resolve({"name": "p", "mapper": probe})
        assert bound.call is _probe
        assert rule_run.writes_itself({"mapper": probe}) is False, (
            "a mapper that registered itself as PROPOSING was still treated as self-writing, "
            "so the seat is inferring from its name again")
        assert rule_run.rule_label({"mapper": probe}) == "decide"
    finally:
        mapper_sdk.MAPPER_REGISTRY.pop(probe, None)
        mapper_sdk.MAPPER_PARAMS.pop(probe, None)
        dynamic_mappers.TEMPLATE_FACTS.pop(probe, None)
