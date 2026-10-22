# -*- coding: utf-8 -*-
"""A declaration form's suggestions come from the declarations (총괄 f3639d4a2): a `ref` leaf names its `section`,
and `authoring_schema` serves every section's names - the tables table_config declares (a `columns` section reads
`tables[T].columns`, T at the first of its `table_from` paths that holds a value), the ledger's entities and its
vocabulary. The three skeletons - chain, ledger, table - are drawn by one renderer, so they speak one vocabulary.
"""
import io
import json
import os
import sys

SERVER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SERVER not in sys.path:
    sys.path.insert(0, SERVER)

import chain_bindings                                                 # noqa: E402
import table_cells                                                    # noqa: E402
from ledger import config_authoring                                  # noqa: E402
from ledger.config_explorer_service import OntologyExplorerService   # noqa: E402
from ledger.setup_bundle import CONFIG_FILENAME                      # noqa: E402

HINTS = config_authoring.SKELETON_LEAF_HINTS


def _nodes(node, path="", defs=None, seen=()):
    """Every node, a `use` read off `defs` as the client's `deref` reads it (once per name on a path)."""
    if "use" in node:
        if node["use"] in seen:
            return
        node, seen = defs[node["use"]], seen + (node["use"],)
    yield path, node
    kind = node.get("kind")
    if kind == "record":
        for field in node["fields"]:
            yield from _nodes(field["node"], path + "." + field["key"], defs, seen)
    elif kind == "map":
        yield from _nodes(node["of"], path + "[]", defs, seen)
    elif kind == "oneOf":
        for key, branch in node["branches"].items():
            yield from _nodes(branch, path + "." + key, defs, seen)


def _three():
    chain = chain_bindings.skeleton()
    ledger = config_authoring.skeleton()
    return {"chain": ([chain["root"], chain["unified_root"]], {}), "table": ([table_cells.skeleton()["root"]], {}),
            "ledger": ([ledger["root"]], ledger.get("defs") or {})}


def _field(record, *keys):
    node = record
    for key in keys:
        node = node["branches"][key] if node["kind"] == "oneOf" else next(
            f["node"] for f in node["fields"] if f["key"] == key)
    return node


def test_the_three_skeletons_speak_one_vocabulary():
    from ledger.config_explorer import AUTHORABLE_SECTIONS

    sections = {chain_bindings.SECTION_TABLES, chain_bindings.SECTION_COLUMNS, *AUTHORABLE_SECTIONS.values()}
    counted = {}
    for name, (roots, defs) in _three().items():
        for root in roots:
            for path, node in _nodes(root, defs=defs):
                counted[name] = counted.get(name, 0) + 1
                assert node["kind"] in config_authoring.SKELETON_NODE_KINDS, (name, path, node["kind"])
                if node["kind"] == "leaf":
                    assert node["hint"] in HINTS, (name, path, node)
                    if "section" in node:
                        assert node["hint"] == "ref" and node["section"] in sections, (name, path, node)
                    if node.get("section") == chain_bindings.SECTION_COLUMNS:
                        assert node["table_from"] and all(isinstance(p, str) for p in node["table_from"]), path
    assert all(counted.get(name, 0) > 20 for name in ("chain", "table", "ledger")), counted


def test_the_files_on_disk_are_what_the_code_generates():
    for name, made in (("chain_skeleton.json", chain_bindings.skeleton()), ("table_skeleton.json", table_cells.skeleton())):
        assert json.load(io.open(os.path.join(SERVER, name), encoding="utf-8")) == made, name


def test_the_chain_table_and_column_cells_name_their_lists():
    chain = chain_bindings.skeleton()
    flat, unified = chain["root"], chain["unified_root"]
    tables = {"kind": "leaf", "hint": "ref", "section": "tables"}
    assert _field(unified, "on", "table") == tables
    assert _field(unified, "into", "table") == tables
    assert _field(flat, "trigger_table") == tables and _field(flat, "target_table") == tables

    def columns(node, table_from):
        assert node == {"kind": "leaf", "hint": "ref", "section": "columns", "table_from": table_from}, node

    # a take item is a source column's name or a record {from, into, fn, separator} (a2b7f6e14, owner 10-21)
    take = _field(unified, "derive", "join", "take")["of"]["branches"]
    columns(take["name"], ["on.table"])
    record = {f["key"]: f["node"] for f in take["record"]["fields"]}
    columns(record["from"], ["on.table"])
    columns(record["into"], ["target_table", "into.table"])
    columns(_field(unified, "key", "columns")["of"], ["on.table"])
    columns(_field(flat, "group_by")["of"], ["trigger_table", "on.table"])
    columns(_field(unified, "limits", "group_by")["of"], ["trigger_table", "on.table"])
    columns(_field(unified, "on", "columns")["of"], ["trigger_table", "on.table"])
    pair = _field(unified, "derive", "join", "on")["of"]
    columns(_field(pair, "left"), ["target_table", "into.table"])
    columns(_field(pair, "right"), ["on.table"])


def _service(root, catalog):
    return OntologyExplorerService(config_root=root, setup_loader=lambda _root: None, catalog_loader=lambda: catalog)


def test_the_lists_come_from_the_declarations(tmp_path):
    root = tmp_path / "ontology"
    root.mkdir()

    def lists(tables, entities, predicates):
        io.open(str(root / CONFIG_FILENAME), "w", encoding="utf-8").write(json.dumps({
            "setup_version": 2, "sources": {},
            "entities": {name: {"keys": ["k"]} for name in entities},
            "vocabulary": {name: {"subject": entities[0], "object": {"kind": "value"}} for name in predicates}}))
        schema = _service(root, {name: {"columns": {"c_" + name: "string"}} for name in tables}).authoring_schema()
        return schema["sections"], {name: sorted(schema["tables"][name]["columns"]) for name in schema["tables"]}

    sections, columns = lists(["lot_t", "die_t"], ["lot", "die"], ["has_die"])
    assert sections == {"tables": ["die_t", "lot_t"], "entities": ["die", "lot"], "vocabulary": ["has_die"]}
    assert columns == {"die_t": ["c_die_t"], "lot_t": ["c_lot_t"]}         # what a `columns` section reads

    sections, columns = lists(["wafer_t"], ["wafer"], [])                  # the declarations change, the lists follow
    assert sections == {"tables": ["wafer_t"], "entities": ["wafer"], "vocabulary": []}
    assert columns == {"wafer_t": ["c_wafer_t"]}


def test_the_table_window_is_handed_the_table_skeleton():
    from ledger import admin

    assert admin.table_config_raw_view()["skeleton"] == table_cells.skeleton()
