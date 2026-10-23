# -*- coding: utf-8 -*-
"""총괄 49792d3f6 B (응용 감사 660377a92): the watcher claims a row only while it is still PENDING_RETRY - one conditional
statement (`run_watcher.claim_retry`) - so a row the cancel put back after the poller read its list is not read."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import run_watcher                                                    # noqa: E402
from database import models                                           # noqa: E402
from ingestion import checkpoint, reread                              # noqa: E402


def test_a_row_cancelled_after_the_list_was_read_is_not_claimed(db_session):
    rows = [checkpoint.note_file(db_session, "t", "C:/x/" + n, status="FAILED") for n in ("a.csv", "b.csv")]
    db_session.commit()
    reread.mark_for_reread(db_session, rows)
    listed = db_session.query(models.FileChecklist).filter_by(status="PENDING_RETRY").order_by(
        models.FileChecklist.id).all()                                 # the poller's list
    assert [log.filename for log in listed] == ["a.csv", "b.csv"], "CANARY: both waiting"
    said = reread.cancel_reread(db_session, apply=True)                # the cancel lands after the list
    assert said["count"] == 2
    assert [run_watcher.claim_retry(db_session, log) for log in listed] == [False, False]
    db_session.expire_all()
    assert {log.filename: log.status for log in db_session.query(models.FileChecklist)} == {
        "a.csv": "FAILED", "b.csv": "FAILED"}
    reread.mark_for_reread(db_session, [listed[0]])
    assert run_watcher.claim_retry(db_session, listed[0]) and listed[0].status == "PENDING"
