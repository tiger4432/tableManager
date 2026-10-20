# -*- coding: utf-8 -*-
"""A mapper name refused once is not refused until the next reload (lead 10-20, owner: a healthy mapper refused as
«unresolvable_mapper» until a reload).

Real processes - the API (uvicorn) and the chain worker - on one sqlite file and a scratch data root, the owner's
mappers in a package of their own (one imports another; one refuses to import while a flag file stands):
  window   reloads while requests read the rule list: after each reload the rule still runs in the API
  flag     a module that did not import at boot imports on the next ask - the save gate takes the rule naming it, and
           the worker's next reload runs it; while it cannot, the refusal says why
"""
import json
import os
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RELOADS = 8

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
TABLE = {"business_key": "k", "column_types": {"k": "string", "v": "string"}}


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _ask(opener, url, body=None, timeout=60):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, method="GET" if body is None else "POST",
                                     headers={"Content-Type": "application/json"})
    try:
        with opener.open(request, timeout=timeout) as reply:
            return reply.status, json.loads(reply.read() or b"null")
    except urllib.error.HTTPError as reply:
        return reply.code, json.loads(reply.read() or b"null")


def _states(opener, base):
    _code, said = _ask(opener, base + "/admin/chain/rules")
    return {rule.get("name"): rule.get("rule_state") for rule in (said or {}).get("data") or []}


def test_a_mapper_refused_once_is_found_on_the_next_ask(tmp_path):
    if os.path.exists(os.path.join(SERVER_DIR, "mappers", "__init__.py")):
        # the slots start as `python -m` from the server folder: a regular `mappers` package there wins over the scratch one
        pytest.skip("server/mappers is a regular package here - the slot processes cannot see the scratch mappers")
    pkg = tmp_path / "mappers"
    pkg.mkdir()
    flag = tmp_path / "flag"
    flag.write_text("up", encoding="utf-8")
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "common.py").write_text("import time\ntime.sleep(0.05)\nFACTOR = 2\n", encoding="utf-8")
    (pkg / "m0.py").write_text("from mappers import common\nfrom mapper_sdk import mapper\n\n"
                               "@mapper()\ndef owner_m0(df, db):\n    return df\n", encoding="utf-8")
    (pkg / "flaky.py").write_text("import os\nif os.path.exists(%r):\n    raise ImportError('the probe flag is up')\n"
                                  "from mapper_sdk import mapper\n\n@mapper()\ndef owner_flaky(df, db):\n"
                                  "    return df\n" % str(flag), encoding="utf-8")
    data = tmp_path / "data"
    (data / "config").mkdir(parents=True)
    (data / "config" / "table_config.json").write_text(json.dumps({"t_src": TABLE, "t_dst": TABLE}), encoding="utf-8")
    (data / "config" / "chain_rules.json").write_text(json.dumps({"rules": [
        {"name": "r0", "trigger_table": "t_src", "mapper": "owner_m0", "target_table": "t_dst"},
        {"name": "r1", "trigger_table": "t_src", "mapper": "owner_flaky", "target_table": "t_dst"}]}),
        encoding="utf-8")
    (tmp_path / "schema.py").write_text(SCHEMA, encoding="utf-8")
    (tmp_path / "api.py").write_text(API, encoding="utf-8")
    (tmp_path / "worker.py").write_text(WORKER, encoding="utf-8")
    port = _free_port()
    base = "http://127.0.0.1:%d" % port
    env = dict(os.environ, ASSY_DATA_ROOT=str(data), DATABASE_URL="sqlite:///" + (tmp_path / "box.db").as_posix(),
               DECOUPLED="True", TESTING="True", API_BASE_URL=base, PYTHONIOENCODING="utf-8",
               PYTHONPATH=os.pathsep.join([str(tmp_path), SERVER_DIR]))   # the slots find the scratch package too
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    subprocess.run([sys.executable, str(tmp_path / "schema.py")], cwd=SERVER_DIR, env=env, check=True,
                   capture_output=True)
    logs = {name: open(tmp_path / ("%s.log" % name), "wb") for name in ("api", "worker")}
    api = subprocess.Popen([sys.executable, str(tmp_path / "api.py"), str(port)], cwd=SERVER_DIR, env=env,
                           stdout=logs["api"], stderr=subprocess.STDOUT)
    worker = subprocess.Popen([sys.executable, str(tmp_path / "worker.py")], cwd=SERVER_DIR, env=env,
                              stdout=logs["worker"], stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 120
        while True:
            assert api.poll() is None, (tmp_path / "api.log").read_text(errors="replace")[-3000:]
            try:
                _ask(opener, base + "/health", timeout=5)
                break
            except OSError:
                assert time.monotonic() < deadline, "the API never came up"
                time.sleep(0.5)

        while "Mapper module refused: mappers.flaky" not in (tmp_path / "worker.log").read_text(errors="replace"):
            assert worker.poll() is None and time.monotonic() < deadline, "the worker never walked with the flag up"
            time.sleep(0.5)

        # flag: refused at boot, and the refusal says why
        assert _states(opener, base)["r1"] != "running"
        _code, opened = _ask(opener, base + "/admin/chain/rules/raw?name=r1")
        rule = {"trigger_table": "t_src", "mapper": "owner_flaky", "target_table": "t_dst", "enabled": True}
        code, refused = _ask(opener, base + "/admin/chain/rules/raw",
                             {"name": "r1", "declaration": rule, "base": opened["base"]})
        assert code >= 400 and "mappers.flaky did not import: ImportError: the probe flag is up" in json.dumps(refused)
        flag.unlink()
        _code, opened = _ask(opener, base + "/admin/chain/rules/raw?name=r1")
        code, saved = _ask(opener, base + "/admin/chain/rules/raw",
                           {"name": "r1", "declaration": rule, "base": opened["base"]})
        assert code == 200, saved

        # window: reloads while requests read the rule list
        stop = threading.Event()

        def read():
            while not stop.is_set():
                try:
                    _states(opener, base)
                except OSError:
                    pass

        readers = [threading.Thread(target=read) for _ in range(3)]
        for reader in readers:
            reader.start()
        after = []
        try:
            for _ in range(RELOADS):
                code, _said = _ask(opener, base + "/admin/reload-configs", {})
                assert code == 200
                after.append(_states(opener, base))
        finally:
            stop.set()
            for reader in readers:
                reader.join(60)
        time.sleep(8)                                  # the worker reads the last reload
    finally:
        for process in (api, worker):
            process.kill()
            process.wait(30)
        for log in logs.values():
            log.close()
    dropped = [states for states in after if states.get("r0") != "running" or states.get("r1") != "running"]
    assert dropped == [], "%d of %d reloads left a rule not running: %s" % (len(dropped), RELOADS, dropped[:2])
    said = (tmp_path / "worker.log").read_text(encoding="utf-8", errors="replace")
    loads = [line.split("[Reload] Loaded", 1)[1].split(" active", 1)[0].strip()
             for line in said.splitlines() if "[Reload] Loaded" in line]
    assert loads and set(loads) == {"2"}, "each reload after the flag came down runs both rules: %s" % loads
