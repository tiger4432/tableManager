# -*- coding: utf-8 -*-
"""S-82. The product door wrote one outbox row per changed row, inside the request.

Measured 2026-09-09 through the application's own load: one `PUT /tables/dt_log/data/updates`
carrying 1,000 rows took 41.3 s and left 1,000 CREATE events, which the ledger's follow-up
then paced one at a time. Collapsing is not new machinery -- ingestion (`directory_watcher`)
and the chain worker have opted into it since [OUTBOX-4]. This door, the one the product
itself writes through, never did.

🔴 THE DECLARATION SAID THIS DOOR MUST STAY PER-ROW, so the reason it may collapse was
measured before the edit rather than argued after it. The retired sentence was "a correction
that reaches the DB but not the screen stops the correction loop" -- true, and about a loop
that does not run through this table: the endpoint broadcasts from `crud.apply_batch_updates`'
own return value, and the recovery sweep fires a table-level refresh keyed on `table_name`.
The only consumer that reads a payload's COLUMNS is the chain worker, which expands first --
`test_every_row_survives_the_collapse` is that half.

⚠️ BOTH ARMS ON THE SAME INPUT, the discipline `test_outbox_collapse.py` established: the
per-row arm is not decoration, it is what shows the collapsed arm is the thing that changed.

[Isolation] The `s82door_` prefix cannot exist in a real user config -- conftest claims the
live config at import time on a shared sqlite, so a colliding name would test another table.
"""
import pytest

import event_constants
import outbox_expand
from database import crud, models, schemas
from database.models import DatabaseOutbox
from utils.payload_helper import get_payload_dict

TABLE = "s82door_rows"
ROWS = 12

_CONFIG = {
    TABLE: {
        "business_key": "key_id",
        "column_types": {"key_id": "string", "lot": "string", "qty": "number"},
    },
}


@pytest.fixture()
def door(db_session):
    models.init_dynamic_models(_CONFIG)
    crud.TABLE_CONFIG.update(_CONFIG)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    return db_session


def _payload(prefix, count=ROWS):
    return {
        "updates": [
            {"business_key_val": f"{prefix}{i}",
             "updates": {"key_id": f"{prefix}{i}", "lot": "LOT-A", "qty": float(i)},
             "source_name": "s82", "updated_by": "tester"}
            for i in range(count)
        ],
        "transaction_id": f"tx-{prefix}",
        "silent": True,
    }


def _events(db, tx_id):
    rows = db.query(DatabaseOutbox).filter(
        DatabaseOutbox.table_name == TABLE
    ).order_by(DatabaseOutbox.id.asc()).all()
    return [e for e in rows if get_payload_dict(e).get("transaction_id") == tx_id]


def test_the_door_stages_one_event_for_the_whole_batch(door, client):
    response = client.put(f"/tables/{TABLE}/data/updates", json=_payload("A"))
    assert response.status_code == 200, response.text

    events = _events(door, "tx-A")
    assert len(events) == 1, f"{len(events)} events for one request of {ROWS} rows"

    payload = get_payload_dict(events[0])
    assert event_constants.is_collapsed_payload(payload)
    assert events[0].event_type == "CREATE"
    assert len(payload["row_ids"]) == ROWS


def test_a_caller_that_does_not_opt_in_is_still_per_row(door):
    """The 'before' arm, on the same input. The default did not move -- the door did."""
    batch = schemas.GeneralUpdateBatch(**_payload("B"))
    crud.apply_batch_updates(door, TABLE, batch)

    events = _events(door, "tx-B")
    assert len(events) == ROWS
    assert not any(event_constants.is_collapsed_payload(get_payload_dict(e)) for e in events)


def test_every_row_survives_the_collapse(door, client):
    """One event, but the chain still sees ROWS rows -- the expander is what makes the
    pointer safe, so a collapse that lost a row would show up here and not in the count."""
    client.put(f"/tables/{TABLE}/data/updates", json=_payload("C"))
    event = _events(door, "tx-C")[0]

    expanded = outbox_expand.expand_events(door, [event])
    rebuilt = expanded[outbox_expand.event_key(event)]
    assert len(rebuilt) == ROWS
    # `data[col]` is a CELL (a dict), not a scalar -- identity rides `business_key`.
    assert {row["business_key"] for row in rebuilt} == {f"C{i}" for i in range(ROWS)}
