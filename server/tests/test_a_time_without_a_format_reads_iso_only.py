# -*- coding: utf-8 -*-
"""총괄 10-11 ㄱ (소유자 운영: 시각 칸 «20261011_213631», format 없음 - 테스트 런은 읽고 백필은 거절): text with no
declared format is read only when it is ISO 8601 extended, the same on every Python - 3.11+ `fromisoformat` also read
«20261011_213631» where 3.10 refused it. Anything else is refused at the one reader (`roleframe.aware_time`) with the
line to write; a declared `format` reads it, on `read.occurred_at` and on any column binding (an attribute too).

  the reader       ISO extended reads · «20261011_213631» and its kin refused, naming the format to declare
  one judge        the test run and the execute door (`preview_cursor_batch`) refuse the same rows the same way
  format           read.occurred_at.format and an attribute binding's format read the text"""
import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from test_a_test_run_shows_the_atoms_its_rows_became import _document, _service
from test_the_test_run_reads_until_it_has_a_molecule import _StubEngine, _row
from ledger import backfill, roleframe, runtime_v2

SOURCE = "lot_slot_wafer"
COMPACT = "%Y%m%d_%H%M%S"
SEOUL = timezone(timedelta(hours=9))


@pytest.mark.parametrize("text, read", [
    ("2026-10-11 21:36:31", datetime(2026, 10, 11, 21, 36, 31, tzinfo=SEOUL)),
    ("2026-10-11T21:36:31", datetime(2026, 10, 11, 21, 36, 31, tzinfo=SEOUL)),
    ("2026-10-11T21:36:31.250000", datetime(2026, 10, 11, 21, 36, 31, 250000, tzinfo=SEOUL)),
    ("2026-10-11T12:36:31Z", datetime(2026, 10, 11, 12, 36, 31, tzinfo=timezone.utc)),
    ("2026-10-11T21:36:31+09:00", datetime(2026, 10, 11, 21, 36, 31, tzinfo=SEOUL)),
    ("2026-10-11", datetime(2026, 10, 11, tzinfo=SEOUL))])
def test_iso_extended_text_reads(text, read):
    assert roleframe.aware_time(text, "Asia/Seoul", "p") == read


@pytest.mark.parametrize("text", ["20261011_213631", "20261011T213631", "2026-10-11_21:36:31",
                                  "2026/10/11 21:36:31"])
def test_other_text_is_refused_naming_the_format_to_declare(text):
    with pytest.raises(roleframe.RoleFrameError) as refused:
        roleframe.aware_time(text, "Asia/Seoul", "p")
    assert "is not ISO 8601" in str(refused.value) and '"format": "%Y%m%d_%H%M%S"' in str(refused.value)


def _relation():
    return [dict(_row(i), event_time="20261011_2136%02d" % i) for i in range(4)]


def _both(tmp_path, document):
    """(the test run's answer, the execute door's preview) on the same rows."""
    service = _service(tmp_path, document)
    setup, _index, _ = service.active()
    plan = setup.snapshot.source_plans[SOURCE]
    relation = _relation()
    result = service.test_run(_StubEngine(relation, plan.driver.cursor_columns[0]), source_id=SOURCE, sample_rows=4)
    reading = backfill.preview_first_batch(_StubEngine(relation, plan.driver.cursor_columns[0]), setup, SOURCE,
                                           sample_rows=4)
    return setup, result, reading


def test_the_test_run_and_the_execute_door_refuse_the_compact_text_alike(tmp_path):
    _setup, result, reading = _both(tmp_path, _document())
    assert result["refused"]["count"] == len(reading.preview.refusals) == 4, result["refused"]
    assert result["molecules"] == reading.preview.molecule_count == 0
    shown = {sample["detail"] for sample in result["refused"]["samples"]}
    assert shown == {r.detail for r in reading.preview.refusals[:len(result["refused"]["samples"])]}
    assert all("is not ISO 8601" in detail for detail in shown), shown


def test_a_declared_occurred_at_format_reads_it(tmp_path):
    document = _document()
    document["sources"][SOURCE]["read"]["occurred_at"]["format"] = COMPACT
    setup, result, reading = _both(tmp_path, document)
    atoms = runtime_v2._screened_atoms(setup.snapshot, SOURCE, reading.preview)
    assert result["refused"]["count"] == 0 and result["molecules"] == 4
    assert sorted({a.occurred_at for a in atoms}) == [datetime(2026, 10, 11, 21, 36, i, tzinfo=SEOUL)
                                                      for i in range(4)]


@pytest.mark.parametrize("fmt", [None, COMPACT])
def test_an_attribute_binding_reads_the_text_by_its_format(tmp_path, fmt):
    document = _document()
    document["sources"][SOURCE]["read"]["occurred_at"]["format"] = COMPACT
    document["entities"]["wafer@1"]["attributes"] = ["moved_at"]
    bound = {"kind": "column", "column": "event_time", "timezone": "Asia/Seoul", **({"format": fmt} if fmt else {})}
    document["sources"][SOURCE]["bind"]["entities"] = {"wafer@1": {"attributes": {"moved_at": bound}}}
    if fmt is None:
        # a value binding refuses its batch, not a molecule: the test run says so, the execute door raises it
        with pytest.raises(roleframe.RoleFrameError) as raised:
            _both(tmp_path, document)
        service = _service(tmp_path, document)
        setup, _index, _ = service.active()
        result = service.test_run(_StubEngine(_relation(), setup.snapshot.source_plans[SOURCE].driver.cursor_columns[0]),
                                  source_id=SOURCE, sample_rows=4)
        assert result["status"] == "refused" and result["refusal"]["message"] in str(raised.value)
        assert "is not ISO 8601" in result["refusal"]["message"] and result["refusal"]["path"].endswith(
            ".attributes.moved_at.column"), result["refusal"]
        return
    setup, result, reading = _both(tmp_path, document)
    atoms = runtime_v2._screened_atoms(setup.snapshot, SOURCE, reading.preview)
    said = json.dumps([a.object_payload for a in atoms], default=str)
    assert result["refused"]["count"] == 0 and "moved_at" in said, said
    assert "2026-10-11T21:36:00+09:00" in said or "2026-10-11 21:36:00+09:00" in said, said
