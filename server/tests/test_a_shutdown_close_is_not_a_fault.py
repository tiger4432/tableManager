# -*- coding: utf-8 -*-
"""소유자 2026-09-23 「서버 종료시 아웃박스 리스너 얼레디 클로즈 에러라는데」 (운영).

🔴 WHERE IT CAME FROM, MEASURED. The close itself was never unguarded - `_reset_connection`
already wraps `conn.close()` and nulls the handle first, so a second close is a no-op. What
raised was the READER: `wait()` offloads a blocking `select` to a thread, shutdown closed the
connection under it, and the wait's own `except` logged that as an ERROR and then called
`_ensure_connection()` again - REBUILDING the LISTEN connection the shutdown had just closed,
which is the leak S-167 put that close there to prevent.

So two things, and they are one knot: the reader is stopped before its connection is taken
away, and the listener knows a close was deliberate so it can say so instead of erroring.
"""
import asyncio
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from outbox_listener import OutboxListener                         # noqa: E402


class _Raises:
    """A connection that has gone away, the way a closed one has."""

    def poll(self):
        raise RuntimeError("connection already closed")

    def close(self):
        pass


def _listener():
    return OutboxListener(lambda: (_ for _ in ()).throw(
        AssertionError("the factory was asked for a session - something reconnected")))


def test_a_wait_after_close_does_not_build_another_connection():
    """⛔ NOT A RECONNECT POINT. A fresh LISTEN connection at shutdown is exactly the leak
    the close exists to prevent.

    ⚠️ COUNTED, NOT RAISED. A factory that raises proves nothing here: the wait's own
    `except` swallows it and the case passes for a listener that tried and failed. What is
    asserted is that nobody ASKED.
    """
    asked = []
    listener = OutboxListener(lambda: asked.append(1))
    listener.close()

    assert listener._wait_blocking(0.0) is False
    assert asked == [], "the listener went looking for a connection after it was closed"
    assert listener._connection is None


def test_a_close_while_a_wait_is_in_flight_is_a_shutdown_not_an_error(caplog):
    """🔴 TWO REASONS, TWO WORDS. The exception is the shutdown arriving."""
    listener = _listener()

    class _ClosesUnderUs:
        """`close()` lands while this wait is already inside `select` - which is the only
        way this happens, and why the flag is read in the `except` and not only at the top."""

        def poll(self):
            listener.close()
            raise RuntimeError("connection already closed")

        def close(self):
            pass

    listener._connection = _ClosesUnderUs()
    before = listener._reconnects

    with caplog.at_level(logging.INFO):
        assert listener._wait_blocking(0.0) is False

    levels = {r.levelno for r in caplog.records}
    assert logging.ERROR not in levels, [r.getMessage() for r in caplog.records]
    assert any("shutdown" in r.getMessage() for r in caplog.records), \
        [r.getMessage() for r in caplog.records]
    assert listener._reconnects == before + 1, (
        "close() itself resets the connection once - that is the close, not a "
        "reconnect by the reader")


def test_a_connection_that_really_died_is_still_an_error(caplog, monkeypatch):
    """대조군. Without this the case above would pass for a listener that never logs."""
    listener = _listener()
    listener._connection = _Raises()
    monkeypatch.setattr("outbox_listener.time.sleep", lambda *_: None)

    with caplog.at_level(logging.INFO):
        assert listener._wait_blocking(0.0) is False

    assert any(r.levelno == logging.ERROR for r in caplog.records), \
        [r.getMessage() for r in caplog.records]
    assert listener._reconnects == 1, "a real death has to be counted"


def test_the_shutdown_stops_the_reader_before_it_closes_the_connection():
    """🔴 THE ORDER IS THE FIX. Closing first is what put the reader's select on a
    connection that had gone away."""
    import main

    order = []

    class _Task:
        def done(self):
            return False

        def cancel(self):
            order.append("cancel")

        def __await__(self):
            order.append("awaited")
            if False:
                yield
            return None

    class _Listener:
        def close(self):
            order.append("close")

    main._outbox_task = _Task()
    main._outbox_listener = _Listener()
    try:
        asyncio.run(main.shutdown_event())
    finally:
        main._outbox_task = None
        main._outbox_listener = None

    assert "cancel" in order and "close" in order, order
    assert order.index("cancel") < order.index("close"), order
