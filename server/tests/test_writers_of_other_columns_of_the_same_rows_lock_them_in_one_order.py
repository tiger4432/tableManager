# -*- coding: utf-8 -*-
"""총괄 5c0a86cec ② (소유자 10-20): a batch's changed rows are locked first, a table's all in row_id order, before the
shape groups write them (`database.write_changed_rows_by_shape`). The groups lock group by group, so two writers that
change other columns of the same rows took them in crossing orders and deadlocked (40P01, which nothing retries)."""
import threading
import time
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from database import crud, schemas

TABLE = "pgqa_bk_table"


def _item(key, **updates):
    return schemas.GeneralUpdateItem(business_key_val=key, updates={"part_no": key, **updates},
                                     source_name="probe.csv", updated_by="watcher")


@pytest.mark.pg
def test_two_writers_changing_other_columns_of_the_same_rows_wait_instead_of_deadlocking(pg_session, pg_engine):
    """The crossing made certain: another writer holds the lower row; this batch changes `qty` on the lower row and
    `note` on the higher one, so its `note` group comes first and would take the higher row before waiting; the other
    writer then asks for the higher row. Locked in row_id order, this batch waits at the lower row with the higher
    one still free."""
    import psycopg2

    from conftest import PG_TEST_SCHEMA, _resolve_pg_test_url
    from tests.support.isolated_pg import scratch_connect_args

    stem = "S%s-" % uuid.uuid4().hex[:6]
    crud.apply_batch_updates(pg_session, TABLE, schemas.GeneralUpdateBatch(updates=[
        _item(stem + "1", qty=1, note="seed"), _item(stem + "2", qty=1, note="seed")]))
    pg_session.commit()
    (lo, k_lo), (hi, k_hi) = pg_session.execute(text(
        'SELECT row_id, business_key_val FROM "%s" WHERE business_key_val LIKE :p ORDER BY row_id' % TABLE),
        {"p": stem + "%"}).all()
    pg_session.commit()
    url, _ = _resolve_pg_test_url()
    other = psycopg2.connect(url, **scratch_connect_args(PG_TEST_SCHEMA))
    watch = psycopg2.connect(url, **scratch_connect_args(PG_TEST_SCHEMA))
    watch.autocommit = True
    failed = {}

    def write():
        db = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)()
        try:
            crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[
                _item(k_lo, qty=2), _item(k_hi, note="mine")]))
        except Exception as exc:                                   # noqa: BLE001 - the assertion reads it
            failed["error"] = exc
        finally:
            db.close()

    try:
        with other.cursor() as cur:
            cur.execute("SET lock_timeout = '5s'")
            cur.execute('UPDATE "%s" SET note = %%s WHERE row_id = %%s' % TABLE, ("theirs", lo))
        writer = threading.Thread(target=write)
        writer.start()
        deadline = time.monotonic() + 15
        waiting = False
        while time.monotonic() < deadline and not waiting:
            with watch.cursor() as cur:
                cur.execute("SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock' AND query ILIKE %s",
                            ("%%%s%%" % TABLE,))
                waiting = cur.fetchone()[0] > 0
            time.sleep(0.05)
        assert waiting, "this batch never waited on the other writer's row - the crossing was not made"
        with other.cursor() as cur:
            cur.execute('UPDATE "%s" SET qty = 9 WHERE row_id = %%s' % TABLE, (hi,))   # raises when the two cross
        other.commit()
        writer.join(30)
    finally:
        other.close()
        watch.close()
    assert not writer.is_alive()
    assert "error" not in failed, failed.get("error")
    got = pg_session.execute(text('SELECT row_id, qty, note FROM "%s" WHERE row_id IN (:a, :b) ORDER BY row_id'
                                  % TABLE), {"a": lo, "b": hi}).all()
    assert [tuple(r) for r in got] == [(lo, 2.0, "theirs"), (hi, 9.0, "mine")], "each writer's own column on each row"
