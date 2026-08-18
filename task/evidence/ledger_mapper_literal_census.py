"""Count the DECLARATION literals a mapper file still carries, by AST.

The pass criterion of the mapper restandardization is "the mapper does not know the
declarations", and that is only checkable against a number taken the same way before and
after.  So this collects every string constant in the file and classifies it against the
four vocabularies the LIVE config declares -- not against a hand-written list, which
would drift from the config the moment either changed.

  mapping_id    profile mapping identifiers        target 0   (pure wiring)
  claim_ref     claim references                   target 0   (pure wiring)
  predicate     ledger vocabulary words            see below
  entity type   entity type spellings              target 0   (pure wiring)
  qualifier     business vocabulary                KEPT      (slot, from, to, wafer)

Usage:  python ledger_mapper_literal_census.py [mapper.py] [ledger_config.json]
"""
import ast
import collections
import json
import pathlib
import sys

sys.stdout.reconfigure(encoding="utf-8")

MAPPER = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else
                      r"C:\Users\kk980\Developments\assyManager\server\mappers"
                      r"\ledger_v2_lot_event_role_mapper.py")
CONFIG = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else
                      r"C:\Users\kk980\Developments\assyManager\server\config\ontology"
                      r"\ledger_config.json")


def _unversioned(name):
    """`derived_from@1` -> `derived_from`. The mapper writes the bare spelling and
    `_base()` strips the version, so a census that compared versioned names would score
    every predicate literal as absent and report a false 0."""
    return str(name).split("@")[0]


def vocabularies():
    """Read the four name sets out of the LIVE config, never out of a literal list.

    🔴 MEASURED, NOT ASSUMED. The first version of this looked for predicates in a
    `claim["predicate"]` key and qualifiers in `claim["qualifiers"]`; neither exists.
    Predicates live in `claims[<name>].emit.predicate` and are VERSIONED, and qualifiers
    are the claim's `roles` entries of kind `attribute`. Against the live config that
    mistake scored predicates 3 instead of 5 and qualifiers 0 instead of 7 -- an
    instrument reading low is indistinguishable from a mapper that is already clean.
    """
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    mapping_ids, predicates, qualifiers = set(), set(), set()
    for profile in (cfg.get("profiles") or {}).values():
        for mapping in profile.get("mappings") or []:
            if mapping.get("mapping_id"):
                mapping_ids.add(mapping["mapping_id"])
    for pack in (cfg.get("packs") or {}).values():
        for name, claim in (pack.get("claims") or {}).items():
            emitted = (claim.get("emit") or {}).get("predicate")
            predicates.add(_unversioned(emitted or name))
            for role_name, role in (claim.get("roles") or {}).items():
                if (role or {}).get("kind") == "attribute":
                    qualifiers.add(role_name)
    entities = {_unversioned(name) for name in (cfg.get("entities") or {})}
    entities |= set(cfg.get("entities") or {})
    # A claim name that is also a predicate spelling (`slot_map`) must not be counted
    # twice; classification below takes the first matching kind, so order matters.
    return {"mapping_id": mapping_ids, "predicate": predicates,
            "entity type": entities, "qualifier": qualifiers}


def main():
    vocab = vocabularies()
    tree = ast.parse(MAPPER.read_text(encoding="utf-8"))
    hits = collections.defaultdict(list)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        value = node.value
        for kind in ("mapping_id", "predicate", "entity type", "qualifier"):
            if value in vocab[kind]:
                hits[kind].append((node.lineno, value))
                break
    # claim_ref is a shape, not a vocabulary: any literal reaching a claim_ref= keyword.
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "claim_ref":
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                hits["claim_ref"].append((node.lineno, node.value.value))

    print(f"mapper: {MAPPER.name}")
    print(f"config: {CONFIG.name}")
    print()
    total = 0
    for kind in ("mapping_id", "claim_ref", "predicate", "entity type", "qualifier"):
        found = hits.get(kind, [])
        total += len(found)
        where = " · ".join(f":{line} {name}" for line, name in sorted(found)[:8])
        print(f"  {kind:<12} {len(found):>3}   {where}")
    print(f"  {'TOTAL':<12} {total:>3}")
    print()
    wiring = sum(len(hits.get(k, [])) for k in ("mapping_id", "claim_ref", "entity type"))
    print(f"WIRING LITERALS (target 0): {wiring}")
    print(f"PREDICATE LITERALS: {len(hits.get('predicate', []))}")
    print(f"QUALIFIER LITERALS (business vocabulary, kept): "
          f"{len(hits.get('qualifier', []))}")


if __name__ == "__main__":
    main()
