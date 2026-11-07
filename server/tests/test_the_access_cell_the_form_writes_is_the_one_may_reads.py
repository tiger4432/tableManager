# -*- coding: utf-8 -*-
"""The table form's access cell (`table_cells`, C 11-07) is the shape `admin.access.may` reads - the same words, the
same depth: a value written in it moves the answer (an edit refused, one name on edit.allow, that edit let through)."""
from admin import access, sso
from database import crud
import table_cells

TABLE = "acc_form"


def _fields(node):
    return {field["key"]: field["node"] for field in node["fields"]}


def test_the_form_s_access_cell_is_what_may_reads(monkeypatch):
    shape = _fields(_fields(table_cells.skeleton()["root"])[access.ACCESS_KEY])
    assert set(shape) == {access.READ, access.EDIT, access.EDIT_BY_KEY}, shape
    assert all(set(_fields(shape[what])) == {"allow", "deny"} for what in (access.READ, access.EDIT)), shape
    monkeypatch.setattr(sso, "enabled", lambda: True)
    monkeypatch.setattr(sso, "is_admin", lambda user: False)
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, {"column_types": {"k": "string"}})
    assert (access.may("kim", TABLE, access.READ), access.may("kim", TABLE, access.EDIT)) == (True, False)
    # what the form writes: one name on access.edit.allow
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, {"column_types": {"k": "string"},
                                                   access.ACCESS_KEY: {access.EDIT: {"allow": ["kim"]}}})
    assert (access.may("kim", TABLE, access.EDIT), access.may("lee", TABLE, access.EDIT)) == (True, False)
