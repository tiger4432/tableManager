"""`derive: {kind: "ask"}` in the real API + chain worker (lead 10-27 A-1): rows put through the API reach the rule,
the model (a stand-in patched in at import) is asked once per product, and its rows land in the output table. A
person's cell and a person's row survive the rule running again. Every name is the declaration's."""
import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PATH = '''
import json, os, sys
sys.path.insert(1, os.path.join(os.getcwd(), "parsers"))
'''
SCHEMA = PATH + '''
import paths
from database.database import Base, engine
from database import models
from database import crud
models.init_dynamic_models(crud.load_table_config())      # the tables boot makes: the owner's and the shipped
Base.metadata.create_all(bind=engine)
'''
API = PATH + '''
import uvicorn
import main
uvicorn.run(main.app, host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
'''
WORKER = PATH + '''
import asyncio
import run_chain_worker
asyncio.run(run_chain_worker.main())
'''
# every child process: utils.llm.ask_json answers from the calls file's count - first ask M1 + V1, then M2 alone
FAKE = r'''
import importlib.abc, importlib.util, json, os, re, sys

CALLS = os.environ["ASK_GATE_CALLS"]


def fake(prompt, **_kw):
    with open(CALLS, "a", encoding="utf-8") as out:
        out.write(json.dumps(len(prompt)) + "\n")
    asked = sum(1 for _ in open(CALLS, encoding="utf-8"))
    rows = [{"structure": "M1", "parent": None, "kind": "line"}, {"structure": "V1", "parent": "M1", "kind": "line"}]
    if asked > 1:
        rows = [{"structure": "M2", "parent": None, "kind": "line"}]
    return {"texts": [{"id": i, "rows": rows} for i in re.findall(r"^\[(.+)\]$", prompt, re.M)]}


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
    "ak_steps": {"composite_key_source": ["product", "step_seq"], "column_types": {
        "product": "string", "step_seq": "string", "step_desc": "string"}},
    "ak_structure": {"composite_key_source": ["product", "structure"], "column_types": {
        "product": "string", "structure": "string", "parent": "string", "kind": "string"}},
    "ak_common": {"business_key": "name", "column_types": {"name": "string"}},
}
DECLARATION = {
    "name": "structure_of_product", "on": {"table": "ak_steps"}, "into": {"table": "ak_structure"},
    "derive": {"kind": "ask", "ask": {
        "input": {"group_by": ["product"], "order_by": "step_seq", "text": ["step_desc"]},
        "output": {"carry": {"product": "product"}, "cells": ["structure", "parent", "kind"]},
        "common": {"cell": "kind", "table": "ak_common", "column": "name", "none": "no common"},
        "prompts": {"common": "Read the step sequence of one product."}}}}


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _put(opener, base, table, items):
    body = json.dumps({"updates": items}).encode()
    request = urllib.request.Request("%s/tables/%s/data/updates" % (base, table), data=body, method="PUT",
                                     headers={"Content-Type": "application/json"})
    try:
        with opener.open(request, timeout=60) as reply:
            return reply.status
    except urllib.error.HTTPError as reply:
        return reply.code, reply.read()[:500]


def _structure(db):
    with sqlite3.connect(db) as con:
        return {row[0]: row[1:] for row in con.execute(
            "SELECT structure, parent, kind FROM ak_structure WHERE product = 'P1'").fetchall()}


def _wait(what, worker, log, seconds=90):
    deadline = time.monotonic() + seconds
    while not what():
        assert worker.poll() is None, log.read_text(errors="replace")[-3000:]
        assert time.monotonic() < deadline, log.read_text(errors="replace")[-3000:]
        time.sleep(0.5)


def test_an_ask_rule_writes_its_rows_and_leaves_a_persons_alone(tmp_path):
    data = tmp_path / "data"
    (data / "config").mkdir(parents=True)
    (data / "config" / "table_config.json").write_text(json.dumps(TABLES), encoding="utf-8")
    (data / "config" / "chain_rules.json").write_text(json.dumps({"rules": [DECLARATION]}), encoding="utf-8")
    llm = json.load(open(os.path.join(SERVER_DIR, "config", "sample", "llm_config.json.sample"), encoding="utf-8"))
    llm.update(base_url="http://127.0.0.1:9/fake", model="fake-model", api_key="fake")
    (data / "config" / "llm_config.json").write_text(json.dumps(llm), encoding="utf-8")
    (tmp_path / "sitecustomize.py").write_text(FAKE, encoding="utf-8")
    for name, body in (("p_schema.py", SCHEMA), ("p_api.py", API), ("p_worker.py", WORKER)):
        (tmp_path / name).write_text(body, encoding="utf-8")
    db = tmp_path / "box.db"
    calls = tmp_path / "calls.txt"
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
        assert _put(opener, base, "ak_common", [{"updates": {"name": "line"}, "source_name": "ingest"}]) == 200
        steps = [{"updates": {"product": "P1", "step_seq": "%03d" % n, "step_desc": "step %d" % n},
                  "source_name": "ingest"} for n in range(6)]
        assert _put(opener, base, "ak_steps", steps) == 200

        _wait(lambda: set(_structure(db)) == {"M1", "V1"}, worker, log)
        first = _structure(db)
        assert first["M1"] == (None, "line") and first["V1"] == ("M1", "line")
        assert sum(1 for _ in open(calls, encoding="utf-8")) == 1, "one product, one call"

        # a person fixes a cell and adds a row
        assert _put(opener, base, "ak_structure", [
            {"updates": {"product": "P1", "structure": "M1", "parent": "by hand"}, "source_name": "user"},
            {"updates": {"product": "P1", "structure": "U1", "kind": "line"}, "source_name": "user"}]) == 200
        # a step changes: the rule runs again, and the model answers M2 alone - M1 and V1 are gone from it
        assert _put(opener, base, "ak_steps", [{"updates": {"product": "P1", "step_seq": "002",
                                                            "step_desc": "step 2 changed"},
                                                "source_name": "ingest"}]) == 200
        _wait(lambda: os.path.exists(calls) and sum(1 for _ in open(calls, encoding="utf-8")) >= 2, worker, log)
        time.sleep(5)                                       # the second answer's write
        after = _structure(db)
        print("after the second answer:", after)
        assert after["M2"] == (None, "line")
        # owner 10-28 «남김»: the gone seat takes this rule's cells and leaves a person's (B's seat)
        assert after.get("V1") in (None, (None, None)), "the rule's row the answer no longer gives is taken"
        assert after["M1"] == ("by hand", None), "a person's cell stays, the rule's cell goes"
        assert after["U1"] == (None, "line"), "a person's row stays"
        assert sum(1 for _ in open(calls, encoding="utf-8")) == 2
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
