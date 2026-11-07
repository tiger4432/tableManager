"""Lead 10-31 ② (C measured: of nine spellings of one moment in a string time column, the ledger read six and refused
three - «is not ISO 8601 … declare the format» - where the write door reads all nine): one time judgment. Text the
ledger's reader refuses and PostgreSQL reads is the moment PostgreSQL reads, on the source's declared zone - the
write door's judge (`crud.times_postgresql_reads`), asked once a page and held around the translation
(`roleframe.times_read`); the row's text is not replaced, so a source whose identity holds the time keeps its refs.

  the order    a declared format is read first; a binding with one is not asked
  a binding    a time attribute declaring its timezone reads the table
A source's own time is a datetime column (owner 11-07) - the ledger's and Latest's text time left with it.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

from ledger import roleframe

SEOUL = timezone(timedelta(hours=9))
MOMENT = datetime(2026, 9, 30, 10, 0, tzinfo=SEOUL)
SPELLINGS = ["2026-09-30 10:00:00", "2026-09-30T10:00:00", "2026-09-30 10:00", "2026-09-30T10:00:00.000",
             "2026-09-30 10:00:00+09:00", "2026-09-30T01:00:00Z",
             "2026/09/30 10:00:00", "2026.09.30 10:00:00", "20260930 100000"]
ONLY_POSTGRESQL = SPELLINGS[6:]


def test_the_board_holds_both_kinds():
    assert [s for s in SPELLINGS if roleframe.unread_time_text(s)] == ONLY_POSTGRESQL, "CANARY: three only PG reads"


def test_a_declared_format_is_read_before_the_table():
    held = {("Asia/Seoul", "20260930 100000"): MOMENT + timedelta(hours=1)}
    with roleframe.times_read(held):
        assert roleframe.aware_time("20260930 100000", "Asia/Seoul", "p", fmt="%Y%m%d %H%M%S") == MOMENT
        assert roleframe.aware_time("20260930 100000", "Asia/Seoul", "p") == MOMENT + timedelta(hours=1), \
            "control: no format - the table"
    with pytest.raises(roleframe.RoleFrameError):
        roleframe.aware_time("20260930 100000", "Asia/Seoul", "p")          # nothing held: refused as before


def test_the_table_is_keyed_by_zone():
    with roleframe.times_read({("Asia/Seoul", "2026/09/30 10:00:00"): MOMENT}):
        with pytest.raises(roleframe.RoleFrameError):
            roleframe.aware_time("2026/09/30 10:00:00", "UTC", "p")      # another zone is another moment


def test_a_time_attribute_with_its_timezone_reads_the_table(tmp_path):
    """The value binding is read at the mapper, not where occurred_at is - the table reaches both; what is asked
    names the attribute's column, and a binding that declares a format is not asked."""
    from test_a_test_run_shows_the_atoms_its_rows_became import _document, _service
    from test_the_test_run_reads_until_it_has_a_molecule import _row
    from ledger import backfill, runtime_v2
    from ledger.setup import preview_selected_cursor_batch

    source = "lot_slot_wafer"
    document = _document()
    document["entities"]["wafer@1"]["attributes"] = ["moved_at"]
    document["sources"][source]["bind"]["entities"] = {"wafer@1": {"attributes": {"moved_at": {
        "kind": "column", "column": "event_type", "timezone": "Asia/Seoul"}}}}
    setup, _index, _ = _service(tmp_path, document).active()
    plan = setup.snapshot.source_plans[source]
    frame = backfill._v2_frame([dict(_row(i), event_type="2026/09/30 10:00:00")
                                for i in range(4)])
    assert roleframe.source_times_to_ask(plan, frame) == {"Asia/Seoul": {"2026/09/30 10:00:00"}}, \
        "the attribute's column - the source's own time is a datetime"
    with pytest.raises(roleframe.RoleFrameError):
        preview_selected_cursor_batch(setup, source, frame, runtime_v2.last_cursor(plan, frame),
                                      known_registrations=())
    with roleframe.times_read({("Asia/Seoul", "2026/09/30 10:00:00"): MOMENT}):
        preview = preview_selected_cursor_batch(setup, source, frame, runtime_v2.last_cursor(plan, frame),
                                                known_registrations=())
    said = json.dumps([a.object_payload for a in runtime_v2._screened_atoms(setup.snapshot, source, preview)],
                      default=str)
    assert "moved_at" in said and MOMENT.isoformat() in said.replace(" ", "T"), said
