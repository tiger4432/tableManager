"""소유자 10-14 «러닝은 뜨는데 토스트 진행 상황이 안 나옴»: a run's progress moved only at a page boundary, so the minute
before its first page read «running» and nothing more. Every beat the run tells its stage (`RunControl.tell`): the run
record's phase · phase_at and the progress notice's phase · phase_seconds · rows_per_second · seconds_left, the pace one
calculation (`retroactive.pace`) the page line and the runs list use too.

  stage    before a page the run's last line («Starting», a `say`) · in a page «Page k: <stage>» · after it the page's
  record   phase and phase_at written; last_progress_at not moved - a stage that does not end still reads stalled
  notice   the same words and the pace, from the same call; none once the run's beat ended (QA 10-14 ④)
  slice    a slice tells nothing - the run's process tells the run's stage
  list     a run in flight carries the four values; a finished one nulls
  pg       the model maps neither column (QA 10-14 ①): on a database without them a run is queued, the list answers
           stageless without adding them (②), and the writer adds them
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from admin import retroactive
from database import models

T = datetime(2026, 10, 14, 1, 0, tzinfo=timezone.utc)


class _Kept:
    """The test's session, not closed by the control that borrows it."""

    def __init__(self, db):
        self._db = db

    def __getattr__(self, name):
        return getattr(self._db, name)

    def close(self):
        pass


@pytest.fixture(autouse=True)
def _columns_asked_again(monkeypatch):
    """The test database's tables are made again for each test on one engine - so is the check's memory of them."""
    import weakref
    monkeypatch.setattr(models, "_PHASE_COLUMNS", weakref.WeakSet())


@pytest.fixture(name="run")
def fixture_run(db_session, monkeypatch):
    db_session.add(models.RetroactiveRun(run_id="told", op="ledger_rescope", params="{}",
                                         state=retroactive.RUN_RUNNING, last_progress_at=T,
                                         started_at=datetime.now(timezone.utc) - timedelta(seconds=10)))
    db_session.commit()
    notices = []
    monkeypatch.setattr(retroactive, "announce_progress", lambda *a, **k: notices.append((a, k)) or True)
    lines = []
    control = retroactive.RunControl("told", session_factory=lambda: _Kept(db_session), op="ledger_rescope",
                                     log=lines.append)
    yield db_session, control, notices


def _stage(db, run_id="told"):
    db.expire_all()
    return db.execute(text("SELECT phase, phase_at, last_progress_at FROM retroactive_runs WHERE run_id = :r"),
                      {"r": run_id}).one()


def test_the_stage_before_in_and_after_a_page_is_written_and_told(run):
    db, control, notices = run
    control.tell()
    phase, phase_at, progressed = _stage(db)
    assert (phase, phase_at is not None) == ("Starting", True)
    assert str(progressed).startswith("2026-10-14 01:00:00"), "the beat does not move the progress time"
    told = notices[-1][1]
    assert told["phase"] == "Starting" and told["phase_seconds"] >= 0
    assert (told["rows_per_second"], told["seconds_left"]) == (None, None), "nothing done - no pace"

    control.say("counting the rows of t")
    control.tell()
    assert _stage(db)[0] == notices[-1][1]["phase"] == "counting the rows of t"

    with control.stage("read"):
        control.tell()
        assert _stage(db)[0] == notices[-1][1]["phase"] == "Page 1: read"

    control._began -= 10                       # a run 10 s in: monotonic steps ~15 ms here, a fast test reads 0 s
    control.progress(40, 100)
    control.tell()
    told = notices[-1][1]
    assert _stage(db)[0] == told["phase"] == "Page 1 done"
    assert told["rows_per_second"] > 0 and told["seconds_left"] is not None and told["seconds_left"] >= 0
    import event_constants
    assert notices[-1][0] == ("told", "ledger_rescope", event_constants.PROGRESS_STATUS_RUNNING)


def test_nothing_is_told_once_the_runs_beat_ended(run):
    """The run's ending notice comes after its beat: a stage told after it would read RUNNING after DONE."""
    db, control, notices = run
    with retroactive._beating(control, db.get_bind()):
        control.tell()
    told = len(notices)
    control.tell()
    assert told == 1 and len(notices) == 1, notices


def test_a_slice_tells_nothing(db_session, monkeypatch):
    notices = []
    monkeypatch.setattr(retroactive, "announce_progress", lambda *a, **k: notices.append(k) or True)
    db_session.add(models.RetroactiveRun(run_id="sliced", op="ledger_rescope", params="{}",
                                         state=retroactive.RUN_RUNNING))
    db_session.commit()
    models.ensure_run_phase_columns(db_session.get_bind())
    slice_control = retroactive.RunControl("sliced", session_factory=lambda: _Kept(db_session), op="ledger_rescope",
                                           log=lambda line: None, report=lambda processed: None)
    slice_control.tell()
    assert _stage(db_session, "sliced")[0] is None
    assert notices == []


def test_the_runs_list_carries_the_stage_and_pace_of_a_run_in_flight(db_session):
    now = datetime.now(timezone.utc)
    common = dict(op="ledger_rescope", params="{}", processed_rows=300, total_rows=1000,
                  started_at=now - timedelta(seconds=30), queued_at=now - timedelta(seconds=40))
    db_session.add(models.RetroactiveRun(run_id="going", state=retroactive.RUN_RUNNING, **common))
    db_session.add(models.RetroactiveRun(run_id="ended", state="done", finished_at=now, **common))
    db_session.commit()
    models.ensure_run_phase_columns(db_session.get_bind())
    db_session.execute(text("UPDATE retroactive_runs SET phase = 'Page 3: insert atoms', phase_at = :at"),
                       {"at": now - timedelta(seconds=7)})
    db_session.commit()
    listed = {run["run_id"]: run for run in retroactive.runs(db_session)}
    going, ended = listed["going"], listed["ended"]
    assert going["phase"] == "Page 3: insert atoms" and 6 <= going["phase_seconds"] <= 9
    assert 9 <= going["rows_per_second"] <= 10.1 and 69 <= going["seconds_left"] <= 78
    assert [ended[key] for key in ("phase", "phase_seconds", "rows_per_second", "seconds_left")] == [None] * 4


@pytest.mark.parametrize("processed, total, seconds, expected", [
    (0, 10, 5, (None, None)), (5, None, 5, (1.0, None)), (5, 10, 5, (1.0, 5.0)), (5, 10, 0, (None, None)),
    (12, 10, 4, (3.0, 0.0)),
])
def test_the_pace(processed, total, seconds, expected):
    assert retroactive.pace(processed, total, seconds) == expected


@pytest.mark.pg
def test_a_database_without_the_two_columns_queues_runs_and_lists_them_until_the_writer_adds_them(
        pg_engine, monkeypatch):
    from conftest import PG_TEST_SCHEMA as S

    def columns():
        with pg_engine.connect() as conn:
            return sorted(conn.execute(text(
                "SELECT attname FROM pg_attribute WHERE attrelid = to_regclass(:t) AND attname IN "
                "('phase', 'phase_at') AND NOT attisdropped"), {"t": '"%s".retroactive_runs' % S}).scalars())

    with pg_engine.begin() as conn:
        assert conn.execute(text("SELECT current_schema()")).scalar() == S
        assert conn.execute(text("SELECT to_regclass(:t)"), {"t": '"%s".retroactive_runs' % S}).scalar()
        conn.execute(text('ALTER TABLE "%s".retroactive_runs DROP COLUMN IF EXISTS phase, '
                          'DROP COLUMN IF EXISTS phase_at' % S))
    import weakref
    monkeypatch.setattr(models, "_PHASE_COLUMNS", weakref.WeakSet())
    monkeypatch.setattr(retroactive, "validate", lambda op, params: params)
    session = sessionmaker(bind=pg_engine)()
    try:
        queued = retroactive.publish(session, "ledger_rescope", {"source": "s", "whole_source": True})
        run_id = queued["run_id"]
        session.query(models.RetroactiveRun).filter_by(run_id=run_id).update({"state": retroactive.RUN_RUNNING})
        session.commit()
        listed = {run["run_id"]: run for run in retroactive.runs(session)}
        assert listed[run_id]["phase"] is None and columns() == [], "the list adds nothing and answers stageless"
        session.rollback()              # a list request's session ends with it - the ALTER waits on an open one

        control = retroactive.RunControl(run_id, session_factory=sessionmaker(bind=pg_engine), op="ledger_rescope",
                                         log=lambda line: None)
        monkeypatch.setattr(retroactive, "announce_progress", lambda *a, **k: True)
        control.tell()
        assert columns() == ["phase", "phase_at"], "the writer adds them"
        assert {run["run_id"]: run for run in retroactive.runs(session)}[run_id]["phase"] == "Starting"
    finally:
        session.rollback()
        with pg_engine.begin() as conn:
            conn.execute(text('DELETE FROM "%s".retroactive_runs WHERE requested_by IS NULL AND op = :op AND '
                              "params LIKE :p" % S), {"op": "ledger_rescope", "p": '%"source": "s"%'})
            conn.execute(text('DELETE FROM "%s".database_outbox WHERE payload::text LIKE :p' % S),
                         {"p": '%"source": "s"%'})
        session.close()
