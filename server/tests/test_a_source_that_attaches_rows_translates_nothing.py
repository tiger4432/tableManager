"""A source that attaches its table's rows (총괄 10-13 행 붙이기) is read by the walk alone: every seat that runs a source -
translating, following an edit, catching up, counting, previewing, fingerprinting a cursor - leaves it out by `runs`,
and every seat that says why a source is not run names it. No atom, no row read (the lead's condition 3)."""
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ledger import backfill, followup  # noqa: E402
from ledger.setup import LedgerSetup, LedgerSetupError, _require_declared_source  # noqa: E402
from ledger.setup_registry import (AttachPlan, LedgerSetupValidationError, SourcePlan,  # noqa: E402
                                   source_cursor_fingerprint)

ATTACH = AttachPlan(predicate="has_defect", subject_type="die", subject_keys=(("die", "die", False),),
                    target_type="defect_row", target_keys=(("defect_id", "defect_id", False),),
                    columns=(("size", "number"),))


def _plans():
    return {"translated": SourcePlan(source_id="translated", relation="dt_job", driver=None, profile=None,
                                     config_path=""),
            "attached": SourcePlan(source_id="attached", relation="dt_defect", driver=None, profile=None,
                                   config_path="", attach=ATTACH),
            "retired": SourcePlan(source_id="retired", relation="dt_old", driver=None, profile=None, config_path="",
                                  status="retired")}


def _setup():
    return LedgerSetup(config_root=Path("box"), bundle=None, mappers=None,
                       snapshot=SimpleNamespace(source_plans=_plans()))


def test_runs_is_false_for_a_source_that_attaches_rows():
    plans = _plans()
    assert (plans["translated"].runs, plans["attached"].runs) == (True, False)


def test_the_name_door_refuses_it_by_name():
    """backfill.run, rescope, preview and execute pass `_require_declared_source` - a typed name meets a refusal that
    says what the source is, not a clean zero."""
    with pytest.raises(LedgerSetupError) as refused:
        _require_declared_source(_setup(), "attached")
    assert refused.value.code == "source_attaches" and "translates nothing" in str(refused.value)
    assert _require_declared_source(_setup(), "translated") == "translated"


def test_the_census_measures_no_row_of_it_and_names_it():
    """The census counts a source's rows not yet translated - for this one that would be every row, forever. It is
    skipped by name, in its own list (a retired one is another sentence)."""
    measured, retired, attaching = backfill.census_sources(_setup())
    assert (measured, retired, attaching) == (["translated"], ["retired"], ["attached"])


def test_the_row_count_and_the_index_backfill_refuse_it_in_the_panel_s_words():
    refused = backfill._loader_refusal(_plans()["attached"])
    assert refused["refused"] == "source_attaches" and refused["refused"] in backfill.CENSUS_NAMES
    assert backfill._loader_refusal(_plans()["translated"]) is None


def test_an_edit_to_its_table_follows_no_source_of_it():
    """The follow-up translates the sources that read an edited table - this one translates nothing."""
    setup = _setup()
    assert followup.sources_for_table(setup, "dt_defect") == ()
    assert followup.sources_for_table(setup, "dt_job") == ("translated",)


def test_it_has_no_cursor_to_fingerprint():
    snapshot = SimpleNamespace(source_plans=_plans())
    with pytest.raises(LedgerSetupValidationError) as refused:
        source_cursor_fingerprint(snapshot, "attached")
    assert refused.value.code == "source_attaches"


def test_the_chain_graph_draws_no_ledger_arrow_from_its_table():
    """A ledger arrow says rows flow into the ledger - attached rows flow to the walk."""
    from chain import graph

    edges = graph._ledger_edges(None, _setup())
    assert [edge["source"] for edge in edges] == ["retired", "translated"]
