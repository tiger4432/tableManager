"""The tables a chain group touches, held while it runs - one group at a time per table across
the chain's slot processes (총괄 19f6a9277 데이터 가드 ㉮ ㄱ).

🔴 WHY. Two groups writing one table at once commit in whatever order they finish, and the
write path is last-write-wins (crud's version gate covers only a table that declares a
version column). A replay reads its rows when it runs; a person saving the row meanwhile and
the chain running that save would write d(v2), then the replay's d(v1) lands on top. One
process taking groups in id order never let the two overlap.

⚠️ THE SET IS THE ONE THE ORDER GUARD ASKS: `_group_target_tables | _group_read_tables`, from
the caller. No second overlap judgement here.
⚠️ SESSION LOCKS ON A CONNECTION OF THEIR OWN. A group's writes commit table by table, so a
transaction lock would go at the first commit. The group takes a connection from the pool for the
block, holds them on it in sorted order (no deadlock between slots), lets them go when the group
ends and gives the connection back; one whose unlock failed is closed instead, so a pooled
connection never holds a table. Kept per thread, three of them held a slot's 2 + 2 pool for good
and a group on a fourth thread waited 30 s every time (07c5a261d).
⚰️ «A BLOCKING WAIT, NOT A RETRY LOOP» stood here - PostgreSQL queues the waiters, so a group waiting behind a
replay group ran before that replay's next group asked again. Reversed (총괄 1ff4dcc6c ④, C 간섭 ④): a wait with no
bound tied the slot to whatever held the table - a group waiting on an LLM held its line, its table and the next
slot's. 🔴 THE WAIT IS BOUNDED BY THE CHAIN STATEMENT LIMIT (`chain_statement_timeout_seconds`, the same file and
read as the group's statements - the wait is one of them); past it `NotHeld` is raised and the caller rewinds the
group to run again, its events as they were. A group so rewound loses its place among the waiters: what it writes is
read again when it runs, so the order changes when, not what.
"""
from contextlib import contextmanager

from sqlalchemy import text

import event_constants

#: The first key of the two-key advisory lock - the chain table locks' own space.
LOCK_SPACE = 70_190_408
#: The stage a group is in while it waits for a table - what the queue's state seat reads.
WAITING_FOR = event_constants.CHAIN_WAITING_FOR
#: ... and once it holds them all (총괄 59f2ab3f4: «waiting for» stayed on the beat after the lock was got).
HOLDING = "holding "
#: How a group's failure that is a table not held begins - the batch rewinds it (`process_pending_groups`).
NOT_HELD = "table not held"


class NotHeld(Exception):
    """A table another group holds was not got within the chain statement limit."""

    def __init__(self, table, seconds):
        super().__init__("%s: %s within %g s (another group holds it)" % (NOT_HELD, table, seconds))

@contextmanager
def hold(db, tables, on_wait=None, on_held=None):
    """Hold `tables` for the block. `on_wait(table, pid)` is called before each wait - `pid` the
    lock connection's backend, which a pause cancels - and `on_held(tables)` once all are held.
    No-op on a database without advisory locks (SQLite)."""
    tables = sorted(t for t in tables or () if t)
    if not tables or db.get_bind().dialect.name != "postgresql":
        yield
        return
    from sqlalchemy.exc import OperationalError
    from parsers.directory_watcher import chain_statement_timeout

    seconds = chain_statement_timeout()
    conn = db.get_bind().connect().execution_options(isolation_level="AUTOCOMMIT")
    held = []
    try:
        # the session's own setting on a pooled connection - reset below before it goes back
        conn.execute(text("SELECT set_config('lock_timeout', :ms, false)"),
                     {"ms": "%dms" % round(seconds * 1000) if seconds else "0"})
        for table in tables:
            if on_wait is not None:
                on_wait(table, conn.connection.dbapi_connection.get_backend_pid())
            try:
                conn.execute(text("SELECT pg_advisory_lock(:space, hashtext(:table))"),
                             {"space": LOCK_SPACE, "table": table})
            except OperationalError as error:
                if type(error.orig).__name__ != "LockNotAvailable":
                    raise
                raise NotHeld(table, seconds) from None
            held.append(table)
        if on_held is not None:
            on_held(held)
        yield
    finally:
        try:
            for table in reversed(held):
                conn.execute(text("SELECT pg_advisory_unlock(:space, hashtext(:table))"),
                             {"space": LOCK_SPACE, "table": table})
            conn.execute(text("RESET lock_timeout"))
        except BaseException:
            conn.invalidate()
            raise
        finally:
            conn.close()
