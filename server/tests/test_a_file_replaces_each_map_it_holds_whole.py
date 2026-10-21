# -*- coding: utf-8 -*-
"""Lead 59b020ca2 (owner 10-20 «ㄱ, 맵키랑 같아»): a table whose table_config sets `allow_replace_map` (the chain rule's
word, widened to files) has each map a file holds - its `map_key_columns` values - replaced whole by the file's rows,
through the chain's door: a replace_map batch per map -> apply_batch_updates -> the purge and its diff. A map the
file does not hold is untouched; a row whose map key is blank refuses the file before anything is written; without
the cell a file is an upsert, as before.

  file 1 = map A 10 rows · map B 5 rows    file 2 = map A 7 rows    ->  A 7 (3 deleted: event · history) · B 5
and the lines say it (총괄 10-21, 소유자 「로그 띄워 지워진 것」): the map's line its written and removed rows with the
removed dies' keys inside the map, the file's line its maps replaced and rows deleted.
"""
import logging
import os
import re
import sys

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from conftest import retire_dynamic_model                  # noqa: E402
from database.database import Base                         # noqa: E402
from database import crud, models                          # noqa: E402

T = "zz_file_map_replace"
REPLACE = {"business_key": "die_key", "composite_key_source": ["map_id", "die_no"], "composite_key_separator": "_",
           "map_key_columns": ["map_id"], "allow_replace_map": True,
           "column_types": {"die_key": "string", "map_id": "string", "die_no": "number", "v": "string"}}
UPSERT = {key: value for key, value in REPLACE.items() if key != "allow_replace_map"}


def _csv(*maps):
    return "map_id,die_no,v\n" + "".join("%s,%d,%s\n" % (map_id, n, value)
                                         for map_id, count, value in maps for n in range(1, count + 1))


FILE_1 = _csv(("A", 10, "a1"), ("B", 5, "b1"))
FILE_2 = _csv(("A", 7, "a2"))


@pytest.fixture(name="load")
def fixture_load(pg_engine, monkeypatch, tmp_path):
    from parsers import directory_watcher as dw
    from parsers.std_parser import parse_std_file

    saved = dict(crud.TABLE_CONFIG)
    retire_dynamic_model(T)
    models.init_dynamic_models({T: REPLACE})

    def clean():
        with pg_engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS "%s"' % T))
            for side in ("cell_sources", "cell_overwrites", "database_outbox", "audit_logs"):
                conn.execute(text("DELETE FROM %s WHERE table_name = :t" % side), {"t": T})

    clean()
    Base.metadata.create_all(bind=pg_engine, tables=[models.DYNAMIC_TABLES[T].__table__])
    Session = sessionmaker(bind=pg_engine)
    monkeypatch.setattr(dw, "SessionLocal", Session)
    monkeypatch.setattr(dw.heartbeat, "beat", lambda *a, **k: None)
    handler = dw.IngestionHandler.__new__(dw.IngestionHandler)
    handler.scripts_path = ""
    handler.on_progress_callback = None
    handler.on_refresh_callback = None

    def load(csv, config=REPLACE, name="maps.csv"):
        path = tmp_path / name
        path.write_text(csv, encoding="utf-8")
        crud.TABLE_CONFIG[T] = config
        rows, total, skipped = parse_std_file(str(path), config, T)
        handler._send_to_upsert(rows, uploader="t", filename=path.name, t_name=T, total_rows=total,
                                table_info=config, checkpoint=None, skipped_no_key=skipped)

    def rows():
        with pg_engine.connect() as conn:
            return conn.execute(text('SELECT map_id, die_no, v, row_id FROM "%s" ORDER BY map_id, die_no' % T)).all()

    try:
        yield load, rows, pg_engine
    finally:
        clean()
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        retire_dynamic_model(T)


def _shape(rows):
    return {(map_id, value): sum(1 for r in rows if (r[0], r[2]) == (map_id, value)) for map_id, _n, value, _id in rows}


@pytest.mark.pg
def test_a_file_replaces_the_maps_it_holds_and_leaves_the_others(load, caplog):
    load_file, rows, engine = load
    with caplog.at_level(logging.INFO):
        load_file(FILE_1)
    assert " · replaced 2 map(s), deleted 0 row(s)" in caplog.text, caplog.text[-2000:]
    before = rows()
    assert _shape(before) == {("A", "a1"): 10, ("B", "b1"): 5}, before                        # canary
    gone = {r[3] for r in before if r[0] == "A" and r[1] > 7}
    kept = {r[3] for r in before if r[0] == "A" and r[1] <= 7}
    caplog.clear()
    with caplog.at_level(logging.INFO):
        load_file(FILE_2, name="maps2.csv")
    [removed] = re.findall(r"\[Map Diff\] Table: 'zz_file_map_replace' .*Written: 7 \| Removed: 3 \((.*)\)", caplog.text)
    assert sorted(removed.split(", ")) == ["die_no=10", "die_no=8", "die_no=9"], removed
    assert " · replaced 1 map(s), deleted 3 row(s)" in caplog.text, caplog.text[-2000:]
    after = rows()
    assert _shape(after) == {("A", "a2"): 7, ("B", "b1"): 5}, after
    assert {r[3] for r in after if r[0] == "A"} == kept, "the 7 dies written again keep their rows"
    with engine.connect() as conn:
        events = conn.execute(text("SELECT payload FROM database_outbox WHERE table_name = :t AND event_type = "
                                   "'DELETE'"), {"t": T}).all()
        said = {row_id for (payload,) in events for row_id in (payload.get("row_ids") or [payload.get("row_id")])}
        history = conn.execute(text("SELECT count(*) FROM audit_logs WHERE table_name = :t AND column_name = :c "
                                    "AND row_id = ANY(:ids)"),
                               {"t": T, "c": crud.ROW_DELETION_COLUMN, "ids": list(gone)}).scalar()
    assert gone <= said, (gone, said)
    assert history == 3


@pytest.mark.pg
def test_a_row_without_its_map_key_refuses_the_file_and_nothing_is_deleted(load):
    load_file, rows, _engine = load
    load_file(FILE_1)
    before = rows()
    with pytest.raises(crud.CellRefused) as refused:            # the parser skips it - the key is blank
        load_file("map_id,die_no,v\nA,1,x\n,2,y\nA,3,z\n", name="blank.csv")
    assert "map_id" in str(refused.value) and "1 row(s) had a blank key" in str(refused.value), str(refused.value)
    assert rows() == before


def test_a_row_reaching_the_write_without_its_map_key_names_its_file_row():
    """A parser that hands the row over (a plugin's rows): refused at the write, by the file's row."""
    from parsers import directory_watcher as dw

    rows = [{"map_id": "A", "die_no": 1}, {"map_id": " ", "die_no": 2}]
    with pytest.raises(crud.CellRefused) as refused:
        dw.IngestionHandler._map_batches(T, rows, ["map_id"], {"map_id": "map_id", "die_no": "die_no"})
    assert refused.value.row == 2 and "map_id" in str(refused.value), str(refused.value)


@pytest.mark.pg
def test_a_map_purged_whole_says_its_rows_by_id(load, caplog):
    """A map table with no composite key is purged, not diffed: its line names the deleted rows by row_id (no key
    inside the map to read), the first five and «…»."""
    load_file, rows, _engine = load
    purge = {key: value for key, value in REPLACE.items() if key != "composite_key_source"}
    load_file("die_key,map_id,die_no,v\n" + "".join("A_%d,A,%d,a1\n" % (n, n) for n in range(1, 8)), config=purge)
    ids = sorted(r[3] for r in rows())
    caplog.clear()
    with caplog.at_level(logging.INFO):
        load_file("die_key,map_id,die_no,v\nA_1,A,1,a2\n", config=purge, name="maps2.csv")
    [said] = re.findall(r"\[Map Replace Executed\] Table: 'zz_file_map_replace' .*Purged Old Rows: 7 \((.*)\) \|",
                        caplog.text)
    assert said.endswith(" …") and len(said[:-2].split(", ")) == 5 and set(said[:-2].split(", ")) <= set(ids), said
    assert " · replaced 1 map(s), deleted 7 row(s)" in caplog.text, caplog.text[-2000:]


@pytest.mark.pg
def test_without_the_cell_a_file_is_an_upsert_as_before(load):
    load_file, rows, _engine = load
    load_file(FILE_1, config=UPSERT)
    load_file(FILE_2, config=UPSERT, name="maps2.csv")
    assert _shape(rows()) == {("A", "a2"): 7, ("A", "a1"): 3, ("B", "b1"): 5}


def test_the_cell_on_a_table_without_map_key_columns_is_refused_where_the_sources_load(tmp_path):
    from parsers import directory_watcher as dw

    table = {key: value for key, value in REPLACE.items() if key != "map_key_columns"}
    specs, errors = dw.validate_external_source_specs(
        {"external_sources": [{"path": str(tmp_path / "share"), "table_name": T, "parser": "std"}]},
        {T: table}, str(tmp_path / "workspace"))
    assert specs == [] and len(errors) == 1 and "allow_replace_map" in errors[0] \
        and "map_key_columns" in errors[0], errors
    with pytest.raises(ValueError, match="declares no map_key_columns"):
        crud.replace_map_columns(T, table)
    with pytest.raises(ValueError, match="must be true or false"):
        crud.replace_map_columns(T, dict(REPLACE, allow_replace_map="yes"))
    assert crud.replace_map_columns(T, UPSERT) is None


def test_the_maps_are_met_by_the_one_key_spelling(monkeypatch):
    """«1» and «1.0» on a number map key are one map (crud.key_part)."""
    from parsers import directory_watcher as dw

    table = dict(REPLACE, column_types=dict(REPLACE["column_types"], map_id="number"))
    monkeypatch.setitem(crud.TABLE_CONFIG, T, table)
    rows = [{"map_id": "1", "die_no": 1}, {"map_id": "2", "die_no": 1}, {"map_id": "1.0", "die_no": 2}]
    batches = dw.IngestionHandler._map_batches(T, rows, ["map_id"], {"map_id": "map_id", "die_no": "die_no"})
    assert [[file_row for file_row, _row in batch] for batch in batches] == [[1, 3], [2]]
