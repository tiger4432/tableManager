# -*- coding: utf-8 -*-
"""A formula column's value is a candidate of the display answer (lead 10-28 ㄱ): `compute_priority_value` takes the
cell, and a column a formula rule writes has one more layer - «chain_ingestion (formula T.c)», undated, ranked as the
chain - whose value is the formula over the row (`chain.formula.columns`).

    seat                                             gate
    no formula                                       every answer is the answer without the cell
    crud write (apply_row_update_internal)           a file layer under the formula shows the formula; a person's wins
    crud delete_cell_source_batch                    the person's layer deleted -> the formula again, not blank
    crud set_cell_manual_priority_batch              a pinned file layer shows; unpinned -> the formula
    cell_layer withdraw (R2 · R3)                    the chain layer withdrawn -> the formula
    main grid · its fast path · cell sources (1 · n)  the badge names the formula's layer
    main cell sources (1 · n)                        a table's own source_priority ranks as the write path's
    formula.columns                                  switched off -> none; the rules read again -> swapped
"""
import json

import pytest

from chain import cell_layer, formula
from chain import ingestion_worker as worker
from database import crud, models, schemas
from tests.test_a_formula_on_a_column_is_a_join_onto_its_own_row import T, _put, fixture_db  # noqa: F401

LAYER = "chain_ingestion (formula fx.c)"


@pytest.fixture(autouse=True)
def rules_file(tmp_path, monkeypatch):
    path = tmp_path / "chain_rules.json"
    monkeypatch.setattr(worker, "RULES_PATH", str(path))
    worker.forget_loaded_chain_rules()
    yield path
    worker.forget_loaded_chain_rules()


def _write(path, *declarations):
    path.write_text(json.dumps({"rules": list(declarations)}), encoding="utf-8")
    worker.forget_loaded_chain_rules()


def _row(db):
    db.expire_all()
    return db.query(models.DYNAMIC_TABLES[T]).filter_by(k="k1").one()


@pytest.fixture(name="fx")
def fixture_fx(db, rules_file):
    _write(rules_file, formula.to_declaration(T, "c", "=[a]+[b]*3"))
    _put(db, [{"k": "k1", "a": 1, "b": 2}])
    return _row(db)


SOURCES = [{}, {"user": {"value": 5}}, {"f.csv": {"value": 1, "ingested_at": "2026-10-01T00:00:00"}},
           {"chain_ingestion": {"value": 2}, "f.csv": {"value": 3}}, {"f.csv": 4, "g.csv": 5}]


@pytest.mark.parametrize("sources", SOURCES)
@pytest.mark.parametrize("pin", [None, "f.csv", "chain_ingestion (formula fx.c)"])
def test_without_a_formula_the_answer_is_the_answer_without_the_cell(db, rules_file, sources, pin):
    _write(rules_file, formula.to_declaration(T, "c", "=[a]*2"))     # a formula elsewhere: column c, not a
    _put(db, [{"k": "k1", "a": 1}])
    row = _row(db)
    for column in ("a", "b"):
        assert crud.compute_priority_value(dict(sources), pin, T, cell=(T, column, row)) == \
            crud.compute_priority_value(dict(sources), pin, T)
    _write(rules_file)
    assert formula.columns() == {}
    assert crud.compute_priority_value(dict(sources), pin, T, cell=(T, "c", row)) == \
        crud.compute_priority_value(dict(sources), pin, T)


def test_the_write_shows_the_formula_over_a_file_layer_and_a_persons_value_over_it(db, fx):
    _put(db, [{"k": "k1", "c": 50}], who="f.csv")
    assert _row(db).c == 7, "a file layer ranks under the chain"
    _put(db, [{"k": "k1", "c": 100}])
    assert _row(db).c == 100
    assert crud.compute_priority_value({}, LAYER, T, cell=(T, "c", fx)) == (7, LAYER), \
        "a pin names a stored layer only - the formula's is ranked"


def test_deleting_the_persons_layer_shows_the_formula_not_blank(db, fx):
    _put(db, [{"k": "k1", "c": 100}])
    crud.delete_cell_source_batch(db, T, [{"row_id": fx.row_id, "column_name": "c"}], "user")
    db.commit()
    assert _row(db).c == 7


def test_a_pinned_layer_shows_and_unpinned_the_formula(db, fx):
    _put(db, [{"k": "k1", "c": 50}], who="f.csv")
    crud.set_cell_manual_priority_batch(db, T, [{"row_id": fx.row_id, "column_name": "c"}], "f.csv")
    db.commit()
    assert _row(db).c == 50
    crud.set_cell_manual_priority_batch(db, T, [{"row_id": fx.row_id, "column_name": "c"}], None)
    db.commit()
    assert _row(db).c == 7


def test_withdrawing_the_chain_layer_shows_the_formula(db, fx):
    from database.write_lines import write_lines

    # a line the funnel no longer makes on a formula column - one an older rule left
    write_lines(db, T, [{"row_id": fx.row_id, "values": {"c": 99}, "source_name": "chain_ingestion",
                         "written_by": "old rule"}], kind="chain", transaction_id="old")
    db.commit()
    assert _row(db).c == 99
    cell_layer.withdraw_layers(db, [(T, fx.row_id, "c", "chain_ingestion", None)], apply=True, log=lambda _l: None)
    db.commit()
    assert _row(db).c == 7


@pytest.mark.parametrize("include_sources", [True, False])
def test_the_grid_badge_names_the_formulas_layer(db, fx, include_sources):
    import main

    said = main.fetch_and_merge_metadata(db, T, [_row(db)], ["a", "c"], include_sources=include_sources)[0]["data"]
    assert (said["c"]["priority_source"], said["a"]["priority_source"]) == (LAYER, "user")


def test_the_cell_sources_views_name_the_formulas_layer(db, fx):
    import main

    assert main.get_cell_sources(T, fx.row_id, "c", db)["priority_source"] == LAYER
    said = main.query_cells_sources(T, schemas.BatchCellPriorityRequest(
        updates=[{"row_id": fx.row_id, "column_name": "c"}]), db)
    assert [cell["priority_source"] for cell in said] == [LAYER]


def test_the_cell_sources_views_rank_by_the_tables_own_source_priority(db, fx, monkeypatch):
    import main

    monkeypatch.setitem(crud.TABLE_CONFIG[T], "source_priority", {"f.csv": 0, "user": 1})
    _put(db, [{"k": "k1", "b": 9}], who="f.csv")
    assert _row(db).b == 9, "the write path ranks the file first on this table"
    assert main.get_cell_sources(T, fx.row_id, "b", db)["priority_source"] == "f.csv"
    said = main.query_cells_sources(T, schemas.BatchCellPriorityRequest(
        updates=[{"row_id": fx.row_id, "column_name": "b"}]), db)
    assert [cell["priority_source"] for cell in said] == ["f.csv"]


def test_the_formula_columns_are_the_switched_on_rules_and_swap_when_the_rules_are_read_again(db, rules_file):
    _write(rules_file, formula.to_declaration(T, "c", "=[a]*2"))
    assert list(formula.columns()) == [(T, "c")] and formula.columns()[(T, "c")][0] == LAYER
    _write(rules_file, dict(formula.to_declaration(T, "c", "=[a]*2"), enabled=False))
    assert formula.columns() == {}
    _write(rules_file, formula.to_declaration(T, "b", "=[a]*2"))
    assert list(formula.columns()) == [(T, "b")]
    rules_file.write_text(json.dumps({"rules": [formula.to_declaration(T, "c", "=[a]*2")]}), encoding="utf-8")
    worker.load_chain_rules()                                  # a chain slot reads them again without forgetting
    assert list(formula.columns()) == [(T, "c")]
