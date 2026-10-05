# -*- coding: utf-8 -*-
"""총괄 4eb1fe98f · 5788bd81c — a node or edge name is the bare name, everywhere (소유자 10-04 「노드
엣지 명칭에 @1 요고 필요 없어 보이는데」).

The shipped sample is still spelled `x@1`: it is the old file, loaded as it is, in this file and in
every other test that reads it. `declaration_names.fold_versions` spells it bare at every read.

  an old file and the same file spelled bare     one setup: one hash, one fingerprint per source
  one name in two spellings                      refused at the spelling's own path
  a reference atom                               its tail names the entity bare
  the routes that answered with @ (declaration · gaps)   no @N
  two worlds, one old file and one bare file     one name each
  a save through the form or the explorer        the whole file written bare, one key per name
"""
import json
import os
import re
import shutil
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import paths                                                             # noqa: E402
from declaration_names import fold_versions                              # noqa: E402
from ledger.implementations import trusted_implementations              # noqa: E402
from ledger.setup_bundle import (                                        # noqa: E402
    load_physical_catalog, require_ready_bundle, validate_bundle, validate_bundle_errors)
from ledger.setup_registry import compile_setup_snapshot, source_cursor_fingerprint  # noqa: E402
from test_an_entity_reference_is_written_by_every_source_naming_it import (  # noqa: E402
    _inspection_rows, _preview, _with_reference)

SAMPLE = os.path.join(SERVER_DIR, "config", "sample")
SUFFIX = re.compile(r"[A-Za-z_]@[0-9]")


def _sample():
    with open(os.path.join(SAMPLE, "ledger_config.json.sample"), encoding="utf-8") as fh:
        return json.load(fh)


def _catalog():
    return load_physical_catalog(os.path.join(SAMPLE, "table_config.json.sample"))


def _compiled(document):
    catalog = _catalog()
    return compile_setup_snapshot(require_ready_bundle(validate_bundle(document, catalog=catalog)),
                                  trusted_implementations(), catalog=catalog)


def test_an_old_file_and_the_same_file_spelled_bare_are_one_setup():
    old = _sample()
    assert SUFFIX.search(json.dumps(old)), "canary: the sample is the old spelling"
    bare = fold_versions(old)
    assert not SUFFIX.search(json.dumps(bare))
    one, other = _compiled(old), _compiled(bare)
    assert one.snapshot_sha256 == other.snapshot_sha256
    running = sorted(name for name, plan in one.source_plans.items() if plan.runs)
    assert running
    for source in running:
        assert source_cursor_fingerprint(one, source) == source_cursor_fingerprint(other, source)
    assert not [name for name in (*one.vocabulary, *one.entities) if "@" in name]


def test_one_name_in_two_spellings_is_refused_at_the_spelling():
    document = _sample()
    document["vocabulary"]["processed_with"] = document["vocabulary"]["processed_with@1"]
    paths_refused = {error.path for error in validate_bundle_errors(document, catalog=_catalog())
                     if error.code == "invalid_name"}
    assert "bundle.vocabulary.processed_with@1" in paths_refused


def test_a_reference_atom_names_its_entity_bare():
    document = _sample()
    _with_reference(document)
    made = [a for a in _preview(_compiled(document), "die_inspection",
                                _inspection_rows()).candidate_semantics
            if a["predicate"] == "in_container"]
    assert made and {a["derivation"] for a in made} == {"entity-reference:die#0"}
    assert all(a["source_translator_ver"].endswith("#entity-reference:die#0") for a in made)


@pytest.fixture(name="config")
def fixture_config(tmp_path, monkeypatch):
    """The old sample on disk as the operating world's file - read, never edited, by the routes."""
    config = tmp_path / "config"
    (config / "ontology").mkdir(parents=True)
    shutil.copy(os.path.join(SAMPLE, "table_config.json.sample"), config / "table_config.json")
    shutil.copy(os.path.join(SAMPLE, "ledger_config.json.sample"),
                config / "ontology" / "ledger_config.json")
    monkeypatch.setattr(paths, "CONFIG_DIR", str(config))
    return config


def test_the_routes_that_answered_with_a_version_answer_bare(config):
    from ledger import trace_router

    assert SUFFIX.search((config / "ontology" / "ledger_config.json").read_text(encoding="utf-8"))
    declaration = trace_router.ledger_declaration_catalog(world=None)
    gaps = trace_router.ledger_gap_catalogue(name=None, world=None)
    assert declaration["entities"] and gaps["gaps"]                     # canary: they answered
    assert not SUFFIX.search(json.dumps(declaration, default=str))
    assert not SUFFIX.search(json.dumps(gaps, default=str))


def test_two_worlds_one_old_file_and_one_bare_walk_one_name_each(config):
    from ledger import trace_router

    root = config / "ontology_worlds" / "bare"
    root.mkdir(parents=True)
    (root / "ledger_config.json").write_text(json.dumps(fold_versions(_sample())), encoding="utf-8")
    from ledger import schema
    declaration = trace_router.ledger_declaration_catalog(world=[schema.DEFAULT_WORLD, "bare"])
    types = [item["type"] for item in declaration["entities"]]
    assert "wafer" in types and len(types) == len(set(types))


def test_a_form_save_writes_the_whole_file_bare(config, monkeypatch):
    from ledger import admin

    path = str(config / "ontology" / "ledger_config.json")
    monkeypatch.setattr(admin, "sources_path", lambda: path)
    declaration = json.loads(json.dumps(_sample()["sources"]["lot_slot_wafer"]))
    admin.save_source("lot_slot_wafer", declaration)
    written = open(path, encoding="utf-8").read()
    assert not SUFFIX.search(written)
    assert "has_wafer" in json.loads(written)["vocabulary"]


def test_an_explorer_activation_writes_one_key_per_name(config, tmp_path):
    from ledger.config_drafts import OntologyDraftStore

    path = config / "ontology" / "ledger_config.json"
    body = fold_versions(_sample())["vocabulary"]["processed_with"]
    OntologyDraftStore(tmp_path / "drafts")._activate_file(
        path, [(("vocabulary", "processed_with"), body)])
    vocabulary = json.loads(path.read_text(encoding="utf-8"))["vocabulary"]
    assert "processed_with" in vocabulary and "processed_with@1" not in vocabulary
    assert not SUFFIX.search(path.read_text(encoding="utf-8"))
