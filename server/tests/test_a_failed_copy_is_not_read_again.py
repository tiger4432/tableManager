# -*- coding: utf-8 -*-
"""총괄 b5b77495a (소유자 ㄱ) — two failed files with the same content used to push each other off
tier 1, so each watcher start re-parsed one of them and added a FAILED record. A path that already
failed and has not changed since is skipped; a new path, a file saved again, or Retry still read.
Files stay where they land (archive_processed_files: false), as on the box."""
import json
import os
import time

import pytest

from tests.test_ingestion_checkpoint import TABLE, _ingestion_logs, _write, p2_env  # noqa: F401

FAILING = "part_no,category,stock_qty\nP-1,Cap,abc\n"


@pytest.fixture
def env(p2_env):
    p2_env["settings_path"].write_text(json.dumps({"archive_processed_files": False}),
                                       encoding="utf-8")
    ws, handler = p2_env["make_handler"]()
    parsed = []
    resolve = handler._resolve_rows
    handler._resolve_rows = lambda *a, **k: (parsed.append(os.path.basename(a[0])),
                                             resolve(*a, **k))[1]

    def drop(name, age=10):
        """A file that landed `age` seconds ago."""
        path = _write(ws / "raws" / name, FAILING)
        then = time.time() - age
        os.utime(path, (then, then))
        return path

    def failed():
        return [log.filename for log in _ingestion_logs(p2_env) if log.status == "FAILED"]

    return {"handler": handler, "drop": drop, "parsed": parsed, "failed": failed, "p2": p2_env}


def test_two_failed_copies_are_not_read_again_on_restart(env):
    a, b = env["drop"]("a.csv"), env["drop"]("b.csv")
    for path in (a, b):
        env["handler"].process_with_retry(path, delay=0.01)
    assert env["failed"]() == ["a.csv", "b.csv"]

    for _restart in range(2):
        for path in (a, b):
            env["handler"].process_with_retry(path, delay=0.01)

    assert env["parsed"] == ["a.csv", "b.csv"], "no copy is parsed again"
    assert env["failed"]() == ["a.csv", "b.csv"], "no FAILED record is added"


def test_the_same_content_under_a_new_name_is_read(env):
    env["handler"].process_with_retry(env["drop"]("a.csv"), delay=0.01)
    env["handler"].process_with_retry(env["drop"]("c.csv"), delay=0.01)

    assert env["parsed"] == ["a.csv", "c.csv"]
    assert env["failed"]() == ["a.csv", "c.csv"]


def test_a_copy_saved_again_after_it_failed_is_read(env):
    a, b = env["drop"]("a.csv"), env["drop"]("b.csv")
    for path in (a, b):
        env["handler"].process_with_retry(path, delay=0.01)
    later = time.time() + 60
    os.utime(a, (later, later))

    env["handler"].process_with_retry(a, delay=0.01)

    assert env["parsed"] == ["a.csv", "b.csv", "a.csv"]


def test_retry_reads_it(env):
    from database import models

    a = env["drop"]("a.csv")
    env["handler"].process_with_retry(a, delay=0.01)
    db = env["p2"]["SessionLocal"]()
    try:
        entry = db.query(models.FileIngestionLog).filter_by(filename="a.csv").one()
        env["handler"].process_archived_file_sync(entry, db)
    finally:
        db.close()

    assert env["parsed"] == ["a.csv", "a.csv"]
