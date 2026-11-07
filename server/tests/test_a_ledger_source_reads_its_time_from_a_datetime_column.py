"""A ledger source reads its time from a datetime column only (owner 11-07 «yymmdd 같은 시각이 키면 칸을 두 표기로 가르고
(체인이 날짜 칸을 채움), 원장 소스에는 datetime만», lead): `setup_bundle._event_time_is_datetime`, on the source's own
path, so the loader drops that source and plans the rest (S-177 ②).

  the time column             declared            the refusal, its next step
  string, not a key           string              «declare <column> datetime»
  string, a key               the row/map key     «=ParseDateTime([<column>], "<its format in .NET spelling>")»,
                                                  the fixed example where it has none or none converts
  datetime with a format      datetime            «not read - <column> is datetime; remove it»
  datetime, no format         datetime            none - read as it always was
  a basis                     -                   none
  an event edge's column      string              the read's refusal (the edge's time is lifted to the read)
"""
import copy
import os
import sys
from datetime import datetime, timezone

import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import expression                                                        # noqa: E402
from ledger.backfill import prepare_v2_cursor_batch                      # noqa: E402
from ledger.config_authoring import isolation_key                        # noqa: E402
from ledger.roleframe import SOURCE_OCCURRED_AT_COLUMN                   # noqa: E402
from test_ledger_setup_bundle import (DEFAULT_CATALOG, logical_bundle,  # noqa: E402
                                      validate_bundle_errors)
from test_ledger_setup_registry import snapshot                          # noqa: E402
from utils.time_format import NET_EXAMPLE, net_spelling                  # noqa: E402

READ = "bundle.sources.input_rows.read.occurred_at"


def _catalog(keys=()):
    catalog = copy.deepcopy(DEFAULT_CATALOG)
    catalog["input_rows"]["columns"]["stamp"] = "string"
    catalog["input_rows"]["keys"] = {"the row key": ["record_id", *keys], "the map key": []}
    return catalog


def _declared(occurred):
    raw = logical_bundle()
    read = raw["sources"]["input_rows"]["read"]
    read["order_by"] = ["record_id"]
    read["occurred_at"] = occurred
    return raw


def _timed(raw, catalog):
    return {(e.code, e.path): str(e) for e in validate_bundle_errors(raw, catalog=catalog)
            if e.code in ("time_not_datetime", "time_format_not_read")}


def test_a_string_time_that_is_not_a_key_is_declared_datetime():
    said = _timed(_declared({"column": "stamp", "timezone": "Asia/Seoul"}), _catalog())
    assert list(said) == [("time_not_datetime", READ + ".column")]
    assert said[("time_not_datetime", READ + ".column")].endswith("stamp is string - declare stamp datetime")


@pytest.mark.parametrize("fmt,net", [
    ("%Y%m%d_%H%M%S", "yyyyMMdd_HHmmss"),          # its format, in the calculator's spelling
    (None, NET_EXAMPLE),                            # none declared
    ("%b %d %Y", NET_EXAMPLE),                      # none the calculator reads
])
def test_a_string_time_that_is_a_key_is_filled_into_a_datetime_column_by_a_chain(fmt, net):
    occurred = {"column": "stamp", "timezone": "Asia/Seoul", **({"format": fmt} if fmt else {})}
    said = _timed(_declared(occurred), _catalog(keys=("stamp",)))
    assert said[("time_not_datetime", READ + ".column")].endswith(
        'stamp is string and the row key - add a datetime column filled by a chain: '
        '=ParseDateTime([stamp], "%s"), and read that column' % net)


def test_a_format_beside_a_datetime_column_is_not_read_and_refused():
    said = _timed(_declared({"column": "event_at", "timezone": "Asia/Seoul", "format": "%Y%m%d_%H%M%S"}), _catalog())
    assert said == {("time_format_not_read", READ + ".format"):
                    READ + ".format: not read - event_at is datetime; remove it"}


def test_a_datetime_column_and_a_basis_are_not_refused_and_the_column_reads_as_it_always_has():
    assert _timed(_declared({"column": "event_at", "timezone": "Asia/Seoul"}), _catalog()) == {}
    assert _timed(_declared({"basis": "ingested", "timezone": "UTC"}), _catalog()) == {}
    at = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)
    compiled = snapshot(_declared({"column": "event_at", "timezone": "Asia/Seoul"}), catalog=_catalog())
    refusals = []
    events = prepare_v2_cursor_batch(compiled, "input_rows", pd.DataFrame([{
        "row_id": "RID-1", "record_id": "R-1", "join_id": "J-1", "source_id": "IN-1", "target_id": "OUT-J-1",
        "event_at": at, "event_key": "E-1", "unselected_note": None, "stamp": None}]), refusals=refusals)
    assert refusals == [] and [e[SOURCE_OCCURRED_AT_COLUMN].iloc[0] for e in events] == [at]


def test_an_event_edges_string_time_is_refused_where_the_read_takes_it():
    raw = _declared(None)
    del raw["sources"]["input_rows"]["read"]["occurred_at"]
    raw["sources"]["input_rows"]["bind"]["mappings"]["main_transition"]["bind"]["occurred_at"] = {
        "kind": "column", "column": "stamp", "timezone": "Asia/Seoul"}
    assert list(_timed(raw, _catalog())) == [("time_not_datetime", READ + ".column")]


def test_the_refusal_drops_its_source_alone():
    assert isolation_key(READ + ".column") == isolation_key("bundle.sources.input_rows.relation")
    assert isolation_key(READ + ".column") != isolation_key("bundle.sources.other_rows.relation")


@pytest.mark.parametrize("strptime_format", [
    "%y%m%d_%H%M%S", "%Y%m%d_%H%M%S", "%Y/%m/%d %H:%M", "%Y-%m-%dT%H:%M:%S.%f", "%d.%m.%Y", "%Y%m%d%H%M%S"])
def test_a_converted_format_is_read_back_by_parse_date_time_as_the_same_format(strptime_format):
    assert expression._net_format(net_spelling(strptime_format))[0] == strptime_format


@pytest.mark.parametrize("strptime_format", ["%b %d %Y", "%Y%m", "%Hh%M %Y%m%d", "%y%m%d %%", "%Y%y%m%d"])
def test_a_format_parse_date_time_would_not_read_has_no_spelling(strptime_format):
    assert net_spelling(strptime_format) is None
