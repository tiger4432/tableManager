"""Read-only probe: WHY is this box slow right after a bulk ingestion?

    conda run --no-capture-output -n assy_manager python server/scripts/diagnose_slow_after_ingest.py

That one line is the whole invocation. Nothing else has to be prepared, no URL
has to be typed, and the output is plain text meant to be pasted back verbatim.

    To keep a copy:  ... diagnose_slow_after_ingest.py > probe.txt 2>&1

⚠️ `--no-capture-output` IS NOT OPTIONAL ON WINDOWS, and it is not cosmetic.
Without it `conda run` pipes the child's output through its own decoder, which on
a Korean Windows box is cp949; every Korean heading in this report then arrives
as replacement characters and the operator cannot read the thing they were asked
to paste back. Measured here: 그대로 -> mojibake with the flag absent, clean with
it present. The script already pins its own stdout to UTF-8, which is necessary
and, by itself, not sufficient.

===============================================================================
STRICTLY READ-ONLY, AND ENFORCED BY THE SERVER RATHER THAN BY GOOD INTENTIONS
===============================================================================
The connection is opened with ``default_transaction_read_only=on`` set as a
CONNECTION OPTION, so it applies to EVERY transaction this session ever opens -
including one that begins after a rollback, which is where a
``SET TRANSACTION READ ONLY`` issued once would have quietly lapsed. PostgreSQL
itself then refuses INSERT/UPDATE/DELETE/DDL from this session. There is no
VACUUM, no ANALYZE, no REINDEX, no CREATE INDEX, no pg_terminate_backend and no
pg_stat_reset anywhere in this file.

Every statement reads catalogues (``pg_class``), statistics views
(``pg_stat_*``), or at most a hundred rows of one table ordered by its primary
key. None of them takes a lock heavier than AccessShareLock. The session also
pins ``lock_timeout``, ``statement_timeout`` and
``idle_in_transaction_session_timeout``, so a probe run on a struggling box
cannot become the long transaction that makes it worse.

The ONLY thing this script can write is the optional ``--json`` snapshot file on
local disk, and only when you ask for it by name.

===============================================================================
WHAT IT ANSWERS
===============================================================================
Each section separates a cause that the others cannot rank:

  1. 지금 무엇을 하고 있는가 - live sessions, waits, blockers, connection budget
  2. 오토배큠            - dead tuples and whether autovacuum is mid-storm
  3. OUTBOX 적체         - backlog depth, age, size, and WHICH PAYLOAD SHAPE
  4. 크기                - heap/index/toast per table + index scan counts
  4b. 1초는 어디서 오는가 - THE DISCRIMINATOR. A ladder of endpoints where each
                           rung adds exactly one cost to the rung below it, so a
                           jump between two rungs names its own cause: thread
                           token / database connection / the query itself.
                           Needs --http. Read its section G first.
  5. 페이지 로드         - the actual page-load work, timed
  5b. 감사 이력 첫 호출  - the one that reproduced the report (see its docstring)
  6. pg_stat_statements  - top queries, or a plain statement that it is absent

===============================================================================
THE LAST LINE
===============================================================================
The report ENDS in one line naming which rung of the 4b ladder jumped and by how
much, because the box this runs on does not allow copying output off it and an
operator has to be able to relay the answer verbatim without understanding the
ladder. Above it sits a twelve-character digest of the whole ladder for when the
verdict alone is ambiguous. See section 4c for what each wording means - in
particular, 판정불가 / 부분측정 / 점프 없음 are three DIFFERENT answers, and an
inconclusive run never renders as a healthy one.

===============================================================================
NUMBERS THAT ARE ESTIMATES, AND WHY IT MATTERS
===============================================================================
Anything marked ``~`` comes from ``pg_class.reltuples`` (maintained by
vacuum/analyze) or from the statistics collector (``pg_stat_*``), not from a
count. That is deliberate: an exact ``count(*)`` on a ten-million-row table is
itself a minute of I/O, and a diagnostic that causes the outage it is measuring
is worthless.

🔴 The statistics collector's counters (``n_live_tup``, ``n_dead_tup``,
``last_autovacuum``, ``idx_scan``) LIVE IN A FILE THAT IS LOST on an unclean
shutdown and zeroed by ``pg_stat_reset()``. On 2026-08-06 that made a
13.7-million-row table read as 5,722 live rows here, and an earlier version of a
sibling script rendered five confident BAD verdicts out of the wreckage - all
five artefacts, while the one genuinely bloated table passed. So section 2
cross-checks every counter against ``reltuples`` and REFUSES TO COMPUTE a ratio
when the two disagree, and section 0 prints when the counters were last reset.
"""
import argparse
import json
import math
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# Korean headings on a Windows console default to cp949 and raise. Fix it here so
# the operator does not have to remember PYTHONIOENCODING before running a
# diagnostic - a probe that crashes on its own section title is not a probe.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import sqlalchemy as sa                                              # noqa: E402
import paths                                                        # noqa: E402

# 🔴 Take the URL the APP resolves, never a literal. `resolve_database_url` is the
#    same three-step chain server/database/database.py consumes at import
#    (env DATABASE_URL > <config>/database.json > default), so this script and the
#    server cannot end up looking at different databases. A clean report about a
#    database nobody asked about is worse than an error.
DEFAULT_PG_URL = "postgresql://postgres:admin@localhost:5432/assy_manager"

# The server's own pool arithmetic, quoted from server/database/database.py:48-49.
# Kept as constants so the printed budget and the engine cannot drift apart
# silently; if those lines move, this line is wrong in an obvious place.
POOL_SIZE = 20
MAX_OVERFLOW = 10
POOL_CEILING_PER_PROCESS = POOL_SIZE + MAX_OVERFLOW

# Anything potentially unbounded runs under this. On timeout the section says so
# and falls back to an estimate rather than dying.
BOUNDED_MS = 5000
# The catalogue/statistics queries are cheap, but a box under vacuum pressure can
# still stall on catalogue I/O. This is the outer bound for everything.
STATEMENT_TIMEOUT_MS = 20000

SEP = "=" * 78
SUB = "-" * 78

snapshot = {}          # only written to disk when --json is given
_notes = []

# Everything the closing one-line verdict is allowed to reason from. Section 4b
# fills it; `main` reads it. Kept as a module global rather than a return value
# because the verdict has to survive a section that returned early, and "the
# ladder did not run, and here is why" is one of the answers it must be able to
# give.
_ladder = {
    "ran": False,        # did the ladder actually take measurements?
    "why_not": None,     # if not, the operator-readable reason
    "rungs": {},         # rung key -> _stat() dict, ONLY for HTTP 200 samples
    "health_db": None,   # /health checks.database, verbatim
    "r0_status": None,   # what GET /health actually answered
    "r0_body_json": None,  # None=not reached, False=200 but not the health doc
}


def note(msg):
    _notes.append(msg)


def head(n, title):
    print(f"\n{SEP}\n{n}. {title}\n{SEP}")


def sub(title):
    print(f"\n  -- {title}")


def human(nbytes):
    if nbytes is None:
        return "-"
    v = float(nbytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(v) < 1024 or unit == "TB":
            return f"{v:,.1f} {unit}" if unit != "B" else f"{int(v):,} B"
        v /= 1024
    return f"{v:,.1f} TB"


def age(seconds):
    if seconds is None:
        return "-"
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m{s % 60:02d}s"
    if s < 86400:
        return f"{s // 3600}h{(s % 3600) // 60:02d}m"
    return f"{s // 86400}d{(s % 86400) // 3600:02d}h"


class Probe:
    """One connection, pinned read-only, with bounded helpers."""

    def __init__(self, url):
        self.engine = sa.create_engine(
            url,
            poolclass=sa.pool.NullPool,          # one connection, no pool of our own
            connect_args={"options": (
                # 🔴 The read-only pin. As a CONNECTION option it survives rollbacks
                #    and applies to every transaction, unlike a one-shot
                #    `SET TRANSACTION READ ONLY`.
                "-c default_transaction_read_only=on "
                f"-c statement_timeout={STATEMENT_TIMEOUT_MS} "
                # Never queue behind someone else's lock: this script would rather
                # report "could not read that" than add a waiter to a jammed box.
                "-c lock_timeout=2000 "
                "-c idle_in_transaction_session_timeout=60000 "
                "-c client_encoding=utf8"
            ),
                "application_name": "assy_slow_probe"},
        )
        self.conn = self.engine.connect()
        self.pg_version = self.conn.execute(
            sa.text("SHOW server_version_num")).scalar()
        self.pg_version = int(self.pg_version or 0)

    def close(self):
        try:
            self.conn.close()
        finally:
            self.engine.dispose()

    def _release(self):
        """End the current transaction. Called after EVERY statement.

        🔴 NOT tidiness. SQLAlchemy opens a transaction on first execute and holds
        it until told otherwise, so without this the probe would keep ONE snapshot
        open for its entire run - and a read-only transaction holds back the xmin
        horizon exactly as a writing one does. On a box whose problem is that
        autovacuum cannot reclaim, a diagnostic that blocks reclaim while it
        measures is part of the fault. Each statement now stands alone.
        """
        try:
            self.conn.rollback()
        except Exception:
            pass

    def rows(self, sql, **params):
        """Query that is expected to work. Returns [] and prints why on failure.

        The rollback is mandatory rather than tidy: a statement_timeout aborts the
        transaction, and without the rollback EVERY remaining query in this file
        fails and the report ends in a lie.
        """
        try:
            out = self.conn.execute(sa.text(sql), params).fetchall()
            self._release()
            return out
        except Exception as e:
            self._release()
            print(f"     [읽기 실패] {type(e).__name__}: {str(e).splitlines()[0][:150]}")
            return []

    def one(self, sql, **params):
        r = self.rows(sql, **params)
        return r[0] if r else None

    def bounded(self, sql, ms=BOUNDED_MS, **params):
        """A query that COULD be expensive. `(rows, timed_out)`.

        Used only where an exact answer is worth trying for and an estimate is an
        acceptable fallback - never as the primary source for a big table.
        """
        try:
            # SET LOCAL, so the shorter budget dies with this transaction and
            # cannot leak into the next section's statement.
            self.conn.execute(sa.text(f"SET LOCAL statement_timeout = {int(ms)}"))
            out = self.conn.execute(sa.text(sql), params).fetchall()
            self._release()
            return out, False
        except Exception:
            self._release()
            return [], True

    def has_relation(self, name):
        return bool(self.one(
            "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE c.relname = :n AND n.nspname NOT IN "
            "('pg_catalog','information_schema') LIMIT 1", n=name))


# ---------------------------------------------------------------------------
# 0. Which database, and what kind of server is it
# ---------------------------------------------------------------------------
def section_context(p, url, url_source):
    head(0, "이 보고서가 측정한 대상 (WHAT WAS MEASURED)")
    row = p.one("SELECT current_database(), inet_server_addr()::text, "
                "inet_server_port(), version(), "
                "EXTRACT(EPOCH FROM (now() - pg_postmaster_start_time()))::bigint")
    dbname, srv_addr, srv_port, ver, uptime = (row if row else (None,) * 5)
    print(f"  데이터베이스   : {dbname}")
    print(f"  접속 URL       : {paths.mask_db_password(url)}   (출처: {url_source})")
    print(f"  서버           : {srv_addr or 'local socket'}:{srv_port}")
    print(f"  버전           : {(ver or '').split(' on ')[0]}")
    print(f"  서버 가동 시간 : {age(uptime)}")
    print(f"  측정 시각      : {datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}")
    print(f"  데이터 루트    : {paths.DATA_ROOT}  (isolated={paths.IS_ISOLATED})")
    snapshot["context"] = {"database": dbname, "url_source": url_source,
                           "uptime_sec": int(uptime or 0),
                           "at": datetime.now(timezone.utc).isoformat()}

    sub("통계 카운터가 마지막으로 초기화된 시각 (⚠️ 2~6절 해석의 전제)")
    r = p.one("SELECT stats_reset, "
              "EXTRACT(EPOCH FROM (now() - stats_reset))::bigint "
              "FROM pg_stat_database WHERE datname = current_database()")
    if r and r[0]:
        print(f"     {r[0]}  ({age(r[1])} 전)")
        print("     이 시각 이후의 누적치만 담겨 있다. 짧으면 «없음»이 «안 일어났다»가 아니라")
        print("     «아직 안 쌓였다»는 뜻이다.")
        snapshot["stats_reset_age_sec"] = int(r[1] or 0)
    else:
        print("     통계 초기화 기록이 없다 (수집기 파일이 유실됐거나 한 번도 리셋되지 않았다).")

    sub("성능에 직접 걸리는 서버 설정")
    keys = ["max_connections", "superuser_reserved_connections", "shared_buffers",
            "work_mem", "maintenance_work_mem", "effective_cache_size",
            "max_wal_size", "min_wal_size", "checkpoint_timeout",
            "checkpoint_completion_target", "autovacuum", "autovacuum_max_workers",
            "autovacuum_naptime", "autovacuum_vacuum_threshold",
            "autovacuum_vacuum_scale_factor", "autovacuum_analyze_scale_factor",
            "autovacuum_vacuum_cost_delay", "autovacuum_vacuum_cost_limit",
            "synchronous_commit", "wal_compression", "random_page_cost"]
    settings = {}
    for name, setting, unit in p.rows(
            "SELECT name, setting, coalesce(unit,'') FROM pg_settings "
            "WHERE name = ANY(:k) ORDER BY name", k=keys):
        settings[name] = f"{setting}{unit}"
        print(f"     {name:38} {setting}{unit}")
    snapshot["settings"] = settings

    sub("체크포인트 압력 (대량 적재 직후 느려지는 고전적 경로)")
    # PG17 split pg_stat_bgwriter's checkpoint counters into pg_stat_checkpointer.
    # Try the new view first, fall back, and say nothing rather than guess.
    ck = None
    if p.pg_version >= 170000:
        ck = p.one("SELECT num_timed, num_requested, "
                   "write_time, sync_time, stats_reset FROM pg_stat_checkpointer")
    if ck is None:
        ck = p.one("SELECT checkpoints_timed, checkpoints_req, "
                   "checkpoint_write_time, checkpoint_sync_time, stats_reset "
                   "FROM pg_stat_bgwriter")
    if ck:
        timed, req, wtime, stime, reset = ck
        print(f"     예정 체크포인트 {timed or 0:,}회 / 강제(요청) 체크포인트 {req or 0:,}회")
        print(f"     write {float(wtime or 0)/1000:,.1f}s   sync {float(stime or 0)/1000:,.1f}s"
              f"   (집계 시작 {reset})")
        total = (timed or 0) + (req or 0)
        if total and (req or 0) / total > 0.3:
            note("체크포인트의 30% 이상이 «강제»다 — max_wal_size가 쓰기량에 비해 작아서 "
                 "대량 적재 중 체크포인트가 연쇄로 터지고 있을 가능성. (5절이 느리지 않은데 "
                 "체감이 느리면 이쪽을 본다)")
        snapshot["checkpoints"] = {"timed": timed, "requested": req}
    else:
        print("     체크포인터 통계를 읽지 못했다.")


# ---------------------------------------------------------------------------
# 1. What the database is doing RIGHT NOW
# ---------------------------------------------------------------------------
def section_activity(p):
    head(1, "지금 데이터베이스가 무엇을 하고 있는가 (NOW)")

    sub("접속 수 vs 상한")
    r = p.one("""
        SELECT count(*) FILTER (WHERE backend_type = 'client backend') AS clients,
               count(*) FILTER (WHERE backend_type = 'client backend'
                                 AND datname = current_database()) AS this_db,
               count(*) FILTER (WHERE state = 'active') AS active,
               count(*) FILTER (WHERE state = 'idle in transaction') AS idle_tx,
               count(*) FILTER (WHERE state = 'idle in transaction (aborted)') AS idle_tx_ab,
               count(*) FILTER (WHERE wait_event_type = 'Lock') AS lock_waiters,
               count(*) AS all_backends
        FROM pg_stat_activity
    """)
    maxconn = int(p.one("SELECT setting FROM pg_settings "
                        "WHERE name = 'max_connections'")[0])
    if r:
        clients, this_db, active, idle_tx, idle_tx_ab, lockw, allb = r
        print(f"     클라이언트 접속 {clients} / max_connections {maxconn}"
              f"   (이 DB: {this_db}, 전체 백엔드: {allb})")
        print(f"     active {active} · idle in transaction {idle_tx}"
              f" (aborted {idle_tx_ab}) · 락 대기 {lockw}")
        print()
        print(f"     [풀 상한 산수] 웹서버 프로세스 1개당 풀 {POOL_SIZE} + 오버플로 "
              f"{MAX_OVERFLOW} = {POOL_CEILING_PER_PROCESS}")
        print(f"     (server/database/database.py:48-49). 5-프로세스 스택이 모두 한계까지 쓰면 "
              f"{POOL_CEILING_PER_PROCESS * 5}개까지 열릴 수 있다.")
        pct = 100.0 * clients / maxconn if maxconn else 0
        print(f"     현재 사용률 {pct:.0f}%")
        if pct >= 80:
            note(f"접속이 max_connections의 {pct:.0f}%다. 여기서 신규 접속은 거절되거나 "
                 f"대기하고, 그것은 API뿐 아니라 «페이지 자체»가 안 뜨는 모양으로 보인다.")
        if idle_tx:
            note(f"«idle in transaction» 접속이 {idle_tx}개다. 하나만 있어도 그 시점 이후의 "
                 f"dead tuple을 autovacuum이 회수하지 못한다 (2절과 함께 읽을 것).")
        snapshot["connections"] = {"clients": clients, "max": maxconn,
                                   "active": active, "idle_in_tx": idle_tx,
                                   "lock_waiters": lockw}

    sub("접속의 출처별 분포 (application_name / 클라이언트)")
    for app, addr, n, act in p.rows("""
        SELECT coalesce(nullif(application_name, ''), '(unnamed)'),
               coalesce(host(client_addr), 'local'),
               count(*), count(*) FILTER (WHERE state = 'active')
        FROM pg_stat_activity
        WHERE backend_type = 'client backend'
        GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 20
    """):
        print(f"     {app[:34]:34} {addr:16} 총 {n:4}  active {act}")

    sub("idle 아닌 세션 (오래된 것부터 — 맨 위가 헤드라인)")
    # 🔴 pg_stat_activity is CLUSTER-WIDE. The datname column is printed on every
    #    line for that reason: on a box that also hosts another database, a session
    #    listed here may have nothing to do with the one this report measured, and
    #    reading it as ours is how a diagnostic invents a culprit. The connection
    #    budget above is cluster-wide on purpose (max_connections is), but a
    #    per-session verdict is not.
    #    Idle background processes (walwriter, io worker, ...) are excluded: their
    #    state is NULL and they are always "waiting", so they would fill the list
    #    with rows that are true and useless. Autovacuum/parallel workers are kept -
    #    they are exactly what an autovacuum storm looks like from here.
    rows = p.rows("""
        SELECT pid, coalesce(state, backend_type) AS st,
               coalesce(wait_event_type, '-') AS wt, coalesce(wait_event, '-') AS we,
               EXTRACT(EPOCH FROM (now() - query_start))::bigint AS q_age,
               EXTRACT(EPOCH FROM (now() - xact_start))::bigint AS x_age,
               coalesce(nullif(application_name, ''), backend_type) AS app,
               left(regexp_replace(coalesce(query, ''), '\\s+', ' ', 'g'), 150) AS q,
               pg_blocking_pids(pid) AS blockers,
               coalesce(datname, '-') AS db,
               (datname IS NOT DISTINCT FROM current_database()) AS is_ours
        FROM pg_stat_activity
        WHERE pid <> pg_backend_pid()
          AND ((state IS NOT NULL AND state <> 'idle')
               OR backend_type IN ('autovacuum worker', 'parallel worker'))
        ORDER BY coalesce(xact_start, query_start, now()) ASC
        LIMIT 40
    """)
    if not rows:
        print("     idle 아닌 세션이 없다. (지금 이 순간 DB는 놀고 있다)")
        note("스냅샷 시점에 DB가 놀고 있었다. 느림이 «항상»이 아니라 «적재 직후 한동안»이라면 "
             "이 절은 조용한 시점을 찍은 것이므로, 느릴 때 다시 한 번 돌려야 한다.")
    else:
        worst = []
        for (pid, st, wt, we, q_age, x_age, app, q, blockers,
             db, is_ours) in rows:
            blk = f"  ⛔ blocked by {list(blockers)}" if blockers else ""
            mark = "" if is_ours else "   ← 다른 데이터베이스"
            print(f"     PID {pid:<7} [{db}]{mark} {str(st)[:24]:24} wait={wt}/{we}")
            print(f"          query {age(q_age)} · xact {age(x_age)} · app={str(app)[:40]}{blk}")
            if q:
                print(f"          {q}")
            worst.append({"pid": pid, "db": db, "ours": bool(is_ours),
                          "state": str(st), "wait": f"{wt}/{we}",
                          "query_age_sec": int(q_age or 0),
                          "xact_age_sec": int(x_age or 0),
                          "blocked_by": list(blockers or [])})
        snapshot["activity"] = worst
        blocked = [w for w in worst if w["blocked_by"]]
        if blocked:
            note(f"{len(blocked)}개 세션이 락 때문에 멈춰 있다. 락 대기는 «느림»이 아니라 "
                 f"«정지»라서, 체감상 가장 먼저 눈에 띈다.")
        # Only OUR database's transactions hold back reclaim on OUR tables.
        longest = max((w["xact_age_sec"] for w in worst if w["ours"]), default=0)
        if longest > 300:
            note(f"이 데이터베이스에서 가장 오래된 트랜잭션이 {age(longest)}째 열려 있다. "
                 f"autovacuum은 이 트랜잭션보다 새로운 행을 회수하지 못하므로, 열려 있는 동안 "
                 f"블로트가 계속 자란다.")

    sub("진행 중인 VACUUM (진짜 «오토배큠 폭풍»인지 여기서 확정된다)")
    rows = p.rows("""
        SELECT v.pid, c.relname,
               v.phase, v.heap_blks_total, v.heap_blks_scanned, v.heap_blks_vacuumed,
               v.index_vacuum_count,
               EXTRACT(EPOCH FROM (now() - a.query_start))::bigint,
               coalesce(a.backend_type, '-')
        FROM pg_stat_progress_vacuum v
        LEFT JOIN pg_class c ON c.oid = v.relid
        LEFT JOIN pg_stat_activity a ON a.pid = v.pid
        ORDER BY v.heap_blks_total DESC
    """)
    if not rows:
        print("     지금 도는 VACUUM 없음.")
    else:
        for pid, rel, phase, tot, scanned, vac, ivc, secs, btype in rows:
            pct = (100.0 * (scanned or 0) / tot) if tot else 0
            print(f"     PID {pid} [{btype}] {rel}: phase={phase} "
                  f"{pct:.1f}% ({scanned or 0:,}/{tot or 0:,} blk) "
                  f"index pass {ivc}  경과 {age(secs)}")
        note(f"VACUUM이 {len(rows)}건 돌고 있다. 대량 적재 직후라면 이것이 «일시적으로 느리고 "
             f"시간이 지나면 회복되는» 증상의 전형적 원인이다 — 끝나면 사라진다.")
        snapshot["vacuum_in_progress"] = len(rows)

    if p.pg_version >= 130000:
        rows = p.rows("""
            SELECT a.pid, c.relname, a.phase, a.sample_blks_total, a.sample_blks_scanned
            FROM pg_stat_progress_analyze a LEFT JOIN pg_class c ON c.oid = a.relid
        """)
        if rows:
            print("\n     진행 중인 ANALYZE:")
            for pid, rel, phase, tot, sc in rows:
                print(f"       PID {pid} {rel}: {phase} ({sc or 0:,}/{tot or 0:,})")


# ---------------------------------------------------------------------------
# 2. Autovacuum
# ---------------------------------------------------------------------------
def section_autovacuum(p):
    head(2, "오토배큠 · 데드 튜플 (AUTOVACUUM)")
    print("  ⚠️ 이 절의 n_live_tup/n_dead_tup/last_autovacuum은 «통계 수집기»의 값이고,")
    print("     비정상 종료나 pg_stat_reset()으로 통째로 유실된다. 그래서 매 행마다")
    print("     pg_class.reltuples(=vacuum/analyze가 유지, 수집기와 함께 유실되지 않음)와")
    print("     대조하고, 2배 이상 어긋나면 «비율을 계산하지 않는다».")

    rows = p.rows("""
        SELECT s.relname, s.n_live_tup, s.n_dead_tup, s.n_mod_since_analyze,
               s.last_autovacuum, s.last_autoanalyze, s.last_vacuum, s.last_analyze,
               s.autovacuum_count, s.autoanalyze_count,
               c.reltuples::bigint, c.relpages,
               pg_total_relation_size(c.oid)
        FROM pg_stat_user_tables s JOIN pg_class c ON c.oid = s.relid
        ORDER BY s.n_dead_tup DESC NULLS LAST, c.relpages DESC
        LIMIT 15
    """)
    if not rows:
        print("     읽을 사용자 테이블이 없다.")
        return

    print(f"\n  {'테이블':28} {'~실행수':>13} {'live(통계)':>13} {'dead(통계)':>12} "
          f"{'dead비율':>9} {'AV횟수':>7}")
    print("  " + SUB)
    out = []
    for (name, live, dead, modsa, av, aa, v, a, avc, aac,
         reltup, relpages, totsize) in rows:
        live, dead, relpages = (live or 0), (dead or 0), (relpages or 0)
        reltup = reltup if (reltup and reltup > 0) else None
        # Believable only if the collector's live count lands in the right order of
        # magnitude. Tiny tables are exempt - the ratio is meaningless there anyway.
        usable = (reltup is None) or (reltup < 100) or (live >= reltup * 0.5)
        ratio = f"{dead / live:.3f}" if (usable and live > 0) else "계산불가"
        # PostgreSQL 14+ stores reltuples = -1 for "never vacuumed or analysed", which
        # is a DIFFERENT fact from "zero rows". Printing -1 as a row count would be a
        # lie in the same family as computing a ratio from a lost counter.
        est = f"{reltup:,}" if reltup else "미상"
        print(f"  {name[:28]:28} {est:>13} {live:>13,} "
              f"{dead:>12,} {ratio:>9} {avc or 0:>7}")
        print(f"    {'':26} last_autovacuum={av or 'never'}  "
              f"last_autoanalyze={aa or 'never'}  분석 후 변경 {modsa or 0:,}행  "
              f"크기 {human(totsize)}")
        if not usable:
            print(f"    {'':26} 🔴 카운터 신뢰 불가 (통계 live {live:,} vs 실제 ~{reltup:,}) "
                  f"— 이 테이블의 dead 비율/«never»는 읽지 말 것")
        out.append({"table": name, "reltuples": reltup, "n_live": live,
                    "n_dead": dead, "counters_usable": usable,
                    "autovacuum_count": avc, "last_autovacuum": str(av),
                    "total_bytes": totsize})
    snapshot["autovacuum"] = out

    hot = [o for o in out if o["counters_usable"] and o["n_dead"] > 100000]
    if hot:
        note("데드 튜플 10만 이상: " + ", ".join(f"{o['table']}({o['n_dead']:,})" for o in hot[:4])
             + ". 대량 적재의 UPDATE/UPSERT는 행마다 dead 튜플을 남기고, 그 뒤 autovacuum이 "
               "그것을 회수하는 동안 I/O를 먹는다 — 이것이 «적재 후 한동안 느리다»의 1번 후보다.")

    sub("테이블별 autovacuum 설정 override (reloptions)")
    rows = p.rows("""
        SELECT c.relname, c.reloptions
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r' AND c.reloptions IS NOT NULL
          AND n.nspname NOT IN ('pg_catalog', 'information_schema')
        ORDER BY 1
    """)
    if not rows:
        print("     override 없음 — 모든 테이블이 서버 전역 설정(0절)을 그대로 쓴다.")
    else:
        for name, opts in rows:
            print(f"     {name:32} {list(opts)}")


# ---------------------------------------------------------------------------
# 3. The outbox backlog
# ---------------------------------------------------------------------------
OUTBOX = "database_outbox"


def section_outbox(p):
    head(3, "OUTBOX 적체 (database_outbox)")
    if not p.has_relation(OUTBOX):
        print(f"     {OUTBOX} 테이블이 없다. (이 DB는 이 스택의 것이 아니거나 스키마가 다르다)")
        return

    sub("크기 — 힙 / 인덱스 / TOAST, 그리고 «부풀었는가»")
    r = p.one("""
        SELECT pg_relation_size(c.oid), pg_indexes_size(c.oid),
               coalesce(pg_total_relation_size(c.reltoastrelid), 0),
               pg_total_relation_size(c.oid), c.reltuples::bigint, c.relpages
        FROM pg_class c WHERE c.relname = :n AND c.relkind = 'r'
    """, n=OUTBOX)
    density = None
    # 🔴 THE EXACT COUNT COMES FIRST, AND THE ORDER IS THE FIX.
    #    This section used to compute page density from `pg_class.reltuples`, and
    #    on the very first run against a real database that check DID NOT FIRE on a
    #    table holding 7 rows across 8,668 pages (67.7 MB of heap for 7 rows). The
    #    reason is that PostgreSQL stores reltuples = -1 for "never vacuumed or
    #    analysed since the last truncate", the guard read `reltup > 0` as false,
    #    and the most bloated table in the database printed clean - the exact shape
    #    of the 2026-08-06 miss this section exists to prevent.
    #    The outbox is a QUEUE: in a healthy state it drains to near zero, so its
    #    count is cheap and exact, and the estimate is the WORSE number here. Count
    #    first, and only fall back to reltuples when the count could not be had.
    rows, timed_out = p.bounded(
        f"SELECT status, count(*) FROM {OUTBOX} GROUP BY status ORDER BY 2 DESC")
    exact_total = None if timed_out else (sum(n for _, n in rows) or 0)

    if r:
        heap, idx, toast, total, reltup, relpages = r
        reltup = reltup if (reltup and reltup > 0) else None
        # The number the density is computed from, and where it came from - printed,
        # because a density is meaningless without knowing which numerator made it.
        truth, src = ((exact_total, "count(*)") if exact_total is not None
                      else ((reltup, "reltuples~") if reltup else (None, "미상")))
        print(f"     힙 {human(heap):>12}   인덱스 {human(idx):>12}   "
              f"TOAST {human(toast):>12}   합계 {human(total):>12}")
        print(f"     행수 {(f'{truth:,}' if truth is not None else '미상')} ({src})"
              f"   페이지 {relpages or 0:,}")
        if truth is not None and relpages:
            density = truth / relpages
            print(f"     페이지 밀도 {density:.4f} 행/페이지  "
                  f"(8KB 한 페이지에 실제로 몇 행이 앉아 있는가)")
            print("     ↑ 이 값은 통계 수집기와 무관하다 — 카운터가 유실돼도 참이다.")
            if density < 1.0 and relpages > 128:
                note(f"{OUTBOX}가 페이지 밀도 {density:.4f}행/페이지로 부풀어 있다 "
                     f"({truth:,}행이 {relpages:,}페이지 = {human(heap)}를 쓴다). 회수되지 "
                     f"않은 공간이며, 이 테이블을 폴링하는 모든 쿼리가 그 빈 페이지를 함께 "
                     f"읽는다. 큐가 비어 있어도 사라지지 않는다 — 일반 VACUUM은 공간을 "
                     f"재사용 가능하게 만들 뿐 파일을 줄이지 않기 때문이다.")
        snapshot["outbox_size"] = {"heap": heap, "index": idx, "toast": toast,
                                   "total": total, "reltuples": reltup,
                                   "rows": truth, "rows_source": src,
                                   "relpages": relpages, "rows_per_page": density}

    sub("status별 건수")
    if timed_out:
        print(f"     [{BOUNDED_MS}ms 안에 세지 못했다 — 그 자체가 «이 테이블이 크다»는 사실이다]")
        print("     위의 추정 행수로 대신 읽을 것.")
        note(f"{OUTBOX}의 status별 count가 {BOUNDED_MS}ms 안에 끝나지 않았다. "
             f"부분 인덱스가 있는데도 그렇다면 힙 방문 비용(=블로트)이 원인일 가능성이 높다.")
    else:
        for status, n in rows:
            print(f"     {str(status or 'NULL'):12} {n:>12,}")
        print(f"     {'합계':12} {exact_total:>12,}   (정확한 count — 추정 아님)")
        snapshot["outbox_status"] = {str(s): n for s, n in rows}
        pending = next((n for s, n in rows if s == "PENDING"), 0)
        if pending > 1000:
            note(f"PENDING이 {pending:,}건 쌓여 있다. 워커가 못 따라가고 있다는 뜻이고, "
                 f"그동안 이 테이블은 계속 자라며 그것을 폴링하는 쿼리도 함께 느려진다.")

    sub("워커별 큐 깊이 (각 소비자가 얼마나 밀렸는가)")
    for label, where in [
        ("체인 워커 미처리 (processed_chain = false)", "processed_chain = false"),
        ("브로드캐스트 미확정 (SUCCESS인데 broadcast_at NULL)",
         "processed_chain = true AND status = 'SUCCESS' AND broadcast_at IS NULL"),
        ("FAILED 격리", "status = 'FAILED'"),
    ]:
        rows, to = p.bounded(f"""
            SELECT count(*), min(id),
                   EXTRACT(EPOCH FROM (now() - min(created_at)))::bigint
            FROM {OUTBOX} WHERE {where}
        """)
        if to or not rows:
            print(f"     {label:52} [시간 내 못 셈]")
            continue
        n, min_id, oldest = rows[0]
        print(f"     {label:52} {n or 0:>10,}"
              + (f"   가장 오래된 것 {age(oldest)} 전 (id={min_id})" if n else ""))
        if label.startswith("체인") and (n or 0) > 0 and (oldest or 0) > 600:
            note(f"체인 워커의 미처리 큐에서 가장 오래된 이벤트가 {age(oldest)}째 남아 있다. "
                 f"워커가 죽었거나 처리 속도가 유입 속도보다 느리다.")

    sub("가장 오래된 PENDING")
    rows, to = p.bounded(f"""
        SELECT id, event_type, table_name,
               EXTRACT(EPOCH FROM (now() - created_at))::bigint, created_at
        FROM {OUTBOX} WHERE status = 'PENDING' ORDER BY id ASC LIMIT 1
    """)
    if to:
        print("     [시간 내 찾지 못했다]")
    elif not rows:
        print("     PENDING 없음. (적체 없음)")
    else:
        i, et, tn, secs, ts = rows[0]
        print(f"     id={i}  {et} on {tn}  나이 {age(secs)}  ({ts})")
        snapshot["outbox_oldest_pending_sec"] = int(secs or 0)
        if (secs or 0) > 300:
            note(f"가장 오래된 PENDING이 {age(secs)}째 처리되지 않았다. 큐가 흐르지 않고 있다.")

    # -----------------------------------------------------------------------
    # 🔴 THE SHAPE QUESTION. `528dfcb` made this table POINT AT rows (a payload
    #    carrying `row_ids`) instead of CARRYING one row's values (a payload
    #    carrying `data`). The cost of a backlog is completely different between
    #    the two - a per-row payload is one row's full cell dict and TOASTs
    #    heavily; a collapsed payload names up to 1,000 row_ids and stands for
    #    1,000 rows. Counting events without knowing the shape gives a number
    #    that means nothing.
    #
    #    Detection mirrors the runtime discriminator exactly
    #    (`event_constants.is_collapsed_payload`: a list under key `row_ids`), so
    #    this report and the workers cannot disagree about what a row is.
    # -----------------------------------------------------------------------
    sub("행의 «모양» — 옛 모양(값을 싣는다) vs 새 모양(행을 가리킨다)  [528dfcb]")
    print("     새 모양(collapsed) = payload에 row_ids 리스트가 있다 → 이벤트 1건이 최대 1,000행을 대표")
    print("     옛 모양(per-row)   = payload에 data 딕셔너리가 있다 → 이벤트 1건이 정확히 1행")
    for label, order in [("최신 200건", "DESC"), ("가장 오래된 PENDING 200건", "ASC")]:
        where = "TRUE" if order == "DESC" else "status = 'PENDING'"
        rows, to = p.bounded(f"""
            SELECT
              count(*) AS n,
              count(*) FILTER (WHERE jsonb_typeof(payload::jsonb -> 'row_ids') = 'array') AS collapsed,
              count(*) FILTER (WHERE jsonb_typeof(payload::jsonb -> 'data') = 'object') AS per_row,
              coalesce(sum((payload::jsonb ->> 'row_count')::bigint)
                       FILTER (WHERE jsonb_typeof(payload::jsonb -> 'row_ids') = 'array'), 0) AS named_rows,
              coalesce(max(pg_column_size(payload)), 0) AS max_payload,
              coalesce(avg(pg_column_size(payload))::bigint, 0) AS avg_payload
            FROM (SELECT payload FROM {OUTBOX} WHERE {where}
                  ORDER BY id {order} LIMIT 200) s
        """)
        if to or not rows:
            print(f"     {label}: [표본을 읽지 못했다]")
            continue
        n, collapsed, per_row, named, mx, avg = rows[0]
        if not n:
            print(f"     {label}: 표본 없음")
            continue
        print(f"     {label}: {n}건 중 새 모양 {collapsed} · 옛 모양 {per_row} · "
              f"기타 {n - (collapsed or 0) - (per_row or 0)}")
        print(f"        payload 크기 평균 {human(avg)} / 최대 {human(mx)}"
              + (f"   새 모양이 대표하는 행 {named:,}개" if collapsed else ""))
        snapshot.setdefault("outbox_shape", {})[label] = {
            "n": n, "collapsed": collapsed, "per_row": per_row,
            "named_rows": named, "avg_payload": avg, "max_payload": mx}
        if per_row and collapsed:
            note(f"{label} 표본에 옛 모양과 새 모양이 «섞여» 있다 (옛 {per_row} / 새 {collapsed}). "
                 f"528dfcb 이전에 쌓인 행이 아직 남아 있다는 뜻이고, 적체 건수를 행수로 "
                 f"환산할 때 두 모양을 따로 세야 한다.")
        elif per_row and not collapsed:
            note(f"{label}이 전부 옛 모양(per-row)이다. 적체 N건 = 실제 N행이고, payload가 "
                 f"행 전체 값을 싣고 있어 TOAST와 워커 역직렬화 비용이 건수에 비례한다.")


# ---------------------------------------------------------------------------
# 4. Sizes and index usage
# ---------------------------------------------------------------------------
def section_sizes(p, limit=20):
    head(4, "크기 · 인덱스 (SIZES)")
    print("  모든 행수는 pg_class.reltuples 기반 «추정»이다(~ 표시). 정확한 count(*)를 안 쓰는")
    print("  이유는 그것 자체가 이 절보다 오래 걸리기 때문이다.")

    sub(f"가장 큰 테이블 {limit}개")
    rows = p.rows("""
        SELECT c.relname,
               pg_relation_size(c.oid), pg_indexes_size(c.oid),
               coalesce(pg_total_relation_size(c.reltoastrelid), 0),
               pg_total_relation_size(c.oid),
               c.reltuples::bigint, c.relpages
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind IN ('r', 'p')
          AND n.nspname NOT IN ('pg_catalog', 'information_schema')
        ORDER BY pg_total_relation_size(c.oid) DESC
        LIMIT :lim
    """, lim=limit)
    print(f"\n  {'테이블':30} {'힙':>12} {'인덱스':>12} {'TOAST':>11} {'합계':>12} {'~행수':>13}")
    print("  " + SUB)
    tables = []
    for name, heap, idx, toast, total, reltup, relpages in rows:
        print(f"  {name[:30]:30} {human(heap):>12} {human(idx):>12} {human(toast):>11} "
              f"{human(total):>12} {(f'{reltup:,}' if reltup and reltup > 0 else '미상'):>13}")
        tables.append({"table": name, "heap": heap, "index": idx, "toast": toast,
                       "total": total, "reltuples": reltup, "relpages": relpages})
    snapshot["tables"] = tables
    # 🔴 "미상" is not a blank, and it must not read as one. reltuples = -1 means
    #    "never vacuumed or analysed since the last truncate", so for these tables
    #    NO size-per-row and NO bloat judgement is possible from this section - and
    #    a table can be entirely empty space while printing a large heap here (the
    #    outbox in section 3 was exactly that: 7 rows over 67.7 MB). Name them.
    unknown = [t for t in tables
               if not (t["reltuples"] and t["reltuples"] > 0)
               and (t["total"] or 0) > 8 * 1024 * 1024]
    if unknown:
        note("행수 추정치가 아예 없는 8MB 초과 테이블: "
             + ", ".join(f"{t['table']} ({human(t['total'])})" for t in unknown[:5])
             + ". reltuples = -1 은 «truncate 이후 vacuum/analyze를 한 번도 안 했다»는 뜻이고, "
               "이런 테이블은 힙이 커도 그 안이 비어 있을 수 있다 — 크기만으로 판단하지 말 것 "
               "(3절의 정확한 count가 있는 테이블은 그쪽을 볼 것).")
    if tables:
        idx_heavy = [t for t in tables
                     if t["heap"] and t["index"] and t["index"] > t["heap"] * 1.5
                     and t["total"] > 50 * 1024 * 1024]
        if idx_heavy:
            note("인덱스가 힙보다 1.5배 이상 큰 테이블: "
                 + ", ".join(t["table"] for t in idx_heavy[:4])
                 + ". 읽기에 쓰이지 않는 인덱스라면 «쓰기»에서만 비용을 내고 있다 — 아래 스캔 수와 함께 볼 것.")

    sub("인덱스 스캔 횟수 (크기순) — 안 쓰이는데 쓰기 비용은 내는 인덱스가 여기서 드러난다")
    rows = p.rows("""
        SELECT s.relname, s.indexrelname, s.idx_scan, s.idx_tup_read, s.idx_tup_fetch,
               pg_relation_size(s.indexrelid), i.indisunique, i.indisprimary
        FROM pg_stat_user_indexes s
        JOIN pg_index i ON i.indexrelid = s.indexrelid
        ORDER BY pg_relation_size(s.indexrelid) DESC
        LIMIT 30
    """)
    print(f"\n  {'테이블':22} {'인덱스':34} {'스캔':>12} {'크기':>11}")
    print("  " + SUB)
    unused = []
    for rel, iname, scans, tread, tfetch, sz, uniq, prim in rows:
        tag = " [PK]" if prim else (" [UNIQUE]" if uniq else "")
        print(f"  {rel[:22]:22} {(iname or '')[:34]:34} {scans or 0:>12,} {human(sz):>11}{tag}")
        if (scans or 0) == 0 and not prim and not uniq and (sz or 0) > 8 * 1024 * 1024:
            unused.append((iname, sz))
    if unused:
        note("스캔 0회인 8MB 초과 인덱스: "
             + ", ".join(f"{n} ({human(s)})" for n, s in unused[:5])
             + ". 다만 스캔 수는 «통계 초기화 이후»의 누적이므로(0절 참조), 초기화가 최근이면 "
               "«안 쓰인다»가 아니라 «아직 안 쓰였다»일 수 있다. 삭제 판단은 초기화 시각을 보고 할 것.")

    sub("순차 스캔 vs 인덱스 스캔 (대량 적재 후 플래너가 뒤집혔는지의 단서)")
    rows = p.rows("""
        SELECT relname, seq_scan, seq_tup_read, idx_scan,
               CASE WHEN seq_scan > 0 THEN (seq_tup_read / seq_scan)::bigint ELSE 0 END
        FROM pg_stat_user_tables
        WHERE seq_scan > 0
        ORDER BY seq_tup_read DESC NULLS LAST
        LIMIT 12
    """)
    print(f"\n  {'테이블':30} {'seq스캔':>10} {'seq로 읽은 행':>16} {'회당 행':>12} {'idx스캔':>12}")
    print("  " + SUB)
    for name, ss, str_, is_, avg in rows:
        print(f"  {name[:30]:30} {ss or 0:>10,} {str_ or 0:>16,} {avg or 0:>12,} {is_ or 0:>12,}")
        if (avg or 0) > 1000000:
            note(f"{name}: 순차 스캔 1회당 평균 {avg:,}행을 읽고 있다. 이 크기에서 순차 스캔은 "
                 f"인덱스가 없거나 플래너가 인덱스를 버린 것이다.")


# ---------------------------------------------------------------------------
# 4b. WHERE DOES THE SECOND GO? - the ladder that separates three causes
# ---------------------------------------------------------------------------
# The report this answers: "every fetch takes over a second, uniformly, and the
# browser says >90% of it is Waiting (TTFB)". TTFB is server think-time, so the
# second is spent inside the process. Three things can spend it, and until they
# are separated any fix is a guess:
#
#   (1) waiting for an anyio THREAD TOKEN   - every `def` handler needs one, and
#       so does every 64 KB chunk of every static file. The limiter is 40.
#   (2) waiting for a DATABASE CONNECTION   - pool_size 20 + max_overflow 10 = 30.
#       Taken INSIDE the thread, so a handler blocked here is holding a token.
#   (3) the QUERY itself being slow         - bloat, a plan flip, cold cache.
#
# The discrimination is structural rather than statistical: each rung of the
# ladder adds exactly ONE of those costs to the rung below it, so a jump between
# two adjacent rungs names its own cause.
#
#   R0  GET /health          async def  -> NO token. Takes a pooled connection on
#                            the asyncio executor and reports its own DB latency
#                            in the response body.
#   S1  small static asset   no handler code, no DB, ~2 token acquisitions.
#   S2  large static asset   no handler code, no DB, 2 + size/64KB acquisitions.
#                            S2 - S1 is therefore an almost pure measurement of
#                            what ONE token acquisition costs right now.
#   R1  sync def, no get_db  + one token + handler code, still no connection.
#   R2  sync def + get_db,   + one connection checkout + a one-row indexed read.
#       limit=1
#   R3/R4 same, limit=200 /  + query work only. The endpoint, the token and the
#       limit=1000             connection are identical to R2 by construction.
#
# Read it as differences, not as absolutes:
#   S2 - S1 large    -> (1). Tokens are contended. Nothing else is in that path.
#   R1 - S1 large    -> a fixed cost inside handler code (config file I/O, path
#                       resolution on a slow share). NOT any of the three above,
#                       and worth naming because it is invisible to all of them.
#   R2 - R1 large    -> (2). Connection checkout.
#   R4 - R2 large    -> (3). Query work, and it should track the direct-SQL row
#                       opposite it.
#   All rungs equally slow, R0 fast -> a per-request constant that lands after the
#                       async path and before the handler body.
#
# 🔴 R0 IS THE LOAD-BEARING CONTROL, and it is a control precisely because
#    `/health` is `async def` yet still opens a pooled connection. Fast /health
#    therefore falsifies (2) on its own: if the pool were exhausted, the health
#    probe would block on it and the handler would report `db.status = timeout`
#    after its own 2 s bound. This script prints that field verbatim instead of
#    inferring it.
_LADDER_REPS = 7
_LADDER_CONCURRENCY = 4


def _get(base, path, timeout=60, headers=None):
    """One GET on a FRESH connection. Returns (ms, status, nbytes, body).

    Fresh connection per call on purpose: a shared keep-alive session serialises
    requests client-side, and the concurrency probe below would then measure its
    own queue instead of the server's.
    """
    import urllib.request
    import urllib.error
    h = {"X-Source": "slow_probe"}
    if headers:
        h.update(headers)
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(base + path, method="GET", headers=h)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            return (time.perf_counter() - t0) * 1000, r.status, len(body), body
    except urllib.error.HTTPError as e:
        try:
            body = e.read()
        except Exception:
            body = b""
        return (time.perf_counter() - t0) * 1000, e.code, len(body), body
    except Exception as e:
        return ((time.perf_counter() - t0) * 1000,
                f"ERR {type(e).__name__}", 0, b"")


def _stat(samples):
    """min / p50 / max / flatness for a list of latencies."""
    if not samples:
        return None
    s = sorted(samples)
    lo, mid, hi = s[0], s[len(s) // 2], s[-1]
    # Spread relative to the median. A queue that is genuinely contended is
    # bursty; a fixed per-request cost is not. The operator is asked for a
    # UNIFORM slowness, so this number is evidence in its own right.
    spread = (hi - lo) / mid if mid > 0 else 0.0
    return {"min": lo, "p50": mid, "max": hi, "spread": spread, "n": len(s)}


def _fmt(st):
    if not st:
        return "         -"
    return (f"{st['min']:8.1f} /{st['p50']:8.1f} /{st['max']:8.1f} ms"
            f"   퍼짐 {st['spread']:4.2f}")


def _flag_tail(label, st):
    """Raise a note when a rung's WORST sample dwarfs its median.

    🔴 A median hides the thing being hunted. Under an injected token saturation
    this ladder printed `/api/effort/config  3.9 / 27.7 / 60016.0 ms` - a request
    that waited a full minute for a thread token, sitting invisibly behind a
    healthy-looking p50. Queueing is exactly the failure that shows up in the tail
    first, so the tail gets its own alarm rather than being left for the reader.
    """
    if not st or st["p50"] <= 0:
        return
    if st["max"] >= 1000 and st["max"] / st["p50"] >= 10:
        note(f"{label}: 중간값은 {st['p50']:.0f}ms인데 최악은 {st['max']:,.0f}ms다 "
             f"({st['max'] / st['p50']:.0f}배). 같은 요청이 대부분 빠르고 이따금 "
             f"통째로 멈춘다면 그것은 «느린 쿼리»가 아니라 «줄서기»다 — 자원 하나를 "
             f"기다렸다는 뜻이고, 어느 자원인지는 이 칸이 무엇을 더했는지가 말한다.")


def _ok(status):
    """Did this rung actually answer? Anything else is not a measurement.

    🔴 A rung that 404s or 500s still produces a LATENCY, and a fast error is the
    fastest number on the ladder. Storing it would make every delta above and
    below that rung a fiction - and the fiction reads as good news, because a
    shadowed `/health` route answering a 200-HTML catch-all or a 500 in 3 ms
    lowers the baseline the whole ladder is measured against. So a rung enters
    `_ladder["rungs"]` only on 200; otherwise the verdict below reports it as
    미측정 rather than as fast.
    """
    return isinstance(status, int) and status == 200


def _rung(base, path, reps=_LADDER_REPS, timeout=60):
    out, status, nbytes, body = [], None, 0, b""
    for _ in range(reps):
        ms, st, n, b = _get(base, path, timeout=timeout)
        out.append(ms)
        status, nbytes, body = st, n, b
    return _stat(out), status, nbytes, body


def _discover_assets(base):
    """Find the smallest and largest /assets/* the document actually pulls.

    Discovered rather than hardcoded: the filenames carry a build hash and change
    on every client build, and a probe that 404s would report a fast static path
    while measuring nothing.

    🔴 THE TIMEOUT HERE IS LOAD-BEARING, AND THIS IS WHY IT IS 600 SECONDS.
    An earlier version used the 60 s default. Under an injected thread-token
    saturation - the exact condition the static rung exists to detect - `GET /`
    exceeded 60 s, this function returned "nothing found", and the whole S1/S2
    rung was skipped with the message "the client is not built". The instrument
    went blind at precisely the moment it mattered AND handed the operator a false
    reason. Measured: 45 held tokens, limiter pinned at 40/40 for 4 minutes,
    static rung absent from the report.

    Returns (small, large, sizes, why) - `why` is a human-readable failure reason
    so a missing rung can never again be reported as a missing client build.
    """
    import re
    ms, status, _n, body = _get(base, "/", timeout=600)
    if not isinstance(status, int) or status != 200 or not body:
        return None, None, {}, (f"GET / 가 {ms:.0f}ms 만에 [{status}] 로 끝났다 "
                                f"(본문 {_n}B). 문서 자체를 못 받았으므로 자산 목록을 "
                                f"얻을 수 없다 — 이것 자체가 «정적 경로가 막혀 있다»는 "
                                f"1차 증거다.")
    html = body.decode("utf-8", "replace")
    paths_found = sorted(set(re.findall(r'["\'](/assets/[A-Za-z0-9_.\-]+)["\']', html)))
    if not paths_found:
        return None, None, {}, (f"GET / 는 {ms:.0f}ms 에 200으로 왔지만 본문에 "
                                f"/assets/ 링크가 없다 (클라이언트 빌드 산출물이 "
                                f"아니거나 다른 문서가 서빙되고 있다).")
    sizes, failures = {}, []
    for pth in paths_found:
        ms2, st2, n2, _b2 = _get(base, pth, timeout=600)
        if isinstance(st2, int) and st2 == 200 and n2 > 0:
            sizes[pth] = n2
        else:
            failures.append(f"{pth} -> [{st2}] {ms2:.0f}ms")
    if not sizes:
        return None, None, {}, ("문서에서 찾은 자산을 하나도 받지 못했다: "
                                + "; ".join(failures[:3]))
    small = min(sizes, key=lambda k: sizes[k])
    large = max(sizes, key=lambda k: sizes[k])
    return small, large, sizes, None


def section_where_the_second_goes(p, http_base, tables):
    head("4b", "1초는 어디서 오는가 — 계층 분해 (WHERE DOES THE SECOND GO)")
    if not http_base:
        print("  --http BASE_URL 을 주지 않아 이 절은 건너뛴다. 이 절이 세 후보")
        print("  (스레드 토큰 / DB 커넥션 / 쿼리 자체)를 가르는 유일한 절이므로,")
        print("  «모든 요청이 1초» 증상을 조사 중이라면 반드시 --http 와 함께 다시 돌릴 것.")
        print("    예) --http http://127.0.0.1:8080")
        _ladder["why_not"] = "--http 없이 실행 (사다리 자체를 안 돌렸다)"
        return

    base = http_base.rstrip("/")
    print("  브라우저가 «Waiting(TTFB)»라고 부르는 시간은 서버가 생각한 시간이다.")
    print("  아래 사다리는 한 칸 오를 때마다 비용을 «정확히 하나씩» 더한다.")
    print("  그래서 어느 칸에서 뛰는지가 곧 원인의 이름이다.")
    print(f"  각 칸을 {_LADDER_REPS}회씩 잰다 (연결은 매번 새로 연다).")

    lad = {}

    # ---- R0: async def, no thread token. The control. -----------------------
    sub("A. R0 — GET /health  (async def · 스레드 토큰 불필요 · 풀 커넥션은 사용)")
    st0, status0, _n0, body0 = _rung(base, "/health")
    print(f"     R0 /health                    {_fmt(st0)}  [{status0}]")
    if _ok(status0):
        lad["R0_health"] = st0
    _ladder["r0_status"] = status0
    _flag_tail("R0 /health", st0)
    health_db = None
    try:
        hj = json.loads(body0.decode("utf-8", "replace"))
        # `health.compute_health` nests it: checks.database.{status,latency_ms}.
        # NOT the top-level `status` - that one also goes 503 for a stale heartbeat
        # or an old config backup, neither of which says anything about the pool.
        health_db = ((hj.get("checks") or {}).get("database") or {}) \
            if isinstance(hj, dict) else {}
        print(f"     └ 응답 본문의 checks.database: status={health_db.get('status')} "
              f"latency_ms={health_db.get('latency_ms')}")
        print(f"       (전체 status={hj.get('status')} — 이것은 하트비트·백업 나이로도 "
              f"503이 되므로 풀 상태의 근거가 아니다)")
        snapshot.setdefault("ladder", {})["health_db"] = health_db
        _ladder["r0_body_json"] = True
    except Exception:
        print("     └ 본문을 JSON으로 읽지 못했다 (정적 catch-all이 HTML을 200으로 "
              "돌려준 것은 아닌지 확인 — /health 라우트가 그늘에 가려졌을 수 있다).")
        # A 200 that is not the health document means R0 may not be the async,
        # tokenless route the ladder assumes - it may be a static file wearing
        # /health's URL. The timing is still real, so the rung stays; but the
        # verdict must not present a possibly-static baseline as the DB control.
        _ladder["r0_body_json"] = False

    if health_db and health_db.get("status") == "ok":
        print("     ⇒ /health 가 커넥션을 «얻어서» 왕복을 마쳤다. 이 한 줄이 «풀 고갈»을")
        print("       반증한다 — 풀이 비었다면 여기서 막혀 status=timeout 이 찍힌다.")
    elif health_db and health_db.get("status") == "timeout":
        note("/health 의 DB 프로브가 2초 안에 답하지 못했다(status=timeout). "
             "커넥션 풀 또는 DB 자체가 막혀 있다는 뜻이다 — 후보 (2)/(3) 쪽이다.")

    # ---- S1/S2: static. No handler code, no DB. Pure token amplifier. -------
    sub("B. S1/S2 — 정적 파일  (핸들러 코드 없음 · DB 없음 · 토큰만 소비)")
    print("     정적 응답은 64KB 청크마다 스레드 토큰을 한 번씩 빌린다(starlette FileResponse).")
    print("     그래서 큰 파일과 작은 파일의 «차이»가 곧 토큰 한 번의 값이다.")
    small, large, sizes, why = _discover_assets(base)
    if not small:
        print(f"     정적 칸을 재지 못했다 — 이유: {why}")
        note("정적(S1/S2) 칸을 재지 못했다. 이 칸은 «토큰 경합»을 가리는 유일한 칸이므로, "
             "빠진 채로는 후보 (1)을 긍정도 부정도 할 수 없다. 위에 적힌 이유를 먼저 볼 것.")
    else:
        n_small, n_large = sizes[small], sizes[large]
        st1, sts1, _a, _b = _rung(base, small)
        st2, sts2, _c, _d = _rung(base, large, timeout=180)
        chunks_small = 2 + max(0, -(-n_small // 65536))
        chunks_large = 2 + max(0, -(-n_large // 65536))
        print(f"     S1 {small[-38:]:38} {_fmt(st1)}  [{sts1}] {human(n_small)}"
              f"  토큰~{chunks_small}회")
        print(f"     S2 {large[-38:]:38} {_fmt(st2)}  [{sts2}] {human(n_large)}"
              f"  토큰~{chunks_large}회")
        if _ok(sts1):
            lad["S1_small_static"] = st1
        if _ok(sts2):
            lad["S2_large_static"] = st2
        _flag_tail(f"S1 {small}", st1)
        _flag_tail(f"S2 {large}", st2)
        if st1 and st2 and chunks_large > chunks_small:
            per_token = (st2["p50"] - st1["p50"]) / (chunks_large - chunks_small)
            print(f"     ⇒ 토큰 1회 획득에 드는 시간 ≈ {per_token:.2f} ms"
                  f"   (S2−S1 를 청크 수 차이로 나눈 값)")
            snapshot.setdefault("ladder", {})["per_token_ms"] = per_token
            if per_token > 5.0:
                note(f"정적 파일의 토큰 1회 획득이 {per_token:.1f}ms다. 정적 경로에는 "
                     f"핸들러 코드도 DB도 없으므로 이 값은 «스레드풀 토큰 경합» 말고는 "
                     f"설명이 없다 — 후보 (1)이 살아 있다.")
            else:
                note(f"정적 파일의 토큰 1회 획득이 {per_token:.2f}ms다(사실상 0). "
                     f"스레드풀 토큰은 «지금» 경합하고 있지 않다 — 후보 (1)은 이 측정에서 "
                     f"살아남지 못한다. 느림은 토큰 대기 이후 구간에 있다.")

        # ---- The same static file, CONCURRENTLY. ------------------------------
        # 🔴 THIS PROBE EXISTS BECAUSE THE SEQUENTIAL ONE ABOVE MISSED A REAL STALL.
        # Measured here on 2026-08-11: with the thread limiter pinned at 40/40 and
        # 6-11 tasks queued for four minutes straight, the SEQUENTIAL large-asset
        # fetch above returned in 14.9 ms - no contention visible at all. The same
        # asset fetched by several clients AT ONCE, under the same injected fault,
        # took 11,021 ms. One arrival at a time can slip through a queue that
        # several simultaneous arrivals cannot, so a ladder that only ever probes
        # sequentially can report a healthy static path while the users' browsers -
        # which open six connections at once - are stalled. Two measurements of
        # mine disagreed on this point; rather than pick one, the script now takes
        # both and prints them side by side.
        if large:
            import threading as _th0
            got0, bad0 = [], []
            _lk0 = _th0.Lock()

            def _one_asset():
                ms_a, _st, _n, _b = _get(base, large, timeout=600)
                with _lk0:
                    (got0 if _ok(_st) else bad0).append(ms_a if _ok(_st) else _st)

            ths0 = [_th0.Thread(target=_one_asset, daemon=True)
                    for _ in range(_LADDER_CONCURRENCY)]
            for t in ths0:
                t.start()
            for t in ths0:
                t.join()
            conc_static = _stat(got0)
            print(f"     S2 를 동시 {_LADDER_CONCURRENCY}개            {_fmt(conc_static)}"
                  f"   ← 브라우저는 한 번에 6개를 연다"
                  + (f"   [실패 {len(bad0)}/{_LADDER_CONCURRENCY}: {bad0[0]}]"
                     if bad0 else ""))
            if got0:
                lad["S2_concurrent"] = conc_static
            snapshot.setdefault("ladder", {})["static_concurrent_p50_ms"] = \
                conc_static["p50"] if conc_static else None
            if st2 and conc_static and st2["p50"] > 0:
                ratio_s = conc_static["p50"] / st2["p50"]
                print(f"     ⇒ 동시/순차 = {ratio_s:.2f}배")
                if ratio_s > 3.0:
                    note(f"큰 정적 파일이 순차 {st2['p50']:.0f}ms → 동시 "
                         f"{_LADDER_CONCURRENCY}개일 때 {conc_static['p50']:,.0f}ms로 "
                         f"{ratio_s:.1f}배가 됐다. 정적 경로에는 핸들러도 DB도 없다 — "
                         f"동시 도착만으로 이렇게 늘어나는 자원은 스레드풀 토큰뿐이다. "
                         f"후보 (1)이 살아 있고, 순차 측정만으로는 보이지 않는다.")

    # ---- R1: sync def, no get_db. Token + handler code, no connection. ------
    sub("C. R1 — sync def · Depends(get_db) 없음  (토큰 1회 + 핸들러 코드, 커넥션 없음)")
    print("     선언 근거: server/main.py 의 라우트 중 sync def 이면서 get_db 를 받지 않는 것.")
    r1_candidates = [
        ("/api/effort/config", "get_effort_config"),
        ("/api/maps/paint-rules", "get_map_paint_rules"),
        ("/map-presets", "get_map_presets"),
        ("/tables", "list_tables"),
    ]
    best_r1 = None
    for pth, fname in r1_candidates:
        st, sts, n, _b = _rung(base, pth)
        ok = isinstance(sts, int) and sts == 200
        print(f"     R1 {pth:34} {_fmt(st)}  [{sts}] {human(n)}  ({fname})")
        if ok:
            _flag_tail(f"R1 {pth}", st)
        if ok and st and (best_r1 is None or st["p50"] < best_r1[1]["p50"]):
            best_r1 = (pth, st)
    if best_r1:
        lad["R1_sync_nodb"] = best_r1[1]

    # ---- R2/R3/R4: sync def + get_db, identical except row count. -----------
    sub("D. R2/R3/R4 — sync def + Depends(get_db)  (+커넥션, 그리고 행 수만 다르다)")
    print("     같은 라우트를 limit 만 바꿔 세 번 부른다. 토큰도 커넥션도 동일하므로,")
    print("     세 값의 «차이»는 오직 쿼리·직렬화 작업량이다.")
    tbl = tables[0] if tables else None
    if not tbl:
        print("     테이블 목록이 없어 이 칸은 건너뛴다.")
    else:
        for t in tables[:6]:
            st, sts, n, _b = _rung(base, f"/tables/{t}/data?limit=1", reps=3)
            if isinstance(sts, int) and sts == 200 and n > 0:
                tbl = t
                break
        print(f"     대상 테이블: {tbl}")
        for label, lim in (("R2", 1), ("R3", 200), ("R4", 1000)):
            st, sts, n, _b = _rung(base, f"/tables/{tbl}/data?limit={lim}",
                                   reps=max(3, _LADDER_REPS // 2), timeout=180)
            print(f"     {label} /tables/{tbl[:18]}/data?limit={lim:<5} {_fmt(st)}"
                  f"  [{sts}] {human(n)}")
            if _ok(sts):
                lad[f"{label}_sync_db_limit{lim}"] = st
            _flag_tail(f"{label} /tables/{tbl}/data?limit={lim}", st)

    # ---- Direct SQL: the same work, with no server in the way ---------------
    sub("E. 같은 일을 스크립트 자신의 커넥션으로 — 서버를 빼고 잰 값")
    print("     여기가 빠른데 위(D)가 느리면, 느린 것은 «쿼리»가 아니다.")
    if tbl:
        for lim in (1, 200, 1000):
            t0 = time.perf_counter()
            rows, timed_out = p.bounded(
                f'SELECT * FROM "{tbl}" ORDER BY row_id LIMIT :lim', ms=20000, lim=lim)
            ms = (time.perf_counter() - t0) * 1000
            print(f"     직접 SQL  LIMIT {lim:<5}            {ms:8.1f} ms"
                  f"   {len(rows)}행{'  (시간초과)' if timed_out else ''}")
            snapshot.setdefault("ladder", {})[f"direct_sql_limit{lim}_ms"] = ms

    # ---- Contention: does concurrency multiply the wait? ---------------------
    sub(f"F. 동시성 — 같은 요청을 {_LADDER_CONCURRENCY}개 동시에")
    print("     줄을 서고 있다면 동시 요청은 서로를 기다려 «배수»로 늘어난다.")
    print("     고정 비용이라면 거의 그대로다. 증상이 «균일»하다니, 이 구분이 중요하다.")
    if tbl:
        import threading as _th
        got, bad = [], []
        _lk = _th.Lock()

        def _one():
            ms, sts, n, _b = _get(base, f"/tables/{tbl}/data?limit=1", timeout=180)
            with _lk:
                (got if _ok(sts) else bad).append(ms if _ok(sts) else sts)

        solo, _s, _n, _b = _rung(base, f"/tables/{tbl}/data?limit=1", reps=3)
        ths = [_th.Thread(target=_one, daemon=True) for _ in range(_LADDER_CONCURRENCY)]
        for t in ths:
            t.start()
        for t in ths:
            t.join()
        conc = _stat(got)
        print(f"     단독 1개                       {_fmt(solo)}")
        print(f"     동시 {_LADDER_CONCURRENCY}개                       {_fmt(conc)}"
              + (f"   [실패 {len(bad)}/{_LADDER_CONCURRENCY}: {bad[0]}]" if bad else ""))
        # The solo/concurrent PAIR is what the verdict's R2→R2동시 step reads.
        # Both are the same route at the same limit, taken in the same run, so the
        # difference between them is concurrency and nothing else. R2 above is a
        # separate sample of the same endpoint; pairing across the two would mix
        # measurement windows.
        if _ok(_s):
            lad["R2_solo"] = solo
            if got:
                lad["R2_concurrent"] = conc
        if solo and conc and solo["p50"] > 0:
            ratio = conc["p50"] / solo["p50"]
            print(f"     ⇒ 동시/단독 = {ratio:.2f}배")
            snapshot.setdefault("ladder", {})["concurrency_ratio"] = ratio
            if ratio > 2.0:
                note(f"동시 {_LADDER_CONCURRENCY}개가 단독의 {ratio:.1f}배로 늘었다. "
                     f"요청들이 서로를 기다린다 — 어딘가에서 직렬화되고 있다.")
            else:
                note(f"동시 {_LADDER_CONCURRENCY}개가 단독의 {ratio:.1f}배다. 이 부하에서는 "
                     f"직렬화가 보이지 않는다 — 1초가 «대기»라면 이 스크립트가 만든 부하보다 "
                     f"훨씬 큰 동시성이 이미 밖에서 걸려 있다는 뜻이다.")

    snapshot.setdefault("ladder", {})["rungs"] = {
        k: v for k, v in lad.items() if v}

    # Hand the readings to the closing verdict. `ran` is true as soon as ANY rung
    # answered - a ladder that took one measurement is a partial ladder, not an
    # absent one, and those two have to end up as different verdicts.
    _ladder["rungs"] = {k: v for k, v in lad.items() if v}
    _ladder["health_db"] = health_db
    _ladder["ran"] = bool(_ladder["rungs"])
    if not _ladder["ran"]:
        _ladder["why_not"] = (
            f"{base} 에서 한 칸도 200을 받지 못했다 (R0 /health → [{_ladder['r0_status']}])")

    # ---- The reading guide, printed with the numbers it refers to -----------
    sub("G. 읽는 법 — 어느 칸에서 뛰었나")
    r0 = lad.get("R0_health")
    s1 = lad.get("S1_small_static")
    s2 = lad.get("S2_large_static")
    r1 = lad.get("R1_sync_nodb")
    r2 = lad.get("R2_sync_db_limit1")
    r4 = lad.get("R4_sync_db_limit1000")

    def d(a, b):
        if not a or not b:
            return None
        return b["p50"] - a["p50"]

    steps = [
        ("R0 → S1  (토큰 획득이 생김)", d(r0, s1),
         "여기서 뛰면 = 스레드 토큰 대기 (후보 1)"),
        ("S1 → S2  (토큰 획득이 여러 번)", d(s1, s2),
         "여기서 뛰면 = 스레드 토큰 대기 (후보 1) — 배수로 확인"),
        ("S1 → R1  (핸들러 코드가 생김)", d(s1, r1),
         "여기서 뛰면 = 핸들러 안의 고정 비용 (설정 파일 I/O 등). 세 후보 어디도 아니다"),
        ("R1 → R2  (커넥션 체크아웃이 생김)", d(r1, r2),
         "여기서 뛰면 = DB 커넥션 대기 (후보 2)"),
        ("R2 → R4  (행 1개 → 1000개)", d(r2, r4),
         "여기서 뛰면 = 쿼리·직렬화 작업량 (후보 3)"),
    ]
    for label, delta, meaning in steps:
        if delta is None:
            print(f"     {label:34} {'측정 안 됨':>12}   {meaning}")
        else:
            print(f"     {label:34} {delta:+10.1f} ms   {meaning}")
    print()
    print("     🔴 이 표는 «판정»이 아니라 «어느 칸에서 뛰었나»다. 가장 큰 양수 한 칸이")
    print("        원인의 이름이고, 모든 칸이 작은데 R0부터 이미 1초라면 원인은 이 사다리")
    print("        바깥(프로세스 앞단)에 있다.")
    print("     (이 표를 한 줄로 접은 «판정»이 보고서 맨 끝에 있다.)")


# ---------------------------------------------------------------------------
# 4c. THE ONE LINE - the ladder folded into something that survives a phone call
# ---------------------------------------------------------------------------
# WHY THIS EXISTS: the production box does not permit copying output off it.
# The operator reads the screen and re-types by hand, and every number that
# crosses that gap can be mistyped or skipped. So the report has to END in one
# line that already contains the answer.
#
# FOUR RULES, each of which is a specific way a line like this usually lies:
#
#   1. NAME THE RUNG, not a category. 「DB 커넥션」 on its own cannot be checked
#      by whoever receives it. 「R1→R2 +842ms」 can: R1 and R2 differ by exactly
#      one cost, so the name carries its own reasoning.
#   2. INCONCLUSIVE MUST NOT RENDER AS HEALTHY. 「사다리를 못 돌렸다」,
#      「일부만 쟀다」 and 「다 쟀는데 아무 칸도 안 뛰었다」 are three different
#      answers and get three different words - 판정불가 / 부분측정 / 점프 없음.
#      🔴 THIS SCRIPT HAS ALREADY MADE EXACTLY THIS MISTAKE ONCE: under an
#      injected token saturation `_discover_assets` timed out and the report
#      announced 「클라이언트가 빌드되지 않았다」 - a confident wrong reason
#      produced by the very fault it was built to detect. A verdict that renders
#      a blind run as a clean run repeats that at the top of the page.
#   3. TWO JUMPS ARE REPORTED AS TWO. Silently taking the larger invents a
#      ranking the ladder does not support: each step adds one cost, and nothing
#      in the structure says the bigger delta is the one to fix first.
#   4. CARRY THE SIZE, not only the name, so the reader can sanity-check the
#      claim without the table it was folded from.
#
# The verdict names a STEP (a pair of rungs), because a step is what has a cause;
# a single rung only has a total.
JUMP_MS = 150.0
# A rung at or above this is "slow" in the sense the report is about ("every
# fetch takes over a second"). Used ONLY to keep two no-jump readings apart:
# 「아무 칸도 안 뛰었고 전부 빨랐다」(증상 미재현 - the ladder did not reproduce
# it) versus 「아무 칸도 안 뛰었는데 첫 칸부터 느리다」(원인이 사다리 바깥).
# A single "no jump" would merge those two into one misleading sentence.
SLOW_MS = 300.0

# from-rung, to-rung, and the ONE cost that step adds. The cause text is the
# step's definition (see the 4b header), not an inference drawn from the number.
_STEPS = [
    ("R0→S1",     "R0_health",          "S1_small_static",      "스레드토큰"),
    ("S1→S2",     "S1_small_static",    "S2_large_static",      "스레드토큰(다회)"),
    ("S2→S2동시", "S2_large_static",    "S2_concurrent",        "스레드토큰(동시도착)"),
    ("S1→R1",     "S1_small_static",    "R1_sync_nodb",         "핸들러고정비"),
    ("R1→R2",     "R1_sync_nodb",       "R2_sync_db_limit1",    "DB커넥션"),
    ("R2→R4",     "R2_sync_db_limit1",  "R4_sync_db_limit1000", "쿼리·직렬화"),
    ("R2→R2동시", "R2_solo",            "R2_concurrent",        "동시경합(자원미상)"),
]

# EVERY rung this file records, in ladder order, with the name the verdict says
# out loud. One list, so the digest's positions and the verdict's rung names
# cannot drift apart - and so that "전 칸" can only ever be said after counting
# against the same list the rungs were stored into.
_RUNG_LABELS = [
    ("R0_health", "R0"),
    ("S1_small_static", "S1"),
    ("S2_large_static", "S2"),
    ("S2_concurrent", "S2동시"),
    ("R1_sync_nodb", "R1"),
    ("R2_sync_db_limit1", "R2"),
    ("R4_sync_db_limit1000", "R4"),
    ("R2_solo", "R2단독"),
    ("R2_concurrent", "R2동시"),
]
# R2단독 is section F's own sample of the same route as R2. It is a rung for the
# purpose of the R2→R2동시 step, but it would spend a digest character restating
# a magnitude the digest already carries, so it is left out of the digest only.
_DIGEST_SKIP = {"R2_solo"}
_DIGEST_ORDER = [k for k, _ in _RUNG_LABELS if k not in _DIGEST_SKIP]
_DIGEST_LEGEND = ",".join(lbl for k, lbl in _RUNG_LABELS if k not in _DIGEST_SKIP)
_HEX = "0123456789ABCDEF"


def _digest(rungs):
    """Twelve characters that rebuild the whole ladder to within a factor of two.

    `L:` + eight rung characters + `-` + one check character, e.g. `L:3348A9C9-B`.

    Each rung character is ``round(log2(p50_ms))`` in hex, so the value is the
    magnitude and nothing else - `A` is about a second, `3` is about 8 ms. That
    resolution is deliberate: a jump is a factor of ten or more, so factor-of-two
    buckets are enough to RE-DERIVE the verdict from the digest alone, while
    being short enough to dictate. Reading five exact numbers off a screen is the
    thing this is replacing, not something to reproduce in a shorter font.

    Three properties make a mis-transcription visible rather than plausible:
      * `X` marks an unmeasured rung, and a measured rung is clamped to 1..15, so
        a `0` anywhere in a received digest is itself proof of a typo.
      * the `-` sits at a fixed position; if it is not the 11th character after
        `L:`, a character was dropped or added.
      * the check character is a POSITION-WEIGHTED sum mod 16, which catches
        every single-character error and every adjacent transposition of two
        unequal values - a plain sum would miss the transposition, and a
        transposition here would rename the rung that jumped.
    """
    vals, chars = [], []
    for key in _DIGEST_ORDER:
        st = rungs.get(key)
        if not st:
            vals.append(0)
            chars.append("X")
            continue
        v = min(15, max(1, int(round(math.log2(max(st["p50"], 1.0))))))
        vals.append(v)
        chars.append(_HEX[v])
    chk = sum((i + 1) * v for i, v in enumerate(vals)) % 16
    return "L:" + "".join(chars) + "-" + _HEX[chk]


def _verdict():
    """`(verdict_line, digest_line_or_None)` - see the rules above.

    A `None` digest is itself information: it is returned only when nothing was
    measured, so the absence of the second line means 판정불가 even if the first
    line was garbled in transit.
    """
    rungs = _ladder.get("rungs") or {}
    if not _ladder.get("ran") or not rungs:
        why = _ladder.get("why_not") or "사다리 미실행 (사유 불명)"
        return f"판정불가 — {why} | 잰 칸 0개 = 원인 지목 불가", None

    jumps, measured, missing = [], [], []
    for name, a, b, cause in _STEPS:
        sa_, sb_ = rungs.get(a), rungs.get(b)
        if not sa_ or not sb_:
            missing.append(name)
            continue
        measured.append(name)
        delta = sb_["p50"] - sa_["p50"]
        if delta >= JUMP_MS:
            jumps.append((name, delta, sa_["p50"], sb_["p50"], cause))

    total, done = len(_STEPS), len(measured)
    worst = max(st["p50"] for st in rungs.values())
    r0 = rungs.get("R0_health")

    if jumps:
        if len(jumps) == 1:
            nm, d, a_ms, b_ms, cz = jumps[0]
            head = f"점프 {nm} +{d:,.0f}ms ({a_ms:,.0f}→{b_ms:,.0f}) = {cz}"
        else:
            # Rule 3. Ladder order, never sorted by size: sorting is the ranking
            # this refuses to invent.
            head = (f"점프 {len(jumps)}곳 — "
                    + " · ".join(f"{nm} +{d:,.0f}ms={cz}"
                                 for nm, d, _a, _b, cz in jumps)
                    + " (전부 해당·순위 아님)")
    elif missing:
        head = (f"부분측정 {done}/{total}칸 — 잰 칸엔 점프 없음, "
                f"미측정 {','.join(missing)} → 단정 불가")
    elif worst < SLOW_MS:
        head = f"점프 없음 · 전 칸 ≤{worst:,.0f}ms → 이번 실행에선 증상 미재현"
    else:
        # No step jumped, yet something is slow. Name WHICH rungs, never "전 칸"
        # by default: a slow R0 with everything above it fast, and a uniformly
        # slow ladder, are opposite findings and 「전 칸」 is false for the first.
        # 🔴 Count against _RUNG_LABELS, not against len(rungs): the two differed
        # once already (R2단독 is a rung but was not in the label list), and the
        # mismatch printed 「R0,S1,...,R2동시 «만» 716ms」 - every rung named as
        # the exception to itself.
        named = [(k, lbl) for k, lbl in _RUNG_LABELS if rungs.get(k)]
        slow = [lbl for k, lbl in named if rungs[k]["p50"] >= SLOW_MS]
        if len(slow) == len(named):
            lo = min(st["p50"] for st in rungs.values())
            head = (f"점프 없음인데 전 칸 {lo:,.0f}~{worst:,.0f}ms "
                    f"→ 원인은 사다리 바깥 (프로세스 앞단의 공통 상수)")
        else:
            head = (f"점프 없음 · {','.join(slow)} «만» {worst:,.0f}ms "
                    f"→ 계단이 아니라 그 칸 고유 비용")

    if r0:
        r0txt = f"R0 {r0['p50']:,.0f}ms" + ("(느림)" if r0["p50"] >= SLOW_MS else "")
    else:
        r0txt = "R0 미측정(기준선 없음)"
    hdb = (_ladder.get("health_db") or {}).get("status")
    if not hdb:
        # 「본문아님」 = /health answered 200 with something that is not the health
        # document. That is the catch-all-serves-HTML trap, and it means R0 is an
        # unverified baseline rather than a confirmed DB round trip.
        hdb = "본문아님" if _ladder.get("r0_body_json") is False else "?"
    tail = f"{r0txt}·최대 {worst:,.0f}ms·칸 {done}/{total}·db={hdb}"
    if jumps and worst < SLOW_MS:
        # A step CAN add 200 ms on a box where nothing ever reaches a second -
        # R2→R4 on a healthy box here was +105 ms just serialising 2.7 MB. The
        # jump is real and stays named, but relayed without this the operator
        # would be reporting a found cause for a symptom the ladder never saw.
        tail += "·1초증상 아님"
    if jumps and missing:
        tail += f"·미측정 {','.join(missing)}"
    return f"{head} | {tail}", _digest(rungs)


def print_verdict():
    """The last thing the report prints. The final line IS the verdict."""
    line, digest = _verdict()
    print()
    print(SEP)
    print("  ▶ 한 줄 판정 — 이 아래 «판정» 줄만 그대로 읽어 전달하면 된다")
    print(SEP)
    if digest:
        print(f"   다이제스트  {digest}")
        print(f"      ({_DIGEST_LEGEND} · 값=log2(ms) · A≈1초 · X=미측정 · "
              f"끝자리=검사문자)")
    print(f"   판정  {line}")
    print(SEP)


# ---------------------------------------------------------------------------
# 5. Are the page-load queries the slow ones?
# ---------------------------------------------------------------------------
def _table_names():
    """The tables the grid page asks about, read from table_config.json.

    Read as a FILE rather than through `database.crud`: this is a diagnostic that
    must run on a box where the app may be struggling, and importing the CRUD
    core drags the whole dynamic-model registry in. The file is the same source
    `crud.TABLE_CONFIG` loads from.
    """
    path = paths.config_path("table_config.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if isinstance(cfg, dict):
            tables = cfg.get("tables") if isinstance(cfg.get("tables"), dict) else cfg
            return sorted(k for k in tables.keys() if not k.startswith("_")), path
    except Exception as e:
        print(f"     [table_config.json을 읽지 못했다: {type(e).__name__}: {e}]")
    return [], path


def section_page_load(p, max_tables, http_base):
    head(5, "페이지 로드 쿼리가 느린가? (PAGE LOAD)")
    print("  그리드 화면 한 번 뜨는 데 테이블마다 /tables/{t}/schema 와")
    print("  /api/maps/paint-rules?table={t} 가 나간다. 그 둘이 DB에서 실제로 하는 일을")
    print("  여기서 직접 재서, «페이지가 느린 이유가 이 호출들인가»를 판정한다.")

    tables, cfg_path = _table_names()
    if not tables:
        print(f"     테이블 목록을 얻지 못했다 ({cfg_path}). 이 절은 건너뛴다.")
        return
    print(f"\n     선언된 테이블 {len(tables)}개 (config: {cfg_path})")
    picked = tables[:max_tables]

    sub("A. 커넥션 확보 시간 — 모든 DB 엔드포인트가 공통으로 내는 비용")
    print("     서버는 요청마다 풀에서 커넥션을 빌린다. 풀이 비어 있으면 «쿼리»가 아니라")
    print("     «빌리는 것»에서 막힌다. 이 스크립트는 서버의 풀을 볼 수 없으므로, 대신")
    print("     «새 백엔드 접속을 여는 데 걸리는 시간»을 잰다 — max_connections 근처거나")
    print("     서버가 포화면 이 값이 먼저 부푼다.")
    samples = []
    for _ in range(3):
        t0 = time.perf_counter()
        try:
            eng = sa.create_engine(
                p.engine.url, poolclass=sa.pool.NullPool,
                connect_args={"options": "-c default_transaction_read_only=on",
                              "application_name": "assy_slow_probe_conn"})
            with eng.connect() as c:
                c.execute(sa.text("SELECT 1"))
            eng.dispose()
            samples.append((time.perf_counter() - t0) * 1000)
        except Exception as e:
            print(f"     신규 접속 실패: {type(e).__name__}: {str(e).splitlines()[0][:120]}")
            break
    if samples:
        print(f"     신규 접속 + SELECT 1 : " +
              "  ".join(f"{s:.1f}ms" for s in samples)
              + f"   (중간값 {sorted(samples)[len(samples) // 2]:.1f}ms)")
        snapshot["connect_ms"] = samples
        if sorted(samples)[len(samples) // 2] > 200:
            note("새 접속을 여는 데만 200ms를 넘는다. 이 값이 크면 어떤 엔드포인트를 고쳐도 "
                 "«페이지가 늦게 뜬다»는 그대로다 — 접속 자체가 병목이다.")

    sub("B. /tables/{t}/schema 가 DB에서 하는 일 — 테이블별 실측")
    print("     이 라우트는 table_config를 읽고, 가상조인 선언을 검증한다. 검증은 «조인 키를")
    print("     덮는 UNIQUE 인덱스가 있는가»를 카탈로그에서 묻는 질의다(행을 세지 않는다).")
    print("     아래는 그 카탈로그 질의를 테이블마다 실제로 실행한 시간이다.")
    per_table = []
    for t in picked:
        t0 = time.perf_counter()
        # The same question virtual_join_config.unique_index_covering asks: does a
        # valid unique index exist on this relation, and what does it cover. Run as
        # SQL here rather than by importing the module, so this section works on a
        # box where the app's imports are the thing that is broken.
        p.rows("""
            SELECT i.indexrelid::regclass::text, i.indisunique,
                   array_agg(a.attname ORDER BY k.ord)
            FROM pg_index i
            JOIN pg_class c ON c.oid = i.indrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS k(attnum, ord) ON true
            LEFT JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = k.attnum
            WHERE c.relname = :t AND i.indisvalid AND i.indisready
              AND n.nspname NOT IN ('pg_catalog', 'information_schema')
            GROUP BY 1, 2
        """, t=t)
        per_table.append((t, (time.perf_counter() - t0) * 1000))

    per_table.sort(key=lambda x: -x[1])
    total = sum(ms for _, ms in per_table)
    for t, ms in per_table:
        bar = "#" * min(40, int(ms / 5))
        print(f"     {t[:34]:34} {ms:8.1f} ms  {bar}")
    print(f"     {'합계 (' + str(len(per_table)) + '개 테이블)':34} {total:8.1f} ms")
    snapshot["schema_query_ms"] = dict(per_table)
    snapshot["schema_query_total_ms"] = total
    if total > 1000:
        note(f"스키마 라우트의 DB 작업만 합쳐 {total:.0f}ms다. 페이지 한 번에 이만큼이 "
             f"직렬로 깔린다면 «페이지 로드»가 느린 이유의 상당 부분이 여기다.")
    else:
        note(f"스키마 라우트의 DB 작업 합계는 {total:.0f}ms로 작다. 그런데도 페이지가 느리다면 "
             f"원인은 이 쿼리가 아니라 «순번을 기다리는 것»(커넥션 풀 / 스레드풀 포화)이거나 "
             f"응답을 만드는 파이썬 쪽이다.")

    # -----------------------------------------------------------------------
    # The call the brief did not name and the access log hides among the others.
    # `switchTable` (client2/src/api.js:130-141) runs schema -> DATA -> history,
    # and it is the middle one that scales with the table: main.py:1627 issues an
    # exact `query.count()`, cached for 2 s in TABLE_COUNT_CACHE - and every
    # ingestion completion calls `invalidate_table_cache`, so the first page load
    # after a bulk load always pays the full count.
    # -----------------------------------------------------------------------
    sub("B-2. /tables/{t}/data 의 진짜 비용 — 캐시가 비워진 직후의 count(*)")
    print("     그리드는 스키마 다음에 /tables/{t}/data 를 부르고, 그 라우트는 총 행수를")
    print("     정확히 센다(server/main.py:1627). 결과는 2초만 캐시되며, 인제션이 끝날 때마다")
    print("     invalidate_table_cache가 그 캐시를 비운다 — 즉 «대량 적재 직후 첫 페이지 로드»는")
    print("     반드시 전량 count를 낸다. 가장 큰 테이블에서 그 비용을 잰다.")
    big = p.rows("""
        SELECT c.relname, c.reltuples::bigint
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r' AND n.nspname NOT IN ('pg_catalog', 'information_schema')
          AND c.relname = ANY(:t)
        ORDER BY pg_total_relation_size(c.oid) DESC LIMIT 3
    """, t=list(tables))
    for name, est in big:
        t0 = time.perf_counter()
        rows, to = p.bounded(f'SELECT count(*) FROM "{name}"', ms=BOUNDED_MS)
        ms = (time.perf_counter() - t0) * 1000
        if to:
            print(f"     {name[:30]:30} count(*) {BOUNDED_MS}ms 안에 못 끝냄 "
                  f"(~{est:,}행 추정)")
            note(f"«{name}» 의 전량 count가 {BOUNDED_MS}ms 안에 끝나지 않았다. 이 테이블을 "
                 f"연 «첫» 페이지 로드는 그 시간을 전부 기다린다(동기 라우트라 스레드풀 "
                 f"슬롯 1개와 커넥션 1개를 그동안 붙잡는다). 2초 캐시가 살아 있는 동안은 "
                 f"빠르므로, «처음만 느리다»로 보인다.")
        else:
            n = rows[0][0] if rows else -1
            print(f"     {name[:30]:30} count(*) {ms:8.1f} ms   {n:,}행 (정확)")
            snapshot.setdefault("count_ms", {})[name] = {"ms": ms, "rows": n}
            if ms > 1000:
                note(f"«{name}» 의 전량 count가 {ms:.0f}ms다. 대량 적재 직후 첫 페이지 로드는 "
                     f"이 값을 그대로 기다린다(카운트 캐시가 인제션 완료 시 비워지므로).")

    sub("C. /api/maps/paint-rules — DB를 전혀 쓰지 않는다 (사실 확인)")
    print("     이 라우트에는 db 의존성이 없다(server/main.py:4830). 매 호출마다")
    print("     map_overlay_config.json 을 «디스크에서 다시 읽는다».")
    ov = paths.config_path("map_overlay_config.json")
    if os.path.exists(ov):
        size = os.path.getsize(ov)
        samples = []
        for _ in range(5):
            t0 = time.perf_counter()
            with open(ov, "r", encoding="utf-8") as f:
                json.load(f)
            samples.append((time.perf_counter() - t0) * 1000)
        med = sorted(samples)[len(samples) // 2]
        n = len(tables)
        print(f"     파일 {human(size)}  파싱 중간값 {med:.2f} ms/회  "
              f"→ 페이지 1회({n}개 테이블) 기준 약 {med * n:.0f} ms")
        snapshot["paint_rules_parse_ms"] = med
        if med * n > 500:
            note(f"paint-rules는 DB를 안 쓰는데도 config 재파싱만으로 페이지당 약 "
                 f"{med * n:.0f}ms를 쓴다. DB를 아무리 고쳐도 이 부분은 줄지 않는다.")
    else:
        print(f"     {ov} 없음 — 이 환경에는 맵 오버레이 설정이 없다.")

    if http_base:
        sub(f"D. 실제 HTTP 왕복 ({http_base}) — GET만, 읽기 전용")
        _time_http(http_base, picked)


def _time_http(base, tables):
    """Time the real endpoints end-to-end. GET only; nothing here writes.

    This is the measurement that separates "the DB is slow" from "the server
    cannot get to my request": a document fetch (`GET /`) needs no database at
    all, so if IT is slow at the same time as the XHRs, the queue is in the
    process, not in PostgreSQL.
    """
    import urllib.request
    import urllib.error

    base = base.rstrip("/")

    def get(path, timeout=60):
        t0 = time.perf_counter()
        try:
            req = urllib.request.Request(base + path, method="GET",
                                         headers={"X-Source": "slow_probe"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
                return (time.perf_counter() - t0) * 1000, r.status, len(body)
        except urllib.error.HTTPError as e:
            return (time.perf_counter() - t0) * 1000, e.code, 0
        except Exception as e:
            return (time.perf_counter() - t0) * 1000, f"ERR {type(e).__name__}", 0

    ms, status, n = get("/")
    print(f"     GET /                             {ms:8.1f} ms  [{status}] {human(n)}"
          f"   ← 문서(정적). DB를 쓰지 않는다.")
    snapshot.setdefault("http", {})["document_ms"] = ms

    schema_total = 0.0
    rows = []
    for t in tables:
        ms_s, st_s, n_s = get(f"/tables/{t}/schema")
        ms_p, st_p, n_p = get(f"/api/maps/paint-rules?table={t}")
        schema_total += ms_s + ms_p
        rows.append((t, ms_s, st_s, ms_p, st_p))
    for t, ms_s, st_s, ms_p, st_p in sorted(rows, key=lambda r: -(r[1] + r[3])):
        print(f"     {t[:30]:30} schema {ms_s:8.1f}ms [{st_s}]   "
              f"paint-rules {ms_p:8.1f}ms [{st_p}]")
    print(f"     {'API 합계 (' + str(len(rows)) + '개 테이블 × 2)':30} {schema_total:8.1f} ms")
    snapshot["http"]["api_total_ms"] = schema_total
    snapshot["http"]["per_table"] = {t: {"schema_ms": a, "paint_ms": b}
                                     for t, a, _, b, _ in rows}

    # 🔴 THE ONE THAT REPRODUCED THE REPORT. Timed LAST, deliberately, because it
    #    has a side effect on the SERVER PROCESS (not the database): it builds the
    #    in-memory audit cache, so every later call - including a real user's - is
    #    fast. Timing it earlier would make everything after it look healthy.
    #    Read-only against PostgreSQL; the only thing it changes is a cache the
    #    next page load would have built anyway.
    print()
    print("     GET /audit_logs/recent ... (이 한 줄은 몇 분이 걸릴 수 있다 — 그것이 측정하려는")
    print("     바로 그 현상이다. 최대 10분까지 기다린다.)", flush=True)
    ms3, status3, n3 = get("/audit_logs/recent?limit_groups=100", timeout=600)
    print(f"     GET /audit_logs/recent            {ms3:8.1f} ms  [{status3}] {human(n3)}")
    print("     ↑ 화면이 테이블을 열 때마다 부르는 것. 응답은 작은데 시간이 크면,")
    print("       그것은 «느린 쿼리»가 아니라 «캐시를 짓는 중»이고 한 번만 낸다.")
    ms4, status4, n4 = get("/audit_logs/recent?limit_groups=100")
    print(f"     GET /audit_logs/recent (2회차)    {ms4:8.1f} ms  [{status4}]")
    snapshot["http"]["audit_recent_first_ms"] = ms3
    snapshot["http"]["audit_recent_second_ms"] = ms4
    if ms3 > 3000 and ms4 < ms3 / 5:
        note(f"/audit_logs/recent 가 첫 호출 {ms3 / 1000:.1f}초 → 두 번째 "
             f"{ms4 / 1000:.2f}초다. 일회성 비용이 확인됐다 — 이것이 «적재 직후에만 "
             f"느리고 저절로 낫는다»의 정체다. 5b절이 그 크기의 근거를 말한다.")

    ms2, status2, n2 = get("/")
    print(f"     GET / (API 호출 뒤 재측정)        {ms2:8.1f} ms  [{status2}]")
    snapshot["http"]["document_ms_after"] = ms2
    print()
    print("     [읽는 법] 문서가 빠른데 API만 느리면 → DB 경합. 문서까지 같이 느리면")
    print("     → 프로세스 안에서 줄을 서고 있다(스레드풀 40 토큰 / 풀 30 커넥션).")


# ---------------------------------------------------------------------------
# 5b. The history route's first-call cost - MEASURED ON THE DEV BOX AT 31.7 s
# ---------------------------------------------------------------------------
def section_audit_first_call(p):
    """How expensive is the FIRST `/audit_logs/recent` after a bulk ingestion.

    This section exists because it is the one thing that reproduced the report.
    Measured on the isolated dev box, 2026-08-11, after ingesting 100,000 rows:

        GET /audit_logs/recent?limit_groups=100   ->  31,737 ms   (66,793 bytes)
        the same call again                       ->     243 ms
        and again                                 ->     130 ms

    A 65 KB response that costs half a minute once and then nothing is not a slow
    query - it is a cache being built, and the cost is proportional to what the
    ingestion just wrote. Two places pay it, both in server/audit_cache.py, both
    reached from the sync `def` at server/main.py:924-931:

      `load_initial` (audit_cache.py:25-66) - pages audit_logs newest-first in
      5,000-row chunks with a GROWING OFFSET until it has collected 100 DISTINCT
      transaction_ids. A bulk ingestion writes one transaction_id per FILE, so
      100,000 fresh rows are ONE group: the scan has to walk past all of them
      before it can find group #2. Paid once per web-server process.

      `refresh_if_stale` (audit_cache.py:69-117) - `MAX(id)` advanced, so it
      fetches EVERY audit row above its watermark with no LIMIT and runs a
      pydantic `model_validate` plus a linear group scan per row. Paid after
      every bulk write by another process (i.e. after every file the watcher
      ingests).

    🔴 The `/internal/events/batch-refresh` path does NOT prevent this. It calls
    `add_logs_batch`, and `add_logs_batch` never advances `_db_max_id` (grep:
    the watermark is written only at audit_cache.py:67 and :116). So the rows the
    event already merged are read and validated a SECOND time by the next
    `refresh_if_stale`.

    What this section can measure from the database alone is the SHAPE that drives
    both costs: how few distinct transactions the newest audit rows belong to.
    """
    head("5b", "감사 이력 «첫 호출» 비용 (AUDIT HISTORY FIRST CALL)")
    if not p.has_relation("audit_logs"):
        print("     audit_logs 테이블이 없다.")
        return
    print("  그리드 화면은 테이블을 열 때마다 /audit_logs/recent 를 부른다")
    print("  (client2/src/api.js switchTable -> loadHistory). 이 라우트는 «서로 다른")
    print("  트랜잭션 100개»를 모을 때까지 audit_logs를 최신순으로 훑는다")
    print("  (server/audit_cache.py:25-66). 그런데 대량 인제션은 파일 하나가 트랜잭션")
    print("  하나이므로, 방금 넣은 10만 행이 전부 «한 그룹»이다 — 두 번째 그룹을 찾으려면")
    print("  그 10만 행을 전부 지나가야 한다.")

    SAMPLE = 200000
    rows, to = p.bounded(f"""
        SELECT count(*), count(DISTINCT transaction_id)
        FROM (SELECT transaction_id FROM audit_logs
              ORDER BY id DESC LIMIT {SAMPLE}) s
    """, ms=15000)
    if to or not rows:
        print(f"\n     [최신 {SAMPLE:,}행을 15초 안에 훑지 못했다 — 그 자체가 이 라우트가 "
              f"느리다는 뜻이다]")
        note("audit_logs의 최신 20만 행을 15초 안에 읽지 못했다. /audit_logs/recent 의 "
             "첫 호출은 이보다 더 많은 행을 훑는다 — 화면이 그만큼 기다린다.")
        return
    scanned, distinct_tx = rows[0]
    print(f"\n     최신 {scanned:,}행이 담고 있는 서로 다른 트랜잭션: {distinct_tx}개")
    snapshot["audit_recent_shape"] = {"sampled": scanned, "distinct_tx": distinct_tx}
    if distinct_tx < 100:
        note(f"최신 audit_logs {scanned:,}행 안에 트랜잭션이 {distinct_tx}개뿐이다. "
             f"/audit_logs/recent 는 100개를 모아야 하므로 이 {scanned:,}행을 «전부» 지나간 "
             f"뒤에도 계속 훑는다. 이것이 «적재 직후 화면이 안 뜨다가 조금 있으면 "
             f"괜찮아지는» 증상의 직접 원인이다(웹서버 기동 후 첫 1회, 그리고 다른 "
             f"프로세스가 대량 기록할 때마다 1회).")
    else:
        print("     100개 이상 — 이 축에서는 첫 호출이 얕게 끝난다.")

    sub("가장 큰 최근 트랜잭션 (한 그룹이 얼마나 큰가)")
    rows, to = p.bounded(f"""
        SELECT transaction_id, count(*) AS n, min(timestamp), max(timestamp)
        FROM (SELECT transaction_id, timestamp FROM audit_logs
              ORDER BY id DESC LIMIT {SAMPLE}) s
        GROUP BY transaction_id ORDER BY n DESC LIMIT 8
    """, ms=15000)
    if to:
        print("     [시간 내 집계하지 못했다]")
        return
    for tx, n, t0, t1 in rows:
        print(f"     {str(tx)[:40]:40} {n:>10,}행   {t0} ~ {t1}")
    # -----------------------------------------------------------------------
    # Why each of those chunk reads is expensive, from the catalogue and the
    # PLANNER only - no EXPLAIN ANALYZE, because that would EXECUTE the full scan
    # this section is warning about and a diagnostic must not become the outage.
    #
    # Measured on the dev box (233,206 audit rows) with EXPLAIN ANALYZE, for the
    # record - do not re-run this on a busy box:
    #   Parallel Seq Scan on audit_logs, then
    #   Sort  Sort Key: "timestamp" DESC, id DESC
    #         Sort Method: external merge  Disk: 46,216 kB
    #   OFFSET 0 -> 427 ms, OFFSET 100,000 -> 491 ms, OFFSET 200,000 -> 543 ms
    # i.e. every chunk re-scans and re-sorts THE WHOLE TABLE, and the cost grows
    # with the offset. `load_initial` issues one of these per 5,000 rows.
    # -----------------------------------------------------------------------
    sub("그 훑기 한 번의 비용 — 정렬을 도울 인덱스가 있는가")
    idx = p.rows("""
        SELECT indexname, indexdef FROM pg_indexes
        WHERE tablename = 'audit_logs' ORDER BY indexname
    """)
    leading_ts = [n for n, d in idx
                  if "USING btree (\"timestamp\"" in d or "USING btree (timestamp" in d]
    for name, d in idx:
        marker = "  ← timestamp 선두" if name in leading_ts else ""
        print(f"     {name:34} {d[d.find('USING'):][:80]}{marker}")
    if not leading_ts:
        print()
        print("     🔴 timestamp로 시작하는 인덱스가 없다. 그런데 이 라우트의 훑기는")
        print("        ORDER BY timestamp DESC, id DESC 이다 → 매 청크마다 테이블 전체를")
        print("        읽고 전체를 정렬한다(대개 디스크로 넘친다). 청크가 수십 개면")
        print("        그 전량 정렬을 수십 번 한다.")
        note("audit_logs에 timestamp 선두 인덱스가 없어서 /audit_logs/recent의 첫 호출은 "
             "5,000행 청크마다 «테이블 전체 스캔 + 전체 정렬»을 한다. 테이블이 커질수록 "
             "청크 하나가 비싸지고, 대량 적재는 청크 «개수»까지 늘린다 — 두 배로 나빠진다.")
    plan = p.rows("EXPLAIN SELECT * FROM audit_logs "
                  "ORDER BY timestamp DESC, id DESC OFFSET 0 LIMIT 5000")
    if plan:
        print("\n     플래너가 고른 방법 (EXPLAIN — 실행하지 않는다):")
        for (line,) in plan[:8]:
            print(f"       {line[:120]}")

    biggest = rows[0][1] if rows else 0
    if biggest > 20000:
        note(f"가장 큰 단일 트랜잭션이 감사 로그 {biggest:,}행이다. 캐시 갱신은 이 행들을 "
             f"«한 건씩» pydantic 검증한다(audit_cache.py:87-95) — 이 박스 실측으로 "
             f"10만 행에 31.7초였다. 그동안 그 요청은 스레드풀 슬롯 1개와 DB 커넥션 "
             f"1개를 붙잡고 있으므로, 같은 순간 정적 문서(/)도 같이 밀린다.")
def section_statements(p, limit=12):
    head(6, "pg_stat_statements (있으면)")
    installed = p.one("SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements'")
    if not installed:
        available = p.one("SELECT 1 FROM pg_available_extensions "
                          "WHERE name = 'pg_stat_statements'")
        print("     이 데이터베이스에는 pg_stat_statements 확장이 설치돼 있지 않다.")
        print("     → 이 절은 «측정 못 함»이지 «문제 없음»이 아니다.")
        if available:
            print("     (서버에 모듈은 있다. 설치하려면 관리자가 postgresql.conf의")
            print("      shared_preload_libraries에 추가하고 재기동한 뒤")
            print("      CREATE EXTENSION pg_stat_statements; — 이 스크립트는 하지 않는다.)")
        else:
            print("     (서버에 모듈 자체가 없다 — contrib 패키지가 설치되지 않았다.)")
        snapshot["pg_stat_statements"] = None
        return

    # PG13 renamed total_time -> total_exec_time. Ask the catalogue rather than
    # guessing from the version, because the extension version and the server
    # version move independently.
    has_exec = p.one("SELECT 1 FROM pg_attribute "
                     "WHERE attrelid = 'pg_stat_statements'::regclass "
                     "AND attname = 'total_exec_time'")
    tot = "total_exec_time" if has_exec else "total_time"
    mean = "mean_exec_time" if has_exec else "mean_time"

    reset = p.one("SELECT stats_reset FROM pg_stat_statements_info") if \
        p.one("SELECT 1 FROM pg_class WHERE relname = 'pg_stat_statements_info'") else None
    if reset:
        print(f"     집계 시작: {reset[0]}")

    for title, order in [("총 시간 상위 (누가 이 서버의 시간을 다 썼는가)", tot),
                         ("평균 시간 상위 (한 번이 오래 걸리는 것)", mean)]:
        sub(title)
        rows = p.rows(f"""
            SELECT calls, {tot} AS total_ms, {mean} AS mean_ms, rows,
                   left(regexp_replace(query, '\\s+', ' ', 'g'), 130)
            FROM pg_stat_statements
            WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
              AND calls > 1
            ORDER BY {order} DESC
            LIMIT :lim
        """, lim=limit)
        if not rows:
            print("     이 데이터베이스에 대한 기록이 없다.")
            continue
        print(f"     {'호출':>10} {'총 ms':>14} {'평균 ms':>11} {'반환행':>14}  쿼리")
        for calls, total_ms, mean_ms, nrows, q in rows:
            print(f"     {calls:>10,} {float(total_ms or 0):>14,.0f} "
                  f"{float(mean_ms or 0):>11,.2f} {nrows or 0:>14,}  {q}")
        if order == tot and rows:
            snapshot["top_statements"] = [
                {"calls": r[0], "total_ms": float(r[1] or 0),
                 "mean_ms": float(r[2] or 0), "query": r[4]} for r in rows[:5]]


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(
        description="Read-only probe for 'everything is slow after a bulk ingestion'.")
    ap.add_argument("--tables", type=int, default=25,
                    help="how many tables to time in section 5 (default 25)")
    ap.add_argument("--http", metavar="BASE_URL", default=None,
                    help="also time the real endpoints end-to-end, e.g. "
                         "http://127.0.0.1:8080 (GET only, nothing is written)")
    ap.add_argument("--json", metavar="PATH", default=None,
                    help="also write a machine-readable snapshot to this file "
                         "(the ONLY thing this script can write; never the database)")
    args = ap.parse_args()

    url, source = paths.resolve_database_url(DEFAULT_PG_URL)
    print(SEP)
    print("  적재 직후 시스템이 느린 원인 진단 (READ-ONLY PROBE)")
    print("  이 스크립트는 데이터베이스에 아무것도 쓰지 않는다 —")
    print("  세션이 default_transaction_read_only=on 으로 고정돼 있어 서버가 거부한다.")
    print(SEP)

    try:
        p = Probe(url)
    except Exception as e:
        print(f"\n  [치명] 데이터베이스에 접속하지 못했다: {type(e).__name__}: {e}")
        print(f"  대상: {paths.mask_db_password(url)} (출처: {source})")
        return 2

    try:
        section_context(p, url, source)
        section_activity(p)
        section_autovacuum(p)
        section_outbox(p)
        section_sizes(p)
        # Runs BEFORE section 5 on purpose: section 5 ends by calling
        # /audit_logs/recent, which builds the server's in-memory audit cache and
        # therefore changes the process it is measuring. The ladder must see the
        # box in the state the operator found it.
        section_where_the_second_goes(p, args.http, _table_names()[0])
        section_page_load(p, args.tables, args.http)
        section_audit_first_call(p)
        section_statements(p)
    finally:
        p.close()

    print(f"\n{SEP}\n읽은 사람이 알아야 할 것 (SUMMARY)\n{SEP}")
    if not _notes:
        print("  이 스냅샷에서는 눈에 띄는 것이 없었다.")
        print("  ⚠️ 느림이 «적재 직후 한동안»이라면, 조용할 때 찍은 이 스냅샷은 아무것도")
        print("     반증하지 못한다. 느린 그 순간에 다시 한 번 돌릴 것.")
    else:
        for i, m in enumerate(_notes, 1):
            print(f"  {i}. {m}")
    print()
    print("  이 보고서는 «무엇을 고칠지»는 정하지 않는다 — 시간이 어디서 늘었는지까지다.")
    print(SEP)

    if args.json:
        snapshot["notes"] = _notes
        line, digest = _verdict()
        snapshot["verdict"] = {"line": line, "digest": digest}
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2, default=str)
        print(f"\n  (스냅샷 저장: {args.json})")

    # LAST, and last on purpose: on a box where the output cannot be copied off,
    # the operator scrolls to the bottom and reads one line.
    print_verdict()
    return 0


if __name__ == "__main__":
    sys.exit(main())
