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
#    🔴 2026-08-06: this constant was declared with the reasoning above and then NEVER
#       REFERENCED - the query filtered on a hardcoded literal 1000 and the verdict was
#       driven by the ratio alone. So the absolute floor that the outbox incident was
#       supposed to install did not actually exist in the verdict. It does now.
DEAD_ABSOLUTE_FLAG = 1000

# Bloat that needs no statistics collector: rows actually stored per 8 KB page. A heap
# holding fewer than one row per page is space that was allocated and never reclaimed.
# `database_outbox` measured 0.23 rows/page (89,250 rows over 384,027 pages) while its
# dead-tuple ratio read a calm 0.15. The page floor keeps small, naturally sparse tables
# out of the verdict - under a megabyte the reading is noise.
DENSITY_MIN_ROWS = 1.0
DENSITY_MIN_PAGES = 128

# An exact count(*) is the tiebreaker when the collector's counters look wrong, but this
# script runs against production, so it is bounded. On timeout the section falls back to
# `reltuples` and says which one it used.
COUNT_TIMEOUT_MS = 5000

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
    #
    # 🔴 EVERY NUMBER THIS SECTION USED TO PRINT CAME FROM `pg_stat_user_tables`, AND THOSE
    #    COUNTERS CAN BE LOST. They live in the statistics collector's file, which is
    #    discarded on an unclean shutdown and zeroed by `pg_stat_reset()`. The TABLE is
    #    untouched when that happens - only the bookkeeping about it disappears. So
    #    `n_live_tup` reads near zero for a table holding millions of rows,
    #    `last_autovacuum`/`last_autoanalyze` read `never` for a table that has been
    #    vacuumed and analysed all along, and `n_dead_tup / n_live_tup` manufactures an
    #    enormous ratio out of a denominator that is simply missing.
    #
    #    Measured here on 2026-08-06: this section reported `cell_sources` at 5,722 live
    #    rows against a real 13,709,607, and `audit_logs` at 1,119 against 2,820,556, then
    #    rendered `[BAD] 5 table(s) carry dead tuples above 20% of live rows`. All five were
    #    artefacts. A lane tracing a slow API spent a round on that verdict. Worse, the one
    #    genuinely bloated table was NOT among the five: `database_outbox` held 89,250 rows
    #    across 384,027 pages (0.23 rows per page, 3.0 GB) and its ratio read a calm 0.15,
    #    because its counters happened to be intact.
    #
    #    THE RULE THIS SECTION NOW FOLLOWS: cross-check against the real row count before
    #    saying anything, and when the counters disagree with it, SAY THEY ARE UNUSABLE
    #    instead of computing a confident number from them. `reltuples` and `relpages` come
    #    from `pg_class`, are maintained by vacuum/analyze rather than by the collector, and
    #    survived intact on the box where everything else was lost - so they are the cheap
    #    cross-check, with a bounded exact `count(*)` as the tiebreaker.
    #
    #    And the bloat verdict is now driven by PAGE DENSITY, which needs no collector
    #    counter at all: rows-per-page is computed from the real count and `relpages`, so it
    #    stays true exactly when the counters have gone missing. That is the check that
    #    would have caught `database_outbox` on the day this tool called it clean.
    print(f"\n4. BLOAT (dead tuples over {int(BLOAT_RATIO_FLAG * 100)}% of live or over "
          f"{DEAD_ABSOLUTE_FLAG:,} absolute; page density judged separately)")
    rows = conn.execute(sa.text("""
        SELECT s.relname, s.n_live_tup, s.n_dead_tup, s.last_autovacuum, s.last_autoanalyze,
               s.last_analyze, s.n_mod_since_analyze, c.reltuples::bigint, c.relpages,
               (SELECT count(*) FROM pg_stats g
                 WHERE g.schemaname = s.schemaname AND g.tablename = s.relname) AS statcols
        FROM pg_stat_user_tables s
        JOIN pg_class c ON c.oid = s.relid
        -- 🔴 종전에는 `WHERE n_dead_tup > 1000`이었다. 그 필터가 **한 번도 ANALYZE된 적 없는
        --    테이블을 구조적으로 안 보이게** 만든다. 그 조건은 유지하되, 여기에 `relpages`
        --    조건을 더한다 — 카운터가 유실되면 `n_dead_tup`도 0으로 읽히므로 데드 기준만으로는
        --    **가장 부푼 테이블이 조회 자체에서 빠진다**(database_outbox가 정확히 그랬다).
        --    페이지 수는 카운터가 아니라 pg_class에서 오므로 그 구멍을 메운다.
        WHERE s.n_dead_tup > :dead OR s.last_autoanalyze IS NULL OR c.relpages > :pages
        ORDER BY c.relpages DESC
        LIMIT 20
    """), {"dead": DEAD_ABSOLUTE_FLAG, "pages": DENSITY_MIN_PAGES}).fetchall()

    def exact_count(table_name):
        """The real row count, bounded. `None` means 'could not settle it in time'.

        Bounded because this runs against production: an unbounded `count(*)` on a very
        large table would turn a diagnostic into an outage of its own. A timeout aborts the
        transaction, so the rollback is mandatory rather than tidy - without it every
        remaining query in this script fails and the report ends in a lie.
        """
        try:
            conn.execute(sa.text(f"SET statement_timeout = {COUNT_TIMEOUT_MS}"))
            return conn.execute(sa.text(f'SELECT count(*) FROM "{table_name}"')).scalar()
        except Exception:
            try:
                conn.rollback()
                conn.execute(sa.text("SET TRANSACTION READ ONLY"))
            except Exception:
                pass
            return None
        finally:
            try:
                conn.execute(sa.text("SET statement_timeout = 0"))
            except Exception:
                pass

    if not rows:
        say("OK", "no table carries a significant dead-tuple count")
    else:
        dead_bad, dense_bad, unusable, no_stats = [], [], [], []
        for (name, live, dead, av, aa, la, modsa, reltup, relpages, statcols) in rows:
            live, dead, relpages = (live or 0), (dead or 0), (relpages or 0)
            real = exact_count(name)
            truth = real if real is not None else (reltup if reltup and reltup > 0 else None)
            src = "count(*)" if real is not None else ("reltuples~" if truth else "unknown")

            # Are the collector's counters believable? Only if `n_live_tup` lands in the
            # right order of magnitude. Tiny tables are exempt - the ratio is meaningless
            # there anyway and rounding would flag them forever.
            usable = (truth is None) or (truth < 100) or (live >= truth * 0.5)
            density = (truth / relpages) if (truth and relpages) else None

            print(f"      {name:32} real {(truth if truth is not None else -1):>12,} ({src})"
                  f"  pages {relpages:>9,}"
                  + (f"  rows/page {density:8.2f}" if density is not None else ""))
            if usable:
                ratio = round(dead / live, 3) if live > 0 else None
                print(f"       {'':32} live {live:>12,}  dead {dead:>10,}  ratio {ratio}"
                      f"  autovacuum {av or 'never'}  autoanalyze {aa or 'never'}")
                if (ratio is not None and ratio >= BLOAT_RATIO_FLAG) or dead > DEAD_ABSOLUTE_FLAG:
                    dead_bad.append(name)
            else:
                # 🔴 The whole point of the rewrite: refuse to compute rather than compute
                #    from numbers that are known to be wrong.
                print(f"       {'':32} [counters unusable] n_live_tup {live:,} vs real "
                      f"{truth:,} - dead-tuple ratio NOT computed for this table")
                unusable.append(name)

            if density is not None and relpages > DENSITY_MIN_PAGES and density < DENSITY_MIN_ROWS:
                dense_bad.append((name, truth, relpages, density))
            # Genuinely missing planner statistics is `pg_stats` having no row for the
            # table - NOT `last_autoanalyze IS NULL`, which is the counter that gets lost.
            if statcols == 0 and truth and truth > 0:
                no_stats.append(name)

        if dense_bad:
            worst = ", ".join(f"{n} ({t:,} rows over {p:,} pages, {d:.2f}/page)"
                              for n, t, p, d in dense_bad[:3])
            say("BAD", f"{len(dense_bad)} table(s) are bloated by page density: {worst}. "
                       f"This measure does not depend on the statistics collector, so it "
                       f"stays true even where the counters were lost.")
        if dead_bad:
            say("BAD", f"{len(dead_bad)} table(s) carry dead tuples above "
                       f"{int(BLOAT_RATIO_FLAG * 100)}% of live or above "
                       f"{DEAD_ABSOLUTE_FLAG:,} absolute ({', '.join(dead_bad[:5])}). "
                       f"If section 2 also flagged a long transaction, that is the cause and "
                       f"not a coincidence: autovacuum cannot reclaim rows newer than the "
                       f"oldest open transaction, so the bloat grows for as long as it stays.")
        if no_stats:
            say("WARN", f"{len(no_stats)} table(s) have NO planner statistics at all "
                        f"({', '.join(no_stats[:5])}) - the planner is costing against a "
                        f"table it knows nothing about. Run ANALYZE on them.")
        if unusable:
            say("WARN", f"the statistics collector's counters are unusable on {len(unusable)} "
                        f"table(s) ({', '.join(unusable[:5])}): n_live_tup disagrees with the "
                        f"real row count by more than 2x, which means the stats file was lost "
                        f"or reset. NO dead-tuple verdict was computed for them, and every "
                        f"'never' printed above for autovacuum/autoanalyze is unreliable for "
                        f"the same reason. `VACUUM (ANALYZE)` on those tables restores the "
                        f"counters; the page-density line above is the reading to trust "
                        f"meanwhile.")

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
