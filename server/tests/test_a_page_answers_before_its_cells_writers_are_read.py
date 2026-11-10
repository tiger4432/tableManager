"""Owner 11-10 ㄱ (ops: a dt_log page 10 s, 8 s of it the layers its colour rules ask): a grid page answers without
reading which layer wrote its cells - its looks say `updating` - and the screen reads those writers after, by the page's
own arguments and `part=writers` (`grid_look.WRITERS`). The two reads paint the cells one read painted.
"""
import grid_look
import grid_read
from database import models
from tests.test_a_cell_looks_by_its_colour_rules_and_hand_paint import TABLE, _layers, _look, _read, grid  # noqa: F401


def _model_writers(db_session, ids):
    _layers(db_session, ids[0], "value", "llm_draft", "user")
    _layers(db_session, ids[1], "value", "llm_draft")
    _layers(db_session, ids[2], "value", "chain_ingestion (r1 k1)")
    _layers(db_session, ids[1], "note", "llm_draft")


def test_the_page_reads_no_writer_and_the_writers_read_paints_what_one_read_painted(grid, db_session, monkeypatch):
    client, ids = grid
    _model_writers(db_session, ids)
    _look(client, "rule", "r-chain", position="9", role="ok", written_by="chain", rule_columns='["value"]')
    model = models.DYNAMIC_TABLES[TABLE]
    rows = db_session.query(model).filter(model.row_id.in_(ids)).all()
    merged, _looks = grid_read.read_as_page(db_session, TABLE, rows, ["lot", "itemid", "value", "note"],
                                            include_sources=False)
    one_read = grid_look.written_of(merged)
    assert {"chain", "ai"} <= set(one_read.values()), ("canary: the fixture's cells name model writers", one_read)

    asked = []
    real = grid_look._writers
    monkeypatch.setattr(grid_look, "_writers", lambda *a, **k: asked.append(1) or real(*a, **k))
    page = client.get("/tables/%s/data" % TABLE)
    assert page.status_code == 200, page.text
    assert page.json()["looks"]["updating"] is True and asked == [], "the page read the layers' writers"
    painted = {key: writer for key, writer in grid_look.written_of(page.json()["data"]).items()}
    assert set(painted.values()) <= grid_look.NAMED_WRITERS, painted

    later = client.get("/tables/%s/data" % TABLE, params={"part": grid_look.WRITERS})
    assert later.status_code == 200 and asked == [1], later.text
    assert set(later.json()) == {"table_name", "skip", "written_by"}
    assert later.json()["written_by"] == one_read
    assert grid_look.written_of(_read(client)["data"]) == one_read


def test_with_no_rule_asking_a_writer_the_page_says_nothing_is_left(grid, db_session, monkeypatch):
    """The rules every table has taken out (as a table turned off): no writer is asked, none is left."""
    import grid_order
    from database import crud

    client, ids = grid
    _model_writers(db_session, ids)
    monkeypatch.setitem(crud.TABLE_CONFIG, grid_order.LOOK_TABLE, {
        k: v for k, v in crud.TABLE_CONFIG[grid_order.LOOK_TABLE].items() if k != grid_look.DECLARED})
    _look(client, "rule", "r-paint", role="accent", rule_when="[value] > 0")
    looks = client.get("/tables/%s/data" % TABLE).json().get("looks") or {}
    asked = [rule for rule in looks.get("rules", []) if rule["written_by"]]
    assert looks.get("rules") and not asked, ("canary: a rule, none asking a writer", looks)
    assert looks["updating"] is False


def test_the_writers_read_counts_nothing_and_refuses_another_part(grid, monkeypatch):
    import main

    client, _ids = grid
    monkeypatch.setattr(main, "grid_count", lambda *a, **k: (_ for _ in ()).throw(AssertionError("counted")))
    assert client.get("/tables/%s/data" % TABLE, params={"part": grid_look.WRITERS}).status_code == 200
    assert client.get("/tables/%s/data" % TABLE, params={"part": "rows"}).status_code == 422
    assert client.get("/tables/%s/data" % TABLE, params={"part": grid_look.WRITERS, "pivot": "true"}).status_code == 422
