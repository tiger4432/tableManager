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

#: PostgreSQL's wire protocol carries the parameter count in an int16, so a single
#: statement can never bind more than this many values - psycopg2 raises before it
#: is sent. SQLite's own limit is an order of magnitude higher (250,000 on the
#: build this suite runs), which is exactly why an unchunked statement can look
#: fine here and be fatal in production.
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
