"""소유자 10-21 「자동 회수 안 됨?」 · 총괄 c67aa93bb ㄱ-a: a rule that answers for whole maps (`allow_replace_map` ·
`allow_retraction`) wakes on a deleted source row without `allow_delete_trigger`, and its mapper is handed the WHOLE map a
row left - the rows that map has now, read from the trigger table - so its batch is the map as it is, not the map
emptied. A map no row holds any more is still named, and its batch empties it.

  wakes     a DELETE wakes allow_delete_trigger · allow_replace_map · allow_retraction - a rule with none, not
  handed    a deletion · a key moved off: the map left comes whole; a row comes once, as it came
  in        an edit inside a map, a key moved on: the map the row is in comes whole too (총괄 f2 10-21)
  gone      a map with no row now: named, nothing written - its batch empties it
  plain     a rule without the two flags reads nothing again
  fetched   the whole map is read by the fetch seat - the mapper's call reads nothing (총괄 78eec1ec1)

On a real chain worker and a real watcher's file replace - measured on a scratch schema (박스 판).
"""
from types import SimpleNamespace

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import chain_bindings
import mapper_sdk
from chain import ingestion_worker as worker
from chain import rule_run
from database import crud, models, schemas
from database.database import Base

TRIG, TGT = "left_trig", "left_tgt"
TABLES = {
    TRIG: {"business_key": "tk", "composite_key_source": ["tk"],
           "column_types": {"tk": "string", "job": "string", "qty": "string"}, "display_columns": ["tk", "job", "qty"]},
    TGT: {"business_key": "cell_key", "composite_key_source": ["job", "cell"], "map_key_columns": ["job"],
          "column_types": {"cell_key": "string", "job": "string", "cell": "string", "v": "string"},
          "display_columns": ["job", "cell", "v"]},
}
SEEN = []


def _build(df, db):
    """The df as it came - one cell per unit of qty."""
    SEEN.append(sorted((r["tk"], r["job"], r["qty"]) for _, r in df.iterrows() if isinstance(r.get("tk"), str)))
    rows = [{"job": r["job"], "cell": "%s%d" % (r["tk"], i), "v": "new"}
            for _, r in df.iterrows() if isinstance(r.get("job"), str) for i in range(int(r["qty"] or 0))]
    return pd.DataFrame(rows, columns=["job", "cell", "v"])


@pytest.fixture(name="db")
def fixture_db():
    mapper_sdk.mapper(name="left_build")(_build)
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    db = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    crud.apply_batch_updates(db, TRIG, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates={"tk": tk, "job": job, "qty": qty}, source_name="seed", updated_by="t")
        for tk, job, qty in (("T1", "J-A", "2"), ("T2", "J-A", "1"), ("T3", "J-B", "1"))]))
    db.commit()
    SEEN.clear()
    yield db
    db.close()
    mapper_sdk.MAPPER_REGISTRY.pop("left_build", None)
    mapper_sdk.MAPPER_PARAMS.pop("left_build", None)
    for name in TABLES:
        crud.TABLE_CONFIG.pop(name, None)


def _rule(**cells):
    rule = {"name": "left_rule", "enabled": True, "trigger_table": TRIG, "target_table": TGT, "mapper": "left_build",
            "is_batch": True, "idempotent": True, "trigger_job_column": "job", "target_job_column": "job"}
    rule.update(cells)
    return rule


def _deleted(tk, job, qty="1"):
    return {"row_id": tk, "data": {}, "old": {"tk": tk, "job": job, "qty": qty}}


def _row_id(db, tk):
    model = models.DYNAMIC_TABLES[TRIG]
    return db.query(model.row_id).filter(model.tk == tk).scalar()


def _edited(db, tk, job, qty, old):
    """An edit as the chain is handed it: the row's own id, and the database already holds what it says."""
    model = models.DYNAMIC_TABLES[TRIG]
    db.query(model).filter(model.tk == tk).update({"job": job, "qty": qty})
    db.commit()
    return {"row_id": _row_id(db, tk), "data": {"tk": {"value": tk}, "job": {"value": job}, "qty": {"value": qty}}, "old": old}


def _maps(envelope, retract=False):
    if retract:
        return {b["retract"]["source_value"]: len(b["updates"]) for b in envelope["batches"]}
    return {b["scope"]["job"]: len(b["updates"]) for b in envelope["batches"]}


@pytest.mark.parametrize("cells, wakes", [
    ({}, False), ({"allow_delete_trigger": True}, True), ({"allow_replace_map": True}, True),
    ({"allow_retraction": True}, True),
])
def test_a_deletion_wakes_a_rule_that_answers_for_whole_maps(cells, wakes):
    assert chain_bindings.takes_deletions(cells) is wakes
    assert worker._is_trigger_event(SimpleNamespace(event_type="DELETE"), cells) is wakes


@pytest.mark.parametrize("flag", ["allow_replace_map", "allow_retraction"])
def test_a_deleted_row_hands_its_map_whole(db, flag):
    envelope = mapper_sdk.MAPPER_REGISTRY["left_build"](db, [_deleted("T9", "J-A")], rule=_rule(**{flag: True}))
    assert SEEN == [[("T1", "J-A", "2"), ("T2", "J-A", "1")]]
    assert _maps(envelope, flag == "allow_retraction") == {"J-A": 3}


def test_a_map_no_row_holds_is_named_and_emptied(db):
    envelope = mapper_sdk.MAPPER_REGISTRY["left_build"](db, [_deleted("T8", "J-Z")], rule=_rule(allow_replace_map=True))
    assert SEEN == [[]] and _maps(envelope) == {"J-Z": 0}


def test_a_key_moved_hands_the_map_it_left_and_the_map_it_joined_whole(db):
    moved = _edited(db, "T2", "J-B", "1", {"job": "J-A"})
    envelope = mapper_sdk.MAPPER_REGISTRY["left_build"](db, [moved], rule=_rule(allow_replace_map=True))
    assert SEEN == [[("T1", "J-A", "2"), ("T2", "J-B", "1"), ("T3", "J-B", "1")]]
    assert _maps(envelope) == {"J-A": 2, "J-B": 2}


@pytest.mark.parametrize("flag", ["allow_replace_map", "allow_retraction"])
def test_an_edit_inside_a_map_hands_the_map_whole(db, flag):
    """총괄 f2 10-21: the edit kept its key, so no map was LEFT - the row came alone and the map was replaced by it."""
    edited = _edited(db, "T2", "J-A", "3", {"qty": "1"})
    envelope = mapper_sdk.MAPPER_REGISTRY["left_build"](db, [edited], rule=_rule(**{flag: True}))
    assert SEEN == [[("T1", "J-A", "2"), ("T2", "J-A", "3")]]
    assert _maps(envelope, flag == "allow_retraction") == {"J-A": 5}


def test_an_incoming_row_comes_once_as_it_came(db):
    incoming = _edited(db, "T1", "J-A", "7", {"qty": "2"})
    envelope = mapper_sdk.MAPPER_REGISTRY["left_build"](db, [incoming, _deleted("T9", "J-A")],
                                                        rule=_rule(allow_replace_map=True))
    assert SEEN == [[("T1", "J-A", "7"), ("T2", "J-A", "1")]]
    assert _maps(envelope) == {"J-A": 8}


def test_a_rule_without_the_flags_reads_nothing_again(db):
    envelope = mapper_sdk.MAPPER_REGISTRY["left_build"](db, [_edited(db, "T2", "J-B", "1", {"job": "J-A"})],
                                                        rule=_rule())
    assert SEEN == [[("T2", "J-B", "1")]] and "batches" not in envelope and len(envelope["updates"]) == 1


def test_the_whole_map_is_read_by_the_fetch_seat(db, monkeypatch, caplog):
    import logging

    monkeypatch.setattr(rule_run, "_SAID_READING", set())
    rule_run.count_reads()
    caplog.set_level(logging.INFO)
    edited = _edited(db, "T2", "J-A", "3", {"qty": "1"})
    envelope = rule_run.run_rule(db, _rule(allow_replace_map=True), payloads=[edited])
    assert SEEN == [[("T1", "J-A", "2"), ("T2", "J-A", "3")]] and _maps(envelope) == {"J-A": 5}
    assert not [r for r in caplog.records if "reads outside the fetch" in r.getMessage()]
