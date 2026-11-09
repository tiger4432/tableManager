# -*- coding: utf-8 -*-
"""총괄 10-07 ④: every HTTP response carries `Server-Timing` - the total, and the database time and
queries of THAT request - and a request over `slow_request_ms` (server/config/server_settings.json,
default 1000) says so in one line: method, path, status, total, db, queries, rows read, bytes and the
stages the request named (lead 11-09); never the query string or the body. A query outside the request
(a thread it starts) is not counted. A part that does not read says «?» in its place."""
import json
import logging
import re
import threading
import time

import pytest
from fastapi import Body
from fastapi.testclient import TestClient
from sqlalchemy import text

import main
from database import database
from runtime import request_timing

PROBE = "/__request_timing_probe"
SHAPE = re.compile(r'^total;dur=(\d+\.\d), db;dur=(\d+\.\d);desc="(\d+) queries"$')
#: One query long enough that its time cannot round to 0.0 ms (총괄 QA: db;dur must be measured).
SLOW_QUERY = ("WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 50000) "
              "SELECT count(*) FROM c")


@pytest.fixture(name="declare")
def fixture_declare(monkeypatch, tmp_path):
    """A route that runs three queries itself and two in a thread of its own."""
    def probe(sleep: float = 0.0, token: str = None, payload: dict = Body(None)):
        session = database.SessionLocal()
        try:
            session.execute(text("SELECT 1"))
            with request_timing.stage("probe"):
                session.execute(text("SELECT 1"))
                session.execute(text(SLOW_QUERY))
                time.sleep(sleep)
        finally:
            session.close()

        def outside():
            other = database.SessionLocal()
            try:
                other.execute(text("SELECT 1"))
                other.execute(text("SELECT 1"))
            finally:
                other.close()
        worker = threading.Thread(target=outside)
        worker.start()
        worker.join()
        return {"ok": True}

    main.app.add_api_route(PROBE, probe, methods=["GET", "POST"])
    route = main.app.router.routes.pop()
    main.app.router.routes.insert(0, route)                   # ahead of the screen's catch-all
    settings = tmp_path / request_timing.SETTINGS_FILE
    monkeypatch.setattr(request_timing, "SETTINGS_PATH", str(settings))
    from database import config_watcher
    config_watcher.forget_held()

    def declare(**cells):
        settings.write_text(json.dumps(cells), encoding="utf-8")
        from database import config_watcher
        config_watcher.forget_held()
    try:
        yield declare
    finally:
        main.app.router.routes.remove(route)
        from database import config_watcher
        config_watcher.forget_held()


def _slow_lines(caplog):
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith("[Slow] ")]


def test_every_response_carries_its_time_and_only_its_own_queries(declare):
    client = TestClient(main.app)
    answered = client.get(PROBE)
    total, db, queries = SHAPE.match(answered.headers["Server-Timing"]).groups()
    assert answered.status_code == 200 and queries == "3", answered.headers["Server-Timing"]
    assert 0 < float(db) <= float(total), answered.headers["Server-Timing"]     # the db time is measured
    other = client.get("/health")                              # a route nobody set up for this
    assert SHAPE.match(other.headers["Server-Timing"]), other.headers.get("Server-Timing")


def test_a_request_over_the_budget_says_so_in_one_line_and_one_under_it_does_not(declare, caplog):
    client = TestClient(main.app)
    declare(slow_request_ms=1)
    with caplog.at_level(logging.WARNING, logger="Server"):
        client.post(PROBE + "?sleep=0.02&token=SECRET-IN-QUERY", json={"secret": "SECRET-IN-BODY"})
    said = _slow_lines(caplog)
    assert len(said) == 1, said
    # rows: a driver that does not tell a SELECT's rows (SQLite) says «?», PostgreSQL the number
    rows, probe, db, python = re.match(
        r"^\[Slow\] POST %s 200 - 응답이 \d+ms 걸렸습니다 \(예산 1ms\) · db \d+ ms · 3 queries · (\?|3) rows · 11 bytes"
        r" · probe (\d+\.\d\d) s \(SQL (\d+\.\d\d) s · (?:\?|2) rows · Python (-?\d+\.\d\d) s\)"
        r" · serialize \d+\.\d\d s$" % re.escape(PROBE), said[0]).groups()
    assert float(probe) >= 0.02 and float(python) >= 0.01, said[0]      # the sleep is the stage's Python part
    assert "SECRET" not in said[0] and "token" not in said[0]
    caplog.clear()
    declare(slow_request_ms=100000)
    with caplog.at_level(logging.WARNING, logger="Server"):
        client.post(PROBE + "?sleep=0.02", json={"secret": "x"})
    assert _slow_lines(caplog) == []


def test_a_part_that_does_not_read_says_a_question_mark_and_the_line_goes_on(monkeypatch, caplog):
    monkeypatch.setattr(request_timing, "slow_request_ms", lambda: 0)
    began = request_timing.begin("/x")
    with request_timing.stage("built"):
        pass
    request_timing.add(0.0, 0, stages=[("broken",)])

    class Answered:
        status_code, headers = 200, {}                         # no content-length: the bytes do not read
    with caplog.at_level(logging.WARNING, logger="Server"):
        request_timing.end(began, "GET", "/x", Answered)
    why, missing, said = _slow_lines(caplog)
    assert why.startswith("[Slow] the next line says «?» for a part that could not be said: ") and "content-length" in why
    assert missing.startswith("[Slow] the next line says «?» ") and "missing 5 required" in missing, missing
    assert re.match(r"^\[Slow\] GET /x 200 - .* · 0 queries · 0 rows · \? · built \d+\.\d\d s · \?$", said), said


def test_the_budget_is_1000_ms_unless_declared_and_null_turns_the_line_off(declare):
    assert request_timing.slow_request_ms() == request_timing.DEFAULT_SLOW_REQUEST_MS == 1000
    declare(slow_request_ms=250)
    assert request_timing.slow_request_ms() == 250
    declare(slow_request_ms=None)
    assert request_timing.slow_request_ms() is None
