"""Bring a deployment's ledger setup to v6: the ledger declaration's `prepare` section retires, the
computation it did for `lot_event` moves to the chain, and `lot_event` - which then has nothing left
to say - retires (총괄 e14416950 · 819726624, owner 10-01 「ㄱ」 · 「ㅇㅇ」). Three files, because the
descent of a lot is now a CHAIN-written table the ledger reads:

    ledger_config.json   lot_event's `descent`     -> a source `lot_lineage` declaring the same
                                                      predicate, said for the event types the
                                                      retired mapper said it for (split, merge)
                         a source mapped by the retired `lot-event-role` -> status retired (its
                                                      atoms stay - a ledger appends)
                         register@1.subjects       -  every type no active source registers
                                                      (lot and wafer, once lot_event retires)
                         setup_version 5 -> 6 by `ledger.setup_bundle.upgrade_setup`, the loader's
                                                      own in-memory reading: a direct-join or a
                                                      retired source's `prepare` is dropped, and
                                                      `exclude_when` moves under `read`
    table_config.json    + lot_lineage             (copied from the shipped sample)
    chain_rules.json     + lot_event_to_lot_lineage (copied from the shipped sample)
                         a rule run by the lot_slot_wafer mapper gets, under `params`, every
                                                      column name it does not state, in the
                                                      words the mapper's code used - the mapper
                                                      has no defaults since 총괄 0cb2ab958

🔴 NO NAME IS GUESSED. The lineage source is built out of the `descent` mapping being removed - its
predicate, and each end's entity type and key - so a deployment that spells them differently
keeps its spelling. A `descent` whose ends carry more than one key is refused: the lineage table
holds one lot per end.

Preview by default; `--apply` writes the three files (each through `ledger.admin`'s atomic writer,
which keeps a backup). Running it twice is safe: a file already in the target shape is unchanged.

Usage:
    python -m scripts.migrate_ledger_config_to_v6 [--apply]
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

LINEAGE = "lot_lineage"
LINEAGE_RULE = "lot_event_to_lot_lineage"
#: The event types the retired `lot-event-role` mapper said a descent for - its own rule
#: (`event_type in {"split", "merge"}`), written into the declaration instead.
DESCENT_KINDS = ("split", "merge")
#: What `mappers/lot_slot_wafer_mapper.py` read and wrote while it had defaults - the words its
#: code said, written into the rule so the rule runs on as it did.
LOT_SLOT_WAFER_MAPPER = "build_lot_slot_wafer_rows"
LOT_SLOT_WAFER_WORDS = {
    "slot_list_column": "slotnumbers", "wafer_list_column": "waferids", "list_delimiter": ":",
    "lot_column": "lot_id", "time_column": "event_time", "event_type_column": "event_type",
    "target_lot_column": "lot", "target_slot_column": "slot", "target_wafer_column": "wafer",
    "target_time_column": "event_time", "target_event_type_column": "event_type"}
SAMPLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "config", "sample")


class MigrationRefusal(RuntimeError):
    """A file this script will not rewrite, with the reason an operator can act on."""


def _sample(name: str) -> dict[str, Any]:
    with open(os.path.join(SAMPLE, name), encoding="utf-8") as handle:
        return json.load(handle)


def _one_key_end(binding: Any, column: str, where: str) -> dict[str, Any]:
    keys = (binding or {}).get("keys") if isinstance(binding, dict) else None
    if (not isinstance(binding, dict) or binding.get("kind") != "entity"
            or not isinstance(keys, dict) or len(keys) != 1):
        raise MigrationRefusal(
            f"{where}: a descent end must be one entity with one key to become a lineage "
            f"column; this one is {json.dumps(binding, ensure_ascii=False)[:200]}")
    return {"kind": "entity", "entity_type": binding["entity_type"],
            "keys": {next(iter(keys)): {"kind": "column", "column": column}}}


def descent_to_lineage(document: dict[str, Any]) -> list[str]:
    """Every `lot-event-role` source's `descent` becomes the `lot_lineage` source."""
    sources = document.setdefault("sources", {})
    said = []
    for source_id, source in list(sources.items()):
        if (source.get("map") or {}).get("implementation_id") != "lot-event-role":
            continue
        mappings = (source.get("bind") or {}).get("mappings") or {}
        descent = mappings.get("descent")
        if descent is None:
            continue
        where = f"sources.{source_id}.bind.mappings.descent"
        if LINEAGE in sources:
            raise MigrationRefusal(
                f"{where} is still declared and a source {LINEAGE!r} already exists - which "
                f"one says derived_from is not knowable; remove one by hand")
        bind = descent.get("bind") or {}
        subject = _one_key_end(bind.get("subject"), "child_lot", f"{where}.bind.subject")
        target = _one_key_end(bind.get("target"), "parent_lot", f"{where}.bind.target")
        timezone = ((source.get("read") or {}).get("occurred_at") or {}).get("timezone")
        occurred_at = {"column": "event_time", **({"timezone": timezone} if timezone else {})}
        sources[LINEAGE] = {
            "relation": LINEAGE,
            "read": {"unit": "row", "identity": ["lot_lineage_key"],
                     "order_by": ["event_time", "lot_lineage_key"],
                     "cursor": {"columns": ["event_time", "lot_lineage_key"]},
                     "occurred_at": occurred_at},
            "map": {"implementation_id": "declarative-role", "implementation_version": 1,
                    "unit": {"kind": "row"}},
            "bind": {"mappings": {
                f"descent_{kind}": {
                    "predicate": descent["predicate"], "when": {"event_type": kind},
                    "bind": {"subject": copy.deepcopy(subject), "target": copy.deepcopy(target),
                             "occurred_at": {"kind": "column", "column": "event_time"}}}
                for kind in DESCENT_KINDS}},
        }
        del mappings["descent"]
        said.append(f"{where} -> sources.{LINEAGE} (derived_from for "
                    f"{', '.join(DESCENT_KINDS)})")
    return said


def retire_lot_event_role(document: dict[str, Any]) -> list[str]:
    """A source mapped by the retired `lot-event-role` has nothing left to say: its descent is the
    lineage source's now and its first sights are no longer said (819726624). Retired, not
    deleted - its atoms are facts."""
    from ledger.setup_bundle import REGISTER_PREDICATE
    from ledger.setup_bundle import is_retired

    said = []
    for source_id, source in (document.get("sources") or {}).items():
        if ((source.get("map") or {}).get("implementation_id") == "lot-event-role"
                and source.get("status") != "retired"):
            source["status"] = "retired"
            said.append(f"sources.{source_id}: retired (its atoms stay)")
    # 총괄 ㄹ ㄱ: a register type nothing active registers is a question the gap table no
    # longer asks ("등록되지 않은 웨이퍼 · 랏" retired) - so the vocabulary stops asking it too.
    registered = {
        ((mapping.get("bind") or {}).get("subject") or {}).get("entity_type")
        for source in (document.get("sources") or {}).values() if not is_retired(source)
        for mapping in ((source.get("bind") or {}).get("mappings") or {}).values()
        if str(mapping.get("predicate", "")).split("@", 1)[0] == REGISTER_PREDICATE}
    for predicate_id, spec in (document.get("vocabulary") or {}).items():
        if predicate_id.split("@", 1)[0] != REGISTER_PREDICATE or not isinstance(spec, dict):
            continue
        dropped = [kind for kind in spec.get("subjects") or () if kind not in registered]
        if dropped:
            spec["subjects"] = [kind for kind in spec["subjects"] if kind in registered]
            said.append(f"vocabulary.{predicate_id}.subjects: - {', '.join(dropped)} "
                        f"(no active source registers them)")
    return said


def to_setup_version_6(document: dict[str, Any]) -> list[str]:
    """The loader's own v5 -> v6 reading, written down."""
    from ledger.setup_bundle import SETUP_VERSION, upgrade_setup

    before = document.get("setup_version")
    held = {s for s, source in (document.get("sources") or {}).items() if "prepare" in source}
    upgraded = upgrade_setup(document)
    if upgraded is document:
        return []
    document.clear()
    document.update(upgraded)
    dropped = sorted(held - {s for s, source in document["sources"].items() if "prepare" in source})
    return [f"setup_version {before} -> {SETUP_VERSION}: prepare dropped from {len(dropped)} "
            f"source(s) ({', '.join(dropped)})"]


def add_lineage_table(tables: dict[str, Any]) -> list[str]:
    if LINEAGE in tables:
        return []
    tables[LINEAGE] = copy.deepcopy(_sample("table_config.json.sample")[LINEAGE])
    return [f"table_config: + {LINEAGE}"]


def add_lineage_rule(document: dict[str, Any]) -> list[str]:
    rules = document["rules"] if isinstance(document, dict) else document
    if any(rule.get("name") == LINEAGE_RULE for rule in rules):
        return []
    sample = _sample("chain_rules.json.sample")
    shipped = sample["rules"] if isinstance(sample, dict) else sample
    rules.append(copy.deepcopy(next(r for r in shipped if r.get("name") == LINEAGE_RULE)))
    return [f"chain_rules: + {LINEAGE_RULE} (enabled)"]


def fill_lot_slot_wafer_params(document: dict[str, Any]) -> list[str]:
    """A cell the rule already states - flat or under `params`, read the way the mapper reads
    it - is kept as written; only the absent ones are added, under `params`."""
    import chain_bindings
    from database import crud

    rules = document["rules"] if isinstance(document, dict) else document
    said = []
    for rule in rules:
        if rule.get("mapper_function") != LOT_SLOT_WAFER_MAPPER:
            continue
        stated = chain_bindings.params_of(rule)
        missing = {cell: word for cell, word in LOT_SLOT_WAFER_WORDS.items()
                   if crud.is_blank_value(stated.get(cell))}
        if missing:
            rule.setdefault(chain_bindings.PARAMS_KEY, {}).update(missing)
            said.append(f"chain_rules.{rule.get('name')}.params: + " + ", ".join(
                f"{cell}={word!r}" for cell, word in missing.items()))
    return said


def migrate(ledger: dict, tables: dict, rules: Any) -> list[str]:
    """Rewrite the three documents IN PLACE; return what changed, one line each."""
    return (descent_to_lineage(ledger) + retire_lot_event_role(ledger)
            + to_setup_version_6(ledger) + add_lineage_table(tables) + add_lineage_rule(rules)
            + fill_lot_slot_wafer_params(rules))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write the three files")
    args = parser.parse_args(argv)
    from ledger import admin

    paths = {"ledger": admin.sources_path(), "tables": admin.table_config_path(),
             "rules": admin.chain_rules_path()}
    documents = {}
    for key, path in paths.items():
        with open(path, encoding="utf-8") as handle:
            documents[key] = json.load(handle)
    before = {key: json.dumps(value, sort_keys=True) for key, value in documents.items()}
    try:
        changes = migrate(documents["ledger"], documents["tables"], documents["rules"])
    except MigrationRefusal as exc:
        print(f"REFUSED: {exc}")
        return 2
    if not changes:
        print("Already v6 - nothing to change.")
        return 0
    for line in changes:
        print(f"  {line}")
    if not args.apply:
        print("Preview only. Next: run again with --apply")
        return 0
    for key, path in paths.items():
        if json.dumps(documents[key], sort_keys=True) != before[key]:
            backup = admin._atomic_write(path, documents[key])
            print(f"wrote {path}" + (f" (backup {backup})" if backup else ""))
    print("Next: restart the server (creates table lot_lineage and loads the rule), then\n"
          "      python server/scripts/chain_replay_cli.py replay lot_event_to_lot_lineage --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
