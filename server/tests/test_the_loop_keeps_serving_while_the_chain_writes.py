# -*- coding: utf-8 -*-
"""S-93's net. One question: does the event loop keep serving while a chain group runs?

🔴 THE DEFECT THIS GUARDS WAS A GRADE 1 AND IT LOOKED LIKE SLOWNESS.
`process_chain_transaction_group` was declared `async def` and contained no `await` in 490
lines, so the mapper, every query it makes and the target write all ran ON THE LOOP THREAD.
Measured live 2026-09-09: a 1,000-row PUT answered in 22.8-33.5 s where the same code with
no chain worker answered in 1.36 s, and a GET issued during it - normally 0.07 s - took
22.76 s. Nothing errored. Every request in the process simply stopped, including the
response owed to the writer who woke the chain.

⚠️ AND THE LATENCY GATE COULD NOT BE THE NET. The lead's own ruling asked for "a GET under
0.3 s during a 1,000-row PUT", then measured that the remaining seconds are GIL contention
from the mapper's CPU-bound python (S-95) - so that number is not reachable by moving the
work off the loop and a test pinned to it would fail for a reason it does not name. What is
structurally true, and all that is claimed here, is that the loop REGAINS CONTROL.

⛔ NOT A TIMING TEST. No sleeps and no wall-clock thresholds: two events and a bounded wait,
so it says "the loop came back" rather than "it came back fast enough".
"""
import asyncio
import importlib
import json
import threading
from unittest.mock import MagicMock

import pytest

from chain import ingestion_worker as worker
from chain import mapper_call
from database.models import DatabaseOutbox

WAIT = 5.0


def _event():
    return DatabaseOutbox(
        event_uuid="s93-uuid-1",
        event_type="CREATE",
        table_name="trigger_table",
        payload=json.dumps({"source_name": "user", "transaction_id": "s93-tx",
                            "data": {"col1": "val1"}}),
    )


#: The module the rule below names. Spelled once so the patch and the rule cannot disagree.
MAPPER_MODULE = "tests.test_the_loop_keeps_serving_while_the_chain_writes"


def _rules():
    return [{
        "name": "s93_rule",
        "trigger_table": "trigger_table",
        "target_table": "target_table",
        "mapper_module": MAPPER_MODULE,
        "mapper_function": "unused_mapper",
        "enabled": True,
        "is_batch": False,
    }]


def unused_mapper(db, payload):                       # pragma: no cover - patched over
    return {"updates": []}


@pytest.mark.anyio
async def test_another_coroutine_completes_while_a_group_is_being_processed(monkeypatch):
    """🔴 THE DISCRIMINATING LINE IS `await asyncio.to_thread(entered.wait, WAIT)`.

    Reaching past it means the loop resumed a coroutine while the group's synchronous work
    was still in flight. With the work back on the loop that await cannot resume at all
    until the mapper gives up, so the group is already finished by the time control returns
    - which is what the `not task.done()` assertion reads.
    """
    entered = threading.Event()
    release = threading.Event()

    def blocking_mapper(db, payload):
        entered.set()
        # Bounded so a regression FAILS rather than hanging the suite. The return value
        # matters less than the fact that this thread is not the loop's.
        release.wait(WAIT)
        return {"updates": []}

    # ⚰️ [판정 498] THE MAPPER ITSELF, NOT THE EXECUTOR OVER IT. `execute_custom_mapper` is
    #    gone - the seat resolves `mapper_module`/`mapper_function` and calls what it finds -
    #    so the block goes where the rule already points, and the signature is the one the
    #    product actually hands a file mapper.
    # ⚠️ PATCHED ON THE MODULE OBJECT THE SEAT WILL IMPORT, not on `sys.modules[__name__]`.
    #    pytest may have this file under a different module name than the rule spells, and
    #    patching the wrong object leaves the real `unused_mapper` running - which shows up as
    #    「the mapper never started」 rather than as an error.
    monkeypatch.setattr(importlib.import_module(MAPPER_MODULE), "unused_mapper",
                        blocking_mapper)

    task = asyncio.create_task(
        worker.process_chain_transaction_group("s93-tx", [_event()], MagicMock(), _rules()))
    try:
        assert await asyncio.to_thread(entered.wait, WAIT), (
            "the mapper never started, so this test measured nothing")

        assert not task.done(), (
            "the group finished before this coroutine got control back: its work is "
            "running ON the event loop, which is S-93")
    finally:
        release.set()
        await task


@pytest.mark.anyio
async def test_the_public_funnel_still_answers_with_the_same_three_values():
    """The wrapper may not change the contract thirteen test files and one caller read."""
    ok, error, messages = await worker.process_chain_transaction_group(
        "s93-tx-2", [], MagicMock(), _rules())

    assert ok is True and error is None
    assert isinstance(messages, list)
