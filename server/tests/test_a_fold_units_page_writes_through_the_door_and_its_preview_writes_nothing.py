"""fold-units' page through the product's write door (lead 11-11 ㄱ, scratchpad ruling): `replay._fold_units_page`
hands a fold rule's marks to crud.apply_batch_updates collapsed - the mark is the rule's layer on the line table, t
shows it, one outbox row a page. Its preview writes nothing (judged read-only, lead 11-12): t, the lines and the
outbox as they were. A row the answer named that is gone is not made again."""
import pytest
from sqlalchemy import text

from chain import replay
from database import crud, lines, models, schemas
from support import line_tables

LOG, MARK = "fu_page_log", "fold_mark"
TABLES = {LOG: {"business_key": "record_id", "column_types": {"record_id": "string", MARK: "string"}}}
RULE = "fu_page_rule"


@pytest.fixture()
def db(db_session):
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    line_tables.build(db_session.get_bind(), LOG)
    crud.apply_batch_updates(db_session, LOG, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        business_key_val=key, updates={"record_id": key}, source_name="log.csv", updated_by="t")
        for key in ("r1", "r2", "r3")], silent=True))
    db_session.commit()
    yield db_session
    db_session.rollback()
    line_tables.drop(db_session.get_bind(), LOG)
    from conftest import retire_dynamic_model
    retire_dynamic_model(LOG)
    crud.TABLE_CONFIG.pop(LOG, None)


def _ids(db):
    model = models.DYNAMIC_TABLES[LOG]
    return {key: row_id for row_id, key in db.query(model.row_id, model.business_key_val)}


def _proposed(db, keys, mark="AUTO"):
    ids = _ids(db)
    return [schemas.GeneralUpdateItem(row_id=ids.get(key, "gone-" + key), updates={MARK: mark},
                                      source_name=crud.CHAIN_SOURCE, updated_by=RULE, owner_key="J1")
            for key in keys]


def _state(db):
    model = models.DYNAMIC_TABLES[LOG]
    db.expire_all()
    return (sorted((key, mark) for key, mark in db.query(model.business_key_val, getattr(model, MARK))),
            db.execute(text('SELECT count(*) FROM "%s"' % lines.lines_relation(LOG))).scalar(),
            db.query(models.DatabaseOutbox).count())


def _page(db, proposed, apply):
    return replay._fold_units_page(db, LOG, models.DYNAMIC_TABLES[LOG], MARK, proposed, "tx-fu", apply)[0]


def test_a_page_writes_the_rules_mark_as_its_layer_and_stages_one_row(db):
    shown, line_count, outbox = _state(db)

    counts = _page(db, _proposed(db, ["r1", "r2", "gone"]), apply=True)

    assert (counts["rows_to_mark"], counts["rows_marked"], counts["rows_gone"]) == (2, 2, 1)
    assert _state(db) == ([("r1", "AUTO"), ("r2", "AUTO"), ("r3", None)], line_count + 2, outbox + 1)
    ids = _ids(db)
    said = lines.layers(db, LOG, [ids["r1"]], [MARK])[(ids["r1"], MARK)]
    assert [crud.layer_ranks_as(source) for source in said] == [crud.CHAIN_SOURCE]
    assert _page(db, _proposed(db, ["r1"]), apply=True)["rows_already_marked"] == 1, "a re-run writes nothing"


def test_the_preview_counts_the_page_and_leaves_t_the_lines_and_the_outbox_as_they_were(db):
    before = _state(db)

    counts = _page(db, _proposed(db, ["r1", "r2"]), apply=False)

    assert counts["rows_to_mark"] == 2, "canary: the preview judged the two marks the run writes"
    assert _state(db) == before
