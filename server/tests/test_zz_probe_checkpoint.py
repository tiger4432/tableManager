# -*- coding: utf-8 -*-
"""SCRATCH PROBE - not committed. What one retroactive page boundary costs (`retroactive._checkpoint`): the hook as
a whole and its parts, with a real run row; then with a mapper change left pending before every call, and with a
SYSTEM_RELOAD row before every call - what a boundary that stays pending would cost a page. Writes PROBE_OUT."""
import json
import os
import time

from sqlalchemy.orm import sessionmaker

from admin import retroactive
from chain import ingestion_worker
from database import config_watcher, models
from runtime import system_reload

OUT = os.environ.get("PROBE_OUT", "probe_checkpoint.jsonl")
N = int(os.environ.get("PROBE_CALLS", "20"))


def _ms(fn, n=N):
    began = time.perf_counter()
    for _ in range(n):
        fn()
    return round((time.perf_counter() - began) * 1000 / n, 2)


def test_probe(db_session, monkeypatch):
    bind = db_session.get_bind()
    maker = sessionmaker(bind=bind)
    import database.database as dbmod
    monkeypatch.setattr(dbmod, "SessionLocal", maker)
    db_session.add(models.RetroactiveRun(run_id="probe1", op="delete_every_row", state="running"))
    db_session.commit()
    control = retroactive.RunControl("probe1", session_factory=maker, op="delete_every_row", log=lambda *a: None)
    hook = retroactive._checkpoint(control)
    seen = [retroactive._reload_mark()]
    line = {"calls": N, "dialect": bind.dialect.name}
    each = []
    for _ in range(N):
        began = time.perf_counter()
        hook(10, None)
        each.append(round((time.perf_counter() - began) * 1000, 1))
    line["hook_each_ms"] = each
    line["hook_ms"] = _ms(lambda: hook(10, None))
    line["progress_ms"] = _ms(lambda: control.progress(10, None))
    line["stop_requested_ms"] = _ms(control.stop_requested)

    def boundary():
        seen[0] = retroactive._reload_between_pages(seen[0])
    line["reload_between_pages_ms"] = _ms(boundary)

    mapper = os.path.join(os.path.dirname(ingestion_worker.__file__), "..", "mappers", "hold_copy.py")
    monkeypatch.setattr(config_watcher, "_BOUNDARY", [True])
    assert config_watcher.name_of(os.path.abspath(mapper)) == config_watcher.MAPPERS
    applied = []

    def pending_mapper():
        config_watcher.changed(os.path.abspath(mapper))
        applied.append(bool(config_watcher._PENDING))
        boundary()
    line["boundary_with_a_pending_mapper_ms"] = _ms(pending_mapper, 5)
    line["pending_each_time"] = all(applied)

    def reload_row():
        system_reload.publish_reload(db_session, msg="probe")
        db_session.commit()
        boundary()
    line["boundary_with_a_reload_row_ms"] = _ms(reload_row, 3)
    with open(OUT, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(line) + "\n")
    print(line)
