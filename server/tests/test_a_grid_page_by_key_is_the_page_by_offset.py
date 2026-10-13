# -*- coding: utf-8 -*-
"""총괄 e570dcda5 ㄱ: the grid's next / previous page is read by key from the row the page before ended on (`after` /
`before`) - no OFFSET - and a page-number jump stays OFFSET. The two ways give the same page (a sort column with NULLs,
one with many equal values, the default orders); a row written between two asks neither repeats nor drops a row by key;
a row that is gone pages by OFFSET; a sort by a table column says whether an index gives its order. On PostgreSQL - its
NULL order is the one the pages keep."""
import pytest

from database import crud, models

TABLE = "grid_key_probe"
ENTRY = {"business_key": "k", "composite_key_source": ["k"],
         "column_types": {"k": "string", "s": "string", "n": "number"}}
ROWS, LIMIT = 523, 50
ORDERS = [("row_id", False), ("row_id", True), ("s", False), ("s", True), ("n", False), ("n", True),
          ("updated_at", True)]


@pytest.fixture
def grid(pg_engine, monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy import MetaData, text
    from sqlalchemy.orm import sessionmaker

    import main
    from conftest import PG_TEST_SCHEMA
    from database.database import get_db

    entry = dict(ENTRY, indexes=[{"columns": ["s", "row_id"]}, {"columns": ["k", "n"]}])   # n is not its lead
    models.init_dynamic_models({TABLE: entry})
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, entry)
    scratch = MetaData(schema=PG_TEST_SCHEMA)
    models.DYNAMIC_TABLES[TABLE].__table__.to_metadata(scratch, schema=None)
    scratch.create_all(pg_engine)
    with pg_engine.begin() as conn:                 # s: NULL every 7th, else 13 values; n: NULL every 11th, else 5
        conn.execute(text(
            'INSERT INTO "%s"."%s" (row_id, business_key_val, k, s, n, updated_at) '
            "SELECT 'r' || lpad(g::text, 5, '0'), 'K' || g, 'K' || g, "
            "CASE WHEN g %% 7 = 0 THEN NULL ELSE 'S' || lpad((g %% 13)::text, 2, '0') END, "
            "CASE WHEN g %% 11 = 0 THEN NULL ELSE g %% 5 END, "
            "timestamp '2026-10-13' + (g %% 17) * interval '1 minute' FROM generate_series(1, %d) g"
            % (PG_TEST_SCHEMA, TABLE, ROWS)))
    made = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)

    def per_request():
        session = made()
        try:
            yield session
        finally:
            session.close()

    main.app.dependency_overrides[get_db] = per_request
    try:
        with TestClient(main.app) as client:
            yield client
    finally:
        main.app.dependency_overrides.pop(get_db, None)
        with pg_engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, TABLE)))


def _page(client, order_by, desc, skip=0, **key):
    answer = client.get("/tables/%s/data" % TABLE, params={
        "skip": skip, "limit": LIMIT, "order_by": order_by, "order_desc": str(desc).lower(), "defer_total": "true",
        **key})
    assert answer.status_code == 200, answer.text
    return answer.json()


def _ids(page):
    return [row["row_id"] for row in page["data"]]


@pytest.mark.pg
@pytest.mark.parametrize("order_by, desc", ORDERS, ids=["%s %s" % (o, "desc" if d else "asc") for o, d in ORDERS])
def test_the_pages_by_key_are_the_pages_by_offset_forward_and_back(grid, order_by, desc):
    by_offset = [_page(grid, order_by, desc, skip) for skip in range(0, ROWS, LIMIT)]
    assert sum(len(page["data"]) for page in by_offset) == ROWS and len(by_offset) == 11
    forward = [by_offset[0]]
    while len(forward) < len(by_offset):
        forward.append(_page(grid, order_by, desc, after=_ids(forward[-1])[-1]))
    back = [by_offset[-1]]
    while len(back) < len(by_offset):
        back.append(_page(grid, order_by, desc, before=_ids(back[-1])[0]))
    assert [page["data"] for page in forward] == [page["data"] for page in by_offset]
    assert [page["data"] for page in reversed(back)] == [page["data"] for page in by_offset]
    assert _page(grid, order_by, desc, after=_ids(by_offset[-1])[-1])["data"] == []


@pytest.mark.pg
def test_a_row_written_between_two_asks_neither_repeats_nor_drops_a_row_by_key(grid, pg_engine):
    from sqlalchemy import text

    from conftest import PG_TEST_SCHEMA

    before_it = [_ids(_page(grid, "s", False, skip)) for skip in range(0, ROWS, LIMIT)]
    first = _page(grid, "s", False)
    with pg_engine.begin() as conn:                 # one sorts before the page read, one after it
        conn.execute(text('INSERT INTO "%s"."%s" (row_id, business_key_val, k, s) VALUES '
                          "('new-early', 'Kx1', 'Kx1', 'S00'), ('new-late', 'Kx2', 'Kx2', 'S12')"
                          % (PG_TEST_SCHEMA, TABLE)))
    by_key, page = [_ids(first)], first
    while page["data"] and len(by_key) <= ROWS // LIMIT + 2:
        page = _page(grid, "s", False, after=_ids(page)[-1])
        by_key.append(_ids(page))
    by_offset = _ids(_page(grid, "s", False, LIMIT))
    walked = [row for ids in by_key for row in ids]
    assert sorted(set(walked) - {"new-late"}) == sorted(row for ids in before_it for row in ids)
    assert len(walked) == len(set(walked)) == ROWS + 1 and "new-late" in walked and "new-early" not in walked
    assert by_offset[0] == before_it[0][-1], "control: by OFFSET the page after repeats the last row before"


@pytest.mark.pg
def test_a_row_gone_pages_by_offset(grid, pg_engine):
    from sqlalchemy import text

    from conftest import PG_TEST_SCHEMA

    second = _page(grid, "s", False, LIMIT)
    gone = _ids(_page(grid, "s", False))[-1]
    with pg_engine.begin() as conn:
        conn.execute(text('DELETE FROM "%s"."%s" WHERE row_id = :r' % (PG_TEST_SCHEMA, TABLE)), {"r": gone})
    assert _page(grid, "s", False, LIMIT, after=gone)["data"] == _page(grid, "s", False, LIMIT)["data"]
    assert len(second["data"]) == LIMIT


@pytest.mark.pg
def test_a_page_by_key_reads_no_offset_and_a_page_number_does(grid, pg_engine):
    from sqlalchemy import event

    sent = []

    def caught(_conn, _cursor, statement, _parameters, _context, _many):
        if TABLE in statement and "ORDER BY" in statement and "count(" not in statement:
            sent.append(statement)

    event.listen(pg_engine, "before_cursor_execute", caught)
    try:
        first = _page(grid, "s", False)
        sent.clear()
        _page(grid, "s", False, LIMIT, after=_ids(first)[-1])
        by_key = list(sent)
        sent.clear()
        _page(grid, "s", False, 5 * LIMIT)
        by_number = list(sent)
    finally:
        event.remove(pg_engine, "before_cursor_execute", caught)
    assert by_key and not any("OFFSET" in statement for statement in by_key), by_key
    assert any("OFFSET" in statement for statement in by_number), by_number


@pytest.mark.pg
def test_a_sort_by_a_table_column_says_whether_an_index_gives_its_order(grid, pg_engine):
    assert _page(grid, "s", False)["sort_index"] == {"s": "declared, not built yet (built at the next Reload or restart)"}
    assert _page(grid, "n", False)["sort_index"] == {"n": "not declared"}
    built = models.ensure_model_indexes(pg_engine, tables={TABLE: crud.TABLE_CONFIG[TABLE]}, say=lambda line: None)
    assert built == {"idx_grid_key_probe_s_row_id": models.INDEX_BUILT, "idx_grid_key_probe_k_n": models.INDEX_BUILT}
    assert _page(grid, "n", False)["sort_index"] == {"n": "not declared"}, "an index led by another column"
    assert _page(grid, "s", True)["sort_index"] == {"s": "built"}
    assert _page(grid, "k", False)["sort_index"] == {"k": "not declared"}, "led by the column, not followed by row_id"
    for order_by in ("row_id", "updated_at", "id"):
        assert "sort_index" not in _page(grid, order_by, False)
