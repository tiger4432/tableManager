# Server 보고서 — 미사용 PostgreSQL 테이블 정리 (조사·준비 단계)

> 작성: server-pm | 2026-07-25 | 본체 main 트리, **미커밋**(지시대로) | DROP **미실행**(총괄 별도 수행)

## 1. 판정 결과 요약

| 테이블 | 행수(실측) | 판정 | 근거 |
|---|---|---|---|
| `data_rows` | 0 | **정리 가능(확정)** | 런타임 인스턴스화 지점 전무(유일한 `DataRow(...)` 생성처는 일회성 이관 스크립트 `scripts/migrate_to_postgres.py`). crud.py 참조 0건. 잔존 참조는 ①models 정의 ②main 기동 마이그레이션 ③outbox 리스너 isinstance ④테스트 방어코드 ⑤인덱스 셋업 스크립트뿐 — 전부 이번에 제거 |
| `graph_sync_statuses` | 2,269 | **정리 가능(확정)** | 현행 코드 참조 **0건** + **전체 git 이력(`git log --all -S`)에도 0건** — 저장소 추적 이전의 고아 테이블. 구 그래프 경로의 per-row 상태(`table_name/row_id/is_synced/synced_nodes/...`)로, 현행은 동적 테이블 per-row `is_graph_synced` 컬럼 + `graph_sync_state`(커서) + `graph_nodes`/`graph_edges`(PG 엣지 스토어)가 완전 대체 |

**graph_sync_worker.py 정밀 판정**: 가상 DB(Mock) 모드·Neo4j 훅 포함 전 경로를 grep — 워커가 읽고/쓰는 것은 `GraphSyncState`(`graph_sync_state`, id=1 커서 1행, :488–509)와 동적 테이블의 `is_graph_synced/needs_graph_rollback/graph_synced_at` 컬럼뿐. `graph_sync_statuses`는 어떤 모드에서도 접근하지 않음.

⚠️ **명칭 혼동 주의**: `graph_sync_state`(단수)는 **현역**(커서 last_outbox_id=3,297,311, 금일도 갱신 중) — DROP 대상 아님. DROP 스크립트에 경고 명시함.

**전수 Grep 범위**: server/ 전체 + docs/ + gitignored 사용자 영역(`server/config/`·`server/mappers/`·`server/ingestion_workspace/`, `rg --no-ignore`로 확인) — 사용자 영역 참조 0건.

## 2. 추가 미사용 테이블 조사 (DB 22개 테이블 전수 실측)

고아 테이블 추가 발견 **없음**. 전 테이블이 ①시스템 테이블(audit_logs, cell_*, database_outbox, file_ingestion_logs, graph_nodes/edges/sync_state) 또는 ②table_config.json 등재 동적 테이블로 분류됨.

관찰 사항(정리 대상 아님 — 사용자 config 소유):
- `parts`(0행)·`test`(0행)·`large_table_100`(1,000행, 성능 테스트 잔재 추정)는 모두 **table_config.json에 등재**된 동적 테이블. 제거하려면 DROP이 아니라 **사용자 config 편집 경로**(등재 해제)가 정도(正道) — 총괄·사용자 판단 사항으로 이관.

## 3. 코드 제거 내역 (확정 미사용분만)

| 파일 | 변경 |
|---|---|
| `server/database/models.py` | `class DataRow` 정의(인덱스 5종 포함) 삭제 → 폐기 주석으로 대체. 이후 `create_all`이 data_rows를 재생성하지 않음 |
| `server/database/database.py` | outbox 리스너 `auto_stage_database_outbox`에서 DataRow import·isinstance 분기 3곳 제거(동적 테이블 경로만 유지). `stage_event`의 DataRow 전용 JSON-blob else 분기(사경로) 제거 |
| `server/main.py` (~:117) | 기동 마이그레이션의 `UPDATE data_rows SET updated_at=...` 블록 제거(폐기 주석 대체). 후속 processed_chain/broadcast_at 블록 구조 불변 |
| `server/scripts/setup_db_performance.py` | Step 2(data_rows 전용 인덱스 5종 생성 루프)·`ANALYZE data_rows` 제거. 확장(pg_trgm/btree_gin)·outbox 인덱스·레거시 인덱스 DROP 단계는 유지 |
| `server/tests/conftest.py` | `DataRow` import + data_rows GIN 인덱스 스트립 방어 블록 제거 |
| `server/tests/test_composite_business_key.py` | 동일 방어 블록 제거 |

**의도적으로 남긴 것**:
- `schemas.py`의 `DataRowBase/Create/Response` — ORM 아닌 Pydantic 응답 스키마. `main.py:1552` GET `/tables/{t}/{row_id}`의 `response_model`로 현역(경계 계약 인접이라 개명 자제).
- `std_parser.py:206`의 `data_rows=` — 로그 문자열의 지역 변수명(파싱 행 수). 동음이의, 무관.
- 일회성 레거시 스크립트(`scripts/migrate_jsonb_to_rdb.py`·`migrate_to_postgres.py`, `migrations/migrate_jsonb_numeric.py`, `scratch/*`, `scripts/archive/*`) — `models.DataRow` 참조가 남아 실행 시 AttributeError가 나지만, 대상 테이블 자체가 폐기되므로 원래부터 defunct. **제안**: archive 밖의 2개(`migrate_jsonb_to_rdb.py`·`migrate_to_postgres.py`)를 `scripts/archive/`로 이동(총괄 승인 시 별도 수행).

## 4. 검증

- 전체 스위트: `conda run -n assy_manager python -m pytest server/tests/ -q` → **177 passed, 1 failed** — 실패는 기허용 `test_api.py::test_map_presets_api`(PROJECT_STATUS 이슈 #4, 본 변경 무관 기존 실패). 요구 조건(기허용 1건 외 green) 충족.
- 잔존 참조 전수 Grep 재확인: 런타임 경로(main/crud/workers/parsers/database) 0건.

## 5. 백업

- `agent_workspace/backup/graph_sync_statuses_20260725.csv` — **2,269행 덤프·행수 검증 완료**(UTF-8, 헤더 포함, 1000행 fetchmany 청킹).
- `data_rows`는 0행이므로 백업 생략(지시 기준: 행 있는 테이블만).

## 6. DROP 스크립트 (준비만 — 실행 금지 준수)

**파일**: `server/scripts/drop_legacy_tables_20260725.sql`

내용: `BEGIN; DROP TABLE IF EXISTS data_rows CASCADE; DROP TABLE IF EXISTS graph_sync_statuses CASCADE; COMMIT;` + 헤더 주석(대상·근거·백업 위치·`graph_sync_state` 보호 경고·사후 검증 쿼리).

**실행 절차·서버 영향**:
1. **선행 조건**: 본 코드 정리분이 커밋·반영된 후 DROP 실행. (모델 제거 전 코드로 프로세스가 재기동하면 `create_all`이 `data_rows`를 재생성 — 순서 역전 금지)
2. 실행: `psql -U postgres -d assy_manager -f server/scripts/drop_legacy_tables_20260725.sql`
3. **구동 중 서버 영향 없음** — 두 테이블 모두 어떤 프로세스도 접근하지 않아 락 경합·장애 위험 없음. DROP 자체는 무중단 가능.
4. **재기동**: DROP 때문에 필요하진 않음. 단, 코드 정리분(models/database/main) 반영에는 5-프로세스 재기동 1회 필요 — 평소 배포 재기동에 편승하면 충분.
5. 사후 검증: `pg_tables`에서 두 테이블 부재 + `graph_sync_state` 1행 생존 확인(스크립트 주석에 쿼리 수록).

## 7. 미해결 / 다음 단계

1. 총괄: 본 정리분 diff 검수 → 커밋 → DROP 스크립트 실행(§6 순서 엄수).
2. 총괄 승인 시: defunct 이관 스크립트 2건 archive 이동(§3 제안).
3. doc-keeper: CODE_MAP §5(models 정적 ORM 목록에서 DataRow 제거)·data_model.md(`DataRow` 행 삭제)·SYSTEM_OVERVIEW.md:104·event_driven_backend.md §2.1 경고문 갱신.
4. `parts`/`test`/`large_table_100` 처분은 사용자 config 결정 사항으로 별도 협의.

## 8. 히스토리 초안 (총괄 커밋 시 `docs/history/`에 등재 요망)

- 파일명 제안: `20260725_HHMMSS_drop_legacy_tables_data_rows_graph_sync_statuses.md`
- 요지: data_rows(0행)·graph_sync_statuses(2,269행) 미사용 확정(코드·git 전이력·사용자 영역 참조 0건) → DataRow ORM/기동 마이그레이션/outbox 리스너 분기/인덱스 셋업/테스트 방어코드 제거 → CSV 백업 → DROP 준비 스크립트. 스위트 177 passed(기허용 1 제외 green).
- ※ 조사·준비 단계(커밋 금지 지시)라 history 파일·gen_index 실행은 총괄 통합 시점으로 이월함.

## 9. 교훈 제안 (memory/server-pm.md 반영 검토 요청)

- **함정**: `Grep` 도구(ripgrep)는 .gitignore를 존중해 gitignored 사용자 영역이 전수 Grep에서 조용히 누락된다.
  **올바른 방법**: 사용자 영역(config/·mappers/·ingestion_workspace/)은 `rg --no-ignore`로 별도 명시 검색(패턴은 `-e` 플래그로 — `-E`는 인코딩 플래그라 파싱 에러).
- **함정**: DB에는 코드·git 전 이력에 없는 선사(先史) 고아 테이블이 존재할 수 있다(`graph_sync_statuses` 사례). 유사 명칭 현역 테이블(`graph_sync_state`)과 혼동 위험.
  **올바른 방법**: 테이블 정리는 pg_tables 전수 실측 → 코드+이력+사용자 영역 3중 참조 판정 → 유사명 현역 자산을 DROP 스크립트에 명시적 경고로 격리.
