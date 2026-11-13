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
from database.models import CellOverwrite, CellSource, sql_type_of
from scripts import copy_layers_to_lines as script

CFG = {"column_types": {"lot": "string"}}
T1 = datetime(2026, 11, 1, 9, tzinfo=timezone.utc)


def build(t_lot_r2):
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    for model in (lines.LineColumn, lines.AuditBatch, lines.LineSource, CellOverwrite, CellSource):
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
    assert "1 cell(s) do not match" in said[-1] and "--rows %s" % out["record"] in said[-1]
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
