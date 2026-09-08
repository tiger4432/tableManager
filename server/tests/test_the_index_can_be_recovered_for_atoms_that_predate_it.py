# -*- coding: utf-8 -*-
"""Atoms written before the row index exist without one, and a delete cannot reach them.

S-54-b, last piece. `ledger_source_row_ref` is written while the row is still there, so it
only covers what has been translated since it existed. Everything older has atoms and no
index line -- and a delete would withdraw nothing for them and say so by saying nothing.

🔴 THE RECOVERY IS A JOIN, AND IT IS THE ORPHAN SWEEP'S JOIN. A `source_raw_ref` carries the
`order_by` values of the rows it names, so those values find the row again -- and the row
carries `row_id`. `count_orphan_atoms` already asks exactly this question to decide which
atoms are orphaned, so the grouping and the predicate are shared: if the two asked
differently, this would index a row the other calls gone.

🔴 A REF THAT WILL NOT JOIN IS A FACT ABOUT THE DATA, NOT A FAULT OF THE TOOL. It means the
physical row is already gone and the atom was already an orphan. Those are counted and NAMED
and left where they are: no delete event was ever seen for them, and 「투영은 지워도 기록은
안 된다」.
"""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import backfill                                          # noqa: E402

RELATION = "dt_log"


def ref_for(job):
    """A `source_raw_ref` in the shape the translator writes: the event, and its rows."""
    return ('{"event":"%s:{\\"dt_job\\":\\"%s\\"}","rows":["%s:{\\"dt_job\\":\\"%s\\"}"]}'
            % (RELATION, job, RELATION, job))


class FakeCursor:
    """Answers the two queries this job asks and records nothing else."""

    def __init__(self, world):
        self.world = world
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        text = " ".join(sql.split())
        if text.startswith("SELECT count(DISTINCT source_raw_ref)"):
            self.rows = [(len(self.world["refs"]),)]
        elif text.startswith("SELECT DISTINCT source_raw_ref"):
            _source, limit, offset = params
            self.rows = [(ref,) for ref in self.world["refs"][offset:offset + limit]]
        else:                                        # the identity join
            self.world["joins"] += 1
            wanted = {tuple(item) for item in params[0]}
            self.rows = [(job, self.world["table"][job])
                         for (job,) in wanted if job in self.world["table"]]

    def fetchone(self):
        return self.rows[0]

    def fetchall(self):
        return list(self.rows)


class FakeConnection:
    def __init__(self, world):
        self.world = world

    def cursor(self):
        return FakeCursor(self.world)

    def commit(self):
        self.world["commits"] += 1

    def rollback(self):
        pass

    def close(self):
        pass


class FakeStore:
    def __init__(self, world):
        self.world = world

    def connection(self):
        return FakeConnection(self.world)

    def _write_row_refs(self, connection, source, pairs):
        self.world["written"].extend((source, *pair) for pair in pairs)
        return len(pairs)


@pytest.fixture
def world(monkeypatch):
    made = {"refs": [], "table": {}, "written": [], "commits": 0, "joins": 0}
    monkeypatch.setattr("ledger.store.LedgerStore", lambda engine: FakeStore(made))
    return made


def run(world, jobs_in_table, refs, **kwargs):
    world["refs"] = [ref_for(job) for job in refs]
    world["table"] = {job: f"RID-{job}" for job in jobs_in_table}
    return backfill.index_existing_refs(None, "dt_job", **kwargs)


# ---------------------------------------------------------------------- what it recovers

def test_a_ref_whose_row_is_still_there_gets_its_index_line(world):
    result = run(world, ["J1", "J2"], ["J1", "J2"], apply=True)
    assert result["indexed"] == 2 and result["refs_read"] == 2
    assert sorted(world["written"]) == [
        ("dt_job", RELATION, "RID-J1", ref_for("J1")),
        ("dt_job", RELATION, "RID-J2", ref_for("J2"))]
    assert world["commits"] == 1


def test_a_dry_run_writes_nothing_and_still_reports(world):
    result = run(world, ["J1"], ["J1"])
    assert world["written"] == [] and world["commits"] == 0
    assert result["applied"] is False and result["indexed"] == 0
    assert result["refs_read"] == 1


# ---------------------------------------------- ㉭ what will not join, counted AND named

def test_a_row_that_is_already_gone_is_counted_and_named(world):
    """🔴 ㉭. A count alone says how big the hole is; an operator cannot act on that without
    a few of the names. And it is not withdrawn: no delete event was ever seen for these,
    and a projection may be rebuilt while a record may not."""
    result = run(world, ["J1"], ["J1", "GONE"], apply=True)
    assert result["indexed"] == 1
    assert result["unindexable_refs"] == 1
    assert result["unindexable_sample"] == [
        {"relation": RELATION, "identity": {"dt_job": "GONE"}}]
    assert [row for row in world["written"] if "GONE" in row[-1]] == [], (
        "an already-orphaned atom must not be indexed against a row that is not there")


def test_a_row_that_joins_but_carries_no_row_id_is_named_too(world):
    """⚠️ FOUND AND UNUSABLE IS NOT FOUND. A relation the framework did not create -- a view,
    say -- can answer the join and carry no `row_id`, and there is nothing to index it by.
    Counting it as resolved would drop it silently: not indexed, and not on the list of
    what could not be."""
    world["refs"] = [ref_for("J1")]
    world["table"] = {"J1": None}
    result = backfill.index_existing_refs(None, "dt_job", apply=True)
    assert result["indexed"] == 0
    assert result["unindexable_refs"] == 1
    assert result["unindexable_sample"] == [
        {"relation": RELATION, "identity": {"dt_job": "J1"}}]


def test_the_sample_is_capped_but_the_count_is_not(world):
    """⚠️ A LIST THAT GREW WITHOUT BOUND WOULD BE THE REPORT'S OWN FAILURE MODE. The count
    is the fact; the names are the handful an operator starts from."""
    missing = [f"G{index}" for index in range(backfill.INDEX_BACKFILL_SAMPLE + 5)]
    result = run(world, [], missing, apply=True)
    assert result["unindexable_refs"] == len(missing)
    assert len(result["unindexable_sample"]) == backfill.INDEX_BACKFILL_SAMPLE


def test_an_unreadable_ref_is_not_an_orphan(world):
    """The orphan sweep's own distinction, kept: a ref this cannot parse is a bookkeeping
    failure of the tool, and folding it into the data's count would report one as the
    other."""
    world["refs"] = ["not a ref at all"]
    world["table"] = {}
    result = backfill.index_existing_refs(None, "dt_job", apply=True)
    assert result["unreadable_refs"] == 1 and result["unindexable_refs"] == 0


# ------------------------------------------------------------------------- what it costs

def test_it_reads_in_chunks_and_rests_between_them(world, monkeypatch):
    """🔴 PACED, AND THE PACE IS THE DECLARED ONE. This reads every distinct ref a source
    ever wrote; nobody is waiting for it, and the table every other long job reads is where
    the answer lives."""
    slept = []
    monkeypatch.setattr(backfill.time, "sleep", lambda seconds: slept.append(seconds))
    result = run(world, ["J1", "J2", "J3"], ["J1", "J2", "J3"],
                 apply=True, pace="trickle", chunk=1)
    assert result["indexed"] == 3
    # `trickle` is one unit per cycle and three seconds of rest, so three chunks rest three
    # times -- the pace is read, not assumed.
    assert slept == [3.0, 3.0, 3.0]


def test_the_fast_pace_never_sleeps(world, monkeypatch):
    slept = []
    monkeypatch.setattr(backfill.time, "sleep", lambda seconds: slept.append(seconds))
    run(world, ["J1", "J2"], ["J1", "J2"], apply=True, chunk=1)
    assert slept == []


def test_identities_are_joined_in_one_query_per_group(world):
    """One query per thousand rather than one per identity -- three sessions share this
    database, and a per-row loop is somebody else's wait."""
    run(world, ["J1", "J2", "J3"], ["J1", "J2", "J3"], apply=True)
    assert world["joins"] == 1


def test_the_grouping_and_the_join_are_the_orphan_sweeps(world):
    """⛔ TWO PREDICATES FOR ONE QUESTION IS THE FAILURE. `count_orphan_atoms` decides which
    atoms are orphaned by this same join; if they drifted, this would index a row the other
    calls gone and a delete would then find an index line pointing at nothing."""
    import inspect

    body = inspect.getsource(backfill.count_orphan_atoms)
    assert "_group_ref_identities(refs)" in body and "_join_identities(" in body
