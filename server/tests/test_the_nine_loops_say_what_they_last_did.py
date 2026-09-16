# -*- coding: utf-8 -*-
"""S-176. `/runtime` answers with VALUES for nine loops; `/health` keeps the verdict.

판정 282. Asked 「is the chain moving?」 an operator had nothing to read. The loops run in
the chain-worker, watcher and scheduler PROCESSES and every lap number they compute was
printed and dropped -- the code said so itself about the follow-up queue: 「the queue depth
lives in this process's memory where no query reaches it」.

🔴 THE CARRIER IS NOT AN INSTRUMENT, and that distinction is what this file scores.
`heartbeat.record_lap` measures nothing: it takes the numbers the log line was already
given and stores them so the beat that loop ALREADY writes can carry them. It writes no
file of its own -- making it beat added a second write per ingest chunk, and
`test_a_chunk_loop_that_stops_stops_the_beats` caught that by counting beats, because a
beat means 「committed progress」 and a carrier must not be able to forge one.

⚠️ AN ABSENT CELL IS OMITTED, NEVER ZEROED. Half of what is asked for does not exist for
every loop -- `web` has no lap, a loop that has never run has no last_seconds -- and 「not
reported」 must not render as 「zero」.
"""
import os
import sys
import time

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

import runtime.loops                                                 # noqa: E402
from utils import heartbeat                                          # noqa: E402


class _FakeDb:
    """The two questions this route asks a database, and nothing else."""

    def __init__(self, pending=0, vacuum=None, dialect="postgresql"):
        self.pending, self.vacuum, self.dialect = pending, vacuum, dialect
        self.asked = []

    def get_bind(self):
        return type("B", (), {"dialect": type("D", (), {"name": self.dialect})()})()

    def query(self, *a, **kw):
        self.asked.append("outbox")
        return self

    def select_from(self, *a, **kw):
        return self

    def filter(self, *a, **kw):
        return self

    def scalar(self):
        return self.pending

    def execute(self, *a, **kw):
        self.asked.append("vacuum")
        return type("R", (), {"fetchone": lambda _s: self.vacuum})()


def by_loop(payload):
    return {item["loop"]: item for item in payload["loops"]}


@pytest.fixture(autouse=True)
def clean_laps():
    heartbeat._laps.clear()
    yield
    heartbeat._laps.clear()


# ---------------------------------------------------------------------------
# 1. Nine entries, named and in the board's order
# ---------------------------------------------------------------------------

def test_all_nine_loops_are_answered_for():
    payload = runtime.loops.runtime_loops(_FakeDb(), heartbeats={})
    loops = [item["loop"] for item in payload["loops"]]
    assert loops == ["web", "watcher", "chain", "outbox_purge", "listen",
                     "ledger_followup", "ledger_census", "scheduler", "postgres"]
    assert [item["board"] for item in payload["loops"]] == [
        "1", "2", "3", "3-a", "3-b", "4", "5", "6", "7"]


def test_the_loop_and_the_process_are_two_columns():
    """Five loops live in ONE process. Collapsing them would make 「the chain process is
    alive」 read as 「the census loop is turning」, which is the false green this exists to
    prevent."""
    payload = runtime.loops.runtime_loops(_FakeDb(), heartbeats={})
    in_chain = [i["loop"] for i in payload["loops"] if i["process"] == "chain"]
    assert in_chain == ["chain", "outbox_purge", "listen", "ledger_followup",
                        "ledger_census"]


# ---------------------------------------------------------------------------
# 2. 🔴 An absent cell is omitted, not zeroed
# ---------------------------------------------------------------------------

def test_a_loop_that_never_reported_has_no_lap_keys():
    """⛔ NOT `last_seconds: 0`. 「it has not said」 and 「it said none」 are different
    facts, and a screen cannot tell them apart once one is written as the other."""
    payload = runtime.loops.runtime_loops(_FakeDb(), heartbeats={})
    census = by_loop(payload)["ledger_census"]
    for absent in ("last_at", "last_seconds", "depth", "pace"):
        assert absent not in census, absent


def test_a_real_zero_survives_while_an_unsaid_one_stays_absent():
    """⛔ THE OTHER HALF OF THE SAME SENTENCE, and the half nothing was scoring.

    `record_lap`'s docstring says `seconds` and `depth` are omitted when None 「rather than
    written as zero -- 「it did not say」 and 「it said none」 are different facts」. The
    sibling above scores the FIRST half (never reported -> no key). This scores the second:
    a loop that DID report, and reported ZERO, keeps its key.

    🔴 MEASURED AS A HOLE BEFORE IT WAS FILLED. Rewriting `if depth is not None` as
    `if depth` makes a `depth=0` lap vanish into 「did not say」 - the queue reports empty
    and the screen reads 「the loop never spoke」 - and 28 tests stayed GREEN. That is the
    exact axis this round spent itself on, in the one seat that carries it for nine loops.

    `seconds` is scored in the same test on purpose: one sentence states the rule for both,
    so one of them going quiet while the other is watched is how the pair drifts apart.
    """
    heartbeat.record_lap("chain", "ledger_followup", seconds=0.0, depth=0)
    lap = heartbeat._laps["chain"]["ledger_followup"]
    assert lap["depth"] == 0, (
        "a loop that reported an EMPTY queue said something. Dropping the key turns "
        f"「none pending」 into 「never reported」: {lap!r}")
    assert lap["seconds"] == 0.0, f"a lap that took no measurable time still ran: {lap!r}"

    # And the omission is still an omission - the two halves are asserted together so
    # neither can be satisfied by making the other unconditional.
    heartbeat.record_lap("chain", "outbox_purge", seconds=1.0)
    quiet = heartbeat._laps["chain"]["outbox_purge"]
    assert "depth" not in quiet, f"nothing was said about depth here: {quiet!r}"


def test_an_extra_word_follows_the_same_rule_as_the_numbers():
    """`**extra` drops None too, and a `0` in it is a value like any other.

    The loops carry their own words through this door (`reconnects`, `items`), so the rule
    that governs `depth` has to govern them or the door is split by argument name.
    """
    heartbeat.record_lap("chain", "listen", reconnects=0, state=None)
    lap = heartbeat._laps["chain"]["listen"]
    assert lap["reconnects"] == 0, f"「reconnected zero times」 is news: {lap!r}"
    assert "state" not in lap, f"nothing was said about state: {lap!r}"


def test_web_is_alive_and_claims_no_lap():
    """① has no heartbeat and needs none -- this route IS the web process answering. A lap
    here would be a number invented to fill the table."""
    web = by_loop(runtime.loops.runtime_loops(_FakeDb(), heartbeats={}))["web"]
    assert web["alive"] is True
    assert "last_seconds" not in web and "knob" not in web


# ---------------------------------------------------------------------------
# 3. The lap a loop recorded comes back out
# ---------------------------------------------------------------------------

def test_a_recorded_lap_reaches_the_route_with_its_own_numbers():
    """End to end through the real carrier: record as the loop does, read as the route
    does, and the numbers are the ones the log line had."""
    heartbeat.record_lap("chain", "ledger_followup", seconds=1.25, depth=7,
                         items=3, pace=60.0, at=1000.0)
    entry = {"age_seconds": 0.5, "stale": False,
             "laps": {"ledger_followup": dict(heartbeat._laps["chain"]["ledger_followup"],
                                              age_seconds=2.0)}}
    payload = runtime.loops.runtime_loops(_FakeDb(), heartbeats={"chain": entry})

    followup = by_loop(payload)["ledger_followup"]
    assert followup["last_seconds"] == 1.25
    assert followup["depth"] == 7
    assert followup["pace"] == 60.0
    assert followup["last_at"] == 1000.0
    assert followup["last_age_seconds"] == 2.0
    # Whatever else the loop chose to carry rides through by name, so the next loop's own
    # fact does not need this file edited to be reportable.
    assert followup["items"] == 3


def test_a_loop_carries_words_as_well_as_numbers():
    """③-b reports `state` and a reconnect COUNT -- 「it reconnected once at boot」 and
    「it reconnects every minute」 are the two states that matter, and a boolean renders
    them alike."""
    heartbeat.record_lap("chain", "listen", state="reconnecting", reconnects=4)
    entry = {"age_seconds": 0.1, "stale": False,
             "laps": {"listen": heartbeat._laps["chain"]["listen"]}}
    listen = by_loop(runtime.loops.runtime_loops(
        _FakeDb(), heartbeats={"chain": entry}))["listen"]
    assert listen["state"] == "reconnecting" and listen["reconnects"] == 4


def test_alive_is_the_processs_and_the_lap_age_is_the_loops():
    """⛔ A LIVE PROCESS DOES NOT MEAN A TURNING LOOP. `alive` sits beside `process` for
    that reason, and a wedged loop shows it in its lap age rather than in a green light."""
    entry = {"age_seconds": 0.2, "stale": False,
             "laps": {"ledger_census": {"at": 10.0, "age_seconds": 3600.0,
                                        "seconds": 0.4}}}
    census = by_loop(runtime.loops.runtime_loops(
        _FakeDb(), heartbeats={"chain": entry}))["ledger_census"]
    assert census["alive"] is True, "the process is beating"
    assert census["last_age_seconds"] == 3600.0, "and the loop has not turned in an hour"


# ---------------------------------------------------------------------------
# 4. The two database questions, both already asked elsewhere
# ---------------------------------------------------------------------------

def test_the_chains_depth_is_the_outbox_backlog():
    db = _FakeDb(pending=1234)
    chain = by_loop(runtime.loops.runtime_loops(db, heartbeats={}))["chain"]
    assert chain["depth"] == 1234
    assert db.asked.count("outbox") == 1, "one query, not one per loop in that process"


def test_postgres_says_idle_when_nothing_is_vacuuming():
    pg = by_loop(runtime.loops.runtime_loops(
        _FakeDb(vacuum=None), heartbeats={}))["postgres"]
    assert pg["alive"] is True and pg["state"] == "idle"


def test_postgres_names_the_phase_and_what_is_left():
    row = type("Row", (), {"relation": "cell_sources", "phase": "scanning heap",
                           "heap_blks_scanned": 400, "heap_blks_total": 1000})()
    pg = by_loop(runtime.loops.runtime_loops(
        _FakeDb(vacuum=row), heartbeats={}))["postgres"]
    assert pg["state"] == "vacuuming" and pg["phase"] == "scanning heap"
    assert pg["relation"] == "cell_sources" and pg["depth"] == 600


def test_a_non_postgres_bind_says_it_does_not_know():
    """⛔ NOT `alive: False`. SQLite cannot answer the question, and 「no」 would be a
    claim about the database rather than about this route's reach."""
    pg = by_loop(runtime.loops.runtime_loops(
        _FakeDb(dialect="sqlite"), heartbeats={}))["postgres"]
    assert pg["alive"] is None
    assert "state" not in pg


# ---------------------------------------------------------------------------
# 5. The carrier costs nothing, and cannot forge progress
# ---------------------------------------------------------------------------

def test_recording_a_lap_writes_no_heartbeat(monkeypatch):
    """🔴 THE COST, AS A VALUE: zero extra writes. A lap rides the beat the loop was
    already going to make, and `at` is stamped at lap time so nothing is lost by sharing
    it. The first cut beat instead, and that second write per ingest chunk is what
    `test_a_chunk_loop_that_stops_stops_the_beats` caught."""
    beats = {"n": 0}
    monkeypatch.setattr(heartbeat, "beat",
                        lambda *a, **kw: beats.__setitem__("n", beats["n"] + 1))

    for _ in range(50):
        heartbeat.record_lap("chain", "chain", seconds=0.01)

    assert beats["n"] == 0, "the carrier must not write, and must not forge a beat"
    assert heartbeat._laps["chain"]["chain"]["seconds"] == 0.01


def test_the_lap_rides_the_next_beat():
    """And it does reach the file -- through the beat the loop makes anyway.

    ⚠️ NO DIRECTORY MONKEYPATCH HERE, deliberately. `conftest`'s session fixture already
    redirects heartbeats away from the live tree, and it replaces `heartbeat_dir` AND
    `heartbeat_path` as a PAIR. Patching only the first wrote through the conftest's path
    and read from a different directory -- a green write and an empty read, which is the
    shape a half-substituted double always takes.
    """
    heartbeat._state.pop("s176", None)
    heartbeat.record_lap("s176", "ledger_census", seconds=2.5, depth=9, at=500.0)
    assert heartbeat.beat("s176", force=True) is True

    everything = heartbeat.read_all(now=505.0)
    assert "s176" in everything, sorted(everything)
    read = everything["s176"]
    lap = read["laps"]["ledger_census"]
    assert lap["seconds"] == 2.5 and lap["depth"] == 9
    assert lap["age_seconds"] == 5.0, (
        "the age is measured against the READ, not against the beat -- a beat that is "
        "itself old must not under-report how long ago the lap happened")


# ---------------------------------------------------------------------------
# 6. The route itself, through the real app
# ---------------------------------------------------------------------------

def test_the_route_answers_200_with_the_nine(client, monkeypatch):
    """The gate's first two lines, through the app rather than through the function.

    ⚠️ The database here is the suite's SQLite one, so `postgres` answers 「I cannot tell」
    and the outbox count is whatever this session holds. What is scored is the SHAPE the
    client component (C-74) will be written against: 200, nine entries, and every entry
    naming its loop, its process and its board number.
    """
    from admin import auth

    token = "s176-runtime-token"
    monkeypatch.setenv(auth.ADMIN_TOKEN_ENV, token)
    res = client.get("/runtime", headers={auth.ADMIN_TOKEN_HEADER: token})

    assert res.status_code == 200, res.text
    payload = res.json()
    assert len(payload["loops"]) == 9
    assert [i["loop"] for i in payload["loops"]] == [
        "web", "watcher", "chain", "outbox_purge", "listen",
        "ledger_followup", "ledger_census", "scheduler", "postgres"]
    for item in payload["loops"]:
        assert item["process"] and item["board"]
    assert res.headers.get("Cache-Control") == "no-store", (
        "a runtime value that a browser may cache is a runtime value that lies")


def test_the_route_is_gated():
    """⚠️ `/runtime` IS NOT UNDER `/admin`, so the durable audit in `test_admin_auth`
    does not walk it. The gate is asserted here instead, by name, rather than assumed."""
    from admin import auth
    from main import app

    for route in app.routes:
        if getattr(route, "path", None) == "/runtime":
            calls = {getattr(d, "dependency", None)
                     for d in getattr(route, "dependencies", ())}
            assert calls & set(auth.ADMIN_GATES), (
                "/runtime publishes queue depths and knob paths; it carries the same "
                "gate /admin/chain/queue does")
            return
    raise AssertionError("/runtime is not registered")
