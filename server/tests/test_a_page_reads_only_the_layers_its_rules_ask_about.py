# -*- coding: utf-8 -*-
"""Lead 11-09 (A measured the box: a 1,000-row dt_log page 0.27 -> 0.91 s after the rules every table has began to ask a
model): a page reads the layers only of the cells holding a layer of a writer its rules ask, and a cell says
`written_by` only when its writer is one a rule asks - every rule matches the cells it matched when every layer of
every unnamed cell was ranked.

  clause   `crud.writer_kind_clause` says of each name what `crud.writer_kind` says (LIKE's «_» and «%» escaped)
  matches  rules asking each set of writers × cells of every layer mix and pin: a rule's cells are the ones ranking
           every layer gives it
  reads    rules asking a person and a merge read no layer; a page with no layer of an asked writer reads once
"""
from datetime import datetime, timedelta, timezone

import pytest

import grid_look
from database import crud, models

TABLE = "who_page"
T0 = datetime(2026, 11, 9, tzinfo=timezone.utc)
NAMES = ["user", "collision_merge", "llm_draft", "llm_draft (r1 k1)", "chain_ingestion", "chain_ingestion (r1 k%7C1)",
         "enrichment_auto_confirm (r1 k1)", "enrichment_backfill", "custom_script", "pipeline_parser", "lots.csv",
         "lots (2).csv", "user (copy).csv", "llmXdraft", "llmXdraft (x).csv", "llm%draft", "chain_ingestionX", "external:csv@t@root|a/b.csv"]
KINDS = ["person", "merge", "ai", "chain", "file"]
#: each cell's layers, oldest first, and its page priority_source (a pin or a person's / a merge's overwrite row)
CELLS = {
    "file": (["lots.csv"], None), "chain": (["chain_ingestion (r1 k1)"], None), "ai": (["llm_draft"], None),
    "ai over file": (["lots.csv", "llm_draft"], None), "file over ai": (["llm_draft", "lots.csv"], None),
    "chain over ai": (["llm_draft", "chain_ingestion"], None), "person over ai": (["llm_draft", "user"], None),
    "merge layer": (["lots.csv", "collision_merge"], None), "person layer": (["user"], None),
    "pinned file over ai": (["llm_draft", "lots.csv"], "lots.csv"), "named person": (["user"], "user"),
    "named merge": (["collision_merge"], "collision_merge"), "no layer": ([], None),
    "llmXdraft": (["llmXdraft"], None), "user (copy).csv": (["user (copy).csv"], None),
}


@pytest.fixture
def page(db_session):
    rows = {}
    for n, (cell, (names, named)) in enumerate(sorted(CELLS.items())):
        row_id = "r%02d" % n
        db_session.add_all([models.CellSource(table_name=TABLE, row_id=row_id, column_name="c", source_name=name,
                                              value="v", ingested_at=T0 + timedelta(minutes=m))
                            for m, name in enumerate(names)])
        rows[cell] = (row_id, named)
    # a layer on a cell the page does not read as layered (a framework column) - it says no writer
    db_session.add(models.CellSource(table_name=TABLE, row_id="r00", column_name="created_at", source_name="llm_draft",
                                     value="v", ingested_at=T0))
    db_session.commit()
    yield db_session, rows
    db_session.query(models.CellSource).filter(models.CellSource.table_name == TABLE).delete()
    db_session.commit()


def _page(rows):
    return [{"row_id": row_id, "data": {"c": {"priority_source": named}, "created_at": {"value": "t"}}}
            for row_id, named in rows.values()]


def _ranked(db, row_id, named):
    """The writer ranking every layer of the cell gives - the page read before lead 11-09."""
    if named is not None:
        return crud.writer_kind(named)
    said = {name: at for name, at in db.query(models.CellSource.source_name, models.CellSource.ingested_at).filter(
        models.CellSource.table_name == TABLE, models.CellSource.row_id == row_id,
        models.CellSource.column_name == "c")}
    if not said:
        return None
    _, source = crud.compute_priority_value({name: {} for name in said}, None, TABLE, ingested_at_by_source=said)
    return crud.writer_kind(source)


def test_the_clause_says_what_writer_kind_says(db_session):
    db_session.add_all([models.CellSource(table_name=TABLE, row_id="n%02d" % n, column_name="c", source_name=name,
                                          value="v") for n, name in enumerate(NAMES)])
    db_session.commit()
    try:
        assert {crud.writer_kind(name) for name in NAMES} == set(KINDS), "canary: every writer among the names"
        for kinds in [{kind} for kind in KINDS] + [{"person", "merge", "ai"}, set(KINDS), set()]:
            picked = {name for (name,) in db_session.query(models.CellSource.source_name).filter(
                models.CellSource.table_name == TABLE, crud.writer_kind_clause(models.CellSource.source_name, kinds))}
            assert picked == {name for name in NAMES if crud.writer_kind(name) in kinds}, kinds
    finally:
        db_session.query(models.CellSource).filter(models.CellSource.table_name == TABLE).delete()
        db_session.commit()


@pytest.mark.parametrize("kinds", [{"ai"}, {"file"}, {"chain"}, {"person", "merge", "ai"}, set(KINDS)],
                         ids=lambda kinds: "+".join(sorted(kinds)))
def test_every_rule_matches_the_cells_ranking_every_layer_gives_it(page, kinds):
    db, rows = page
    before = {cell: _ranked(db, row_id, named) for cell, (row_id, named) in rows.items()}
    assert {"ai", "file", "chain", "person", "merge", None} <= set(before.values()), "canary: the board's writers"
    read = _page(rows)
    grid_look._writers(db, TABLE, read, None, kinds)
    after = {cell: row["data"]["c"].get("written_by") for cell, row in zip(rows, read)}
    for kind in kinds:
        assert {c for c, w in after.items() if w == kind} == {c for c, w in before.items() if w == kind}, kind
    assert set(after.values()) - {None} <= kinds, "a cell says only a writer a rule asks"
    assert not any("written_by" in row["data"]["created_at"] for row in read), "a cell outside the layers says none"


def test_a_person_and_a_merge_read_no_layer_and_a_page_with_no_asked_layer_reads_once(page, monkeypatch):
    db, rows = page
    asked = []
    real = db.query
    monkeypatch.setattr(db, "query", lambda *a, **k: asked.append(a) or real(*a, **k))
    read = _page(rows)
    grid_look._writers(db, TABLE, read, None, {"person", "merge"})
    said = {cell: row["data"]["c"].get("written_by") for cell, row in zip(rows, read)}
    assert asked == [] and {c: w for c, w in said.items() if w} == {"named person": "person", "named merge": "merge"}
    grid_look._writers(db, TABLE, _page({"chain": rows["chain"]}), None, {"person", "merge", "file"})
    assert len(asked) == 1, "the chain's cell holds no layer a rule asks: one read, and no layer read"
