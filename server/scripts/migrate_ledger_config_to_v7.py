"""Write a deployment's ledger setup short - setup_version 7 (소유자 10-13 「read 관련 다 빼고 소스 맵핑만」,
10-14 «ㄹ»): each source becomes {table, status?, attributes?, sentences}, by
`ledger.setup_bundle.shorten_setup`, whose pair `expand_short_form` is how the loader reads it back.

Each source is said one way:

    same     its declaration reads back to the same fingerprint - its atoms keep their identity
    mixes    it reads back on the product's defaults (the table's shortest unique key, the event
             edges' time), so rows translated from here on are named on those; the atoms written
             before stay as they are, and an edited row's old atoms are withdrawn by the row it
             came from (총괄 10-14 ㄹ). To align a source at once: its whole-source re-translate
    dropped  retired and not writable short - it reads nothing, and its atoms stay
    refused  not writable short, with why and what to do - THE FILE IS NOT WRITTEN

Preview by default; `--apply` writes the file through `ledger.admin`'s atomic writer, which keeps a
backup. A v7 file is left alone.

Usage:
    python -m scripts.migrate_ledger_config_to_v7 [--apply]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _snapshot(document: dict, catalog):
    """The document as the ledger process loads it - `load_setup`, where a broken source falls
    alone and by name (S-177 ②) - so a source the loader refuses today is said, not fatal."""
    import logging
    import tempfile

    from ledger.setup import load_setup
    from ledger.setup_bundle import CONFIG_FILENAME

    with tempfile.TemporaryDirectory() as root:
        with open(os.path.join(root, CONFIG_FILENAME), "w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False)
        logging.disable(logging.CRITICAL)       # its per-source lines are this script's lines below
        try:
            return load_setup(root, catalog=catalog).snapshot
        finally:
            logging.disable(logging.NOTSET)


def _stamps(snapshot) -> dict[str, str]:
    from ledger.setup_registry import cursor_translator_version

    return {source: cursor_translator_version(snapshot, source)
            for source, plan in snapshot.source_plans.items() if plan.runs}


def _without_retired_words(document: dict) -> dict:
    """The long document without the binding words that retired for holding one value
    (`approval_status` …) - they reach no atom, and the short form does not write them."""
    from ledger.setup_bundle import _RETIRED_BINDING_FIELDS

    def strip(value):
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items() if k not in _RETIRED_BINDING_FIELDS}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value
    return {**document, "sources": strip(document.get("sources") or {})}


def _read_moves(before, after) -> list[tuple[str, Any, Any]]:
    """The read cells an atom's identity is made of that the short form answers differently."""
    out = []
    for cell in ("identity", "order_by", "occurred_at"):
        was, now = (getattr(plan.driver, cell, None) for plan in (before, after))
        if was != now:
            out.append((cell, _spoken(was), _spoken(now)))
    return out


def _spoken(value) -> str:
    if hasattr(value, "basis"):                          # the read's time: a basis or a column
        return f"stored {value.basis}" if value.basis else value.column
    if isinstance(value, (list, tuple)):
        return "+".join(map(str, value))
    return json.dumps(value, ensure_ascii=False, default=str) if value is not None else "-"


def _refusal(plan) -> str:
    said = plan.refusal or {}
    return str(said.get("message") or said.get("code") or said)[:200]


def convert(document: dict, catalog) -> tuple[dict, list[str], bool]:
    """(the short document, one line per source, written?) - `written` False is a refusal."""
    from declaration_names import fold_versions
    from ledger.setup_bundle import (DROPPED, REFUSED, SHORT_FORM_VERSION, LedgerSetupValidationError,
                                     shorten_setup, upgrade_setup)

    document = fold_versions(upgrade_setup(document))
    short, verdicts = shorten_setup(document)
    width = max(map(len, verdicts), default=0)
    lines = [f"  {name:<{width}} refused  - {why}" for name, (verdict, why) in verdicts.items()
             if verdict == REFUSED]
    lines += [f"  {name:<{width}} dropped  - retired and {why.split(' - ')[0]}; its atoms stay"
              for name, (verdict, why) in verdicts.items() if verdict == DROPPED]
    if any(verdict == REFUSED for verdict, _why in verdicts.values()):
        return short, lines, False
    try:
        today, written = _snapshot(_without_retired_words(document), catalog), _snapshot(short, catalog)
    except LedgerSetupValidationError as exc:
        return short, lines + [f"  the short file does not load: {exc}"], False
    before, after = _stamps(today), _stamps(written)
    stopped = sorted(set(before) - set(after))
    if stopped:
        return short, lines + [f"  {name:<{width}} refused  - the short file stops it: "
                               f"{_refusal(written.source_plans[name])}" for name in stopped], False
    lines += [f"  {name:<{width}} loader   - refused by the loader today, and after: "
              f"{_refusal(today.source_plans[name])}"
              for name in sorted(set(today.source_plans) - set(before))
              if today.source_plans[name].status == "active"]
    for name in sorted(before):
        if before[name] == after.get(name):
            lines.append(f"  {name:<{width}} same     - its atoms keep their identity")
            continue
        moved = ", ".join(f"{cell} {was} -> {now}" for cell, was, now in _read_moves(
            today.source_plans[name], written.source_plans[name])) or "its declaration"
        lines.append(f"  {name:<{width}} mixes    - {moved}: rows from here on are named so, atoms "
                     f"written before stay. At once: python server/ledger/backfill.py --source "
                     f"{name} --whole-source")
    lines += [f"  {name:<{width}} retired  - written short, still retired"
              for name, source in sorted(short["sources"].items()) if source.get("status") == "retired"]
    assert short["setup_version"] == SHORT_FORM_VERSION
    return short, lines, True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write the file")
    args = parser.parse_args(argv)
    from ledger import admin
    from ledger.setup import live_physical_catalog
    from ledger.setup_bundle import SHORT_FORM_VERSION

    path = admin.sources_path()
    with open(path, encoding="utf-8") as handle:
        document = json.load(handle)
    if document.get("setup_version") == SHORT_FORM_VERSION:
        print(f"Already v{SHORT_FORM_VERSION} - nothing to change.")
        return 0
    short, lines, written = convert(document, live_physical_catalog())
    print(f"{path}")
    for line in lines:
        print(line)
    if not written:
        print("REFUSED - the file is not written. Fix the refused lines, then run again.")
        return 2
    if not args.apply:
        print("Preview only. Next: run again with --apply")
        return 0
    backup = admin._atomic_write(path, short)
    print(f"wrote {path}" + (f" (backup {backup})" if backup else ""))
    print("Next: restart the launcher (the ledger process reads the file at start)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
