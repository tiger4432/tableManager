"""Regression tests for server/scripts/list_undeclared_tables.py.

The script answers one operational question: after a rollback, what physical
schema is left over that ``table_config.json`` no longer declares. Two of its
rules are load-bearing and both have already been wrong once:

1. The "expected columns" set must come from the built ORM model, not from a
   second reading of the JSON. The first version of the script re-derived it and
   reported the seven bookkeeping columns as residue on every table in the
   database -- 21 tables of pure false positives.
2. An unreadable config must NOT be treated as "declares nothing", or every
   table in the database looks like residue and the report tells an operator to
   drop their entire schema.

These tests pin both. They need no database: the classification rules are pure.
"""
import importlib.util
import io
import json
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPT = os.path.join(SERVER_DIR, "scripts", "list_undeclared_tables.py")

# Names that cannot collide with a user's real config: a fake table name that
# happens to exist in the operator's gitignored table_config.json would let
# init_dynamic_models bind a real schema underneath the test.
DRILL_TABLE = "undeclared_report_probe"


def _load_script():
    if SERVER_DIR not in sys.path:
        sys.path.insert(0, SERVER_DIR)
    spec = importlib.util.spec_from_file_location("list_undeclared_tables", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def script():
    return _load_script()


def _write_config(tmp_path, entries):
    p = tmp_path / "table_config.json"
    p.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    return str(p)


class TestDeclaredTables:
    def test_missing_file_is_none_not_empty(self, script, tmp_path):
        """"cannot read" and "declares nothing" must not be the same answer."""
        assert script.declared_tables(str(tmp_path / "nope.json")) is None

    def test_corrupt_json_is_none_not_empty(self, script, tmp_path):
        p = tmp_path / "table_config.json"
        p.write_text("{ this is not json", encoding="utf-8")
        assert script.declared_tables(str(p)) is None

    def test_valid_config_returns_the_declared_names(self, script, tmp_path):
        path = _write_config(tmp_path, {DRILL_TABLE: {"column_types": {"a": "string"}}})
        assert script.declared_tables(path) == {DRILL_TABLE}

    def test_run_refuses_when_the_config_cannot_be_read(self, script, tmp_path, monkeypatch):
        """The whole report must abort, not proceed with an empty declared set.

        The message assertion is the load-bearing one. Verified by injecting the
        defect (declared_tables returning an empty set): the broken version also
        returns 2, because it proceeds and then fails opening the same missing
        file from build_models. Only the wording distinguishes "I refused" from
        "I tried and tripped". Do not drop it and keep the rc check alone.
        """
        monkeypatch.setattr(script.paths, "config_path",
                            lambda *p: str(tmp_path / "absent.json"))
        out = io.StringIO()
        rc = script.run(out=out)
        assert rc == 2
        assert "refusing to report" in out.getvalue()


class TestModelledColumns:
    """The bookkeeping columns are NOT residue.

    models.init_dynamic_models adds seven columns to every dynamic table
    regardless of the declaration. A report that re-derives the expected set from
    the JSON misses them and flags each one on every table.
    """

    BOOKKEEPING = {"row_id", "business_key_val", "created_at", "updated_at",
                   "is_graph_synced", "needs_graph_rollback", "graph_synced_at"}

    def test_bookkeeping_columns_are_expected(self, script, tmp_path):
        path = _write_config(tmp_path, {
            DRILL_TABLE: {"business_key": "probe_key",
                          "column_types": {"probe_key": "string", "note": "string"}}
        })
        script.build_models(path)
        expected = script.modelled_columns(DRILL_TABLE)
        assert expected is not None
        missing = self.BOOKKEEPING - expected
        assert not missing, (
            f"{sorted(missing)} would be reported as residue on every dynamic table. "
            f"Read the expected set off the ORM model, not off the JSON."
        )

    def test_declared_columns_are_expected(self, script, tmp_path):
        path = _write_config(tmp_path, {
            DRILL_TABLE: {"business_key": "probe_key",
                          "column_types": {"probe_key": "string", "note": "string"}}
        })
        script.build_models(path)
        expected = script.modelled_columns(DRILL_TABLE)
        assert {"probe_key", "note"} <= expected

    def test_an_undeclared_physical_column_is_not_expected(self, script, tmp_path):
        """The case the report exists for: a column left behind by a revert."""
        path = _write_config(tmp_path, {
            DRILL_TABLE: {"business_key": "probe_key",
                          "column_types": {"probe_key": "string"}}
        })
        script.build_models(path)
        expected = script.modelled_columns(DRILL_TABLE)
        assert "rolled_back_column" not in expected

    def test_unknown_table_returns_none(self, script, tmp_path):
        path = _write_config(tmp_path, {DRILL_TABLE: {"column_types": {"a": "string"}}})
        script.build_models(path)
        assert script.modelled_columns("no_such_table_anywhere") is None


class TestSystemTables:
    """System tables must never be reported as undeclared residue."""

    def test_product_system_tables_are_excluded(self, script, tmp_path):
        path = _write_config(tmp_path, {DRILL_TABLE: {"column_types": {"a": "string"}}})
        models = script.build_models(path)
        system = script.system_tables(models)
        for name in ("audit_logs", "cell_sources", "cell_overwrites",
                     "database_outbox", "file_ingestion_logs",
                     "file_ingestion_checkpoints",
                     "graph_nodes", "graph_edges", "graph_sync_state"):
            assert name in system, f"{name} would be reported as residue"

    def test_dynamic_tables_are_not_system_tables(self, script, tmp_path):
        path = _write_config(tmp_path, {DRILL_TABLE: {"column_types": {"a": "string"}}})
        models = script.build_models(path)
        assert DRILL_TABLE not in script.system_tables(models)


class TestReadOnly:
    """The script prints DROP statements; it must never execute one."""

    def test_no_ddl_verbs_in_the_source(self):
        with io.open(SCRIPT, encoding="utf-8") as f:
            src = f.read()
        # The DROP/ALTER strings that DO appear are inside f-strings that are
        # printed. Nothing may hand them to a connection.
        for forbidden in (".execute(text(f'DROP", ".execute(text(f'ALTER",
                          'conn.execute(text(f"DROP', 'conn.execute(text(f"ALTER'):
            assert forbidden not in src, "the report must not issue DDL"
        assert "engine.begin()" not in src, (
            "engine.begin() opens a write transaction; the report is SELECT-only "
            "and must use engine.connect()"
        )
