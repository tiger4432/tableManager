"""Recent audit history must observe a replay worker's committed write."""
from __future__ import annotations

from datetime import datetime, timezone

from admin import audit_history
from admin.audit_cache import AuditLogCache
from database import models


def _audit(tx_id: str, row_id: str):
    return models.AuditLog(
        table_name="audit_cache_cross_process_test",
        row_id=row_id,
        column_name="value",
        old_value=None,
        new_value="new",
        source_name="chain_ingestion",
        updated_by="chain_replay",
        transaction_id=tx_id,
        timestamp=datetime.now(timezone.utc),
    )


def _event_log(tx_id: str, row_id: str):
    """A log dict shaped exactly like the ones the internal event carries.

    `id` is 0 because that is the literal `crud.create_audit_log` writes
    (crud.py:1138); `bulk_insert_mappings` never writes the assigned key back.
    It is the whole reason `add_logs_batch` cannot advance the watermark, and a
    fixture that invented a real id here would test a system that does not exist.
    """
    return {"id": 0, "table_name": "audit_cache_cross_process_test",
            "row_id": row_id, "column_name": "value", "old_value": None,
            "new_value": "new", "source_name": "chain_ingestion",
            "updated_by": "chain_replay", "transaction_id": tx_id,
            "timestamp": datetime.now(timezone.utc), "business_key": None}


def test_recent_projection_refreshes_after_an_external_worker_commit(db_session):
    cache = AuditLogCache()
    db_session.add(_audit("before-replay", "before"))
    db_session.commit()
    cache.load_initial(db_session)

    # No cache mutation: this is the worker -> API-process boundary.
    db_session.add(_audit("chain_replay_after", "after"))
    db_session.commit()

    # A replay refresh must be a delta merge, never a second full history scan.
    cache.load_initial = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("refresh must not rebuild historic audit groups"))
    assert cache.refresh_if_stale(db_session) is True
    assert cache.groups[0]["transaction_id"] == "chain_replay_after"
    assert cache.groups[0]["total_count"] == 1
    assert cache.refresh_if_stale(db_session) is False


def test_rows_an_event_already_merged_are_not_counted_a_second_time(db_session):
    """ALARM FOR: the double count that the missing watermark write caused.

    `/internal/events/batch-refresh` merges a TRUNCATED sample of the rows plus
    the transaction's true size, and then cannot advance `_db_max_id` because
    every log dict it received carries id 0. So the very same rows are read
    again by the next `refresh_if_stale`. Measured against c723585 on a
    2,900,000-row fixture: 300 rows written, event reports 300, `total_count`
    reads 600 - and 100,000 rows read 200,000. Exactly two times, every time.
    """
    cache = AuditLogCache()
    db_session.add(_audit("seed-tx", "seed"))
    db_session.commit()
    cache.load_initial(db_session)

    # The worker commits ten rows and notifies with a two-row sample.
    for i in range(10):
        db_session.add(_audit("event-tx", f"row-{i}"))
    db_session.commit()
    cache.add_logs_batch([_event_log("event-tx", "row-0"),
                          _event_log("event-tx", "row-1")],
                         message_total_count=10)

    group = next(g for g in cache.groups if g["transaction_id"] == "event-tx")
    assert group["total_count"] == 10, "the event's own claim is unchanged"

    cache.refresh_if_stale(db_session)

    group = next(g for g in cache.groups if g["transaction_id"] == "event-tx")
    assert group["total_count"] == 10, \
        "the refresh read the same ten rows and added them a second time"


def test_a_bulk_delta_is_merged_not_rebuilt_and_models_only_what_a_group_keeps(db_session, monkeypatch):
    """ALARM FOR: the unbounded delta merge coming back - and for the rebuild coming back in its place.

    Until 2026-10-22 a delta past `recent_refresh_max_delta_rows` (2,000) fell back to the bounded rebuild, because
    the merge modelled every new row (~40 us each, 100,000 rows 4,010 ms against c723585). The lead's freeze
    measurement reversed that ruling (총괄 10-22, rebuild debt ㄱ): with a 2,000-row file every 2 s the rebuild ran
    every ~6 s and re-read up to 30,500 rows each time, 94 % of it the database's. Now a delta of any size is merged:
    its count by one GROUP BY, its logs the newest `recent_logs_per_group` of the group - so it models no more rows
    than the group keeps, and no rebuild runs."""
    from database import schemas

    monkeypatch.setattr(audit_history, "load_config", lambda *a, **k: {"recent_logs_per_group": 5})
    cache = AuditLogCache()
    db_session.add(_audit("bulk-seed", "seed"))
    db_session.commit()
    cache.load_initial(db_session)

    for i in range(12):
        db_session.add(_audit("bulk-tx", f"row-{i:02d}"))
    db_session.commit()

    monkeypatch.setattr(cache, "load_initial",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("a bulk delta must not rebuild")))
    modelled = []
    real_validate = schemas.AuditLogResponse.model_validate
    monkeypatch.setattr(schemas.AuditLogResponse, "model_validate",
                        lambda *a, **k: (modelled.append(1), real_validate(*a, **k))[1])

    assert cache.refresh_if_stale(db_session) is True
    group = next(g for g in cache.groups if g["transaction_id"] == "bulk-tx")
    assert group["total_count"] == 12
    assert [log.row_id for log in group["logs"]] == ["row-11", "row-10", "row-09", "row-08", "row-07"]
    assert len(modelled) == 5, "the merge modelled %d rows for a group that keeps 5" % len(modelled)
