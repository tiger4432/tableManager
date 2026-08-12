"""Statement-count instrumentation for the write path.

Why counts and not timings: a timing assertion on the upsert path measures this
box (and CI's mood), so it is either flaky or so loose it asserts nothing. The
property these tests actually defend is "how many round trips does one save cost,
and how big is each one", and those numbers are identical on SQLite and
PostgreSQL. Count them.

One record per `execute()`/`executemany()` call, which is one client->server round
trip - an `executemany` over 500 rows is one record here, and that is the correct
unit. `bind_count` is only meaningful for a single `execute`; for `executemany`
the driver sends one row's parameters at a time, so it is reported as 0.
"""

from collections import namedtuple
from contextlib import contextmanager

from sqlalchemy import event


Call = namedtuple("Call", "sql bind_count executemany")

#: ⚠️ [2026-08-12] THIS CONSTANT USED TO BE DOCUMENTED AS A DRIVER-ENFORCED
#: CEILING - "psycopg2 raises before it is sent" - AND THAT IS FALSE. psycopg2
#: interpolates parameters CLIENT-SIDE (`cursor.mogrify` returns a finished SQL
#: string), so no bound parameters cross the wire and the extended-query
#: protocol's int16 parameter count is never consulted. Measured on the isolated
#: `assy_qa`: one multi-row upsert of 12,000 rows x 7 columns = 84,000 binds was
#: accepted and stored all 12,000 rows. Nothing refuses at 32,767 on this driver.
#:
#: The number is REAL for the protocol and it becomes a hard ceiling under a
#: server-side-binding driver (psycopg v3, asyncpg). It is kept here as a
#: BUDGET, not as a prediction of refusal: a statement that binds fewer than
#: this many values is also one whose text and `mogrify` memory stay bounded,
#: whose locks are held briefly, and which would survive a driver switch. See
#: `crud.BULK_CHUNK_SIZE` for what the chunk bound actually buys.
PG_MAX_BIND_PARAMS = 32767


@contextmanager
def record_statements(session):
    """Record every SQL statement the session's engine runs inside the block."""
    engine = session.get_bind()
    recorded = []

    def _before(conn, cursor, statement, parameters, context, executemany):
        try:
            n = 0 if executemany else len(parameters or ())
        except TypeError:
            n = 0
        recorded.append(Call(statement, n, bool(executemany)))

    event.listen(engine, "before_cursor_execute", _before)
    try:
        yield recorded
    finally:
        event.remove(engine, "before_cursor_execute", _before)


def _matching(recorded, verb, table_name):
    needle = table_name.lower()
    return [c for c in recorded
            if c.sql.lstrip().lower().startswith(verb) and needle in c.sql.lower()]


def selects_from(recorded, table_name):
    """The recorded SELECTs that read `table_name`.

    Deliberately excludes INSERT/UPDATE/DELETE against the same table: the thing
    being budgeted is reads issued to answer a question, not the writes that are
    the point of the request.
    """
    return _matching(recorded, "select", table_name)


def inserts_into(recorded, table_name):
    return _matching(recorded, "insert", table_name)


def deletes_from(recorded, table_name):
    return _matching(recorded, "delete", table_name)
