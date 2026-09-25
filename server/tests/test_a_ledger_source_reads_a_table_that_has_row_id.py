# -*- coding: utf-8 -*-
"""총괄 f3bc02f6e · da3fa7493 — a ledger source reads a table that has `row_id`, and each grid
row says which sources put it in the ledger.

> 소유자: 「소급은 하지 말고 그냥 걷어내 · 운영에서는 뷰 안 써」 · 「이대로 해」

A source whose relation is a VIEW is refused at load BY NAME and falls alone - through the
translating loader and the reading loader alike - and the view-only branches behind it are
gone. The grid row carries `ledger_sources` from the ledger's own row index.
"""
import ast
import copy
import json
import os
import subprocess
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from ledger import admin, config as ledger_config                     # noqa: E402
from ledger.config_explorer import resolve_declarations              # noqa: E402
from ledger.setup_bundle import (load_physical_catalog,              # noqa: E402
                                 validate_bundle_errors)

SAMPLE = os.path.join(SERVER_DIR, "config", "sample")
VIEW = "e_view_over_dt_log"
ON_A_VIEW = "dt_job_on_a_view"


def _world():
    """The shipped declaration plus ONE source reading a view that passes `row_id` through -
    the shape five of the retired sources had, and the one a `row_id`-only test lets in."""
    catalog = dict(load_physical_catalog(os.path.join(SAMPLE, "table_config.json.sample")))
    catalog[VIEW] = dict(copy.deepcopy(catalog["dt_log"]), kind="view")
    assert "row_id" in catalog[VIEW]["columns"], "CANARY: the view must carry row_id"
    with open(os.path.join(SAMPLE, "ledger_config.json.sample"), encoding="utf-8") as fh:
        document = json.load(fh)
    document["sources"][ON_A_VIEW] = dict(copy.deepcopy(document["sources"]["dt_job"]),
                                          relation=VIEW)
    return document, catalog


# ---------------------------------------------------------------------------
# ① refused by name, alone
# ---------------------------------------------------------------------------

def test_a_view_source_is_refused_by_name_even_when_the_view_carries_row_id():
    document, catalog = _world()
    said = [(e.code, e.path, e.message) for e in validate_bundle_errors(document, catalog=catalog)]

    assert [(c, p) for c, p, _m in said] == [
        ("relation_not_a_row_table", "bundle.sources.%s.relation" % ON_A_VIEW)], said
    message = said[0][2]
    assert ON_A_VIEW in message and VIEW in message and "a table that has row_id" in message


def test_the_refused_source_falls_alone_and_the_table_sources_stand():
    document, catalog = _world()
    report = resolve_declarations(document, catalog=catalog)

    assert report["config_level"] == []
    assert sorted(report["invalid"]) == ["source_plan|%s" % ON_A_VIEW]
    assert "dt_job" in report["document"]["sources"], "CANARY: a table source must stand"


def test_the_reading_loader_drops_it_alone_too(tmp_path):
    document, catalog = _world()
    path = tmp_path / "ledger_config.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    read = ledger_config.load(str(path), catalog=catalog)

    assert ON_A_VIEW not in read["sources"]
    assert "dt_job" in read["sources"], "CANARY: the rest of the declaration is read"


# ---------------------------------------------------------------------------
# da3fa7493 — what the reading loader drops never reaches the file
# ---------------------------------------------------------------------------

def test_a_save_after_a_read_keeps_the_refused_source_in_the_file(tmp_path, monkeypatch):
    document, catalog = _world()
    path = tmp_path / "ledger_config.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setattr(ledger_config, "config_path", lambda: str(path))
    monkeypatch.setattr(admin, "backup_file", lambda p: None)

    before = json.loads(path.read_text(encoding="utf-8"))["sources"]
    read = ledger_config.load(str(path), catalog=catalog)
    admin.save_source("dt_job", read["sources"]["dt_job"])
    after = json.loads(path.read_text(encoding="utf-8"))["sources"]

    assert ON_A_VIEW in before and ON_A_VIEW not in read["sources"]
    assert ON_A_VIEW in after, "the reduced declaration was written back over the operator's file"


# ---------------------------------------------------------------------------
# ② the view-only branches are gone
# ---------------------------------------------------------------------------

def test_nothing_in_the_ledger_tests_frame_row_id_for_absence():
    """AST over every tracked non-test module: no `if`/`while`/comprehension test names
    `frame_row_id` - a planned source always carries it."""
    files = [f for f in subprocess.check_output(["git", "ls-files", "*.py"], text=True,
                                                cwd=SERVER_DIR).split()
             if not f.startswith("tests/") and os.path.exists(os.path.join(SERVER_DIR, f))]
    assert len(files) > 100, "CANARY: the file list is broken"

    def names_it(node):
        return any((isinstance(n, ast.Attribute) and n.attr == "frame_row_id")
                   or (isinstance(n, ast.Constant) and n.value == "frame_row_id")
                   for n in ast.walk(node))

    found = []
    for rel in files:
        with open(os.path.join(SERVER_DIR, rel), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            tests = ([node.test] if isinstance(node, (ast.If, ast.IfExp, ast.While))
                     else list(node.ifs) if isinstance(node, ast.comprehension) else [])
            found += ["%s:%d" % (rel, t.lineno) for t in tests if names_it(t)]
    assert found == []


# ---------------------------------------------------------------------------
# ⑤ each grid row says which ledger sources put it there
# ---------------------------------------------------------------------------

def test_a_row_says_which_sources_translated_it_and_a_new_row_says_none():
    from conftest import _declared_as_test_database, _resolve_pg_test_url
    from tests.support.isolated_pg import scratch_connect_args

    url, reason = _resolve_pg_test_url()
    if url is None:
        pytest.skip(reason)
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.pool import NullPool

    import main
    from ledger import schema, store as ledger_store

    scratch = "assy_pytest_f3bc02f6e"
    with _declared_as_test_database(url):
        engine = create_engine(url, poolclass=NullPool,
                               connect_args=scratch_connect_args(scratch))
        maker = create_engine(url, poolclass=NullPool)
        try:
            with maker.begin() as conn:
                conn.execute(text('DROP SCHEMA IF EXISTS "%s" CASCADE' % scratch))
                conn.execute(text('CREATE SCHEMA "%s"' % scratch))
        except OperationalError as exc:
            pytest.skip("PostgreSQL is not reachable: %s" % str(exc).strip().splitlines()[0])
        db = type("Db", (), {"get_bind": lambda self: engine})()
        try:
            # before the index exists: the key is OFF, which the screen draws as Unknown
            unread = [{"row_id": "R1"}]
            main._attach_ledger_sources(db, "e_log", unread)
            assert "ledger_sources" not in unread[0]

            ledger_store.LedgerStore(engine).ensure_schema()
            with engine.begin() as conn:
                for row_id, who, ref in (("R1", "dt_job", "a"), ("R1", "dt_job", "b"),
                                         ("R1", "alpha", "c"), ("R9", "dt_job", "d")):
                    conn.execute(text(
                        "INSERT INTO %s (relation, row_id, source_who, source_raw_ref) "
                        "VALUES (:r, :i, :w, :f)" % schema.ROW_REF_TABLE),
                        {"r": "e_log" if row_id == "R1" else "elsewhere", "i": row_id,
                         "w": who, "f": ref})
            rows = [{"row_id": "R1"}, {"row_id": "R2"}]
            main._attach_ledger_sources(db, "e_log", rows)

            assert rows[0]["ledger_sources"] == ["alpha", "dt_job"], "sorted, one name each"
            assert rows[1]["ledger_sources"] == [], "a row the index does not name is 「not yet」"
        finally:
            with maker.begin() as conn:
                conn.execute(text('DROP SCHEMA IF EXISTS "%s" CASCADE' % scratch))
            engine.dispose()
            maker.dispose()
