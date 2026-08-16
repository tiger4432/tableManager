import os
import sys


SCRIPTS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import seed_dt_log_from_root_refs as seed


def test_groups_use_all_core_wafers_and_at_least_two_per_dt():
    wafers = [f"NAB115-W{i:02d}" for i in range(1, 26)]
    groups = seed._groups(wafers)
    assert [len(group) for group in groups] == [3, 2] * 5
    assert sorted(w for group in groups for w in group) == wafers


def test_front_frame_tokens_are_mixed_and_inventory_is_exactly_half_blank():
    dt_tokens = [seed.FRAME_TOKENS[i % len(seed.FRAME_TOKENS)] for i in range(50)]
    core_tokens = [seed.FRAME_TOKENS[(i * 3 + 1) % len(seed.FRAME_TOKENS)] for i in range(50)]
    assert len(set(dt_tokens)) == 4
    assert len(set(core_tokens)) == 4
    assert all(token.endswith("_front") for token in dt_tokens + core_tokens)
    assert all(a != b for a, b in zip(dt_tokens, core_tokens))
    assert sum(i % 2 == 0 for i in range(50)) == 25


def test_generated_frames_point_to_the_root_valid_die_floor():
    assert seed._valid_die_pointer("NAB115") == {
        "table": "valid_die_ref",
        "map_id": "NAB115_WF",
    }
