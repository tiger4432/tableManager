"""The two «Delete every row of a table» previews read t__lines, not cell_sources (lead 11-11, overhaul B package):
the full reset's `layers` / `user_layers` are the cells the head lines of t's rows still claim, per source - what
`lines.layers` reads - and the by-row count's «rows with a person's value» is the rows of t a person's head line sits
on, `cell_layer.person_cells`' judgement (a key merge's «user (...)» backup included). A row already gone from t keeps
its lines (history) and is not counted. sqlite.
"""
from types import SimpleNamespace

import pytest

from admin import retroactive
from chain import cell_layer, replay
from database import crud, lines, models, schemas
from database.database import Base
from test_write_lines_writes_a_line_a_change_and_its_current_line import ticking_clock

TABLE, LOADER, BACKUP = "reset_preview", "f.csv", "user (old_exist_K2)"
NO_LEDGER = SimpleNamespace(snapshot=SimpleNamespace(source_plans={}))


@pytest.fixture(name="env")
def fixture_env(db_session, monkeypatch):
    db = db_session
    cfg = {"composite_key_source": ["k"], "column_types": {"k": "string", "a": "string", "b": "string",
                                                          "c": "string"}}
    models.init_dynamic_models({TABLE: cfg})
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, cfg)
    Base.metadata.create_all(bind=db.get_bind())
    lines.ensure_line_table(db, TABLE, cfg)
    db.commit()
    ticking_clock(monkeypatch)

    def put(source, key, **values):
        crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
            business_key_val=key, updates={"k": key, **values}, source_name=source, updated_by="tester")]))
        db.commit()

    put(LOADER, "K1", a="1", b="1")                     # one line, three cells
    put(crud.USER_SOURCE, "K1", a="p")                  # a person's cell
    put(LOADER, "K2", a="2")
    put(BACKUP, "K2", c="b")                            # a key merge's backup of a person's line
    put(LOADER, "K3", a="3", b="3", c="3")
    put(LOADER, "K4", a="4")
    put(crud.USER_SOURCE, "K4", b="p4")
    model = models.DYNAMIC_TABLES[TABLE]
    db.query(model).filter(model.business_key_val == "K4").delete()    # gone from t, its lines stay
    db.commit()
    return db


def _in_t(db):
    return [r.row_id for r in db.query(models.DYNAMIC_TABLES[TABLE])]


def test_the_full_reset_preview_counts_the_cells_the_lines_of_its_rows_claim(env):
    found = replay.full_reset(env, TABLE, setup=NO_LEDGER, rules=[])
    read = lines.layers(env, TABLE, _in_t(env))          # THE layer read, over t's rows
    per_source = {}
    for named in read.values():
        for name in named:
            per_source[name] = per_source.get(name, 0) + 1

    assert per_source == {LOADER: 3 + 2 + 4, crud.USER_SOURCE: 2, BACKUP: 2}, "canary: the fixture (k in each)"
    assert found["layers"] == sum(per_source.values()) == 13, found
    assert found["user_layers"] == 4, found             # «user» and its backup - crud.layer_writer
    assert found["rows"] == 3


def test_the_by_row_preview_counts_the_rows_a_person_wrote_on_and_the_run_deletes_what_it_said(env):
    person = {row_id for row_id, _column in cell_layer.person_cells(env, TABLE, _in_t(env))}
    out = retroactive.count(env, "delete_every_row", {"table": TABLE})

    assert len(person) == 2, "canary: K1's person line and K2's backup; K4 is gone from t"
    assert out["extra"]["rows_with_person"] == len(person), out["extra"]
    assert "2 of them hold a person's value" in out["detail"], out["detail"]
    run = retroactive._run_delete_every_row(env, {"table": TABLE}, log=lambda m: None)
    assert out["affected"] == run["rows_deleted"] == 3, (out, run)
