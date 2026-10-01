# -*- coding: utf-8 -*-
"""One die is one key, whatever spelling its source gave (총괄 7233a7a31, 소유자 「원장에 die 가 x,y 를
1 로 읽은 것 1.0 으로 읽은 게 뒤섞여서 중복되고 난리남」).

An entity key a declaration binds is spelled by the one key canonicalizer
(`map_overlay.canonical_key_value`) by the declared type of the column it came from: a number
column's 1, 1.0 and '01' are one key '1'; a text column's '1.0' stays '1.0' - there the spelling
is the meaning, and the operator's handle is declaring that column `number`.
"""
import copy
import json
import os
import sys
import uuid
from datetime import datetime

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import crud                                               # noqa: E402
from ledger import explorer                                             # noqa: E402
from ledger.backfill import _v2_frame, _v2_registration_subjects        # noqa: E402
from ledger.envelope import canonical_keys                              # noqa: E402
from ledger.implementations import (role_mapper_registry,                # noqa: E402
                                    trusted_implementations)
from ledger.runtime_v2 import preview_cursor_batch                      # noqa: E402
from ledger.setup_bundle import (load_physical_catalog,                  # noqa: E402
                                 require_ready_bundle, validate_bundle)
from ledger.setup_registry import compile_setup_snapshot                 # noqa: E402
from ledger_api import ledger_subgraph                                  # noqa: E402

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "config", "sample")
NUM, TXT = "zz_die_by_number", "zz_die_by_text"
TABLES = {NUM: "zz_inspection_number", TXT: "zz_inspection_text"}


@pytest.fixture(name="snapshot")
def fixture_snapshot(tmp_path, monkeypatch):
    """The sample's die_inspection twice: over a table whose x,y are declared `number` and over
    one whose x,y are declared `string`. The declared type is read from the live catalogue
    (`map_overlay.declared_column_type`), so both tables are put there too."""
    with open(os.path.join(SAMPLE, "table_config.json.sample"), encoding="utf-8") as fh:
        tables = json.load(fh)
    tables[TABLES[NUM]] = copy.deepcopy(tables["inspection_run"])
    tables[TABLES[TXT]] = copy.deepcopy(tables["inspection_run"])
    tables[TABLES[TXT]]["column_types"].update({"base_x": "string", "base_y": "string"})
    (tmp_path / "table_config.json").write_text(json.dumps(tables), encoding="utf-8")
    for name in TABLES.values():
        monkeypatch.setitem(crud.TABLE_CONFIG, name, tables[name])
    with open(os.path.join(SAMPLE, "ledger_config.json.sample"), encoding="utf-8") as fh:
        document = json.load(fh)
    for source, table in TABLES.items():
        copied = copy.deepcopy(document["sources"]["die_inspection"])
        copied["relation"] = table
        document["sources"][source] = copied
    catalog = load_physical_catalog(str(tmp_path / "table_config.json"))
    bundle = require_ready_bundle(validate_bundle(document, catalog=catalog))
    return compile_setup_snapshot(bundle, trusted_implementations(), catalog=catalog)


def _atoms(snapshot, source, xs, first):
    rows = _v2_frame([
        {"row_id": "R%d" % (first + i), "run_uid": "U%d" % (first + i), "base_wafer_id": "W1",
         "base_x": x, "base_y": 2, "stack_gate": 1, "observed_at": "2026-09-30 10:00:00"}
        for i, x in enumerate(xs)])
    preview = preview_cursor_batch(
        snapshot, source, rows, {"run_uid": rows.iloc[-1]["run_uid"]}, role_mapper_registry(), known_registrations=())
    return list(preview.candidate_semantics)


def _evidence(semantics):
    return [ledger_subgraph.EvidenceAtom(
        id=str(uuid.UUID(int=number + 1)), subject_type=a["subject_type"],
        subject_keys=a["subject_keys"], predicate=a["predicate"], object_kind=a["object_kind"],
        object_payload=a["object_payload"], occurred_at=datetime.fromisoformat(a["occurred_at"]),
        source_who=a["source_who"], source_translator_ver=a["source_translator_ver"],
        source_raw_ref=a["source_raw_ref"], supersedes=None,
        source_event_id=a["source_event_id"], source_event_state=a["source_event_state"])
        for number, a in enumerate(semantics)]


def test_one_die_from_four_spellings_and_two_sources_is_one_node_with_all_its_facts(snapshot):
    said = (_atoms(snapshot, NUM, [1, 1.0, "01"], 1)      # a number column: int, float, '01'
            + _atoms(snapshot, TXT, ["1", "1.0"], 10))    # a text column: '1', and '1.0'
    dies = [a["object_payload"]["keys"] for a in said]
    assert [d["x"] for d in dies] == ["1", "1", "1", "1", "1.0"]
    assert {d["y"] for d in dies} == {"2"}

    lookup = ledger_subgraph.InMemoryEvidenceLookup(_evidence(said))
    body = ledger_subgraph.subgraph(explorer.entity_id("wafer", {"wafer": "W1"}), lookup, hops=1)
    die_ids = sorted(n["id"] for n in body["nodes"] if n.get("type") == "die")
    one = explorer.entity_id("die", dies[0])
    assert die_ids == sorted([one, explorer.entity_id("die", dies[-1])]), \
        "four spellings are one die; the text '1.0' is its own"
    # The response draws one edge per (subject, predicate, object); the facts are what the walk
    # FETCHES for the node - every one of them, from both sources.
    facts, _cut = lookup.claims_for_entities([("die", dies[0])], "incoming", 100)
    assert sorted(f.source_who for f in facts) == [NUM, NUM, NUM, TXT]


def test_a_text_column_keeps_its_spelling_and_a_number_column_folds_it(snapshot):
    (text_said,) = _atoms(snapshot, TXT, ["1.0"], 20)
    (number_said,) = _atoms(snapshot, NUM, ["1.0"], 21)
    assert text_said["object_payload"]["keys"]["x"] == "1.0"
    assert number_said["object_payload"]["keys"]["x"] == "1"


def test_a_registration_probe_names_a_number_key_as_the_atom_does(snapshot):
    """The probe's token and the atom's key are one spelling, or the key re-registers. The
    probe reads two things off a plan - its relation and its probes - so that is all this
    stands in for."""
    probe = type("Probe", (), {"subject_type": "die", "identity_key": "x",
                               "columns": ("base_x",), "list_separator": None})()
    driver = type("Driver", (), {"registration_probe": (probe,)})()
    plan = type("Plan", (), {"relation": TABLES[NUM], "driver": driver})()
    frame = _v2_frame([{"base_x": 1.0}, {"base_x": "01"}, {"base_x": 3}])
    assert _v2_registration_subjects(plan, frame) == {
        ("die", canonical_keys({"x": "1"})), ("die", canonical_keys({"x": "3"}))}
