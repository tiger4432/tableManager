# -*- coding: utf-8 -*-
"""A retroactive page longer than the stall rule reads progressing while its steps return; a step waiting
on another connection's lock still reads stalled (총괄 e71f7d6f1, 소유자 「왜 요즘 만들어 주는 거 죄다
stalled 뜨냐」 · 「깜깜이라 되는 건지 느린 건지」). The op's own thread stamps each step's end
(`RunControl.step`) - a timer would read a lock wait as progressing."""
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import notation_norm as nn                                                  # noqa: E402
from admin import retroactive                                               # noqa: E402
from chain import keyset_scan, replay                                       # noqa: E402
from database import models                                                 # noqa: E402

pytestmark = pytest.mark.pg

TABLE, RUN = "pgqa_bk_table", "stallsteps01"
STALL = 3.0          # the stall rule, shortened
SLOW = 1.8           # the read and the fold of every page: each under the rule, the page over it


def test_a_slow_page_reads_progressing_and_a_lock_wait_reads_stalled(pg_engine, pg_session, tmp_path,
                                                                      monkeypatch):
    rules = tmp_path / "notation_rules.json"
    rules.write_text(json.dumps({"columns": {TABLE: {"note": {"write": True, "rules": {"join": "-"}}}}}),
                     encoding="utf-8")
    monkeypatch.setattr(nn, "NOTATION_RULES_PATH", str(rules))
    from database import config_watcher
    config_watcher.forget_held()
    model = models.DYNAMIC_TABLES[TABLE]
    for n in (1, 2):                                     # one row a page; each page folds x.n -> x-n
        pg_session.add(model(row_id="r%d" % n, business_key_val="P%d" % n, part_no="P%d" % n, note="x.%d" % n))
    now = datetime.now(timezone.utc)
    pg_session.add(models.RetroactiveRun(run_id=RUN, op="fold_written_notation", state="running",
                                         queued_at=now, started_at=now, last_progress_at=now))
    pg_session.commit()

    real_pages, real_fold = keyset_scan.iter_pages, replay._fold_by_values

    def slow_pages(*args, **kwargs):
        for page in real_pages(*args, **kwargs):
            time.sleep(SLOW)
            yield page

    def slow_fold(*args, **kwargs):
        time.sleep(SLOW)
        return real_fold(*args, **kwargs)

    monkeypatch.setattr(keyset_scan, "iter_pages", slow_pages)
    monkeypatch.setattr(replay, "_fold_by_values", slow_fold)
    monkeypatch.setattr(retroactive, "announce_progress", lambda *a, **k: True)     # no web server here
    factory = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)
    said = []                                             # the run's log - where its step lines go
    hook = retroactive._checkpoint(retroactive.RunControl(RUN, session_factory=factory, op="fold_written_notation",
                                                          log=said.append))

    holder = pg_engine.connect()                          # the second page's row, held by another connection
    held = holder.begin()
    holder.execute(text("SELECT 1 FROM %s WHERE row_id = 'r2' FOR UPDATE" % TABLE))
    holder_pid = holder.execute(text("SELECT pg_backend_pid()")).scalar()
    op = threading.Thread(target=replay.fold_written_notation, args=(pg_session, TABLE),
                          kwargs={"apply": True, "chunk_size": 1, "checkpoint": hook, "log": lambda m: None})
    seen = []                                             # (moving, the op waits on the holder, notes)
    try:
        op.start()
        deadline = time.monotonic() + 4 * SLOW + STALL + 10
        while time.monotonic() < deadline and (not seen or seen[-1][0] != retroactive.MOVING_STALLED):
            time.sleep(0.25)
            with factory() as db:
                moving = retroactive.in_flight(db, stall_after=STALL)["moving"]
                waits = db.execute(text("SELECT count(*) FROM pg_stat_activity WHERE :holder = ANY("
                                        "pg_blocking_pids(pid))"), {"holder": holder_pid}).scalar()
                notes = sorted(db.execute(text("SELECT note FROM %s" % TABLE)).scalars())
            seen.append((moving, waits > 0, notes))
        held.rollback()
        op.join(30)
    finally:
        holder.close()
        with factory() as db:
            db.query(models.RetroactiveRun).filter(models.RetroactiveRun.run_id == RUN).delete()
            db.commit()

    # ① before the lock wait every reading is progressing - page one (2 x SLOW) is longer than STALL
    before = [s for s in seen if not s[1]]
    assert before and {s[0] for s in before} == {retroactive.MOVING_PROGRESSING}, seen
    # ② page one written, page two's write held by the holder: stalled
    assert seen[-1] == (retroactive.MOVING_STALLED, True, ["x-1", "x.2"]), seen
    # the step lines - a page line (`RunControl._page_line`, its rows/s) is the boundary's, not a step's
    lines = [line.rsplit(" · ", 1)[0] for line in said if "rows/s" not in line]
    assert lines == ["[fold_written_notation] page %d: %s · 1 rows" % step for step in (
        (1, "read"), (1, "fold"), (1, "write"), (2, "read"), (2, "fold"), (2, "write"))], lines
