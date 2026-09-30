# -*- coding: utf-8 -*-
"""총괄 8d8abfb5d (소유자 「취소 다 되게 해」) — every retroactive operation stops between pages.

`ledger_rescope` read its whole scope as one batch and `enrichment_confirm` handed its whole
queue to one call, so a cancel had nowhere to land. Both page now: a rescope page withdraws
and remakes its rows in one commit and never splits a group; a confirm page commits its
writes; the checkpoint is asked between pages, and a rerun finishes."""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from admin import retroactive                                    # noqa: E402
from chain.enrichment import analysis, candidates                # noqa: E402
from ledger import backfill                                      # noqa: E402

#: (page key, row id) - the key is constant within a group, as `_page_key` requires.
ROWS = [("a", "r1"), ("a", "r2"), ("b", "r3"), ("b", "r4"), ("b", "r5"), ("c", "r6")]


class _Plan:
    relation = "t"
    frame_row_id = "row_id"
    driver = SimpleNamespace(cursor_columns=("k",), order_by=())


class _Connection:
    def rollback(self):
        pass

    def close(self):
        pass


_ENGINE = SimpleNamespace(raw_connection=_Connection)


def _fetch(connection, plan, *, after=None, group_value=None, limit=None, scope=None):
    rows = [{"k": k, "row_id": r} for k, r in ROWS]
    if group_value is not None:
        rows = [row for row in rows if row["k"] == group_value]
    elif after is not None:
        rows = [row for row in rows if row["k"] > after]
    return rows if limit is None else rows[:limit]


def test_every_registered_operation_takes_a_cancel():
    assert {op: spec["cancellable"] for op, spec in retroactive.OPERATIONS.items()} == {
        op: True for op in retroactive.OPERATIONS}


def test_a_rescope_page_ends_on_a_group_boundary(monkeypatch):
    monkeypatch.setattr(backfill, "_fetch_v2_lineage_rows", _fetch)
    pages = [list(frame["k"]) for frame in backfill._scope_pages(_ENGINE, _Plan(), None, 2)]
    assert pages == [["a", "a"], ["b", "b", "b"], ["c"]], "a group read whole, never cut"


@pytest.fixture
def rescope_doors(monkeypatch):
    """The reads are `_fetch`; the writer records the row ids of each page it is handed."""
    import ledger.setup as setup_module
    import ledger.store as store_module

    written = []
    store = SimpleNamespace(row_refs_for=lambda relation, ids: [],
                            forget_row_refs=lambda relation, ids, source=None: 0)
    monkeypatch.setattr(backfill, "_fetch_v2_lineage_rows", _fetch)
    monkeypatch.setattr(backfill, "_scope_predicate", lambda plan, scope: scope)
    monkeypatch.setattr(setup_module, "_require_declared_source", lambda setup, source: source)
    monkeypatch.setattr(backfill, "_v2_registration_subjects", lambda plan, frame: None)
    monkeypatch.setattr(backfill, "_preview_frame", lambda e, s, src, plan, frame, **_: {
        "withdraw": len(frame), "remake": len(frame), "refs": list(frame["row_id"])})
    monkeypatch.setattr(store_module, "LedgerStore", lambda engine, **_: store)

    def _write(setup, source, frame, scope, reader, store, known_registrations=None,
               withdraw_refs=None):
        written.append(list(frame["row_id"]))
        return SimpleNamespace(
            store_result={"attempted": len(frame), "inserted": len(frame),
                          "deduped": 0, "withdrawn": len(withdraw_refs or ())},
            preview=SimpleNamespace(row_refs=[("t", r, r) for r in frame["row_id"]]))

    monkeypatch.setattr(setup_module, "execute_selected_scoped_batch", _write)
    return SimpleNamespace(setup=SimpleNamespace(snapshot=SimpleNamespace(
        source_plans={"s": _Plan()})), written=written)


def test_a_rescope_stop_leaves_whole_pages_and_a_rerun_finishes(rescope_doors):
    asked = []

    def stop_after_first(processed=None, total=None):
        asked.append(processed)
        return True

    stopped = backfill.rescope(_ENGINE, rescope_doors.setup, "s", "k", ["a", "b", "c"],
                               apply=True, page_rows=2, checkpoint=stop_after_first)
    assert (stopped["stopped"], stopped["pages"], asked) == (True, 1, [2])
    assert rescope_doors.written == [["r1", "r2"]], "the second page is not touched"
    assert stopped["withdrawn"] == stopped["inserted"] == 2

    rescope_doors.written.clear()
    done = backfill.rescope(_ENGINE, rescope_doors.setup, "s", "k", ["a", "b", "c"],
                            apply=True, page_rows=2)
    assert "stopped" not in done and done["pages"] == 3
    assert rescope_doors.written == [["r1", "r2"], ["r3", "r4", "r5"], ["r6"]]


def test_the_live_path_is_still_one_page(rescope_doors):
    """The follow-up queue passes no page size: its receipt rides one commit."""
    done = backfill.rescope(_ENGINE, rescope_doors.setup, "s", "k", ["a", "b", "c"],
                            apply=True)
    assert done["pages"] == 1 and len(rescope_doors.written) == 1


class _Control:
    def __init__(self):
        self.reported = []

    def progress(self, processed=None, total=None):
        self.reported.append((processed, total))

    def stop_requested(self):
        return True


def test_the_operator_rescope_pages_and_asks_the_run(monkeypatch):
    seen = {}

    def _rescope(*args, **kwargs):
        seen.update(kwargs)
        return {"source": "s", "scope_column": "k", "rows_in_scope": 0, "withdrawn": 0,
                "attempted": 0, "inserted": 0, "deduped": 0, "applied": False}

    monkeypatch.setattr(backfill, "rescope", _rescope)
    monkeypatch.setattr("ledger.setup.load_setup", lambda *a: None)
    control = _Control()
    retroactive._run_ledger_rescope(
        SimpleNamespace(get_bind=lambda: None),
        {"source": "s", "scope_column": "k", "scope_values": ["a"]}, lambda *a: None, control)
    assert seen["page_rows"] == backfill.RESCOPE_PAGE_ROWS
    assert seen["checkpoint"](5) is True and control.reported[-1] == (5, None)


@pytest.fixture
def confirm_doors(monkeypatch):
    calls = []
    queue = [{"row_id": "r%d" % i, "business_key_val": None, "keys": {}, "targets": {}}
             for i in range(5)]
    monkeypatch.setattr(analysis, "iter_derived_rows", lambda *a, **k: iter(queue))
    monkeypatch.setattr(candidates, "rule_auto_confirm_enabled", lambda rule: True)
    monkeypatch.setattr(candidates, "candidate_target_fields", lambda rule: ["t"])
    monkeypatch.setattr(candidates, "log_stats", lambda *a, **k: None)

    def _confirm(db, rule, keyed, apply=False, stats=None, tx_prefix=None, caps=None,
                 tx_id=None, **_):
        calls.append(([row["row_id"] for row in keyed], tx_id))
        stats["confirmed"] = stats.get("confirmed", 0) + len(keyed)
        return stats

    monkeypatch.setattr(candidates, "confirm_keys", _confirm)
    return calls


RULE = {"name": "r", "target_fields": ["t"]}


def test_a_confirm_stop_lands_between_pages_under_one_transaction(confirm_doors):
    stopped = analysis.run_auto_confirm_sweep(None, RULE, apply=True, caps={}, page_rows=2,
                                              checkpoint=lambda processed, total: True)
    assert stopped["stopped"] is True and stopped["confirmed"] == 2
    assert [ids for ids, _tx in confirm_doors] == [["r0", "r1"]]

    confirm_doors.clear()
    done = analysis.run_auto_confirm_sweep(None, RULE, apply=True, caps={}, page_rows=2)
    assert "stopped" not in done and done["confirmed"] == 5
    assert [ids for ids, _tx in confirm_doors] == [["r0", "r1"], ["r2", "r3"], ["r4"]]
    txs = {tx for _ids, tx in confirm_doors}
    assert len(txs) == 1 and None not in txs, "one sweep, one transaction id"


def test_the_operator_confirm_pages_at_the_write_chunk_and_asks_the_run(monkeypatch):
    seen = {}

    def _sweep(db, rule, **kwargs):
        seen.update(kwargs)
        return {"queue_size": 9, "rows_examined": 4, "stopped": True}

    monkeypatch.setattr(analysis, "run_auto_confirm_sweep", _sweep)
    monkeypatch.setattr(retroactive, "_enrichment_rule", lambda name: {"name": name})
    control = _Control()
    retroactive._run_enrichment_confirm(None, {"rule": "r"}, lambda *a: None, control)
    assert control.reported == [(4, None)], "a stopped sweep reports the rows it reached"
    assert seen["page_rows"] == candidates.CHUNK_SIZE
    assert seen["checkpoint"](3, 9) is True and control.reported[-1] == (3, 9)
