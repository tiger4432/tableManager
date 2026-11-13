# -*- coding: utf-8 -*-
"""Lead 11-13 (TO_MOVE D): preflight counts the database's tables through `lines.base_tables` - line tables too - and
its views apart, and prints both."""
import importlib.util
import os

import sqlalchemy as sa

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "ledger_deploy_preflight.py")


def _preflight(tmp_path, monkeypatch):
    url = "sqlite:///" + str(tmp_path / "pre.db").replace("\\", "/")
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        for name in ("ledger_events", "dt_a", "dt_a__lines"):
            conn.execute(sa.text('CREATE TABLE "%s" (k int)' % name))
        conn.execute(sa.text("CREATE VIEW v_one AS SELECT k FROM dt_a"))
        conn.execute(sa.text("CREATE VIEW v_two AS SELECT k FROM dt_a__lines"))
    engine.dispose()
    spec = importlib.util.spec_from_file_location("ledger_deploy_preflight", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_database_url", lambda: (url, "test"))
    return module


def test_the_tables_are_counted_line_tables_too_and_the_views_apart(tmp_path, monkeypatch):
    db = _preflight(tmp_path, monkeypatch).inspect_database()
    assert (db["table_count"], db["view_count"], db["has_ledger_events"]) == (3, 2, True), db


def test_both_numbers_are_printed(tmp_path, monkeypatch, capsys):
    module = _preflight(tmp_path, monkeypatch)
    monkeypatch.setattr(module, "inspect_config", lambda: {
        "ontology_json_files": [], "legacy_sources": [], "legacy_config_present": False,
        "ontology_root_present": False, "is_single_file": True})
    monkeypatch.setattr(module, "verdict", lambda cfg, db: [])
    module.main()
    assert "표 3개 · 뷰 2개 · ledger_events 있음" in capsys.readouterr().out
