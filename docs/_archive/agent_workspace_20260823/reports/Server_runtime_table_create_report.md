# 보고서: 이슈 #7 — 런타임 신규 테이블 물리 CREATE 누락 해소

- 발신: Server PM / 수신: 총괄 PM
- 지시서: `agent_workspace/tasks/Server_runtime_table_create_task.md`
- 상태: **구현 완료 / 전체 스위트 green(기허용 1건 제외) / 미커밋(총괄 검수 대기)**

## 1. 원인 진단

- 부팅 경로(웹서버 main.py, run_watcher, run_chain_worker, run_graph_sync)만
  `Base.metadata.create_all` + `sync_dynamic_tables_schema(engine)`를 수행.
- 런타임 리로드 경로는 셋 다 물리 CREATE가 없었다:
  1. `reload_local_process_cache()`(main.py): `load_table_config()` 반환값을 **버리는 사실상
     no-op** — TABLE_CONFIG 싱글턴 갱신도, ORM 등록도 안 하고 모듈 캐시만 비움.
     (ORM 등록이 그동안 됐던 것은 config watchdog 스레드의 우연한 타이밍 덕.)
  2. `config_watcher` 핸들러: `init_dynamic_models` + `sync_dynamic_tables_schema`를 하지만
     후자는 `if not inspector.has_table: continue` — **존재하는 테이블의 ALTER 전용**이라
     신규 테이블은 영원히 스킵.
  3. 워커 SYSTEM_RELOAD 핸들러(run_watcher 폴러 / chain 루프): 모듈 캐시 무효화만 수행,
     모델·물리 스키마 무관여.

## 2. 설계 결정 (지시서 주의사항 4건 대응)

- **DDL 소유권**: 웹서버가 1차 CREATE 소유자 — `/admin/reload-configs`가 outbox 발화 **전에**
  동기적으로 CREATE하므로, 워커가 SYSTEM_RELOAD를 볼 시점엔 보통 테이블이 이미 존재.
  watcher/chain 워커는 게이트+checkfirst로 무해화된 **보충 안전망**(웹서버 CREATE 실패,
  직접 파일 편집 후 watchdog 유실 등 대비)이자 모델 캐시 정합 확보 수단. (주의 3·4)
- **트랜잭션 오염 방지**: `inspector.has_table`(information_schema) 게이트로 존재 테이블엔
  DDL 미발행 + `create_all(bind=engine, ..., checkfirst=True)`는 engine 자체 커넥션의 독립
  트랜잭션이라 실패 시 자체 rollback — 공유 세션 무오염. 테이블별 try/except 격리. (주의 1)
- **C-8 비악화**: 신규 테이블 CREATE만 수행. 기존 테이블 런타임 ALTER는 추가하지 않음
  (`sync_dynamic_tables_schema`의 기존 호출처는 그대로, 신규 호출 추가 없음). (주의 2)
- **동일 프로세스 경합**: 웹서버는 watchdog 스레드와 reload-configs 요청 스레드가 동시 진입
  가능 → `models._runtime_ddl_lock`(threading.Lock)으로 in-process 직렬화.

## 3. 변경 함수 / 시그니처 목록 (코드맵 갱신용 — doc-keeper 전달)

| 파일 | 함수 | 변경 |
|---|---|---|
| `server/database/models.py` | `create_missing_dynamic_tables(engine) -> list[str]` | **신규** (~L313) — 신규 테이블 한정 물리 CREATE, 게이트+checkfirst+락 |
| `server/database/models.py` | `refresh_dynamic_models(engine=None) -> list[str]` | **신규** (~L354) — 핫리로드 공용 진입점(config 재로드→싱글턴→ORM→CREATE) |
| `server/database/models.py` | `_runtime_ddl_lock` | **신규** 모듈 전역 threading.Lock |
| `server/main.py` | `reload_local_process_cache()` | **수정** — no-op config 로드를 `models.refresh_dynamic_models(engine)`로 교체(시그니처 불변) |
| `server/database/config_watcher.py` | `ConfigChangeHandler.on_modified` | **수정** — engine 분기에서 `create_missing_dynamic_tables` 선(先)호출 후 기존 sync |
| `server/run_watcher.py` | `poll_pending_retries()` SYSTEM_RELOAD 블록 | **수정** — `refresh_dynamic_models(engine)` 삽입(sync_new_workspaces 직전) |
| `server/chain_ingestion_worker.py` | 워커 루프 SYSTEM_RELOAD 블록 (~L829) | **수정** — `refresh_dynamic_models(engine)` 삽입(지연 import) |
| `server/tests/test_runtime_table_create.py` | 테스트 4건 | **신규 파일** |

경계 계약(REST/WS/셀 형태/스키마 계약) **불변** — 추가 공개 API 없음, 기존 시그니처 무변경.
전수 Grep(gitignored 사용자 영역 포함) 결과 신규 함수명 충돌·외부 호출처 없음.

## 4. 검증

- 신규 회귀 4건 (`server/tests/test_runtime_table_create.py`, 테이블명 `rtct_*` — 사용자
  config 충돌 불가 접두, 교훈 파일 준수):
  1. `test_create_missing_dynamic_tables_creates_only_new` — ORM만 등록된 상태에서 조회
     실패(OperationalError, 버그 재현) → CREATE 후 즉시 조회 성공, 기존 테이블 스킵, 멱등.
  2. `test_refresh_dynamic_models_hot_reload_then_query_200` — E2E: 404 → config 추가 →
     리로드 → `GET /tables/{t}/data` **200**, 기존 테이블 무손상.
  3. `test_refresh_dynamic_models_guards_empty_config` — 빈/손상 config가 싱글턴을 지우지 않음.
  4. `test_refresh_dynamic_models_without_engine_skips_ddl` — engine=None은 ORM만, DDL 없음.
- 전체 스위트: `conda run -n assy_manager python -m pytest server/tests/ -q`
  → **119 passed, 1 failed** (실패 = 기허용 `test_map_presets_api`).
- 편집 5개 파일 `py_compile` 통과.

## 5. 라이브 검증 절차 (총괄 수행)

1. 5-프로세스 기동 상태에서 `server/config/table_config.json`에 임시 테이블
   (예: `live_test_issue7`, business_key + 컬럼 1~2개) 추가.
2. 어드민에서 reload(`POST /admin/reload-configs`) 실행.
3. **재기동 없이** `GET /tables/live_test_issue7/data` → 200(빈 목록) 확인
   (수정 전엔 UndefinedTable 500).
4. 서버 로그에서 `[Schema Sync] Created missing physical table 'live_test_issue7'` 1회 확인,
   watcher/chain 로그엔 CREATE 없이 게이트 스킵(무로그)인지 확인 — 중복 DDL 없음 검증.
5. `ingestion_workspace/live_test_issue7/` 자동 생성 + raws/ 파일 드롭 인제션 정상 확인(선택).
6. 정리: config에서 테이블 제거 + `DROP TABLE live_test_issue7` + 워크스페이스 폴더 삭제.

## 6. 미해결 / 다음 단계

- **graph_sync 워커**: SYSTEM_RELOAD 경로·config watcher가 원래 없어 신규 테이블을 재기동
  전까지 모름 — 그래프 동기화 지연일 뿐 500은 아니므로 이번 범위에서 제외. 별도 이슈 등재
  권고(DYNAMIC_TABLES 순회 중 watchdog 뮤테이션 동시성 검토 필요해 단순 1줄 추가로는 위험).
- 리빙 문서: `event_driven_backend.md`의 SYSTEM_RELOAD 흐름 설명에 "신규 테이블 물리 CREATE
  포함" 1줄 반영 필요 — doc-keeper 전담이라 본 보고서로 이관.
- 히스토리 기록 완료: `docs/history/20260725_170000_issue7_runtime_table_create.md` +
  인덱스 재생성(188건). PROJECT_STATUS 이슈 #7 종결 처리는 총괄 몫.

## 7. 교훈 제안 (총괄 검수 후 memory/server-pm.md 반영)

- **함정**: `sync_dynamic_tables_schema`는 이름과 달리 **존재하는 테이블의 ALTER 전용**
  (`has_table` 아니면 continue) — "스키마 동기화" 호출만 믿으면 신규 테이블 CREATE가 조용히
  누락된다. **올바른 방법**: 신규 테이블은 `create_missing_dynamic_tables`(게이트+checkfirst)
  경로임을 구분해서 배선할 것.
- **함정**: 웹서버 `reload_local_process_cache`류의 "리로드" 함수가 반환값을 버리는 no-op일
  수 있다 — watchdog 스레드가 우연히 메워주면 증상이 늦게 드러난다. **올바른 방법**: 리로드
  경로는 단일 공용 진입점(`refresh_dynamic_models`)으로 수렴시키고 결정적(동기) 경로를 1차로.
