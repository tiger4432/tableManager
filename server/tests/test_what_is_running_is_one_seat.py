# -*- coding: utf-8 -*-
"""총괄 78ebdcfc0 · 5996d7f54 (소유자 「러닝도 한문으로」) — everything running, one shape, four
sources. The top queue counted the chain rules alone: a retroactive run left the queue when
it was claimed, so the queue said RUNNING 0 while it ran.

Each source is fed through the door it really uses - the chain worker's heartbeat lap, the
run table, the scheduler's status file, the watcher's registry - and none is stubbed in
`runtime.running` itself."""
import json
import os
import sys
import time
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main                                                      # noqa: E402
from admin import retroactive                                    # noqa: E402
from chain import activity                                       # noqa: E402
from database import models                                      # noqa: E402
from ingestion.activity import registry as ingestions            # noqa: E402
from runtime import running                                      # noqa: E402
from utils import auto_update_control as auc                     # noqa: E402
from utils import heartbeat                                      # noqa: E402

FILE = ("t_probe", "big_probe.csv")


@pytest.fixture
def sources(tmp_path, monkeypatch, db_session):
    """Four writers, one per source; nothing running until a test says so."""
    monkeypatch.setattr(activity.registry, "_attached", False)
    monkeypatch.setattr(heartbeat, "heartbeat_dir", lambda: str(tmp_path))
    monkeypatch.setattr(heartbeat, "heartbeat_path",
                        lambda name: os.path.join(str(tmp_path), "%s.json" % name))
    monkeypatch.setattr(auc, "SERVER_DIR", str(tmp_path))
    (tmp_path / "config").mkdir()

    def beat(name, pid, lap=None):
        ts = time.time()
        with open(os.path.join(str(tmp_path), "%s.json" % name), "w", encoding="utf-8") as fh:
            json.dump({"name": name, "pid": pid, "ts": ts, "beats": 1, "started_at": ts,
                       "note": None, "work": {},
                       "laps": {name: dict(lap, at=ts)} if lap else {}}, fh)

    def chain(rules):
        beat("chain", 111, {"outcomes": {}, "running": [
            {"rule": r, "mapper": "m", "target_table": "u", "rows_in": 7,
             "started": time.time() - 30} for r in rules]})

    def run(state):
        db_session.add(models.RetroactiveRun(
            run_id="run-probe", op="withdraw", params="{}", state=state,
            runner="retroactive/HOST/4321", processed_rows=5, total_rows=50,
            started_at=datetime.now(timezone.utc)))
        db_session.flush()

    def collector(status):
        (tmp_path / "config" / "scheduler_status.json").write_text(json.dumps(
            {"collectors": [{"table_name": "t_probe", "script_name": "pull.py",
                             "last_status": status,
                             "last_run": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}]}),
            encoding="utf-8")

    def ingestion(status):
        ingestions.apply_state({"table_name": FILE[0], "filename": FILE[1], "status": status})

    beat("scheduler", 222)
    beat("watcher", 333)
    chain([])
    yield {"chain": chain, "run": run, "collector": collector, "ingestion": ingestion}
    ingestions.remove(*FILE)


def test_the_four_sources_run_through_one_door_in_one_shape(db_session, sources):
    sources["chain"](["rule_probe"])
    sources["run"](retroactive.RUN_RUNNING)
    sources["collector"]("RUNNING")
    sources["ingestion"]("PROCESSING")

    items = running.running_now(db_session)

    by_where = {item["where"]: item for item in items}
    assert sorted(by_where) == sorted([running.WHERE_CHAIN_WORKER, running.WHERE_OWN_PROCESS,
                                       running.WHERE_SCHEDULER, running.WHERE_WATCHER])
    assert all(set(item) == {"what", "where", "pid", "started_at", "elapsed_seconds",
                             "progress", "cancel"} for item in items)
    assert (by_where["chain_worker"]["what"], by_where["chain_worker"]["pid"]) == (
        "rule_probe", 111)
    run = by_where["own_process"]
    assert (run["pid"], run["progress"], run["cancel"]) == (
        4321, {"processed": 5, "total": 50}, {"run_id": "run-probe"})
    assert run["what"] == retroactive.operation("withdraw")["label"]
    assert (by_where["scheduler"]["what"], by_where["scheduler"]["pid"]) == (
        "t_probe/pull.py", 222)
    assert (by_where["watcher"]["what"], by_where["watcher"]["pid"]) == (FILE[1], 333)
    assert all(item["cancel"] is None for item in items if item["where"] != "own_process")


def test_nothing_running_is_an_empty_list(db_session, sources):
    """Finished, waiting and queued are not running: a done run, a collector that last
    succeeded, a file queued in the heavy lane."""
    sources["run"](retroactive.RUN_DONE)
    sources["collector"]("SUCCESS")
    sources["ingestion"]("QUEUED")

    assert running.running_now(db_session) == []


def test_the_queue_carries_the_seat(db_session, sources):
    sources["chain"](["rule_probe"])
    sources["run"](retroactive.RUN_RUNNING)

    out = main.get_chain_queue_depth(db=db_session)

    assert sorted(item["where"] for item in out["now_running"]) == sorted(
        [running.WHERE_CHAIN_WORKER, running.WHERE_OWN_PROCESS])
    assert "running" not in out, "the chain-only field retired once the screen read the seat"
