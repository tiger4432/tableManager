# -*- coding: utf-8 -*-
"""CLI for the deterministic 125-wafer split/merge source fixture.

This writes staging files only.  It never writes the database or a watched ``raws``
directory, so generation cannot accidentally ingest data.
"""
from __future__ import annotations

import argparse
import os
import sys


_HERE = os.path.dirname(os.path.abspath(__file__))
_SERVER = os.path.dirname(_HERE)
_REPO = os.path.dirname(_SERVER)
if _SERVER not in sys.path:
    sys.path.insert(0, _SERVER)

from source_fixtures.lot_split_merge import (  # noqa: E402
    DEFAULT_ROOT_LOTS,
    generate_lot_split_merge_sources,
    write_sources,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate exact-schema lot_event/process_event split-merge source CSVs."
    )
    parser.add_argument("--root-lots", nargs="+", default=list(DEFAULT_ROOT_LOTS))
    parser.add_argument("--wafers-per-root", type=int, default=25)
    parser.add_argument("--seed", type=int, default=20260816)
    parser.add_argument(
        "--output-dir",
        default=os.path.join(_REPO, "outputs", "syn_lot_split_merge"),
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    built = generate_lot_split_merge_sources(
        args.root_lots,
        wafers_per_root=args.wafers_per_root,
        seed=args.seed,
    )
    summary = built.summary()
    print("Synthetic lot split/merge source fixture")
    print(f"  roots         : {len(summary['root_lots'])}")
    print(f"  wafers        : {summary['total_wafers']}")
    print(f"  process rows  : {summary['process_event_rows']}")
    print(f"  lot rows      : {summary['lot_event_rows']}")
    for root, steps in built.event_steps.items():
        print(f"  {root:<8} events: {','.join(str(step) for step in steps)}")

    if args.dry_run:
        print("  dry-run       : nothing written")
        return 0

    paths = write_sources(built, args.output_dir)
    for name, path in paths.items():
        print(f"  {name:<13}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
