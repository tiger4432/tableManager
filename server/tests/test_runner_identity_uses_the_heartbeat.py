# -*- coding: utf-8 -*-
"""Asking "is the owner alive" by host/pid could not answer for another machine.

`runner` was `host/pid`, so `_runner_state` compared hostnames and gave up whenever they
differed - every run stamped elsewhere was "unknown" forever. The fix is not to handle
unknown better; it is to stop producing it, by asking the mechanism that already answers
this question without caring which machine it is on: the heartbeat.

⚠️ AND IT ANSWERS ONLY ONE QUESTION. The heartbeat says whether the PROCESS is alive, not
whether the RUN is progressing. Folding the two together would reap a run that is merely
blocked - which `gate_blocked` already reports separately.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import retroactive                                               # noqa: E402
from utils import heartbeat                                      # noqa: E402


def beats(monkeypatch, name, pid, stale=False):
    monkeypatch.setattr(heartbeat, "read_all",
                        lambda **k: {name: {"pid": pid, "stale": stale}})


def test_the_identity_carries_the_heartbeat_name(monkeypatch):
    monkeypatch.setattr(heartbeat, "own_name", lambda: "scheduler")
    got = retroactive.runner_identity()
    assert got.startswith("scheduler/")
    assert got.endswith("/%d" % os.getpid())
    assert len(got.split("/")) == 3


def test_a_process_that_has_not_beaten_stamps_unknown_not_a_guess(monkeypatch):
    monkeypatch.setattr(heartbeat, "own_name", lambda: None)
    assert retroactive.runner_identity().startswith("?/")


def test_the_host_stopped_mattering(monkeypatch):
    """🔴 THE POINT. Same name, same pid, a hostname this process has never heard of -
    and it is still answerable."""
    beats(monkeypatch, "scheduler", os.getpid())
    assert retroactive._runner_state("scheduler/some-other-box/%d" % os.getpid()) == "owned"


def test_a_fresh_beat_with_a_different_pid_is_orphaned(monkeypatch):
    """The kind of process is alive; the one that started this run is not."""
    beats(monkeypatch, "scheduler", 4242)
    assert retroactive._runner_state("scheduler/h/999999") == "orphaned"


def test_a_stale_beat_is_orphaned(monkeypatch):
    beats(monkeypatch, "scheduler", 4242, stale=True)
    assert retroactive._runner_state("scheduler/h/4242") == "orphaned"


def test_no_heartbeat_of_that_name_is_orphaned(monkeypatch):
    beats(monkeypatch, "watcher", 4242)
    assert retroactive._runner_state("scheduler/h/4242") == "orphaned"


def test_rows_predating_the_stamp_stay_unknown(monkeypatch):
    """⚠️ UNKNOWN IS NOT ORPHANED. A row written before the name existed must not be
    reaped on the strength of a shape it never had."""
    beats(monkeypatch, "scheduler", os.getpid())
    for old in ("host/1234", "?/host/1234", "", None):
        assert retroactive._runner_state(old) == "unknown"


def test_an_unreadable_heartbeat_is_unknown_rather_than_dead(monkeypatch):
    def boom(**k):
        raise OSError("no heartbeat dir")
    monkeypatch.setattr(heartbeat, "read_all", boom)
    assert retroactive._runner_state("scheduler/h/1") == "unknown"
