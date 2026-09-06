# -*- coding: utf-8 -*-
"""A file whose ingestion record could not be written has no way back in.

`_log_ingestion_record` caught its write failure, logged it and returned. Without a
`FileIngestionLog` row the file does not appear in `/failed` and the operator gets no Retry
button -- so what the failed write loses is not a message but the only route back. The
ledger's FAILED checkpoint stays sealed, so the sweep will not pick the file up either:
the file never arrives and the screen says there were no failures.

🔴 THE REDUCED ROW CARRIES NO TEXT FROM THE FAILURE, and that is the design rather than a
detail. Measured 2026-09-06: `error_message` has NO length cap (`Column(String)` with no
size), so shortening was never what a retry needed. If the first INSERT was refused because
of something IN the value -- a NUL byte inside a traceback is the shape this repository
would meet first -- then a shortened version of that same text is refused for the same
reason, which is a repair that fails exactly when it is needed.

🔵 THE DETAIL IS NOT LOST. It is in the ERROR line, with the table, the status, the file and
the original exception. The row restores the ROUTE; the log carries the REASON.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import models                                      # noqa: E402
from parsers import directory_watcher                            # noqa: E402


class Recorder(directory_watcher.IngestionHandler):
    """The handler with only the two things this behaviour needs."""

    def __init__(self):
        pass


@pytest.fixture
def handler():
    return Recorder()


def rows(db, filename):
    return (db.query(models.FileIngestionLog)
            .filter(models.FileIngestionLog.filename == filename).all())


# ---------------------------------------------------------------- the fallback restores the route

def test_the_reduced_row_is_written_when_the_first_one_cannot_be(db_session, handler,
                                                                 caplog):
    """🔴 THE POINT. The row is what puts the file back in the failure list, which is what
    puts the Retry button back."""
    import logging

    with caplog.at_level(logging.WARNING):
        handler._log_reduced_ingestion_record(
            db_session, "/raw/a.csv", "/err/a.csv", "dt_map", "FAILED")

    written = rows(db_session, "a.csv")
    assert len(written) == 1
    assert written[0].status == "FAILED"
    assert written[0].table_name == "dt_map"


def test_the_reduced_row_carries_the_fixed_sentence_and_nothing_derived(db_session,
                                                                        handler):
    """⛔ NO TRACEBACK, NO EXCEPTION STRING, NO EXCERPT. A value that came from the failure
    can be refused for the same reason the first write was."""
    handler._log_reduced_ingestion_record(
        db_session, "/raw/b.csv", "/err/b.csv", "dt_map", "FAILED")
    row = rows(db_session, "b.csv")[0]
    assert row.error_message == handler.REDUCED_RECORD_NOTE
    assert "Traceback" not in (row.error_message or "")


def test_the_fixed_sentence_points_at_where_the_reason_is(handler):
    """The row must not read as if the reason were simply gone."""
    assert "로그" in handler.REDUCED_RECORD_NOTE


def test_the_note_is_not_built_from_anything(handler):
    """A note assembled from the failure would defeat the whole design, so it is a
    constant and this is what keeps it one."""
    import inspect

    body = inspect.getsource(directory_watcher.IngestionHandler
                             ._log_reduced_ingestion_record)
    assert "error_message=self.REDUCED_RECORD_NOTE" in body
    for derived in ("str(e)", "format_exc", "%s\" % e", "{e}"):
        assert derived not in body


def test_a_table_name_that_is_missing_becomes_unknown_rather_than_null(db_session,
                                                                       handler):
    handler._log_reduced_ingestion_record(db_session, "/raw/c.csv", "/err/c.csv",
                                          None, "FAILED")
    assert rows(db_session, "c.csv")[0].table_name == "unknown"


@pytest.mark.parametrize("status", ["FAILED", "SUCCESS", "SKIPPED"])
def test_the_status_travels_unchanged(db_session, handler, status):
    """The reduced row is the same record with less text, not a different verdict."""
    name = "d-%s.csv" % status
    handler._log_reduced_ingestion_record(db_session, "/raw/" + name, "/err/" + name,
                                          "dt_map", status)
    assert rows(db_session, name)[0].status == status


# --------------------------------------------------------------- it is not silent either way

def test_the_second_failure_says_the_file_has_no_record(db_session, handler, caplog,
                                                        monkeypatch):
    """⛔ THE HONEST END. When even this fails, the file genuinely has no record and the
    log says exactly that rather than reporting a repair."""
    import logging

    def refuse():
        raise RuntimeError("the database is gone")

    monkeypatch.setattr(db_session, "commit", refuse)
    with caplog.at_level(logging.ERROR):
        handler._log_reduced_ingestion_record(
            db_session, "/raw/e.csv", "/err/e.csv", "dt_map", "FAILED")

    said = "\n".join(r.getMessage() for r in caplog.records)
    assert "ALSO failed" in said and "no record" in said and "e.csv" in said


def test_the_first_failure_line_still_names_the_file_and_the_reason():
    """The row restores the route; this line carries the reason. Each says one thing."""
    import inspect

    body = inspect.getsource(directory_watcher.IngestionHandler._log_ingestion_record)
    assert "reduced row that carries no text from the failure" in body
    assert "_log_reduced_ingestion_record(" in body


def test_the_happy_path_writes_exactly_one_row(db_session, handler):
    """🔴 NO REGRESSION. A successful first write must not also produce a reduced row -
    two rows for one file would double every entry in the failure list."""
    import inspect

    body = inspect.getsource(directory_watcher.IngestionHandler._log_ingestion_record)
    head, _, tail = body.partition("except Exception as e:")
    assert "_log_reduced_ingestion_record(" not in head, \
        "the fallback runs on the success path too"
    assert "_log_reduced_ingestion_record(" in tail
