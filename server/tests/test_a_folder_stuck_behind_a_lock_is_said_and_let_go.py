# -*- coding: utf-8 -*-
"""총괄 10-07 ③ (소유자 운영: raws/<폴더> 의 트리 일꾼이 걸리면 그 폴더가 영영 막힌다).

On a real PostgreSQL, another connection holds a row lock the second chunk of f1 needs:

  ingestion_settings.json lock_timeout_seconds -> f1 FAILED, the sentence names the holder's pid,
     left in place and unsealed (retry 0 · retry 1 on the next sweep) · f2 of the same folder loads
  the lock released -> the next sweep finishes f1 from its last committed chunk, and the table equals
     the control that loaded the same file once
  a top-level file that waited is swept again although its (mtime, size) was tried
  the stalled line (once, from the sweep loop) and the sweep's 「running for N min」 line say the
     folder, the file and the holder
  statement_timeout_seconds is set on the same transactions
"""
import codecs
import json
import logging
import os
import threading
import time

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from conftest import retire_dynamic_model
from database import crud, models
from database.database import Base
from parsers import directory_watcher as dw
from tests.test_a_failed_external_file_retries_on_its_own_handler import env  # noqa: F401 - its harness
from tests.test_external_source_watcher import _write_voids
from utils import heartbeat

TABLE, CONTROL = "lock_probe_parts", "lock_probe_control"
DECLARED = {"business_key": "part_no",
            "column_types": {"part_no": "string", "category": "string", "stock_qty": "number"},
            "display_columns": ["part_no", "category", "stock_qty"]}
HEADER = "part_no,category,stock_qty\n"
SEED = HEADER + "P-1200,Old,0\n"
F1 = HEADER + "".join("P-%d,Cap,%d\n" % (i, i) for i in range(1, 1501))      # chunks of 1000 + 500
F2 = HEADER + "Q-1,Res,1\nQ-2,Res,2\n"
HELD = "P-1200"                                                                 # in f1's chunk 2
SAFETY_RELEASE_S = 20.0           # a build without the limit must fail, not hang the suite


@pytest.fixture(name="box")
def fixture_box(pg_engine, monkeypatch, tmp_path):
    saved = dict(crud.TABLE_CONFIG)
    config = {TABLE: dict(DECLARED), CONTROL: dict(DECLARED)}
    for name in config:
        retire_dynamic_model(name)
    models.init_dynamic_models(config)
    crud.TABLE_CONFIG.update(config)
    with pg_engine.begin() as conn:
        for name in config:
            conn.execute(text('DROP TABLE IF EXISTS "%s"' % name))
    Base.metadata.create_all(bind=pg_engine, tables=[models.DYNAMIC_TABLES[n].__table__ for n in config])
    models.ensure_ingestion_checkpoint_table(pg_engine)
    Session = sessionmaker(bind=pg_engine)
    monkeypatch.setattr(dw, "SessionLocal", Session)
    monkeypatch.setattr(heartbeat, "heartbeat_dir", lambda: str(tmp_path))      # never the box's
    monkeypatch.setattr(heartbeat, "heartbeat_path", lambda name: str(tmp_path / (name + ".json")))
    monkeypatch.setattr(dw, "load_global_table_config", lambda: config)
    monkeypatch.setattr(dw, "FLATTEN_STABILITY_INTERVAL_SECONDS", 0.05)
    monkeypatch.setattr(dw, "FLATTEN_STABILITY_MAX_WAIT_SECONDS", 5.0)
    settings_path = tmp_path / "ingestion_settings.json"
    monkeypatch.setattr(dw, "INGESTION_SETTINGS_PATH", str(settings_path))
    base = tmp_path / "ingestion_workspace"

    def handler_for(table):
        ws = base / table
        for sub in ("raws", "archives", "err"):
            (ws / sub).mkdir(parents=True, exist_ok=True)
        made = dw.IngestionHandler(workspace_path=str(ws), config_path=None,
                                   archives_path=str(ws / "archives"), default_table_name=table)
        quick = made.process_with_retry
        made.process_with_retry = lambda fp, uploader="system", retries=3, delay=1.0: quick(
            fp, uploader=uploader, retries=retries, delay=0.01)
        return made

    def write(handler, relative, content):
        path = os.path.join(handler.raws_path, relative)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(content)
        return path

    class Locker:
        """Another session holding `HELD`'s row (or what `statement` takes) - released by the
        test, or by the safety timer."""

        def __init__(self, statement=None):
            self.conn = pg_engine.connect()
            self.tx = self.conn.begin()
            self.pid = self.conn.execute(text("SELECT pg_backend_pid()")).scalar()
            self.conn.execute(text(statement or 'SELECT 1 FROM "%s" WHERE business_key_val = :k FOR UPDATE'
                                   % TABLE), {} if statement else {"k": HELD})
            self._timer = threading.Timer(SAFETY_RELEASE_S, self.release)
            self._timer.start()
            self._released = threading.Lock()

        def release(self):
            with self._released:
                if self.tx is not None:
                    self._timer.cancel()
                    self.tx.rollback()
                    self.conn.close()
                    self.tx = None

    def rows(table):
        with pg_engine.connect() as conn:
            return conn.execute(text('SELECT part_no, category, stock_qty FROM "%s" ORDER BY part_no'
                                     % table)).all()

    def logs(name):
        with pg_engine.connect() as conn:
            return conn.execute(text("SELECT status, error_message, retry_count FROM file_ingestion_logs "
                                     "WHERE filename = :f AND table_name = :t ORDER BY id"),
                                {"f": name, "t": TABLE}).all()

    def settings(**cells):
        settings_path.write_text(json.dumps(cells), encoding="utf-8")

    try:
        yield {"engine": pg_engine, "handler_for": handler_for, "write": write, "Locker": Locker,
               "rows": rows, "logs": logs, "settings": settings, "base": base}
    finally:
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        with pg_engine.begin() as conn:
            for name in config:
                conn.execute(text('DROP TABLE IF EXISTS "%s"' % name))
                conn.execute(text("DELETE FROM file_ingestion_checkpoints WHERE table_name = :t"), {"t": name})
            conn.execute(text("DELETE FROM file_ingestion_logs WHERE table_name IN (:a, :b)"),
                         {"a": TABLE, "b": CONTROL})
        for name in config:
            retire_dynamic_model(name)


def _tree(handler, folder):
    worker = handler.request_tree_ingest(os.path.join(handler.raws_path, folder))
    assert worker is not None, "the tree worker did not start"
    worker.join(60)
    assert not worker.is_alive()


def _stalled(caplog):
    return [r.getMessage() for r in caplog.records
            if r.getMessage().startswith("[Watcher] ") and ": stalled " in r.getMessage()]


def _checkpoint(engine, table, filename):
    with engine.connect() as conn:
        return conn.execute(text("SELECT status, processed_rows FROM file_ingestion_checkpoints "
                                 "WHERE table_name = :t AND filename = :f"), {"t": table, "f": filename}).one()


@pytest.mark.pg
def test_a_file_held_up_by_a_lock_fails_unsealed_and_the_next_sweep_finishes_it(box):
    box["settings"](lock_timeout_seconds=1)
    handler, control = box["handler_for"](TABLE), box["handler_for"](CONTROL)
    for made in (handler, control):
        made.process_with_retry(box["write"](made, "seed.csv", SEED))
    f1 = box["write"](handler, os.path.join("batch", "f1.csv"), F1)
    box["write"](handler, os.path.join("batch", "f2.csv"), F2)
    for name, content in (("f1.csv", F1), ("f2.csv", F2)):          # the control: each file once
        control.process_with_retry(box["write"](control, os.path.join("batch", name), content))

    locker = box["Locker"]()
    try:
        _tree(handler, "batch")                                   # the sweep, lock held
        _tree(handler, "batch")                                   # the next sweep, still held
    finally:
        locker.release()
    said = box["logs"]("f1.csv")
    assert [(status, count) for status, _m, count in said] == [("FAILED", 0), ("FAILED", 1)], said
    assert said[0][1].startswith(dw.LOCK_WAITED_OUT_PREFIX + " (1 s) in chunk 2 - waiting"), said[0][1]
    for (_status, message, count) in said:
        assert "on pid %d " % locker.pid in message and message.endswith("(retry %d)" % count), message
    assert [s for s, _m, _c in box["logs"]("f2.csv")] == ["SUCCESS"]
    assert os.path.exists(f1) and os.path.abspath(f1) in handler.waiting_on_a_lock     # unsealed, in place
    assert _checkpoint(box["engine"], TABLE, "f1.csv") == ("IN_PROGRESS", 1000)

    _tree(handler, "batch")                                       # the sweep after the release
    assert [s for s, _m, _c in box["logs"]("f1.csv")][-1] == "SUCCESS"
    assert not os.path.exists(os.path.join(handler.raws_path, "batch"))
    assert os.path.abspath(f1) not in handler.waiting_on_a_lock
    once = box["rows"](CONTROL)
    assert len(once) == 1502 and box["rows"](TABLE) == once       # rows and cells, as loaded once


@pytest.mark.pg
def test_a_top_level_file_that_waited_on_a_lock_is_swept_again(box):
    box["settings"](lock_timeout_seconds=1)
    handler = box["handler_for"](TABLE)
    handler.process_with_retry(box["write"](handler, "seed.csv", SEED))
    top = box["write"](handler, "top.csv", HEADER + "%s,New,9\n" % HELD)
    watcher = dw.WorkspaceWatcher(base_dir=str(box["base"]))
    watcher.handlers_by_raw_path[os.path.abspath(handler.raws_path)] = handler
    locker = box["Locker"]()
    try:
        watcher.sweep_existing_files()
    finally:
        locker.release()
    assert [s for s, _m, _c in box["logs"]("top.csv")] == ["FAILED"] and os.path.exists(top)
    watcher.sweep_existing_files()                                # same (mtime, size), same watcher
    assert [s for s, _m, _c in box["logs"]("top.csv")] == ["FAILED", "SUCCESS"]
    assert [r for r in box["rows"](TABLE) if r[0] == HELD] == [(HELD, "New", 9)]


@pytest.mark.pg
def test_the_stalled_line_and_the_folder_line_say_the_folder_the_file_and_the_holder(box, monkeypatch, caplog):
    box["settings"](lock_timeout_seconds=4)
    monkeypatch.setattr(heartbeat, "DEFAULT_STALL_AFTER_SEC", 0.5)
    monkeypatch.setattr(dw, "HEARTBEAT_SLICE_SECONDS", 0.2)
    monkeypatch.setattr(dw, "PERIODIC_SWEEP_INTERVAL_SECONDS", 3600)
    handler = box["handler_for"](TABLE)
    handler.process_with_retry(box["write"](handler, "seed.csv", SEED))
    batch = os.path.join(handler.raws_path, "batch")
    f1 = box["write"](handler, os.path.join("batch", "f1.csv"), F1)
    watcher = dw.WorkspaceWatcher(base_dir=str(box["base"]))
    watcher.handlers_by_raw_path[os.path.abspath(handler.raws_path)] = handler
    locker = box["Locker"]()
    loop = threading.Thread(target=watcher._periodic_sweep_loop, daemon=True)
    stuck = threading.Thread(target=handler.process_with_retry, args=(f1,), daemon=True)
    try:
        with caplog.at_level(logging.INFO):
            stuck.start()
            loop.start()
            deadline = time.time() + 3.0
            while time.time() < deadline and not _stalled(caplog):
                time.sleep(0.05)
            time.sleep(1.0)                    # five more slices of the loop, the claim still stalled
            with handler._processing_lock:                         # its tree worker, two minutes in
                handler._ingesting_dirs[os.path.normcase(os.path.abspath(batch))] = time.time() - 125
            watcher.recheck_subfolders()                           # the subfolder look says it (2f487efb5)
    finally:
        watcher._stop_event.set()
        stuck.join(10)
        locker.release()
        loop.join(5)
    stalled = _stalled(caplog)
    assert len(stalled) == 1, stalled                             # once per episode
    assert stalled[0].startswith("[Watcher] ingest f1.csv: stalled ")
    assert "(folder batch · db pid " in stalled[0] and "on pid %d " % locker.pid in stalled[0], stalled
    running = [r.getMessage() for r in caplog.records if "tree ingestion has been running" in r.getMessage()]
    assert running == ["[%s] 📂 'batch': 1 file(s) left - tree ingestion has been running for 2 min (now: ingest"
                       " f1.csv) - next look in 30 s - #1 for this folder and reason (said at the 1st, 10th, 100th"
                       " ...)" % TABLE], running


@pytest.mark.pg
def test_a_statement_timeout_is_set_on_the_same_transactions(box):
    box["settings"](lock_timeout_seconds=0, statement_timeout_seconds=1)
    handler = box["handler_for"](TABLE)
    handler.process_with_retry(box["write"](handler, "seed.csv", SEED))
    locker = box["Locker"]()
    try:
        handler.process_with_retry(box["write"](handler, "late.csv", HEADER + "%s,New,9\n" % HELD))
    finally:
        locker.release()
    (status, message, _count), = box["logs"]("late.csv")
    assert status == "FAILED" and "QueryCanceled" in message, message    # the server's words are its locale's


def test_the_lock_limit_defaults_to_the_stall_threshold_and_a_wrong_spelling_keeps_it():
    stall = heartbeat.DEFAULT_STALL_AFTER_SEC
    assert dw.file_write_timeouts({}) == (stall, None)
    assert dw.file_write_timeouts({"lock_timeout_seconds": "5", "statement_timeout_seconds": -1}) == (stall, None)
    assert dw.file_write_timeouts({"lock_timeout_seconds": None, "statement_timeout_seconds": 30}) == (None, 30.0)
    assert dw.file_write_timeouts({"lock_timeout_seconds": 0}) == (None, None)


@pytest.mark.pg
def test_an_analyze_held_up_by_a_lock_is_skipped_and_the_folder_goes_on(box, caplog):
    """Applied QA 8652ddb26: ANALYZE runs on its own connection and takes SHARE UPDATE EXCLUSIVE,
    so a CREATE INDEX CONCURRENTLY, a VACUUM or another ANALYZE of the table held it without end."""
    box["settings"](lock_timeout_seconds=1, analyze_after_rows=1)
    handler = box["handler_for"](TABLE)
    for name, row in (("f1.csv", "A-1,Cap,1\n"), ("f2.csv", "A-2,Cap,2\n")):
        box["write"](handler, os.path.join("batch", name), HEADER + row)
    locker = box["Locker"]('LOCK TABLE "%s" IN SHARE UPDATE EXCLUSIVE MODE' % TABLE)
    try:
        with caplog.at_level(logging.WARNING):
            _tree(handler, "batch")
    finally:
        locker.release()
    assert [box["logs"](name)[-1][0] for name in ("f1.csv", "f2.csv")] == ["SUCCESS", "SUCCESS"]
    skipped = [r.getMessage() for r in caplog.records if "ANALYZE skipped" in r.getMessage()]
    said = "[%s] ANALYZE skipped: %s locked by waiting Lock:relation on pid %d " % (TABLE, TABLE, locker.pid)
    assert len(skipped) == 2 and all(line.startswith(said) for line in skipped), skipped
    assert not os.path.exists(os.path.join(handler.raws_path, "batch"))


def test_the_ingestion_settings_file_is_read_with_a_bom(monkeypatch, tmp_path):
    """총괄 10-07: the same reading as table_config (crud._decode_config_text)."""
    path = tmp_path / "ingestion_settings.json"
    path.write_bytes(codecs.BOM_UTF8 + b'{"lock_timeout_seconds": 7}')
    monkeypatch.setattr(dw, "INGESTION_SETTINGS_PATH", str(path))
    assert dw.file_write_timeouts() == (7.0, None)


def test_both_sweeps_try_again_a_file_that_waited_on_a_lock_and_only_that_file(env, monkeypatch):
    """총괄 10-07 ③ 1) ㄱ: the raws/ sweep and the external sweep skip by one rule (`_tried_already`)."""
    import directory_watcher as running                 # the module the external harness wires
    dispatched = []
    monkeypatch.setattr(running.IngestionHandler, "_handle_event",
                        lambda self, fp: dispatched.append(os.path.basename(fp)))
    watcher = env["watcher"]({})
    raws = watcher.raws_root_for("rt_parts")
    top = os.path.join(raws, "parts.csv")
    with open(top, "w", encoding="utf-8") as fh:
        fh.write(HEADER + "P-1,Cap,1\n")
    external = str(_write_voids(env["external"]))

    def sweep():
        dispatched.clear()
        watcher.sweep_existing_files()
        watcher.sweep_external_sources()
        return sorted(dispatched)

    assert sweep() == ["parts.csv", "voids.json"]                    # first sight
    assert sweep() == []                                              # tried at this (mtime, size)
    for root, path in ((raws, top), (watcher.raws_root_for("void_obs"), external)):
        watcher.handlers_by_raw_path[root].waiting_on_a_lock.add(os.path.abspath(path))
    assert sweep() == ["parts.csv", "voids.json"]
