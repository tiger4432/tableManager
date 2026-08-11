"""The bounded scan behind `/audit_logs/recent`, and the word it must say.

Every assertion here was made to FAIL against a deliberately broken version of
`audit_cache` before it was committed, because a regression net that has never
caught anything is indistinguishable from one that cannot. The defect each test
is the alarm for is named in its docstring.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa

import audit_cache
import audit_history
from audit_cache import AuditLogCache
from database import models

TABLE = "audit_recent_scan_probe"
BASE = datetime(2026, 8, 11, 6, 0, 0, tzinfo=timezone.utc)


def seed(db, transactions):
    """`transactions` is [(tx_id, row_count)], OLDEST FIRST.

    Every row of one transaction shares one timestamp, which is what the server
    actually produces: `AuditLog.timestamp` defaults to `func.now()`, i.e.
    transaction start, so a 100,000-row batch stamps 100,000 identical values
    and the ordering is decided entirely by the `id` tiebreak.
    """
    for index, (tx_id, count) in enumerate(transactions):
        stamp = BASE + timedelta(minutes=index)
        for row in range(count):
            db.add(models.AuditLog(
                table_name=TABLE, row_id=f"{tx_id}-{row}", column_name="value",
                old_value=None, new_value=f"v{row}", source_name="pipeline_parser",
                updated_by="system", transaction_id=tx_id, timestamp=stamp,
                business_key=f"BK-{tx_id}"))
    db.commit()


@pytest.fixture
def knobs(monkeypatch):
    """Drive the shipped config path, not a private attribute.

    `load_initial` resolves its settings through `audit_history.load_config`, so
    overriding that here exercises exactly the code an operator's
    `audit_history_config.json` would.
    """
    def set_config(**overrides):
        monkeypatch.setattr(audit_history, "load_config", lambda *a, **k: overrides)
    return set_config


def test_a_bounded_scan_says_it_gave_up(db_session, knobs):
    """ALARM FOR: the ceiling is removed, or a short list is served silently.

    Three transactions of thirty rows with a fifty-row ceiling can only reach
    two of them. The list is therefore SHORT, and a short list that does not say
    so is indistinguishable from the whole of history.
    """
    seed(db_session, [("scan-tx-c", 30), ("scan-tx-b", 30), ("scan-tx-a", 30)])
    knobs(recent_max_scan_rows=50, recent_scan_chunk_rows=10)

    cache = AuditLogCache()
    cache.load_initial(db_session, limit_groups=3)

    assert cache.scanned_rows == 50, "the ceiling did not stop the walk"
    assert [g["transaction_id"] for g in cache.groups] == ["scan-tx-a", "scan-tx-b"]
    assert cache.truncated is True
    assert cache.next_cursor, "a truncated answer must carry where to resume"
    # The token is the one `audit_history` already defines - not a second
    # spelling of the same position.
    stamp, log_id = audit_history.decode_cursor(cache.next_cursor)
    assert isinstance(log_id, int)
    assert isinstance(stamp, datetime)


def test_b_an_exhausted_table_is_not_called_truncated(db_session, knobs):
    """ALARM FOR: `truncated` hard-wired to True.

    "There is more" and "that was all of it" are different answers, and a flag
    that is always on carries no information at all.
    """
    seed(db_session, [("done-tx-b", 3), ("done-tx-a", 4)])
    knobs(recent_max_scan_rows=10_000, recent_scan_chunk_rows=5)

    cache = AuditLogCache()
    cache.load_initial(db_session, limit_groups=50)

    assert [g["transaction_id"] for g in cache.groups] == ["done-tx-a", "done-tx-b"]
    assert cache.truncated is False
    assert cache.next_cursor is None


def test_c_group_order_and_counts_match_an_independent_query(db_session, knobs):
    """ALARM FOR: a wrong sort key in the aggregate, or a lost/duplicated count.

    The oracle is deliberately NOT the walk: it is one straightforward
    `GROUP BY` over the whole table. A self-consistent walk that agrees only
    with itself would pass any check built from its own machinery.
    """
    shape = [("ord-tx-e", 7), ("ord-tx-d", 1), ("ord-tx-c", 12),
             ("ord-tx-b", 3), ("ord-tx-a", 5)]
    seed(db_session, shape)
    knobs(recent_max_scan_rows=10_000, recent_scan_chunk_rows=4)

    cache = AuditLogCache()
    cache.load_initial(db_session, limit_groups=10)

    oracle = db_session.query(
        models.AuditLog.transaction_id,
        sa.func.count().label("n"),
    ).filter(models.AuditLog.table_name == TABLE)\
     .group_by(models.AuditLog.transaction_id)\
     .order_by(sa.func.max(models.AuditLog.id).desc()).all()

    assert [g["transaction_id"] for g in cache.groups] == [row[0] for row in oracle]
    assert [g["total_count"] for g in cache.groups] == [row[1] for row in oracle]
    # And the chunk boundaries did not lose or duplicate a row on the way.
    assert sum(g["total_count"] for g in cache.groups) == sum(n for _, n in shape)


def test_d_the_kept_logs_are_capped_but_the_count_is_not(db_session, knobs):
    """ALARM FOR: hydration growing with the transaction.

    A bulk transaction is the case that made the first call cost minutes. The
    projection must report its true size while modelling only the handful of
    rows it actually keeps - otherwise pydantic is back on the critical path
    with a bill proportional to the ingestion.
    """
    seed(db_session, [("cap-tx-a", 40)])
    knobs(recent_max_scan_rows=10_000, recent_scan_chunk_rows=100,
          recent_logs_per_group=6)

    cache = AuditLogCache()
    cache.load_initial(db_session, limit_groups=10)

    group = cache.groups[0]
    assert group["total_count"] == 40
    assert len(group["logs"]) == 6
    # Newest first, and they are the NEWEST six - not the first six the scan met
    # in some other order.
    ids = [log.id for log in group["logs"]]
    assert ids == sorted(ids, reverse=True)
    newest = db_session.query(models.AuditLog.id)\
        .filter(models.AuditLog.transaction_id == "cap-tx-a")\
        .order_by(models.AuditLog.id.desc()).limit(6).all()
    assert ids == [row[0] for row in newest]


def test_e_the_route_publishes_the_two_words(client, db_session, knobs):
    """ALARM FOR: the fact never reaching the wire, in either channel.

    The projection can know perfectly well that it gave up and still leave the
    caller believing it received all of history. The route is where that stops
    being an internal detail.

    THE BODY IS AN ENVELOPE, AND THE HEADERS ARE STILL PUBLISHED. The body was a
    bare list until 2026-08-11 - not because that was the right shape, but
    because client2 iterated it directly and a body envelope broke the history
    panel outright, so the headers were the whole channel. Both are asserted
    here: dropping the envelope silently un-does the flip, and dropping the
    headers silently breaks whatever already reads them.
    """
    seed(db_session, [("hdr-tx-c", 8), ("hdr-tx-b", 8), ("hdr-tx-a", 8)])
    knobs(recent_max_scan_rows=10, recent_scan_chunk_rows=5)
    audit_cache.audit_cache.__init__()  # a fresh projection for this request

    response = client.get("/audit_logs/recent?limit_groups=3")

    assert response.status_code == 200
    assert response.headers["x-audit-truncated"] == "true"
    assert response.headers.get("x-audit-next-cursor")

    body = response.json()
    assert isinstance(body, dict), \
        "the body is an envelope, not a bare list - see schemas.AuditLogGroupPage"
    assert body["truncated"] is True
    assert body["next_cursor"] == response.headers["x-audit-next-cursor"], \
        "the two channels must name the SAME position, or one of them is lying"
    # The list is `groups`, NOT `logs`: this route returns transaction groups and
    # each of them carries a `logs` of its own.
    assert "logs" not in body
    assert isinstance(body["groups"], list) and body["groups"]
    assert body["returned"] == len(body["groups"])
    assert body["limit_groups"] == 3
    # The envelope WRAPS the groups; it does not reshape them. A client reading
    # `body.groups` must find exactly what it used to find in the bare list.
    for g in body["groups"]:
        assert {"transaction_id", "total_count", "summary_columns", "logs"} <= set(g)


def test_e2_an_exhausted_projection_says_so_in_both_channels(client, db_session, knobs):
    """ALARM FOR: `truncated` hard-wired on in the envelope.

    `test_b` pins this on the projection; this pins it on the WIRE, because the
    route composes the envelope by hand and a flag that is always true carries
    no information at all. It is also the only place `next_cursor: null` is
    scored - a header simply goes missing, so its absence proves nothing about
    the body.
    """
    seed(db_session, [("full-tx-b", 3), ("full-tx-a", 4)])
    knobs(recent_max_scan_rows=10_000, recent_scan_chunk_rows=5)
    audit_cache.audit_cache.__init__()

    body = client.get("/audit_logs/recent?limit_groups=50").json()

    assert [g["transaction_id"] for g in body["groups"]] == ["full-tx-a", "full-tx-b"]
    assert body["truncated"] is False
    assert body["next_cursor"] is None
    assert body["returned"] == 2
    assert body["limit_groups"] == 50


def test_g_a_row_with_no_timestamp_stops_the_walk_instead_of_restarting_it(
        db_session, knobs):
    """ALARM FOR: the walk restarting from the top and counting a lap twice.

    A null-stamped row has no encodable position. If one becomes a chunk edge,
    the cursor is `None`, `None` reads as "no cursor", and the walk starts AT
    THE TOP OF THE TABLE again - counting the head rows once per lap until the
    ceiling stops it. Not a hang: worse, because it returns an answer.

    TWO THINGS THIS TEST HAD TO GET RIGHT, both learned by watching it stay
    silent against code that was genuinely broken:

    1. `timestamp=None` on the ORM does NOT store a NULL. The column carries a
       `server_default`, so SQLAlchemy omits it from the INSERT and the database
       fills it in. The rows have to be inserted as raw SQL to be null.
    2. SQLite sorts NULLs LAST under DESC and PostgreSQL sorts them FIRST, so on
       the suite's database a null-stamped row can never be the FIRST chunk's
       edge - the one chunk that has no cursor to filter it out. The order is
       therefore pinned to PostgreSQL's for this test; without that it passes
       against the broken code, on a hazard that only production would meet.
    """
    seed(db_session, [("null-tx-b", 4), ("null-tx-a", 4)])
    # One of the unstamped rows belongs to a transaction the walk WILL discover,
    # so hydration is forced to meet it too: `AuditLogResponse.timestamp` is a
    # required `datetime`, and a null reaching it is a 500 rather than a wrong
    # number.
    db_session.execute(sa.text(
        "INSERT INTO audit_logs (table_name, row_id, column_name, new_value, "
        "source_name, updated_by, transaction_id, timestamp) VALUES "
        f"('{TABLE}', 'nul-0', 'value', '\"v\"', 'p', 's', 'null-stamp-tx', NULL), "
        f"('{TABLE}', 'nul-1', 'value', '\"v\"', 'p', 's', 'null-tx-a', NULL)"))
    db_session.commit()

    # PostgreSQL's ordering for `DESC`, which is the ordering production walks.
    monkey_order = lambda m: (sa.nulls_first(m.timestamp.desc()), m.id.desc())
    original = audit_history.order_desc
    audit_history.order_desc = monkey_order
    try:
        knobs(recent_max_scan_rows=10_000, recent_scan_chunk_rows=2)
        cache = AuditLogCache()
        cache.load_initial(db_session, limit_groups=50)
    finally:
        audit_history.order_desc = original

    counted = {g["transaction_id"]: g["total_count"] for g in cache.groups}
    assert counted.get("null-tx-a") == 4
    assert counted.get("null-tx-b") == 4
    assert sum(counted.values()) == 8, \
        f"the walk counted rows more than once: {counted}"
    assert cache.scanned_rows == 8


def test_f_a_malformed_knob_falls_back_instead_of_taking_the_scan_down(knobs, capsys):
    """ALARM FOR: a typo in config silently becoming a number.

    `True` is an `int` in Python. A ceiling of 1 is not a ceiling, and it would
    turn every first call into a one-row answer that still claims to be history.
    """
    knobs(recent_max_scan_rows=True, recent_scan_chunk_rows=-5,
          recent_logs_per_group=250)
    resolved = audit_cache.resolve_recent_settings()

    assert resolved["recent_max_scan_rows"] == \
        audit_cache.RECENT_DEFAULTS["recent_max_scan_rows"]
    assert resolved["recent_scan_chunk_rows"] == \
        audit_cache.RECENT_DEFAULTS["recent_scan_chunk_rows"]
    assert resolved["recent_logs_per_group"] == 250
    assert "must be a positive integer" in capsys.readouterr().out
