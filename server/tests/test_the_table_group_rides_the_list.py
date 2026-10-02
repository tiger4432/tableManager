# -*- coding: utf-8 -*-
"""Lead 685f236d7 (owner 10-02): the main grid's table dropdown groups by a `group` the operator
writes on a table in table_config. `/tables` hands it over beside the list, the way
`map_key_columns` (S-72) and `kinds` (S-187) ride: {table: group}, a table without one absent.
The list itself does not move - four client readers take it as it is."""
import os
import sys

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)


@pytest.fixture()
def client():
    os.environ.setdefault("TESTING", "1")
    from fastapi.testclient import TestClient

    import main

    return TestClient(main.app, raise_server_exceptions=False)


def test_a_written_group_rides_the_list_and_the_list_does_not_move(client, monkeypatch):
    from database import crud

    names = [n for n, e in crud.TABLE_CONFIG.items() if isinstance(e, dict)]
    if len(names) < 3:
        pytest.skip("this catalogue has fewer than three tables")
    before = client.get("/tables").json()
    grouped, spaces, unwritten = names[:3]
    monkeypatch.setitem(crud.TABLE_CONFIG, grouped, {**crud.TABLE_CONFIG[grouped], "group": " Process "})
    monkeypatch.setitem(crud.TABLE_CONFIG, spaces, {**crud.TABLE_CONFIG[spaces], "group": "   "})
    after = client.get("/tables").json()

    # the operator's word, folded like every other value (strip); a blank one is no group
    assert after["groups"] == {grouped: "Process"}, after["groups"]
    assert unwritten not in after["groups"] and spaces not in after["groups"]
    # 🔴 THE LIST IS UNTOUCHED - same names, same order - and so is every other key
    assert after["tables"] == before["tables"] == list(crud.TABLE_CONFIG.keys())
    assert {k: v for k, v in after.items() if k != "groups"} == \
           {k: v for k, v in before.items() if k != "groups"}
