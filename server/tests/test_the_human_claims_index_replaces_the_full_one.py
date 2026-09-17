# -*- coding: utf-8 -*-
"""쓰기 경로가 읽기 경로의 인덱스를 대신 내지 않는다 (S-118, 판정 245-b).

🔴 WHAT IT COST. `idx_sources_by_source` indexed all 34M rows of `cell_sources` on
(table_name, source_name, column_name, row_id) so that "withdraw one source" - a rare,
batched, by-hand operation - could bound its scope. Measured on the QA box: 5,164 MB, 38 %
of every index byte on the table, against a 5,133 MB heap, and every ingested cell updated
it. Cell writes are the ingestion path's largest single cost (54.8 % of a 20,000-row file,
94 % of that inside the driver call), so the write path was paying thousands of times a
second for a read that runs by hand.

⛔ AND THE REPLACEMENT IS NOT A SECOND SPELLING OF "user". A partial index is only useful
while its predicate is the SAME STRING its readers filter on, and the failure when they
drift is silent - the planner simply stops choosing it and every interactive withdraw goes
back to scanning. Nothing raises, no test goes red, the box just gets slower. So the value
lives in one constant and these cases pin that the seam has not been re-split.
"""
import inspect
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import models                                            # noqa: E402


def test_the_index_indexes_only_the_human_layer():
    name, ddl = models.human_claims_index_ddl()

    assert name == models.HUMAN_CLAIMS_INDEX
    assert "WHERE source_name = '%s'" % models.HUMAN_SOURCE_NAME in ddl, ddl
    assert "CONCURRENTLY" in ddl and "IF NOT EXISTS" in ddl, ddl


def test_the_columns_are_the_order_both_readers_filter_in():
    """⚠️ (table_name, row_id, column_name) IS NOT A PREFERENCE. Both readers lead
    `table_name` then `row_id IN (...)`, and both select exactly (row_id, column_name) - so
    this order makes the scan an Index Only Scan for each of them. Any other order turns at
    least one of them back into a heap fetch per match, which is when a planner starts
    weighing a sequential scan again."""
    _, ddl = models.human_claims_index_ddl()

    assert '("table_name", "row_id", "column_name")' in ddl, ddl


def test_the_model_declares_the_partial_index_and_not_the_full_one():
    """A fresh database must not grow the retired index back. `create_all` builds from
    this declaration, so a name left here is a name that returns on every new install."""
    declared = {arg.name for arg in models.CellSource.__table_args__
                if hasattr(arg, "name") and arg.name}

    assert models.HUMAN_CLAIMS_INDEX in declared, sorted(declared)
    assert models.RETIRED_CLAIMS_INDEX not in declared, sorted(declared)


def _source_of(module_name, function_name):
    import importlib

    module = importlib.import_module(module_name)
    return inspect.getsource(getattr(module, function_name))


def test_both_readers_name_the_constant_rather_than_quoting_the_value():
    """🔴 THE SEAM, AND THE TEXT IS ITS SUBJECT.

    What has to hold is that the index's predicate and the readers' predicate are ONE
    decision. A behavioural assertion cannot see the difference - a reader carrying its own
    `"user"` returns exactly the same rows, just slowly - so what is asserted is the thing
    that actually differs: which spelling each file uses.
    """
    for module_name, function_name in (
            ("chain.replay", "_count_user_protected"),
            # ⚰️ `enrichment.analysis` — enrich is a chain declaration kind, so it
            #    moved into `chain/` with the rest (소유자, 2026-09-17).
            ("chain.enrichment.analysis", "_human_resolved_cells"),
    ):
        body = _source_of(module_name, function_name)
        assert "HUMAN_SOURCE_NAME" in body, (module_name, function_name, body[:400])
        # The PREDICATE, not the prose: both functions explain in their docstrings
        # what the human layer means, and a comment quoting the value is not a second
        # spelling of it - only a filter is.
        assert not re.search(r'CellSource[.]source_name\s*==\s*[\x22\x27]', body), (
            module_name, function_name)


def test_the_migration_gate_names_the_same_two_indexes():
    """⛔ A THIRD SPELLING WOULD MAKE THE GATE CHECK THE WRONG INDEX. The replacement
    section drops the old index only once the new one exists, so if either name here
    drifted from the model the gate would be looking at something that is not the
    replacement - and would then either refuse forever or drop with nothing standing in."""
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..",
                                                    "migrations")))
    import drop_redundant_layering_indexes as migration

    entries = [e for e in migration.REPLACED if e[0] == models.RETIRED_CLAIMS_INDEX]
    assert len(entries) == 1, migration.REPLACED
    _, table, replacement = entries[0]
    assert table == "cell_sources"
    assert replacement == models.HUMAN_CLAIMS_INDEX


def test_the_boot_sequence_calls_the_ensure():
    """🔴 착지는 배선이 아니다 — the same check the decision-key index needed, for the
    same reason: an ensure wired only into config reload leaves a restarted deployment
    without the index, and the reader then scans without anything saying so."""
    from chain import ingestion_worker as worker

    body = inspect.getsource(worker.start_chain_ingestion_worker)
    assert "_ensure_human_claims_index_sync" in body, body[:400]
    assert hasattr(worker, "_ensure_human_claims_index_sync")


def test_the_ensure_runs_against_a_database_that_refuses():
    """What is proved here is that the ensure gets as far as asking the engine and does
    not raise out of the boot sequence - not what the engine says. A boot that dies on an
    index build is a worse outage than a missing index."""
    from chain import ingestion_worker as worker

    class _Refuses:
        def connect(self):
            raise RuntimeError("no database here")

    class _Session:
        def get_bind(self):
            return _Refuses()

        def close(self):
            pass

    worker._ensure_human_claims_index_sync(lambda: _Session())
