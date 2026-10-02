"""Time on the event edges, and the read cells the product answers (총괄 0c9b6e3c0 · db8f71231 · 261311e71).

Preview by default: for every active source, its time (the source's `read.occurred_at` and what each
mapping binds as `occurred_at`) and the read cells it writes that equal the product's default. Those
cells may stay - a written value is read as written.

`--apply --source <id>` moves ONE source's time onto its event edges: each mapping that binds
`occurred_at` gets the source's timezone, and `read.occurred_at` goes. Nothing else is written, and no
source is touched that is not named (총괄 0c9b6e3c0 ② · 015ef2aab: the operator chooses).
🔴 A source whose event edges name another time than the source reads (`dt_job`: basis ingested,
edges `event_time`) changes its atoms' time and event ids when moved - refused unless
`--change-atoms` is also given, and then every atom of that source has to be re-translated.

The file is written through `ledger.admin`'s atomic writer, which keeps a backup. Running it twice
is safe: a moved source has no `read.occurred_at` left to move.

`--drop-retired` removes the retired binding cells (`approval_status` and its two siblings, read by
nothing). Only when asked: it moves the bundle hash once (총괄 0c9b6e3c0 ② ㄱ).

Usage:
    python -m scripts.migrate_ledger_slim_sources [--apply] [--source <id> ...] [--change-atoms] [--drop-retired]
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class MigrationRefusal(Exception):
    pass


def _event_edges(source: dict) -> dict:
    """{sentence: the mapping's `occurred_at` binding} for every mapping that binds one."""
    from ledger.setup_bundle import OCCURRED_AT_ROLE

    mappings = ((source.get("bind") or {}).get("mappings") or {})
    return {sentence: (mapping.get("bind") or {})[OCCURRED_AT_ROLE]
            for sentence, mapping in sorted(mappings.items())
            if isinstance(mapping, dict) and OCCURRED_AT_ROLE in (mapping.get("bind") or {})}


def time_of(source: dict) -> dict:
    """What a source's time is today and what moving it would do."""
    read_time = (source.get("read") or {}).get("occurred_at")
    edges = _event_edges(source)
    columns = {binding.get("column") for binding in edges.values() if isinstance(binding, dict)}
    if read_time is None:
        verdict = "moved"
    elif not edges:
        verdict = "no event edge"
    elif len(columns) > 1:
        verdict = "edges name different columns"
    elif ("column" in read_time and columns == {read_time["column"]}
          and {binding.get("timezone") or read_time["timezone"] for binding in edges.values()}
          == {read_time["timezone"]}):
        verdict = "movable - atoms unchanged"
    else:
        verdict = "movable - atoms change"
    return {"read.occurred_at": read_time, "event edges": edges, "verdict": verdict}


def defaulted_cells(source: dict, catalog: dict) -> list[str]:
    """The read/map cells this source writes whose value is the product's default."""
    from ledger.setup_bundle import source_defaults

    bare = copy.deepcopy(source)
    found = []
    for clause, cell in (("read", "unit"), ("read", "identity"), ("read", "order_by"),
                         ("read", "registration_probe"), ("map", "unit")):
        if cell not in (bare.get(clause) or {}):
            continue
        written = bare[clause].pop(cell)
        if (source_defaults(bare, catalog).get(clause) or {}).get(cell) == written:
            found.append(f"{clause}.{cell}")
        bare[clause][cell] = written
    return found


def move_time(document: dict, source_id: str, change_atoms: bool = False) -> list[str]:
    source = (document.get("sources") or {}).get(source_id)
    if not isinstance(source, dict):
        raise MigrationRefusal(f"no source {source_id!r} in the declaration")
    time = time_of(source)
    verdict = time["verdict"]
    if verdict == "moved":
        return []
    if verdict == "no event edge":
        raise MigrationRefusal(
            f"{source_id}: no mapping binds occurred_at - removing read.occurred_at makes every atom "
            f"read the row's stored time. Not moved; write it by hand if that is meant")
    if verdict == "edges name different columns":
        raise MigrationRefusal(f"{source_id}: its event edges name different columns - one molecule "
                               f"has one time. Make them one column first")
    if verdict == "movable - atoms change" and not change_atoms:
        raise MigrationRefusal(
            f"{source_id}: its event edges name another time than the source reads "
            f"({json.dumps(time['read.occurred_at'])}) - moving changes every atom's time and event "
            f"id. Run again with --change-atoms to choose that, then re-translate the source")
    zone = time["read.occurred_at"]["timezone"]
    changes = []
    for sentence, binding in time["event edges"].items():
        if not binding.get("timezone"):
            binding["timezone"] = zone
            changes.append(f"{source_id}.bind.mappings.{sentence}.bind.occurred_at.timezone = {zone}")
    del source["read"]["occurred_at"]
    changes.append(f"{source_id}.read.occurred_at removed")
    return changes


def _count_key(node: Any, key: str) -> int:
    if isinstance(node, dict):
        return (key in node) + sum(_count_key(value, key) for value in node.values())
    if isinstance(node, list):
        return sum(_count_key(value, key) for value in node)
    return 0


def drop_retired(document: dict) -> list[str]:
    """Remove every retired binding cell (read by nothing) - only when the operator asks
    (`--drop-retired`, 총괄 0c9b6e3c0 ② ㄱ): it moves the bundle hash."""
    from ledger.setup_bundle import _RETIRED_BINDING_FIELDS

    def strip(node):
        if isinstance(node, dict):
            gone = sum(1 for key in _RETIRED_BINDING_FIELDS if node.pop(key, None) is not None)
            return gone + sum(strip(value) for value in node.values())
        if isinstance(node, list):
            return sum(strip(value) for value in node)
        return 0
    removed = sum(strip(source.get("bind")) for source in (document.get("sources") or {}).values()
                  if isinstance(source, dict))
    return [f"{removed} retired binding cells removed"] if removed else []


def report(document: dict, catalog: dict) -> list[str]:
    from ledger.setup_bundle import _RETIRED_BINDING_FIELDS

    lines, retired = [], 0
    for source_id, source in sorted((document.get("sources") or {}).items()):
        if not isinstance(source, dict) or source.get("status", "active") != "active":
            continue
        time = time_of(source)
        lines.append(f"{source_id}: time {json.dumps(time['read.occurred_at'])} | event edges "
                     f"{len(time['event edges'])} | {time['verdict']}")
        cells = defaulted_cells(source, catalog)
        if cells:
            lines.append(f"    written as the default (may stay): {', '.join(cells)}")
        counts = {field: _count_key(source.get("bind"), field) for field in _RETIRED_BINDING_FIELDS}
        if any(counts.values()):
            lines.append("    retired binding cells (read by nothing): " + ", ".join(
                f"{field} {n}" for field, n in counts.items() if n))
            retired += sum(counts.values())
    if retired:
        lines.append(f"retired binding cells: {retired}. --drop-retired removes them; the bundle hash moves "
                     f"once, so every source's NEW atoms carry a new translator version (atoms already "
                     f"written and cursor positions stay)")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write the declaration")
    parser.add_argument("--source", action="append", default=[], help="a source to move")
    parser.add_argument("--change-atoms", action="store_true",
                        help="also move a source whose event edges name another time")
    parser.add_argument("--drop-retired", action="store_true",
                        help="remove the retired binding cells (moves the bundle hash once)")
    args = parser.parse_args(argv)
    from ledger import admin
    from ledger.setup import live_physical_catalog
    from ledger.setup_bundle import SETUP_VERSION, upgrade_setup, validate_bundle_errors

    path = admin.sources_path()
    with open(path, encoding="utf-8") as handle:
        document = json.load(handle)
    catalog = dict(live_physical_catalog())
    old = document.get("setup_version") != SETUP_VERSION
    for line in report(upgrade_setup(document) if old else document, catalog):
        print(line)
    if old:
        print(f"{path} is setup_version {document.get('setup_version')} (read above as {SETUP_VERSION}). "
              f"Nothing is moved in it - Next: python -m scripts.migrate_ledger_config_to_v6 --apply")
        return 2 if (args.source or args.drop_retired) else 0
    if not args.source and not args.drop_retired:
        print("Preview only. Next: --apply --source <id> to move a source's time onto its event edges")
        return 0
    changes = drop_retired(document) if args.drop_retired else []
    try:
        for source_id in args.source:
            changes.extend(move_time(document, source_id, args.change_atoms))
    except MigrationRefusal as exc:
        print(f"REFUSED: {exc}")
        return 2
    issues = validate_bundle_errors(document, catalog=catalog)
    if issues:
        print(f"REFUSED: the moved declaration does not validate - {issues[0].code} at {issues[0].path}")
        return 2
    for line in changes or ["nothing to move"]:
        print(f"  {line}")
    if not args.apply or not changes:
        print("Preview only." if not args.apply else "Nothing written.")
        return 0
    backup = admin._atomic_write(path, document)
    print(f"wrote {path}" + (f" (backup {backup})" if backup else ""))
    print("Next: restart the server")
    return 0


if __name__ == "__main__":
    sys.exit(main())
