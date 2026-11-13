# -*- coding: utf-8 -*-
"""Lead 11-09 ② (owner «필요한 로그는 빨리 다 지어»): every few minutes a [LayerHealth] line for each of the largest
tables this database writes - live · dead · last autovacuum · autovacuums · the vacuum on it now; how many tables and
how far apart a `pacing.json` job's cells; a failed reading «?» in its own cells.

  a lap                  one line per table read, its vacuum running or none, the job's rest returned
  the vacuum unread      every line's vacuum cell «?», the lines still said
  the tables unread      one line «tables ?», nothing else
  the job                declared in pacing.json - 8 tables, 300 s
"""
import datetime
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pacing                                                       # noqa: E402
from database import lines                                          # noqa: E402
from chain import ingestion_worker as worker                        # noqa: E402
from runtime import loops, stall_watch                              # noqa: E402

AT = datetime.datetime(2026, 11, 9, 6, 12, 3)
TABLES = [("cell_sources", 1200, 45, AT, 31, 180000000), ("public.dt_log", 900, 0, None, 0, 12)]
SCHEMAS = ["public", "w_alt"]


def _engine(monkeypatch, tables, asked):
    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, statement, params=None):
            asked.append(params)
            if isinstance(tables, Exception):
                raise tables
            return type("R", (), {"fetchall": lambda self: tables})()

    monkeypatch.setattr(stall_watch, "_kept", lambda: type("E", (), {"connect": lambda self: Conn()})())
    monkeypatch.setattr(lines, "every_schema_tables", lambda conn: (SCHEMAS, ["cell_sources", "dt_log"]))


def _lines(caplog):
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith("[LayerHealth]")]


def test_a_lap_names_each_table_its_vacuum_and_returns_the_rest(monkeypatch, caplog):
    asked = []
    _engine(monkeypatch, TABLES, asked)
    monkeypatch.setattr(pacing, "job_pace", lambda job: (2, 300.0) if job == worker.LAYER_HEALTH_JOB else None)
    monkeypatch.setattr(loops, "vacuums_running", lambda conn: [("cell_sources", "scanning heap", 1200, 50000)])
    caplog.set_level(logging.INFO, logger=worker.logger.name)
    assert worker._report_layer_table_health() == 300.0
    assert asked == [{"n": 2, "schemas": SCHEMAS, "names": ["cell_sources", "dt_log"]}]
    assert _lines(caplog) == [
        "[LayerHealth] cell_sources: live 1200 · dead 45 · last autovacuum 2026-11-09 06:12:03 · autovacuums 31 · "
        "xid age 180000000 · vacuum scanning heap 1200/50000",
        "[LayerHealth] public.dt_log: live 900 · dead 0 · last autovacuum never · autovacuums 0 · xid age 12 · "
        "vacuum none"]


def test_a_failed_reading_says_its_own_cells(monkeypatch, caplog):
    _engine(monkeypatch, TABLES, [])
    monkeypatch.setattr(pacing, "job_pace", lambda job: (2, 300.0))

    def unread(conn):
        raise RuntimeError("canceling statement due to statement timeout")

    monkeypatch.setattr(loops, "vacuums_running", unread)
    caplog.set_level(logging.INFO, logger=worker.logger.name)
    worker._report_layer_table_health()
    said = _lines(caplog)
    assert said[0].startswith("[LayerHealth] vacuum progress unread: canceling statement")
    assert [line.rsplit(" · ", 1)[1] for line in said[1:]] == ["vacuum ?", "vacuum ?"]

    caplog.clear()
    _engine(monkeypatch, RuntimeError("canceling statement due to statement timeout"), [])
    assert worker._report_layer_table_health() == 300.0
    assert [line.split(" - ")[0] for line in _lines(caplog)] == ["[LayerHealth] tables ?"]


def test_the_job_is_declared():
    assert pacing.job_pace(worker.LAYER_HEALTH_JOB) == (8, 300.0)
