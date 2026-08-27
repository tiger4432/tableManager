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


@pytest.fixture(autouse=True)
def _declared_entities(tmp_path_factory, monkeypatch):
    """The catalogue takes its entity types from the DECLARATION as of 2026-08-27, so these
    tests declare one instead of depending on the operator's file being present and saying
    what they assume. The spellings are the bare lowercase ones the ledger stores.
    """
    from ledger_api import entity_references

    path = tmp_path_factory.mktemp("decl") / "ledger_config.json"
    path.write_text(json.dumps({"entities": {
        "wafer@1": {"keys": ["wafer"]},
        "recipe@1": {"keys": ["recipe", "rev"]},
        "lot_slot@1": {"keys": ["lot", "slot"]},
    }}), encoding="utf-8")
    monkeypatch.setattr(entity_references, "_config_path", lambda: str(path))
    entity_references.load(force_reload=True)
    yield
    monkeypatch.undo()
    entity_references.load(force_reload=True)


def test_the_catalogue_lists_what_the_declaration_names(tmp_path, monkeypatch):
    """🔴 REPLACED 2026-08-27. This used to pin {Lot, Wafer, Product, Equipment,
    Recipe} - the `vocabulary.ENTITY_TYPES` names carrying a register atom - and every one of
    them was dead. MEASURED that day against the live ledger:

        ledger_events.subject_type, distinct   die, dtjob, lot_slot, wafer
        atoms carrying any of the five         0
        register atoms                         396, all `dtjob`

    So the catalogue listed five types whose every page was empty and refused every type the
    ledger actually holds. The names now come from the declaration, which is where the atoms'
    names come from too.
    """
    import json
    from ledger_api import entity_references

    path = tmp_path / "ledger_config.json"
    path.write_text(json.dumps({"entities": {
        "Wafer@1": {"keys": ["wafer"]},
        "lot_slot@2": {"keys": ["lot", "slot"]},
    }}), encoding="utf-8")
    monkeypatch.setattr(entity_references, "_config_path", lambda: str(path))
    try:
        entity_references.load(force_reload=True)
        rows = {entry["type"]: entry for entry in ledger_catalog.entity_types()}
        # The version leaves and the case folds: the ledger stores the bare lower name, and
        # a catalogue keyed any other way is the disjoint-namespace bug all over again.
        assert set(rows) == {"wafer", "lot_slot"}
        assert rows["lot_slot"]["keys"] == ["lot", "slot"]
        assert rows["wafer"]["label"] == "wafer"
        assert "entity_class" not in rows["wafer"], (
            "the declaration has no `class` field - serving the key would be inventing one")
        assert ledger_catalog._label("lot_slot", {"lot": "L1", "slot": 3}) == "L1 / 3"
    finally:
        monkeypatch.undo()
        entity_references.load(force_reload=True)


def test_catalog_is_keyset_paged_and_keeps_structured_identity():
    rows = [
        ({"wafer": "WF-01"}, 2, NOW, NOW),
        ({"wafer": "WF-02"}, 1, NOW, NOW),
        ({"wafer": "WF-03"}, 1, NOW, NOW),
    ]
    connection = Connection(rows)
    body = ledger_catalog.entity_catalog(connection, subject_type="wafer", limit=2)
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
        ledger_catalog.entity_catalog(connection, subject_type="recipe", q="RCP")
    assert caught.value.detail["reason"] == "catalog_search_index_absent"
    assert len(connection.calls) == 1


def test_contains_search_is_server_side_and_index_named():
    connection = Connection([({"recipe": "RCP-A", "rev": "4"}, 1, NOW, NOW)])
    body = ledger_catalog.entity_catalog(
        connection, subject_type="recipe", q="RCP-A")
    sql, params = connection.calls[-1]
    assert "subject_keys::text ILIKE" in sql
    assert params["pattern"] == "%RCP-A%"
    assert body["search"]["index"] == ledger_catalog.SEARCH_INDEX
    assert body["items"][0]["label"] == "RCP-A / 4"


def test_cursor_round_trip_and_type_refusal_are_named():
    cursor = ledger_catalog._encode_cursor({"wafer": "WF-한글"})
    assert ledger_catalog._decode_cursor(cursor) == {"wafer": "WF-한글"}
    with pytest.raises(ledger_catalog.CatalogRequestError) as caught:
        # 🔴 WAS "Die" - composed, and the old vocabulary deliberately gave it no
        # register atom. Under the declaration「not catalogued」means「not declared」, so the
        # refusal is asked for with a name no declaration carries.
        ledger_catalog.entity_catalog(Connection(), subject_type="no_such_type")
    assert caught.value.detail["reason"] == "entity_type_not_catalogued"
