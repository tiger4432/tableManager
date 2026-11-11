# -*- coding: utf-8 -*-
"""`cell_layer.cells_written_by` - the layers a rule wrote on the cells asked - answers the same set on PostgreSQL (the
pairs joined as two arrays, 총괄 11-06 소유자 ㄱ) and elsewhere (a row-value IN) - what settle asks (owner 11-06
step 2: everything the rule owns there):

  some cells, one writer · every row x every column, two rules · whole rows, one writer

  found      the plain chain layer and a decide's stamp by the writer · the layer it wrote from a source row (its own
             row's or another's - a join's) · its owned layer · the backfill's old name
  not found  another rule's · a file's · another table's · a cell not asked whose row and column both are

Each layer is a source's head line in the table's line table (lead 11-11: the layers live in t__lines).
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import MetaData, Table, create_engine
from sqlalchemy.orm import sessionmaker

from chain import cell_layer
from chain.enrichment import backfill
from database import crud, lines
from database.models import sql_type_of

TABLE = "zz_cells_written"
OTHER = "zz_other"
CFG = {"column_types": {"a": "string", "b": "string", "c": "string"}}


def _layers():
    own = crud.merged_layer_name(crud.CHAIN_SOURCE, "r2")
    join = crud.merged_layer_name(crud.CHAIN_SOURCE, "r9")
    owned = crud.owned_layer_name("rule_a", "k (1)")
    return [  # (table, row, column, source, updated_by, origin)
        (TABLE, "r1", "a", "chain_ingestion", "rule_a", None),
        (TABLE, "r1", "a", "file_x", "w", None),
        (TABLE, "r1", "b", "enrichment_auto_confirm", "rule_a", None),
        (TABLE, "r1", "c", "chain_ingestion", "rule_b", None),
        (TABLE, "r2", "a", own, "rule_a", "r2"),
        (TABLE, "r2", "b", join, "rule_a", "r9"),
        (TABLE, "r2", "c", backfill.SOURCE_NAME, "w", None),
        (TABLE, "r2", "c", owned, "rule_a", None),
        (TABLE, "r3", "a", "chain_ingestion", "rule_a", None),           # not asked: its row and column both are
        (TABLE, "r3", "b", "chain_ingestion", "rule_a", None),
        (OTHER, "r1", "a", "chain_ingestion", "rule_a", None)]


ASKED = [("r1", "a"), ("r1", "b"), ("r1", "c"), ("r2", "a"), ("r2", "b"), ("r2", "c"), ("r3", "b")]


def _answers(db, chunk_size):
    def found(cells, rules):
        return sorted((row, column, source) for _t, row, column, source, _o in
                      cell_layer.cells_written_by(db, TABLE, cells, rules, chunk_size=chunk_size))
    own = crud.merged_layer_name(crud.CHAIN_SOURCE, "r2")
    join = crud.merged_layer_name(crud.CHAIN_SOURCE, "r9")
    owned = crud.owned_layer_name("rule_a", "k (1)")
    r2 = [("r2", "a", own), ("r2", "b", join), ("r2", "c", backfill.SOURCE_NAME), ("r2", "c", owned)]
    one_writer = sorted([("r1", "a", "chain_ingestion"), ("r1", "b", "enrichment_auto_confirm"),
                         ("r3", "b", "chain_ingestion")] + r2)
    assert found(sorted(ASKED), ("rule_a",)) == one_writer, "some cells, one writer"
    product = [(r, c) for r in ("r1", "r2") for c in ("a", "b", "c")]
    assert found(product, ("rule_a", "rule_b")) == sorted(
        [("r1", "a", "chain_ingestion"), ("r1", "b", "enrichment_auto_confirm"), ("r1", "c", "chain_ingestion")]
        + r2), "two rules"
    whole = sorted((row, column, source) for _t, row, column, source, _o in cell_layer.cells_written_by(
        db, TABLE, [("r1", "a"), ("r3", "a")], ("rule_a",), chunk_size=chunk_size, rows=["r2"]))
    assert whole == sorted([("r1", "a", "chain_ingestion"), ("r3", "a", "chain_ingestion")] + r2), "rows and cells"


def _seed(db):
    """Both tables with their line tables, and one head line a layer - `updated_by` the line's writer, the origin its
    input row."""
    conn = db.connection()
    for model in (lines.LineColumn, lines.AuditBatch, lines.LineSource):
        model.__table__.create(conn, checkfirst=True)
    for table in (TABLE, OTHER):
        Table(table, MetaData(), *lines._data_columns(CFG, sql_type_of, row_id_key=True)).create(conn)
        lines.ensure_line_table(db, table, CFG)
    at = datetime(2026, 11, 1, tzinfo=timezone.utc)
    for table, row, column, source, by, origin in _layers():
        shape = lines.shape(db, table, CFG)
        bit = shape["bits"][column]
        mask, chunk = lines._mask(bit), bit // lines.BITS_PER_CHUNK
        db.execute(shape["lines"].insert().values(
            line_kind="write", source_name=source, at=at, row_id=row, written_by=by, input_row=origin,
            **{lines.value_column(column): "v", f"written_{chunk}": mask, f"head_{chunk}": mask,
               f"withdrawn_{chunk}": 0}))
    db.flush()


def test_elsewhere_the_cells_asked_find_their_layers():
    engine = create_engine("sqlite://")
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
        for table in (TABLE, OTHER):
            lines.drop_line_table(db, table)
            db.connection().exec_driver_sql(f'DROP TABLE IF EXISTS "{table}"')
            db.query(lines.LineColumn).filter(lines.LineColumn.table_name == table).delete()
        db.commit()
