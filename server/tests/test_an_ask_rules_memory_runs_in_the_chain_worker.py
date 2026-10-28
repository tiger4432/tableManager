"""The ask rule's memory half in the real processes (lead 10-27 A-3): the API takes a person's correction, the chain
worker's memory half writes the memory row, the next ask carries it in its prompt, and putting the AI's value back
takes the row away. sqlite, a stand-in model (the A-1 gate's hook, its prompts kept)."""
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

from test_an_ask_rule_runs_in_the_chain_worker import API, FAKE, SCHEMA, SERVER_DIR, WORKER, _free_port, _put, _wait

TABLES = {
    "ak_steps": {"composite_key_source": ["product", "step_seq"], "column_types": {
        "product": "string", "step_seq": "string", "step_desc": "string"}},
    "ak_structure": {"composite_key_source": ["product", "structure"], "column_types": {
        "product": "string", "structure": "string", "parent": "string", "kind": "string"}},
    "ak_memory": {"composite_key_source": ["purpose", "situation", "cell"], "column_types": {
        "purpose": "string", "situation": "string", "cell": "string", "ai": "string", "right": "string",
        "memo": "string", "who": "string", "at": "string"}},
}
DECLARATION = {
    "name": "structure_of_product", "on": {"table": "ak_steps"}, "into": {"table": "ak_structure"},
    "derive": {"kind": "ask", "ask": {
        "input": {"group_by": ["product"], "order_by": "step_seq", "text": ["step_desc"]},
        "output": {"carry": {"product": "product"}, "cells": ["structure", "parent", "kind"]},
        "prompts": {"memory": {"scope": ["product"], "limit": 5}},
        "memory": {"table": "ak_memory", "columns": {
            "purpose": "purpose", "key": "situation", "cell": "cell", "ai": "ai", "right": "right", "memo": "memo",
            "who": "who", "when": "at"}}}}}
# the A-1 hook, its prompts kept and the same two rows every time
KEPT = FAKE.replace('out.write(json.dumps(len(prompt)) + "\\n")', 'out.write(json.dumps(prompt) + "\\n")').replace(
    "    if asked > 1:\n", "    if False:\n")


def _memory(db):
    with sqlite3.connect(db) as con:
        return con.execute("SELECT purpose, situation, cell, ai, right FROM ak_memory "
                           "WHERE ai IS NOT NULL OR right IS NOT NULL").fetchall()


def _calls(path):
    return [json.loads(line) for line in open(path, encoding="utf-8")] if os.path.exists(path) else []


def test_a_correction_is_remembered_asked_with_and_taken_back(tmp_path):
    assert KEPT != FAKE and "if False" in KEPT, "the A-1 hook's lines this gate rewrites moved"
    data = tmp_path / "data"
    (data / "config").mkdir(parents=True)
    (data / "config" / "table_config.json").write_text(json.dumps(TABLES), encoding="utf-8")
    (data / "config" / "chain_rules.json").write_text(json.dumps({"rules": [DECLARATION]}), encoding="utf-8")
    llm = json.load(open(os.path.join(SERVER_DIR, "config", "sample", "llm_config.json.sample"), encoding="utf-8"))
    llm.update(base_url="http://127.0.0.1:9/fake", model="fake-model", api_key="fake")
    (data / "config" / "llm_config.json").write_text(json.dumps(llm), encoding="utf-8")
    (tmp_path / "sitecustomize.py").write_text(KEPT, encoding="utf-8")
    for name, body in (("p_schema.py", SCHEMA), ("p_api.py", API), ("p_worker.py", WORKER)):
        (tmp_path / name).write_text(body, encoding="utf-8")
    db, calls, port = tmp_path / "box.db", tmp_path / "calls.txt", _free_port()
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
    situation = json.dumps({"product": "P1", "structure": "V1"}, sort_keys=True, ensure_ascii=False)
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
        steps = [{"updates": {"product": "P1", "step_seq": "%03d" % n, "step_desc": "step %d" % n},
                  "source_name": "ingest"} for n in range(3)]
        assert _put(opener, base, "ak_steps", steps) == 200
        _wait(lambda: len(_calls(calls)) == 1, worker, log)
        assert "Past corrections" not in _calls(calls)[0]

        # a person corrects the AI's parent of V1
        assert _put(opener, base, "ak_structure", [{"updates": {"product": "P1", "structure": "V1",
                                                                "parent": "by hand"}, "source_name": "user"}]) == 200
        _wait(lambda: _memory(db), worker, log)
        assert _memory(db) == [("structure_of_product", situation, "parent", "M1", "by hand")]

        # the next ask carries it
        assert _put(opener, base, "ak_steps", [{"updates": {"product": "P1", "step_seq": "001",
                                                            "step_desc": "step 1 changed"},
                                                "source_name": "ingest"}]) == 200
        _wait(lambda: len(_calls(calls)) == 2, worker, log)
        second = _calls(calls)[1]
        print("prompt %d chars, the first %d" % (len(second), len(_calls(calls)[0])))
        assert "Past corrections" in second and "you said M1; correct: by hand" in second

        # the person puts the AI's value back: the memory row goes
        assert _put(opener, base, "ak_structure", [{"updates": {"product": "P1", "structure": "V1",
                                                                "parent": "M1"}, "source_name": "user"}]) == 200
        _wait(lambda: not _memory(db), worker, log, seconds=60)
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
