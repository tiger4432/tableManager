"""e6a0bdbbd (owner 10-21 ㄱ, lead's six rulings): one mechanism reads a changed declaration again in every process that
holds it - `config_watcher`. Each cell here is a file x a row of its one table, or a property of `held`."""
import json
import logging
import os
import time

import pytest

import paths
from database import config_watcher

WATCHER_LOG = "Watcher.ConfigWatcher"

#: Where each row's file sits under a config root. A row added to `ROWS` without a path here reds the first test.
WHERE = {
    "table_config.json": "table_config.json",
    "chain_rules.json": "chain_rules.json",
    config_watcher.ONTOLOGY: os.path.join("ontology", "ledger_config.json"),
    "ledger_resolver.json": "ledger_resolver.json",
    "notation_rules.json": "notation_rules.json",
    "map_overlay_config.json": "map_overlay_config.json",
    "ingestion_settings.json": "ingestion_settings.json",
    "database.json": "database.json",
    config_watcher.MAPPERS: os.path.join("..", "mappers", "probe_row.py"),
}


@pytest.fixture
def root(tmp_path, monkeypatch):
    """A config root of this test's own, a mappers folder beside it, and the boundary off."""
    config = tmp_path / "config"
    (config / "ontology").mkdir(parents=True)
    (tmp_path / "mappers").mkdir()
    monkeypatch.setattr(paths, "CONFIG_DIR", str(config))
    monkeypatch.setattr(config_watcher, "_MAPPER_DIRS", [(os.path.normcase(str(tmp_path / "mappers")),)])
    monkeypatch.setattr(config_watcher, "_NAMES", {})
    monkeypatch.setattr(config_watcher, "_PENDING", {})
    monkeypatch.setattr(config_watcher, "_SAID_HERE", {})
    monkeypatch.setattr(config_watcher, "_BOUNDARY", [False])
    return config


def _recording_rows(monkeypatch):
    ran = []
    rows = {name: ((lambda paths_, engine, name=name: ran.append((name, paths_))), boundary)
            for name, (_, boundary) in config_watcher.ROWS.items()}
    monkeypatch.setattr(config_watcher, "ROWS", rows)
    return ran


def _write(path, value):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(value if isinstance(value, str) else json.dumps(value))


def test_every_row_has_a_file_here():
    assert set(WHERE) == set(config_watcher.ROWS), "a row of the table with no cell in this file"


@pytest.mark.parametrize("name", sorted(WHERE))
@pytest.mark.parametrize("boundary", [False, True], ids=["api", "chain process"])
def test_a_changed_file_moves_its_name_and_runs_its_row_once(root, monkeypatch, name, boundary):
    ran = _recording_rows(monkeypatch)
    config_watcher._BOUNDARY[0] = boundary
    path = os.path.normpath(os.path.join(str(root), WHERE[name]))
    before = config_watcher.generation(name)

    assert config_watcher.changed(path) == name
    waits = boundary and config_watcher.ROWS[name][1]
    assert ran == ([] if waits else [(name, [path])])
    assert config_watcher.generation(name) != before or waits

    assert config_watcher.apply_pending() == ([name] if waits else [])
    assert ran == [(name, [path])], "once, now or at the boundary"


@pytest.mark.parametrize("rel", ["table_config.json.bak", os.path.join("sample", "x.json"), "beat.txt"])
def test_a_file_that_is_no_declaration_moves_nothing(root, monkeypatch, rel):
    ran = _recording_rows(monkeypatch)
    every = config_watcher.generation(*config_watcher.ROWS)
    assert config_watcher.changed(os.path.join(str(root), rel)) is None
    assert ran == [] and config_watcher.generation(*config_watcher.ROWS) == every


def test_a_held_value_is_read_once_until_its_file_changes_and_kept_when_it_stops_reading(root, caplog):
    path = str(root / "notation_rules.json")
    _write(path, {"a": 1})
    assert config_watcher.json_object(path) == {"a": 1}

    _write(path, {"a": 2})
    assert config_watcher.json_object(path) == {"a": 1}, "not read per call - only once it changed"
    config_watcher.changed(path)
    assert config_watcher.json_object(path) == {"a": 2}

    _write(path, "{broken")
    with caplog.at_level(logging.ERROR, logger=WATCHER_LOG):
        config_watcher.changed(path)
        assert config_watcher.json_object(path) == {"a": 2}, "the value read before is kept"
        assert config_watcher.json_object(path) == {"a": 2}
    said = [r.getMessage() for r in caplog.records if "keeps what it read before" in r.getMessage()]
    assert len(said) == 1 and "notation_rules.json" in said[0], said

    _write(path, {"a": 3})
    config_watcher.changed(path)
    assert config_watcher.json_object(path) == {"a": 3}


def test_a_first_read_that_fails_is_read_as_empty_and_said(root, caplog):
    path = str(root / "map_overlay_config.json")
    _write(path, "[1, 2]")
    with caplog.at_level(logging.ERROR, logger=WATCHER_LOG):
        assert config_watcher.json_object(path) == {}
    said = [r.getMessage() for r in caplog.records if "reads it as empty" in r.getMessage()]
    assert len(said) == 1 and "map_overlay_config.json" in said[0] and "not an object" in said[0], said


def test_a_refusal_that_is_the_answer_is_given_again_until_the_file_changes(root):
    """`keep=False` - the ledger's compile: a refusal after a good read is the answer, read once per change."""
    path = str(root / "ontology" / "ledger_config.json")
    reads = []

    def read():
        reads.append(1)
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)

    names = config_watcher.names_of([path])
    _write(path, {"v": 1})
    assert config_watcher.held(names, "probe.compile", read, keep=False) == {"v": 1}
    _write(path, "{broken")
    config_watcher.changed(path)
    for _ in range(3):
        with pytest.raises(ValueError):
            config_watcher.held(names, "probe.compile", read, keep=False)
    assert len(reads) == 2, "the failure is held, not read again per call"


def test_a_declared_entity_is_known_once_its_declaration_changes(monkeypatch, tmp_path):
    """④ control: declared_entities was read once a process - an entity activated was unknown until a restart."""
    from ledger.schema import world_names
    from ledger_api import declared_entities
    from tests.support.declaration import use_committed_declaration

    use_committed_declaration(monkeypatch, tmp_path)
    path = world_names().declaration_path
    with open(path, encoding="utf-8") as handle:
        declaration = json.load(handle)
    assert "probe_entity" not in declared_entities.load()

    declaration.setdefault("entities", {})["probe_entity"] = {"keys": ["probe_key"]}
    _write(path, declaration)
    assert "probe_entity" not in declared_entities.load(), "held until it changed"
    config_watcher.changed(path)
    assert declared_entities.load()["probe_entity"] == ["probe_key"]


def test_a_process_without_an_engine_reads_the_changed_table_config(monkeypatch, tmp_path):
    """④ control: a chain slot (no engine) ran the table config it started with until a Reload or a restart."""
    from database import crud, models
    from tests.support.declaration import use_committed_declaration

    root = use_committed_declaration(monkeypatch, tmp_path)
    monkeypatch.setattr(config_watcher, "_ENGINE", [None])
    monkeypatch.setattr(config_watcher, "_BOUNDARY", [True])
    kept = dict(crud.TABLE_CONFIG)
    path = str(root / "table_config.json")
    with open(path, encoding="utf-8") as handle:
        catalogue = json.load(handle)
    tables = catalogue.get("tables", catalogue)
    tables["probe_slot_table"] = {"column_types": {"probe_col": "TEXT"}}
    _write(path, catalogue)
    try:
        assert config_watcher.changed(path) == "table_config.json"
        assert "probe_slot_table" in crud.TABLE_CONFIG, "applied now - the table config does not wait a boundary"
    finally:
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(kept)
        models.init_dynamic_models(kept)


def test_a_whole_reload_starts_the_walk_pool_once(monkeypatch):
    from runtime import process_pool

    recycled = []
    monkeypatch.setattr(process_pool, "recycle", lambda: recycled.append(1))
    monkeypatch.setattr(config_watcher, "ROWS", {
        "probe_a": ((lambda p, e: config_watcher.recycle_pools()), False),
        "probe_b": ((lambda p, e: config_watcher.recycle_pools()), False)})
    config_watcher.reload_everything()
    assert recycled == [1], "once for the whole reload"
    config_watcher._apply("probe_a", None, None)
    assert recycled == [1, 1], "and once for one row"


def test_a_watched_folder_reads_a_hand_edit_and_a_save_once(root, monkeypatch, caplog):
    """The watcher's own event (watchdog, this folder): a hand edit is read again with no one calling `changed`; a
    process that saved and said so is not applied twice by the event of its own write."""
    from database import crud

    monkeypatch.setattr(config_watcher, "DEBOUNCE_SEC", 0.05)
    monkeypatch.setattr(config_watcher, "_ENGINE", [None])
    monkeypatch.setattr(crud, "CONFIG_PATH", str(root / "table_config.json"))
    monkeypatch.setattr(config_watcher, "_MAPPER_DIRS", [()])
    path = str(root / "notation_rules.json")
    _write(path, {"v": 1})
    assert config_watcher.json_object(path) == {"v": 1}

    observer = config_watcher.start_config_watcher(None)
    try:
        _write(path, {"v": 2})
        deadline = time.time() + 10
        while config_watcher.json_object(path) != {"v": 2} and time.time() < deadline:
            time.sleep(0.05)
        assert config_watcher.json_object(path) == {"v": 2}, "a hand edit read again by the watcher"
        time.sleep(0.5)                  # a write is two events (truncate, then the bytes): the second may come late
        assert observer.config_handler.wait_for_idle(timeout=10)

        with caplog.at_level(logging.INFO, logger=WATCHER_LOG):
            start = len(caplog.records)
            _write(path, {"v": 3, "saved": "here"})
            config_watcher.changed(path)
            assert config_watcher.json_object(path) == {"v": 3, "saved": "here"}
            time.sleep(0.5)
            assert observer.config_handler.wait_for_idle(timeout=10)
        applied = [r for r in caplog.records[start:] if "notation_rules.json changed - read again" in r.getMessage()]
        assert len(applied) == 1, "the save and its own event: one apply, not %d" % len(applied)
    finally:
        observer.config_handler.cancel_pending()
        observer.stop()
        observer.join(5)
