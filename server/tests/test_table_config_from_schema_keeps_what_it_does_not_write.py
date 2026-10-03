# -*- coding: utf-8 -*-
"""총괄 338abb9f3: `table_config_from_schema --merge` writes the sheet's two cells for a table the
sheet names and keeps every other cell an existing entry carries - it used to keep three named
ones and drop the rest (`kind`, `decision_key`, `indexes`, `smart_paste`, `group`)."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

import table_config_from_schema as generator                        # noqa: E402

ROWS = [("lot_event", "lot_id", "string"), ("lot_event", "event_time", "datetime"),
        ("lot_event", "qty", "number")]
SITE_CELLS = {"kind": "table", "decision_key": ["lot_id"], "indexes": [["event_time"]],
              "smart_paste": {"enabled": True}, "group": "lots",
              "composite_key_source": ["lot_id", "event_time"], "composite_key_separator": "|"}


def test_a_merge_keeps_every_cell_the_sheet_does_not_write():
    existing = {"lot_event": {"__comment": "events", "business_key": "lot_key",
                              "column_types": {"lot_id": "string", "old": "string"},
                              "display_columns": ["old"], **SITE_CELLS},
                "other": {"business_key": "x", "group": "kept"}}
    config, _, _, _ = generator.build(ROWS, existing)
    entry = config["lot_event"]
    assert {k: entry.get(k) for k in SITE_CELLS} == SITE_CELLS
    assert (entry["__comment"], entry["business_key"]) == ("events", "lot_key")
    assert entry["column_types"] == {"lot_id": "string", "event_time": "datetime", "qty": "number"}
    assert entry["display_columns"] == ["lot_id", "event_time", "qty"]
    assert config["other"] == {"business_key": "x", "group": "kept"}


def test_a_table_the_merge_has_not_seen_gets_the_sheet_and_the_two_human_cells_empty():
    config, _, decisions, _ = generator.build(ROWS, {})
    assert config["lot_event"] == {
        "__comment": "", "business_key": None,
        "column_types": {"lot_id": "string", "event_time": "datetime", "qty": "number"},
        "display_columns": ["lot_id", "event_time", "qty"]}
    assert {field for _, field, _ in decisions} == {"business_key", "__comment"}
