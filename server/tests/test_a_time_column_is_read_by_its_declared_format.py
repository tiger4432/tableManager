"""A timestamp value's column written as text is read by the format its binding states (총괄 ca87ffdb3,
소유자 「yyyymmdd_hhmmss 형식」 → 「ㄱ 바인딩에 format」). A source's own time is a datetime column only (owner 11-07,
test_a_ledger_source_reads_its_time_from_a_datetime_column) - its `format` is refused there.

  the read      a binding's `format` - text is read by THE parser for a declared shape,
                `utils.time_format.parse_occurred_at`; nothing is guessed: no format, no reading
  the check     today's time written in the format and read back gives the same text and today's
                date, or the declaration is refused at save
  the default   a source that leaves `read.occurred_at` out takes its event edge's column,
                timezone - and format, so the read's refusal names it
"""
import copy
import os
import sys
from datetime import datetime, timedelta, timezone


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import setup_bundle                                          # noqa: E402
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


def _refused(occurred=None, binding=None):
    raw = _declared(occurred or {"column": "stamp", "timezone": "Asia/Seoul"})
    if binding is not None:
        raw["sources"]["input_rows"]["bind"]["mappings"]["main_transition"]["bind"]["occurred_at"] = binding
    return {(e.code, e.path) for e in validate_bundle_errors(raw, catalog=_catalog())}


def test_a_binding_format_that_does_not_read_back_today_is_refused():
    bound = "bundle.sources.input_rows.bind.mappings.main_transition.bind.occurred_at.format"
    assert ("invalid_time_format", bound) in _refused(binding={"kind": "column", "column": "stamp",
                                                               "timezone": "Asia/Seoul", "format": "stamp"})
    assert not {code for code, _path in _refused(binding={"kind": "column", "column": "stamp",
                                                          "timezone": "Asia/Seoul", "format": FORMAT})} \
        & {"invalid_time_format"}


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
