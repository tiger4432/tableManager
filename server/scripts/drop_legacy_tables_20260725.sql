-- =============================================================================
-- 레거시 미사용 테이블 정리 (2026-07-25) — 조사·준비: Server PM / 실행: 총괄 PM
-- =============================================================================
-- ⚠️ 이 스크립트는 준비본이다. 실행 전 아래 전제·절차를 반드시 확인할 것.
--
-- [대상]
--   1) data_rows            (0행)     — 구 JSONB blob 저장소. 동적 네이티브 테이블로 완전 대체.
--                                        ORM 모델(DataRow)·기동 마이그레이션·인덱스 셋업 코드는
--                                        2026-07-25 코드 정리로 제거됨(제거 전엔 create_all이 재생성했음).
--   2) graph_sync_statuses  (2,269행) — 구 그래프 경로의 per-row 동기화 상태 테이블.
--                                        현행 코드·전체 git 이력 모두 참조 0건(고아 테이블).
--                                        현행 대체: 동적 테이블 per-row is_graph_synced 컬럼
--                                                  + graph_sync_state(커서) + graph_nodes/graph_edges.
--
-- [절대 건드리지 말 것 — 유사 명칭 현역 테이블]
--   graph_sync_state  (단수, id=1 커서 1행) — graph_sync_worker가 상시 사용 중. DROP 금지.
--
-- [백업]
--   graph_sync_statuses → agent_workspace/backup/graph_sync_statuses_20260725.csv (2,269행 검증 완료)
--   data_rows 는 0행이므로 백업 생략.
--
-- [실행 절차]
--   1. 코드 정리 커밋(DataRow 모델 제거)이 배포/반영된 상태인지 확인.
--      (모델 제거 전 상태의 프로세스가 재기동하면 create_all이 data_rows를 재생성한다)
--   2. 실행: psql -U postgres -d assy_manager -f server/scripts/drop_legacy_tables_20260725.sql
--      또는 pgAdmin 쿼리 창에서 본문 실행.
--   3. 구동 중 서버 영향: 없음(두 테이블 모두 어떤 프로세스도 읽기/쓰기하지 않음).
--      DROP 자체는 무중단 실행 가능. 단, 코드 정리분(models/database/main/setup 스크립트)을
--      실제 프로세스에 반영하려면 5-프로세스(웹서버·워처·체인워커·그래프워커 등) 재기동 1회 필요.
--   4. 검증: 아래 [사후 검증] 쿼리로 존재 여부 확인.
--
-- [사후 검증]
--   SELECT tablename FROM pg_tables WHERE schemaname='public'
--    AND tablename IN ('data_rows','graph_sync_statuses');   -- 0행이어야 함
--   SELECT * FROM graph_sync_state;                          -- 커서 1행 생존 확인
-- =============================================================================

BEGIN;

DROP TABLE IF EXISTS data_rows CASCADE;
DROP TABLE IF EXISTS graph_sync_statuses CASCADE;

COMMIT;
