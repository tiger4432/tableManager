"""[Tier 1, hoisted] The sweep asks the ledger about MANY files, ONCE, with the
stat it already holds — and clears exactly the same set it cleared before.

Why this file exists
--------------------
The tier-1 lookup worked, but it lived one dispatch deeper than the information
it needs. `sweep_existing_files` already holds the `os.stat` of every file it is
looking at; `_try_path_stat_skip` re-derived it inside `_process_with_retry`,
after a `SessionLocal()` per file and after `_snapshot_table_context()` re-read
`table_config.json` from disk per file. Measured on this box: ~92 ms per tier-1
HIT, ≈35 min over a 22,626-file tree, once per process restart. None of it was
the ledger.

🔴 What this file is actually guarding is not speed. A batched lookup fails
SILENTLY: it can clear a file it should not have, and that file is then never
ingested and nobody is told. So every scenario is checked **by name** — which
files were dispatched, which were read from disk, which business keys ended up
in the table — and the whole scenario is run TWICE, with the hoist on and with
the hoist off, and the two name sets must be equal. A total that matches while
the membership changed is exactly the failure this project caught in its own
suite baseline today.

Table names use the user-config-impossible `hoist_test_*` prefix (lesson file).
"""

import json
import os
import shutil
import sys
import unittest.mock as mock

import pytest
from sqlalchemy import create_engine, event
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
import ingestion_checkpoint
from directory_watcher import IngestionHandler, WorkspaceWatcher
from database.database import Base
from database import crud, models

TABLE = "hoist_test_parts"
PARTS_INFO = {
    "business_key": "part_no",
    "column_types": {"part_no": "string", "category": "string", "stock_qty": "number"},
    "display_columns": ["part_no", "category", "stock_qty"],
}

def _broken(name: str = "x") -> str:
    """Content the std parser refuses (no business key column) -> FAILED.

    The payload carries the file's name for a reason that cost a debugging round:
    the ledger's unique key is `(table_name, file_signature)`, so two files with
    byte-identical content share ONE row and the second one to be written takes
    the `filepath` with it. Two broken files with the same bytes therefore leave
    only one of them findable by tier 1 — a property of the ledger, not of the
    batch, but one that will silently rewrite any fixture that ignores it.
    """
    return f"nothing,here\n{os.path.splitext(os.path.basename(name))[0]},2\n"


def _csv_for(name: str, n: int = 2) -> str:
    """Content whose BUSINESS KEYS carry the file's own name.

    So "which files were ingested" is answerable from the table itself, by name,
    instead of from a count that cannot tell one file from another.
    """
    stem = os.path.splitext(os.path.basename(name))[0]
    lines = ["part_no,category,stock_qty"]
    lines += [f"{stem}#{i},Cap,{i}" for i in range(1, n + 1)]
    return "\n".join(lines) + "\n"


def _write(path, text):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return str(path)


@pytest.fixture
def env(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    table_config = {TABLE: dict(PARTS_INFO)}
    models.init_dynamic_models(table_config)
    crud.TABLE_CONFIG.update(table_config)

    def build_schema():
        Base.metadata.create_all(bind=engine)
        models.sync_dynamic_tables_schema(engine)
        models.ensure_ingestion_checkpoint_table(engine)

    build_schema()

    # Count the MECHANISM, not elapsed time. Elapsed time on a shared box with
    # three other lanes writing the same tree is not evidence; "how many sessions
    # were opened / how many times was table_config.json read / how many SELECTs
    # hit the ledger" is.
    counter = {"sessions": 0, "config_reads": 0, "ledger_selects": 0,
               "tier1_single": 0, "tier1_batch_calls": 0}
    dispatched, hashed = [], []

    @event.listens_for(engine, "after_cursor_execute")
    def _count_ledger_selects(conn, cursor, statement, parameters, context, many):
        if ("file_ingestion_checkpoints" in statement
                and statement.lstrip().upper().startswith("SELECT")):
            counter["ledger_selects"] += 1

    def counting_session(*a, **kw):
        counter["sessions"] += 1
        return TestingSessionLocal(*a, **kw)

    def counting_config():
        counter["config_reads"] += 1
        return table_config

    real_sig = ingestion_checkpoint.compute_file_signature

    def counting_sig(p):
        counter["hashes"] = counter.get("hashes", 0) + 1
        hashed.append(os.path.basename(p))
        return real_sig(p)

    real_single = ingestion_checkpoint.find_terminal_by_path_stat
    real_batch = ingestion_checkpoint.find_terminal_by_path_stat_batch

    def counting_single(*a, **kw):
        counter["tier1_single"] += 1
        return real_single(*a, **kw)

    def counting_batch(*a, **kw):
        counter["tier1_batch_calls"] += 1
        return real_batch(*a, **kw)

    real_handle = IngestionHandler._handle_event

    def recording_handle(self, fp):
        dispatched.append(os.path.basename(fp))
        return real_handle(self, fp)

    monkeypatch.setattr(directory_watcher, "load_global_table_config", counting_config)
    monkeypatch.setattr(directory_watcher, "SessionLocal", counting_session)
    monkeypatch.setattr(directory_watcher, "compute_file_signature", counting_sig)
    monkeypatch.setattr(ingestion_checkpoint, "find_terminal_by_path_stat", counting_single)
    monkeypatch.setattr(ingestion_checkpoint, "find_terminal_by_path_stat_batch", counting_batch)
    monkeypatch.setattr(IngestionHandler, "_handle_event", recording_handle)
    # Tree quiescence: two identical snapshots, taken fast.
    monkeypatch.setattr(directory_watcher, "FLATTEN_STABILITY_INTERVAL_SECONDS", 0.05)
    monkeypatch.setattr(directory_watcher, "FLATTEN_STABILITY_MAX_WAIT_SECONDS", 5.0)

    # 🔴 Isolate the settings file. Reading the operator's real
    # ingestion_settings.json is what makes tests in this tree red on the box they
    # were written on (history 20260813_105852).
    settings_path = tmp_path / "ingestion_settings.json"
    monkeypatch.setattr(directory_watcher, "INGESTION_SETTINGS_PATH", str(settings_path))

    base = tmp_path / "ingestion_workspace"
    ws = base / TABLE
    state = {}

    def settings(**kw):
        settings_path.write_text(json.dumps(kw), encoding="utf-8")

    def zero():
        dispatched.clear()
        hashed.clear()
        for k in list(counter):
            counter[k] = 0

    def reset():
        """Fresh disk + fresh database, so the two arms start from one place."""
        Base.metadata.drop_all(bind=engine)
        build_schema()
        if ws.exists():
            shutil.rmtree(str(ws))
        for sub in ("raws", "archives", "err"):
            (ws / sub).mkdir(parents=True, exist_ok=True)
        handler = IngestionHandler(workspace_path=str(ws), config_path=None,
                                   archives_path=str(ws / "archives"),
                                   default_table_name=TABLE)
        orig = handler.process_with_retry

        def fast(fp, uploader="system", retries=3, delay=1.0):
            return orig(fp, uploader=uploader, retries=retries, delay=0.01)

        handler.process_with_retry = fast
        state["handler"] = handler
        zero()
        return handler

    def observed():
        return {"dispatched": sorted(dispatched), "hashed": sorted(hashed),
                **dict(counter)}

    def sweep():
        """A sweep from a NEWLY CONSTRUCTED watcher = the restart case.

        The in-memory (mtime, size) cache is exactly what makes a LIVE process
        cheap; a restart throws it away, and that is where the 35 minutes was.
        """
        zero()
        ww = WorkspaceWatcher(base_dir=str(base))
        ww.handlers_by_raw_path[os.path.abspath(str(ws / "raws"))] = state["handler"]
        n = ww.sweep_existing_files()
        return {"returned": n, **observed()}

    def tree(dir_path, timeout=30):
        zero()
        t = state["handler"].request_tree_ingest(str(dir_path))
        assert t is not None, "tree ingestion was not started"
        t.join(timeout)
        assert not t.is_alive(), "tree ingestion worker did not finish in time"
        return observed()

    yield {"engine": engine, "SessionLocal": TestingSessionLocal, "ws": ws,
           "base": base, "raws": ws / "raws", "settings": settings,
           "reset": reset, "sweep": sweep, "tree": tree, "state": state}
    Base.metadata.drop_all(bind=engine)


def _keys(env):
    """Every business key in the table — i.e. WHICH files are in there, by name."""
    db = env["SessionLocal"]()
    try:
        Model = models.DYNAMIC_TABLES[TABLE]
        return sorted(r.business_key_val for r in db.query(Model).all())
    finally:
        db.close()


def _ledger(env):
    db = env["SessionLocal"]()
    try:
        return sorted((r.filename, r.status)
                      for r in db.query(models.FileIngestionCheckpoint).all())
    finally:
        db.close()


def _hoist_off():
    """The BEFORE arm: the hoist clears nothing, so every file takes the old
    route (`_handle_event` -> `_process_with_retry` -> `_try_path_stat_skip`).
    That route is untouched by this change, which is what makes it a baseline."""
    return mock.patch.object(IngestionHandler, "settle_already_terminal",
                             lambda self, entries: set())


# ---------------------------------------------------------------------------
# The scenario every arm runs: one of each thing a sweep can meet.
# ---------------------------------------------------------------------------

def _build_scenario(env):
    """A prior run, then the six situations the brief names.

    keep_a / keep_b   already DONE, untouched      -> cleared, never dispatched
    changed           already DONE, rewritten      -> re-ingested
    fresh             never seen                   -> ingested
    go__force__       already DONE, force token    -> re-ingested regardless
    broken            already FAILED, untouched    -> stays sealed
    repaired          already FAILED, then fixed   -> ingested
    """
    handler = env["reset"]()
    env["settings"](archive_processed_files=False)
    raws = env["raws"]

    for name in ("keep_a.csv", "keep_b.csv", "changed.csv", "go__force__.csv"):
        _write(raws / name, _csv_for(name))
    _write(raws / "broken.csv", _broken("broken.csv"))
    _write(raws / "repaired.csv", _broken("repaired.csv"))

    env["sweep"]()  # the prior run: every file reaches a terminal answer

    # ...then the world changes underneath us.
    _write(raws / "changed.csv", _csv_for("changed.csv", 5))
    _write(raws / "repaired.csv", _csv_for("repaired.csv"))
    _write(raws / "fresh.csv", _csv_for("fresh.csv"))
    return handler


EXPECTED_DISPATCH = sorted(["changed.csv", "fresh.csv", "go__force__.csv", "repaired.csv"])
CLEARED_NAMES = {"keep_a.csv", "keep_b.csv", "broken.csv"}
EXPECTED_KEYS = sorted(
    [f"keep_a#{i}" for i in (1, 2)]
    + [f"keep_b#{i}" for i in (1, 2)]
    + [f"go__force__#{i}" for i in (1, 2)]
    + [f"changed#{i}" for i in range(1, 6)]
    + [f"fresh#{i}" for i in (1, 2)]
    + [f"repaired#{i}" for i in (1, 2)]
)


def test_the_same_files_are_ingested_before_and_after_by_name(env):
    """🔴 The proof that matters: identical MEMBERSHIP, not an identical count.

    Both arms build the same world from scratch, sweep it from a fresh watcher,
    and are compared by the names of the files dispatched, the names read from
    disk, the business keys in the table, and the ledger rows.
    """
    with _hoist_off():
        _build_scenario(env)
        before = env["sweep"]()
        before_keys, before_ledger = _keys(env), _ledger(env)

    _build_scenario(env)
    after = env["sweep"]()
    after_keys, after_ledger = _keys(env), _ledger(env)

    # What CHANGED is the dispatch list, and only it: before, all seven files
    # walked into `_process_with_retry` to be told three of them were finished.
    assert before["dispatched"] == sorted(EXPECTED_DISPATCH + list(CLEARED_NAMES))
    assert after["dispatched"] == EXPECTED_DISPATCH

    # 🔴 What must NOT change is which files were actually READ and what ended up
    # stored. `hashed` is the honest membership signal: a file only reaches
    # `compute_file_signature` if tier 1 declined to clear it, in either arm.
    assert before["hashed"] == after["hashed"] == EXPECTED_DISPATCH
    assert before_keys == after_keys == EXPECTED_KEYS
    assert before_ledger == after_ledger
    # And the cleared ones really were cleared, not merely absent from a list.
    assert CLEARED_NAMES.isdisjoint(after["dispatched"])
    assert CLEARED_NAMES.isdisjoint(after["hashed"])


def test_the_hoist_is_what_made_it_cheap_and_the_cost_is_not_the_ledger(env):
    """One query for many files, and the per-file dispatch is what disappears."""
    _build_scenario(env)
    after = env["sweep"]()

    assert after["tier1_batch_calls"] == 1, "7 files must cost ONE batched lookup"
    assert after["ledger_selects"] > 0, "the batch must actually query the ledger"
    # The files the batch does NOT clear still ask the single-file question on
    # their own way through the unchanged path. That is the design: nothing was
    # reimplemented, the fast answer just arrives earlier. `__force__` is the one
    # that never asks — it leaves before the ledger is consulted, in both places.
    assert after["tier1_single"] == len(EXPECTED_DISPATCH) - 1 == 3

    _build_scenario(env)
    with _hoist_off():
        without = env["sweep"]()

    assert without["tier1_single"] == 6, "every non-forced file used to ask on its own"
    assert without["sessions"] > after["sessions"]
    assert without["config_reads"] > after["config_reads"]
    # Each cleared file used to pay 2 config reads (`_handle_event`'s
    # `self.table_name` plus `_process_with_retry`'s snapshot); the batch pays 1
    # for all of them.
    assert without["config_reads"] - after["config_reads"] >= 2 * len(CLEARED_NAMES) - 1


def test_an_unchanged_resweep_from_a_fresh_watcher_reads_nothing(env):
    """The restart case itself: same tree, new process, zero file reads."""
    _build_scenario(env)
    env["sweep"]()
    keys_before = _keys(env)

    again = env["sweep"]()
    # `go__force__.csv` is the ONE file that must still be dispatched: the token
    # means "ingest it again" and it is honoured on every sweep, forever. Naming
    # it here rather than removing it from the tree keeps that visible.
    assert again["dispatched"] == ["go__force__.csv"]
    assert again["hashed"] == ["go__force__.csv"], "an unchanged file was re-read"
    assert again["returned"] == 1
    assert again["tier1_batch_calls"] == 1, "one call answered the whole tree"
    assert _keys(env) == keys_before

    # And with the forced file gone, a restart re-sweep touches the disk not at all.
    os.remove(os.path.join(str(env["raws"]), "go__force__.csv"))
    silent = env["sweep"]()
    assert silent["dispatched"] == [] and silent["hashed"] == []
    assert silent["returned"] == 0 and silent["sessions"] == 1
    assert _keys(env) == keys_before


# ---------------------------------------------------------------------------
# 🔴 Fault injection. A batched lookup fails silently, so each way it can be
# wrong is INJECTED and the assertions above are shown to go red.
# ---------------------------------------------------------------------------

def test_fault_batch_clears_everything(env):
    """If the batch cleared every file it was asked about, four files would
    silently never be ingested."""
    _build_scenario(env)
    with mock.patch.object(IngestionHandler, "settle_already_terminal",
                           lambda self, entries: {p for p, _st in entries}):
        broken = env["sweep"]()

    assert broken["dispatched"] != EXPECTED_DISPATCH
    assert broken["dispatched"] == []
    assert _keys(env) != EXPECTED_KEYS
    assert "fresh#1" not in _keys(env), "a brand new file was silently swallowed"
    assert "changed#5" not in _keys(env), "a rewritten file was silently swallowed"


def test_fault_batch_clears_nothing(env):
    """The opposite failure is SAFE for correctness and costs only speed — and
    that asymmetry is the design. Same names, same keys; the counters differ."""
    _build_scenario(env)
    with _hoist_off():
        fell_back = env["sweep"]()

    assert fell_back["dispatched"] == sorted(EXPECTED_DISPATCH + list(CLEARED_NAMES))
    assert fell_back["hashed"] == EXPECTED_DISPATCH, "the same files were read"
    assert _keys(env) == EXPECTED_KEYS, "falling back must not change the result"
    assert fell_back["tier1_single"] == 6, "the old path answered all six non-forced"


def test_fault_batch_ignores_mtime(env):
    """A batch that matches on path alone clears `changed.csv` too — the one case
    tier 1 must never swallow. The stat is in the predicate for this reason."""
    _build_scenario(env)

    def mtime_blind(db, table_name, entries, batch_size=None):
        Model = models.FileIngestionCheckpoint
        wanted = {p for p, _st in entries}
        found = {}
        rows = (db.query(Model)
                .filter(Model.table_name == table_name,
                        Model.status.in_(ingestion_checkpoint.TERMINAL_STATUSES))
                .order_by(Model.updated_at.desc(), Model.id.desc()).all())
        for row in rows:
            if row.filepath in wanted and row.filepath not in found:
                found[row.filepath] = row
        return found

    with mock.patch.object(ingestion_checkpoint, "find_terminal_by_path_stat_batch",
                           mtime_blind):
        blind = env["sweep"]()

    assert "changed.csv" not in blind["dispatched"], "premise: the fault must be active"
    assert _keys(env) != EXPECTED_KEYS
    assert "changed#5" not in _keys(env), "the rewritten file was never re-read"


def test_fault_a_failed_file_is_redispatched(env):
    """FAILED is a TERMINAL answer. A batch that honours only DONE re-dispatches a
    sealed failure on every sweep — the infinite retry the ledger exists to stop
    once files are no longer moved to `err/`."""
    _build_scenario(env)
    with mock.patch.object(ingestion_checkpoint, "TERMINAL_STATUSES",
                           (ingestion_checkpoint.STATUS_DONE,)):
        leaky = env["sweep"]()

    assert "broken.csv" in leaky["dispatched"], "premise: the fault must be active"
    assert "broken.csv" in leaky["hashed"], "the sealed failure was read again"
    assert leaky["dispatched"] != EXPECTED_DISPATCH


# ---------------------------------------------------------------------------
# 🔴 The archive retry. A tier-1 hit is not "do nothing" when files are moved.
# ---------------------------------------------------------------------------

def _fail_the_first_move():
    moves = {"n": 0}
    real_move = directory_watcher.shutil.move

    def failing_move(src, dst):
        moves["n"] += 1
        if moves["n"] == 1:
            raise OSError("simulated locked file")
        return real_move(src, dst)

    return mock.patch.object(directory_watcher.shutil, "move", failing_move)


def test_a_cleared_file_still_retries_a_move_that_failed(env):
    """Fixed only yesterday one level down; the hoist must not reintroduce it.

    A file whose move failed is STILL in raws/ although the ledger already
    concluded about it. If the batch merely walks past it, it — and, for nested
    ingestion, its whole directory — stays in raws/ forever.
    """
    env["reset"]()
    env["settings"]()  # move mode (the default): a stuck file is possible at all
    p = _write(env["raws"] / "stuck.csv", _csv_for("stuck.csv"))

    with _fail_the_first_move():
        env["sweep"]()
        assert os.path.exists(p), "premise: the first move must fail"
        second = env["sweep"]()

    assert second["hashed"] == [], "tier 1 should have cleared it without reading"
    assert second["dispatched"] == [], "it must not take the full path either"
    assert not os.path.exists(p), "the batched hit skipped the move retry"
    assert (env["ws"] / "archives" / "stuck.csv").exists()


def test_a_cleared_failure_still_retries_the_move_to_err(env):
    """Same on the failure side: a sealed FAILED file whose err/ move failed must
    keep being offered to err/, not silently kept in raws/."""
    env["reset"]()
    env["settings"]()
    p = _write(env["raws"] / "bad.csv", _broken("bad.csv"))

    with _fail_the_first_move():
        env["sweep"]()
        assert os.path.exists(p), "premise: the first err-move must fail"
        second = env["sweep"]()

    assert second["hashed"] == []
    assert not os.path.exists(p)
    assert (env["ws"] / "err" / "bad.csv").exists(), "the failure never reached err/"


def test_a_cleared_file_is_not_moved_while_another_thread_owns_it(env):
    """The batch takes the same claim `_handle_event` takes.

    Moving a file out from under the thread that is ingesting it is precisely the
    race `processing_files` exists for, and hoisting the skip out of
    `_handle_event` hoists it out of that guard too — unless it takes it itself.
    """
    env["reset"]()
    env["settings"](archive_processed_files=False)  # conclude it where it lies
    p = _write(env["raws"] / "claimed.csv", _csv_for("claimed.csv"))
    env["sweep"]()
    assert os.path.exists(p)

    handler = env["state"]["handler"]
    env["settings"]()  # now switch to move mode, so a hit owes an archive
    with handler._processing_lock:
        handler.processing_files.add(os.path.abspath(p))
    try:
        env["sweep"]()
        assert os.path.exists(p), "the batch moved a file another thread claimed"
    finally:
        with handler._processing_lock:
            handler.processing_files.discard(os.path.abspath(p))

    env["sweep"]()  # released -> the retry happens on the next sweep
    assert not os.path.exists(p)


# ---------------------------------------------------------------------------
# The escapes must keep working from the new position.
# ---------------------------------------------------------------------------

def test_dedup_by_path_stat_false_disables_the_batch_entirely(env):
    _build_scenario(env)
    env["settings"](archive_processed_files=False, dedup_by_path_stat=False)
    off = env["sweep"]()
    assert off["tier1_batch_calls"] == 0, "the batch ran with tier 1 switched off"
    assert off["dispatched"] == sorted(EXPECTED_DISPATCH + list(CLEARED_NAMES))


def test_dedup_by_signature_false_disables_the_batch_too(env):
    """The global force-reingest switch must not be quietly defeated by a faster
    tier 1 sitting in front of it."""
    _build_scenario(env)
    env["settings"](archive_processed_files=False, dedup_by_signature=False)
    off = env["sweep"]()
    assert off["tier1_batch_calls"] == 0
    assert "keep_a.csv" in off["dispatched"]
    assert "keep_a.csv" in off["hashed"], "the file was not actually re-read"


def test_force_token_leaves_before_the_ledger_is_asked(env):
    _build_scenario(env)
    swept = env["sweep"]()
    assert "go__force__.csv" in swept["dispatched"]
    assert "go__force__.csv" in swept["hashed"], "__force__ was swallowed by the batch"


# ---------------------------------------------------------------------------
# The batch itself: one query per TIER1_BATCH_SIZE, and it picks the same row.
# ---------------------------------------------------------------------------

def test_batching_is_by_size_not_by_file(env):
    env["reset"]()
    env["settings"](archive_processed_files=False)
    for i in range(12):
        name = f"b{i:03d}.csv"
        _write(env["raws"] / name, _csv_for(name))
    env["sweep"]()

    with mock.patch.object(ingestion_checkpoint, "TIER1_BATCH_SIZE", 5):
        chunked = env["sweep"]()
    assert chunked["dispatched"] == []
    # 12 files at 5 per query = 3 SELECTs, in ONE call and ONE session.
    assert chunked["ledger_selects"] == 3
    assert chunked["tier1_batch_calls"] == 1 and chunked["sessions"] == 1

    whole = env["sweep"]()  # default batch size: all 12 in one SELECT
    assert whole["ledger_selects"] == 1 and whole["dispatched"] == []


def test_batch_and_single_lookup_agree_file_by_file(env):
    """The batch is only allowed to be a faster way to ask the SAME question.

    An independent oracle: run the single-file lookup over every file and demand
    the same answer, including WHICH row won when several could match.
    """
    _build_scenario(env)
    raws = str(env["raws"])
    entries = [(os.path.abspath(os.path.join(raws, n)),
                ingestion_checkpoint.read_file_stat(os.path.abspath(os.path.join(raws, n))))
               for n in sorted(os.listdir(raws))]

    db = env["SessionLocal"]()
    try:
        batched = ingestion_checkpoint.find_terminal_by_path_stat_batch(db, TABLE, entries)
        one_at_a_time = {}
        for p, st in entries:
            row = ingestion_checkpoint.find_terminal_by_path_stat(db, TABLE, p, st)
            if row is not None:
                one_at_a_time[p] = row
        assert set(batched) == set(one_at_a_time)
        assert ({p: r.id for p, r in batched.items()}
                == {p: r.id for p, r in one_at_a_time.items()}), \
            "the batch picked a different row than the single-file total order"
    finally:
        db.close()
    assert {os.path.basename(p) for p in batched} == CLEARED_NAMES | {"go__force__.csv"}


def test_a_null_stat_row_never_matches_the_batch(env):
    """The NULL contract, restated for the batched form: rows written before the
    stat columns existed must fall through to full hashing."""
    env["reset"]()
    env["settings"](archive_processed_files=False)
    p = _write(env["raws"] / "a.csv", _csv_for("a.csv"))
    env["sweep"]()

    db = env["SessionLocal"]()
    try:
        row = db.query(models.FileIngestionCheckpoint).one()
        row.file_mtime = None
        row.file_size = None
        db.commit()
    finally:
        db.close()

    swept = env["sweep"]()
    assert swept["dispatched"] == ["a.csv"], "a NULL-stat row matched the batch"
    assert swept["hashed"] == ["a.csv"]
    assert os.path.exists(p)


# ---------------------------------------------------------------------------
# The tree walk pays the same cost for the same reason — every cycle, not once.
# ---------------------------------------------------------------------------

def test_nested_tree_reingestion_is_cleared_by_the_same_batch(env):
    """With files left in place a folder is never emptied, so every periodic
    sweep re-triggers the tree and re-dispatches every file in it. That path has
    no equivalent of the sweep's in-memory cache, so it re-pays EVERY cycle."""
    handler = env["reset"]()
    env["settings"](archive_processed_files=False)
    batch = env["raws"] / "lot42"
    for name in ("n1.csv", "n2.csv"):
        _write(batch / name, _csv_for(name))
    _write(batch / "deep" / "n3.csv", _csv_for("n3.csv"))
    expected = sorted(f"n{k}#{i}" for k in (1, 2, 3) for i in (1, 2))

    first = env["tree"](batch)
    assert first["dispatched"] == ["n1.csv", "n2.csv", "n3.csv"]
    assert _keys(env) == expected

    second = env["tree"](batch)
    assert second["dispatched"] == [], "the tree re-dispatched an unchanged file"
    assert second["hashed"] == [], "the tree re-read an unchanged file"
    assert second["tier1_batch_calls"] == 1 and second["sessions"] == 1
    assert _keys(env) == expected
    assert batch.exists(), "retention mode keeps the tree where it is"

    # ...and a file added to that same tree is still picked up.
    _write(batch / "deep" / "n4.csv", _csv_for("n4.csv"))
    third = env["tree"](batch)
    assert third["dispatched"] == ["n4.csv"]
    assert _keys(env) == sorted(expected + ["n4#1", "n4#2"])


def test_nested_tree_still_archives_and_removes_the_folder_when_moving(env):
    """Move mode is unchanged: the batch clears nothing on a first pass, files
    are archived, and the emptied tree is removed exactly as before."""
    env["reset"]()
    env["settings"]()
    batch = env["raws"] / "lot43"
    _write(batch / "sub" / "m1.csv", _csv_for("m1.csv"))

    env["tree"](batch)
    assert not batch.exists(), "the emptied tree should have been removed"
    assert (env["ws"] / "archives" / "m1.csv").exists()
