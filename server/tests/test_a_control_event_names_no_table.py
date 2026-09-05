# -*- coding: utf-8 -*-
"""A row with no table filled the column with a table name that does not exist.

`database_outbox.table_name` is not empty by convention, so a retroactive run -- which has
no single table -- carries `__retroactive__` to fill the square. The queue view then listed
it among the tables a waiting transaction touches, and an operator reading that list goes
looking for a table nobody ever created. That trip IS the cost of this defect: it is not a
missing fact, it is ABSENCE SPOKEN AS A NAME.

🔴 THE FIX IS ON THE READING SIDE, and that is the whole point. The row already says what
it is -- `event_type` is `RETROACTIVE_RUN`, and the same grouping already collects
`event_types`. So nothing has to be produced; the reader stops taking a placeholder for an
identity it already has by another name.

⛔ AND IT IS RULED ON THE CLASS, NOT THE INSTANCE. `event_constants.CONTROL_EVENT_TYPES`
already names every outbox row that is an instruction rather than data. Matching
`__retroactive__` itself would put a placeholder string in the reader too, and the next
control event would arrive with the same defect and no test to catch it.
"""
import json
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import event_constants                                           # noqa: E402
import retroactive                                               # noqa: E402
from database import models                                      # noqa: E402

TX = "tx-control-probe"


def outbox_row(db, *, event_type, table_name, transaction_id=TX):
    db.add(models.DatabaseOutbox(
        event_uuid=str(uuid.uuid4()), table_name=table_name, event_type=event_type,
        payload=json.dumps({"transaction_id": transaction_id}), processed_chain=False))
    db.flush()


def waiting_transactions(client):
    body = client.get("/admin/chain/queue",
                      headers={"X-Admin-Token": os.environ.get("ADMIN_TOKEN", "")}).json()
    return {g["transaction_id"]: g for g in body.get("waiting_transactions", [])}


def group(client, tx=TX):
    groups = waiting_transactions(client)
    assert tx in groups, "the probe row is not in the waiting list at all"
    return groups[tx]


def test_the_placeholder_never_reaches_the_table_list(client, db_session):
    """🔴 THE DEFECT. `__retroactive__` is not a table and must not be offered as one."""
    outbox_row(db_session, event_type=retroactive.RUN_EVENT_TYPE,
               table_name=retroactive.RUN_EVENT_TABLE)
    assert retroactive.RUN_EVENT_TABLE not in group(client)["tables"]
    assert group(client)["tables"] == []


def test_the_row_still_says_what_it_is():
    """⚠️ NOT A DELETION. Withholding the identity as well would trade a wrong answer for
    no answer -- the failure class this repository spent the day removing."""
    assert retroactive.RUN_EVENT_TYPE in event_constants.CONTROL_EVENT_TYPES


def test_the_event_type_carries_the_identity_the_table_name_was_faking(client, db_session):
    outbox_row(db_session, event_type=retroactive.RUN_EVENT_TYPE,
               table_name=retroactive.RUN_EVENT_TABLE)
    assert retroactive.RUN_EVENT_TYPE in group(client)["event_types"]


def test_a_real_data_row_still_names_its_table(client, db_session):
    """🔴 THE OTHER HALF. A rule that hid every table name would pass the test above and
    blind the list it exists to fill."""
    outbox_row(db_session, event_type="ROW_UPDATED", table_name="dt_map")
    assert group(client)["tables"] == ["dt_map"]


def test_one_transaction_holding_both_keeps_only_the_real_table(client, db_session):
    """The mixed case, which is the one a placeholder survives in: a control row beside a
    data row would otherwise contribute a second 'table'."""
    outbox_row(db_session, event_type="ROW_UPDATED", table_name="dt_map")
    outbox_row(db_session, event_type=retroactive.RUN_EVENT_TYPE,
               table_name=retroactive.RUN_EVENT_TABLE)
    listed = group(client)
    assert listed["tables"] == ["dt_map"]
    assert listed["rows"] == 2, "the control row was dropped from the count as well"


@pytest.mark.parametrize("event_type", sorted(event_constants.CONTROL_EVENT_TYPES))
def test_every_control_event_is_covered_not_just_the_retroactive_one(
        client, db_session, event_type):
    """⛔ THE CLASS. A control event added later inherits this without an edit here -- and
    if someone narrows the reader back to one name, this goes red on the others."""
    outbox_row(db_session, event_type=event_type, table_name="__some_placeholder__")
    assert group(client)["tables"] == []
