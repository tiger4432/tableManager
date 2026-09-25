# -*- coding: utf-8 -*-
""""How long has this been failing" has to be answerable from the response.

Client measurement, 2026-09-04: the groups come newest-first and each group's `failed_at`
is the MAX over its own events, so it says when that group LAST failed. Nothing in the
response distinguishes "one failure a minute ago" from "twenty, for four days" - and the
last page cannot supply it either, because the oldest group's timestamp is also a max.

One field answers it, taken over the WHOLE set rather than a page, so the answer does not
change as somebody pages through.

⛔ AND IT IS null WHEN THERE ARE NO FAILURES. Not 0, not "now". The screen has to be able
to tell "nothing has failed" from "I do not know", and collapsing those two into one
pixel is the defect this whole day was about.
"""
import datetime
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main                                                      # noqa: E402
from database import models                                      # noqa: E402


def failed_row(db, minutes_ago, tx):
    when = datetime.datetime(2026, 9, 4, 12, 0) - datetime.timedelta(minutes=minutes_ago)
    row = models.DatabaseOutbox(
        event_uuid=str(uuid.uuid4()), event_type="CREATE", table_name="t",
        payload={"transaction_id": tx}, status="FAILED", retry_count=3,
        processed_chain=True, created_at=when)
    db.add(row)
    db.flush()
    return row


def test_the_oldest_failure_is_reported_over_the_whole_set(db_session):
    """Three groups, and the answer is the oldest of ALL of them - not of this page."""
    failed_row(db_session, 5, "tx_recent")
    failed_row(db_session, 4000, "tx_ancient")     # the answer
    failed_row(db_session, 60, "tx_middle")
    db_session.flush()

    out = main.get_failed_outbox_events(page=1, limit=1, db=db_session)

    assert out["oldest_failed_at"] is not None
    assert out["oldest_failed_at"].startswith("2026-09-01"), out["oldest_failed_at"]
    assert out["total"] == 3
    assert len(out["data"]) == 1, "the page is still one group"


def test_the_answer_does_not_change_as_you_page(db_session):
    """🔴 THE POINT OF TAKING IT OVER THE SET. A per-page minimum would move, and a
    number that moves while you page cannot be read as "since when"."""
    for i in range(5):
        failed_row(db_session, (i + 1) * 100, "tx_%d" % i)
    db_session.flush()

    first = main.get_failed_outbox_events(page=1, limit=2, db=db_session)
    last = main.get_failed_outbox_events(page=3, limit=2, db=db_session)
    assert first["oldest_failed_at"] == last["oldest_failed_at"]


def test_no_failures_answers_null_rather_than_a_time(db_session):
    out = main.get_failed_outbox_events(page=1, limit=10, db=db_session)
    assert out["total"] == 0
    assert out["oldest_failed_at"] is None, \
        "an empty set was given a timestamp; 'nothing failed' now reads as 'failed then'"


def test_the_field_is_shaped_like_the_others_in_this_response(db_session):
    """Same format as the sibling timestamps in this same payload. A second time format
    in one response is a second thing for the screen to get wrong."""
    failed_row(db_session, 10, "tx_one")
    db_session.flush()

    out = main.get_failed_outbox_events(page=1, limit=10, db=db_session)
    group = out["data"][0]
    assert out["oldest_failed_at"] == group["events"][0]["created_at"], \
        "the new field is not formatted like the created_at beside it"


def test_the_failures_fold_to_one_line_per_table_kind_and_day(db_session):
    """총괄 36dff3b6a (소유자 「ㄴ」) — one burst of a table and kind on one day is one line, and
    the Chain tab and the Overview read this same answer."""
    def at(day, hour, table, kind, retry):
        db_session.add(models.DatabaseOutbox(
            event_uuid=str(uuid.uuid4()), event_type=kind, table_name=table, payload={},
            status="FAILED", retry_count=retry, processed_chain=True,
            created_at=datetime.datetime(2026, 9, day, hour, 0)))
    for hour in (0, 1, 2):
        at(23, hour, "dt_inventory", "EDIT", 1)
    at(24, 5, "dt_inventory", "EDIT", 2)
    at(23, 3, "wafer", "CREATE", 0)
    db_session.add(models.DatabaseOutbox(      # not a failure: not in the summary
        event_uuid=str(uuid.uuid4()), event_type="EDIT", table_name="dt_inventory",
        payload={}, status="SUCCESS", processed_chain=True,
        created_at=datetime.datetime(2026, 9, 23, 4, 0)))
    db_session.flush()

    lines = main.get_failed_outbox_events(page=1, limit=1, db=db_session)["summary"]

    assert [(l["table_name"], l["event_type"], l["day"], l["count"], l["retry_max"])
            for l in lines] == [("dt_inventory", "EDIT", "2026-09-24", 1, 2),
                                ("wafer", "CREATE", "2026-09-23", 1, 0),
                                ("dt_inventory", "EDIT", "2026-09-23", 3, 1)]
    assert lines[2]["first_at"] < lines[2]["last_at"]


def test_the_day_does_not_move_with_the_postgresql_session_zone():
    """23:30 UTC is the next morning in a KST session; the day is the UTC day either way,
    like the `first_at` beside it. sqlite has no session zone, so a scratch schema."""
    from conftest import _declared_as_test_database, _resolve_pg_test_url
    from tests.support.isolated_pg import scratch_connect_args

    url, reason = _resolve_pg_test_url()
    if url is None:
        pytest.skip(reason)
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import NullPool

    scratch = "assy_pytest_failed_day_36df"
    with _declared_as_test_database(url):
        maker = create_engine(url, poolclass=NullPool)
        try:
            with maker.begin() as conn:
                conn.execute(text('DROP SCHEMA IF EXISTS "%s" CASCADE' % scratch))
                conn.execute(text('CREATE SCHEMA "%s"' % scratch))
        except OperationalError as exc:
            pytest.skip("PostgreSQL is not reachable: %s" % str(exc).strip().splitlines()[0])
        engine = create_engine(url, poolclass=NullPool,
                               connect_args=scratch_connect_args(scratch))
        try:
            models.DatabaseOutbox.__table__.create(engine)
            with Session(engine) as db:
                db.execute(text("SET TIME ZONE 'Asia/Seoul'"))
                db.add(models.DatabaseOutbox(
                    event_uuid=str(uuid.uuid4()), event_type="EDIT", table_name="t",
                    payload={}, status="FAILED", retry_count=1, processed_chain=True,
                    created_at=datetime.datetime(2026, 9, 22, 23, 30,
                                                 tzinfo=datetime.timezone.utc)))
                db.flush()
                line, = main.get_failed_outbox_events(page=1, limit=1, db=db)["summary"]
                assert (line["day"], line["first_at"]) == ("2026-09-22",
                                                           "2026-09-22 23:30:00+00:00")
        finally:
            with maker.begin() as conn:
                conn.execute(text('DROP SCHEMA IF EXISTS "%s" CASCADE' % scratch))
            engine.dispose()
            maker.dispose()
