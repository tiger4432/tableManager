# -*- coding: utf-8 -*-
"""Lead 11-08 (access QA ①): a row of an edit_by table (sys_looks: look_table) is judged on the table it names - after
the edit_by table's own cell: «deny always wins», and «never without read» (`admin.access`).

  doors    PUT data/updates · DELETE rows/<id> · POST rows/batch_delete
  cell     sys_looks' own access: none · read.deny kim · edit.deny kim · read.allow lee only
  person   kim, on the named table's edit.allow - refused by sys_looks' own cell, else let through; lee, not on it
  refusal  names the table and the cell that refused: a deny says remove the name there (an allow would not lift
           it), an allow list missed says add it - sys_looks for its own cell, the named table for lee
"""
import pytest

import shipped
from admin import access
from database import crud, models
from test_a_cell_looks_by_its_colour_rules_and_hand_paint import LOOKS, TABLE, grid  # noqa: F401 - the fixture

DOORS = ["updates", "delete", "batch_delete"]
#: sys_looks' own access cell -> kim's answer at every door, and the refusal's sentence
CELLS = {"none": ({}, 200, None),
         "read_deny": ({"read": {"deny": ["kim"]}}, 403, access.DENIED_BY % ("kim", "read", LOOKS)),
         "edit_deny": ({"edit": {"deny": ["kim"]}}, 403, access.DENIED_BY % ("kim", "edit", LOOKS)),
         "read_allow_other": ({"read": {"allow": ["lee"]}}, 403, access.DENIED % ("kim", "edit", LOOKS, "read"))}


@pytest.fixture
def signed(grid, monkeypatch):
    import main  # noqa: F401 - the app the client drives
    from admin import sso

    who = {"name": None}

    def admit(request):
        request.state.sso_user = who["name"]
    monkeypatch.setattr(sso, "enabled", lambda: True)
    monkeypatch.setattr(sso, "admit", admit)
    monkeypatch.setattr(sso, "is_admin", lambda user: user == "boss")
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, {**crud.TABLE_CONFIG[TABLE], "access": {"edit": {"allow": ["kim"]}}})
    return grid[0], who


def _own(monkeypatch, cell):
    shipped_cell = shipped.tables()[LOOKS]["access"]
    assert shipped_cell == {"edit_by": "look_table"}, "CANARY: sys_looks ships its edit_by"
    monkeypatch.setitem(crud.TABLE_CONFIG, LOOKS, {**shipped.tables()[LOOKS], "access": {**shipped_cell, **cell}})


def _row(client, who, db_session, key):
    who["name"] = "boss"
    answer = client.put("/tables/%s/data/updates" % LOOKS, json={"updates": [{"updates": {
        "look_table": TABLE, "look_axis": "rule", "look_key": key, "role": "accent"}, "updated_by": "probe"}]})
    assert answer.status_code == 200, answer.text
    looks = models.DYNAMIC_TABLES[LOOKS]
    db_session.expire_all()
    return db_session.query(looks.row_id).filter(looks.look_table == TABLE, looks.look_key == key).one()[0]


def _door(client, door, row_id, key):
    if door == "updates":
        return client.put("/tables/%s/data/updates" % LOOKS, json={"updates": [{"updates": {
            "look_table": TABLE, "look_axis": "rule", "look_key": key, "role": "muted"}, "updated_by": "web_client"}]})
    if door == "delete":
        return client.delete("/tables/%s/rows/%s" % (LOOKS, row_id))
    return client.post("/tables/%s/rows/batch_delete" % LOOKS, json={"row_ids": [row_id]})


@pytest.mark.parametrize("door", DOORS)
def test_an_edit_by_table_s_own_cell_refuses_before_the_table_it_names(signed, db_session, monkeypatch, door):
    client, who = signed
    got, said = {}, {}
    for name, (cell, _want, _said) in CELLS.items():
        key = "r-%s-%s" % (door, name)
        row_id = _row(client, who, db_session, key)
        _own(monkeypatch, cell)
        who["name"] = "kim"
        answer = _door(client, door, row_id, key)
        got[name] = answer.status_code
        said[name] = answer.json()["detail"] if answer.status_code == 403 else None
        _own(monkeypatch, {})
    assert got == {name: want for name, (_cell, want, _said) in CELLS.items()}, got
    assert said == {name: sentence for name, (_cell, _want, sentence) in CELLS.items()}, said


@pytest.mark.parametrize("door", DOORS)
def test_a_person_off_the_named_table_is_refused_by_that_table(signed, db_session, door):
    client, who = signed
    key = "r-lee-%s" % door
    row_id = _row(client, who, db_session, key)
    who["name"] = "lee"
    answer = _door(client, door, row_id, key)
    assert answer.status_code == 403, answer.text
    assert answer.json()["detail"] == access.DENIED % ("lee", "edit", TABLE, "edit"), answer.json()


@pytest.mark.parametrize("what", ["read", "edit"])
def test_a_deny_on_a_plain_table_says_remove_the_name_there(signed, monkeypatch, what):
    """Not edit_by only: any table's deny refuses with the deny's sentence - adding the name to allow would not lift it."""
    client, who = signed
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, {**crud.TABLE_CONFIG[TABLE], "access": {
        "read": {"deny": ["kim"] if what == "read" else []}, "edit": {"allow": ["kim"], "deny": ["kim"]}}})
    who["name"] = "kim"
    answer = (client.get("/tables/%s/data" % TABLE) if what == "read" else
              client.put("/tables/%s/data/updates" % TABLE, json={"updates": [{"updates": {
                  "lot": "L9", "itemid": "z"}, "updated_by": "web_client"}]}))
    assert answer.status_code == 403, answer.text
    assert answer.json()["detail"] == access.DENIED_BY % ("kim", what, TABLE), answer.json()
