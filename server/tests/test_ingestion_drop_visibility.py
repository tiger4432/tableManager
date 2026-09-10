"""[Drop visibility] A dropped column must leave a record, without becoming noise.

`_send_to_upsert` filters each row down to the loadable columns BEFORE handing it to
`crud`, so `crud._warn_undeclared_column_once` can never fire for anything the filter
removes. The write still reports SUCCESS with an empty error_message, so today a drop
produces no evidence of any kind.

Dropping is frequently the CORRECT outcome - a file carrying fields of a superseded
scheme should not grow the table. What these tests pin is narrower: an operator must be
able to tell that outcome apart from a new or misspelled column silently going nowhere.

The shape under test is `개별 침묵 + 명명된 총계`:
  - nothing per row or per cell;
  - WARNING once per (table, column) per process, on first sighting;
  - INFO per file with names and counts, so 0 dropped and 200 dropped never look alike.
"""
import logging
import os
import sys

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)
parsers_dir = os.path.join(server_dir, "parsers")
if parsers_dir not in sys.path:
    sys.path.insert(0, parsers_dir)

import directory_watcher as dw  # noqa: E402

WATCHER_LOGGER = "Watcher.DirectoryWatcher"

# Deliberately not a real table. The lesson from the `bonding_log` incident: a fake
# table name that collides with the user's gitignored config poisons the shared
# in-memory sqlite at import time.
FAKE_TABLE = "dropvis_test_table"
FAKE_TABLE_INFO = {
    "business_key": "pkg_id",
    # 🔴 `column_types` IS WHAT SAYS A COLUMN EXISTS, and existence is what a write is
    # filtered by since S-119 (판정 09-10 12:20). This entry used to declare the table by
    # what a SCREEN shows, which now means "no column of this table exists" and drops
    # every field of every file - so the counts these cases pin came out nine instead of
    # four. `display_columns` stays because the showing axis is still real; it is simply
    # not the one this filter reads.
    "display_columns": ["pkg_id", "base", "x", "y", "leg"],
    "column_types": {"pkg_id": "string", "base": "string", "x": "number",
                     "y": "number", "leg": "string"},
}


class _StubSession:
    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


class _StubCrud:
    # 🔴 THE REAL ONE, NOT A STUB ANSWER (S-119). Which columns may be written is the
    # subject of these cases, so a stub deciding it here would be a second spelling of the
    # loadable axis - free to agree with the assertions while the product disagreed.
    from database import crud as _real_crud
    loadable_columns = staticmethod(_real_crud.loadable_columns)

    @staticmethod
    def apply_batch_updates(_db, _t_name, batch_obj):
        # results, changed_cells, created_logs, deleted_row_ids
        return [], [], [], []


@pytest.fixture
def watcher(monkeypatch):
    """A handler wired to stubs - no DB, no heartbeat file."""
    monkeypatch.setattr(dw, "SessionLocal", _StubSession)
    monkeypatch.setattr(dw, "crud", _StubCrud)
    monkeypatch.setattr(dw.heartbeat, "beat", lambda *a, **k: None)
    # Process-lifetime registry: isolate each test from the ones before it.
    monkeypatch.setattr(dw, "_dropped_column_announced", {})

    handler = dw.IngestionHandler.__new__(dw.IngestionHandler)
    handler.scripts_path = ""
    handler.on_progress_callback = None
    handler.on_refresh_callback = None
    return handler


def _ingest(handler, rows, filename):
    handler._send_to_upsert(
        rows, uploader="tester", filename=filename,
        t_name=FAKE_TABLE, table_info=FAKE_TABLE_INFO,
    )


def _lines(caplog, level):
    return [r.getMessage() for r in caplog.records
            if r.name == WATCHER_LOGGER and r.levelno == level]


def _clean_rows(n=3):
    return [{"pkg_id": f"P{i}", "base": "A", "x": i, "y": 1, "leg": "F"}
            for i in range(n)]


def _rows_with_dropped_columns(n=3):
    """The real bonding-map shape: header fields of a superseded scheme ride along."""
    return [{"pkg_id": f"P{i}", "base": "A", "x": i, "y": 1, "leg": "F",
             "title": "AAA", "bdie_wf": "B", "cdie_lot": "C", "cdie_wf": "D"}
            for i in range(n)]


def test_nothing_dropped_says_nothing(watcher, caplog):
    """The quiet case must stay completely quiet - no warning, no drop report."""
    with caplog.at_level(logging.DEBUG, logger=WATCHER_LOGGER):
        _ingest(watcher, _clean_rows(), "clean.csv")

    assert _lines(caplog, logging.WARNING) == []
    assert not [m for m in _lines(caplog, logging.INFO) if "undeclared column" in m]


def test_dropped_columns_are_named_and_counted(watcher, caplog):
    with caplog.at_level(logging.DEBUG, logger=WATCHER_LOGGER):
        _ingest(watcher, _rows_with_dropped_columns(200), "smart_paste.html")

    report = [m for m in _lines(caplog, logging.INFO) if "undeclared column" in m]
    assert len(report) == 1, "one named aggregate per file, no more and no less"
    line = report[0]
    for col in ("title", "bdie_wf", "cdie_lot", "cdie_wf"):
        assert f"{col}=200" in line, line
    assert "200 row(s)" in line
    assert "smart_paste.html" in line
    # 0 dropped and 200 dropped must not look the same
    assert "Dropped 4 undeclared column(s)" in line


def test_first_sighting_warns_once_then_stops_shouting(watcher, caplog):
    """Steady-state old-scheme columns spend one warning, then report at INFO only.

    This is the whole sizing decision: a log that shouts on every sweep gets trained
    away within a day, and then a genuinely new column is invisible again.
    """
    with caplog.at_level(logging.DEBUG, logger=WATCHER_LOGGER):
        _ingest(watcher, _rows_with_dropped_columns(), "file_one.html")
        first_warnings = _lines(caplog, logging.WARNING)
        caplog.clear()
        _ingest(watcher, _rows_with_dropped_columns(), "file_two.html")
        second_warnings = _lines(caplog, logging.WARNING)
        second_info = [m for m in _lines(caplog, logging.INFO) if "undeclared column" in m]

    assert len(first_warnings) == 1
    for col in ("title", "bdie_wf", "cdie_lot", "cdie_wf"):
        assert col in first_warnings[0]
    assert "file_one.html" in first_warnings[0]

    assert second_warnings == [], "an expected drop must not warn on every file"
    assert len(second_info) == 1, "but it must still be reported where someone can find it"
    assert "file_two.html" in second_info[0]


def test_a_new_column_warns_even_after_the_expected_ones_went_quiet(watcher, caplog):
    """The reason the warning exists: a misspelled or brand-new column must surface.

    After the superseded fields have burned their one warning, a fresh name still
    produces a WARNING - and it names ONLY the new column, so it is not buried in a
    repeat of the known ones.
    """
    with caplog.at_level(logging.DEBUG, logger=WATCHER_LOGGER):
        _ingest(watcher, _rows_with_dropped_columns(), "known.html")
        caplog.clear()
        rows = _rows_with_dropped_columns()
        for r in rows:
            r["bsae"] = "A"  # the misspelling of `base` this exists to catch
        _ingest(watcher, rows, "typo.html")
        warnings = _lines(caplog, logging.WARNING)

    assert len(warnings) == 1
    assert "bsae" in warnings[0]
    for known in ("title", "bdie_wf", "cdie_lot", "cdie_wf"):
        assert known not in warnings[0], "already-announced columns must not be repeated"


def test_blank_only_column_is_still_named_with_a_zero_count(watcher, caplog):
    """A column offered with nothing in it was still refused - name it, count it 0."""
    rows = [{"pkg_id": "P1", "base": "A", "x": 1, "y": 1, "leg": "F",
             "obsolete_note": "", "title": "AAA"}]
    with caplog.at_level(logging.DEBUG, logger=WATCHER_LOGGER):
        _ingest(watcher, rows, "blank.csv")

    line = [m for m in _lines(caplog, logging.INFO) if "undeclared column" in m][0]
    assert "obsolete_note=0" in line
    assert "title=1" in line


def test_report_is_capped_and_says_so(watcher, caplog, monkeypatch):
    """Column names come from the payload, so a malformed header must not grow the
    registry without limit. On saturation the truncation is announced, never silent."""
    monkeypatch.setattr(dw, "MAX_DROPPED_COLUMNS_REPORTED", 4)
    row = {"pkg_id": "P1", "base": "A", "x": 1, "y": 1, "leg": "F"}
    for i in range(20):
        row[f"junk_{i:02d}"] = "v"

    with caplog.at_level(logging.DEBUG, logger=WATCHER_LOGGER):
        _ingest(watcher, [row], "malformed.csv")

    line = [m for m in _lines(caplog, logging.INFO) if "undeclared column" in m][0]
    assert "Dropped 4 undeclared column(s)" in line
    assert "report cap 4 reached" in line
    assert "junk_19" not in line


def test_every_emitted_line_is_cp949_encodable(watcher, caplog):
    """Windows consoles here are cp949. A log line that cannot be encoded is a crash,
    not a log line - so no emoji and no U+2014 in anything this path emits."""
    with caplog.at_level(logging.DEBUG, logger=WATCHER_LOGGER):
        _ingest(watcher, _rows_with_dropped_columns(), "encoding.html")

    emitted = [r.getMessage() for r in caplog.records
               if r.name == WATCHER_LOGGER
               and ("undeclared column" in r.getMessage()
                    or "absent from the declaration are dropped" in r.getMessage())]
    assert emitted
    for msg in emitted:
        msg.encode("cp949")


# ---------------------------------------------------------------------------
# [Zero-row visibility] A refused parse must not look like a clean success.
#
# When the parser refuses a shape it returns 0 records rather than a plausible-looking
# wrong grid origin. Nothing downstream raises, so `status` is SUCCESS and
# `error_message` is empty - which made "not one cell was stored" and "processed
# normally" indistinguishable on screen. Same sizing as the drop report: silent per
# row, named once per file, in the slot that already carries this kind of news.
# ---------------------------------------------------------------------------

def test_zero_rows_is_named_in_the_detail_slot():
    detail = dw.IngestionHandler._compose_detail(0, None, has_rows=False)
    assert detail is not None, "0 rows and a clean run must not both be an empty detail"
    assert "0행" in detail
    detail.encode("cp949")


def test_rows_present_leaves_the_detail_exactly_as_before():
    """The slot already carries the F1 skip and the P2 resume note. Adding the zero-row
    reason must not perturb either, or every existing consumer shifts."""
    assert dw.IngestionHandler._compose_detail(0, None) is None
    assert dw.IngestionHandler._compose_detail(2, None) == "키 결측으로 2행 스킵"
    assert dw.IngestionHandler._compose_detail(2, None, has_rows=True) == "키 결측으로 2행 스킵"


def test_zero_rows_and_key_skip_are_both_reported():
    detail = dw.IngestionHandler._compose_detail(5, None, has_rows=False)
    assert "0행" in detail and "키 결측으로 5행 스킵" in detail
