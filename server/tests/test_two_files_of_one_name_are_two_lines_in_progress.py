# -*- coding: utf-8 -*-
"""총괄 10-20 (소유자 «다 voids.json 이면 뭐가 뭔지»): the progress list keys a file by table + full path. Two files of
one name in one table - a/voids.csv read while b/voids.csv waits in the heavy lane - are two lines, each with its
filepath, and the one that finishes leaves the other. Driven through the watcher's own notices, run_watcher's
forwarders and the API's internal events, read back from GET /admin/file-ingestion/active."""
import os
import sys
import types

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for path in (SERVER_DIR, os.path.join(SERVER_DIR, "parsers")):
    if path not in sys.path:
        sys.path.insert(0, path)

import directory_watcher                                         # noqa: E402
import event_constants                                           # noqa: E402
import run_watcher                                               # noqa: E402
from directory_watcher import IngestionHandler                   # noqa: E402
from ingestion import activity                                   # noqa: E402
from isolated_data_root import isolate_data_root                 # noqa: E402

INFO = {"business_key": "part_no", "column_types": {"part_no": "string", "qty": "number"},
        "display_columns": ["part_no", "qty"]}


class _Query:
    def filter(self, *a, **kw):
        return self

    def one_or_none(self):
        return None

    def update(self, *a, **kw):
        return 0


class _DB:
    def add(self, obj):
        pass

    def query(self, *a, **kw):
        return _Query()

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return os.path.abspath(path)


def test_two_files_of_one_name_are_two_lines_and_one_ending_leaves_the_other(tmp_path, monkeypatch, client):
    isolate_data_root(monkeypatch, tmp_path / "root")
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: {"inventory_master": INFO})
    monkeypatch.setattr(directory_watcher, "SessionLocal", lambda: _DB())
    monkeypatch.setattr(directory_watcher.crud, "apply_batch_updates",
                        lambda db, t, batch, notation_report=None: ([], [("r", "c")] * len(batch.updates), [], []))
    monkeypatch.setattr(run_watcher, "post_event", lambda endpoint, payload: client.post(endpoint, json=payload))
    ws = tmp_path / "ws"
    for sub in ("raws", "archives", "config"):
        (ws / sub).mkdir(parents=True)
    handler = IngestionHandler(str(ws), None, str(ws / "archives"), default_table_name="inventory_master",
                               on_file_processed_callback=run_watcher.trigger_ws_file_processed,
                               on_progress_callback=run_watcher.trigger_ws_progress,
                               on_ingestion_state_callback=run_watcher.trigger_ws_ingestion_state)
    a = _write(ws / "raws" / "a" / "voids.csv", "part_no,qty\nA-1,1\n")
    b = _write(ws / "raws" / "b" / "voids.csv", "part_no,qty\nB-1,1\n")
    activity.registry.clear()
    try:
        held = []
        handler.heavy_lane = types.SimpleNamespace(submit=lambda job, key: held.append(job))
        assert handler._submit_to_heavy_lane(b, "system", "heavy", 10)              # b waits: QUEUED

        seen, told = [], handler.on_progress_callback
        handler.on_progress_callback = lambda *args: (
            told(*args), seen.append(client.get("/admin/file-ingestion/active").json()["data"]))
        handler.process_with_retry(a, delay=0.01)

        assert seen, "no progress was told"
        lines = sorted(((e["filename"], e["filepath"], e["status"]) for e in seen[-1]), key=repr)
        assert lines == [("voids.csv", a, event_constants.PROGRESS_STATUS_RUNNING), ("voids.csv", b, "QUEUED")], lines
        left = client.get("/admin/file-ingestion/active").json()["data"]
        assert [(e["filepath"], e["status"]) for e in left] == [(b, "QUEUED")], left
    finally:
        activity.registry.clear()
