# -*- coding: utf-8 -*-
"""`class` on entities and predicates - one word or a list of words (총괄 e6dd72526 · 07889c83d).

  one grammar   one word reads as a one-word list; absent, None and '' are no class
  one reader    `setup_bundle.class_words` - the static judgement, the catalogue, the resolve
                report and `follow=class:<word>` all go through it
  words         the operator's, on an entity and a predicate alike (총괄 022dcf17a); the one
                word the code reads is an entity's `static`
  one answer    the save's verdict and the loader agree on every input (the table below)
  walk          `follow=class:<word>` = every predicate carrying the word; an unknown word is
                refused by name, like an undeclared predicate
  form          written in the declaration window, saved to the file as written, read back
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from ledger import config as ledger_config
from ledger import setup_bundle, trace_router
from ledger.config_explorer_service import OntologyExplorerService
from ledger.setup import load_setup

SHIPPED = Path(__file__).resolve().parent.parent / "config" / "sample"


def _sample() -> dict:
    return json.loads((SHIPPED / "ledger_config.json.sample").read_text(encoding="utf-8"))


def _catalog():
    return setup_bundle.load_physical_catalog(SHIPPED / "table_config.json.sample")


def _classed(*_args, **_kwargs) -> dict:
    """The shipped declaration with two predicates in `model` and one in `context`."""
    document = _sample()
    vocabulary = document["vocabulary"]
    vocabulary["measures@1"]["class"] = ["model"]
    vocabulary["leads_to@1"]["class"] = ["model", "context"]
    vocabulary["inspected@1"]["class"] = "context"
    return document


# ----------------------------------------------------------------------------- one reader

@pytest.mark.parametrize("value,words", [
    ("static", ("static",)), (["static"], ("static",)), (["a", "b"], ("a", "b")),
    ([" a ", ""], ("a",)), ("", ()), (None, ()), ([], ())])
def test_one_word_and_a_list_read_the_same_way(value, words):
    assert setup_bundle.class_words({"class": value}) == words
    assert setup_bundle.class_words({}) == ()


# ------------------------------------------------------------------------------- grammar

def _issues(document):
    return {(issue.path, issue.code)
            for issue in setup_bundle.validate_bundle_errors(document, catalog=_catalog())}


def test_the_save_gate_takes_a_predicate_class_as_a_word_or_a_list():
    assert not {p for p, _c in _issues(_classed()) if p.endswith(".class")}


@pytest.mark.parametrize("value", [[3], ["a", 3], {"a": 1}])
def test_a_predicate_class_that_is_not_words_is_refused(value):
    document = _sample()
    document["vocabulary"]["measures@1"]["class"] = value
    assert ("bundle.vocabulary.measures@1.class", "invalid_predicate") in _issues(document)


#: (the entity's `class`, whether the grammar refuses it). 🔴 [총괄 022dcf17a] An entity's words
#: are the operator's too - ["static", "probe"] used to pass the draft save as 「Saved」 and then
#: drop quantity@1 from the loaded declaration.
ENTITY_CLASSES = [
    ("static", False), (["static"], False), (["static", "probe"], False), ("probe", False),
    (["static", "dynamic"], False), ([""], False), ([" "], False),
    (3, True), (["a", 3], True), ({"a": 1}, True)]


@pytest.mark.parametrize("value,refused", ENTITY_CLASSES)
def test_the_save_verdict_and_the_loader_give_one_answer(value, refused, tmp_path):
    """The table: the same input through the save's verdict and through the loader. An entity
    the grammar accepts stays in what the loader returns; one it refuses is the one it drops."""
    document = _sample()
    document["entities"]["quantity@1"]["class"] = value
    saved_refuses = ("bundle.entities.quantity@1.class", "invalid_entity_ref") in _issues(document)
    path = tmp_path / "ledger_config.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    loaded = ledger_config.load(str(path), catalog=_catalog())
    loader_drops = "quantity@1" not in (loaded.get("entities") or {})
    assert (saved_refuses, loader_drops) == (refused, refused)


def test_an_operator_word_beside_static_keeps_the_type_static(monkeypatch):
    document = _sample()
    document["entities"]["quantity@1"]["class"] = ["static", "probe"]
    monkeypatch.setattr(ledger_config, "load", lambda *_args, **_kwargs: document)
    assert "quantity" in trace_router._static_types()
    types = {item["type"]: item["class"] for item in trace_router.ledger_declaration_catalog()["entities"]}
    assert types["quantity@1"] == ["static", "probe"]


# ---------------------------------------------------------------------------------- walk

class _Db:
    def connection(self):
        return None


def _walk(monkeypatch, document, follow):
    monkeypatch.setattr(ledger_config, "load", lambda *_args, **_kwargs: document)
    seen = {}
    monkeypatch.setattr(trace_router, "_evidence_graph",
                        lambda *a, **kw: seen.update(kw) or {"nodes": [], "edges": []})
    monkeypatch.setattr(trace_router, "_signed_start", lambda *a, **kw: "seed")
    trace_router.evidence_subgraph(
        node_id="seed", response_format="json", db=_Db(),
        hops=1, direction="both", since=None, until=None,
        node_limit=400, edge_limit=1200, positive=None, negative=None,
        follow=follow, backbone_hops=0, collect=None, include_superseded=False)
    return seen["follow"]


def test_follow_class_walks_every_predicate_of_that_class_and_only_those(monkeypatch):
    assert _walk(monkeypatch, _classed(), ["class:model"]) == ["leads_to", "measures"]
    assert _walk(monkeypatch, _classed(), ["observed", "class:context"]) == [
        "observed", "inspected", "leads_to"]


def test_an_unknown_class_is_refused_by_name(monkeypatch):
    with pytest.raises(HTTPException) as refused:
        _walk(monkeypatch, _classed(), ["class:nope"])
    detail = refused.value.detail
    assert refused.value.status_code == 422
    assert detail["reason"] == "predicate_class_not_declared"
    assert detail["unknown"] == ["nope"] and detail["declared"] == ["context", "model"]


def test_a_declaration_without_classes_walks_as_it_did(monkeypatch):
    assert _walk(monkeypatch, _sample(), ["inspected"]) == ["inspected"]
    with pytest.raises(HTTPException):
        _walk(monkeypatch, _sample(), ["class:model"])


def test_the_catalogue_carries_the_words_as_a_list(monkeypatch):
    monkeypatch.setattr(ledger_config, "load", _classed)
    catalogue = trace_router.ledger_declaration_catalog()
    by_name = {item["name"]: item["class"] for item in catalogue["predicates"]}
    assert by_name["measures@1"] == ["model"]
    assert by_name["inspected@1"] == ["context"], "one word reads as a one-word list"
    assert by_name["observed@1"] is None
    types = {item["type"]: item["class"] for item in catalogue["entities"]}
    assert types["quantity@1"] == ["static"] and types["die@1"] is None


def test_the_static_judgement_still_reads_a_single_word(monkeypatch):
    document = _sample()
    document["entities"]["recipe@1"]["class"] = ["static"]
    monkeypatch.setattr(ledger_config, "load", lambda *_args, **_kwargs: document)
    assert trace_router._static_types() == {"quantity", "defect_kind", "recipe"}


# ---------------------------------------------------------------------- the declaration window

def test_the_window_writes_a_predicate_class_and_reads_it_back(tmp_path):
    root = tmp_path / "ontology"
    root.mkdir()
    (root / "ledger_config.json").write_text(json.dumps(_sample()), encoding="utf-8")
    catalog = _catalog()

    def service():
        return OntologyExplorerService(
            config_root=root, draft_root=tmp_path / "drafts",
            setup_loader=lambda where: load_setup(where, catalog=catalog),
            catalog_loader=lambda: catalog,
            convergence_probe=lambda expected: {
                "ontology-explorer-api": expected, "ledger-persistent-reader": expected})

    first = service()
    _, index, _ = first.active()
    draft = first.create_draft(target_key="predicate|derived_from@1",
                               base_snapshot_hash=index.snapshot_hash)
    raw = dict(draft["raw"])
    raw["class"] = ["lineage", "model"]
    saved = first.save_draft(draft["draft_id"], expected_revision=0, raw=json.dumps(raw))
    assert saved["preview_valid"] is True, saved.get("validation_errors")
    first.review_draft(draft["draft_id"], expected_revision=1)
    first.activate_draft(draft["draft_id"], expected_revision=1, reload_callback=lambda: None)

    written = json.loads((root / "ledger_config.json").read_text(encoding="utf-8"))
    assert written["vocabulary"]["derived_from@1"]["class"] == ["lineage", "model"]
    assert written["entities"]["quantity@1"]["class"] == "static", \
        "a word written alone is not rewritten into a list"

    again = service()
    _, index, _ = again.active()
    reopened = again.create_draft(target_key="predicate|derived_from@1",
                                  base_snapshot_hash=index.snapshot_hash)
    assert reopened["raw"]["class"] == ["lineage", "model"]


def test_an_entity_saved_with_an_operator_word_stays_in_the_declaration(tmp_path, monkeypatch):
    """🔴 [총괄 022dcf17a] THE WINDOW'S OWN ORDER - save, then activate with no review - and the
    type must still be in what the loader serves, with the words as written."""
    root = tmp_path / "ontology"
    root.mkdir()
    (root / "ledger_config.json").write_text(json.dumps(_sample()), encoding="utf-8")
    catalog = _catalog()
    service = OntologyExplorerService(
        config_root=root, draft_root=tmp_path / "drafts",
        setup_loader=lambda where: load_setup(where, catalog=catalog),
        catalog_loader=lambda: catalog,
        convergence_probe=lambda expected: {
            "ontology-explorer-api": expected, "ledger-persistent-reader": expected})
    _, index, _ = service.active()
    draft = service.create_draft(target_key="entity|quantity@1",
                                 base_snapshot_hash=index.snapshot_hash)
    raw = dict(draft["raw"])
    raw["class"] = ["static", "probe"]
    saved = service.save_draft(draft["draft_id"], expected_revision=0, raw=json.dumps(raw))
    assert saved["preview_valid"] is True, saved.get("validation_errors")
    service.activate_draft(draft["draft_id"], expected_revision=1, reload_callback=lambda: None)

    path = str(root / "ledger_config.json")
    real_load = ledger_config.load
    monkeypatch.setattr(ledger_config, "load", lambda *_args, **_kwargs: real_load(path, catalog=catalog))
    served = {item["type"]: item["class"]
              for item in trace_router.ledger_declaration_catalog()["entities"]}
    assert served["quantity@1"] == ["static", "probe"]
    assert "quantity" in trace_router._static_types()
