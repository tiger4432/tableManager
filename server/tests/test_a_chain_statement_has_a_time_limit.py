# -*- coding: utf-8 -*-
"""소유자 10-08 「체인 타임아웃 걸어」 · 「DB 질의 하나」 · 「2분」 (총괄 7a4f18281 · ㄴ): a chain group's statement
runs at most `chain_statement_timeout_seconds` (ingestion_settings.json - the file limits' file and
read; 120 by default, 0 = none). The one `after_begin` listener that bounds a file's writes sets it on
every transaction a chain group begins - whatever channel its writes go out on, a replay's too; past
it the database stops the statement, the group fails once with the limit, its stage and its rule in
the record, and the chain goes on to the next group."""
import asyncio
import os
import sys
import textwrap
import time

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import event_constants                                                # noqa: E402
import mapper_sdk                                                     # noqa: E402
import paths                                                          # noqa: E402
from admin import retroactive                                         # noqa: E402
from chain import ingestion_worker as worker                          # noqa: E402
from chain import replay                                              # noqa: E402
from database import crud, models, schemas                            # noqa: E402
from database.context import chain_group, channel                     # noqa: E402
from database.database import Base                                    # noqa: E402
from parsers import directory_watcher as dw                           # noqa: E402
from utils import heartbeat                                           # noqa: E402
from utils import logger as process_logging                           # noqa: E402
from utils.payload_helper import get_payload_dict                     # noqa: E402

CELL = dw.CHAIN_STATEMENT_TIMEOUT_SETTING
CANCELLED = "Traceback (most recent call last):\npsycopg2.errors.QueryCanceled: (the server's words)"
CHAIN, RETRO = event_constants.CHANNEL_CHAIN, event_constants.CHANNEL_RETROACTIVE
FILE, API = event_constants.CHANNEL_FILE, event_constants.CHANNEL_API


@pytest.mark.parametrize("written, limit", [
    ({}, dw.CHAIN_STATEMENT_TIMEOUT_DEFAULT), ({CELL: 0}, None), ({CELL: None}, None),
    ({CELL: "5"}, dw.CHAIN_STATEMENT_TIMEOUT_DEFAULT), ({CELL: -1}, dw.CHAIN_STATEMENT_TIMEOUT_DEFAULT),
    ({CELL: True}, dw.CHAIN_STATEMENT_TIMEOUT_DEFAULT), ({CELL: 5}, 5.0)],
    ids=["absent", "zero", "null", "text", "negative", "boolean", "five"])
def test_the_chain_limit_is_read_as_the_file_limits_are(written, limit):
    assert dw.chain_statement_timeout(written) == limit


def test_a_statement_stopped_by_the_limit_is_said_with_the_limit_its_stage_and_its_rule(monkeypatch):
    monkeypatch.setattr(dw, "load_ingestion_settings", lambda: {CELL: 2})
    failed = worker.named_failure(["r1"], ["t1"], CANCELLED)

    said = worker._said_timeout(failed, "write:t1", 2.5)

    assert worker.failure_cause(said) == (
        "[rules=r1 target=t1] statement timeout · 2 s · stage write:t1 - one statement of this group "
        "ran past %s (ingestion_settings.json); the database stopped it" % CELL)
    assert (said.rules, said.tables) == (["r1"], ["t1"])
    assert worker._said_timeout(failed, "write:t1", 1.0) is failed            # younger than the limit
    assert worker._said_timeout(worker.named_failure(["r1"], ["t1"], "ValueError: x"), "s", 9) != said
    monkeypatch.setattr(dw, "load_ingestion_settings", lambda: {CELL: 0})
    assert worker._said_timeout(failed, "write:t1", 9.0) is failed            # no limit: not ours


@pytest.mark.pg
@pytest.mark.parametrize("in_group, on, written, shown", [
    (True, None, {}, "2min"),
    (True, None, {CELL: 5}, "5s"),
    (True, None, {CELL: 0}, None),
    (True, CHAIN, {CELL: 5}, "5s"),
    (True, RETRO, {CELL: 5}, "5s"),
    (False, CHAIN, {CELL: 5}, None),
    (False, RETRO, {CELL: 5}, None),
    (False, FILE, {"statement_timeout_seconds": 7, CELL: 5}, "7s"),
    (False, API, {CELL: 5}, None),
    (False, None, {CELL: 5}, None),
], ids=["group-default", "group-five", "group-off", "group-chain-write", "group-replay-write",
        "chain-channel-outside-a-group", "replay-run-outside-a-group", "file-unchanged", "api",
        "nothing"])
def test_a_transaction_begun_in_a_chain_group_carries_the_chain_limit(pg_engine, monkeypatch, in_group,
                                                                     on, written, shown):
    monkeypatch.setattr(dw, "load_ingestion_settings", lambda: dict(written))
    session = sessionmaker(bind=pg_engine)()
    try:
        untouched = session.execute(text("SHOW statement_timeout")).scalar()
        session.rollback()
        with channel(on):
            if in_group:
                with chain_group():
                    got = session.execute(text("SHOW statement_timeout")).scalar()
            else:
                got = session.execute(text("SHOW statement_timeout")).scalar()
        session.rollback()
    finally:
        session.close()
    assert got == (untouched if shown is None else shown)


# ------------------------------------------------------------------ a whole group, on PostgreSQL

TA, TB, TC = "tl_a", "tl_b", "tl_c"
TABLES = {name: {"business_key": "k", "composite_key_source": ["k"],
                 "column_types": {"k": "string", "n": "string"}, "display_columns": ["k", "n"]}
          for name in (TA, TB, TC)}
#: Passes `k` on; a row whose `n` is a number of seconds asks the database to wait that long first.
SLOW = """
from sqlalchemy import text

def pass_on(db, payload, rule=None):
    out = []
    for p in (payload if isinstance(payload, list) else [payload]):
        data = p.get("data") or {}
        k = (data.get("k") or {}).get("value")
        n = (data.get("n") or {}).get("value")
        if n:
            db.execute(text("SELECT pg_sleep(%s)" % float(n)))
        out.append({"business_key_val": k, "updates": {"k": k}})
    return {"updates": out}
"""
RULES = [{"name": "tl_a_to_b", "enabled": True, "is_batch": True, "trigger_table": TA,
          "target_table": TB, "mapper_module": "tl_slow", "mapper_function": "pass_on",
          "allow_chain_trigger": False},
         {"name": "tl_c_to_a", "enabled": True, "is_batch": True, "trigger_table": TC,
          "target_table": TA, "mapper_module": "tl_slow", "mapper_function": "pass_on",
          "allow_chain_trigger": False}]


@pytest.fixture(name="pg_db")
def fixture_pg_db(pg_engine, tmp_path, monkeypatch):
    """A scratch-schema session, the three tables, the slow mapper, and the beats, the pause file and
    the settings in this test's own directory."""
    from conftest import PG_TEST_SCHEMA, retire_dynamic_model

    def clean():
        with pg_engine.begin() as conn:
            for name in TABLES:
                conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, name)))
            for table in ("cell_sources", "database_outbox"):
                conn.execute(text('DELETE FROM "%s".%s WHERE table_name IN (:a, :b, :c)' % (
                    PG_TEST_SCHEMA, table)), {"a": TA, "b": TB, "c": TC})
    monkeypatch.setattr(paths, "CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(heartbeat, "heartbeat_dir", lambda: str(tmp_path / "beats"))
    monkeypatch.setattr(heartbeat, "heartbeat_path",
                        lambda name: str(tmp_path / "beats" / (name + ".json")))
    monkeypatch.setattr(process_logging, "active_process_name", lambda: "Chain")
    monkeypatch.setattr(retroactive, "announce_progress", lambda *a, **k: None)

    async def no_notice(pending, factory):
        """A group's notices stay here - a test passed or failed never reaches the API a box runs
        (총괄 daf4985d5 QA: a 401 from 127.0.0.1:8080, nothing sent). The order guard's own stand-in."""
    monkeypatch.setattr(worker, "_dispatch_broadcasts", no_notice)
    mapper_sdk.discover()
    (tmp_path / "tl_slow.py").write_text(textwrap.dedent(SLOW), encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("tl_slow", None)
    for name in TABLES:
        retire_dynamic_model(name)
    clean()
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=pg_engine)
    models.sync_dynamic_tables_schema(pg_engine)
    made = sessionmaker(bind=pg_engine)
    monkeypatch.setattr("database.database.SessionLocal", made)
    db = made()
    try:
        yield db
    finally:
        db.rollback()
        db.close()
        clean()
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)
            retire_dynamic_model(name)
        sys.modules.pop("tl_slow", None)


def _write(db, table, row):
    with channel(API):
        crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates=row, source_name="seed", updated_by="tl")]))
        db.commit()


def _pending(db):
    """This file's waiting events - the session's scratch schema is shared, and another file's
    leftovers counted here made `slow, quick = _pending(...)` three (총괄 10-08 QA)."""
    return (db.query(models.DatabaseOutbox)
            .filter(models.DatabaseOutbox.processed_chain.is_(False),
                    models.DatabaseOutbox.table_name.in_(sorted(TABLES)))
            .order_by(models.DatabaseOutbox.id).all())


def _run_the_queue(db):
    """`process_pending_groups` over what is pending, each transaction its own group, in order. The
    read leaves its transaction open, as the worker's batch read does: the first group's statements run
    in a transaction begun before that group."""
    groups = {}
    for event in _pending(db):
        groups.setdefault(get_payload_dict(event).get("transaction_id"), []).append(event)
    started = time.time()
    asyncio.run(worker.process_pending_groups(db, list(groups), groups, RULES, None))
    db.expire_all()
    return time.time() - started, groups


def _said(event):
    return (get_payload_dict(event).get("error_log") or {}).get("reason")


def _rows(db, table):
    return sorted(r.k for r in db.query(models.DYNAMIC_TABLES[table]).all())


STOPPED = ("[rules=tl_a_to_b target=tl_b] statement timeout · 1 s · stage mapper - one statement of "
           "this group ran past %s (ingestion_settings.json); the database stopped it" % CELL)


@pytest.mark.pg
@pytest.mark.parametrize("limit, stopped", [(1, True), (0, False)], ids=["one-second", "off"])
def test_a_group_whose_statement_runs_past_the_limit_fails_once_and_the_next_group_runs(
        pg_db, monkeypatch, limit, stopped):
    monkeypatch.setattr(dw, "load_ingestion_settings", lambda: {CELL: limit})
    _write(pg_db, TA, {"k": "A1", "n": "5"})                     # 5 s in its mapper
    _write(pg_db, TC, {"k": "B1", "n": ""})                      # touches neither tl_b nor the wait
    slow, quick = _pending(pg_db)

    ran, _groups = _run_the_queue(pg_db)

    pg_db.refresh(slow)
    pg_db.refresh(quick)
    assert quick.status == "SUCCESS" and "B1" in _rows(pg_db, TA), "the next group did not run"
    if stopped:
        assert (slow.status, slow.retry_count, _said(slow)) == ("FAILED", 1, STOPPED)
        assert _rows(pg_db, TB) == []
        assert ran < 4, "the statement was waited out"
    else:
        assert slow.status == "SUCCESS" and _rows(pg_db, TB) == ["A1"]


@pytest.mark.pg
def test_a_group_a_replay_woke_is_stopped_the_same(pg_db, monkeypatch):
    monkeypatch.setattr(dw, "load_ingestion_settings", lambda: {CELL: 1})
    _write(pg_db, TA, {"k": "A1", "n": "5"})
    for event in _pending(pg_db):                                # the write's own wake, done
        event_constants.mark_processed(event, "SUCCESS")
    pg_db.commit()
    row_id = pg_db.query(models.DYNAMIC_TABLES[TA]).one().row_id
    replay.replay_rule(pg_db, RULES[0], apply=True, log=lambda m: None, row_ids=[row_id])
    woken = _pending(pg_db)
    assert woken and all(event_constants.replay_of(get_payload_dict(e)) for e in woken), \
        "the replay staged no event of its own"

    ran, _groups = _run_the_queue(pg_db)

    for event in woken:
        pg_db.refresh(event)
        assert (event.status, _said(event)) == ("FAILED", STOPPED)
    assert ran < 4


@pytest.mark.pg
def test_an_edit_retraction_the_limit_stopped_stays_contained_and_says_the_limit(
        pg_db, monkeypatch, caplog):
    from chain import rule_run
    monkeypatch.setattr(dw, "load_ingestion_settings", lambda: {CELL: 1})
    _write(pg_db, TA, {"k": "A1", "n": ""})
    _run_the_queue(pg_db)
    _write(pg_db, TA, {"k": "A1", "n": "0"})                     # an edit of a row it fed
    monkeypatch.setattr(rule_run, "stamps_its_origin", lambda rule: True)
    monkeypatch.setattr(worker, "_withdraw_and_tell",
                        lambda db, *a, **k: db.execute(text("SELECT pg_sleep(5)")))
    edited = [e for e in _pending(pg_db) if e.table_name == TA]
    assert [e.event_type for e in edited] == ["EDIT"]

    ran, _groups = _run_the_queue(pg_db)

    pg_db.refresh(edited[0])
    assert edited[0].status == "SUCCESS", "the retraction's failure left its group"
    said = [r.getMessage() for r in caplog.records if "[ChainRetract]" in r.getMessage()]
    assert len(said) == 1 and "old layers may remain: statement timeout · 1 s - [OperationalError]" \
        in said[0], said
    assert ran < 4
