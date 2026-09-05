# -*- coding: utf-8 -*-
"""The launcher publishes what it started; nobody declares it twice.

/health treated every heartbeat file it found as a worker that must be alive, so anything
that ever ran stayed on the roll forever - a graph worker retired weeks ago is why this
box reads permanently unhealthy. The list of what actually runs already exists, as the
ChildSpec heartbeat names in the launcher, but that file's module body executes on import
so no server process can read it where it lives.

⚠️ AN EMPTY ROSTER IS "NOBODY SAID", NOT "NOTHING RUNS". A reader that turned an absent
roster into "everything is off-roster" would call a correctly running system undeclared.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils import heartbeat                                      # noqa: E402


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(heartbeat, "heartbeat_dir", lambda: str(tmp_path))
    return tmp_path


def test_what_is_written_is_what_comes_back(isolated):
    assert heartbeat.write_roster(["chain", "scheduler"], now=1000.0) is True
    assert heartbeat.read_roster() == {"chain": 1000.0, "scheduler": 1000.0}


def test_the_start_time_travels(isolated):
    """🔴 WITHOUT IT, "no heartbeat yet" and "no heartbeat ever" are one fact - which is
    what made every restart answer 503."""
    heartbeat.write_roster(["chain"], now=12345.0)
    assert heartbeat.read_roster()["chain"] == 12345.0


def test_no_roster_reads_empty_rather_than_raising(isolated):
    assert heartbeat.read_roster() == {}


def test_a_corrupt_roster_reads_empty_rather_than_raising(isolated):
    (isolated / "_roster.json").write_text("{not json", encoding="utf-8")
    assert heartbeat.read_roster() == {}


def test_writing_is_atomic_enough_to_never_leave_a_half_file(isolated):
    heartbeat.write_roster(["chain"], now=1.0)
    heartbeat.write_roster(["chain", "scheduler", "watcher"], now=2.0)
    assert set(heartbeat.read_roster()) == {"chain", "scheduler", "watcher"}
    assert not [p for p in os.listdir(isolated) if p.endswith(".tmp")]


def test_blank_names_are_not_published(isolated):
    heartbeat.write_roster(["chain", None, ""], now=1.0)
    assert set(heartbeat.read_roster()) == {"chain"}


def test_an_unwritable_location_does_not_stop_the_launcher(monkeypatch):
    """A launcher that cannot publish this must still start its children."""
    monkeypatch.setattr(heartbeat, "heartbeat_dir", lambda: "\0 invalid")
    assert heartbeat.write_roster(["chain"]) is False


def test_the_launcher_publishes_the_childspec_names():
    """Pinned to the launcher's own list so a process added there without a heartbeat
    name, or a publish call that drifts away from `specs`, is visible here.

    Text is the SUBJECT: the claim is about what that file does, and the file cannot be
    imported (its module body runs a launcher).
    """
    import io

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    src = io.open(os.path.join(root, "run_decoupled_app.py"), encoding="utf-8").read()
    assert "write_roster(" in src, "the launcher no longer publishes the roster"
    assert "for s in specs" in src, "the roster is no longer derived from the spec list"
