# Server 경합 수정 배치 1 — 완료 보고서

> **작성:** Server PM · 2026-07-25 (총괄 검수 보완 반영 rev.2) | **근거:** [Server_contention_audit.md](./Server_contention_audit.md) | **승인 범위:** C-2 · C-1 · C-5 · C-3 (사용자 승인분만, 확장 없음)
> **검증:** `conda run -n assy_manager python -m pytest server/tests/ -q` → **59 passed, 1 failed**(기존실패 `test_map_presets_api`만 — 무관·불변). 신규 테스트 9건 전부 통과. 커밋·스테이징 없음. 라이브 DB 무변경(DDL·정리는 스크립트 제공, 사용자 실행). 사용자 워크스페이스 스크립트 무수정.

---

## 1. C-2 — outbox ×2 중복 발행 근절 (최우선)

### 통일 방향과 근거
**bare `database.*` 경로(sys.path에 `server/`)로 통일.** 레포 전수 Grep 결과 `server.*` 접두 import는 단 2개 파일 — `parsers/directory_watcher.py`(라이브 프로세스에 로드됨 — 진범)와 `migrations/normalize_schema.py`(일회성 스크립트). 라이브 5-프로세스(main.py, run_watcher.py, run_chain_worker.py, run_graph_sync.py, run_auto_update.py)와 테스트(conftest.py) **전부**가 이미 bare 경로를 쓰므로, 2개 파일을 맞추는 쪽이 유일하게 안전한 방향이다(역방향은 수십 개 파일 + 전 프로세스 기동 스크립트 수정 필요).

### 수정 내역
| 파일:위치 | 내용 |
|---|---|
| `server/parsers/directory_watcher.py:8-19` | sys.path 삽입을 repo root → `server/`로 수정 + 재도입 금지 경고 주석 |
| 같은 파일 (구 :14-15, :148, :168) | `server.database.*` → `database.*` (SessionLocal, crud, schemas, FileIngestionLog ×2) |
| 같은 파일 (구 :289, :399) | `server.parsers.pipeline_base` → `pipeline_base` — 플러그인·run_watcher와 **동일 모듈 정체성** 확보(기존 issubclass 불일치를 MRO 이름 비교로 우회하던 잠재 결함도 함께 해소) |
| `server/migrations/normalize_schema.py:21-28` | 동일 통일 (부수: 기존엔 `server.database.crud` 로드 시 crud 내부의 `from database.context import`가 해석 불가라 사실상 실행 불가 상태였음 — 통일로 실행 가능해짐) |

수정 후 레포 전수 Grep `from server\.|import server\.` → **0건** (추적 파일 기준).

### 하위호환 shim (총괄 검수 지적 반영 — gitignored 사용자 스크립트 무수정 원칙)
- **문제**: gitignored 워크스페이스 스크립트 3개(`bonding_map/scripts/bonding_map_parser.py:3-4`, `inventory_master/scripts/custom_parser.py:3`)가 `from server.parsers.pipeline_base import BasePipelineParser`(+ `server.parsers.html_topology_parser`)를 모듈 레벨 사용 — 새 sys.path 체계 그대로면 커스텀 파서 인제션 전면 실패.
- **shim 방식**: `directory_watcher._register_legacy_import_shim()` — `_discover_and_execute_pipeline`의 `pipeline_base` import 직후 호출(멱등). sys.modules에 **동일 객체 별칭**을 등록: dotted 완전명은 sys.modules 조회가 `__path__` 탐색·meta_path보다 우선하므로, 구식 import가 top-level 정본과 **같은 모듈 객체**를 받는다 → issubclass 정체성 유지 + 이중 로드(리스너 2중 등록) 원천 불가.
- **별칭 목록** (워크스페이스 전수 조사 기반):
  | 구식 dotted 이름 | 별칭 대상 (top-level) | 근거 |
  |---|---|---|
  | `server.parsers.pipeline_base` | `pipeline_base` | 실사용 2개 파일 |
  | `server.parsers.html_topology_parser` | `html_topology_parser` | 실사용 1개 파일 (선택 의존 — 실패 시 경고 후 생략) |
  | `server.database` / `.database` / `.models` / `.crud` / `.schemas` | `database` / 동일 하위 모듈 | 실사용 0건이나 **방어적 선점** (아래 환경 발견) |
  | 더미 패키지 `server`, `server.parsers` | `types.ModuleType`, `__path__=[]` | dotted 별칭 해석용 (기존 로드분 있으면 재사용) |
- **환경 발견 (검수 중 확인)**: conda env에 본 프로젝트가 **pip editable 설치**되어 있어(`__editable___assy_manager_0_1_0_finder._EditableFinder`가 sys.meta_path 상주) `server.*` import는 부모 `__path__`와 무관하게 **항상 실 파일로 해석**된다. 즉 더미 패키지의 빈 `__path__`로는 '차단' 불가 → 리스너 보유 모듈(`server.database.*`)까지 별칭 선점하는 '중화' 전략을 채택했다. 어떤 스크립트가 어떤 경로로 import해도 단일 객체가 보장된다.
- **검증**: ① 실제 워크스페이스 구식 스크립트를 discovery 경로 그대로 로드 — 로드 성공, `BasePipelineParser` 동일 객체 True, 구식 파서 2종(CustomHtmlIngestionParser·STDIngestionParser) issubclass **직격** 성립(MRO 이름 비교 fallback 불요), database 이중 로드 없음. ② 회귀 테스트 `test_legacy_server_parsers_import_shim`: 임시 구식 플러그인 spec-load(실제 플러그인 로드 방식 동일) → `BasePipelineParser is pipeline_base.BasePipelineParser` + `server.database.database`/`server.database.crud` import 시에도 top-level과 동일 객체.
- **문서**: `docs/guide/INGESTION_GUIDE.md` §2 — 신규 스크립트 top-level import 권장 + 구식 경로는 shim으로 동작 명시.

### 회귀 방지 테스트 (`server/tests/test_contention_fixes.py`)
- `test_before_flush_listener_registered_once`: directory_watcher import 후 ① `server.database.database`가 별도 모듈로 sys.modules에 없음 ② Session dispatch의 `auto_stage_database_outbox` 리스너 **정확히 1개**.
- `test_outbox_event_staged_exactly_once`: 동적 테이블 행 1건 flush → outbox 이벤트 **정확히 1건** (점검 보고서의 실측 증상 그 자체를 가드).
- 단독 재현 스크립트로도 확인: 수정 후 listeners = `['auto_stage_database_outbox']` 1개, `server.database.database` 미로드.

---

## 2. C-1 — 웹서버 이벤트 루프 동결 격리

### 필수 2건
| 지점 | 수정 |
|---|---|
| `main.py` PUT `/tables/{t}/data/updates` (구 :1665) | `fetch_and_merge_metadata` + msg_items 빌드(O(행×컬럼) 루프, ORM 속성 접근→잠재 lazy-load)를 `_merge_and_build_items` 클로저로 묶어 `run_in_threadpool` 이관 — 기존 :1653 업서트 격리 패턴 준용 |
| `main.py` POST `/rows/batch_delete` (구 :1145) | 삭제 행별 `get_deleted_row_business_key` N+1 → 신규 `get_deleted_rows_business_keys_bulk`(1000행 청킹, business_key 직접 조회 + key_col new_value fallback의 IN 쿼리 2회 — 기존 행별 함수와 의미론 동일) + 삭제·조회 전체를 threadpool 클로저로 격리 |

### 저위험 일괄 격리 (같은 패턴 적용)
- threadpool 클로저 격리: `POST /rows`(create, 구 :1592), `DELETE /rows/{id}`(구 :1116), `PUT .../priority`(단건, 구 :1891), `PUT /cells/priority/batch`(구 :1953·:1964), `DELETE .../sources/{s}`(구 :1868), `POST /cells/sources/delete/batch`(구 :2017·:2028).
- await 없는 핸들러 `async def`→`def` 전환(FastAPI가 threadpool 실행): `GET .../sources`(구 :1825), `GET .../cells/{c}/history`, `POST /admin/auto-update/run-now`(구 :2723).
- `/internal/events/batch-refresh`·`/internal/events/broadcast`(구 :2787): `audit_cache.add_logs_batch`(pydantic 검증 CPU 바운드)와 `json.dumps`를 threadpool 이관.

### 목록화만 (후속 제안 — 과공학 회피)
- `/internal/events/broadcast`의 **요청 body JSON 파싱**은 여전히 루프 위(FastAPI `Body` 파싱) — C-5로 워처발 대형 body는 사라졌으나, **체인 워커가 `created_logs`를 무상한 동봉**(chain_ingestion_worker :386·:395)하는 잔여 경로가 있음. 체인측 상한(승인 범위 밖)과 함께 수정 배치 2 후보.
- PUT `async_broadcast` 내 `json.dumps`(created_logs ≤5000 바운드)·`GET /audit_logs/recent` 캐시 미스 시 N+1 — 저위험 보류.

---

## 3. C-5 — 워처 최종 통지 payload 상한

**경계 계약 유지 확인: 형태 불변.** `client2/src/websocket.js:101`은 `msg.created_logs || []`를 배열로 소비하고 `batch_refresh_required`(:238)는 전체 refetch 트리거 — **항목 수만 제한하면 클라이언트 무영향**. 에스컬레이션 불요.

- `directory_watcher.py`: `MAX_NOTIFY_CREATED_LOGS = 500`(웹서버측 절단 상한과 동일값). **누적 자체를 절단**해 워처 메모리도 O(500) 고정. 실제 총 건수는 `total_log_count`로 별도 집계.
- 콜백 시그니처에 `total_log_count` 4번째 인자 추가 — 소비처 3곳 전수 갱신(기본값 있는 파라미터): `run_watcher.trigger_ws_refresh`, `main.py` 임베디드 `trigger_ws_refresh`(:190), `main.py` retry `sync_refresh_callback`(:2628).
- `/internal/events/batch-refresh`에 optional `total_log_count` Body 추가(서버 내부 계약 — 클라이언트 무관, 구버전 워처 호환 유지). audit_cache `override_total_count`에 사용해 히스토리 패널의 트랜잭션 total_count 표기가 절단과 무관하게 정확.
- 테스트: 1200행 인제션 시뮬레이션 → 통지 로그 500건 + total 1200 (`test_watcher_created_logs_capped_at_500`), 엔드포인트 수용 스모크.

---

## 4. C-3 — outbox 7일 보관 정책

### purge 설계 (판단 근거 포함)
- **실행 주체**: 체인 워커 루프 내 저빈도 태스크(`purge_expired_outbox_sync`) — 기동 직후 1회(다운타임 백로그 소화) + **1시간 주기**. 전달 기한이 없는 유지보수 작업이므로 `asyncio.create_task(asyncio.to_thread(...))` 백그라운드 발사(+done 가드) — 인라인 통지와 달리 기아가 무해하고, 폴링 루프(SLO 100ms 경로)를 purge가 블로킹하지 않는다.
- **세션**: 스윕·메인 세션과 **격리된 별도 짧은 세션**(`_stamp_broadcast_at_sync` 패턴 준용) — 청크마다 commit해 락 보유시간 최소화. 재사용하지 않는 이유: purge는 별 스레드에서 돌므로 메인 세션 공유는 스레드 안전 위반.
- **조건**: `processed_chain = true AND created_at < now() - 7d`. 처리시점 컬럼(processed_at)은 워커가 채우지 않아 신뢰 불가 — 정상 운영에서 처리는 생성 후 수 초 내이므로 created_at이 안전한 보수적 proxy(백로그 복구 중 처리가 늦은 행은 그만큼 더 오래 보존됨). **미처리 행은 나이 무관 절대 보호.**
- **확장성**: 1000행 청킹 + 사이클당 50청크(5만 행) 상한 + 부분 인덱스 `idx_outbox_purge`(`(created_at) WHERE processed_chain=true`) — 삭제 대상 0건일 때도 인덱스만 스치고 끝나 1000만 행 안전.
- 테스트: 보관기간·미처리 보호(`test_outbox_purge_deletes_only_expired_processed_rows`), 청킹 상한·이월(`test_outbox_purge_respects_chunk_cap`).

### 레거시 인덱스 4종 (429MB)
- `setup_db_performance.py` Step 3.5: `DROP INDEX CONCURRENTLY IF EXISTS` ×4 (멱등, **대체 인덱스 생성 이후** 실행) — `ix_database_outbox_id`(pkey 완전 중복 124MB)·`ix_database_outbox_event_uuid`(조회처 전무 224MB)·`ix_database_outbox_status`(44MB)·`ix_database_outbox_processed_chain`(37MB).
- `models.py` 선언 동기화: `id`/`status`의 `index=True`, `event_uuid`의 `unique/index` 제거(신규 DB 재생성 방지). status 대체로 부분 인덱스 `idx_outbox_failed`(`(status,id) WHERE status='FAILED'`) 신설 — `/admin/outbox/failed`·`retry-failed`의 FAILED 조회가 인덱스를 잃지 않도록.

### 기존 백로그(270만 행) 판단
**자연 소화 불가 → 별도 정리 스크립트 제공.** 주기 purge는 사이클당 5만 행 상한이라 270만 행 소화에 ~54시간(그동안 워커 purge가 계속 대량 삭제를 수행) — 오프피크 일괄 정리가 낫다. `scripts/purge_outbox_backlog.py`(신규, **수동 실행 전용**): dry-run 지원, 1000행 청킹, 진행 출력, 종료 시 ANALYZE. 라이브 프로세스는 절대 자동 실행하지 않음. 공간 실반환은 VACUUM 안내(일반 VACUUM = 무중단 재사용 회수 / VACUUM FULL = 완전 반환이나 ACCESS EXCLUSIVE — 사용자 선택).

---

## 5. 수정 파일 전체 목록

| 파일 | 변경 |
|---|---|
| `server/parsers/directory_watcher.py` | C-2 import 통일 + 하위호환 shim(`_register_legacy_import_shim`) + C-5 상한·total_log_count |
| `server/migrations/normalize_schema.py` | C-2 import 통일 |
| `server/run_watcher.py` | C-5 콜백 시그니처 + total_log_count 전달 |
| `server/main.py` | C-1 threadpool 격리 11개 지점 + `get_deleted_rows_business_keys_bulk` 신설 + C-5 콜백 2곳·내부 엔드포인트 |
| `server/chain_ingestion_worker.py` | C-3 `purge_expired_outbox_sync` + 루프 훅(1h 주기·백그라운드) |
| `server/database/models.py` | C-3 인덱스 선언 정리 + `idx_outbox_purge`/`idx_outbox_failed` |
| `server/scripts/setup_db_performance.py` | C-3 신규 인덱스 2종 + 레거시 4종 멱등 DROP |
| `server/scripts/purge_outbox_backlog.py` | 신규 — 백로그 수동 정리 |
| `server/tests/test_contention_fixes.py` | 신규 — 회귀 테스트 9건 |
| docs: `history/20260725_090000_contention_fix_batch1.md`(+gen_index), `architecture/event_driven_backend.md` §2.1·§2.3, `architecture/backend.md` §1.1·§1.2, `guide/INGESTION_GUIDE.md` §2, `process/PROJECT_STATUS.md` | 문서 동기화 |

## 6. 총괄 검수 포인트

1. **event_uuid 유일 제약 제거**(C-3): 인덱스 224MB 절감을 위해 unique 인덱스와 모델 선언을 함께 제거. 조회처·ON CONFLICT 의존 전무(전수 Grep), uuid4 충돌은 통계적으로 무시 가능 — 다만 **정합성 계약의 완화**이므로 명시 승인 요망.
2. **FAILED 격리 행도 7일 후 삭제**됨 → 수동 재시도(`/admin/outbox/retry-failed`) 유예가 7일로 제한. 운영 수칙으로 문서화함(event_driven_backend §2.3).
3. C-5의 `total_log_count`는 서버 내부 계약(워처→웹서버)의 **additive optional 필드** — 클라이언트 WS 페이로드는 불변. 클라이언트 확인 필요 시 Client PM에 통지만.
4. 부수 발견: **배치 삭제 DELETE 감사 로그 DB 미저장**(crud.delete_rows_batch의 add_to_cache=False가 persist까지 생략) — 범위 밖이라 미수정, 태스크 칩 발행 + PROJECT_STATUS #6 등재.
5. 잔여 리스크(C-4·C-6~C-11 + 체인 created_logs 무상한)는 PROJECT_STATUS #5로 등재 — 수정 배치 2 승인 대상.
6. **환경 리스크: 프로젝트 pip editable 설치** — conda env의 `_EditableFinder`가 `server.*` import를 어디서든 해석 가능하게 만들어 C-2류 이중 로드의 환경적 기여 요인. shim 별칭이 핵심 모듈을 중화하나, 근본적으로는 editable 설치 제거(`pip uninstall assy-manager`) 여부를 사용자와 협의 권장(다른 워크플로우가 의존할 수 있어 단독 결정 부적절).

## 7. 사용자 운영 액션 (순서 중요)

```
0) C-2 반영 코드로 전 프로세스 재기동  ← 신규 중복 유입 차단이 선행돼야 함
1) conda run -n assy_manager python server/scripts/setup_db_performance.py
   (레거시 인덱스 4종 DROP → 이후 대량 DELETE의 인덱스 유지비 절감 + purge/failed 인덱스 생성)
2) conda run -n assy_manager python server/scripts/purge_outbox_backlog.py --dry-run   # 대상 확인
3) conda run -n assy_manager python server/scripts/purge_outbox_backlog.py             # 본실행 (오프피크 권장)
4) 오프피크에 VACUUM (ANALYZE) database_outbox;
   (디스크 공간 완전 반환이 필요하면 VACUUM FULL — ACCESS EXCLUSIVE, 전 프로세스 중지 후)
```
이후 7일 보관은 체인 워커가 자동 유지(시간당 소량 삭제).
