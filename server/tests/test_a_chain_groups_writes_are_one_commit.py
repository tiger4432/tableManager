# -*- coding: utf-8 -*-
"""총괄 09f58844f (C 다섯 단계 ⑤⑥⑦) — a chain group's writes, withdrawals, shells, deleted rows' withdrawal and
processed mark are ONE commit, its holder's (`session_contract.hold_commit` · `end_step` · `undo_step`).

  sqlite  the seat: steps release, an undone step keeps the ones before it, any other commit is refused while held,
          a step called alone commits as before
          the group: nothing of it is left when it dies before its mark · its deleted rows' withdrawal rides the mark's
          commit · a mapper's commit on a further page (more()) is refused, by its sentence on the queue · on the first
          page (before the write stage) it is as before
          ⑥ the edit withdrawal's columns come from what was written · ⑦ an output row its mapper left without its
          source row gets it by key, the plain layer it sat on goes, a deleted source leaves no old value · several
          matches: «origin unknown» once by the rule's name
          a deadlock with a save rewinds, says how many times
  PG      a save over HTTP waits for a held row at most `save_lock_timeout_seconds`, then is told to save again
"""
import asyncio
import logging
import os
import sys
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import event_constants                                              # noqa: E402
import mapper_sdk                                                   # noqa: E402
import session_contract                                             # noqa: E402
from chain import ingestion_worker as worker                        # noqa: E402
from database import crud, models, schemas                          # noqa: E402
from database.database import Base                                  # noqa: E402
from utils.payload_helper import get_payload_dict                   # noqa: E402

SRC, DST = "oc_src", "oc_dst"
TABLES = {SRC: {"business_key": "k", "composite_key_source": ["k"], "column_types": {"k": "string", "v": "string"},
                "display_columns": ["k", "v"]},
          DST: {"business_key": "k", "composite_key_source": ["k"], "column_types": {"k": "string", "w": "string"},
                "display_columns": ["k", "w"]}}
PAGES = []          # what the paging mapper's further page does: "commit" or nothing


def _rows(payload):
    return payload if isinstance(payload, list) else [payload]


def _copy(db, payload, rule=None):
    """k -> k, v -> w, WITHOUT the row it read (a frame cut to the columns it writes)."""
    return {"updates": [{"updates": {"k": (one["data"].get("k") or {}).get("value"),
                                     "w": (one["data"].get("v") or {}).get("value")}}
                        for one in _rows(payload) if one.get("data")]}


def _first_letter(db, payload, rule=None):
    """Every row onto the row its key's first letter names - several handed rows match one output row."""
    return {"updates": [{"updates": {"k": ((one["data"].get("k") or {}).get("value") or "?")[0], "w": "x"}}
                        for one in _rows(payload) if one.get("data")]}


def _paging(db, payload, rule=None):
    rows = [one for one in _rows(payload) if one.get("data")]

    def page():
        if "commit" in PAGES:
            db.commit()
        return {"updates": [{"updates": {"k": "P2", "w": "two"}}]}
    if "first" in PAGES:
        db.commit()                                     # before the write stage - as today
    return {"updates": [{"updates": {"k": "P1", "w": "one"}, "origin_row_id": rows[0]["row_id"]}],
            "next_page": page}


MAPPERS = {"oc_copy": _copy, "oc_first": _first_letter, "oc_paging": _paging}


@pytest.fixture(name="db")
def fixture_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    for name, body in MAPPERS.items():
        mapper_sdk.register(name, body)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    PAGES.clear()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)
        for name in MAPPERS:
            mapper_sdk.MAPPER_REGISTRY.pop(name, None)
            mapper_sdk.MAPPER_PARAMS.pop(name, None)


def _rule(mapper, **more):
    return dict({"name": mapper, "mapper": mapper, "trigger_table": SRC, "target_table": DST, "enabled": True,
                 "is_batch": True}, **more)


def _push(db, rows, table=SRC):
    from database.context import channel, outbox_mode

    with channel(event_constants.CHANNEL_API), outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
        crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates=dict(r), source_name="user", updated_by="oc") for r in rows]))
    db.commit()


def _waiting(db, table=None):
    O = models.DatabaseOutbox
    return (db.query(O).filter(O.processed_chain.is_(False), *([O.table_name == table] if table else []))
            .order_by(O.id).all())


def _group(db, rules):
    """One group of every waiting event, through the claim that commits it (`_claimed_group_sync`)."""
    events = _waiting(db, SRC)
    return worker._claimed_group_sync("oc_tx", events, db, rules)


def _dst(db):
    db.expire_all()
    return {row.business_key_val: row.w for row in db.query(models.DYNAMIC_TABLES[DST])}


def _layers(db, table=DST):
    S = models.CellSource
    return sorted((r, c, s, o) for r, c, s, o in db.query(S.row_id, S.column_name, S.source_name, S.origin_row_id)
                  .filter(S.table_name == table, S.column_name != "k"))


# ------------------------------------------------------------------------------ the seat

def _count(db, table=DST):
    return db.query(models.DYNAMIC_TABLES[table]).count()


def _write(db, k, w="v"):
    crud.apply_batch_updates(db, DST, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates={"k": k, "w": w}, source_name="user", updated_by="oc")]))


def test_held_steps_are_savepoints_of_one_commit_and_another_commit_is_refused(db):
    db.execute(text("CREATE TABLE oc_plain (x INTEGER)"))
    db.commit()
    session_contract.hold_commit(db)
    _write(db, "A")                                       # its end_step: a savepoint released
    with pytest.raises(session_contract.CommitRefused, match=session_contract.COMMIT_REFUSED):
        db.commit()
    db.execute(text("INSERT INTO oc_plain VALUES (1)"))
    session_contract.undo_step(db)                        # back to after A
    assert _count(db) == 1 and db.execute(text("SELECT count(*) FROM oc_plain")).scalar() == 0
    session_contract.release_hold(db)
    assert db.info.get(session_contract.HELD_STEP) is None
    db.commit()                                           # the caller's one commit
    db.rollback()
    assert _count(db) == 1, "the caller's commit took A"


def test_a_step_called_alone_commits_as_it_always_did(db):
    _write(db, "A")
    db.rollback()
    assert _count(db) == 1, "a write's end_step not held is a commit (the API path)"


def test_a_held_transaction_that_rolls_back_is_not_held_after(db):
    session_contract.hold_commit(db)
    _write(db, "A")
    db.rollback()
    assert session_contract._held(db) is None
    _write(db, "B")
    db.rollback()
    assert _count(db) == 1


# ------------------------------------------------------------------------------ the group

def test_a_group_that_dies_before_its_mark_leaves_nothing(db, monkeypatch):
    _push(db, [{"k": "K1", "v": "a"}, {"k": "K2", "v": "b"}])

    def dies(event, status):
        raise RuntimeError("killed before the mark")
    monkeypatch.setattr(worker, "mark_processed", dies)
    with pytest.raises(RuntimeError, match="killed before the mark"):
        _group(db, [_rule("oc_copy")])
    db.rollback()
    assert _dst(db) == {} and _layers(db) == [], "its write went with it"
    assert len(_waiting(db, SRC)) == 1


def test_a_group_commits_its_write_and_its_mark_together(db):
    _push(db, [{"k": "K1", "v": "a"}])
    ok, error, _ = _group(db, [_rule("oc_copy")])
    assert ok, error
    db.rollback()
    assert _dst(db) == {"K1": "a"} and _waiting(db, SRC) == []


def test_the_deleted_rows_withdrawal_rides_the_marks_commit(db, monkeypatch):
    _push(db, [{"k": "K1", "v": "a"}])
    ok, error, _ = _group(db, [_rule("oc_copy")])
    assert ok, error
    assert _layers(db), "K1's copy sits on K1's layer (⑦)"
    src_row = db.query(models.DYNAMIC_TABLES[SRC]).one().row_id
    crud.delete_rows_batch(db, SRC, [src_row], "oc")

    def dies_at_the_mark(event, status):
        raise RuntimeError("killed at the mark")
    monkeypatch.setattr(worker, "mark_processed", dies_at_the_mark)     # after the withdrawal, before the commit
    with pytest.raises(RuntimeError, match="killed at the mark"):
        _group(db, [_rule("oc_copy")])
    monkeypatch.undo()
    db.rollback()
    assert _layers(db), "the withdrawal went with the mark - not committed before it"
    ok, error, _ = _group(db, [_rule("oc_copy")])
    assert ok, error
    db.rollback()
    assert _layers(db) == [] and _waiting(db, SRC) == []


def test_a_mappers_commit_on_a_further_page_is_refused_and_leaves_nothing(db):
    PAGES.append("commit")
    _push(db, [{"k": "K1", "v": "a"}])
    ok, error, _ = _group(db, [_rule("oc_paging")])
    assert not ok and session_contract.COMMIT_REFUSED in str(error)
    assert "return rows; the worker writes them" in event_constants.failure_cause(error), "the queue says it"
    db.rollback()
    assert _dst(db) == {}, "its first page went with it"


def test_a_mappers_commit_on_its_first_page_is_as_before(db):
    PAGES.append("first")
    _push(db, [{"k": "K1", "v": "a"}])
    ok, error, _ = _group(db, [_rule("oc_paging")])
    assert ok, error
    db.rollback()
    assert _dst(db) == {"P1": "one", "P2": "two"}


# ------------------------------------------------------------------------------ ⑥ ⑦

def test_an_output_row_its_mapper_left_without_its_source_gets_it_by_key(db):
    _push(db, [{"k": "K1", "v": "a"}])
    ok, error, _ = _group(db, [_rule("oc_copy")])
    assert ok, error
    src_row = db.query(models.DYNAMIC_TABLES[SRC]).one().row_id
    [(row, column, source, origin)] = _layers(db)
    assert (column, origin) == ("w", src_row) and source == crud.merged_layer_name(crud.CHAIN_SOURCE, src_row)


def test_the_plain_layer_it_sat_on_moves_and_a_deleted_source_leaves_no_old_value(db):
    from chain import rule_shape

    rule = _rule("oc_copy")
    # before the landing: the rule's cell on the plain chain layer, its old value
    crud.apply_batch_updates(db, DST, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        updates={"k": "K1", "w": "old"}, source_name=crud.CHAIN_SOURCE, updated_by=rule_shape.declaration_of(rule))]))
    _push(db, [{"k": "K1", "v": "new"}])
    ok, error, _ = _group(db, [rule])
    assert ok, error
    assert [layer[2] for layer in _layers(db)] == [crud.merged_layer_name(crud.CHAIN_SOURCE, layer[3])
                                                  for layer in _layers(db)], "the plain layer went"
    src_row = db.query(models.DYNAMIC_TABLES[SRC]).one().row_id
    crud.delete_rows_batch(db, SRC, [src_row], "oc")
    ok, error, _ = _group(db, [rule])
    assert ok, error
    assert _dst(db).get("K1") in (None, ""), "the old value does not come back"


def test_several_matches_leave_it_without_and_say_so_once(db, caplog):
    _push(db, [{"k": "A1", "v": "a"}, {"k": "A2", "v": "b"}])
    with caplog.at_level(logging.WARNING):
        ok, error, _ = _group(db, [_rule("oc_first")])
    assert ok, error
    said = [r.getMessage() for r in caplog.records if "origin unknown - rule oc_first" in r.getMessage()]
    assert len(said) == 1 and "2 of 2 row(s)" in said[0]
    assert [layer[3] for layer in _layers(db)] == [None]


def test_the_edit_withdrawal_takes_its_columns_from_what_was_written(db):
    from chain import rule_run

    assert not hasattr(rule_run, "_COLUMNS_SEEN"), "no process memory answers which columns a rule writes"
    rule = _rule("oc_copy")
    _push(db, [{"k": "K1", "v": "a"}])
    assert _group(db, [rule])[0]
    _push(db, [{"k": "K1", "v": "b"}])
    assert _group(db, [rule])[0]
    assert _dst(db) == {"K1": "b"} and len(_layers(db)) == 1


# ------------------------------------------------------------------------------ a deadlock with a save

def test_a_deadlock_with_a_save_rewinds_uncharged_and_says_how_many_times(db, monkeypatch):
    _push(db, [{"k": "K1", "v": "a"}])

    async def deadlocked(tx_id, events, session, rules):
        return False, "psycopg2.errors.DeadlockDetected: deadlock detected", []
    monkeypatch.setattr(worker, "process_chain_transaction_group", deadlocked)
    for _ in range(2):
        events = _waiting(db)
        asyncio.run(worker.process_pending_groups(db, ["oc_tx"], {"oc_tx": events}, [_rule("oc_copy")], None))
    db.expire_all()
    [event] = _waiting(db)
    assert (event.retry_count, event.status) == (0, "RETRYING"), "tried again, no attempt charged"
    said = get_payload_dict(event)[event_constants.LAST_FAILURE]
    assert said == "deadlock with a save, rewound 2 time(s)"
    from chain import queue_lines
    [line] = queue_lines.waiting_lines(db, 10)
    assert line.retrying and line.max_retry == 0, "the queue's retrying line, where its last failure is said"


# ------------------------------------------------------------------------------ PG: a save behind a held row

@pytest.mark.pg
def test_a_save_waits_for_a_held_row_at_most_its_limit_then_is_told_to_save_again(pg_session, pg_engine, monkeypatch):
    import main
    from database.context import channel
    from parsers import directory_watcher
    from sqlalchemy.exc import OperationalError

    table = "pgqa_bk_table"
    crud.apply_batch_updates(pg_session, table, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates={"part_no": "P1", "qty": 1}, source_name="user", updated_by="oc")]))
    session_contract.hold_commit(pg_session)                    # a chain group's write stage, still open
    crud.apply_batch_updates(pg_session, table, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates={"part_no": "P1", "qty": 2}, source_name="chain_ingestion",
                                  updated_by="oc")]))
    monkeypatch.setattr(directory_watcher, "save_lock_timeout", lambda settings=None: 1.0)
    save = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)()
    try:
        with channel(event_constants.CHANNEL_API), pytest.raises(OperationalError) as refused:
            crud.apply_batch_updates(save, table, schemas.GeneralUpdateBatch(updates=[
                schemas.GeneralUpdateItem(updates={"part_no": "P1", "qty": 3}, source_name="user", updated_by="p")]))
        save.rollback()
    finally:
        save.close()
    answer = asyncio.run(main._a_lock_not_got(SimpleNamespace(method="PUT", url=SimpleNamespace(path="/t")),
                                              refused.value))
    assert answer.status_code == 409 and b"Another write is in progress - save again" in answer.body
    session_contract.release_hold(pg_session)
    pg_session.commit()


@pytest.mark.pg
def test_a_held_write_locks_the_rows_it_read_even_when_it_changes_none(pg_session, pg_engine, monkeypatch):
    """The lost update (C 간섭 ①): the write reads its rows and their layers to compute its cells - those rows are
    locked as read, so a second writer waits even where the first wrote the same value (no UPDATE of its own)."""
    from database.context import channel
    from parsers import directory_watcher
    from sqlalchemy.exc import OperationalError

    table = "pgqa_bk_table"
    item = {"part_no": "P1", "qty": 1}
    crud.apply_batch_updates(pg_session, table, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates=dict(item), source_name="user", updated_by="oc")]))
    session_contract.hold_commit(pg_session)
    crud.apply_batch_updates(pg_session, table, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates=dict(item), source_name="user", updated_by="oc")]))   # the same value
    monkeypatch.setattr(directory_watcher, "save_lock_timeout", lambda settings=None: 1.0)
    save = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)()
    try:
        with channel(event_constants.CHANNEL_API), pytest.raises(OperationalError):
            crud.apply_batch_updates(save, table, schemas.GeneralUpdateBatch(updates=[
                schemas.GeneralUpdateItem(updates={"part_no": "P1", "qty": 3}, source_name="user", updated_by="p")]))
        save.rollback()
    finally:
        save.close()
    session_contract.release_hold(pg_session)
    pg_session.commit()


# ------------------------------------------------------------------------------ a deletion set aside, run again

def test_a_deletion_run_again_after_its_set_aside_withdrew_it_withdraws_nothing_more(db, monkeypatch):
    """총괄 g26: a rule with lineage had what the deleted row fed withdrawn when the deletion was set aside; the
    deletion rerun_set_aside puts back reaches it again and changes nothing."""
    from admin import retroactive
    from chain import replay, set_aside

    rule = _rule("oc_copy", allow_delete_trigger=True)
    monkeypatch.setattr(replay, "load_rules", lambda: [rule])
    _push(db, [{"k": "K1", "v": "a"}, {"k": "K2", "v": "b"}])
    assert _group(db, [rule])[0]
    gone = db.query(models.DYNAMIC_TABLES[SRC]).filter_by(business_key_val="K1").one().row_id
    crud.delete_rows_batch(db, SRC, [gone], "oc")
    set_aside.set_aside(db, ids=[e.id for e in _waiting(db, SRC)], apply=True)
    before = (_layers(db), _dst(db), _count(db))
    assert all(origin != gone for *_rest, origin in before[0]), "withdrawn by its lineage when set aside"

    out = retroactive._run_rerun_set_aside(db, {"tables": [SRC]}, lambda line: None)
    assert out["deletions_staged"] == 1
    ok, error, _ = _group(db, [rule])
    assert ok, error
    assert (_layers(db), _dst(db), _count(db)) == before and _waiting(db, SRC) == []
