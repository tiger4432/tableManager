# -*- coding: utf-8 -*-
"""총괄 363db7dfa · 1dd4091a6 — a process row after a DT step is said about a dtwafer, not the core
wafer that shares its id. The shipped sample declares it: step_phase lists the DT steps, a join
copies mat_type onto wafer_process, and wafer_process_recipe says its sentence about wafer@1 when
mat_type is blank and about dtwafer@1 when it is DT. A row whose mat_type is anything else is
said by no sentence - and that is counted and named, not silent.
"""
import logging
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger.implementations import (role_mapper_registry,                # noqa: E402
                                    source_preparer_registry,
                                    trusted_implementations)
from ledger.runtime_v2 import execute_scoped_batch, preview_cursor_batch # noqa: E402
from ledger.setup_bundle import (load_physical_catalog,                  # noqa: E402
                                 require_ready_bundle, validate_bundle)
from ledger.setup_registry import compile_setup_snapshot                 # noqa: E402
from ledger.source_preparation import VerifiedJoinBatchReader            # noqa: E402

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "config", "sample")
SOURCE = "wafer_process_recipe"
#: wafer id -> the mat_type its row carries. None is a row the join found no step for.
ROWS = {"W-NULL": None, "W-BLANK": "", "W-DT": "DT", "W-WF": "WF"}


class _NoJoin(VerifiedJoinBatchReader):
    def read_chunk(self, descriptor, keys):
        raise AssertionError("this source reads no joins")


@pytest.fixture(scope="module", name="snapshot")
def fixture_snapshot():
    import json

    catalog = load_physical_catalog(os.path.join(SAMPLE, "table_config.json.sample"))
    with open(os.path.join(SAMPLE, "ledger_config.json.sample"), encoding="utf-8") as fh:
        document = json.load(fh)
    bundle = require_ready_bundle(validate_bundle(document, catalog=catalog))
    return compile_setup_snapshot(bundle, trusted_implementations(), (), catalog=catalog)


def _preview(snapshot, rows):
    frame = pd.DataFrame(rows)
    return preview_cursor_batch(
        snapshot, SOURCE, frame, {"row_id": frame.iloc[-1]["row_id"]},
        _NoJoin(), source_preparer_registry(), role_mapper_registry(), known_registrations=())


def _rows():
    return [{"row_id": "R%d" % index, "wafer_id": wafer, "recipe_id": "RCP-1", "step": "S1",
             "eventtime": "2026-09-30 10:00:00", "mat_type": mat_type}
            for index, (wafer, mat_type) in enumerate(ROWS.items(), start=1)]


def test_each_row_is_said_about_the_wafer_its_material_type_names(snapshot):
    preview = _preview(snapshot, _rows())
    said = {}
    for atom in preview.candidate_semantics:
        said.setdefault(atom["subject_keys"]["wafer"], set()).add(atom["subject_type"])
    # ㉠ a join that found no step (NULL) and an emptied cell ('') both stay on the core wafer
    assert said.get("W-NULL") == {"wafer"}, said
    assert said.get("W-BLANK") == {"wafer"}, said
    assert said.get("W-DT") == {"dtwafer"}, said
    # ㉡ a value no sentence names is said by none
    assert "W-WF" not in said, said


class _Store:
    """What the execute door asks of a store here: one write, answered with counts."""

    def __init__(self):
        self.written = []

    def write_batch(self, source, version, atoms, cursor, molecules, *args, **kwargs):
        self.written.append(list(atoms))
        return {"attempted": len(atoms), "inserted": len(atoms), "deduped": 0, "withdrawn": 0}


def test_a_row_no_sentence_says_is_counted_by_its_value_and_named(snapshot, caplog):
    """총괄 4b5964ab2 ①: through the execute door - the line an operator reads is the one the
    door writes, not a call a test makes."""
    assert dict(_preview(snapshot, _rows()).unsaid) == {(("mat_type", "WF"),): 1}
    frame = pd.DataFrame(_rows())
    store = _Store()
    with caplog.at_level(logging.WARNING, logger="Ledger.Gate"):
        executed = execute_scoped_batch(
            snapshot, SOURCE, frame, ("row_id", tuple(frame["row_id"])), _NoJoin(),
            source_preparer_registry(), role_mapper_registry(), store, known_registrations=())
    assert len(store.written) == 1 and len(store.written[0]) == 3
    assert dict(executed.preview.unsaid) == {(("mat_type", "WF"),): 1}
    lines = [r.getMessage() for r in caplog.records if "said no sentence" in r.getMessage()]
    assert len(lines) == 1, lines
    assert "%s: 1 unit(s) said no sentence - mat_type='WF' (1)" % SOURCE in lines[0], lines
    assert "Next:" in lines[0], lines


def test_every_row_said_leaves_nothing_to_count(snapshot):
    rows = [row for row in _rows() if row["mat_type"] != "WF"]
    preview = _preview(snapshot, rows)
    assert dict(preview.unsaid) == {}
    assert preview.atom_count == len(rows)


# --------------------------------------------------------------- dies, by a FIXTURE source
# 총괄 4349db8e8 ①: no sample source reads a stepped table into die@1, so the same mechanism is
# scored on a fixture - a copy of the sample's die_inspection over a table that carries step and
# mat_type, its die sentence said twice: mat_type blank -> key 'Wafer', DT -> 'DT'.
DIE_SOURCE, DIE_TABLE = "zz_die_inspection_by_step", "zz_step_inspection"


@pytest.fixture(scope="module", name="die_snapshot")
def fixture_die_snapshot(tmp_path_factory):
    import copy
    import json

    folder = tmp_path_factory.mktemp("die_fixture")
    with open(os.path.join(SAMPLE, "table_config.json.sample"), encoding="utf-8") as fh:
        tables = json.load(fh)
    tables[DIE_TABLE] = copy.deepcopy(tables["inspection_run"])
    tables[DIE_TABLE]["column_types"].update({"step": "string", "mat_type": "string"})
    (folder / "table_config.json").write_text(json.dumps(tables), encoding="utf-8")
    with open(os.path.join(SAMPLE, "ledger_config.json.sample"), encoding="utf-8") as fh:
        document = json.load(fh)
    source = copy.deepcopy(document["sources"]["die_inspection"])
    source["relation"] = DIE_TABLE
    for stage in ("prepare", "map"):
        source[stage]["input_columns"] += ["step", "mat_type"]
    core = source["bind"]["mappings"].pop("die-inspected")
    dt = copy.deepcopy(core)
    core["when"] = {"mat_type": ""}
    dt["when"] = {"mat_type": "DT"}
    dt["bind"]["target"]["keys"]["mat_type"] = {"kind": "constant", "value": "DT"}
    source["bind"]["mappings"] = {"die-inspected": core, "dt-die-inspected": dt}
    document["sources"][DIE_SOURCE] = source
    catalog = load_physical_catalog(str(folder / "table_config.json"))
    bundle = require_ready_bundle(validate_bundle(document, catalog=catalog))
    return compile_setup_snapshot(bundle, trusted_implementations(), (), catalog=catalog)


def test_a_die_inspected_after_a_dt_step_is_the_dt_die(die_snapshot):
    rows = pd.DataFrame([
        {"row_id": "R%d" % index, "run_uid": "U%d" % index, "base_wafer_id": wafer,
         "base_x": 1, "base_y": 2, "stack_gate": "G", "observed_at": "2026-09-30 10:00:00",
         "step": "S1", "mat_type": mat_type}
        for index, (wafer, mat_type) in enumerate(ROWS.items(), start=1)])
    preview = preview_cursor_batch(
        die_snapshot, DIE_SOURCE, rows, {"run_uid": rows.iloc[-1]["run_uid"]},
        _NoJoin(), source_preparer_registry(), role_mapper_registry(), known_registrations=())
    dies = {atom["object_payload"]["keys"]["mat_id"]: atom["object_payload"]["keys"]["mat_type"]
            for atom in preview.candidate_semantics}
    assert dies == {"W-NULL": "Wafer", "W-BLANK": "Wafer", "W-DT": "DT"}, dies
    assert dict(preview.unsaid) == {(("mat_type", "WF"),): 1}
