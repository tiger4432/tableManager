# -*- coding: utf-8 -*-
"""Lead 10-28 (C found it on the box): a rule the chain switched off after failures in a row (control.rules_off,
owner 10-24) stayed off across a restart while the load's set(N) line said it on, no batch line said it skipped,
and the queue outcome's reason said «rule declares enabled: false» of a rule its file declares on. One judgement
(rules_off / with_rules_off), one sentence (control.switched_off_line) - the set line marks it OFF, the outcome's
reason is the rules list's sentence, and a batch it would have woken says SKIPPED once per switch-off, folded as
failures are."""
import json
import logging

import event_constants
from chain import control as chain_control
from chain import ingestion_worker as worker
from test_the_rule_list_says_what_runs_and_what_is_only_written import DST, SRC, fixture_declared  # noqa: F401

RULE = {"name": "r_off", "enabled": True, "is_batch": True, "trigger_table": SRC, "target_table": DST,
        "trigger_columns": ["job"], "mapper_module": "m", "mapper_function": "f"}
OFF = {"at": "2026-10-28T19:02:11", "failures": 10, "cause": "KeyError: 'job'"}


def _off(monkeypatch, record):
    monkeypatch.setattr(chain_control, "rules_off", lambda: {"r_off": record})


def test_the_set_line_says_off(declared, tmp_path, monkeypatch, caplog):
    chain_file = tmp_path / "rules.json"
    chain_file.write_text(json.dumps({"rules": [RULE]}), encoding="utf-8")
    monkeypatch.setattr(worker, "RULES_PATH", str(chain_file))
    _off(monkeypatch, OFF)
    with caplog.at_level(logging.INFO):
        worker.load_chain_rules()
    said = [r.getMessage() for r in caplog.records if r.getMessage().startswith("[ChainRules] set(")]
    assert said and "r_off[" in said[-1] and said[-1].endswith(" OFF"), said


def test_the_outcome_reason_is_the_lists_sentence_and_a_batch_says_skipped_once(monkeypatch, caplog):
    _off(monkeypatch, OFF)
    monkeypatch.setattr(worker, "wakes", lambda rule, event: True)
    monkeypatch.setattr(worker, "fire_refusal", lambda rule, event: "switched off")
    monkeypatch.setattr(worker, "_FAILURE_SEEN", {})
    rules = chain_control.with_rules_off([RULE])
    outcome, reason = worker._rule_outcome_before_running(rules[0], ["e"])
    assert (outcome, reason) == (event_constants.RULE_OUTCOME_SKIPPED_DISABLED, chain_control.switched_off_line(OFF))
    assert reason == "Switched off after 10 failures in a row since 2026-10-28T19:02:11 · KeyError: 'job'"
    with caplog.at_level(logging.ERROR, logger="Chain"):
        for _batch in range(2):
            worker._record_pre_run_outcomes(rules, ["e"])
    skipped = [r.getMessage() for r in caplog.records if " SKIPPED" in r.getMessage()]
    assert skipped == ["[Chain] rule=r_off target=%s SKIPPED: %s" % (DST, reason)], skipped

    caplog.clear()
    again = dict(OFF, at="2026-10-28T19:40:00")    # switched back on, off again the same hour: a new line
    _off(monkeypatch, again)
    with caplog.at_level(logging.ERROR, logger="Chain"):
        worker._record_pre_run_outcomes(chain_control.with_rules_off([RULE]), ["e"])
    assert [r.getMessage() for r in caplog.records if " SKIPPED" in r.getMessage()] == [
        "[Chain] rule=r_off target=%s SKIPPED: %s" % (DST, chain_control.switched_off_line(again))]
