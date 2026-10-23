# -*- coding: utf-8 -*-
"""총괄 35b76ba92 — 표 하나를 통째로 비운다 (소유자 10-02 「100만 행인데 어케 지움」), 소유자 10-23 부터
«Delete every row of a table» 의 full reset (was scripts/empty_table.py).

On PostgreSQL, on the hold-copy world: the dry run says what goes; the apply takes the rows, the
table's cell layers and overwrites in one transaction with one summary audit line, withdraws the
ledger atoms of every source reading the table through `rescope`, and leaves no outbox event. It
refuses a count that moved and a view; the op takes confirm_rows with a full reset and only then.
"""
import os
import sys

import pytest
from sqlalchemy import text

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from admin import retroactive                                        # noqa: E402
from chain import replay                                             # noqa: E402
from database import crud, models, schemas                           # noqa: E402
from support import hold_world as hw                                 # noqa: E402

pytestmark = pytest.mark.pg


@pytest.fixture(name="world")
def fixture_world(pg_engine, monkeypatch, tmp_path):
    yield from hw.build(pg_engine, monkeypatch, tmp_path)


def _seeded(world):
    """Two official rows (two keys), said by the ledger, and a person's cell on one."""
    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7},
                    {"log_id": "B", "dt_job": "J2", "dt_x": 3, "dt_y": 4, "netdie": 8}])
    hw.settle(world)
    db = world["db"]
    target = db.query(models.DYNAMIC_TABLES[hw.OFFICIAL]).filter_by(dt_job="J2").one().row_id
    crud.apply_batch_updates(db, hw.OFFICIAL, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(row_id=target, updates={"netdie": 9}, source_name=crud.USER_SOURCE,
                                  updated_by="person")]))
    db.commit()
    hw.settle(world)
    assert len(hw.said(world)) == 2


def _count(world, sql, **params):
    return world["db"].execute(text(sql), params).scalar()


def _reset(world, **kw):
    return replay.full_reset(world["db"], hw.OFFICIAL, setup=world["setup"], rules=world["rules"], **kw)


def test_the_command_line_registers_the_declared_tables_itself(world, monkeypatch, pg_engine, capsys):
    """총괄 151688c2b (소유자 10-08): run as a command, nothing has registered the tables yet - the command
    must register them from table_config, as the other entry points do."""
    if os.path.join(SERVER_DIR, "scripts") not in sys.path:
        sys.path.append(os.path.join(SERVER_DIR, "scripts"))                 # after tests/: scripts has a support too
    import chain_replay_cli
    from sqlalchemy.orm import sessionmaker
    from conftest import retire_dynamic_model
    from database import database
    from ledger import setup as ledger_setup

    _seeded(world)
    before = set(models.DYNAMIC_TABLES)
    for name in hw.TABLES:
        retire_dynamic_model(name)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=pg_engine))
    monkeypatch.setattr(ledger_setup, "load_setup", lambda: world["setup"])
    try:
        code = chain_replay_cli.main(["delete-every-row", hw.OFFICIAL, "--how", "full_reset"])
    finally:
        for name in set(models.DYNAMIC_TABLES) - before:
            retire_dynamic_model(name)
    said = capsys.readouterr().out
    assert code == 0 and "not a declared table" not in said, said
    assert "Full reset of '%s': 2 row(s)" % hw.OFFICIAL in said, said


def test_the_dry_run_says_what_goes_and_writes_nothing(world):
    _seeded(world)
    found = _reset(world)
    assert (found["rows"], found["user_layers"], found["ledger_atoms"], found["chain_rules"]) \
        == (2, 1, {hw.SOURCE: 2}, [hw.RECOUNT["name"]])
    assert found["layers"] > found["user_layers"] and found["overwrites"] > 0
    assert _count(world, 'SELECT count(*) FROM "%s"' % hw.OFFICIAL) == 2


def test_apply_takes_rows_layers_overwrites_and_atoms_and_wakes_nothing(world):
    _seeded(world)
    log_layers = _count(world, "SELECT count(*) FROM cell_sources WHERE table_name = :t", t=hw.LOG)
    outbox = _count(world, "SELECT coalesce(max(id), 0) FROM database_outbox")
    history = "SELECT count(*) FROM audit_logs WHERE table_name = :t AND source_name = :s"
    lines = _count(world, history, t=hw.OFFICIAL, s=replay.FULL_RESET_SOURCE)
    result = _reset(world, confirm_rows=2, apply=True, by="tester")

    assert result["rows_deleted"] == 2
    assert result["ledger_withdrawn"] == {hw.SOURCE: 2}
    for sql in ('SELECT count(*) FROM "%s"' % hw.OFFICIAL,
                "SELECT count(*) FROM cell_sources WHERE table_name = '%s'" % hw.OFFICIAL,
                "SELECT count(*) FROM cell_overwrites WHERE table_name = '%s'" % hw.OFFICIAL,
                "SELECT count(*) FROM database_outbox WHERE id > %d" % outbox):
        assert _count(world, sql) == 0, sql
    assert hw.said(world) == []
    assert _count(world, "SELECT count(*) FROM cell_sources WHERE table_name = :t", t=hw.LOG) \
        == log_layers                                                 # the other table untouched
    assert _count(world, history, t=hw.OFFICIAL, s=replay.FULL_RESET_SOURCE) == lines + 1


def test_a_count_that_moved_is_refused_and_nothing_goes(world):
    _seeded(world)
    for confirm in (3, None):
        with pytest.raises(replay.ReplayRefused):
            _reset(world, confirm_rows=confirm, apply=True)
    assert _count(world, 'SELECT count(*) FROM "%s"' % hw.OFFICIAL) == 2
    assert len(hw.said(world)) == 2


def test_a_view_is_refused(world, monkeypatch):
    monkeypatch.setitem(crud.TABLE_CONFIG, hw.OFFICIAL, {**crud.TABLE_CONFIG[hw.OFFICIAL],
                                                         "kind": "view"})
    with pytest.raises(replay.ReplayRefused):
        _reset(world)


def test_the_op_takes_confirm_rows_with_a_full_reset_only_and_its_run_needs_it(world, monkeypatch):
    from chain import ingestion_worker
    from ledger import setup as ledger_setup

    _seeded(world)
    monkeypatch.setattr(ledger_setup, "load_setup", lambda: world["setup"])
    monkeypatch.setattr(ingestion_worker, "loaded_chain_rules", lambda: world["rules"])
    base = {"table": hw.OFFICIAL}
    for params in ({"confirm_rows": 2}, {"how": "by_row", "confirm_rows": 2}):
        with pytest.raises(retroactive.RetroactiveRefused):
            retroactive.validate("delete_every_row", dict(base, **params))
    for params in ({}, {"how": retroactive.FULL_RESET}, {"how": retroactive.FULL_RESET, "confirm_rows": 2}):
        assert retroactive.validate("delete_every_row", dict(base, **params)) == dict(base, **params)
    with pytest.raises(retroactive.RetroactiveRefused):
        retroactive._run_delete_every_row(world["db"], dict(base, how=retroactive.FULL_RESET), log=lambda m: None)
    assert _count(world, 'SELECT count(*) FROM "%s"' % hw.OFFICIAL) == 2
