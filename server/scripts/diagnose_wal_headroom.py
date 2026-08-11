"""WAL 여유(headroom) 한 방 진단 — 운영 DB에 그대로 돌려도 되는 읽기 전용 프로브.

    conda run --no-capture-output -n assy_manager python agent_workspace/reports/wal_headroom.py

⚠️ `--no-capture-output` 은 선택이 아니다. 없으면 conda 가 자식 출력을 cp949 로
디코드해서 한글 제목이 전부 깨진다(diagnose_slow_after_ingest.py 와 같은 이유).

===============================================================================
이 스크립트가 답하는 질문 (그리고 왜 이것만 답하면 되는가)
===============================================================================
"인제션이 WAL 을 740 GB 만든다" 는 문장은 **디스크에 대한 문장이 아니다.**
WAL 은 정상 운용에서 재사용(recycle)된다 — 생성량이 아니라 **동시에 남아 있는 양
(resident)** 이 디스크를 채운다. 생성된 WAL 이 남아 있게 되는 조건은 정해져 있고
셀 수 있다:

    (a) 아카이빙이 밀린다      archive_mode=on 인데 archive_command 가 실패/지연
    (b) 복제 슬롯이 붙잡는다   restart_lsn 이 뒤에 남은 슬롯 (특히 inactive)
    (c) wal_keep_size          하한선으로 강제 보관
    (d) 체크포인트가 못 따라간다  max_wal_size 는 soft limit 이라 초과할 수 있다
    (e) WAL 요약기가 밀린다    (PG17+) summarize_wal=on 인데 summarizer 가 뒤처짐

이 다섯이 전부 비어 있으면 **생성량은 디스크 문제가 아니라 처리량 문제**이고,
pg_wal 은 max_wal_size 근처에서 평평하게 유지된다. 하나라도 걸려 있으면 그것이
진짜 결함이고, 쓰기량을 줄이는 것보다 훨씬 싸게 고칠 수 있다.

===============================================================================
읽기 전용이라는 것을 의도가 아니라 서버가 보장한다
===============================================================================
접속은 `default_transaction_read_only=on` 을 **연결 옵션**으로 걸어서 연다. 롤백
뒤에 새로 시작되는 트랜잭션까지 포함해 이 세션의 모든 트랜잭션에 적용되므로,
`SET TRANSACTION READ ONLY` 한 번과 달리 조용히 풀리지 않는다. INSERT/UPDATE/
DELETE/DDL/VACUUM/pg_stat_reset 은 서버가 거부한다.

모든 문장은 카탈로그(pg_class, pg_settings)·통계뷰(pg_stat_*)·디렉터리 목록
(pg_ls_waldir)만 읽으며 AccessShareLock 보다 무거운 잠금을 잡지 않는다.
statement_timeout / lock_timeout / idle_in_transaction_session_timeout 을 모두
고정해서, 힘들어하는 서버에서 이 프로브 자신이 문제의 일부가 되지 않는다.

유일하게 쓰는 것은 `--json <파일>` 을 이름으로 지정했을 때의 로컬 스냅샷 파일뿐이다.

===============================================================================
숫자 두 개는 서버 밖에서 온다
===============================================================================
* **WAL 볼륨의 남은 공간**은 SQL 로 알 수 없다. 이 스크립트를 **DB 서버 자신에서**
  돌렸을 때만 `data_directory` 를 통해 읽는다. 원격에서 돌리면 "측정 불가"라고
  말하고 절대 추정하지 않는다.
* **생성 속도**는 기본 10 초 동안 LSN 을 두 번 읽어서 잰다(`--sample-seconds`).
  10 초가 한가한 순간이면 낮게 나온다 — 그래서 pg_stat_wal 의 리셋 이후 장기
  평균도 함께 찍는다. 둘이 크게 다르면 그 사실 자체가 답이다.
"""
import argparse
import json
import os
import shutil
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import sqlalchemy as sa

DEFAULT_PG_URL = "postgresql://postgres:admin@localhost:5432/assy_manager"
STATEMENT_TIMEOUT_MS = 15000
SEP = "=" * 78
SUB = "-" * 78

snap = {}
_verdicts = []


def hb(n):
    """바이트를 사람이 읽는 단위로. 로케일을 타지 않게 직접 나눈다."""
    if n is None:
        return "-"
    v = float(n)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if abs(v) < 1024 or u == "TB":
            return ("%d B" % int(v)) if u == "B" else ("%.1f %s" % (v, u))
        v /= 1024
    return "%.1f TB" % v


def dur(sec):
    if sec is None:
        return "-"
    s = int(sec)
    if s < 3600:
        return "%d분%02d초" % (s // 60, s % 60)
    if s < 86400:
        return "%d시간%02d분" % (s // 3600, (s % 3600) // 60)
    return "%d일%02d시간" % (s // 86400, (s % 86400) // 3600)


class RO:
    """읽기 전용으로 못박은 연결 하나. diagnose_slow_after_ingest.py:189-207 과
    같은 설정을 쓴다 — 이 프로젝트에 진단용 접속 패턴은 하나만 있어야 한다."""

    def __init__(self, url):
        self.engine = sa.create_engine(
            url,
            poolclass=sa.pool.NullPool,
            connect_args={
                "options": ("-c default_transaction_read_only=on "
                            f"-c statement_timeout={STATEMENT_TIMEOUT_MS} "
                            "-c lock_timeout=2000 "
                            "-c idle_in_transaction_session_timeout=60000 "
                            "-c client_encoding=utf8"),
                "application_name": "assy_wal_headroom",
            },
        )
        self.conn = self.engine.connect()
        self.vnum = int(self.conn.execute(sa.text("SHOW server_version_num")).scalar() or 0)
        self._release()

    def _release(self):
        # 통계 조회 하나 때문에 스냅샷 트랜잭션을 붙들고 있으면, 읽기 전용이어도
        # xmin horizon 을 잡아 vacuum 을 막는다. 문장마다 끊는다.
        try:
            self.conn.rollback()
        except Exception:
            pass

    def rows(self, sql, **p):
        try:
            out = self.conn.execute(sa.text(sql), p).fetchall()
            self._release()
            return out
        except Exception as e:
            self._release()
            print("     [읽기 실패] %s: %s" % (type(e).__name__,
                                            str(e).splitlines()[0][:140]))
            return None            # None = 못 읽음, [] = 진짜로 없음 (구분한다)

    def one(self, sql, **p):
        r = self.rows(sql, **p)
        if r is None:
            return None
        return r[0] if r else ()

    def scalar(self, sql, **p):
        r = self.one(sql, **p)
        return r[0] if r else None

    def setting(self, name):
        r = self.one("SELECT setting, unit FROM pg_settings WHERE name = :n", n=name)
        return (r[0], r[1]) if r else (None, None)

    def setting_bytes(self, name):
        """pg_settings 의 값을 바이트로. unit 이 '8kB'/'MB'/'B'/'kB' 로 오는 것을
        문자열로 짐작하지 않고 카탈로그가 준 unit 으로 환산한다."""
        v, u = self.setting(name)
        if v is None:
            return None
        try:
            n = float(v)
        except ValueError:
            return None
        mult = {"B": 1, "kB": 1024, "8kB": 8192, "16kB": 16384, "32kB": 32768,
                "64kB": 65536, "MB": 1048576, "GB": 1073741824, None: 1, "": 1}
        return int(n * mult.get(u, 1))

    def close(self):
        try:
            self.conn.close()
        finally:
            self.engine.dispose()


def head(n, t):
    print("\n%s\n%s. %s\n%s" % (SEP, n, t, SEP))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=None, help="기본값은 앱이 해석하는 URL")
    ap.add_argument("--sample-seconds", type=float, default=10.0)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    url = args.url
    src = "인자"
    if not url:
        # 앱이 해석하는 것과 같은 URL 을 쓴다. 아무도 묻지 않은 DB 에 대한 깨끗한
        # 보고서는 오류보다 나쁘다.
        try:
            sys.path.insert(0, os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "server"))
            import paths                                            # noqa: E402
            url, src = paths.resolve_database_url(DEFAULT_PG_URL)
        except Exception:
            url, src = DEFAULT_PG_URL, "내장 기본값"

    db = RO(url)
    shown = url.split("@")[-1]
    print(SEP)
    print("WAL 여유 진단 — 읽기 전용 (%s)" % time.strftime("%Y-%m-%d %H:%M:%S"))
    print(SEP)
    print("  대상    : %s  (URL 출처: %s)" % (shown, src))
    print("  서버    : %s" % db.scalar("SELECT version()"))
    print("  세션    : default_transaction_read_only=on / statement_timeout=%dms"
          % STATEMENT_TIMEOUT_MS)
    snap["target"] = shown
    snap["server_version_num"] = db.vnum

    # ------------------------------------------------------------------ 1
    head(1, "지금 디스크에 남아 있는 WAL (resident) — 이 숫자가 절벽까지의 거리다")
    waldir = db.one("SELECT coalesce(sum(size),0)::bigint, count(*) FROM pg_ls_waldir()")
    max_wal = db.setting_bytes("max_wal_size")
    min_wal = db.setting_bytes("min_wal_size")
    segsz = db.setting_bytes("wal_segment_size")
    resident, nseg = (waldir[0], waldir[1]) if waldir else (None, None)
    if resident is None:
        print("     pg_ls_waldir() 를 읽지 못했다. 이 계정에 pg_monitor 롤이 필요하다:")
        print("       GRANT pg_monitor TO <이 스크립트가 쓰는 사용자>;")
        print("     🔴 이 항목 없이는 '절벽까지의 거리'를 말할 수 없다 — 추정하지 않는다.")
    else:
        print("     pg_wal 실제 크기        : %s  (%s개 세그먼트 × %s)"
              % (hb(resident), nseg, hb(segsz)))
        print("     max_wal_size (목표 상한): %s      min_wal_size: %s"
              % (hb(max_wal), hb(min_wal)))
        if max_wal:
            pct = 100.0 * resident / max_wal
            print("     비율                    : %.0f%% of max_wal_size" % pct)
            if resident > max_wal * 1.5:
                _verdicts.append(
                    "pg_wal 이 max_wal_size 의 %.1f배다. max_wal_size 는 soft limit "
                    "이므로 이것 자체가 '무언가가 WAL 을 붙잡고 있거나 체크포인트가 "
                    "못 따라간다'는 신호다 — 2번 항목에서 범인을 찾아라." % (resident / max_wal))
            elif resident <= max_wal * 1.2:
                print("     → 재사용(recycle)이 정상 동작 중인 모습이다. 생성량이 아무리")
                print("       커도 이 값 근처에서 평평하게 유지된다.")
    snap["resident_bytes"] = resident
    snap["max_wal_size_bytes"] = max_wal
    snap["segments"] = nseg

    # ------------------------------------------------------------------ 2
    head(2, "생성된 WAL 을 «남아 있게» 만들 수 있는 것들 — 이게 전부다")
    holders = []

    print("\n  (a) 아카이빙")
    am, _ = db.setting("archive_mode")
    ac, _ = db.setting("archive_command")
    al, _ = db.setting("archive_library")
    print("      archive_mode = %s   archive_command = %r   archive_library = %r"
          % (am, ac, al))
    if am in ("on", "always"):
        ar = db.one("SELECT archived_count, last_archived_wal, last_archived_time, "
                    "failed_count, last_failed_wal, last_failed_time, stats_reset "
                    "FROM pg_stat_archiver")
        if ar:
            print("      성공 %s건 (마지막 %s @ %s)" % (ar[0], ar[1], ar[2]))
            print("      실패 %s건 (마지막 %s @ %s)" % (ar[3], ar[4], ar[5]))
        ready = db.scalar(
            "SELECT count(*) FROM pg_ls_archive_statusdir() WHERE name LIKE '%%.ready'")
        if ready is not None:
            print("      아카이브 대기(.ready) : %s개  ≈ %s"
                  % (ready, hb((ready or 0) * (segsz or 16777216))))
            if ready and ready > 8:
                holders.append(("아카이빙 적체", (ready or 0) * (segsz or 16777216),
                                ".ready 파일 %d개가 밀려 있다. 이 세그먼트들은 "
                                "아카이브될 때까지 재사용되지 않는다." % ready))
        if ar and ar[3] and (ar[5] is not None):
            holders.append(("아카이브 실패", None,
                            "archive_command 가 %s건 실패했다 (마지막 %s). 실패가 "
                            "계속되면 pg_wal 은 무한히 자란다." % (ar[3], ar[4])))
    else:
        print("      → archive_mode 가 꺼져 있다. 아카이빙은 이 서버에서 WAL 을 "
              "붙잡을 수 «없다».")

    print("\n  (b) 복제 슬롯")
    slots = db.rows("""
        SELECT slot_name, slot_type, active, restart_lsn::text,
               CASE WHEN restart_lsn IS NULL THEN NULL
                    ELSE pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint END,
               wal_status, safe_wal_size, database
        FROM pg_replication_slots ORDER BY 5 DESC NULLS LAST""")
    mskws = db.setting_bytes("max_slot_wal_keep_size")
    mskw_raw, _ = db.setting("max_slot_wal_keep_size")
    if slots is None:
        print("      pg_replication_slots 를 읽지 못했다.")
    elif not slots:
        print("      → 슬롯이 하나도 없다. 슬롯은 이 서버에서 WAL 을 붙잡고 있지 «않다».")
    else:
        for s in slots:
            print("      %-28s %-9s active=%-5s wal_status=%-10s 보유 %s"
                  % (s[0], s[1], s[2], s[5], hb(s[4])))
            if s[4] and s[4] > (max_wal or 0):
                holders.append(("복제 슬롯 %s" % s[0], s[4],
                                "restart_lsn 이 현재 LSN 보다 %s 뒤에 있다%s."
                                % (hb(s[4]), "" if s[2] else " (그리고 INACTIVE 다 — "
                                   "아무도 소비하지 않는데 보관만 한다)")))
    print("      max_slot_wal_keep_size = %s%s"
          % (mskw_raw,
             ("  ⚠️ -1 = 무제한: 슬롯이 «생기면» 그 하나가 디스크를 끝까지 채울 수 있다"
              if not slots else
              "  🔴 -1 = 무제한: 위 슬롯의 소비자가 멈추면 pg_wal 에 상한이 없다")
             if str(mskw_raw) == "-1" else ""))
    if slots and str(mskw_raw) == "-1":
        _verdicts.append("슬롯이 존재하는데 max_slot_wal_keep_size 가 -1(무제한)이다. "
                         "슬롯 소비자가 멈추면 pg_wal 에 상한이 없어진다.")

    print("\n  (c) wal_keep_size")
    wks = db.setting_bytes("wal_keep_size")
    print("      wal_keep_size = %s%s" % (hb(wks),
          "  → 0. 하한 보관 없음." if not wks else "  → 이만큼은 항상 남는다."))
    if wks:
        holders.append(("wal_keep_size", wks, "설정상 항상 이만큼은 보관된다."))

    print("\n  (d) 체크포인트가 쓰기 속도를 따라가는가")
    ct, _ = db.setting("checkpoint_timeout")
    cct, _ = db.setting("checkpoint_completion_target")
    if db.vnum >= 170000:
        ck = db.one("SELECT num_timed, num_requested, stats_reset FROM pg_stat_checkpointer")
    else:
        ck = db.one("SELECT checkpoints_timed, checkpoints_req, stats_reset "
                    "FROM pg_stat_bgwriter")
    print("      checkpoint_timeout = %ss   completion_target = %s" % (ct, cct))
    if ck:
        timed, req = int(ck[0] or 0), int(ck[1] or 0)
        tot = timed + req
        print("      체크포인트: 시간기반 %s건 / 요청기반(=max_wal_size 초과) %s건  "
              "(통계 리셋 %s)" % (timed, req, ck[2]))
        if tot and req > timed:
            print("      → 요청기반이 더 많다. 쓰기 속도가 max_wal_size 를 %.0f%% 의 "
                  "체크포인트에서 밀어내고 있다. 위험은 아니지만 max_wal_size 를 "
                  "키우면 FPI(전체 페이지 쓰기)가 줄어 WAL 총량이 줄어든다."
                  % (100.0 * req / tot))
        snap["checkpoints"] = {"timed": timed, "requested": req}

    print("\n  (e) WAL 요약기 (PG17+ 증분 백업)")
    if db.vnum >= 170000:
        sw, _ = db.setting("summarize_wal")
        print("      summarize_wal = %s" % sw)
        if sw == "on":
            st = db.one("SELECT summarized_lsn::text, pending_lsn::text, summarizer_pid "
                        "FROM pg_get_wal_summarizer_state()")
            lag = db.scalar("SELECT pg_wal_lsn_diff(pg_current_wal_lsn(), "
                            "(SELECT summarized_lsn FROM pg_get_wal_summarizer_state()))::bigint")
            print("      요약 완료 LSN=%s  대기=%s  pid=%s  뒤처짐 %s"
                  % (st[0] if st else "?", st[1] if st else "?",
                     st[2] if st else "?", hb(lag)))
            if lag and max_wal and lag > max_wal:
                holders.append(("WAL 요약기 지연", lag,
                                "요약기가 %s 뒤처져 있다. 요약 전 세그먼트는 지워지지 "
                                "않는다." % hb(lag)))
        else:
            print("      → 꺼져 있다. 요약기는 WAL 을 붙잡을 수 «없다».")
    else:
        print("      → 서버가 PG17 미만이라 해당 없음.")

    snap["holders"] = [{"what": h[0], "bytes": h[1], "why": h[2]} for h in holders]

    # ------------------------------------------------------------------ 3
    head(3, "지금 WAL 이 만들어지는 속도")
    w0 = db.one("SELECT pg_current_wal_lsn()::text")
    st0 = db.one("SELECT wal_records, wal_fpi, wal_bytes, stats_reset, "
                 "extract(epoch FROM now() - stats_reset) FROM pg_stat_wal")
    print("     %.0f초 표본을 뜬다..." % args.sample_seconds)
    time.sleep(args.sample_seconds)
    w1 = db.one("SELECT pg_current_wal_lsn()::text")
    st1 = db.one("SELECT wal_records, wal_fpi, wal_bytes FROM pg_stat_wal")
    rate = None
    if w0 and w1:
        # CAST(...) 로 쓴다: `:b::pg_lsn` 은 SQLAlchemy 의 바인드 파라미터 문법과
        # PostgreSQL 의 `::` 캐스트가 충돌해 구문 오류가 난다(측정 중 실제로 났다).
        d = db.scalar("SELECT pg_wal_lsn_diff(CAST(:b AS pg_lsn), "
                      "CAST(:a AS pg_lsn))::bigint", a=w0[0], b=w1[0])
        if d is not None:
            rate = d / max(args.sample_seconds, 0.001)
            print("     최근 %.0f초 : %s 생성  →  %s/초  (=%s/시간)"
                  % (args.sample_seconds, hb(d), hb(rate), hb(rate * 3600)))
    if st0 and st1 and st0[4]:
        long_avg = float(st0[2]) / float(st0[4])
        print("     통계 리셋(%s) 이후 장기 평균 : %s/초 (=%s/일)"
              % (st0[3], hb(long_avg), hb(long_avg * 86400)))
        print("     누적 %s (레코드 %s건, 그중 전체페이지쓰기 %s건 = %.1f%%)"
              % (hb(float(st0[2])), "{:,}".format(int(st0[0])),
                 "{:,}".format(int(st0[1])),
                 100.0 * int(st0[1]) / max(int(st0[0]), 1)))
        snap["rate_bytes_per_sec_sampled"] = rate
        snap["rate_bytes_per_sec_longrun"] = long_avg
        if rate is not None and long_avg and rate > long_avg * 5:
            print("     → 지금이 장기 평균의 %.0f배다. 인제션 중일 가능성이 높다."
                  % (rate / long_avg))

    # ------------------------------------------------------------------ 4
    head(4, "판정 — 디스크가 위험한가")
    freeb = None
    dd = db.scalar("SHOW data_directory")
    if dd and os.path.isdir(dd):
        try:
            freeb = shutil.disk_usage(dd).free
            print("     WAL 볼륨 남은 공간 : %s   (data_directory = %s)" % (hb(freeb), dd))
        except Exception as e:
            print("     남은 공간을 읽지 못했다: %s" % e)
    else:
        print("     ⚠️ 남은 디스크 공간은 «측정 불가» 다 — 이 스크립트를 DB 서버 «자신»")
        print("        에서 돌려야 읽을 수 있다 (data_directory=%r 가 여기서 안 보인다)."
              % dd)
        print("        추정하지 않는다. 서버에서 그 경로의 여유 공간을 직접 확인하라.")
    snap["free_bytes"] = freeb

    if not holders:
        print("\n     ✅ WAL 을 붙잡는 조건이 하나도 없다 (아카이빙 꺼짐/밀림 없음,")
        print("        슬롯 없음, wal_keep_size 0, 요약기 해당없음).")
        print("        → 인제션이 만드는 WAL «총량» 은 디스크 문제가 아니다. 재사용되어")
        print("          pg_wal 은 max_wal_size 근처에서 평평하게 유지된다.")
        print("          이 경우 WAL 은 «처리량» 비용이지 «용량» 위험이 아니다.")
        if resident and max_wal and resident > max_wal * 1.5:
            print("        ⚠️ 다만 pg_wal 이 max_wal_size 를 크게 넘고 있다 — 위 다섯 개")
            print("           중 무엇도 아니라면 체크포인트가 못 따라가는 것이다.")
    else:
        print("\n     🔴 WAL 을 붙잡고 있는 것이 %d개 있다. 이것이 진짜 결함이고, 쓰기량을"
              % len(holders))
        print("        줄이는 것보다 훨씬 싸게 고칠 수 있다:")
        for w, b, why in holders:
            print("        - %-24s %s" % (w, hb(b) if b else ""))
            print("          %s" % why)
        # 절벽까지의 시간은 «두 속도 중 큰 쪽» 으로 잰다. 표본 10초가 마침 한가한
        # 순간이면 0 이 나오는데(측정 중 실제로 그랬다), 그 0 을 근거로 "시간이
        # 무한하다"고 말하면 안 된다.
        use = max(rate or 0, snap.get("rate_bytes_per_sec_longrun") or 0)
        if freeb and use:
            which = "표본" if (rate or 0) >= (snap.get("rate_bytes_per_sec_longrun") or 0) \
                else "장기평균"
            print("\n     생성 속도 %s/초(%s)가 «전부 보관» 된다고 보면 남은 공간 %s 는"
                  % (hb(use), which, hb(freeb)))
            print("     %s 만에 찬다. (지금 보관 중인 %s 는 이미 쓴 것이다)"
                  % (dur(freeb / use), hb(sum(h[1] or 0 for h in holders))))
    for v in _verdicts:
        print("\n     ※ %s" % v)

    print("\n%s" % SUB)
    print("  ⚠️ WAL 이 가득 차면 PostgreSQL 은 WAL 쓰기 실패에서 PANIC 하고 클러스터")
    print("     «전체» 가 재시작(크래시 복구)된다. 특정 요청이 느려지는 게 아니라 모든")
    print("     쓰기가 멈춘다. 그래서 이 판정은 '언젠가'가 아니라 '지금 몇 %' 로 본다.")
    print(SUB)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(snap, f, indent=1, ensure_ascii=False, default=str)
        print("  스냅샷 저장: %s" % args.json)
    db.close()


if __name__ == "__main__":
    main()
