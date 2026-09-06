# -*- coding: utf-8 -*-
"""The startup said the chain worker was spawned, and the task was already dead.

`main_loop.create_task(...)` succeeds even when the coroutine dies at its first await, so
`startup_event` logged "Chained Ingestion Worker background task spawned." and that
sentence was FALSE whenever `load_chain_rules` refused -- which it does BY DESIGN when the
cascade graph has a cycle (`docs/architecture/event_driven_backend.md` §3.4 ②).

Nothing awaited the task and nothing observed it, so the reason left only as asyncio's
"Task exception was never retrieved", at garbage-collection time, through asyncio's handler
rather than this app's logger. Measured 2026-09-06: `add_done_callback` appeared zero times
in `main.py` and `chain_ingestion_worker.py`. What an operator was left with was a worker
with no heartbeat and no `why` -- the standalone worker logs the reason, uvicorn did not.

⛔ THE CALLBACK DOES NOT RESTART, RECOVER OR NOTIFY. Restarting would put a retry loop
behind a refusal the loader raises on purpose. This makes the sentence true; that is all.
"""
import asyncio
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main                                                      # noqa: E402

CYCLE = ("allow_chain_trigger cycle: "
         "wafer_map_metadata -> dt_inventory -> wafer_map_metadata")


def run_and_capture(coro, caplog):
    """Drive the coroutine exactly as startup does: create_task + the callback, no await."""
    async def driver():
        task = asyncio.get_running_loop().create_task(coro)
        task.add_done_callback(main._log_chain_worker_exit)
        await asyncio.sleep(0)          # let it run and let the callback fire
        await asyncio.sleep(0)
        return task

    with caplog.at_level(logging.WARNING):
        asyncio.run(driver())
    return "\n".join(r.getMessage() for r in caplog.records)


def test_the_refusal_reaches_this_apps_logger(caplog):
    """🔴 THE GATE. The loader's own refusal sentence has to be readable in the log the
    operator is already looking at."""
    async def refuses():
        raise ValueError(CYCLE)

    said = run_and_capture(refuses(), caplog)
    assert CYCLE in said, "the reason still does not reach this logger"
    assert "ValueError" in said


def test_the_line_that_lied_is_named_so_the_two_can_be_read_together(caplog):
    """⚠️ NOT JUST THE REASON. "spawned" is still printed a moment earlier and is still
    there in the log; the callback has to say that line is about a task that is gone, or a
    reader takes the earlier line at face value."""
    async def refuses():
        raise ValueError(CYCLE)

    said = run_and_capture(refuses(), caplog)
    assert "spawned" in said, "the correction no longer refers to the sentence it corrects"


def test_a_clean_stop_is_reported_too(caplog):
    """The loop is supposed to run forever, so returning is also news."""
    async def returns():
        return None

    said = run_and_capture(returns(), caplog)
    assert "stopped without an error" in said


def test_an_ordinary_cancellation_says_nothing(caplog):
    """⛔ SHUTDOWN IS NOT A DEATH. A line here on every shutdown would train an operator to
    ignore the one line this exists to make them read."""
    async def sleeps():
        await asyncio.sleep(3600)

    async def driver():
        task = asyncio.get_running_loop().create_task(sleeps())
        task.add_done_callback(main._log_chain_worker_exit)
        await asyncio.sleep(0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    with caplog.at_level(logging.WARNING):
        asyncio.run(driver())
    assert not [r for r in caplog.records if "Chained Ingestion Worker" in r.getMessage()]


def test_the_callback_does_not_restart_recover_or_notify():
    """⛔ THE SCOPE, PINNED. The approval was for removing a lie, not for a supervisor."""
    import ast
    import inspect

    # 🔴 THE CODE, NOT THE PROSE. The docstring NAMES `create_task` to explain what went
    # wrong; scoring the raw source would fail on the explanation instead of on the
    # behaviour, which is the assertion answering a different question than it asks.
    tree = ast.parse(inspect.getsource(main._log_chain_worker_exit).lstrip())
    function = tree.body[0]
    if (function.body and isinstance(function.body[0], ast.Expr)
            and isinstance(function.body[0].value, ast.Constant)):
        function.body = function.body[1:]          # drop the docstring
    body = ast.unparse(function)

    for banned in ("create_task", "restart", "start_chain_ingestion_worker",
                   "post_event", "record_undelivered"):
        assert banned not in body, "the callback grew a %s" % banned


def test_the_startup_attaches_it(caplog):
    """A callback nothing attaches is the same silence with more code."""
    import inspect

    body = inspect.getsource(main.startup_event)
    assert "add_done_callback(_log_chain_worker_exit)" in body


def test_the_startup_except_no_longer_blames_the_watcher():
    """The try covers the watcher AND the chain worker, and the message named only the
    watcher -- so a chain-side failure was reported as the watcher's. A sentence that
    misdirects is worse than a vague one."""
    import inspect

    body = inspect.getsource(main.startup_event)
    assert "Failed to start Directory Watcher" not in body
    assert "watcher/chain worker" in body
