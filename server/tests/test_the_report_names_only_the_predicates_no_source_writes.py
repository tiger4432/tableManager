# -*- coding: utf-8 -*-
"""총괄 6142e81bc. The config report's 「No translator states …」 list is the declaration's own
answer - `setup_bundle.emitted_predicates`, the one seat. Its second answer read the retired
grammar (source kinds) and called 15 of the shipped sample's 16 words unwritten, and all 4 of
the transfer explorer's."""
import json
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import config_resolve_report as report                                 # noqa: E402
from ledger import config as ledger_config                             # noqa: E402
from ledger import setup as ledger_setup                               # noqa: E402
from ledger.setup_bundle import load_physical_catalog                  # noqa: E402

SAMPLE = os.path.join(SERVER_DIR, "config", "sample")
SHIPPED = (os.path.join(SAMPLE, "ledger_config.json.sample"),
           os.path.join(SAMPLE, "table_config.json.sample"))
TRANSFER = (os.path.join(SAMPLE, "ontology", "transfer_explorer", "ledger_config.json"),
            os.path.join(SERVER_DIR, "tests", "support", "transfer_explorer_table_config.json"))


def _die_read_from_a_column(document):
    """die's `references` edge comes only through roles whose type is read from a column - every
    role that named die (die_inspection's target, transfer_event's subject and target)."""
    document["entities"]["die@1"]["references"] = {
        "edge": "in_container@1", "to": {"entity": "wafer@1", "keys": {"wafer": "mat_id"}}}
    sources = document["sources"]
    inspected = sources["die_inspection"]["bind"]["mappings"]["die-inspected"]["bind"]
    inspected["target"]["entity_type"] = {"kind": "column", "column": "method"}
    moved = sources["transfer_event"]["bind"]["mappings"]["die-transfer"]["bind"]
    for role in ("subject", "target"):
        moved[role]["entity_type"] = {"kind": "column", "column": "product"}


def _report(tmp_path, monkeypatch, declaration, catalog, change=None):
    """The report's ledger domain on `declaration` read as the operating world's file, and the
    setup the loader compiled from that very file."""
    root = tmp_path / "world"
    root.mkdir()
    with open(declaration, encoding="utf-8") as handle:
        document = json.load(handle)
    if change:
        change(document)
    (root / ledger_config.CONFIG_FILENAME).write_text(json.dumps(document), encoding="utf-8")
    setup = ledger_setup.load_setup(root, catalog=load_physical_catalog(catalog))
    monkeypatch.setattr(ledger_config, "config_path",
                        lambda filename=ledger_config.CONFIG_FILENAME: str(root / filename))

    def compiled(root=None, **_kwargs):
        assert root is not None and os.path.samefile(root, str(root_dir)), (
            "the vocabulary is the compiled form of the very file the report read", root)
        return setup

    root_dir = root
    monkeypatch.setattr(ledger_setup, "load_setup", compiled)
    domain = report._resolve_ledger()
    assert domain["effective"], "the report read the declaration"
    return domain, setup


def _unwritten(*args, **kwargs):
    domain, _setup = _report(*args, **kwargs)
    return {name for item in domain["ineffective"]
            for name in item["fields"].get("predicates") or ()}


@pytest.mark.parametrize("files, change, unwritten", [
    (SHIPPED, None, {"bonded_from", "in_container", "leads_to", "measures", "observed",
                     "of_kind", "slot_map"}),
    (TRANSFER, None, set()),
    # the compiled vocabulary is handed over: in_container is written through the column type
    (SHIPPED, _die_read_from_a_column, {"bonded_from", "leads_to", "measures", "observed",
                                        "of_kind", "slot_map"}),
])
def test_the_report_names_only_the_words_no_source_writes(tmp_path, monkeypatch, files, change,
                                                          unwritten):
    assert _unwritten(tmp_path, monkeypatch, *files, change=change) == unwritten


def _a_source_reading_a_view(document):
    """A source the loader refuses by design: a ledger source must read a table with row_id, and
    `ledger_events` is a view in the shipped catalogue."""
    refused = json.loads(json.dumps(document["sources"]["lot_slot_wafer"]))
    refused["relation"] = "ledger_events"
    document["sources"]["reads_a_view"] = refused


@pytest.mark.parametrize("files, change", [
    (SHIPPED, None), (TRANSFER, None), (SHIPPED, _a_source_reading_a_view)])
def test_each_source_line_is_the_loaders_own_verdict(tmp_path, monkeypatch, files, change):
    """총괄 11d0b6b88: the lines asked the retired grammar's validator, and all 7 of the shipped
    sample's sources were 「rejected」. Read is what the loader planned; rejected what it refused,
    in its own sentence."""
    domain, setup = _report(tmp_path, monkeypatch, *files, change=change)
    plans = setup.snapshot.source_plans
    rejected = {item["subject"]: item["detail"] for item in domain["rejected"]
                if item["scope"] == report.SCOPE_RULE}
    read = {item["fields"]["source"] for item in domain["effective"]
            if "source" in item["fields"]}
    assert read == {name for name, plan in plans.items() if plan.planned}
    assert set(rejected) == {name for name, plan in plans.items() if not plan.planned}
    for name, detail in rejected.items():
        assert plans[name].refusal["message"] in detail
    if change:
        assert "reads_a_view" in rejected


def test_a_declaration_that_does_not_compile_is_one_line_and_no_source_is_called_read(
        tmp_path, monkeypatch):
    root = tmp_path / "world"
    root.mkdir()
    with open(SHIPPED[0], encoding="utf-8") as handle:
        (root / ledger_config.CONFIG_FILENAME).write_text(handle.read(), encoding="utf-8")
    monkeypatch.setattr(ledger_config, "config_path",
                        lambda filename=ledger_config.CONFIG_FILENAME: str(root / filename))

    def broken(*_a, **_k):
        raise ValueError("probe: does not compile")

    monkeypatch.setattr(ledger_setup, "load_setup", broken)
    domain = report._resolve_ledger()
    (line,) = [item for item in domain["rejected"] if item["scope"] == report.SCOPE_FILE]
    assert "does not compile" in line["detail"] and "probe" in line["detail"]
    assert not [item for item in domain["effective"] if "source" in item["fields"]]


def test_with_no_declaration_file_the_sample_is_shown_and_no_source_is_called_read(
        tmp_path, monkeypatch):
    root = tmp_path / "world"
    root.mkdir()
    with open(SHIPPED[0], encoding="utf-8") as handle:
        (root / (ledger_config.CONFIG_FILENAME + ".sample")).write_text(handle.read(),
                                                                       encoding="utf-8")
    monkeypatch.setattr(ledger_config, "config_path",
                        lambda filename=ledger_config.CONFIG_FILENAME: str(root / filename))
    monkeypatch.setattr(ledger_config, "sample_path", lambda path: path + ".sample")
    domain = report._resolve_ledger()
    (line,) = [item for item in domain["ineffective"] if item["scope"] == report.SCOPE_FILE]
    assert "no declaration file" in line["detail"]
    assert not [item for item in domain["rejected"] + domain["effective"]
                if "source" in item["fields"]]


def _dt_job_retired(document):
    document["sources"]["dt_job"]["status"] = "retired"


def test_a_retired_source_is_said_to_be_retired_not_read(tmp_path, monkeypatch):
    domain, setup = _report(tmp_path, monkeypatch, *SHIPPED, change=_dt_job_retired)
    assert setup.snapshot.source_plans["dt_job"].status == "retired"
    (line,) = [item for item in domain["effective"] if item["fields"].get("source") == "dt_job"]
    assert line["fields"]["status"] == "retired" and "no longer reads" in line["detail"]
