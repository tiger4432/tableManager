# -*- coding: utf-8 -*-
"""A setup_version 5 declaration is read as 6 in memory (총괄 e14416950): the one reading the loader
and the v6 migration share (`setup_bundle.upgrade_setup`).

A `direct-join` preparer computed nothing, so its body is dropped and the source reads on - one
load note for all of them. A working preparer on an active source cannot be dropped in memory: that
source alone is refused by name with the migration as its Next, and the rest of the file loads.
"""
import copy
import json
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import setup_bundle                                         # noqa: E402
from ledger.config_explorer import resolve_declarations                 # noqa: E402
from ledger.setup_bundle import load_physical_catalog, validate_bundle_errors  # noqa: E402
from scripts import migrate_ledger_config_to_v6 as v6                   # noqa: E402

HERE = os.path.dirname(__file__)
V5_LEDGER = os.path.join(HERE, "support", "v5_setup", "ledger_config.json")
SAMPLE = os.path.join(HERE, "..", "config", "sample")
NEXT = "Next: run scripts/migrate_ledger_config_to_v6.py"


@pytest.fixture(name="v5")
def fixture_v5():
    with open(V5_LEDGER, encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(name="catalog", scope="module")
def fixture_catalog():
    return load_physical_catalog(os.path.join(SAMPLE, "table_config.json.sample"))


def test_a_v5_file_of_direct_join_preparers_loads_with_one_note(v5, catalog, caplog):
    del v5["sources"]["lot_event"]
    setup_bundle._UPGRADE_SAID.clear()
    with caplog.at_level(logging.INFO, logger="Ledger.Config"):
        assert validate_bundle_errors(v5, catalog=catalog) == ()
        assert validate_bundle_errors(v5, catalog=catalog) == (), "read again: no second note"
    notes = [r.getMessage() for r in caplog.records if "read as 6" in r.getMessage()]
    assert notes == ["[Ledger] setup_version 5 read as 6: 5 source(s)' prepare section dropped "
                     "in memory (direct-join, or a retired source) - Next: run "
                     "scripts/migrate_ledger_config_to_v6.py to write it"]


def test_a_working_preparer_is_refused_by_name_and_falls_alone(v5, catalog):
    issues = validate_bundle_errors(v5, catalog=catalog)
    assert [(i.code, i.path) for i in issues] == [
        ("prepare_retired", "bundle.sources.lot_event.prepare")]
    assert NEXT in issues[0].message
    report = resolve_declarations(v5, catalog=catalog)
    assert sorted(report["invalid"]) == ["source_plan|lot_event"]
    assert sorted(report["document"]["sources"]) == [
        "die_inspection", "dt_job", "lot_slot_wafer", "transfer_event", "wafer_process_recipe"]


def test_a_v6_file_that_still_writes_prepare_is_refused_the_same_way(catalog):
    with open(os.path.join(SAMPLE, "ledger_config.json.sample"), encoding="utf-8") as handle:
        v6_document = json.load(handle)
    v6_document["sources"]["dt_job"]["prepare"] = {"implementation_id": "direct-join"}
    issues = validate_bundle_errors(v6_document, catalog=catalog)
    assert [(i.code, i.path) for i in issues] == [
        ("prepare_retired", "bundle.sources.dt_job.prepare")]


def test_what_the_loader_reads_is_what_the_migration_writes(v5):
    """Source by source, for every source both keep: the in-memory reading and the written file
    are one document. (The migration also retires lot_event and adds the lineage source - the
    two things a reader cannot do.)"""
    read = setup_bundle.upgrade_setup(copy.deepcopy(v5))
    written = copy.deepcopy(v5)
    v6.migrate(written, {}, {"rules": []})
    shared = sorted(set(read["sources"]) - {"lot_event"})
    assert shared == ["die_inspection", "dt_job", "lot_slot_wafer", "transfer_event",
                      "wafer_process_recipe"]
    assert {s: read["sources"][s] for s in shared} == {s: written["sources"][s] for s in shared}
    assert read["setup_version"] == written["setup_version"] == setup_bundle.SETUP_VERSION == 6
