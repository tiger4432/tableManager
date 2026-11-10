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
    pivot = client.get("/tables/%s/data" % TABLE, params={"part": grid_look.WRITERS, "pivot": "true"})
    assert pivot.status_code == 200 and set(pivot.json()) == {"table_name", "skip", "written_by"}, pivot.text


def test_a_pivot_page_reads_no_writer_either(grid, db_session, monkeypatch):
    """Lead 11-10 (ops: a pivot page read cell_sources 13 s for its 2,000 rows - the row page alone had been split):
    a pivot page says `updating` and reads no layer's writer; its `part=writers` read does."""
    client, ids = grid
    _model_writers(db_session, ids)
    _look(client, "rule", "r-chain", position="9", role="ok", written_by="chain", rule_columns='["value"]')
    asked = []
    real = grid_look._writers
    monkeypatch.setattr(grid_look, "_writers", lambda *a, **k: asked.append(1) or real(*a, **k))
    page = client.get("/tables/%s/data" % TABLE, params={"pivot": "true"})
    assert page.status_code == 200 and page.json()["pivot"], page.text
    assert page.json()["looks"]["updating"] is True and asked == [], "the pivot page read the layers' writers"
    later = client.get("/tables/%s/data" % TABLE, params={"pivot": "true", "part": grid_look.WRITERS})
    assert later.status_code == 200 and asked == [1] and "chain" in later.json()["written_by"].values(), later.text


def test_the_writers_read_runs_under_the_grid_read_limit(grid, monkeypatch):
    """Lead 11-10 (ops: a page's writers read 13 s on cell_sources while the screen had moved on): its statements run
    under grid_read_timeout_seconds, as a search does - a plain page read does not."""
    from database import context
    from parsers import directory_watcher

    client, _ids = grid
    monkeypatch.setattr(directory_watcher, "grid_read_timeout", lambda settings=None: 7.0)
    seen = []
    real = grid_look.read
    monkeypatch.setattr(grid_look, "read", lambda *a, **k: seen.append(context.request_read_seconds.get())
                        or real(*a, **k))
    assert client.get("/tables/%s/data" % TABLE).status_code == 200
    assert client.get("/tables/%s/data" % TABLE, params={"part": grid_look.WRITERS}).status_code == 200
    assert seen == [None, 7.0], seen


def test_the_same_page_asked_again_while_its_writers_read_runs_waits_for_that_read(grid, monkeypatch):
    """One writers read a page at a time: a second ask of the same page shares the running read's answer; another
    page reads its own."""
    import threading
    import time

    client, _ids = grid
    reads, go = [], threading.Event()
    real = grid_look.written_of

    def held(rows):
        reads.append(1)
        go.wait(10)
        return real(rows)

    monkeypatch.setattr(grid_look, "written_of", held)
    answers = []

    def ask(skip, **more):
        answers.append(client.get("/tables/%s/data" % TABLE, params=dict(more, part=grid_look.WRITERS, skip=skip)))

    first = threading.Thread(target=ask, args=(0,))
    first.start()
    deadline = time.monotonic() + 10
    while not reads and time.monotonic() < deadline:
        time.sleep(0.01)
    assert reads == [1], "canary: the first read runs"
    second = threading.Thread(target=ask, args=(0,))
    second.start()
    time.sleep(0.3)
    assert reads == [1], "the same page was read twice at once"
    pivot = threading.Thread(target=ask, args=(0,), kwargs={"pivot": "true"})
    pivot.start()
    while len(reads) < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert reads == [1, 1], "the same arguments as a pivot are another read"
    go.set()
    for thread in (first, second, pivot):
        thread.join(10)
    assert [a.status_code for a in answers] == [200, 200, 200]
    plain = [a.json() for a in answers if "pivot" not in a.request.url.query.decode()]
    assert len(plain) == 2 and plain[0] == plain[1]
    assert client.get("/tables/%s/data" % TABLE, params={"part": grid_look.WRITERS, "skip": 1}).status_code == 200
    assert reads == [1, 1, 1], "another page reads its own"
