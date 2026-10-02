# -*- coding: utf-8 -*-
"""Lead e67ef53f3 (owner 10-02 「메인그리드에 rowid 검색 추가 가능?」): the main grid finds a row by its
id. Two halves:

- every table's `/schema` columns end with `row_id`, after `created_at` and `updated_at` - the same
  seat (`system_cols`) and the same mechanism; the declaration itself is not touched by the answer;
- the server's filter door (`apply_column_filters`, the one the grid page, the row count and the
  export share) reads `row_id` as the table's own column and narrows on a real query.
"""
import json
import os
import sys

import pytest
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main                                                          # noqa: E402

Base = declarative_base()


class _Rows(Base):
    __tablename__ = "rowid_filter_probe"
    id = Column(Integer, primary_key=True)
    row_id = Column(String, nullable=False)


def _ids(spec):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add_all([_Rows(row_id=r) for r in ("01a0fb7a-1", "01a0fb7a-2", "9901a0fb", "77bc")])
    db.commit()
    query = main.apply_column_filters(db.query(_Rows), _Rows, "rowid_filter_probe",
                                      json.dumps({"row_id": spec}))
    return sorted(r.row_id for r in query.all())


def test_a_row_id_filter_narrows_by_the_first_characters_and_by_any_part():
    assert _ids({"filterType": "text", "type": "startsWith", "filter": "01a0fb"}) == \
        ["01a0fb7a-1", "01a0fb7a-2"]
    assert _ids({"filterType": "text", "type": "contains", "filter": "01a0fb"}) == \
        ["01a0fb7a-1", "01a0fb7a-2", "9901a0fb"]
    assert _ids({"filterType": "text", "type": "equals", "filter": "77bc"}) == ["77bc"]


@pytest.fixture()
def client():
    os.environ.setdefault("TESTING", "1")
    from fastapi.testclient import TestClient
    return TestClient(main.app, raise_server_exceptions=False)


def test_every_table_lists_row_id_last_and_the_declaration_is_not_touched(client, monkeypatch):
    from database import crud

    monkeypatch.setitem(crud.TABLE_CONFIG, "probe_declared", {
        "column_types": {"a": "string", "b": "string"}, "display_columns": ["a", "b"]})
    monkeypatch.setitem(crud.TABLE_CONFIG, "probe_named_it", {
        "column_types": {"a": "string"}, "display_columns": ["row_id", "a"]})
    for _ in range(2):
        declared = client.get("/tables/probe_declared/schema").json()["columns"]
        named = client.get("/tables/probe_named_it/schema").json()["columns"]
    # 🔴 the end of the list, in this order, after the declared columns
    assert declared == ["a", "b", "created_at", "updated_at", "row_id"], declared
    # an operator who already names row_id keeps their place for it, and it is not listed twice
    assert named == ["row_id", "a", "created_at", "updated_at"], named
    # 🔴 THE ANSWER IS A COPY - two reads later the declaration still says what was written
    assert crud.TABLE_CONFIG["probe_declared"]["display_columns"] == ["a", "b"]
    assert crud.TABLE_CONFIG["probe_named_it"]["display_columns"] == ["row_id", "a"]
