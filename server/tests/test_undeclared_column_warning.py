"""[Schema] A column absent from ``column_types`` is dropped from an update while the
write still reports success -- a silent data-loss channel open on every table
(``map_doe``/``map_doe_source`` lost ``eventtime`` this way for an unknown period).

The drop itself is deliberate and unchanged: rejecting the write would turn a config
that lags its client into an outage. These tests pin the *diagnostic* instead --
it must fire on the real write path, exactly once per (table, column), separately
for distinct pairs, and it must never interfere with persisting declared columns.
"""

import logging

import pytest

from database import crud, models, schemas


class _WarningCollector(logging.Handler):
    """Attached directly to the "Server" logger. Deliberately not ``caplog``: the
    whole point of these tests is *how many* records are emitted, so capture must
    not depend on propagation or on pytest's per-test handler juggling."""

    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.records = []

    def emit(self, record):
        self.records.append(record.getMessage())

    @property
    def schema_warnings(self):
        return [m for m in self.records if "[Schema]" in m]


@pytest.fixture
def warn_capture():
    logger = logging.getLogger("Server")
    handler = _WarningCollector()
    logger.addHandler(handler)
    # The registry is a process global; without this a prior test in the same
    # session could pre-warm a pair and make "fires once" pass vacuously.
    crud._undeclared_column_warned.clear()
    try:
        yield handler
    finally:
        logger.removeHandler(handler)
        crud._undeclared_column_warned.clear()


def _batch(business_key_val, updates):
    return schemas.GeneralUpdateBatch(
        updates=[
            schemas.GeneralUpdateItem(
                business_key_val=business_key_val,
                updates=updates,
                source_name="user",
                updated_by="tester",
            )
        ],
        silent=True,
    )


def test_undeclared_column_warns_once_and_row_still_saves(client, db_session, warn_capture):
    """Real path: PUT /tables/{t}/data/updates with an undeclared column.

    Asserts the three things the incident turned on -- the request still succeeds,
    the declared columns are still written, and the dropped column is now visible.
    """
    payload = {
        "updates": [
            {
                "business_key_val": "PN-1001",
                "updates": {
                    "part_no": "PN-1001",
                    "category": "BRACKET",
                    "stock_qty": 7,
                    # Not present in column_types -> dropped, request still 200.
                    "eventtime": "2026-07-27T10:00:00",
                },
                "source_name": "user",
                "updated_by": "tester",
            }
        ],
        "silent": True,
    }

    resp = client.put("/tables/inventory_master/data/updates", json=payload)
    assert resp.status_code == 200, resp.text

    model = models.DYNAMIC_TABLES["inventory_master"]
    row = db_session.query(model).filter(model.business_key_val == "PN-1001").first()
    assert row is not None, "declared columns must still be written"
    assert row.part_no == "PN-1001"
    assert row.category == "BRACKET"
    assert row.stock_qty == 7
    # The undeclared column is genuinely absent -- the write really did lose it.
    assert getattr(row, "eventtime", None) is None

    warnings = warn_capture.schema_warnings
    assert len(warnings) == 1, warnings
    assert "eventtime" in warnings[0]
    assert "inventory_master" in warnings[0]

    # Fires ONCE: repeat the identical write and show no second line.
    resp2 = client.put("/tables/inventory_master/data/updates", json=payload)
    assert resp2.status_code == 200, resp2.text
    assert len(warn_capture.schema_warnings) == 1, warn_capture.schema_warnings


def test_repeated_rows_in_one_batch_warn_once(db_session, warn_capture):
    """The drop is a per-cell branch: 500 rows carrying the same undeclared column
    must still produce exactly one line, not 500."""
    batch = schemas.GeneralUpdateBatch(
        updates=[
            schemas.GeneralUpdateItem(
                business_key_val=f"PN-{i}",
                updates={"part_no": f"PN-{i}", "eventtime": "2026-07-27T10:00:00"},
                source_name="user",
                updated_by="tester",
            )
            for i in range(500)
        ],
        silent=True,
    )
    crud.apply_batch_updates(db_session, "inventory_master", batch)

    assert len(warn_capture.schema_warnings) == 1, len(warn_capture.schema_warnings)


def test_distinct_table_column_pairs_each_warn(db_session, warn_capture):
    """Warn-once is keyed by (table, column), not by table and not by column."""
    crud.apply_batch_updates(
        db_session,
        "inventory_master",
        _batch("PN-2001", {"part_no": "PN-2001", "ghost_a": 1}),
    )
    crud.apply_batch_updates(
        db_session,
        "inventory_master",
        _batch("PN-2002", {"part_no": "PN-2002", "ghost_b": 1}),
    )
    crud.apply_batch_updates(
        db_session,
        "production_plan",
        _batch("PL-1", {"plan_id": "PL-1", "ghost_a": 1}),
    )

    warnings = warn_capture.schema_warnings
    assert len(warnings) == 3, warnings
    assert any("ghost_a" in m and "inventory_master" in m for m in warnings)
    assert any("ghost_b" in m and "inventory_master" in m for m in warnings)
    assert any("ghost_a" in m and "production_plan" in m for m in warnings)


def test_registry_is_bounded_and_announces_its_own_silence(db_session, warn_capture, monkeypatch):
    """Column names come from the payload, so a junk-header caller could grow the
    registry without limit. Past the budget it stops growing AND says so once."""
    monkeypatch.setattr(crud, "_MAX_UNDECLARED_WARNED_PER_TABLE", 3)

    for i in range(10):
        crud.apply_batch_updates(
            db_session,
            "inventory_master",
            _batch(f"PN-3{i:03d}", {"part_no": f"PN-3{i:03d}", f"junk_{i}": 1}),
        )

    assert len(crud._undeclared_column_warned["inventory_master"]) == 3

    warnings = warn_capture.schema_warnings
    drops = [m for m in warnings if "DROPPED" in m]
    saturation = [m for m in warnings if "WITHOUT a warning" in m]
    assert len(drops) == 3, drops
    assert len(saturation) == 1, saturation
