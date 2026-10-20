"""총괄 88761926b (owner 10-20 «1 ㅇㅇ 2 ㅇㅇ 3 ㅇㅇ»): a value compared as a key has ONE spelling - the declared
column type's, `map_overlay.canonical_key_value` (contracts/map_seam canonical_value_cases). The same input table goes
through every seat that composes or compares a key and each answers what the speller answers:

  number   '001' · '+1' · ' 1 ' · 1.0 · '1.0' · '1e3' -> integers; '1.50' · Decimal('1.50') · numpy 1.5 -> '1.5'
  text · undeclared   letters kept ('001' · '1.50'); a float value integral -> its integer

Held until the owner answers (lead 10-20): a time column's spelling, a code mapper's typeless keys, the pandas reader.
"""
import os
import sys
from decimal import Decimal

import numpy as np
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import chain_bindings                                          # noqa: E402
import map_alignment                                           # noqa: E402
import map_overlay                                             # noqa: E402
from chain import ingestion_worker, join_into                  # noqa: E402
from chain.enrichment import analysis, mapper                  # noqa: E402
from database import crud, schemas                             # noqa: E402
from maps import frame_confirmation                            # noqa: E402

T, R = "zz_one_spelling", "zz_one_spelling_right"
COLUMNS = {"k_number": "number", "k_string": "string", "k_none": None}
INPUTS = [1, 1.0, "1.0", "001", "1.50", "1.5000", np.float64(1.5), np.int64(1), Decimal("1.50"), "1e3", "+1",
          "-0", " 1 "]                      # '0x10' on a number: the speller keeps it, the typed bind refuses it


@pytest.fixture(autouse=True)
def config(monkeypatch):
    monkeypatch.setitem(crud.TABLE_CONFIG, T, {
        "column_types": {c: t for c, t in COLUMNS.items() if t}})
    monkeypatch.setitem(crud.TABLE_CONFIG, R, {"column_types": {"code": "string"}})


class _Row:
    business_key_val = None


def _seats(column, value):
    """Every seat's spelling of `value` as a key of `column` - the seat's own call, its answer as text."""
    group = ingestion_worker.group_key({chain_bindings.GROUP_BY_KEY: [column]},
                                       {"table_name": T, "data": {column: value}})
    row = _Row()
    crud._update_row_business_key(row, column, schemas.GeneralUpdateItem(row_id="r", updates={column: value}),
                                  None, T)
    return {
        "key_part": crud.clean_str_value(crud.key_part(T, column, value)),
        "canonical_bind_value": map_overlay.canonical_bind_value(T, column, value),
        "compose_business_key": crud.compose_business_key(T, [value], [column]),
        "map_alignment.compose_map_id": map_alignment.compose_map_id([value], T, [column]),
        "group_key": group.split("=", 1)[1].strip("'"),
        "enrichment._clean_key": mapper._clean_key(T, [column], [value])[0],
        "analysis._typed_key_values": analysis._typed_key_values(
            {"source_table": T, "decision_key": [column]}, {column: value})[0][0],
        "compose_unit_key": frame_confirmation.compose_unit_key(
            {"name": "r", "decision_key": [column], "derived_table": T}, {column: value}),
        "_update_row_business_key": row.business_key_val,
    }


@pytest.mark.parametrize("column", list(COLUMNS))
@pytest.mark.parametrize("value", INPUTS, ids=[repr(v) for v in INPUTS])
def test_every_seat_spells_a_key_as_the_one_speller(column, value):
    want = map_overlay.canonical_key_value(value, COLUMNS[column])
    assert want, "canary: every input is a key"
    seats = _seats(column, value)
    assert {seat: got for seat, got in seats.items() if got != want} == {}, (want, seats)


def test_the_number_rule_reads_as_the_owner_said():
    """The speller itself on the inputs the census found split (the vectors pin the rest)."""
    spell = map_overlay.canonical_key_value
    assert [spell(v, "number") for v in ("1.50", Decimal("1.50"), np.float64(1.5), "001", "1e3", "-0", "0x10")] == \
        ["1.5", "1.5", "1.5", "1", "1000", "0", "0x10"]
    assert [spell(v, "string") for v in ("1.50", "001", 1.0)] == ["1.50", "001", "1"]


def test_a_void_body_wafer_and_its_path_compare_in_one_spelling():
    from parsers import voids_json_format

    out = voids_json_format._merge_path_identity(
        {"base_wafer_id": 12.0}, {"base_wafer_id": "12", "observed_at": "2026-10-20T00:00:00+09:00",
                                  "work_datetime": "x"}, row_label="r")
    assert out["base_wafer_id"] == "12"
    with pytest.raises(ValueError):
        voids_json_format._merge_path_identity(
            {"base_wafer_id": "13"}, {"base_wafer_id": "12", "observed_at": "2026-10-20T00:00:00+09:00",
                                      "work_datetime": "x"}, row_label="r")


def test_a_join_that_matched_nothing_says_its_key_types_differ():
    spec = {"right_table": R, "on": [{"left": "k_number", "right": "code"}]}
    assert join_into._key_types_differ(spec, T) == ["%s.k_number number · %s.code string" % (T, R)]
    assert join_into._key_types_differ({"right_table": R, "on": [{"left": "k_string", "right": "code"}]}, T) == []
