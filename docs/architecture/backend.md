# 🖥️ Backend Architecture

> **Status:** 🟢 Living | **Last-verified:** 2026-07-27 (HEAD `be58210` — 프로세스 감시·헬스 신설) | **Owner:** Backend / Sync
> **Source-of-truth:** `server/main.py`, `server/database/crud.py`, `server/*_worker.py`, `server/run_*.py`, `server/map_overlay.py`, `server/transfer_plan.py`, `server/process_supervisor.py`, `server/health.py`, `server/utils/heartbeat.py`, `server/paths.py`
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md)

---

> 이벤트 기반 흐름(Outbox staging·체인·그래프)의 심화 설명은 [event_driven_backend.md](./event_driven_backend.md) 참조.

## 1. 멀티프로세스 설계

FastAPI 웹서버(`main.py`)는 API + WebSocket 허브이고, 무거운 작업은 별도 데몬으로 분리됩니다. 조정은 PostgreSQL **Transactional Outbox** 패턴으로 이루어집니다.

- **Outbox 테이블** `database_outbox` — 이벤트를 트랜잭션과 함께 커밋해 유실 없이 전달.
- **LISTEN/NOTIFY** 채널 `outbox_event` — 데몬이 폴링 대신 알림 기반으로 반응.
- **HTTP 콜백** `POST /internal/events/*` — 데몬이 웹서버에 UI 이벤트(브로드캐스트/캐시 무효화)를 되돌려 보냄.
- `main.py`의 `startup_event`는 `DECOUPLED=True`가 아니면 워처·체인 워커를 인라인 기동. 운영에서는 `run_decoupled_app.py`가 `DECOUPLED=True`로 완전 분리.
- **런처는 감시자다** — 자식을 띄우고 자는 것이 아니라 생존을 감시하고 재시작한다(§1.3). API 포트는 `ASSY_API_PORT`(기본 8080)로 덮을 수 있어, 감시 정책 자체를 격리 스택(:8081)에서 재구현 없이 그대로 검증할 수 있다.
- **데이터 루트는 `ASSY_DATA_ROOT` 하나로 옮긴다**(`server/paths.py`) — `config/`·`ingestion_workspace/`·프로세스 로그가 모두 여기서 유도된다. 미설정이면 `server/` 그대로. 새 경로를 `__file__`에서 다시 조립하면 격리가 샌다.

미들웨어 `db_context_middleware`가 `X-User`/`X-Transaction-ID`/`X-Source` 헤더를 ContextVar로 읽어 감사 추적에 사용. CORS는 `localhost:5173`으로 제한.

### 1.1 이벤트 루프 보호 원칙 (C-1, 2026-07-25)

uvicorn은 **단일 이벤트 루프**이므로, `async def` 핸들러 본문에서 동기 SQLAlchemy 쿼리·O(행×컬럼) 병합 루프·대형 JSON 직렬화를 실행하면 웹서버 전체(모든 REST/WS/내부 브로드캐스트)가 동결된다(라이브 실측 7초 freeze). 강제 규칙:

- **await가 필요 없는 핸들러는 `def`(sync)로 작성** → FastAPI가 threadpool에서 실행.
- **await(브로드캐스트 등)가 필요한 핸들러의 동기 구간(crud 호출, `fetch_and_merge_metadata`, ORM 속성 접근/직렬화)은 `run_in_threadpool`로 격리**. 적용 지점: PUT `/data/updates`, `batch_delete`(N+1 → `get_deleted_rows_business_keys_bulk` 벌크 IN 조회로 대체), `POST /rows`, `DELETE /rows/{id}`, priority(단건·배치), sources delete(단건·배치), `/internal/events/*`(audit_cache 갱신·json.dumps).
- 신규 엔드포인트 추가 시 이 원칙을 리뷰 포인트로 명시한다.

### 1.2 import 경로 불변식 (C-2)

모든 프로세스·스크립트는 `server/`를 sys.path에 두고 **최상위 `database.*` / `parsers.*` 경로로만** import한다. `server.database.*` 혼용 import는 동일 모듈 이중 로드 → outbox `before_flush` 리스너 2중 등록 → **전 이벤트 ×2 중복 발행**을 유발한다(상세: [event_driven_backend.md](./event_driven_backend.md) §2.1).

### 1.3 프로세스 감시와 헬스 (2026-07-27)

런처는 더 이상 자식을 띄우고 자기만 자는 루프가 아니다. `run_decoupled_app.py`가 `process_supervisor.Supervisor`를 돌리고, 그 결과를 `/health`가 밖으로 내보낸다. **두 축이 한 쌍**이다 — 감시 결과를 외부에서 볼 수 없으면 감시는 없는 것과 같다.

**감시자** (`server/process_supervisor.py` — 상태 파일 `<DATA_ROOT>/config/supervisor_status.json`)

- `ChildSpec(name, cmd, cwd, env, restartable, heartbeat, start_delay)`로 자식을 선언하고 1초 주기로 `poll_once()`.
- **유한 재시작 예산**: 연속 실패 n회째 `min(2·2^(n-1), 60)`초 백오프(2/4/8/16/32) → **6번째 연속 실패에서 `FAILED` 확정, 이후 재기동 없음**. 무한 재시작은 고장을 "감시가 도는 것처럼" 위장하므로 금지.
- **예산 회복**: 60초 이상 살아 있었으면 크래시 루프가 아니라고 보고 연속 카운터를 리셋.
- `restartable=False`(데스크톱 셸)의 종료는 **전체 종료 신호**다.
- `stop_all()`은 **정지 플래그를 먼저 세운 뒤** 종료한다(감시 루프가 종료 중인 자식을 "죽었다"고 되살리는 경쟁 방지). 자식의 손자 프로세스(스케줄러가 띄우는 수집기)는 부모가 살아 있는 동안 pid를 수집해 함께 정리한다 — 부모가 먼저 죽으면 손자를 찾을 방법이 없다.
- 상태 파일의 `updated_at`이 **감시자 자신의 생존 신호**다(감시자가 죽으면 자식은 계속 박동하는데 이 값만 멈춘다).

**진행 박동** (`server/utils/heartbeat.py` — `<DATA_ROOT>/config/worker_heartbeats/<name>.json`)

- 워커가 **자기 작업 루프 안에서** `beat(name)`을 호출한다. 이름 4종: `watcher` · `chain` · `graph` · `scheduler`.
- pid 검사가 아니라 **진행** 신호인 이유: 우리가 실제로 겪은 장애는 프로세스가 살아 있는 채 멈춘 이벤트 루프 동결이었다.
- 쓰기는 워커당 1초 이하로 스로틀되고, 원자적 replace이며, **모든 디스크 오류를 삼킨다**(감시 기능이 새 장애 원인이 되면 안 된다).
- 정체 임계 기본 **60초** — 워커별 루프 주기(2~5초) 대비 연속 12회 이상 누락에 해당한다. DB가 아니라 파일에 두는 이유는, DB 장애 때 전 워커가 동시에 정체로 보여 "DB 다운"과 "워커 정지"가 뭉개지기 때문이다.

**판정 조인** (`server/health.py`) — 프로세스 존재는 감시자가, 진행은 워커가 권위를 갖는다.

| 감시자 | 박동 | 판정 |
|---|---|---|
| running 아님 | — | `down` |
| running | 정체 | `wedged` (살아 있는데 진행 없음) |
| running | 없음 · uptime < 60s | `starting` (유예, 경보 아님) |
| running | 신선 | `ok` |

- **박동은 감시자가 띄운 pid의 것만 인정한다.** 같은 역할의 유령 프로세스나 재기동 직전에 죽은 전임자의 박동이 정체를 가리는 사례가 드릴에서 관측됐다(불일치 시 `foreign_beat`).
- **outbox 적체는 크기가 아니라 나이로 판정한다** — 정상적인 10만 행 적재 하나가 outbox 약 11.6만 행을 만들기 때문에, 멈춘 워커를 잡을 만큼 낮은 크기 임계는 큰 파일마다 오경보한다. 가장 오래된 미처리 행이 5분 초과 `degraded` / 15분 초과 `unhealthy`, 건수는 참고값(1만 캡). 두 질의 모두 부분 인덱스 `idx_outbox_unprocessed` 위 O(1).
- 감시자 상태 파일이 없으면 `supervisor: absent`(bare uvicorn·격리 스택) — 디스크의 박동만 참고 판정한다.

---

## 2. API 엔드포인트 지도 (`main.py`, ~3,934줄)

> **라인 앵커는 이 문서에서 관리하지 않습니다** — 핸들러 함수명·정확 위치는 [CODE_MAP §1](./CODE_MAP.md#1-servermainpy--api--ws-허브) 참조(doc-keeper가 Grep 실측으로 유지).

### 데이터 CRUD / 조회
| 메서드 · 경로 | 용도 |
|---|---|
| `GET /tables` | 구성된 테이블 목록 |
| `GET /tables/{t}/data` | 페이징/지연 그리드 조회(q 검색, cols, order_by, filters, tx 필터, target_row_id 점프). 카운트 5초 캐시 |
| `GET /tables/{t}/schema` | columns, column_types, business_key, composite_key_source, map_key_columns |
| `GET /tables/{t}/{row_id}` | 단건(전 소스 병합 메타 포함) |
| `POST /tables/{t}/rows` | 빈 행 N개 생성 |
| `PUT /tables/{t}/data/updates` | **통합 배치 업서트**(`crud.apply_batch_updates` 위임, 백그라운드 브로드캐스트) |
| `DELETE /tables/{t}/rows/{row_id}` | 단건 삭제 |
| `POST /tables/{t}/rows/batch_delete` | 일괄 물리 삭제 |
| `POST /tables/{t}/row_ids/target` | 정렬 오프셋의 row_id 해석(점프 스캐너) |
| `GET /tables/{t}/export` | 필터/정렬 반영 CSV 스트림(최대 ~100만 행) |

### 이력 / 감사
`GET /audit_logs/recent` · `GET /audit_logs/transaction/{tx_id}` · `GET /tables/{t}/rows/{id}/history` · `GET .../cells/{col}/history` · `GET /dashboard/summary`

### 소스 / 레이어링
| 경로 | 용도 |
|---|---|
| `GET .../{col}/sources` | 셀에 중첩된 전 소스값 + 계산 우선순위 |
| `DELETE .../sources/{source}` | 소스 1개 제거 |
| `PUT .../{col}/priority` | 표시 소스 수동 핀/해제 |
| `PUT /tables/{t}/cells/priority/batch` | 일괄 핀 |
| `POST /tables/{t}/cells/sources/delete/batch` | 일괄 소스 삭제 |
| `POST /tables/{t}/cells/sources/query` | 다중 셀 소스 조회 |

### 그래프 조회 (read-only — 웹서버가 `graph_nodes/edges` 직접 조회, 워커 미경유)
| 경로 | 용도 |
|---|---|
| `GET /graph/stats` | label/edge_type 카운트 + `last_sync`(graph_sync_state) — 뷰어 첫 화면 |
| `GET /graph/neighbors` | k-hop(1\|2) 이웃 서브그래프. **노드 limit 하드캡 500, 초과 시 `truncated`**, (from,type)/(to,type) 인덱스 경로만(C-7) |
| `GET /graph/nodes/search` | identity 시작일치 자동완성(LIKE 메타문자 이스케이프, limit 캡 50). **빈 q + label = 라벨 전체 리스팅**(identity 오름차순, limit/offset, 캡 200 — 뷰어 라벨 노드 리스트용, 전 테이블 덤프 금지 유지) |
| `POST /graph/trace` | **[G2] 멀티 시드 BFS 합집합** — depth 1..3(기본 2), 시간 필터(NULL event_time 통과)·edge_types 필터, 노드 하드캡 1000, `missing_seeds`/`truncated`. 의미 검증 실패는 400 |
| `GET /graph/mapping-summary` | 로드된 온톨로지 매핑 요약(enrichment 승격 포함) — 클라이언트 추적 진입점 활성 판정용 |

### 인제션 / 어드민 / 내부 / 맵 / WS
| 경로 | 용도 |
|---|---|
| `GET /health` | **[운영]** 헬스체크. **항상 JSON**, 정상 200 / `unhealthy` 503(`degraded`는 200). 본문 `{status, checked_at, problems[], checks{database, workers, outbox, supervisor}}`. DB 프로브는 2초 타임아웃 + 스레드 격리 + **중복 프로브 차단**(직전 프로브 미귀환이면 즉시 `timeout`으로 응답 — 헬스체크가 2차 장애가 되면 안 된다), `Cache-Control: no-store`. 판정 규칙은 §1.3 |
| `POST /tables/{t}/upload` | 클라이언트 파일을 `raws/`로 업로드 |
| `POST /api/graph/sync` | GraphSync 워커(:8090)로 프록시 — **백필/복구 도구**(주 경로는 materializer 자동 승격, [event_driven_backend §4](./event_driven_backend.md)) |
| `/admin/outbox/*`, `/admin/file-ingestion/*` | 아웃박스·파일적재 데드레터 관리·재시도 |
| `GET /admin/file-ingestion/active` | **[P1]** 진행 중 인제션 스냅샷(웹서버 인메모리 `ingestion_activity.py` 레지스트리 — TTL 퇴거 포함). admin File 탭 진행 섹션·재기동 경고의 데이터원 |
| `GET /api/bonding-plan/core-summary` | **[본딩 M1]** 코어(lot,slot) 역할별 집계(`bonding_plan.py` — 역할 바인딩 config, `remaining = total − defect − eds_fail − used`, align은 서버 단독 변환). `region` rects 파라미터, 잘못된 region 400 |
| `GET /api/maps/overlay` | **[M2 · 맵 인프라]** 임의의 맵들을 타깃 맵 **프레임 좌표로 정렬**해 `overlays[]` 반환(`map_overlay.py`). `sources`는 `table` 또는 `table:key` CSV(키 생략 시 `target_key` 승계, **최대 8종**), 셀 상한 20,000(초과 시 `truncated:true`). **align 규율: 소스·타깃 `wafer_map_metadata` 델타에서만 유도 > identity. 선언(`align_overrides`) 레이어는 2026-07-27 제거 — 정렬의 근거는 메타 하나뿐이다. 메타 부재는 실패가 아니며, 변환을 계산할 근거 자체가 없을 때만 `status: align_unavailable`. 변환기는 `map_overlay.resolve_map_transform` 단일 진입점이며 `bonding_plan`/`transfer_plan`의 가용량 산출도 이것을 쓴다.** 잘못된 `sources`/`limit` 400 |
| `GET /api/maps/paint-rules` | **[M2]** 페인트 잠금 선언 정본(`config/map_overlay_config.json`의 `paint_lock`) — **기존엔 클라 하드코딩 `'F'`**였다. 응답 `{table, rules{enabled, blocking_values, from_overlay, message}}`. 클라는 404/405만 "선언 없음"으로 해석하고 네트워크·5xx는 직전 잠금을 유지한다(fail-open 금지) |
| `GET /api/transfer-plan/stages` | **[M2]** 선언된 전사 stage 목록 + 역할 연결 상태(config 해석만 — 행 조회 없음). 역할·`plan_store` 누락은 `missing` 부분 가동(에러 아님) |
| `GET /api/transfer-plan/source-summary` | **[M2]** 단계별 소스 (lot,slot) 가용 집계(`transfer_plan.py`). 공통 형태 `{identity, stage, source_kind, sources, chips{total, fail_breakdown, transferred, remaining, remaining_reliable}, history, warnings}`. tape-kind는 `by_core`(7키 `core_id/core_lot/core_slot/total/fail/used/remaining`) + `by_core_origin`(`"log"` 정확 \| `"area_map"` 강등, 후자는 `fail=null`) 동봉. **degraded 시 `remaining: null` + `remaining_reliable: false` + `warnings[source_degraded]` 3층 방어** — 소비자가 초록으로 뒤집을 수 없다. **칩 좌표 목록은 반환하지 않는다**(집계만). 미선언 stage 404 |
| `GET /api/transfer-plan/validate` | **[M2-v2]** 계획 검증 — **계획 정체성은 `(ref_table, map_key)`**(구 `plan_id` 폐기, 계획 헤더 테이블도 계획 맵 사본도 없다). stage는 `stages.*.target_map.table` 역인덱스로 유도하며 미선언 맵은 404가 아니라 `stage_unknown` 경고 + `status: unverified`(임의의 맵도 열 수 있어야 하므로). `status`는 `ok`/`warnings`/`unverified` 3값 — **"검사 안 함"과 "이상 없음"을 같은 값으로 내지 않는다.** `plan_store.doe` 미구성만 404 |
| `/admin/chain/rules`, `/admin/mappers/list` | 체인 규칙·맵퍼(AST 파싱) 목록 |
| `/admin/auto-update/{status,run-now,toggle}` | 스케줄러 상태(각 항목에 `active` 부가)·즉시실행·수집기 active 토글. toggle body `{"script": "<workspace>/<script.py>", "active": bool}` → `config/auto_update_control.json` 갱신(스케줄러 핫 반영, 재기동 불필요; 미존재 404·검증실패 400). **run-now는 active 무관 실행**(수동 실행은 명시적 의도) |
| `/admin/reload-configs` | 로컬 캐시 리로드(`models.refresh_dynamic_models` — 신규 테이블 **물리 CREATE 포함**, 이슈 #7) + `SYSTEM_RELOAD` 발행. CREATE가 발행보다 선행(웹서버가 1차 DDL 소유자) |
| `/admin/scripts/{list,code}` | 브라우저 코드 에디터(경로 traversal 가드) |
| `POST /internal/events/{batch-refresh,broadcast,file-processed}` | 데몬→웹서버 콜백. batch-refresh 수신부는 msg 재구성 시 `total_log_count` 동봉(체인 passthrough 경로와 대칭 — P1 후속), broadcast/file-processed는 진행 레지스트리 인터셉트 겸함 |
| `POST /internal/events/ingestion-state` | **[P1]** watcher → 진행 상태 push(QUEUED/PROCESSING/FINISHED, heavy만 명시 통지). **WS 브로드캐스트 없음** — 레지스트리 전용 내부 이벤트 |
| `/map-presets`, `/api/map-presets` | 맵 지오메트리 프리셋(`config/maps.json`) |
| `GET /enrichment/rules` | Enrichment 규칙 메타(참조뷰는 label만 노출 — 쿼리 본문 노출 금지). 소스: `config/enrichment_rules.json`(`enrichment_config.py` 로더, 요청 시 재로드) |
| `GET /enrichment/rules/{rule}/references/{i}` | 참조뷰 서버측 실행 — `params`는 decision_key 컬럼만 허용(그 외 400), 파라미터 바인딩 전용(주입 불가), 서버 LIMIT 강제(기본 200/최대 1000), 규칙·인덱스 미존재 404 |
| `WS /ws` | `ConnectionManager` 브로드캐스트 허브 |
| `GET /`, `/admin`, `/map-editor`, `/enrichment`, `/{file:path}` | SPA 서빙 + fallback(`graph.html`/`trace.html`은 catch-all 경유) |

---

## 3. 배치 업서트 코어 (`crud.apply_batch_updates`)

모든 데이터 변경(수동 편집·파일 인제션·체인·맵 저장)이 이 함수 하나로 수렴합니다. (함수 위치는 [CODE_MAP §2](./CODE_MAP.md#2-serverdatabasecrudpy--레이어링-코어))

1. `transaction_context`(user/tx/source ContextVar)로 래핑.
2. **replace_map 모드** — 맵 저장 시 `map_key_columns` 기준으로 기존 행·`CellSource`·`CellOverwrite`를 bulk purge 후 신규 활성 칩만 재적재(유령 셀 0%). `deleted_row_ids` 반환.
3. 기존 행을 `row_id`/`business_key_val`로 `row_cache`에 적재하고 소스·오버라이트를 bulk 프리로드.
4. 셀별 `apply_row_update_internal` → `CellSource`에 값 기록 → `compute_priority_value`로 승자 재계산 → 네이티브 컬럼 + `CellOverwrite` 갱신. dialect별 `ON CONFLICT` upsert로 flush.
5. **collision_merge** — 비즈니스 키 변경 충돌 시 사용자 오버라이트 보존·병합, `manual_priority_source="collision_merge"` 태깅. → [data_preservation 규율](../guide/data_preservation_and_signature_change.md)
6. 반환: `(results[(row,is_new)], changed_cells, created_logs, deleted_row_ids)`.

> ⚠️ 이 반환 시그니처를 바꾸면 `main.py` 라우터·`chain_ingestion_worker.py`·`server/tests/` 언패킹을 **전수 연쇄 갱신**해야 합니다. → [시그니처 변경 규율](../guide/data_preservation_and_signature_change.md)

---

## 4. 백그라운드 워커

| 워커 | 트리거 | 동작 요약 |
|---|---|---|
| **Directory Watcher** (`directory_watcher.py`) | watchdog 파일 이벤트 | `raws/` 신규 파일 → `scripts/*.py`의 `BasePipelineParser.match()` 매칭 → `parse()` → 정규화 → `apply_batch_updates` 1000행 청크. **커스텀 스크립트 무매칭 시 std parser 폴백**(`parsers/std_parser.py` — `column_types` 헤더 검증 기반 CSV/TSV/TXT 스트리밍, 키 결측 행 스킵). 성공 시 `archives/`, 실패 시 `err/`. `FileIngestionLog` 기록. 워크스페이스 폴더는 config 등록 시 자동 보충. **기동/주기 스윕**: 기동·신규 등록 시 `raws/` 기존 파일을 이벤트 경로 재사용으로 자동 처리 + 300s 주기 잔류 재스캔((mtime,size) 시그니처로 무한 재시도 차단). **[P1] Heavy 레인**: 크기 임계(기본 10MB, `config/ingestion_settings.json` 파일 경계 핫리로드) 초과 파일은 전용 큐+데몬 워커 `watcher-heavy-lane` 1개로 격리(HOL 제거 — 교차 워크스페이스 비차단), 같은 워크스페이스 FIFO는 backlog+직렬화 락+논블로킹 재라우팅으로 보존, 진행 상태는 `/internal/events/ingestion-state`로 push([INGESTION_GUIDE §1.7](../guide/INGESTION_GUIDE.md)). **[P2] 체크포인트·dedup**: 파일 전체 sha256 시그니처(`sha256:<size>:<digest>`)로 ① 동일 시그니처 `DONE`이면 skip(+archive+`FileIngestionLog(SKIPPED)`, 단 WS 통지 status는 `SUCCESS`+사유 detail) ② 미완이면 오프셋 재개. **오프셋 갱신은 청크 upsert와 같은 트랜잭션**이라 "커밋된 행 수 == 기록된 오프셋"이 원자적으로 성립하며, 재개는 시그니처+`total_rows`+`source_kind`+오프셋 범위가 전부 일치할 때만 한다(불일치는 0부터 + 사유 명시). 강제 재처리 3경로: 파일명 `__force__` / `dedup_by_signature:false` / 관리자 재시도([INGESTION_GUIDE §1.8](../guide/INGESTION_GUIDE.md)) |
| **Auto-Update Scheduler** (`run_auto_update.py`) | 5초 틱 + 크론 | `auto_update/*.py` 발견 → 상단 `# schedule:` 크론 파싱 → `exec()`로 `out` 변수 캡처(또는 stdout 폴백) → CSV를 `raws/`에 원자적 드롭. `scheduler_status.json` 갱신(`active` 포함). 매 틱 `config/auto_update_control.json`(`{"disabled": [...]}`, 부재/손상 시 전부 active)을 읽어 disabled 수집기는 실행 스킵 + `last_status="SKIPPED"` + next_run 전진(핫 반영). run-now(on-demand)는 active 무관 실행 |
| **Chain Ingestion Worker** (`chain_ingestion_worker.py`) | outbox LISTEN/NOTIFY | `processed_chain=False` 폴링(200 배치) → tx별 그룹 → `chain_rules.json` 매칭 규칙의 맵퍼 동적 임포트·실행 → 파생 업데이트를 `chain_*` tx로 적용(source=chain_ingestion 순환 차단) → `/internal/events/broadcast`(통지의 created_logs는 직렬화 전 `MAX_NOTIFY_CREATED_LOGS`=500 절단 + `total_log_count` 실건수 동봉 — `event_constants.py` 공용 상수, 워처 C-5 계약과 동일 형태). 3회 재시도 후 FAILED. `load_chain_rules()`는 `enrichment_rules.json`에서 dedup 투영 룰(`enrichment_mapper.map_enrichment_dedup`, is_batch)을 자동 파생·병합하며, `rule` 인자를 선언한 맵퍼에만 룰 dict가 전달된다(기존 맵퍼 시그니처 불변) |
| **Graph Sync Worker — materializer** (`graph_sync_worker.py` + `graph_materializer.py`) | outbox 증분 소비(자체 keyset 커서 `graph_sync_state.last_outbox_id`, LISTEN/NOTIFY) | 독립 FastAPI(:8090). 이벤트 행을 `ontology_mapping.json` v2 매핑에 따라 **PG 엣지 스토어(`graph_nodes/edges`)로 자동 승격**. 엣지 provenance는 식별 컬럼 CellSource winner의 최저 서열(보수적), 재교정 시 `(from,type,source_row_ref)` 스코프 retarget. `[GraphLatency]` 계측(SLO 10s), 배치 본체는 `asyncio.to_thread` 격리. `/sync`(수동)는 키셋 청킹 **백필/복구** 도구(`"all"` 지원). Neo4j는 청크 훅으로 병행 가능(G3). 상세: [event_driven_backend §4](./event_driven_backend.md) · [ONTOLOGY_GRAPH_SPEC](../spec/ONTOLOGY_GRAPH_SPEC.md) |

공통: 위 4종 워커는 각자의 작업 루프 안에서 **진행 박동**(`watcher`/`chain`/`graph`/`scheduler`)을 발행하며, `/health`가 감시자의 프로세스 관점과 조인해 `ok`/`starting`/`wedged`/`down`을 판정합니다(§1.3).

공통: 모든 워커가 `SYSTEM_RELOAD` outbox 이벤트로 규칙·설정·맵퍼 캐시를 핫리로드하며, 이때 `models.refresh_dynamic_models(engine)`로 **신규 동적 테이블의 물리 CREATE까지 보충**합니다(게이트+checkfirst로 중복 무해 — 웹서버가 1차 소유자, 이슈 #7). graph materializer도 배치 내 SYSTEM_RELOAD를 감지해 매핑·테이블 config를 리로드합니다(이슈 #8 해소).

---

## 5. 참고

- 데이터 모델·레이어링 상세: [data_model.md](./data_model.md)
- 설정 파일: [SYSTEM_OVERVIEW §5](../overview/SYSTEM_OVERVIEW.md)
- 배치 스펙: [batch_update_technical_specification](../spec/batch_update_technical_specification.md)
- 실패 관리: [FAILURE_MANAGEMENT_SPEC](../spec/FAILURE_MANAGEMENT_SPEC.md)
