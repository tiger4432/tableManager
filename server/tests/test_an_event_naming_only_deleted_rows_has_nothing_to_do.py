# -*- coding: utf-8 -*-
"""총괄 10-09 · 5eee501eb — S-158 widened, not reversed: a collapsed event whose named rows were all DELETED (a
deletion history line, `crud.deleted_rows`) has nothing to do and the group succeeds; a named row that cannot be
read and has no such line is refused for a retry, as before.

The doors that delete a row while an event may still name it - each writes the history line:
  the grid's delete           crud.delete_rows_batch (the chain's shell rows go this way)
  the map purge               crud.purge_map_rows (replace_map)
  the job retraction          dt_map_derivation.apply_retraction
  control                     a row gone with no history line -> rows_not_visible, deferred as before
And the chain's write seat asks only a row its write emptied (5eee501eb): a row a rule only keyed is not a shell.
"""
import os
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import dt_map_derivation                                            # noqa: E402
import event_constants                                              # noqa: E402
import mapper_sdk                                                   # noqa: E402
from chain import ingestion_worker as worker                        # noqa: E402
from database import crud, models, schemas                          # noqa: E402
from database.context import channel, outbox_mode                   # noqa: E402
from database.database import Base                                  # noqa: E402
from utils.payload_helper import get_payload_dict                   # noqa: E402

T = "gone_rows"
TABLES = {T: {"business_key": "k", "composite_key_source": ["k"],
              "column_types": {"k": "string", "a": "string", "x": "string"}, "display_columns": ["k", "a", "x"]}}
RULE = {"name": "gone_rule", "mapper": "gone_mapper", "enabled": True, "is_batch": True, "trigger_table": T,
        "target_table": T, "trigger_columns": ["a"]}
CALLED = []


def _body(db, payload, rule=None):
    CALLED.append(len(payload if isinstance(payload, list) else [payload]))
    return {"updates": [{"updates": {"k": ((p.get("data") or {}).get("k") or {}).get("value"), "x": "seen"},
                         "origin_row_id": p["row_id"], "source_name": "chain_ingestion"}
                        for p in (payload if isinstance(payload, list) else [payload])]}


@pytest.fixture(name="db")
def fixture_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    mapper_sdk.register("gone_mapper", _body)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        crud.TABLE_CONFIG.pop(T, None)
        mapper_sdk.MAPPER_REGISTRY.pop("gone_mapper", None)
        mapper_sdk.MAPPER_PARAMS.pop("gone_mapper", None)


def _edit_waiting(db):
    """K1 exists; then a person's edit of `a` is queued, collapsed - the event that will name a gone row."""
    with channel(event_constants.CHANNEL_API), outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
        for a in ("v", "w"):
            crud.apply_batch_updates(db, T, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
                updates={"k": "K1", "a": a}, source_name="user", updated_by="gone")]))
            db.commit()
    events = (db.query(models.DatabaseOutbox).filter(models.DatabaseOutbox.processed_chain.is_(False))
              .order_by(models.DatabaseOutbox.id).all())
    edit = events[-1]
    assert edit.event_type == "EDIT" and event_constants.is_collapsed_payload(get_payload_dict(edit)), "canary"
    row_id = db.execute(text("SELECT row_id FROM %s" % T)).scalar()
    return edit, row_id


def _run(db, edit):
    return worker._process_chain_transaction_group_sync(get_payload_dict(edit).get("transaction_id"), [edit],
                                                        db, [dict(RULE)])[:2]


@pytest.mark.parametrize("door", ["the grid's delete", "the map purge", "the job retraction"])
def test_an_event_naming_only_rows_a_door_deleted_succeeds_with_nothing_to_do(db, door):
    edit, row_id = _edit_waiting(db)
    model = models.DYNAMIC_TABLES[T]
    if door == "the grid's delete":
        crud.delete_rows_batch(db, T, [row_id], "gone")
    elif door == "the map purge":
        crud.purge_map_rows(db, model, T, [row_id])
        db.commit()
    else:
        dt_map_derivation.apply_retraction(db, {"target_table": T, "delete_row_ids": [row_id]})
    assert db.query(model).count() == 0 and crud.deleted_rows(db, T, [row_id]) == {row_id}
    CALLED.clear()
    assert (_run(db, edit), CALLED) == ((True, None), []), "no rule is handed an event of gone rows"


def test_a_row_gone_with_no_history_line_is_refused_as_before(db):
    edit, row_id = _edit_waiting(db)
    db.execute(text("DELETE FROM %s WHERE row_id = :r" % T), {"r": row_id})
    db.commit()
    ok, error = _run(db, edit)
    assert (ok, (error or "").startswith(worker.ROWS_NOT_VISIBLE)) == (False, True)


def test_a_row_a_rule_only_keyed_is_not_asked(db):
    """A rule whose write creates a row with its key alone - nothing emptied - leaves the row."""
    keys_only = dict(RULE, name="keys_rule", mapper="keys_mapper", trigger_table=T, target_table="gone_keys")
    crud.TABLE_CONFIG["gone_keys"] = {"business_key": "k", "composite_key_source": ["k"],
                                      "column_types": {"k": "string", "x": "string"}, "display_columns": ["k", "x"]}
    models.init_dynamic_models({"gone_keys": crud.TABLE_CONFIG["gone_keys"]})
    models.DYNAMIC_TABLES["gone_keys"].__table__.create(bind=db.get_bind(), checkfirst=True)
    mapper_sdk.register("keys_mapper", lambda db, payload, rule=None: {"updates": [
        {"updates": {"k": ((p.get("data") or {}).get("k") or {}).get("value")}, "source_name": "chain_ingestion"}
        for p in (payload if isinstance(payload, list) else [payload])]})
    try:
        edit, _row_id = _edit_waiting(db)
        ok, error, _ = worker._process_chain_transaction_group_sync(
            get_payload_dict(edit).get("transaction_id"), [edit], db, [keys_only])
        assert (ok, error) == (True, None)
        assert db.execute(text("SELECT k FROM gone_keys")).scalars().all() == ["K1"]
    finally:
        crud.TABLE_CONFIG.pop("gone_keys", None)
        mapper_sdk.MAPPER_REGISTRY.pop("keys_mapper", None)
        mapper_sdk.MAPPER_PARAMS.pop("keys_mapper", None)
