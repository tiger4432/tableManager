"""[Flatten] Nested directory flatten in raws/ — spec verification.

A directory (arbitrarily nested) dropped into a workspace's raws/ must be:
1. left untouched until the tree is quiescent (tree-generalized stability check),
2. flattened: every regular file moved to the raws/ root, then dispatched through
   the UNCHANGED existing pipeline (event path, lane routing, parser, archives/),
3. collision-safe: never overwrite — relative-subpath prefix with the "~"
   separator (must never fabricate the `__force__` token, must preserve the
   `user(<name>)` uploader prefix),
4. conservative on failure: a locked/unmovable file preserves its directory
   (only emptied directories are removed, via os.rmdir),
5. junk-aware: Thumbs.db / desktop.ini / .DS_Store / ._* discarded with the tree,
6. switchable: ingestion_settings.json `flatten_nested_dirs` (default true).

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
from ingestion_checkpoint import is_force_reingest

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
    """SQLite in-memory DB + handler factory + fast flatten timings."""
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


def _stub_processing(handler):
    """Replace processing with a recorder so files stay in raws/ for inspection."""
    calls = []

    def stub(fp, uploader="system", retries=3, delay=1.0):
        calls.append(os.path.basename(fp))

    handler.process_with_retry = stub
    return calls


def _flatten_sync(handler, dir_path, timeout=20):
    t = handler.request_flatten(dir_path)
    assert t is not None, "flatten was not started"
    t.join(timeout)
    assert not t.is_alive(), "flatten worker did not finish in time"
    return t


def _rows(env):
    db = env["SessionLocal"]()
    try:
        return db.query(models.DYNAMIC_TABLES[TABLE]).all()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Core: nested tree -> files ingested, folders gone, archives populated
# ---------------------------------------------------------------------------

def test_nested_three_levels_all_ingested_folders_gone(flat_env):
    ws, handler = flat_env["make_handler"]()
    _speed_up_processing(handler)
    raws = ws / "raws"
    batch = raws / "batch"
    _write(batch / "a.csv", _csv(2, "A"))
    _write(batch / "lv2" / "b.csv", _csv(2, "B"))
    _write(batch / "lv2" / "lv3" / "c.csv", _csv(2, "C"))

    _flatten_sync(handler, str(batch))

    # Directory tree fully removed, raws/ back to flat.
    assert not batch.exists()
    assert [p for p in raws.iterdir()] == []  # all moved files processed away

    # All three files went through the real pipeline into the DB and archives/.
    parts = {r.part_no for r in _rows(flat_env)}
    assert parts == {"A-1", "A-2", "B-1", "B-2", "C-1", "C-2"}
    archived = sorted(os.listdir(ws / "archives"))
    assert archived == ["a.csv", "b.csv", "c.csv"]


# ---------------------------------------------------------------------------
# Collisions: never overwrite, subpath prefix, batch-internal claim set
# ---------------------------------------------------------------------------

def test_collision_gets_subpath_prefix_never_overwrites(flat_env):
    ws, handler = flat_env["make_handler"]()
    calls = _stub_processing(handler)
    raws = ws / "raws"
    _write(raws / "x.csv", "root-content\n")           # pre-existing at raws root
    batch = raws / "batchA"
    _write(batch / "x.csv", "level1-content\n")        # collides with root
    _write(batch / "sub2" / "x.csv", "level2-content\n")  # collides with both
    _write(batch / "sub2" / "y.csv", "y-content\n")    # no collision

    _flatten_sync(handler, str(batch))

    assert not batch.exists()
    names = sorted(os.listdir(raws))
    # Colliding names get the subpath prefix; the unique y.csv keeps its name.
    assert names == ["batchA~sub2~x.csv", "batchA~x.csv", "x.csv", "y.csv"]
    # Nothing was overwritten — every content survived.
    assert (raws / "x.csv").read_text() == "root-content\n"
    assert (raws / "batchA~x.csv").read_text() == "level1-content\n"
    assert (raws / "batchA~sub2~x.csv").read_text() == "level2-content\n"
    assert (raws / "y.csv").read_text() == "y-content\n"
    # Only the three MOVED files were dispatched (pre-existing x.csv untouched).
    assert sorted(calls) == sorted(n for n in names if n != "x.csv")


def test_no_collision_keeps_plain_basename_and_claim_set_blocks_batch_dupes(flat_env):
    ws, handler = flat_env["make_handler"]()
    _stub_processing(handler)
    raws = ws / "raws"
    batch = raws / "b"
    _write(batch / "solo.csv", "solo\n")
    _flatten_sync(handler, str(batch))
    assert (raws / "solo.csv").exists()  # unique name is NOT prefixed

    # Claim set: even if the first mover's raws/ path no longer exists (already
    # archived), a same-named sibling must not reuse the plain name.
    dest = handler._resolve_flatten_dest(str(raws), ["c"], "gone.csv", {"gone.csv"})
    assert os.path.basename(dest) == "c~gone.csv"


def test_prefixed_name_also_taken_falls_back_to_numeric_suffix(flat_env):
    ws, handler = flat_env["make_handler"]()
    raws = ws / "raws"
    _write(raws / "x.csv", "1")
    _write(raws / "d~x.csv", "2")
    dest = handler._resolve_flatten_dest(str(raws), ["d"], "x.csv", set())
    assert os.path.basename(dest) == "d~x~2.csv"


# ---------------------------------------------------------------------------
# Filename conventions: __force__ never fabricated, user(...) prefix survives
# ---------------------------------------------------------------------------

def test_force_token_never_fabricated_by_prefixing(flat_env):
    ws, handler = flat_env["make_handler"]()
    # A folder literally named "force": with "__" separators this would have
    # produced "__force__" (forced reingestion). "~" junctions cannot.
    name = handler._build_collision_name(["batch", "force"], "x.csv")
    assert name == "batch~force~x.csv"
    assert not is_force_reingest(name)
    # A directory name that itself contains the token is neutralized,
    # including re-formation from surrounding underscores.
    name = handler._build_collision_name(["a__force__b"], "x.csv")
    assert not is_force_reingest(name)
    name = handler._build_collision_name(["____force____"], "x.csv")
    assert not is_force_reingest(name)
    # A file whose OWN name carries the token keeps it (user intent preserved).
    name = handler._build_collision_name(["batch"], "report__force__.csv")
    assert is_force_reingest(name)


def test_user_token_hoisted_to_front_on_collision_rename(flat_env):
    ws, handler = flat_env["make_handler"]()
    name = handler._build_collision_name(["batchA", "sub2"], "user(kim)x.csv")
    assert name == "user(kim)batchA~sub2~x.csv"
    assert handler._extract_user_from_filename(name) == "kim"


# ---------------------------------------------------------------------------
# Quiescence: a tree mid-copy must not be flattened half-full
# ---------------------------------------------------------------------------

def test_mid_copy_waits_until_tree_is_stable(flat_env, monkeypatch):
    monkeypatch.setattr(directory_watcher, "FLATTEN_STABILITY_INTERVAL_SECONDS", 0.1)
    ws, handler = flat_env["make_handler"]()
    _stub_processing(handler)
    raws = ws / "raws"
    batch = raws / "copying"
    target = _write(batch / "grow.csv", "start\n")

    stop_at = time.monotonic() + 0.4
    def writer():
        while time.monotonic() < stop_at:
            with open(target, "a", encoding="utf-8") as f:
                f.write("more-data\n")
            time.sleep(0.03)
    w = threading.Thread(target=writer)
    w.start()
    t0 = time.monotonic()
    _flatten_sync(handler, str(batch))
    elapsed = time.monotonic() - t0
    w.join()

    # Flatten only completed after the writer went quiet...
    assert elapsed >= 0.35
    assert not batch.exists()
    # ...and the moved file carries the COMPLETE content (no half-full flatten).
    content = (raws / "grow.csv").read_text()
    assert content.startswith("start\n") and content.endswith("more-data\n")
    # The old path was never recreated by a post-move write (quiescence held).
    assert not os.path.exists(target)


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
            _flatten_sync(handler, str(batch))
    finally:
        stop.set()
        w.join()

    assert batch.exists() and os.path.exists(target)  # untouched
    assert calls == []                                # nothing dispatched
    assert any("Flatten deferred" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Locked file: directory preserved + warning; retry completes after unlock
# ---------------------------------------------------------------------------

@pytest.mark.skipif(os.name != "nt", reason="open-handle rename lock is a Windows semantic")
def test_locked_file_preserves_directory_then_retry_completes(flat_env, caplog):
    ws, handler = flat_env["make_handler"]()
    calls = _stub_processing(handler)
    raws = ws / "raws"
    batch = raws / "batch"
    locked = _write(batch / "sub" / "locked.csv", "locked\n")
    _write(batch / "sub2" / "free.csv", "free\n")

    fh = open(locked, "r")
    try:
        with caplog.at_level("WARNING"):
            _flatten_sync(handler, str(batch))
        # Movable file was promoted and dispatched; locked one stayed put.
        assert (raws / "free.csv").exists()
        assert calls == ["free.csv"]
        assert os.path.exists(locked)
        assert (batch / "sub").exists()      # never delete a dir containing anything
        assert not (batch / "sub2").exists()  # emptied branch IS removed
        assert any("Flatten incomplete" in r.message for r in caplog.records)
        assert any("cannot move" in r.message for r in caplog.records)
    finally:
        fh.close()

    # Periodic-sweep semantics: a later trigger finishes the job.
    _flatten_sync(handler, str(batch))
    assert not batch.exists()
    assert (raws / "locked.csv").exists()
    assert calls == ["free.csv", "locked.csv"]


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

    _flatten_sync(handler, str(batch))

    assert not batch.exists()
    assert sorted(os.listdir(raws)) == ["real.csv"]
    assert calls == ["real.csv"]  # junk never dispatched to the parser


# ---------------------------------------------------------------------------
# Config knob (ingestion_settings.json, hot, default ON)
# ---------------------------------------------------------------------------

def test_flatten_disabled_by_setting_leaves_directory_alone(flat_env):
    flat_env["settings_path"].write_text('{"flatten_nested_dirs": false}', encoding="utf-8")
    ws, handler = flat_env["make_handler"]()
    raws = ws / "raws"
    batch = raws / "batch"
    _write(batch / "a.csv", _csv(1))

    assert handler.request_flatten(str(batch)) is None
    assert batch.exists() and (batch / "a.csv").exists()

    # Hot semantics: removing the off-switch re-enables on the NEXT trigger.
    flat_env["settings_path"].write_text('{"flatten_nested_dirs": true}', encoding="utf-8")
    _stub_processing(handler)
    _flatten_sync(handler, str(batch))
    assert not batch.exists()


# ---------------------------------------------------------------------------
# Idempotency / re-entrancy and trigger scoping
# ---------------------------------------------------------------------------

def test_second_trigger_on_same_tree_is_noop_while_in_flight(flat_env, monkeypatch):
    monkeypatch.setattr(directory_watcher, "FLATTEN_STABILITY_INTERVAL_SECONDS", 0.3)
    ws, handler = flat_env["make_handler"]()
    _stub_processing(handler)
    raws = ws / "raws"
    batch = raws / "batch"
    _write(batch / "a.csv", "a\n")

    t1 = handler.request_flatten(str(batch))
    assert t1 is not None
    assert handler.request_flatten(str(batch)) is None  # guarded: in flight
    t1.join(20)
    assert not batch.exists()
    # After completion the guard is released; a stale trigger is a safe no-op
    # (directory no longer exists).
    assert handler.request_flatten(str(batch)) is None


def test_request_flatten_rejects_non_direct_children_and_files(flat_env):
    ws, handler = flat_env["make_handler"]()
    raws = ws / "raws"
    f = _write(raws / "plain.csv", "x")
    assert handler.request_flatten(f) is None                    # not a dir
    assert handler.request_flatten(str(ws / "archives")) is None  # outside raws/
    nested = raws / "a" / "b"
    nested.mkdir(parents=True)
    assert handler.request_flatten(str(nested)) is None  # not a DIRECT child


# ---------------------------------------------------------------------------
# Sweep integration: startup/periodic sweep triggers flatten for directories
# ---------------------------------------------------------------------------

def test_sweep_triggers_flatten_for_directories(flat_env, monkeypatch):
    ws, handler = flat_env["make_handler"]()
    swept = _stub_processing(handler)
    raws = ws / "raws"
    batch = raws / "batch"
    _write(batch / "nested.csv", "n\n")
    _write(raws / "direct.csv", "d\n")

    ww = WorkspaceWatcher(base_dir=str(flat_env["tmp_path"]))
    ww.handlers_by_raw_path[os.path.abspath(str(raws))] = handler

    requested = []
    monkeypatch.setattr(handler, "request_flatten", lambda p: requested.append(os.path.abspath(p)))
    processed = ww.sweep_existing_files()

    assert requested == [os.path.abspath(str(batch))]  # dir -> flatten trigger
    assert processed == 1 and swept == ["direct.csv"]  # file -> normal sweep


# ---------------------------------------------------------------------------
# Heavy lane: a big file inside a folder still routes by size AFTER flattening
# ---------------------------------------------------------------------------

class _RecordingLane:
    def __init__(self):
        self.jobs = []

    def submit(self, job):
        self.jobs.append(job)


def test_heavy_file_in_folder_routes_to_heavy_lane_after_flatten(flat_env):
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

    _flatten_sync(handler, str(batch))

    assert not batch.exists()
    # Lane classification ran on the FLATTENED paths.
    assert handler._classify_lane(str(raws / "big.csv"))[0] == "heavy"
    assert handler._classify_lane(str(raws / "tiny.csv"))[0] == "normal"
    # big.csv (older mtime, dispatched first) was queued to the heavy lane; the
    # follower tiny.csv also went to the queue tail because the workspace-order
    # FIFO invariant holds while heavy backlog is nonzero (fake lane never runs).
    assert len(lane.jobs) == 2
    assert small_calls == []
    assert (raws / "big.csv").exists() and (raws / "tiny.csv").exists()
