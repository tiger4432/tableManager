# -*- coding: utf-8 -*-
"""Lead 11-08 (QA ④d): the ledger parent's `CREATE INDEX ... ON ONLY` asks for SHARE on the parent (C measured 11-08:
ShareLock not granted while a writer is open, and a second writer queued behind it); it ran with lock_timeout 0. It
now waits db_safety.DDL_LOCK_TIMEOUT, and a cut is put off as a build's is (`models.cut_sentence`).
"""
import threading
import time
import types

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.pg


def test_a_long_writer_on_the_ledger_parent_cuts_its_on_only_at_the_short_wait(pg_engine, monkeypatch):
    import db_safety
    from database import models
    from ledger import schema

    with pg_engine.begin() as conn:
        for sql in ("DROP TABLE IF EXISTS zz_led CASCADE",
                    "CREATE TABLE zz_led (k int, at date) PARTITION BY RANGE (at)",
                    "CREATE TABLE zz_led_a PARTITION OF zz_led FOR VALUES FROM ('2026-01-01') TO ('2026-02-01')"):
            conn.execute(text(sql))
    monkeypatch.setattr(db_safety, "DDL_LOCK_TIMEOUT", "1s")
    monkeypatch.setattr(schema, "world_names", lambda world: types.SimpleNamespace(ledger="zz_led"))
    monkeypatch.setattr(schema, "partitioned_indexes", lambda names: [("zz_led_k", "(k)", "", "{index}_c", None)])
    monkeypatch.setattr(schema, "in_space", lambda names, name: name)

    def on_only(connection, names, index, columns, predicate, **_kw):
        with connection.cursor() as cursor:
            cursor.execute("CREATE INDEX IF NOT EXISTS %s ON ONLY %s %s" % (index, names.ledger, columns))
        connection.commit()
        return {"parent_valid": True, "deferred": False}

    monkeypatch.setattr(schema, "build_partitioned_index", on_only)
    holder = pg_engine.raw_connection()
    holder.cursor().execute("INSERT INTO zz_led (k, at) VALUES (1, '2026-01-05')")      # a writer left open
    release = threading.Timer(6.0, holder.rollback)
    release.start()
    lines = []
    row = {"world": "w", "name": "zz_led_k", "table": "zz_led", "partitions_missing": 1, "partitions": 1}
    try:
        with models.built_tables():
            started = time.monotonic()
            word = models._build_ledger_index(pg_engine, row, lines.append)
            took = time.monotonic() - started
            sentence = models.cut_sentence("zz_led_k")
    finally:
        release.join()
        holder.close()
        with pg_engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS zz_led CASCADE"))
    assert word == models.INDEX_DEFERRED and took < 4.0, (word, took, lines)
    assert sentence.startswith("cut 1 time(s)") and any(sentence in line for line in lines), lines
