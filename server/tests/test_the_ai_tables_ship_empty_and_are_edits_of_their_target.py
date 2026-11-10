# -*- coding: utf-8 -*-
"""Lead 11-08 (owner «운영에서 받으면 바로 셋업되게» · «메모리 표도»): the AI's four tables ship in server/declarations/,
empty, group AI (owner 11-10 «ai 그룹으로 지어») - an action, an action kind, a judge's example, a memory row.

  tables   sys_ai_actions · sys_ai_action_kinds · sys_ai_judge_tests  (edit_by target_table) · sys_ai_memory
  people   kim (on the target's edit.allow) · lee (not on it) · an administrator
  a row    its target_table filled -> judged on that table · blank -> on the shipped table's own cell, which allows no
           name: an administrator only (sign-in off: anyone)
"""
import pytest

import shipped
from admin import access, sso
from chain import ask_rule
from database import crud

EDIT_BY = ("sys_ai_actions", "sys_ai_action_kinds", "sys_ai_judge_tests")
MEMORY = "sys_ai_memory"
TARGET = "mail_raw"


@pytest.fixture
def signed_in(monkeypatch):
    admins = {"root"}
    monkeypatch.setattr(sso, "enabled", lambda: True)
    monkeypatch.setattr(sso, "is_admin", lambda user: user in admins)
    for name in EDIT_BY + (MEMORY,):
        monkeypatch.setitem(crud.TABLE_CONFIG, name, shipped.tables()[name])
    monkeypatch.setitem(crud.TABLE_CONFIG, TARGET, {"business_key": "k", "column_types": {"k": "string"},
                                                    "access": {"edit": {"allow": ["kim"]}}})


def test_the_four_ship_in_the_ai_group():
    tables = shipped.tables()
    assert "sys_templates" in tables, "CANARY: the shipped file is the one read"
    assert {name: tables[name].get("group") for name in EDIT_BY + (MEMORY,)} == dict.fromkeys(EDIT_BY + (MEMORY,), "AI")


@pytest.mark.parametrize("table", EDIT_BY)
def test_a_row_naming_its_target_is_edited_by_whoever_may_edit_that_table(signed_in, table):
    assert "target_table" in shipped.tables()[table]["column_types"], "CANARY: the row names its table"
    row = {"target_table": TARGET}
    assert [access.may(user, table, access.EDIT, row=row) for user in ("kim", "lee", "root")] == [True, False, True]


@pytest.mark.parametrize("blank", [None, ""])
@pytest.mark.parametrize("table", EDIT_BY)
def test_a_row_with_no_target_is_an_administrators_edit(signed_in, table, blank):
    row = {"target_table": blank}
    assert [access.may(user, table, access.EDIT, row=row) for user in ("kim", "lee", "root")] == [False, False, True]


def test_with_sign_in_off_anyone_edits_a_row_with_no_target(monkeypatch, signed_in):
    monkeypatch.setattr(sso, "enabled", lambda: False)
    assert access.may("lee", "sys_ai_actions", access.EDIT, row={"target_table": None})


def test_the_memory_table_holds_every_memory_role_and_the_samples_key():
    table = shipped.tables()[MEMORY]
    named = {role: {"key": "situation", "when": "at"}.get(role, role) for role in ask_rule.MEMORY_ROLES}
    assert len(named) == 8, "CANARY: the roles are read"
    assert set(named.values()) == set(table["column_types"])
    assert table["composite_key_source"] == [named["purpose"], named["key"], named["cell"]]
