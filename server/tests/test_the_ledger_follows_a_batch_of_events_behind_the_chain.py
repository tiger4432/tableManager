# -*- coding: utf-8 -*-
"""총괄 7763dd6d0 · 796f04605 ② — the ledger process follows several events at once, behind the chain.

A batch takes the oldest events up to a row budget and follows each table's run of one kind once; what it writes is
what following them one at a time writes - additions, an edit and a deletion mixed, in their order. A translation that
covered several chain transactions leaves a receipt in each of them (lead (가)). The chain's Pause holds the follow-up:
no new batch is taken while it lasts.
"""
import asyncio
import os
import sys

import pytest
from sqlalchemy import event as sa_event, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from chain import control as chain_control                          # noqa: E402
from database import crud                                            # noqa: E402
from ledger import followup, schema                                 # noqa: E402
from ledger import worker as ledger_worker                          # noqa: E402
from ledger.runtime_v2 import RECEIPT_COLUMN                        # noqa: E402
from support import hold_world as hw                                # noqa: E402

pytestmark = pytest.mark.pg


@pytest.fixture(name="world")
def fixture_world(pg_engine, monkeypatch, tmp_path):
    yield from hw.build(pg_engine, monkeypatch, tmp_path)


def _row(i, netdie):
    return {"log_id": "L%03d" % i, "dt_job": "J%03d" % i, "dt_x": 1, "dt_y": 2, "netdie": netdie}


def _changes(world):
    """Transactions on the log - two additions, an edit of one, the other deleted - then a row of the table the ledger
    reads deleted, then one more addition: a batch of that table holds a deletion between additions."""
    hw.push(world, [_row(1, 10), _row(2, 20)])
    hw.push(world, [_row(1, 11)])
    hw.delete(world, "L002")
    hw.run_chain(world)
    db = world["db"]
    row_id = db.execute(text('SELECT row_id FROM "%s" WHERE dt_job = :j' % hw.OFFICIAL), {"j": "J001"}).scalar()
    crud.delete_rows_batch(db, hw.OFFICIAL, [row_id], "hc")
    db.commit()
    hw.push(world, [_row(3, 30)])
    hw.run_chain(world)


def _written(world):
    """The source's atoms (every column but id) and its row index lines."""
    with world["engine"].connect() as conn:
        columns = [r[0] for r in conn.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = current_schema() AND "
            "table_name = :t AND column_name <> 'id' ORDER BY ordinal_position"), {"t": schema.LEDGER_TABLE})]
        atoms = sorted(tuple(map(str, r)) for r in conn.execute(text(
            "SELECT %s FROM %s WHERE source_who = :s" % (", ".join(columns), schema.LEDGER_TABLE)), {"s": hw.SOURCE}))
        refs = sorted(tuple(map(str, r)) for r in conn.execute(text(
            "SELECT * FROM %s WHERE source_who = :s" % schema.ROW_REF_TABLE), {"s": hw.SOURCE}))
    return atoms, refs


def _forget_and_requeue(world):
    """The ledger's facts of the source gone and every event waiting for it again."""
    with world["engine"].begin() as conn:
        conn.execute(text("DELETE FROM %s WHERE source_who = :s" % schema.LEDGER_TABLE), {"s": hw.SOURCE})
        conn.execute(text("DELETE FROM %s WHERE source_who = :s" % schema.ROW_REF_TABLE), {"s": hw.SOURCE})
        conn.execute(text("DELETE FROM audit_logs WHERE column_name = :c"), {"c": RECEIPT_COLUMN})
        conn.execute(text("UPDATE database_outbox SET ledger_state = NULL WHERE processed_chain = true"))


def _drain(world, rows):
    calls = 0
    while followup.drain_outbox_once(world["engine"], world["setup"], rows=rows) is not None:
        calls += 1
    return calls


def _receipt_transactions(world):
    with world["engine"].connect() as conn:
        return sorted({r[0] for r in conn.execute(text(
            "SELECT transaction_id FROM audit_logs WHERE column_name = :c"), {"c": RECEIPT_COLUMN})}, key=str)


def test_a_batch_writes_what_one_event_at_a_time_writes(world):
    _changes(world)
    one_by_one = _drain(world, None)
    first = _written(world)
    assert first[0] and one_by_one >= 4, (one_by_one, first)                        # canary: there was work

    _forget_and_requeue(world)
    batched = _drain(world, 1000)

    assert _written(world) == first
    assert batched < one_by_one, (batched, one_by_one)


def test_a_translation_that_folded_transactions_leaves_a_receipt_in_each(world):
    """Three chain transactions, each adding a row of the table the ledger reads, followed in one batch: one
    translation, and a receipt in each transaction carrying that translation's counts."""
    for i in (1, 2, 3):
        hw.push(world, [_row(i, 10 * i)])
    hw.run_chain(world)
    with world["engine"].connect() as conn:
        transactions = sorted({r[0] for r in conn.execute(text(
            "SELECT payload->>'transaction_id' FROM database_outbox WHERE table_name = :t"), {"t": hw.OFFICIAL})})
    assert len(transactions) == 3, transactions                                      # canary: three to fold

    done = followup.drain_outbox_once(world["engine"], world["setup"], rows=1000)
    assert done["events"] >= 3 and done["sources"][hw.SOURCE]["inserted"] == 3, done
    with world["engine"].connect() as conn:
        receipts = conn.execute(text("SELECT transaction_id, new_value->>'atoms_written' FROM audit_logs "
                                     "WHERE column_name = :c AND transaction_id = ANY(:t)"),
                                {"c": RECEIPT_COLUMN, "t": transactions}).fetchall()
    assert sorted(tx for tx, _n in receipts) == transactions, receipts
    assert {n for _tx, n in receipts} == {"3"}, receipts


def test_every_event_of_a_batch_is_marked_with_its_runs_outcome(world):
    _changes(world)
    done = followup.drain_outbox_once(world["engine"], world["setup"], rows=1000)
    with world["engine"].connect() as conn:
        left = conn.execute(text("SELECT count(*) FROM database_outbox WHERE processed_chain = true "
                                 "AND ledger_state IS NULL")).scalar()
        states = {r[0] for r in conn.execute(text("SELECT ledger_state FROM database_outbox WHERE id <= :i "
                                                  "AND event_type IN ('CREATE', 'EDIT', 'DELETE')"),
                                             {"i": done["outbox_id"]})}
    assert done["events"] >= 4 and left == 0, (done, left)
    assert states <= {followup.LEDGER_DONE} | {s for s in states if s and s.startswith(followup.LEDGER_SKIPPED)}


def test_a_batch_reads_the_payload_of_only_the_events_its_rows_take(world):
    """총괄 fa5417c28 5: ids and row counts first - the payloads read are those of the events the row budget takes."""
    hw.push(world, [_row(1, 10), _row(2, 20)])
    hw.push(world, [_row(3, 30)])
    hw.run_chain(world)
    with world["engine"].connect() as conn:
        pending = conn.execute(text("SELECT count(*) FROM database_outbox WHERE %s" % followup._PENDING)).scalar()
    read = []

    def seen(conn, cursor, statement, parameters, context, executemany):
        if "payload" in statement and "WHERE id IN" in statement:
            read.append([value for key, value in parameters.items() if key.startswith("ids")])

    sa_event.listen(world["engine"], "before_cursor_execute", seen)
    try:
        done = followup.drain_outbox_once(world["engine"], world["setup"], rows=2)
    finally:
        sa_event.remove(world["engine"], "before_cursor_execute", seen)
    assert pending > done["events"], "CANARY: the budget cut the batch (%d waiting)" % pending
    assert [len(ids) for ids in read] == [done["events"]], read


def test_a_molecule_whose_row_list_overflows_the_row_index_key_is_its_sources_refusal(world, monkeypatch, caplog):
    """총괄 f7394bfdf ㄷ: the database's own error for a row-index key over the btree limit (what a group_by molecule's
    whole row list makes) - that source refused by name, the event followed, not failed."""
    import json
    import logging
    import secrets
    from ledger import roleframe

    # the ref a molecule of thousands of rows makes - {"event", "rows": [every row's ref]}, too long for the index's key;
    # the real translation and the real write say so
    rows = [secrets.token_urlsafe(48) for _ in range(120)]
    monkeypatch.setattr(roleframe, "_claim_source_raw_ref", lambda event_ref, row_refs: json.dumps(
        {"event": event_ref, "rows": sorted(set(row_refs)) + rows}, sort_keys=True, separators=(",", ":")))
    hw.push(world, [_row(1, 10)])
    hw.run_chain(world)
    caplog.set_level(logging.WARNING, logger=followup.logger.name)
    done = followup.drain_outbox_once(world["engine"], world["setup"], rows=1000)
    assert done["sources"][hw.SOURCE].get("refused"), done        # the database's own sentence, in its language
    with world["engine"].connect() as conn:
        states = {r[0] for r in conn.execute(text("SELECT ledger_state FROM database_outbox WHERE id <= :i AND "
                                                  "ledger_state IS NOT NULL"), {"i": done["outbox_id"]})}
    assert not any(s.startswith(followup.LEDGER_FAILED) for s in states), states
    said = [r.getMessage() for r in caplog.records if "row-index key too long" in r.getMessage()]
    assert len(said) == 1 and said[0].startswith("[LedgerFollowUp] %s refused" % hw.SOURCE), said


def test_the_pause_holds_the_follow_up_and_resuming_lets_it_go(world, monkeypatch, tmp_path):
    import ledger.setup

    monkeypatch.setattr(ledger.setup, "load_setup", lambda *a, **k: world["setup"])
    monkeypatch.setattr(chain_control, "control_path", lambda: str(tmp_path / "chain_control.json"))
    monkeypatch.setattr(ledger_worker, "FOLLOWUP_IDLE_SECONDS", 0.05)
    hw.push(world, [_row(1, 10)])
    hw.run_chain(world)
    factory = sessionmaker(bind=world["engine"])
    waiting = followup.outbox_depth(world["engine"])
    assert waiting > 0

    async def run_for(seconds):
        task = asyncio.ensure_future(ledger_worker.run_ledger_followup(factory))
        await asyncio.sleep(seconds)
        task.cancel()

    chain_control.pause("test", "held")
    asyncio.run(run_for(1.0))
    assert followup.outbox_depth(world["engine"]) == waiting, "a batch was taken while the chain is paused"
    chain_control.resume()
    asyncio.run(run_for(3.0))
    assert followup.outbox_depth(world["engine"]) == 0
