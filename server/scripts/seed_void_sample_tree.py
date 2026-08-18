"""Write a sample void folder tree, then read it back through the real parser.

WHY THIS EXISTS
---------------
`external_sources` for voids.json is refused for reasons that live in the FOLDER, not in
the JSON: the reader takes the wafer id and the scan time from the directory names and
requires exactly three path components.  An operator who only ever sees the JSON cannot
tell a good tree from a bad one, and the refusal arrives one file at a time.  This script
builds a tree that is correct by construction and then feeds it to
`parsers.voids_json_format.parse_voids_json` -- the same function the watcher calls -- so
the shape is demonstrated rather than described.

It touches no database, registers no source, and writes only under the directory you
name.  Point `--root` at a scratch directory, not at a watched one, unless you mean to
ingest what it writes.

    python scripts/seed_void_sample_tree.py --root C:/tmp/void_sample
    python scripts/seed_void_sample_tree.py --root C:/tmp/void_sample --no-verify
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "parsers"))

FILENAME = "voids.json"
UNIT = "um"

# One entry per folder.  The work id is free text; the timestamp must close the name.
# The third case is the one operators forget: a scan that found nothing still has to say
# WHICH package layer it looked at, or "clean" and "never scanned" become the same row.
SAMPLES = (
    {
        "wafer": "BW-2601-01",
        "folder": "JOB1234_20260818_143000",
        "voids": [
            {"base_x": 1, "base_y": 2, "stack_gate": 3,
             "inchip_x": 10.5, "inchip_y": 20.25, "radius_x": 0.40, "radius_y": 0.60},
            {"base_x": 1, "base_y": 2, "stack_gate": 3,
             "inchip_x": 30.0, "inchip_y": 40.0, "radius_x": 0.20, "radius_y": 0.30},
            {"base_x": 4, "base_y": 5, "stack_gate": 3,
             "inchip_x": 12.0, "inchip_y": 22.0, "radius_x": 0.15, "radius_y": 0.15},
        ],
        "runs": None,
        "note": "two package positions, three findings - runs are derived from them",
    },
    {
        "wafer": "BW-2601-02",
        "folder": "JOB1235_20260818_151500",
        "voids": [
            {"base_x": 2, "base_y": 2, "stack_gate": 5,
             "inchip_x": 5.0, "inchip_y": 5.0, "radius_x": 0.9, "radius_y": 1.1},
        ],
        "runs": None,
        "note": "single finding on one layer",
    },
    {
        "wafer": "BW-2601-03",
        "folder": "JOB1236_20260818_160000",
        "voids": [],
        "runs": [
            {"base_x": 3, "base_y": 3, "stack_gate": 5},
            {"base_x": 3, "base_y": 4, "stack_gate": 5},
        ],
        "note": "CLEAN scan - zero findings, so the layers inspected must be declared",
    },
)


def write_tree(root: str) -> list[tuple[str, str]]:
    written = []
    for sample in SAMPLES:
        folder = os.path.join(root, sample["wafer"], sample["folder"])
        os.makedirs(folder, exist_ok=True)
        payload = {"unit": UNIT, "voids": sample["voids"]}
        if sample["runs"] is not None:
            payload["runs"] = sample["runs"]
        path = os.path.join(folder, FILENAME)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        rel = f"{sample['wafer']}/{sample['folder']}/{FILENAME}"
        written.append((path, rel))
        print(f"  wrote {rel}  ({len(sample['voids'])} void(s)) - {sample['note']}")
    return written


def verify(written: list[tuple[str, str]]) -> int:
    from parsers.voids_json_format import parse_voids_json

    failures = 0
    for path, rel in written:
        for table in ("inspection_run", "void_obs"):
            try:
                rows, total, refused = parse_voids_json(
                    path, rel_path=rel, table_name=table, options={})
            except Exception as exc:                      # noqa: BLE001 - report, not raise
                failures += 1
                print(f"  REFUSED {rel} -> {table}: {type(exc).__name__}: {exc}")
                continue
            work_ids = sorted({str(row.get("work_id")) for row in rows})
            print(f"  ok {rel} -> {table:15s} rows={total} refused={refused} "
                  f"work_id={work_ids}")
    return failures


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", required=True,
                        help="directory to write the sample tree into")
    parser.add_argument("--no-verify", action="store_true",
                        help="write the files but do not read them back")
    args = parser.parse_args(argv)

    root = os.path.abspath(args.root)
    print(f"root: {root}")
    print(f"shape: <WAFERID>/<WORKID>_<YYYYMMDD>_<HHMMSS>/{FILENAME}  (exactly 3 levels)")
    written = write_tree(root)
    if args.no_verify:
        return 0
    print()
    print("reading the tree back through the watcher's own parser:")
    failures = verify(written)
    print()
    if failures:
        print(f"REFUSALS: {failures} - the tree above is NOT ingestible as written")
        return 1
    print("all files parse for both tables")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
