# 경합 점검 수정 배치 1 — outbox 이중 발행 근절 · 이벤트 루프 격리 · payload 상한 · 7일 보관 정책

- **일시**: 2026-07-25
- **작업자**: Server PM (총괄 위임, 사용자 승인분)
- **근거**: `agent_workspace/reports/Server_contention_audit.md` (5-프로세스 경합 전수 점검, 실측 포함)

## 현상 (실측)

수십만 건 파일 인제션 + 다수 사용자 동시 사용 시나리오에서:
1. **[C-2]** 라이브 outbox에 동일 (tx,row,event) 중복 그룹 **1,259,076개** — 모든 데이터 이벤트가 ×2 발행.
2. **[C-1]** 웹서버 access 로그 약 **7초 공백**(이벤트 루프 동결) → 체인 통지 3s 타임아웃 → 스윕 오버 리프레시.
3. **[C-5]** 워처가 파일 전체 감사 로그(셀당 1건, 수십만~수백만 dict)를 메모리 누적 후 전량 HTTP POST.
4. **[C-3]** outbox 무한 보존 — 2,705,513행/4,862MB(DB의 44%) + 레거시 중복 인덱스 4종 429MB.

## 근본 원인

1. **C-2**: `parsers/directory_watcher.py`가 sys.path에 repo root를 넣고 `from server.database.database import ...`로 import — 나머지 전 프로세스는 `from database.database import ...`(server/ 기준). 동일 모듈이 서로 다른 이름으로 2회 로드되어 `@event.listens_for(Session, "before_flush")` 리스너가 **Session 클래스에 2중 등록** → flush마다 `stage_event` 2회 실행.
2. **C-1**: `main.py`의 다수 `async def` 핸들러가 동기 SQLAlchemy(`fetch_and_merge_metadata`, crud 배치, AuditLog 조회)와 O(행×컬럼) 병합 루프를 단일 이벤트 루프 위에서 직접 실행. `batch_delete`는 삭제 행별 `get_deleted_row_business_key` N+1 쿼리까지 루프 위에서 수행.
3. **C-5**: `_send_to_upsert`의 `all_created_logs` 누적·전송에 상한 부재(웹서버는 어차피 500건으로 절단).
4. **C-3**: 처리 완료 outbox의 purge 경로 부재 + `id`(pkey 중복)/`event_uuid`(미사용)/`status`/`processed_chain`(부분 인덱스로 대체됨) 비부분 인덱스 4종 잔존.

## 해결

### C-2 — import 경로 단일화 (`database.*`로 통일)
- `server/parsers/directory_watcher.py`: sys.path 삽입을 repo root → **server/** 로 수정, `server.database.*` → `database.*`, `server.parsers.pipeline_base` → `pipeline_base`(플러그인·run_watcher와 동일 모듈 정체성 — issubclass 불일치 잠재 결함도 함께 해소).
- `server/migrations/normalize_schema.py`: 동일 방식으로 통일(레포 전수 Grep 결과 `server.*` 접두 import 이 2개 파일뿐 — 수정 후 0건 확인).
- 회귀 가드: `tests/test_contention_fixes.py` — 리스너 1개 등록 + 행 1건 flush당 outbox 이벤트 1건.

### C-2 보완 — 구식 사용자 스크립트 하위호환 shim (총괄 검수 지적 반영)
- **문제**: gitignored 사용자 워크스페이스 스크립트 3개(`bonding_map_parser.py`, `inventory_master/scripts/custom_parser.py` 등)가 `from server.parsers.pipeline_base import ...`(+`html_topology_parser`)를 모듈 레벨에서 사용 — 새 sys.path 체계에서 그대로면 커스텀 파서 인제션 전면 실패. 사용자 스크립트는 무수정 원칙.
- **해법**: `directory_watcher._register_legacy_import_shim()` — 플러그인 로드 직전(`_discover_and_execute_pipeline`) sys.modules에 **동일 객체 별칭** 등록. dotted 완전명은 sys.modules 조회가 `__path__` 탐색·meta_path보다 우선하므로, 구식 import가 top-level 정본과 **정확히 같은 모듈 객체**를 받는다(issubclass 정체성 유지, 이중 로드 원천 불가).
- **별칭 목록**: `server.parsers.pipeline_base`→`pipeline_base`, `server.parsers.html_topology_parser`→`html_topology_parser`(실사용 2종, 워크스페이스 전수 조사) + `server.database`/`.database`/`.models`/`.crud`/`.schemas`→top-level 동일 모듈(방어적 — 아래 발견 때문).
- **환경 발견**: conda env에 프로젝트가 **pip editable 설치**되어 있어(`__editable___assy_manager_0_1_0_finder._EditableFinder`가 sys.meta_path 상주) `server.*` import가 부모 `__path__`와 무관하게 항상 실 파일로 해석됨 — 더미 패키지 빈 `__path__`로 '차단'은 불가. 따라서 리스너 보유 모듈(`server.database.*`)까지 별칭으로 선점해 어떤 경로로 import돼도 단일 객체가 되도록 **중화** 전략 채택. (editable finder는 C-2 재발의 환경적 기여 요인 — 검수 포인트로 보고.)
- **검증**: 실제 워크스페이스 스크립트를 discovery 경로 그대로 로드 — `BasePipelineParser` 동일 객체 True, 구식 스크립트의 파서 2종 issubclass 직격 성립, database 이중 로드 없음. 회귀 테스트 `test_legacy_server_parsers_import_shim`(임시 구식 플러그인 spec-load → 동일 객체 + `server.database.database` import 시에도 동일 객체 보장) 추가.
- **문서**: `docs/guide/INGESTION_GUIDE.md` §2에 신규 스크립트 top-level import 권장 + 구식 경로 shim 동작 명시.

### C-1 — 이벤트 루프 격리
- `PUT /tables/{t}/data/updates`: `fetch_and_merge_metadata` + msg_items 빌드를 `run_in_threadpool` 클로저로 이관 (`main.py` `_merge_and_build_items`).
- `POST /rows/batch_delete`: 행별 N+1 → `get_deleted_rows_business_keys_bulk`(1000행 청킹, IN 쿼리 2회, 기존 행별 함수와 동일 의미론) + 삭제·조회 전체 threadpool 격리.
- 동일 패턴 일괄 적용: `POST /rows`(create), `DELETE /rows/{id}`, priority 단건/배치, sources delete 단건/배치.
- await 없는 핸들러 `def` 전환: `GET .../sources`, `GET .../history`, `POST /admin/auto-update/run-now`.
- `/internal/events/batch-refresh`·`/broadcast`: `audit_cache.add_logs_batch`(pydantic 검증)·`json.dumps`를 threadpool로 이관.

### C-5 — 워처 통지 payload 상한 (경계 계약 불변)
- `directory_watcher.MAX_NOTIFY_CREATED_LOGS = 500`: 누적 자체를 상한 절단(메모리 O(500) 고정), 실제 총 건수는 `total_log_count`로 별도 집계.
- 콜백 4번째 인자 `total_log_count` 추가(run_watcher·main.py 임베디드·retry 경로 3곳 기본값 있는 시그니처로 갱신) → `/internal/events/batch-refresh`가 `total_log_count`(optional Body)를 수용, audit_cache `override_total_count`에 사용. **WS 이벤트명·`created_logs` 필드 형태는 불변**(항목 수만 제한) — 클라이언트(websocket.js) 무변경.

### C-3 — 7일 보관 정책 + 인덱스 정리
- `chain_ingestion_worker.purge_expired_outbox_sync`: `processed_chain=true AND created_at < now()-7d` 행을 1000행 청킹 DELETE(사이클당 50청크 상한). 기동 직후 1회 + 1시간 주기, `asyncio.to_thread` 백그라운드 발사(폴링 루프 비블로킹), 별도 세션. 미처리 행은 절대 삭제 안 함.
- `models.py`: `idx_outbox_purge`(`(created_at) WHERE processed_chain=true`)·`idx_outbox_failed`(`(status,id) WHERE status='FAILED'` — 비부분 status 인덱스 DROP 대체) 부분 인덱스 추가, `id`/`status`의 `index=True` 및 `event_uuid`의 `unique/index` 선언 제거.
- `scripts/setup_db_performance.py`: 신규 인덱스 2종 생성 + 레거시 4종 멱등 `DROP INDEX CONCURRENTLY IF EXISTS`(대체 인덱스 생성 이후 실행).
- `scripts/purge_outbox_backlog.py`(신규, 수동 실행 전용): 기존 백로그 270만 행 정리 — dry-run 지원, 청킹 DELETE, ANALYZE. 라이브 자동 실행 없음.

## 검증

- `conda run -n assy_manager python -m pytest server/tests/ -q` → **59 passed, 1 failed** (기존실패 `test_map_presets_api`만 — 본 작업과 무관, 불변).
- 신규 테스트 9건(`test_contention_fixes.py`): C-2 리스너 1개·이벤트 1건·하위호환 shim 동일 객체, C-1 벌크 BK 의미론 동등성·batch_delete 스모크, C-5 500건 상한+total_log_count, C-3 보관기간·미처리 보호·청킹 상한.
- 단독 재현 스크립트로 directory_watcher import 후 `server.database.database` 미로드 + 리스너 1개 실측 확인.
- 라이브 DB 무변경(읽기만) — DDL·백로그 정리는 스크립트로만 제공(사용자 실행).

## 부수 발견 (별도 태스크로 분리)

- `crud.delete_rows_batch`가 `create_audit_log(add_to_cache=False)`로 호출 → 이 플래그가 DB persist까지 생략하여 **배치 삭제의 DELETE 감사 로그가 DB에 저장되지 않음**(인메모리 캐시에만 존재, 재시작 시 소실). batch_delete 엔드포인트의 created_logs 블록은 항상 빈 결과. → spawn_task로 등록.

## 후속 제안 (미수정 — 점검 보고서 C-4·C-6~C-11 및 잔여)

- `/internal/events/broadcast`의 요청 body JSON 파싱은 여전히 루프 위(FastAPI Body) — 체인 워커의 `created_logs` 무상한 전송(C-5의 체인측 대응물)과 함께 후속 검토.
- PUT `async_broadcast` 내 `json.dumps`(≤5000 로그 바운드) 및 audit `/recent`의 N+1은 저위험으로 보류.
