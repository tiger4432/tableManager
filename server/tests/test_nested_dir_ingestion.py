"""[Nested dirs] A directory dropped into raws/ is ingested IN PLACE.

The folder names are data (lot, equipment, date), so the file is dispatched at its
REAL nested path and the path reaches the parser — it is not promoted to raws/ with
the folder names encoded into its filename (superseded 2026-07-30: that was a round
trip through a string for information the callee already holds).

Spec verified here:
1. quiescence: a tree mid-copy is not read (tree-generalized stability check),
2. in-place dispatch: every regular file goes through the UNCHANGED pipeline
   (event path → lane routing → parser → checkpoint/dedup → archives/, err/) at
   its nested path, and only the directories that end up empty are removed,
3. the relative path is what a declaration sees: relative to raws/, POSIX
   separators, and a component that escapes raws/ is refused,
4. archive is CONDITIONAL: a workspace file is archived as before; a file outside
   raws/ (a foreign, read-only tree) is never moved — its signature still answers
   dedup,
5. junk-aware: Thumbs.db / desktop.ini / .DS_Store / ._* discarded with the tree,
6. conservative on failure: a locked/unprocessable file preserves its directory,
7. switchable: ingestion_settings.json `flatten_nested_dirs` (default true).

Table names use the user-config-impossible `flat_test_*` prefix (lesson file).
"""

import os
import sys
import threading
import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)
parsers_dir = os.path.join(server_dir, "parsers")
if parsers_dir not in sys.path:
    sys.path.insert(0, parsers_dir)

import directory_watcher
from directory_watcher import IngestionHandler, WorkspaceWatcher
from database.database import Base
from database import crud, models
from database.models import FileIngestionLog

PARTS_INFO = {
    "business_key": "part_no",
    "column_types": {"part_no": "string", "category": "string", "stock_qty": "number"},
    "display_columns": ["part_no", "category", "stock_qty"],
}

TABLE = "flat_test_parts"


def _write(path, text):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return str(path)


def _csv(n, prefix="P"):
    lines = ["part_no,category,stock_qty"]
    for i in range(1, n + 1):
        lines.append(f"{prefix}-{i},Cap,{i}")
    return "\n".join(lines) + "\n"


@pytest.fixture
def flat_env(tmp_path, monkeypatch):
    """SQLite in-memory DB + handler factory + fast quiescence timings."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    table_config = {TABLE: dict(PARTS_INFO)}
    models.init_dynamic_models(table_config)
    crud.TABLE_CONFIG.update(table_config)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    models.ensure_ingestion_checkpoint_table(engine)

    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: table_config)
    monkeypatch.setattr(directory_watcher, "SessionLocal", TestingSessionLocal)
    settings_path = tmp_path / "ingestion_settings.json"
    monkeypatch.setattr(directory_watcher, "INGESTION_SETTINGS_PATH", str(settings_path))
    # Fast quiescence polling for tests (module globals are read at call time).
    monkeypatch.setattr(directory_watcher, "FLATTEN_STABILITY_INTERVAL_SECONDS", 0.05)
    monkeypatch.setattr(directory_watcher, "FLATTEN_STABILITY_MAX_WAIT_SECONDS", 5.0)

    def make_handler(heavy_lane=None):
        ws = tmp_path / f"ws_{TABLE}"
        (ws / "raws").mkdir(parents=True, exist_ok=True)
        (ws / "archives").mkdir(exist_ok=True)
        (ws / "err").mkdir(exist_ok=True)
        handler = IngestionHandler(
            workspace_path=str(ws),
            config_path=None,
            archives_path=str(ws / "archives"),
            default_table_name=TABLE,
            heavy_lane=heavy_lane,
        )
        return ws, handler

    yield {
        "SessionLocal": TestingSessionLocal,
        "make_handler": make_handler,
        "settings_path": settings_path,
        "tmp_path": tmp_path,
    }

    Base.metadata.drop_all(bind=engine)


def _speed_up_processing(handler):
    """Keep the real processing path but shrink the 1s debounce to 0.01s."""
    orig = handler.process_with_retry

    def fast(fp, uploader="system", retries=3, delay=1.0):
        return orig(fp, uploader=uploader, retries=retries, delay=0.01)

    handler.process_with_retry = fast


def _stub_processing(handler, root=None):
    """Replace processing with a recorder so files stay in place for inspection.

    Records the path RELATIVE TO raws/ (POSIX) — the dispatch location is the
    thing under test, so recording only the basename would hide it.
    """
    root = root or os.path.abspath(handler.raws_path)
    calls = []

    def stub(fp, uploader="system", retries=3, delay=1.0):
        calls.append(os.path.relpath(fp, root).replace(os.sep, "/"))

    handler.process_with_retry = stub
    return calls


def _ingest_sync(handler, dir_path, timeout=20):
    t = handler.request_tree_ingest(dir_path)
    assert t is not None, "tree ingestion was not started"
    t.join(timeout)
    assert not t.is_alive(), "tree ingestion worker did not finish in time"
    return t


def _rows(env):
    db = env["SessionLocal"]()
    try:
        return db.query(models.DYNAMIC_TABLES[TABLE]).all()
    finally:
        db.close()


def _logs(env):
    db = env["SessionLocal"]()
    try:
        return db.query(FileIngestionLog).all()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Core: files dispatched AT THEIR NESTED PATH, then archived, folders gone
# ---------------------------------------------------------------------------

def test_nested_files_are_dispatched_at_their_real_path(flat_env):
    ws, handler = flat_env["make_handler"]()
    raws = ws / "raws"
    calls = _stub_processing(handler)
    _write(raws / "batch" / "a.csv", _csv(1, "A"))
    _write(raws / "batch" / "lv2" / "b.csv", _csv(1, "B"))
    _write(raws / "batch" / "lv2" / "lv3" / "c.csv", _csv(1, "C"))

    _ingest_sync(handler, str(raws / "batch"))

    # The path handed to processing is the NESTED one — not raws/a.csv.
    assert sorted(calls) == ["batch/a.csv", "batch/lv2/b.csv", "batch/lv2/lv3/c.csv"]
    # Nothing was promoted to the raws/ root.
    assert sorted(p.name for p in raws.iterdir()) == ["batch"]


def test_nested_three_levels_all_ingested_and_archived_folders_gone(flat_env):
    ws, handler = flat_env["make_handler"]()
    _speed_up_processing(handler)
    raws = ws / "raws"
    batch = raws / "batch"
    _write(batch / "a.csv", _csv(2, "A"))
    _write(batch / "lv2" / "b.csv", _csv(2, "B"))
    _write(batch / "lv2" / "lv3" / "c.csv", _csv(2, "C"))

    _ingest_sync(handler, str(batch))

    # The tree drains through the ARCHIVE (a workspace file is still archived on
    # success), so the emptied directories are removed.
    assert not batch.exists()
    assert [p for p in raws.iterdir()] == []

    parts = {r.part_no for r in _rows(flat_env)}
    assert parts == {"A-1", "A-2", "B-1", "B-2", "C-1", "C-2"}
    assert sorted(os.listdir(ws / "archives")) == ["a.csv", "b.csv", "c.csv"]


def test_same_basename_in_two_folders_never_overwrites_in_archives(flat_env):
    """In-place ingestion routinely archives same-named files from different
    folders. The old single `_<epoch>` attempt collided for two files finishing in
    the same second — on POSIX shutil.move would overwrite the earlier archive."""
    ws, handler = flat_env["make_handler"]()
    _speed_up_processing(handler)
    raws = ws / "raws"
    batch = raws / "batch"
    _write(batch / "one" / "dup.csv", _csv(1, "X"))
    _write(batch / "two" / "dup.csv", _csv(1, "Y"))
    _write(batch / "three" / "dup.csv", _csv(1, "Z"))

    _ingest_sync(handler, str(batch))

    archived = sorted(os.listdir(ws / "archives"))
    assert len(archived) == 3, archived            # nothing was clobbered
    assert len({(ws / "archives" / n).read_text() for n in archived}) == 3
    assert {r.part_no for r in _rows(flat_env)} == {"X-1", "Y-1", "Z-1"}


# ---------------------------------------------------------------------------
# The relative path: what a declaration sees
# ---------------------------------------------------------------------------

def test_relative_source_path_is_posix_and_relative(flat_env):
    ws, handler = flat_env["make_handler"]()
    root = os.path.abspath(str(ws / "raws"))
    rel = handler.relative_source_path(os.path.join(root, "batchA", "sub2", "x.csv"), root)
    assert rel == "batchA/sub2/x.csv"
    assert os.sep not in rel or os.sep == "/"      # never a backslash
    assert not os.path.isabs(rel)                  # no machine layout in the rule
    # A file directly in raws/ is the degenerate case: just the filename.
    assert handler.relative_source_path(os.path.join(root, "x.csv"), root) == "x.csv"


@pytest.mark.parametrize("escaping", [
    os.path.join("..", "archives", "x.csv"),
    os.path.join("batch", "..", "..", "x.csv"),
    os.path.join("..", "..", "..", "etc", "passwd"),
])
def test_escaping_paths_get_no_relative_path(flat_env, escaping):
    """A ".." component must never reach a declaration or a destination. The check
    is result-based (rejoin must land on the same file under root), not a
    character blacklist — that misses `C:foo` and over-refuses `..foo`."""
    ws, handler = flat_env["make_handler"]()
    root = os.path.abspath(str(ws / "raws"))
    assert handler.relative_source_path(os.path.join(root, escaping), root) is None
    # ...while a name that merely STARTS with dots is legal and not over-refused.
    assert handler.relative_source_path(os.path.join(root, "..foo", "x.csv"), root) \
        == "..foo/x.csv"


def test_a_walk_entry_that_escapes_raws_is_refused_and_not_ingested(flat_env, monkeypatch, caplog):
    """os.walk under raws/ cannot normally produce an escaping path; a junction or
    a symlinked branch can. Such a file is refused — never dispatched, never given
    a ".."-bearing path — and the directory is preserved rather than removed."""
    ws, handler = flat_env["make_handler"]()
    calls = _stub_processing(handler)
    raws = ws / "raws"
    batch = raws / "batch"
    _write(batch / "ok.csv", "ok\n")
    # A file OUTSIDE raws/ (archives/ is a sibling) — what a junction inside
    # batch/ pointing at ../archives would make os.walk yield.
    outside = _write(ws / "archives" / "foreign.csv", "bad\n")

    real_walk = os.walk

    def walk_with_a_junction(top, *a, **kw):
        for entry in real_walk(top, *a, **kw):
            yield entry
            if os.path.normpath(entry[0]) == os.path.normpath(str(batch)):
                yield str(ws / "archives"), [], ["foreign.csv"]

    monkeypatch.setattr(directory_watcher.os, "walk", walk_with_a_junction)
    with caplog.at_level("WARNING"):
        _ingest_sync(handler, str(batch))
    monkeypatch.undo()

    assert calls == ["batch/ok.csv"]            # the escaping file was NOT dispatched
    assert os.path.exists(outside)              # and was not touched
    assert any("escaping component" in r.message for r in caplog.records)
    assert any("Tree ingestion incomplete" in r.message for r in caplog.records)


def test_pipeline_parser_receives_the_relative_path(flat_env):
    """The watcher provides the path; the parser turns folder names into columns.
    Handed in as an attribute so parse(path) — a contract user scripts subclass —
    keeps its signature."""
    ws, handler = flat_env["make_handler"]()
    raws = ws / "raws"
    scripts = ws / "scripts"
    scripts.mkdir(exist_ok=True)
    (scripts / "rel_probe.py").write_text(
        "from pipeline_base import BasePipelineParser\n"
        "SEEN = []\n"
        "class RelProbe(BasePipelineParser):\n"
        "    @classmethod\n"
        "    def match(cls, file_path):\n"
        "        return file_path.endswith('.probe')\n"
        "    def parse(self, file_path):\n"
        "        import json, os\n"
        "        with open(os.path.join(os.path.dirname(file_path), 'seen.json'), 'w') as f:\n"
        "            json.dump({'rel_path': self.rel_path}, f)\n"
        "        return [{'part_no': 'R-1', 'category': 'Cap', 'stock_qty': 1}]\n",
        encoding="utf-8",
    )
    _speed_up_processing(handler)
    target = _write(raws / "LOT-A1" / "EQP-7" / "m.probe", "x\n")

    _ingest_sync(handler, str(raws / "LOT-A1"))

    import json
    seen = json.loads((raws / "LOT-A1" / "EQP-7" / "seen.json").read_text())
    assert seen["rel_path"] == "LOT-A1/EQP-7/m.probe"
    assert {r.part_no for r in _rows(flat_env)} == {"R-1"}
    assert not os.path.exists(target)  # archived on success


# ---------------------------------------------------------------------------
# Conditional archive: a foreign (read-only) tree is never moved
# ---------------------------------------------------------------------------

def test_workspace_file_is_managed_and_foreign_file_is_not(flat_env):
    ws, handler = flat_env["make_handler"]()
    raws = ws / "raws"
    assert handler.is_managed_source(str(raws / "x.csv"))
    assert handler.is_managed_source(str(raws / "deep" / "x.csv"))
    assert not handler.is_managed_source(str(ws / "archives" / "x.csv"))
    assert not handler.is_managed_source(str(flat_env["tmp_path"] / "share" / "x.csv"))


def test_foreign_source_is_ingested_but_never_moved(flat_env, caplog):
    ws, handler = flat_env["make_handler"]()
    _speed_up_processing(handler)
    foreign = _write(flat_env["tmp_path"] / "share" / "eqp" / "lot.csv", _csv(2, "F"))

    with caplog.at_level("INFO"):
        handler._handle_event(foreign)

    # Rows landed...
    assert {r.part_no for r in _rows(flat_env)} == {"F-1", "F-2"}
    # ...and the file is still exactly where it was. Not archived, not deleted.
    assert os.path.exists(foreign)
    assert os.listdir(ws / "archives") == []
    assert os.listdir(ws / "err") == []
    assert any("Source left untouched" in r.message for r in caplog.records)
    # The ingestion record points at the ORIGINAL path, which is the truth for it.
    logs = _logs(flat_env)
    assert [l.status for l in logs] == ["SUCCESS"]
    assert os.path.normcase(logs[0].filepath) == os.path.normcase(os.path.abspath(foreign))


def test_foreign_source_failure_does_not_move_it_to_err(flat_env):
    ws, handler = flat_env["make_handler"]()
    _speed_up_processing(handler)
    # A file the std parser cannot make rows from -> the failure path.
    foreign = _write(flat_env["tmp_path"] / "share" / "broken.xyz", "not-a-table\n")

    handler._handle_event(foreign)

    assert os.path.exists(foreign)
    assert os.listdir(ws / "err") == []
    assert [l.status for l in _logs(flat_env)] == ["FAILED"]


def test_foreign_source_reingest_is_deduped_quietly(flat_env, caplog):
    """A foreign file cannot be archived away, so every sweep re-finds it and the
    dedup skip repeats forever by construction. One log row + one callback per
    sweep would bury every real event, so the repeat is quiet — the durable record
    is the SUCCESS row from the first ingestion, keyed by the same signature."""
    ws, handler = flat_env["make_handler"]()
    _speed_up_processing(handler)
    foreign = _write(flat_env["tmp_path"] / "share" / "lot.csv", _csv(1, "F"))
    fired = []
    handler.on_file_processed_callback = lambda *a: fired.append(a)

    handler._handle_event(foreign)
    assert [l.status for l in _logs(flat_env)] == ["SUCCESS"]

    for _ in range(3):  # what the periodic sweep does
        with handler._processing_lock:
            handler.processing_files.discard(os.path.abspath(foreign))
        handler._handle_event(foreign)

    # Still exactly ONE row and ONE callback — no unbounded SKIPPED noise.
    assert [l.status for l in _logs(flat_env)] == ["SUCCESS"]
    assert len(fired) == 1
    # And a MANAGED file's skip is still loud (the no-silent-skip rule holds where
    # the repeat is not structural).
    managed = _write(ws / "raws" / "same.csv", _csv(1, "F"))
    handler._handle_event(managed)
    assert sorted(l.status for l in _logs(flat_env)) == ["SKIPPED", "SUCCESS"]


# ---------------------------------------------------------------------------
# Quiescence: a tree mid-copy must not be read
# ---------------------------------------------------------------------------

def test_mid_copy_waits_until_tree_is_stable(flat_env, monkeypatch):
    monkeypatch.setattr(directory_watcher, "FLATTEN_STABILITY_INTERVAL_SECONDS", 0.1)
    ws, handler = flat_env["make_handler"]()
    seen = {}
    raws = ws / "raws"
    batch = raws / "copying"
    target = _write(batch / "grow.csv", "start\n")

    def record(fp, uploader="system", retries=3, delay=1.0):
        with open(fp, encoding="utf-8") as f:
            seen[os.path.relpath(fp, str(raws)).replace(os.sep, "/")] = f.read()

    handler.process_with_retry = record

    stop_at = time.monotonic() + 0.4
    def writer():
        while time.monotonic() < stop_at:
            with open(target, "a", encoding="utf-8") as f:
                f.write("more-data\n")
            time.sleep(0.03)
    w = threading.Thread(target=writer)
    w.start()
    t0 = time.monotonic()
    _ingest_sync(handler, str(batch))
    elapsed = time.monotonic() - t0
    w.join()

    # The file was READ only after the writer went quiet, and read WHOLE.
    assert elapsed >= 0.35
    content = seen["copying/grow.csv"]
    assert content.startswith("start\n") and content.endswith("more-data\n")


def test_never_stable_tree_is_deferred_untouched(flat_env, monkeypatch, caplog):
    monkeypatch.setattr(directory_watcher, "FLATTEN_STABILITY_INTERVAL_SECONDS", 0.05)
    monkeypatch.setattr(directory_watcher, "FLATTEN_STABILITY_MAX_WAIT_SECONDS", 0.2)
    ws, handler = flat_env["make_handler"]()
    calls = _stub_processing(handler)
    raws = ws / "raws"
    batch = raws / "endless"
    target = _write(batch / "grow.csv", "x")

    stop = threading.Event()
    def writer():
        while not stop.is_set():
            with open(target, "a") as f:
                f.write("x")
            time.sleep(0.02)
    w = threading.Thread(target=writer, daemon=True)
    w.start()
    try:
        with caplog.at_level("WARNING"):
            _ingest_sync(handler, str(batch))
    finally:
        stop.set()
        w.join()

    assert batch.exists() and os.path.exists(target)  # untouched
    assert calls == []                                # nothing dispatched
    assert any("Tree ingestion deferred" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Locked file: directory preserved + warning; retry completes after unlock
# ---------------------------------------------------------------------------

@pytest.mark.skipif(os.name != "nt", reason="open-handle move lock is a Windows semantic")
def test_locked_file_preserves_directory_then_retry_completes(flat_env):
    ws, handler = flat_env["make_handler"]()
    _speed_up_processing(handler)
    raws = ws / "raws"
    batch = raws / "batch"
    locked = _write(batch / "sub" / "locked.csv", _csv(1, "L"))
    _write(batch / "sub2" / "free.csv", _csv(1, "R"))

    fh = open(locked, "r")
    try:
        _ingest_sync(handler, str(batch))
        # The movable file completed and its emptied branch was removed...
        assert not (batch / "sub2").exists()
        assert (ws / "archives" / "free.csv").exists()
        # ...the locked one kept its directory alive (os.rmdir never deletes a
        # directory containing anything).
        assert os.path.exists(locked)
        assert (batch / "sub").exists()
    finally:
        fh.close()

    # Periodic-sweep semantics: a later trigger finishes the job.
    with handler._processing_lock:
        handler.processing_files.clear()
    _ingest_sync(handler, str(batch))
    assert not batch.exists()
    assert (ws / "archives" / "locked.csv").exists()


# ---------------------------------------------------------------------------
# Hidden/system file policy: discarded with the folder
# ---------------------------------------------------------------------------

def test_hidden_system_files_discarded_with_folder(flat_env):
    ws, handler = flat_env["make_handler"]()
    calls = _stub_processing(handler)
    raws = ws / "raws"
    batch = raws / "batch"
    _write(batch / "real.csv", "real\n")
    _write(batch / "Thumbs.db", "junk")
    _write(batch / "sub" / "desktop.ini", "junk")
    _write(batch / "sub" / ".DS_Store", "junk")
    _write(batch / "sub" / "._real.csv", "appledouble")

    _ingest_sync(handler, str(batch))

    assert calls == ["batch/real.csv"]  # junk never dispatched to the parser
    # The junk-only branch was emptied and removed; batch/ survives because
    # real.csv is still there (the stub did not archive it).
    assert not (batch / "sub").exists()
    assert (batch / "real.csv").exists()
    assert not (batch / "Thumbs.db").exists()


# ---------------------------------------------------------------------------
# Config knob (ingestion_settings.json, hot, default ON)
# ---------------------------------------------------------------------------

def test_disabled_by_setting_leaves_directory_alone(flat_env, caplog):
    flat_env["settings_path"].write_text('{"flatten_nested_dirs": false}', encoding="utf-8")
    ws, handler = flat_env["make_handler"]()
    raws = ws / "raws"
    batch = raws / "batch"
    _write(batch / "a.csv", _csv(1))

    with caplog.at_level("INFO"):
        assert handler.request_tree_ingest(str(batch)) is None
    assert batch.exists() and (batch / "a.csv").exists()
    # The off-switch means "not ingested", and the log says so rather than
    # implying the files were merely left where they are.
    assert any("are NOT ingested" in r.message for r in caplog.records)

    # Hot semantics: removing the off-switch re-enables on the NEXT trigger.
    flat_env["settings_path"].write_text('{"flatten_nested_dirs": true}', encoding="utf-8")
    _speed_up_processing(handler)
    _ingest_sync(handler, str(batch))
    assert not batch.exists()


# ---------------------------------------------------------------------------
# Idempotency / re-entrancy and trigger scoping
# ---------------------------------------------------------------------------

def test_second_trigger_on_same_tree_is_noop_while_in_flight(flat_env, monkeypatch):
    monkeypatch.setattr(directory_watcher, "FLATTEN_STABILITY_INTERVAL_SECONDS", 0.3)
    ws, handler = flat_env["make_handler"]()
    _speed_up_processing(handler)
    raws = ws / "raws"
    batch = raws / "batch"
    _write(batch / "a.csv", _csv(1))

    t1 = handler.request_tree_ingest(str(batch))
    assert t1 is not None
    assert handler.request_tree_ingest(str(batch)) is None  # guarded: in flight
    t1.join(20)
    assert not batch.exists()
    # After completion the guard is released; a stale trigger is a safe no-op.
    assert handler.request_tree_ingest(str(batch)) is None


def test_request_tree_ingest_rejects_non_direct_children_and_files(flat_env):
    ws, handler = flat_env["make_handler"]()
    raws = ws / "raws"
    f = _write(raws / "plain.csv", "x")
    assert handler.request_tree_ingest(f) is None                    # not a dir
    assert handler.request_tree_ingest(str(ws / "archives")) is None  # outside raws/
    nested = raws / "a" / "b"
    nested.mkdir(parents=True)
    assert handler.request_tree_ingest(str(nested)) is None  # not a DIRECT child


# ---------------------------------------------------------------------------
# Sweep integration: startup/periodic sweep triggers tree ingestion
# ---------------------------------------------------------------------------

def test_sweep_triggers_tree_ingest_for_directories(flat_env, monkeypatch):
    ws, handler = flat_env["make_handler"]()
    swept = _stub_processing(handler)
    raws = ws / "raws"
    batch = raws / "batch"
    _write(batch / "nested.csv", "n\n")
    _write(raws / "direct.csv", "d\n")

    ww = WorkspaceWatcher(base_dir=str(flat_env["tmp_path"]))
    ww.handlers_by_raw_path[os.path.abspath(str(raws))] = handler

    requested = []
    monkeypatch.setattr(handler, "request_tree_ingest",
                        lambda p: requested.append(os.path.abspath(p)))
    processed = ww.sweep_existing_files()

    assert requested == [os.path.abspath(str(batch))]  # dir -> tree trigger
    assert processed == 1 and swept == ["direct.csv"]  # file -> normal sweep


# ---------------------------------------------------------------------------
# Heavy lane: a big file inside a folder still routes by size, in place
# ---------------------------------------------------------------------------

class _RecordingLane:
    def __init__(self):
        self.jobs = []

    def submit(self, job):
        self.jobs.append(job)


def test_heavy_file_in_folder_routes_to_heavy_lane_in_place(flat_env):
    # Threshold ~10 bytes so the "big" file is cheap to fabricate.
    flat_env["settings_path"].write_text('{"heavy_file_mb": 0.00001}', encoding="utf-8")
    lane = _RecordingLane()
    ws, handler = flat_env["make_handler"](heavy_lane=lane)
    small_calls = _stub_processing(handler)
    raws = ws / "raws"
    batch = raws / "batch"
    big = _write(batch / "big.csv", "part_no,category,stock_qty\n" + "H-1,Cap,1\n" * 50)
    tiny = _write(batch / "tiny.csv", "t")  # 1 byte, below the ~10B threshold
    # Deterministic dispatch order (mtime ascending): big first, then tiny.
    now = time.time()
    os.utime(big, (now - 10, now - 10))
    os.utime(tiny, (now, now))

    _ingest_sync(handler, str(batch))

    # Lane classification ran on the NESTED paths.
    assert handler._classify_lane(big)[0] == "heavy"
    assert handler._classify_lane(tiny)[0] == "normal"
    # big.csv (older mtime, dispatched first) was queued to the heavy lane; the
    # follower tiny.csv also went to the queue tail because the workspace-order
    # FIFO invariant holds while heavy backlog is nonzero (fake lane never runs).
    assert len(lane.jobs) == 2
    assert small_calls == []
    assert os.path.exists(big) and os.path.exists(tiny)
    assert batch.exists()  # nothing archived yet -> directory preserved
