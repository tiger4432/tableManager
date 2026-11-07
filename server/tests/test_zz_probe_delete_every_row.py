# -*- coding: utf-8 -*-
"""SCRATCH PROBE - not committed. «Delete every row» row by row, split by stage, on the hold world (PG throwaway DB):
LOG (trigger of hc_copy -> OFFICIAL, OFFICIAL read by a ledger source) deleted whole, with the rules and without."""
import json
import os
import time

import pytest
from sqlalchemy import text

from chain import cell_layer, replay
from chain import ingestion_worker as worker
from database import crud
from ledger import followup
from support import hold_world as hw

pytestmark = pytest.mark.pg
OUT = os.environ.get("PROBE_OUT", "probe_delete.jsonl")
SIZES = [int(n) for n in os.environ.get("PROBE_SIZES", "1000").split(",")]


@pytest.fixture(name="world")
def fixture_world(pg_engine, monkeypatch, tmp_path):
    yield from hw.build(pg_engine, monkeypatch, tmp_path, batch=True)


def _timed(monkeypatch, owner, name, label, spent, counts):
    real = getattr(owner, name)

    def wrap(*a, **k):
        began = time.perf_counter()
        try:
            return real(*a, **k)
        finally:
            spent[label] = spent.get(label, 0.0) + time.perf_counter() - began
            counts[label] = counts.get(label, 0) + 1
    monkeypatch.setattr(owner, name, wrap)


@pytest.mark.parametrize("rules", ["with_rules", "no_rules", "live"])
@pytest.mark.parametrize("n", SIZES)
def test_probe(world, monkeypatch, n, rules):
    import database.database as dbmod
    import session_contract
    from admin.audit_cache import AuditLogCache

    monkeypatch.setattr(hw, "stale_holds", lambda *a: [])     # the hold world's own after-commit oracle - not the product's

    rows = [{"log_id": "L%06d" % i, "dt_job": "J%d" % (i // 100), "dt_x": i % 10, "dt_y": (i // 10) % 10, "netdie": i}
            for i in range(n)]
    if rules == "no_rules":
        world["rules"][:] = []
    began = time.perf_counter()
    for i in range(0, n, 1000):
        hw.push(world, rows[i:i + 1000])
    if rules == "no_rules":
        hw.run_chain(world, rounds=200)
    else:
        hw.settle(world, rounds=200)
    seed = time.perf_counter() - began
    live, done = None, []
    if rules == "live":                     # the chain and the ledger follow-up running while the op deletes
        import threading
        from sqlalchemy.orm import sessionmaker
        other = dict(world, db=sessionmaker(autocommit=False, autoflush=False, bind=world["engine"])())

        def keep_settling():
            while not done:
                hw.settle(other, rounds=400)
                time.sleep(0.2)
        live = threading.Thread(target=keep_settling, daemon=True)
    db = world["db"]
    official = db.execute(text('SELECT count(*) FROM "%s"' % hw.OFFICIAL)).scalar()
    spent, counts = {}, {}
    for owner, name, label in (
            (crud, "delete_rows_batch", "delete_rows_batch (all)"),
            (crud, "delete_row_layers", "  layers (cell_sources+overwrites)"),
            (crud, "record_row_deletions", "  audit write"),
            (dbmod, "stage_collapsed_event", "  outbox event"),
            (session_contract, "end_step", "  commit"),
            (AuditLogCache, "add_logs_batch", "  audit cache"),
            (worker, "_process_chain_transaction_group_sync", "chain group (all)"),
            (worker, "_delete_gone", "  _delete_gone"),
            (worker, "_withdraw_blanks", "  _withdraw_blanks"),
            (worker, "_move_off_the_plain_layer", "  _move_off_the_plain_layer"),
            (cell_layer, "cells_written_by", "  cells_written_by"),
            (worker, "_retract_deleted_rows", "chain retract deleted rows"),
            (followup, "drain_outbox_once", "ledger follow-up"),
            (replay.keyset_scan, "iter_pages", "  keyset read (generator made)")):
        _timed(monkeypatch, owner, name, label, spent, counts)
    if live is not None:
        live.start()
    began = time.perf_counter()
    stats = replay.delete_every_row(db, hw.LOG, apply=True, log=lambda m: None)
    op = time.perf_counter() - began
    if live is not None:
        done.append(True)
        live.join(600)
    op_stages, op_counts = dict(spent), dict(counts)
    spent.clear()
    counts.clear()
    began = time.perf_counter()
    if rules == "no_rules":
        hw.run_chain(world, rounds=400)
    else:
        hw.settle(world, rounds=400)
    after = time.perf_counter() - began
    left = db.execute(text('SELECT count(*) FROM "%s"' % hw.OFFICIAL)).scalar()
    line = {"n": n, "rules": rules, "seed_s": round(seed, 2), "official_before": official, "official_after": left,
            "op_s": round(op, 3), "op_rows_per_s": round(n / op, 1), "pages": stats["pages"],
            "deleted": stats["rows_deleted"], "settle_s": round(after, 3),
            "op_stages": {k: [round(v, 3), op_counts[k], round(v * 1000 / n, 3)] for k, v in op_stages.items()},
            "settle_stages": {k: [round(v, 3), counts[k], round(v * 1000 / n, 3)] for k, v in spent.items()}}
    with open(OUT, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, ensure_ascii=False) + "\n")
    assert stats["rows_deleted"] == n
