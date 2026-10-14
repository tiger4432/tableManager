# -*- coding: utf-8 -*-
"""The declaration window's doors on a ledger file written short (총괄 10-14 창 문, 소유자 «창도 이대로 만들어»).

  open        a source of a short file opens as a draft whose body is short
  save        a short body is taken, held long (every reader of the record reads the grammar it read)
  new         a new source in a short file starts as the short empty body
  test run    on a draft: the draft's compiled setup, the draft's id on the answer, nothing recorded
  schema      the tables' columns and key, the entities' keys and attributes, the predicates'
              qualifiers and far end - what the window draws its chips from
"""
import copy
import json
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import setup_bundle as sb                                      # noqa: E402
from ledger import config_explorer_service as service_module                # noqa: E402
from ledger.config_explorer_service import OntologyExplorerService         # noqa: E402
from ledger.setup import load_setup                                        # noqa: E402
from scripts import migrate_ledger_config_to_v7 as v7                      # noqa: E402

SERVER = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SAMPLE = os.path.join(SERVER, "config", "sample")
CATALOG = sb.load_physical_catalog(os.path.join(SAMPLE, "table_config.json.sample"))


def _service(tmp_path):
    with open(os.path.join(SAMPLE, "ledger_config.json.sample"), encoding="utf-8") as fh:
        short, _lines, _ = v7.convert(json.load(fh), CATALOG)
    root = tmp_path / "ontology"
    root.mkdir()
    (root / sb.CONFIG_FILENAME).write_text(json.dumps(short), encoding="utf-8")
    service = OntologyExplorerService(config_root=root, draft_root=tmp_path / "drafts",
                                      setup_loader=lambda r: load_setup(r, catalog=CATALOG),
                                      catalog_loader=lambda: CATALOG)
    return service, short


def _open(service, source):
    _setup, index, _ = service.active()
    return service.create_draft(target_key=f"source_plan|{source}", base_snapshot_hash=index.snapshot_hash)


def test_a_source_of_a_short_file_opens_short(tmp_path):
    service, short = _service(tmp_path)
    assert _open(service, "transfer_event")["raw"] == short["sources"]["transfer_event"]


def test_a_short_body_is_saved_held_long_and_shown_short(tmp_path):
    service, short = _service(tmp_path)
    draft = _open(service, "transfer_event")
    body = copy.deepcopy(short["sources"]["transfer_event"])
    column = next(iter(CATALOG["dt_transfer_log"]["columns"]))
    body["sentences"][0]["when"] = {column: {"not": ""}}

    saved = service.save_draft(draft["draft_id"], expected_revision=draft["revision"], raw=json.dumps(body))

    assert saved["raw"] == body and saved["preview_valid"], saved["validation_errors"]
    held = service.draft_store.get(draft["draft_id"])["raw"]
    assert held["relation"] == body["table"] and "mappings" in held["bind"]


def test_a_new_source_in_a_short_file_starts_short(tmp_path):
    service, _short = _service(tmp_path)
    _setup, index, _ = service.active()
    draft = service.create_declaration_draft(kind="source_plan", canonical_id="new_one",
                                             base_snapshot_hash=index.snapshot_hash)
    assert draft["raw"] == {"table": "", "sentences": []}


def test_a_test_run_on_a_draft_runs_the_draft_and_records_nothing(tmp_path, monkeypatch):
    from ledger import backfill

    service, short = _service(tmp_path)
    draft = _open(service, "transfer_event")
    body = copy.deepcopy(short["sources"]["transfer_event"])
    body["sentences"][0]["sentence"] = "said-by-the-draft"
    service.save_draft(draft["draft_id"], expected_revision=draft["revision"], raw=json.dumps(body))
    ran, recorded = [], []

    def preview_first_batch(engine, setup, source, **_kw):
        ran.append((setup.mappers is not None, sorted(setup.snapshot.source_plans[source].profile.mappings)))
        # one molecule, so the answer reaches «passed» - the step that records an active run
        return SimpleNamespace(rows_read=1, pages=1, excluded_rows=None, refusals=(), rows_sample=(),
                               page_keys=(), preview=SimpleNamespace(molecule_count=1, incomplete_count=0,
                                                                     atom_count=1))

    monkeypatch.setattr(backfill, "preview_first_batch", preview_first_batch)
    monkeypatch.setattr(service_module, "_atoms_per_sentence", lambda preview, plan: [])
    monkeypatch.setattr(service, "_atoms_sample", lambda *a: None)
    monkeypatch.setattr(service, "_record_test_run", recorded.append)

    answer = service.test_run(None, source_id="transfer_event", draft_id=draft["draft_id"])
    active = service.test_run(None, source_id="transfer_event")

    assert answer["draft_id"] == draft["draft_id"] and "draft_id" not in active
    assert ran[0] == (True, ["said-by-the-draft"]) and "said-by-the-draft" not in ran[1][1]
    assert (answer["status"], active["status"]) == ("passed", "passed")
    assert [run["source_id"] for run in recorded] == ["transfer_event"]      # the active run only


def test_the_schema_carries_what_the_window_draws_from(tmp_path):
    service, _short = _service(tmp_path)
    schema = service.authoring_schema()

    assert schema["tables"]["dt_transfer_log"]["key"] == list(sb.default_ordering_key(CATALOG, "dt_transfer_log"))
    assert schema["tables"]["dt_transfer_log"]["columns"] == dict(CATALOG["dt_transfer_log"]["columns"])
    assert schema["entities"]["dtjob"] == {"keys": ["dt_job"], "attributes": ["dt_eqp"]}
    assert schema["vocabulary"]["register"]["object"] == {"kind": "none", "types": []}
    assert schema["vocabulary"]["measures"]["object"] == {"kind": "entity_ref", "types": ["quantity"]}
    assert "value" in schema["vocabulary"]["measures"]["qualifiers"]


@pytest.mark.parametrize("change, code, path", [
    (lambda body: body["sentences"].append(copy.deepcopy(body["sentences"][0])),
     "duplicate_sentence", "bundle.sources.transfer_event.sentences[1].sentence"),
    (lambda body: body.update(atributes={}), "unknown_field", "bundle.sources.transfer_event.atributes"),
])
def test_a_short_body_is_judged_in_its_own_shape_before_it_is_read_long(tmp_path, change, code, path):
    """검수 1: what the long reading would drop without a word is refused, by the short path."""
    from ledger.config_explorer import ConfigExplorerError

    service, short = _service(tmp_path)
    draft = _open(service, "transfer_event")
    body = copy.deepcopy(short["sources"]["transfer_event"])
    change(body)
    with pytest.raises(ConfigExplorerError) as refused:
        service.save_draft(draft["draft_id"], expected_revision=draft["revision"], raw=json.dumps(body))
    assert (refused.value.code, refused.value.path) == (code, path)


def test_a_body_with_a_cell_only_the_long_form_holds_is_shown_long(tmp_path):
    """검수 2: an identity the short form would drop is shown, not hidden and lost on the next save."""
    service, _short = _service(tmp_path)
    draft = _open(service, "transfer_event")
    with open(os.path.join(SAMPLE, "ledger_config.json.sample"), encoding="utf-8") as fh:
        body = json.load(fh)["sources"]["transfer_event"]
    body["read"].update({"identity": ["row_id"], "order_by": ["row_id"]})
    saved = service.save_draft(draft["draft_id"], expected_revision=draft["revision"], raw=json.dumps(body))
    assert saved["raw"]["read"]["identity"] == ["row_id"]


def test_a_refusal_is_said_where_the_short_body_writes_it(tmp_path):
    """검수 3: a column the table does not have, on the sentence's own path."""
    service, short = _service(tmp_path)
    draft = _open(service, "transfer_event")
    body = copy.deepcopy(short["sources"]["transfer_event"])
    body["sentences"][0]["when"] = {"no_such_column": "x"}
    saved = service.save_draft(draft["draft_id"], expected_revision=draft["revision"], raw=json.dumps(body))
    assert [e["path"] for e in saved["validation_errors"]] == [
        "bundle.sources.transfer_event.sentences[0].when.no_such_column"]
    assert saved["validation_errors"][0]["json_pointer"] == "/sources/transfer_event/sentences/0/when/no_such_column"


def test_a_draft_runs_only_for_its_own_source(tmp_path):
    """검수 4."""
    from ledger.config_explorer import ConfigExplorerError

    service, _short = _service(tmp_path)
    draft = _open(service, "transfer_event")
    with pytest.raises(ConfigExplorerError) as refused:
        service.test_run(None, source_id="die_inspection", draft_id=draft["draft_id"])
    assert refused.value.code == "draft_not_this_source"


def test_a_catalog_that_cannot_be_read_empties_the_tables_only(tmp_path):
    """검수 5: the lists answer without it, and say why the tables are empty."""
    service, _short = _service(tmp_path)
    service.active()

    def unreadable():
        raise OSError("table_config.json is gone")

    service._catalog_loader = unreadable
    schema = service.authoring_schema()
    assert schema["tables"] == {} and "table_config.json is gone" in schema["tables_unavailable"]
    assert schema["entities"] and schema["vocabulary"]
