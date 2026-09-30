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

from ledger import gate                                                  # noqa: E402
from ledger.implementations import (role_mapper_registry,                # noqa: E402
                                    source_preparer_registry,
                                    trusted_implementations)
from ledger.runtime_v2 import preview_cursor_batch                       # noqa: E402
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


def test_a_row_no_sentence_says_is_counted_by_its_value_and_named(snapshot, caplog):
    preview = _preview(snapshot, _rows())
    assert dict(preview.unsaid) == {(("mat_type", "WF"),): 1}
    with caplog.at_level(logging.WARNING, logger="Ledger.Gate"):
        gate.record_unsaid(SOURCE, preview.unsaid)
    line = caplog.records[-1].getMessage()
    assert "%s: 1 unit(s) said no sentence - mat_type='WF' (1)" % SOURCE in line, line
    assert "Next:" in line, line


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
