# -*- coding: utf-8 -*-
"""S-173. A failing chunk is HALVED, not written out one event per row.

The per-row shape was right about WHERE to be fine-grained and wrong about the price. A
collapsed chunk that failed its attempts wrote one outbox event per row, and in production
that queue reached ~660,000 pending events -- at a group's plumbing cost, days of work to
find rows that would have taken about two hours collapsed.

Halving reaches the same end state -- the poison row alone, named -- for about twenty
events instead of a thousand, and the innocent rows travel as a handful of CHUNKS rather
than as 999 separate groups.

🔴 WHAT MAKES IT SAFE IS TERMINATION, AND IT NOW NEEDS TWO REASONS RATHER THAN ONE.
The per-row shape terminated by construction: its children carried `data` and no
`row_ids`, so nothing could ever split them again. A half still carries `row_ids`, so the
argument has to be made twice -- the leaf of ONE row is written per-row (and therefore
cannot split), and a depth cap refuses BY NAME above it. Both are scored below, because
the second is what turns a bug in the first into a loud stop rather than a queue.
"""
import os
import sys

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

import event_constants                                               # noqa: E402
import outbox_expand                                                 # noqa: E402


TABLE = "s173_test_table"
ROOT_TX = "s173-root-tx"


class _Event:
    def __init__(self, uuid_="s173-parent"):
        self.event_uuid = uuid_
        self.event_type = "CREATE"
        self.table_name = TABLE


class _Session:
    """Collects what would be written. `reexpand_collapsed_event` only ever `add`s."""

    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    def expunge(self, obj):
        self.added.remove(obj)


def collapsed(row_ids, *, lineage=None, tx=ROOT_TX):
    payload = {"transaction_id": tx, "source_name": "user", "row_ids": list(row_ids)}
    if lineage is not None:
        payload["reexpanded_from"] = lineage
    return payload


def split(payload, *, event=None, db=None):
    db = db or _Session()
    written = outbox_expand.reexpand_collapsed_event(
        db, event or _Event(), payload, "boom")
    return written, [child.payload for child in db.added]


# ---------------------------------------------------------------------------
# 1. Two halves, not N rows
# ---------------------------------------------------------------------------

def test_a_thousand_row_chunk_becomes_two_halves(monkeypatch):
    """KILLS: the per-row shape. One event per row is the queue this round removes."""
    written, children = split(collapsed([f"r{i}" for i in range(1000)]))

    assert written == 2, "a chunk is halved, not expanded"
    assert [len(c["row_ids"]) for c in children] == [500, 500]
    assert children[0]["row_ids"] + children[1]["row_ids"] == [
        f"r{i}" for i in range(1000)], "no row may be lost or duplicated by the split"


def test_a_split_reads_no_rows(monkeypatch):
    """⚠️ A HALF IS THE PARENT'S ENVELOPE WITH HALF THE IDS. Per-row expansion had to load
    every row to synthesize its payload; if a split still did, narrowing a large chunk
    would cost ten full reads of it."""
    def _refuse(*a, **kw):
        raise AssertionError("a split must not touch the database")

    monkeypatch.setattr(outbox_expand, "load_rows_by_ids", _refuse)
    written, _ = split(collapsed([f"r{i}" for i in range(64)]))
    assert written == 2


def test_an_odd_chunk_splits_without_losing_the_odd_row(monkeypatch):
    written, children = split(collapsed(["a", "b", "c"]))
    assert [len(c["row_ids"]) for c in children] == [1, 2]
    assert children[0]["row_ids"] + children[1]["row_ids"] == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# 2. Each half is its own group, and the family is still findable
# ---------------------------------------------------------------------------

def test_each_half_is_its_own_transaction_group():
    """The worker's unit of failure is the GROUP. Two halves sharing one id would be
    regrouped, fail together, and the split would have bought nothing."""
    _written, children = split(collapsed(["a", "b", "c", "d"]))
    ids = [c["transaction_id"] for c in children]
    assert len(set(ids)) == 2
    assert all(i.startswith(ROOT_TX) for i in ids), (
        "one prefix search must still find the whole family")
    assert ids == [f"{ROOT_TX}#half#a", f"{ROOT_TX}#half#b"]


def test_the_path_records_which_half_of_which_half():
    """`ab` reads as 「the first half, then its second half」 -- and it is what keeps two
    branches at the same depth from colliding on one id."""
    _w, first = split(collapsed([f"r{i}" for i in range(8)]))
    _w2, second = split(first[0])
    assert [c["reexpanded_from"]["path"] for c in second] == ["aa", "ab"]
    assert [c["transaction_id"] for c in second] == [
        f"{ROOT_TX}#half#aa", f"{ROOT_TX}#half#ab"]


def test_a_child_does_not_inherit_the_parents_verdict():
    """⛔ `error_log` IS WHY THE PARENT STOPPED. Carried onto a child it would make a fresh
    event look like one that already failed -- and the idempotence guard reads exactly that
    key, so an inherited one would refuse the child's own split."""
    payload = collapsed(["a", "b"])
    payload["error_log"] = {"reason": "parent died", "reexpanded_into": 2}
    _written, children = split(payload)
    assert all("error_log" not in c for c in children)


# ---------------------------------------------------------------------------
# 3. 🔴 Termination
# ---------------------------------------------------------------------------

def test_a_single_row_is_written_per_row_and_can_never_split_again(monkeypatch):
    """THE REASON THE RECURSION ENDS. A leaf carries `data` and no `row_ids`, so
    `is_collapsed_payload` is False for it."""
    class _Row:
        row_id = "r1"

    monkeypatch.setattr(outbox_expand, "load_rows_by_ids",
                        lambda db, table, ids: (object(), {"r1": _Row()}))
    monkeypatch.setattr(outbox_expand, "_data_columns", lambda model: [])
    monkeypatch.setattr(outbox_expand, "_synthesize_payload",
                        lambda row, columns, envelope: {"data": {"row_id": row.row_id}})

    written, children = split(collapsed(["r1"]))
    assert written == 1
    assert "row_ids" not in children[0]
    assert not event_constants.is_collapsed_payload(children[0]), (
        "a leaf that still looked collapsed would split for ever")


def test_halving_reaches_one_row_and_stops(monkeypatch):
    """The whole narrowing, driven: always follow the half holding the poison row, and
    count what it cost. A thousand rows must not cost a thousand events."""
    class _Row:
        def __init__(self, rid):
            self.row_id = rid

    monkeypatch.setattr(outbox_expand, "load_rows_by_ids",
                        lambda db, table, ids: (object(), {i: _Row(i) for i in ids}))
    monkeypatch.setattr(outbox_expand, "_data_columns", lambda model: [])
    monkeypatch.setattr(outbox_expand, "_synthesize_payload",
                        lambda row, columns, envelope: {"data": {"row_id": row.row_id}})

    poison = "r777"
    payload = collapsed([f"r{i}" for i in range(1000)])
    events, rounds = 0, 0
    while event_constants.is_collapsed_payload(payload):
        rounds += 1
        assert rounds <= outbox_expand.MAX_REEXPANSION_DEPTH + 2, "it did not terminate"
        written, children = split(payload)
        events += written
        assert written, "narrowing stopped before reaching the row"
        payload = next(c for c in children
                       if poison in (c.get("row_ids") or [])
                       or c.get("data", {}).get("row_id") == poison)

    assert payload["data"]["row_id"] == poison, "the narrowing found the poison row"
    assert rounds == 11, rounds
    # 🔴 THE NUMBER THIS ROUND EXISTS FOR. The per-row shape wrote 1,000 here.
    assert events == 21, events


def test_the_depth_cap_refuses_by_name_rather_than_filling_a_queue(caplog):
    """⛔ REACHING THE CAP MEANS THE LEAF RULE STOPPED ENDING THE RECURSION -- a defect in
    this function. A defect that fills a queue is exactly what this round removed, so it
    stops loudly and the caller quarantines the chunk whole."""
    caplog.set_level("ERROR")
    payload = collapsed(
        ["a", "b"],
        lineage={"depth": outbox_expand.MAX_REEXPANSION_DEPTH, "path": "a" * 12})
    written, children = split(payload)

    assert written == 0 and children == []
    assert any("refusing to split further" in r.getMessage() for r in caplog.records)


def test_the_depth_is_carried_and_grows():
    _w, children = split(collapsed(["a", "b"]))
    assert all(c["reexpanded_from"]["depth"] == 1 for c in children)
    _w2, grandchildren = split(children[1])
    assert all(c["reexpanded_from"]["depth"] == 2 for c in grandchildren)


# ---------------------------------------------------------------------------
# 4. What did not change
# ---------------------------------------------------------------------------

def test_a_parent_that_already_split_refuses_to_split_again(caplog):
    """The idempotence guard predates this round and still holds: `POST
    /admin/outbox/retry-failed` resets a FAILED parent to PENDING, and without it every
    click would narrow the same chunk again."""
    caplog.set_level("WARNING")
    payload = collapsed(["a", "b"])
    payload["error_log"] = {"reexpanded_into": 2}
    written, children = split(payload)
    assert written == 0 and children == []


def test_a_payload_naming_no_rows_is_not_narrowed():
    assert split(collapsed([]))[0] == 0
