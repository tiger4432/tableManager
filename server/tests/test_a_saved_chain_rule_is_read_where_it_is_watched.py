# -*- coding: utf-8 -*-
"""A saved chain declaration is read where it is watched (e6a0bdbbd, owner 10-21 ㄱ) - the saving process at once,
every other one from its own config watcher, the chain loop at its next boundary, and only the rules: no mapper
re-import, no table shapes, no warmup. The scoped row a save wrote (76aa4b6ed) is retired; the Reload button's row is
the heavy path as before, and the join-keys row is the index line's word to the writers. The rules file the worker
read is carried in the queue answer, to be held against a save's `base`.
"""
import asyncio
import json
import os
import sys
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from chain import activity                                            # noqa: E402
from chain import ingestion_worker as worker                          # noqa: E402
from database import models                                           # noqa: E402
from ledger import admin                                              # noqa: E402
from runtime import system_reload as sr                               # noqa: E402

JOIN_KEYS = {"scope": sr.SCOPE_JOIN_KEYS}


def _row(row_id, payload):
    return SimpleNamespace(id=row_id, payload=payload, processed_chain=True)


# ---------------------------------------------------------------- the one seat, every reader

READERS = [sr.CHAIN_WORKER, sr.WATCHER, sr.SCHEDULER, sr.API, sr.INDEX_LINE]
F5 = [sr.FULL] * 5
CASES = [
    ("nothing new", [], [None] * 5),
    ("the button", [{"msg": "x"}], F5),
    ("a scope this build does not know", [{"scope": "later"}], F5),
    ("the code editor's string payload", ['{"trigger": "code_editor"}'], F5),
    # 총괄 10-20: the index line built or took back a join unique index - the writers forget their join keys
    ("a join unique index changed", [JOIN_KEYS],
     [sr.SCOPE_JOIN_KEYS, sr.SCOPE_JOIN_KEYS, None, sr.SCOPE_JOIN_KEYS, None]),
    ("a join index change and the button", [JOIN_KEYS, {"msg": "x"}], F5),
]


@pytest.mark.parametrize("label,payloads,expected", CASES, ids=[c[0] for c in CASES])
def test_each_reader_does_what_its_row_asks(label, payloads, expected):
    rows = [_row(i + 1, p) for i, p in enumerate(payloads)]
    assert [sr.reload_for(reader, rows) for reader in READERS] == expected


@pytest.fixture(name="outbox")
def fixture_outbox(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    models.DatabaseOutbox.__table__.create(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    import database.database as database_module
    monkeypatch.setattr(database_module, "SessionLocal", Session)
    return Session


def test_a_reader_gets_every_row_past_its_mark_oldest_first(outbox):
    db = outbox()
    first = sr.publish_reload(db, msg="button")
    second = sr.publish_reload(db, scope=sr.SCOPE_JOIN_KEYS)
    third = sr.publish_reload(db, scope=sr.SCOPE_JOIN_KEYS)

    assert [r.id for r in sr.reloads_after(db, 0)] == [first.id, second.id, third.id]
    assert [r.id for r in sr.reloads_after(db, first.id)] == [second.id, third.id]
    assert sr.reloads_after(db, third.id) == []
    assert second.payload["scope"] == sr.SCOPE_JOIN_KEYS and "scope" not in first.payload


def test_the_chain_worker_forgets_its_join_keys_and_keeps_its_rules(monkeypatch):
    forgot = []
    monkeypatch.setattr(worker, "_reset_right_keys", lambda: forgot.append(1))
    monkeypatch.setattr(worker, "loaded_chain_rules", lambda: ["the rules as loaded"])
    monkeypatch.setattr(worker, "load_chain_rules", lambda: pytest.fail("the rules were read again"))

    assert worker.reload_rules(sr.SCOPE_JOIN_KEYS) == ["the rules as loaded"] and forgot == [1]


@pytest.mark.parametrize("payload,runs", [(JOIN_KEYS, False), (None, True), ({"msg": "x"}, True)],
                         ids=["its own join-keys row", "a changed rules file", "the button"])
def test_the_index_line_does_its_declared_work_again_except_for_its_own_row(outbox, monkeypatch, payload, runs):
    import threading

    from database import config_watcher
    from runtime import maintenance_line

    monkeypatch.setattr(maintenance_line, "_DECLARATIONS_CHANGED", threading.Event())
    ran = []
    monkeypatch.setattr(maintenance_line, "_declared_work", lambda factory: ran.append(1) or [])
    if payload is None:
        config_watcher.changed("chain_rules.json")      # the row in this process: the line's flag
    else:
        sr.publish_reload(outbox(), **payload)

    maintenance_line.poll_once(outbox, 0)
    assert bool(ran) is runs


@pytest.mark.parametrize("created,dropped,said", [
    (True, [], True), (False, ["uq_vjoin_t_k_ns"], True), (False, ["ix_vjoin_t_k_ns"], False), (False, [], False)],
    ids=["built", "taken back", "only a lookup index taken back", "nothing changed"])
def test_the_index_line_tells_the_writers_once_when_a_join_unique_index_changes(outbox, monkeypatch, created, dropped,
                                                                                 said):
    from chain import synthesis, unique_key

    monkeypatch.setattr(unique_key, "forget", lambda *a: None)
    monkeypatch.setattr(unique_key, "forget_retractions", lambda *a: None)
    monkeypatch.setattr(synthesis, "ensure_declared_unique_keys", lambda db, rules: {
        "ensured": [("r", {"created": "CREATE UNIQUE INDEX …" if created else None})], "skipped": []})
    monkeypatch.setattr(synthesis, "ensure_declared_lookup_keys", lambda db, rules: {"ensured": []})
    monkeypatch.setattr(synthesis, "retract_unrequired_indexes_once", lambda db: {"dropped": list(dropped)})

    worker._ensure_declared_indexes_sync([], outbox)

    rows = sr.reloads_after(outbox(), 0)
    assert [r.payload.get("scope") for r in rows] == ([sr.SCOPE_JOIN_KEYS] if said else [])


# ---------------------------------------------------------------- the save tells the worker

@pytest.fixture(name="rules_file")
def fixture_rules_file(tmp_path, monkeypatch):
    path = tmp_path / "chain_rules.json"
    path.write_text(json.dumps({"rules": [
        {"name": "live_one", "trigger_table": "a", "target_table": "b",
         "mapper_module": "m", "mapper_function": "f", "enabled": True}]}), encoding="utf-8")
    monkeypatch.setattr(admin, "chain_rules_path", lambda: str(path))
    monkeypatch.setattr(worker, "RULES_PATH", str(path))
    monkeypatch.setattr(admin.config_backup, "backup_dir_for", lambda p: str(tmp_path / "bk"))
    return path


def test_a_save_is_read_here_at_once_and_writes_no_row(outbox, rules_file):
    """The saving process reads the saved file on its next ask; no SYSTEM_RELOAD row is written - every other
    process watches the file. The queue names the base it read."""
    worker.loaded_chain_rules()
    saved = admin.save_chain_rule_raw(
        "live_one", {"trigger_table": "a", "target_table": "b2", "mapper_module": "m",
                     "mapper_function": "f"}, admin.file_fingerprint(str(rules_file)))

    assert sr.reloads_after(outbox(), 0) == []
    rules = worker.loaded_chain_rules()
    assert [r.get("target_table") for r in rules if r.get("name") == "live_one"] == ["b2"]
    shape = activity.view(activity.registry.instants())
    assert shape["rules_base"] == saved["base"], "the queue cannot tell the save was read"
    assert shape["rules_loaded_age_seconds"] is not None


# ---------------------------------------------------------------- the real loop

class _Query:
    def filter(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def first(self):
        return None

    def all(self):
        return []


class _Session:
    def query(self, *a, **k):
        return _Query()

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


class _Listener:
    def __init__(self, *a, **k):
        pass

    async def start(self):
        pass

    async def stop(self):
        pass

    def close(self):
        pass

    async def wait(self, timeout):
        await asyncio.sleep(0.01)
        return False


@pytest.fixture(name="loop")
def fixture_loop(monkeypatch):
    """The real loop over a scripted SYSTEM_RELOAD feed; everything heavy counted."""
    seen = {"load": 0, "refresh": 0, "evict": 0, "warmup": 0, "index_rules": []}

    def load():
        seen["load"] += 1
        return [{"name": "loaded_%d" % seen["load"]}]

    async def no_sweep(*a, **k):
        return None

    monkeypatch.setattr(worker, "load_chain_rules", load)
    monkeypatch.setattr(worker, "reload_worker_process_cache",
                        lambda: seen.__setitem__("evict", seen["evict"] + 1))
    monkeypatch.setattr(worker, "warmup_worker",
                        lambda *a, **k: seen.__setitem__("warmup", seen["warmup"] + 1))
    monkeypatch.setattr(models, "refresh_dynamic_models",
                        lambda *a, **k: seen.__setitem__("refresh", seen["refresh"] + 1))
    monkeypatch.setattr(worker, "sweep_undelivered_broadcasts", no_sweep)
    # The startup query-ender is not this file's subject.
    monkeypatch.setattr(worker, "_end_queries_a_gone_chain_worker_left_sync", lambda *a: None)
    monkeypatch.setattr(worker, "another_chain_loop_is_running", lambda *a, **k: None)
    monkeypatch.setattr(worker, "OutboxListener", _Listener)
    monkeypatch.setattr(worker.internal_event_client, "startup_lines", lambda *a, **k: [])
    monkeypatch.setattr(worker.heartbeat, "beat", lambda *a, **k: None)

    def run(feed, seconds):
        batches = list(feed)
        monkeypatch.setattr(sr, "reloads_after",
                            lambda db, after: batches.pop(0) if batches else [])

        async def go():
            try:
                await asyncio.wait_for(worker.start_chain_ingestion_worker(_Session), seconds)
            except asyncio.TimeoutError:
                pass
        asyncio.run(go())
        return seen

    return run


def test_a_changed_rules_file_waits_for_the_boundary_and_never_the_heavy_path(loop, monkeypatch):
    """A rules file changed while the loop runs (`config_watcher` in a boundary process): the rules once more at the
    loop's next check - never refresh_dynamic_models, the mapper eviction or a second warmup."""
    from database import config_watcher

    monkeypatch.setattr(config_watcher, "_BOUNDARY", [True])
    monkeypatch.setattr(config_watcher, "_PENDING", {})
    for _ in range(10):
        config_watcher.changed("chain_rules.json")
    assert list(config_watcher._PENDING) == ["chain_rules.json"], "it waits for the boundary"
    seen = loop([], 1.5)

    assert seen["refresh"] == 0 and seen["evict"] == 0 and seen["warmup"] == 1
    assert seen["load"] == 2, "boot, then once at the boundary for ten changes"
    assert config_watcher._PENDING == {}


def test_the_button_is_the_heavy_path_as_before(loop):
    seen = loop([[_row(1, {"msg": "Reload configs and custom scripts modules"}), _row(2, JOIN_KEYS)]],
                1.5)

    assert seen["refresh"] == 1 and seen["evict"] == 1 and seen["warmup"] == 2
    assert seen["load"] == 2
