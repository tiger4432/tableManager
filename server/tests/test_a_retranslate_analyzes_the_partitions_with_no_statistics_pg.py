"""A re-translate's withdrawal finds atoms by `source_who = %s AND source_raw_ref = ANY(%s)` (총괄 10-14): on a ledger
partition never analyzed that reads a default selectivity, and the valid ref index lost to a Seq Scan - 27 rows a page,
1.56 s in production. The run analyzes the partitions with no statistics before its first page and, at the end of every
page, the ones it has written that its own writes changed by the share (총괄 dcccc914b: production slowed again as a run
went on); and it searches once a page: the DELETE; the count is a preview's.

  stale     never analyzed · analyzed · changed by the share since (a share above that: not) · `only` narrows
  the run   a run analyzes the never-analyzed one and says «analyzed N partition(s) in X s: …»; every page asks after
            the partitions the run has written
  held      a partition another session holds is not waited for - said, left to the next page; one analyzed meanwhile
            (asked again under its lock) is not analyzed twice - two slices never analyze one partition
  the page  one withdrawal search a page - the DELETE - and the run's «withdraw» is what it took; a preview still counts
  setting   anything but a number above 0 reads the default, said
"""
import logging
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from admin import retroactive
from chain import keyset_scan
from conftest import PG_TEST_SCHEMA
from ledger import backfill, schema
from ledger.store import LedgerStore
from support import hold_world as hw

pytestmark = pytest.mark.pg
S = PG_TEST_SCHEMA
FAR = datetime(2031, 1, 15, tzinfo=timezone.utc)


@pytest.fixture(name="world")
def fixture_world(pg_engine, monkeypatch, tmp_path):
    for w in hw.build(pg_engine, monkeypatch, tmp_path, batch=True):
        hw.push(w, [{"log_id": "L%03d" % i, "dt_job": "J%d" % (i % 3), "dt_x": i, "dt_y": 1, "netdie": i}
                    for i in range(30)])
        hw.settle(w)
        yield w


@pytest.fixture(name="far")
def fixture_far(world):
    """A partition of its own in the scratch schema - copies of the world's atoms, autovacuum off: never analyzed."""
    engine = world["engine"]
    raw = engine.raw_connection()
    try:
        name = schema.ensure_partition(raw, FAR)
    finally:
        raw.close()
    with engine.begin() as conn:
        assert conn.execute(text("SELECT current_schema()")).scalar() == S
        conn.execute(text('ALTER TABLE "%s".%s SET (autovacuum_enabled = false)' % (S, name)))
        columns = [c for c in conn.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = :s AND table_name = "
            "'ledger_events' AND column_name NOT IN ('id', 'occurred_at') ORDER BY ordinal_position"),
            {"s": S}).scalars()]
        copied = conn.execute(text(
            'INSERT INTO "%s".ledger_events (id, occurred_at, %s) SELECT gen_random_uuid(), :far, %s '
            'FROM "%s".ledger_events WHERE source_who = :w AND occurred_at < :far'
            % (S, ", ".join(columns), ", ".join(columns), S)), {"far": FAR, "w": hw.SOURCE}).rowcount
        assert copied > 0
    yield name
    with engine.begin() as conn:
        conn.execute(text('DROP TABLE IF EXISTS "%s".%s' % (S, name)))


def _stale(engine, share=backfill.ANALYZE_SHARE_DEFAULT, only=None):
    raw = engine.raw_connection()
    try:
        return schema.stale_partitions(raw, schema.world_names(None), share, only)
    finally:
        raw.rollback()
        raw.close()


def _run(world, **given):
    """A whole-source re-translate inside a run - its lines."""
    lines = []
    control = retroactive.RunControl(None, op="ledger_rescope", log=lines.append, report=lambda processed: None)
    token = keyset_scan.RUN_CONTROL.set(control)
    try:
        out = backfill.rescope(world["engine"], world["setup"], hw.SOURCE, None, [], apply=True,
                               page_rows=backfill.RESCOPE_PAGE_ROWS, whole_source=True, **given)
    finally:
        keyset_scan.RUN_CONTROL.reset(token)
    return out, lines


def test_which_partitions_are_stale(world, far):
    engine = world["engine"]
    # a share no change reaches: «never analyzed» names it by itself
    assert far in _stale(engine, share=1e9), "never analyzed"
    assert _stale(engine, only=[far]) == [far]
    assert _stale(engine, only=["ledger_events_2030_12"]) == [] and _stale(engine, only=[]) == []
    with engine.begin() as conn:
        conn.execute(text('ANALYZE "%s".%s' % (S, far)))
    assert far not in _stale(engine), "analyzed"
    with engine.begin() as conn:
        rows = conn.execute(text('SELECT count(*) FROM "%s".%s' % (S, far))).scalar()
        changed = conn.execute(text(
            'UPDATE "%s".%s SET source_event_state = source_event_state WHERE id IN (SELECT id FROM "%s".%s LIMIT :n)'
            % (S, far, S, far)), {"n": rows // 2}).rowcount
        conn.execute(text("SELECT pg_stat_force_next_flush()"))
    assert changed == rows // 2 > 0
    assert far in _stale(engine, share=0.2), "half its rows changed since"
    assert far not in _stale(engine, share=0.9)


def test_a_run_analyzes_a_partition_never_analyzed_and_says_so(world, far):
    out, lines = _run(world)
    said = [line for line in lines if line.startswith("[ledger_rescope] analyzed ")]
    assert said and far in said[0] and " partition" in said[0] and " s: " in said[0], lines[:6]
    before = [line for line in lines if line.startswith("[ledger_rescope] analyzing ")]
    assert before and far in before[0] and lines.index(before[0]) < lines.index(said[0]), \
        "the run's stage while it analyzes says so (QA 10-14 ③)"
    assert out["rows_in_scope"] == 30
    # analyzed: reltuples is no longer -1 (its atoms were then withdrawn by the run - stale again by its changes)
    with world["engine"].connect() as conn:
        assert conn.execute(text("SELECT reltuples FROM pg_class WHERE oid = to_regclass(:p)"),
                            {"p": '"%s".%s' % (S, far)}).scalar() >= 0


def test_every_page_asks_after_the_partitions_the_run_has_written(world, monkeypatch):
    """A slice (`key_range`) has no start check - the run's process did it; each of its pages asks after the partitions
    it has written so far."""
    asked = []
    monkeypatch.setattr(backfill, "analyze_stale_partitions",
                        lambda engine, world, only=None: asked.append(sorted(only)) or [])
    out, _lines = _run(world, key_range=(None, None))
    assert out["pages"] >= 3
    assert len(asked) == out["pages"], (len(asked), out["pages"])
    assert all(names and all(name.startswith("ledger_events_") for name in names) for names in asked), asked


def test_a_partition_another_session_holds_is_not_waited_for(world, far):
    """Another slice analyzing it (or autovacuum, an index build) holds its SHARE UPDATE EXCLUSIVE lock."""
    import time

    holder = world["engine"].raw_connection()
    try:
        with holder.cursor() as cursor:
            cursor.execute('LOCK TABLE "%s".%s IN SHARE UPDATE EXCLUSIVE MODE' % (S, far))
        lines = []
        control = retroactive.RunControl(None, op="ledger_rescope", log=lines.append)
        token = keyset_scan.RUN_CONTROL.set(control)
        try:
            started = time.monotonic()
            done = backfill.analyze_stale_partitions(world["engine"], None, [far])
            took = time.monotonic() - started
        finally:
            keyset_scan.RUN_CONTROL.reset(token)
    finally:
        holder.rollback()
        holder.close()
    assert done == [] and took < 2, (done, took)
    assert any(" · not analyzed: " in line and far in line for line in lines), lines
    assert far in _stale(world["engine"], share=1e9), "still never analyzed - the next page asks again"


def test_one_analyzed_meanwhile_is_not_analyzed_twice(world, far, monkeypatch):
    """The partition was stale when asked and is not once its lock is held - another slice analyzed it in between."""
    real, calls = schema.stale_partitions, []

    def asked(connection, names, share, only=None):
        calls.append(only)
        return real(connection, names, share, only) if len(calls) == 1 else []
    monkeypatch.setattr(schema, "stale_partitions", asked)
    assert backfill.analyze_stale_partitions(world["engine"], None, [far]) == []
    assert len(calls) == 2 and calls[1] == [far], calls
    monkeypatch.setattr(schema, "stale_partitions", real)
    assert far in _stale(world["engine"], share=1e9), "not analyzed by this one"


def test_one_withdrawal_search_a_page_and_withdraw_is_what_it_took(world, monkeypatch):
    calls = {"count": 0, "delete": 0}
    count, delete = LedgerStore.atoms_for_refs, LedgerStore._withdraw_refs

    def counted(self, *a, **k):
        calls["count"] += 1
        return count(self, *a, **k)

    def deleted(self, *a, **k):
        calls["delete"] += 1
        return delete(self, *a, **k)
    monkeypatch.setattr(LedgerStore, "atoms_for_refs", counted)
    monkeypatch.setattr(LedgerStore, "_withdraw_refs", deleted)
    out = backfill.rescope(world["engine"], world["setup"], hw.SOURCE, None, [], apply=True,
                           page_rows=backfill.RESCOPE_PAGE_ROWS, whole_source=True)
    assert out["pages"] >= 3 and calls == {"count": 0, "delete": out["pages"]}, (out["pages"], calls)
    assert out["withdraw"] == out["withdrawn"] > 0
    preview = backfill.preview_rescope(world["engine"], world["setup"], hw.SOURCE, "dt_job", ["J1"])
    assert calls["count"] == 1 and preview["withdraw"] > 0, (calls, preview)


@pytest.mark.parametrize("value", [0, -1, "0.2", True, None])
def test_a_share_that_is_not_a_number_above_0_reads_the_default(world, monkeypatch, caplog, value):
    import ingestion.settings
    seen = []
    monkeypatch.setattr(ingestion.settings, "read_ingestion_settings",
                        lambda path=None: {backfill.ANALYZE_SHARE_SETTING: value})
    monkeypatch.setattr(schema, "stale_partitions", lambda conn, names, share, only: seen.append(share) or [])
    with caplog.at_level(logging.WARNING, logger="Ledger.Backfill"):
        assert backfill.analyze_stale_partitions(world["engine"], None) == []
    assert seen == [backfill.ANALYZE_SHARE_DEFAULT]
    assert any(backfill.ANALYZE_SHARE_SETTING in r.getMessage() for r in caplog.records)
