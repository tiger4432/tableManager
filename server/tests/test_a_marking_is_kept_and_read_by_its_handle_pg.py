# -*- coding: utf-8 -*-
"""Lead 11-07 S-mark · S-rows (owner 11-06 Tables): a person's marking is kept on the server under a handle it makes -
`POST /markings` {table, column, values} -> {id, rev} - and the grid pages it by that handle
(`/tables/{t}/data?marking=` and its count), the values never in the URL. One row a marking, no audit, no outbox.

  people     kim · lee (acc_allow: kim reads, lee does not) · sign-in on
  cells      kept and paged · overwritten by its id (rev 2) · 60 KB of values in the body, the URL the handle only ·
             two people's markings apart · a table one may not read refused at both doors · no audit or outbox row ·
             the screen deletes it"""
import pytest
from sqlalchemy import text

from test_a_table_is_read_and_edited_by_the_names_it_lists import _write, grid  # noqa: F401

pytestmark = pytest.mark.pg


def _keys(client, table, marking, **params):
    answer = client.get("/tables/%s/data" % table, params={"marking": marking, **params})
    assert answer.status_code == 200, answer.text
    cells = [(row.get("data") or row)["k"] for row in answer.json()["data"]]
    return sorted(cell["value"] if isinstance(cell, dict) else cell for cell in cells), answer


def _count(client, table, marking):
    return client.get("/tables/%s/data/count" % table, params={"marking": marking}).json()


def _seed(client, who, table, keys):
    who["name"] = "boss"
    for k in keys:
        assert _write(client, table, k).status_code == 200


def test_a_marking_is_kept_and_the_grid_pages_it_by_its_handle(grid):
    client, who = grid
    _seed(client, who, "acc_open", ("k1", "k2", "k3"))
    who["name"] = "kim"
    kept = client.post("/markings", json={"table": "acc_open", "column": "k", "values": ["k1", "k3"]}).json()
    assert kept["rev"] == 1 and kept["id"]
    keys, answer = _keys(client, "acc_open", kept["id"])
    assert keys == ["k1", "k3"] and "k1" not in str(answer.url)
    assert _count(client, "acc_open", kept["id"]).get("total") == 2
    again = client.post("/markings", json={"id": kept["id"], "table": "acc_open", "column": "k", "values": ["k2"]})
    assert again.json() == {"id": kept["id"], "rev": 2}
    assert _keys(client, "acc_open", kept["id"])[0] == ["k2"]
    assert _keys(client, "acc_open", kept["id"], limit=1)[0] == ["k2"]


def test_sixty_kilobytes_of_values_ride_the_body_and_the_url_holds_the_handle(grid):
    client, who = grid
    _seed(client, who, "acc_open", ("k1",))
    who["name"] = "kim"
    values = ["k1"] + ["v%09d" % i for i in range(6000)]
    kept = client.post("/markings", json={"table": "acc_open", "column": "k", "values": values})
    assert kept.status_code == 200 and len(kept.request.content) > 56000
    keys, answer = _keys(client, "acc_open", kept.json()["id"])
    assert keys == ["k1"] and len(str(answer.url)) < 200


def test_two_people_s_markings_are_apart(grid):
    client, who = grid
    _seed(client, who, "acc_open", ("k1", "k2"))
    who["name"] = "kim"
    kims = client.post("/markings", json={"table": "acc_open", "column": "k", "values": ["k1"]}).json()["id"]
    who["name"] = "lee"
    lees = client.post("/markings", json={"table": "acc_open", "column": "k", "values": ["k2"]}).json()["id"]
    assert _keys(client, "acc_open", lees)[0] == ["k2"]
    assert client.get("/tables/acc_open/data", params={"marking": kims}).status_code == 404
    assert client.post("/markings", json={"id": kims, "table": "acc_open", "column": "k", "values": []}).status_code == 404
    who["name"] = "kim"
    assert _keys(client, "acc_open", kims)[0] == ["k1"]


def test_a_table_one_may_not_read_is_refused_at_both_doors(grid):
    client, who = grid
    _seed(client, who, "acc_allow", ("k1",))
    who["name"] = "lee"
    assert client.post("/markings", json={"table": "acc_allow", "column": "k", "values": ["k1"]}).status_code == 403
    who["name"] = "kim"
    kims = client.post("/markings", json={"table": "acc_allow", "column": "k", "values": ["k1"]}).json()["id"]
    assert _keys(client, "acc_allow", kims)[0] == ["k1"]
    assert client.get("/tables/acc_open/data", params={"marking": kims}).json()["detail"]["reason"] == (
        "marking_of_another_table")


def test_keeping_a_marking_writes_no_audit_and_no_outbox_row(grid, pg_engine):
    client, who = grid
    _seed(client, who, "acc_open", ("k1",))

    def journal():
        with pg_engine.connect() as conn:
            return [conn.execute(text("SELECT count(*) FROM %s" % name)).scalar()
                    for name in ("audit_logs", "database_outbox", "cell_sources")]

    before = journal()
    assert before[0] > 0, "the seed's write is journaled - the count reads the scratch tables"
    who["name"] = "kim"
    kept = client.post("/markings", json={"table": "acc_open", "column": "k", "values": ["k1"]}).json()
    client.post("/markings", json={"id": kept["id"], "table": "acc_open", "column": "k", "values": ["k1", "k2"]})
    assert journal() == before


def test_the_screen_deletes_a_marking(grid):
    client, who = grid
    _seed(client, who, "acc_open", ("k1",))
    who["name"] = "kim"
    kept = client.post("/markings", json={"table": "acc_open", "column": "k", "values": ["k1"]}).json()["id"]
    assert client.delete("/markings/%s" % kept).json() == {"id": kept, "deleted": True}
    assert client.get("/tables/acc_open/data", params={"marking": kept}).status_code == 404
