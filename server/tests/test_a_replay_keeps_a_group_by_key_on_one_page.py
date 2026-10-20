# -*- coding: utf-8 -*-
"""소유자 10-20 「집계하는 체인인데도 리플레이 쪼개네」 (총괄 47e2a155d): a replay's events name rows, so the worker
groups them by the page's transaction - a group_by key cut across pages reached an aggregating mapper in parts and the
later part overwrote the sum. A group_by rule's replay now pages whole keys (`keyset_scan.key_pages`), spelled by the
live grouping's own speller; a rule with no group_by pages as before. The worker here is its batch body
(`drain_events`), run between the replay's pages as the live worker takes each page as it lands.
"""
import asyncio
import os
import sys
import textwrap

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import event_constants                                                # noqa: E402
import mapper_sdk                                                     # noqa: E402
import pacing                                                         # noqa: E402
import paths                                                          # noqa: E402
from chain import ingestion_worker as worker                          # noqa: E402
from chain import replay                                              # noqa: E402
from database import crud, models, schemas                            # noqa: E402
from database.context import channel, outbox_mode                     # noqa: E402
from database.database import Base                                    # noqa: E402
from utils import heartbeat                                           # noqa: E402
from utils.payload_helper import get_payload_dict                     # noqa: E402

TABLES = {"gb_src": {"business_key": "k", "composite_key_source": ["k"],
                     "column_types": {"k": "string", "lot": "string", "n": "number"},
                     "display_columns": ["k", "lot", "n"]},
          "gb_sum": {"business_key": "lot", "composite_key_source": ["lot"],
                     "column_types": {"lot": "string", "total": "number", "rows": "number"},
                     "display_columns": ["lot", "total", "rows"]}}
MAPPERS = """
def sum_by_lot(db, payload, rule=None):
    sums = {}
    for p in (payload if isinstance(payload, list) else [payload]):
        data = p.get("data") or {}
        lot = ((data.get("lot") or {}).get("value") or "").strip() or "(blank)"
        total, rows = sums.get(lot, (0, 0))
        sums[lot] = (total + float((data.get("n") or {}).get("value") or 0), rows + 1)
    return {"updates": [{"business_key_val": lot, "updates": {"lot": lot, "total": total, "rows": rows}}
                        for lot, (total, rows) in sums.items()]}
"""
#: A 9, B 3, C 2, a blank key of three spellings, D 1 - interleaved, so a row_id page cuts every key it can
LOTS = ["A", "B", "A", "C", "", "A", "B", None, "A", "C", "A", "  ", "A", "B", "A", "D", "A", "A"]
ROWS = [{"k": "r%02d" % i, "lot": lot, "n": i + 1} for i, lot in enumerate(LOTS)]
WHOLE = {}
for _row in ROWS:
    _lot = (_row["lot"] or "").strip() or "(blank)"
    WHOLE[_lot] = (WHOLE.get(_lot, (0, 0))[0] + _row["n"], WHOLE.get(_lot, (0, 0))[1] + 1)


class _NoClose:
    def __init__(self, session):
        self._session = session

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self._session, name)


async def _no_post(_endpoint, _payload):
    return True


@pytest.fixture(name="db")
def fixture_db(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(heartbeat, "heartbeat_dir", lambda: str(tmp_path / "beats"))
    monkeypatch.setattr(heartbeat, "heartbeat_path", lambda name: str(tmp_path / "beats" / (name + ".json")))
    monkeypatch.setattr(worker, "post_event_async", _no_post)
    monkeypatch.setattr(pacing, "page_seconds", lambda: 1000.0)      # pages 1, 2, 4, 4 ... - no clock in the answer
    mapper_sdk.discover()
    (tmp_path / "gb_maps.py").write_text(textwrap.dedent(MAPPERS), encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("gb_maps", None)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    monkeypatch.setattr("database.database.SessionLocal", lambda: _NoClose(session))
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)
        sys.modules.pop("gb_maps", None)


def _rule(**cells):
    return {"name": "gb_sum_by_lot", "enabled": True, "is_batch": True, "trigger_table": "gb_src",
            "target_table": "gb_sum", "mapper_module": "gb_maps", "mapper_function": "sum_by_lot",
            "allow_chain_trigger": False, **cells}


BY_LOT = _rule(group_by=["lot"])


def _pending(db):
    return (db.query(models.DatabaseOutbox)
            .filter(models.DatabaseOutbox.processed_chain.is_(False),
                    models.DatabaseOutbox.table_name.in_(list(TABLES)))
            .order_by(models.DatabaseOutbox.id).all())


def _drain(db, rules, monkeypatch):
    monkeypatch.setattr(worker, "loaded_chain_rules", lambda: list(rules))
    for _ in range(40):
        pending = _pending(db)
        if not pending:
            return
        asyncio.run(worker.drain_events(db, pending, rules, None))
    raise AssertionError("the chain did not settle")


def _write(db, rules, monkeypatch):
    with channel(event_constants.CHANNEL_API), outbox_mode(event_constants.OUTBOX_MODE_PER_ROW):
        crud.apply_batch_updates(db, "gb_src", schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates=row, source_name="seed", updated_by="gb") for row in ROWS]))
        db.commit()
    _drain(db, rules, monkeypatch)


def _sums(db):
    db.expire_all()
    return {r.lot: (r.total, r.rows) for r in db.query(models.DYNAMIC_TABLES["gb_sum"]).all()}


def _replay(db, rule, monkeypatch, **kw):
    """The replay, the worker taking each page before the next is staged; -> (stats, staged row_id lists, log lines)."""
    staged, said = [], []

    def between_pages(_rows):
        for event in _pending(db):
            staged.append(sorted(get_payload_dict(event)["row_ids"]))
        _drain(db, [rule], monkeypatch)
        return False

    stats = replay.replay_rule(db, rule, apply=True, chunk_size=4, checkpoint=between_pages, log=said.append, **kw)
    between_pages(None)
    return stats, staged, said


def _row_ids(db):
    return {r.k: r.row_id for r in db.query(models.DYNAMIC_TABLES["gb_src"]).all()}


def test_the_live_chain_sums_each_key_whole(db, monkeypatch):
    """The answer the replay is held to - one commit, one batch, the live grouping."""
    _write(db, [BY_LOT], monkeypatch)
    assert _sums(db) == WHOLE


def test_a_replay_hands_each_key_whole_and_the_sums_are_the_live_ones(db, monkeypatch):
    _write(db, [], monkeypatch)                                  # the rows are there, the rule has not run
    assert _sums(db) == {}
    stats, staged, said = _replay(db, BY_LOT, monkeypatch)
    assert _sums(db) == WHOLE
    by_id = {row_id: (row["lot"] or "").strip() or "(blank)" for row, row_id in
             ((r, _row_ids(db)[r["k"]]) for r in ROWS)}
    pages_of = {}
    for number, ids in enumerate(staged):
        for row_id in ids:
            pages_of.setdefault(by_id[row_id], set()).add(number)
    assert all(len(pages) == 1 for pages in pages_of.values()), pages_of
    assert sorted(i for ids in staged for i in ids) == sorted(by_id)            # no row lost, the blank key included
    assert stats["rows_scanned"] == len(ROWS) and stats["events_staged"] == len(staged)
    assert any("key lot='A' holds 9 rows, more than a page of 4" in line for line in said), said


def test_a_rule_without_group_by_pages_as_before(db, monkeypatch):
    _write(db, [], monkeypatch)
    _stats, staged, _said = _replay(db, _rule(), monkeypatch)
    ordered = sorted(_row_ids(db).values())
    assert staged == [ordered[0:1], ordered[1:3], ordered[3:7], ordered[7:11], ordered[11:15], ordered[15:18]]


def test_a_dry_run_reads_its_limit_not_every_key(db, monkeypatch):
    """A preview stages nothing, so it pages as before - scan_limit rows, no key read."""
    _write(db, [], monkeypatch)
    said = []
    stats = replay.replay_rule(db, BY_LOT, apply=False, chunk_size=4, limit=2, log=said.append)
    assert stats["rows_scanned"] == 2 and not any("groups by" in line for line in said), said


def test_a_limit_ends_after_the_key_it_reached_and_says_how_far_past(db, monkeypatch):
    _write(db, [], monkeypatch)
    said = []
    stats = replay.replay_rule(db, BY_LOT, apply=True, chunk_size=4, limit=2, log=said.append)
    assert stats["rows_scanned"] == 9                        # the first key by row_id is A, nine rows
    assert "[replay] limit 2: 7 row(s) past it to keep the last key whole" in said
