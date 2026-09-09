"""
[C-3] database_outbox 기존 백로그 수동 정리 스크립트
====================================================
경합 점검(2026-07-25)에서 실측된 outbox 백로그(2,705,513행 / 4,862MB — C-2 이중 발행으로
중복 그룹 1,259,076개 포함)를 오프피크에 일괄 정리하기 위한 **수동 실행 전용** 스크립트입니다.
라이브 프로세스는 이 스크립트를 절대 자동 실행하지 않습니다.

동작: processed_chain = true 이고 created_at이 보관기간(기본 7일)을 경과한 행을
      1000행 청크 DELETE로 삭제합니다(청크마다 commit → 락 보유시간 최소화, 중단 후 재실행 안전·멱등).
      미처리(processed_chain=false) 행은 나이와 무관하게 절대 삭제하지 않습니다.

권장 실행 순서 (사용자 운영 액션):
  0) C-2 수정이 반영된 코드로 전 프로세스 재기동 (신규 중복 유입 차단이 선행되어야 함)
  1) conda run -n assy_manager python server/scripts/setup_db_performance.py
     (레거시 중복 인덱스 4종 DROP → 대량 DELETE의 인덱스 유지비 절감 + purge용 인덱스 생성)
  2) conda run -n assy_manager python server/scripts/purge_outbox_backlog.py --dry-run   # 삭제 대상 확인
  3) conda run -n assy_manager python server/scripts/purge_outbox_backlog.py             # 실제 삭제
  4) 디스크 공간 실반환이 필요하면 오프피크에 수동 VACUUM:
       - 일반: VACUUM (ANALYZE) database_outbox;   ← 무중단, 공간은 재사용 가능 상태로만 회수
       - 완전 반환: VACUUM FULL database_outbox;   ← ACCESS EXCLUSIVE 락(전 프로세스 중지 후 실행)

사용법:
  conda run -n assy_manager python server/scripts/purge_outbox_backlog.py [--days 7] [--chunk 1000] [--dry-run]
"""
import sys
import os
import time
import argparse

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from sqlalchemy import text
from database.database import engine


def main():
    parser = argparse.ArgumentParser(description="database_outbox 처리 완료 백로그 수동 정리 (7일 보관 정책)")
    parser.add_argument("--days", type=int, default=7, help="보관 일수 (기본 7)")
    parser.add_argument("--chunk", type=int, default=1000, help="삭제 청크 크기 (기본 1000)")
    parser.add_argument("--dry-run", action="store_true", help="삭제하지 않고 대상 건수만 출력")
    args = parser.parse_args()

    if engine.dialect.name != "postgresql":
        print(f"이 스크립트는 PostgreSQL 전용입니다 (현재 dialect: {engine.dialect.name}). 중단합니다.")
        sys.exit(1)

    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        total_rows = conn.execute(text("SELECT count(*) FROM database_outbox")).scalar()
        target_rows = conn.execute(text(
            "SELECT count(*) FROM database_outbox "
            "WHERE processed_chain = true AND created_at < now() - make_interval(days => :days)"
        ), {"days": args.days}).scalar()
        print(f"database_outbox 전체: {total_rows:,}행 / 삭제 대상(처리완료 & {args.days}일 경과): {target_rows:,}행")

        if args.dry_run:
            print("[dry-run] 삭제를 수행하지 않고 종료합니다.")
            return

        if not target_rows:
            print("삭제 대상이 없습니다.")
            return

        deleted_total = 0
        chunk_no = 0
        t_start = time.time()
        while True:
            res = conn.execute(text(
                "DELETE FROM database_outbox WHERE id IN ("
                "  SELECT id FROM database_outbox "
                "  WHERE processed_chain = true AND created_at < now() - make_interval(days => :days) "
                "  LIMIT :chunk)"
            ), {"days": args.days, "chunk": args.chunk})
            deleted = res.rowcount or 0
            deleted_total += deleted
            chunk_no += 1
            if chunk_no % 50 == 0 or deleted < args.chunk:
                elapsed = time.time() - t_start
                print(f"  ... {deleted_total:,}/{target_rows:,}행 삭제 ({elapsed:.1f}s)")
            if deleted < args.chunk:
                break

        print(f"완료: 총 {deleted_total:,}행 삭제 ({time.time() - t_start:.1f}s). ANALYZE 갱신 중...")
        conn.execute(text("ANALYZE database_outbox"))
        print("ANALYZE 완료. 공간 실반환이 필요하면 오프피크에 VACUUM (ANALYZE) 또는 VACUUM FULL을 수동 실행하세요.")


if __name__ == "__main__":
    main()
