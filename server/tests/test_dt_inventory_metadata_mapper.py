import filecmp
import json
from pathlib import Path

from mappers.dt_inventory_metadata_mapper import copy_dt_metadata_to_inventory_batch


def _payload(target_table="dt_log", map_id="SYN-001", grid_metadata=None):
    return {
        "data": {
            "target_table": {"value": target_table},
            "map_id": {"value": map_id},
            "grid_metadata": {"value": grid_metadata or json.dumps({"ncols": 12})},
        }
    }


def test_copies_dt_log_metadata_to_matching_inventory_job():
    result = copy_dt_metadata_to_inventory_batch(None, [_payload()])

    assert result == {
        "updates": [{
            "business_key_val": "SYN-001",
            "updates": {"dt_job": "SYN-001", "dt_frame": '{"ncols": 12}'},
            "source_name": "chain_ingestion",
            "updated_by": "chain_metadata_identity",
        }]
    }


def test_skips_other_metadata_targets_invalid_json_and_duplicate_jobs():
    result = copy_dt_metadata_to_inventory_batch(None, [
        _payload(target_table="core_log"),
        _payload(map_id="bad", grid_metadata="[]"),
        _payload(map_id="broken", grid_metadata="not-json"),
        _payload(map_id="SYN-001"),
        _payload(map_id="SYN-001", grid_metadata=json.dumps({"ncols": 99})),
    ])

    assert len(result["updates"]) == 1
    assert result["updates"][0]["updates"]["dt_frame"] == '{"ncols": 12}'


def test_live_mapper_matches_tracked_sample():
    mapper_dir = Path(__file__).parents[1] / "mappers"
    assert filecmp.cmp(
        mapper_dir / "dt_inventory_metadata_mapper.py",
        mapper_dir / "dt_inventory_metadata_mapper.py.sample",
        shallow=False,
    )
