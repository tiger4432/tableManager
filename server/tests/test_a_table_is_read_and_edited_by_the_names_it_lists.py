# -*- coding: utf-8 -*-
"""Owner 11-06: who may read or edit a table - one seat (`admin.access.may`), every door asks it.

  states     no access cell · read/edit allow · read deny · read allow + deny (deny wins) · edit_by (sys_looks' shape)
  people     kim · lee · boss (an admin: every table, always) · sign-in off (today's answer: yes)
  doors      GET data (read) · PUT data/updates (edit) · GET /tables (absent when unreadable) · the audit lists ·
             a socket broadcast · a walk's leave_out
  the table  every cell asserted, the empty ones too - a missing cell would read as a pass
"""
import json

import pytest
from sqlalchemy import MetaData, text
from sqlalchemy.orm import sessionmaker

from database import crud, models

pytestmark = pytest.mark.pg
COLUMNS = {"k": "string", "v": "string"}
STATES = {
    "acc_open": {},
    "acc_allow": {"read": {"allow": ["kim"]}, "edit": {"allow": ["kim"]}},
    "acc_deny": {"read": {"deny": ["kim"]}, "edit": {"allow": ["kim", "lee"]}},
    "acc_both": {"read": {"allow": ["kim", "lee"], "deny": ["kim"]}, "edit": {"allow": ["lee"]}},
}
LOOKS = "acc_looks"
TABLES = {**{name: {"business_key": "k", "composite_key_source": ["k"], "column_types": COLUMNS,
                    **({"access": cell} if cell else {})} for name, cell in STATES.items()},
          LOOKS: {"business_key": "k", "composite_key_source": ["k"],
                  "column_types": {"k": "string", "look_table": "string", "v": "string"},
                  "access": {"edit_by": "look_table"}}}
PEOPLE = ("kim", "lee", "boss")
#: (table, person) -> (read, edit), as the owner's rule says
WANT = {
    ("acc_open", "kim"): (True, False), ("acc_open", "lee"): (True, False), ("acc_open", "boss"): (True, True),
    ("acc_allow", "kim"): (True, True), ("acc_allow", "lee"): (False, False), ("acc_allow", "boss"): (True, True),
    ("acc_deny", "kim"): (False, False), ("acc_deny", "lee"): (True, True), ("acc_deny", "boss"): (True, True),
    ("acc_both", "kim"): (False, False), ("acc_both", "lee"): (True, True), ("acc_both", "boss"): (True, True),
}


@pytest.fixture
def grid(pg_engine, monkeypatch):
    from fastapi.testclient import TestClient
    import main
    from admin import sso
    from conftest import PG_TEST_SCHEMA
    from database.database import get_db

    models.init_dynamic_models(TABLES)
    for name, entry in TABLES.items():
        monkeypatch.setitem(crud.TABLE_CONFIG, name, entry)
    scratch = MetaData(schema=PG_TEST_SCHEMA)
    for name in TABLES:
        models.DYNAMIC_TABLES[name].__table__.to_metadata(scratch, schema=None)
    scratch.create_all(pg_engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)()

    async def broadcast(message):
        return None
    monkeypatch.setattr(main.manager, "broadcast", broadcast)
    who = {"name": None, "on": True}

    def admit(request):
        request.state.sso_user = who["name"]
    monkeypatch.setattr(sso, "enabled", lambda: who["on"])
    monkeypatch.setattr(sso, "admit", admit)
    monkeypatch.setattr(sso, "is_admin", lambda user: user == "boss")
    main.app.dependency_overrides[get_db] = lambda: session
    try:
        with TestClient(main.app) as client:
            yield client, who
    finally:
        main.app.dependency_overrides.pop(get_db, None)
        session.close()
        with pg_engine.begin() as conn:
            for name in TABLES:
                conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, name)))
            for table in ("cell_sources", "cell_overwrites", "audit_logs", "database_outbox"):
                conn.execute(text('DELETE FROM "%s".%s WHERE table_name = ANY(:t)' % (PG_TEST_SCHEMA, table)),
                             {"t": list(TABLES)})


def _write(client, table, k, **more):
    return client.put("/tables/%s/data/updates" % table, json={"updates": [
        {"updates": {"k": k, "v": "x", **more}, "source_name": "user", "updated_by": "web_client"}]})


def test_each_door_answers_as_the_table_s_access_cell_says(grid):
    client, who = grid
    got = {}
    for table in STATES:
        for person in PEOPLE:
            who["name"] = person
            read = client.get("/tables/%s/data" % table).status_code
            edit = _write(client, table, "%s-%s" % (table, person)).status_code
            listed = table in client.get("/tables").json()["tables"]
            assert read in (200, 403) and edit in (200, 403), (table, person, read, edit)
            assert listed == (read == 200), (table, person, listed, read)       # the list says what the door says
            got[(table, person)] = (read == 200, edit == 200)
    assert got == WANT
    who["name"] = "kim"
    refused = client.get("/tables/acc_allow/data")
    assert refused.status_code == 200
    who["name"] = "lee"
    refused = client.get("/tables/acc_allow/data")
    assert refused.status_code == 403 and "access.read.allow" in refused.json()["detail"]     # says the next step


def test_sign_in_off_answers_as_today(grid):
    client, who = grid
    who["on"], who["name"] = False, None
    for table in STATES:
        assert client.get("/tables/%s/data" % table).status_code == 200
        assert _write(client, table, "off").status_code == 200


def test_an_edit_by_row_is_judged_on_the_table_it_names(grid):
    client, who = grid
    who["name"] = "kim"
    assert _write(client, LOOKS, "a", look_table="acc_allow").status_code == 200       # kim edits acc_allow
    assert _write(client, LOOKS, "b", look_table="acc_open").status_code == 403        # nobody but admins edits
    who["name"] = "lee"
    assert _write(client, LOOKS, "c", look_table="acc_allow").status_code == 403
    assert _write(client, LOOKS, "d", look_table="acc_deny").status_code == 200


#: (person, the table the row names) -> may delete it (lead 11-08: deleting a row edits it - judged as the rows door does)
DELETES = {("kim", "acc_allow"): True, ("lee", "acc_allow"): False, ("kim", "acc_deny"): False,
           ("lee", "acc_deny"): True, ("kim", None): False, ("lee", None): False}


@pytest.mark.parametrize("door", ["one", "batch"])
def test_a_delete_door_judges_an_edit_by_row_on_the_table_it_names(grid, door):
    """Both doors that delete a row: each row on the table its look_table names; a row not there on LOOKS's own cell
    (admins). cb4310be8 answered LOOKS's own cell at both, for every row."""
    client, who = grid

    def delete(row_id):
        return (client.delete("/tables/%s/rows/%s" % (LOOKS, row_id)) if door == "one" else
                client.post("/tables/%s/rows/batch_delete" % LOOKS, json={"row_ids": [row_id]})).status_code

    got = {}
    for person in ("kim", "lee"):
        for named in ("acc_allow", "acc_deny", None):
            who["name"] = "boss"
            if named:
                assert _write(client, LOOKS, "%s-%s" % (person, named), look_table=named).status_code == 200
                row_id = [r["row_id"] for r in client.get("/tables/%s/data" % LOOKS).json()["data"]
                          if r["data"]["k"]["value"] == "%s-%s" % (person, named)][0]
            else:
                row_id = "no-such-row"
            who["name"] = person
            status = delete(row_id)
            assert status in (200, 403, 404), (person, named, status)
            got[(person, named)] = status != 403
    assert got == DELETES


def test_the_audit_lists_leave_out_an_unreadable_table(grid):
    client, who = grid
    who["name"] = "boss"
    for table in ("acc_allow", "acc_open"):
        assert _write(client, table, "audit").status_code == 200
    who["name"] = "lee"
    tables = {group["logs"][0]["table_name"] for group in client.get("/audit_logs/recent").json()["groups"]}
    assert "acc_open" in tables and "acc_allow" not in tables, tables          # canary: one table is seen
    who["name"] = "kim"
    tables = {group["logs"][0]["table_name"] for group in client.get("/audit_logs/recent").json()["groups"]}
    assert {"acc_open", "acc_allow"} <= tables, tables


def test_a_broadcast_skips_a_socket_whose_person_may_not_read_its_table(monkeypatch):
    import asyncio

    import main
    from admin import sso

    monkeypatch.setattr(sso, "enabled", lambda: True)
    monkeypatch.setattr(sso, "is_admin", lambda user: False)
    for name, entry in TABLES.items():
        monkeypatch.setitem(crud.TABLE_CONFIG, name, entry)

    class Socket:
        def __init__(self, user):
            self.state, self.sent = type("S", (), {"sso_user": user})(), []

        async def send_text(self, message):
            self.sent.append(message)

    manager = main.ConnectionManager()
    kim, lee, worker = Socket("kim"), Socket("lee"), Socket(None)
    manager.active_connections = [kim, lee, worker]
    asyncio.run(manager.broadcast(json.dumps({"event": "x", "table_name": "acc_allow"})))
    asyncio.run(manager.broadcast(json.dumps({"event": "y", "table_name": "acc_open"})))
    asyncio.run(manager.broadcast(json.dumps({"event": "z"})))
    assert [len(kim.sent), len(lee.sent), len(worker.sent)] == [3, 2, 3]       # lee: 0 frames of acc_allow


def test_a_walk_leaves_out_the_sources_of_a_hidden_table(monkeypatch):
    from ledger import schema, trace_router

    declared = {"w1": {"sources": {"s_allow": {"relation": "acc_allow"}, "s_open": {"relation": "acc_open"}}},
                "w2": {"sources": {"s_allow2": {"relation": "acc_allow"}}}}
    monkeypatch.setattr(trace_router, "_declaration", lambda world=None: declared.get(world))

    class World:
        def __init__(self, name):
            self.name, self.ledger = name, "ledger_" + name

    names = [World("w1"), World("w2")]
    count, leave_out = trace_router._hidden_here(names, ("acc_allow", "acc_none"))
    assert (count, leave_out) == (1, {"w1": ["s_allow"], "w2": ["s_allow2"]})
    assert trace_router._hidden_here(names, ()) == (0, None)                       # nobody hidden: today's read
    assert trace_router._hidden_here(names, object()) == (0, None)                 # a direct call: the Depends
    assert trace_router._hidden_here(names, ("acc_allow",), {"w1": ["x"]})[1] == {"w1": ["x", "s_allow"],
                                                                                    "w2": ["s_allow2"]}
    sql = schema.walk_relation(names, leave_out)
    assert "NOT IN ('s_allow')" in sql and "NOT IN ('s_allow2')" in sql and "s_open" not in sql


def test_every_route_that_takes_a_table_carries_the_door():
    """A route that names a table in its path or by a TABLE_ARGS argument carries `table_door` (TableRoute); a route
    that takes a table only in its body is listed here, with where it is judged - a new one fails this test."""
    import inspect

    import main
    from admin import access

    taking = [route for route in main.app.routes if hasattr(route, "endpoint")
              and access.takes_a_table(route.path, route.endpoint)]
    assert len(taking) > 20                                                       # canary: the grid routes are seen
    bare = [route.path for route in taking
            if not any(getattr(d.dependency, "__name__", "") == "table_door" for d in route.dependencies)]
    assert bare == []
    body_tables = {}
    for route in main.app.routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None or access.takes_a_table(route.path, endpoint) or route.path.startswith(("/admin", "/internal")):
            continue
        source = inspect.getsource(inspect.unwrap(endpoint))
        if any(word in source for word in ('"map_table"', '"table_name"', '"target_table"', "'table'", '"table"')):
            body_tables[route.path] = sorted(route.methods or ())
    assert body_tables == BODY_TABLE_ROUTES, body_tables


#: Routes that take a table in their body (not path or query) - each judged where it says. Admin and internal routes
#: are the token's (admins and workers) and are not listed.
BODY_TABLE_ROUTES = {
    "/api/maps/alignment/confirm": ["POST"],      # payload map_table - access.may(EDIT) first thing in the route
    "/outbox/queue/rows": ["GET"],                # each row's table - an unreadable one's rows are left out
    "/markings": ["POST"],                        # the marked table - access.may(READ) in the route (S-mark)
}


def test_a_report_opens_to_who_may_read_every_table_it_read(grid, tmp_path, monkeypatch):
    import paths
    from chain import report_html, report_reads

    client, who = grid
    monkeypatch.setattr(paths, "DATA_ROOT", str(tmp_path))
    read = report_reads.fresh_reading()
    report_reads._model("acc_allow")                                 # the report's own read names its table
    assert read == {"acc_allow"}
    report_html.keep("R1", "<p>r1</p>", tables=read)
    report_html.keep("R0", "<p>r0</p>")                              # written before - no record
    answers = {}
    for person in PEOPLE:
        who["name"] = person
        listed = client.get("/reports").text
        answers[person] = tuple((client.get("/reports/%s.html" % name).status_code, name + ".html" in listed)
                                for name in ("R1", "R0"))
    assert answers == {"kim": ((200, True), (403, False)), "lee": ((403, False), (403, False)),
                       "boss": ((200, True), (200, True))}
