"""The cells of ONE table's entry in table_config.json - the one list, and the form's skeleton generated from it
(총괄 f3639d4a2). Every key the product reads off an entry is here and nothing else is:
`tests/test_the_table_skeleton_is_the_keys_the_product_reads.py` counts the reads (AST) against this list both
ways. `table_skeleton.json` beside this file is the generated copy the client harnesses read.

A column-name cell here names a column of the entry's OWN table - its `column_types` keys, not a declared table's -
so it carries no `section` (`chain_bindings.column_ref` picks a table by a cell of the declaration; an entry has
none naming itself).
"""
from __future__ import annotations

import chain_bindings

SKELETON_VERSION = 1


def _leaf(hint="free"):
    return {"kind": "leaf", "hint": hint}


def _names(member, of):
    """A map keyed by a NAME (`column_types`: column -> type)."""
    return {"kind": "map", "keyed_by": "name", "member": member, "of": of}


def _columns():
    return chain_bindings.list_node("column", _leaf())


#: (cell, node) - the order is the form's.
TABLE_CELLS = (
    ("column_types", _names("column", _leaf())),
    ("business_key", _leaf()),
    ("composite_key_source", _columns()),
    ("composite_key_separator", _leaf()),
    ("display_columns", _columns()),
    ("search_columns", _columns()),
    ("map_key_columns", _columns()),
    ("version_column", _leaf()),
    ("null_policy", _names("column", _leaf())),
    ("source_priority", _names("source", _leaf("number"))),
    ("indexes", chain_bindings.list_node("index", {"kind": "record", "fields": [
        {"key": "columns", "required": True, "node": _columns()},
        {"key": "unique", "required": False, "node": _leaf("flag")},
        {"key": "search", "required": False, "node": _leaf("flag")},
        {"key": "purpose", "required": False, "node": _leaf()}]})),
    ("kind", _leaf()),
    ("group", _leaf()),
    ("workspace_name", _leaf()),
    ("std_parse", _leaf("flag")),
    ("allow_replace_map", _leaf("flag")),
    ("map_push_ok", _leaf("flag")),
    ("smart_paste", chain_bindings.list_node("format", _leaf())),
    ("pivot", {"kind": "record", "fields": [
        {"key": "column", "required": True, "node": _leaf()},
        {"key": "value", "required": True, "node": _leaf()}]}),
)


def skeleton():
    """The shape of ONE table's entry, in the chain and ledger skeletons' grammar."""
    return {
        "skeleton_version": SKELETON_VERSION,
        "note": ("The shape of ONE table's entry in table_config.json. Generated from `table_cells.TABLE_CELLS`; "
                 "server/tests/test_the_table_skeleton_is_the_keys_the_product_reads.py counts it against the keys "
                 "the product reads."),
        "root": {"kind": "record", "fields": [{"key": cell, "required": False, "node": node}
                                              for cell, node in TABLE_CELLS]},
    }
