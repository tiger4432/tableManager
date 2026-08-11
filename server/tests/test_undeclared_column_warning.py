"""[Schema] A column absent from ``column_types`` is dropped from an update while the
write still reports success -- a silent data-loss channel open on every table
(``map_doe``/``map_doe_source`` lost ``eventtime`` this way for an unknown period).

The drop itself is deliberate and unchanged: rejecting the write would turn a config
that lags its client into an outage. These tests pin the *diagnostic* instead --
it must fire on the real write path, exactly once per (table, column), separately
for distinct pairs, and it must never interfere with persisting declared columns.
"""

import logging

import pytest

from database import crud, models, schemas


class _WarningCollector(logging.Handler):
    """Attached directly to the "Server" logger. Deliberately not ``caplog``: the
    whole point of these tests is *how many* records are emitted, so capture must
    not depend on propagation or on pytest's per-test handler juggling."""

    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.records = []

    def emit(self, record):
        self.records.append(record.getMessage())

    @property
    def schema_warnings(self):
        return [m for m in self.records if "[Schema]" in m]


@pytest.fixture
def warn_capture():
    logger = logging.getLogger("Server")
    handler = _WarningCollector()
    logger.addHandler(handler)
    # The registry is a process global; without this a prior test in the same
    # session could pre-warm a pair and make "fires once" pass vacuously.
    # The DROP COUNTERS have to be cleared for the same reason and more sharply: the
    # re-announce thresholds are absolute counts, so a pair left at 7 by an earlier
    # test would cross 10 three drops early and move every assertion below.
    crud._undeclared_column_warned.clear()
    crud._undeclared_column_drops.clear()
    crud._undeclared_column_drops_over_budget.clear()
    try:
        yield handler
    finally:
        logger.removeHandler(handler)
        crud._undeclared_column_warned.clear()
        crud._undeclared_column_drops.clear()
        crud._undeclared_column_drops_over_budget.clear()


def _batch(business_key_val, updates):
    return schemas.GeneralUpdateBatch(
        updates=[
            schemas.GeneralUpdateItem(
                business_key_val=business_key_val,
                updates=updates,
                source_name="user",
                updated_by="tester",
            )
        ],
        silent=True,
    )


def test_undeclared_column_warns_once_and_row_still_saves(client, db_session, warn_capture):
    """Real path: PUT /tables/{t}/data/updates with an undeclared column.

    Asserts the three things the incident turned on -- the request still succeeds,
    the declared columns are still written, and the dropped column is now visible.
    """
    payload = {
        "updates": [
            {
                "business_key_val": "PN-1001",
                "updates": {
                    "part_no": "PN-1001",
                    "category": "BRACKET",
                    "stock_qty": 7,
                    # Not present in column_types -> dropped, request still 200.
                    "eventtime": "2026-07-27T10:00:00",
                },
                "source_name": "user",
                "updated_by": "tester",
            }
        ],
        "silent": True,
    }

    resp = client.put("/tables/inventory_master/data/updates", json=payload)
    assert resp.status_code == 200, resp.text

    model = models.DYNAMIC_TABLES["inventory_master"]
    row = db_session.query(model).filter(model.business_key_val == "PN-1001").first()
    assert row is not None, "declared columns must still be written"
    assert row.part_no == "PN-1001"
    assert row.category == "BRACKET"
    assert row.stock_qty == 7
    # The undeclared column is genuinely absent -- the write really did lose it.
    assert getattr(row, "eventtime", None) is None

    warnings = warn_capture.schema_warnings
    assert len(warnings) == 1, warnings
    assert "eventtime" in warnings[0]
    assert "inventory_master" in warnings[0]

    # Fires ONCE: repeat the identical write and show no second line.
    resp2 = client.put("/tables/inventory_master/data/updates", json=payload)
    assert resp2.status_code == 200, resp2.text
    assert len(warn_capture.schema_warnings) == 1, warn_capture.schema_warnings


def _bulk_batch(n, col="eventtime", start=0):
    return schemas.GeneralUpdateBatch(
        updates=[
            schemas.GeneralUpdateItem(
                business_key_val=f"PN-{i}",
                updates={"part_no": f"PN-{i}", col: "2026-07-27T10:00:00"},
                source_name="user",
                updated_by="tester",
            )
            for i in range(start, start + n)
        ],
        silent=True,
    )


def test_repeated_rows_in_one_batch_announce_at_powers_of_ten(db_session, warn_capture):
    """The drop is a per-cell branch, so 500 rows carrying the same undeclared column
    must not produce 500 lines. But they must not produce ONE either.

    Once-per-process is what made a broken deployment indistinguishable from a fixed
    one: after the single startup line, ten thousand further drops looked exactly like
    zero further drops. The volume is the signal, so it is announced at 1, 10 and 100
    -- three lines for five hundred drops.
    """
    crud.apply_batch_updates(db_session, "inventory_master", _bulk_batch(500))

    warnings = warn_capture.schema_warnings
    assert len(warnings) == 3, warnings
    assert "Dropped 1 time(s)" in warnings[0]
    assert "Dropped 10 time(s)" in warnings[1]
    assert "Dropped 100 time(s)" in warnings[2]
    assert crud.undeclared_column_drops()[("inventory_master", "eventtime")] == 500


def test_the_count_survives_across_batches_so_a_quiet_process_means_it_stopped(
        db_session, warn_capture):
    """THE POINT OF THE WHOLE CHANGE. The counter is per process, not per call, so a
    chain that keeps dropping keeps announcing -- and a chain that was FIXED goes
    quiet. Those two had been indistinguishable."""
    for chunk in range(4):
        crud.apply_batch_updates(db_session, "inventory_master",
                                 _bulk_batch(3, start=chunk * 3))
    assert crud.undeclared_column_drops()[("inventory_master", "eventtime")] == 12
    # 12 drops spread over four separate calls still crosses exactly the 1 and 10
    # thresholds -- the threshold is the running total, not a per-call count.
    assert len(warn_capture.schema_warnings) == 2, warn_capture.schema_warnings
    assert "Dropped 10 time(s)" in warn_capture.schema_warnings[1]


def test_a_declared_column_never_reaches_the_counter(db_session, warn_capture):
    """The accessor has to be readable as 'is this deployment losing a column right
    now', so a healthy write must leave it empty rather than at zero-for-everything."""
    crud.apply_batch_updates(
        db_session, "inventory_master",
        _batch("PN-OK", {"part_no": "PN-OK", "category": "BRACKET"}))
    assert crud.undeclared_column_drops() == {}
    assert warn_capture.schema_warnings == []


def test_the_worker_heartbeat_carries_the_drop_digest(db_session, warn_capture):
    """The drops happen in the chain worker; the question is asked at the web server's
    /health. This pins the existing cross-process channel actually carrying them --
    and pins the note staying None on a healthy worker, so a clean deployment's
    heartbeat is unchanged."""
    import chain_ingestion_worker

    assert chain_ingestion_worker._undeclared_drop_note() is None

    crud.apply_batch_updates(db_session, "inventory_master", _bulk_batch(4))
    note = chain_ingestion_worker._undeclared_drop_note()
    assert "total=4" in note
    assert "inventory_master.eventtime=4" in note


def test_the_digest_is_bounded_and_says_what_it_left_out(db_session, warn_capture):
    """The note is republished on every beat into a ~200 byte file, so a table with
    dozens of dropped columns must not be able to inflate it -- but it must say that
    it truncated, or the total stops adding up in the reader's head."""
    for i in range(9):
        crud.apply_batch_updates(
            db_session, "inventory_master",
            _batch(f"PN-D{i}", {"part_no": f"PN-D{i}", f"dcol_{i}": 1}))
    import chain_ingestion_worker

    note = chain_ingestion_worker._undeclared_drop_note()
    assert "total=9" in note
    assert note.count("dcol_") == 5, note
    assert "(+4 more)" in note, note


def test_the_accessor_returns_a_copy_and_cannot_be_mutated_through(db_session, warn_capture):
    crud.apply_batch_updates(db_session, "inventory_master",
                             _batch("PN-C1", {"part_no": "PN-C1", "ghost_c": 1}))
    snap = crud.undeclared_column_drops()
    snap[("inventory_master", "ghost_c")] = 999
    snap[("bogus", "bogus")] = 1
    assert crud.undeclared_column_drops() == {("inventory_master", "ghost_c"): 1}


def test_distinct_table_column_pairs_each_warn(db_session, warn_capture):
    """Warn-once is keyed by (table, column), not by table and not by column."""
    crud.apply_batch_updates(
        db_session,
        "inventory_master",
        _batch("PN-2001", {"part_no": "PN-2001", "ghost_a": 1}),
    )
    crud.apply_batch_updates(
        db_session,
        "inventory_master",
        _batch("PN-2002", {"part_no": "PN-2002", "ghost_b": 1}),
    )
    crud.apply_batch_updates(
        db_session,
        "production_plan",
        _batch("PL-1", {"plan_id": "PL-1", "ghost_a": 1}),
    )

    warnings = warn_capture.schema_warnings
    assert len(warnings) == 3, warnings
    assert any("ghost_a" in m and "inventory_master" in m for m in warnings)
    assert any("ghost_b" in m and "inventory_master" in m for m in warnings)
    assert any("ghost_a" in m and "production_plan" in m for m in warnings)


def test_registry_is_bounded_and_announces_its_own_silence(db_session, warn_capture, monkeypatch):
    """Column names come from the payload, so a junk-header caller could grow the
    registry without limit. Past the budget it stops growing AND says so once.

    The counter is bounded by the SAME budget, which is the point: a
    `{(table, column): count}` dict that accepted every name a malformed header
    invented would be exactly the unbounded growth this budget exists to stop.
    """
    monkeypatch.setattr(crud, "_MAX_UNDECLARED_WARNED_PER_TABLE", 3)

    for i in range(10):
        crud.apply_batch_updates(
            db_session,
            "inventory_master",
            _batch(f"PN-3{i:03d}", {"part_no": f"PN-3{i:03d}", f"junk_{i}": 1}),
        )

    assert len(crud._undeclared_column_warned["inventory_master"]) == 3

    warnings = warn_capture.schema_warnings
    drops = [m for m in warnings if "DROPPED" in m]
    saturation = [m for m in warnings if "without naming the column" in m]
    assert len(drops) == 3, drops
    assert len(saturation) == 1, saturation

    # Attribution is what saturation costs -- not visibility. The 7 unattributable
    # drops are still counted, under the `(table, None)` key, so the totals add up.
    snap = crud.undeclared_column_drops()
    assert len([k for k in snap if k[1] is not None]) == 3, snap
    assert snap[("inventory_master", None)] == 7, snap
    assert sum(snap.values()) == 10, "every drop must be counted somewhere"
