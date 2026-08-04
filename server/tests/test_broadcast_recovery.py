"""Announcements that were lost forever when the hub was briefly unreachable.

Two defects, one shared recovery path:

  (5) `sweep_undelivered_broadcasts` stamped `broadcast_at` and returned WITHOUT
      broadcasting anything whenever the undelivered rows mapped to no chain
      target table. The durable marker was consumed and nothing was announced,
      so a write to any table that is not a chain target had no recovery at all.

  (6) `run_watcher.post_event` logged the failure and dropped it. No marker, no
      retry: every batch-refresh, file-processed and ingestion-state
      notification emitted while the web server was unreachable was permanently
      lost. The row lands, the screen never learns.

The fix for (6) is deliberately the marker (5) already sweeps, so there is one
durable mechanism rather than two. Each test below is a red/green pair: the
first half asserts the loss the old code produced, the second half the
recovery - and the anti-sweep guard is asserted separately, because a fix that
re-broadcasts without ever stamping would trade a lost announcement for an
infinite sweep.
"""
import pytest

import chain_ingestion_worker as ciw
import event_constants


RULES = [
    {"name": "rA", "trigger_table": "tblA_src", "target_table": "table_A", "enabled": True},
]


class FakeRow:
    def __init__(self, row_id, table_name, event_type="CREATE",
                 source_name="user", tx=None):
        self.id = row_id
        self.event_uuid = f"uuid_{row_id}"
        self.table_name = table_name
        self.event_type = event_type
        self.status = "SUCCESS"
        self.processed_chain = True
        self.broadcast_at = None
        payload = {"source_name": source_name}
        if tx:
            payload["transaction_id"] = tx
        self.payload = payload
        self._parsed_payload = payload


class FakeQuery:
    """Just enough of a SQLAlchemy query for the sweep: the stale SELECT, and the
    id-in-list UPDATE that stamps `broadcast_at`."""

    def __init__(self, db):
        self._db = db

    def filter(self, *a, **kw):
        self._db.filtered = True
        return self

    def order_by(self, *a):
        return self

    def limit(self, n):
        return self

    def all(self):
        return [r for r in self._db.rows if r.broadcast_at is None]

    def update(self, values, synchronize_session=False):
        # The sweep always stamps by `id IN (stale_ids)`; the ids it means are
        # exactly the rows it just read.
        for r in self._db.rows:
            if r.broadcast_at is None:
                r.broadcast_at = "stamped"
        self._db.stamped += 1
        return len(self._db.rows)


class FakeDB:
    def __init__(self, rows):
        self.rows = rows
        self.commits = 0
        self.stamped = 0

    def query(self, *a, **kw):
        return FakeQuery(self)

    def commit(self):
        self.commits += 1


def _capture_posts(monkeypatch, ok=True):
    posted = []

    async def fake_post(endpoint, payload):
        posted.append(payload)
        return ok

    monkeypatch.setattr(ciw, "post_event_async", fake_post)
    return posted


# ===========================================================================
# (5) The sweep that consumed the marker and announced nothing.
# ===========================================================================

@pytest.mark.anyio
async def test_a_row_with_no_chain_target_is_announced_not_swallowed(monkeypatch):
    """RED before the fix: `affected_targets` is empty for a table no chain rule
    triggers on, and the old code stamped and returned with `posted == []`.

    GREEN: the table the row was actually written to is itself the refresh
    target, so the grid catches up.
    """
    rows = [FakeRow(1, "standalone_table", tx="tx1")]
    db = FakeDB(rows)
    posted = _capture_posts(monkeypatch)

    await ciw.sweep_undelivered_broadcasts(db, RULES, lambda: FakeDB([]))

    assert posted, "the marker was consumed and nothing was announced"
    assert [p["table_name"] for p in posted] == ["standalone_table"]
    assert posted[0]["event"] == "batch_refresh_required"
    # ...and the marker is only then consumed.
    assert all(r.broadcast_at is not None for r in rows)


@pytest.mark.anyio
async def test_the_source_table_is_refreshed_alongside_the_chain_target(monkeypatch):
    """A chain trigger table is not a chain TARGET table, so it had no recovery
    either: the sweep refreshed table_A and left the table the operator was
    actually looking at stale."""
    rows = [FakeRow(1, "tblA_src", tx="tx1")]
    db = FakeDB(rows)
    posted = _capture_posts(monkeypatch)

    await ciw.sweep_undelivered_broadcasts(db, RULES, lambda: FakeDB([]))

    assert sorted(p["table_name"] for p in posted) == ["table_A", "tblA_src"]


@pytest.mark.anyio
async def test_one_refresh_per_table_however_many_rows(monkeypatch):
    """500 undelivered rows on one table is one refresh, not 500 - the sweep runs
    against a table that must stay sane at ten million rows."""
    rows = [FakeRow(i, "standalone_table", tx=f"tx{i}") for i in range(200)]
    db = FakeDB(rows)
    posted = _capture_posts(monkeypatch)

    await ciw.sweep_undelivered_broadcasts(db, RULES, lambda: FakeDB([]))

    assert len(posted) == 1


@pytest.mark.anyio
async def test_the_sweep_cannot_spin_forever(monkeypatch):
    """THE ANTI-SWEEP GUARD, and the mutation check for this whole fix.

    The empty-target branch existed to stop an infinite re-sweep, and the only
    thing that actually stops one is stamping the marker after a successful
    announcement. A fix that re-broadcasts unconditionally - or one that fires
    and forgets to stamp - makes this test red on the second sweep.
    """
    rows = [FakeRow(1, "standalone_table", tx="tx1")]
    db = FakeDB(rows)
    posted = _capture_posts(monkeypatch)

    await ciw.sweep_undelivered_broadcasts(db, RULES, lambda: FakeDB([]))
    first = len(posted)
    assert first == 1

    for _ in range(5):
        await ciw.sweep_undelivered_broadcasts(db, RULES, lambda: FakeDB([]))
    assert len(posted) == first, \
        "the sweep re-announced rows it had already delivered - infinite re-sweep"


@pytest.mark.anyio
async def test_a_failed_broadcast_is_not_stamped(monkeypatch):
    """Eventual delivery: if the announcement did not get through, the marker
    must survive to the next sweep. This is the property that makes the stamp
    safe rather than a second way to lose the notification."""
    rows = [FakeRow(1, "standalone_table", tx="tx1")]
    db = FakeDB(rows)
    posted = _capture_posts(monkeypatch, ok=False)

    await ciw.sweep_undelivered_broadcasts(db, RULES, lambda: FakeDB([]))

    assert posted, "nothing was even attempted"
    assert all(r.broadcast_at is None for r in rows), \
        "a broadcast that failed was marked delivered - the row is now lost"

    # And the retry really happens.
    posted2 = _capture_posts(monkeypatch, ok=True)
    await ciw.sweep_undelivered_broadcasts(db, RULES, lambda: FakeDB([]))
    assert posted2 and all(r.broadcast_at is not None for r in rows)


@pytest.mark.anyio
async def test_nothing_to_sweep_is_silent(monkeypatch):
    """The normal state of the system. A sweep that fires refreshes when nothing
    was lost is a full-table reload storm."""
    db = FakeDB([])
    posted = _capture_posts(monkeypatch)
    await ciw.sweep_undelivered_broadcasts(db, RULES, lambda: FakeDB([]))
    assert posted == []


# ===========================================================================
# (6) The watcher's log-and-drop notification path.
# ===========================================================================

class _Recorder:
    """Stands in for SessionLocal: collects what would have been committed."""

    def __init__(self, fail=False):
        self.added = []
        self.fail = fail
        self.committed = False
        self.closed = False

    def __call__(self):
        return self

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        if self.fail:
            raise RuntimeError("database is gone too")
        self.committed = True

    def rollback(self):
        pass

    def close(self):
        self.closed = True


def _drive_watcher_post(monkeypatch, recorder, response=None, exc=None):
    """Run the REAL run_watcher.post_event with only the socket faked."""
    import run_watcher
    import internal_event_client

    class _Sess:
        @staticmethod
        def post(url, **kw):
            if exc is not None:
                raise exc
            return response

    monkeypatch.setattr(internal_event_client, "internal_event_session", lambda: _Sess())
    monkeypatch.setattr(run_watcher, "SessionLocal", recorder)
    run_watcher.post_event("/internal/events/batch-refresh",
                           {"table_name": "inventory_master", "change_count": 3})
    return recorder


class _Resp:
    def __init__(self, status_code):
        from requests.structures import CaseInsensitiveDict
        self.status_code = status_code
        self.headers = CaseInsensitiveDict()
        self.ok = 200 <= status_code < 300


def test_a_notification_that_could_not_be_sent_leaves_a_durable_marker(monkeypatch):
    """RED before the fix: `post_event` logged the exception and returned, and
    `recorder.added` stayed empty - nothing on disk remembered that an
    announcement was owed."""
    import requests
    rec = _drive_watcher_post(
        monkeypatch, _Recorder(),
        exc=requests.exceptions.ConnectionError("hub is down"))

    assert rec.added, "the notification was dropped with no durable marker"
    row = rec.added[0]
    assert rec.committed
    assert row.table_name == "inventory_master"
    assert row.event_type == event_constants.EVENT_BROADCAST_RECOVERY
    # Exactly the shape the chain worker's sweep collects, and nothing a mapper
    # could ever re-run.
    assert row.processed_chain is True
    assert row.status == "SUCCESS"
    assert row.broadcast_at is None
    # Small scalars only: a batch-refresh payload carries up to 500 audit
    # entries and a marker that size is how a recovery path becomes an incident.
    assert set(row.payload) == {"endpoint", "reason", "marker"}
    assert "/internal/events/batch-refresh" == row.payload["endpoint"]


def test_an_http_refusal_also_leaves_the_marker(monkeypatch):
    """A 503 from the hub loses the announcement exactly as thoroughly as a
    refused connection does."""
    rec = _drive_watcher_post(monkeypatch, _Recorder(), response=_Resp(503))
    assert rec.added and rec.added[0].payload["reason"] == "HTTP 503"


def test_a_delivered_notification_leaves_no_marker(monkeypatch):
    """The control. Without it, "always writes a marker" would pass the tests
    above while filling the outbox on every healthy notification."""
    rec = _drive_watcher_post(monkeypatch, _Recorder(), response=_Resp(200))
    assert rec.added == []


def test_a_marker_that_cannot_be_written_does_not_kill_the_watcher(monkeypatch):
    """When the hub is down because the whole box is in trouble, the database may
    be unreachable too. A recovery path that raises into the ingestion loop is
    worse than the loss it was trying to prevent."""
    import requests
    rec = _drive_watcher_post(monkeypatch, _Recorder(fail=True),
                              exc=requests.exceptions.ConnectionError("down"))
    assert rec.closed, "the session was leaked when the marker write failed"


@pytest.mark.anyio
async def test_the_watchers_marker_is_recovered_by_the_chain_workers_sweep(monkeypatch):
    """The two halves joined: the marker the watcher leaves is collected by the
    sweep the chain worker already ran, and comes out as a refresh for the table
    whose row nobody announced.

    This is why (6) reuses (5)'s marker instead of inventing a second queue -
    and why (5) had to be fixed first: a BROADCAST_RECOVERY row maps to no chain
    target, which is precisely the case the old sweep swallowed.
    """
    marker = FakeRow(1, "inventory_master",
                     event_type=event_constants.EVENT_BROADCAST_RECOVERY)
    db = FakeDB([marker])
    posted = _capture_posts(monkeypatch)

    await ciw.sweep_undelivered_broadcasts(db, RULES, lambda: FakeDB([]))

    assert [p["table_name"] for p in posted] == ["inventory_master"]
    assert marker.broadcast_at is not None


def test_the_marker_type_is_never_read_as_a_data_change():
    """A BROADCAST_RECOVERY row that reached the chain worker's grouping logic
    would have its payload read as a set of changed rows. It cannot: it is
    written processed_chain=True, and the type is declared as a control event
    so the queue path skips it even if that ever changed."""
    assert event_constants.EVENT_BROADCAST_RECOVERY in event_constants.CONTROL_EVENT_TYPES
    # The graph materializer only acts on CREATE/EDIT, so the marker is inert
    # there too.
    assert event_constants.EVENT_BROADCAST_RECOVERY not in ("CREATE", "EDIT", "DELETE")
