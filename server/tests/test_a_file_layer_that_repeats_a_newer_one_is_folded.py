"""Same-valued file layers fold (총괄 225b2c658 · f224477c1 · a7d2e90ec).

Write path: a file layer equal to the newest layer of its priority class writes nothing; one whose value an older
file layer of its share holds moves that layer to the front, no new layer (소유자 11-08 «층을 새로하지 말고 순서를
바꿔»); one that differs from all is written. Stacked layers: withdrawing the newest shows the one beneath.
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


def test_a_file_saying_an_older_layers_value_moves_that_layer_to_the_front(env):
    _write(env, "f03.csv", [{"k": "K1", "v": "A"}])
    _write(env, "f07.csv", [{"k": "K1", "v": "B"}])
    counts = _write(env, "f10.csv", [{"k": "K1", "v": "A"}])
    assert counts["folded layers"] == [0, "rows"] and counts["cell sources"] == [1, "rows"], counts
    assert _layers(env, "K1") == {"f03.csv": "A", "f07.csv": "B"}
    assert _row(env, "K1").v == "A"


def test_only_the_newest_layer_decides_a_repeat(env):
    """⛔ f224477c1: 'the same as ANY layer' is wrong - f03 A · f07 B · f10 A must write f10."""
    _write(env, "f03.csv", [{"k": "K1", "v": "A"}])
    _write(env, "f07.csv", [{"k": "K1", "v": "B"}])
    assert _row(env, "K1").v == "B"
    _write(env, "f10.csv", [{"k": "K1", "v": "A"}])
    assert _row(env, "K1").v == "A"


def test_person_chain_and_auto_confirm_layers_are_never_folded(env):
    # the chain's and auto-confirm's layers stacked: a chain write of the shown value makes none now (소유자 11-08)
    _write(env, "user", [{"k": "K1", "v": "A"}])
    _stack(env, "K1", "v", [(crud.CHAIN_SOURCE, "A"), ("f01.csv", "A"), (AUTO, "A")])
    _write(env, "f02.csv", [{"k": "K1", "v": "A"}])
    assert _layers(env, "K1") == {"user": "A", crud.CHAIN_SOURCE: "A", AUTO: "A",
                                  "f01.csv": "A"}, \
        "the newest of the class was auto-confirm, so f01 goes to the front - no f02 layer"


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


def test_withdrawing_the_newest_reveals_the_layer_beneath(env):
    """R2's edge (225b2c658): f01 B · f03 A · f10 A - withdraw f10, f03's A shows."""
    from chain import cell_layer

    _write(env, "seed", [{"k": "K1"}])
    env.query(models.CellSource).filter(models.CellSource.source_name == "seed").delete()
    env.commit()
    _stack(env, "K1", "v", [("f01.csv", "B"), ("f03.csv", "A"), ("f10.csv", "A")])
    cell_layer.withdraw_source(env, TABLE, "f10.csv", apply=True)
    env.expire_all()
    assert _row(env, "K1").v == "A"
