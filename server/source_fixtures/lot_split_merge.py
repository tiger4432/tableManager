"""Generate exact-schema ``lot_event`` and ``process_event`` source rows.

The fixture models five independent 25-wafer roots across process steps 1..100.
Each root has four valid splits and four merges.  A split or merge is represented by
two source rows, matching the ledger lineage grammar:

* split: source and child rows are post-event membership snapshots;
* merge: source is a pre-event snapshot and destination is post-event.

The event is applied immediately before the process rows at the same ``event_time``.
That carries the event's step without inventing a ``step_seq`` column in ``lot_event``.
"""
from __future__ import annotations

import csv
import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Mapping, Sequence


DEFAULT_ROOT_LOTS = ("NAB123", "NAB115", "NAB122", "NAB163", "NAB539")

LOT_EVENT_COLUMNS = (
    "lot_id",
    "event_time",
    "txn_seq",
    "event_type",
    "parent_lot",
    "child_lot",
    "slotnumbers",
    "waferids",
)

PROCESS_EVENT_COLUMNS = (
    "txn_seq",
    "lot_id",
    "wafer_id",
    "step_seq",
    "rcp_id",
    "eqp_id",
    "event_time",
)

_EVENT_PATTERN = ("split", "split", "merge", "split", "split", "merge", "merge", "merge")


@dataclass(frozen=True)
class SyntheticLotSources:
    lot_event: tuple[dict[str, str], ...]
    process_event: tuple[dict[str, str], ...]
    event_steps: Mapping[str, tuple[int, ...]]
    child_lots: Mapping[str, tuple[str, ...]]
    seed: int
    wafers_per_root: int

    def summary(self) -> dict[str, object]:
        return {
            "seed": self.seed,
            "root_lots": list(self.event_steps),
            "wafers_per_root": self.wafers_per_root,
            "total_wafers": len(self.event_steps) * self.wafers_per_root,
            "step_seq": {"from": 1, "to": 100},
            "logical_events_per_root": len(_EVENT_PATTERN),
            "lot_event_rows": len(self.lot_event),
            "process_event_rows": len(self.process_event),
            "event_steps": {root: list(steps) for root, steps in self.event_steps.items()},
            "child_lots": {root: list(lots) for root, lots in self.child_lots.items()},
            "event_order": list(_EVENT_PATTERN),
            "event_application": "before process_event rows at the same event_time",
        }


def _excel_letters(index: int) -> str:
    """Return A, B, ..., Z, AA... for a zero-based index."""
    if index < 0:
        raise ValueError("child index must be non-negative")
    value = index + 1
    letters = []
    while value:
        value, remainder = divmod(value - 1, 26)
        letters.append(chr(ord("A") + remainder))
    return "".join(reversed(letters))


def child_lot_name(root_lot: str, index: int) -> str:
    return f"{root_lot}T{_excel_letters(index)}"


def _snapshot(members: Mapping[str, int]) -> tuple[str, str]:
    ordered = sorted(members.items(), key=lambda item: (item[1], item[0]))
    return (
        ":".join(f"{slot:02d}" for _wafer, slot in ordered),
        ":".join(wafer for wafer, _slot in ordered),
    )


def _event_row(
    *,
    lot_id: str,
    event_time: str,
    txn_seq: str,
    event_type: str,
    members: Mapping[str, int],
    parent_lot: str = "",
    child_lot: str = "",
) -> dict[str, str]:
    slots, wafers = _snapshot(members)
    return {
        "lot_id": lot_id,
        "event_time": event_time,
        "txn_seq": txn_seq,
        "event_type": event_type,
        "parent_lot": parent_lot,
        "child_lot": child_lot,
        "slotnumbers": slots,
        "waferids": wafers,
    }


def _split(
    *,
    root: str,
    active: dict[str, dict[str, int]],
    child_index: int,
    rng: random.Random,
    event_time: str,
    event_number: int,
    step: int,
) -> tuple[list[dict[str, str]], str]:
    candidates = [(lot, members) for lot, members in active.items() if len(members) >= 4]
    if not candidates:
        raise AssertionError(f"{root}: no lot can be split at step {step}")

    largest = max(len(members) for _lot, members in candidates)
    source_candidates = [item for item in candidates if len(item[1]) == largest]
    source_lot, source_members = rng.choice(source_candidates)
    child_lot = child_lot_name(root, child_index)

    max_move = min(8, len(source_members) - 2)
    move_count = rng.randint(2, max_move)
    moved_wafers = rng.sample(sorted(source_members), move_count)
    child_members = {wafer: source_members.pop(wafer) for wafer in moved_wafers}
    active[child_lot] = child_members

    prefix = f"LE-{root}-{step:03d}-{event_number:02d}"
    return [
        _event_row(
            lot_id=source_lot,
            event_time=event_time,
            txn_seq=f"{prefix}-P",
            event_type="split",
            members=source_members,
            child_lot=child_lot,
        ),
        _event_row(
            lot_id=child_lot,
            event_time=event_time,
            txn_seq=f"{prefix}-C",
            event_type="split",
            members=child_members,
            parent_lot=source_lot,
        ),
    ], child_lot


def _merge(
    *,
    root: str,
    active: dict[str, dict[str, int]],
    rng: random.Random,
    event_time: str,
    event_number: int,
    step: int,
    wafers_per_root: int,
) -> list[dict[str, str]]:
    source_candidates = sorted(lot for lot in active if lot != root)
    if not source_candidates:
        raise AssertionError(f"{root}: no child lot can be merged at step {step}")
    source_lot = rng.choice(source_candidates)
    source_before = dict(active[source_lot])
    destination = active[root]
    free_slots = [slot for slot in range(1, wafers_per_root + 1) if slot not in destination.values()]

    for wafer, old_slot in sorted(source_before.items(), key=lambda item: (item[1], item[0])):
        target_slot = old_slot if old_slot in free_slots else free_slots[0]
        free_slots.remove(target_slot)
        destination[wafer] = target_slot
    del active[source_lot]

    prefix = f"LE-{root}-{step:03d}-{event_number:02d}"
    return [
        _event_row(
            lot_id=source_lot,
            event_time=event_time,
            txn_seq=f"{prefix}-P",
            event_type="merge",
            members=source_before,
            child_lot=root,
        ),
        _event_row(
            lot_id=root,
            event_time=event_time,
            txn_seq=f"{prefix}-C",
            event_type="merge",
            members=destination,
            parent_lot=source_lot,
        ),
    ]


def _validate_roots(root_lots: Iterable[str]) -> tuple[str, ...]:
    roots = tuple(str(root).strip() for root in root_lots)
    if not roots or any(not root for root in roots):
        raise ValueError("root_lots must contain non-blank lot ids")
    if len(set(roots)) != len(roots):
        raise ValueError("root_lots must be unique")
    return roots


def generate_lot_split_merge_sources(
    root_lots: Sequence[str] = DEFAULT_ROOT_LOTS,
    *,
    wafers_per_root: int = 25,
    seed: int = 20260816,
    start_time: datetime = datetime(2026, 1, 1, 8, 0, 0),
) -> SyntheticLotSources:
    """Build deterministic raw source rows without writing or ingesting anything."""
    roots = _validate_roots(root_lots)
    if wafers_per_root < 8:
        raise ValueError("wafers_per_root must be at least 8 for four valid splits")

    rng = random.Random(seed)
    lot_rows: list[dict[str, str]] = []
    process_rows: list[dict[str, str]] = []
    event_steps: dict[str, tuple[int, ...]] = {}
    child_lots: dict[str, tuple[str, ...]] = {}

    for root_index, root in enumerate(roots):
        root_event_steps = tuple(sorted(rng.sample(range(5, 97), len(_EVENT_PATTERN))))
        event_steps[root] = root_event_steps
        operation_by_step = dict(zip(root_event_steps, _EVENT_PATTERN))
        active = {
            root: {
                f"{root}-W{slot:02d}": slot
                for slot in range(1, wafers_per_root + 1)
            }
        }
        made_children: list[str] = []
        event_number = 0

        for step in range(1, 101):
            event_time = (start_time + timedelta(hours=step - 1, minutes=root_index)).isoformat()
            operation = operation_by_step.get(step)
            if operation:
                event_number += 1
                if operation == "split":
                    rows, child = _split(
                        root=root,
                        active=active,
                        child_index=len(made_children),
                        rng=rng,
                        event_time=event_time,
                        event_number=event_number,
                        step=step,
                    )
                    made_children.append(child)
                    lot_rows.extend(rows)
                else:
                    lot_rows.extend(_merge(
                        root=root,
                        active=active,
                        rng=rng,
                        event_time=event_time,
                        event_number=event_number,
                        step=step,
                        wafers_per_root=wafers_per_root,
                    ))

            for lot_id, members in sorted(active.items()):
                for wafer_id, _slot in sorted(members.items(), key=lambda item: (item[1], item[0])):
                    wafer_number = int(wafer_id.rsplit("W", 1)[1])
                    process_rows.append({
                        "txn_seq": f"PE-{root_index + 1:02d}-{step:03d}-{wafer_number:02d}",
                        "lot_id": lot_id,
                        "wafer_id": wafer_id,
                        "step_seq": str(step),
                        "rcp_id": f"RCP-{((step - 1) // 10) + 1:02d}",
                        "eqp_id": f"EQP-{((step + wafer_number + root_index) % 6) + 1:02d}",
                        "event_time": event_time,
                    })

        if set(active) != {root} or len(active[root]) != wafers_per_root:
            raise AssertionError(f"{root}: final merge did not restore all wafers to root")
        child_lots[root] = tuple(made_children)

    result = SyntheticLotSources(
        lot_event=tuple(lot_rows),
        process_event=tuple(process_rows),
        event_steps=event_steps,
        child_lots=child_lots,
        seed=seed,
        wafers_per_root=wafers_per_root,
    )
    _validate_result(result)
    return result


def _validate_result(result: SyntheticLotSources) -> None:
    root_count = len(result.event_steps)
    expected_process = root_count * result.wafers_per_root * 100
    expected_lot_rows = root_count * len(_EVENT_PATTERN) * 2
    if len(result.process_event) != expected_process:
        raise AssertionError(f"process rows {len(result.process_event)} != {expected_process}")
    if len(result.lot_event) != expected_lot_rows:
        raise AssertionError(f"lot rows {len(result.lot_event)} != {expected_lot_rows}")
    if len({row["txn_seq"] for row in result.process_event}) != expected_process:
        raise AssertionError("process_event txn_seq is not unique")
    if len({row["txn_seq"] for row in result.lot_event}) != expected_lot_rows:
        raise AssertionError("lot_event txn_seq is not unique")
    if any(tuple(row) != PROCESS_EVENT_COLUMNS for row in result.process_event):
        raise AssertionError("process_event row does not match the declared source schema")
    if any(tuple(row) != LOT_EVENT_COLUMNS for row in result.lot_event):
        raise AssertionError("lot_event row does not match the declared source schema")
    for row in result.lot_event:
        if len(row["slotnumbers"].split(":")) != len(row["waferids"].split(":")):
            raise AssertionError(f"positional lot snapshot mismatch: {row['txn_seq']}")


def _write_csv(path: Path, columns: Sequence[str], rows: Sequence[Mapping[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def write_sources(result: SyntheticLotSources, output_dir: str | Path) -> dict[str, Path]:
    """Write Excel/Spotfire-friendly UTF-8 CSVs and a non-source summary JSON."""
    target = Path(output_dir).resolve()
    target.mkdir(parents=True, exist_ok=True)
    lot_path = target / "lot_event.csv"
    process_path = target / "process_event.csv"
    summary_path = target / "scenario_summary.json"
    _write_csv(lot_path, LOT_EVENT_COLUMNS, result.lot_event)
    _write_csv(process_path, PROCESS_EVENT_COLUMNS, result.process_event)
    summary_path.write_text(
        json.dumps(result.summary(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {"lot_event": lot_path, "process_event": process_path, "summary": summary_path}
