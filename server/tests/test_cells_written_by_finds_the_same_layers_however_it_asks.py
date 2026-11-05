# -*- coding: utf-8 -*-
"""`cell_layer.cells_written_by` - the layers a rule wrote on the cells asked - answers the same set on PostgreSQL (the
pairs joined as two arrays, 총괄 11-06 소유자 ㄱ) and elsewhere (a row-value IN), in each caller's shape:

  _withdraw_blanks            some cells of the rows, one writer
  _delete_gone                every row x every column, the rules
  _move_off_the_plain_layer   some cells of the rows, one writer

  found      the plain chain layer and a decide's stamp by the writer · the layer it wrote from the cell's own row ·
             the backfill's old name
  not found  another rule's · a join's (written from another row) · a file's · another table's · a cell not asked
             whose row and column both are
"""
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from chain import cell_layer
from chain.enrichment import backfill
from database import crud, models

TABLE = "zz_cells_written"


def _layers():
    own = crud.merged_layer_name(crud.CHAIN_SOURCE, "r2")
    join = crud.merged_layer_name(crud.CHAIN_SOURCE, "r9")
    return [  # (table, row, column, source, updated_by, origin)
        (TABLE, "r1", "a", "chain_ingestion", "rule_a", None),
        (TABLE, "r1", "a", "file_x", "w", None),
        (TABLE, "r1", "b", "enrichment_auto_confirm", "rule_a", None),
        (TABLE, "r1", "c", "chain_ingestion", "rule_b", None),
        (TABLE, "r2", "a", own, "rule_a", "r2"),
        (TABLE, "r2", "b", join, "rule_a", "r9"),
        (TABLE, "r2", "c", backfill.SOURCE_NAME, "w", None),
        (TABLE, "r3", "a", "chain_ingestion", "rule_a", None),           # not asked: its row and column both are
        (TABLE, "r3", "b", "chain_ingestion", "rule_a", None),
        ("zz_other", "r1", "a", "chain_ingestion", "rule_a", None)]


ASKED = [("r1", "a"), ("r1", "b"), ("r1", "c"), ("r2", "a"), ("r2", "b"), ("r2", "c"), ("r3", "b")]


def _answers(db, chunk_size):
    def found(cells, rules):
        return sorted((row, column, source) for _t, row, column, source, _o in
                      cell_layer.cells_written_by(db, TABLE, cells, rules, chunk_size=chunk_size))
    own = crud.merged_layer_name(crud.CHAIN_SOURCE, "r2")
    one_writer = [("r1", "a", "chain_ingestion"), ("r1", "b", "enrichment_auto_confirm"), ("r2", "a", own),
                  ("r2", "c", backfill.SOURCE_NAME), ("r3", "b", "chain_ingestion")]
    assert found(sorted(ASKED), ("rule_a",)) == one_writer, "_withdraw_blanks / _move_off_the_plain_layer"
    product = [(r, c) for r in ("r1", "r2") for c in ("a", "b", "c")]
    assert found(product, ("rule_a", "rule_b")) == sorted(
        [("r1", "a", "chain_ingestion"), ("r1", "b", "enrichment_auto_confirm"), ("r1", "c", "chain_ingestion"),
         ("r2", "a", own), ("r2", "c", backfill.SOURCE_NAME)]), "_delete_gone"


def _seed(db):
    for table, row, column, source, by, origin in _layers():
        db.add(models.CellSource(table_name=table, row_id=row, column_name=column, source_name=source, updated_by=by,
                                 origin_row_id=origin))
    db.flush()


def test_elsewhere_the_cells_asked_find_their_layers():
    engine = create_engine("sqlite://")
    models.CellSource.__table__.create(engine)
    db = sessionmaker(bind=engine)()
    try:
        _seed(db)
        for chunk_size in (3, 1000):                       # the asked cut in chunks, and all in one
            _answers(db, chunk_size)
    finally:
        db.close()


@pytest.mark.pg
def test_on_postgresql_the_pairs_joined_find_the_same_layers(pg_session):
    db = pg_session
    try:
        _seed(db)
        for chunk_size in (3, 1000):
            _answers(db, chunk_size)
    finally:
        db.rollback()
        db.execute(text("DELETE FROM cell_sources WHERE table_name IN (:a, 'zz_other')"), {"a": TABLE})
        db.commit()
