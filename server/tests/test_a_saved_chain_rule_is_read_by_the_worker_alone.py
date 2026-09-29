# -*- coding: utf-8 -*-
"""총괄 76aa4b6ed — 체인 선언을 저장하면 체인 워커가 «규칙만» 다시 읽는다 (소유자 09-29 ㄱ).

저장 -> 범위(scope = chain_rules)를 실은 SYSTEM_RELOAD 한 행 -> 워커는 규칙만, 워처·스케줄러는
지나감. 범위 없는 행(Reload 버튼 · 코드 편집기)은 전과 같이 무거운 길. 워커가 읽은 규칙 파일의
지문·시각은 대기열 응답에 실려 저장 답의 `base` 와 견줄 수 있다.
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

import mapper_sdk                                                     # noqa: E402
from chain import activity, rule_run                                  # noqa: E402
from chain import ingestion_worker as worker                          # noqa: E402
from database import models                                           # noqa: E402
from ledger import admin                                              # noqa: E402
from runtime import system_reload as sr                               # noqa: E402

SCOPED = {"scope": sr.SCOPE_CHAIN_RULES}


def _row(row_id, payload):
    return SimpleNamespace(id=row_id, payload=payload, processed_chain=True)


# ---------------------------------------------------------------- the one seat, every reader

READERS = [sr.CHAIN_WORKER, sr.WATCHER, sr.SCHEDULER]
CASES = [
    ("nothing new", [], [None, None, None]),
    ("the button", [{"msg": "x"}], [sr.FULL, sr.FULL, sr.FULL]),
    ("a chain rules save", [SCOPED], [sr.SCOPE_CHAIN_RULES, None, None]),
    ("a save right after the button", [{"msg": "x"}, SCOPED], [sr.FULL, sr.FULL, sr.FULL]),
    ("the button right after a save", [SCOPED, {"msg": "x"}], [sr.FULL, sr.FULL, sr.FULL]),
    ("a scope this build does not know", [{"scope": "later"}], [sr.FULL, sr.FULL, sr.FULL]),
    ("the code editor's string payload", ['{"trigger": "code_editor"}'],
     [sr.FULL, sr.FULL, sr.FULL]),
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
    second = sr.publish_reload(db, scope=sr.SCOPE_CHAIN_RULES, rule="r")
    third = sr.publish_reload(db, scope=sr.SCOPE_CHAIN_RULES, rule="r")

    assert [r.id for r in sr.reloads_after(db, 0)] == [first.id, second.id, third.id]
    assert [r.id for r in sr.reloads_after(db, first.id)] == [second.id, third.id]
    assert sr.reloads_after(db, third.id) == []
    assert second.payload["scope"] == sr.SCOPE_CHAIN_RULES and "scope" not in first.payload


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


def test_a_save_writes_one_scoped_row_and_the_reread_names_the_saved_base(outbox, rules_file):
    saved = admin.save_chain_rule_raw(
        "live_one", {"trigger_table": "a", "target_table": "b2", "mapper_module": "m",
                     "mapper_function": "f"}, admin.file_fingerprint(str(rules_file)))

    rows = sr.reloads_after(outbox(), 0)
    assert [(r.payload.get("scope"), r.payload.get("rule")) for r in rows] == [
        (sr.SCOPE_CHAIN_RULES, "live_one")]

    rules = worker.reread_rules_only()
    assert [r.get("target_table") for r in rules if r.get("name") == "live_one"] == ["b2"]
    shape = activity.view(activity.registry.instants())
    assert shape["rules_base"] == saved["base"], "the queue cannot tell the save was read"
    assert shape["rules_loaded_age_seconds"] is not None


def test_a_save_given_the_request_session_writes_through_it(outbox, rules_file, monkeypatch):
    """The routes pass theirs - the row rides the request's own session."""
    import database.database as database_module

    def refuse():
        raise AssertionError("the save opened its own session")

    request_db = outbox()
    monkeypatch.setattr(database_module, "SessionLocal", refuse)
    admin.save_chain_rule_raw(
        "live_one", {"trigger_table": "a", "target_table": "b3", "mapper_module": "m",
                     "mapper_function": "f"}, admin.file_fingerprint(str(rules_file)),
        db=request_db)

    assert [r.payload.get("rule") for r in sr.reloads_after(request_db, 0)] == ["live_one"]


# ---------------------------------------------------------------- ① a new mapper name

def test_a_new_mapper_name_walks_the_package_once_and_a_known_one_never(monkeypatch):
    walks = []

    def fake_discover(package="mappers"):
        walks.append(package)
        mapper_sdk.MAPPER_REGISTRY["s76_late"] = lambda db, payload: []
        return tuple(mapper_sdk.MAPPER_REGISTRY), {}

    monkeypatch.setattr(mapper_sdk, "discover", fake_discover)
    monkeypatch.setattr(mapper_sdk, "_DISCOVERY_ATTEMPTED", True)   # boot already looked
    monkeypatch.setitem(mapper_sdk.MAPPER_REGISTRY, "s76_known", lambda db, payload: [])
    monkeypatch.setattr(worker, "load_chain_rules", lambda: [])
    try:
        worker.reread_rules_only()
        assert rule_run.runnable("s76_known") is not None and walks == []
        assert rule_run.runnable("s76_late") is not None and walks == ["mappers"]
        assert rule_run.runnable("s76_nowhere") is None and walks == ["mappers"], "walks once"
    finally:
        mapper_sdk.MAPPER_REGISTRY.pop("s76_late", None)


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
    monkeypatch.setattr(worker, "_start_index_work",
                        lambda rules, *a, **k: seen["index_rules"].append(rules))
    monkeypatch.setattr(models, "refresh_dynamic_models",
                        lambda *a, **k: seen.__setitem__("refresh", seen["refresh"] + 1))
    monkeypatch.setattr(worker, "sweep_undelivered_broadcasts", no_sweep)
    # The loop's ledger tasks and startup query-ender are not this file's subject.
    monkeypatch.setattr(worker, "run_ledger_followup", no_sweep)
    monkeypatch.setattr(worker, "run_ledger_row_census", no_sweep)
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


def test_ten_saves_reread_the_rules_and_never_the_heavy_path(loop):
    """저장 반복 10 번 -> refresh_dynamic_models 0 · 매퍼 비우기 0 · 웜업은 기동의 1 번뿐."""
    feed = [[_row(1, SCOPED), _row(2, SCOPED), _row(3, SCOPED), _row(4, SCOPED)],
            [_row(5, SCOPED), _row(6, SCOPED), _row(7, SCOPED)],
            [_row(8, SCOPED), _row(9, SCOPED), _row(10, SCOPED)]]
    seen = loop(feed, 3.6)

    assert seen["refresh"] == 0 and seen["evict"] == 0 and seen["warmup"] == 1
    assert seen["load"] == 1 + 3, "boot, then once per check that found saves"
    assert seen["index_rules"][-1] == [{"name": "loaded_4"}], "the loop runs the new rules"


def test_the_button_is_the_heavy_path_as_before(loop):
    seen = loop([[_row(1, {"msg": "Reload configs and custom scripts modules"}), _row(2, SCOPED)]],
                1.5)

    assert seen["refresh"] == 1 and seen["evict"] == 1 and seen["warmup"] == 2
    assert seen["load"] == 2
