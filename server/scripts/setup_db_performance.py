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

        # 3.7 [V1 계기 — 완료까지의 상호작용 점수] interaction_effort_logs 집계/멱등성 인덱스.
        #   models.py InteractionEffortLog.__table_args__ 와 동일 정의 — **두 곳을 함께 고칠 것**.
        #   신규 설치에서는 create_all 이 테이블과 함께 만들지만, 테이블이 이미 존재하는 DB에는
        #   create_all 이 인덱스를 추가하지 않으므로 이 경로가 유일한 반영 수단이다
        #   (idx_audit_user_recorrection 이 정확히 그 이유로 여기 있다).
        #
        #   - uq_effort_transaction : tx당 1행 불변식. 없으면 클라 재시도가 같은 공수를 두 번
        #     세어 세션 평균이 왜곡된다.
        #   - idx_effort_window     : 창 집계(timestamp 범위 + session_id GROUP BY)의 커버링
        #     인덱스. 없으면 대시보드 집계가 Seq Scan 으로 떨어진다.
        print("\nStep 3.7: Creating interaction_effort_logs indices (V1 effort metric)...")
        effort_table_exists = conn.execute(text(
            "SELECT to_regclass('public.interaction_effort_logs')"
        )).scalar()
        if not effort_table_exists:
            # 테이블이 없으면 create_all 이 인덱스까지 함께 만든다 — 여기서 할 일이 없다.
            print(" - Table not present yet; create_all will build it with its indices. Skipping.")
        else:
            # [총괄 addendum 2026-07-29] nav_preserved_count 보정. create_all 은 기존 테이블에
            #   컬럼을 추가하지 않으므로, 이 컬럼이 생기기 전에 테이블이 만들어진 DB에는
            #   이 경로로만 반영된다(database_outbox.broadcast_at 과 같은 패턴).
            #   NOT NULL DEFAULT 0 이므로 기존 행은 0 으로 채워진다 — 그 시점엔 면제 전이를
            #   세지 않았으니 0 이 정직한 값이다(추정으로 메우지 않는다).
            col_exists = conn.execute(text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'interaction_effort_logs' "
                "AND column_name = 'nav_preserved_count'"
            )).first()
            if not col_exists:
                print(" - Adding missing column nav_preserved_count...")
                conn.execute(text(
                    "ALTER TABLE interaction_effort_logs "
                    "ADD COLUMN nav_preserved_count INTEGER NOT NULL DEFAULT 0"))
                print("   Done.")

            effort_indices = [
                ("uq_effort_transaction", "interaction_effort_logs", "UNIQUE", "(transaction_id)"),
                ("idx_effort_window", "interaction_effort_logs", "",
                 "(timestamp) INCLUDE (session_id, key_count, mouse_count, nav_count, "
                 "nav_preserved_count)"),
            ]
            for idx_name, table, uniq, definition in effort_indices:
                print(f" - Creating {idx_name} on {table}...")
                t0 = time.time()
                try:
                    conn.execute(text(
                        f"CREATE {uniq} INDEX CONCURRENTLY IF NOT EXISTS "
                        f"{idx_name} ON {table} {definition}"))
                    print(f"   Success ({time.time() - t0:.2f}s)")
                except Exception as e:
                    # UNIQUE 생성 실패는 중복 tx 행이 이미 있다는 뜻일 수 있다 — 조용히 넘기지 않는다.
                    print(f"   Failed to create {idx_name}: {e}")

        # 3.8 [F3 값 제안] 접두 조회 인덱스 — `(lower(col) COLLATE "C", col COLLATE "C")`.
        #   **models.py에 선언하지 않는다.** 두 가지 이유가 겹친다:
        #     ① create_all은 이미 존재하는 테이블에 인덱스를 추가하지 않는다
        #        (idx_audit_user_recorrection·idx_effort_window이 여기 있는 바로 그 이유).
        #     ② `COLLATE "C"`는 PostgreSQL 전용 표현이라 테스트 스위트의 sqlite
        #        create_all이 깨진다. 따라서 이 경로가 **유일한** 반영 수단이다.
        #
        #   왜 이 형태인가: 이 DB의 콜레이션은 Korean_Korea.949다. 비-C 콜레이션에서
        #   btree는 `LIKE 'p%'`를 **범위로 만들지 못한다** — 플래너는 인덱스를 고르고도
        #   전 엔트리를 Filter로 버린다(bonding_map 실측: 1,755,308행 폐기 / 232ms).
        #   같은 질의가 이 인덱스에서는 `Index Cond: lower(base) >= 'c' AND < 'd'` /
        #   0.2ms가 된다. 두 번째 키는 loose index scan(값 1개당 seek 1회)의 커서
        #   `(lower(col), col) > (last_lower, last_value)`를 인덱스 탐색으로 만든다.
        #
        #   대상 선정 정책은 server/value_suggest.py `index_targets`가 단독 소유하고
        #   (suggest_config.json의 index_min_rows / index_columns / index_exclude),
        #   인덱스 이름·정의도 같은 모듈이 한 곳에서 유도한다.
        print("\nStep 3.8: Creating value-suggestion prefix indices (F3)...")
        try:
            import value_suggest
            from database import crud

            settings = value_suggest.resolve_settings(value_suggest.load_config())
            table_config = crud.load_table_config() or {}
            # reltuples는 추정치라 공짜다. 한 번도 ANALYZE되지 않은 테이블(-1)만
            # 실제 count로 보정한다 — 그렇지 않으면 갓 적재한 대형 테이블이
            # "작은 테이블"로 잘못 분류되어 인덱스 없이 조용히 남는다.
            row_counts = {}
            for name, reltuples in conn.execute(text(
                "SELECT relname, reltuples FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relkind = 'r'"
            )).fetchall():
                row_counts[name] = int(reltuples) if reltuples and reltuples > 0 else -1
            for name, count in list(row_counts.items()):
                if count < 0:
                    row_counts[name] = conn.execute(
                        text(f'SELECT count(*) FROM "{name}"')).scalar() or 0

            targets = value_suggest.index_targets(table_config, settings, row_counts)
            if not targets:
                print(" - No suggestion index targets "
                      f"(index_min_rows={settings['index_min_rows']}). Skipping.")

            # INVALID indices must be named BEFORE the create loop. A cancelled
            # CONCURRENTLY build leaves one behind under the wanted name, the
            # planner never uses it, and `IF NOT EXISTS` below then skips that
            # name on every future run - so re-running this script silently
            # fixes nothing while the column stays timed out forever. The
            # CONCURRENTLY warning in POSTGRES_OPERATIONS §3.1 (a worker sitting
            # `idle in transaction` makes this step look hung) describes exactly
            # how an operator arrives here.
            invalid = [r[0] for r in conn.execute(text(
                "SELECT ci.relname FROM pg_index i "
                "JOIN pg_class ci ON ci.oid = i.indexrelid "
                "JOIN pg_namespace n ON n.oid = ci.relnamespace "
                "WHERE n.nspname = 'public' AND ci.relname LIKE :p "
                "AND NOT (i.indisvalid AND i.indisready)"),
                {"p": value_suggest.INDEX_PREFIX + "%"})]
            if invalid:
                print(" - !! INVALID suggestion indices (planner ignores them, and "
                      "IF NOT EXISTS below will SKIP these names):")
                for name in invalid:
                    print(f"     REINDEX INDEX CONCURRENTLY {name};"
                          f"   -- or DROP INDEX CONCURRENTLY {name}; then re-run")

            for table, column, idx_name, definition in targets:
                print(f" - Creating {idx_name} on {table} {definition}...")
                t0 = time.time()
                try:
                    conn.execute(text(
                        f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {idx_name} "
                        f'ON "{table}" {definition}'))
                    size = conn.execute(text(
                        "SELECT pg_size_pretty(pg_relation_size(:n))"),
                        {"n": idx_name}).scalar()
                    print(f"   Success ({time.time() - t0:.2f}s, {size})")
                except Exception as e:
                    print(f"   Failed to create {idx_name}: {e}")

            # 대상에서 빠진 잔존 인덱스는 **자동 삭제하지 않고 보고만** 한다.
            # config 로드가 일시 실패한 상태에서 일괄 DROP이 돌면 조용히 전 인덱스를
            # 날리게 된다 — 삭제는 사람이 판단할 일이다.
            wanted = {t[2] for t in targets}  # index names
            orphans = [r[0] for r in conn.execute(text(
                "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' "
                "AND indexname LIKE :p"), {"p": value_suggest.INDEX_PREFIX + "%"})
                if r[0] not in wanted]
            if orphans:
                print(" - Orphaned suggestion indices (no longer targets; "
                      "drop manually if intended):")
                for o in orphans:
                    print(f"     DROP INDEX CONCURRENTLY IF EXISTS {o};")
        except Exception as e:
            print(f"   Suggestion index step failed: {e}")

        # 4. 통계 정보 갱신
        print("\nStep 4: Refreshing Statistics (ANALYZE)...")
        conn.execute(text("ANALYZE database_outbox"))
        conn.execute(text("ANALYZE audit_logs"))
        if effort_table_exists:
            conn.execute(text("ANALYZE interaction_effort_logs"))
        print("Done.")

    print("\n✅ All performance optimizations have been applied successfully!")

if __name__ == "__main__":
    setup_performance()
