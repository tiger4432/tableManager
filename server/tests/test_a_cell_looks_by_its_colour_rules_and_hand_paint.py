# -*- coding: utf-8 -*-
"""Owner 11-06, lead L2: a table's colour rules and hand paint are rows of the shipped sys_looks (look_axis rule ·
paint), written through the table write door; a page read carries the table's rules and its rows' paints, and - only
when a rule asks who wrote a cell - each cell of that rule's columns says its writer, in four words or none.

  writer   crud.writer_kind: a person · the chain (a bracketed layer by its base name, the enrichment chain) · a
           language model · a file · a merge (owner 11-08 1ㄱ - TURNED, was «no word», lead 11-07 ②); no layer none
  looks    rules in their order, a wiped role gone; the paints of the page's rows only; none - no "looks" at all
  writers  the source of the line t.won_by names (the write ranked it - a person over a model's draft; the
           cell-source overhaul's lines, here written by hand); asked only by a written_by rule, on its columns, and
           said only when it is a writer a rule asks (lead 11-09); the pivot's cells carry it too
"""
from datetime import datetime, timedelta, timezone

import pytest
import uuid6

import grid_look
import shipped
from conftest import retire_dynamic_model
from database import crud, models
from tests.support import line_tables

TABLE = "look_probe"
LOOKS = "sys_looks"
ENTRY = {"business_key": "bk", "composite_key_source": ["lot", "itemid"],
         "column_types": {"lot": "string", "itemid": "string", "value": "number", "note": "string"},
         "pivot": {"column": "itemid", "value": "value"}}
ROWS = [("L1", "a"), ("L1", "b"), ("L2", "a"), ("L2", "b")]
T0 = datetime(2026, 11, 7, tzinfo=timezone.utc)


@pytest.fixture
def grid(db_session, client, monkeypatch):
    for name in ("_undeclared_column_drops", "_undeclared_column_warned", "_undeclared_column_drops_over_budget"):
        monkeypatch.setattr(crud, name, {})
    assert LOOKS in shipped.tables() and LOOKS in models.DYNAMIC_TABLES, "CANARY: the shipped look table"
    models.init_dynamic_models({TABLE: ENTRY})
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, ENTRY)
    monkeypatch.setitem(crud.TABLE_CONFIG, LOOKS, shipped.tables()[LOOKS])
    bind = db_session.get_bind()
    line_tables.build(bind, TABLE)                         # t with won_by and its line table
    model = models.DYNAMIC_TABLES[TABLE]
    ids = sorted(str(uuid6.uuid7()) for _ in ROWS)
    db_session.add_all([model(row_id=rid, lot=lot, itemid=item, value=0.1 * (n + 1), note="n%d" % n,
                              business_key_val="%s|%s" % (lot, item)) for n, (rid, (lot, item)) in enumerate(zip(ids, ROWS))])
    db_session.commit()
    try:
        yield client, ids
    finally:
        db_session.rollback()
        looks = models.DYNAMIC_TABLES[LOOKS]
        db_session.query(looks).filter(looks.look_table == TABLE).delete()
        db_session.commit()
        line_tables.drop(bind, TABLE)
        models.DYNAMIC_TABLES[TABLE].__table__.drop(bind=bind)
        retire_dynamic_model(TABLE)


def _look(client, axis, key, **cells):
    answer = client.put("/tables/%s/data/updates" % LOOKS, json={"updates": [{"updates": {
        "look_table": TABLE, "look_axis": axis, "look_key": key, **cells}, "updated_by": "probe"}]})
    assert answer.status_code == 200, answer.text


def _layers(db_session, row_id, column, *names):
    """A line of `column` from each source in `names`, the LAST the one the write ranked first: t.won_by names it."""
    from sqlalchemy import MetaData, Table

    bind, bits = db_session.get_bind(), line_tables.bits_of(TABLE)
    with bind.begin() as conn:
        ids = [line_tables.line(conn, TABLE, bits, row_id, source=name, at=T0 + timedelta(minutes=n),
                                values={column: 1.5 if column == "value" else "x"}) for n, name in enumerate(names)]
        t = Table(TABLE, MetaData(), autoload_with=conn)
        won = dict(conn.execute(t.select().where(t.c.row_id == row_id)).one().won_by or {})
        won[column] = ids[-1]
        conn.execute(t.update().where(t.c.row_id == row_id).values(won_by=won))


def _read(client, **params):
    """The page as the screen paints it (owner 11-10 ㄱ): the page, then - its looks `updating` - its cells' writers,
    read by the page's own arguments and `part=writers`."""
    answer = client.get("/tables/%s/data" % TABLE, params=params)
    assert answer.status_code == 200, answer.text
    page = answer.json()
    if (page.get("looks") or {}).get("updating"):
        later = client.get("/tables/%s/data" % TABLE, params=dict(params, part=grid_look.WRITERS))
        assert later.status_code == 200, later.text
        written = later.json()["written_by"]
        for row in page["data"]:
            for column, cell in (row.get("data") or {}).items():
                if grid_look.paint_key(row["row_id"], column) in written:
                    cell["written_by"] = written[grid_look.paint_key(row["row_id"], column)]
            for cell in (row.get("cells") or {}).values():       # a pivot's cell: its row's value column (lead 11-10)
                key = grid_look.paint_key(cell.get("row_id"), page["pivot"]["value"])
                if key in written:
                    cell["written_by"] = written[key]
    return page


def test_a_layer_is_written_by_a_person_the_chain_a_model_a_file_or_a_merge():
    said = {name: crud.writer_kind(name) for name in (
        "user", "chain_ingestion", "chain_ingestion (r1 k%7C1)", "enrichment_auto_confirm (r1 k1)",
        "enrichment_auto_confirm_partial_key", "enrichment_backfill", "custom_script", "llm_draft",
        "pipeline_parser", "lots (2).csv", "external:csv@t@root|a/b.csv", "collision_merge", None, "")}
    assert said == {
        "user": "person", "chain_ingestion": "chain", "chain_ingestion (r1 k%7C1)": "chain",
        "enrichment_auto_confirm (r1 k1)": "chain", "enrichment_auto_confirm_partial_key": "chain",
        "enrichment_backfill": "chain", "custom_script": "chain", "llm_draft": "ai", "pipeline_parser": "file",
        "lots (2).csv": "file", "external:csv@t@root|a/b.csv": "file", "collision_merge": "merge", None: None, "": None}


def test_a_page_carries_the_rules_in_order_and_the_paints_of_its_rows_and_nothing_without_looks(grid):
    client, ids = grid
    every = [(r["id"], r["role"], r["shape"], r["every"]) for r in _read(client)["looks"]["rules"]]
    assert every == [("written-by-person", "warn", "line", True), ("written-by-merge", "danger", "fill", True),
                     ("written-by-ai", "accent", "line", True)], "no rule of its own: the rules every table has"
    _look(client, "rule", "r-1", position="8", role="danger", rule_when="[value] > 0.3")
    _look(client, "rule", "r-2", position="08", role="warn", rule_when="[value] > 0.1", rule_columns='["value"]')
    _look(client, "rule", "r-gone", position="9", role="accent", rule_when="[value] > 0")
    _look(client, "rule", "r-gone", role="")
    _look(client, "paint", "%s/value" % ids[0], role="ok")
    _look(client, "paint", "%s/value" % ids[3], role="danger")
    looks = _read(client, limit=2)["looks"]
    assert [(r["id"], r["role"], r["columns"]) for r in looks["rules"] if not r["every"]] == [
        ("r-2", "warn", ["value"]), ("r-1", "danger", None)], "by position, not by id"
    assert {key: paint["role"] for key, paint in looks["paints"].items()} == {"%s/value" % ids[0]: "ok"}, \
        "a paint of a row off the page is not sent"
    assert all(paint["row_id"] for paint in looks["paints"].values()), "a paint names its row - its history"
    assert not any("written_by" in cell for row in _read(client)["data"] for cell in row["data"].values()),         "TURNED (lead 11-09): a cell says its writer only when it is one a rule asks - these cells have no layer"


def test_a_written_by_rule_has_its_cells_say_their_writer_by_the_values_own_ranking(grid, db_session):
    client, ids = grid
    _layers(db_session, ids[0], "value", "llm_draft", "user")
    _layers(db_session, ids[1], "value", "llm_draft")
    _layers(db_session, ids[2], "value", "chain_ingestion (r1 k1)")
    _layers(db_session, ids[3], "value", "lots.csv", "collision_merge")
    _layers(db_session, ids[1], "note", "llm_draft")
    _look(client, "rule", "r-ai", position="8", role="accent", written_by="ai", rule_columns='["value"]')
    data = {row["row_id"]: row["data"] for row in _read(client)["data"]}
    assert [data[rid]["value"].get("written_by") for rid in ids] == ["person", "ai", None, "merge"],         "no rule asks the chain (lead 11-09)"
    assert data[ids[1]]["note"].get("written_by") == "ai", "TURNED (owner 11-08 1ㄱ): the rules every table has name no column"
    _look(client, "rule", "r-chain", position="9", role="ok", written_by="chain", rule_columns='["value"]')
    data = {row["row_id"]: row["data"] for row in _read(client)["data"]}
    assert [data[rid]["value"].get("written_by") for rid in ids] == ["person", "ai", "chain", "merge"]
    pivot = _read(client, pivot="true")
    by_cell = {(row["lot"], item): cell.get("written_by") for row in pivot["data"] for item, cell in row["cells"].items()}
    assert by_cell == {("L1", "a"): "person", ("L1", "b"): "ai", ("L2", "a"): "chain", ("L2", "b"): "merge"}
