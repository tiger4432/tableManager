"""Lead 5667ea0fe: the server's calculator (`expression`) solves contracts/expression/vectors.json as it is - the
screen's calculator's exam (client2/tests/expression_vectors_harness.mjs). A vector that walks a graph or reads the
page's markings is the screen's: the server refuses it by name."""
import json
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, SERVER_DIR)

import expression  # noqa: E402

FILE = json.load(open(os.path.join(SERVER_DIR, "..", "contracts", "expression", "vectors.json"), encoding="utf-8"))
SCORED = FILE["vectors"] + FILE["ours"]
#: A vector the screen alone answers (`screen_only`: markings, a sheet's cells, node constructors) or that walks a graph.
REFUSED = [v for v in SCORED if v.get("screen_only") or "graph" in v]
ANSWERED = [v for v in SCORED if v not in REFUSED]
SAID = {"reach": "Reach is the screen's - it reads the walk's judgment",
        "markings": "is the screen's - it reads the page's markings", "cells": "is the screen's - a sheet's cells",
        "nodes": "node constructors (type(\"key\")) are the screen's",
        "graph": "is a way from the row - ways are not read on the server yet"}


def _near(got, want):
    if isinstance(want, (int, float)) and not isinstance(want, bool):
        return (isinstance(got, (int, float)) and not isinstance(got, bool)
                and abs(got - want) <= 1e-9 * max(1, abs(want)))
    return json.dumps(got) == json.dumps(want)


def test_the_file_is_the_one_both_calculators_read():
    assert len(SCORED) == len({v["id"] for v in SCORED}) and len(ANSWERED) > 200, (len(SCORED), len(ANSWERED))
    assert not (FILE.get("unsettled") or []), "an unsettled row is not scored by either calculator"


@pytest.mark.parametrize("vector", ANSWERED, ids=[v["id"] for v in ANSWERED])
def test_a_vector(vector):
    out = expression.run(expression.compile(vector["expr"]), vector["rows"], vector.get("types"), vector.get("zone"))
    if "expect_not_time" in vector:
        assert out.get("not_time") == vector["expect_not_time"], out
    if "expect_rows" in vector:
        got = out.get("values")
        assert got is not None and len(got) == len(vector["expect_rows"]) and all(
            _near(g, w) for g, w in zip(got, vector["expect_rows"])), (out, vector["expect_rows"])
    else:
        assert "value" in out and _near(out["value"], vector["expect"]), (out, vector["expect"])


@pytest.mark.parametrize("text, zone, said", [
    ('DatePart("minute", "2026-10-14")', "Asia/Seoul", "DatePart «minute» is not in this edition"),
    ('DatePart("fortnight", "2026-10-14")', "Asia/Seoul", "DatePart takes a part name"),
    ('Date("2026-10-14")', "Nowhere/Zone", "«Nowhere/Zone» is not a time zone")])
def test_a_date_refusal_is_said_by_name(text, zone, said):
    out = expression.run(expression.compile(text), [], zone=zone)
    assert said in out.get("why", ""), out


def test_the_declaration_answer_carries_the_setting_the_screen_cuts_by(monkeypatch):
    """Lead fe2ba4b1f ①: the screen's calculator reads the zone from GET /api/ledger/declaration - set to another zone
    (an offset not Seoul's), both calculators answer alike (the screen's half: expression_vectors_harness E10)."""
    import ingestion.settings
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from admin.auth import require_admin_token
    from ledger import config, trace_router

    _settings_file_says(monkeypatch, {expression.ZONE_SETTING: "America/New_York"})
    monkeypatch.setattr(config, "load", lambda *_args, **_kwargs: {      # any declaration - the zone is not its
        "entities": {"wafer@1": {"keys": ["wid"]}}, "vocabulary": {}})
    app = FastAPI()
    app.dependency_overrides[require_admin_token] = lambda: None
    app.include_router(trace_router.router)
    answer = TestClient(app).get("/api/ledger/declaration")
    assert answer.status_code == 200 and answer.json()["expression_time_zone"] == "America/New_York", answer.text[:300]
    out = expression.run(expression.compile('Date("2026-10-14T02:00:00Z")'), [])
    assert out["value"] == "2026-10-13T00:00:00-04:00", out


def _settings_file_says(monkeypatch, settings):
    """The settings file as one that now holds `settings` - its stamp changed with it (`time_zone` reads again then)."""
    import ingestion.settings
    from ledger import setup

    stamp = ("a file holding", repr(sorted(settings.items())))
    monkeypatch.setattr(setup, "file_stamp", lambda path: stamp)
    monkeypatch.setattr(ingestion.settings, "read_ingestion_settings", lambda path=None: dict(settings))


def test_with_no_zone_the_setting_is_read(monkeypatch):
    """The product's callers give none: ingestion_settings "expression_time_zone", else Asia/Seoul (owner «ㅇㅇ kst»)."""
    compiled = expression.compile('Date("2026-10-13T23:00:00Z")')
    _settings_file_says(monkeypatch, {})
    assert expression.run(compiled, [])["value"] == "2026-10-14T00:00:00+09:00"
    _settings_file_says(monkeypatch, {expression.ZONE_SETTING: "UTC"})
    assert expression.run(compiled, [])["value"] == "2026-10-13T00:00:00Z"


def test_the_setting_is_read_again_only_when_its_file_changed(monkeypatch, caplog):
    """Lead's review ④: not every run reads the file - once a stamp; a name that is no zone is said once a process."""
    import ingestion.settings
    from ledger import setup

    reads = []
    monkeypatch.setattr(ingestion.settings, "read_ingestion_settings",
                        lambda path=None: reads.append(1) or {expression.ZONE_SETTING: "Nowhere/Zone"})
    monkeypatch.setattr(expression, "_ZONE_REFUSED", set())
    caplog.set_level("WARNING", logger="Expression")
    for stamp in ("one", "one", "one", "two", "two"):
        monkeypatch.setattr(setup, "file_stamp", lambda path, stamp=stamp: stamp)
        assert expression.time_zone().key == expression.ZONE_DEFAULT
    assert len(reads) == 2, reads
    assert [r.getMessage() for r in caplog.records].count(
        "ingestion_settings.json: expression_time_zone is 'Nowhere/Zone' - not a time zone; read as Asia/Seoul") == 1


@pytest.mark.parametrize("vector", REFUSED, ids=[v["id"] for v in REFUSED])
def test_a_screen_vector_is_refused_by_name(vector):
    compiled = expression.compile(vector["expr"])
    said = SAID[next(k for k in SAID if k in vector)]
    assert not compiled["ok"] and said in compiled["why"], compiled


@pytest.mark.parametrize("text, number", [("29.50", 29.5), (" 1 ", 1), ("+2", 2), ("1e1", 10), (".5", 0.5), ("5.", 5),
                                          ("-3E-2", -0.03), (7, 7)])
def test_a_numeral_is_a_number(text, number):
    assert expression.number_of(text) == number


@pytest.mark.parametrize("text", ["29,50", "29 mm", "0x10", "", "  ", "Infinity", "1e", ".", "+", None, True])
def test_anything_else_is_not_a_number(text):
    assert expression.number_of(text) is None


@pytest.mark.parametrize("text, said", [
    ("A1 * 2", "A1 is the screen's - a sheet's cells"), ("Sum(B1:B3)", "B1 is the screen's - a sheet's cells"),
    ("wafer(\"W01\")", "wafer is not a function here - node constructors"), ("Log10(100)", None)])
def test_a_sheet_s_cell_and_a_node_constructor_are_refused_by_name(text, said):
    compiled = expression.compile(text)
    assert (compiled["ok"], compiled.get("why", "")[:len(said or "")]) == (said is None, said or ""), compiled


def test_an_operator_counts_each_row_it_met_a_text_on_once():
    out = expression.run(expression.compile("[x] * 2 + [x]"), [{"x": "29 mm"}, {"x": "29.50"}, {"x": None},
                                                               {"x": "a"}, {"x": 3}])
    assert out == {"values": [None, 88.5, None, None, 9], "not_number": 2, "not_time": 0}, out
