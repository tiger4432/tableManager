# -*- coding: utf-8 -*-
"""The declarations the product ships (owner 11-06 «풀하면 다 알아서 셋업되게»): tracked files under
`server/declarations/` that boot merges with the owner's own - which it never writes.

    table_config.json            tables, merged into the catalogue every reader of `table_config.json` reads
                                 (`crud.load_table_config_or_raise` · `ledger.setup.live_physical_catalog`)
    worlds/<world>/ledger_config.json   a ledger world (`ledger.schema.worlds` · `_declaration_root`)

A table the owner declares under a shipped name is refused by name - the shipped one stands; a world the owner
declares under a shipped name is the owner's.
"""
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger("Shipped")

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "declarations")
TABLES_FILE = os.path.join(ROOT, "table_config.json")
WORLDS_DIR = os.path.join(ROOT, "worlds")

_said = set()


def tables() -> dict:
    """The shipped table declarations - {} when the file is not there."""
    if not os.path.isfile(TABLES_FILE):
        return {}
    with open(TABLES_FILE, encoding="utf-8") as handle:
        return json.load(handle)


def merged(owner: dict) -> dict:
    """The owner's tables and the shipped ones; an owner table under a shipped name is left out, said once."""
    shipped = tables()
    out = {name: entry for name, entry in owner.items() if name not in shipped}
    for name in sorted(set(owner) & set(shipped)):
        if name not in _said:
            _said.add(name)
            logger.error("[Config] table_config.json declares '%s', a table the product ships "
                         "(server/declarations/table_config.json) - the shipped declaration stands; "
                         "rename yours", name)
    out.update(shipped)
    return out


def owner_only(config: dict) -> dict:
    """`config` without the shipped tables - what is written back to the owner's file."""
    shipped = tables()
    return {name: entry for name, entry in config.items() if name not in shipped}


def world_root(world: str) -> str | None:
    """The shipped declaration root of `world`, or None when the product ships none."""
    root = os.path.join(WORLDS_DIR, world)
    return root if os.path.isfile(os.path.join(root, "ledger_config.json")) else None


def worlds() -> list:
    """The worlds the product ships."""
    if not os.path.isdir(WORLDS_DIR):
        return []
    return sorted(name for name in os.listdir(WORLDS_DIR) if world_root(name))
