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
TODAY = [(True, True), ("1.0", "1.0")]


@pytest.mark.parametrize("value, stored", FOLDS)
def test_a_number_into_a_text_column_is_stored_as_the_reader_spells_it(value, stored):
    for column_type in ("string", "TEXT"):
        assert crud.cast_value_by_type(value, column_type, "v") == stored
        assert crud.clean_str_value(value) == stored, "the fold IS the read function"


@pytest.mark.parametrize("value, stored", TODAY)
def test_everything_else_keeps_todays_path(value, stored):
    assert crud.cast_value_by_type(value, "string", "v") == stored
    assert type(crud.cast_value_by_type(value, "string", "v")) is type(stored)
    # TURNED (owner 11-08 1ㄱ 2ㄱ, was «NaN is passed on as it was» and inf kept): a NaN is blank, inf refused by name
    assert crud.cast_value_by_type(float("nan"), "string", "v") is None
    with pytest.raises(crud.CellRefused):
        crud.cast_value_by_type(float("inf"), "string", "v")
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
        conn.execute(text("DELETE FROM database_outbox WHERE table_name = :t"), {"t": T})
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
            conn.execute(text("DELETE FROM database_outbox WHERE table_name = :t"), {"t": T})


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


# --- ② what was stored before a declaration: a key moves only when its cells still spell it -------
# (A 11-11: a line holds text, so «a number left in a text layer» - what this section folded - is no state of a
# table with lines; the migration's copy is where such a layer gets its spelling.)

C = "numtext_comp"
COMP_TABLE = {"business_key": "row_key", "composite_key_source": ["lot", "wafer"],
              "composite_key_separator": "_",
              "column_types": {"row_key": "string", "lot": "string", "wafer": "string"}}


@pytest.fixture(name="comp")
def fixture_comp(table, tmp_path, monkeypatch):
    import notation_norm as nn
    from database import config_watcher, lines

    models.init_dynamic_models({C: COMP_TABLE})
    crud.TABLE_CONFIG[C] = COMP_TABLE
    Base.metadata.create_all(bind=table.get_bind())
    lines.ensure_line_table(table, C, COMP_TABLE)
    table.query(models.DYNAMIC_TABLES[C]).delete()
    table.execute(text('DELETE FROM "%s"' % lines.lines_relation(C)))
    table.commit()
    rules = tmp_path / "notation_rules.json"
    rules.write_text(json.dumps({"columns": {}}), encoding="utf-8")
    monkeypatch.setattr(nn, "NOTATION_RULES_PATH", str(rules))
    config_watcher.forget_held()
    yield table, rules
    config_watcher.forget_held()
    crud.TABLE_CONFIG.pop(C, None)
    retire_dynamic_model(C)


def _key(db, row_id, key):
    """A key as an older writer stored it - its cells spell another."""
    db.execute(text("UPDATE %s SET business_key_val = :k WHERE row_id = :r" % C), {"k": key, "r": row_id})
    db.commit()


def test_a_key_moves_only_when_its_cells_still_spell_it(comp):
    """총괄 c6a8c069c ㉡ 가. Three rows, `wafer` declared to fold after they were stored:
        off      key in an older separator (L2:w2)    -> skipped and named, untouched - its cells too
        spelled  key spelled from its cells (L3_w3)    -> re-keyed to L3_w03
        still    older separator, nothing folds (L4:x) -> not touched, not counted
    """
    from chain import replay
    from database import config_watcher

    db, rules = comp
    crud.apply_batch_updates(db, C, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates={"lot": lot, "wafer": wafer}, source_name="f01.csv", updated_by="t")
        for lot, wafer in (("L2", "w2"), ("L3", "w3"), ("L4", "x"))], silent=True))
    db.commit()
    model = models.DYNAMIC_TABLES[C]
    ids = {r.lot: r.row_id for r in db.query(model)}
    off, spelled, still = ids["L2"], ids["L3"], ids["L4"]
    _key(db, off, "L2:w2")
    _key(db, still, "L4:x")
    rules.write_text(json.dumps({"columns": {C: {"wafer": {"write": True, "rules": {"pad_last_number": 2}}}}}),
                     encoding="utf-8")
    config_watcher.forget_held()

    stats = replay.fold_written_notation(db, C, apply=True)
    db.expire_all()
    rows = {r.row_id: r for r in db.query(model).all()}
    assert (rows[off].wafer, rows[off].business_key_val) == ("w2", "L2:w2"), "identity kept"
    assert (rows[spelled].wafer, rows[spelled].business_key_val) == ("w03", "L3_w03")
    assert (rows[still].wafer, rows[still].business_key_val) == ("x", "L4:x")
    assert (stats["keys_changed"], stats["keys_not_rebuilt"]) == (1, 1)
    assert [s["business_key_val"] for s in stats["not_rebuilt"]] == ["L2:w2"]
