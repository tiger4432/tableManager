# -*- coding: utf-8 -*-
"""총괄 4b5964ab2 ② — a row whose cursor cell is empty is refused by name, with its molecule,
and the rest of its batch is translated. Before, one such row stopped the whole batch:
`_cursor_value` read every row's cursor and pandas 3 holds an empty text cell as NaN,
「cursor number must be finite」 - the box's dt_job over dt_log, whose cursor is
(dt_job, dt_cell_key), on every follow-up of a job holding one. The refusal is the existing
one - `no_raw_ref`, the ledger names a row by its cursor - with the address of the column to
fill. A group source's whole molecule goes: `test_ledger_source_preparation`.

The fixture copies the sample's wafer_process_recipe over a table whose cursor is (row_id, seq),
the box's shape: the second cursor column is read and bound by no sentence.
"""
import copy
import json
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import gate                                                  # noqa: E402
from ledger.implementations import (role_mapper_registry,                # noqa: E402
                                    trusted_implementations)
from ledger.runtime_v2 import (execute_scoped_batch, last_cursor,        # noqa: E402
                               preview_cursor_batch)
from ledger.setup_bundle import (load_physical_catalog,                  # noqa: E402
                                 require_ready_bundle, validate_bundle)
from ledger.setup_registry import compile_setup_snapshot                 # noqa: E402

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "config", "sample")
SOURCE, TABLE = "zz_process_by_seq", "zz_process_seq"
ADDRESS = {"code": "source_preparation_incomplete",
           "path": "bundle.sources.%s.read.order_by.seq" % SOURCE}


class _Store:
    def __init__(self):
        self.written = []

    def write_batch(self, source, version, atoms, cursor, molecules, *args, **kwargs):
        self.written.append(list(atoms))
        return {"attempted": len(atoms), "inserted": len(atoms), "deduped": 0, "withdrawn": 0}


@pytest.fixture(scope="module", name="snapshot")
def fixture_snapshot(tmp_path_factory):
    folder = tmp_path_factory.mktemp("cursor_fixture")
    with open(os.path.join(SAMPLE, "table_config.json.sample"), encoding="utf-8") as fh:
        tables = json.load(fh)
    tables[TABLE] = copy.deepcopy(tables["wafer_process"])
    tables[TABLE]["column_types"]["seq"] = "string"
    (folder / "table_config.json").write_text(json.dumps(tables), encoding="utf-8")
    with open(os.path.join(SAMPLE, "ledger_config.json.sample"), encoding="utf-8") as fh:
        document = json.load(fh)
    source = copy.deepcopy(document["sources"]["wafer_process_recipe"])
    source["relation"] = TABLE
    source["read"]["order_by"] = ["row_id", "seq"]
    source["read"]["cursor"] = {"columns": ["row_id", "seq"]}
    source["map"]["input_columns"] += ["seq"]
    document["sources"][SOURCE] = source
    catalog = load_physical_catalog(str(folder / "table_config.json"))
    bundle = require_ready_bundle(validate_bundle(document, catalog=catalog))
    return compile_setup_snapshot(bundle, trusted_implementations(), catalog=catalog)


@pytest.fixture(autouse=True)
def clean_counters():
    gate.reset_counters()
    yield
    gate.reset_counters()


def _frame(seqs):
    return pd.DataFrame([
        {"row_id": "R%d" % index, "seq": seq, "wafer_id": "W%d" % index, "recipe_id": "RCP-1",
         "step": "S1", "eventtime": "2026-09-30 10:00:00", "mat_type": ""}
        for index, seq in enumerate(seqs, start=1)])


def _preview(snapshot, frame):
    plan = snapshot.source_plans[SOURCE]
    return preview_cursor_batch(snapshot, SOURCE, frame, last_cursor(plan, frame), role_mapper_registry(),
                                known_registrations=())


def test_the_row_is_refused_by_name_and_the_rest_is_translated(snapshot):
    preview = _preview(snapshot, _frame(["a", None, "c", "d"]))
    assert preview.atom_count == 3
    assert [(r.reason, r.rows) for r in preview.refusals] == [("no_raw_ref", 1)]
    refusal = preview.refusals[0]
    assert list(refusal.addresses) == [ADDRESS]
    assert "R2" in refusal.detail and "fill seq" in refusal.detail, refusal.detail


def test_the_cursor_is_the_last_row_a_cursor_can_name(snapshot):
    plan = snapshot.source_plans[SOURCE]
    # R4's cursor cell is empty and it is the last row - the plain last row was the one taken
    assert last_cursor(plan, _frame(["a", "b", "c", None])) == {"row_id": "R3", "seq": "c"}
    assert last_cursor(plan, _frame([None, None])) == {}


def test_the_execute_door_keeps_going_batch_after_batch_and_names_the_column(snapshot):
    frame = _frame(["a", None, "c"])
    store = _Store()
    for _ in range(2):          # the row is read again on the next follow-up - and refused again
        execute_scoped_batch(snapshot, SOURCE, frame, ("row_id", tuple(frame["row_id"])),
                             role_mapper_registry(),
                             store, known_registrations=())
    assert [len(atoms) for atoms in store.written] == [2, 2]
    sample = gate.samples()[0]
    assert sample["reason"] == "no_raw_ref"
    assert sample["addresses"] == [ADDRESS]


def test_a_batch_of_nothing_but_such_rows_writes_nothing_and_does_not_stop(snapshot):
    preview = _preview(snapshot, _frame([None, None]))
    assert preview.atom_count == 0
    assert [r.reason for r in preview.refusals] == ["no_raw_ref", "no_raw_ref"]
