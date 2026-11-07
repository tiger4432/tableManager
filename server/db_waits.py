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
       left(regexp_replace(coalesce(a.query, ''), '\\s+', ' ', 'g'), {chars}),
       b.pid,
       coalesce(nullif(b.application_name, ''), b.backend_type),
       b.state,
       EXTRACT(EPOCH FROM (now() - b.xact_start)),
       EXTRACT(EPOCH FROM (now() - b.state_change)),
       left(regexp_replace(coalesce(b.query, ''), '\\s+', ' ', 'g'), {chars})
FROM pg_stat_activity a
LEFT JOIN LATERAL unnest(pg_blocking_pids(a.pid)) AS held(pid) ON true
LEFT JOIN pg_stat_activity b ON b.pid = held.pid
WHERE {where}
ORDER BY a.pid, b.pid
"""

#: Every backend of this database that another one is holding up - the lock section's list.
_BLOCKED = "a.datname = current_database() AND cardinality(pg_blocking_pids(a.pid)) > 0"


#: A run's own backends that are not idle - a retroactive run's beat (총괄 d9be013cb · bdc08ec39 ⑦); the probe asking is
#: left out.
_BUSY_OF = ("a.datname = current_database() AND a.pid = ANY(%s) "
            "AND a.state IS DISTINCT FROM 'idle' AND a.pid <> pg_backend_pid()")


def backend_waits(dbapi_conn, pid=None, pids=None, chars=60):
    """One row per (backend, backend holding it up) - for `pid`; for every busy backend of `pids` (a run's own); or
    for every blocked backend of this database when both are None. A backend nobody holds up is one row with `blocker`
    None; a pid that is not connected is no row at all. `chars`: how much of each query is read."""
    where = "a.pid = %s" if pid is not None else _BUSY_OF if pids is not None else _BLOCKED
    args = (int(pid),) if pid is not None else ([int(p) for p in pids],) if pids is not None else None
    with dbapi_conn.cursor() as cur:
        cur.execute(_SQL.format(where=where, chars=int(chars)), args)
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
    """The one sentence for a row of `backend_waits` (None = the pid is not connected). The holder is named by the work
    on it (`work_on`), else its application."""
    if row is None:
        return "pid %s is not in pg_stat_activity - its connection is gone" % pid
    held = row["blocker"]
    if held is not None:
        return "waiting %s on pid %s (%s, %s %s): %s" % (
            row["wait"], held["pid"], work_on(held["pid"]) or held["app"], held["state"] or "no state",
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


_INDEX_BUILDS = (
    "SELECT n.nspname, c.relname, p.pid, p.phase, p.current_locker_pid, l.application_name"
    "  FROM pg_stat_progress_create_index p JOIN pg_class c ON c.oid = p.index_relid"
    "  JOIN pg_namespace n ON n.oid = c.relnamespace"
    "  LEFT JOIN pg_stat_activity l ON l.pid = p.current_locker_pid"
    " WHERE p.datid = (SELECT oid FROM pg_database WHERE datname = current_database())")


#: The lock modes a CONCURRENTLY build waits out before it starts building - the ones its own lock
#: (ShareUpdateExclusive) conflicts with. 총괄 11-06: a writing session (RowExclusiveLock) is not waited for - on a table
#: written without pause (audit_logs · cell_sources · an ingested table) the wait never saw none and the index was put
#: off for ever (the owner's audit_logs 228 s statement, the likely cause). A writer open when the build starts is waited
#: out by the build itself, which keeps no one else waiting meanwhile and says so («building - waiting for ...»).
BUILD_WAITS_ON = ("ShareUpdateExclusiveLock", "ShareLock", "ShareRowExclusiveLock", "ExclusiveLock", "AccessExclusiveLock")

#: What else a CONCURRENTLY build waits for (measured on PG 18.3, 총괄 11-07): the table's writers - locks that conflict
#: with ShareLock - and every transaction of this database holding a snapshot (`backend_xmin`), whatever it read. Waited
#: for before the build only once open longer than the wait itself (`older_than`): 11-06 stands for a short one, and one
#: left open (idle in transaction, a query that runs on) is what held the build for ever.
WRITES = ("RowExclusiveLock", "ShareUpdateExclusiveLock", "ShareRowExclusiveLock", "ExclusiveLock", "AccessExclusiveLock")

_TABLE_HOLDERS = (
    "SELECT a.pid, coalesce(bool_or(l.mode = ANY(%(strong)s)), false), coalesce(bool_or(l.mode = ANY(%(writes)s)), false),"
    " a.state, extract(epoch FROM now() - coalesce(a.xact_start, a.query_start))::int,"
    " to_char(coalesce(a.xact_start, a.query_start), 'HH24:MI:SS'), left(regexp_replace(coalesce(a.query, ''), '\\s+', ' ', 'g'), 60) "
    "FROM pg_stat_activity a LEFT JOIN pg_locks l ON l.pid = a.pid AND l.granted "
    " AND l.relation = to_regclass(quote_ident(coalesce(%(schema)s, current_schema())) || '.' || quote_ident(%(table)s)) "
    "WHERE a.pid <> pg_backend_pid() AND a.datname = current_database() AND a.backend_type <> 'autovacuum worker' "
    "GROUP BY a.pid, a.state, a.xact_start, a.query_start, a.query, a.backend_xmin "
    "HAVING coalesce(bool_or(l.mode = ANY(%(strong)s)), false) OR (%(older)s IS NOT NULL "
    " AND now() - coalesce(a.xact_start, a.query_start) > make_interval(secs => %(older)s) "
    " AND (a.backend_xmin IS NOT NULL OR coalesce(bool_or(l.mode = ANY(%(writes)s)), false))) ORDER BY a.pid")


#: PostgreSQL's query_canceled - what a statement_timeout's cancel raises (`exc.orig.pgcode`).
QUERY_CANCELED = "57014"


def table_holders(dbapi_conn, table, schema=None, older_than=None):
    """-> the other sessions a CONCURRENTLY build of `table` would wait for and that the wait before it waits out
    (총괄 11-05 ㄱ-2): one holding the table in a mode its own lock conflicts with, any age (`BUILD_WAITS_ON`); and, open
    longer than `older_than` seconds, one writing the table or holding a snapshot of this database (`WRITES`, 11-07).
    An autovacuum worker left out (a build's lock request cancels it). Each said for the line: «<pid> holding <table>»
    and, when open that long, «(<state>, open <n> s since <hh:mm:ss>: <its query's head>)»."""
    with dbapi_conn.cursor() as cur:
        cur.execute(_TABLE_HOLDERS, {"strong": list(BUILD_WAITS_ON), "writes": list(WRITES), "schema": schema,
                                     "table": table, "older": older_than})
        return ["%s%s%s" % (pid, " holding %s" % table if strong or writes else "",
                            " (%s, open %s s since %s: %s)" % (state, age, since, query)
                            if older_than is not None and age > older_than else "")
                for pid, strong, writes, state, age, since, query in cur.fetchall()]


def index_builds(dbapi_conn):
    """-> {(schema, index): (the building backend's pid, the pid it waits for or None, what its build is doing)} - each
    index of this database a session is building now; a waiting one names whom it waits for. The index master's
    «building» and the ledger builder's «left to it» and its waits (총괄 bdc08ec39 ① ②)."""
    with dbapi_conn.cursor() as cur:
        cur.execute(_INDEX_BUILDS)
        rows = cur.fetchall()
    return {(space, name): (pid, locker or None, "building - waiting for transactions older than it: pid %s (%s)"
                            % (locker, app or "no application_name") if locker else "building - %s" % phase)
            for space, name, pid, phase, locker, app in rows}


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


def work_on(pid, beats=None):
    """-> what work holds database backend `pid`: «<beat> · <its claim>[, rule <name>]» - the open work claim whose
    database pid it is, as each process's beat publishes it (`heartbeat.note_work` db_pid / lock_db_pid: a chain
    group, a slot's, a watcher file); None when no fresh beat names it. Up to one beat old. `beats`: `heartbeat.read_all()`
    already read."""
    from runtime.running import work_facts
    from utils import heartbeat

    for name, beat in sorted((heartbeat.read_all() if beats is None else beats).items()):
        work = beat.get("work") or {}
        facts = work.get("facts") or {}
        if beat.get("stale") or pid not in (facts.get("db_pid"), facts.get("lock_db_pid")):
            continue
        run = work_facts(work)["rule_run"]
        return "%s · %s%s" % (name, work.get("what") or "work", ", rule %s" % run["rule"] if run else "")
    return None


def _seconds(value):
    return None if value is None else float(value)


def _age(seconds):
    if seconds is None:
        return "for an unknown time"
    return "%d s" % seconds if seconds < 600 else "%d min" % (seconds // 60)
