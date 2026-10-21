# -*- coding: utf-8 -*-
"""The checklist (소유자 10-21 「(파일, 돌려야 할 테이블) 을 키로 넣고 체크리스트 하면 되잖아」 · 「테이블 스크립트 바뀌면 그 테이블
키만 체크 해제하고」): «already read?» is one answer - a log row of the same (path, table) carrying the file's (mtime,
size) - asked by every seat through `checkpoint.checked`.

  path spelling       stored C:\\X\\a.csv, asked c:/x/a.csv                     -> checked
  stamp spelling      a read's row stamped through _file_result                  -> the same file asked again is checked
  table               the same file, another table                              -> not checked
  file changed        another size                                              -> not checked
  no stamp            a read that waited out a lock writes none                  -> not checked
  reading changed     table ta: its read rows unchecked, its failed handed; tb   -> untouched
  enabled             switching a source off and on                             -> no new reading
  the fill            off the stat a sweep took: unchanged SUCCESS stamped; failed / changed told; a path or table
                      not asked untouched; once more                             -> nothing
  a real watcher      rows from before the checklist + their files in place -> started: none read, the failed one read
                      once, the first sweep's line says the fill; a file saved again -> read; tb's plugin changed -> tb's files read again, ta's not;
                      restarted -> nothing read
"""
import http.server
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

from database import models
from ingestion import checkpoint, reread

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _write(path, text):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return str(path)


def _row(db, table, path, status="SUCCESS", file_stat=None, at=None):
    row = models.FileIngestionLog(filename=os.path.basename(path), filepath=path, table_name=table, status=status,
                                  retry_count=0, file_mtime=file_stat[0] if file_stat else None,
                                  file_size=file_stat[1] if file_stat else None)
    if at is not None:
        row.created_at = row.updated_at = at
    db.add(row)
    db.commit()
    return row


def test_a_file_is_checked_by_its_path_and_table_and_stamp(db_session, tmp_path):
    a = _write(tmp_path / "X" / "a.csv", "lot,val\nL1,v\n")
    stat = checkpoint.read_file_stat(a)
    from parsers.directory_watcher import _file_result
    result = _file_result(time.monotonic(), None, 0, {}, file_stat=stat)
    row = models.FileIngestionLog(filename="a.csv", filepath=a, table_name="ta", status="SUCCESS", retry_count=0,
                                  **result)
    db_session.add(row)
    db_session.commit()

    assert checkpoint.checked(db_session, "ta", [(a, checkpoint.read_file_stat(a))]) == {a: "SUCCESS"}
    other = a.replace("\\", "/").upper() if os.sep == "\\" else a
    assert checkpoint.checked(db_session, "ta", [(other, stat)]) == {other: "SUCCESS"}      # one spelling
    assert checkpoint.checked(db_session, "tb", [(a, stat)]) == {}                          # its own table
    assert checkpoint.checked(db_session, "ta", [(a, (stat[0], stat[1] + 1))]) == {}        # changed
    b = _write(tmp_path / "X" / "b.csv", "lot,val\nL2,v\n")
    _row(db_session, "ta", b, "FAILED")                                                     # waited out a lock
    assert checkpoint.checked(db_session, "ta", [(b, checkpoint.read_file_stat(b))]) == {}


def test_a_changed_reading_unchecks_its_own_table_in_place_only(db_session, tmp_path, monkeypatch):
    raws = tmp_path / "ta" / "raws"
    a, f, b = (_write(raws / name, "x") for name in ("a.csv", "f.csv", "b.csv"))
    moved = _write(tmp_path / "ta" / "archives" / "m.csv", "x")
    ra = _row(db_session, "ta", a, "SUCCESS", checkpoint.read_file_stat(a))
    rf = _row(db_session, "ta", f, "FAILED", checkpoint.read_file_stat(f))
    rb = _row(db_session, "tb", b, "SUCCESS", checkpoint.read_file_stat(b))
    rm = _row(db_session, "ta", moved, "SUCCESS", checkpoint.read_file_stat(moved))

    line = reread.hand_on_a_changed_reading(db_session, "ta", {"scripts\\p.py": [1, 1]}, {"scripts\\p.py": [2, 1]},
                                            folders=[str(raws)])

    db_session.expire_all()
    assert line == "[Watcher] ta: its reading changed (scripts\\p.py) - 1 read file(s) unchecked, 1 failed file(s) handed again"
    assert (ra.file_mtime, ra.file_size) == (None, None)
    assert rf.status == reread.REREAD_STATUS and rf.file_size is not None     # the retry door owns it, still checked
    assert rb.file_size is not None                                            # another table is not touched
    assert rm.file_size is not None                                            # moved: 소유자 「옮겨진 건 하지 마」


def test_named_files_are_let_go_by_the_same_uncheck(db_session, tmp_path):
    """scripts/replay_ingestion.py --apply: those (path, table) keys, in any spelling; another table's and the retry
    door's rows keep theirs."""
    a, b = _write(tmp_path / "W1" / "a.csv", "x"), _write(tmp_path / "W1" / "b.csv", "x")
    ra = _row(db_session, "ta", a, "SUCCESS", checkpoint.read_file_stat(a))
    rta = _row(db_session, "tb", a, "SUCCESS", checkpoint.read_file_stat(a))
    rb = _row(db_session, "ta", b, reread.REREAD_STATUS, checkpoint.read_file_stat(b))
    asked = [path.replace("\\", "/").upper() if os.sep == "\\" else path for path in (a, b)]

    assert reread.uncheck(db_session, table="ta", paths=asked) == 1

    db_session.expire_all()
    assert (ra.file_size, rta.file_size is not None, rb.file_size is not None) == (None, True, True)


def test_switching_a_source_off_and_on_is_no_new_reading(tmp_path):
    source = {"path": "D:/share", "table_name": "ta", "options": {"glob": "*.csv"}}
    on = reread.reading_of("ta", {}, [source], str(tmp_path))
    assert reread.reading_of("ta", {}, [dict(source, enabled=False)], str(tmp_path)) == on
    assert reread.reading_of("ta", {}, [dict(source, options={"glob": "*.txt"})], str(tmp_path)) != on


def test_the_rows_from_before_the_checklist_are_stamped_once(db_session, tmp_path):
    later = datetime.now(timezone.utc) + timedelta(seconds=5)
    root = tmp_path / "share"
    same = _write(root / "same.csv", "x")
    failed = _write(root / "failed.csv", "x")
    changed = _write(root / "changed.csv", "x")
    outside = _write(tmp_path / "elsewhere" / "o.csv", "x")
    rows = [_row(db_session, "ta", same, at=later), _row(db_session, "ta", failed, "FAILED", at=later),
            _row(db_session, "ta", changed, at=later - timedelta(days=1)),
            _row(db_session, "tb", same, at=later), _row(db_session, "ta", outside, at=later)]
    asked = [(path.replace("\\", "/").upper() if os.sep == "\\" else path, checkpoint.read_file_stat(path))
             for path in (same, failed, changed)]

    said = checkpoint.stamp_read_files(db_session, "ta", asked)

    db_session.expire_all()
    assert said == {"stamped": [rows[0].id], "failed": [rows[1].id], "changed": [rows[2].id]}
    assert [row.file_size is not None for row in rows] == [True, False, False, False, False]
    assert checkpoint.checked(db_session, "ta", [(same, checkpoint.read_file_stat(same))]) == {same: "SUCCESS"}
    assert checkpoint.stamp_read_files(db_session, "ta", asked) == {"stamped": [], "failed": [rows[1].id],
                                                                     "changed": [rows[2].id]}


# ── a real watcher ────────────────────────────────────────────────────────────────────────────────────────────────────

DRIVER = '''
import json, sys
sys.path.insert(0, "parsers")
import paths
from database.database import Base, engine
from database import models
models.init_dynamic_models(json.load(open(paths.config_path("table_config.json"), encoding="utf-8")))
Base.metadata.create_all(bind=engine)
import run_watcher
run_watcher.main()
'''
PLUGIN = '''
import csv
from pipeline_base import BasePipelineParser
class P(BasePipelineParser):
    @classmethod
    def match(cls, path):
        return True
    def parse(self, path):
        with open(path, newline="") as f:
            return [dict(r) for r in csv.DictReader(f)]
'''
TABLE = {"business_key": "lot", "column_types": {"lot": "string", "val": "string"}, "display_columns": ["lot", "val"]}


class _Stub(http.server.BaseHTTPRequestHandler):
    def _ok(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b"{}")

    do_GET = do_POST = do_PUT = _ok

    def log_message(self, *args):
        pass


def test_a_real_watcher_reads_each_file_once_and_again_only_when_asked(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    data, share_a, share_b = tmp_path / "data", tmp_path / "share_a", tmp_path / "share_b"
    (data / "config").mkdir(parents=True)
    with open(data / "config" / "table_config.json", "w", encoding="utf-8") as f:
        json.dump({"ta": TABLE, "tb": TABLE}, f)
    for table in ("ta", "tb"):
        scripts = data / "ingestion_workspace" / table / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "p.py").write_text(PLUGIN, encoding="utf-8")
        (data / "ingestion_workspace" / table / "raws").mkdir(parents=True)
    with open(data / "config" / "ingestion_settings.json", "w", encoding="utf-8") as f:
        json.dump({"external_sources": [{"path": str(share_a), "table_name": "ta", "options": {"glob": "*.csv"}},
                                        {"path": str(share_b), "table_name": "tb", "options": {"glob": "*.csv"}}]}, f)
    a1 = _write(share_a / "a1.csv", "lot,val\nA1,v\n")
    a2 = _write(share_a / "a2.csv", "lot,val\nA2,v\n")
    af = _write(share_a / "af.csv", "lot,val\nAF,v\n")
    b1 = _write(share_b / "b1.csv", "lot,val\nB1,v\n")
    _write(data / "ingestion_workspace" / "tb" / "raws" / "rb.csv", "lot,val\nRB,v\n")     # read, then moved

    # rows from before the checklist: no stamp, written after each file
    db = tmp_path / "box.db"
    engine = create_engine("sqlite:///" + db.as_posix())
    models.FileIngestionLog.__table__.create(engine)
    later = datetime.now(timezone.utc) + timedelta(seconds=5)
    with Session(engine) as session:
        for table, path, status in (("ta", a1, "SUCCESS"), ("ta", a2, "SUCCESS"), ("ta", af, "FAILED"),
                                    ("tb", b1, "SUCCESS")):
            _row(session, table, path, status, at=later)
    engine.dispose()

    api = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=api.serve_forever, daemon=True).start()
    env = dict(os.environ, ASSY_DATA_ROOT=str(data), DATABASE_URL="sqlite:///" + db.as_posix(),
               API_BASE_URL="http://127.0.0.1:%d" % api.server_address[1], NO_PROXY="127.0.0.1,localhost",
               PYTHONIOENCODING="utf-8", PYTHONPATH=SERVER_DIR, DECOUPLED="True")
    env.pop("TESTING", None)
    driver = tmp_path / "driver.py"
    driver.write_text(DRIVER, encoding="utf-8")
    log_path = tmp_path / "watcher.log"

    def start():
        log = open(log_path, "ab")
        return subprocess.Popen([sys.executable, str(driver)], cwd=SERVER_DIR, env=env, stdout=log,
                                stderr=subprocess.STDOUT), log

    def reads():
        """{(table, file name): log rows} - each read writes one."""
        with sqlite3.connect(str(db)) as c:
            rows = c.execute("SELECT table_name, filename FROM file_ingestion_logs").fetchall()
        out = {}
        for key in rows:
            out[key] = out.get(key, 0) + 1
        return out

    def said(text):
        return text in log_path.read_text(encoding="utf-8", errors="replace")

    def until(holds, watcher, seconds=60):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            assert watcher.poll() is None, log_path.read_text(encoding="utf-8", errors="replace")[-3000:]
            if holds():
                return True
            time.sleep(0.5)
        return False

    watcher, log = start()
    try:
        assert until(lambda: reads().get(("ta", "af.csv")) == 2, watcher), reads()        # the failed one, once
        assert until(lambda: said("[Watcher] read files stamped 3 · left for re-read 1 (failed 1 · changed since read 0)"),
                     watcher)
        assert until(lambda: reads().get(("tb", "rb.csv")) == 1, watcher), reads()
        time.sleep(5)
        assert reads() == {("ta", "a1.csv"): 1, ("ta", "a2.csv"): 1, ("ta", "af.csv"): 2, ("tb", "b1.csv"): 1,
                           ("tb", "rb.csv"): 1}

        _write(a1, "lot,val\nA1,changed\n")                                                 # saved again
        assert until(lambda: reads().get(("ta", "a1.csv")) == 2, watcher), reads()

        (data / "ingestion_workspace" / "tb" / "scripts" / "p.py").write_text(PLUGIN + "\n# fixed\n", encoding="utf-8")
        assert until(lambda: reads().get(("tb", "b1.csv")) == 2, watcher), reads()        # tb's file again
        time.sleep(5)
        assert reads() == {("ta", "a1.csv"): 2, ("ta", "a2.csv"): 1, ("ta", "af.csv"): 2, ("tb", "b1.csv"): 2,
                           ("tb", "rb.csv"): 1}                             # moved: not again (소유자 「옮겨진 건 하지 마」)
        with sqlite3.connect(str(db)) as c:
            stamp = c.execute("SELECT file_size FROM file_ingestion_logs WHERE filename = 'rb.csv'").fetchone()[0]
        assert stamp, "a moved file was unchecked"
        assert said("its reading changed (scripts\\p.py) - 1 read file(s) unchecked, 0 failed file(s) handed again "
                    "- 1 dispatched to be read again")
    finally:
        watcher.kill()
        watcher.wait(30)
        log.close()

    watcher, log = start()                                                                 # restarted
    try:
        assert until(lambda: said("External sweep:") or said("Started observer"), watcher)
        time.sleep(8)
        assert reads() == {("ta", "a1.csv"): 2, ("ta", "a2.csv"): 1, ("ta", "af.csv"): 2, ("tb", "b1.csv"): 2,
                           ("tb", "rb.csv"): 1}
        assert log_path.read_text(encoding="utf-8", errors="replace").count("read files stamped") == 1
    finally:
        watcher.kill()
        watcher.wait(30)
        log.close()
        api.shutdown()
