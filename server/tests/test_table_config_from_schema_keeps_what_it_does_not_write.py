# -*- coding: utf-8 -*-
"""총괄 338abb9f3: `table_config_from_schema --merge` writes the sheet's two cells for a table the
sheet names and keeps every other cell an existing entry carries - it used to keep three named
ones and drop the rest (`kind`, `decision_key`, `indexes`, `smart_paste`, `group`).
총괄 3a8c89f28: even those two the sheet adds to and changes, never takes from."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

import table_config_from_schema as generator                        # noqa: E402

ROWS = [("lot_event", "lot_id", "string"), ("lot_event", "event_time", "datetime"),
        ("lot_event", "qty", "number")]
SITE_CELLS = {"kind": "table", "decision_key": ["lot_id"], "indexes": [["event_time"]],
              "smart_paste": {"enabled": True}, "group": "lots",
              "composite_key_source": ["lot_id", "event_time"], "composite_key_separator": "|"}
# `old` is typed only by the declaration; `lot_id` a person hid; `note` a person shows first.
EXISTING = {"lot_event": {"__comment": "events", "business_key": "lot_key",
                          "column_types": {"lot_id": "number", "old": "string",
                                           "note": "string"},
                          "display_columns": ["note", "old"], **SITE_CELLS},
            "other": {"business_key": "x", "group": "kept"}}


def test_a_merge_keeps_every_cell_the_sheet_does_not_write():
    config, _, _, _, _ = generator.build(ROWS, EXISTING)
    entry = config["lot_event"]
    assert {k: entry.get(k) for k in SITE_CELLS} == SITE_CELLS
    assert (entry["__comment"], entry["business_key"]) == ("events", "lot_key")
    assert config["other"] == {"business_key": "x", "group": "kept"}


def test_the_sheet_adds_and_changes_column_types_and_a_column_it_does_not_name_stays():
    config, _, _, _, kept = generator.build(ROWS, EXISTING)
    assert config["lot_event"]["column_types"] == {
        "lot_id": "string", "old": "string", "note": "string",
        "event_time": "datetime", "qty": "number"}
    assert kept == [("lot_event", ["old", "note"])]
    text = generator.report(["lot_event"], [], [], "out.json", kept)
    assert "[시트에 없음, 남겨 둠]" in text and "  · lot_event: old, note" in text


def test_a_persons_order_and_hidden_column_stay_and_a_new_column_joins_the_end():
    config, _, _, _, _ = generator.build(ROWS, EXISTING)
    # `lot_id` was typed before and hidden, so it does not come back.
    assert config["lot_event"]["display_columns"] == ["note", "old", "event_time", "qty"]


def test_where_nobody_wrote_a_list_the_sheet_order_is_written():
    config, _, _, _, _ = generator.build(ROWS, {"lot_event": {"column_types": {"old": "string"}}})
    assert config["lot_event"]["display_columns"] == ["lot_id", "event_time", "qty"]


def test_a_table_the_merge_has_not_seen_gets_the_sheet_and_the_two_human_cells_empty():
    config, _, decisions, _, kept = generator.build(ROWS, {})
    assert config["lot_event"] == {
        "__comment": "", "business_key": None,
        "column_types": {"lot_id": "string", "event_time": "datetime", "qty": "number"},
        "display_columns": ["lot_id", "event_time", "qty"]}
    assert {field for _, field, _ in decisions} == {"business_key", "__comment"}
    assert kept == []
    assert "남겨 둠" not in generator.report(["lot_event"], [], decisions, "out.json", kept)
