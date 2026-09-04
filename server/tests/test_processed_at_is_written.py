# -*- coding: utf-8 -*-
""""When did this stop being work" had a column, a reader, and no writer.

`database_outbox.processed_at` is declared on the model and published by
`GET /admin/outbox/failed`, and measured on 2026-09-04 nothing ever assigned it: a
thousand-row run left every row, successes included, with NULL. So the interval between
"the mapper finished" and "the event was marked done" had no observation point at all,
and the screen reading that column would have answered "unknown" forever.

⛔ AND IT IS ONE PLACE, NOT FOUR. "Processed" was hand-written at four sites; adding a
timestamp to each would have made eight copies of one judgement and left the fifth
branch to forget. `mark_processed` is that one place, and these tests are what keeps it
one.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import chain_ingestion_worker as worker                          # noqa: E402


class FakeEvent:
    """Just the three columns the function touches."""
    def __init__(self):
        self.status = "PENDING"
        self.processed_chain = False
        self.processed_at = None


def test_marking_processed_sets_the_status_the_flag_and_the_time():
    e = FakeEvent()
    worker.mark_processed(e, "SUCCESS")
    assert e.status == "SUCCESS"
    assert e.processed_chain is True
    assert e.processed_at is not None, "the column that had no writer still has none"


def test_a_failure_is_stamped_too():
    """🔴 THE HALF THAT WOULD HAVE BEEN MISSED. The column means "stopped being worked
    on", and a permanently failed event has stopped. `/admin/outbox/failed` is the one
    route that publishes it, so leaving failures blank makes that route answer "unknown"
    about every row it serves."""
    e = FakeEvent()
    worker.mark_processed(e, "FAILED")
    assert e.status == "FAILED"
    assert e.processed_chain is True
    assert e.processed_at is not None


def test_the_time_comes_from_the_database_clock():
    """`created_at` is a server default. Reading one end from Python's clock and the
    other from the server's makes the difference a measurement of clock skew."""
    from sqlalchemy.sql.functions import Function

    e = FakeEvent()
    worker.mark_processed(e, "SUCCESS")
    assert isinstance(e.processed_at, Function), \
        f"processed_at was set from the local clock: {e.processed_at!r}"


def test_nothing_marks_an_event_processed_except_this_function():
    """🔴 GATE 1, AS AN ASSERTION: the number of places is ONE.

    Text is the SUBJECT here, not a proxy for behaviour: the claim is about how many
    sites in this file exist, which is a fact about the file. A fifth branch that
    hand-writes the flag again fails here, which is exactly when somebody would
    otherwise forget the timestamp.
    """
    import inspect
    import re

    source = inspect.getsource(worker)
    assignments = [m for m in re.finditer(r"^\s*\w+\.processed_chain\s*=\s*True",
                                          source, re.MULTILINE)]
    assert len(assignments) == 1, (
        f"{len(assignments)} places set processed_chain directly; there must be exactly "
        f"one (inside mark_processed) or the timestamp will be forgotten by one of them")

    body = inspect.getsource(worker.mark_processed)
    assert "processed_chain = True" in body, \
        "the single assignment is no longer the one inside mark_processed"
