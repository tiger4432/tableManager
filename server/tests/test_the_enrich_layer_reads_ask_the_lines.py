# -*- coding: utf-8 -*-
"""Cell-source overhaul read share (lead 11-11, the 11-14 gate's census): the enrich reads of «who wrote this cell» ask
the table's lines (`lines.layers`), not cell_sources - `analysis._human_resolved_cells` (a person's standing word) and
`candidates.find_unresolved_cells` (no word but the asking rule's own). A cell_sources row left behind is not read."""
import pytest

from conftest import retire_dynamic_model
from database import crud, models
from tests.support import line_tables

T = "lyr_probe"
ENTRY = {"composite_key_source": ["k"], "column_types": {"k": "string", "a": "string", "b": "string"}}
ROWS = ["r1", "r2", "r3", "r4", "r5"]


@pytest.fixture
def seeded(db_session, monkeypatch):
    models.init_dynamic_models({T: ENTRY})
    monkeypatch.setitem(crud.TABLE_CONFIG, T, ENTRY)
    engine = db_session.get_bind()
    bits = line_tables.build(engine, T)
    conn = db_session.connection()
    line_tables.line(conn, T, bits, "r1", source=crud.USER_SOURCE, written_by="kim", values={"a": "x"})
    line_tables.line(conn, T, bits, "r1", source="file.csv", written_by="parser", values={"b": "y"})
    # a collision-merge copy of a person's layer - not the human layer by its exact name (as the old read)
    line_tables.line(conn, T, bits, "r2", source="user (old_exist_r9)", written_by="lee", values={"a": "z"})
    # a person's word the person then withdrew: the head line withdrew it - no standing word
    line_tables.line(conn, T, bits, "r3", source=crud.USER_SOURCE, written_by="kim", values={"a": "q"}, head=False)
    line_tables.line(conn, T, bits, "r3", kind="withdraw", source=crud.USER_SOURCE, written_by="kim",
                     withdrawn=["a"])
    # the asking rule's own answer
    line_tables.line(conn, T, bits, "r4", source="chain_ingestion (r4)", written_by="my_rule", values={"a": "m"})
    # left behind in the retired table - a read of it would see a person on r5.a
    db_session.add(models.CellSource(table_name=T, row_id="r5", column_name="a", source_name=crud.USER_SOURCE,
                                     value="old", updated_by="kim"))
    db_session.commit()
    try:
        yield db_session
    finally:
        db_session.rollback()
        line_tables.drop(engine, T)
        retire_dynamic_model(T)


def test_a_persons_standing_word_is_the_human_layer(seeded):
    from chain.enrichment import analysis

    assert analysis._human_resolved_cells(seeded, T, ROWS, ["a", "b"]) == {("r1", "a")}


def test_a_cell_with_no_word_but_the_rule_s_own_is_unresolved(seeded):
    from chain.enrichment import candidates

    got = candidates.find_unresolved_cells(seeded, T, ROWS, ["a", "b"], own=("my_rule",))
    assert got == {(r, c) for r in ROWS for c in ("a", "b")} - {("r1", "a"), ("r1", "b"), ("r2", "a")}
    assert ("r4", "a") not in candidates.find_unresolved_cells(seeded, T, ["r4"], ["a"]), "another rule's: taken"
