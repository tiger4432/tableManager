"""Drop `layer` from every `vocabulary` item of a `ledger_config.json`.

    vocabulary.<predicate>.layer  ->  removed.  Only one value could ever legally be
                                      written here, so the square carried no decision.
    setup_version                 ->  UNCHANGED.  See the note at the bottom.

🔴 WHY THE KEY GOES, AND WHY IT IS NOT "NOBODY READS IT".  It IS read:
`ledger.config_explorer._node_description` builds a predicate node's on-screen line from
`raw.get('layer', 'ontology')`.  The reason it goes is that `ledger.vocabulary` declares
`LAYER_CANONICAL` / `LAYER_ONTOLOGY` and makes `EDITABLE_LAYER` the ontology one ALONE --
`canonical` is code plus a ruling and is not reachable from a declaration.  A square with
exactly one legal value has zero freedom, which is what makes it a copy of the code rather
than a contract with it.  And the reader needs no change: its default IS that one legal
value, so the description string is byte-identical once the field is gone.

🔴 THE DROP IS VERIFIED, NOT ASSUMED.  Before a `layer` is discarded its value is compared
against `ontology`.  A file that declares anything else -- `canonical` most of all -- is
REFUSED with the value printed, because for that file the premise of this round ("the key
could only ever say `ontology`") is false, and dropping it would lose the one thing it
said.  This is the same discipline `migrate_ledger_config_to_v5` applies before it drops
`packs`: a section is only deleted once the file has been asked whether it agrees.

🔴 `setup_version` IS DELIBERATELY NOT BUMPED, and this is the reasoning, not an oversight.
`setup_bundle` pins the version by EQUALITY at two sites (`validate_bundle_errors` and
`_root_document_errors`): exactly one value is accepted and there is no version-conditional
branch anywhere downstream -- the compiler only copies the number into the snapshot.  So
the number can never route between two shapes; its only job in a refusal is to be a label.
An un-migrated file is already refused, by name and at its own path, once per predicate
(`unknown_field` at `bundle.vocabulary.<id>.layer`).  Bumping would add a second refusal
saying the same thing while also invalidating every file whose ONLY fault is the number --
including the backups an operator restores to diagnose this very migration.

Usage:
    python -m scripts.migrate_ledger_config_drop_vocabulary_layer <path...> [--check]

`--check` reports what would change and writes nothing.  Running it twice is safe: a file
already in the target shape is rewritten unchanged.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


#: The one value a declaration could legally carry.  Kept next to the migration rather
#: than imported so this script keeps working on an old file after the code moves on
#: again -- the same reason `migrate_ledger_config_to_v5` re-states its Role names.  It
#: agrees with `ledger.vocabulary.EDITABLE_LAYER`.
EDITABLE_LAYER = "ontology"

FIELD = "layer"


class MigrationRefusal(RuntimeError):
    """A file this script will not rewrite, with the reason an operator can act on."""


def _drop_layer(document: dict[str, Any]) -> int:
    """Remove `layer` from every vocabulary item.  Returns how many were removed."""
    vocabulary = document.get("vocabulary")
    if not isinstance(vocabulary, dict):
        return 0
    removed = 0
    for predicate_id, item in vocabulary.items():
        if not isinstance(item, dict) or FIELD not in item:
            continue
        declared = item[FIELD]
        if declared != EDITABLE_LAYER:
            raise MigrationRefusal(
                f"vocabulary.{predicate_id}.{FIELD}: declares {declared!r}, not "
                f"{EDITABLE_LAYER!r}.  This key is being dropped because "
                f"{EDITABLE_LAYER!r} was the only value a declaration could legally "
                f"carry; this file says otherwise, so dropping it would lose what it "
                f"says.  Decide what that predicate's layer means before migrating")
        item.pop(FIELD)
        removed += 1
    return removed


# ----------------------------------------------------------------------------- driver


def migrate(document: dict[str, Any]) -> dict[str, Any]:
    """Return the target shape of one parsed config.  Idempotent."""
    out = json.loads(json.dumps(document, ensure_ascii=False))
    _drop_layer(out)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--check", action="store_true",
                        help="report what would change and write nothing")
    args = parser.parse_args(argv)

    failures = 0
    for path in args.paths:
        raw = path.read_text(encoding="utf-8")
        try:
            before = json.loads(raw)
            after = migrate(before)
        except MigrationRefusal as refusal:
            print(f"{path}: REFUSED {refusal}")
            failures += 1
            continue
        dropped = sum(
            1 for item in (before.get("vocabulary") or {}).values()
            if isinstance(item, dict) and FIELD in item)
        text = json.dumps(after, ensure_ascii=False, indent=2) + "\n"
        unchanged = text == raw
        if args.check:
            print(f"{path}: {'unchanged' if unchanged else 'would rewrite'} "
                  f"({FIELD} dropped from {dropped} predicate(s))")
            continue
        if not unchanged:
            path.write_text(text, encoding="utf-8")
        print(f"{path}: {'unchanged' if unchanged else 'migrated'} "
              f"({FIELD} dropped from {dropped} predicate(s))")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
