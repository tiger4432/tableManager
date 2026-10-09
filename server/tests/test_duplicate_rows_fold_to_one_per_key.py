# -*- coding: utf-8 -*-
"""총괄 d72dc0283 (소유자 10-09 「해당 dtwaferid 중에서 최소 시간으로 접으면 되긴 함」): per key one row
stays - the earliest (or latest) by an order column, a blank one last, a tie the smaller row_id - and
the rest go through the product's delete door, a page at a time. Keys compare blank = NULL = NULL.
"""
import os
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from admin import retroactive                                          # noqa: E402
from chain import replay                                               # noqa: E402
from database.database import Base                                     # noqa: E402
from database import crud, models, schemas                             # noqa: E402

TABLE = "fold_rows_log"
TABLES = {TABLE: {"business_key": "log_id", "composite_key_source": ["log_id"],
                  "column_types": {"log_id": "string", "wafer": "string", "lot": "string",
                                   "ts": "string", "v": "number"},
                  "display_columns": ["log_id", "wafer", "lot", "ts", "v"]}}


@pytest.fixture(name="db")
def fixture_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        crud.TABLE_CONFIG.pop(TABLE, None)


def _seed(db, rows):
    crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates=dict(r), source_name="seed", updated_by="fold")
        for r in rows]))
    db.commit()


def _left(db):
    db.expire_all()
    return sorted(r.log_id for r in db.query(models.DYNAMIC_TABLES[TABLE]).all())


def _row_id(db, log_id):
    return db.query(models.DYNAMIC_TABLES[TABLE]).filter_by(log_id=log_id).one().row_id


def _fold(db, keys=("wafer",), keep="min", **kw):
    return replay.fold_duplicate_rows(db, TABLE, list(keys), "ts", keep=keep, apply=True,
                                      log=lambda m: None, **kw)


def test_the_earliest_of_a_key_stays_and_another_key_is_untouched(db):
    _seed(db, [{"log_id": "a2", "wafer": "W1", "ts": "2026-10-01 10:05:00"},
               {"log_id": "a1", "wafer": "W1", "ts": "2026-10-01 10:00:00"},
               {"log_id": "a3", "wafer": "W1", "ts": "2026-10-01 10:09:00"},
               {"log_id": "b1", "wafer": "W2", "ts": "2026-10-01 11:00:00"}])
    dry = replay.fold_duplicate_rows(db, TABLE, ["wafer"], "ts", log=lambda m: None)
    assert (dry["keys_folded"], dry["rows_to_delete"], dry["rows_kept"], dry["rows_deleted"]) == (1, 2, 2, 0)
    assert _left(db) == ["a1", "a2", "a3", "b1"]                         # the dry run writes nothing
    [one] = dry["sample"]
    assert one["key"] == {"wafer": "W1"} and one["rows"] == 3
    assert one["kept"]["row_id"] == _row_id(db, "a1")
    assert [d["row_id"] for d in one["deleted"]] == [_row_id(db, "a2"), _row_id(db, "a3")]
    done = _fold(db)
    assert done["rows_deleted"] == 2 and _left(db) == ["a1", "b1"]


def test_keep_max_keeps_the_latest(db):
    _seed(db, [{"log_id": "a1", "wafer": "W1", "ts": "2026-10-01 10:00:00"},
               {"log_id": "a2", "wafer": "W1", "ts": "2026-10-01 10:05:00"}])
    _fold(db, keep="max")
    assert _left(db) == ["a2"]


def test_the_same_time_keeps_the_smaller_row_id(db):
    _seed(db, [{"log_id": "a1", "wafer": "W1", "ts": "2026-10-01 10:00:00"},
               {"log_id": "a2", "wafer": "W1", "ts": "2026-10-01 10:00:00"}])
    smaller = min(_row_id(db, "a1"), _row_id(db, "a2"))
    _fold(db)
    db.expire_all()
    assert [r.row_id for r in db.query(models.DYNAMIC_TABLES[TABLE]).all()] == [smaller]


def test_a_blank_order_value_is_last(db):
    _seed(db, [{"log_id": "a1", "wafer": "W1"},
               {"log_id": "a2", "wafer": "W1", "ts": "2026-10-01 10:05:00"}])
    _fold(db)
    assert _left(db) == ["a2"]


def test_blank_keys_are_one_key(db):
    """NULL = NULL, and a blank is NULL (`crud.blank_to_null`) - the key cells' own comparison."""
    _seed(db, [{"log_id": "n1", "lot": "L1", "ts": "2026-10-01 10:00:00"},
               {"log_id": "n2", "lot": "L1", "ts": "2026-10-01 10:05:00"},
               {"log_id": "x1", "wafer": "W9", "lot": "L1", "ts": "2026-10-01 09:00:00"}])
    db.execute(text('UPDATE "%s" SET wafer = \'\' WHERE log_id = \'n2\'' % TABLE))   # a blank stored
    db.commit()
    _fold(db, keys=("wafer", "lot"))
    assert _left(db) == ["n1", "x1"]


def test_a_stop_between_pages_keeps_what_went_and_a_rerun_finds_the_rest(db, monkeypatch):
    _seed(db, [{"log_id": "a%d" % i, "wafer": "W1", "ts": "2026-10-01 10:0%d:00" % i} for i in range(4)])
    monkeypatch.setattr(replay, "FOLD_ROWS_PAGE", 1)
    seen = []

    def checkpoint(done, total):
        seen.append((done, total))
        return done >= 1
    first = _fold(db, checkpoint=checkpoint)
    assert first["stopped"] and first["rows_deleted"] == 1 and seen == [(0, 3), (1, 3)]
    again = _fold(db)
    assert again["rows_to_delete"] == 2 and again["rows_deleted"] == 2 and _left(db) == ["a0"]


def test_a_column_the_table_does_not_declare_is_refused_by_name(db):
    with pytest.raises(retroactive.RetroactiveRefused) as refused:
        retroactive.validate("fold_duplicate_rows", {"table": TABLE, "keys": "wafer,wafer_id", "order": "ts"})
    assert "wafer_id" in str(refused.value)
    with pytest.raises(retroactive.RetroactiveRefused):
        retroactive.validate("fold_duplicate_rows", {"table": TABLE, "keys": "wafer", "order": "ts",
                                                     "keep": "first"})


def test_the_cli_previews_and_writes_nothing_without_apply(db, monkeypatch, capsys):
    if os.path.join(SERVER_DIR, "scripts") not in sys.path:
        sys.path.append(os.path.join(SERVER_DIR, "scripts"))
    import chain_replay_cli
    from database import database

    _seed(db, [{"log_id": "a1", "wafer": "W1", "ts": "2026-10-01 10:00:00"},
               {"log_id": "a2", "wafer": "W1", "ts": "2026-10-01 10:05:00"}])
    monkeypatch.setattr(database, "SessionLocal", lambda: db)
    assert chain_replay_cli.main(["fold-rows", TABLE, "--keys", "wafer", "--order", "ts"]) == 0
    said = capsys.readouterr().out
    assert "1 key(s) of (wafer) in 'fold_rows_log' hold more than one row: 1 row(s) go, 1 stay." in said, said
    assert said.rstrip().endswith("-> add --apply to delete") and _left(db) == ["a1", "a2"]


def test_the_preview_says_keys_rows_and_a_sample(db):
    _seed(db, [{"log_id": "a1", "wafer": "W1", "ts": "2026-10-01 10:00:00"},
               {"log_id": "a2", "wafer": "W1", "ts": "2026-10-01 10:05:00"},
               {"log_id": "b1", "wafer": "W2", "ts": "2026-10-01 11:00:00"}])
    params = retroactive.validate("fold_duplicate_rows", {"table": TABLE, "keys": "wafer", "order": "ts"})
    said = retroactive.OPERATIONS["fold_duplicate_rows"]["count"](db, params, 1000)
    assert (said["affected"], said["scanned"], said["extra"]["keys_folded"], said["extra"]["rows_kept"]) \
        == (1, 3, 1, 2)
    assert said["detail"].startswith("1 key(s) of (wafer) in 'fold_rows_log' hold more than one row: "
                                     "1 row(s) go, 2 stay."), said["detail"]
    assert "wafer=W1: keeps 2026-10-01 10:00:00, deletes 2026-10-01 10:05:00" in said["detail"], said["detail"]
