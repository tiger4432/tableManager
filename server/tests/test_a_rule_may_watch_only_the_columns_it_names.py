# -*- coding: utf-8 -*-
"""규칙이 «컬럼까지» 좁혀 깨어난다 (S-140, 소유자 09-10 21:37 「트리거를 컬럼까지 세분화」).

🔴 UNTIL NOW A RULE WOKE ON THE TABLE. Every rule declared on one trigger table ran on
every write to it, in declaration order, because the outbox payload carried `row_ids` and
never said WHICH columns moved.

⛔ NAMES, NEVER VALUES. The payload gains `columns: [...]` - deduped and sorted - because
the question a rule asks is 「did MY column change」, not 「to what」. A value there would
put user data in the outbox.

⚠️ ABSENCE IS 「모른다」 AND MUST RUN. An event staged before this key existed, and every
non-collapsed per-row event, carries no `columns`. Reading that as an empty set would stop
every column-scoped rule on exactly the events nobody re-staged - the class where five
different zeros render identically.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import chain_ingestion_worker as worker                              # noqa: E402


class _Event:
    def __init__(self, payload):
        self.payload = payload
        self.event_type = "EDIT"
        self.table_name = "t"


def _rule(**kw):
    base = {"name": "r", "trigger_table": "t", "target_table": "u"}
    base.update(kw)
    return base


# ── ② the intersection ───────────────────────────────────────────────────────

def test_a_rule_that_names_no_columns_is_table_scoped_as_before():
    assert worker.rule_watches_changed_columns(_rule(), _Event({"columns": ["a"]}))


def test_a_rule_runs_when_one_of_its_columns_changed():
    rule = _rule(trigger_columns=["a", "b"])

    assert worker.rule_watches_changed_columns(rule, _Event({"columns": ["a"]}))


def test_a_rule_does_not_run_when_none_of_its_columns_changed():
    rule = _rule(trigger_columns=["b"])

    assert not worker.rule_watches_changed_columns(rule, _Event({"columns": ["a"]}))


# ── ③ absence means unknown, and unknown runs ────────────────────────────────

def test_an_event_with_no_columns_key_runs_every_rule():
    """⛔ THE TRAP THIS AVOIDS. Old events and per-row events carry no key at all."""
    rule = _rule(trigger_columns=["b"])

    assert worker.rule_watches_changed_columns(rule, _Event({"row_ids": ["x"]}))
    assert worker.rule_watches_changed_columns(rule, _Event({}))


def test_an_explicitly_empty_list_is_still_not_a_reason_to_run():
    """⚠️ THE OTHER HALF: the writer never STAMPS an empty list - it omits the key - so an
    empty list can only mean 「this flush set nothing」, which no rule watches."""
    rule = _rule(trigger_columns=["b"])

    assert not worker.rule_watches_changed_columns(rule, _Event({"columns": []}))


# ── ① the writer stamps names only, and omits rather than empties ────────────

def test_the_payload_carries_sorted_names_and_omits_the_key_when_empty():
    import inspect

    from database import database as db_module

    body = inspect.getsource(db_module.stage_collapsed_event)

    assert '**({"columns": sorted(columns)} if columns else {})' in body, body[-800:]


def test_create_and_edit_compute_changed_columns_the_same_way():
    """🔴 ONE SPELLING. Two ways to answer 「which columns did this flush set」 is how a
    CREATE and an EDIT come to disagree about the same row."""
    import inspect

    from database import database as db_module

    body = inspect.getsource(db_module)

    assert "def _changed_columns(obj):" in body
    assert '_emit("EDIT", obj, dirty_cols)' in body
    assert "names = columns if columns is not None else _changed_columns(obj)" in body


# ── ④ a name the table does not have is named at load ────────────────────────

def test_an_unknown_trigger_column_is_named_and_the_rule_stays_table_scoped(monkeypatch, caplog):
    """🔴 OTHERWISE THE RULE STANDS AND NEVER FIRES - enabled, looking live, never woken."""
    import logging

    from database import crud

    monkeypatch.setitem(crud.TABLE_CONFIG, "t", {"column_types": {"a": "string"}})

    with caplog.at_level(logging.ERROR):
        worker._report_unwatchable_trigger_columns(
            [_rule(trigger_columns=["a", "typo_here"])])

    messages = " ".join(r.getMessage() for r in caplog.records)
    assert "typo_here" in messages and "'a'" not in messages.split("typo_here")[1]


def test_a_catalogue_it_cannot_see_is_not_reported_as_missing(monkeypatch, caplog):
    """⚠️ 「모른다」 와 「없다」 는 다르다 - an unreadable table must not produce a refusal
    about names that may be perfectly good."""
    import logging

    from database import crud

    monkeypatch.setattr(crud, "TABLE_CONFIG", {})

    with caplog.at_level(logging.ERROR):
        worker._report_unwatchable_trigger_columns([_rule(trigger_columns=["a"])])

    assert not [r for r in caplog.records if "trigger_columns" in r.getMessage()]


def test_the_load_path_calls_it():
    """착지는 배선이 아니다."""
    import inspect

    assert "_report_unwatchable_trigger_columns(rules)" in inspect.getsource(
        worker.load_chain_rules)
