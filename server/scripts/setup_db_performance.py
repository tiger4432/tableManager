import sys
import os
import time
from sqlalchemy import text

# 프로젝트 루트를 경로에 추가
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from database.database import engine

def setup_performance():
    print("🚀 AssyManager DB Performance Setup Starting...")
    
    # AUTOCOMMIT 모드로 실행 (CONCURRENTLY 인덱스 생성 지원)
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        
        # 1. 필수 확장 프로그램 설치
        print("\nStep 1: Enabling PostgreSQL Extensions...")
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gin"))
        print("Done.")

        # [2026-07-25 정리] Step 2(레거시 data_rows 전용 인덱스 5종)는 data_rows 폐기와 함께 제거됨
        # (동적 네이티브 테이블 인덱스는 models.py의 동적 모델 정의가 소유 — drop_legacy_tables_20260725.sql 참조).

        # 3. Outbox 폴링 최적화 인덱스 (체인/그래프 워커 폴링 스캔 가속)
        #    부분/표현식 인덱스는 PostgreSQL 전용이며, models.py DatabaseOutbox.__table_args__ 와 동일 패턴.
        #    기존 운영 DB(create_all 이 새 인덱스를 추가하지 않는 환경)에 멱등적으로 반영한다.
        outbox_indices = [
            # [#1] SYSTEM_RELOAD 트리거 조회 전용 부분 인덱스
            ("idx_outbox_reload", "database_outbox",
             "(event_type, id) WHERE event_type = 'SYSTEM_RELOAD'"),

            # [#3] 미처리 체인 이벤트 큐 스캔 전용 부분 인덱스
            ("idx_outbox_unprocessed", "database_outbox",
             "(processed_chain, id) WHERE processed_chain = false"),

            # [#3] tx 보완 쿼리(payload->>'transaction_id') 가속용 표현식 인덱스
            ("idx_outbox_txid", "database_outbox",
             "((payload->>'transaction_id'))"),

            # [Reliability F1] 통지 미확정 교정 행 안전망 스윕 전용 부분 인덱스.
            #   정상 상태에선 거의 빈 인덱스 → 1000만행 누적에도 스윕이 O(미전달)로 안전.
            ("idx_outbox_undelivered", "database_outbox",
             "(id) WHERE processed_chain = true AND status = 'SUCCESS' AND broadcast_at IS NULL"),

            # [C-3] 보관 정책(7일) purge 대상 탐색 전용 부분 인덱스 (chain worker의 주기 purge가 사용).
            ("idx_outbox_purge", "database_outbox",
             "(created_at) WHERE processed_chain = true"),

            # [C-3] FAILED 격리 이벤트 관리 API 전용 부분 인덱스 — 비부분 status 인덱스 DROP의 대체.
            ("idx_outbox_failed", "database_outbox",
             "(status, id) WHERE status = 'FAILED'"),
        ]

        # [Reliability F1] broadcast_at 컬럼 보정 + 최초 생성 시 1회 청킹 백필.
        #   idx_outbox_undelivered(부분 인덱스)가 broadcast_at 을 참조하므로 인덱스 생성 전에 컬럼이 존재해야 한다.
        #   컬럼을 새로 만든 경우에만 기존 처리완료 행을 백필한다(기존 행을 전달완료로 간주 → 스윕 대량 오발사 방지).
        #   이미 존재하면(=앱 기동 시 마이그레이션됨) skip 하여 진짜 미전달 행을 덮어쓰지 않는다.
        print("\nStep 2.5: Ensuring database_outbox.broadcast_at column (Reliability F1)...")
        col_exists = conn.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'database_outbox' AND column_name = 'broadcast_at'"
        )).first()
        if not col_exists:
            conn.execute(text("ALTER TABLE database_outbox ADD COLUMN broadcast_at TIMESTAMPTZ"))
            print(" - Column added. Backfilling existing processed rows (chunked)...")
            backfilled = 0
            while True:
                res = conn.execute(text(
                    "UPDATE database_outbox SET broadcast_at = COALESCE(processed_at, created_at) "
                    "WHERE id IN (SELECT id FROM database_outbox "
                    "WHERE processed_chain = true AND broadcast_at IS NULL LIMIT 1000)"
                ))
                if not res.rowcount:
                    break
                backfilled += res.rowcount
            print(f"   Backfilled broadcast_at for {backfilled} row(s).")
        else:
            print(" - Column already present. Skipping backfill (undelivered rows handled by worker sweep).")

        print("\nStep 3: Creating Outbox Polling Indices...")
        for idx_name, table, definition in outbox_indices:
            print(f" - Creating {idx_name} on {table}...")
            t0 = time.time()
            try:
                conn.execute(text(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {idx_name} ON {table} {definition}"))
                print(f"   Success ({time.time() - t0:.2f}s)")
            except Exception as e:
                print(f"   Failed to create {idx_name}: {e}")

        # 3.5 [C-3] 레거시 중복 outbox 인덱스 제거 (실측 합계 429MB — 전량 역할 중복/미사용)
        #   - ix_database_outbox_id            : pkey와 완전 중복 (124MB)
        #   - ix_database_outbox_event_uuid    : 조회처 전무, uuid4 유일성은 통계적 보장 (224MB)
        #   - ix_database_outbox_status        : 부분 인덱스 idx_outbox_pending/idx_outbox_failed로 대체 (44MB)
        #   - ix_database_outbox_processed_chain : 부분 인덱스 idx_outbox_unprocessed로 대체 (37MB)
        #   models.py에서도 해당 컬럼의 index/unique 선언을 제거했으므로 create_all이 재생성하지 않는다.
        #   반드시 대체 인덱스(Step 3) 생성 이후에 DROP한다. CONCURRENTLY로 무중단 삭제(멱등).
        legacy_outbox_indexes = [
            "ix_database_outbox_id",
            "ix_database_outbox_event_uuid",
            "ix_database_outbox_status",
            "ix_database_outbox_processed_chain",
        ]
        print("\nStep 3.5: Dropping legacy duplicate outbox indices...")
        for idx_name in legacy_outbox_indexes:
            print(f" - Dropping {idx_name} (if exists)...")
            t0 = time.time()
            try:
                conn.execute(text(f"DROP INDEX CONCURRENTLY IF EXISTS {idx_name}"))
                print(f"   Done ({time.time() - t0:.2f}s)")
            except Exception as e:
                print(f"   Failed to drop {idx_name}: {e}")

        # 3.6 [재교정률] 대시보드 재교정률 집계 전용 부분 커버링 인덱스.
        #   create_all은 이미 존재하는 테이블에 인덱스를 추가하지 않으므로, 운영 DB에는 이 경로로만
        #   반영된다(models.py AuditLog.__table_args__ 와 동일 정의 — 두 곳을 함께 고칠 것).
        #   없으면 /dashboard/summary 의 재교정률 집계가 병렬 Seq Scan으로 떨어진다(실측 512ms/2.6M행).
        print("\nStep 3.6: Creating audit_logs re-correction index...")
        recorrection_idx = (
            "idx_audit_user_recorrection", "audit_logs",
            "(timestamp) INCLUDE (table_name, row_id, column_name, transaction_id) "
            "WHERE source_name = 'user'",
        )
        idx_name, table, definition = recorrection_idx
        print(f" - Creating {idx_name} on {table}...")
        t0 = time.time()
        try:
            conn.execute(text(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {idx_name} ON {table} {definition}"))
            print(f"   Success ({time.time() - t0:.2f}s)")
        except Exception as e:
            print(f"   Failed to create {idx_name}: {e}")

        # 4. 통계 정보 갱신
        print("\nStep 4: Refreshing Statistics (ANALYZE)...")
        conn.execute(text("ANALYZE database_outbox"))
        conn.execute(text("ANALYZE audit_logs"))
        print("Done.")

    print("\n✅ All performance optimizations have been applied successfully!")

if __name__ == "__main__":
    setup_performance()
