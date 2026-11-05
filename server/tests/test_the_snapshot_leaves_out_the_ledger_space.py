# -*- coding: utf-8 -*-
"""The snapshot (scripts/snapshot.py, owner 11-05 «ㄱ») leaves out what a restore rebuilds - the ledger space, read
from `ledger.schema` - and with --no-secrets empties the two secret cells; the restore it carries is the
standard library only.

  the default world      its ledger · cursor · row_ref, their partitions, the atom view, <ledger>_pre_rebuild*
  a world with a schema  the schema whole
  --no-secrets           database.json url · llm_config.json api_key emptied and named; other cells kept
"""
import ast
import json
import os
import sys

SCRIPTS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, SCRIPTS)

import snapshot  # noqa: E402
from ledger import schema  # noqa: E402


def test_the_default_worlds_ledger_space_is_left_out(monkeypatch):
    monkeypatch.setattr(schema, "worlds", lambda: [])
    tables, schemas = snapshot.left_out()
    names = schema.world_names(None)
    for name in (names.ledger, names.cursor, names.row_ref):
        assert name in tables and name + "_*" in tables
    assert schema.atom_rows_view_name(names) in tables
    assert names.ledger + "_pre_rebuild_*" in tables
    assert schemas == []


def test_a_world_with_its_own_schema_is_left_out_whole(monkeypatch):
    monkeypatch.setattr(schema, "worlds", lambda: ["w1"])
    real = schema.world_names

    def names_of(world):
        names = real(world)
        return names if world is None else type("_Names", (), {"schema": "ledger_w1"})()
    tables, schemas = snapshot.left_out(names_of)
    assert schemas == ["ledger_w1"] and schema.world_names(None).ledger in tables


def test_no_secrets_empties_the_two_cells_and_names_them(tmp_path):
    (tmp_path / "database.json").write_text(json.dumps({"url": "postgresql://u:p@h/db", "_url_doc": "x"}),
                                            encoding="utf-8")
    (tmp_path / "llm_config.json").write_text(json.dumps({"api_key": "k", "base_url": "http://g"}), encoding="utf-8")
    assert sorted(snapshot._secrets_out(str(tmp_path))) == ["database.json:url", "llm_config.json:api_key"]
    assert json.loads((tmp_path / "database.json").read_text(encoding="utf-8")) == {"url": "", "_url_doc": "x"}
    assert json.loads((tmp_path / "llm_config.json").read_text(encoding="utf-8")) == {"api_key": "",
                                                                                      "base_url": "http://g"}


def test_the_restore_imports_the_standard_library_only():
    with open(os.path.join(SCRIPTS, "restore.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    imported = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import)
                for alias in node.names}
    imported |= {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert imported <= set(sys.stdlib_module_names), imported - set(sys.stdlib_module_names)
