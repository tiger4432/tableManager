# -*- coding: utf-8 -*-
"""Lead 11-06 ②: `build_partitioned_index` reads every partition's state in one catalogue read, so /admin/indexes'
look at a world costs the same statements however many partitions its ledger has.

  partition            its own index                       the dry run says
  first                built and attached                  already
  second               built, valid, not attached          would attach
  third                none                                would build
  fourth               INVALID, nobody building it         would build
                       INVALID, a session building it      left to that build - pid and phase
  statements           four partitions, then two detached  the same count
"""
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db_waits                                                        # noqa: E402
from ledger import schema                                              # noqa: E402

pytestmark = pytest.mark.pg
WORLD = "gatec"
INDEX, COLUMNS = "zz_gate_c", "(source_raw_ref)"


class _Counted:
    """The raw connection, its statements counted - what the judgment costs."""

    def __init__(self, driver):
        self._driver, self.statements = driver, 0

    def cursor(self, *a, **k):
        outer, cursor = self, self._driver.cursor(*a, **k)

        class Cursor:
            def execute(self, *a, **k):
                outer.statements += 1
                return cursor.execute(*a, **k)

            def __enter__(self):
                cursor.__enter__()
                return self

            def __exit__(self, *a):
                return cursor.__exit__(*a)

            def __getattr__(self, name):
                return getattr(cursor, name)
        return Cursor()

    @property
    def autocommit(self):
        return self._driver.autocommit

    @autocommit.setter
    def autocommit(self, value):
        self._driver.autocommit = value

    def __getattr__(self, name):
        return getattr(self._driver, name)


def _judge(connection):
    counted = _Counted(getattr(connection, "driver_connection", connection))
    said = []
    out = schema.build_partitioned_index(counted, names_of(), INDEX, COLUMNS, apply=False, say=said.append)
    return out, counted.statements, said


def names_of():
    return schema.world_names(WORLD)


def test_every_partition_is_judged_from_one_read(pg_engine, monkeypatch):
    monkeypatch.setattr(schema, "worlds", lambda: [WORLD])
    names = names_of()
    space = names.ledger.split(".")[0]
    ledger_name = names.ledger.rsplit(".", 1)[-1]
    builds = {}
    asked = []
    monkeypatch.setattr(db_waits, "index_builds", lambda driver: asked.append(1) or dict(builds))
    connection = pg_engine.raw_connection()

    def child(partition):
        return "%s_%s" % (INDEX, partition.removeprefix(ledger_name + "_"))

    def run(*statements):
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
        connection.commit()
    try:
        schema.ensure_schema(connection, names=names)
        for month in (7, 8, 9, 10):                             # before the index - a later partition gets its copy
            schema.ensure_partition(connection, datetime(2026, month, 15, tzinfo=timezone.utc), names=names)
        first, second, third, fourth = [name for name, _bound in schema.partitions(connection, names)]
        run("CREATE INDEX %s ON ONLY %s %s" % (INDEX, names.ledger, COLUMNS),
            "CREATE INDEX %s ON %s.%s %s" % (child(first), space, first, COLUMNS),
            "ALTER INDEX %s.%s ATTACH PARTITION %s.%s" % (space, INDEX, space, child(first)),
            "CREATE INDEX %s ON %s.%s %s" % (child(second), space, second, COLUMNS),
            "CREATE INDEX %s ON %s.%s %s" % (child(fourth), space, fourth, COLUMNS),
            "UPDATE pg_index SET indisvalid = false WHERE indexrelid = to_regclass('%s.%s')" % (space, child(fourth)))

        four, four_statements, said = _judge(connection)
        assert (four["already"], four["would_attach"], four["would_build"], four["building"]) == (1, 1, 2, []), said
        assert four["parent_valid"] is False
        assert len(asked) == 1, "an INVALID index and the running builds were read %d times" % len(asked)
        assert said == ["%s: already has it" % first,
                        "%s: would attach the %s already there" % (second, child(second)),
                        "%s: would build %s CONCURRENTLY and attach it" % (third, child(third)),
                        "%s: would build %s CONCURRENTLY and attach it" % (fourth, child(fourth))]

        builds[(space, child(fourth))] = (4242, None, "building - scanning table")
        held, _, said = _judge(connection)
        assert (held["already"], held["would_attach"], held["would_build"]) == (1, 1, 1), said
        assert held["building"] == ["%s building - scanning table by pid 4242" % child(fourth)]

        rows = [row for row in schema.partitioned_index_states(pg_engine) if row["world"] == names.name]
        assert rows and all(row["partitions"] == 4 for row in rows), rows

        run(*["ALTER TABLE %s DETACH PARTITION %s.%s" % (names.ledger, space, name) for name in (third, fourth)])
        two, two_statements, _ = _judge(connection)
        assert (two["already"], two["would_attach"], two["would_build"], two["building"]) == (1, 1, 0, [])
        assert len(asked) == 2, "no attached partition's index is INVALID, yet the running builds were read"
        assert four_statements == two_statements, \
            "four partitions took %d statements, two took %d" % (four_statements, two_statements)
    finally:
        connection.rollback()
        with connection.cursor() as cursor:
            cursor.execute("DROP SCHEMA IF EXISTS %s CASCADE" % space)
        connection.commit()
        connection.close()
