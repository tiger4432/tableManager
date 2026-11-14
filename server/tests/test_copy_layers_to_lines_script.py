"""The migration command (owner 11-11): a table copies to its end, a second run says «already copied»; a cell whose
copied lines do not give what t shows is recorded in copy_mismatch_<t>.csv and its page lands (owner ㄴ, lead 11-12);
--rows copies a record's rows again."""
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import MetaData, Table, create_engine, func, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from database import lines
from database.models import CellOverwrite, CellSource, FileIngestionCheckpoint, sql_type_of
from scripts import copy_layers_to_lines as script

CFG = {"column_types": {"lot": "string"}}
T1 = datetime(2026, 11, 1, 9, tzinfo=timezone.utc)


def build(t_lot_r2):
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    for model in (lines.LineColumn, lines.AuditBatch, lines.LineSource, CellOverwrite, CellSource,
                  FileIngestionCheckpoint):
        model.__table__.create(engine)
    with Session(bind=engine) as db:
        Table("t", MetaData(), *lines._data_columns(CFG, sql_type_of, row_id_key=True)).create(db.connection())
        db.execute(text("INSERT INTO t (row_id, business_key_val, lot) VALUES ('r1', 'k1', 'a'), ('r2', 'k2', :v)"),
                   {"v": t_lot_r2})
        for row_id, value in (("r1", "a"), ("r2", "b")):
            db.execute(CellSource.__table__.insert().values(table_name="t", row_id=row_id, column_name="lot",
                                                            source_name="fileA", value=value, ingested_at=T1,
                                                            updated_by="seed"))
        lines.ensure_line_table(db, "t", CFG)
        db.commit()
    return engine


def copied_rows(engine):
    with Session(bind=engine) as db:
        lt = lines.shape(db, "t", CFG)["lines"]
        return sorted(db.execute(select(lt.c.row_id).where(lt.c.batch == "copy_lines:t")).scalars().all())


def test_a_table_copies_to_its_end_and_a_second_run_says_already_copied():
    engine, said = build("b"), []
    first = script.copy_table(engine, "t", CFG, 1, say=said.append)
    assert (first["copied"], copied_rows(engine)) == (2, ["r1", "r2"])
    assert script.copy_table(engine, "t", CFG, 1, say=said.append) == {"table": "t", "already": True}
    assert said[-1].startswith("t: already copied")


def test_a_resumed_copy_says_the_rows_an_earlier_run_copied_and_counts_from_them(monkeypatch):
    """Lead 11-13 (the rehearsal's resume said «5000 / 2174000 rows» after 1,264,000 were copied): the first line of a
    resumed table says the rows already copied, and its progress counts from them against the table's rows."""
    from database import line_migration

    engine, said = build("b"), []
    with Session(bind=engine) as db:                          # an earlier run: its first page committed, then stopped
        line_migration.copy_page(db, "t", CFG, None, 1, transaction_id="copy_lines:t")
        db.commit()
    assert copied_rows(engine) == ["r1"], "CANARY: one row copied before the resume"
    monkeypatch.setattr(script, "SAY_EVERY", 0.0)
    out = script.copy_table(engine, "t", CFG, 1, say=said.append)
    assert said[0] == "t: resuming - already copied 1 / 2 rows (an earlier run's pages)", said
    progress = [line for line in said if " / 2 rows, " in line]
    assert progress and progress[0].startswith("t: 2 / 2 rows, "), said
    assert (out["copied"], copied_rows(engine)) == (1, ["r1", "r2"])


def test_a_resumed_copys_end_line_says_this_runs_cells_and_what_the_file_holds(tmp_path, monkeypatch):
    """Lead 11-13 (the rehearsal's resume said 44,893 while its file held 98,804): an earlier run's recorded cell and
    this run's are both in the file, and the end line says each."""
    from database import line_migration

    monkeypatch.chdir(tmp_path)
    engine, said = build("not b"), []
    script.record(script.RECORD % "t", "t", [("r0", "lot", "x", "y")])      # an earlier run's mismatched cell
    with Session(bind=engine) as db:                          # and its first page committed (r1 matches)
        line_migration.copy_page(db, "t", CFG, None, 1, transaction_id="copy_lines:t")
        db.commit()
    out = script.copy_table(engine, "t", CFG, 1, say=said.append)
    assert (out["mismatched"], out["held"]) == (1, 2), out
    assert "this run 1 · the file now holds 2 mismatched cell(s)" in said[-1], said[-1]


def test_a_key_merge_between_two_runs_does_not_move_where_the_copy_resumes(monkeypatch):
    """Lead 11-14 (a defect of resume itself): a table half copied, then a new-release key merge of a copied row (r1)
    into a row past the cursor (r4) moves r1's copy lines onto r4 - the resume still copies every row after the
    page it committed, r2 and r3 included, each under its own layer."""
    from database import crud, line_migration, write_lines
    from database.models import DatabaseOutbox

    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    for model in (lines.LineColumn, lines.AuditBatch, lines.LineSource, CellOverwrite, CellSource, DatabaseOutbox,
                  FileIngestionCheckpoint):
        model.__table__.create(engine)
    rows = ("r1", "r2", "r3", "r4")
    with Session(bind=engine) as db:
        Table("t", MetaData(), *lines._data_columns(CFG, sql_type_of, row_id_key=True)).create(db.connection())
        for n, row_id in enumerate(rows):
            db.execute(text("INSERT INTO t (row_id, business_key_val, lot) VALUES (:r, :k, :v)"),
                       {"r": row_id, "k": "k%d" % n, "v": "v%d" % n})
            db.execute(CellSource.__table__.insert().values(table_name="t", row_id=row_id, column_name="lot",
                                                            source_name="fileA", value="v%d" % n, ingested_at=T1,
                                                            updated_by="seed"))
        lines.ensure_line_table(db, "t", CFG)
        db.commit()
    monkeypatch.setitem(crud.TABLE_CONFIG, "t", CFG)
    with Session(bind=engine) as db:                          # an earlier run: its first page (r1), then stopped
        line_migration.copy_page(db, "t", CFG, None, 1, transaction_id="copy_lines:t")
        db.commit()
    assert copied_rows(engine) == ["r1"], "CANARY: one page copied before the merge"
    with Session(bind=engine) as db:                          # the new release runs between the two runs
        write_lines.merge_rows(db, "t", [("r1", "r4")], source_name="user", written_by="tester",
                               transaction_id="merge-between-runs")
        db.commit()
    assert copied_rows(engine) == ["r4"], "CANARY: the merge moved r1's copy lines onto r4"

    script.copy_table(engine, "t", CFG, 1, say=lambda line: None)
    with Session(bind=engine) as db:
        lt = lines.shape(db, "t", CFG)["lines"]
        own = set(db.execute(select(lt.c.row_id).where(lt.c.batch == "copy_lines:t", lt.c.source_name == "fileA"))
                  .scalars())
        record = db.query(FileIngestionCheckpoint).filter_by(table_name="t", file_signature="copy_lines:t").one()
        took = (record.cursor, record.status, record.pages, record.layers, record.processed_rows)
    assert own == {"r2", "r3", "r4"}, own
    assert took == ("r4", "DONE", 4, 4, 4) and record.seconds > 0, (took, record.seconds)   # owner: ops figures kept


def test_a_copy_killed_half_way_then_written_by_the_old_release_resumes_on_the_rest(tmp_path, monkeypatch):
    """Ops 11-14 (owner): ⑥ killed half way, the old release (11-11e - no line tables) ran and wrote, then the copy
    resumes. A row the old release wrote AFTER its page was copied keeps t's value, its new old-shape layer is not
    copied and no mismatch names it (RUN ⑨ «다시 올리면»); a row not copied yet comes over with that layer too."""
    from database import line_migration

    monkeypatch.chdir(tmp_path)
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    for model in (lines.LineColumn, lines.AuditBatch, lines.LineSource, CellOverwrite, CellSource,
                  FileIngestionCheckpoint):
        model.__table__.create(engine)
    with Session(bind=engine) as db:
        Table("t", MetaData(), *lines._data_columns(CFG, sql_type_of, row_id_key=True)).create(db.connection())
        for n, row_id in enumerate(("r1", "r2", "r3", "r4")):
            db.execute(text("INSERT INTO t (row_id, business_key_val, lot) VALUES (:r, :k, :v)"),
                       {"r": row_id, "k": "k%d" % n, "v": "v%d" % n})
            db.execute(CellSource.__table__.insert().values(table_name="t", row_id=row_id, column_name="lot",
                                                            source_name="fileA", value="v%d" % n, ingested_at=T1,
                                                            updated_by="seed"))
        lines.ensure_line_table(db, "t", CFG)
        db.commit()
    with Session(bind=engine) as db:                          # ⑥ killed after its first two pages
        after = None
        for _ in range(2):
            _n, after = line_migration.copy_page(db, "t", CFG, after, 1, transaction_id="copy_lines:t")
            db.commit()
    assert copied_rows(engine) == ["r1", "r2"], "CANARY: two pages copied before the kill"
    with Session(bind=engine) as db:                          # 14b kept no record - ops's table has copy lines only
        assert db.query(FileIngestionCheckpoint).delete() == 1, "CANARY: the two pages wrote the record"
        db.commit()
    later = datetime(2026, 11, 14, 15, tzinfo=timezone.utc)
    with Session(bind=engine) as db:                          # the old release writes the old way: a layer and t
        for row_id, value in (("r1", "new1"), ("r3", "new3")):
            db.execute(CellSource.__table__.insert().values(table_name="t", row_id=row_id, column_name="lot",
                                                            source_name="fileB", value=value, ingested_at=later,
                                                            updated_by="old release"))
            db.execute(text("UPDATE t SET lot = :v WHERE row_id = :r"), {"v": value, "r": row_id})
        db.commit()

    said = []
    out = script.copy_table(engine, "t", CFG, 1, say=said.append)
    assert said[0] == "t: cursor seeded from copied lines at row r2", said
    with Session(bind=engine) as db:
        record = db.query(FileIngestionCheckpoint).filter_by(table_name="t", file_signature="copy_lines:t").one()
        assert (record.cursor, record.status, record.pages) == ("r4", "DONE", 2), (record.cursor, record.pages)
        lt = lines.shape(db, "t", CFG)["lines"]
        copied = {(r, s) for r, s in db.execute(select(lt.c.row_id, lt.c.source_name).where(
            lt.c.batch == "copy_lines:t"))}
        lot = dict(db.execute(text("SELECT row_id, lot FROM t")).all())
    assert {("r3", "fileA"), ("r3", "fileB"), ("r4", "fileA")} <= copied, copied      # not copied yet: all of it
    assert ("r1", "fileB") not in copied, copied              # copied before the old release wrote: its layer stays out
    assert lot["r1"] == "new1" and lot["r3"] == "new3", lot   # t keeps what the old release wrote
    assert out["mismatched"] == 0 and not out.get("held"), out   # and no mismatch names r1


def test_an_old_layer_table_without_the_owner_columns_is_refused_in_one_line():
    engine, said = build("b"), []
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE cell_sources DROP COLUMN owner_key"))
    out = script.copy_table(engine, "t", CFG, 1, say=said.append)
    assert out["stopped"] and copied_rows(engine) == []
    assert said == ["REFUSED - t: cell_sources has no owner_key - the copy reads them; this database cannot be copied"]


def test_an_old_merge_copy_layer_is_noted_as_a_copy_and_the_preview_counts_it():
    engine = build("b")
    copy = "fileA (k9_a1b2c3)"
    with engine.begin() as conn:
        conn.execute(CellSource.__table__.insert().values(table_name="t", row_id="r1", column_name="lot",
                                                          source_name=copy, value="a", ingested_at=T1,
                                                          updated_by="seed"))
    planned = script.plan(engine, {"t": CFG})
    assert planned[0]["copies"] == [copy]
    script.copy_table(engine, "t", CFG, 1, say=lambda line: None)
    with Session(bind=engine) as db:
        noted = dict(db.execute(select(lines.LineSource.source_name, lines.LineSource.copy_of)).all())
    assert noted[copy] == "fileA" and noted["fileA"] is None


def test_the_check_counts_after_every_page_and_leaves_nothing():
    engine, said = build("not b"), []
    out = script.check_table(engine, "t", CFG, 1, say=said.append)
    assert out == {"table": "t", "checked": 2, "mismatched": 1}
    assert said[0] == "t: 1 / 2 rows checked, 0 mismatched so far"
    assert said[1].startswith("t: 2 / 2 rows checked, 1 mismatched so far, first: r2.lot t='not b' lines='b'")
    assert copied_rows(engine) == []
    with Session(bind=engine) as db:
        assert db.execute(select(lines.AuditBatch.__table__.c.work_kind)).scalars().all() == []


def shown(engine, row_id):
    with Session(bind=engine) as db:
        t = lines.current_table(db, "t", CFG)
        lot = db.execute(select(t.c.lot).where(t.c.row_id == row_id)).scalar_one()
        return lot, lines.won_by_of(db, "t", [row_id]).get(row_id, {})


def copy_audits(engine):
    with Session(bind=engine) as db:
        ab = lines.AuditBatch.__table__
        return db.execute(select(func.count()).select_from(ab).where(ab.c.work_kind == "copy")).scalar()


@pytest.mark.parametrize("page", [1, 2])
def test_a_cell_whose_lines_do_not_give_t_is_recorded_and_its_page_lands(page, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    engine, said = build("not b"), []
    out = script.copy_table(engine, "t", CFG, page, say=said.append)
    assert out["mismatched"] == 1 and copied_rows(engine) == ["r1", "r2"] and copy_audits(engine) == 1
    with open(out["record"], encoding="utf-8") as f:
        assert f.read().splitlines() == ["table,row_id,column,t_value,lines_value", "t,r2,lot,not b,b"]
    assert "this run 1 · the file now holds 1 mismatched cell(s)" in said[-1] and "--rows %s" % out["record"] in said[-1]
    lot, won_by = shown(engine, "r2")
    assert lot == "not b" and "lot" not in won_by          # t shows its value; no line is named its winner
    assert "lot" in shown(engine, "r1")[1]


def test_a_records_rows_copied_again_after_t_is_fixed_match_and_r1_is_untouched(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    engine, said = build("not b"), []
    out = script.copy_table(engine, "t", CFG, 1, say=said.append)
    r1_line = shown(engine, "r1")[1]["lot"]
    with engine.begin() as conn:
        conn.execute(text("UPDATE t SET lot = 'b' WHERE row_id = 'r2'"))
    again = script.copy_table(engine, "t", CFG, 1, say=said.append, rows=script.recorded_rows(out["record"])["t"])
    assert again == {"table": "t", "again": 1, "copied": 1, "mismatched": 0, "record": None}
    assert copied_rows(engine) == ["r1", "r2"] and copy_audits(engine) == 1     # one copy line a row, one audit row
    assert shown(engine, "r1")[1]["lot"] == r1_line and "lot" in shown(engine, "r2")[1]
    assert said[-1].startswith("t: 1 row(s) copied again - 1 copy line(s) taken out") and "every cell matches" in said[-1]
