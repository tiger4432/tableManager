# 이슈 #7 수정 — 런타임 신규 테이블 물리 CREATE 누락 해소

- **일시:** 2026-07-25 17:00
- **주체:** Server PM (총괄 지시서 `Server_runtime_table_create_task.md`)
- **영역:** server (models/config_watcher/main/run_watcher/chain_ingestion_worker + tests)
- **커밋:** (미커밋 — 총괄 검수 후 커밋 예정)

## 무엇이 바뀌었나

`table_config.json`에 신규 테이블 추가 후 핫리로드하면 ORM 등록·`/tables` 노출·워크스페이스
생성은 되지만 물리 `CREATE TABLE`은 부팅 스키마 동기화에서만 수행되어, 재기동 전까지 해당
테이블 조회가 `UndefinedTable` 500이었다(2026-07-25 enrichment 스모크 실측).

- **신규** `models.create_missing_dynamic_tables(engine)`: DYNAMIC_TABLES 중 물리 DB에 없는
  **신규 테이블만** CREATE. information_schema 게이트(`inspector.has_table`) + `checkfirst=True`
  + engine 단위 독립 트랜잭션(실패 자체 rollback, 테이블별 격리) + in-process DDL 락
  (watchdog 스레드 vs reload-configs 요청 스레드 동시 진입 직렬화). 기존 테이블 ALTER는
  **범위 밖**(C-8 런타임 ALTER 락 컨보이 방지).
- **신규** `models.refresh_dynamic_models(engine=None)`: 핫리로드 공용 진입점 —
  config 디스크 재로드 → `crud.TABLE_CONFIG` 싱글턴 갱신(빈/손상 config 시 기존 보존) →
  `init_dynamic_models` → engine 지정 시 물리 CREATE.
- **배선(4곳)**: ① 웹서버 `reload_local_process_cache()`(/admin/reload-configs 동기 경로 —
  1차 CREATE 소유자) ② `config_watcher` 핸들러 engine 분기(직접 파일 편집 경로) ③
  `run_watcher` SYSTEM_RELOAD 폴러 ④ `chain_ingestion_worker` SYSTEM_RELOAD 블록
  (③④는 게이트+checkfirst로 무해한 보충 안전망 + 모델 캐시 정합 확보).

## 검증

- 신규 회귀 테스트 `server/tests/test_runtime_table_create.py` 4건: 신규만 CREATE·멱등성,
  리로드→즉시 API 200 E2E, 빈 config 가드, engine=None 무DDL 경로.
- 전체 스위트 `conda run -n assy_manager python -m pytest server/tests/ -q`:
  **119 passed / 1 failed** — 실패는 기허용 `test_map_presets_api`(사용자 maps.json 의존) 1건뿐.

## 잔여/미해결

- graph_sync 워커는 SYSTEM_RELOAD 경로/ config watcher가 원래 없어 신규 테이블 모델을
  재기동 전까지 모름(그래프 동기화 지연일 뿐 500 아님) — 별도 이슈로 보드 등재 검토.
- 경계 계약 불변(REST/WS/셀 형태/스키마 계약 무변경). 코드맵 갱신은 doc-keeper 전담.
