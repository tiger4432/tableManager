# -*- coding: utf-8 -*-
"""The THIRD grammar - `dt_log` -> `transferred`. Everything provable without a database.

WHAT THIS FILE IS ACTUALLY GUARDING
------------------------------------
The atom-shape half of this file drove `ledger/transfer_translator.py` and was retired
with that module on 2026-08-18. Two things remain, and neither of them is leftovers:

  * THE DECLARATION GRAMMAR, which `ledger/config.py` still validates and still runs.
    These die with that module, not before it.
  * THE BATCH BOUNDARY - `backfill.walk_group_pages`. It uses no translator at all, and
    it is the test that caught a silent loss of 17 job-runs / 1,862 rows: a group that
    straddled a page cut was dropped and never re-read. `_FakePage` below drives the real
    walk, so a group that goes missing has nowhere to hide.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import backfill                            # noqa: E402
from ledger import config as ledger_config             # noqa: E402
from ledger import gate                                # noqa: E402

SOURCE = "dt_log"
EVENT_TIME = "2026-05-11 00:00:00"


@pytest.fixture(autouse=True)
def _clean_counters():
    gate.reset_counters()
    yield
    gate.reset_counters()


# ------------------------------------------------------------------------- declarations
def transfer_cfg(**overrides):
    cfg = {
        "kind": "transfer",
        "occurred_at_column": "event_time",
        "occurred_at_format": "%Y-%m-%dT%H:%M:%S",
        "occurred_at_timezone": "Asia/Seoul",
        "subject_types": ["Wafer"],
        "register_entity_types": ["Wafer"],
        "group": {"column": "dt_job", "row_order_column": "row_id"},
        "container": {"relation": "dt_inventory", "key_column": "dt_job",
                      "lot_column": "dt_lot", "slot_column": "dt_slot"},
        "columns": {"row_identity": "business_key_val", "group_key": "dt_job",
                    "wafer": "core_wafer", "recorded_lot": "dt_lot",
                    "recorded_slot": "dt_slot"},
    }
    cfg.update(overrides)
    return cfg


def full_cfg(**overrides):
    return {"version": 1, "sources": {SOURCE: transfer_cfg(**overrides)}}


def row(wafer="WF.010120", job="DT-EQP-01_20260511T0000_T01", **overrides):
    base = {"row_identity": f"{job}_1_3", "group_key": job, "wafer": wafer,
            "event_time": EVENT_TIME, "recorded_lot": "DT-2601-001",
            "recorded_slot": "01"}
    base.update(overrides)
    return base



# ----------------------------------------------------------------- the declaration itself
# 🗄️ RETIRED 2026-08-30 — `test_the_live_declaration_validates_and_declares_this_source`
# asserted that the operator's declaration carries `dt_log` as a TRANSFER-kind source with
# both transfer derivations. No declaration on this box does. MEASURED: the live file and
# the shipped sample carry fourteen sources between them and every one has `kind: null`;
# `config/sample/ontology/transfer_explorer/ledger_config.json` does declare a `dt_log`,
# but with no kind, no container relation and no register types, so it is not a transfer
# source either.
#
# 🔴 THIS IS THE MIRROR OF R-2026-08-29-T IN `docs/process/LEDGER_RULINGS.md`. The
# resolver's class-1 list was emptied that night for exactly this measurement -- nothing
# can stamp `job_run_to_confirmed_container` -- and this test asserted the opposite half
# of the same fact.
#
# WHAT BRINGS IT BACK: declaring a transfer source turns
# `test_every_declared_derivation_is_explicitly_classified` red until the derivation is
# classified, and that is the moment to restore this assertion with it. The GRAMMAR is
# still covered by the fixture-config tests below, which do not read the live file.


def test_a_transfer_source_that_declares_no_container_cannot_emit_the_confirmed_rule():
    cfg = full_cfg(container={"relation": None})
    ledger_config.validate(cfg)
    assert ledger_config.declared_derivations(cfg, SOURCE) == frozenset(
        {"first_sight", "job_run_to_job"})


@pytest.mark.parametrize("mutation,fragment", [
    ({"group": {"row_order_column": "row_id"}}, "group must declare the column"),
    ({"group": {"column": "dt_job"}}, "row_order_column"),
    ({"container": "dt_inventory"}, "container must declare"),
    ({"container": {"relation": "dt_inventory", "key_column": "dt_job"}}, "lot_column"),
    ({"vocabulary": {"split": {}}}, "LINEAGE declaration"),
])
def test_a_transfer_declaration_that_would_have_to_be_guessed_at_is_refused(mutation,
                                                                           fragment):
    cfg = full_cfg(**mutation)
    with pytest.raises(ledger_config.LedgerConfigError, match=fragment):
        ledger_config.validate(cfg)


def test_a_column_mapping_nothing_reads_is_refused():
    cfg = full_cfg()
    cfg["sources"][SOURCE]["columns"]["core_x"] = "core_x"
    with pytest.raises(ledger_config.LedgerConfigError, match="core_x"):
        ledger_config.validate(cfg)


def test_the_group_column_may_not_be_spelled_twice_differently():
    cfg = full_cfg()
    cfg["sources"][SOURCE]["columns"]["group_key"] = "dt_eqp"
    with pytest.raises(ledger_config.LedgerConfigError, match="group.column"):
        ledger_config.validate(cfg)


# --------------------------------------------------------------------- the batch boundary
def test_the_page_cut_never_splits_a_job_run():
    """A group that the page may have cut is DROPPED, not processed.

    The rule shared with the lineage driver, over a different column. A batch boundary
    inside a job-run would fold a FRAGMENT of the dies into `qty`, and a wrong count is the
    one defect that looks exactly like a right one.
    """
    rows = [{"group_key": "J1"}, {"group_key": "J1"}, {"group_key": "J2"}]
    kept, dropped = backfill._cut_on_group_boundary(rows, 3, key="group_key")
    assert [r["group_key"] for r in kept] == ["J1", "J1"]
    assert dropped == "J2"
    # A short page reached the end of the source: nothing is at risk, nothing is dropped.
    kept, dropped = backfill._cut_on_group_boundary(rows, 10, key="group_key")
    assert len(kept) == 3 and dropped is None


def test_a_group_bigger_than_a_page_leaves_nothing_to_process():
    """The escape hatch's precondition. When every row of a full page is one group the cut
    returns EMPTY, which is the signal the driver uses to fetch that group whole."""
    rows = [{"group_key": "J1"} for _ in range(3)]
    kept, dropped = backfill._cut_on_group_boundary(rows, 3, key="group_key")
    assert kept == [] and dropped == "J1"


def test_the_lineage_cut_is_unchanged_by_the_new_parameter():
    rows = [{"event_time": "t1"}, {"event_time": "t2"}]
    kept, dropped = backfill._cut_on_group_boundary(rows, 2)
    assert [r["event_time"] for r in kept] == ["t1"]
    assert dropped == "t2"


# ------------------------------------------------------- the dropped group comes BACK
class _FakePage:
    """A source table with a page limit, so the drop-and-resume path can be walked.

    🔴 THIS IS THE ONLY TEST IN THE PACKAGE THAT MAKES THE PAGE LOOP DROP A GROUP.
    `lot_event` is 43 rows on every box this has ever run on, so `dropped` was always
    `None` and the resume path was unreachable - which is why a cursor that advanced PAST
    the dropped group survived until a 34,939-row source ran the same loop.
    """

    def __init__(self, groups, limit):
        self.rows = [{"group_key": g, "row_identity": f"{g}-{i}"}
                     for g, n in groups for i in range(n)]
        self.limit = limit
        self.pages = 0

    def page(self, after):
        self.pages += 1
        rows = [r for r in self.rows if after is None or r["group_key"] > after]
        return rows[:self.limit]

    def group(self, key):
        return [r for r in self.rows if r["group_key"] == key]


def _walk(source, max_pages=20):
    """🔴 Drives `backfill.walk_group_pages` ITSELF, not a copy of it.

    An earlier draft of this test reimplemented the loop, which would have gone green on a
    driver that had regressed - the shape this project has already paid for twice ("a
    snippet reproduced out of context is not the behaviour"). The fetch halves are fakes;
    every rule under test is the production function's.
    """
    seen = []
    pages = backfill.walk_group_pages(source.page, source.group, "group_key", None,
                                      source.limit)
    for complete, _after, _last in pages:
        seen.extend(complete)
        if len(seen) > max_pages * source.limit:      # a runaway guard, never a page count
            raise AssertionError("walk_group_pages did not terminate")
    return seen


def test_a_group_dropped_at_a_page_boundary_is_read_on_the_next_page():
    """The defect this round measured: 17 job-runs and 1,862 rows silently gone.

    The cursor used to advance to the DROPPED group's key while the fetch is `> cursor`,
    so the group that was set aside *because it might be cut* was then skipped entirely.
    Both halves are asserted - every row arrives, and each arrives exactly once - because
    a resume that re-read a group would pass a completeness check while doubling `qty`.
    """
    source = _FakePage([("J1", 2), ("J2", 3), ("J3", 2), ("J4", 1)], limit=4)
    seen = _walk(source)
    assert [r["row_identity"] for r in seen] == [r["row_identity"] for r in source.rows]
    assert len(seen) == len(set(r["row_identity"] for r in seen)) == 8


def test_a_group_larger_than_a_page_is_read_whole_and_the_walk_continues():
    source = _FakePage([("J1", 6), ("J2", 1)], limit=4)
    seen = _walk(source)
    assert sorted(r["row_identity"] for r in seen) == sorted(
        r["row_identity"] for r in source.rows)
