# -*- coding: utf-8 -*-
"""판정 163 ② · 166. An initial load stages CREATE events; the cursor is not involved.

Every repair of the last week -- S-53, S-54, S-65 and its letters, S-66, S-74 -- was the
cursor path being told something the outbox already knew. So the load uses the path that is
told, and "did this row sort before or after the watermark" stops being a question anyone can
get wrong.

🔴 THE PROGRESS MARKER IS THE ROW INDEX, NOT A POSITION. A cursor says "I read up to here"
and is wrong the moment a row arrives behind it; the index says "the ledger holds facts from
THIS row", which is about the row rather than about an ordering. A load that dies resumes by
asking the same question again.

🔴 AND THE QUEUE IS MEMORY. The follow-up queue is a deque, so ten million row ids cannot go
in at once: the loader enqueues a page and then blocks on its own drain, which bounds what is
held to the queue limit times the page size.

Measured 2026-09-09 on 5,000 fresh `wafer_process` rows: five pages, 18.7 s, 3.74 ms per row,
queue depth never above the limit of four, atoms +5,000 and index +5,000 with nothing left
missing.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import backfill                                          # noqa: E402
from ledger.setup import LedgerSetupError                            # noqa: E402


class _Plan:
    def __init__(self, relation, frame_row_id, planned=True, refusal=None):
        self.relation = relation
        self.frame_row_id = frame_row_id
        self.planned = planned
        self.refusal = refusal
        self.driver = type("D", (), {"cursor_columns": ("row_id",),
                                     "identity": ("row_id",)})()


def _setup(plans):
    return type("S", (), {"snapshot": type(
        "Snap", (), {"source_plans": plans, "__hash__": None})()})()


def test_the_loader_reports_the_refusal_rather_than_looping():
    """A source the loader refused is refused here in its words (총괄 f3bc02f6e)."""
    setup = _setup({"void_observation": _Plan("void_obs_observed", None, planned=False,
                                              refusal={"path": "bundle.sources.void_observation.relation", "message": "not a table that has row_id"})})
    report = backfill.load_via_events(object(), setup, "void_observation", apply=True)
    assert report["refused"] == "source_refused"
    assert report["rows"] == 0


def test_the_page_and_the_queue_limit_are_named_constants():
    """The page is one collapsed event's worth, and the limit is what bounds memory."""
    assert backfill.EVENT_LOAD_PAGE_ROWS == 1000
    assert backfill.EVENT_LOAD_QUEUE_LIMIT >= 1


def test_it_pages_by_what_the_index_does_not_name_and_stops_when_that_is_empty(monkeypatch):
    """🔴 THE LOOP'S END IS "the index names everything", not a row count or a position."""
    from ledger import followup

    pages = [["a", "b"], ["c"], []]
    asked = []

    def fake_missing(engine, setup, source, limit, after=None):
        asked.append(after)
        return pages.pop(0) if pages else []

    drained = []
    monkeypatch.setattr(backfill, "rows_missing_from_the_index", fake_missing)
    monkeypatch.setattr(followup, "enqueue",
                        lambda table, ids, kind: drained.append((table, list(ids), kind)))
    monkeypatch.setattr(followup, "queue_depth", lambda: 0)
    monkeypatch.setattr(followup, "drain_once", lambda engine, setup: None)

    setup = _setup({"s": _Plan("t", "row_id")})
    report = backfill.load_via_events(object(), setup, "s", page_rows=2, apply=True)

    assert report["pages"] == 2 and report["rows"] == 3
    assert [kind for _t, _i, kind in drained] == ["CREATE", "CREATE"]
    assert asked == [None, "b", "c"], asked


def test_a_dry_run_reads_but_stages_nothing(monkeypatch):
    from ledger import followup

    pages = [["a"], []]
    monkeypatch.setattr(backfill, "rows_missing_from_the_index",
                        lambda engine, setup, source, limit, after=None:
                        pages.pop(0) if pages else [])
    staged = []
    monkeypatch.setattr(followup, "enqueue",
                        lambda table, ids, kind: staged.append(ids))
    setup = _setup({"s": _Plan("t", "row_id")})
    report = backfill.load_via_events(object(), setup, "s")
    assert report["rows"] == 1 and report["applied"] is False
    assert staged == []
