# -*- coding: utf-8 -*-
"""판정 163 ② · 166. A load stages CREATE events; the cursor is not involved.

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

⚰️ 총괄 68a194f8c: these measured `load_via_events`, a second loader doing `run()`'s job under
another name. It retired; what `run()` must keep is measured on `run()`'s body here, and
its refusal of a refused source in `test_a_broken_source_falls_alone`.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import backfill                                          # noqa: E402
from ledger.setup import LedgerSetupError                            # noqa: E402


class _Plan:
    def __init__(self, relation):
        self.relation = relation


def _setup(plans):
    return type("S", (), {"snapshot": type(
        "Snap", (), {"source_plans": plans, "__hash__": None})()})()


def test_the_queue_limit_is_a_named_constant():
    """The limit is what bounds memory."""
    assert backfill.EVENT_LOAD_QUEUE_LIMIT >= 1


def test_it_pages_by_what_the_index_does_not_name_and_stops_when_that_is_empty(monkeypatch):
    """🔴 THE LOOP'S END IS "the index names everything", not a row count or a position."""
    from ledger import followup, setup_registry

    pages = [["a", "b"], ["c"], []]
    asked = []

    def fake_missing(engine, setup, source, limit, after=None):
        asked.append(after)
        return pages.pop(0) if pages else []

    drained = []
    monkeypatch.setattr(backfill, "rows_missing_from_the_index", fake_missing)
    monkeypatch.setattr(backfill, "rows_not_yet_translated", lambda *a, **k: {})
    monkeypatch.setattr(setup_registry, "cursor_translator_version", lambda *a: "v")
    monkeypatch.setattr(followup, "enqueue",
                        lambda table, ids, kind: drained.append((table, list(ids), kind)))
    monkeypatch.setattr(followup, "queue_depth", lambda: 0)
    monkeypatch.setattr(followup, "drain_once", lambda engine, setup: None)

    setup = _setup({"s": _Plan("t")})
    report = backfill._run_via_events(object(), setup, "s", page_rows=2)

    assert report["batches"] == 2 and report["rows_read"] == 3
    assert [kind for _t, _i, kind in drained] == ["CREATE", "CREATE"]
    assert asked == [None, "b", "c"], asked


def test_the_retired_option_is_refused_by_name_before_the_store(monkeypatch):
    """총괄 68a194f8c ① - an old command line is told, not run as something else."""
    from ledger import store

    class _Untouchable:
        def __init__(self, *a, **k):
            raise AssertionError("the store was opened before the refusal")

    monkeypatch.setattr(store, "LedgerStore", _Untouchable)
    with pytest.raises(LedgerSetupError) as refused:
        backfill.main(["--via-events", "--source", "s"])
    assert (refused.value.code, refused.value.path) == ("retired_option", "via_events")
    assert "run without it" in refused.value.message
