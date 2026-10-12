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
⚠️ A BLOCKING WAIT, NOT A RETRY LOOP. PostgreSQL queues the waiters, so a group waiting behind
a replay group runs before that replay's next group asks again.
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

@contextmanager
def hold(db, tables, on_wait=None, on_held=None):
    """Hold `tables` for the block. `on_wait(table, pid)` is called before each wait - `pid` the
    lock connection's backend, which a pause cancels - and `on_held(tables)` once all are held.
    No-op on a database without advisory locks (SQLite)."""
    tables = sorted(t for t in tables or () if t)
    if not tables or db.get_bind().dialect.name != "postgresql":
        yield
        return
    conn = db.get_bind().connect().execution_options(isolation_level="AUTOCOMMIT")
    held = []
    try:
        for table in tables:
            if on_wait is not None:
                on_wait(table, conn.connection.dbapi_connection.get_backend_pid())
            conn.execute(text("SELECT pg_advisory_lock(:space, hashtext(:table))"),
                         {"space": LOCK_SPACE, "table": table})
            held.append(table)
        if on_held is not None:
            on_held(held)
        yield
    finally:
        try:
            for table in reversed(held):
                conn.execute(text("SELECT pg_advisory_unlock(:space, hashtext(:table))"),
                             {"space": LOCK_SPACE, "table": table})
        except BaseException:
            conn.invalidate()
            raise
        finally:
            conn.close()
