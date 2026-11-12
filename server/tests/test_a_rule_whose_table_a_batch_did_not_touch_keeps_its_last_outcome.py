# -*- coding: utf-8 -*-
"""Lead 11-10 D1: every batch wrote every rule's last outcome - a rule whose table the batch never touched read
«not triggered», no reason, after any unrelated write. Only a rule whose table was touched (or that is switched off)
records; a touched rule none of whose wake columns changed says so."""
import event_constants as ec
from chain import activity
from chain import ingestion_worker as worker
from test_a_rule_says_why_it_did_nothing import _Ev, _rule


def test_only_a_rule_whose_table_was_touched_records_and_the_columns_reason_is_kept(monkeypatch):
    reg = activity.ChainActivityRegistry()
    monkeypatch.setattr(activity, "registry", reg)
    reg.record_outcome("on_b", ec.RULE_OUTCOME_RAN_CHANGED)

    worker._record_pre_run_outcomes([
        _rule("on_b", "b"),
        _rule("on_a_cols", "a", trigger_columns=["y"]),
        _rule("on_a_off", "a", enabled=False),
    ], [_Ev("a", event_type="EDIT", payload='{"columns": ["x"]}')])
    out = reg.outcomes()

    assert out["on_b"]["outcome"] == ec.RULE_OUTCOME_RAN_CHANGED, "an untouched rule's last outcome was overwritten"
    assert (out["on_a_cols"]["outcome"], out["on_a_cols"]["reason"]) == (
        ec.RULE_OUTCOME_SKIPPED_NOT_TRIGGERED, worker.FIRE_REFUSED_COLUMNS)
    assert out["on_a_off"]["outcome"] == ec.RULE_OUTCOME_SKIPPED_DISABLED
