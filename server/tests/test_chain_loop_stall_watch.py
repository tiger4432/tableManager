# -*- coding: utf-8 -*-
"""The chain loop must say when it keeps picking work up and putting nothing down.

Owner's observation 2026-09-04, in production: 570 rows waiting, the oldest nine minutes
old, NO error anywhere, and "it does not clear until a restart". From outside, a loop that
drains nothing looks exactly like a busy one - the only observable difference is that the
head of the queue never moves.

🔴 THIS ROUND DOES NOT PICK A CULPRIT. Two candidates remain (a failed group holding its
target, and importlib caching a broken mapper module for the life of the process) and
fixing one now would clear the symptom without anyone learning which it was. The whole day
has been the same lesson: the defect was never "it got stuck", it was "nothing said so".

⛔ AND A HEALTHY LOOP MUST STAY SILENT. An instrument that talks during normal operation
gets filtered out, and a filtered instrument is not one.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import chain_ingestion_worker as worker                          # noqa: E402

STALL = 60.0


def watch(t0=1000.0):
    return worker.QueueHeadWatch(stall_after=STALL, now=t0)


# ------------------------------------------------------------------ stays quiet

def test_an_empty_queue_is_not_a_stall():
    """Nothing to drain is not failing to drain, however long it lasts."""
    w = watch()
    for i in range(20):
        assert w.observe(0, None, now=1000.0 + i * STALL) is None


def test_a_draining_queue_is_quiet_however_slow():
    """The head advancing IS progress. A big backlog moving one row at a time is a busy
    system, not a stuck one."""
    w = watch()
    for i in range(20):
        assert w.observe(200, head_id=i, now=1000.0 + i * STALL * 2) is None


def test_it_says_nothing_before_the_threshold():
    w = watch()
    assert w.observe(570, head_id=7, now=1000.0) is None
    assert w.observe(570, head_id=7, now=1000.0 + STALL - 1) is None


# --------------------------------------------------------------- speaks up once

def test_a_head_that_never_moves_is_reported_with_the_numbers_that_matter():
    """🔴 THE SIGNATURE. Fetched again, same first row, no error. The line has to carry
    the row, how long, how many, and the two ages that make "a restart clears it" a
    measurement rather than a feeling."""
    w = watch()
    w.note_reload(now=1000.0)
    assert w.observe(570, head_id=7, now=1000.0) is None
    said = w.observe(570, head_id=7, now=1000.0 + STALL + 1)
    assert said, "the stall was never reported"
    assert "outbox#7" in said and "570" in said, said
    assert "Uptime" in said and "reload" in said, said


def test_it_does_not_repeat_itself_every_iteration():
    """⛔ Once per threshold, not once per loop. A stuck queue is fetched several times a
    second; a line per fetch would bury the first one."""
    w = watch()
    w.observe(570, head_id=7, now=1000.0)
    assert w.observe(570, head_id=7, now=1000.0 + STALL + 1)
    for i in range(1, 30):
        assert w.observe(570, head_id=7, now=1000.0 + STALL + 1 + i) is None
    assert w.observe(570, head_id=7, now=1000.0 + 2 * STALL + 2)


def test_progress_after_a_stall_clears_the_alarm():
    """It has to be able to stop saying it, or the operator cannot tell recovery from
    the same message repeating."""
    w = watch()
    w.observe(570, head_id=7, now=1000.0)
    assert w.observe(570, head_id=7, now=1000.0 + STALL + 1)
    # The head moved: the clock restarts from HERE, so the next fetch is quiet again and
    # stays quiet for a full threshold - which is what "the alarm cleared" means.
    assert w.observe(569, head_id=8, now=1000.0 + STALL + 2) is None
    assert w.observe(569, head_id=8, now=1000.0 + 2 * STALL + 1) is None
    # ...and if the NEW head then stops moving for a threshold, it is reported on its own
    # merits rather than as a continuation of the first.
    assert w.observe(569, head_id=8, now=1000.0 + 2 * STALL + 3)


def test_the_threshold_is_the_one_this_system_already_uses():
    """⚠️ Not a new number: `heartbeat.DEFAULT_STALE_AFTER_SEC` is what this codebase
    already means by "a worker that is not progressing"."""
    from utils import heartbeat
    assert worker.QueueHeadWatch().stall_after == heartbeat.DEFAULT_STALE_AFTER_SEC
