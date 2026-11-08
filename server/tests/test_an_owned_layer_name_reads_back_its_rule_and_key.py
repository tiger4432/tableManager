# -*- coding: utf-8 -*-
"""Owner 11-06 step 2 ㄱ: the chain layer (rule, key) owns is named by ONE builder (`crud.owned_layer_name`) and read
back by ONE parser (`crud.layer_owner`), whatever the rule and the key hold.

  any rule, any key                    built then read back -> the same (rule, key)
  an owned name                        ranks and is judged as the chain's (`layer_writer` · `layer_ranks_as`)
  two owners on one cell               two names - the one unique index (table, row, column, source_name) keeps both
  a source row's bracket · a person's · a file's · a collision copy      no owner
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import crud                                              # noqa: E402

RULES = ["zz_join", "formula fx.c", "enrichment_dedup:encand_rule", "규칙 (둘)", "", "a%b", "r)(x"]
KEYS = ["", " ", "k1", "a b", "(x)", "%", "%25", "%2", "a) (b", "x\n\ty\r", "\x00\x7f", "웨이퍼 (1)",
        "chain_ingestion (r k)", "1.0", "L1|S2", "a" * 500, "😀 (ok)"]


@pytest.mark.parametrize("rule", RULES)
@pytest.mark.parametrize("key", KEYS)
def test_a_name_reads_back_its_owner(rule, key):
    name = crud.owned_layer_name(rule, key)
    assert crud.layer_owner(name) == (rule, key)
    assert crud.layer_writer(name) == crud.CHAIN_SOURCE
    assert crud.layer_ranks_as(name) == crud.CHAIN_SOURCE
    assert "\n" not in name and "\x00" not in name


@pytest.mark.parametrize("base", ["enrichment_auto_confirm", "enrichment_auto_confirm_partial_key"])
def test_auto_confirm_s_owned_layer_keeps_its_base(base):
    name = crud.owned_layer_name("ac rule", "k (1)", base)
    assert crud.layer_owner(name) == ("ac rule", "k (1)")
    assert crud.layer_writer(name) == base and crud.layer_ranks_as(name) == base


def test_two_owners_on_one_cell_are_two_names():
    names = {crud.owned_layer_name(rule, key) for rule in RULES for key in KEYS}
    assert len(names) == len(RULES) * len(KEYS)


@pytest.mark.parametrize("name", [crud.CHAIN_SOURCE, crud.merged_layer_name(crud.CHAIN_SOURCE, "0192f1c2-row"),
                                  "user", "file_a", crud.merged_layer_name("file_a", "0192f1c2-row"), "", None,
                                  "chain_ingestion (a b c)", "chain_ingestion (a b", "file a (x y)",
                                  "enrichment_auto_confirm (0192f1c2-row)"])
def test_a_name_no_owner_built_has_no_owner(name):
    assert crud.layer_owner(name) is None


def test_both_write_doors_stamp_the_owner_cells_off_the_name():
    """A layer row says its owner in `owner_rule` / `owner_key` - the bulk upsert and an ORM insert alike, both off the
    one parser; a layer no rule owns says none."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from database import models

    engine = create_engine("sqlite://")
    models.CellSource.__table__.create(engine)
    db = sessionmaker(bind=engine)()
    owned = crud.owned_layer_name("r (1)", "k|2")
    crud.bulk_upsert_cell_sources(db, [
        {"table_name": "t", "row_id": "a", "column_name": "c", "source_name": owned, "value": 1},
        {"table_name": "t", "row_id": "a", "column_name": "d", "source_name": "file_a", "value": 2}])
    db.add(models.CellSource(table_name="t", row_id="b", column_name="c", source_name=owned, value=3))
    db.add(models.CellSource(table_name="t", row_id="b", column_name="d", source_name="user", value=4))
    db.commit()
    got = {(row.row_id, row.column_name): (row.owner_rule, row.owner_key) for row in db.query(models.CellSource)}
    assert got == {("a", "c"): ("r (1)", "k|2"), ("a", "d"): (None, None),
                   ("b", "c"): ("r (1)", "k|2"), ("b", "d"): (None, None)}
