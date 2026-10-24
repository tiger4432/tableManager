# -*- coding: utf-8 -*-
"""A chain group's failure says where it broke - «at <file>:<line> in <function>» (owner 10-24 «딸랑 이거 나오는데
어쩌라는 거임» → «2 해», lead): the traceback's innermost frame in a mapper file, else its innermost in the product.

Real processes - the API and the chain worker - on one sqlite file and a scratch data root, the owner's mappers in a
package of their own:
  mapper    a pandas error inside the owner's mapper (reset_index over a column of its index's name, as in ops) -
            the permanent failure line and the queue's recent failures name the mapper's file, line and function
  twice     the same failure in two transactions - the same sentence
  product   a mapper that hands back what the product cannot take - the product's innermost frame
"""
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SERVER_DIR)

import event_constants  # noqa: E402

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
BOOM = '''from mapper_sdk import mapper


def _fold(df):
    df = df.set_index("k", drop=False)
    return df.reset_index()


@mapper()
def owner_boom(df, db):
    return _fold(df)
'''
BAD = '''from mapper_sdk import mapper


@mapper()
def owner_bad(df, db):
    return 42
'''
TABLE = {"business_key": "k", "column_types": {"k": "string", "v": "string"}}
COLOUR = re.compile(r"\x1b\[[0-9;]*m")                  # the log's colour codes
SAID = re.compile(r"Transaction (\S+) permanently failed: .*\[rules=(\S+) tables=.*\]\. 원인: (.*)$")


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _failures(log):
    """{rule: [the permanent failure line's cause, in order]}"""
    out = {}
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        found = SAID.search(COLOUR.sub("", line))
        if found:
            out.setdefault(found.group(2), []).append(found.group(3).strip())
    return out


def test_a_chain_failure_says_where_it_broke(tmp_path):
    if os.path.exists(os.path.join(SERVER_DIR, "mappers", "__init__.py")):
        pytest.skip("server/mappers is a regular package here - the slot processes cannot see the scratch mappers")
    pkg = tmp_path / "mappers"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "boom.py").write_text(BOOM, encoding="utf-8")
    (pkg / "bad.py").write_text(BAD, encoding="utf-8")
    data = tmp_path / "data"
    (data / "config").mkdir(parents=True)
    (data / "config" / "table_config.json").write_text(json.dumps(
        {"t_a": TABLE, "t_b": TABLE, "t_dst": TABLE, "t_dst2": TABLE}), encoding="utf-8")
    (data / "config" / "chain_rules.json").write_text(json.dumps({"rules": [
        {"name": "r_boom", "trigger_table": "t_a", "mapper": "owner_boom", "target_table": "t_dst"},
        {"name": "r_bad", "trigger_table": "t_b", "mapper": "owner_bad", "target_table": "t_dst2"}]}),
        encoding="utf-8")
    for name, body in (("schema.py", SCHEMA), ("write.py", WRITE), ("api.py", API), ("worker.py", WORKER)):
        (tmp_path / name).write_text(body, encoding="utf-8")
    port = _free_port()
    base = "http://127.0.0.1:%d" % port
    env = dict(os.environ, ASSY_DATA_ROOT=str(data), DATABASE_URL="sqlite:///" + (tmp_path / "box.db").as_posix(),
               DECOUPLED="True", TESTING="True", API_BASE_URL=base, PYTHONIOENCODING="utf-8",
               PYTHONPATH=os.pathsep.join([str(tmp_path), SERVER_DIR]))
    env.pop("ASSY_ADMIN_TOKEN", None)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    subprocess.run([sys.executable, str(tmp_path / "schema.py")], cwd=SERVER_DIR, env=env, check=True,
                   capture_output=True)
    worker_log = tmp_path / "worker.log"
    logs = {name: open(tmp_path / ("%s.log" % name), "wb") for name in ("api", "worker")}
    api = subprocess.Popen([sys.executable, str(tmp_path / "api.py"), str(port)], cwd=SERVER_DIR, env=env,
                           stdout=logs["api"], stderr=subprocess.STDOUT)
    worker = subprocess.Popen([sys.executable, str(tmp_path / "worker.py")], cwd=SERVER_DIR, env=env,
                              stdout=logs["worker"], stderr=subprocess.STDOUT)

    def write(rows):
        subprocess.run([sys.executable, str(tmp_path / "write.py"), json.dumps(rows)], cwd=SERVER_DIR, env=env,
                       check=True, capture_output=True)

    def wait_for(rule, count, seconds=120):
        deadline = time.monotonic() + seconds
        while len(_failures(worker_log).get(rule, ())) < count:
            assert worker.poll() is None and time.monotonic() < deadline, (
                "no permanent failure line for %s: %s" % (rule, worker_log.read_text(errors="replace")[-3000:]))
            time.sleep(0.5)

    try:
        write({"t_a": [{"k": "a1", "v": "x"}]})
        wait_for("r_boom", 1)
        write({"t_a": [{"k": "a2", "v": "x"}]})
        wait_for("r_boom", 2)
        write({"t_b": [{"k": "b1", "v": "x"}]})
        wait_for("r_bad", 1)
        with opener.open(base + "/admin/chain/queue", timeout=60) as reply:
            queue = json.loads(reply.read())
    finally:
        for process in (api, worker):
            process.kill()
            process.wait(30)
        for log in logs.values():
            log.close()

    said = _failures(worker_log)
    line = BOOM.splitlines().index("    return df.reset_index()") + 1
    where = " at %s:%d in _fold" % (pkg / "boom.py", line)
    # mapper: the owner's file, line and function - the innermost of its frames; twice: the same sentence
    assert said["r_boom"] == ["ValueError: cannot insert k, already exists" + where] * 2, said
    # product: the product's innermost frame - where the decorator refuses what the mapper handed back, said from
    # the server folder (the mapper's own frame is no longer on the traceback)
    bad = said["r_bad"][0]
    assert re.search(r" at mapper_sdk\.py:\d+ in \S+$", bad), bad
    # the queue's recent failures draw the same sentence (one function: event_constants.failure_cause)
    drawn = {item.get("failure") for item in queue.get("recent_failures") or ()}
    assert {said["r_boom"][0], bad} <= drawn, (drawn, queue.get("recent_failures"))
    assert event_constants.failure_cause(said["r_boom"][0]) == said["r_boom"][0]      # a sentence reads as itself
    # the terminal: the whole traceback under the line, the mapper's frame in it (owner 10-24 «나 터미널 보고 일하니까»)
    text = COLOUR.sub("", worker_log.read_text(encoding="utf-8", errors="replace"))
    tail = text[text.index(" traceback:"):]
    assert "Traceback (most recent call last):" in tail and 'boom.py", line %d, in _fold' % line in tail, tail[:3000]
