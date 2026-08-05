"""Read-only PostgreSQL health probe: long transactions, bloat, blocking.

WHY THIS EXISTS. "The API got slower" and "there are probably zombie transactions" are the
same sentence viewed from two ends, and the link between them is mechanical rather than
mysterious: a transaction left open holds back the xmin horizon, autovacuum cannot reclaim
dead tuples older than it, the table bloats, and every sequential scan over it costs more.
That produces a slowdown that arrives GRADUALLY, which is exactly what "slower than it used
to be" describes and exactly what a single timing measurement cannot see.

READ-ONLY, AND NOT MERELY BY INTENTION. The session is pinned `transaction_read_only = on`
before anything runs, so a mistake in this file cannot write. It issues no VACUUM, no
ANALYZE, no terminate. It names the PIDs it would be reasonable to look at and stops there:
killing a session is an operator's decision, and an idle-in-transaction connection may be a
person mid-edit rather than a leak.

Run:  python server/scripts/diagnose_db_health.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import sqlalchemy as sa                                          # noqa: E402
# 🔴 Take the URL the APP resolved, never the module's built-in default. `DEFAULT_PG_URL` is
#    the last fallback in a three-step chain (env DATABASE_URL > <config>/database.json >
#    default), so reading it directly probes the developer's database name while claiming to
#    report on production - which is precisely what happened on the first run of this script.
#    `DB_URL_SOURCE` is printed below so the operator can see WHICH of the three answered.
from database.database import SQLALCHEMY_DATABASE_URL, DB_URL_SOURCE   # noqa: E402

# An open transaction older than this is worth a look. Not a threshold with authority -
# a five-minute transaction on a busy system may be ordinary and a one-minute one may be a
# leak. It only decides what gets printed in bold.
LONG_XACT_SEC = 300
BLOAT_RATIO_FLAG = 0.20          # dead tuples as a fraction of live

# 🔴 AN ABSOLUTE FLOOR, BECAUSE THE RATIO IS BLIND WHERE IT MATTERS MOST.
#    `dead / live` is undefined when a table has no live rows, and the tables that hurt most
#    are exactly the ones that churn to empty: a queue or an outbox drains to zero live and
#    accumulates dead forever, so its ratio is NULL and a ratio-only alarm never fires. It
#    did not fire. `database_outbox` was measured at 11,734 dead, 0 live, `last_autovacuum`
#    NEVER - reported clean by this script the day the product owner traced a system-wide
#    slowdown to dead-tuple bloat.
#
#    This is the same shape as the ratio that inverts alignment rankings: a normalised
#    number discards the denominator, and the denominator was the fact.
#
#    1000 is the PRODUCT OWNER'S POLICY (2026-08-05): no table over 1,000 dead tuples. This
#    constant mirrors that policy so the report and the database agree on what "too many"
#    means; if the policy moves, both move.
DEAD_ABSOLUTE_FLAG = 1000

findings = []


def say(sev, msg):
    findings.append((sev, msg))
    print(f"  [{sev}] {msg}")


url = SQLALCHEMY_DATABASE_URL
print("=" * 72)
print("POSTGRES HEALTH (read-only)")
print("=" * 72)
# Name the database and where the URL came from. A probe that reports on the wrong database
# is worse than no probe, and "it errored" is the friendly version of that mistake - the
# unfriendly version is a clean report about a database nobody asked about.
_dbname = url.rsplit("/", 1)[-1].split("?")[0]
print(f"  database: {_dbname}   (url source: {DB_URL_SOURCE})")

engine = sa.create_engine(url)
with engine.connect() as conn:
    conn.execute(sa.text("SET TRANSACTION READ ONLY"))

    # 1. What every connection is doing -------------------------------------
    print("\n1. CONNECTIONS BY STATE")
    rows = conn.execute(sa.text("""
        SELECT state,
               count(*) AS n,
               max(EXTRACT(EPOCH FROM (now() - xact_start)))::int AS oldest_xact_sec
        FROM pg_stat_activity
        WHERE datname = current_database()
        GROUP BY state
        ORDER BY n DESC
    """)).fetchall()
    for state, n, oldest in rows:
        age = f", oldest transaction {oldest}s" if oldest else ""
        print(f"  {str(state or 'unknown'):24} {n:4}{age}")
    idle_tx = next((n for s, n, _ in rows if s == "idle in transaction"), 0)
    if idle_tx:
        say("WARN", f"{idle_tx} connection(s) sit in 'idle in transaction' - each one holds "
                    f"back the xmin horizon for as long as it lasts")

    # 2. The oldest open transaction, which is the one that matters ----------
    # Only the SINGLE oldest matters for vacuum: the horizon is held at the earliest xmin,
    # so ten recent transactions cost nothing and one forgotten one costs everything.
    print(f"\n2. TRANSACTIONS OPEN LONGER THAN {LONG_XACT_SEC}s")
    rows = conn.execute(sa.text("""
        SELECT pid, state,
               EXTRACT(EPOCH FROM (now() - xact_start))::int AS xact_sec,
               EXTRACT(EPOCH FROM (now() - state_change))::int AS state_sec,
               application_name, left(coalesce(query, ''), 90) AS q
        FROM pg_stat_activity
        WHERE datname = current_database()
          AND xact_start IS NOT NULL
          AND now() - xact_start > make_interval(secs => :lim)
          AND pid <> pg_backend_pid()
        ORDER BY xact_start
    """), {"lim": LONG_XACT_SEC}).fetchall()
    if not rows:
        say("OK", f"no transaction has been open longer than {LONG_XACT_SEC}s")
    else:
        for pid, state, xs, ss, app, q in rows:
            print(f"  PID {pid}  open {xs}s  state '{state}' for {ss}s  app={app or '-'}")
            print(f"      last query: {q}")
        say("BAD", f"{len(rows)} long-running transaction(s). The OLDEST one alone sets the "
                   f"vacuum horizon, so reclaim is blocked back to PID {rows[0][0]} "
                   f"({rows[0][2]}s). Decide per PID whether it is a person or a leak - this "
                   f"script does not terminate anything.")

    # 3. Is anything actually blocked ----------------------------------------
    print("\n3. LOCK WAITS")
    rows = conn.execute(sa.text("""
        SELECT w.pid AS waiter, b.pid AS blocker,
               EXTRACT(EPOCH FROM (now() - w.query_start))::int AS wait_sec,
               left(coalesce(w.query, ''), 70) AS q
        FROM pg_stat_activity w
        JOIN LATERAL unnest(pg_blocking_pids(w.pid)) AS b(pid) ON true
        WHERE w.datname = current_database()
    """)).fetchall()
    if not rows:
        say("OK", "nothing is waiting on a lock")
    else:
        for waiter, blocker, secs, q in rows:
            print(f"  PID {waiter} waiting {secs}s on PID {blocker}: {q}")
        say("BAD", f"{len(rows)} session(s) blocked on locks")

    # 4. Bloat - the mechanism that turns a stale transaction into slowness ---
    print(f"\n4. DEAD TUPLES (flagged over {int(BLOAT_RATIO_FLAG * 100)}% of live rows)")
    rows = conn.execute(sa.text("""
        SELECT relname, n_live_tup, n_dead_tup,
               CASE WHEN n_live_tup > 0
                    THEN round(n_dead_tup::numeric / n_live_tup, 3) ELSE NULL END AS ratio,
               last_autovacuum, last_autoanalyze
        FROM pg_stat_user_tables
        WHERE n_dead_tup > 1000
        ORDER BY n_dead_tup DESC
        LIMIT 15
    """)).fetchall()
    if not rows:
        say("OK", "no table carries a significant dead-tuple count")
    else:
        worst = []
        for name, live, dead, ratio, av, aa in rows:
            flag = "  <-- " if (ratio or 0) >= BLOAT_RATIO_FLAG else "      "
            print(f"{flag}{name:34} live {live:>10,}  dead {dead:>10,}  "
                  f"ratio {ratio}  last autovacuum {av or 'never'}")
            if (ratio or 0) >= BLOAT_RATIO_FLAG:
                worst.append(name)
        if worst:
            say("BAD", f"{len(worst)} table(s) carry dead tuples above "
                       f"{int(BLOAT_RATIO_FLAG * 100)}% of live rows ({', '.join(worst[:5])}). "
                       f"If section 2 also flagged a long transaction, that is the cause and "
                       f"not a coincidence: autovacuum cannot reclaim rows newer than the "
                       f"oldest open transaction, so the bloat grows for as long as it stays.")

    # 5. Cache hit ratio - a blunt instrument, stated as one ------------------
    print("\n5. CACHE HIT RATIO (cumulative since stats reset - NOT a current reading)")
    row = conn.execute(sa.text("""
        SELECT sum(heap_blks_hit), sum(heap_blks_read)
        FROM pg_statio_user_tables
    """)).fetchone()
    # float(), not the raw values: these come back as Decimal and `100.0 * Decimal` raises.
    hit, read = float(row[0] or 0), float(row[1] or 0)
    if hit + read > 0:
        pct = 100.0 * hit / (hit + read)
        print(f"  {pct:.2f}%  ({hit:,} hit / {read:,} read)")
        if pct < 95:
            say("WARN", f"cache hit ratio {pct:.1f}% - a bloated table pushes useful pages out, "
                        f"so this often falls as a side effect rather than a cause")
    else:
        print("  no I/O recorded")

print("\n" + "=" * 72)
bad = [m for s, m in findings if s == "BAD"]
warn = [m for s, m in findings if s == "WARN"]
if bad:
    print(f"VERDICT: {len(bad)} problem(s).\n")
    for i, m in enumerate(bad, 1):
        print(f"  {i}. {m}")
elif warn:
    print("VERDICT: nothing conclusive, but see the warnings above.\n")
else:
    print("VERDICT: no long transactions, no lock waits, no significant bloat.\n")
    print("  So a gradual slowdown is not coming from this axis. The next places to look")
    print("  are the query plans themselves and the table sizes they scan.")
print("=" * 72)
sys.exit(1 if bad else 0)
