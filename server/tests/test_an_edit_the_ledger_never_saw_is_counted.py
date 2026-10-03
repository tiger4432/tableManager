# -*- coding: utf-8 -*-
"""총괄 bb9b1c19c (나) · 1472ec1cc — an edit the ledger never saw is a number, and one command redoes
exactly those rows (소유자 10-02 「누락 절대 없고 회수도 절대 잘 됨?」).

The row index carries the print of the columns the source reads, written with the index line;
the census recomputes it from the table now. On PostgreSQL, on the hold world, the edit made by
SQL so no outbox event carries it - the follow-up never sees it.

  translated                             printed, nothing drifted
  a read column edited behind the chain  drifted 1 - the redo makes it 0 and the atom says the new value
  a column no binding names             not drifted - read, but no binding reaches it (판정 201)
  '' and NULL                            one print
  an index line with no print            counted apart, not as drift
  a paced census after a person's        carries the person's two counts and their time; counts nothing
  the record's next step                 the --drifted redo while edits are missed · the census when never counted
"""
import os
import sys

import pytest
from sqlalchemy import text

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from ledger import backfill, schema                                  # noqa: E402
from ledger.store import row_fingerprint_sql                         # noqa: E402
from support import hold_world as hw                                 # noqa: E402

pytestmark = pytest.mark.pg


@pytest.fixture(name="world")
def fixture_world(pg_engine, monkeypatch, tmp_path):
    yield from hw.build(pg_engine, monkeypatch, tmp_path)


def _drift(world):
    return backfill.rows_drifted(world["engine"], world["setup"], hw.SOURCE)


def _behind_the_chain(world, sql):
    world["db"].execute(text(sql))
    world["db"].commit()


def _translated(world):
    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    assert _drift(world) == {"rows_drifted": 0, "rows_unprinted": 0}


def test_an_edit_behind_the_chain_is_counted_and_redone(world):
    _translated(world)
    _behind_the_chain(world, 'UPDATE "%s" SET netdie = 8' % hw.OFFICIAL)
    assert _drift(world) == {"rows_drifted": 1, "rows_unprinted": 0}
    from ledger.store import LedgerStore
    census = backfill.measure_and_store(world["engine"], world["setup"], hw.SOURCE,
                                        LedgerStore(world["engine"]))
    assert census["rows_drifted"]["estimate"] == 1
    assert census["rows_drifted"]["measured_at"] == census["measured_at"]   # when it was counted
    assert census["rows_unprinted"]["estimate"] == 0                         # counted apart
    assert census["next_step"] == "python -m ledger.backfill --source %s --drifted" % hw.SOURCE
    backfill.retranslate_drifted(world["engine"], world["setup"], hw.SOURCE, apply=True)
    assert _drift(world) == {"rows_drifted": 0, "rows_unprinted": 0}
    assert [(job, float(value)) for job, value in hw.said(world)] == [("J1", 8.0)]
    census = backfill.measure_and_store(world["engine"], world["setup"], hw.SOURCE,
                                        LedgerStore(world["engine"]))
    assert census["rows_drifted"]["estimate"] == 0 and "next_step" not in census


def _stored(world):
    from ledger.store import LedgerStore
    store = LedgerStore(world["engine"])
    connection = store.connection()
    try:
        return store.read_cursor(connection, hw.SOURCE)["row_census"]
    finally:
        connection.close()


def test_a_paced_census_carries_the_persons_counts_and_counts_nothing(world, monkeypatch):
    """총괄 5baab7b8d: a person's census -> a paced tick -> the two counts and their time stand,
    though the table drifted again in between -> a person's census again -> the new counts."""
    from ledger.store import LedgerStore
    _translated(world)
    _behind_the_chain(world, 'UPDATE "%s" SET netdie = 8' % hw.OFFICIAL)
    person = backfill.measure_and_store(world["engine"], world["setup"], hw.SOURCE,
                                        LedgerStore(world["engine"]))
    assert person["rows_drifted"]["estimate"] == 1
    _behind_the_chain(world, 'UPDATE "%s" SET netdie = 9' % hw.OFFICIAL)   # still one row
    hw.push(world, [{"log_id": "B", "dt_job": "J2", "dt_x": 3, "dt_y": 4, "netdie": 5}])
    hw.settle(world)
    _behind_the_chain(world, "UPDATE \"%s\" SET netdie = 6 WHERE dt_job = 'J2'" % hw.OFFICIAL)
    assert _drift(world)["rows_drifted"] == 2, "canary: the table drifted again"

    def no_scan(*_args, **_kwargs):
        raise AssertionError("the paced tick counted drift")
    monkeypatch.setattr(backfill, "rows_drifted", no_scan)
    paced = backfill.measure_and_store(world["engine"], world["setup"], hw.SOURCE,
                                       LedgerStore(world["engine"]), exact_rows=False)
    monkeypatch.undo()
    for box in ("rows_drifted", "rows_unprinted"):
        assert paced[box] == person[box], box                  # the count and its own time
    assert paced["measured_at"] > person["measured_at"]        # the tick itself is new
    assert paced["next_step"] == person["next_step"]
    assert _stored(world)["rows_drifted"] == person["rows_drifted"]

    again = backfill.measure_and_store(world["engine"], world["setup"], hw.SOURCE,
                                       LedgerStore(world["engine"]))
    assert again["rows_drifted"]["estimate"] == 2
    assert again["rows_drifted"]["measured_at"] == again["measured_at"] > person["measured_at"]


def test_a_source_no_person_counted_names_the_census_as_its_next_step(world):
    """총괄 e1648e884: Not measured -> the census command, spelled as the census CLI's own."""
    from ledger import census_cli
    from ledger.store import LedgerStore
    _translated(world)
    paced = backfill.measure_and_store(world["engine"], world["setup"], hw.SOURCE,
                                       LedgerStore(world["engine"]), exact_rows=False)
    assert "rows_drifted" not in paced
    assert paced["next_step"] == "%s --source %s" % (census_cli.PROG, hw.SOURCE)
    assert _stored(world)["next_step"] == paced["next_step"]


def test_a_column_the_source_does_not_read_is_not_drift(world):
    _translated(world)
    _behind_the_chain(world, "UPDATE \"%s\" SET note = 'seen by nobody'" % hw.OFFICIAL)
    assert _drift(world)["rows_drifted"] == 0


def test_a_blank_and_a_null_print_alike(world):
    printed = row_fingerprint_sql(["a"], "t")
    with world["engine"].connect() as conn:
        blank = conn.execute(text("SELECT %s FROM (VALUES (''::text)) t(a)" % printed)).scalar()
        null = conn.execute(text("SELECT %s FROM (VALUES (NULL::text)) t(a)" % printed)).scalar()
    assert blank == null


def test_a_line_with_no_print_is_counted_apart(world):
    _translated(world)
    _behind_the_chain(world, "UPDATE %s SET row_fingerprint = NULL" % schema.ROW_REF_TABLE)
    assert _drift(world) == {"rows_drifted": 0, "rows_unprinted": 1}
