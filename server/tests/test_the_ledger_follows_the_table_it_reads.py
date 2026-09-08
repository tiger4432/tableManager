# -*- coding: utf-8 -*-
"""운영에서는 아무것도 적지 않습니다 -- 소스가 읽는 표를 체인이나 사람이 고치면 원장이 따라옵니다.

S-54. The outbox already names `(table, row_ids)` and `backfill.rescope` already re-translates
a named scope without touching the cursor; what did not exist was the step between them. This
scores that step, and it scores the two properties the ruling put ahead of the feature: the
chain's own transaction must cost what it cost before, and the queue must not be silent.

⚠️ WHAT IS NOT SCORED HERE, and why. ㉠ (atoms of other rows byte-identical), ㉡ (a second
delivery writes nothing) and ㉦ (the S-53 fixture) are statements about `rescope` against a
real ledger, and `rescope` is unchanged by this landing -- it has its own gates. What this
file can decide is everything on THIS side of the call: which events are followed, which
column aims the scope, how many calls one event costs, and what the chain path pays.
"""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pacing                                                    # noqa: E402
from ledger import backfill, followup                            # noqa: E402


# ------------------------------------------------------------------------------- fakes

class FakeDriver:
    def __init__(self, cursor_columns, identity):
        self.cursor_columns = cursor_columns
        self.identity = identity


class FakePlan:
    def __init__(self, relation, cursor_columns, identity):
        self.relation = relation
        self.driver = FakeDriver(cursor_columns, identity)


class FakeSetup:
    def __init__(self, plans):
        self.snapshot = type("S", (), {"source_plans": plans})()


class FakeCursor:
    def __init__(self, rows, seen):
        self._rows = rows
        self._seen = seen

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, query, params=None):
        # 🔴 THE COMPOSED OBJECT, NOT ITS RENDERED TEXT. `as_string` needs a live
        # connection, and rendering it would also hide the thing worth scoring: whether the
        # table and the column travel as `Identifier` (psycopg2 quotes them) or as
        # interpolated text (it does not).
        self._seen.append((repr(query), params))

    def fetchall(self):
        return self._rows


class FakeConnection:
    def __init__(self, rows, seen):
        self._rows, self._seen = rows, seen

    def cursor(self):
        return FakeCursor(self._rows, self._seen)

    def rollback(self):
        pass

    def close(self):
        pass


class FakeEngine:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def raw_connection(self):
        return FakeConnection(self.rows, self.queries)


@pytest.fixture(autouse=True)
def empty_queue():
    followup.reset()
    yield
    followup.reset()


def one_source_on(table, cursor_columns=("dt_job",), identity=("dt_job",)):
    return FakeSetup({"dt_job": FakePlan(table, cursor_columns, identity)})


def calls_to_rescope(monkeypatch, result=None):
    seen = []

    def fake(engine, setup, source, column, values, apply=False):
        seen.append({"source": source, "column": column, "values": list(values),
                     "apply": apply})
        return result or {"withdrawn": 1, "inserted": 1, "deduped": 0}

    monkeypatch.setattr(backfill, "rescope", fake)
    return seen


# ------------------------------------------------------- which events are followed at all

@pytest.mark.parametrize("event_type,followed", [
    ("EDIT", True),
    ("DELETE", True),
    ("CREATE", False),
    ("SYSTEM_RELOAD", False),
])
def test_only_a_change_to_an_existing_row_is_followed(event_type, followed):
    """🔴 ㉣ CREATE COSTS NOTHING HERE, and it is not an oversight. The forward run reads a
    new row once from the cursor; following it as well would translate the same row twice
    and buy nothing.

    ⚠️ DELETE JOINED ON 2026-09-08 (S-54-b) AND IT IS A DIFFERENT INSTRUMENT, not a wider
    scope -- see `test_a_delete_is_withdrawn_from_the_index_not_rescoped`. Until the ledger
    could name which physical row a fact came from, a DELETE here would have queued and
    then quietly done nothing, which reads as "deletes are covered"; it was refused at the
    door for exactly that reason."""
    assert followup.enqueue("dt_log", ["r1"], event_type) is followed
    assert followup.queue_depth() == (1 if followed else 0)


def test_an_event_that_names_no_row_is_not_queued():
    assert followup.enqueue("dt_log", [], "EDIT") is False
    assert followup.enqueue("dt_log", None, "EDIT") is False
    assert followup.enqueue("", ["r1"], "EDIT") is False
    assert followup.queue_depth() == 0


def test_both_envelope_shapes_are_read():
    """A per-row event carries `row_id` at the ENVELOPE level and a collapsed one carries
    `row_ids`; reading the row id out of `data` would find nothing in either."""
    assert followup.row_ids_of({"row_id": "r1", "data": {}}) == ("r1",)
    assert followup.row_ids_of({"row_ids": ["r1", "r2"]}) == ("r1", "r2")
    assert followup.row_ids_of({"data": {"row_id": {"value": "r1"}}}) == ()
    assert followup.row_ids_of(None) == ()


# ------------------------------------------------------------------- one rule, 15 sources

def test_the_scope_column_is_the_page_key_whether_the_identity_is_derived_or_not():
    """🔴 ㉲/판정 131. The two kinds of source do NOT get two rules. A source whose identity
    is a physical column and a source whose identity the preparer derives both aim with
    `cursor_columns[0]` -- for the first that IS the identity, and for the second the page
    key is a coarsening of the group, which cannot split a molecule (`_page_key`'s own
    docstring). A branch here would be the "14 and a special one" shape the ruling refused.
    """
    physical = FakePlan("dt_log", ("dt_job",), ("dt_job",))
    derived = FakePlan("lot_log", ("event_time",), ("event_group_key",))
    assert followup.scope_column(physical) == "dt_job"
    assert followup.scope_column(derived) == "event_time"
    for plan in (physical, derived):
        assert followup.scope_column(plan) == backfill._page_key(plan), (
            "the scope column must be the page key and nothing else")


# ---------------------------------------------------------- what one queued event costs

def test_a_collapsed_event_is_one_scope_and_not_a_thousand(monkeypatch):
    """🔴 ㉥. A collapsed event names up to 1,000 rows. They go into ONE scope, so a chain
    batch that touched a thousand rows costs one re-translation, not a thousand."""
    seen = calls_to_rescope(monkeypatch)
    engine = FakeEngine([("J%d" % i,) for i in range(1000)])
    followup.enqueue("dt_log", ["r%d" % i for i in range(1000)], "EDIT")
    done = followup.drain_once(engine, one_source_on("dt_log"))
    assert done["rows"] == 1000
    assert len(seen) == 1, "one event, one rescope"
    assert len(seen[0]["values"]) == 1000
    assert seen[0]["column"] == "dt_job" and seen[0]["apply"] is True
    assert len(engine.queries) == 1, "one event, one scope query"
    statement, params = engine.queries[0]
    assert "Identifier('dt_job')" in statement, (
        "the page key must travel as an identifier, not as interpolated text")
    assert "Identifier('dt_log')" in statement
    assert "row_id = ANY(%s)" in statement
    assert params == ([f"r{i}" for i in range(1000)],)


def test_a_table_no_source_reads_costs_no_query_and_no_rescope(monkeypatch):
    """🔴 ㉧. Most outbox traffic is about tables the ledger has never heard of, so the
    step must be free for them -- and free means no query either, which is why the sources
    are resolved on the drain side rather than at the door."""
    seen = calls_to_rescope(monkeypatch)
    engine = FakeEngine([("J1",)])
    followup.enqueue("something_else", ["r1"], "EDIT")
    done = followup.drain_once(engine, one_source_on("dt_log"))
    assert done["sources"] == {}
    assert seen == [] and engine.queries == []


def test_rows_that_are_gone_ask_for_no_rescope(monkeypatch):
    """`remake` with an empty scope would be a withdrawal aimed at nothing. The empty
    answer is reported rather than turned into a wider one."""
    seen = calls_to_rescope(monkeypatch)
    followup.enqueue("dt_log", ["r1"], "EDIT")
    done = followup.drain_once(FakeEngine([]), one_source_on("dt_log"))
    assert done["sources"] == {"dt_job": {"scope_values": 0}}
    assert seen == []


def test_the_same_event_twice_asks_for_the_same_scope(monkeypatch):
    """㉡ on this side of the call: a redelivery produces an IDENTICAL request, so whether
    the second one writes anything is `rescope`'s question and not a new one."""
    seen = calls_to_rescope(monkeypatch)
    setup = one_source_on("dt_log")
    for _ in range(2):
        followup.enqueue("dt_log", ["r1"], "EDIT")
        followup.drain_once(FakeEngine([("J1",)]), setup)
    assert len(seen) == 2 and seen[0] == seen[1]


def test_a_failed_batch_is_named_and_not_requeued(monkeypatch):
    """⛔ NO POISONED ROW. A batch that cannot be followed is counted and dropped, because
    a head that never clears holds everything behind it -- and the retroactive run, which is
    this queue's canonical filler, is where a retry belongs."""
    def boom(*args, **kwargs):
        raise RuntimeError("no")

    monkeypatch.setattr(backfill, "rescope", boom)
    followup.enqueue("dt_log", ["r1"], "EDIT")
    done = followup.drain_once(FakeEngine([("J1",)]), one_source_on("dt_log"))
    assert "RuntimeError" in done["sources"]["dt_job"]["error"]
    assert followup.queue_depth() == 0, "a failed event must not go back on the queue"
    assert "failed=1" in followup.note()


def test_an_empty_queue_drains_to_nothing():
    assert followup.drain_once(FakeEngine([]), one_source_on("dt_log")) is None


# ------------------------------------------------------------------- the queue is not mute

def test_the_queue_says_what_it_is_holding():
    """🔴 ㉪ 「쌓이는데 조용」 ⛔. An idle queue says nothing -- an instrument that talks
    during healthy operation gets filtered out -- and a queue holding anything says so on
    the channel `/health` already reads."""
    assert followup.note() is None
    followup.enqueue("dt_log", ["r1"], "EDIT")
    said = followup.note()
    assert "waiting=1" in said and "oldest=" in said


def test_the_worker_heartbeat_carries_it():
    """The digest rides the note the chain worker already sends, rather than a second
    channel: `/health` reads that note across the process boundary today."""
    import chain_ingestion_worker as worker

    assert worker.ledger_followup is followup
    followup.enqueue("dt_log", ["r1"], "EDIT")
    assert "ledger follow-up" in (worker._worker_note() or "")


def test_a_full_queue_drops_loudly_rather_than_quietly(monkeypatch):
    monkeypatch.setattr(followup, "MAX_QUEUED_EVENTS", 2)
    for i in range(4):
        followup.enqueue("dt_log", ["r%d" % i], "EDIT")
    assert followup.queue_depth() == 2
    assert "dropped=2" in followup.note()


# --------------------------------------------------------------- what the chain path pays

class FakeEvent:
    def __init__(self, table_name, event_type, payload):
        self.table_name = table_name
        self.event_type = event_type
        self.payload = payload


def test_the_chain_group_queues_above_its_trigger_filter_and_translates_nothing(monkeypatch):
    """🔴 ㉤ AND ㉩ IN ONE RUN.

    ㉤ -- the subject is the OUTBOX EVENT, not a chain rule. A person editing a cell in the
    grid produces an event no rule matches, and `process_chain_transaction_group` RETURNS
    EARLY on that. The queueing therefore has to sit above that return, and this passes it
    zero rules to prove it does.

    ㉩ -- and the chain path itself must translate nothing. `rescope` is replaced with a
    detonator: if the follow-up were inline, the chain transaction would pay for it here.
    """
    import chain_ingestion_worker as worker

    def boom(*args, **kwargs):
        raise AssertionError("the chain path re-translated inline")

    monkeypatch.setattr(backfill, "rescope", boom)
    events = [FakeEvent("dt_log", "EDIT", {"row_id": "r1"}),
              FakeEvent("dt_log", "EDIT", {"row_ids": ["r2", "r3"]}),
              FakeEvent("dt_log", "CREATE", {"row_id": "r4"})]
    ok, reason, messages = asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        worker.process_chain_transaction_group("tx", events, None, []))
    assert ok is True and reason is None and messages == []
    assert followup.queue_depth() == 2, (
        "both EDIT shapes queued, the CREATE did not, and no rule was needed for any of it")


def test_an_empty_queue_never_becomes_a_hot_loop(monkeypatch):
    """🔴 THE PACE ANSWERS "HOW HARD MAY I PUSH", NOT "HOW OFTEN DO I LOOK". `fast`
    declares zero rest, and zero rest around an empty deque is a spin -- on the chain
    worker's own event loop. So an idle cycle waits the floor whatever the declaration
    says, and this drives the loop with the fastest pace there is to prove it."""
    import chain_ingestion_worker as worker

    class Stop(Exception):
        pass

    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)
        raise Stop

    monkeypatch.setattr(worker.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(pacing, "job_pace", lambda job: (None, 0))
    loop = asyncio.new_event_loop()
    try:
        with pytest.raises(Stop):
            loop.run_until_complete(worker.run_ledger_followup(None))
    finally:
        loop.close()
    assert slept == [worker.FOLLOWUP_IDLE_SECONDS] and worker.FOLLOWUP_IDLE_SECONDS > 0


# ------------------------------------------------------------------------------ the pace

def test_the_follow_up_starts_on_the_slowest_declared_pace():
    """🔴 A JOB NOBODY STARTS HAS NOBODY TO ASK. So the pace is a declared cell rather than
    a constant in the worker, and it starts at the slowest one there is: this work is work
    nobody is waiting for, and the chain feeding it is.

    The "slowest" is MEASURED off the table, not spelled `trickle` here -- a pace added
    below `trickle` should turn this red and make somebody choose, rather than leaving the
    follow-up quietly no longer slowest."""
    paces = pacing.load_paces()
    rest = {name: float(spec.get("rest_seconds") or 0) for name, spec in paces.items()}
    slowest = max(rest, key=lambda name: rest[name])
    assert pacing.load_jobs()["chain_followup"] == slowest
    assert pacing.job_pace(followup.FOLLOWUP_JOB) == pacing.resolve(slowest)
