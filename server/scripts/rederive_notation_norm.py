"""Operator's door to notation re-derivation - report, then optionally write.

The logic lives in ``server/notation_norm.py`` (what the rules are, why the raw
column is never touched, and why re-deriving is the supported repair are
documented there). This file is the human path: argparse, the printed report,
and the exit code - the ``scripts/backfill_enrichment.py`` <->
``enrichment_backfill.py`` split, applied here for the reason that split exists.

WHY THIS EXISTS
    A folding rule shipped before its false-merge census had been run. That is
    only safe because the normalized value is DERIVED: if a rule turns out to
    merge two genuinely different entities, you edit
    ``config/notation_rules.json`` and run this, and the derived column is
    whatever the new rules say. Nothing was lost, because the raw column - the
    only thing that cannot be recomputed - was never written.

Usage (dry-run is the default - report first, act only on an explicit flag):

    conda run -n assy_manager python server/scripts/rederive_notation_norm.py
    conda run -n assy_manager python server/scripts/rederive_notation_norm.py --apply
    conda run -n assy_manager python server/scripts/rederive_notation_norm.py --table dt_log --apply

Flags:
    --apply         actually write the derived column (default: dry-run report)
    --table T       restrict to one table (default: every declared table)
    --chunk-size N  scan/write chunk size (default 1000)

EXIT CODES
    0  the report was produced (dry-run), or the derived columns were written
    2  refused: bad --chunk-size, no declaration, or a rejected declaration
"""
import argparse
import os
import sys

# Standalone bootstrap: make server/ importable (same pattern every script in
# this directory uses).
_SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)

import notation_norm  # noqa: E402  (the single implementation; see its docstring)


def format_report(stats: dict) -> str:
    on = [name for name in notation_norm.KNOWN_RULES if stats["rules"].get(name)]
    lines = [
        "",
        f"=== notation re-derivation {'APPLY' if stats['mode'] == 'apply' else 'DRY-RUN'}"
        f" - {stats['table']}.{stats['raw']} -> {stats['derived']} ===",
        f"  rules in effect : {', '.join(on) if on else '(none - value passes through)'}",
        f"  rows scanned    : {stats['scanned']}",
        f"  rows to change  : {stats['changed']}"
        + ("" if stats["mode"] == "apply" else "   (nothing written - dry run)"),
    ]
    if stats["samples"]:
        lines.append("  sample:")
        for s in stats["samples"]:
            lines.append(f"    raw={s['raw']!r}  was={s['was']!r}  now={s['now']!r}")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Recompute notation-normalized derived columns.")
    parser.add_argument("--apply", action="store_true",
                        help="write the derived column (default: dry-run report)")
    parser.add_argument("--table", default=None, help="restrict to one table")
    parser.add_argument("--chunk-size", type=int,
                        default=notation_norm.REDERIVE_CHUNK_SIZE)
    args = parser.parse_args(argv)

    if args.chunk_size < 1:
        print("--chunk-size must be >= 1", file=sys.stderr)
        return 2

    from database import crud, models
    from database.database import SessionLocal

    table_config = crud.load_table_config()
    if not table_config:
        print("table_config.json is empty or unreadable - nothing to derive",
              file=sys.stderr)
        return 2
    # Models only - deliberately NO create_all. This tool reads and updates one
    # column of tables that already exist; issuing DDL from a re-derivation run
    # would make a repair tool capable of changing the schema it repairs.
    models.init_dynamic_models(table_config)

    rejections = []
    by_table = notation_norm.load_notation_rules(
        known_tables=table_config, rejections=rejections)
    for r in rejections:
        print(f"  REJECTED [{r['code']}] {r['scope']} {r['subject']}: {r['detail']}",
              file=sys.stderr)
    if args.table:
        by_table = {k: v for k, v in by_table.items() if k == args.table}
    if not by_table:
        print("no notation derivation is declared (config/notation_rules.json) - "
              "nothing to do", file=sys.stderr)
        return 2

    db = SessionLocal()
    try:
        for table_name, specs in sorted(by_table.items()):
            for _, spec in sorted(specs.items()):
                stats = notation_norm.rederive(
                    db, table_name, spec, chunk_size=args.chunk_size,
                    apply=args.apply)
                print(format_report(stats))
    finally:
        db.close()
    print("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
