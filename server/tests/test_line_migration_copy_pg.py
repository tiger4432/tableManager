"""line_migration.copy_page on PostgreSQL (scratch schema): JSONB layer values, timestamptz and bigint bits copy
as they are - the merge over the copied lines gives what t shows."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import MetaData, Table, text
from sqlalchemy.orm import sessionmaker

from database import line_migration, lines
from database.models import CellSource, sql_type_of

CFG = {"column_types": {"lot": "string", "qty": "number"}}
NAME = "cp_t"
T1, T2 = datetime(2026, 11, 1, 9, tzinfo=timezone.utc), datetime(2026, 11, 2, 9, tzinfo=timezone.utc)


@pytest.fixture()
def db(pg_engine):
    session = sessionmaker(bind=pg_engine)()
    Table(NAME, MetaData(), *lines._data_columns(CFG, sql_type_of, row_id_key=True)).create(session.connection())
    session.execute(text(f'CREATE UNIQUE INDEX "uq_bk_{NAME}" ON "{NAME}" (business_key_val)'))
    session.execute(text(f"INSERT INTO {NAME} (row_id, business_key_val, lot, qty) VALUES "
                         "('r1', 'k1', 'u', 5), ('r2', 'k2', 'x', NULL)"))
    for row_id, col, source, value, at in [("r1", "lot", "user", "u", T1), ("r1", "lot", "fileA", "a", T2),
                                           ("r1", "qty", "fileA", 5, T2), ("r2", "lot", "fileA", "x", T1)]:
        session.execute(CellSource.__table__.insert().values(table_name=NAME, row_id=row_id, column_name=col,
                                                             source_name=source, value=value,
                                                             ingested_at=at, updated_by="seed"))
    lines.ensure_line_table(session, NAME, CFG)
    session.commit()
    yield session
    session.rollback()
    lines.drop_line_table(session, NAME)
    session.execute(text(f'DROP TABLE IF EXISTS "{NAME}"'))
    for table in ("cell_sources", "audit_batches", "line_columns", "file_ingestion_checkpoints"):
        session.execute(text(f"DELETE FROM {table} WHERE table_name = '{NAME}'"))
    session.commit()
    session.close()


def test_copied_lines_merge_to_what_t_shows_on_pg(db):
    after = None
    while True:
        _n, after = line_migration.copy_page(db, NAME, CFG, after, 1, transaction_id="tx-copy")
        if after is None:
            break
    db.commit()
    merged = lines.merge(db, NAME, CFG, ["r1", "r2"])
    assert merged["r1"]["lot"][0] == "u" and merged["r1"]["qty"][0] == 5 and merged["r2"]["lot"][0] == "x"
    won = lines.won_by_of(db, NAME, ["r1"])["r1"]
    assert set(won) == {"lot", "qty"}
    with pytest.raises(line_migration.AlreadyCopied, match="already copied, 3 lines"):
        line_migration.copy_page(db, NAME, CFG, None, 1, transaction_id="tx-again")


@pytest.mark.parametrize("stored, line, won", [(1.0, "1", False), ("1.0", "1.0", True)])
def test_a_text_cell_copies_what_todays_write_would_store_on_pg(db, stored, line, won):
    """JSONB keeps 1.0 a float (sqlite reads it back as 1): the copy runs the write's cast, so a text column's JSON
    1.0 is «1» and a text «1.0» stays (lead 11-11). t shows «1.0» as PostgreSQL wrote it, so won_by names the line
    only where it says what t shows - no «lot» key is the state the notation retro reads (A 95b58102c)."""
    from sqlalchemy import select

    db.execute(text(f"UPDATE {NAME} SET lot = '1.0' WHERE row_id = 'r2'"))
    db.execute(CellSource.__table__.insert().values(table_name=NAME, row_id="r2", column_name="lot",
                                                    source_name="fileN", value=stored,
                                                    ingested_at=T2, updated_by="seed"))
    line_migration.copy_page(db, NAME, CFG, None, 10, transaction_id="tx-copy")
    lt = lines.shape(db, NAME, CFG)["lines"]
    line_id, said = db.execute(select(lt.c.line_id, lt.c[lines.value_column("lot")])
                               .where(lt.c.row_id == "r2", lt.c.source_name == "fileN")).one()
    assert said == line
    won_by = lines.won_by_of(db, NAME, ["r2"]).get("r2", {})
    assert (won_by.get("lot") == line_id) if won else ("lot" not in won_by)


def test_verify_lists_a_copied_row_the_old_release_wrote_and_rows_brings_it_to_0_on_pg(db, pg_engine, tmp_path,
                                                                                         monkeypatch):
    """--verify on PostgreSQL, where won_by is a bigint array (lead 11-14): after the copy nothing is listed; the old
    release writing r2 the old way (a layer and t) lists that one cell, and --rows brings it to 0."""
    import csv

    from scripts import copy_layers_to_lines as script

    monkeypatch.chdir(tmp_path)
    script.copy_table(pg_engine, NAME, CFG, 1000, say=lambda line: None)
    said = []
    assert script.verify_table(pg_engine, NAME, CFG, 2, say=said.append)["cells"] == 0, said
    assert said == [f"{NAME}: every cell matches its winning line (3 compared)"], said     # canary: each cell compared
    db.execute(CellSource.__table__.insert().values(table_name=NAME, row_id="r2", column_name="lot",
                                                    source_name="fileB", value="new2",
                                                    ingested_at=datetime(2026, 11, 14, 15, tzinfo=timezone.utc),
                                                    updated_by="old release"))
    db.execute(text(f"UPDATE {NAME} SET lot = 'new2' WHERE row_id = 'r2'"))
    db.commit()

    out = script.verify_table(pg_engine, NAME, CFG, 2, say=said.append)
    with open(out["record"], newline="", encoding="utf-8") as f:
        listed = [tuple(r.values()) for r in csv.DictReader(f)]
    assert listed == [(NAME, "r2", "lot", "new2", "x")], listed
    assert script.recorded_rows(out["record"]) == {NAME: ["r2"]}
    script.copy_table(pg_engine, NAME, CFG, 1000, say=lambda line: None, rows=["r2"])
    assert script.verify_table(pg_engine, NAME, CFG, 2, say=said.append)["cells"] == 0, said[-1]
