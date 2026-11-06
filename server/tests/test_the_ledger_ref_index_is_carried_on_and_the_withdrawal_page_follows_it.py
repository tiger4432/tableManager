# -*- coding: utf-8 -*-
"""총괄 7b: the ledger's ref index (`idx_ledger_events_source_raw_ref_hash`, hash on source_raw_ref) is built
online by `scripts/build_ledger_ref_index.py`, and the stale withdrawal's page follows it.

  the owner's SQL run halfway        the parent ON ONLY, the first partition's `<partition>_ref_hash`
                                     built and not attached, the second partition without
  the script, preview                builds nothing; 1 would be attached as it is, 1 built
  the script, applied                the first partition's own index is attached, not built again;
                                     the second built and attached; the parent valid
  the script, again                  both already - nothing built
  the page                           50,000 and the script's command while the parent is not valid;
                                     1,000 once it is
"""
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import backfill, schema                                   # noqa: E402
from scripts import build_ledger_ref_index                            # noqa: E402

pytestmark = pytest.mark.pg
WORLD = "ref7b"


def _ref_indexes_on(connection, names, partition):
    """The hash indexes on source_raw_ref one partition holds, by name."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT indexname FROM pg_indexes WHERE schemaname = %s AND tablename = %s"
                       " AND indexdef LIKE '%%USING hash (source_raw_ref)%%' ORDER BY 1",
                       (names.ledger.split(".")[0], partition))
        return [row[0] for row in cursor.fetchall()]


def test_a_half_built_ref_index_is_carried_on_and_the_page_follows_it(pg_engine, monkeypatch):
    monkeypatch.setattr(schema, "worlds", lambda: [WORLD])
    names = schema.world_names(WORLD)
    space = names.ledger.split(".")[0]
    connection = pg_engine.raw_connection()
    try:
        schema.ensure_schema(connection, names=names)
        with connection.cursor() as cursor:                     # partitions older than the index
            cursor.execute("DROP INDEX IF EXISTS %s" % schema.in_space(names, schema.REF_INDEX))
        connection.commit()
        for month in (9, 10):
            schema.ensure_partition(connection, datetime(2026, month, 15, tzinfo=timezone.utc), names=names)
        first, second = [name for name, _bound in schema.partitions(connection, names)]
        with connection.cursor() as cursor:                     # the owner's three statements, half run
            cursor.execute(schema.ref_index_parent_sql(names))
            cursor.execute("CREATE INDEX %s ON %s.%s USING hash (source_raw_ref)"
                           % (schema.REF_INDEX_CHILD.format(partition=first), space, first))
        connection.commit()

        page, said = backfill.stale_page_refs(pg_engine, WORLD)
        assert page == backfill.STALE_PAGE_REFS_UNINDEXED == 50000, said
        assert "build_ledger_ref_index.py --apply --world %s" % WORLD in said

        preview = build_ledger_ref_index.main(["--world", WORLD], connection=connection, say=lambda line: None)
        assert (preview["built"], preview["already"], preview["would_build"], preview["would_attach"]) == (0, 0, 1, 1)
        assert not preview["parent_valid"]

        done = build_ledger_ref_index.main(["--world", WORLD, "--apply"], connection=connection, engine=pg_engine,
                                           say=lambda line: None)
        assert (done["built"], done["attached"], done["already"], done["parent_valid"]) == (1, 1, 0, True)
        assert _ref_indexes_on(connection, names, first) == [schema.REF_INDEX_CHILD.format(partition=first)], \
            "the half-run's own index was built a second time"
        assert _ref_indexes_on(connection, names, second) == [schema.REF_INDEX_CHILD.format(partition=second)]

        page, said = backfill.stale_page_refs(pg_engine, WORLD)
        assert page == backfill.STALE_PAGE_REFS == 1000, said

        again = build_ledger_ref_index.main(["--world", WORLD, "--apply"], connection=connection, engine=pg_engine,
                                            say=lambda line: None)
        assert (again["built"], again["attached"], again["already"], again["parent_valid"]) == (0, 0, 2, True)
    finally:
        connection.rollback()
        with connection.cursor() as cursor:
            cursor.execute("DROP SCHEMA IF EXISTS %s CASCADE" % space)
        connection.commit()
        connection.close()


def test_a_partition_held_in_its_world_s_own_schema_is_waited_for_and_deferred(pg_engine, monkeypatch):
    """C 11-06 C4: a branch world's partitions live in a schema the search path does not reach - the wait before the
    build asks who holds the partition THERE (the builder's `schema`). Held past the wait it is deferred and not
    attached, the other one built; asked in the search path's schema the holder would not be seen and the build would
    wait on it for as long as it holds - bounded here, so that is red, not a hang."""
    import threading

    from database import models

    monkeypatch.setattr(schema, "worlds", lambda: [WORLD])
    monkeypatch.setattr(models, "INDEX_WAIT_BEFORE_SECONDS", 1.0)
    monkeypatch.setattr(models, "INDEX_WAIT_POLL_SECONDS", 0.2)
    names = schema.world_names(WORLD)
    space = names.ledger.split(".")[0]
    connection, holder = pg_engine.raw_connection(), pg_engine.raw_connection()
    build, said, out = None, [], {}
    try:
        schema.ensure_schema(connection, names=names)
        with connection.cursor() as cursor:
            cursor.execute("DROP INDEX IF EXISTS %s" % schema.in_space(names, schema.REF_INDEX))
        connection.commit()
        for month in (9, 10):
            schema.ensure_partition(connection, datetime(2026, month, 15, tzinfo=timezone.utc), names=names)
        first, second = [name for name, _bound in schema.partitions(connection, names)]
        with holder.cursor() as cursor:                             # held, its transaction left open
            cursor.execute("LOCK TABLE %s.%s IN SHARE ROW EXCLUSIVE MODE" % (space, first))
        build = threading.Thread(target=lambda: out.update(done=build_ledger_ref_index.main(
            ["--world", WORLD, "--apply"], connection=connection, engine=pg_engine, say=said.append)), daemon=True)
        build.start()
        build.join(15)
        assert "done" in out, "past the wait it gives up - not a build waiting on the holder: %s" % said
        assert (out["done"]["deferred"], out["done"]["built"], out["done"]["parent_valid"]) == (1, 1, False), said
        assert any("not built - waited 1s for pid " in line and "holding %s" % first in line for line in said), said
    finally:
        holder.rollback()
        holder.close()
        if build is not None:
            build.join(60)
        connection.rollback()
        with connection.cursor() as cursor:
            cursor.execute("DROP SCHEMA IF EXISTS %s CASCADE" % space)
        connection.commit()
        connection.close()
