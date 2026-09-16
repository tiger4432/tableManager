import asyncio
from unittest.mock import MagicMock

import pytest

from chain import ingestion_worker as worker
from chain import mapper_call
from database.models import DatabaseOutbox


def _event(source_name="chain_ingestion"):
    return DatabaseOutbox(
        event_uuid="cascade-event",
        event_type="EDIT",
        table_name="wafer_map_metadata",
        payload={"source_name": source_name, "data": {}},
    )


def test_chain_events_are_opt_in_per_rule_and_target_group():
    event = _event()
    blocked = {"trigger_table": "wafer_map_metadata", "target_table": "blocked", "enabled": True}
    allowed = {**blocked, "target_table": "dt_inventory", "allow_chain_trigger": True}

    assert not worker._rule_accepts_event(blocked, event)
    assert worker._rule_accepts_event(allowed, event)
    assert worker._group_target_tables([event], [blocked]) == set()
    assert worker._group_target_tables([event], [blocked, allowed]) == {"dt_inventory"}
    assert worker._rule_accepts_event(blocked, _event("user"))


def test_names_an_opt_in_chain_cycle_without_killing_the_load(caplog):
    """⚰️ THIS USED TO RAISE, AND THE RAISE KILLED THE LOAD (판정 402). `_validate_chain_cascade_graph`
    answers 「do the opt-in chain triggers loop」, and the answer 「yes」 is not a fault: the
    drain enforces `max_chain_depth`, so the loop is finite. Raising here took the whole rules
    file down - and the save route with it, so a declaration that RUNS correctly could not be
    written at all."""
    import logging

    from chain import rule_order

    rule_order.forget_cycles()
    with caplog.at_level(logging.INFO):
        worker._validate_chain_cascade_graph([
            {"name": "a_to_b", "trigger_table": "a", "target_table": "b", "allow_chain_trigger": True},
            {"name": "b_to_a", "trigger_table": "b", "target_table": "a", "allow_chain_trigger": True},
        ])

    said = " ".join(record.getMessage() for record in caplog.records)
    assert "고리" in said and "max_chain_depth" in said, said
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


def test_processor_only_invokes_the_opted_in_rule(monkeypatch):
    calls = []
    event = _event()
    blocked = {
        "name": "blocked", "trigger_table": "wafer_map_metadata", "target_table": "blocked",
        "mapper_module": "unused", "mapper_function": "unused", "is_batch": True, "enabled": True,
    }
    allowed = {
        **blocked, "name": "allowed", "target_table": "dt_inventory", "allow_chain_trigger": True,
    }

    monkeypatch.setattr(worker.outbox_expand, "expand_events", lambda _db, events: {
        worker.outbox_expand.event_key(event): [{"data": {}}] for event in events
    })
    monkeypatch.setattr(
        mapper_call,
        "execute_custom_mapper",
        lambda _module, _function, _db, _payload, rule=None: calls.append(rule["name"]) or {"updates": []},
    )

    ok, error, _messages = asyncio.run(
        worker.process_chain_transaction_group("cascade-tx", [event], MagicMock(), [blocked, allowed])
    )
    assert ok and error is None
    assert calls == ["allowed"]
