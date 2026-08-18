"""Measure one declared source's ordering against the real table, BEFORE the backfill.

    conda run -n assy_manager python server/scripts/check_source_ordering.py dt_job

🔴 WHY A COMMAND AND NOT ONLY A SCREEN.  The ordering contract is enforced during the
backfill, so an ordering that does not identify a row fails hours into a run.  On
2026-08-18 the answer was obtained with a throwaway script written at the moment it was
needed; this is that script, kept, so the next person does not write it again.

The compile-time check asks only whether the ordering COVERS a key the catalog declares.
It cannot ask whether the data agrees, and for `dt_log` the declared composite key is
three columns that are all empty -- it passes every check and identifies nothing.

READ ONLY.  Reads `ledger_config.json`, `table_config.json` and the table.  No write, no
backfill, no cursor movement.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.database import SessionLocal                       # noqa: E402
from ledger import column_stats                                  # noqa: E402
from ledger.setup import DEFAULT_ONTOLOGY_ROOT, load_setup       # noqa: E402


def _thousands(value: int | None) -> str:
    return "-" if value is None else f"{value:,}"


def report(db, setup, source_id: str) -> int:
    sources = setup.bundle.to_mapping()["sources"]
    if source_id not in sources:
        print(f"unknown source {source_id!r}; declared: {', '.join(sorted(sources))}",
              file=sys.stderr)
        return 2
    source = sources[source_id]
    relation = source["relation"]
    driver = source["driver"]
    print(f"source {source_id}  ->  relation {relation}")

    table = setup.catalog.get(relation)
    if table is None:
        print(f"  relation {relation!r} is not declared in table_config.json",
              file=sys.stderr)
        return 2

    stats = column_stats.population(db, relation)
    total = stats["total_rows"]
    print(f"  rows: {total:,}\n")

    print("  columns (populated / total)")
    for column in sorted(stats["columns"], key=lambda item: (-item["populated"],
                                                             item["name"])):
        mark = "  <-- EMPTY" if column["empty"] else ""
        print(f"    {column['name']:<22} {_thousands(column['populated']):>10}"
              f" / {_thousands(total):<10} {column['data_type']}{mark}")

    empty = [column["name"] for column in stats["columns"] if column["empty"]]
    if empty:
        print(f"\n  {len(empty)} column(s) hold no value at all: {', '.join(empty)}")
        print("  Binding an entity key to one of these compiles, runs, and yields nothing.")

    print("\n  declared unique keys, MEASURED")
    ordering = column_stats.ordering_candidates(db, relation, table)
    for key in ordering["declared_keys"]:
        columns = ", ".join(key["columns"])
        if not key.get("measurable"):
            print(f"    [{columns}]  {key['reason']}")
            continue
        verdict = "UNIQUE" if key["unique"] else "NOT UNIQUE"
        print(f"    [{columns}]  {verdict}  "
              f"distinct {_thousands(key['distinct_combinations'])} / "
              f"{_thousands(key['total_rows'])}  "
              f"duplicate rows {_thousands(key['duplicate_rows'])}  "
              f"null-bearing {_thousands(key['null_bearing_rows'])}")
    print(f"    recommended: {ordering['recommended'] or 'NONE -- the catalog cannot '
                                                        'supply a working ordering'}")

    failures = 0
    for field in ("order_by", "cursor"):
        columns = (driver.get("cursor", {}).get("columns") if field == "cursor"
                   else driver.get(field))
        if not columns:
            continue
        print(f"\n  declared {field}: [{', '.join(columns)}]")
        try:
            result = column_stats.combination_uniqueness(db, relation, list(columns))
        except column_stats.ColumnStatsError as refusal:
            print(f"    {refusal.code}: {refusal.message}")
            failures += 1
            continue
        if result["unique"]:
            print(f"    UNIQUE  {_thousands(result['total_rows'])} rows, "
                  f"{_thousands(result['distinct_combinations'])} combinations")
        else:
            failures += 1
            print(f"    🔴 NOT UNIQUE -- the backfill will refuse this ordering")
            print(f"       duplicate rows        {_thousands(result['duplicate_rows'])}")
            print(f"       rows in dup groups    "
                  f"{_thousands(result['rows_in_duplicated_groups'])}")
            print(f"       largest group         {_thousands(result['largest_group'])}")
            print(f"       null-bearing rows     "
                  f"{_thousands(result['null_bearing_rows'])}")
    return 1 if failures else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_source_ordering.py",
        description="Measure a declared source's ordering against the real table. "
                    "Read only.")
    parser.add_argument("source_id")
    parser.add_argument("--root", default=None, metavar="PATH",
                        help=f"config root. Default: {DEFAULT_ONTOLOGY_ROOT.as_posix()}")
    args = parser.parse_args(argv)

    setup = load_setup(args.root or DEFAULT_ONTOLOGY_ROOT)
    db = SessionLocal()
    try:
        return report(db, setup, args.source_id)
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
