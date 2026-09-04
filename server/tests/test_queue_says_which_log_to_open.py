# -*- coding: utf-8 -*-
""""Which log file do I open" has to be answerable from the response.

The mapper lines carry `[mapper@<file>]`, but that tag is only visible to somebody who
already opened the right file - it cannot help you choose one. Two lanes measured the
same gap independently: nothing in the admin surface names a log file, and hardcoding
one would be false twice over, because the data root can move the path and because which
file is written depends on whether the chain loop shares the web server's process.

The second half of that is already published (`loop_in_this_process`). This is the
first: the name of the file this process actually writes.

⛔ READ FROM THE LOGGER, NEVER A CONSTANT. A constant was exactly how the mapper tag
came to say `chain_worker.log` on lines sitting in `server.log`.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main                                                      # noqa: E402
from utils import logger as process_logging                      # noqa: E402


def test_the_queue_says_which_file_this_process_writes(db_session):
    out = main.get_chain_queue_depth(db=db_session)
    assert "log_filename" in out, "the response does not name a log file at all"
    assert out["log_filename"] == process_logging.active_log_filename()


def test_it_is_a_name_and_not_a_path(db_session):
    """The server's disk layout is not something to put on a screen, and the path moves
    with the data root anyway."""
    out = main.get_chain_queue_depth(db=db_session)
    name = out["log_filename"]
    if name is None:
        pytest.skip("no process logger configured in this run")
    assert os.sep not in name and "/" not in name, f"a path leaked out: {name!r}"
    assert name.endswith(".log")


def test_an_unconfigured_process_answers_null_rather_than_a_guess(db_session, monkeypatch):
    """🔴 «모를 때의 기본값» IS THE DEFECT. A screen can draw "unknown"; it cannot draw
    "this value is a guess"."""
    monkeypatch.setattr(process_logging, "active_log_filename", lambda: None)
    out = main.get_chain_queue_depth(db=db_session)
    assert out["log_filename"] is None


def test_it_follows_the_logger_rather_than_a_constant(db_session, monkeypatch):
    """The field must move when the process's log file moves - that is the whole reason
    it is read rather than written down."""
    monkeypatch.setattr(process_logging, "active_log_filename", lambda: "somewhere_else.log")
    out = main.get_chain_queue_depth(db=db_session)
    assert out["log_filename"] == "somewhere_else.log"
