"""A chain line the funnel writes carries its owner (lead 11-12 ㄱ): owner_rule / owner_key from its item, else from
its source's name (`crud.layer_owner`) - so the merge's «a rule that says its priority first» (83de1715e, 11-09) reads
it. Two rules' lines on one cell: the rule with a declared priority shows over the newer rule without one."""
import pytest

from database import crud, lines, models, schemas
from tests.support import line_tables

T = "zzowner_rank"
CONFIG = {"business_key": "k", "column_types": {"k": "string", "v": "string"}}


@pytest.fixture
def db(db_session, monkeypatch):
    crud.TABLE_CONFIG[T] = CONFIG
    models.init_dynamic_models({T: CONFIG})
    line_tables.build(db_session.get_bind(), T)
    monkeypatch.setattr(crud, "_rule_priorities", lambda: {"said_rule": 1})
    monkeypatch.setattr(crud, "_rule_order", lambda: {})
    yield db_session
    db_session.rollback()
    line_tables.drop(db_session.get_bind(), T)
    crud.TABLE_CONFIG.pop(T, None)


def _write(db, rule, value):
    crud.apply_batch_updates(db, T, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        business_key_val="K1", updates={"k": "K1", "v": value}, updated_by=rule,
        source_name=crud.owned_layer_name(rule, "K1"))]))
    db.commit()


def test_a_rule_that_says_its_priority_shows_over_a_newer_one_that_does_not(db):
    _write(db, "said_rule", "said")
    _write(db, "quiet_rule", "quiet")                          # newer, no priority declared
    db.expire_all()
    row = db.query(models.DYNAMIC_TABLES[T]).one()
    assert row.v == "said", row.v                            # the declared rule shows
    said = lines.layers(db, T, [row.row_id], ["v"])[(row.row_id, "v")]
    assert {s: (e["owner_rule"], e["owner_key"]) for s, e in said.items()} == {
        crud.owned_layer_name("said_rule", "K1"): ("said_rule", "K1"),
        crud.owned_layer_name("quiet_rule", "K1"): ("quiet_rule", "K1")}
