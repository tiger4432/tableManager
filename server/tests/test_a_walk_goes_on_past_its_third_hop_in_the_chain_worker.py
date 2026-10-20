# -*- coding: utf-8 -*-
"""e38466810 (lead 10-21: 「착지 전에 진짜 프로세스로 홉 3 이상 이어짐을 한 번」): the agent walk's two shipped rules
take turns in the real chain worker - a rule is never woken by its own writes, so walk_request -> walk_log ->
walk_request ... - and the walk goes on to its fourth hop and ends there with max_chain_depth 8, no event refused for
its depth.

Real: the chain worker and its slot processes, the outbox, the two rules as `chain_rules.json.sample` ships them, a
gateway answering over HTTP (a stub). Not real, and said: the one-hop ledger walk and the declaration read - both need
the PostgreSQL ledger - and `utils.llm.ask_json`'s openai client (not installed on every box; the same POST) are
replaced in a scratch `mappers` package that runs the product's `mappers/agent_walk.py` whole and replaces those
seams after it."""
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SERVER_DIR)

import product_tables  # noqa: E402

PATH = '''
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))     # the scratch mappers package first
sys.path.insert(1, os.path.join(os.getcwd(), "parsers"))
'''
SCHEMA = PATH + '''
import paths
from database.database import Base, engine
from database import models
models.init_dynamic_models(json.load(open(paths.config_path("table_config.json"), encoding="utf-8")))
Base.metadata.create_all(bind=engine)
'''
WRITE = PATH + '''
import paths
from database.database import SessionLocal
from database import crud, models, schemas
models.init_dynamic_models(json.load(open(paths.config_path("table_config.json"), encoding="utf-8")))
crud.TABLE_CONFIG.update(json.load(open(paths.config_path("table_config.json"), encoding="utf-8")))
db = SessionLocal()
for table, rows in json.loads(sys.argv[1]).items():
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates=row, source_name="user", updated_by="t") for row in rows]))
    db.commit()
'''
WORKER = PATH + '''
import asyncio
import run_chain_worker
asyncio.run(run_chain_worker.main())
'''
#: The product mapper, whole, then its two PostgreSQL seams: a line of steps (n - next -> n+1) and its declaration.
SCRATCH_MAPPER = '''
import os
_PRODUCT = os.path.join(os.environ["ASSY_SERVER_DIR"], "mappers", "agent_walk.py")
exec(compile(open(_PRODUCT, encoding="utf-8").read(), _PRODUCT, "exec"))

from ledger import explorer as _explorer, trace_router as _trace_router

_DECLARATION = {"entities": {"step@1": {"keys": ["n"]}},
                "vocabulary": {"next@1": {"subjects": ["step@1"],
                                          "object": {"kind": "entity_ref", "types": ["step@1"]}}}}
_trace_router._declaration = lambda world=None: _DECLARATION


def _step(n):
    return _explorer.entity_id("step", {"n": str(n)})


def _ask_json(prompt, system=None):
    """`utils.llm.ask_json` without the openai client (not installed on every box): the same POST to the gateway."""
    import json as _json
    import urllib.request as _request

    cells = _json.load(open(os.path.join(os.environ["ASSY_DATA_ROOT"], "config", "llm_config.json"), encoding="utf-8"))
    body = _json.dumps({"model": cells["model"], "messages": [{"role": "user", "content": prompt}]}).encode()
    opener = _request.build_opener(_request.ProxyHandler({}))
    answer = opener.open(_request.Request(cells["base_url"] + "chat/completions", data=body,
                                          headers={"Content-Type": "application/json"}), timeout=30)
    return _json.loads(_json.loads(answer.read())["choices"][0]["message"]["content"])


from utils import llm as _llm
_llm.ask_json = _ask_json


def _one_hop(db, position, limit):
    n = int(_explorer.decode_entity_id(position)[1]["n"])
    return {"nodes": [{"id": _step(k), "type": "step", "label": str(k)} for k in (n, n + 1)],
            "edges": [{"source": _step(n), "target": _step(n + 1), "predicate": "next"}]}
'''
TABLES = (product_tables.WALK_REQUEST_TABLE, product_tables.WALK_LOG_TABLE, product_tables.WALK_RECIPE_TABLE,
          product_tables.MEANING_TABLE)
RECIPE = [("on_node", 1, "edges"), ("on_node", 2, "path"), ("on_node", 3, "budget"), ("on_node", 4, "question"),
          ("stuck", 1, "dead_end"), ("end", 1, "full_path")]


class Gateway(BaseHTTPRequestHandler):
    """A chat-completions stub: go to the highest step listed; at the end, answer."""
    asked = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        prompt = body["messages"][-1]["content"]
        Gateway.asked.append(prompt)
        if '{"go"' not in prompt:
            said = {"answer": "the line goes on", "evidence": ["N1"], "rule_draft": ""}
        else:
            listed = re.findall(r"^(N\d+): step (\d+)", prompt, re.M)
            said = {"go": max(listed, key=lambda pair: int(pair[1]))[0], "reason": "further along"}
        out = json.dumps({"id": "c%d" % len(Gateway.asked), "object": "chat.completion", "created": 0,
                          "model": "stub", "choices": [{"index": 0, "finish_reason": "stop",
                                                        "message": {"role": "assistant", "content": json.dumps(said)}}],
                          "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *args):
        pass


def _shipped(names):
    with open(os.path.join(SERVER_DIR, "config", "sample", "chain_rules.json.sample"), encoding="utf-8") as f:
        rules = json.load(f)["rules"]
    return [rule for rule in rules if rule.get("name") in names]


def test_the_walk_goes_on_past_its_third_hop_and_ends_at_half_the_depth(tmp_path):
    if os.path.exists(os.path.join(SERVER_DIR, "mappers", "__init__.py")):
        pytest.skip("server/mappers is a regular package here - the slot processes cannot see the scratch mappers")
    pkg = tmp_path / "mappers"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "agent_walk.py").write_text(SCRATCH_MAPPER, encoding="utf-8")
    gateway = ThreadingHTTPServer(("127.0.0.1", 0), Gateway)
    threading.Thread(target=gateway.serve_forever, daemon=True).start()
    Gateway.asked = []
    data = tmp_path / "data"
    (data / "config").mkdir(parents=True)
    (data / "config" / "table_config.json").write_text(json.dumps(
        {t: product_tables.PRODUCT_TABLES[t] for t in TABLES}), encoding="utf-8")
    (data / "config" / "chain_rules.json").write_text(json.dumps(
        {"max_chain_depth": 8, "rules": _shipped({"agent_walk_hop", "agent_walk_follow"})}), encoding="utf-8")
    (data / "config" / "llm_config.json").write_text(json.dumps(
        {"base_url": "http://127.0.0.1:%d/v1/" % gateway.server_address[1], "model": "stub",
         "api_key": "test-key", "proxy": None}), encoding="utf-8")
    for name, body in (("schema", SCHEMA), ("write", WRITE), ("worker", WORKER)):
        (tmp_path / ("%s.py" % name)).write_text(body, encoding="utf-8")
    box = tmp_path / "box.db"
    env = dict(os.environ, ASSY_DATA_ROOT=str(data), DATABASE_URL="sqlite:///" + box.as_posix(), DECOUPLED="True",
               TESTING="True", API_BASE_URL="http://127.0.0.1:9", PYTHONIOENCODING="utf-8", ASSY_SERVER_DIR=SERVER_DIR,
               PYTHONPATH=os.pathsep.join([str(tmp_path), SERVER_DIR]))   # the slots find the scratch package too
    subprocess.run([sys.executable, str(tmp_path / "schema.py")], cwd=SERVER_DIR, env=env, check=True,
                   capture_output=True)
    from ledger import explorer
    start = explorer.entity_id("step", {"n": "0"})
    rows = {product_tables.WALK_RECIPE_TABLE: [{"recipe": "r", "state": s, "card_order": o, "card": c,
                                                "card_limit": 5} for s, o, c in RECIPE],
            product_tables.WALK_REQUEST_TABLE: [{"request_id": "q1", "question": "Where does step 0 lead?",
                                                 "start_node": start, "recipe": "r"}]}
    log = open(tmp_path / "worker.log", "wb")
    worker = subprocess.Popen([sys.executable, str(tmp_path / "worker.py")], cwd=SERVER_DIR, env=env,
                              stdout=log, stderr=subprocess.STDOUT)
    try:
        subprocess.run([sys.executable, str(tmp_path / "write.py"), json.dumps(rows)], cwd=SERVER_DIR, env=env,
                       check=True, capture_output=True)
        deadline, written = time.monotonic() + 240, []
        while not any(kind == "end" for _s, kind, *_ in written):
            assert worker.poll() is None and time.monotonic() < deadline, (
                written, (tmp_path / "worker.log").read_text(errors="replace")[-4000:])
            time.sleep(1)
            with sqlite3.connect(box) as conn:
                written = conn.execute("SELECT step, kind, position, reason FROM walk_log WHERE request_id = 'q1' "
                                       "ORDER BY step").fetchall()
        time.sleep(3)                                        # the request's last turn, and nothing after it
        with sqlite3.connect(box) as conn:
            request = conn.execute("SELECT state, step FROM walk_request WHERE request_id = 'q1'").fetchone()
            failed = conn.execute("SELECT count(*) FROM database_outbox WHERE status = 'FAILED'").fetchone()[0]
            written = conn.execute("SELECT step, kind, position, reason FROM walk_log WHERE request_id = 'q1' "
                                   "ORDER BY step").fetchall()
    finally:
        worker.terminate()
        worker.wait(30)
        log.close()
        gateway.shutdown()
    said = (tmp_path / "worker.log").read_text(errors="replace")
    assert [(int(step), kind) for step, kind, *_ in written] == [(1, "hop"), (2, "hop"), (3, "hop"), (4, "hop"),
                                                                 (5, "end")], (written, said[-3000:])
    assert [explorer.decode_entity_id(position)[1]["n"] for _s, _k, position, _r in written[:4]] == ["1", "2", "3", "4"]
    assert written[-1][3] == "chain depth 8 → 4 hops"
    assert len(Gateway.asked) == 5                              # four hops and the end
    assert request[0] == "end" and int(request[1]) == 5
    assert failed == 0 and "[Chain Depth]" not in said
