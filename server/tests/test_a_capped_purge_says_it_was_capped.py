# -*- coding: utf-8 -*-
"""The outbox purge stopped at its per-cycle cap and reported the same number either way.

`purge_expired_outbox_sync` deletes in chunks up to `OUTBOX_PURGE_MAX_CHUNKS` and carries
the remainder to the next cycle. Its only output was the row count, and that count says
"20 rows went" whether twenty were all that had expired or twenty was as far as the cap
allowed. In a deployment whose arrival rate outruns the purge rate the backlog then grows
with no symptom but disk.

🔴 THE RETURN WAS NOT WIDENED, AND THAT IS THE POINT OF THE SHAPE. Measured 2026-09-06:
the function has exactly ONE live caller and it discards the result --
`asyncio.create_task(asyncio.to_thread(purge_expired_outbox_sync, db_session_factory))`.
A second return value would have had zero readers. The fact is published instead on the
registry `GET /admin/chain/queue` already spreads, which is an existing surface rather
than a new one.

⚠️ THREE STATES. `None` is "never purged, or the last cycle raised before it could tell";
`False` is "everything expired was removed"; `True` is "stopped at the cap, more remain".
Folding None into False would state "there is no more" about a cycle that never finished.
"""
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import chain_activity                                             # noqa: E402
from chain_ingestion_worker import purge_expired_outbox_sync      # noqa: E402
from database import models                                       # noqa: E402


@pytest.fixture(autouse=True)
def a_clean_registry():
    chain_activity.registry.clear()
    yield
    chain_activity.registry.clear()


def expired_rows(db, count):
    """Processed outbox rows old enough for the retention window to take them."""
    for i in range(count):
        db.add(models.DatabaseOutbox(
            event_uuid=str(uuid.uuid4()),
            event_type="CREATE", table_name="dt_map", payload={"n": i},
            status="SUCCESS", processed_chain=True,
            created_at=datetime.now(timezone.utc) - timedelta(days=10)))
    db.commit()


def published():
    return chain_activity.registry.ages()


# ------------------------------------------------------- the three states are separate

def test_a_process_that_never_purged_says_none_on_all_three():
    """Not zero rows, not "drained" - unknown. Zero would read as "it ran and found
    nothing", which is a different fact about the same table."""
    now = published()
    assert now["outbox_purge_age_seconds"] is None
    assert now["outbox_purge_deleted"] is None
    assert now["outbox_purge_capped"] is None


def test_a_capped_cycle_and_a_drained_one_are_different_values():
    """🔴 THE WHOLE DEFECT IN ONE ASSERTION. These two cycles removed the SAME number of
    rows; only this field can tell them apart."""
    chain_activity.registry.note_outbox_purge(20, True)
    assert published()["outbox_purge_capped"] is True
    chain_activity.registry.note_outbox_purge(20, False)
    assert published()["outbox_purge_capped"] is False
    assert published()["outbox_purge_deleted"] == 20


def test_an_unfinished_cycle_is_none_rather_than_false():
    """⚠️ `is False` would be a claim ("nothing more expired") about a cycle that raised
    partway and counted only some of what it removed."""
    chain_activity.registry.note_outbox_purge(7, None)
    assert published()["outbox_purge_capped"] is None
    assert published()["outbox_purge_deleted"] == 7


def test_the_age_starts_counting_from_the_purge():
    chain_activity.registry.note_outbox_purge(1, False)
    age = published()["outbox_purge_age_seconds"]
    assert isinstance(age, float) and age >= 0.0


def test_clear_forgets_the_purge_too():
    """A stale purge left behind `clear()` would read as this process's own."""
    chain_activity.registry.note_outbox_purge(5, True)
    chain_activity.registry.clear()
    assert published()["outbox_purge_capped"] is None


# ------------------------------------------------ the real purge, on real outbox rows

def test_a_purge_that_stops_at_the_cap_publishes_capped(db_session):
    """🔴 ARM ONE, THROUGH THE REAL FUNCTION. 35 expired rows, two chunks of ten - the
    cap binds and fifteen rows are still there."""
    expired_rows(db_session, 35)
    deleted = purge_expired_outbox_sync(lambda: db_session, retention_days=7,
                                        chunk_size=10, max_chunks=2)
    assert deleted == 20
    assert published()["outbox_purge_capped"] is True
    assert published()["outbox_purge_deleted"] == 20


def test_a_purge_that_removes_everything_publishes_not_capped(db_session):
    """🔴 ARM TWO. Without this a repair that hardcodes True would pass arm one."""
    expired_rows(db_session, 12)
    deleted = purge_expired_outbox_sync(lambda: db_session, retention_days=7,
                                        chunk_size=10, max_chunks=5)
    assert deleted == 12
    assert published()["outbox_purge_capped"] is False


def test_a_purge_with_nothing_to_remove_is_not_capped(db_session):
    """An empty run drained everything there was, which is zero of them."""
    assert purge_expired_outbox_sync(lambda: db_session, retention_days=7) == 0
    assert published()["outbox_purge_capped"] is False
    assert published()["outbox_purge_deleted"] == 0


def test_the_return_shape_did_not_change(db_session):
    """⛔ ONE LIVE CALLER, AND IT DISCARDS THIS. Widening the return would have produced
    a value with no reader; the three tests above read the published field instead."""
    expired_rows(db_session, 3)
    assert purge_expired_outbox_sync(lambda: db_session, retention_days=7) == 3


# ------------------------------------------------------------- it reaches the route

def test_the_worker_records_on_the_registry_the_route_reads():
    import inspect

    import chain_ingestion_worker as worker

    body = inspect.getsource(worker.purge_expired_outbox_sync)
    assert "chain_activity.registry.note_outbox_purge(" in body


def test_the_route_spreads_the_ages_dict_these_keys_live_in():
    """No route change was needed, and this is what keeps that true: the handler spreads
    `ages()`, so a key added there is published without editing main."""
    import inspect

    import main

    body = inspect.getsource(main.get_chain_queue_depth)
    assert "**chain_activity.registry.ages()" in body
    for key in ("outbox_purge_age_seconds", "outbox_purge_deleted", "outbox_purge_capped"):
        assert key in chain_activity.registry.ages()
