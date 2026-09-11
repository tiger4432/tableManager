# -*- coding: utf-8 -*-
"""The operator's way out of a re-expansion flood (S-172).

🔴 WHAT THIS GUARDS. A quarantined chunk re-expands into 1,000 per-row events so the
poison row can be narrowed. When many chunks quarantine, that arithmetic inverts: ~660,000
per-row events at a group's plumbing cost is DAYS for rows that take ~2 hours collapsed.
The script turns the queue back into collapsed work, and the two properties that make it
safe to run on a production queue are pinned here: nothing is deleted, and every skipped
event says who skipped it and why.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest                                                        # noqa: E402
from sqlalchemy import text                                          # noqa: E402

from database.models import DatabaseOutbox                           # noqa: E402
from scripts import outbox_triage                                    # noqa: E402
from utils.payload_helper import get_payload_dict                    # noqa: E402


def _per_row_event(db, table, i, reexpanded=True):
    ev = DatabaseOutbox(
        event_uuid="triage-%s-%03d" % (table, i),
        event_type="EDIT",
        table_name=table,
        payload={"transaction_id": "chain_tx#row#%03d" % i,
                 "data": {"row_id": "r%03d" % i},
                 **({"reexpanded_from": "chunk-1"} if reexpanded else {})},
    )
    db.add(ev)
    return ev


@pytest.fixture()
def flooded(db_session):
    for i in range(5):
        _per_row_event(db_session, "triage_tbl", i)
    collapsed = DatabaseOutbox(
        event_uuid="triage-collapsed",
        event_type="EDIT",
        table_name="triage_tbl",
        payload={"transaction_id": "chain_tx", "row_ids": ["r900", "r901"]},
    )
    db_session.add(collapsed)
    db_session.commit()
    return db_session


def test_count_splits_the_queue_by_shape_and_cause(flooded, capsys):
    """① The operator's first question: what IS this queue made of."""
    buckets = outbox_triage.count(flooded, "triage_tbl")

    per_row = {k: v for k, v in buckets.items() if k[1] == "per-row"}
    collapsed = {k: v for k, v in buckets.items() if k[1] == "collapsed"}
    assert sum(per_row.values()) == 5
    assert sum(collapsed.values()) == 1
    assert any(k[2] == "quarantine re-expansion" for k in per_row), (
        "the cause is the point - 're-expanded' and 'original' need different answers")


def test_cancel_skips_without_deleting_and_says_who(flooded):
    """② ⛔ NOT A DELETE. The row stays, carrying who skipped it and why."""
    before = flooded.query(DatabaseOutbox).count()

    outbox_triage.cancel(flooded, "triage_tbl", apply=True)

    assert flooded.query(DatabaseOutbox).count() == before, "nothing may be deleted"
    skipped = [e for e in flooded.query(DatabaseOutbox).all()
               if get_payload_dict(e).get(outbox_triage.CANCEL_MARK)]
    assert len(skipped) == 5, "only the per-row events"
    for e in skipped:
        assert e.processed_chain is True
        p = get_payload_dict(e)
        assert p[outbox_triage.CANCEL_MARK] == outbox_triage.OPERATOR
        assert p[outbox_triage.CANCEL_REASON], "a skip with no reason is an unexplained gap"
    # the collapsed event is untouched - it was never the problem
    coll = flooded.query(DatabaseOutbox).filter(
        DatabaseOutbox.event_uuid == "triage-collapsed").one()
    assert coll.processed_chain is not True


def test_a_dry_run_changes_nothing(flooded):
    """The default. An operator script that acts before being asked is the defect."""
    outbox_triage.cancel(flooded, "triage_tbl", apply=False)

    assert not [e for e in flooded.query(DatabaseOutbox).all()
                if get_payload_dict(e).get(outbox_triage.CANCEL_MARK)]


def test_cancel_refuses_without_the_blast_radius_written_down():
    """--cancel without --table/--per-row is refused: the scope is stated, not assumed."""
    assert outbox_triage.main(["--cancel"]) == 2
    assert outbox_triage.main(["--cancel", "--table", "triage_tbl"]) == 2


def test_replay_cancelled_finds_exactly_the_rows_that_were_skipped(flooded):
    """③ The round trip: what was skipped is what comes back, and no row is lost."""
    outbox_triage.cancel(flooded, "triage_tbl", apply=True)

    found = outbox_triage.replay_cancelled(flooded, "triage_tbl", apply=False)

    assert found == 5, "every skipped event's row must be offered back for replay"
