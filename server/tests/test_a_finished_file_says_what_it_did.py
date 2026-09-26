# -*- coding: utf-8 -*-
"""A finished file writes ONE line - the same line whichever lane ran it - that says what the
file did: rows, time, rows per minute, how long it waited, new / changed / unchanged rows,
cells changed, the rows each side table took, where the time went (소유자 2026-09-26
「헤비 레인 쓰기 속도 느린 거는 로그는 추가해 봐」 · 「(ㄱ + 넓힌 ㄴ) ㅇㅇ»: two files of one
table with the same columns, one slow - side by side, the lines show what differs).

The chunk line names the four side-table writes apart, each with its seconds and its rows.
Every number comes from what the write already holds; no query is added to count it.
"""
import os
import re
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
for path in (server_dir, os.path.join(server_dir, "parsers")):
    if path not in sys.path:
        sys.path.insert(0, path)

import directory_watcher                                                   # noqa: E402
from conftest import retire_dynamic_model                                  # noqa: E402
from database import crud, models                                          # noqa: E402
from database.database import Base                                         # noqa: E402
from directory_watcher import IngestionHandler                             # noqa: E402
from test_heavy_lane import FakeLane                                       # noqa: E402

TABLE = "file_line_parts"
INFO = {"business_key": "part_no",
        "column_types": {"part_no": "string", "category": "string", "stock_qty": "string"},
        "display_columns": ["part_no", "category", "stock_qty"]}
#: The four side-table writers - each is wrapped to count the rows it was handed.
WRITERS = {"audit logs": "bulk_insert_audit_logs", "cell sources": "bulk_upsert_cell_sources",
           "cell overwrites": "bulk_upsert_cell_overwrites",
           "overwrite deletes": "bulk_delete_cell_overwrites"}
#: One source for the seed and the file: the 8-hex tail is not part of the source name.
SEED_NAME, FILE_NAME = "parts_aaaaaaa1.csv", "parts_bbbbbbb2.csv"

SEED = [("P-1", "Cap", "1"), ("P-2", "Cap", "2"), ("P-3", "Cap", "3")]
#: shape -> (seed rows, file rows, new, changed, unchanged, cells changed)
SHAPES = {
    "all new": ([], SEED, 3, 0, 0, 9),
    "all changed": (SEED, [(k, "Res", q) for k, _c, q in SEED], 0, 3, 0, 3),
    "all unchanged": (SEED, list(reversed(SEED)), 0, 0, 3, 0),
    "mixed": (SEED, [("P-1", "Cap", "1"), ("P-2", "Res", "2"), ("P-4", "Ind", "4"),
                     ("P-5", "Ind", "5")], 2, 1, 1, 7),
}
LINE = re.compile(
    r"FILE (?P<file>\S+): (?P<rows>\d+) row\(s\) in [\d.]+ s \(\d+ rows/min\) · (?P<lane>\w+) lane"
    r" · waited (?P<waited>[\d.]+ s \((?P<span>[^)]*)\)|not measured) · sent: new (?P<new>\d+)"
    r" · changed "
    r"(?P<changed>\d+) · unchanged (?P<unchanged>\d+) · cells changed (?P<cells>\d+)"
    r" · side-table rows (?P<side>\d+) · STAGES.* · INSIDE THE WRITE(?P<write>.*) · DB wait")


@pytest.fixture(name="env")
def fixture_env(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.init_dynamic_models({TABLE: dict(INFO)})
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, dict(INFO))
    Base.metadata.create_all(bind=engine)
    models.ensure_ingestion_checkpoint_table(engine)
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: {TABLE: INFO})
    monkeypatch.setattr(directory_watcher, "SessionLocal", session_factory)
    monkeypatch.setattr(directory_watcher, "INGESTION_SETTINGS_PATH",
                        str(tmp_path / "ingestion_settings.json"))
    written = {name: 0 for name in WRITERS}
    for name, attr in WRITERS.items():
        real = getattr(crud, attr)

        def counting(db, rows, _real=real, _name=name):
            written[_name] += len(rows)
            return _real(db, rows)
        monkeypatch.setattr(crud, attr, counting)
    yield tmp_path, written
    engine.dispose()
    retire_dynamic_model(TABLE)


def _drop(handler, workspace, name, rows, lane, monkeypatch):
    path = os.path.join(workspace, "raws", name)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("part_no,category,stock_qty\n" + "".join("%s,%s,%s\n" % r for r in rows))
    monkeypatch.setattr(directory_watcher, "get_heavy_threshold_bytes",
                        lambda: 1 if lane == "heavy" else 10 ** 9)
    handler._handle_event(path)
    handler.heavy_lane.run_all()


@pytest.mark.parametrize("shape", sorted(SHAPES))
@pytest.mark.parametrize("lane", ["heavy", "normal"])
def test_one_file_line_counts_what_the_file_did(env, lane, shape, monkeypatch, caplog):
    tmp_path, written = env
    workspace = str(tmp_path / "ws")
    for sub in ("raws", "archives", "err"):
        os.makedirs(os.path.join(workspace, sub))
    handler = IngestionHandler(workspace, None, os.path.join(workspace, "archives"),
                               default_table_name=TABLE, heavy_lane=FakeLane())
    seed, rows, new, changed, unchanged, cells = SHAPES[shape]
    if seed:
        _drop(handler, workspace, SEED_NAME, seed, lane, monkeypatch)
    for name in written:
        written[name] = 0
    caplog.clear()

    with caplog.at_level("INFO"):
        _drop(handler, workspace, FILE_NAME, rows, lane, monkeypatch)

    lines = [r.getMessage() for r in caplog.records if " FILE %s:" % FILE_NAME in r.getMessage()]
    assert len(lines) == 1, lines
    got = LINE.search(lines[0])
    assert got, lines[0]
    assert got["lane"] == lane and got["waited"] != "not measured"
    assert got["span"] == {"heavy": "queue + table lock", "normal": "table lock"}[lane]
    assert (int(got["rows"]), int(got["new"]), int(got["changed"]), int(got["unchanged"]),
            int(got["cells"])) == (len(rows), new, changed, unchanged, cells)
    # every side table's rows on the line are the rows its writer was handed
    for name, n in written.items():
        assert " %s " % name in got["write"] and "/ %d rows" % n in got["write"].split(
            " %s " % name, 1)[1].split(" · ", 1)[0], (name, n, got["write"])
    assert int(got["side"]) == sum(written.values())
    if shape == "all unchanged":
        assert sum(written.values()) == 0, "an unchanged file writes no side table"
    if shape == "all new":
        assert int(got["changed"]) == 0


def test_reading_the_new_rows_asks_the_database_nothing(env):
    """「새 질의 0」, counted: the ids are read from rows still in memory after the write."""
    from sqlalchemy import event

    from database import schemas

    db = directory_watcher.SessionLocal()
    try:
        results, _cells, _logs, _deleted = crud.apply_batch_updates(
            db, TABLE, schemas.GeneralUpdateBatch(updates=[
                schemas.GeneralUpdateItem(updates={"part_no": k, "category": c, "stock_qty": q},
                                          source_name="seed", updated_by="test")
                for k, c, q in SEED]))
        statements = []
        listener = lambda *args, **kw: statements.append(args[2])      # noqa: E731
        event.listen(db.get_bind(), "before_cursor_execute", listener)
        try:
            new_ids = directory_watcher._new_row_ids(TABLE, results)
        finally:
            event.remove(db.get_bind(), "before_cursor_execute", listener)
    finally:
        db.rollback()
        db.close()

    assert len(new_ids) == len(SEED)
    assert statements == []


def test_a_tally_that_breaks_silences_the_line_and_not_the_file(env, monkeypatch, caplog):
    """🔴 The observer may not kill what it observes (the first cut read a row after the
    commit and failed the file). Forced here: the tally raises, the file still lands."""
    tmp_path, _written = env
    workspace = str(tmp_path / "ws")
    for sub in ("raws", "archives", "err"):
        os.makedirs(os.path.join(workspace, sub))
    handler = IngestionHandler(workspace, None, os.path.join(workspace, "archives"),
                               default_table_name=TABLE, heavy_lane=FakeLane())

    def boom(*args, **kwargs):
        raise RuntimeError("boom")
    monkeypatch.setattr(directory_watcher._FileTally, "_add_chunk", boom)

    with caplog.at_level("INFO"):
        _drop(handler, workspace, FILE_NAME, SEED, "normal", monkeypatch)

    messages = [r.getMessage() for r in caplog.records]
    assert sum("stops counting (RuntimeError: boom)" in m for m in messages) == 1
    assert any("FILE %s: not counted (RuntimeError: boom)" % FILE_NAME in m for m in messages)
    db = directory_watcher.SessionLocal()
    try:
        assert db.query(models.DYNAMIC_TABLES[TABLE]).count() == len(SEED), "the file landed"
    finally:
        db.close()


def test_the_chunk_line_names_the_four_side_writes_apart(env, monkeypatch, caplog):
    tmp_path, written = env
    workspace = str(tmp_path / "ws")
    for sub in ("raws", "archives", "err"):
        os.makedirs(os.path.join(workspace, sub))
    handler = IngestionHandler(workspace, None, os.path.join(workspace, "archives"),
                               default_table_name=TABLE, heavy_lane=FakeLane())

    with caplog.at_level("INFO"):
        _drop(handler, workspace, FILE_NAME, SEED, "normal", monkeypatch)

    [chunk] = [r.getMessage() for r in caplog.records if " chunk 1:" in r.getMessage()]
    for name in WRITERS:
        assert re.search(r" · %s [\d.]+ s / %d rows" % (name, written[name]), chunk), chunk
    assert "side tables" not in chunk
    assert re.search(r" · row build [\d.]+ s / 9 cells changed", chunk), chunk
