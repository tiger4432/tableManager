# -*- coding: utf-8 -*-
"""A retroactive run's write wakes no rule (owner 09-26) - and the refusal says THAT, not «this rule does not declare
allow_chain_trigger», which was untrue for a rule that declares it (lead 11-10: the owner's two-chain withdrawal - a
withdrawal from the reprocessing screen left the next chain's value, and the queue screen named the wrong reason)."""
import pytest

import event_constants
from chain import ingestion_worker as worker
from database import models

TABLE = "rw_y"


def _event(**payload):
    return models.DatabaseOutbox(id=1, table_name=TABLE, event_type="EDIT", payload=dict(payload, row_id="r1"))


def _rule(chain_trigger):
    return {"name": "y_to_z", "trigger_table": TABLE, "target_table": "rw_z", "allow_chain_trigger": chain_trigger}


@pytest.mark.parametrize("payload, chain_trigger, why", [
    # a retroactive run's write: held whatever the rule opts into - and said as such
    ({event_constants.CHANNEL_KEY: event_constants.CHANNEL_RETROACTIVE}, True, worker.FIRE_REFUSED_RETROACTIVE),
    ({event_constants.CHANNEL_KEY: event_constants.CHANNEL_RETROACTIVE}, False, worker.FIRE_REFUSED_RETROACTIVE),
    # the grid's click replay asks to cascade: it runs as the chain does
    ({event_constants.CHANNEL_KEY: event_constants.CHANNEL_RETROACTIVE, event_constants.CASCADE_KEY: True}, True, None),
    ({event_constants.CHANNEL_KEY: event_constants.CHANNEL_RETROACTIVE, event_constants.CASCADE_KEY: True}, False,
     worker.FIRE_REFUSED_CHAIN),
    # the chain's own write: the opt-in decides, as before
    ({event_constants.CHANNEL_KEY: event_constants.CHANNEL_CHAIN}, True, None),
    ({event_constants.CHANNEL_KEY: event_constants.CHANNEL_CHAIN}, False, worker.FIRE_REFUSED_CHAIN),
])
def test_the_refusal_names_its_reason(payload, chain_trigger, why):
    rule, event = _rule(chain_trigger), _event(**payload)
    assert worker.fire_refusal(rule, event) == why
    assert worker._rule_outcome_before_running(rule, [event]) == (
        (None, None) if why is None else (event_constants.RULE_OUTCOME_SKIPPED_NOT_TRIGGERED, why))
