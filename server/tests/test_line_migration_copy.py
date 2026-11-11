"""line_migration.copy_page / copy_total / AlreadyCopied on sqlite: old layers become lines as they are - the merge
over the copied lines gives what t shows, won_by names those lines, a column a later write already heads keeps
that head, the last page leaves the «copy» audit row and a second copy is refused."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import MetaData, Table, create_engine, select, text
from sqlalchemy.orm import sessionmaker

from database import line_migration, lines
from database.models import CellOverwrite, CellSource, sql_type_of

CFG = {"column_types": {"lot": "string", "qty": "number"}}
T1, T2 = datetime(2026, 11, 1, 9, tzinfo=timezone.utc), datetime(2026, 11, 2, 9, tzinfo=timezone.utc)


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    for model in (lines.LineColumn, lines.AuditBatch, lines.LineSource, CellOverwrite, CellSource):
        model.__table__.create(engine)
    session = sessionmaker(bind=engine)()
    Table("t", MetaData(), *lines._data_columns(CFG, sql_type_of, row_id_key=True)).create(session.connection())
    session.execute(text("INSERT INTO t (row_id, business_key_val, lot, qty) VALUES "
                         "('r1', 'k1', 'u', 5), ('r2', 'k2', 'x', NULL), ('r3', 'k3', NULL, 7)"))
    layers = [("r1", "lot", "user", "u", T1), ("r1", "lot", "fileA", "a", T2), ("r1", "qty", "fileA", 5, T2),
              ("r2", "lot", "fileA", "x", T1), ("r3", "qty", "fileB", 7, T1), ("gone", "lot", "fileA", "z", T1)]
    for row_id, col, source, value, at in layers:
        session.execute(CellSource.__table__.insert().values(table_name="t", row_id=row_id, column_name=col,
                                                             source_name=source, value=value,
                                                             ingested_at=at, updated_by="seed"))
    lines.ensure_line_table(session, "t", CFG)
    yield session
    session.close()


def copy_all(db, page_size=2):
    after, cells, pages = None, 0, 0
    while True:
        n, after = line_migration.copy_page(db, "t", CFG, after, page_size, transaction_id="tx-copy")
        cells, pages = cells + n, pages + 1
        if after is None:
            return cells, pages


def test_the_copied_lines_merge_to_what_t_shows_and_won_by_names_them(db):
    assert line_migration.copy_total(db, "t") == 6
    cells, pages = copy_all(db)
    assert (cells, pages) == (5, 3)       # the row t no longer holds is not copied; a full page asks once more
    merged = lines.merge(db, "t", CFG, ["r1", "r2", "r3"])
    shown = {r.row_id: r for r in db.execute(text("SELECT row_id, lot, qty, won_by FROM t"))}
    for row_id, cols in merged.items():
        for col, (value, line_id) in cols.items():
            assert value == getattr(shown[row_id], col), (row_id, col)
    lt = lines.shape(db, "t", CFG)["lines"]
    user_line = db.execute(select(lt.c.line_id).where(lt.c.row_id == "r1", lt.c.source_name == "user")).scalar()
    import json

    won = shown["r1"].won_by
    won = json.loads(won) if isinstance(won, str) else won
    assert won["lot"] == user_line and "qty" in won
    assert db.execute(select(lt.c.batch).distinct()).scalars().all() == ["tx-copy"]


def test_a_column_a_later_write_heads_keeps_that_head(db):
    s = lines.shape(db, "t", CFG)
    bit = s["bits"]["lot"]
    mask = lines._mask(bit)
    db.execute(s["lines"].insert().values(line_kind="write", source_name="fileA", at=T2, row_id="r2", batch="later",
                                          **{lines.value_column("lot"): "y", "written_0": mask, "head_0": mask}))
    copy_all(db)
    lt = s["lines"]
    copied = db.execute(select(lt.c.head_0).where(lt.c.row_id == "r2", lt.c.batch == "tx-copy")).scalar()
    assert copied & mask == 0
    assert lines.merge(db, "t", CFG, ["r2"])["r2"]["lot"][0] == "y"


def test_a_second_copy_is_refused_with_its_count(db):
    copy_all(db)
    with pytest.raises(line_migration.AlreadyCopied, match="already copied, 4 lines"):
        line_migration.copy_page(db, "t", CFG, None, 2, transaction_id="tx-again")


def test_a_table_without_lines_is_refused(db):
    lines.drop_line_table(db, "t")
    with pytest.raises(ValueError, match="not built"):
        line_migration.copy_page(db, "t", CFG, None, 2, transaction_id="tx")
    with pytest.raises(ValueError, match="keeps lines"):
        line_migration.copy_page(db, "v", {"kind": "view", "column_types": {}}, None, 2, transaction_id="tx")


def test_an_interrupted_copy_resumes_after_its_last_committed_row(db):
    n, after = line_migration.copy_page(db, "t", CFG, None, 2, transaction_id="tx-copy")      # gone, r1
    assert after == "r1" and line_migration.copied_through(db, "t", CFG, "tx-copy") == "r1"
    cells, pages = copy_all(db)                                     # a new run starts from None
    assert cells == 2                                               # r2, r3 only - r1 is not copied twice
    lt = lines.shape(db, "t", CFG)["lines"]
    assert db.execute(select(lt.c.line_id).where(lt.c.row_id == "r1")).all().__len__() == 2


def test_a_blank_layer_copies_as_null_through_the_one_seat(db):
    """Length-0 text (after strip) is absence, folded by one function (crud.layer_value / line_text) - a «» or «  »
    layer copies as a NULL value that still speaks for its column."""
    for source, value in (("fileC", ""), ("fileD", "   ")):
        db.execute(CellSource.__table__.insert().values(table_name="t", row_id="r3", column_name="lot",
                                                        source_name=source, value=value,
                                                        ingested_at=T2, updated_by="seed"))
    copy_all(db)
    lt = lines.shape(db, "t", CFG)["lines"]
    got = dict(db.execute(select(lt.c.source_name, lt.c[lines.value_column("lot")])
                          .where(lt.c.row_id == "r3", lt.c.source_name.in_(["fileC", "fileD"]))).all())
    assert got == {"fileC": None, "fileD": None}
    assert ("r3", "lot") in {cell for cell in lines.layers(db, "t", ["r3"])}          # it still speaks


def test_an_object_value_refuses_the_page_and_copies_nothing(db):
    db.execute(CellSource.__table__.insert().values(table_name="t", row_id="r1", column_name="qty",
                                                    source_name="fileZ", value={"value": 5},
                                                    ingested_at=T2, updated_by="seed"))
    with pytest.raises(ValueError) as said:
        line_migration.copy_page(db, "t", CFG, None, 10, transaction_id="tx-copy")
    assert str(said.value) == line_migration.copy_refusal("t", "r1", "qty", "fileZ", line_migration.OBJECT_HELD)
    lt = lines.shape(db, "t", CFG)["lines"]
    assert db.execute(select(lt.c.line_id)).all() == []


@pytest.mark.parametrize("stored, line, won", [("1.0", "1.0", True)])     # JSON 1.0: sqlite keeps it as 1 - see _pg
def test_a_text_cell_copies_what_todays_write_would_store(db, stored, line, won):
    """A JSON number in a text column's layer is stored in the write's spelling (cast_value_by_type ->
    clean_str_value, «1»); a text «1.0» stays as written (6d77e1ad0) - the copy runs the write's cast (lead 11-11).
    t shows «1.0» as PostgreSQL wrote it: won_by names the line only where the line says what t shows - the state
    the notation retro reads (A 95b58102c: no won_by key = ask lines.merge)."""
    import json

    db.execute(text("UPDATE t SET lot = '1.0' WHERE row_id = 'r2'"))
    db.execute(CellSource.__table__.insert().values(table_name="t", row_id="r2", column_name="lot",
                                                    source_name="fileN", value=stored,
                                                    ingested_at=T2, updated_by="seed"))
    copy_all(db)
    lt = lines.shape(db, "t", CFG)["lines"]
    line_id, said = db.execute(select(lt.c.line_id, lt.c[lines.value_column("lot")])
                               .where(lt.c.row_id == "r2", lt.c.source_name == "fileN")).one()
    assert said == line
    won_by = db.execute(text("SELECT won_by FROM t WHERE row_id = 'r2'")).scalar()
    won_by = (json.loads(won_by) if isinstance(won_by, str) else won_by) or {}
    assert (won_by.get("lot") == line_id) if won else ("lot" not in won_by)


def test_a_value_the_write_refuses_refuses_the_page_and_copies_nothing(db):
    db.execute(CellSource.__table__.insert().values(table_name="t", row_id="r1", column_name="qty",
                                                    source_name="fileZ", value="abc",
                                                    ingested_at=T2, updated_by="seed"))
    with pytest.raises(ValueError) as said:
        line_migration.copy_page(db, "t", CFG, None, 10, transaction_id="tx-copy")
    assert str(said.value) == ("Cannot copy t: row r1 column qty (source fileZ) holds 'abc', which the write refuses: "
                               "a number is expected - nothing of this page was copied; tell the lead")
    lt = lines.shape(db, "t", CFG)["lines"]
    assert db.execute(select(lt.c.line_id)).all() == []


@pytest.mark.parametrize("gone", ["owner_key", "owner_rule"])
def test_an_old_table_without_a_column_the_copy_reads_is_refused_by_name(db, gone):
    """The old table is cold after the landing - nothing adds its columns any more (lead 11-11): a database whose
    cell_sources lacks one the copy reads is refused, the column named, before any line is written."""
    db.execute(text(f"ALTER TABLE cell_sources DROP COLUMN {gone}"))
    with pytest.raises(ValueError, match=f"cell_sources has no {gone} - the copy reads them"):
        line_migration.copy_page(db, "t", CFG, None, 2, transaction_id="tx-copy")
