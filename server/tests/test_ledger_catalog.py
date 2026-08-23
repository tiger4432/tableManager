from datetime import datetime, timezone
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ledger_api import ledger_catalog
import ledger_explorer


NOW = datetime(2026, 8, 15, tzinfo=timezone.utc)


class Cursor:
    def __init__(self, owner):
        self.owner = owner
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self.owner.calls.append((sql, params or {}))
        if "to_regclass" in sql:
            self.rows = [(self.owner.search_index,)]
        else:
            self.rows = list(self.owner.rows)

    def fetchall(self):
        return self.rows


class Connection:
    def __init__(self, rows=(), search_index=True):
        self.rows = list(rows)
        self.search_index = search_index
        self.calls = []

    def cursor(self):
        return Cursor(self)


def test_catalog_is_generated_for_every_registered_entity_type():
    names = {entry["type"] for entry in ledger_catalog.entity_types()}
    assert names == {"Lot", "Wafer", "Product", "Equipment", "Recipe"}
    assert "Die" not in names  # composed, deliberately no register atom


def test_catalog_is_keyset_paged_and_keeps_structured_identity():
    rows = [
        ({"wafer": "WF-01"}, 2, NOW, NOW),
        ({"wafer": "WF-02"}, 1, NOW, NOW),
        ({"wafer": "WF-03"}, 1, NOW, NOW),
    ]
    connection = Connection(rows)
    body = ledger_catalog.entity_catalog(connection, subject_type="Wafer", limit=2)
    assert [item["label"] for item in body["items"]] == ["WF-01", "WF-02"]
    assert body["items"][0]["keys"] == {"wafer": "WF-01"}
    assert body["page"]["has_more"] is True
    assert body["page"]["next_cursor"]
    sql, params = connection.calls[-1]
    assert "OFFSET" not in sql.upper()
    assert "ORDER BY subject_keys" in sql
    assert params["fetch"] == 3


def test_contains_search_refuses_to_scan_when_its_index_is_absent():
    connection = Connection(search_index=False)
    with pytest.raises(ledger_catalog.CatalogUnavailable) as caught:
        ledger_catalog.entity_catalog(connection, subject_type="Recipe", q="RCP")
    assert caught.value.detail["reason"] == "catalog_search_index_absent"
    assert len(connection.calls) == 1


def test_contains_search_is_server_side_and_index_named():
    connection = Connection([({"recipe": "RCP-A", "rev": "4"}, 1, NOW, NOW)])
    body = ledger_catalog.entity_catalog(
        connection, subject_type="Recipe", q="RCP-A")
    sql, params = connection.calls[-1]
    assert "subject_keys::text ILIKE" in sql
    assert params["pattern"] == "%RCP-A%"
    assert body["search"]["index"] == ledger_catalog.SEARCH_INDEX
    assert body["items"][0]["label"] == "RCP-A / 4"


def test_cursor_round_trip_and_type_refusal_are_named():
    cursor = ledger_catalog._encode_cursor({"wafer": "WF-한글"})
    assert ledger_catalog._decode_cursor(cursor) == {"wafer": "WF-한글"}
    with pytest.raises(ledger_catalog.CatalogRequestError) as caught:
        ledger_catalog.entity_catalog(Connection(), subject_type="Die")
    assert caught.value.detail["reason"] == "entity_type_not_catalogued"


class GraphCursor(Cursor):
    def execute(self, sql, params=None):
        self.owner.calls.append((sql, params or {}))
        frontier = json.loads((params or {})["frontier"])
        assert frontier == [{"keys": {"wafer": "WF-01"}, "type": "Wafer"}]
        self.rows = list(self.owner.rows)


class GraphConnection(Connection):
    def cursor(self):
        return GraphCursor(self)


def test_any_registered_entity_opens_a_claim_subgraph():
    rows = [
        ("1", "Wafer", {"wafer": "WF-01"}, "register", None, None,
         NOW, "fixture", "1", "r1", None),
        ("2", "Wafer", {"wafer": "WF-01"}, "processed_with", "value",
         {"step": "ETCH", "recipe": "RCP-7"}, NOW, "fixture", "1", "r2", None),
        ("3", "Wafer", {"wafer": "WF-01"}, "measured", "value",
         {"metric": "etched_cd", "unit": "um", "method": "CD-SEM",
          "state": "recorded", "value": 48.8, "run_uid": "RUN-1"},
         NOW, "fixture", "1", "r3", None),
    ]
    body = ledger_explorer.explore_entity(
        "Wafer", {"wafer": "WF-01"}, GraphConnection(rows), hops=20)
    assert body["seed"]["type"] == "Wafer"
    assert {node["type"] for node in body["nodes"]} >= {"Wafer", "Value", "Empty"}
    assert {edge["predicate"] for edge in body["edges"]} >= {
        "register", "processed_with", "measured"}
    assert body["walk"]["hops_requested"] == 20
