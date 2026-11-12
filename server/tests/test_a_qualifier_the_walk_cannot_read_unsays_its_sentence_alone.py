"""Owner on ops 11-11 («all Not read», «qualifier float»): the virtual walk's compile read a qualifier from a text or
integer column only, and one it could not read left its WHOLE source out - a table_config «number» column is a float,
so a source with a measured qualifier dropped whole. A qualifier now reads the column kinds a value object reads (one
judge, `sql_translate._value`), its cell shaped as the stored translator's `_attribute_value` shapes it (9.0, 0.1,
blank, NaN - a NaN row is refused earlier on the stored page, `_row_sort_token`); one it still cannot read (a naive time
with no zone declared) unsays its sentence alone - «<sentence>: qualifier <name> not read» (owner 11-08 «per sentence»)."""
import json
import math
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import paths
from ledger import roleframe, sql_translate
from ledger.setup import load_setup
from ledger_api.ledger_subgraph import VirtualEvidenceLookup
from test_ledger_worlds_are_independent_and_meet_in_a_walk import CHANGED, _only, fixture_config  # noqa: F401

PLAIN = "wafer-processed-with-recipe"
DT = "dtwafer-processed-with-recipe"
KINDS = {"string": "text", "number": "float", "datetime": "time"}


def _compiled(config, step_columns, held=None):
    """`CHANGED`'s legs and left-out lines with each sentence's `step` read from `step_columns[sentence]`; the table holds
    a float `thick`."""
    tables = json.loads((config / "table_config.json").read_text(encoding="utf-8"))
    tables["wafer_process"]["column_types"].update(thick="number", eventtime="datetime")
    (config / "table_config.json").write_text(json.dumps(tables), encoding="utf-8")
    document = _only(CHANGED)
    for sentence, column in step_columns.items():
        document["sources"][CHANGED]["bind"]["mappings"][sentence]["bind"]["step"] = {"kind": "column", "column": column}
    (config / "ontology" / "ledger_config.json").write_text(json.dumps(document), encoding="utf-8")
    snapshot = load_setup(paths.config_path("ontology")).snapshot
    plan = snapshot.source_plans[CHANGED]
    assert plan.runs, plan.refusal
    kinds = {column: KINDS[kind] for column, kind in tables["wafer_process"]["column_types"].items()}
    return sql_translate.compile_source(snapshot, plan, dict(kinds, row_id="integer", **(held or {})), "w")


def test_a_float_qualifier_is_read(config):
    legs, unread = _compiled(config, {PLAIN: "thick", DT: "thick"})
    assert unread == []
    said = {leg.sentence: leg.qualifiers for leg in legs if leg.sentence in (PLAIN, DT)}
    assert said == {PLAIN: {"step": {"column": "thick", "kind": "float"}},
                    DT: {"step": {"column": "thick", "kind": "float"}}}


def test_a_qualifier_read_from_a_naive_time_with_no_zone_unsays_its_sentence_alone(config):
    legs, unread = _compiled(config, {PLAIN: "eventtime"}, held={"eventtime": "timestamp without time zone"})
    assert unread == [f"{PLAIN}: qualifier step not read"]
    sentences = {leg.sentence for leg in legs}
    assert PLAIN not in sentences and DT in sentences, sentences


class _Read(VirtualEvidenceLookup):
    def __init__(self):                         # no connection - `_atom` shapes a read row only
        pass

    @staticmethod
    def _ends(leg, row):
        return ("wafer", {"wafer": "W1"}), ("recipe", {"recipe": "R1"})


@pytest.mark.parametrize("cell", [9.0, 0.1, None, float("nan")], ids=["9.0", "0.1", "blank", "NaN"])
def test_a_float_qualifier_cell_says_what_the_stored_translator_says(cell):
    leg = SimpleNamespace(qualifiers={"step": {"column": "thick", "kind": "float"}}, columns_of=lambda arm: [],
                          source=CHANGED, sentence=PLAIN, value=None, predicate="processed_with", version="v",
                          relation="wafer_process", basis="b", world_name="w")
    atom = _Read()._atom(leg, ("row-1", cell, False), datetime(2026, 9, 30, tzinfo=timezone.utc))
    stored = roleframe._attribute_value({"kind": "column", "column": "thick"}, None, path="p", columns={"thick": (cell,)})
    expected = {} if stored is roleframe._NO_ATTRIBUTE_VALUE else {"step": roleframe._plain(stored)}
    assert (atom.object_payload.get("qualifiers") or {}) == expected
    assert bool(expected) == (cell is not None and not math.isnan(cell)), "canary: 9.0 and 0.1 said, blank and NaN not"
