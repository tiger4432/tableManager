"""Operator's door to the retroactive enrichment backfill - report, then optionally write.

The logic lives in ``server/enrichment_backfill.py`` (why the backfill exists, what
it refuses to touch, and the provenance invariants are documented there). The same
module is what ``GET /admin/retroactive/enrichment_backfill/count`` and the queued
run behind ``POST /admin/retroactive/enrichment_backfill/run`` call, so this script
and the admin button can never drift into two different definitions of "new derived
identity".

This file is the human path: argparse, the printed report, and the exit code.
``server/scripts`` is on no runtime process's
``sys.path``, so anything a route needs has to live in ``server/``.

Usage (dry-run is the default - report first, act only on explicit flag):

    conda run -n assy_manager python server/scripts/backfill_enrichment.py <rule_name>
    conda run -n assy_manager python server/scripts/backfill_enrichment.py <rule_name> --apply
    conda run -n assy_manager python server/scripts/backfill_enrichment.py <rule_name> --apply --limit 100

Flags:
    --apply           actually write the new derived rows (default: dry-run report)
    --limit N         cap the number of NEW derived identities created per run
    --force-disabled  run even if the rule has "enabled": false
    --chunk-size N    source scan chunk size (default 1000)

EXIT CODES
    0  the report was produced (dry-run), or the rows were written (--apply)
    2  refused: bad --chunk-size, no table_config, or the rule was rejected
"""
import argparse
import os
import sys

# Standalone bootstrap: make server/ importable (same pattern every script in this
# directory uses; `chain_replay_cli.py` is the nearest sibling).
_SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)

import enrichment_backfill  # noqa: E402  (the single implementation; see its docstring)
from enrichment_backfill import (  # noqa: E402
    DEFAULT_CHUNK_SIZE, SAMPLE_NEW_KEYS, BackfillRefused,
)


def format_report(stats: dict, limit: int = None) -> str:
    lines = [
        "",
        f"=== enrichment backfill {'APPLY' if stats['mode'] == 'apply' else 'DRY-RUN'} "
        f"- rule '{stats['rule']}' ===",
        f"  source table          : {stats['source_table']}",
        f"  derived table         : {stats['derived_table']}",
        f"  source rows scanned   : {stats['rows_scanned']}",
        # Names what it counts, because it no longer counts what it used to.
        # "blank key" meant ANY blank key column until the 2026-08-05 partial-key
        # ruling; those rows are now WORKED, so this line would have quietly gone
        # to zero on an operator's screen with the same label above it.
        f"  skipped (no key at all): {stats['skipped_no_key']}",
        f"  distinct combinations : {stats['distinct_combinations']}",
        f"  already derived       : {stats['already_derived']}  (NOT touched)",
    ]
    if stats["partial_key_combinations"]:
        lines.append(
            f"  ...on a PARTIAL key   : {stats['partial_key_combinations']} "
            f"(new identities whose decision key is only partly present - these "
            f"used to be dropped)"
        )
    if stats["skipped_unexpressible_key"]:
        lines.append(
            f"  partial keys REFUSED  : {stats['skipped_unexpressible_key']} "
            f"(the derived table's key declaration cannot give a partial key its "
            f"own identity - see the log line for the one config change that "
            f"fixes it; forcing them would merge rows on top of each other)"
        )
    if stats["mode"] == "apply":
        lines.append(f"  new identities created: {stats['created_rows']}")
        if stats["updated_rows"]:
            lines.append(
                f"  refined in later chunks: {stats['updated_rows']} "
                f"(rows created by this run only)"
            )
        if stats["limit_skipped"]:
            lines.append(
                f"  skipped by --limit    : {stats['limit_skipped']} "
                f"(re-run to continue)"
            )
    else:
        would = stats["new_combinations"]
        lines.append(f"  new (would create)    : {would}")
        if limit is not None and stats["limit_skipped"]:
            lines.append(
                f"  ... of which beyond --limit {limit}: {stats['limit_skipped']}"
            )
        if would:
            lines.append(
                "  -> re-run with --apply to create them "
                "(target fields stay blank; the worklist picks them up)"
            )
    if stats["sample_new_keys"]:
        lines.append(f"  sample new keys       : {stats['sample_new_keys'][:SAMPLE_NEW_KEYS]}")
    lines.append("")
    return "\n".join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Retroactively apply an enrichment rule to source rows that predate "
            "it. Dry-run by default; nothing is written without --apply."
        )
    )
    parser.add_argument("rule_name", help="rule name as declared in enrichment_rules.json")
    parser.add_argument("--apply", action="store_true",
                        help="write the new derived rows (default: report only)")
    parser.add_argument("--limit", type=int, default=None,
                        help="cap the number of NEW derived identities per run")
    parser.add_argument("--force-disabled", action="store_true",
                        help="run even if the rule is disabled (enabled: false)")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE,
                        help=f"source scan chunk size (default {DEFAULT_CHUNK_SIZE})")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.chunk_size <= 0:
        print(f"REFUSED: --chunk-size must be positive (got {args.chunk_size})")
        return 2

    from database import crud, models
    from database.database import SessionLocal

    if not crud.TABLE_CONFIG:
        print("REFUSED: table_config.json is empty or missing - nothing is registered")
        return 2
    models.init_dynamic_models(crud.TABLE_CONFIG)

    try:
        rule = enrichment_backfill.load_rule(args.rule_name, crud.TABLE_CONFIG,
                                             force_disabled=args.force_disabled)
    except BackfillRefused as e:
        print(f"REFUSED: {e}")
        return 2

    db = SessionLocal()
    try:
        stats = enrichment_backfill.run_backfill(
            db, rule, apply=args.apply, limit=args.limit, chunk_size=args.chunk_size)
        print(format_report(stats, limit=args.limit))
        return 0
    except BackfillRefused as e:
        print(f"REFUSED: {e}")
        return 2
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
