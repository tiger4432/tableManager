"""A re-translate run says each stage of a page and, every few seconds, what it waits on (총괄 d9be013cb, 소유자
「재번역 디버그 로그 다띄워 실시간으로 뭐가돌고 뭘 기다리는지」) - through the run's own door (`retroactive.execute`, the
Re-translate button's op) on the hold world's ledger source.

  stages   each stage of a page ends in a line: the read (its page key's index, its plan), the translation's three, the
           withdrawal count (which index finds the atoms, its plan), the write's six
  off      `retroactive_debug: false` leaves the page lines and only them
  wait     a lock held on the ledger is named by the beat - the holder's pid and name - and the blocked statement by
           the slow-statement line
  quiet    a beat that breaks says so once and the run goes to its end
  answer   the atoms the run writes are the same with the lines on and off
"""
import re
import threading
import time

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from admin import retroactive
from support import hold_world as hw
from support.isolated_pg import scratch_connect_args
from conftest import PG_TEST_SCHEMA

pytestmark = pytest.mark.pg
ROWS = 30
STAGES = ("read", "event frames", "dry run", "row refs", "translate", "withdrawal count", "index lines of the rows",
          "screen atoms", "partitions", "withdraw atoms", "insert atoms", "index lines", "commit", "write")


@pytest.fixture(name="world")
def fixture_world(pg_engine, monkeypatch, tmp_path):
    for w in hw.build(pg_engine, monkeypatch, tmp_path, batch=True):
        hw.push(w, [{"log_id": "L%03d" % i, "dt_job": "J%d" % (i % 3), "dt_x": i, "dt_y": 1, "netdie": i}
                    for i in range(ROWS)])
        hw.settle(w)
        import database.database as database
        monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=pg_engine))
        monkeypatch.setattr(retroactive, "_ledger_setup", lambda params: w["setup"])
        yield w


def _settings(monkeypatch, **cells):
    import ingestion.settings
    monkeypatch.setattr(ingestion.settings, "read_ingestion_settings", lambda path=None: dict(cells))


def _retranslate():
    lines = []
    out = retroactive.execute({"op": "ledger_rescope", "run_id": "?",
                               "params": {"source": hw.SOURCE, "whole_source": True}}, log=lines.append)
    assert out["status"] == "ok", out
    return out, lines


def _stage_lines(lines):
    """{stage name: [its lines]} - `[ledger_rescope] page k: <stage> · <rows> rows · <s> s[ · note]`."""
    said = {}
    for line in lines:
        m = re.match(r"\[ledger_rescope\] page \d+: ([a-z][a-z ]*?) · ", line)
        if m:
            said.setdefault(m.group(1), []).append(line)
    return said


def _atoms(world):
    with world["engine"].connect() as conn:
        return sorted(tuple(map(str, r)) for r in conn.execute(text(
            "SELECT subject_type, subject_keys::text, predicate, object_kind, object_payload::text, occurred_at, "
            "source_who, source_translator_ver, source_raw_ref, source_event_id, occurred_at_basis "
            "FROM ledger_events WHERE source_who = :s"), {"s": hw.SOURCE}))


def test_each_stage_of_a_page_says_itself(world, monkeypatch):
    _settings(monkeypatch, retroactive_debug=True)
    out, lines = _retranslate()
    assert out["result"]["rows_in_scope"] == ROWS
    said = _stage_lines(lines)
    assert set(STAGES) <= set(said), sorted(set(STAGES) - set(said))
    # the read names its page key, the index that serves it, and its plan
    assert any(re.search(r" · key row_id · \S+ · plan: \S", line) for line in said["read"]), said["read"][:3]
    # the withdrawal count names what finds the atoms - the ref index by name, valid or not - and its plan
    assert any("by idx_ledger_events_source_raw_ref_hash" in line and " · plan: " in line
               for line in said["withdrawal count"]), said["withdrawal count"][:3]
    # the page lines are still there
    assert any(re.match(r"\[ledger_rescope\] page \d+: \d+ rows · ", line) for line in lines), lines[:5]


def test_off_leaves_the_page_lines_and_only_them(world, monkeypatch):
    _settings(monkeypatch, retroactive_debug=False)
    out, lines = _retranslate()
    assert out["result"]["rows_in_scope"] == ROWS
    assert _stage_lines(lines) == {}
    assert any(re.match(r"\[ledger_rescope\] page \d+: \d+ rows · ", line) for line in lines), lines[:5]


def test_the_two_defects_are_said_once_with_the_lines_off(world, monkeypatch):
    """The ledger's ref index gone, and a page key with no index (hc_official pages on its primary key, so the
    page-key judgment is made to answer none): one line each at the run's start, with retroactive_debug off."""
    from database import models
    from ledger import backfill, schema
    _settings(monkeypatch, retroactive_debug=False)
    with world["engine"].connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text("DROP INDEX %s" % schema.REF_INDEX))
    monkeypatch.setattr(backfill, "_page_key_index", lambda connection, plan: None)
    try:
        out, lines = _retranslate()
    finally:
        models.ensure_model_indexes(world["engine"], say=lambda *_a: None)
    assert out["result"]["rows_in_scope"] == ROWS
    ref = [line for line in lines if line.startswith(
        "[ledger_rescope] idx_ledger_events_source_raw_ref_hash missing or not valid - each page's withdrawal count "
        "and DELETE read the whole ledger")]
    key = [line for line in lines if line.startswith(
        "[ledger_rescope] page key row_id of hc_official has no index - each page sorts the table")]
    assert (len(ref), len(key)) == (1, 1), [line for line in lines if "index" in line][:6]
    assert _stage_lines(lines) == {}


def test_a_held_lock_is_named_by_the_beat(world, monkeypatch, pg_engine):
    _settings(monkeypatch, retroactive_debug=True, retroactive_slow_statement_seconds=0.5)
    monkeypatch.setattr(retroactive, "BEAT_SECONDS", 0.5)
    monkeypatch.setattr(retroactive, "LOOK_SECONDS", 0.2)
    import psycopg2
    dsn = pg_engine.url.render_as_string(hide_password=False).replace("postgresql+psycopg2", "postgresql")
    holder = psycopg2.connect(dsn, application_name="b_lock_holder", **scratch_connect_args(PG_TEST_SCHEMA))
    try:
        with holder.cursor() as cur:
            cur.execute("SELECT current_schema()")
            assert cur.fetchone()[0] == PG_TEST_SCHEMA
            cur.execute("LOCK TABLE ledger_events IN ACCESS EXCLUSIVE MODE")
        release = threading.Timer(3.0, holder.rollback)
        release.start()
        started = time.monotonic()
        out, lines = _retranslate()
        release.join()
    finally:
        holder.close()
    assert time.monotonic() - started >= 2.5                          # canary: the run did wait on the lock
    assert out["result"]["rows_in_scope"] == ROWS
    beats = [line for line in lines if line.startswith("[ledger_rescope] beat: page ")]
    assert any(re.search(r"waiting Lock:relation on pid \d+ \(b_lock_holder, idle in transaction", line)
               for line in beats), beats[:6]
    assert any(re.match(r"\[ledger_rescope\] slow statement: pid \d+ running [\d.]+ s \(Lock:relation\): \S", line)
               for line in lines), [line for line in lines if "slow" in line][:4]
    assert any(re.match(r"\[ledger_rescope\] slow statement ended: pid \d+ after about [\d.]+ s", line)
               for line in lines)


def test_a_beat_that_breaks_leaves_the_run_to_its_end(world, monkeypatch):
    _settings(monkeypatch, retroactive_debug=True)
    monkeypatch.setattr(retroactive, "LOOK_SECONDS", 0.01)
    import db_waits

    def broke(*_args, **_kwargs):
        raise RuntimeError("probe broke")
    monkeypatch.setattr(db_waits, "backend_waits", broke)
    out, lines = _retranslate()
    assert out["result"]["rows_in_scope"] == ROWS
    stopped = [line for line in lines if line.startswith("[ledger_rescope] beat stopped - RuntimeError: probe broke")]
    assert len(stopped) == 1, [line for line in lines if "beat" in line][:4]
    assert "commit" in _stage_lines(lines)                            # the stage lines went on after it


def test_the_answer_is_the_same_with_the_lines_on_and_off(world, monkeypatch):
    before = _atoms(world)
    assert before                                                     # canary: the settled world has atoms
    _settings(monkeypatch, retroactive_debug=True)
    _retranslate()
    on = _atoms(world)
    _settings(monkeypatch, retroactive_debug=False)
    _retranslate()
    assert on == _atoms(world) == before
