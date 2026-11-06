# -*- coding: utf-8 -*-
"""Lead 11-06 ①: /admin/indexes reads each index's size from the catalogue (relpages), not by opening the index, so a
session holding an index's lock - a DROP or REINDEX not yet committed, an ALTER queued behind autovacuum - does not
hold the screen (owner 11-06 «32s P /admin/indexes»). The size is said as an estimate.

  another session holds idx_outbox_pending's lock      index_states answers within the wait below
  the declared row                                      present, a size in bytes, size_estimate
  an index the catalogue counted 0 pages of             size None - not counted yet, never «0 B»
"""
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import models                                            # noqa: E402

pytestmark = pytest.mark.pg
INDEX = "idx_outbox_pending"
WAIT_SECONDS = 20


def test_a_held_index_lock_does_not_hold_the_index_screen(pg_engine):
    with pg_engine.begin() as connection:
        connection.exec_driver_sql("ANALYZE database_outbox")         # the catalogue counts its pages
    holder = pg_engine.raw_connection()
    answer = {}

    def read():
        answer["states"] = models.index_states(pg_engine, tables={})
    try:
        with holder.cursor() as cursor:
            cursor.execute("SELECT to_regclass(%s)", (INDEX,))
            assert cursor.fetchone()[0] is not None, "the scratch schema has no %s to hold" % INDEX
            cursor.execute("DROP INDEX %s" % INDEX)           # its AccessExclusive lock, held - not committed
        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        reader.join(WAIT_SECONDS)
        assert not reader.is_alive(), "index_states waited %d s on a lock held on %s" % (WAIT_SECONDS, INDEX)
    finally:
        holder.rollback()
        holder.close()
    [row] = [row for row in answer["states"]["declared"] if row["name"] == INDEX]
    assert row["state"] == models.INDEX_PRESENT, row
    assert isinstance(row["size_bytes"], int) and row["size_bytes"] > 0, row
    assert row["size_estimate"] is True, row


def test_an_index_not_counted_yet_has_no_size(pg_engine):
    with pg_engine.begin() as connection:
        connection.exec_driver_sql("ANALYZE database_outbox")
        connection.exec_driver_sql("UPDATE pg_class SET relpages = 0 WHERE oid = to_regclass('%s')" % INDEX)
    [row] = [row for row in models.index_states(pg_engine, tables={})["declared"] if row["name"] == INDEX]
    assert (row["state"], row["size_bytes"], row["size_estimate"]) == (models.INDEX_PRESENT, None, True), row
