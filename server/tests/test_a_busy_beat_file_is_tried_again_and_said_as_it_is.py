# -*- coding: utf-8 -*-
"""A beat file busy on Windows (lead 10-28 ㄷ): a reader's open and a writer's replace of the same file refuse each other
there (PermissionError) - C's big3 run served one 503 «worker 'scheduler' has made no progress for Nones» 5 s after the
API stood. Both sides wait once through `heartbeat._when_free`; a beat still unreadable is said as it is, and inside
the startup grace it is a worker starting.

    seat                      gate
    heartbeat._write          a busy replace is tried once more - the beat is written
    heartbeat.read_all        a busy open is tried once more - the beat is read
    health, worker            unreadable past the grace: 503 with the error; inside it: starting, 200
    health, chain slot        unreadable: the error, not «Nones»
"""
import json
import os

import pytest

from runtime.health import STATUS_DEGRADED, STATUS_UNHEALTHY
from tests.test_health_endpoint import fresh, run, running, supervisor_status
from utils import heartbeat

ERROR = "unreadable heartbeat: PermissionError: [Errno 13] Permission denied: 'scheduler.json'"


@pytest.fixture(name="beats")
def fixture_beats(tmp_path, monkeypatch):
    monkeypatch.setattr(heartbeat, "heartbeat_dir", lambda: str(tmp_path))
    monkeypatch.setattr(heartbeat, "heartbeat_path", lambda name: str(tmp_path / (name + ".json")))
    monkeypatch.setattr(heartbeat, "BUSY_WAIT_SECONDS", 0)
    return tmp_path


def _busy(monkeypatch, module, name, times):
    real, left = getattr(module, name), [times]

    def busy(*args, **kwargs):
        if left[0]:
            left[0] -= 1
            raise PermissionError(13, "Permission denied")
        return real(*args, **kwargs)

    monkeypatch.setattr(module, name, busy)


def test_a_busy_replace_is_tried_once_more_and_the_beat_is_written(beats, monkeypatch):
    _busy(monkeypatch, os, "replace", 1)
    assert heartbeat._write("scheduler", {"pid": 1, "ts": 1.0}) is True
    assert json.loads((beats / "scheduler.json").read_text())["pid"] == 1


def test_a_busy_open_is_tried_once_more_and_the_beat_is_read(beats, monkeypatch):
    (beats / "scheduler.json").write_text(json.dumps({"pid": 7, "ts": 1.0}))
    _busy(monkeypatch, heartbeat, "_load", 1)
    assert heartbeat.read_all()["scheduler"]["pid"] == 7


def test_twice_busy_is_unreadable_and_the_error_says_so(beats, monkeypatch):
    (beats / "scheduler.json").write_text(json.dumps({"pid": 7, "ts": 1.0}))
    _busy(monkeypatch, heartbeat, "_load", 2)
    said = heartbeat.read_all()["scheduler"]
    assert said["stale"] is True and said["error"].startswith("unreadable heartbeat: PermissionError")


def _unreadable():
    return {"pid": None, "beats": None, "age_seconds": None, "stale": True, "stale_after_seconds": 60.0,
            "error": ERROR}


def test_an_unreadable_beat_past_the_grace_is_said_with_its_error():
    payload, code = run(hbs={"scheduler": _unreadable()},
                        sup=supervisor_status({"Scheduler": running("scheduler", uptime=3600.0)}))
    assert code == 503 and payload["status"] == STATUS_UNHEALTHY
    assert payload["problems"] == ["worker 'scheduler': " + ERROR]


def test_an_unreadable_beat_inside_the_grace_is_a_worker_starting():
    payload, code = run(hbs={"scheduler": _unreadable()},
                        sup=supervisor_status({"Scheduler": running("scheduler", uptime=5.0)}))
    assert code == 200 and payload["status"] == STATUS_DEGRADED and payload["problems"] == []
    assert payload["checks"]["workers"]["scheduler"]["status"] == "starting"


def test_an_unreadable_slot_beat_is_said_with_its_error():
    from chain.slots import BEAT_PREFIX

    payload, _code = run(hbs={BEAT_PREFIX + "1": _unreadable(), "scheduler": fresh()},
                         sup=supervisor_status({"Scheduler": running("scheduler")}))
    assert "chain slot '%s1': %s" % (BEAT_PREFIX, ERROR) in payload["problems"]
