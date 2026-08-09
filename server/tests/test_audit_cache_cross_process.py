"""Recent audit history must observe a replay worker's committed write."""
from __future__ import annotations

from datetime import datetime, timezone

from audit_cache import AuditLogCache
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
