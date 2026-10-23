# -*- coding: utf-8 -*-
"""Every file the watcher reads says why, by one word (총괄 64b264610, 소유자 10-23 「죄다 뉴 파일이래」 - the line said
«New file detected» for a changed or unchecked file too).

  seat                          word                     from
  the checklist (every sweep,   new · changed ·          `checkpoint.checked(words=)` - the file's newest row: none ·
  the event, the tree walk)     unstamped                another stamp · no stamp
  the retry door                read again · retry ·     `reread.why_handed` - the mark's state before it was handed:
                                read now                 SUCCESS (Read all again) · FAILED · stood by the re-read
And with a real watcher: the line «File to read (<word>): <path>», the sweep line's counts by word, and each external
source's sweep as a heartbeat lap (state · looked · dispatched · why) - the file page's line per store.
"""
import json
import os
import re

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database import models
from ingestion import checkpoint, reread
from tests.test_an_external_source_reads_as_raws_does import TABLE, _csvs, _run, _settings


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return path


def _row(db, table, path, status="SUCCESS", file_stat=None):
    """The file's checklist row, as a read leaves it."""
    row = checkpoint.note_file(db, table, path, status=status, source="raws",
                               file_mtime=file_stat[0] if file_stat else None,
                               file_size=file_stat[1] if file_stat else None)
    db.commit()
    return row


def test_the_checklist_says_why_it_reads(db_session, tmp_path):
    read, changed, unchecked, new = (_write(str(tmp_path / n), "lot\nL%s\n" % n) for n in ("a", "b", "c", "d"))
    stat = {p: checkpoint.read_file_stat(p) for p in (read, changed, unchecked, new)}
    _row(db_session, "ta", read, file_stat=stat[read])
    _row(db_session, "ta", changed, file_stat=(stat[changed][0], stat[changed][1] + 1))     # read when it was other
    _row(db_session, "ta", unchecked)
    _row(db_session, "tb", new, file_stat=stat[new])                                       # another table's
    words = {}
    assert checkpoint.checked(db_session, "ta", list(stat.items()), words=words) == {read: "SUCCESS"}
    assert words == {changed: checkpoint.WHY_CHANGED, unchecked: checkpoint.WHY_UNSTAMPED, new: checkpoint.WHY_NEW}
    assert checkpoint.checked(db_session, "ta", list(stat.items())) == {read: "SUCCESS"}       # no words asked: as ever


def test_the_retry_door_says_why_it_reads(db_session, tmp_path):
    was_read, failed = _row(db_session, "ta", str(tmp_path / "a.csv")), _row(db_session, "ta", str(tmp_path / "b.csv"),
                                                                              status="FAILED")
    reread.mark_for_reread(db_session, [was_read, failed])
    _logs, (stood,) = reread.stand_rows(db_session, "ta", [(None, None, str(tmp_path / "c.csv"))])
    db_session.commit()
    assert [reread.why_handed(row) for row in (was_read, failed, stood)] == [
        checkpoint.WHY_READ_AGAIN, checkpoint.WHY_RETRY, checkpoint.WHY_READ_NOW]


def test_a_real_watcher_says_why_on_its_lines_and_its_lap(tmp_path):
    data = tmp_path / "data"
    (data / "config").mkdir(parents=True)
    share = str(tmp_path / "share")
    _csvs(share, 3, "S")
    _settings(str(data), {"ta": TABLE}, [("ta", share, "*.csv")])
    db = tmp_path / "box.db"

    def stamped(n):
        return lambda c: c.execute("SELECT count(*) FROM file_ingestion_logs WHERE file_mtime IS NOT NULL").fetchone()[0] >= n

    said = _run(tmp_path, db, stamped(3))
    assert len(re.findall(r"File to read \(new\): \S+S\d\.csv", said)) == 3, said[-3000:]
    assert re.search(r"External source ta@\S+: 3 file\(s\) looked at - .* dispatched 3 \(new 3\)", said), said[-3000:]

    with open(os.path.join(share, "S0.csv"), "a", encoding="utf-8") as f:            # written again
        f.write("S0b,file\n")
    engine = create_engine("sqlite:///" + db.as_posix())
    with Session(engine) as s:
        assert reread.uncheck(s, table="ta", paths=[os.path.join(share, "S1.csv")]) == 1
    said = _run(tmp_path, db, lambda c: c.execute("SELECT count(*) FROM file_ingestion_logs").fetchone()[0] >= 5)
    assert re.search(r"File to read \(changed\): \S+S0\.csv", said) and re.search(
        r"File to read \(unstamped\): \S+S1\.csv", said), said[-3000:]
    assert re.search(r"dispatched 2 \(changed 1 · unstamped 1\)", said), said[-3000:]
    assert not re.search(r"File to read \(\w+\): \S+S2\.csv", said)
    lap = json.load(open(data / "config" / "worker_heartbeats" / "watcher.json", encoding="utf-8"))["laps"]
    (name, sweep), = [(k, v) for k, v in lap.items() if k.startswith("sweep:")]
    assert (sweep["table"], sweep["source"], sweep["state"]) == ("ta", share, "rested"), sweep
    assert sweep["looked"] == 3 and sweep["seconds"] is not None, sweep

    with Session(engine) as s:                                                           # Read all again: one file
        reread.mark_for_reread(s, s.query(models.FileChecklist).filter(
            models.FileChecklist.filepath.like("%S2.csv")).all())
    said = _run(tmp_path, db, lambda c: c.execute(
        "SELECT count(*) FROM file_checklist WHERE status = 'PENDING_RETRY'").fetchone()[0] == 0)
    assert re.search(r"File to read \(read again\): \S+S2\.csv", said), said[-3000:]
    with Session(engine) as s:                                   # every file's newest row checked again
        assert [(p["total"], p["left"]) for p in checkpoint.read_progress(s)] == [(3, 0)]
    engine.dispose()
