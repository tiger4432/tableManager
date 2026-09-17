# -*- coding: utf-8 -*-
"""S-246 · 판정 497·498. 도는 규칙은 «어떻게 자기 코드를 이름 짓든» 대기열 화면에 있다.

> 소유자 2026-09-15: 「**체인 대기열에서 안 뜨고 돌고 있었네**」

🔴 THE REGISTRATION LIVED INSIDE ONE OF TWO DOORS. `activity.registry.start` /
`record_outcome` / `finish` were spelled inside `mapper_call.execute_custom_mapper` - the
door a FILE mapper came through - and `builtins.run_builtin` did none of the three. So
`builtin:join_into`, `builtin:join` and `builtin:auto_confirm` ran with no entry in
`GET /admin/chain/queue`'s running list at all.

⚰️ AND S-246 FIXED IT BY WRITING THE REGISTRATION A SECOND TIME. That repair was correct and
it made the split one layer thicker - 판정 497 counted it as the clearest case of a ruling
satisfiable by a copy. 판정 498 deleted BOTH doors into one seat, so this file no longer has
two functions to score; what it scores now is that a rule is registered the same way whichever
of the three ways it names its code (`builtin:` kind · `@mapper` registry name · import path).

⛔ AND THE SECOND HALF IS WORSE THAN AN EMPTY LIST. The loader SEEDS every declared rule
as `never_evaluated` so that absence means 「old server」 and nothing else - so a builtin
that had run a thousand times still reported 「아직 평가 안 됨」 for the life of the
process. A value that is wrong reads as an answer; an absent one at least reads as a gap.

⚠️ WHAT THIS FILE DOES NOT PROVE. It scores the REGISTRATION, not the route: that
`/admin/chain/queue` renders these entries is that route's own tests, and it reads the
same `snapshot()` this asserts on.
"""
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import event_constants                                             # noqa: E402
import mapper_sdk                                                  # noqa: E402
from chain import activity, builtins, rule_run                     # noqa: E402

KIND = "builtin:s246_probe"
RULE = {"name": "s246_rule", "target_table": "s246_target", "mapper": KIND}

#: ⚠️ THE KNOBS TRAVEL ON THE RULE, NOT ON THE CALL. The seat hands a self-writing kind
#: `(db, rule, row_ids=, done=)` and nothing else - 판정 498 put that convention out of
#: scope - so a probe that needed extra kwargs would be asking this file to test a signature
#: the product does not use.
WRITTEN = "s246_written"
BOOM = "s246_boom"
#: 🔴 [판정 525] THE SENTENCE THE KIND ITSELF GIVES. A registered kind is product code
#: and knows why it wrote nothing; the seat no longer supplies a default, so this knob is
#: how the probe behaves like `join_into` and `auto_confirm` now do.
REFUSAL = "s246_refusal"


def _rule(**knobs):
    out = dict(RULE)
    out.update(knobs)
    return out


@pytest.fixture(autouse=True)
def _clean_registry():
    """⚠️ THE REGISTRY IS A PROCESS SINGLETON, so a case that left an entry would decide
    the next one - and 「still running」 is exactly the false state under test."""
    activity.registry.clear()
    yield
    activity.registry.clear()


@pytest.fixture(name="kind")
def fixture_kind(monkeypatch):
    """A `builtin:` kind whose body reports what it saw, so 「during」 can be asserted."""
    seen = {"snapshot": None}

    def _run(db, rule, **kwargs):
        seen["snapshot"] = activity.registry.snapshot()
        if rule.get(BOOM):
            raise RuntimeError("the kind threw")
        if WRITTEN in rule:
            return {"written": rule[WRITTEN], "refusal": rule.get(REFUSAL)}
        return None

    monkeypatch.setitem(builtins.BUILTIN_KINDS, KIND, _run)
    # ⚠️ [판정 509] BOTH TABLES. `register_builtin` writes them together; faking a kind
    #    by hand has to say how it is called, or the seat refuses it by name.
    monkeypatch.setitem(builtins.BUILTIN_HANDS, KIND, builtins.HANDS_ROW_IDS)
    monkeypatch.setitem(builtins.BUILTIN_LABELS, KIND, "decide")
    builtins.SELF_WRITING_KINDS.add(KIND)
    yield seen
    builtins.SELF_WRITING_KINDS.discard(KIND)


# ---------------------------------------------------------------------------
# 🔴 ⓐ — the entry exists WHILE it runs, which is the whole question
# ---------------------------------------------------------------------------

def test_a_builtin_rule_that_is_running_is_in_the_running_list(kind):
    """🔴 THE GATE OF THIS ROUND. Asserted from INSIDE the kind, because 「it was in the
    list afterwards」 is a different and useless claim - the view answers 「what is in one
    right now」 and an entry that only exists after the run is an entry nobody can see."""
    rule_run.run_rule(None, _rule(**{WRITTEN: 3}), row_ids=[1, 2, 3])

    assert len(kind["snapshot"]) == 1
    entry = dict(kind["snapshot"][0])
    # ⚠️ The elapsed time is not pinned - it is a clock, and a fixture that asserted `0.0`
    # would go red on a slow machine for a reason that has nothing to do with the subject.
    assert entry.pop("running_seconds") >= 0
    assert entry == {"rule": "s246_rule", "mapper": KIND,
                     "target_table": "s246_target", "rows_in": 3}


def test_the_entry_names_the_kind_so_a_reader_can_tell_them_apart(kind):
    """⚠️ THE `mapper` CELL CARRIES `builtin:`, which is what the operator needs: a file
    mapper's entry says a module and a function, and 「which of these is this」 has to be
    readable off the same cell rather than inferred from the name.

    🔴 [판정 498] AND THE SEAT IS WHERE THAT CELL IS FILLED IN. It is `Resolved.who` - the
    one name the seat resolved - so the two spellings cannot drift into different columns."""
    rule_run.run_rule(None, _rule(**{WRITTEN: 1}), row_ids=[1])

    assert kind["snapshot"][0]["mapper"].startswith("builtin:")


def test_the_entry_is_gone_when_the_run_ends(kind):
    rule_run.run_rule(None, _rule(**{WRITTEN: 1}), row_ids=[1])

    assert activity.registry.snapshot() == []


def test_a_kind_that_throws_leaves_no_entry_behind(kind):
    """🔴 IN `finally`. An entry left behind sits in the view forever saying a rule is
    still running, and a stuck-looking chain is the symptom this registry exists to stop
    inventing."""
    with pytest.raises(RuntimeError):
        rule_run.run_rule(None, _rule(**{BOOM: True}), row_ids=[1])

    assert activity.registry.snapshot() == []


# ---------------------------------------------------------------------------
# 🔴 ⓑ — and the outcome stops saying 「never evaluated」 forever
# ---------------------------------------------------------------------------

def test_a_builtin_that_wrote_rows_is_recorded_as_having_changed_something(kind):
    activity.registry.seed_rules(["s246_rule"])

    rule_run.run_rule(None, _rule(**{WRITTEN: 2}), row_ids=[1, 2])

    assert (activity.registry.outcomes()["s246_rule"]["outcome"]
            == event_constants.RULE_OUTCOME_RAN_CHANGED)


def test_a_builtin_that_wrote_nothing_says_so_in_its_own_words(kind):
    """🔴 [판정 525] THIS TEST PINNED THE OPPOSITE OF ITS OWN NAME. It asserted
    「the rule wrote no rows」 - a DEFAULT the seat handed to every kind, and a restatement of
    `rows_out=0` the operator could already see. 509 had settled that shape the same morning:
    a default is an absence that looks like an answer. So the words come from the KIND now,
    and when the kind says nothing the cell is empty rather than filled by the seat.
    """
    rule_run.run_rule(
        None, _rule(**{WRITTEN: 0, REFUSAL: "확정을 기다리는 행이 없습니다"}), row_ids=[1])

    entry = activity.registry.outcomes()["s246_rule"]
    assert entry["outcome"] == event_constants.RULE_OUTCOME_RAN_UNCHANGED
    assert entry["reason"] == "확정을 기다리는 행이 없습니다", (
        "the kind's own sentence did not reach the queue cell an operator reads")


def test_a_kind_that_gives_no_reason_leaves_the_cell_empty(kind):
    """⚠️ THE CONTROL FOR THE ABOVE. Without it the test above would also pass while the
    seat invented a sentence for every kind - which is the state 525 removed."""
    rule_run.run_rule(None, _rule(**{WRITTEN: 0}), row_ids=[1])

    entry = activity.registry.outcomes()["s246_rule"]
    assert entry["outcome"] == event_constants.RULE_OUTCOME_RAN_UNCHANGED
    assert entry["reason"] is None, (
        "a reason nobody gave was written down as if somebody had: %r" % entry["reason"])


def test_a_kind_that_threw_is_recorded_as_failed_with_the_reason(kind):
    with pytest.raises(RuntimeError):
        rule_run.run_rule(None, _rule(**{BOOM: True}), row_ids=[1])

    entry = activity.registry.outcomes()["s246_rule"]
    assert entry["outcome"] == event_constants.RULE_OUTCOME_FAILED
    assert "the kind threw" in entry["reason"]


def test_a_kind_that_reports_no_count_leaves_the_outcome_alone(kind):
    """🔴 「안 셌다」 AND 「0 이었다」 ARE DIFFERENT FACTS. A kind that returns no `written`
    has not said it changed nothing - and recording `ran:unchanged` for it would be this
    registry inventing the very answer it exists to stop inventing."""
    activity.registry.seed_rules(["s246_rule"])

    rule_run.run_rule(None, _rule(), row_ids=[1])

    assert (activity.registry.outcomes()["s246_rule"]["outcome"]
            == event_constants.RULE_OUTCOME_NEVER_EVALUATED)


# ---------------------------------------------------------------------------
# ⚠️ ⓒ — the ways a rule names its code, and the one that is not a run
# ---------------------------------------------------------------------------

def test_a_name_nothing_implements_is_refused_without_ever_being_registered(kind):
    """⚠️ A NAME NOTHING IMPLEMENTS NEVER RAN. An entry for it - even for the length of one
    raise - would be a false sentence about a rule the seat is in the middle of refusing, and
    `failed` is an outcome for a rule that RAN and threw.

    🔴 [판정 498] AND IT IS REFUSED BY NAME FOR BOTH SPELLINGS NOW. The builtin arm always
    said which kind; the file-mapper arm let `importlib` throw, so an operator who mistyped a
    module got an ImportError stack instead of a sentence naming their rule."""
    unknown = _rule(mapper="builtin:nothing_implements_this")

    with pytest.raises(rule_run.UnresolvableRule) as raised:
        rule_run.run_rule(None, unknown, row_ids=[1])

    assert "s246_rule" in str(raised.value)
    assert "builtin:nothing_implements_this" in str(raised.value)
    assert activity.registry.snapshot() == []
    assert activity.registry.outcomes() == {}


def test_both_ways_of_naming_code_go_through_the_one_registration(kind, monkeypatch):
    """🔴 ONE AUTHOR, AND THAT IS THE POINT OF THE ROUND. Two spellings of 「register this
    run」 is 「같은 기능에 두 경로」, and the way it failed here is the quiet way: the door
    that had it kept working and the door that did not was invisible.

    ⚰️ THIS USED TO READ THE TWO DOORS' SOURCE with `inspect.getsource` and assert the string
    `activity.running(` appeared in each. That scored 「the words are in both bodies」, which
    is a text claim about a property that is now structural - there is one body. It scores
    the BEHAVIOUR instead: two rules that name their code in different ways, one registration
    each, read off the same registry.
    """
    seen = {}

    def _file_mapper(db, payload):
        seen["snapshot"] = activity.registry.snapshot()
        return {"updates": []}

    monkeypatch.setitem(mapper_sdk.MAPPER_REGISTRY, "s246_registered", _file_mapper)
    named_rule = {"name": "s246_mapper_rule", "target_table": "s246_target",
                  "mapper": "s246_registered"}

    rule_run.run_rule(None, _rule(**{WRITTEN: 1}), row_ids=[1])
    rule_run.run_rule(None, named_rule, payloads=[{"row_id": 1}])

    for entry, who in ((kind["snapshot"], KIND), (seen["snapshot"], "s246_registered")):
        assert len(entry) == 1, who
        assert entry[0]["rule"] and entry[0]["mapper"] == who
    assert activity.registry.snapshot() == []


def test_auto_confirm_reports_its_row_count_under_the_name_the_others_use(monkeypatch):
    """🔴 `written` IS WHAT A `builtin:` KIND CALLS ITS ROW COUNT, and this one did not say
    it. `join_into.run` and `materialize_rows` both answer under that name; auto-confirm
    answered `confirmed` only - so the follow-up line S-249 added printed `written=None`
    for it, and the registration here would have had nothing to read and would have left
    the outcome at 「아직 평가 안 됨」 no matter how many rows it confirmed."""
    import enrichment.candidates

    class _Collector:
        active = True

        def __init__(self, *_a, **_k):
            pass

        def collect_rows(self, *_a):
            pass

        def flush(self, *_a):
            return {"confirmed": 4, "refused": {"key": 1}}

    monkeypatch.setattr(enrichment.candidates, "AutoConfirmCollector", _Collector)

    result = builtins._run_auto_confirm(None, {"name": "ac"}, row_ids=[1, 2, 3, 4],
                                        done={"table": "t"})

    assert result["written"] == result["confirmed"] == 4
    assert result["refused"] == 1


def test_the_rows_in_count_is_what_the_seat_was_handed_either_way(kind, monkeypatch):
    """⚠️ THE QUEUE VIEW PUTS THESE NUMBERS SIDE BY SIDE, so they have to be counted the same
    way or the column means two things.

    ⚰️ THIS USED TO SCORE `builtins._rows_handed`, which read `row_ids` OR `key_values` off
    the door's kwargs. 🔴 MEASURED WHILE RETARGETING IT: nothing in the product passes
    `key_values` to a rule run - at HEAD either, so this is not something 498 broke. The
    `key_values` arm of `_run_join` (and the cell `_rows_handed` read for it) answered a call
    shape no caller makes. Reported rather than repaired: deleting a reachable-looking arm is
    its own round.
    """
    seen = {}

    def _file_mapper(db, payload):
        seen["snapshot"] = activity.registry.snapshot()
        return {"updates": []}

    monkeypatch.setitem(mapper_sdk.MAPPER_REGISTRY, "s246_registered", _file_mapper)

    rule_run.run_rule(None, _rule(**{WRITTEN: 0}), row_ids=[1, 2, 3])
    rule_run.run_rule(None,
                      {"name": "s246_mapper_rule", "target_table": "s246_target",
                       "mapper": "s246_registered", "is_batch": True},
                      payloads=[{"row_id": 1}, {"row_id": 2}])

    assert kind["snapshot"][0]["rows_in"] == 3
    assert seen["snapshot"][0]["rows_in"] == 2
