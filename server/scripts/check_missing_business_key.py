"""업무키가 비어 있는 행을 찾고, **채울 수 있는지**를 먼저 답한다. 읽기 전용.

대량 인제션에서 일부 행의 `business_key_val`이 비는 일이 보고됐다(제품 소유자 2026-08-07).
원본 `composite_key_source` 컬럼은 다 차 있는데 키만 빈 상태다.

🔴 이 스크립트는 **아무것도 쓰지 않는다.** 세션을 읽기 전용으로 고정해 구조적으로 못 쓰게 한다.

   ⚠️ THE SECOND HALF OF THAT SENTENCE WAS FALSE AND IS WORTH RECORDING RATHER THAN
   QUIETLY FIXING. What stood below was `SET SESSION default_transaction_read_only = on`
   on a connection borrowed from the application pool at the ORDINARY isolation level.
   Measured on the isolated `assy_qa` (PostgreSQL 18.3 / SQLAlchemy 2.0.49 /
   psycopg2 2.9.11) on 2026-08-13, in exactly that arrangement:

       default_transaction_read_only = on     <- the variable the sentence meant
       transaction_read_only         = off    <- the one PostgreSQL enforces
       CREATE / INSERT / UPDATE               ALL THREE ACCEPTED

   So the session was NOT pinned and nothing was structural about it. 🔴 AND NOTHING
   FOLLOWS FROM THAT ABOUT THIS SCRIPT'S SAFETY: there is no write statement anywhere in
   this file, which is why the first half of the sentence is still true and why nothing
   was ever written. The defect was a claim, not an incident. It is fixed here because a
   guard that has never been armed is indistinguishable from one that has been disarmed,
   and because this file was one of three that copied the wrong spelling from a document
   which taught it - the copying is the thing being repaired, and this is the copy that
   proves it was copying rather than three independent mistakes.

   채우는 일은 별개 라운드다 — 그 전에 답해야 할 것이 셋이고, 그 셋이 이 스크립트의 출력이다:

   ① 몇 행인가                     — 규모
   ② 재료가 있는가                 — `composite_key_source` 컬럼이 비어 있으면 어떤 스크립트도
                                      못 만든다. 사람이 값을 넣어야 한다
   ③ 채우면 충돌하는가             — 조합한 키가 **이미 있는 행의 키와 같으면** 그 둘은
                                      중복이다. 유니크 인덱스가 서면 거절되고, 안 서 있으면
                                      조용히 둘이 된다. 어느 쪽이든 **사람이 정할 일**이다

⚠️ 키 조합은 `crud.assemble_composite_business_key`가 정본이다. 여기서 문자열을 이어 붙이면
   그것이 **두 번째 철자**가 되고, 조합 규칙이 바뀌는 날 이 스크립트만 옛 규칙으로 남는다.
   그래서 이 스크립트는 조합을 **하지 않고**, 재료가 있는지와 충돌하는지만 센다.

Usage
-----
    python server/scripts/check_missing_business_key.py
    python server/scripts/check_missing_business_key.py --table dt_log
"""

import argparse
import io
import json
import os
import sys

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from sqlalchemy import text                                    # noqa: E402

# 🔴 The read-only guard has ONE home, `server/db_safety.py`. This script no
# longer borrows the application's pooled engine, because the flag cannot be
# armed at connect time on an engine somebody else built - and connect time is
# what makes it independent of the isolation level, which is the whole repair.
from db_safety import (  # noqa: E402
    close_readonly_connection, open_readonly_connection)
import db_safety  # noqa: E402

CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "..", "config", "table_config.json")

READONLY_APPLICATION_NAME = "assy_missing_bk_check"


def open_readonly_engine(url=None):
    """This script's engine. One line of policy over the shared door."""
    return db_safety.open_readonly_engine(
        url, application_name=READONLY_APPLICATION_NAME)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", help="이 표만 본다. 없으면 전부")
    args = ap.parse_args()

    cfg = json.load(io.open(CONFIG, encoding="utf-8"))
    # 🔴 구조적으로 못 쓰게 한다. 「읽기 전용입니다」라고 적는 것과 세션이 거절하는 것은
    #    다른 물건이고, 이 저장소는 후자만 증거로 친다. The door below REFUSES unless
    #    PostgreSQL itself answers `transaction_read_only = on`.
    ro_engine = open_readonly_engine()
    try:
        conn = open_readonly_connection(ro_engine)
    except BaseException:
        ro_engine.dispose()
        raise
    try:
        _report(conn, cfg, args.table)
    finally:
        close_readonly_connection(conn)
        ro_engine.dispose()


def _report(conn, cfg, only_table):
    q = lambda s: [tuple(r) for r in conn.execute(text(s))]

    tables = [r[0] for r in q(
        "SELECT table_name FROM information_schema.columns "
        "WHERE column_name='business_key_val' AND table_schema='public' ORDER BY 1")]
    if only_table:
        tables = [t for t in tables if t == only_table]

    total_missing = 0
    for t in tables:
        try:
            n = q("SELECT count(*) FROM \"%s\" "
                  "WHERE business_key_val IS NULL OR business_key_val=''" % t)[0][0]
        except Exception as e:
            print("%-24s  조회 실패: %s" % (t, str(e)[:60]))
            continue
        if not n:
            continue
        total_missing += n
        src = (cfg.get(t) or {}).get("composite_key_source") or []
        print()
        print("== %s — 키 없는 행 %d" % (t, n))
        if not src:
            print("   composite_key_source 선언이 없다. 이 표는 복합키를 조합하도록 설정된 적이 "
                  "없으므로, 채우려면 **선언이 먼저**다.")
            continue
        print("   composite_key_source = %s" % src)

        cols = ", ".join('"%s"' % s for s in src)
        blank_pred = " OR ".join(
            "(\"%s\" IS NULL OR \"%s\"::text = '')" % (s, s) for s in src)
        no_material = q('SELECT count(*) FROM "%s" '
                        'WHERE (business_key_val IS NULL OR business_key_val=\'\') '
                        'AND (%s)' % (t, blank_pred))[0][0]
        # ② 재료
        print("   재료 없음(키 컬럼이 빈 행) : %d  ← 사람이 값을 넣어야 한다" % no_material)
        print("   재료 있음(조합 가능)       : %d" % (n - no_material))

        # ③ 충돌 — 조합 규칙을 흉내내지 않고, **같은 재료를 가진 기존 행이 있는지**로 센다.
        #    조합기가 순서와 구분자를 정하므로 정확한 키 문자열은 여기서 못 만든다. 그러나
        #    「같은 재료 조합이 이미 키를 갖고 존재한다」면 채우는 순간 충돌한다 — 그것은
        #    조합 규칙과 무관하게 참이다.
        join_on = " AND ".join('a."%s" = b."%s"' % (s, s) for s in src)
        clash = q('SELECT count(*) FROM "%s" a JOIN "%s" b ON %s '
                  'WHERE (a.business_key_val IS NULL OR a.business_key_val=\'\') '
                  'AND b.business_key_val IS NOT NULL AND b.business_key_val <> \'\''
                  % (t, t, join_on))[0][0]
        print("   채우면 기존 행과 충돌   : %d  ← 같은 재료를 가진 행이 이미 키를 갖고 있다"
              % clash)
        if clash:
            print("      ⚠️ 이 행들은 중복이다. 유니크 인덱스가 서면 거절되고 안 서 있으면 "
                  "조용히 둘이 된다. **어느 행이 사는지는 사람이 정한다** — "
                  "audit_logs·cell_sources 귀속이 그 선택을 따라간다.")

        # 재료가 있는 행의 표본
        rows = q('SELECT %s, count(*) FROM "%s" '
                 'WHERE (business_key_val IS NULL OR business_key_val=\'\') '
                 'AND NOT (%s) GROUP BY %s LIMIT 5' % (cols, t, blank_pred, cols))
        if rows:
            print("   표본(조합 가능한 재료):")
            for r in rows:
                print("      %s  x%s" % (list(r[:-1]), r[-1]))

    print()
    if not total_missing:
        print("키 없는 행 없음. (이 박스 기준이고, 운영은 다른 기계다.)")
    else:
        print("합계 키 없는 행: %d" % total_missing)
    # This line used to be printed on the strength of a `SET` that did not take. It
    # is printed now on the strength of PostgreSQL having answered the question -
    # `open_readonly_connection` refuses the run otherwise, so reaching here IS the
    # evidence rather than a restatement of the intent.
    print("아무것도 쓰지 않았다 — 세션이 읽기 전용이라고 PostgreSQL 이 답했다 "
          "(transaction_read_only=%s)." % db_safety.readonly_state(conn))


if __name__ == "__main__":
    main()
