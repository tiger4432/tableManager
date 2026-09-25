# -*- coding: utf-8 -*-
"""총괄 d34247b3d ㉠ — one rule name had two answers. A CLI asked the operation's own lookup
before recording and refused; the admin publish only normalized the params, queued the run, and
the child failed on that same lookup. `validate` - which the publish, the count and a CLI's
`run_here` all pass - now asks it, so a name the operation cannot find leaves no row behind."""
import pytest

from admin import retroactive
from chain import enrich_declarations, replay
from database import models
from tests.test_a_declared_join_can_be_backfilled_like_any_rule import _rules
from tests.test_retroactive_admin import RULE_MIXED, retro_env  # noqa: F401

RULE_OPS = ["chain_replay", "enrichment_backfill", "enrichment_confirm"]


def _recorded(db):
    return (db.query(models.RetroactiveRun).count(),
            db.query(models.DatabaseOutbox).filter(
                models.DatabaseOutbox.event_type == retroactive.RUN_EVENT_TYPE).count())


@pytest.fixture(name="no_enrich_rules")
def fixture_no_enrich_rules(monkeypatch):
    """No enrich declaration stands - the box's own rules file is never read."""
    monkeypatch.setattr(enrich_declarations, "declarations", lambda *a, **k: [])
    monkeypatch.setattr(enrich_declarations, "find", lambda *a, **k: None)


def test_the_rule_taking_operations_are_the_three_judged():
    """Canary: the parametrized cells below are every operation that takes a rule."""
    takes_rule = sorted(op for op, spec in retroactive.OPERATIONS.items()
                        if any(p["name"] == "rule" for p in spec["params"]))
    assert takes_rule == sorted(RULE_OPS)
    assert all(retroactive.OPERATIONS[op]["judge"] is not None for op in RULE_OPS)


@pytest.mark.parametrize("op", RULE_OPS)
def test_the_publish_the_count_and_a_cli_give_one_refusal_and_record_nothing(
        retro_env, no_enrich_rules, op):
    answers = []
    for ask in (lambda: retroactive.publish(retro_env, op, {"rule": "no_such_rule"}),
                lambda: retroactive.count(retro_env, op, {"rule": "no_such_rule"}),
                lambda: retroactive.run_here(op, {"rule": "no_such_rule"},
                                             log=lambda *_: None)):
        with pytest.raises(retroactive.RetroactiveRefused) as refused:
            ask()
        answers.append(str(refused.value))

    assert len(set(answers)) == 1, answers
    assert "'no_such_rule'" in answers[0], answers[0]
    assert _recorded(retro_env) == (0, 0), "a refused name must leave no run and no event"


def test_a_rule_it_can_find_is_still_queued(retro_env):
    """The control: the judgment refuses what the run would refuse, nothing more."""
    out = retroactive.publish(retro_env, "chain_replay", {"rule": RULE_MIXED["name"]})

    assert out["status"] == "queued"
    assert _recorded(retro_env)[0] == 1


def test_picked_rows_still_make_a_companion_a_legal_subject(monkeypatch):
    """S-270: the rows travel into the judgment - without them the grid's replay of a join's
    second half would be refused at the door it used to pass."""
    rules = _rules()
    monkeypatch.setattr(replay, "load_rules", lambda: rules)
    companion = rules[1]["name"]

    assert retroactive.validate(
        "chain_replay", {"rule": companion, "row_ids": "r1"})["row_ids"] == ["r1"]
    with pytest.raises(retroactive.RetroactiveRefused) as refused:
        retroactive.validate("chain_replay", {"rule": companion})
    assert "second half of declaration" in str(refused.value)


def test_force_disabled_still_reaches_the_judgment(monkeypatch):
    """The CLI's `--force-disabled` travels too - a disabled rule the operator forced is not
    refused as disabled."""
    monkeypatch.setattr(enrich_declarations, "declarations", lambda *a, **k: [])
    monkeypatch.setattr(
        enrich_declarations, "find",
        lambda name, include_disabled=False, **k: (
            {"name": name, "enabled": False} if include_disabled else None))

    assert retroactive.validate(
        "enrichment_backfill", {"rule": "enr_off", "force_disabled": "true"}
    )["force_disabled"] is True
    with pytest.raises(retroactive.RetroactiveRefused) as refused:
        retroactive.validate("enrichment_backfill", {"rule": "enr_off"})
    assert "is disabled" in str(refused.value)
