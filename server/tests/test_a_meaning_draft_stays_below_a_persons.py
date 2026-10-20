# -*- coding: utf-8 -*-
"""e38466810 (owner 10-20 「뜻은 LLM 이 초안, 사람이 승인」): `meaning_draft` writes a blank meaning's draft in its own
layer (`crud.LLM_DRAFT_SOURCE`), below a person's. A person's value wins; a person who empties the meaning keeps it
empty (S-243) and is not drafted over again - no LLM call for a meaning a person or a draft has written."""
import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

SERVER = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER not in sys.path:
    sys.path.insert(0, SERVER)

import product_tables  # noqa: E402
from database import crud, models, schemas  # noqa: E402
from database.database import Base  # noqa: E402
from ledger import meanings, trace_router, walk_cards  # noqa: E402
from mappers import agent_walk  # noqa: E402
from utils import llm  # noqa: E402

TABLE = product_tables.MEANING_TABLE
RULE = {"name": "meaning_draft", "trigger_table": TABLE}
DECLARATION = {"entities": {"wafer@1": {"keys": ["wafer"]}},
               "vocabulary": {"processed_with@1": {"subjects": ["wafer@1"],
                                                   "object": {"kind": "entity_ref", "types": ["recipe@1"]}}}}


@pytest.fixture
def box(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///" + str(tmp_path / "draft.db"))
    cfg = {TABLE: product_tables.effective_declaration(product_tables.PRODUCT_TABLES[TABLE])}
    models.init_dynamic_models(cfg)
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, cfg[TABLE])
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    monkeypatch.setattr(trace_router, "_declaration", lambda world=None: DECLARATION)
    monkeypatch.setattr(walk_cards, "key_values", lambda sight, t, limit, starts_with=None: {
        "nodes": [{"keys": {"wafer": "W01"}, "count": 3}]})
    asked = []

    def ask_json(prompt, system=None):
        asked.append(prompt)
        return {"meanings": {"entity:wafer": "a silicon disc", "predicate:processed_with": "ran a recipe"}}

    monkeypatch.setattr(llm, "ask_json", ask_json)
    meanings.fill_blank_meanings(engine)
    with Session(bind=engine) as db:
        yield db, asked
    engine.dispose()


def draft(db):
    model = models.DYNAMIC_TABLES[TABLE]
    out = agent_walk.meaning_draft(db, [{"row_id": r.row_id} for r in db.query(model)], RULE)
    if out["updates"]:
        crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=out["updates"]))
        db.commit()
    return out


def person(db, name, meaning):
    crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        updates={"target_kind": "entity", "target_name": name, "meaning": meaning},
        source_name=crud.USER_SOURCE, updated_by="hc")]))
    db.commit()


def shown(db):
    model = models.DYNAMIC_TABLES[TABLE]
    return {(r.target_kind, r.target_name): r.meaning for r in db.query(model)}


def test_a_blank_meaning_gets_the_draft_in_its_own_layer(box):
    db, asked = box
    out = draft(db)
    assert {item.source_name for item in out["updates"]} == {crud.LLM_DRAFT_SOURCE}
    assert shown(db) == {("entity", "wafer"): "a silicon disc", ("predicate", "processed_with"): "ran a recipe"}
    assert "entity:wafer - keys ['wafer']; nodes [{'wafer': 'W01'}]" in asked[0]
    assert "predicate:processed_with - from ['wafer'] to ['recipe'] (entity_ref)" in asked[0]
    assert crud.SOURCE_PRIORITY[crud.LLM_DRAFT_SOURCE] > crud.SOURCE_PRIORITY[crud.USER_SOURCE]


def test_a_persons_value_wins_and_is_not_drafted_over(box):
    db, asked = box
    draft(db)
    person(db, "wafer", "the disc a lot carries")
    assert shown(db)[("entity", "wafer")] == "the disc a lot carries"
    assert draft(db)["updates"] == [] and len(asked) == 1


def test_a_person_who_empties_a_meaning_keeps_it_empty(box):
    db, asked = box
    draft(db)
    person(db, "wafer", "")
    assert shown(db)[("entity", "wafer")] is None                 # the draft does not show through
    assert draft(db)["updates"] == [] and len(asked) == 1         # nor is it drafted again
