# -*- coding: utf-8 -*-
"""S-154 (판정 381). 체인이 묶는 단위를 «규칙이» 고를 수 있다 — 없으면 오늘 그대로.

🔴 THE GROUP WAS THE WRITER'S COMMIT, AND NOTHING COULD SAY OTHERWISE. `chain_rules.json`'s
44 top-level cells held no `group_by`, so what reached a mapper in one call was decided by
whatever the ingestion happened to commit together. A mapper that needed rows grouped by a
lot re-grouped them in its own body - and those bodies are gitignored, so the product could
not state its own groups.

🔴 THE AXIS WAS SPELLED TWICE. The batch drain and the undelivered sweep each wrote
`payload["transaction_id"] or f"single_{uuid}"` and each built its own dict. Adding a cell
without folding those two would have taught ONE of them about it - so the fold is in the
same commit, and this file scores both seats through one function.

⚠️ WITHIN ONE BATCH. Rows for one key arriving in a LATER batch form their own group;
「wait until they are all here」 needs a 「how long」 cell and is a different feature.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import chain_bindings                                                  # noqa: E402
from chain import ingestion_worker as worker                           # noqa: E402
from database import crud                                              # noqa: E402

TRIGGER = "s154_src"
BY_LOT = {"name": "by_lot", "trigger_table": TRIGGER, "target_table": "s154_out",
          "enabled": True, "group_by": ["lot"]}
BY_SLOT = {"name": "by_slot", "trigger_table": TRIGGER, "target_table": "s154_out",
           "enabled": True, "group_by": ["slot"]}
SAYS_NOTHING = {"name": "plain", "trigger_table": TRIGGER, "target_table": "s154_out",
                "enabled": True}


class FakeEvent:
    """Only what the grouping seat reads: a table, a uuid, and a payload."""

    def __init__(self, uuid, tx, cells=None, extra=None):
        self.event_uuid = uuid
        self.id = uuid
        self.table_name = TRIGGER
        self.event_type = "CREATE"
        payload = {"transaction_id": tx, "table_name": TRIGGER,
                   "data": {name: {"value": value} for name, value in (cells or {}).items()}}
        payload.update(extra or {})
        self.payload = payload
        self._parsed_payload = payload


# ---------------------------------------------------------------------------
# 🔴 gate ⓐ - declaring nothing changes nothing
# ---------------------------------------------------------------------------

def test_a_rule_that_declares_no_key_leaves_the_writers_transaction(monkeypatch):
    """⚠️ THE NO-REGRESSION, AND IT IS THE WHOLE OF WHAT MOST DEPLOYMENTS SEE."""
    events = [FakeEvent("u1", "txA", {"lot": "L1"}), FakeEvent("u2", "txA", {"lot": "L2"}),
              FakeEvent("u3", "txB", {"lot": "L1"})]

    order, groups = worker.group_events(events, [SAYS_NOTHING])

    assert order == ["txA", "txB"]
    assert [len(groups[key]) for key in order] == [2, 1]


def test_an_event_with_no_transaction_is_its_own_group():
    """The other half of today's answer: `single_<uuid>`, kept to the character."""
    event = FakeEvent("u9", None)

    assert worker.group_id(event, []) == "single_u9"


# ---------------------------------------------------------------------------
# 🔴 gate ⓑ - a declared key regroups across commits
# ---------------------------------------------------------------------------

def test_rows_with_the_same_key_from_two_commits_become_one_group():
    """🔴 THE POINT. Under today's answer these are two groups because two commits wrote
    them; the declaration is what makes them one call."""
    events = [FakeEvent("u1", "txA", {"lot": "L1"}), FakeEvent("u2", "txB", {"lot": "L1"}),
              FakeEvent("u3", "txB", {"lot": "L2"})]

    order, groups = worker.group_events(events, [BY_LOT])

    assert len(order) == 2
    assert [len(groups[key]) for key in order] == [2, 1]
    assert {e.event_uuid for e in groups[order[0]]} == {"u1", "u2"}


def test_the_groups_keep_first_appearance_order():
    """🔴 판정 381 ㈛. Re-keying moves rows between groups, so the order is STATED - a group
    stands where its first event stood, and work is never moved past work."""
    events = [FakeEvent("u1", "txA", {"lot": "L2"}), FakeEvent("u2", "txA", {"lot": "L1"}),
              FakeEvent("u3", "txB", {"lot": "L2"})]

    order, groups = worker.group_events(events, [BY_LOT])

    assert [e.event_uuid for e in groups[order[0]]] == ["u1", "u3"]
    assert [e.event_uuid for e in groups[order[1]]] == ["u2"]


def test_a_blank_and_an_absent_value_are_one_key():
    """⚠️ ONE FOLD FOR A KEY PART (S-181). `None`, `''` and `'  '` are the same key here
    because they are the same key everywhere else a key is composed."""
    events = [FakeEvent("u1", "txA", {"lot": None}), FakeEvent("u2", "txB", {"lot": ""}),
              FakeEvent("u3", "txC", {"lot": "   "})]

    order, groups = worker.group_events(events, [BY_LOT])

    assert len(order) == 1
    assert len(groups[order[0]]) == 3


def test_two_rules_asking_for_different_keys_get_the_finer_partition():
    """🔴 AN EVENT CAN BE IN EXACTLY ONE GROUP. Obeying one rule and not the other would make
    the answer depend on rule order, so the keys COMBINE - the partition both are true of.
    Same reading as 「가장 엄한 상한이 이긴다」 one axis over."""
    events = [FakeEvent("u1", "txA", {"lot": "L1", "slot": 1}),
              FakeEvent("u2", "txA", {"lot": "L1", "slot": 2}),
              FakeEvent("u3", "txA", {"lot": "L1", "slot": 1})]

    order, groups = worker.group_events(events, [BY_LOT, BY_SLOT])

    assert len(order) == 2
    assert {e.event_uuid for e in groups[order[0]]} == {"u1", "u3"}


def test_a_disabled_rules_key_is_not_used():
    """A rule that cannot run cannot decide what a group is."""
    events = [FakeEvent("u1", "txA", {"lot": "L1"}), FakeEvent("u2", "txB", {"lot": "L1"})]

    order, _groups = worker.group_events(events, [dict(BY_LOT, enabled=False)])

    assert order == ["txA", "txB"]


def test_a_rule_for_another_table_does_not_regroup_this_one():
    events = [FakeEvent("u1", "txA", {"lot": "L1"}), FakeEvent("u2", "txB", {"lot": "L1"})]

    order, _groups = worker.group_events(events, [dict(BY_LOT, trigger_table="elsewhere")])

    assert order == ["txA", "txB"]


# ---------------------------------------------------------------------------
# 🔴 gate ⓒ - what a key must NOT fold back together
# ---------------------------------------------------------------------------

def test_a_re_expanded_event_is_never_regrouped():
    """⛔ QUARANTINE MUST NOT COME UNDONE. `outbox_expand` splits a failed chunk into per-row
    events ON PURPOSE; a key that folded them back would rebuild the group that just failed,
    and nothing would say so. `root_transaction_id` is the mark that it was split."""
    split = [FakeEvent("u1", "txA#row#r1", {"lot": "L1"}, {"root_transaction_id": "txA"}),
             FakeEvent("u2", "txA#row#r2", {"lot": "L1"}, {"root_transaction_id": "txA"})]

    order, groups = worker.group_events(split, [BY_LOT])

    assert order == ["txA#row#r1", "txA#row#r2"]
    assert all(len(groups[key]) == 1 for key in order)


def test_a_collapsed_event_carries_no_values_so_it_keeps_its_transaction():
    """⛔ MEASURED, NOT ASSUMED: the collapsed stager writes `row_ids` and a count where the
    per-row stager writes `data`. There is nothing to key on without reading the rows back."""
    collapsed = FakeEvent("u1", "txA", {}, {"row_ids": ["r1", "r2"], "row_count": 2})

    assert worker.group_key(BY_LOT, collapsed.payload) is None
    assert worker.group_id(collapsed, [BY_LOT]) == "txA"


# ---------------------------------------------------------------------------
# 🔴 gate ⓓ - the cell is declared, and a name that matches nothing is refused
# ---------------------------------------------------------------------------

def test_the_cell_is_in_the_grammar_and_in_the_skeleton():
    assert chain_bindings.GROUP_BY_KEY == "group_by"
    assert chain_bindings.GROUP_BY_KEY in chain_bindings.RULE_ROUTING_OPTIONAL
    assert chain_bindings.GROUP_BY_KEY in chain_bindings.routing_keys()


def _refusals(rule, monkeypatch, columns=("lot", "slot")):
    monkeypatch.setitem(crud.TABLE_CONFIG, TRIGGER,
                        {"column_types": {name: "string" for name in columns}})
    return [issue.code for issue in chain_bindings.rule_refusals(
        rule, "rule", mapper_resolvable=lambda name: True)]


def test_a_group_key_naming_a_column_the_table_does_not_have_is_refused(monkeypatch):
    """🔴 A NAME THAT MATCHES NOTHING IS THE LOUDEST MISSPELLING THERE IS: every row keys on
    the same absent value, so the WHOLE TABLE arrives as one group."""
    rule = dict(BY_LOT, mapper="m", group_by=["lto"])

    assert "unknown_group_column" in _refusals(rule, monkeypatch)


def test_a_group_key_of_declared_columns_is_accepted(monkeypatch):
    """⚠️ THE CONTROL. Without it the branch could be refusing every declaration."""
    rule = dict(BY_LOT, mapper="m", group_by=["lot", "slot"])

    assert _refusals(rule, monkeypatch) == []


@pytest.mark.parametrize("written", ["lot", 7, [""], ["lot", 3], {}])
def test_a_group_key_that_is_not_a_list_of_names_is_refused(monkeypatch, written):
    """A single string is the likely typo and the worst one: it would be read character by
    character if anything downstream iterated it."""
    rule = dict(BY_LOT, mapper="m", group_by=written)

    assert "bad_group_by" in _refusals(rule, monkeypatch)


def test_a_table_the_catalogue_does_not_declare_is_not_judged(monkeypatch):
    """⚠️ `declared_columns` returning None means 「the catalogue says nothing」, and a table it
    does not declare has to keep working rather than be refused."""
    monkeypatch.delitem(crud.TABLE_CONFIG, TRIGGER, raising=False)
    rule = dict(BY_LOT, mapper="m", group_by=["anything_at_all"])

    codes = [issue.code for issue in chain_bindings.rule_refusals(
        rule, "rule", mapper_resolvable=lambda name: True)]

    assert "unknown_group_column" not in codes
