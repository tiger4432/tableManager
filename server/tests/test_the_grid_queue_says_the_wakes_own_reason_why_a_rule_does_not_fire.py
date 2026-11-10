# -*- coding: utf-8 -*-
"""Lead 11-10 D2: `/outbox/queue/rows` told its own three-way «why not» - an edit that changed none of a rule's wake
columns read «chain-produced event». The reason is `fire_refusal`'s, the seat `wakes` asks."""
import event_constants
from chain import ingestion_worker as worker
from test_the_queue_says_what_will_run_and_who_owns_each_row import _a_rule_watches_t, row, rows_of  # noqa: F401


def test_why_not_is_the_seats_sentence(client, db_session, monkeypatch):
    monkeypatch.setattr(worker, "load_chain_rules", lambda: [
        # fires on both rows, so both are listed
        {"name": "on", "enabled": True, "trigger_table": "t", "target_table": "u", "allow_chain_trigger": True},
        {"name": "cols", "enabled": True, "trigger_table": "t", "target_table": "u", "trigger_columns": ["y"]}])
    edit = row(db_session, table_name="t", payload={"transaction_id": "tx-why", "columns": ["x"]})
    chain = row(db_session, table_name="t",
                payload={"transaction_id": "tx-why", event_constants.CHANNEL_KEY: event_constants.CHANNEL_CHAIN})
    _body, by_id = rows_of(client)

    said = {r["name"]: r for r in by_id[edit.id]["rules"]}
    assert (said["cols"]["will_fire"], said["cols"]["why_not"]) == (False, worker.FIRE_REFUSED_COLUMNS)
    said = {r["name"]: r for r in by_id[chain.id]["rules"]}
    assert (said["cols"]["will_fire"], said["cols"]["why_not"]) == (False, worker.FIRE_REFUSED_CHAIN)
