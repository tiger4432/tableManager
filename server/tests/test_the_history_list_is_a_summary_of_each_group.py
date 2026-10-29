# -*- coding: utf-8 -*-
"""Owner 10-29 «감사로그는 네비게이션 · 상세보기 밖에 안 씀 — 경량화» (lead ㄱ): the history list carries each group's
summary - its count, its columns, its receipts per world in the order written, one representative row - and never a
group's logs. The answer is the same whichever way the rows reached the list: a rebuild, a refresh's delta, or a
notification, on SQLite and on PostgreSQL."""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main                                                   # noqa: E402
from admin.audit_cache import AuditLogCache                   # noqa: E402
from database import models, schemas                          # noqa: E402
from ledger.runtime_v2 import RECEIPT_COLUMN, RECEIPT_FAILED  # noqa: E402

TX = "summary-probe-tx"
T0 = datetime(2026, 10, 29, 9, 0, tzinfo=timezone.utc)
# oldest first: (row, column, new value)
WRITTEN = [("r1", "a", "1"), ("_BATCH_", RECEIPT_COLUMN, {"world": "W1", "status": RECEIPT_FAILED}),
           ("r2", "b", "2"), ("_BATCH_", RECEIPT_COLUMN, {"world": "W2", "status": "ok"}),
           ("_BATCH_", RECEIPT_COLUMN, {"world": "W1", "status": "ok"})]
LISTED = {"transaction_id": TX, "total_count": 5, "summary_columns": sorted({"a", "b", RECEIPT_COLUMN}),
          "representative": "r2",
          "receipt_worlds": [{"world": "W1", "receipts": 2, "failed": 1}, {"world": "W2", "receipts": 1, "failed": 0}]}


def _row(i, row_id, column, value):
    return models.AuditLog(table_name="summary_probe", row_id=row_id, column_name=column, old_value=None,
                           new_value=value, source_name="probe", updated_by="probe", transaction_id=TX,
                           timestamp=T0 + timedelta(seconds=i))


def _listed(db, cache):
    shaped = main._shape_recent_groups(db, cache.groups, False, None, 100)["groups"]
    one = next(g for g in shaped if g["transaction_id"] == TX)
    return {"transaction_id": one["transaction_id"], "total_count": one["total_count"],
            "summary_columns": one["summary_columns"], "representative": one["logs"][0].row_id,
            "receipt_worlds": one["receipt_worlds"]}


def _every_way(db):
    db.add(models.AuditLog(table_name="summary_probe", row_id="seed", column_name="z", new_value="0",
                           source_name="probe", updated_by="probe", transaction_id="summary-seed", timestamp=T0))
    db.commit()
    split = AuditLogCache()
    split.load_initial(db)
    for i, (row_id, column, value) in enumerate(WRITTEN[:2]):
        db.add(_row(i, row_id, column, value))
    db.commit()
    assert split.refresh_if_stale(db) is True
    for i, (row_id, column, value) in enumerate(WRITTEN[2:], start=2):
        db.add(_row(i, row_id, column, value))
    db.commit()
    assert split.refresh_if_stale(db) is True

    modelled = []
    real_validate = schemas.AuditLogResponse.model_validate
    rebuilt = AuditLogCache()
    try:
        schemas.AuditLogResponse.model_validate = lambda *a, **k: (modelled.append(1), real_validate(*a, **k))[1]
        rebuilt.load_initial(db)
    finally:
        schemas.AuditLogResponse.model_validate = real_validate
    assert len(modelled) == len(rebuilt.groups), "the list read %d rows for %d groups" % (len(modelled), len(rebuilt.groups))

    told = AuditLogCache()
    told.is_loaded = True
    logs = [{"id": 0, "table_name": "summary_probe", "row_id": row_id, "column_name": column, "old_value": None,
             "new_value": value, "source_name": "probe", "updated_by": "probe", "transaction_id": TX,
             "timestamp": (T0 + timedelta(seconds=i)).isoformat()} for i, (row_id, column, value) in enumerate(WRITTEN)]
    told.add_logs_batch(logs[:2][::-1])
    told.add_logs_batch(logs[2:][::-1])
    assert _listed(db, rebuilt) == _listed(db, split) == _listed(db, told) == LISTED


def test_the_list_is_the_same_summary_however_its_rows_arrive(db_session):
    _every_way(db_session)


@pytest.mark.pg
def test_the_list_is_the_same_summary_however_its_rows_arrive_on_postgres(pg_session):
    _every_way(pg_session)
