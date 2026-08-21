"""Bring a `ledger_config.json` up to `setup_version` 5: drop `packs`, name the predicate.

    packs                          ->  removed.  A Claim declared Roles and an `emit`
                                       clause, and both are derivable from the predicate
                                       it emitted -- see `setup_bundle.predicate_claim`
    bind.mappings.<s>.use          ->  bind.mappings.<s>.predicate, the vocabulary id the
                                       named Claim emitted
    bind.mappings.<s>.bind.<role>  ->  the Role names the predicate forces:
                                       `subject`, `target`/`value`, `occurred_at`, and
                                       each qualifier BY ITS DECLARED NAME
    setup_version                  ->  5

🔴 NO NAME IS GUESSED.  Every rename is read out of the `emit` clause that is being
deleted: `emit.subject` is `$child` in `lot-lineage@1/lineage`, so `child` becomes
`subject`; `emit.object.value` is `$count` in `dt-job@1/die_count`, so `count` becomes
`value`; `emit.object.qualifiers.slot` is `$slot`, so `slot` stays `slot`.  The clause is
the authority on which Role played which part, and it is still present while this runs.

🔴 AND THE DROP IS VERIFIED, NOT ASSUMED.  Before a Claim is discarded, the Roles it
declared are compared -- after renaming -- against the Roles its predicate derives, name
for name and required-flag for required-flag.  A file where they disagree is REFUSED with
the difference printed, because for that file the premise of the whole round ("the Claim
only restated the predicate") is false and dropping the section would lose something.

Usage:
    python -m scripts.migrate_ledger_config_to_v5 <path...> [--check]

`--check` reports what would change and writes nothing.  Running it twice is safe: a file
already in the target shape is rewritten unchanged.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


TARGET_SETUP_VERSION = 5

#: The Role names the target shape uses, kept next to the migration rather than imported
#: so this script keeps working on an old file after the code moves on again.  They agree
#: with `setup_bundle.SUBJECT_ROLE` and friends, and `test_ledger_setup_bundle` scores that
#: agreement.
SUBJECT_ROLE = "subject"
OCCURRED_AT_ROLE = "occurred_at"
TARGET_ROLE = "target"
VALUE_ROLE = "value"


class MigrationRefusal(RuntimeError):
    """A file this script will not rewrite, with the reason an operator can act on."""


def _role_name(ref: Any) -> str | None:
    if not isinstance(ref, str) or not ref.startswith("$"):
        return None
    return ref[1:-1] if ref.endswith("?") else ref[1:]


def _claim_of(document: dict[str, Any], use: Any) -> dict[str, Any] | None:
    if not isinstance(use, str) or "/" not in use:
        return None
    pack_id, claim_id = use.split("/", 1)
    pack = document.get("packs", {}).get(pack_id)
    if not isinstance(pack, dict):
        return None
    claim = pack.get("claims", {}).get(claim_id)
    return claim if isinstance(claim, dict) else None


def _renames(claim: dict[str, Any], where: str) -> dict[str, str]:
    """old Role name -> new Role name, read out of the Claim's own `emit` clause."""
    emission = claim.get("emit")
    if not isinstance(emission, dict):
        raise MigrationRefusal(f"{where}: claim has no emit clause")
    obj = emission.get("object") if isinstance(emission.get("object"), dict) else {}
    out: dict[str, str] = {}

    def take(ref: Any, new: str) -> None:
        old = _role_name(ref)
        if old is not None:
            out[old] = new

    take(emission.get("subject"), SUBJECT_ROLE)
    take(emission.get("occurred_at"), OCCURRED_AT_ROLE)
    take(obj.get("entity"), TARGET_ROLE)
    take(obj.get("value"), VALUE_ROLE)
    for qualifier, ref in (obj.get("qualifiers") or {}).items():
        take(ref, str(qualifier))
    return out


def _derived_roles(predicate: Any) -> dict[str, bool]:
    """Role name -> required, exactly as `setup_bundle.predicate_claim` derives them."""
    obj = predicate.get("object") if isinstance(predicate, dict) else None
    obj = obj if isinstance(obj, dict) else {}
    qualifiers = obj.get("qualifiers") if isinstance(obj.get("qualifiers"), dict) else {}
    out: dict[str, bool] = {SUBJECT_ROLE: True, OCCURRED_AT_ROLE: True}
    if obj.get("kind") == "entity_ref":
        out[TARGET_ROLE] = True
    elif obj.get("kind") in ("value", "event_ref"):
        out[VALUE_ROLE] = True
    for name in qualifiers.get("required") or ():
        out[str(name)] = True
    for name in qualifiers.get("optional") or ():
        out.setdefault(str(name), False)
    return out


def _rewrite_mapping(document: dict[str, Any], where: str,
                     mapping: dict[str, Any]) -> None:
    claim = _claim_of(document, mapping.get("use"))
    if claim is None:
        raise MigrationRefusal(
            f"{where}.use: {mapping.get('use')!r} names no claim in this file's packs")
    predicate_id = claim.get("emit", {}).get("predicate")
    predicate = document.get("vocabulary", {}).get(predicate_id)
    if not isinstance(predicate, dict):
        raise MigrationRefusal(
            f"{where}.use: claim emits unknown predicate {predicate_id!r}")

    renames = _renames(claim, where)
    declared = claim.get("roles") if isinstance(claim.get("roles"), dict) else {}
    renamed_roles = {
        renames.get(role_id, role_id): bool(role.get("required"))
        for role_id, role in declared.items() if isinstance(role, dict)
    }
    derived = _derived_roles(predicate)
    if renamed_roles != derived:
        raise MigrationRefusal(
            f"{where}: claim {mapping.get('use')!r} does not restate predicate "
            f"{predicate_id!r} -- claim roles {sorted(renamed_roles.items())} vs derived "
            f"{sorted(derived.items())}.  The packs section carries something here that "
            f"the vocabulary cannot say, so it is not dropped")

    bindings = mapping.get("bind") if isinstance(mapping.get("bind"), dict) else {}
    moved: dict[str, Any] = {}
    for role_id in sorted(bindings, key=str):
        new_id = renames.get(role_id, role_id)
        if new_id in moved:
            raise MigrationRefusal(
                f"{where}.bind: {role_id!r} and another role both become {new_id!r}")
        moved[new_id] = bindings[role_id]
    mapping.pop("use", None)
    mapping["predicate"] = predicate_id
    mapping["bind"] = {key: moved[key] for key in sorted(moved)}


def _name_the_predicate(document: dict[str, Any]) -> None:
    for source_id, source in document.get("sources", {}).items():
        profile = source.get("bind")
        if not isinstance(profile, dict):
            continue
        mappings = profile.get("mappings")
        if not isinstance(mappings, dict):
            continue
        for sentence, mapping in mappings.items():
            if not isinstance(mapping, dict) or "use" not in mapping:
                continue
            _rewrite_mapping(
                document, f"sources.{source_id}.bind.mappings.{sentence}", mapping)


# ----------------------------------------------------------------------------- driver


def migrate(document: dict[str, Any]) -> dict[str, Any]:
    """Return the v5 shape of one parsed config.  Idempotent."""
    out = json.loads(json.dumps(document, ensure_ascii=False))
    _name_the_predicate(out)
    out.pop("packs", None)
    out["setup_version"] = TARGET_SETUP_VERSION
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
        text = json.dumps(after, ensure_ascii=False, indent=2) + "\n"
        unchanged = text == raw
        if args.check:
            print(f"{path}: {'unchanged' if unchanged else 'would rewrite'} "
                  f"(setup_version {before.get('setup_version')} -> "
                  f"{after['setup_version']})")
            continue
        if not unchanged:
            path.write_text(text, encoding="utf-8")
        print(f"{path}: {'unchanged' if unchanged else 'migrated'} "
              f"(setup_version {before.get('setup_version')} -> {after['setup_version']})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
