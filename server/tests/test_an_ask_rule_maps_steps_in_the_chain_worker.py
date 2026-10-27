"""`derive.ask` step mapping in the real API + chain worker (lead 10-27 A-2): six steps in windows of three are asked
twice; one changed step asks its window alone, and the other window's rows stay as they were. The harness is the A-1
gate's (`test_an_ask_rule_runs_in_the_chain_worker`)."""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

from test_an_ask_rule_runs_in_the_chain_worker import API, SCHEMA, SERVER_DIR, WORKER, _free_port, _put, _wait

# the stand-in answers every line it is asked with a row stamped by the call's number
FAKE = r'''
import importlib.abc, importlib.util, json, os, re, sys

CALLS = os.environ["ASK_GATE_CALLS"]


def fake(prompt, **_kw):
    with open(CALLS, "a", encoding="utf-8") as out:
        out.write("1\n")
    asked = sum(1 for _ in open(CALLS, encoding="utf-8"))
    texts = []
    for ident, body in re.findall(r"^\[(.+)\]\n((?:(?!^\[).*\n?)*)", prompt, re.M):
        rows = [{"step_seq": line.split(" | ")[0], "item_id": None, "process_kind": "call%d" % asked}
                for line in body.splitlines() if line.strip() and "context only" not in line]
        texts.append({"id": ident, "rows": rows})
    return {"texts": texts}


class Hook(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path, target=None):
        if name != "utils.llm":
            return None
        sys.meta_path.remove(self)
        spec = importlib.util.find_spec(name)
        run = spec.loader.exec_module

        def exec_module(module):
            run(module)
            module.ask_json = fake
        spec.loader.exec_module = exec_module
        return spec


sys.meta_path.insert(0, Hook())
'''
TABLES = {
    "sm_steps": {"composite_key_source": ["product", "step_seq"], "column_types": {
        "product": "string", "step_seq": "string", "step_desc": "string"}},
    "sm_map": {"composite_key_source": ["product", "step_seq", "item_id"], "column_types": {
        "product": "string", "step_seq": "string", "item_id": "string", "process_kind": "string"}},
}
DECLARATION = {
    "name": "step_mapping", "on": {"table": "sm_steps"}, "into": {"table": "sm_map"},
    "derive": {"kind": "ask", "ask": {
        "input": {"group_by": ["product"], "order_by": "step_seq", "text": ["step_desc"], "window": 3, "overlap": 1},
        "output": {"carry": {"product": "product"}, "line": "step_seq", "item": "item_id",
                   "cells": ["process_kind"]}}}}


def _mapped(db):
    import sqlite3
    with sqlite3.connect(db) as con:
        return dict(con.execute("SELECT step_seq, process_kind FROM sm_map WHERE product = 'P1'").fetchall())


def test_one_changed_step_asks_its_window_and_the_other_windows_rows_stay(tmp_path):
    data = tmp_path / "data"
    (data / "config").mkdir(parents=True)
    (data / "config" / "table_config.json").write_text(json.dumps(TABLES), encoding="utf-8")
    (data / "config" / "chain_rules.json").write_text(json.dumps({"rules": [DECLARATION]}), encoding="utf-8")
    llm = json.load(open(os.path.join(SERVER_DIR, "config", "sample", "llm_config.json.sample"), encoding="utf-8"))
    llm.update(base_url="http://127.0.0.1:9/fake", model="fake-model", api_key="fake", batch_chars=1)
    (data / "config" / "llm_config.json").write_text(json.dumps(llm), encoding="utf-8")
    (tmp_path / "sitecustomize.py").write_text(FAKE, encoding="utf-8")
    for name, body in (("p_schema.py", SCHEMA), ("p_api.py", API), ("p_worker.py", WORKER)):
        (tmp_path / name).write_text(body, encoding="utf-8")
    db, calls = tmp_path / "box.db", tmp_path / "calls.txt"
    port = _free_port()
    base = "http://127.0.0.1:%d" % port
    env = dict(os.environ, ASSY_DATA_ROOT=str(data), DATABASE_URL="sqlite:///" + db.as_posix(), DECOUPLED="True",
               TESTING="True", API_BASE_URL=base, PYTHONIOENCODING="utf-8", ASK_GATE_CALLS=str(calls),
               PYTHONPATH=os.pathsep.join([str(tmp_path), SERVER_DIR]))
    env.pop("ASSY_ADMIN_TOKEN", None)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    subprocess.run([sys.executable, str(tmp_path / "p_schema.py")], cwd=SERVER_DIR, env=env, check=True,
                   capture_output=True)
    logs = {name: open(tmp_path / ("%s.log" % name), "wb") for name in ("api", "worker")}
    api = subprocess.Popen([sys.executable, str(tmp_path / "p_api.py"), str(port)], cwd=SERVER_DIR, env=env,
                           stdout=logs["api"], stderr=subprocess.STDOUT)
    worker = subprocess.Popen([sys.executable, str(tmp_path / "p_worker.py")], cwd=SERVER_DIR, env=env,
                              stdout=logs["worker"], stderr=subprocess.STDOUT)
    log = tmp_path / "worker.log"

    def count():
        return sum(1 for _ in open(calls, encoding="utf-8")) if os.path.exists(calls) else 0
    try:
        deadline = time.monotonic() + 120
        while True:
            assert api.poll() is None, (tmp_path / "api.log").read_text(errors="replace")[-3000:]
            try:
                opener.open(base + "/health", timeout=5)
                break
            except urllib.error.HTTPError:
                break
            except OSError:
                assert time.monotonic() < deadline, "the API never came up"
                time.sleep(0.5)
        steps = [{"updates": {"product": "P1", "step_seq": "AA%03d" % n, "step_desc": "step %d" % n},
                  "source_name": "ingest"} for n in range(1, 7)]
        assert _put(opener, base, "sm_steps", steps) == 200
        _wait(lambda: len(_mapped(db)) == 6, worker, log)
        assert count() == 2, "six steps, windows of three"
        first = _mapped(db)

        assert _put(opener, base, "sm_steps", [{"updates": {"product": "P1", "step_seq": "AA005",
                                                            "step_desc": "step 5 changed"},
                                                "source_name": "ingest"}]) == 200
        _wait(lambda: count() >= 3 and _mapped(db) != first, worker, log)
        time.sleep(3)
        after = _mapped(db)
        assert count() == 3, "one changed step - its window alone"
        assert {s: after[s] for s in ("AA001", "AA002", "AA003")} == {s: first[s] for s in ("AA001", "AA002", "AA003")}
        assert {after[s] for s in ("AA004", "AA005", "AA006")} == {"call3"}
    finally:
        for proc in (worker, api):
            proc.terminate()
        for proc in (worker, api):
            try:
                proc.wait(30)
            except subprocess.TimeoutExpired:
                proc.kill()
        for handle in logs.values():
            handle.close()
