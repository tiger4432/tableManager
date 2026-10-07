"""What a database backend is doing, and who holds it up - one question, one answer.

Asked by the watcher's chunk sampler, by `scripts/diagnose_db_health.py`'s lock section and
by the stalled line of the chain and the watcher (총괄 fc1c0781d ② · 10-07 ③). Each used to spell its own SQL; a second
spelling is a second answer, so they pass through here.

Takes a DBAPI (psycopg2) connection: the sampler holds one outside any pool on purpose
(S-167), and a SQLAlchemy caller hands over `conn.connection.dbapi_connection`.
"""

_SQL = """
SELECT a.pid,
       coalesce(nullif(a.application_name, ''), a.backend_type),
       a.state, a.wait_event_type, a.wait_event,
       EXTRACT(EPOCH FROM (now() - a.xact_start)),
       EXTRACT(EPOCH FROM (now() - a.query_start)),
       EXTRACT(EPOCH FROM (now() - a.state_change)),
       left(regexp_replace(coalesce(a.query, ''), '\\s+', ' ', 'g'), 60),
       b.pid,
       coalesce(nullif(b.application_name, ''), b.backend_type),
       b.state,
       EXTRACT(EPOCH FROM (now() - b.xact_start)),
       EXTRACT(EPOCH FROM (now() - b.state_change)),
       left(regexp_replace(coalesce(b.query, ''), '\\s+', ' ', 'g'), 60)
FROM pg_stat_activity a
LEFT JOIN LATERAL unnest(pg_blocking_pids(a.pid)) AS held(pid) ON true
LEFT JOIN pg_stat_activity b ON b.pid = held.pid
WHERE {where}
ORDER BY a.pid, b.pid
"""

#: Every backend of this database that another one is holding up - the lock section's list.
_BLOCKED = "a.datname = current_database() AND cardinality(pg_blocking_pids(a.pid)) > 0"


def backend_waits(dbapi_conn, pid=None):
    """One row per (backend, backend holding it up) - for `pid`, or for every blocked
    backend of this database when `pid` is None. A backend nobody holds up is one row with
    `blocker` None; a pid that is not connected is no row at all."""
    where = "a.pid = %s" if pid is not None else _BLOCKED
    with dbapi_conn.cursor() as cur:
        cur.execute(_SQL.format(where=where), (int(pid),) if pid is not None else None)
        rows = cur.fetchall()
    out = []
    for r in rows:
        out.append({
            "pid": r[0], "app": r[1], "state": r[2],
            "wait_type": r[3], "wait": "%s:%s" % (r[3], r[4]) if r[3] else None,
            "xact_age": _seconds(r[5]), "query_age": _seconds(r[6]),
            "state_age": _seconds(r[7]), "query": r[8],
            "blocker": None if r[9] is None else {
                "pid": r[9], "app": r[10], "state": r[11],
                "xact_age": _seconds(r[12]), "state_age": _seconds(r[13]),
                "query": r[14]},
        })
    return out


def wait_sentence(row, pid=None):
    """The one sentence for a row of `backend_waits` (None = the pid is not connected)."""
    if row is None:
        return "pid %s is not in pg_stat_activity - its connection is gone" % pid
    held = row["blocker"]
    if held is not None:
        return "waiting %s on pid %s (%s, %s %s): %s" % (
            row["wait"], held["pid"], held["app"], held["state"] or "no state",
            _age(held["xact_age"] if held["xact_age"] is not None else held["state_age"]),
            held["query"])
    state = row["state"] or "no state"
    if state == "active":
        waiting = (row["wait"] if row["wait_type"] == "Lock" else
                   "no lock" + (", " + row["wait"] if row["wait"] else ""))
        return "its own query active %s (%s): %s" % (
            _age(row["query_age"]), waiting, row["query"])
    if state.startswith("idle in transaction"):
        return "%s %s - the time is not in the database (last query: %s)" % (
            state, _age(row["state_age"]), row["query"])
    return "%s %s (last query: %s)" % (state, _age(row["state_age"]), row["query"])


#: How long the stalled line's own question may run. It reads two system views and takes
#: no lock, so this bounds a database that cannot answer at all.
STALL_PROBE_TIMEOUT_MS = 5000


def what_a_backend_waits_on(bind_url, pid):
    """The sentence for one backend, asked over a connection of its own outside the pool
    (S-167), read-only and bounded - the stalled work's own session is the one that is stuck.
    The stalled line of every claimed worker asks this (총괄 10-07 ③: chain and watcher alike)."""
    import db_safety
    from database.database import connection_name
    probe = db_safety.open_readonly_engine(
        bind_url, application_name=connection_name() + "_probe",
        statement_timeout_ms=STALL_PROBE_TIMEOUT_MS)
    try:
        with probe.connect() as conn:
            rows = backend_waits(conn.connection.dbapi_connection, pid)
    finally:
        probe.dispose()
    return wait_sentence(rows[0] if rows else None, pid)


def _seconds(value):
    return None if value is None else float(value)


def _age(seconds):
    if seconds is None:
        return "for an unknown time"
    return "%d s" % seconds if seconds < 600 else "%d min" % (seconds // 60)
