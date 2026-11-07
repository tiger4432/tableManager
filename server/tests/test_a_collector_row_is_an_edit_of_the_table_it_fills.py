# -*- coding: utf-8 -*-
"""Lead 11-07 (ㄱ1): the browser collector's four shipped tables - a template, its fields, a run, a run's missed items -
each row an edit of the table its target_table names, judged in `access.may`'s one seat (sys_looks' edit_by).

  tables   sys_templates · sys_template_fields · sys_collect_runs · sys_collect_misses
  people   kim (on the target's edit.allow) -> yes · lee (not on it) -> no
"""
import pytest

import shipped
from admin import access, sso
from database import crud

COLLECTOR = ("sys_templates", "sys_template_fields", "sys_collect_runs", "sys_collect_misses")
TARGET = "mail_raw"


@pytest.fixture
def signed_in(monkeypatch):
    monkeypatch.setattr(sso, "enabled", lambda: True)
    monkeypatch.setattr(sso, "is_admin", lambda user: False)
    for name in COLLECTOR:
        monkeypatch.setitem(crud.TABLE_CONFIG, name, shipped.tables()[name])
    monkeypatch.setitem(crud.TABLE_CONFIG, TARGET, {"business_key": "k", "column_types": {"k": "string"},
                                                    "access": {"edit": {"allow": ["kim"]}}})


@pytest.mark.parametrize("table", COLLECTOR)
def test_a_collector_row_is_edited_by_whoever_may_edit_its_target_table(signed_in, table):
    assert "target_table" in shipped.tables()[table]["column_types"], "CANARY: the row names its table"
    row = {"target_table": TARGET}
    assert [access.may(user, table, access.EDIT, row=row) for user in ("kim", "lee")] == [True, False]
