# -*- coding: utf-8 -*-
"""The checklist's progress (소유자 10-23 「몇 개 중 몇 개 읽고 있는지」, 총괄 07a16f238): GET /admin/file-ingestion/tables
says per table, per source, files read / total / left by state - a file being its newest row (`newest_of_its_file`),
counted by the whole counter, not by the request.

  board                                         total   read   left
  read, re-read before (an older row too)         1      1      -
  unchecked (SUCCESS, no stamp)                   1      -      SUCCESS
  failed and let go                               1      -      FAILED
  waiting (handed to the retry door)              1      -      PENDING_RETRY
  being read                                      1      -      PROCESSING
  read again under another spelling of its path   1      1      -      (path_key: one file)
  the same path, another table                    its own table's count
And with a real watcher: «Read all again» then the sweeps - `left` only goes down, to 0, the total never moves.
"""
import os
import sqlite3
import time
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database import models
from ingestion import checkpoint, reread
from tests.test_an_external_source_reads_as_raws_does import TABLE, _csvs, _run, _settings

STAMP = {"file_mtime": datetime(2026, 10, 23), "file_size": 10}


def _log(db, table, path, status, source="raws", stamped=False):
    db.add(models.FileIngestionLog(filename=os.path.basename(path), filepath=path, table_name=table, status=status,
                                   source=source, retry_count=0, **(STAMP if stamped else {})))
    db.flush()


def _newest_per_file(db):
    """The same answer, in Python over every row: the highest id of each (table, folded path)."""
    newest = {}
    for row in db.query(models.FileIngestionLog).order_by(models.FileIngestionLog.id):
        newest[(row.table_name, row.filepath.replace("/", "\\").lower())] = row
    said = {}
    for row in newest.values():
        entry = said.setdefault((row.table_name, row.source), [0, 0, {}])
        entry[0] += 1
        if row.file_mtime is not None:
            entry[1] += 1
        else:
            entry[2][row.status] = entry[2].get(row.status, 0) + 1
    return said


def _progress(client):
    for _ in range(50):
        said = client.get("/admin/file-ingestion/tables").json()
        if not said["progress"]["counting"]:
            return said
        time.sleep(0.1)
    raise AssertionError(said)


def test_the_tables_say_read_total_and_left_per_source(client, db_session, monkeypatch):
    from parsers import directory_watcher

    monkeypatch.setattr(directory_watcher, "count_recount_seconds", lambda settings=None: 0.0)
    _log(db_session, "insp", r"C:\raws\insp\a.csv", "SUCCESS")                    # read before, then again
    _log(db_session, "insp", r"C:\raws\insp\a.csv", "SUCCESS", stamped=True)
    _log(db_session, "insp", r"C:\raws\insp\b.csv", "SUCCESS")                    # unchecked
    _log(db_session, "insp", r"C:\raws\insp\c.csv", "FAILED")
    _log(db_session, "insp", r"C:\raws\insp\d.csv", "PENDING_RETRY")
    _log(db_session, "insp", r"C:\raws\insp\e.csv", "PROCESSING")
    _log(db_session, "insp", r"\\share\lots\f.csv", "FAILED", source=r"\\share\lots")
    _log(db_session, "insp", "//share/LOTS/F.csv", "SUCCESS", source=r"\\share\lots", stamped=True)
    _log(db_session, "voids", r"C:\raws\insp\a.csv", "PENDING_RETRY")
    db_session.commit()

    said = _progress(client)
    tables = {t["table_name"]: t for t in said["data"]}
    got = {(table, s["source"]): [s["total"], s["read"], s["left_by_status"]]
           for table, t in tables.items() for s in t["sources"]}
    assert got == {
        ("insp", "raws"): [5, 1, {"SUCCESS": 1, "FAILED": 1, "PENDING_RETRY": 1, "PROCESSING": 1}],
        ("insp", r"\\share\lots"): [1, 1, {}],
        ("voids", "raws"): [1, 0, {"PENDING_RETRY": 1}]}
    assert {k: [v[0], v[1], v[2]] for k, v in _newest_per_file(db_session).items()} == got
    assert all(s["left"] == s["total"] - s["read"] for t in said["data"] for s in t["sources"])
    assert said["progress"]["counted_at"] and said["progress"]["failed"] is None
    assert (tables["insp"]["total"], tables["insp"]["by_status"]["SUCCESS"]) == (8, 4)   # rows, as before

    # a file read since: counted again on the next ask past its pacing
    _log(db_session, "insp", r"C:\raws\insp\b.csv", "SUCCESS", stamped=True)
    db_session.commit()
    raws = next(s for s in {t["table_name"]: t for t in _progress(client)["data"]}["insp"]["sources"]
                if s["source"] == "raws")
    assert (raws["total"], raws["read"], raws["left"]) == (5, 2, 3)


def test_a_real_watcher_reading_again_only_brings_left_down(tmp_path):
    data = tmp_path / "data"
    (data / "config").mkdir(parents=True)
    share = str(tmp_path / "share")
    _csvs(share, 4, "S")
    _settings(str(data), {"ta": TABLE}, [("ta", share, "*.csv")])
    db = tmp_path / "box.db"
    engine = create_engine("sqlite:///" + db.as_posix())

    def stamped(c):
        return c.execute("SELECT count(*) FROM file_ingestion_logs WHERE file_mtime IS NOT NULL").fetchone()[0] >= 4

    _run(tmp_path, db, stamped)
    with Session(engine) as s:
        assert [(p["total"], p["read"]) for p in checkpoint.read_progress(s)] == [(4, 4)]
        assert reread.uncheck(s, table="ta") == 4                                   # «Read all again»
        assert [(p["total"], p["read"], p["left"]) for p in checkpoint.read_progress(s)] == [(4, 0, 4)]

    seen = []

    def read_again(c):
        with Session(engine) as s:
            seen.extend((p["total"], p["left"]) for p in checkpoint.read_progress(s))
        return seen and seen[-1] == (4, 0)

    _run(tmp_path, db, read_again)
    with sqlite3.connect(str(db)) as c:
        rows = c.execute("SELECT count(*) FROM file_ingestion_logs").fetchone()[0]
    assert rows > 4, rows                                          # the re-reads wrote rows; the count is per file
    assert seen[-1] == (4, 0), seen
    assert {total for total, _left in seen} == {4}, seen
    lefts = [left for _total, left in seen]
    assert lefts == sorted(lefts, reverse=True) and len(set(lefts)) > 2, seen
    engine.dispose()
