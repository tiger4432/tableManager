"""Silent-failure regression tests for the config -> schema path.

Three defects, one theme: the system could fail to apply a schema change, fail
to read its own config, or issue DDL nobody asked for - and say nothing.

  #9   config_watcher handled only `on_modified`. An atomic save (write temp
       file, then rename over the target) is reported by the OS as a MOVE, so
       the ALTER for existing tables was skipped silently. Verified below on the
       PHYSICAL column list, never on `GET /tables/{t}/schema` - that endpoint
       answers from the in-memory config singleton and returns 200 with the new
       column whether or not the database ever heard about it.

  H2   the debounce was LEADING edge: the first event in a 1s window ran and
       every later one was discarded. Two saves 0.3s apart therefore lost the
       second one whole - disk declared three columns, the table had two, the
       log said success. The same rule discarded the completion of a slow
       non-atomic write whose first event arrives while the file is truncated.
       Now trailing edge: every event re-arms, the reload runs after the last.

  H3   a temp file in a DIFFERENT directory renamed onto the config emits
       deleted+created and no `moved` at all (`tempfile.mkstemp()` defaults to
       the system temp dir). With no `on_created` handler nothing ran and
       nothing was logged. Safe to add only because of H2 - under a leading edge
       the truncation-time `created` could win the window.

  H1   the loader decoded with a strict "utf-8", so a UTF-8 BOM - what
       PowerShell 5.1's `Set-Content -Encoding utf8`/`Out-File` and Notepad's
       "UTF-8 with BOM" write by default on this platform - turned a perfectly
       valid config into a boot-blocking parse failure. Combined with #13's
       fail-fast that meant one column added with the wrong editor left the web
       server permanently unable to start on a file that looks right everywhere.

  H5   the loader returned whatever json.loads produced, so `[]` reached
       init_dynamic_models, died on AttributeError, was caught by main's broad
       handler, and the server booted with ZERO dynamic models behind one ERROR
       line - the exact failure #13 exists to abolish. `null` was worse:
       TABLE_CONFIG stayed None for the process lifetime.

  H4   chain_ingestion_worker did `from main import to_local_str` inside its
       notification try/except. Importing main runs #13's fail-fast, so a config
       that broke while the system was running made the worker COMMIT rows and
       then silently drop the WebSocket notification.

  #13  crud.load_table_config() returned `{}` on a JSON parse error with no log
       at all. Live, refresh_dynamic_models' empty-config guard absorbs it; on a
       RESTART every table simply vanished, with nothing in the log to say why.

  #16a main.py ran `Base.metadata.create_all(bind=engine)` at MODULE IMPORT, so
       importing the app - which collecting this suite does - issued DDL against
       whatever DATABASE_URL resolved to, production included. The path may not
       be deleted: a fresh install has an empty database and onboarding is "add
       a table to table_config.json -> boot -> use it". So it moved to an
       explicit boot step instead, and both halves are asserted here.

Table names use a `cfgint_` prefix that cannot collide with a real table in the
user's gitignored config (see the server-pm `bonding_log` lesson).
"""

import codecs
import itertools
import json
import logging
import os
import subprocess
import sys
import time

import pytest
from sqlalchemy import create_engine, inspect

from database import crud, models
from database import config_watcher as config_watcher_mod
from database.config_watcher import ConfigChangeHandler, start_config_watcher

from watchdog.events import (
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
)

_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# The reload is trailing-edge debounced (config_watcher.DEBOUNCE_SEC), so every
# assertion about its effect has to wait for the quiet period plus the DDL. Long
# enough to absorb a slow CI box; the tests settle in about a second.
_IDLE_TIMEOUT = 20.0

# Debounce window used by the two "a save inside the window must not be lost"
# tests. Deliberately larger than production's 1.0s: the interval between the two
# writes scales with it, and a wider window is what makes the defect axis
# (event #2 arriving while the window is still open) reliably ACTIVE despite
# watchdog delivery latency. See the docstring on the first of those tests.
_SCALED_DEBOUNCE = 3.0

# One fresh table name per test. init_dynamic_models hot-swaps new columns onto
# the LIVE Table object in the process-wide Base.metadata, so a shared name would
# arrive at the second test already carrying the column the first test added -
# i.e. with the defect axis switched off, passing while proving nothing.
_table_seq = itertools.count()


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _config_with(table_name: str, columns: dict) -> dict:
    """Current TABLE_CONFIG plus one table declared with `columns`.

    Mirrors the real file: the watcher replaces the whole config, so a partial
    config would wipe every other table out of the singleton for the rest of the
    test (the same shape test_runtime_table_create.py uses).
    """
    cfg = {k: dict(v) for k, v in crud.TABLE_CONFIG.items()}
    cfg[table_name] = {"business_key": "lot_id", "column_types": dict(columns)}
    return cfg


def _write_json(path: str, payload: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _atomic_write_json(path: str, payload: dict):
    """Save the way an editor/agent saves: temp file in the same dir, then rename.

    This is the exact write pattern that produced the silent miss. Confirmed on
    this platform (watchdog 6.0.0 / Windows) to emit created+modified for the
    temp path, deleted for the target, and finally MOVED temp -> target. There is
    no `modified` event on the target at all, which is why an on_modified-only
    handler never woke up.
    """
    tmp = path + ".tmp"
    _write_json(tmp, payload)
    os.replace(tmp, path)


def _physical_columns(engine, table_name: str) -> set:
    # A fresh Inspector every call - a reused one caches get_columns() and would
    # happily report the pre-ALTER column list forever.
    return {c["name"] for c in inspect(engine).get_columns(table_name)}


def _stop_watcher(observer):
    """Tear a started watcher down without leaving an armed reload behind.

    The debounce fires on a `threading.Timer`, which `observer.stop()` does not
    know about. A leftover timer would run DDL against this test's disposed
    engine some time inside the NEXT test.
    """
    handler = getattr(observer, "config_handler", None)
    if handler is not None:
        handler.cancel_pending()
    observer.stop()
    observer.join(timeout=5)
    if handler is not None:
        handler.cancel_pending()  # an event delivered during stop() can re-arm
        handler.wait_for_idle(timeout=5)


@pytest.fixture(autouse=True)
def _isolate_table_config():
    """Restore the process-wide config singleton around every test in this file.

    `ConfigChangeHandler._reload` does `crud.TABLE_CONFIG.clear()` followed by
    `.update(...)` on the ONE dict the whole suite shares. Every test here
    triggers that on purpose, so without this fixture a test in this file
    silently redefines what tests in other files see - and, because the reload is
    debounced onto a timer thread, it can do so at an arbitrary later moment.
    That is exactly the shape of bug that makes a suite answer differently
    depending on order.
    """
    saved = {k: (dict(v) if isinstance(v, dict) else v) for k, v in crud.TABLE_CONFIG.items()}
    yield
    crud.TABLE_CONFIG.clear()
    crud.TABLE_CONFIG.update(saved)


@pytest.fixture
def make_handler():
    """Build handlers that cannot outlive the test that made them.

    The trailing-edge debounce fires on a `threading.Timer`. A handler dropped on
    the floor with a timer armed will run DDL - and clobber the config singleton -
    some time inside a LATER test. Every handler in this file comes from here so
    that cannot happen by omission.
    """
    created = []

    def _make(engine=None):
        handler = ConfigChangeHandler(engine=engine)
        created.append(handler)
        return handler

    yield _make
    for handler in created:
        handler.cancel_pending()
        handler.wait_for_idle(timeout=10)


@pytest.fixture
def alter_target(tmp_path):
    """A throwaway file-backed database plus one physically-created table.

    Deliberately NOT the suite's shared in-memory engine: the watcher runs its
    ALTER on its own thread, and a StaticPool in-memory engine would have that
    thread and the fixture's session sharing a single sqlite connection.

    Yields `(engine, table_name)`.
    """
    table_name = f"cfgint_alter_{next(_table_seq)}"
    db_path = tmp_path / "alter_probe.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")

    models.init_dynamic_models({
        table_name: {"business_key": "lot_id", "column_types": {"lot_id": "string"}}
    })
    models.Base.metadata.create_all(
        bind=engine, tables=[models.DYNAMIC_TABLES[table_name].__table__], checkfirst=True
    )

    cols = _physical_columns(engine, table_name)
    assert "lot_id" in cols, "fixture failed to create the target table"
    # The defect axis must start INACTIVE. If `qty` were already present an
    # ALTER-less run would pass and prove nothing - which is exactly how a stale
    # fixture turns a regression test into a rubber stamp.
    assert "qty" not in cols

    yield engine, table_name
    engine.dispose()
    # Take this test's table back out of the process-wide registries. Every test
    # here adds one, `init_dynamic_models` never removes anything, and
    # models.DYNAMIC_TABLES / Base.metadata are shared with the entire suite - so
    # without this the rest of the run carries a growing set of tables whose
    # physical counterpart exists only in a tmp database that is already gone.
    dynamic_class = models.DYNAMIC_TABLES.pop(table_name, None)
    if dynamic_class is not None and table_name in models.Base.metadata.tables:
        models.Base.metadata.remove(dynamic_class.__table__)


# --------------------------------------------------------------------------
# INV-9-1 - an atomic save reaches the PHYSICAL schema
# --------------------------------------------------------------------------

def test_inv_9_1_atomic_save_event_applies_physical_alter(alter_target, make_handler, tmp_path, monkeypatch):
    """A move event for table_config.json must produce a real ALTER.

    Dispatched through `handler.dispatch()` rather than by calling on_moved
    directly, so the test also covers the wiring watchdog actually uses
    (event_type -> `on_<event_type>`): removing the handler method makes this
    test fail, which is the point.
    """
    engine, table_name = alter_target
    cfg_path = tmp_path / "table_config.json"
    monkeypatch.setattr(crud, "CONFIG_PATH", str(cfg_path))
    _write_json(str(cfg_path), _config_with(table_name, {"lot_id": "string", "qty": "number"}))

    handler = make_handler(engine=engine)
    handler.dispatch(FileMovedEvent(str(tmp_path / "table_config.json.tmp"), str(cfg_path)))
    assert handler.wait_for_idle(timeout=_IDLE_TIMEOUT), "debounced reload never ran"

    assert "qty" in _physical_columns(engine, table_name), (
        "atomic save (temp+rename) did not reach the physical schema"
    )


def test_h3_cross_directory_replace_applies_physical_alter(alter_target, make_handler, tmp_path, monkeypatch):
    """deleted+created (no `moved`) must still reach the physical schema.

    `os.replace` only reports a MOVE when source and destination sit in the same
    directory. A temp file built anywhere else - which is what
    `tempfile.mkstemp()` gives you by default - arrives as deleted followed by
    created, and an on_moved/on_modified-only handler runs nothing and logs
    nothing. Deleting `on_created` from the handler makes this fail.
    """
    engine, table_name = alter_target
    cfg_path = tmp_path / "table_config.json"
    monkeypatch.setattr(crud, "CONFIG_PATH", str(cfg_path))
    _write_json(str(cfg_path), _config_with(table_name, {"lot_id": "string", "qty": "number"}))

    handler = make_handler(engine=engine)
    handler.dispatch(FileDeletedEvent(str(cfg_path)))
    handler.dispatch(FileCreatedEvent(str(cfg_path)))
    assert handler.wait_for_idle(timeout=_IDLE_TIMEOUT), "debounced reload never ran"

    assert "qty" in _physical_columns(engine, table_name), (
        "a cross-directory atomic replace (deleted+created, no moved) was ignored"
    )


def test_h3_cross_directory_replace_through_real_watchdog(alter_target, tmp_path, monkeypatch):
    """Same shape, but let the OS produce the events instead of the test.

    Without this the fix would rest on an assumption about which events a
    cross-device-style replace emits on this platform.
    """
    engine, table_name = alter_target
    cfg_dir = tmp_path / "cfg"
    other_dir = tmp_path / "elsewhere"
    cfg_dir.mkdir()
    other_dir.mkdir()
    cfg_path = cfg_dir / "table_config.json"
    monkeypatch.setattr(crud, "CONFIG_PATH", str(cfg_path))
    _write_json(str(cfg_path), _config_with(table_name, {"lot_id": "string"}))

    observer = start_config_watcher(engine)
    try:
        time.sleep(0.5)  # let the OS watch take effect before the write
        staged = other_dir / "staged.json"
        _write_json(str(staged), _config_with(table_name, {"lot_id": "string", "qty": "number"}))
        os.replace(str(staged), str(cfg_path))

        deadline = time.time() + _IDLE_TIMEOUT
        while time.time() < deadline:
            if "qty" in _physical_columns(engine, table_name):
                break
            time.sleep(0.25)
    finally:
        _stop_watcher(observer)

    assert "qty" in _physical_columns(engine, table_name), (
        "a config staged outside the watched directory never reached the schema"
    )


# --------------------------------------------------------------------------
# H2 - the debounce must coalesce a burst, never discard a save
# --------------------------------------------------------------------------

def test_h2_second_save_within_the_debounce_window_is_not_lost(alter_target, tmp_path, monkeypatch):
    """QA reproduction (a): two atomic saves inside one debounce window.

    The leading-edge debounce ran the first and threw the second away whole. The
    invariant is not "two reloads happened" - a trailing edge legitimately
    coalesces them into one - it is that when the dust settles the PHYSICAL
    columns match what the file on disk declares. Agent edit tools write the
    same file twice in a row routinely, so this is the common case, not a corner.

    The window and the interval are BOTH scaled x3 from QA's literal 0.3s/1.0s,
    preserving the ratio. At the literal numbers the outcome depends on
    watchdog's event-delivery latency, which measured longer than 0.3s here: the
    first reload then happens to read the file after the second write had already
    landed, so the test passed with the defect fully present - a rubber stamp.
    Scaled up, the first event is certainly delivered and read before write #2,
    and restoring `if now - self.last_triggered < DEBOUNCE_SEC: return` fails
    this test with `qty2` missing.
    """
    engine, table_name = alter_target
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir()
    cfg_path = cfg_dir / "table_config.json"
    monkeypatch.setattr(crud, "CONFIG_PATH", str(cfg_path))
    monkeypatch.setattr(config_watcher_mod, "DEBOUNCE_SEC", _SCALED_DEBOUNCE)
    _write_json(str(cfg_path), _config_with(table_name, {"lot_id": "string"}))

    observer = start_config_watcher(engine)
    try:
        time.sleep(0.5)
        _atomic_write_json(
            str(cfg_path),
            _config_with(table_name, {"lot_id": "string", "qty": "number"}),
        )
        # Well inside the window, but late enough that save #1 has certainly been
        # delivered AND read - otherwise the defect axis is switched off.
        time.sleep(_SCALED_DEBOUNCE / 3.0)
        _atomic_write_json(
            str(cfg_path),
            _config_with(table_name, {"lot_id": "string", "qty": "number", "qty2": "number"}),
        )

        deadline = time.time() + _IDLE_TIMEOUT + _SCALED_DEBOUNCE
        while time.time() < deadline:
            if {"qty", "qty2"} <= _physical_columns(engine, table_name):
                break
            time.sleep(0.25)
    finally:
        _stop_watcher(observer)

    cols = _physical_columns(engine, table_name)
    assert {"qty", "qty2"} <= cols, (
        f"a save inside the debounce window was discarded: physical={sorted(cols)}, "
        f"disk declares lot_id/qty/qty2"
    )


def test_h2_slow_nonatomic_write_completion_is_not_discarded(alter_target, make_handler, tmp_path, monkeypatch):
    """QA reproduction (b): the first event sees a truncated file.

    A plain `open(w)` - which is what `crud.update_table_config` does, so this is
    the product's own write path - truncates first and finishes later. Under a
    leading edge the handler read partial JSON, aborted, and then discarded the
    `modified` that meant "finished", leaving the system on the old schema with a
    success-shaped log. Under a trailing edge the truncation event only re-arms.

    Driven through `dispatch()` so the interleaving is exact rather than a race:
    with the old code the first dispatch reloads synchronously (partial JSON ->
    abort) and the second is swallowed by the window.
    """
    engine, table_name = alter_target
    cfg_path = tmp_path / "table_config.json"
    monkeypatch.setattr(crud, "CONFIG_PATH", str(cfg_path))
    monkeypatch.setattr(config_watcher_mod, "DEBOUNCE_SEC", _SCALED_DEBOUNCE)
    complete = _config_with(table_name, {"lot_id": "string", "qty": "number"})

    handler = make_handler(engine=engine)

    # 1. writer truncates and flushes half the document -> `modified`
    cfg_path.write_text(json.dumps(complete)[: len(json.dumps(complete)) // 2], encoding="utf-8")
    handler.dispatch(FileModifiedEvent(str(cfg_path)))

    # 2. writer finishes, well inside the debounce window -> `modified`
    _write_json(str(cfg_path), complete)
    handler.dispatch(FileModifiedEvent(str(cfg_path)))

    assert handler.wait_for_idle(timeout=_IDLE_TIMEOUT), "debounced reload never ran"
    assert "qty" in _physical_columns(engine, table_name), (
        "the completion of a slow non-atomic write was discarded by the debounce"
    )


def test_inv_9_1_atomic_save_through_real_watchdog(alter_target, tmp_path, monkeypatch):
    """End-to-end: a real Observer, a real os.replace, a real ALTER.

    The unit test above proves the handler acts on a move event; this one proves
    the OS actually delivers a move event for the way files really get saved.
    Without it the fix would rest on an assumption about the platform.
    """
    engine, table_name = alter_target
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir()
    cfg_path = cfg_dir / "table_config.json"
    monkeypatch.setattr(crud, "CONFIG_PATH", str(cfg_path))
    _write_json(str(cfg_path), _config_with(table_name, {"lot_id": "string"}))

    observer = start_config_watcher(engine)
    try:
        time.sleep(0.5)  # let the OS watch take effect before the write
        _atomic_write_json(
            str(cfg_path),
            _config_with(table_name, {"lot_id": "string", "qty": "number"}),
        )

        deadline = time.time() + _IDLE_TIMEOUT
        while time.time() < deadline:
            if "qty" in _physical_columns(engine, table_name):
                break
            time.sleep(0.25)
    finally:
        _stop_watcher(observer)

    assert "qty" in _physical_columns(engine, table_name), (
        "an atomically-saved table_config.json never reached the physical schema"
    )


# --------------------------------------------------------------------------
# INV-9-2 - a reload that cannot be applied says so
# --------------------------------------------------------------------------

def test_inv_9_2_unusable_config_is_logged_not_skipped(alter_target, make_handler, tmp_path, monkeypatch, caplog):
    """An unparsable config must not be absorbed by a falsy check.

    The old handler read `if new_config:` and fell off the end when it was empty.
    Nothing was applied and nothing was logged, so the operator's evidence for
    "my column never appeared" was an empty log.
    """
    engine, table_name = alter_target
    cfg_path = tmp_path / "table_config.json"
    monkeypatch.setattr(crud, "CONFIG_PATH", str(cfg_path))
    cfg_path.write_text('{"%s": {' % table_name, encoding="utf-8")

    handler = make_handler(engine=engine)
    with caplog.at_level(logging.ERROR, logger="Watcher.ConfigWatcher"):
        handler.dispatch(FileModifiedEvent(str(cfg_path)))
        assert handler.wait_for_idle(timeout=_IDLE_TIMEOUT), "debounced reload never ran"

    watcher_errors = [
        r for r in caplog.records
        if r.name == "Watcher.ConfigWatcher" and r.levelno >= logging.ERROR
    ]
    assert watcher_errors, "config reload failed silently - no ERROR from the watcher"
    assert str(cfg_path) in " ".join(r.getMessage() for r in watcher_errors)


# --------------------------------------------------------------------------
# INV-13-1 - a parse failure is logged with path and position
# --------------------------------------------------------------------------

def test_inv_13_1_parse_failure_logs_path_and_position(tmp_path, monkeypatch, caplog):
    """`load_table_config()` may still return {} at runtime, but never quietly.

    Returning {} is what keeps a transient read failure from wiping the live
    singleton (refresh_dynamic_models' guard). The log line is what turns "every
    table disappeared" into "line 3 column 5 of this file".
    """
    cfg_path = tmp_path / "table_config.json"
    cfg_path.write_text('{\n  "a": {},\n  "b": \n}', encoding="utf-8")
    monkeypatch.setattr(crud, "CONFIG_PATH", str(cfg_path))

    with caplog.at_level(logging.ERROR):
        assert crud.load_table_config() == {}

    errors = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    joined = " ".join(errors)
    assert errors, "a corrupt table_config.json was swallowed without a log"
    assert str(cfg_path) in joined, f"log names no file path: {joined}"
    assert "line" in joined.lower() and "column" in joined.lower(), (
        f"log names no parse position: {joined}"
    )


def test_inv_13_1_missing_file_is_not_an_error(tmp_path, monkeypatch, caplog):
    """Scope guard: absent != corrupt.

    A fresh install has no table_config.json yet. Logging that as an error - or
    failing fast on it - would make first boot look broken.
    """
    monkeypatch.setattr(crud, "CONFIG_PATH", str(tmp_path / "nope.json"))
    with caplog.at_level(logging.ERROR):
        assert crud.load_table_config() == {}
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


# --------------------------------------------------------------------------
# INV-13-2 - boot refuses to come up on a corrupt config
# --------------------------------------------------------------------------

def test_inv_13_2_strict_loader_raises_on_parse_failure(tmp_path, monkeypatch):
    cfg_path = tmp_path / "table_config.json"
    cfg_path.write_text("{ not json at all", encoding="utf-8")
    monkeypatch.setattr(crud, "CONFIG_PATH", str(cfg_path))

    with pytest.raises(crud.TableConfigError) as exc:
        crud.load_table_config_or_raise()
    msg = str(exc.value)
    assert str(cfg_path) in msg
    assert "line" in msg.lower() and "column" in msg.lower()


def test_inv_13_2_semantically_odd_config_still_boots(tmp_path, monkeypatch):
    """Scope guard, and the more important half of #13.

    Fail-fast is limited to "this file is not JSON". A config that parses but
    declares something strange must still boot: a production server refusing to
    start over a semantic complaint is a bigger outage than the complaint.
    """
    cfg_path = tmp_path / "table_config.json"
    cfg_path.write_text(
        '{"cfgint_weird": {"business_key": "", "column_types": {}, "unknown_key": 1}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(crud, "CONFIG_PATH", str(cfg_path))

    cfg = crud.load_table_config_or_raise()
    assert "cfgint_weird" in cfg


# --------------------------------------------------------------------------
# H1 - a BOM is an encoding marker, not corruption
# --------------------------------------------------------------------------

_H1_DOC = {"cfgint_bom": {"business_key": "k", "column_types": {"k": "string", "값": "string"}}}


@pytest.mark.parametrize("encoding,label", [
    ("utf-8-sig", "UTF-8 BOM (PowerShell 5.1 Set-Content -Encoding utf8 / Out-File, Notepad)"),
    ("utf-16", "UTF-16 with native BOM (PowerShell 5.1 `>` redirect)"),
    ("utf-16-le", "UTF-16 LE"),
    ("utf-16-be", "UTF-16 BE"),
    ("utf-32", "UTF-32 with native BOM"),
])
def test_h1_bom_encodings_load(tmp_path, monkeypatch, encoding, label):
    """A valid config written by a normal Windows tool must load.

    This is not tolerance for malformed input - it is reading the file in the
    encoding it was written in. The measured failure was worse than a bad error
    message: the strict `utf-8` decode raised, #13's fail-fast turned that into a
    refusal to boot, and the operator saw a file that every editor renders
    perfectly next to a web server that will not come up again.

    UTF-16 LE/BE are written WITH their BOMs on purpose (Python's `utf-16` codec
    emits one; the explicit -le/-be codecs do not), because the BOM is the only
    thing that tells the loader what it is looking at.
    """
    cfg_path = tmp_path / "table_config.json"
    text = json.dumps(_H1_DOC, ensure_ascii=False)
    if encoding in ("utf-16-le", "utf-16-be"):
        bom = codecs.BOM_UTF16_LE if encoding == "utf-16-le" else codecs.BOM_UTF16_BE
        cfg_path.write_bytes(bom + text.encode(encoding))
    else:
        cfg_path.write_bytes(text.encode(encoding))
    monkeypatch.setattr(crud, "CONFIG_PATH", str(cfg_path))

    cfg = crud.load_table_config_or_raise()
    assert "cfgint_bom" in cfg, f"{label} config was rejected"
    # The BOM must be consumed, not smuggled into the first key.
    assert list(cfg.keys()) == ["cfgint_bom"], f"{label}: BOM leaked into the key"
    assert "값" in cfg["cfgint_bom"]["column_types"], f"{label}: non-ASCII column mangled"


def test_h1_bom_config_still_boots(tmp_path):
    """The headline symptom, measured on a real boot: BOM config, server starts.

    The unit test above proves the loader; this proves the thing the operator
    actually experiences. Reverting the decode to `raw.decode("utf-8")` makes
    this fail with a non-zero exit and TableConfigError.
    """
    data_root = tmp_path / "data"
    (data_root / "config").mkdir(parents=True)
    (data_root / "config" / "table_config.json").write_bytes(
        codecs.BOM_UTF8 + json.dumps({
            "cfgint_bom_boot": {"business_key": "k", "column_types": {"k": "string"}}
        }).encode("utf-8")
    )

    proc = subprocess.run(
        [sys.executable, "-c", _BOOT_PROBE],
        cwd=_SERVER_DIR, env=_probe_env(data_root),
        capture_output=True, text=True, timeout=180,
    )
    assert proc.returncode == 0, (
        f"a BOM-prefixed but perfectly valid table_config.json blocked boot\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    assert "BOOTED" in proc.stdout


def test_h1_non_utf8_without_bom_is_still_rejected(tmp_path, monkeypatch):
    """Scope guard: accepting BOMs must not mean accepting any byte soup.

    A cp949-encoded file with no BOM is genuinely mis-encoded and there is no
    marker to read it by. It must still raise, or the BOM fix would have quietly
    widened the loader into "decode with errors='replace'".
    """
    cfg_path = tmp_path / "table_config.json"
    cfg_path.write_bytes(
        json.dumps({"cfgint_cp949": {"컬럼": "값"}}, ensure_ascii=False).encode("cp949")
    )
    monkeypatch.setattr(crud, "CONFIG_PATH", str(cfg_path))

    with pytest.raises(crud.TableConfigError) as exc:
        crud.load_table_config_or_raise()
    assert "byte offset" in str(exc.value), f"decode failure lost its position: {exc.value}"


def test_h1_empty_file_is_a_parse_failure(tmp_path, monkeypatch):
    """A zero-byte config is truncation, not "no tables declared".

    Documented rather than changed: an empty file cannot be distinguished from a
    half-finished write, and #13's whole point is that coming up with zero tables
    is the worst available outcome.
    """
    cfg_path = tmp_path / "table_config.json"
    cfg_path.write_bytes(b"")
    monkeypatch.setattr(crud, "CONFIG_PATH", str(cfg_path))

    with pytest.raises(crud.TableConfigError):
        crud.load_table_config_or_raise()


# --------------------------------------------------------------------------
# H5 - JSON that is not an object is a parse-level failure, not a nitpick
# --------------------------------------------------------------------------

@pytest.mark.parametrize("body,described", [
    ("[]", "list"),
    ("null", "NoneType"),
    ('"just a string"', "str"),
    ("42", "int"),
])
def test_h5_non_object_toplevel_raises(tmp_path, monkeypatch, body, described):
    """`[]` used to sail through the boot gate and produce zero dynamic models.

    Measured: init_dynamic_models([]) raised AttributeError, main's broad
    `except Exception` caught it, and the server booted with an empty schema and
    one ERROR line - the UI looks wiped, the log looks nearly clean. `null` left
    TABLE_CONFIG as None for the whole process lifetime.

    A top-level type check is not a semantic complaint about a declaration; it is
    "this document is not a table map", which is the same class of failure as
    unparsable bytes.
    """
    cfg_path = tmp_path / "table_config.json"
    cfg_path.write_text(body, encoding="utf-8")
    monkeypatch.setattr(crud, "CONFIG_PATH", str(cfg_path))

    with pytest.raises(crud.TableConfigError) as exc:
        crud.load_table_config_or_raise()
    msg = str(exc.value)
    assert described in msg, f"error does not name the actual top-level type: {msg}"
    assert str(cfg_path) in msg


def test_h5_non_object_toplevel_is_runtime_safe(tmp_path, monkeypatch, caplog):
    """...and the runtime loader still degrades instead of raising into a worker."""
    cfg_path = tmp_path / "table_config.json"
    cfg_path.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(crud, "CONFIG_PATH", str(cfg_path))

    with caplog.at_level(logging.ERROR):
        assert crud.load_table_config() == {}
    assert [r for r in caplog.records if r.levelno >= logging.ERROR], (
        "a non-object table_config was swallowed without a log"
    )


def test_h5_list_config_refuses_to_boot(tmp_path):
    """The boot-level proof: `[]` must stop the server, not empty it out."""
    data_root = tmp_path / "data"
    (data_root / "config").mkdir(parents=True)
    (data_root / "config" / "table_config.json").write_text("[]", encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, "-c", _BOOT_PROBE],
        cwd=_SERVER_DIR, env=_probe_env(data_root),
        capture_output=True, text=True, timeout=180,
    )
    assert proc.returncode != 0, (
        f"server booted on a table_config.json whose top level is a list\n"
        f"STDOUT:\n{proc.stdout}"
    )
    assert "BOOTED" not in proc.stdout
    assert "TableConfigError" in proc.stdout + proc.stderr


# --------------------------------------------------------------------------
# Boot-path probes (subprocess) - INV-13-2, INV-16-1, INV-16-2
# --------------------------------------------------------------------------

def _probe_env(data_root, db_file=None):
    env = os.environ.copy()
    # conftest exports these into THIS process; a child must not inherit them or
    # the probe would measure the test harness instead of a production boot.
    env.pop("TESTING", None)
    env.pop("ASSY_ADMIN_TOKEN", None)
    env["ASSY_DATA_ROOT"] = str(data_root)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PROBE_SERVER_DIR"] = _SERVER_DIR
    if db_file is not None:
        env["DATABASE_URL"] = "sqlite:///" + str(db_file).replace("\\", "/")
        env["PROBE_DB_FILE"] = str(db_file)
    else:
        env["DATABASE_URL"] = "sqlite:///:memory:"
    return env


_DDL_PROBE = """
import json, os, sqlite3, sys
sys.path.insert(0, os.environ["PROBE_SERVER_DIR"])
db_file = os.environ["PROBE_DB_FILE"]

def tables():
    if not os.path.exists(db_file):
        return []
    con = sqlite3.connect(db_file)
    try:
        return sorted(r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall())
    finally:
        con.close()

import main
after_import = tables()
main.bootstrap_database_schema()
after_bootstrap = tables()
print("PROBE_RESULT " + json.dumps(
    {"after_import": after_import, "after_bootstrap": after_bootstrap}))
"""


@pytest.fixture(scope="module")
def ddl_probe(tmp_path_factory):
    """One child process answers both #16 halves: import is inert, boot creates.

    Uses a *file*-backed sqlite database as a stand-in for the production
    database: if importing the app emits any DDL, the file exists and holds
    tables, and there is nowhere for that evidence to hide.
    """
    root = tmp_path_factory.mktemp("ddl_probe")
    data_root = root / "data"
    (data_root / "config").mkdir(parents=True)
    _write_json(str(data_root / "config" / "table_config.json"), {
        "cfgint_fresh_install": {
            "business_key": "lot_id",
            "column_types": {"lot_id": "string", "qty": "number"},
        }
    })
    db_file = root / "prod_stand_in.db"

    proc = subprocess.run(
        [sys.executable, "-c", _DDL_PROBE],
        cwd=_SERVER_DIR, env=_probe_env(data_root, db_file),
        capture_output=True, text=True, timeout=180,
    )
    assert proc.returncode == 0, f"probe failed\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    line = [l for l in proc.stdout.splitlines() if l.startswith("PROBE_RESULT ")]
    assert line, f"probe produced no result\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    return json.loads(line[-1][len("PROBE_RESULT "):])


def test_inv_16_1_importing_the_app_issues_no_ddl(ddl_probe):
    """Importing main must not touch the database it happens to be pointed at."""
    assert ddl_probe["after_import"] == [], (
        f"`import main` created tables at import time: {ddl_probe['after_import']}"
    )


def test_inv_16_2_boot_still_creates_tables_on_a_fresh_install(ddl_probe):
    """The onboarding path survives: boot builds the schema from table_config."""
    created = ddl_probe["after_bootstrap"]
    assert "cfgint_fresh_install" in created, (
        f"a fresh install did not get its declared table: {created}"
    )
    assert len(created) > 1, f"system tables missing on a fresh install: {created}"


def test_inv_16_2_startup_event_invokes_the_bootstrap(monkeypatch):
    """...and the boot step is actually wired to startup, not merely defined.

    Moving DDL out of import only helps if something calls it. A refactor that
    leaves `bootstrap_database_schema` orphaned would break every new install
    while every existing one kept working - the quietest possible regression.

    TESTING is cleared because startup skips the bootstrap under it (conftest
    owns that step for the suite - see the comment at the call site), and
    DECOUPLED is set so startup returns right after the migration block instead
    of spinning up the inline watcher and workers.
    """
    import main
    from fastapi.testclient import TestClient

    calls = []
    monkeypatch.setattr(main, "bootstrap_database_schema", lambda: calls.append(1))
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.setenv("DECOUPLED", "True")
    with TestClient(main.app):
        pass
    assert calls, "startup never called bootstrap_database_schema()"


_BOOT_PROBE = """
import os, sys
sys.path.insert(0, os.environ["PROBE_SERVER_DIR"])
import main
print("BOOTED")
"""


def test_inv_13_2_corrupt_config_refuses_to_boot(tmp_path):
    """A restart on a corrupt config must fail loudly, not come up empty.

    Coming up "successfully" with zero tables is the worst outcome available: the
    UI looks wiped, the log is clean, and the operator has no thread to pull.
    """
    data_root = tmp_path / "data"
    (data_root / "config").mkdir(parents=True)
    (data_root / "config" / "table_config.json").write_text(
        '{"cfgint_broken": {"business_key": "k",', encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, "-c", _BOOT_PROBE],
        cwd=_SERVER_DIR, env=_probe_env(data_root),
        capture_output=True, text=True, timeout=180,
    )
    assert proc.returncode != 0, (
        f"server booted on a corrupt table_config.json\nSTDOUT:\n{proc.stdout}"
    )
    assert "BOOTED" not in proc.stdout
    combined = proc.stdout + proc.stderr
    assert "TableConfigError" in combined, f"boot failure did not name the cause:\n{combined}"
    assert "table_config.json" in combined


def test_inv_13_2_valid_config_still_boots(tmp_path):
    """Control for the test above: the failure must be caused by the corruption.

    Without this, a boot probe that fails for an unrelated reason (a bad path, a
    missing dependency) would read as "fail-fast works".
    """
    data_root = tmp_path / "data"
    (data_root / "config").mkdir(parents=True)
    _write_json(str(data_root / "config" / "table_config.json"), {
        "cfgint_ok": {"business_key": "k", "column_types": {"k": "string"}}
    })

    proc = subprocess.run(
        [sys.executable, "-c", _BOOT_PROBE],
        cwd=_SERVER_DIR, env=_probe_env(data_root),
        capture_output=True, text=True, timeout=180,
    )
    assert proc.returncode == 0, f"valid config failed to boot\nSTDERR:\n{proc.stderr}"
    assert "BOOTED" in proc.stdout


# --------------------------------------------------------------------------
# H4 - the chain worker's notification path must not depend on importing main
# --------------------------------------------------------------------------

_WORKER_NOTIFY_PROBE = """
import os, sys
from datetime import datetime
sys.path.insert(0, os.environ["PROBE_SERVER_DIR"])

# 1. Establish that this environment is the failing one: with the config broken,
#    importing the web application module raises. (The running web server is
#    already past its own fail-fast, so it stays up - which is exactly why this
#    is reachable in production.)
try:
    import main
    print("MAIN_IMPORT_OK")
except Exception as exc:
    print("MAIN_IMPORT_RAISED " + type(exc).__name__)

# 2. The chain worker must still be able to format the timestamps its WebSocket
#    payload needs. Rows are already COMMITTED by the time this runs.
import chain_ingestion_worker as worker
print("NOTIFY_TS " + worker.to_local_str(datetime(2026, 7, 29, 12, 34, 56)))
print("MAIN_IN_MODULES " + str("main" in sys.modules))
"""


def test_h4_chain_worker_formats_timestamps_without_importing_main(tmp_path):
    """A corrupt config must not silence the chain worker's WebSocket notification.

    The worker did `from main import to_local_str` INSIDE the try/except that
    builds the notification. Importing main runs #13's fail-fast, so a config
    that broke while the system was running produced: rows committed, import
    raises, exception swallowed, notification never sent - and the one log line
    said "Failed to build chained update notification", naming the wrong cause.
    Real-time propagation you can trust is core value #3; a notification path
    that depends on importing a module allowed to refuse does not have it.

    Restoring the lazy `from main import to_local_str` makes this fail: the
    module-level attribute disappears and the probe dies on AttributeError.
    """
    data_root = tmp_path / "data"
    (data_root / "config").mkdir(parents=True)
    (data_root / "config" / "table_config.json").write_text(
        '{"cfgint_corrupt": {"business_key": "k",', encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, "-c", _WORKER_NOTIFY_PROBE],
        cwd=_SERVER_DIR, env=_probe_env(data_root),
        capture_output=True, text=True, timeout=180,
    )
    out = proc.stdout
    assert proc.returncode == 0, (
        f"chain worker could not build a notification under a corrupt config\n"
        f"STDOUT:\n{out}\nSTDERR:\n{proc.stderr}"
    )
    # The defect axis must be ACTIVE: if main imported cleanly here the probe
    # would pass no matter where to_local_str came from.
    assert "MAIN_IMPORT_RAISED TableConfigError" in out, (
        f"probe did not reproduce the corrupt-config condition:\n{out}"
    )
    # Compared against the shared helper rather than a hardcoded string: the
    # value is local-timezone dependent, and pinning it would make this test a
    # timezone assertion instead of an availability one.
    from datetime import datetime as _dt
    from utils.time_format import to_local_str as _fmt
    expected = _fmt(_dt(2026, 7, 29, 12, 34, 56))
    assert f"NOTIFY_TS {expected}" in out, (
        f"chain worker lost its timestamp helper (expected {expected!r}):\n{out}"
    )
    assert "MAIN_IN_MODULES False" in out, (
        f"the worker still drags the web application module in:\n{out}"
    )


def test_h4_chain_worker_never_imports_main():
    """The general form of H4, not just the one call site that was found.

    The probe above proves today's notification path is clean. This proves the
    RULE: any lazy `main` import anywhere in this worker is a latent silent-drop,
    because most of its work happens inside broad try/excepts and importing main
    is allowed to raise. Comment lines are stripped so the rule can be written
    down next to the import it replaced.
    """
    src_path = os.path.join(_SERVER_DIR, "chain_ingestion_worker.py")
    with open(src_path, encoding="utf-8") as f:
        code_lines = [l for l in f if not l.lstrip().startswith("#")]
    offenders = [
        l.strip() for l in code_lines
        if "from main import" in l or l.strip().startswith("import main")
    ]
    assert not offenders, (
        f"chain_ingestion_worker imports the web application module: {offenders}. "
        f"Importing main runs the #13 boot fail-fast; inside a swallowed try that "
        f"means committed rows and no WebSocket notification."
    )
