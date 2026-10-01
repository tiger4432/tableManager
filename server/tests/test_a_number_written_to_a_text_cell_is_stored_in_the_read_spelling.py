# -*- coding: utf-8 -*-
"""A number written to a text cell is stored in `clean_str_value`'s spelling (총괄 c6a8c069c ㉡,
소유자 「문자타입에 숫자 들어올때 정수형으로 접어서」).

The text branch of `crud.cast_value_by_type` passed a number through: the layer kept a JSON
number (1.0), PostgreSQL wrote '1.0' into the text column, Python read '1' and `->>` read '1.0'
- one cell, two answers. The fold is the read function itself, at the one write seat; every
other value keeps today's path.
"""
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import cell_layer                                       # noqa: E402
from conftest import retire_dynamic_model                          # noqa: E402
from database import crud, models, schemas                         # noqa: E402
from database.database import Base                                 # noqa: E402

T = "numtext_probe"
TABLE = {"business_key": "k",
         "column_types": {"k": "string", "v": "string", "w": "TEXT", "n": "number"}}
#: (value written, what the text cell stores). The left five fold; the rest are today's answer.
FOLDS = [(1.0, "1"), (np.int64(3), "3"), (1.5, "1.5"), (1e16, "10000000000000000"),
         (np.float64(2.0), "2")]
TODAY = [(True, True), ("1.0", "1.0"), (float("inf"), float("inf"))]


@pytest.mark.parametrize("value, stored", FOLDS)
def test_a_number_into_a_text_column_is_stored_as_the_reader_spells_it(value, stored):
    for column_type in ("string", "TEXT"):
        assert crud.cast_value_by_type(value, column_type, "v") == stored
        assert crud.clean_str_value(value) == stored, "the fold IS the read function"


@pytest.mark.parametrize("value, stored", TODAY)
def test_everything_else_keeps_todays_path(value, stored):
    assert crud.cast_value_by_type(value, "string", "v") == stored
    assert type(crud.cast_value_by_type(value, "string", "v")) is type(stored)
    nan = crud.cast_value_by_type(float("nan"), "string", "v")
    assert nan != nan, "NaN is passed on as it was"
    assert crud.cast_value_by_type(1.0, "number", "n") == 1.0
    assert isinstance(crud.cast_value_by_type(1.0, "number", "n"), float)


def test_the_cell_a_layer_recompute_shows_is_the_same_answer():
    """`cell_layer` re-decides a shown cell from its stored layers through the same cast."""
    row = type("Row", (), {"v": None})()
    layers = {"f.csv": {"value": 1.0, "ingested_at": datetime(2026, 10, 1, tzinfo=timezone.utc)}}
    decided = cell_layer._resolve_cell(T, TABLE["column_types"], row, "v", layers, None)
    assert decided["new_value"] == "1"


def _write(db, rows):
    crud.apply_batch_updates(db, T, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates=dict(r), source_name="f01.csv", updated_by="t",
                                  business_key_val=r["k"]) for r in rows], silent=True))


ROWS = [{"k": f"r{i}", "v": value, "w": value, "n": 1.0} for i, (value, _) in enumerate(FOLDS)]


@pytest.fixture(name="table")
def fixture_table(db_session):
    models.init_dynamic_models({T: TABLE})
    crud.TABLE_CONFIG[T] = TABLE
    Base.metadata.create_all(bind=db_session.get_bind())
    db_session.query(models.DYNAMIC_TABLES[T]).delete()
    db_session.query(models.CellSource).filter(models.CellSource.table_name == T).delete()
    db_session.commit()
    yield db_session
    crud.TABLE_CONFIG.pop(T, None)
    retire_dynamic_model(T)


def test_the_funnel_stores_the_folded_text_in_the_cell_and_in_its_layer(table):
    _write(table, ROWS)
    rows = {r.k: r for r in table.query(models.DYNAMIC_TABLES[T]).all()}
    layers = {(row_id, column): value for row_id, column, value in table.query(
        models.CellSource.row_id, models.CellSource.column_name, models.CellSource.value)
        .filter(models.CellSource.table_name == T)}
    for i, (_, stored) in enumerate(FOLDS):
        row = rows[f"r{i}"]
        assert (row.v, row.w) == (stored, stored)
        assert layers[(row.row_id, "v")] == stored, "the layer holds the same text"
        assert row.n == 1.0 and isinstance(row.n, float), "a number column is untouched"


@pytest.fixture(name="pg_table")
def fixture_pg_table(pg_engine):
    saved = dict(crud.TABLE_CONFIG)
    retire_dynamic_model(T)
    models.init_dynamic_models({T: TABLE})
    with pg_engine.begin() as conn:
        conn.execute(text('DROP TABLE IF EXISTS "%s"' % T))
        conn.execute(text("DELETE FROM cell_sources WHERE table_name = :t"), {"t": T})
    Base.metadata.create_all(bind=pg_engine, tables=[models.DYNAMIC_TABLES[T].__table__])
    crud.TABLE_CONFIG[T] = TABLE
    db = sessionmaker(bind=pg_engine, autoflush=False)()
    try:
        yield db, pg_engine
    finally:
        db.close()
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        retire_dynamic_model(T)
        with pg_engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS "%s"' % T))
            conn.execute(text("DELETE FROM cell_sources WHERE table_name = :t"), {"t": T})


@pytest.mark.pg
def test_python_and_postgres_read_one_answer_from_the_cell_and_its_layer(pg_table):
    db, engine = pg_table
    _write(db, ROWS)
    with engine.connect() as conn:
        cells = dict(conn.execute(text('SELECT k, v FROM "%s"' % T)).all())
        layers = dict(conn.execute(text(
            'SELECT t.k, s.value #>> \'{}\' FROM cell_sources s JOIN "%s" t ON t.row_id = s.row_id '
            "WHERE s.table_name = :t AND s.column_name = 'v'" % T), {"t": T}).all())
    for i, (_, stored) in enumerate(FOLDS):
        key = f"r{i}"
        assert cells[key] == layers[key] == stored
        assert crud.clean_str_value(cells[key]) == stored


# --- ② what was stored before the fold is folded in place (fold_written_notation, widened) -------

C = "numtext_comp"
COMP_TABLE = {"business_key": "row_key", "composite_key_source": ["lot", "wafer"],
              "composite_key_separator": "_",
              "column_types": {"row_key": "string", "lot": "string", "wafer": "string"}}


def _stored_as_production_did(db, table, key, column, written_text, number, stored_key=None):
    """The state a number left before ①: PostgreSQL wrote its text into the shown cell, the layer
    kept the JSON number. Written through the funnel as text, then the layer is set back."""
    model = models.DYNAMIC_TABLES[table]
    row = db.query(model).filter(model.business_key_val == key).one()
    layer = db.query(models.CellSource).filter(
        models.CellSource.table_name == table, models.CellSource.row_id == row.row_id,
        models.CellSource.column_name == column).one()
    assert getattr(row, column) == written_text
    layer.value = number
    if stored_key is not None:
        row.business_key_val = stored_key
    db.commit()
    return row.row_id


def _layer(db, table, row_id, column):
    return db.query(models.CellSource.value).filter(
        models.CellSource.table_name == table, models.CellSource.row_id == row_id,
        models.CellSource.column_name == column).scalar()


@pytest.fixture(name="comp")
def fixture_comp(table):
    models.init_dynamic_models({C: COMP_TABLE})
    crud.TABLE_CONFIG[C] = COMP_TABLE
    Base.metadata.create_all(bind=table.get_bind())
    table.query(models.DYNAMIC_TABLES[C]).delete()
    table.query(models.CellSource).filter(models.CellSource.table_name == C).delete()
    table.commit()
    yield table
    crud.TABLE_CONFIG.pop(C, None)
    retire_dynamic_model(C)


def test_a_number_stored_in_a_text_layer_is_counted_folded_and_shown_as_the_layer_decides(table):
    from chain import replay

    _write(table, [{"k": "r", "v": "1.0", "n": 1.0}])
    row_id = _stored_as_production_did(table, T, "r", "v", "1.0", 1.0)
    dry = replay.fold_written_notation(table, T)
    assert (dry["cells_folded"], dry["layers_folded"]) == (1, 1), "counted - before the fold, 0"
    replay.fold_written_notation(table, T, apply=True)
    row = table.query(models.DYNAMIC_TABLES[T]).filter_by(row_id=row_id).one()
    assert (row.v, _layer(table, T, row_id, "v")) == ("1", "1")
    assert row.n == 1.0, "a number column is not the text fold's"
    again = replay.fold_written_notation(table, T)
    assert (again["cells_folded"], again["layers_folded"]) == (0, 0)


def test_a_write_column_with_a_number_layer_is_counted_where_the_notation_fold_saw_nothing(
        table, tmp_path, monkeypatch):
    """총괄 0f5992e74: the notation fold reads text, so before ② the number layer counted 0."""
    import notation_norm as nn
    from chain import replay

    path = tmp_path / "notation_rules.json"
    path.write_text(json.dumps({"columns": {T: {"v": {"write": True, "rules": {
        "replace": [["x", "y"]]}}}}}), encoding="utf-8")
    monkeypatch.setattr(nn, "NOTATION_RULES_PATH", str(path))
    nn.reset_cache()
    try:
        _write(table, [{"k": "r", "v": "1.0"}])
        row_id = _stored_as_production_did(table, T, "r", "v", "1.0", 1.0)
        assert replay.fold_written_notation(table, T)["layers_folded"] == 1
        replay.fold_written_notation(table, T, apply=True)
        row = table.query(models.DYNAMIC_TABLES[T]).filter_by(row_id=row_id).one()
        assert (row.v, _layer(table, T, row_id, "v")) == ("1", "1")
        assert replay.fold_written_notation(table, T)["layers_folded"] == 0
    finally:
        nn.reset_cache()


def test_a_key_moves_only_when_its_cells_still_spell_it(comp):
    """총괄 c6a8c069c ㉡ 가. Four rows, a number layer under `wafer` in three of them:
        born     key built from the number (L1_1), cell '1.0'  -> cell folds, key already right
        off      key in an older separator (L2:2.0)            -> skipped and named, untouched
        spelled  key spelled from its cells (L3_3.0)           -> re-keyed to L3_3
        still    older separator, nothing folds (L4:x)         -> not touched, not counted
    """
    from chain import replay

    crud.apply_batch_updates(comp, C, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates={"lot": lot, "wafer": wafer}, source_name="f01.csv",
                                  updated_by="t")
        for lot, wafer in (("L1", "1.0"), ("L2", "2.0"), ("L3", "3.0"), ("L4", "x"))],
        silent=True))
    born = _stored_as_production_did(comp, C, "L1_1.0", "wafer", "1.0", 1.0, stored_key="L1_1")
    off = _stored_as_production_did(comp, C, "L2_2.0", "wafer", "2.0", 2.0, stored_key="L2:2.0")
    spelled = _stored_as_production_did(comp, C, "L3_3.0", "wafer", "3.0", 3.0)
    model = models.DYNAMIC_TABLES[C]
    still = comp.query(model).filter(model.business_key_val == "L4_x").one()
    still.business_key_val = "L4:x"
    comp.commit()

    stats = replay.fold_written_notation(comp, C, apply=True)
    rows = {r.row_id: r for r in comp.query(model).all()}
    assert (rows[born].wafer, rows[born].business_key_val) == ("1", "L1_1")
    assert (rows[off].wafer, rows[off].business_key_val) == ("2.0", "L2:2.0"), "identity kept"
    assert _layer(comp, C, off, "wafer") == 2.0, "a skipped row keeps its layers too"
    assert (rows[spelled].wafer, rows[spelled].business_key_val) == ("3", "L3_3")
    assert rows[still.row_id].business_key_val == "L4:x"
    assert (stats["keys_changed"], stats["keys_not_rebuilt"]) == (1, 1)
    assert [s["business_key_val"] for s in stats["not_rebuilt"]] == ["L2:2.0"]


@pytest.mark.pg
def test_postgres_reads_one_answer_after_the_stored_fold(pg_table):
    from chain import replay

    db, engine = pg_table
    _write(db, [{"k": "r", "v": "1.0"}])
    row_id = _stored_as_production_did(db, T, "r", "v", "1.0", 1.0)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT json_typeof(value) FROM cell_sources WHERE row_id = :r "
                                 "AND column_name = 'v'"), {"r": row_id}).scalar() == "number"
    assert replay.fold_written_notation(db, T)["layers_folded"] == 1
    replay.fold_written_notation(db, T, apply=True)
    with engine.connect() as conn:
        shown = conn.execute(text('SELECT v FROM "%s" WHERE row_id = :r' % T), {"r": row_id}).scalar()
        layer = conn.execute(text("SELECT value #>> '{}' FROM cell_sources WHERE row_id = :r "
                                  "AND column_name = 'v'"), {"r": row_id}).scalar()
    assert shown == layer == "1"
    assert replay.fold_written_notation(db, T)["layers_folded"] == 0
