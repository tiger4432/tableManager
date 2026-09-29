# -*- coding: utf-8 -*-
"""A websocket connection leaves the broadcast list once, however many seats take it out
(총괄 f10905f33, 소유자 09-29 「asgi exception … list.remove(x) x not in list, error sending client」).

🔴 A broadcast's failed send and /ws's WebSocketDisconnect both take a dead connection out, and
two broadcasts running at once collect the same dead one - the second `remove` raised
ValueError, which ended `_outbox_queue_broadcast_loop` (it catches only CancelledError) until a
restart. And a broadcast walked the live list across its awaits, so a client leaving mid-way
made it skip the next one.
"""
import asyncio
import logging

import pytest

import main


class Socket:
    """A websocket as the manager uses one: `send_text` awaits, and may fail or run a hook."""

    def __init__(self, dead=False, during_send=None):
        self.dead, self.during_send, self.got = dead, during_send, []

    async def send_text(self, message):
        await asyncio.sleep(0)
        if self.during_send:
            self.during_send()
        if self.dead:
            raise RuntimeError("socket closed")
        self.got.append(message)


def _left(caplog):
    return sum("Client disconnected" in r.getMessage() for r in caplog.records)


@pytest.mark.anyio
async def test_two_broadcasts_that_find_the_same_dead_connection_take_it_out_once(caplog):
    caplog.set_level(logging.INFO)
    manager = main.ConnectionManager()
    dead, live = Socket(dead=True), Socket()
    manager.active_connections.extend([dead, live])

    await asyncio.gather(manager.broadcast("a"), manager.broadcast("b"))

    assert manager.active_connections == [live]
    assert sorted(live.got) == ["a", "b"]
    assert _left(caplog) == 1


@pytest.mark.anyio
async def test_ws_leaving_after_a_broadcast_took_it_out_is_quiet(caplog):
    caplog.set_level(logging.INFO)
    manager = main.ConnectionManager()
    dead = Socket(dead=True)
    manager.active_connections.append(dead)

    await manager.broadcast("a")
    manager.disconnect(dead)                  # the /ws handler's WebSocketDisconnect, after

    assert manager.active_connections == [] and _left(caplog) == 1


@pytest.mark.anyio
async def test_a_client_leaving_mid_broadcast_does_not_make_it_skip_another():
    manager = main.ConnectionManager()
    first, third = Socket(), Socket()
    second = Socket(during_send=lambda: manager.disconnect(first))
    manager.active_connections.extend([first, second, third])

    await manager.broadcast("x")

    assert third.got == ["x"], "a client that left mid-way made the broadcast skip the next"


@pytest.mark.anyio
async def test_the_outbox_broadcast_loop_keeps_going(monkeypatch):
    """/ws takes a connection out while its send is failing; the broadcast takes it out too."""
    manager = main.ConnectionManager()
    dead = Socket(dead=True, during_send=lambda: manager.disconnect(dead))
    live = Socket()
    manager.active_connections.extend([dead, live])
    monkeypatch.setattr(main, "manager", manager)
    rounds = []

    class Listener:
        def __init__(self, *args, **kwargs):
            pass

        async def wait(self, timeout):
            rounds.append(timeout)
            if len(rounds) > 2:
                await asyncio.sleep(3600)
            return True

        def close(self):
            pass

    monkeypatch.setattr(main, "OutboxListener", Listener)
    loop = asyncio.create_task(main._outbox_queue_broadcast_loop())
    for _ in range(100):
        await asyncio.sleep(0)
        if len(rounds) >= 3:
            break

    assert not loop.done(), loop.exception()
    assert len(live.got) == 2, "both notices reached the live client"
    loop.cancel()
    with pytest.raises(asyncio.CancelledError):
        await loop
