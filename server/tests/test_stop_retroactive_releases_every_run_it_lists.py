"""stop_retroactive.bat (owner 10-11 「강종 단축 스크립트 하나 배치 파일로」): every run it lists leaves the
queue - a dead runner's row through the screen's own cancel, a row nobody can judge by the hand release, a
queued one cancelled - and a «no» stops nothing."""
import socket

import pytest

from admin import retroactive
from database import models
from scripts import stop_retroactive
from tests.test_retroactive_admin import retro_env  # noqa: F401  - its session and tables


@pytest.fixture
def no_taskkill(monkeypatch):
    killed = []
    monkeypatch.setattr(stop_retroactive.subprocess, "run",
                        lambda args, **_kw: killed.append(args) or type("Done", (), {
                            "stdout": "", "stderr": "", "returncode": 128})())
    return killed


def _runs(db, **runs):
    for run_id, (state, runner) in runs.items():
        db.add(models.RetroactiveRun(run_id=run_id, op="fold_written_notation", state=state, runner=runner))
    db.commit()


def _states(db):
    db.expire_all()
    return {row.run_id: (row.state, row.error) for row in db.query(models.RetroactiveRun)}


def test_every_listed_run_leaves_the_queue(retro_env, no_taskkill):
    here = socket.gethostname()
    _runs(retro_env,
          dead=(retroactive.RUN_RUNNING, "%s/%s/999999" % (retroactive.RUN_HERE_HEARTBEAT, here)),
          unstamped=(retroactive.RUN_CANCEL_REQUESTED, None),
          waiting=(retroactive.RUN_QUEUED, None),
          over=(retroactive.RUN_DONE, None))

    assert stop_retroactive.main(["--yes"], say=lambda *_: None) == 0

    states = _states(retro_env)
    assert states["dead"][0] == retroactive.RUN_FAILED and "ghost lock" in states["dead"][1]
    assert states["unstamped"] == (retroactive.RUN_FAILED, stop_retroactive.HAND_RELEASE)
    assert states["waiting"][0] == retroactive.RUN_CANCELLED
    assert states["over"] == (retroactive.RUN_DONE, None)
    assert no_taskkill == [["taskkill", "/F", "/T", "/PID", "999999"]], "only this host's run process"


def test_a_no_stops_nothing_and_a_run_id_narrows(retro_env, no_taskkill):
    _runs(retro_env, one=(retroactive.RUN_CANCEL_REQUESTED, None), two=(retroactive.RUN_CANCEL_REQUESTED, None))

    assert stop_retroactive.main([], ask=lambda _q: "n", say=lambda *_: None) == 1
    assert {s for s, _e in _states(retro_env).values()} == {retroactive.RUN_CANCEL_REQUESTED}

    stop_retroactive.main(["two", "--yes"], say=lambda *_: None)
    states = _states(retro_env)
    assert (states["one"][0], states["two"][0]) == (retroactive.RUN_CANCEL_REQUESTED, retroactive.RUN_FAILED)
    assert no_taskkill == []
