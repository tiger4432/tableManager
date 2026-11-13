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


def _declared():
    (index,) = [arg for arg in models.CellSource.__table_args__ if getattr(arg, "name", None) ==
                models.HUMAN_CLAIMS_INDEX]
    return index


def test_the_index_indexes_only_the_human_layer():
    where = _declared().dialect_options["postgresql"]["where"]
    assert str(where) == "source_name = '%s'" % models.HUMAN_SOURCE_NAME, where


def test_the_columns_are_the_order_both_readers_filter_in():
    """⚠️ (table_name, row_id, column_name) IS NOT A PREFERENCE. Both readers lead
    `table_name` then `row_id IN (...)`, and both select exactly (row_id, column_name) - so
    this order makes the scan an Index Only Scan for each of them. Any other order turns at
    least one of them back into a heap fetch per match, which is when a planner starts
    weighing a sequential scan again."""
    assert [c.name for c in _declared().columns] == ["table_name", "row_id", "column_name"]


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


def test_every_reader_names_the_constant_rather_than_quoting_the_value():
    """🔴 THE SEAM, AND THE TEXT IS ITS SUBJECT.

    What has to hold is that the index's predicate and the readers' predicate are ONE
    decision. A behavioural assertion cannot see the difference - a reader carrying its own
    `"user"` returns exactly the same rows, just slowly - so what is asserted is the thing
    that actually differs: which spelling each file uses.
    """
    # ⚰️ `("chain.replay", "_count_user_protected")` STOOD FIRST IN THIS LIST. It
    #    counted the cells a replay would refuse to overwrite so a preview could show the
    #    number; the owner ruled there is no preview and replay stopped writing
    #    (d62f40730), so the reader went with the write path. The index's own comment in
    #    `models.py` said 「two readers」 and has been corrected to one.
    readers = (
            # ⚰️ `enrichment.analysis` — enrich is a chain declaration kind, so it
            #    moved into `chain/` with the rest (소유자, 2026-09-17).
            ("chain.enrichment.analysis", "_human_resolved_cells"),
    )
    assert readers, "no readers left: this case would pass by having nothing to check"
    for module_name, function_name in readers:
        body = _source_of(module_name, function_name)
        assert "HUMAN_SOURCE_NAME" in body, (module_name, function_name, body[:400])
        # The PREDICATE, not the prose: both functions explain in their docstrings
        # what the human layer means, and a comment quoting the value is not a second
        # spelling of it - only a filter is.
        assert not re.search(r'CellSource[.]source_name\s*==\s*[\x22\x27]', body), (
            module_name, function_name)
