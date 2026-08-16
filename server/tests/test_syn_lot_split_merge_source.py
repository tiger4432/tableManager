from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from source_fixtures.lot_split_merge import (
    DEFAULT_ROOT_LOTS,
    LOT_EVENT_COLUMNS,
    PROCESS_EVENT_COLUMNS,
    child_lot_name,
    generate_lot_split_merge_sources,
    write_sources,
)


def test_default_fixture_is_125_wafers_over_all_100_steps():
    built = generate_lot_split_merge_sources()

    assert len(built.process_event) == 12_500
    assert len({row["wafer_id"] for row in built.process_event}) == 125
    assert {int(row["step_seq"]) for row in built.process_event} == set(range(1, 101))

    for root in DEFAULT_ROOT_LOTS:
        root_rows = [row for row in built.process_event if row["wafer_id"].startswith(root + "-")]
        assert len(root_rows) == 2_500
        for step in range(1, 101):
            step_rows = [row for row in root_rows if int(row["step_seq"]) == step]
            assert len(step_rows) == 25
            assert len({row["wafer_id"] for row in step_rows}) == 25


def test_every_root_has_four_split_four_merge_and_ta_to_td_children():
    built = generate_lot_split_merge_sources()

    assert len(built.lot_event) == 80
    for root in DEFAULT_ROOT_LOTS:
        assert built.child_lots[root] == tuple(child_lot_name(root, i) for i in range(4))
        logical = [
            rows
            for rows in zip(built.lot_event[::2], built.lot_event[1::2])
            if rows[0]["txn_seq"].startswith(f"LE-{root}-")
        ]
        assert [pair[0]["event_type"] for pair in logical] == [
            "split", "split", "merge", "split", "split", "merge", "merge", "merge"
        ]
        assert all(1 <= step <= 100 for step in built.event_steps[root])


def test_event_pairs_are_complementary_and_positionally_valid():
    built = generate_lot_split_merge_sources()

    for left, right in zip(built.lot_event[::2], built.lot_event[1::2]):
        assert left["event_type"] == right["event_type"]
        assert left["event_time"] == right["event_time"]
        assert left["parent_lot"] == ""
        assert right["child_lot"] == ""
        assert left["child_lot"] == right["lot_id"]
        assert right["parent_lot"] == left["lot_id"]
        for row in (left, right):
            assert len(row["slotnumbers"].split(":")) == len(row["waferids"].split(":"))


def test_same_seed_is_reproducible_and_other_seed_changes_schedule():
    first = generate_lot_split_merge_sources(seed=41)
    same = generate_lot_split_merge_sources(seed=41)
    other = generate_lot_split_merge_sources(seed=42)

    assert first == same
    assert first.event_steps != other.event_steps


def test_writer_keeps_exact_source_columns(tmp_path):
    built = generate_lot_split_merge_sources()
    paths = write_sources(built, tmp_path)

    with paths["lot_event"].open(encoding="utf-8-sig", newline="") as handle:
        lot_reader = csv.DictReader(handle)
        assert tuple(lot_reader.fieldnames or ()) == LOT_EVENT_COLUMNS
        assert sum(1 for _row in lot_reader) == 80
    with paths["process_event"].open(encoding="utf-8-sig", newline="") as handle:
        process_reader = csv.DictReader(handle)
        assert tuple(process_reader.fieldnames or ()) == PROCESS_EVENT_COLUMNS
        assert sum(1 for _row in process_reader) == 12_500

    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    assert summary["total_wafers"] == 125
    assert summary["step_seq"] == {"from": 1, "to": 100}


def test_columns_match_current_source_table_config():
    config_path = Path(__file__).parents[1] / "config" / "table_config.json"
    table_config = json.loads(config_path.read_text(encoding="utf-8"))

    assert tuple(table_config["lot_event"]["display_columns"]) == LOT_EVENT_COLUMNS
    assert tuple(table_config["process_event"]["display_columns"]) == PROCESS_EVENT_COLUMNS


@pytest.mark.parametrize("roots", [[], [""], ["NAB123", "NAB123"]])
def test_invalid_root_lists_are_refused(roots):
    with pytest.raises(ValueError):
        generate_lot_split_merge_sources(roots)
