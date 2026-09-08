# -*- coding: utf-8 -*-
"""The ledger follows the tables it reads, one paced batch behind the chain.

운영에서는 아무것도 적지 않습니다 -- 소스가 읽는 표를 체인이나 사람이 고치면 원장이 따라옵니다.

🔴 NOT ON THE COMMIT PATH. The chain worker drops `(table, row_ids, event_type)` in here and
goes straight on; a separate paced task drains it. That is the whole reason this module
exists as a queue rather than as a call inside `process_chain_transaction_group`: a chain
transaction must cost exactly what it costs today, and re-translating a molecule is a read,
a withdrawal and a write against the ledger.

🔴 THE QUEUE IS MEMORY, AND LOSING IT IS NOT LOSING THE FACT. If the worker dies with
entries in it, those rows are picked up by the ledger's own forward run and by `rescope` on
a retroactive pass -- that pass is the CANONICAL filler and this is the prompt one. What a
crash costs is promptness, not correctness, and that is why no durable queue is built here
and why `enqueue` cannot raise into the chain's path.

🔴 THE SCOPE COLUMN IS THE SOURCE'S PAGE KEY, FOR ALL OF THEM, WITH NO BRANCH.
`backfill._page_key` already answers it: the cursor's first column. For a source whose
identity IS a physical column that is the same column; for a source whose identity the
PREPARER derives, the page key is a coarsening of the group (the derived key embeds it),
and a coarsening never splits a molecule -- `_page_key`'s own docstring rules that, and it
is why "14 plus a special one" is not the shape of this.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque

logger = logging.getLogger(__name__)

#: EDIT only.
#:
#: CREATE is the cursor's own path -- the forward run reads the row once, and following it
#: here would translate the same row twice for nothing (ruling 129 ㉣).
#:
#: DELETE is a different instrument and is not this one. `rescope` aims its withdrawal with
#: the CURRENT translation of the rows in scope, so a row that is gone has no translation to
#: aim with and its old atoms would stay (`backfill.rescope`'s own docstring says so). That
#: is a structural "cannot", not a width to widen, and it is why DELETE waits for its own
#: instrument rather than riding this queue quietly and doing nothing.
FOLLOWED_EVENT_TYPES = ("EDIT",)

#: The job name the pace is declared under, in `server/pacing.json`.
FOLLOWUP_JOB = "chain_followup"

#: A bound so a stalled drain cannot eat the worker's memory. Overflow is COUNTED and named
#: in the heartbeat note rather than dropped in silence: a queue that quietly forgets is the
#: 2026-09-04 shape, where 570 rows waited with no error anywhere.
MAX_QUEUED_EVENTS = 10000

_lock = threading.Lock()
_queue: deque = deque()
_dropped = 0
_failed = 0


# ------------------------------------------------------------------- the chain's one line

def enqueue(table_name, row_ids, event_type):
    """Remember that rows of `table_name` changed. Returns whether anything was queued.

    Called from the chain worker's group step BEFORE its trigger filter, because the
    subject of this step is the OUTBOX event, not a chain rule: a person editing a cell in
    the grid produces the same event and must be followed the same way (ruling 129 ㉤).
    """
    global _dropped
    if event_type not in FOLLOWED_EVENT_TYPES:
        return False
    ids = tuple(str(item) for item in (row_ids or ()) if item)
    if not table_name or not ids:
        return False
    with _lock:
        if len(_queue) >= MAX_QUEUED_EVENTS:
            _dropped += 1
            return False
        _queue.append((str(table_name), ids, str(event_type), time.time()))
    return True


def row_ids_of(payload):
    """The row ids an outbox payload names, in BOTH envelope shapes.

    Measured rather than assumed (2026-09-08): a per-row event carries `row_id` at the
    ENVELOPE level (`database.stage_event`) -- `_EXCLUDED` only filters the column dict
    below it -- and a collapsed event carries `row_ids` (`database.stage_collapsed_event`),
    which is also the discriminator `event_constants.is_collapsed_payload` uses.
    """
    if not isinstance(payload, dict):
        return ()
    many = payload.get("row_ids")
    if isinstance(many, (list, tuple)):
        return tuple(item for item in many if item)
    one = payload.get("row_id")
    return (one,) if one else ()


def queue_depth():
    with _lock:
        return len(_queue)


def note():
    """What the worker's heartbeat says about this queue, or `None` while it is idle.

    ⛔ 「쌓이는데 조용」. A queue that drains as fast as it fills is ordinary and says
    nothing; a queue holding anything, or that has dropped or failed anything, says so --
    and `/health` already carries this worker's note across the process boundary, so no
    second channel is opened for it.
    """
    with _lock:
        waiting = len(_queue)
        oldest = time.time() - _queue[0][3] if _queue else None
        dropped, failed = _dropped, _failed
    if not waiting and not dropped and not failed:
        return None
    parts = [f"waiting={waiting}"]
    if oldest is not None:
        parts.append(f"oldest={oldest:.1f}s")
    if dropped:
        parts.append(f"dropped={dropped}")
    if failed:
        parts.append(f"failed={failed}")
    return "ledger follow-up: " + " ".join(parts)


def reset():
    """Drop everything. For tests and for a worker reload; never called on the chain path."""
    global _dropped, _failed
    with _lock:
        _queue.clear()
        _dropped = 0
        _failed = 0


# ------------------------------------------------------------------------- the paced side

def sources_for_table(setup, table_name):
    """Every ledger source that reads this table, by name.

    Resolved HERE and not at enqueue time on purpose: `enqueue` runs on the chain's own
    path and must not load a setup or wait on anybody's lock. An event about a table no
    source reads therefore costs one append and one pop, and no query at all (ruling
    129 ㉧).
    """
    plans = setup.snapshot.source_plans
    return tuple(sorted(name for name in plans if plans[name].relation == table_name))


def scope_column(plan):
    """The column a scope aims with: the source's page key. See the module docstring."""
    from .backfill import _page_key

    return _page_key(plan)


def _scope_values(connection, plan, column, row_ids):
    """`SELECT DISTINCT <page key> FROM <relation> WHERE row_id = ANY(...)`.

    `row_id` is the frame column of every dynamic table, so it is nameable without the
    declaration saying anything about it; the page key comes from the compiled plan and is
    always one of `base_select_columns` (`cursor_columns` is a term of that set), which is
    the same allow-list `backfill._scope_predicate` checks a hand-typed scope against.
    """
    from psycopg2 import sql

    relation = sql.SQL(".").join(
        sql.Identifier(part) for part in plan.relation.split("."))
    query = sql.SQL("SELECT DISTINCT {} FROM {} WHERE row_id = ANY(%s)").format(
        sql.Identifier(column), relation)
    with connection.cursor() as cursor:
        cursor.execute(query, (list(row_ids),))
        return [row[0] for row in cursor.fetchall() if row[0] is not None]


def _take():
    with _lock:
        return _queue.popleft() if _queue else None


def drain_once(engine, setup):
    """Follow ONE queued event: all of its rows, one `rescope` per source. Or `None`.

    🔴 ONE BATCH IS ONE EVENT, NOT ONE ROW (ruling 129 ㉥). A collapsed event names up to
    1,000 rows; they go into a single scope, so a chain batch that touched a thousand rows
    costs one re-translation and not a thousand.

    🔴 A FAILURE IS NAMED AND THE EVENT IS DONE. It is not requeued: a row that cannot be
    followed would otherwise sit at the head forever and hold everything behind it, which is
    the poisoned-row shape this repo has already been bitten by. Retrying is the retroactive
    run's job, and that run is this queue's canonical filler anyway.
    """
    global _failed
    item = _take()
    if item is None:
        return None
    table, row_ids, event_type, queued_at = item
    from . import backfill

    done = {"table": table, "event_type": event_type, "rows": len(row_ids),
            "waited": time.time() - queued_at, "sources": {}}
    for source in sources_for_table(setup, table):
        plan = setup.snapshot.source_plans[source]
        column = scope_column(plan)
        try:
            connection = engine.raw_connection()
            try:
                values = _scope_values(connection, plan, column, row_ids)
            finally:
                connection.rollback()
                connection.close()
            if not values:
                # The rows are gone, or none of them carries a page key. Neither is this
                # step's to fix: a vanished row needs the instrument DELETE is waiting for,
                # and a null page key would have been refused by the read long before now.
                done["sources"][source] = {"scope_values": 0}
                continue
            result = backfill.rescope(engine, setup, source, column, values, apply=True)
            done["sources"][source] = {
                "scope_values": len(values),
                "withdrawn": result.get("withdrawn", 0),
                "inserted": result.get("inserted", 0),
                "deduped": result.get("deduped", 0),
            }
        except Exception as exc:  # named, counted, and NOT requeued -- see the docstring
            with _lock:
                _failed += 1
            done["sources"][source] = {"error": f"{type(exc).__name__}: {exc}"}
            logger.warning(
                "[LedgerFollowUp] %s <- %s (%d rows) failed: %s",
                source, table, len(row_ids), exc)
    return done
