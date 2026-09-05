# -*- coding: utf-8 -*-
"""One test that crosses the seam: write the marker, then sweep for it.

The undelivered-notification marker is written by `record_undelivered_notification` and
collected by `sweep_undelivered_broadcasts`, and the two used to spell its three values
independently. Five tests cover the sweep - and every one of them hand-builds its own row,
so the writer could change any of the three and all five would stay green while the marker
sat in the database forever and the screen never learned. That silence IS the incident
this mechanism exists to prevent.

⛔ THE FIVE ARE NOT TOUCHED. They measure the sweep and they are right about it. This is
the test that was missing: the one that goes through both sides.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import event_constants                                           # noqa: E402
import internal_event_client                                     # noqa: E402
from database import models                                      # noqa: E402


def marker_row(db):
    """The row THIS test wrote, selected by what makes it a marker."""
    rows = (db.query(models.DatabaseOutbox)
            .filter(models.DatabaseOutbox.event_type
                    == event_constants.EVENT_BROADCAST_RECOVERY)
            .order_by(models.DatabaseOutbox.id.desc()).all())
    assert rows, "the writer produced no marker at all"
    return rows[0]


def test_a_marker_written_by_the_writer_is_found_by_the_sweeper(db_session):
    """🔴 THE SEAM. Not "does the sweeper work" and not "does the writer work" - does what
    one produces match what the other looks for."""
    assert internal_event_client.record_undelivered_notification(
        lambda: db_session, "dt_map", "/internal/events/broadcast", "timeout") is True
    db_session.flush()

    found = (db_session.query(models.DatabaseOutbox)
             .filter(models.DatabaseOutbox.processed_chain
                     == event_constants.UNDELIVERED_MARKER_PROCESSED_CHAIN,
                     models.DatabaseOutbox.status
                     == event_constants.UNDELIVERED_MARKER_STATUS,
                     models.DatabaseOutbox.broadcast_at.is_(None))
             .all())
    assert len(found) == 1, "the sweeper's own filter does not match what the writer wrote"
    assert found[0].table_name == "dt_map"
    assert found[0].payload["marker"] == event_constants.UNDELIVERED_MARKER_TAG


def test_the_writer_and_the_sweeper_read_the_same_names(db_session):
    """The seam is held by shared constants rather than by two matching literals, so a
    change on one side cannot leave the other behind."""
    import inspect

    import chain_ingestion_worker as worker

    sweeper = inspect.getsource(worker.sweep_undelivered_broadcasts)
    writer = inspect.getsource(internal_event_client.record_undelivered_notification)
    for name in ("UNDELIVERED_MARKER_PROCESSED_CHAIN", "UNDELIVERED_MARKER_STATUS"):
        assert name in sweeper, "the sweeper spells %s by hand again" % name
    assert "UNDELIVERED_MARKER_STATUS" in writer, "the writer spells the status by hand again"


def test_the_marker_is_left_unbroadcast_on_purpose(db_session):
    """`broadcast_at` NULL is the marker itself - the sweeper's whole selector. A writer
    that stamped it would produce a row nothing ever collects."""
    internal_event_client.record_undelivered_notification(
        lambda: db_session, "dt_map", "/internal/events/broadcast", "timeout")
    db_session.flush()
    # 🔴 SELECT THE ROW, DO NOT TAKE THE FIRST ONE. An unordered `.first()` picks whatever
    # the table hands back - it picked a different row here and the assertion failed
    # against a fact about somebody else's data.
    row = marker_row(db_session)
    assert row.broadcast_at is None


def test_the_event_type_keeps_it_out_of_the_data_path(db_session):
    """It must not be re-run as a data transaction, and the type is what says so."""
    internal_event_client.record_undelivered_notification(
        lambda: db_session, "dt_map", "/internal/events/broadcast", "timeout")
    db_session.flush()
    assert marker_row(db_session).event_type == event_constants.EVENT_BROADCAST_RECOVERY
