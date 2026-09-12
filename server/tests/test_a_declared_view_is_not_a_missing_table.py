# -*- coding: utf-8 -*-
"""S-193. The boot schema check stopped calling every declared view a missing table.

🔴 MEASURED BY THE LEAD, THEN BY ME. `[MISSING-TABLE]` named exactly the ten SQL views this
catalogue declares, on EVERY boot, identically from 09-11 23:46 to 09-12 13:18 — and two of
those ten answer HTTP 200 on the data route, so they were not missing at all. `_actual` reads
`get_multi_columns`/`get_table_names`, and neither of those lists views.

⛔ THE COST IS THE ONE `models.py` ALREADY NAMES: 「a permanent error line is how a real one
stops being read」. Ten permanent lines is how the eleventh, the true one, goes unnoticed.

🔴 AND THE QUESTION IS EXISTENCE, NOT VIEW-NESS. Measured: this catalogue declares ELEVEN
relations `kind: view`, and the eleventh — `ledger_events` — is a physical TABLE declared a
view so the write door refuses it (S-186). A probe asking 「is it in `get_view_names()`?」
would have called that one a MISSING-VIEW: ten false alarms traded for one.
"""
import os
import sys

import pytest
from sqlalchemy import create_engine, text

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

import schema_drift                                                   # noqa: E402


@pytest.fixture()
def sqlite_engine(tmp_path):
    """A real database with one table and one view, so 「missing」 has both meanings here."""
    engine = create_engine("sqlite:///%s" % (tmp_path / "s193.db"))
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE plain_tbl (id TEXT)"))
        conn.execute(text("CREATE VIEW plain_vw AS SELECT id FROM plain_tbl"))
    return engine


def _findings(engine, declared, kinds, monkeypatch):
    """Drive the real `check` over a declared set we control."""
    monkeypatch.setattr(schema_drift, "_declared", lambda: declared)
    monkeypatch.setattr(schema_drift, "_declared_kind", lambda name: kinds.get(name, "table"))
    monkeypatch.setattr(schema_drift, "_dynamic_table_names", lambda: set())
    return {(f["severity"], f["table"]) for f in schema_drift.check(engine)}


def test_a_declared_view_that_exists_is_not_reported_at_all(sqlite_engine, monkeypatch):
    """🔴 THE GATE. This is the ten-to-zero case: the relation is there, it is simply not a
    table, and `get_table_names` was never going to list it."""
    found = _findings(sqlite_engine, {"plain_vw": {}}, {"plain_vw": "view"}, monkeypatch)
    assert not [f for f in found if "MISSING" in f[0]], found


def test_a_declared_view_that_is_really_gone_is_named_as_a_view(sqlite_engine, monkeypatch):
    """⚠️ NAMED, NOT SILENCED. 「없는 것」 and 「0인 것」 must not render the same — a catalogue
    that declares a view the database does not have is a real finding, and it needed its own
    severity because the table remedy (「boot once, create_all builds it」) is FALSE for a
    view: `create_all` makes tables."""
    found = _findings(sqlite_engine, {"absent_vw": {}}, {"absent_vw": "view"}, monkeypatch)
    assert ("MISSING-VIEW", "absent_vw") in found
    assert ("MISSING-TABLE", "absent_vw") not in found

    remedy = [f["remedy"] for f in schema_drift.check(sqlite_engine)
              if f["table"] == "absent_vw"][0]
    assert "create_all" in remedy and "not" in remedy.lower()


def test_a_declared_table_that_is_gone_still_says_missing_table(sqlite_engine, monkeypatch):
    """⛔ THE REGRESSION LINE. The whole value of this check is the table case; a fix that
    quieted it would remove the thing 2026-08-05's outages were about."""
    found = _findings(sqlite_engine, {"absent_tbl": {}}, {}, monkeypatch)
    assert ("MISSING-TABLE", "absent_tbl") in found


def test_a_relation_of_either_kind_that_exists_answers_true(sqlite_engine):
    """`_relation_exists` asks about EXISTENCE, so a table and a view both answer yes — which
    is what keeps `ledger_events`, a table declared `kind: view`, out of the findings."""
    assert schema_drift._relation_exists(sqlite_engine, "plain_tbl")
    assert schema_drift._relation_exists(sqlite_engine, "plain_vw")
    assert not schema_drift._relation_exists(sqlite_engine, "no_such_relation")


def test_an_unanswerable_probe_is_not_read_as_absence(monkeypatch):
    """⚠️ A PROBE THAT FAILS MUST NOT MEAN 「MISSING」. Reporting absence because the question
    could not be asked is how a permanent error line gets written about a healthy database —
    which is the defect this whole file is about, arriving by a different door."""
    class Broken:
        dialect = type("D", (), {"name": "sqlite"})()

        def connect(self):
            raise RuntimeError("no")

    monkeypatch.setattr(schema_drift, "inspect",
                        lambda engine: (_ for _ in ()).throw(RuntimeError("no")))
    # sqlite + a failing inspector: there is no second probe, so it must not claim absence.
    assert schema_drift._relation_exists(Broken(), "anything") is False, (
        "on a dialect with no sharpening the inspector's answer is all there is")


def test_the_severity_is_ranked_beside_the_table_one():
    """A view that is genuinely gone breaks queries exactly as hard as a missing table, so it
    sorts with it rather than below the self-healing kind."""
    assert (schema_drift.SEVERITY_ORDER["MISSING-VIEW"]
            == schema_drift.SEVERITY_ORDER["MISSING-TABLE"])


def test_the_catalogue_is_asked_through_the_one_function():
    """🔴 `catalog_kind` (S-187) IS THE AUTHOR OF 「is this a view」. A second spelling here is
    how the boot check and the write door come to disagree about the same relation."""
    import inspect as _inspect

    body = _inspect.getsource(schema_drift._declared_kind)
    assert "catalog_kind" in body
    assert 'get("kind")' not in body, "that would be a second spelling"


def test_an_undeclared_relation_is_treated_as_a_table():
    """⚠️ The framework's own relations (`cell_sources`, `audit_logs`, …) are declared in CODE
    and are not in the catalogue at all — they are tables, and `catalog_kind(None)` already
    says so."""
    assert schema_drift._declared_kind("cell_sources") == "table"
    assert schema_drift._declared_kind("no_such_relation_anywhere") == "table"
