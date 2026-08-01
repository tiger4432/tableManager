# -*- coding: utf-8 -*-
"""Thin CLI over `server/trace_fixture`. All logic lives in the package.

`server/scripts/` is a one-way door in this repo: scripts bootstrap `server/`, never
the reverse. So this file only parses arguments and prints -- move any decision you
are tempted to make here into the package instead, or the auto-update collector and
the CLI will drift into two different fixtures.

Usage:
    conda run -n assy_manager python server/scripts/generate_trace_fixture.py --batch 1
    conda run -n assy_manager python server/scripts/generate_trace_fixture.py --dry-run

Console output is ASCII plus the CP949 range only: an em dash (U+2014) makes the whole
line vanish from a Windows console, so this file uses a horizontal bar (U+2015).
"""

import argparse
import os
import sys
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
_SERVER = os.path.dirname(_HERE)
if _SERVER not in sys.path:
    sys.path.insert(0, _SERVER)

import paths  # noqa: E402
from trace_fixture import GeneratorConfig, emit_batch, generate_batch  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate a trace fixture batch.")
    ap.add_argument("--batch", type=int, default=1,
                    help="batch number; also seeds the RNG, so a batch is reproducible")
    ap.add_argument("--core-lots", type=int, default=8)
    ap.add_argument("--slots-per-lot", type=int, default=25)
    ap.add_argument("--grid", type=int, default=13)
    ap.add_argument("--tape-wafers", type=int, default=120)
    ap.add_argument("--data-root", default=None,
                    help="defaults to paths.DATA_ROOT (honours ASSY_DATA_ROOT)")
    ap.add_argument("--dry-run", action="store_true",
                    help="build and report, write nothing")
    ap.add_argument("--no-oracle", action="store_true")
    ap.add_argument("--to-raws", action="store_true",
                    help="write straight into ingestion_workspace/<table>/raws so a "
                         "running watcher ingests immediately. WITHOUT this the batch "
                         "lands in trace_fixture_staging/ and ingesting it is a "
                         "separate, deliberate step.")
    args = ap.parse_args(argv)

    cfg = GeneratorConfig(batch=args.batch, core_lots=args.core_lots,
                          slots_per_lot=args.slots_per_lot, grid=args.grid,
                          tape_wafers=args.tape_wafers)
    built = generate_batch(cfg)
    st = built.stats

    print("trace fixture ― batch %d (seed %d)" % (cfg.batch, cfg.seed))
    print("  jobs               : %d  (symmetric %d / %d)"
          % (st["jobs"], st["jobs_symmetric"], st["jobs"]))
    print("  anchor bands       : %s" % st["anchor_bands"])
    for t, n in sorted(st["rows"].items()):
        print("  rows %-20s %d" % (t, n))
    for t, n in sorted(st["oracle"].items()):
        print("  oracle %-18s %d" % (t, n))

    if args.dry_run:
        print("  dry-run ― nothing written")
        return 0

    root = args.data_root or paths.DATA_ROOT
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = emit_batch(built, root, stamp, write_oracle=not args.no_oracle,
                     to_raws=args.to_raws)
    print("  target             : %s" % out["target"])
    for table, n, path in out["ingestion"]:
        print("  wrote %-20s %6d rows -> %s" % (table, n, path))
    if out["target"] == "staging":
        print("  not ingested ― move these into ingestion_workspace/<table>/raws/ "
              "when you want them loaded")
    if out["oracle_skipped"]:
        print("  oracle ― batch %d already recorded, not appended again" % cfg.batch)
    for name, n, path in out["oracle"]:
        print("  oracle %-18s %6d rows -> %s" % (name, n, path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
