# -*- coding: utf-8 -*-
"""총괄 bb9b1c19c (나) · 1472ec1cc — an edit the ledger never saw is a number, and one command redoes
exactly those rows (소유자 10-02 「누락 절대 없고 회수도 절대 잘 됨?」).

The row index carries the print of the columns the source reads, written with the index line;
the census recomputes it from the table now. On PostgreSQL, on the hold world, the edit made by
SQL so no outbox event carries it - the follow-up never sees it.

  translated                             printed, nothing drifted
  a read column edited behind the chain  drifted 1 - the redo makes it 0 and the atom says the new value
  a column only map.input_columns names  not drifted - no binding reaches it (판정 201)
  '' and NULL                            one print
  an index line with no print            counted apart, not as drift
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
    paced = backfill.measure_and_store(world["engine"], world["setup"], hw.SOURCE,
                                       LedgerStore(world["engine"]), exact_rows=False)
    assert "rows_drifted" not in paced                      # the paced tick does not scan
    backfill.retranslate_drifted(world["engine"], world["setup"], hw.SOURCE, apply=True)
    assert _drift(world) == {"rows_drifted": 0, "rows_unprinted": 0}
    assert [(job, float(value)) for job, value in hw.said(world)] == [("J1", 8.0)]


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
