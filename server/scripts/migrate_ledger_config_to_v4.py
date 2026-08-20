"""Bring a `ledger_config.json` up to `setup_version` 4, in one pass.

Four rounds landed on 2026-08-20/21 and each changed the file's shape.  The first three
were migrated BY HAND because the shape was still moving and a script written then would
only have been rewritten; this one carries all four, because the shape has arrived.

    source_preparers / mappers  ->  the body sits inside the source that uses it
    profiles                    ->  the body sits inside the source that binds it
    driver                      ->  read . prepare . map . bind
    emits / packs               ->  removed; both were restatements of `use`
    binding_origin: user_declared -> removed; it is the default the reader supplies
    mappings: [ {mapping_id} ]  ->  { "<sentence>": {...} }
    setup_version               ->  4

Every step is IDEMPOTENT: a file already in the target shape is rewritten unchanged, so
the live config, the sample, and an operator's year-old backup all take the same command.

🔴 THE SENTENCE IS DERIVED, NEVER GUESSED (brief: 「`sentence` 를 «추측해서» 채우지 말 것」).
A mapping's key is which sentence its source's MAPPER resolves to it, and the only truth
about that is the rule the mapper used before this round: match the Claim's structure --
object-ness, qualifier names, and the two entity-type spellings -- exactly as
`setup_bundle._sentence_signature` did, since that function existed to be the same
expression.  `_LEGACY_SENTENCES` below is the pre-round shape declaration of each mapper
that HAS shapes, and nothing here reads a `mapping_id` to decide a name.  A mapping that
resolves to no shape, or to a shape another mapping already took, is REPORTED with its id
and the file is left alone.

A mapper that declares no shapes at all -- `declarative-role`, which says every mapping in
the profile and asks the declaration nothing -- has no sentence to resolve.  Its mappings
keep the name they already have as their key.  That is not a guess about which sentence
they realize; it is the observation that there is none to be wrong about, and the key has
to be something.

Usage:
    python -m scripts.migrate_ledger_config_to_v4 <path...> [--check]

`--check` reports what would change and writes nothing.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


TARGET_SETUP_VERSION = 4
_DEFAULT_BINDING_ORIGIN = "user_declared"

#: Every sentence each pre-round mapper declared, with the discriminators the pre-round
#: `ProfileSentences._resolve` matched on.  `subject_is` names the sentence whose entity
#: binding tells this one's subject apart, and which end of it to read -- which is how the
#: mapper itself told its two first-sight announcements apart, by asking the declaration
#: rather than by spelling `Lot@1`.  Written as data because the code that used to hold it
#: is what this round replaces.
_LEGACY_SENTENCES: dict[str, tuple[dict[str, Any], ...]] = {
    "lot-event-role": (
        {"name": "in_slot", "has_object": True, "qualifiers": ("slot",)},
        {"name": "descent", "has_object": True, "qualifiers": ()},
        {"name": "split_slot_carry", "has_object": True,
         "qualifiers": ("from", "to", "wafer")},
        {"name": "merge_slot_join", "has_object": True,
         "qualifiers": ("from", "to", "wafer")},
        {"name": "first_sight_holder", "has_object": False, "qualifiers": (),
         "subject_is": ("in_slot", "subject")},
        {"name": "first_sight_item", "has_object": False, "qualifiers": (),
         "subject_is": ("in_slot", "object")},
    ),
    "dt-job-role": (
        {"name": "register", "has_object": False, "qualifiers": ()},
        {"name": "counted", "has_object": True, "qualifiers": ()},
    ),
}


class MigrationRefusal(Exception):
    """Named, addressed refusal: the file is not touched."""


# ------------------------------------------------------------------ shape (rounds 1-3)


def _absorb_bodies(document: dict[str, Any]) -> None:
    """`source_preparers` / `mappers` / `profiles` move inside the source that uses them."""
    preparers = document.pop("source_preparers", None) or {}
    mappers = document.pop("mappers", None) or {}
    profiles = document.pop("profiles", None) or {}
    for source_id, source in document.get("sources", {}).items():
        driver = source.get("driver")
        if isinstance(driver, dict):
            preparation = driver.get("preparation")
            if isinstance(preparation, dict):
                preparer_id = preparation.get("preparer_id")
                body = dict(preparers.get(preparer_id) or {})
                if not body:
                    raise MigrationRefusal(
                        f"sources.{source_id}.driver.preparation.preparer_id: "
                        f"no source_preparers entry named {preparer_id!r}")
                for key, value in preparation.items():
                    if key != "preparer_id":
                        body[key] = value
                driver["preparation"] = body
            mapper_id = driver.pop("mapper_id", None)
            if mapper_id is not None:
                body = dict(mappers.get(mapper_id) or {})
                if not body:
                    raise MigrationRefusal(
                        f"sources.{source_id}.driver.mapper_id: "
                        f"no mappers entry named {mapper_id!r}")
                driver["mapper"] = body
        profile_id = source.pop("profile_id", None)
        if profile_id is not None:
            body = dict(profiles.get(profile_id) or {})
            if not body:
                raise MigrationRefusal(
                    f"sources.{source_id}.profile_id: "
                    f"no profiles entry named {profile_id!r}")
            body.pop("source", None)
            source["profile"] = body


def _split_driver(document: dict[str, Any]) -> None:
    """`driver` becomes the four steps a source actually performs, in that order."""
    for source_id, source in document.get("sources", {}).items():
        driver = source.pop("driver", None)
        profile = source.pop("profile", None)
        if driver is None and "read" not in source:
            raise MigrationRefusal(
                f"sources.{source_id}: neither `driver` nor `read` is declared")
        if driver is not None:
            prepare = driver.pop("preparation", None)
            mapper = driver.pop("mapper", None)
            if prepare is None or mapper is None:
                raise MigrationRefusal(
                    f"sources.{source_id}.driver: a source declares both a preparation "
                    f"and a mapper")
            source["read"] = driver
            source["prepare"] = prepare
            source["map"] = mapper
        if profile is not None:
            source["bind"] = profile
        # `emits` restated `bind.mappings.<sentence>.use`; `packs` restated the packs those
        # refs name.  Both are compiled from the refs now.
        source.get("map", {}).pop("emits", None)
        source.get("bind", {}).pop("packs", None)
        for key in ("relation", "read", "prepare", "map", "bind"):
            if key in source:
                source[key] = source.pop(key)


def _strip_default_binding_origin(value: Any) -> Any:
    if isinstance(value, dict):
        out = {
            key: _strip_default_binding_origin(item)
            for key, item in value.items()
            if not (key == "binding_origin" and item == _DEFAULT_BINDING_ORIGIN)
        }
        return out
    if isinstance(value, list):
        return [_strip_default_binding_origin(item) for item in value]
    return value


# ------------------------------------------------------- the sentence key (this round)


def _claim_of(document: dict[str, Any], use: Any) -> dict[str, Any] | None:
    if not isinstance(use, str) or "/" not in use:
        return None
    pack_id, claim_id = use.split("/", 1)
    pack = document.get("packs", {}).get(pack_id)
    if not isinstance(pack, dict):
        return None
    claim = pack.get("claims", {}).get(claim_id)
    return claim if isinstance(claim, dict) else None


def _role_name(ref: Any) -> str | None:
    if not isinstance(ref, str) or not ref.startswith("$"):
        return None
    return ref[1:-1] if ref.endswith("?") else ref[1:]


def _signature(document: dict[str, Any], mapping: dict[str, Any]
               ) -> tuple[bool, tuple[str, ...], Any, Any] | None:
    """What the pre-round resolver compared, computed from the declaration.

    Deliberately the same four values `setup_bundle._sentence_signature` produced, in the
    same order: object-ness, sorted qualifier names, subject entity type, object entity
    type.  `None` means the mapping was unreachable through `ProfileSentences` at all.
    """
    claim = _claim_of(document, mapping.get("use"))
    if claim is None:
        return None
    emission = claim.get("emit")
    if not isinstance(emission, dict):
        return None
    obj = emission.get("object") if isinstance(emission.get("object"), dict) else {}
    subject_role = _role_name(emission.get("subject"))
    binding = mapping["bind"].get(subject_role) if subject_role else None
    if not isinstance(binding, dict) or binding.get("kind") != "entity":
        return None
    object_role = _role_name(obj.get("entity"))
    object_binding = mapping["bind"].get(object_role) if object_role else None
    return (
        obj.get("entity", obj.get("value")) is not None,
        tuple(sorted(obj.get("qualifiers", {}))),
        binding.get("entity_type"),
        (object_binding.get("entity_type")
         if isinstance(object_binding, dict) else None),
    )


def _resolve_sentences(document: dict[str, Any], source_id: str,
                       source: dict[str, Any]) -> dict[str, str]:
    """Which sentence each mapping realizes: mapping_id -> sentence.

    Runs the pre-round structure match, shape by shape, and refuses rather than choosing
    when a shape matches nothing or more than one mapping.
    """
    mappings = source.get("bind", {}).get("mappings")
    if not isinstance(mappings, list):
        return {}
    implementation = source.get("map", {}).get("implementation_id")
    shapes = _LEGACY_SENTENCES.get(implementation)
    ids = [str(mapping.get("mapping_id")) for mapping in mappings]
    if shapes is None:
        # No shapes to resolve: this mapper says every mapping and asks nothing.
        return {mapping_id: mapping_id for mapping_id in ids}

    declared = {
        str(mapping.get("mapping_id")): str(mapping["sentence"])
        for mapping in mappings
        if str(mapping.get("sentence") or "").strip()
    }
    signatures = {
        str(mapping.get("mapping_id")): _signature(document, mapping)
        for mapping in mappings
    }
    out: dict[str, str] = dict(declared)
    taken = set(declared.values())
    for shape in sorted(shapes, key=lambda item: "subject_is" in item):
        name = shape["name"]
        if name in taken:
            continue
        candidates = [
            mapping_id for mapping_id, signature in signatures.items()
            if mapping_id not in out and signature is not None
            and signature[0] is shape["has_object"]
            and signature[1] == tuple(sorted(shape["qualifiers"]))
            and _subject_matches(shape, signature, out, signatures)
        ]
        if len(candidates) != 1:
            raise MigrationRefusal(
                f"sources.{source_id}.bind.mappings: sentence {name!r} of mapper "
                f"{implementation!r} matches {len(candidates)} mappings {candidates}; "
                f"a name is not invented here -- report it")
        out[candidates[0]] = name
        taken.add(name)
    missing = [mapping_id for mapping_id in ids if mapping_id not in out]
    if missing:
        raise MigrationRefusal(
            f"sources.{source_id}.bind.mappings: no sentence of mapper "
            f"{implementation!r} resolves to {missing}")
    return out


def _subject_matches(shape: dict[str, Any], signature: tuple[Any, ...],
                     resolved: dict[str, str],
                     signatures: dict[str, Any]) -> bool:
    """Apply the one discriminator a call site used to pass: a learned entity type."""
    discriminator = shape.get("subject_is")
    if discriminator is None:
        return True
    peer_name, end = discriminator
    peer = next((signature_of for mapping_id, signature_of in signatures.items()
                 if resolved.get(mapping_id) == peer_name), None)
    if peer is None:
        return False
    return signature[2] == (peer[2] if end == "subject" else peer[3])


def _key_mappings_by_sentence(document: dict[str, Any]) -> None:
    for source_id, source in document.get("sources", {}).items():
        profile = source.get("bind")
        if not isinstance(profile, dict):
            continue
        mappings = profile.get("mappings")
        if isinstance(mappings, dict):
            continue
        sentences = _resolve_sentences(document, source_id, source)
        keyed: dict[str, Any] = {}
        for mapping in mappings:
            mapping_id = str(mapping.get("mapping_id"))
            sentence = sentences[mapping_id]
            if sentence in keyed:
                raise MigrationRefusal(
                    f"sources.{source_id}.bind.mappings: {mapping_id!r} and another "
                    f"mapping both realize {sentence!r}; a map cannot hold both")
            keyed[sentence] = {
                key: value for key, value in mapping.items()
                if key not in ("mapping_id", "sentence")
            }
        profile["mappings"] = {key: keyed[key] for key in sorted(keyed)}


# ----------------------------------------------------------------------------- driver


def migrate(document: dict[str, Any]) -> dict[str, Any]:
    """Return the v4 shape of one parsed config.  Idempotent."""
    out = json.loads(json.dumps(document, ensure_ascii=False))
    _absorb_bodies(out)
    _split_driver(out)
    _key_mappings_by_sentence(out)
    out = _strip_default_binding_origin(out)
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
        try:
            before = json.loads(path.read_text(encoding="utf-8"))
            after = migrate(before)
        except MigrationRefusal as refusal:
            print(f"{path}: REFUSED {refusal}")
            failures += 1
            continue
        text = json.dumps(after, ensure_ascii=False, indent=2) + "\n"
        unchanged = text == path.read_text(encoding="utf-8")
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
