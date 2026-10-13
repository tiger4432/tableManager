# -*- coding: utf-8 -*-
"""An entity key is written in ONE spelling, whoever hands it (lead 112293f73 ①, owner «접어, 정수변환», forward
only): an integer-valued number is its integer's text (1.0 -> «1»), a text keeps its letters («01» stays «01»).

  declared binding   a text column's «1» and a number column's 1.0 name one die (folded by the column's type - 7233a7a31)
  code mapper        the keys a mapper hands arrive as it made them - 1.0 is written «1», «01» stays «01»
  reference          a reference's constant key 1.0 is written «1»
"""
import copy
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.dirname(__file__))

from ledger.backfill import _v2_frame                                   # noqa: E402
from ledger.implementations import role_mapper_registry, trusted_implementations  # noqa: E402
from ledger.roleframe import (BaseLedgerMapper, ProfileSentences, RoleEmission,  # noqa: E402
                              SentenceShape, compile_role_frame, map_event_frame, mapper_context)
from ledger.runtime_v2 import last_cursor, preview_cursor_batch         # noqa: E402
from ledger.setup_bundle import load_physical_catalog, require_ready_bundle, validate_bundle  # noqa: E402
from ledger.setup_registry import compile_setup_snapshot                # noqa: E402
from test_ledger_roleframe import event_frame, implementations          # noqa: E402
from test_ledger_setup_registry import snapshot                         # noqa: E402

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "config", "sample")


class HandsNumbersMapper(BaseLedgerMapper):
    """A code mapper handing a subject key as a number and a target key as a text with a leading zero."""

    def interpret_unit(self, context, unit, profile):
        row = unit.iloc[0]
        return [RoleEmission(
            sentence=next(iter(profile.mappings)),
            roles={"subject": {"type": "InputEntity", "keys": {"input_id": 1.0}},
                   "target": {"type": "OutputEntity", "keys": {"output_id": "01"}},
                   "occurred_at": row["event_at"], "event_key": row["event_key"]},
            source_row_refs=(unit.attrs["source_raw_ref"],))]


def test_a_code_mappers_keys_are_written_in_the_one_spelling():
    compiled = snapshot()
    context = mapper_context(compiled, "input_rows")
    ledger = compile_role_frame(context, map_event_frame(context, event_frame(compiled),
                                                         implementations(HandsNumbersMapper)))

    row = ledger.iloc[0]
    assert (row["subject_keys"], row["object_payload"]["keys"]) == ({"input_id": "1"}, {"output_id": "01"})


def test_a_first_sight_of_1_0_and_1_is_one_sight(monkeypatch):
    """A mapper's first sight is judged on the key as the atom writes it (총괄 10-14 ①)."""
    monkeypatch.setattr(ProfileSentences, "_resolve", lambda self, shape: None)
    monkeypatch.setattr(ProfileSentences, "say", lambda self, shape, subject, refs: subject)
    class Sights:
        SEEN = SentenceShape()

    sentences = ProfileSentences(None, None, occurred_at=None)

    assert [sentences.first_sight(Sights.SEEN, key, ()) for key in (1.0, "1", "01")] == [1.0, None, "01"]


def _sample_snapshot(change):
    catalog = load_physical_catalog(os.path.join(SAMPLE, "table_config.json.sample"))
    with open(os.path.join(SAMPLE, "ledger_config.json.sample"), encoding="utf-8") as fh:
        document = json.load(fh)
    change(document)
    bundle = require_ready_bundle(validate_bundle(document, catalog=catalog))
    return compile_setup_snapshot(bundle, trusted_implementations(), catalog=catalog)


def _preview(compiled, source, rows):
    frame = _v2_frame(rows)
    return preview_cursor_batch(compiled, source, frame, last_cursor(compiled.source_plans[source], frame),
                                role_mapper_registry(), known_registrations=())


def _inspection_rows(x):
    return [{"row_id": "R1", "run_uid": "U1", "method": "aoi", "base_wafer_id": "W1", "base_x": x, "base_y": 0.0,
             "stack_gate": None, "recipe_id": None, "eqp_id": None, "observed_at": "2026-09-30 10:00:00",
             "work_id": None}]


def test_a_references_constant_key_is_written_in_the_one_spelling():
    def constant_wafer(document):
        document["entities"]["die@1"]["references"] = {
            "edge": "in_container@1", "to": {"entity": "wafer@1", "keys": {"wafer": {"value": 1.0}}},
            "from": {"when": {"mat_type": "Wafer"}}}

    preview = _preview(_sample_snapshot(constant_wafer), "die_inspection", _inspection_rows(1.0))

    assert sorted({json.dumps(a["object_payload"]["keys"]) for a in preview.candidate_semantics
                   if a["predicate"] == "in_container"}) == ['{"wafer": "1"}']


def test_a_text_one_and_a_number_one_name_one_die():
    """The declared path, already folded by the column's type - a cell here so the three seats are read together."""
    def dies(x):
        preview = _preview(_sample_snapshot(lambda document: None), "die_inspection", _inspection_rows(x))
        return {json.dumps(a["object_payload"]["keys"], sort_keys=True) for a in preview.candidate_semantics
                if (a["object_payload"] or {}).get("type") == "die"}

    assert dies(1.0) == dies("1") and len(dies(1.0)) == 1
