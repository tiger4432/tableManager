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
                                                             source_name=source, value={"value": value},
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
