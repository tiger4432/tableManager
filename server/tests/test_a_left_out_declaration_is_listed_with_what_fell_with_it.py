# -*- coding: utf-8 -*-
"""[총괄 57ae5c2da ②] A declaration the load leaves out after a save stays on the explorer's
unread list - with what fell with it - and the save answer names both.

🔴 THE LOADER NOW LEAVES THINGS OUT WITHOUT RAISING (S-177 ②), and the explorer filled its
unread list only when the loader RAISED - so an entity saved with a bad `class` vanished from
the list together with the predicates that name it, and the save answer named the entity
alone. `resolve_declarations` is the one seat that decides what is left out; the loader keeps
its whole report (`LedgerSetup.left_out`), the snapshot reads that, and the draft preview asks
the same seat.
"""
import json

import pytest

from ledger.config_explorer_service import OntologyExplorerService
from ledger.setup import load_setup
from test_a_declared_thing_carries_classes import _catalog, _sample

LEFT_WITH_QUANTITY = {"predicate|leads_to@1", "predicate|measures@1"}


@pytest.fixture
def root(tmp_path):
    path = tmp_path / "ontology"
    path.mkdir()
    (path / "ledger_config.json").write_text(json.dumps(_sample()), encoding="utf-8")
    return path


@pytest.fixture
def service(root, tmp_path):
    catalog = _catalog()
    return OntologyExplorerService(
        config_root=root, draft_root=tmp_path / "drafts",
        setup_loader=lambda where: load_setup(where, catalog=catalog),
        catalog_loader=lambda: catalog,
        convergence_probe=lambda expected: {
            "ontology-explorer-api": expected, "ledger-persistent-reader": expected})


def _save(service, key, change):
    """The window's order: save, then activate with no review."""
    _, index, _ = service.active()
    draft = service.create_draft(target_key=key, base_snapshot_hash=index.snapshot_hash)
    raw = dict(draft["raw"])
    change(raw)
    saved = service.save_draft(draft["draft_id"], expected_revision=0, raw=json.dumps(raw))
    service.activate_draft(draft["draft_id"], expected_revision=1, reload_callback=lambda: None)
    return saved


def _unread(service):
    payload = service.view(limit=500)
    listed = {item["key"] for item in payload["items"] if item["change_status"] == "invalid"}
    return payload["invalid"], listed


def test_a_predicate_saved_unreadable_stays_on_the_list_with_its_reason(service):
    _save(service, "predicate|derived_from@1", lambda raw: raw.__setitem__("class", 3))

    invalid, listed = _unread(service)

    record = invalid["predicate|derived_from@1"]
    assert record["blames_itself"] is True
    assert record["reasons"][0]["path"].endswith("derived_from@1.class")
    assert "predicate|derived_from@1" in listed
    # What named it fell with it, and says so in words that point at the right place.
    fell = {key: value for key, value in invalid.items() if not value["blames_itself"]}
    assert fell and all(reason["message"] == "predicate derived_from@1 left out"
                        for value in fell.values() for reason in value["reasons"])


def test_an_entity_saved_unreadable_takes_the_predicates_that_name_it_onto_the_list(service):
    saved = _save(service, "entity|quantity@1", lambda raw: raw.__setitem__("class", 3))

    invalid, listed = _unread(service)

    assert invalid["entity|quantity@1"]["blames_itself"] is True
    fell = {key for key, value in invalid.items() if not value["blames_itself"]}
    assert fell == LEFT_WITH_QUANTITY
    assert {"entity|quantity@1", *LEFT_WITH_QUANTITY} <= listed
    for key in LEFT_WITH_QUANTITY:
        assert {r["message"] for r in invalid[key]["reasons"]} == {"entity quantity@1 left out"}
        assert all(r["code"] == "blocked_by_unread_declaration" for r in invalid[key]["reasons"])

    # 🔴 THE SAVE ANSWER NAMES THEM TOO - from the same seat, before anything was activated.
    said = [(error["path"], error["message"]) for error in saved["validation_errors"]]
    assert any(path.endswith("quantity@1.class") for path, _ in said), said
    fell_said = [path for path, message in said if message == "entity quantity@1 left out"]
    assert sorted({p.split(".")[2] for p in fell_said}) == ["leads_to@1", "measures@1"], said


def test_fixing_it_takes_it_off_the_list(service):
    """Through the unread row's own door - a new-declaration draft with the row's text -
    because an unread declaration is not in the index to be selected."""
    _save(service, "entity|quantity@1", lambda raw: raw.__setitem__("class", 3))
    row = next(item for item in service.view(limit=500)["items"]
               if item["key"] == "entity|quantity@1")

    _, index, _ = service.active()
    draft = service.create_declaration_draft(
        kind="entity", canonical_id="quantity@1", base_snapshot_hash=index.snapshot_hash)
    raw = dict(row["raw"], **{"class": "static"})
    saved = service.save_draft(draft["draft_id"], expected_revision=0, raw=json.dumps(raw))
    assert saved["preview_valid"] is True, saved.get("validation_errors")
    service.activate_draft(draft["draft_id"], expected_revision=1, reload_callback=lambda: None)

    invalid, listed = _unread(service)
    assert invalid == {} and listed == set()
