"""Same-valued file layers fold (총괄 225b2c658 · f224477c1 · a7d2e90ec).

Write path: a file layer equal to the newest layer of its priority class writes nothing; one that
differs is written and the older file layers of the class holding its value go. Stacked layers:
`replay.fold_file_layers` keeps, per class and value, the newest (and a pinned one). In every case
the shown value is the one `compute_priority_value` picked before - asserted cell by cell.
"""
from datetime import datetime, timedelta

import pytest

from database import crud, models, schemas
from maps import alignment_batch_counts

TABLE = "foldl_test"
TABLES = {TABLE: {"business_key": "k",
                  "column_types": {"k": "string", "v": "string", "n": "number"}}}
AUTO = "enrichment_auto_confirm"


@pytest.fixture()
def env(db_session):
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    yield db_session
    from conftest import retire_dynamic_model
    retire_dynamic_model(TABLE)
    crud.TABLE_CONFIG.pop(TABLE, None)


def _write(db, source, updates):
    with alignment_batch_counts.counting_group() as summary:
        crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates=dict(u), business_key_val=u["k"],
                                      source_name=source, updated_by="t")
            for u in updates], silent=True))
    return summary()["write_counts"]


def _row(db, key):
    model = models.DYNAMIC_TABLES[TABLE]
    return db.query(model).filter(model.business_key_val == key).one()


def _layers(db, key, col="v"):
    return {s.source_name: s.value for s in db.query(models.CellSource).filter(
        models.CellSource.table_name == TABLE, models.CellSource.row_id == _row(db, key).row_id,
        models.CellSource.column_name == col)}


# --- the write path ---------------------------------------------------------------------------

def test_an_hourly_refetch_of_an_unchanged_row_writes_no_layer(env):
    """The owner's hourly one-day refetch (f224477c1): from the second file on, nothing."""
    first = _write(env, "day_0100.csv", [{"k": "K1", "v": "A"}])
    assert first["cell sources"] == [2, "rows"], "k and v"
    for hour in ("day_0200.csv", "day_0300.csv", "day_0400.csv"):
        counts = _write(env, hour, [{"k": "K1", "v": "A"}])
        assert counts["cell sources"] == [0, "rows"] and counts["folded layers"] == [0, "rows"]
    assert _layers(env, "K1") == {"day_0100.csv": "A"}


def test_a_differing_file_is_written_and_older_file_layers_of_its_value_go(env):
    _write(env, "f03.csv", [{"k": "K1", "v": "A"}])
    _write(env, "f07.csv", [{"k": "K1", "v": "B"}])
    counts = _write(env, "f10.csv", [{"k": "K1", "v": "A"}])
    assert counts["folded layers"] == [1, "rows"]
    assert _layers(env, "K1") == {"f07.csv": "B", "f10.csv": "A"}
    assert _row(env, "K1").v == "A"


def test_only_the_newest_layer_decides_a_repeat(env):
    """⛔ f224477c1: 'the same as ANY layer' is wrong - f03 A · f07 B · f10 A must write f10."""
    _write(env, "f03.csv", [{"k": "K1", "v": "A"}])
    _write(env, "f07.csv", [{"k": "K1", "v": "B"}])
    assert _row(env, "K1").v == "B"
    _write(env, "f10.csv", [{"k": "K1", "v": "A"}])
    assert _row(env, "K1").v == "A"


def test_person_chain_and_auto_confirm_layers_are_never_folded(env):
    _write(env, "user", [{"k": "K1", "v": "A"}])
    _write(env, crud.CHAIN_SOURCE, [{"k": "K1", "v": "A"}])
    _write(env, "f01.csv", [{"k": "K1", "v": "A"}])
    _write(env, AUTO, [{"k": "K1", "v": "A"}])
    _write(env, "f02.csv", [{"k": "K1", "v": "A"}])
    assert _layers(env, "K1") == {"user": "A", crud.CHAIN_SOURCE: "A", AUTO: "A",
                                  "f02.csv": "A"}, \
        "the newest of the class was auto-confirm, so f02 is written and only f01 goes"


def test_a_pinned_file_layer_is_kept(env):
    _write(env, "f03.csv", [{"k": "K1", "v": "A"}])
    row = _row(env, "K1")
    env.add(models.CellOverwrite(table_name=TABLE, row_id=row.row_id, column_name="v",
                                 is_overwrite=False, updated_by="t",
                                 manual_priority_source="f03.csv"))
    env.commit()
    _write(env, "f07.csv", [{"k": "K1", "v": "B"}])
    _write(env, "f10.csv", [{"k": "K1", "v": "A"}])
    assert _layers(env, "K1") == {"f03.csv": "A", "f07.csv": "B", "f10.csv": "A"}


def test_the_layer_no_op_uses_the_one_equality(env):
    """a7d2e90ec: the value layer, the layer no-op and the fold share `values_differ`.
    ⚠️ A trailing space was never the difference - the cast trims text before any of them
    compares. What the shared equality changes is a writer re-sending 1 as '1' (a mapper's
    int, a file's text): the old `==` rewrote the layer for it; the one equality does not.
    A machine writer, so the file rule cannot be what keeps it."""
    stamp = env.query(models.CellSource.ingested_at).filter(
        models.CellSource.source_name == crud.CHAIN_SOURCE, models.CellSource.column_name == "v")
    _write(env, crud.CHAIN_SOURCE, [{"k": "K1", "v": 1}])
    before = stamp.scalar()
    assert _write(env, crud.CHAIN_SOURCE, [{"k": "K1", "v": "1"}])["cell sources"] == \
        [0, "rows"]
    assert stamp.scalar() == before
    assert crud.cast_value_by_type("A ", "string", "v", TABLE) == "A", \
        "the cast trims - the reason a space is no case here"


# --- layers already stacked ------------------------------------------------------------------

T0 = datetime(2026, 9, 26, 1, 0, 0)


def _stack(db, key, col, layers, pin=None):
    """Store `[(source, value), ...]` oldest first, one hour apart - the stack the write path
    no longer builds."""
    row = _row(db, key)
    for hour, (source, value) in enumerate(layers):
        db.add(models.CellSource(table_name=TABLE, row_id=row.row_id, column_name=col,
                                 source_name=source, value=value, updated_by="t",
                                 ingested_at=T0 + timedelta(hours=hour)))
    if pin:
        db.add(models.CellOverwrite(table_name=TABLE, row_id=row.row_id, column_name=col,
                                    is_overwrite=False, updated_by="t",
                                    manual_priority_source=pin))
    db.commit()


def _shown(db, key, col):
    row = _row(db, key)
    layers = {s.source_name: {"value": s.value, "ingested_at": s.ingested_at}
              for s in db.query(models.CellSource).filter(
                  models.CellSource.table_name == TABLE,
                  models.CellSource.row_id == row.row_id, models.CellSource.column_name == col)}
    pin = db.query(models.CellOverwrite.manual_priority_source).filter(
        models.CellOverwrite.table_name == TABLE, models.CellOverwrite.row_id == row.row_id,
        models.CellOverwrite.column_name == col).scalar()
    return crud.compute_priority_value(layers, pin, TABLE)


CELLS = {
    # key: (column, stack oldest first, pin, what stays)
    "NINE": ("v", [("f%02d.csv" % i, v) for i, v in enumerate("AABABAABA", 1)], None,
             {"f08.csv": "B", "f09.csv": "A"}),
    "PERSON": ("v", [("user", "A"), ("f01.csv", "A"), ("f02.csv", "A")], None,
               {"user": "A", "f02.csv": "A"}),
    "CHAIN": ("v", [(crud.CHAIN_SOURCE, "A"), ("f01.csv", "A"), ("f02.csv", "A")], None,
              {crud.CHAIN_SOURCE: "A", "f02.csv": "A"}),
    "AUTO": ("v", [("f01.csv", "A"), (AUTO, "A"), ("f02.csv", "A")], None,
             {AUTO: "A", "f02.csv": "A"}),
    "PINNED": ("v", [("f01.csv", "A"), ("f02.csv", "A"), ("f03.csv", "A")], "f01.csv",
               {"f01.csv": "A", "f03.csv": "A"}),
    "MERGED": ("v", [(crud.merged_layer_name("user", "old_exist_abc123"), "A"),
                     (crud.merged_layer_name(crud.CHAIN_SOURCE, "K9_abc123"), "A"),
                     ("f01.csv", "A"), ("f02.csv", "A")], None,
               {"user (old_exist_abc123)": "A", "chain_ingestion (K9_abc123)": "A",
                "f02.csv": "A"}),
    "NUMBER": ("n", [("f01.csv", 1.0), ("f02.csv", "01"), ("f03.csv", 2.0)], None,
               {"f02.csv": "01", "f03.csv": 2.0}),
}


def test_the_fold_over_stacked_layers_keeps_every_winner_and_one_layer_per_value(env):
    from chain import replay

    _write(env, "seed", [{"k": key} for key in CELLS])
    env.query(models.CellSource).filter(models.CellSource.source_name == "seed").delete()
    env.commit()
    for key, (col, stack, pin, _stays) in CELLS.items():
        _stack(env, key, col, stack, pin)
    shown_before = {key: _shown(env, key, col) for key, (col, *_rest) in CELLS.items()}

    dry = replay.fold_file_layers(env, TABLE, apply=False)
    assert (dry["layers_before"], dry["layers_after"], dry["deepest_before"],
            dry["deepest_after"]) == (28, 15, 9, 3)
    assert dry["layers_deleted"] == 13 and dry["cells_folded"] == 7
    assert len(_layers(env, "NINE")) == 9, "a dry run deletes nothing"

    applied = replay.fold_file_layers(env, TABLE, apply=True)
    assert applied["layers_deleted"] == 13
    for key, (col, _stack_, _pin, stays) in CELLS.items():
        assert _layers(env, key, col) == stays, key
        assert _shown(env, key, col) == shown_before[key], "the winner moved in " + key
    assert replay.fold_file_layers(env, TABLE, apply=True)["layers_deleted"] == 0


@pytest.mark.parametrize("folded, revealed", [(False, "A"), (True, "B")])
def test_withdrawing_the_newest_reveals_a_different_layer_once_folded(env, folded, revealed):
    """R2's edge (225b2c658): f01 B · f03 A · f10 A - withdraw f10. Unfolded, f03's A shows;
    folded, f03 is gone and the layer under it (f01's B) shows. The same holds when f10 was
    never written because it repeated f03 (f224477c1): the file named is then f03."""
    from chain import cell_layer, replay

    _write(env, "seed", [{"k": "K1"}])
    env.query(models.CellSource).filter(models.CellSource.source_name == "seed").delete()
    env.commit()
    _stack(env, "K1", "v", [("f01.csv", "B"), ("f03.csv", "A"), ("f10.csv", "A")])
    if folded:
        replay.fold_file_layers(env, TABLE, apply=True)
    cell_layer.withdraw_source(env, TABLE, "f10.csv", apply=True)
    env.expire_all()
    assert _row(env, "K1").v == revealed
