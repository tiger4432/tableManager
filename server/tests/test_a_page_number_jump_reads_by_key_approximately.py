# -*- coding: utf-8 -*-
"""Owner 11-13 ㄷ: a page-number jump deep in row_id order, nothing narrowing it, reads by key from the row_id
histogram's bound at that depth (`main.jump_boundary`) - no OFFSET in its SQL, the page within one histogram bucket of
the exact page, the answer saying `approximate`. Sorted, filtered, shallow or with no statistics it stays OFFSET and
exact. On PostgreSQL - pg_stats is the boundary table."""
import json

import pytest
from sqlalchemy import event, text

from test_a_grid_page_by_key_is_the_page_by_offset import LIMIT, ROWS, TABLE, grid  # noqa: F401 - the fixture

DEEP = 5 * LIMIT


def _analyze(pg_engine):
    from conftest import PG_TEST_SCHEMA

    with pg_engine.begin() as conn:
        conn.execute(text('ANALYZE "%s"."%s"' % (PG_TEST_SCHEMA, TABLE)))
        bounds = conn.execute(text("SELECT histogram_bounds::text::text[] FROM pg_stats WHERE schemaname = :s "
                                   "AND tablename = :t AND attname = 'row_id'"), {"s": PG_TEST_SCHEMA, "t": TABLE}).scalar()
    assert bounds and len(bounds) > 2, "control: the histogram the jump reads exists"
    return len(bounds) - 1


def _ask(client, pg_engine, **params):
    sent = []

    def caught(_conn, _cursor, statement, _parameters, _context, _many):
        if TABLE in statement and "ORDER BY" in statement and "count(" not in statement:
            sent.append(statement)

    event.listen(pg_engine, "before_cursor_execute", caught)
    try:
        answer = client.get("/tables/%s/data" % TABLE, params=dict({"limit": LIMIT, "defer_total": "true"}, **params))
    finally:
        event.remove(pg_engine, "before_cursor_execute", caught)
    assert answer.status_code == 200, answer.text
    return answer.json(), sent


def _ordered(pg_engine, desc):
    from conftest import PG_TEST_SCHEMA

    with pg_engine.begin() as conn:
        return [r[0] for r in conn.execute(text('SELECT row_id FROM "%s"."%s" ORDER BY row_id %s' % (
            PG_TEST_SCHEMA, TABLE, "DESC" if desc else "ASC")))]


@pytest.mark.pg
@pytest.mark.parametrize("desc", [False, True], ids=["asc", "desc"])
def test_a_deep_jump_reads_by_key_within_one_bucket_and_says_approximate(grid, pg_engine, desc):  # noqa: F811
    buckets = _analyze(pg_engine)
    page, sent = _ask(grid, pg_engine, skip=DEEP, order_by="row_id", order_desc=str(desc).lower())
    assert sent and not any("OFFSET" in statement for statement in sent), sent
    assert page.get("approximate") is True, page.keys()
    ordered = _ordered(pg_engine, desc)
    first = ordered.index(page["data"][0]["row_id"])
    assert abs(first - DEEP) <= ROWS / buckets + 1, (first, DEEP, buckets)
    assert [row["row_id"] for row in page["data"]] == ordered[first:first + LIMIT]     # a whole page from there


@pytest.mark.pg
@pytest.mark.parametrize("how", ["sorted", "filtered", "shallow", "no statistics"])
def test_a_jump_that_is_sorted_narrowed_shallow_or_unanalyzed_stays_offset_and_exact(grid, pg_engine, how):  # noqa: F811
    if how != "no statistics":
        _analyze(pg_engine)
    else:
        from conftest import PG_TEST_SCHEMA

        with pg_engine.begin() as conn:
            assert not conn.execute(text("SELECT count(*) FROM pg_stats WHERE schemaname = :s AND tablename = :t"),
                                    {"s": PG_TEST_SCHEMA, "t": TABLE}).scalar(), "control: no statistics taken"
    params = {"sorted": dict(skip=DEEP, order_by="s"),
              "filtered": dict(skip=DEEP // 5, order_by="row_id",
                               filters=json.dumps({"n": {"filterType": "number", "type": "notBlank"}})),
              "shallow": dict(skip=1, order_by="row_id"),
              "no statistics": dict(skip=DEEP, order_by="row_id")}[how]
    page, sent = _ask(grid, pg_engine, **params)
    assert "approximate" not in page, page.keys()
    assert any("OFFSET" in statement for statement in sent), sent
    if how in ("shallow", "no statistics"):
        assert [row["row_id"] for row in page["data"]] == _ordered(pg_engine, False)[params["skip"]:params["skip"] + LIMIT]
