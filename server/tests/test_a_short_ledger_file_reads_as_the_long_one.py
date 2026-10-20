# -*- coding: utf-8 -*-
"""The ledger file written short (setup_version 7, 소유자 10-13 「read 관련 다 빼고 소스 맵핑만」 ·
10-14 «ㄹ»): `shorten_setup` writes it, `expand_short_form` reads it back - one module's pair.

  the converter        each tracked declaration's sources: same · mixes (the read cells that move) ·
                       dropped (retired, not writable short) · refused (the file is not written)
  same                 a same source's row is translated to the same atoms, ids included
  the loader           a v6 file is read as it is, with one note naming the converter
                       a v7 file is read through the same expansion - same fingerprints
  the short shape      refused on its own paths, before the expansion
  the explorer         a long body activated into a short file is written short; a part is refused
"""
import copy
import json
import logging
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from declaration_names import fold_versions                               # noqa: E402
from ledger import setup_bundle as sb                                     # noqa: E402
from ledger.backfill import _v2_frame                                     # noqa: E402
from ledger.implementations import role_mapper_registry, trusted_implementations  # noqa: E402
from ledger.runtime_v2 import last_cursor, preview_cursor_batch           # noqa: E402
from ledger.setup_registry import compile_setup_snapshot, cursor_translator_version  # noqa: E402
from scripts import migrate_ledger_config_to_v7 as v7                     # noqa: E402
from scripts import migrate_ledger_config_to_v6 as v6                     # noqa: E402
from ledger.roleframe import when_says  # noqa: E402

SERVER = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SAMPLE = os.path.join(SERVER, "config", "sample")
CATALOG = sb.load_physical_catalog(os.path.join(SAMPLE, "table_config.json.sample"))


def _read(*parts):
    with open(os.path.join(SERVER, *parts), encoding="utf-8") as fh:
        return json.load(fh)


def _sample():
    return _read("config", "sample", "ledger_config.json.sample")


def _verdicts(lines):
    return {line.split()[0]: line.split()[1] for line in lines}


@pytest.mark.parametrize("parts, said, written", [
    (("config", "sample", "ledger_config.json.sample"),
     {"die_inspection": "same", "lot_slot_wafer": "same", "transfer_event": "same",
      "dt_job": "mixes", "lot_lineage": "mixes", "wafer_process_recipe": "mixes",
      "lot_event": "dropped"}, True),
    (("config", "sample", "ontology", "transfer_explorer", "ledger_config.json"),
     {"virtual_joins": "refused", "dt_log": "refused"}, False),
    (("tests", "support", "v5_setup", "ledger_config.json"),
     {"lot_event": "refused", "die_inspection": "same", "dt_job": "mixes", "transfer_event": "same",
      "wafer_process_recipe": "mixes", "lot_slot_wafer": "same"}, False),
])
def test_each_tracked_declaration_s_sources_are_said_one_way(parts, said, written):
    _short, lines, wrote = v7.convert(_read(*parts), CATALOG)
    assert (_verdicts(lines), wrote) == (said, written)


def test_a_mixing_source_names_the_read_cells_that_move():
    _short, lines, _ = v7.convert(_sample(), CATALOG)
    moves = {line.split()[0]: line.split(" - ", 1)[1].split(":")[0] for line in lines
             if line.split()[1] == "mixes"}
    assert moves == {"dt_job": "occurred_at stored ingested -> event_time",
                     "lot_lineage": "order_by event_time+lot_lineage_key -> lot_lineage_key",
                     "wafer_process_recipe": "identity row_id -> proc_id, order_by row_id -> proc_id"}


def _compiled(document):
    bundle = sb.require_ready_bundle(sb.validate_bundle(document, catalog=CATALOG))
    return compile_setup_snapshot(bundle, trusted_implementations(), catalog=CATALOG)


def _row(relation):
    """One row a table can hold, every column filled by its type - a time held as text included."""
    spelled = {"number": 1, "datetime": "2026-09-30 10:00:00", "boolean": True}
    types = CATALOG[relation]["columns"]
    return {"row_id": "R1", **{column: spelled["datetime"] if "time" in column else spelled.get(kind, "S1")
                               for column, kind in types.items()}}


@pytest.mark.parametrize("source", ["die_inspection", "lot_slot_wafer", "transfer_event"])
def test_a_same_source_s_row_is_translated_to_the_same_atoms(source):
    long = fold_versions(_sample())
    short, _verdicts_ = sb.shorten_setup(long, says=when_says)

    def atoms(document):
        compiled = _compiled(document)
        frame = _v2_frame([_row(compiled.source_plans[source].relation)])
        preview = preview_cursor_batch(compiled, source, frame,
                                       last_cursor(compiled.source_plans[source], frame),
                                       role_mapper_registry(), known_registrations=())
        # the stamp is the fingerprint's, and the retired approval words move it - not an atom
        return sorted(json.dumps({**atom, "source_translator_ver": None}, sort_keys=True, default=str)
                      for atom in preview.candidate_semantics)

    said = atoms(long)
    assert said and atoms(short) == said


def _root(tmp_path, document):
    root = tmp_path / "ontology"
    root.mkdir()
    (root / sb.CONFIG_FILENAME).write_text(json.dumps(document), encoding="utf-8")
    return root


def test_a_v6_file_is_read_as_it_is_with_one_note(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(sb, "_V7_SAID", set())
    caplog.set_level(logging.INFO, logger="Ledger.Config")
    loaded = sb.load_setup_bundle(_root(tmp_path, _sample()), catalog=CATALOG)
    sb.load_setup_bundle(tmp_path / "ontology", catalog=CATALOG)

    assert loaded.to_mapping() == sb.validate_bundle(_sample(), catalog=CATALOG).to_mapping()
    assert [r.getMessage() for r in caplog.records if "read as it is" in r.getMessage()] == [
        "[Ledger] setup_version 6 read as it is - Next: scripts/migrate_ledger_config_to_v7.py "
        "writes it short (preview first)"]


def test_a_v7_file_is_read_through_the_same_expansion(tmp_path, monkeypatch, caplog):
    short, _lines, _ = v7.convert(_sample(), CATALOG)
    monkeypatch.setattr(sb, "_V7_SAID", set())
    caplog.set_level(logging.INFO, logger="Ledger.Config")
    bundle = sb.load_setup_bundle(_root(tmp_path, short), catalog=CATALOG)
    sb.validate_bundle(sb.upgrade_setup(short), catalog=CATALOG)     # the expanded document comes back too
    assert not [r for r in caplog.records if "read as it is" in r.getMessage()]
    compiled = compile_setup_snapshot(bundle, trusted_implementations(), catalog=CATALOG)
    today = _compiled(v7._without_retired_words(fold_versions(_sample())))

    for source in ("die_inspection", "lot_slot_wafer", "transfer_event"):
        assert cursor_translator_version(compiled, source) == cursor_translator_version(today, source)
    assert compiled.source_plans["transfer_event"].relation == "dt_transfer_log"


def _short_errors(change):
    short, _verdicts_ = sb.shorten_setup(fold_versions(_sample()), says=when_says)
    change(short)
    return [(e.code, e.path) for e in sb.validate_bundle_errors(short, catalog=CATALOG)]


def test_a_short_shape_is_refused_on_its_own_path():
    def a_number_for_a_column(short):
        short["sources"]["transfer_event"]["sentences"][0]["subject"]["keys"]["lot"] = 5

    def a_join(short):
        short["virtual_joins"] = {"j": {}}

    def a_sentence_twice(short):
        sentences = short["sources"]["dt_job"]["sentences"]
        sentences.append(copy.deepcopy(sentences[0]))

    assert _short_errors(a_number_for_a_column) == [
        ("invalid_binding", "bundle.sources.transfer_event.sentences[0].subject.keys.lot")]
    assert _short_errors(a_join) == [("virtual_joins_retired", "ledger_config.virtual_joins")]
    assert _short_errors(a_sentence_twice) == [
        ("duplicate_sentence", "bundle.sources.dt_job.sentences[2].sentence")]


def test_a_long_body_activated_into_a_short_file_is_written_short(tmp_path):
    from ledger.config_drafts import OntologyDraftStore
    from ledger.config_explorer import ConfigExplorerError

    short, _lines, _ = v7.convert(_sample(), CATALOG)
    path = _root(tmp_path, short) / sb.CONFIG_FILENAME
    body = fold_versions(_sample())["sources"]["transfer_event"]
    store = OntologyDraftStore(tmp_path / "drafts")
    store._activate_file(path, [(("sources", "transfer_event"), body)], catalog=CATALOG)

    assert json.loads(path.read_text(encoding="utf-8"))["sources"]["transfer_event"] == \
        short["sources"]["transfer_event"]
    with pytest.raises(ConfigExplorerError) as part:
        store._activate_file(path, [(("sources", "transfer_event", "bind"), body["bind"])])
    assert part.value.code == "short_file_takes_a_source"


def test_the_v6_script_leaves_a_v7_file_alone(tmp_path, monkeypatch, capsys):
    from ledger import admin

    short, _lines, _ = v7.convert(_sample(), CATALOG)
    path = _root(tmp_path, short) / sb.CONFIG_FILENAME
    monkeypatch.setattr(admin, "sources_path", lambda: str(path))
    monkeypatch.setattr(admin, "table_config_path",
                        lambda: os.path.join(SAMPLE, "table_config.json.sample"))
    monkeypatch.setattr(admin, "chain_rules_path",
                        lambda: os.path.join(SAMPLE, "chain_rules.json.sample"))
    before = path.read_text(encoding="utf-8")

    assert v6.main(["--apply"]) == 0
    assert "Already v7" in capsys.readouterr().out and path.read_text(encoding="utf-8") == before


@pytest.mark.parametrize("excluded, said", [
    ([{"column": "lot", "blank": True}], {"lot": {"not": ""}}),
    ([{"when": {"kind": "bbox"}}], {"kind": {"not": "bbox"}}),
    ([{"when": {"kind": {"not": "die"}}}], {"kind": "die"}),
    ([{"when": {"kind": "bbox", "lot": "L1"}}], None),
    # 총괄 10-20 (소유자 「둘 다 물을 수도 있지, 막지 마」): one column's two clauses are «none of them»
    ([{"column": "kind", "blank": True}, {"when": {"kind": "bbox"}}], {"kind": {"not": ["", "bbox"]}}),
    ([{"when": {"kind": "bbox"}}, {"when": {"kind": "bbox"}}], {"kind": {"not": "bbox"}}),
    ([{"when": {"kind": {"not": "die"}}}, {"when": {"kind": "bbox"}}], {"kind": "die"}),
])
def test_a_row_the_read_excluded_is_a_row_no_sentence_says(excluded, said):
    source = copy.deepcopy(fold_versions(_sample())["sources"]["transfer_event"])
    source["read"]["exclude_when"] = excluded
    short, why = sb.shorten_source(source, says=when_says)
    if said is None:
        assert short is None and "several columns" in why
    else:
        assert {json.dumps(s.get("when"), sort_keys=True) for s in short["sentences"]} == {
            json.dumps(said, sort_keys=True)}


@pytest.mark.parametrize("own, excluded, said", [
    ("die", {"when": {"kind": "bbox"}}, "die"),            # A != B: the exclusion says nothing more
    ("die", {"when": {"kind": "die"}}, None),              # A == B: no row says the sentence
    ("die", {"column": "kind", "blank": True}, "die"),
])
def test_a_sentence_s_own_condition_and_an_exclusion_on_its_column(own, excluded, said):
    source = copy.deepcopy(fold_versions(_sample())["sources"]["transfer_event"])
    next(iter(source["bind"]["mappings"].values()))["when"] = {"kind": own}
    source["read"]["exclude_when"] = [excluded]
    short, why = sb.shorten_source(source, says=when_says)
    if said is None:
        assert short is None and why.startswith(
            "sentence 'die-transfer' is said for no row: its when asks 'kind' \"die\" and read.exclude_when[0] asks "
            "'kind' {\"not\": \"die\"}")
    else:
        assert [s["when"] for s in short["sentences"]] == [{"kind": said}]


def test_two_exclusions_of_one_column_written_short_translate_to_the_same_atoms():
    """The owner's file's shape (총괄 10-20): a blank clause and a value clause on one column - the short file says
    the rows the long one kept, and reads back through its expansion to its own fingerprint."""
    long = fold_versions(_sample())
    long["sources"]["transfer_event"]["read"]["exclude_when"] = [
        {"column": "product", "blank": True}, {"when": {"product": "P9"}}]
    short, verdicts = sb.shorten_setup(copy.deepcopy(long), says=when_says)
    assert verdicts["transfer_event"] == (sb.SHORTENED, "")
    assert [s["when"] for s in short["sources"]["transfer_event"]["sentences"]] == [{"product": {"not": ["", "P9"]}}]

    def atoms(document):
        compiled = _compiled(document)
        rows = [dict(_row("dt_transfer_log"), row_id="R%d" % k, dt_cell_key="C%d" % k, product=product)
                for k, product in enumerate(["P1", "", "P9", None, "P2"])]
        frame = _v2_frame(rows)
        preview = preview_cursor_batch(compiled, "transfer_event", frame,
                                       last_cursor(compiled.source_plans["transfer_event"], frame),
                                       role_mapper_registry(), known_registrations=())
        return sorted(json.dumps({**atom, "source_translator_ver": None}, sort_keys=True, default=str)
                      for atom in preview.candidate_semantics)

    said = atoms(long)
    assert said and atoms(short) == said
    unexcluded = copy.deepcopy(long)
    del unexcluded["sources"]["transfer_event"]["read"]["exclude_when"]
    assert len(atoms(unexcluded)) > len(said), "the three blank or P9 rows are not said - the cell is not vacuous"
    expanded = {**short, "sources": {**short["sources"],
                                     "transfer_event": sb.expand_source(short["sources"]["transfer_event"])}}
    assert cursor_translator_version(_compiled(short), "transfer_event") == \
        cursor_translator_version(_compiled(expanded), "transfer_event")


@pytest.mark.parametrize("value, ok", [
    ({"not": ["", "P9"]}, True), ({"not": ["a", 1, True]}, True), ({"not": []}, False),
    ({"not": [{"x": 1}]}, False), ({"not": [None]}, False), ({"not": [["a"]]}, False)])
def test_a_column_that_is_none_of_several_values_is_one_condition(value, ok):
    from ledger.roleframe import when_says

    problems = sb._Problems()
    sb._validate_when({"c": value}, "when", problems)
    assert (not problems.finish()) is ok
    if ok:
        assert [when_says(cell, value) for cell in ("", None, "  ", "P9", "a", "1", 1.0, "x")] == [
            "" not in value["not"], "" not in value["not"], "" not in value["not"], "P9" not in value["not"],
            "a" not in value["not"], 1 not in value["not"], 1 not in value["not"], True]


def test_the_explorer_s_authoring_reads_a_short_file_as_the_loader_does(tmp_path):
    from ledger.config_explorer_service import OntologyExplorerService

    short, _lines, _ = v7.convert(_sample(), CATALOG)
    service = OntologyExplorerService(config_root=_root(tmp_path, short),
                                            draft_root=tmp_path / "drafts", catalog_loader=lambda: CATALOG)
    plan = service.authoring(selection_prefix="bundle.sources.transfer_event")

    relation = [f for f in plan["fields"] if f["path"] == "bundle.sources.transfer_event.relation"]
    assert [f.get("value") for f in relation] == ["dt_transfer_log"]
    assert "declarative-role" in json.dumps(service.authoring_schema())


def test_a_read_cell_the_short_form_would_drop_refuses_the_activation_by_its_name(tmp_path):
    """검수 1: an identity the operator wrote is not dropped in silence - the file stays as it was."""
    from ledger.config_drafts import OntologyDraftStore
    from ledger.config_explorer import ConfigExplorerError

    short, _lines, _ = v7.convert(_sample(), CATALOG)
    path = _root(tmp_path, short) / sb.CONFIG_FILENAME
    before = path.read_text(encoding="utf-8")
    body = copy.deepcopy(fold_versions(_sample())["sources"]["transfer_event"])
    body["read"].update({"identity": ["row_id"], "order_by": ["row_id"]})

    with pytest.raises(ConfigExplorerError) as refused:
        OntologyDraftStore(tmp_path / "drafts")._activate_file(
            path, [(("sources", "transfer_event"), body)], catalog=CATALOG)
    assert refused.value.code == "not_writable_short" and "read.identity" in str(refused.value)
    assert path.read_text(encoding="utf-8") == before


def test_a_source_the_loader_refuses_today_that_the_short_file_reads_starts():
    """검수 2: refused on a cell the short form does not write - said as starting, not as refused after."""
    document = _sample()
    document["sources"]["transfer_event"]["read"]["order_by"] = ["no_such_column"]
    _short, lines, written = v7.convert(document, CATALOG)
    assert written and [line.split()[1] for line in lines if line.split()[0] == "transfer_event"] == ["starts"]


@pytest.mark.parametrize("value", [None, float("nan"), "", "  ", "x", 0])
def test_a_blank_row_is_judged_the_same_before_and_after_the_conversion(value):
    """검수 3: `exclude_when` blank and the sentence's when {"not": ""} - one judgement of empty."""
    from ledger.event_frame import row_excluded
    from ledger.roleframe import _unit_says

    excluded = row_excluded([{"column": "c", "blank": True}], lambda column: value)
    assert _unit_says({"c": (value,)}, {"c": {"not": ""}}) is (not excluded)


def test_a_node_typed_from_a_column_with_attributes_is_refused_by_name():
    """검수 4: a draft that would not compile is a named refusal, not a 500."""
    source = copy.deepcopy(fold_versions(_sample())["sources"]["transfer_event"])
    mapping = next(iter(source["bind"]["mappings"].values()))
    mapping["bind"]["subject"]["entity_type"] = {"kind": "column", "column": "kind"}
    mapping["bind"]["subject"]["attributes"] = {"a": {"kind": "column", "column": "a"}}
    short, why = sb.shorten_source(source, says=when_says)
    assert short is None and "read from a column" in why
