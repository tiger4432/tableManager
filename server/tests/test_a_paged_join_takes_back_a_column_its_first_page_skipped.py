# -*- coding: utf-8 -*-
"""총괄 a02ad0f2b ㄱ: a join's answer comes in pages from one row, so its first page is not all it writes. An edited
source row takes back the columns of the rule - the declaration with the first page - not the first page's alone:
  skipped   the first row skipped a blank take (take two, blank: skip) - a row the edit no longer feeds loses that
            column's old value too
  kept      the rows written on every page keep what was written
Through the worker's group seat, pages adaptive (`keyset_scan.PageSize`)."""
import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from chain import ingestion_worker as worker                                 # noqa: E402
from chain import rule_shape                                                 # noqa: E402
from database import crud, models, schemas                                   # noqa: E402
from database.database import Base                                          # noqa: E402

LEFT, RIGHT = "pj_left", "pj_right"
TABLES = {
    LEFT: {"business_key": "log_key", "composite_key_source": ["log_key"],
           "column_types": {"log_key": "string", "job": "string", "lot": "string", "grade": "string"}},
    RIGHT: {"business_key": "rid", "composite_key_source": ["rid"],
            "column_types": {"rid": "string", "job": "string", "lot": "string", "grade": "string"}},
}
DECLARATION = {
    "name": "pj_join", "on": {"table": RIGHT}, "into": {"table": LEFT},
    "derive": {"kind": "join", "join": {"on": [{"left": "job", "right": "job"}], "blank": "skip",
                                        "take": [{"from": "lot", "into": "lot"}, {"from": "grade", "into": "grade"}]}},
}


def _push(db, table, rows):
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates=dict(row), source_name="seed", updated_by="pj") for row in rows]))
    db.commit()


def _run(db):
    events = db.query(models.DatabaseOutbox).filter(models.DatabaseOutbox.table_name == RIGHT,
                                                    models.DatabaseOutbox.processed_chain.is_(False)).all()
    assert events
    ok, error, _ = worker._process_chain_transaction_group_sync(
        "tx-pj", events, db, rule_shape.expand_declaration(DECLARATION, crud.TABLE_CONFIG)[0])
    assert ok, error
    db.query(models.DatabaseOutbox).update({"processed_chain": True})
    db.commit()


def test_an_edit_takes_back_the_column_the_first_page_skipped_and_keeps_every_page_written():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    try:
        Base.metadata.create_all(bind=engine)
        models.sync_dynamic_tables_schema(engine)
        db = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
        # J1's rows first (the first page is one of them), J2's after - five pages of 1 · 2 · 2 · 2 · 1
        _push(db, LEFT, [{"log_key": "L-%d" % i, "job": "J1" if i < 6 else "J2"} for i in range(8)])
        db.query(models.DatabaseOutbox).update({"processed_chain": True})
        _push(db, RIGHT, [{"rid": "R1", "job": "J1", "lot": "LOT1"}, {"rid": "R2", "job": "J2", "lot": "LOT2", "grade": "G2"}])
        _run(db)
        left = models.DYNAMIC_TABLES[LEFT]
        assert {r.log_key: (r.lot, r.grade) for r in db.query(left)} == {
            "L-%d" % i: ("LOT1", None) if i < 6 else ("LOT2", "G2") for i in range(8)}

        # R1 writes its lot again (its grade blank - skipped, so the first page says lot alone); R2 moves to a job no
        # left row carries - it no longer feeds its rows
        _push(db, RIGHT, [{"rid": "R1", "job": "J1", "lot": "LOT1b"}, {"rid": "R2", "job": "J9"}])
        _run(db)
        cells = {r.log_key: (r.lot, r.grade) for r in db.query(left)}
        assert all(cells["L-%d" % i][0] == "LOT1b" for i in range(6)), cells          # kept: every page's rows
        assert all(cells["L-%d" % i] == (None, None) for i in (6, 7)), cells           # skipped: grade taken back too
    finally:
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)
