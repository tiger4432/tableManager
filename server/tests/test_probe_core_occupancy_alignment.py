import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from probe_core_occupancy_alignment import judge_occupancy


def _payload(scores, count=61):
    return {"sources": {"cell_count": count}, "candidates": [
        {"frame": frame, "agreement": score, "state": "scored", "shift": {"dx": 0, "dy": 0}}
        for frame, score in scores
    ]}


def test_partial_or_dumped_source_can_propose_without_perfect_overlap():
    verdict = judge_occupancy(_payload([("rot270_tl", 55), ("rot90_tl", 43)]))
    assert verdict["state"] == "proposed"
    assert verdict["winner"] == "rot270_tl"
    assert verdict["hit_ratio"] < 1


def test_close_or_weak_occupancy_result_stays_in_manual_review():
    close = judge_occupancy(_payload([("rot270_tl", 55), ("rot90_tl", 52)]))
    weak = judge_occupancy(_payload([("rot270_tl", 45), ("rot90_tl", 32)]))
    assert close["state"] == "review"
    assert weak["state"] == "review"
