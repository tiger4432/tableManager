# -*- coding: utf-8 -*-
"""Lead e67ef53f3 (owner 10-02 「메인그리드에 rowid 검색 추가 가능?」) and d692af408: the main grid
finds a row by its id, where the relation HAS one.

- `/schema` columns end with `row_id` after `created_at` and `updated_at` - the same seat
  (`system_cols`) - when the relation's MODEL has a row_id column (`column_filter.model_has_row_id`).
  A `kind: view` is built from its column_types, so a view that does not declare row_id gets no
  ROW_ID column. The declaration itself is not touched by the answer.
- The filter door (`apply_column_filters`, the one the grid page, the row count and the export
  share) narrows by row_id on a real query, and refuses BY NAME (422) on a relation without one -
  for `row_id` and for `id`, which the door reads as the same column.
"""
import json
import os
import sys

import pytest
from fastapi import HTTPException
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main                                                          # noqa: E402

Base = declarative_base()


class _Table(Base):
    __tablename__ = "rowid_probe_table"
    id = Column(Integer, primary_key=True)
    row_id = Column(String, nullable=False)


class _ViewWith(Base):
    """A view that passes its base table's row_id through (declares it in column_types)."""
    __tablename__ = "rowid_probe_view_with"
    pk = Column(Integer, primary_key=True)
    row_id = Column(String)
    note = Column(String)


class _ViewWithout(Base):
    """A view built from column_types that do not name row_id."""
    __tablename__ = "rowid_probe_view_without"
    pk = Column(Integer, primary_key=True)
    atom_id = Column(String)


IDS = ("01a0fb7a-1", "01a0fb7a-2", "9901a0fb", "77bc")


def _db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add_all([_Table(row_id=r) for r in IDS] + [_ViewWith(row_id=r, note="n") for r in IDS])
    db.commit()
    return db


def _ids(model, name, spec):
    query = main.apply_column_filters(_db().query(model), model, name, json.dumps({"row_id": spec}))
    return sorted(r.row_id for r in query.all())


@pytest.mark.parametrize("model, name", [(_Table, "rowid_probe_table"),
                                         (_ViewWith, "rowid_probe_view_with")])
def test_a_row_id_filter_narrows_where_the_relation_has_one(model, name):
    assert _ids(model, name, {"filterType": "text", "type": "startsWith", "filter": "01a0fb"}) == \
        ["01a0fb7a-1", "01a0fb7a-2"]
    assert _ids(model, name, {"filterType": "text", "type": "contains", "filter": "01a0fb"}) == \
        ["01a0fb7a-1", "01a0fb7a-2", "9901a0fb"]
    assert _ids(model, name, {"filterType": "text", "type": "equals", "filter": "77bc"}) == ["77bc"]


@pytest.mark.parametrize("col", ["row_id", "id"])
def test_a_relation_without_row_id_refuses_the_filter_by_name(col):
    db = _db()
    with pytest.raises(HTTPException) as refused:
        main.apply_column_filters(db.query(_ViewWithout), _ViewWithout, "rowid_probe_view_without",
                                  json.dumps({col: {"filterType": "text", "type": "contains", "filter": "x"}}))
    # 🔴 a sentence naming the relation and the column, not the Python of a missing attribute
    assert refused.value.status_code == 422
    assert refused.value.detail == \
        f"'rowid_probe_view_without' has no row_id, so it cannot be filtered by '{col}'"


@pytest.fixture()
def client():
    os.environ.setdefault("TESTING", "1")
    from fastapi.testclient import TestClient
    return TestClient(main.app, raise_server_exceptions=False)


def test_the_column_list_ends_with_row_id_only_where_the_model_has_it(client, monkeypatch):
    from database import crud, models

    entries = {
        "rowid_probe_table": ({"column_types": {"a": "string"}, "display_columns": ["a"]}, _Table),
        "rowid_probe_view_with": ({"kind": "view", "column_types": {"note": "string", "row_id": "string"},
                                   "display_columns": ["note"]}, _ViewWith),
        "rowid_probe_view_without": ({"kind": "view", "column_types": {"atom_id": "string"},
                                      "display_columns": ["atom_id"]}, _ViewWithout),
        "rowid_probe_named_it": ({"column_types": {"a": "string"}, "display_columns": ["row_id", "a"]}, _Table),
    }
    for name, (entry, model) in entries.items():
        monkeypatch.setitem(crud.TABLE_CONFIG, name, entry)
        monkeypatch.setitem(models.DYNAMIC_TABLES, name, model)
    for _ in range(2):
        got = {name: client.get(f"/tables/{name}/schema").json()["columns"] for name in entries}
    assert got["rowid_probe_table"] == ["a", "created_at", "updated_at", "row_id"]
    assert got["rowid_probe_view_with"] == ["note", "created_at", "updated_at", "row_id"]
    # 🔴 a view whose model has no row_id gets no ROW_ID column
    assert got["rowid_probe_view_without"] == ["atom_id", "created_at", "updated_at"]
    # an operator who already names row_id keeps their place for it, and it is not listed twice
    assert got["rowid_probe_named_it"] == ["row_id", "a", "created_at", "updated_at"]
    # 🔴 THE ANSWER IS A COPY - two reads later each declaration still says what was written
    for name, (entry, _model) in entries.items():
        assert crud.TABLE_CONFIG[name]["display_columns"] == entry["display_columns"], name
