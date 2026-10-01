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
identity IS a physical column that is the same column (⚰️ a source whose identity a
PREPARER derived retired with setup_version 6), and a page cut on a group-constant key
never splits a molecule -- `_page_key`'s own docstring rules that, and it is why
"14 plus a special one" is not the shape of this.
"""
from __future__ import annotations

import contextlib
import contextvars
import uuid6
import logging
import threading
import time
from collections import deque

logger = logging.getLogger(__name__)

#: EDIT and DELETE, each with its OWN instrument -- see `drain_once`.
#:
#: 🔴 CREATE JOINED ON 2026-09-08 (S-65), AND THAT REPLACES RULING 129 ㉣. That ruling said
#: the forward run reads a new row once from the cursor, so following it too would translate
#: the same row twice for nothing. The premise was measured false: a new row only reaches the
#: cursor if it sorts AFTER it, and the shipped sources mostly page on a NAME. A lot whose id
#: sorts earlier is never read, with no error and a cursor that reports it is finished --
#: measured here on 3,008 `lot_event` rows dated before the cursor's own instant, and on
#: 470,000 `wafer_process` rows whose uuid7 row_ids all sort before a hand-written literal
#: the cursor sat on. Both produced ZERO atoms.
#:
#: Ruling 144 splits the two paths instead: the outbox is the LIVE path and the cursor is the
#: CATCH-UP path. `drain_once` therefore follows a CREATE only for a source that has been SEEN
#: with nothing past its cursor, and skips the rest by name -- so a source still catching up
#: keeps reading its own new rows exactly as before, and nothing is translated twice.
#:
#: 🔴 DELETE JOINED ON 2026-09-08 (S-54-b) AND IT IS STILL NOT THE SAME STEP. A deleted
#: row cannot be selected, so there is nothing to scope and nothing to remake -- which is why
#: DELETE waited until the ledger wrote down, while the row was still there, which physical
#: row each fact came from. Since S-101 `rescope` aims its withdrawal with that same note
#: rather than with the new translation, so an EDIT that stops a row being this source's row
#: withdraws by the same road; the step stays separate because only DELETE has no remake.
FOLLOWED_EVENT_TYPES = ("CREATE", "EDIT", "DELETE")


# ⚰️ [총괄 f3bc02f6e, 소유자 「운영에서는 뷰 안 써 · 걷어내기」] THE VIEW FOLLOW STOOD HERE -
#    `base_tables_of` (a `pg_depend` walk), `ViewDependencyTooDeep`, `view_followers_of` and the
#    `cannot_follow` note. A ledger source now reads a table that has `row_id` (refused by name
#    at load otherwise), so a base table's event reaches its sources through
#    `sources_for_table` alone and there is no view to follow.


#: The job name the pace is declared under, in `server/pacing.json`.
FOLLOWUP_JOB = "chain_followup"

#: The audit column, source layer and writer a ledger receipt carries. Imported from the
#: one place that already names them so the failure receipt below and the success receipt
#: in `runtime_v2` cannot describe themselves differently.
from .runtime_v2 import RECEIPT_COLUMN, RECEIPT_SOURCE                # noqa: E402
RECEIPT_WRITER = "ledger"

#: A bound so a stalled drain cannot eat the worker's memory. Overflow is COUNTED and named
#: in the heartbeat note rather than dropped in silence: a queue that quietly forgets is the
#: 2026-09-04 shape, where 570 rows waited with no error anywhere.
MAX_QUEUED_EVENTS = 10000

_lock = threading.Lock()
_queue: deque = deque()
_dropped = 0
_failed = 0

#: The chain transaction id of the event the batch running on THIS thread is following.
#:
#: 🔴 A CONTEXTVAR AND NOT FOUR SIGNATURES (S-117, 판정 248). The value has to reach the
#: statement that writes the atoms, and that statement is four calls down
#: (`rescope` -> `execute_selected_scoped_batch` -> `execute_scoped_batch` ->
#: `write_batch`); widening all four so one leaf can read one string is the change the
#: standing rule about touching only the layer that changes exists to prevent. Scoped the
#: way the chain worker's own group scope is (판정 235): opened by the one loop that knows
#: where a batch begins, invisible to anything that did not open one.
#:
#: ⚠️ DELIBERATELY NOT `request_transaction_id`. That one stamps every ORM write in its
#: scope, so a batch that wrote anything through the session would silently take this id as
#: well. This var is read by one seat and stamps nothing on its own.
_FOLLOWING: contextvars.ContextVar = contextvars.ContextVar(
    "assy_manager.ledger_followup.following", default=None)


@contextlib.contextmanager
def following(transaction_id):
    """Mark this thread as following `transaction_id` for the duration of one batch."""
    token = _FOLLOWING.set(str(transaction_id) if transaction_id else None)
    try:
        yield
    finally:
        _FOLLOWING.reset(token)


def event_transaction_id():
    """The chain transaction this batch is following, or `None`.

    🔴 `None` IS A VALUE HERE, NOT A GAP. A backfill or a retroactive run fills this queue
    with no chain transaction behind it, and that emptiness is what tells an operator on the
    timeline that a row came from a backfill rather than from somebody's edit. Inventing an
    id would erase exactly the distinction S-117 exists to show.
    """
    return _FOLLOWING.get()


# ------------------------------------------------------------------- the chain's one line

def enqueue(table_name, row_ids, event_type, transaction_id=None, chain_depth=None):
    """Remember that rows of `table_name` changed. Returns whether anything was queued.

    Called from the chain worker's group step BEFORE its trigger filter, because the
    subject of this step is the OUTBOX event, not a chain rule: a person editing a cell
    in the grid produces the same event and must be followed the same way
    (ruling 129 ㉤).

    `transaction_id` is the chain transaction of that event, so the receipt this batch
    writes lands in the SAME audit group as the table change that caused it (S-117,
    판정 248). Absent for a backfill or retroactive filler, and LEFT absent - see
    `event_transaction_id`.

    🔴 [S-249 ⓒ] `chain_depth` RIDES ALONG BECAUSE THE FOLLOW-UP LAP IS A HOP. Measured
    before building: `request_chain_depth` is set in exactly ONE place - the chain group step
    - and the follow-up drain runs in its own thread outside that scope, so everything this
    lap writes carried NO hop at all and could never meet `max_chain_depth`. A loop that goes
    through the follow-up lap was therefore unbounded while a loop that stayed in the group
    step was bounded, which is one ceiling with two answers.
    ⚠️ ABSENT STAYS ABSENT. A change that is not the chain's has no hop, and inventing a
    zero for it would make every ordinary edit look like the first step of a cascade.
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
        _queue.append((str(table_name), ids, str(event_type), time.time(),
                       str(transaction_id) if transaction_id else None,
                       chain_depth))
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
    # 🔴 A RETIRED SOURCE IS NOT READ (S-103, ruling 198). This is the live path: every row
    # that arrives asks which sources translate it, so a source left out here stops making
    # atoms from now on and keeps every atom it already made - which is what retiring one
    # means. A ledger appends; it does not forget.
    return tuple(sorted(name for name, plan in plans.items()
                        if plan.relation == table_name and plan.runs))


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
    return _scope_values_from(connection, plan.relation, column, row_ids)


def _scope_values_from(connection, relation_name, column, row_ids):
    """The same read, aimed at a named relation.

    ⚠️ ONE IMPLEMENTATION, TWO AIMS. A view source's scope is read from the BASE TABLE the
    event named (S-65-c), not from the view -- the event carries base-table row ids. Copying
    this query to do that would be the second spelling this file's own docstrings keep
    warning about, so the aim is a parameter instead.
    """
    from psycopg2 import sql

    relation = sql.SQL(".").join(
        sql.Identifier(part) for part in str(relation_name).split("."))
    query = sql.SQL("SELECT DISTINCT {} FROM {} WHERE row_id = ANY(%s)").format(
        sql.Identifier(column), relation)
    with connection.cursor() as cursor:
        cursor.execute(query, (list(row_ids),))
        return [row[0] for row in cursor.fetchall() if row[0] is not None]


def _write_failure_receipt(engine, relation, source, transaction_id, exc):
    """One audit row saying this batch failed, in a commit of its own. Never raises.

    ⚠️ A RECEIPT THAT CAN TAKE THE DRAIN DOWN WITH IT IS WORSE THAN NO RECEIPT. This runs
    inside the handler for a failure that has already been named and counted; letting a
    second failure escape from here would turn "one source could not be followed" into
    "the follow-up loop stopped", which is the poisoned-row shape this file's docstring
    already refuses.
    """
    try:
        from database import crud

        from . import store as store_module

        row = crud.create_audit_log(
            None, relation, str(uuid6.uuid7()), RECEIPT_COLUMN, None,
            {"source": source, "status": "failed",
             "error": f"{type(exc).__name__}: {exc}"},
            RECEIPT_SOURCE, RECEIPT_WRITER,
            transaction_id=transaction_id, add_to_cache=False)
        connection = engine.raw_connection()
        try:
            store_module._insert_audit_row(connection, row)
            connection.commit()
        finally:
            connection.close()
    except Exception as receipt_error:                                 # noqa: BLE001
        logger.warning("[LedgerFollowUp] the failure receipt for %s <- %s could not be "
                       "written: %s", source, relation, receipt_error)


def _take():
    with _lock:
        return _queue.popleft() if _queue else None


def drain_once(engine, setup, world=None, sources=None):
    """Follow ONE queued event: all of its rows, one `rescope` per source. Or `None`.

    `sources`, when given, is the only ones to translate - a branch speaks only for what its
    declaration changed, not for every source that reads the table (총괄 c23b02aeb ③).

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
    table, row_ids, event_type, queued_at, transaction_id, chain_depth = item
    from . import backfill

    # 🔴 `row_ids` IS RETURNED AS A VALUE so a caller can act on the rows this batch
    # followed WITHOUT this module learning what that action is (S-151, 판정 264). The
    # enrichment auto-confirm rides this drain, and it is called from the worker loop:
    # importing it here would tie the ledger basis to the enrichment one in code, and the
    # ledger only ever READS these tables.
    # 🔴 [S-249 ⓒ] THE CAUSE TRAVELS WITH THE BATCH. A follow-up kind cannot ask 「have I
    # already answered for this change」 unless it can name the change, and the transaction
    # that caused it is that name. It was taken off the queue and dropped here.
    done = {"table": table, "event_type": event_type, "rows": len(row_ids),
            "row_ids": list(row_ids), "transaction_id": transaction_id,
            "chain_depth": chain_depth,
            "waited": time.time() - queued_at, "sources": {}}
    # 🔴 ASKED BEFORE THE DELETE BRANCH, because a deletion has view followers too (S-65-d).
    if event_type == "DELETE":
        # 🔴 A DIFFERENT INSTRUMENT, NOT A DIFFERENT SCOPE. The rows are gone, so there is
        # nothing to re-translate and nothing to build a ref from; `withdraw_deleted_rows`
        # reads the refs the ledger wrote down while they were still here. It asks by
        # RELATION, so it needs no source list -- one deleted row withdraws the atoms of
        # every source that read that table.
        try:
            withdrawn = backfill.withdraw_deleted_rows(engine, setup, table, list(row_ids),
                                                       apply=True)
            done["sources"] = withdrawn["sources"]
            done["forgotten"] = withdrawn["forgotten"]
        except Exception as exc:
            with _lock:
                _failed += 1
            done["error"] = f"{type(exc).__name__}: {exc}"
            logger.warning("[LedgerFollowUp] delete on %s (%d rows) failed: %s",
                           table, len(row_ids), exc)
        return done
    table_sources = [source for source in sources_for_table(setup, table)
                     if sources is None or source in sources]
    # ⚰️ THE "CAUGHT UP" GATE WENT WITH THE CURSOR (판정 171). It existed because a source
    # still walking its cursor would read a new row itself, so following it here too would
    # translate the same molecule twice. There is no cursor walk any more -- the initial load
    # stages CREATE events like everything else, and a row already translated is in the row
    # index and so is never staged again -- which leaves the gate one possible answer.
    #
    # 🔴 IT COULD NOT BE LEFT IN PLACE. Nothing wrote `caught_up_at` once `run()` stopped
    # walking, so a source that had not already been marked would have had its new rows
    # skipped forever: a gate whose input is never produced fails closed, and silently.
    # The column itself is retired now (판정 173) -- `ledger/schema.py` says where it went.
    targets = [(source, scope_column(setup.snapshot.source_plans[source]))
               for source in table_sources]
    if not targets:
        return done
    for source, column in targets:
        try:
            connection = engine.raw_connection()
            try:
                values = _scope_values_from(connection, table, column, row_ids)
            finally:
                connection.rollback()
                connection.close()
            if not values:
                # The rows are gone, or none of them carries a page key. Neither is this
                # step's to fix: a vanished row needs the instrument DELETE is waiting for,
                # and a null page key would have been refused by the read long before now.
                done["sources"][source] = {"scope_values": 0}
                continue
            # 🔴 A CREATE IS TRANSLATED ONCE (판정 166). There is nothing to withdraw for a
            # row that has just appeared, and the preview exists only to aim a withdrawal.
            # The scope the receipt inside that write is stamped with. Opened here
            # because this is the one loop that knows which event a batch is following.
            with following(transaction_id):
                result = backfill.rescope(engine, setup, source, column, values,
                                          apply=True,
                                          withdraw=(event_type != "CREATE"),
                                          world=world)
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
            # 🔴 A FAILURE IS THE ONE AN OPERATOR MOST NEEDS TO SEE, AND IT NEEDS ITS OWN
            # COMMIT (S-117, 판정 248). The successful receipt rides the atoms' commit so
            # it cannot be lost while they stand; a FAILED batch has no such commit - it
            # was rolled back, taking any receipt inside it with it - so this one is
            # written afterwards, on its own. That is the shape rejected for the success
            # path, used here because here there is nothing left to ride.
            _write_failure_receipt(engine, table, source, transaction_id, exc)
            logger.warning(
                "[LedgerFollowUp] %s <- %s (%d rows) failed: %s",
                source, table, len(row_ids), exc)
    return done
