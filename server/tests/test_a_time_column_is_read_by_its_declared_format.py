"""A time column written as text is read by the format its declaration states (총괄 ca87ffdb3,
소유자 「원장 백필이 occurred_at 이 datetime 이 아니라고 안 됨 · yyyymmdd_hhmmss 형식」 → 「ㄱ 바인딩에
format」).

  the read      `read.occurred_at.format` (and a time binding's `format`) - text is read by THE
                parser for a declared shape, `utils.time_format.parse_occurred_at`; nothing is
                guessed: no format, no reading, exactly as before
  the check     one function for both cells - today's time written in the format and read back
                gives the same text and today's date, or the declaration is refused at save
  the default   a source that leaves `read.occurred_at` out takes its event edge's column,
                timezone - and format
"""
import copy
import os
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import setup_bundle                                          # noqa: E402
from ledger.backfill import prepare_v2_cursor_batch                      # noqa: E402
from ledger.roleframe import SOURCE_OCCURRED_AT_COLUMN                   # noqa: E402
from test_ledger_setup_bundle import (DEFAULT_CATALOG, logical_bundle,  # noqa: E402
                                      validate_bundle_errors)
from test_ledger_setup_registry import snapshot                          # noqa: E402

FORMAT = "%Y%m%d_%H%M%S"
SEOUL = timezone(timedelta(hours=9))


def _catalog():
    catalog = copy.deepcopy(DEFAULT_CATALOG)
    catalog["input_rows"]["columns"]["stamp"] = "string"
    return catalog


def _declared(occurred):
    raw = logical_bundle()
    read = raw["sources"]["input_rows"]["read"]
    read["order_by"] = ["record_id"]                     # the time is not the order column
    read["occurred_at"] = occurred
    return raw


def _rows(stamps, event_at=None):
    return pd.DataFrame([{
        "row_id": "RID-%04d" % index, "record_id": "R-%04d" % index, "join_id": "J-%04d" % index,
        "source_id": "IN-%04d" % index, "target_id": "OUT-J-%04d" % index,
        "event_at": event_at or datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc),
        "event_key": "E-%04d" % index, "unselected_note": None, "stamp": stamp,
    } for index, stamp in enumerate(stamps)])


def _prepared(occurred, stamps, event_at=None):
    compiled = snapshot(_declared(occurred), catalog=_catalog())
    refusals = []
    events = prepare_v2_cursor_batch(compiled, "input_rows", _rows(stamps, event_at), refusals=refusals)
    return [event[SOURCE_OCCURRED_AT_COLUMN].iloc[0] for event in events], refusals


@pytest.mark.parametrize("fmt,text", [
    (FORMAT, "20261008_123000"),                    # the owner's shape
    ("%Y%m%d%H%M%S", "20261008123000"),             # one ISO reading cannot read at all
])
def test_a_text_time_in_the_declared_format_is_that_instant_in_the_declared_zone(fmt, text):
    instants, refusals = _prepared({"column": "stamp", "timezone": "Asia/Seoul", "format": fmt}, [text])
    assert refusals == []
    assert instants == [datetime(2026, 10, 8, 12, 30, tzinfo=SEOUL)]


def test_text_no_reading_takes_is_refused_without_a_format_and_refuses_its_molecule_only():
    """Nothing is guessed: no format, the one ISO reading - and what it cannot take is refused,
    now that molecule only (총괄 ca87ffdb3 ②; it used to stop the whole page)."""
    instants, refusals = _prepared({"column": "stamp", "timezone": "Asia/Seoul"},
                                   ["20261008123000", "2026-10-08T12:30:00"])
    assert instants == [datetime(2026, 10, 8, 12, 30, tzinfo=SEOUL)]
    assert [r.reason for r in refusals] == ["unreadable_occurred_at"]


def test_a_datetime_column_reads_as_it_always_has_whatever_the_format():
    at = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)
    instants, refusals = _prepared({"column": "event_at", "timezone": "Asia/Seoul", "format": FORMAT},
                                   ["anything"], event_at=at)
    assert refusals == [] and instants == [at]


def test_a_row_the_format_does_not_read_is_refused_alone_and_says_the_value_and_the_format():
    instants, refusals = _prepared({"column": "stamp", "timezone": "Asia/Seoul", "format": FORMAT},
                                   ["20261008_123000", "2026-10-08"])
    assert instants == [datetime(2026, 10, 8, 12, 30, tzinfo=SEOUL)]
    refusal, = refusals
    assert refusal.reason == "unreadable_occurred_at"
    assert "'2026-10-08' does not match format %Y%m%d_%H%M%S" in refusal.detail
    assert refusal.addresses == ({"code": "source_preparation_incomplete",
                                  "path": "source_batch.rows[1].stamp"},)


def test_an_offset_in_the_text_wins_over_the_declared_zone():
    instants, refusals = _prepared({"column": "stamp", "timezone": "Asia/Seoul", "format": "%Y-%m-%dT%H:%M:%S"},
                                   ["2026-10-08T03:30:00+00:00"])
    assert refusals == []
    assert instants == [datetime(2026, 10, 8, 3, 30, tzinfo=timezone.utc)]


def _refused(occurred=None, binding=None):
    raw = _declared(occurred or {"column": "stamp", "timezone": "Asia/Seoul"})
    if binding is not None:
        raw["sources"]["input_rows"]["bind"]["mappings"]["main_transition"]["bind"]["occurred_at"] = binding
    return {(e.code, e.path) for e in validate_bundle_errors(raw, catalog=_catalog())}


def test_a_format_that_does_not_read_back_today_is_refused_in_both_cells():
    read = "bundle.sources.input_rows.read.occurred_at.format"
    bound = "bundle.sources.input_rows.bind.mappings.main_transition.bind.occurred_at.format"
    assert ("invalid_time_format", read) in _refused({"column": "stamp", "timezone": "Asia/Seoul",
                                                      "format": "%H:%M"})
    assert ("invalid_time_format", bound) in _refused(binding={"kind": "column", "column": "stamp",
                                                               "timezone": "Asia/Seoul", "format": "stamp"})
    assert not {code for code, _path in _refused({"column": "stamp", "timezone": "Asia/Seoul",
                                                  "format": FORMAT})} & {"invalid_time_format"}


def test_a_format_needs_a_timezone_on_a_binding_and_a_column_on_the_read():
    bound = "bundle.sources.input_rows.bind.mappings.main_transition.bind.occurred_at.format"
    assert ("invalid_binding", bound) in _refused(binding={"kind": "column", "column": "stamp",
                                                           "format": FORMAT})
    assert ("invalid_driver", "bundle.sources.input_rows.read.occurred_at.format") in _refused(
        {"basis": "ingested", "timezone": "UTC", "format": FORMAT})


def test_a_source_that_leaves_the_read_time_out_takes_its_event_edges_format():
    profile = {"mappings": {"one": {"bind": {"occurred_at": {
        "kind": "column", "column": "stamp", "timezone": "Asia/Seoul", "format": FORMAT}}}}}
    assert setup_bundle._event_edge_time(profile) == {"column": "stamp", "timezone": "Asia/Seoul",
                                                      "format": FORMAT}
    profile["mappings"]["one"]["bind"]["occurred_at"].pop("format")
    assert setup_bundle._event_edge_time(profile) == {"column": "stamp", "timezone": "Asia/Seoul"}


def test_an_event_edge_written_with_a_format_makes_the_atoms_time_that_text():
    """총괄 ca87ffdb3 ①: a mapping's time binding (column · timezone · format) is where the author
    writes it; the read takes it from there and the atom's time is the text, read."""
    raw = _declared(None)
    del raw["sources"]["input_rows"]["read"]["occurred_at"]
    raw["sources"]["input_rows"]["bind"]["mappings"]["main_transition"]["bind"]["occurred_at"] = {
        "kind": "column", "column": "stamp", "timezone": "Asia/Seoul", "format": "%Y%m%d%H%M%S"}
    compiled = snapshot(raw, catalog=_catalog())
    refusals = []
    events = prepare_v2_cursor_batch(compiled, "input_rows", _rows(["20261008123000"]), refusals=refusals)
    assert refusals == []
    assert [e[SOURCE_OCCURRED_AT_COLUMN].iloc[0] for e in events] == [datetime(2026, 10, 8, 12, 30, tzinfo=SEOUL)]


def test_a_timestamp_value_binding_reads_its_text_by_its_format():
    """The binding seat (`roleframe._evaluate_binding`) - text a timestamp role's column holds is
    read by the same parser, wherever the atom's time comes from."""
    from ledger.roleframe import map_event_frame, mapper_context
    from test_ledger_roleframe import event_frame, implementations

    raw = logical_bundle()
    raw["vocabulary"]["moves_to@1"]["object"] = {
        "kind": "value", "value_type": "timestamp", "qualifiers": {"required": [], "optional": []}}
    bind = raw["sources"]["input_rows"]["bind"]["mappings"]["main_transition"]["bind"]
    bind.pop("target")
    bind.pop("event_key")
    bind["value"] = {"kind": "column", "column": "stamp", "timezone": "Asia/Seoul", "format": "%Y%m%d%H%M%S"}
    compiled = snapshot(raw, catalog=_catalog())
    rows = [{"source_id": "IN-1", "target_id": "OUT-1", "event_at": datetime(2026, 8, 17, 1, 30, tzinfo=timezone.utc),
             "event_key": "E-1", "stamp": "20261008123000"}]

    roles = map_event_frame(mapper_context(compiled, "input_rows"),
                            event_frame(compiled, rows), implementations()).iloc[0]["roles"]

    assert roles["value"] == datetime(2026, 10, 8, 12, 30, tzinfo=SEOUL)
