# -*- coding: utf-8 -*-
"""Owner 11-06 tables for people: people see source tables, and an arrow leaves a KEY cell for the tables that share
that entity. `/api/ledger/declaration` says, per source, which column is which entity's key part, attribute, time or
qualifier - from `ledger.setup.bound_columns`, the one reader of bind by column (`declared_value_type` reads it too).
The rows are the shared vectors `contracts/declaration_columns/vectors.json`, driven through the mounted route."""
import dataclasses
import json
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from test_a_test_run_shows_the_atoms_its_rows_became import SOURCE, _document  # noqa: E402
from test_an_attribute_bound_on_a_source_becomes_its_entitys_registration import _atoms  # noqa: E402
from test_the_test_run_reads_until_it_has_a_molecule import _row  # noqa: E402
from ledger import setup as ledger_setup  # noqa: E402
from ledger import trace_router  # noqa: E402

with open(os.path.join(os.path.dirname(__file__), "..", "..", "contracts", "declaration_columns", "vectors.json"),
          encoding="utf-8") as _fh:
    VECTORS = json.load(_fh)


def _declared(declare):
    document = _document()
    source = document["sources"][SOURCE]
    sentence = source["bind"]["mappings"]["seat-holds-wafer"]["bind"]
    if "attribute" in declare:
        said = declare["attribute"]
        document["entities"][said["entity"]]["attributes"] = [said["name"]]
        source["bind"]["entities"] = {said["entity"]: {"attributes": {
            said["name"]: {"kind": "column", "column": said["column"]}}}}
    if "qualifier" in declare:
        said = declare["qualifier"]
        document["vocabulary"]["has_wafer@1"]["object"]["qualifiers"]["optional"] = [said["name"]]
        sentence[said["name"]] = {"kind": "column", "column": said["column"]}
    if "constant_key" in declare:
        said = declare["constant_key"]
        sentence[said["as"]]["keys"][said["part"]] = {"kind": "constant", "value": said["value"]}
    if "type_column" in declare:
        said = declare["type_column"]
        sentence[said["as"]]["entity_type"] = {"kind": "column", "column": said["column"]}
    return document


@pytest.fixture(name="route")
def fixture_route(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    def answer(document, plan=lambda plan: plan):
        setup, _ = _atoms(tmp_path / "compiled", document, [_row(0)])
        plans = dict(setup.snapshot.source_plans, **{SOURCE: plan(setup.snapshot.source_plans[SOURCE])})
        object.__setattr__(setup.snapshot, "source_plans", plans)          # the compiled snapshot is frozen
        root = tmp_path / "declaration"
        root.mkdir(exist_ok=True)
        (root / "ledger_config.json").write_text(json.dumps(document), encoding="utf-8")
        world = SimpleNamespace(name="default", declaration_root=str(root),
                                declaration_path=str(root / "ledger_config.json"))
        monkeypatch.setattr(trace_router, "_worlds", lambda _world=None: (world,))
        whose = {part: {name: "default" for name in document.get(part) or {}} for part in ("entities", "vocabulary")}
        monkeypatch.setattr(trace_router, "_declaration_and_whose", lambda _world=None: (document, whose))
        monkeypatch.setattr(ledger_setup, "load_setup", lambda _root: setup)
        monkeypatch.setattr(trace_router, "_row_census_by_source", lambda _world=None: {})
        app = FastAPI()
        app.include_router(trace_router.router)
        reply = TestClient(app).get("/api/ledger/declaration")
        assert reply.status_code == 200, reply.text
        body = reply.json()
        return body, {row["source"]: row for row in body.get("sources") or []}
    return answer


@pytest.mark.parametrize("case", VECTORS["cases"], ids=[case["name"] for case in VECTORS["cases"]])
def test_each_bound_column_is_one_row_saying_what_the_bind_says(route, case):
    body, sources = route(_declared(case["declare"]))
    columns = sources[VECTORS["source"]]["columns"]
    assert sorted(columns, key=json.dumps) == sorted(case["columns"], key=json.dumps)
    # spelled as the same answer's lists spell them, so a screen never builds a name
    assert {row["entity"] for row in columns if "entity" in row} <= {item["type"] for item in body["entities"]}
    assert {row["predicate"] for row in columns if "predicate" in row} <= {item["name"] for item in body["predicates"]}


def test_a_source_the_loader_refused_has_no_column_map(route):
    _body, sources = route(_declared({}), plan=lambda plan: dataclasses.replace(plan, planned=False))
    assert SOURCE in sources and "columns" not in sources[SOURCE], sources.get(SOURCE)
