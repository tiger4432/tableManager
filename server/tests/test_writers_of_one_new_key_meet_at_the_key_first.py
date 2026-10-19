# -*- coding: utf-8 -*-
"""총괄 5c0a86cec (소유자 10-20): two writers of one table that insert the same new key meet at its unique index
BEFORE either writes its history and layers - the batch's rows go in first, the new ones in business-key order.
So the loser's rollback leaves ~2 dead rows instead of every layer and audit line it wrote, two batches of the
same new keys in opposite orders wait in one order instead of deadlocking (40P01, which nothing retries), and the
admin retry that runs in the server process takes the table's file lock as the watcher does."""
import os
import threading
import time
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from database import crud, models, schemas
from sql_budget import inserts_into, record_statements

TABLE = "inventory_master"


def _items(keys, source="day.csv"):
    return [schemas.GeneralUpdateItem(business_key_val=k, updates={"part_no": k, "category": "c", "stock_qty": 1},
                                      source_name=source, updated_by="watcher") for k in keys]


def test_new_rows_go_in_in_business_key_order(db_session):
    keys = ["K3", "K1", "K4", "K2"]
    crud.apply_batch_updates(db_session, TABLE, schemas.GeneralUpdateBatch(updates=_items(keys)))
    # sqlite numbers a table's rows in the order they were inserted
    order = [k for (k,) in db_session.execute(text(
        'SELECT business_key_val FROM "%s" ORDER BY rowid' % TABLE)).all()]
    assert order == sorted(keys)


def test_the_rows_go_in_before_the_history_and_the_layers(db_session):
    with record_statements(db_session) as recorded:
        crud.apply_batch_updates(db_session, TABLE, schemas.GeneralUpdateBatch(updates=_items(["K1", "K2"])))
    position = {id(call): n for n, call in enumerate(recorded)}
    first = {name: min(position[id(c)] for c in inserts_into(recorded, name))
             for name in (TABLE, "cell_sources", "audit_logs")}
    assert first[TABLE] < first["cell_sources"] and first[TABLE] < first["audit_logs"], first


def test_the_server_s_admin_retry_takes_the_table_s_file_lock(client, db_session, tmp_path, monkeypatch):
    import directory_watcher

    monkeypatch.delenv("DECOUPLED", raising=False)
    workspace = tmp_path / "ws"
    (workspace / "archives").mkdir(parents=True)
    monkeypatch.setattr(directory_watcher, "resolve_workspace_root", lambda *a, **k: str(workspace))
    held = []
    monkeypatch.setattr(directory_watcher.IngestionHandler, "process_archived_file_sync",
                        lambda self, log, db, uploader="system": held.append(
                            directory_watcher.get_workspace_serial_lock(self.workspace_path).locked()) or True)
    log = models.FileIngestionLog(filename="f.csv", filepath=str(workspace / "raws" / "f.csv"), table_name="t",
                                  status="FAILED")
    db_session.add(log)
    db_session.commit()

    client.post("/admin/file-ingestion/retry-failed", params={"log_id": log.id})

    assert held == [True]
    assert not directory_watcher.get_workspace_serial_lock(str(workspace)).locked(), "and lets it go"


@pytest.mark.pg
def test_two_writers_of_the_same_new_keys_in_opposite_orders_wait_instead_of_deadlocking(pg_session, pg_engine):
    """The crossing made certain: another writer holds K1 uncommitted, this batch sends K2 then K1, and the
    other writer then asks for K2. Rows in payload order hold K2 by then - the two wait on each other; in key
    order this batch is still waiting at K1 and K2 is free."""
    import psycopg2

    from conftest import PG_TEST_SCHEMA, _resolve_pg_test_url
    from tests.support.isolated_pg import scratch_connect_args

    pg_table = "pgqa_bk_table"
    url, _ = _resolve_pg_test_url()
    stem = "X%s-" % uuid.uuid4().hex[:6]
    k1, k2 = stem + "1", stem + "2"
    other = psycopg2.connect(url, **scratch_connect_args(PG_TEST_SCHEMA))
    watch = psycopg2.connect(url, **scratch_connect_args(PG_TEST_SCHEMA))
    watch.autocommit = True
    failed = {}

    def write():
        db = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)()
        try:
            crud.apply_batch_updates(db, pg_table, schemas.GeneralUpdateBatch(updates=[
                schemas.GeneralUpdateItem(business_key_val=k, updates={"part_no": k, "qty": 1, "note": "mine"},
                                          source_name="hour.csv", updated_by="watcher") for k in (k2, k1)]))
        except Exception as exc:                                   # noqa: BLE001 - the assertion reads it
            failed["error"] = exc
        finally:
            db.close()

    insert = 'INSERT INTO "%s" (row_id, business_key_val, part_no, qty, note) VALUES (%%s, %%s, %%s, 9, %%s)' % pg_table
    try:
        with other.cursor() as cur:
            cur.execute("SET lock_timeout = '5s'")
            cur.execute(insert, ("THEIRS-1", k1, k1, "theirs"))
        writer = threading.Thread(target=write)
        writer.start()
        deadline = time.monotonic() + 15
        waiting = False
        while time.monotonic() < deadline and not waiting:
            with watch.cursor() as cur:
                cur.execute("SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock' AND query ILIKE %s",
                            ("%%INSERT INTO %s%%" % pg_table,))
                waiting = cur.fetchone()[0] > 0
            time.sleep(0.05)
        assert waiting, "this batch never waited on the other writer's K1 - the crossing was not made"
        with other.cursor() as cur:
            cur.execute(insert, ("THEIRS-2", k2, k2, "theirs"))       # raises when the two wait on each other
        other.commit()
        writer.join(30)
    finally:
        other.close()
        watch.close()
    assert not writer.is_alive()
    assert "error" not in failed, failed.get("error")
    rows = pg_session.execute(text('SELECT business_key_val, row_id, note FROM "%s" WHERE business_key_val IN (:a, :b) '
                                   "ORDER BY 1" % pg_table), {"a": k1, "b": k2}).all()
    assert [(r[0], r[1], r[2]) for r in rows] == [(k1, "THEIRS-1", "mine"), (k2, "THEIRS-2", "mine")], \
        "one row per key, the other writer's, carrying this batch's values"
