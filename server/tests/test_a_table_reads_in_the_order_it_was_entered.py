# -*- coding: utf-8 -*-
"""소유자 11-06 (총괄 ①②④): a table that declares `"order": "entered"` is read by the sort name `entered` - each row,
and in pivot view each key group and each item, at its first row_id (uuid7: arrival order) unless a row of the shipped
`sys_looks` gives it a place, which a drag writes through the table write door.

  pivot     groups and items in first-entry order; a count and its pages agree; a filter on the item column does not
            move a group (its first row is the whole table's); each group says its first row_id and its order key
  drag      a place written for a group, an item, a row moves it there and nowhere else
  plain     rows in entered order, each with its order key; a page read by key and a jump to a row agree with it
  declared  /schema says "entered" or null; another word is refused at save
  access    a place is an edit of the table it is on (sys_looks edit_by look_table): a person who may edit it drags, one
            who may not is refused with the access sentence, an administrator always drags
"""
import json

import pytest
import uuid6

import shipped
from conftest import retire_dynamic_model
from database import crud, models

TABLE = "entered_probe"
LOOKS = "sys_looks"
ENTRY = {"business_key": "bk", "composite_key_source": ["lot", "wafer", "itemid"],
         "column_types": {"lot": "string", "wafer": "string", "itemid": "string", "value": "number"},
         "pivot": {"column": "itemid", "value": "value"}, "order": "entered"}
#: (lot, wafer, itemid) in the order entered - groups first entered L2W1, L1W1, L1W2, L3W1; items b, c, a
ENTERED = [("L2", "W1", "b"), ("L1", "W1", "c"), ("L1", "W2", "a"), ("L2", "W1", "a"), ("L1", "W1", "a"),
           ("L3", "W1", "c"), ("L1", "W1", "b"), ("L1", "W2", "c")]
GROUPS = [("L2", "W1"), ("L1", "W1"), ("L1", "W2"), ("L3", "W1")]
ITEMS = ["b", "c", "a"]


@pytest.fixture
def grid(db_session, client, monkeypatch):
    for name in ("_undeclared_column_drops", "_undeclared_column_warned", "_undeclared_column_drops_over_budget"):
        monkeypatch.setattr(crud, name, {})
    # the shipped look table is built with the catalogue (conftest), as boot builds it
    assert LOOKS in shipped.tables() and LOOKS in models.DYNAMIC_TABLES, "CANARY: the shipped look table"
    models.init_dynamic_models({TABLE: ENTRY})
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, ENTRY)
    monkeypatch.setitem(crud.TABLE_CONFIG, LOOKS, shipped.tables()[LOOKS])
    bind = db_session.get_bind()
    models.DYNAMIC_TABLES[TABLE].__table__.create(bind=bind)
    model = models.DYNAMIC_TABLES[TABLE]
    ids = sorted(str(uuid6.uuid7()) for _ in ENTERED)
    db_session.add_all([model(row_id=rid, lot=lot, wafer=wafer, itemid=item, value=float(n),
        business_key_val="%s|%s|%s" % (lot, wafer, item)) for n, (rid, (lot, wafer, item)) in enumerate(zip(ids, ENTERED))])
    db_session.commit()
    assert db_session.query(model).count() == len(ENTERED), "CANARY: the long rows"
    try:
        yield client, ids
    finally:
        db_session.rollback()
        looks = models.DYNAMIC_TABLES[LOOKS]
        db_session.query(looks).filter(looks.look_table == TABLE).delete()
        db_session.commit()
        models.DYNAMIC_TABLES[TABLE].__table__.drop(bind=bind)
        retire_dynamic_model(TABLE)


def _read(client, **params):
    answer = client.get("/tables/%s/data" % TABLE, params=params)
    assert answer.status_code == 200, answer.text
    return answer.json()


def _groups(read):
    return [(row["lot"], row["wafer"]) for row in read["data"]]


def _place(client, axis, key, position):
    answer = client.put("/tables/%s/data/updates" % LOOKS, json={"updates": [{"updates": {
        "look_table": TABLE, "look_axis": axis, "look_key": key, "position": position}, "updated_by": "probe"}]})
    assert answer.status_code == 200, answer.text


def _first(ids, at):
    return ids[ENTERED.index(at)]


def test_a_pivot_reads_its_groups_and_items_in_first_entry_order_and_its_pages_agree(grid):
    client, ids = grid
    whole = _read(client, pivot="true", order_by="entered")
    assert _groups(whole) == GROUPS and whole["pivot"]["items"] == ITEMS
    assert whole["total"] == len(GROUPS)
    firsts = [next(i for i, row in zip(ids, ENTERED) if row[:2] == g) for g in GROUPS]
    assert [row["first"] for row in whole["data"]] == firsts == [row["order_key"] for row in whole["data"]]
    assert {item: place["first"] for item, place in whole["pivot"]["item_places"].items()} == {
        item: next(i for i, row in zip(ids, ENTERED) if row[2] == item) for item in ITEMS}
    paged = _groups(_read(client, pivot="true", order_by="entered", limit=3)) + _groups(
        _read(client, pivot="true", order_by="entered", limit=3, skip=3))
    assert paged == GROUPS
    # the item column's filter narrows the long rows - L1W1's first row («c») is filtered out, its place stays
    narrowed = _read(client, pivot="true", order_by="entered",
                     filters=json.dumps({"itemid": {"filterType": "set", "values": ["a", "b"]}}))
    assert _groups(narrowed) == [g for g in GROUPS if g != ("L3", "W1")] and narrowed["pivot"]["items"] == ["b", "a"]
    # the read by key order is today's, untouched
    assert _groups(_read(client, pivot="true")) == sorted(GROUPS)


def test_a_dragged_group_item_and_row_read_at_their_place(grid):
    client, ids = grid
    # L3W1 between L2W1 and L1W1; item «a» first; the last entered row first
    l2w1, l1w1 = _first(ids, ("L2", "W1", "b")), _first(ids, ("L1", "W1", "c"))
    _place(client, "group", _first(ids, ("L3", "W1", "c")), l2w1 + "8")
    assert l2w1 < l2w1 + "8" < l1w1
    _place(client, "item", _first(ids, ("L1", "W2", "a")), "0")
    read = _read(client, pivot="true", order_by="entered")
    assert _groups(read) == [("L2", "W1"), ("L3", "W1"), ("L1", "W1"), ("L1", "W2")]
    assert read["pivot"]["items"] == ["a", "b", "c"]
    assert read["data"][1]["order_key"] == l2w1 + "8"
    _place(client, "row", ids[-1], "0")
    plain = _read(client, order_by="entered")
    assert [row["row_id"] for row in plain["data"]] == [ids[-1]] + ids[:-1]
    assert [row["order_key"] for row in plain["data"]] == ["0"] + ids[:-1]
    # a group's place is not a row's: the plain read did not move L3W1's first row
    assert plain["data"][ENTERED.index(("L3", "W1", "c")) + 1]["row_id"] == _first(ids, ("L3", "W1", "c"))


def test_a_page_read_by_key_and_a_jump_to_a_row_follow_the_entered_order(grid):
    client, ids = grid
    _place(client, "row", ids[5], "0")
    order = [ids[5]] + ids[:5] + ids[6:]
    first = _read(client, order_by="entered", limit=3)
    assert [row["row_id"] for row in first["data"]] == order[:3]
    after = _read(client, order_by="entered", limit=3, after=order[2])
    assert [row["row_id"] for row in after["data"]] == order[3:6]
    jump = _read(client, order_by="entered", limit=100, target_row_id=ids[2])
    assert jump["target_offset"] == order.index(ids[2])


def test_the_schema_says_the_order_and_another_word_is_refused(grid, monkeypatch):
    import grid_order

    client, _ids = grid
    assert client.get("/tables/%s/schema" % TABLE).json()["order"] == "entered"
    assert grid_order.refusal(TABLE, ENTRY) is None
    assert grid_order.refusal(TABLE, {**ENTRY, "order": "latest"})[0] == "tables.%s.order" % TABLE
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, {**ENTRY, "order": "latest"})
    assert client.get("/tables/%s/schema" % TABLE).json()["order"] is None


def test_a_place_is_an_edit_of_the_table_it_is_on(grid, db_session, monkeypatch):
    """Sign-in on (lead 11-07, cb4310be8): the shipped sys_looks says edit_by look_table, so the write door judges each
    place on the table being reordered - kim may edit it, lee may not, boss is an administrator."""
    from admin import access, sso

    client, ids = grid
    assert shipped.tables()[LOOKS]["access"] == {"edit_by": "look_table"}
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, {**ENTRY, "access": {"edit": {"allow": ["kim"]}}})
    who = {"name": None}

    def admit(request):
        request.state.sso_user = who["name"]
    monkeypatch.setattr(sso, "enabled", lambda: True)
    monkeypatch.setattr(sso, "admit", admit)
    monkeypatch.setattr(sso, "is_admin", lambda user: user == "boss")

    def drag(name, position):
        who["name"] = name
        return client.put("/tables/%s/data/updates" % LOOKS, json={"updates": [{"updates": {
            "look_table": TABLE, "look_axis": "row", "look_key": ids[-1], "position": position}, "updated_by": name}]})

    refused = drag("lee", "0")
    assert refused.status_code == 403 and refused.json()["detail"] == access.DENIED % ("lee", "edit", TABLE, "edit")
    assert _read(client, order_by="entered")["data"][0]["row_id"] == ids[0], "a refused place moved nothing"
    assert drag("kim", "0").status_code == 200
    assert _read(client, order_by="entered")["data"][0]["row_id"] == ids[-1]
    assert drag("boss", "08").status_code == 200
    looks = models.DYNAMIC_TABLES[LOOKS]
    # the same place written again is the same row (every key part filled - a blank one would make a row per write)
    assert [r.position for r in db_session.query(looks).filter(looks.look_table == TABLE)] == ["08"]


@pytest.mark.pg
def test_the_places_read_the_same_on_postgresql(pg_session, monkeypatch):
    """Production is PostgreSQL: a row, a group and an item each read at a place between two row ids - the screen's
    «a + 8» - and the groups' and items' first row_id read through an aggregate over the whole table."""
    import grid_order
    import grid_pivot
    from main import _named_sort

    db = pg_session
    bind = db.get_bind()
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, ENTRY)
    monkeypatch.setitem(crud.TABLE_CONFIG, LOOKS, shipped.tables()[LOOKS])
    models.init_dynamic_models({TABLE: ENTRY, LOOKS: shipped.tables()[LOOKS]})
    model, looks = models.DYNAMIC_TABLES[TABLE], models.DYNAMIC_TABLES[LOOKS]
    made = not bind.dialect.has_table(bind.connect(), LOOKS)
    looks.__table__.create(bind=bind, checkfirst=True)
    model.__table__.create(bind=bind)
    try:
        db.add_all([model(row_id=rid, lot=lot, wafer="W1", itemid=item, value=1.0)
                    for rid, lot, item in (("019ab", "L1", "a"), ("019ac", "L2", "b"), ("019ad", "L3", "c"))])
        db.add_all([looks(row_id="p%d" % n, look_table=TABLE, look_axis=axis, look_key=key, position="019aa8")
                    for n, (axis, key) in enumerate((("row", "019ac"), ("group", "019ac"), ("item", "019ac")))])
        db.commit()
        plain = db.query(model.row_id).order_by(*_named_sort(model, TABLE, grid_order.ENTERED, False)).all()
        assert [r[0] for r in plain] == ["019ac", "019ab", "019ad"]
        pivot = grid_pivot.of(TABLE)
        groups = grid_pivot.order(grid_pivot.groups(db.query(model), model, pivot), model, pivot, grid_order.ENTERED,
                                  False).all()
        assert [g[0] for g in groups] == ["L2", "L1", "L3"] and groups[0][-1] == "019aa8"
        places = {}
        assert grid_pivot.item_names(db.query(model), model, pivot, 10, places=places) == (["b", "a", "c"], 0)
    finally:
        db.rollback()
        db.query(looks).filter(looks.look_table == TABLE).delete()
        db.commit()
        model.__table__.drop(bind=bind)
        if made:
            looks.__table__.drop(bind=bind)
        retire_dynamic_model(TABLE)


@pytest.mark.pg
def test_a_table_node_walks_to_the_places_dragged_on_it(pg_engine, tmp_path, monkeypatch):
    """총괄 11-06 ㄱ: `sys_looks` is a source of the shipped `system` world - a look is keyed as grid_order reads a
    place (look_table · look_axis · look_key), and
    `placed_on` reaches the very table node `sys_tables` registers. Walked from the table: its looks, and the table's
    own group from sys_tables on the same node."""
    import os
    import shutil

    import database.database as database_module
    import event_constants
    import paths
    from conftest import PG_TEST_SCHEMA
    from database import schemas
    from database.context import channel
    from ledger import backfill, explorer, schema, trace_router
    from ledger.store import LedgerStore
    from sqlalchemy import MetaData, text
    from sqlalchemy.orm import sessionmaker
    from tests.support.pools import bodies_here

    sample = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "sample")
    config = tmp_path / "config"
    (config / "ontology").mkdir(parents=True)
    shutil.copy(os.path.join(sample, "table_config.json.sample"), config / "table_config.json")
    shutil.copy(os.path.join(sample, "ledger_config.json.sample"), config / "ontology" / "ledger_config.json")
    monkeypatch.setattr(paths, "CONFIG_DIR", str(config))
    monkeypatch.setattr(database_module, "engine", pg_engine)
    bodies_here(monkeypatch)
    names = ("sys_tables", LOOKS)
    declared = {name: shipped.tables()[name] for name in names}
    # what the session built is left as found - every grid read asks sys_looks (L2), so a dropped one fails a later file
    had = [name for name in names if name in models.DYNAMIC_TABLES]
    with pg_engine.connect() as conn:
        existed = {name for name in names if pg_engine.dialect.has_table(conn, name, schema=PG_TEST_SCHEMA)}
    probe = {"sys_tables": "table_name", LOOKS: "look_table"}
    for name in names:
        retire_dynamic_model(name)
        monkeypatch.setitem(crud.TABLE_CONFIG, name, declared[name])
    models.init_dynamic_models(declared)
    world = schema.require_world("system")

    def clean():
        with pg_engine.begin() as conn:
            for name in names:
                if name in existed:
                    conn.execute(text('DELETE FROM "%s"."%s" WHERE %s = :t' % (PG_TEST_SCHEMA, name, probe[name])), {"t": TABLE})
                else:
                    conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, name)))
                for side in ("cell_sources", "database_outbox", "audit_logs"):
                    conn.execute(text('DELETE FROM "%s".%s WHERE table_name = :t' % (PG_TEST_SCHEMA, side)),
                                 {"t": name})
            for relation, who in ((world.ledger, "source_who"), (world.row_ref, "source_who"),
                                  (world.cursor, "source")):
                if conn.execute(text("SELECT to_regclass(:r)"), {"r": relation}).scalar():
                    conn.execute(text("DELETE FROM %s WHERE %s = ANY(:w)" % (relation, who)), {"w": list(names)})
        schema._ensured.clear()

    clean()
    scratch = MetaData(schema=PG_TEST_SCHEMA)
    for name in names:
        models.DYNAMIC_TABLES[name].__table__.to_metadata(scratch, schema=None)
    scratch.create_all(pg_engine)
    db = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)()
    try:
        with channel(event_constants.CHANNEL_API):
            for table, rows in (("sys_tables", [{"table_name": TABLE, "group": "Plans", "declared": "yes"}]),
                                (LOOKS, [{"look_table": TABLE, "look_axis": "row", "look_key": "r1", "position": "08"},
                                         {"look_table": TABLE, "look_axis": "group", "look_key": "r2",
                                          "position": "r18"}])):
                crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
                    schemas.GeneralUpdateItem(updates=row, source_name="user", updated_by="probe") for row in rows]))
        db.commit()
        LedgerStore(pg_engine, world="system").ensure_schema()
        raw = pg_engine.raw_connection()
        try:
            schema.ensure_schema(raw)
            raw.commit()
        finally:
            raw.close()
        # the walk's deployment check names its two indexes without a schema (trace_router._subgraph_contract_state),
        # so it finds the default ledger's whichever world is walked - both get them
        with pg_engine.begin() as conn:
            for statement in (*schema.SOURCE_EVENT_INDEXES, *schema.source_event_indexes(world)):
                conn.execute(text(statement))
        ran = {name: backfill.run(pg_engine, source=name, world="system") for name in names}
        with pg_engine.connect() as conn:
            graph = trace_router._evidence_graph(conn, node_id=explorer.entity_id("table", {"table": TABLE}), hops=1,
                                                 direction="both", node_limit=200, edge_limit=400, world=["system"])
        nodes = {node["id"]: node for node in graph["nodes"]}
        looks = sorted(((n["keys"], n["attributes"].get("position")) for n in nodes.values() if n["type"] == "look"),
                       key=lambda look: look[0]["axis"])
        assert looks == [({"table": TABLE, "axis": "group", "key": "r2"}, "r18"),
                         ({"table": TABLE, "axis": "row", "key": "r1"}, "08")], json.dumps(ran, default=str)
        assert {e["predicate"] for e in graph["edges"]} >= {"placed_on"}
        table = nodes[explorer.entity_id("table", {"table": TABLE})]
        assert table["attributes"]["group"] == "Plans", table
    finally:
        db.close()
        clean()
        for name in names:
            retire_dynamic_model(name)
        if had:
            models.init_dynamic_models({name: declared[name] for name in had})
