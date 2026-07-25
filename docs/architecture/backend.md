# 🖥️ Backend Architecture

> **Status:** 🟢 Living | **Last-verified:** 2026-07-25 | **Owner:** Backend / Sync
> **Source-of-truth:** `server/main.py`, `server/database/crud.py`, `server/*_worker.py`, `server/run_*.py`
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md)

---

> 이벤트 기반 흐름(Outbox staging·체인·그래프)의 심화 설명은 [event_driven_backend.md](./event_driven_backend.md) 참조.

## 1. 멀티프로세스 설계

FastAPI 웹서버(`main.py`)는 API + WebSocket 허브이고, 무거운 작업은 별도 데몬으로 분리됩니다. 조정은 PostgreSQL **Transactional Outbox** 패턴으로 이루어집니다.

- **Outbox 테이블** `database_outbox` — 이벤트를 트랜잭션과 함께 커밋해 유실 없이 전달.
- **LISTEN/NOTIFY** 채널 `outbox_event` — 데몬이 폴링 대신 알림 기반으로 반응.
- **HTTP 콜백** `POST /internal/events/*` — 데몬이 웹서버에 UI 이벤트(브로드캐스트/캐시 무효화)를 되돌려 보냄.
- `main.py:99-213` 시작 로직은 `DECOUPLED=True`가 아니면 워처·체인 워커를 인라인 기동. 운영에서는 `run_decoupled_app.py`가 `DECOUPLED=True`로 완전 분리.

미들웨어 `db_context_middleware`(`main.py:55-71`)가 `X-User`/`X-Transaction-ID`/`X-Source` 헤더를 ContextVar로 읽어 감사 추적에 사용. CORS는 `localhost:5173`으로 제한.

### 1.1 이벤트 루프 보호 원칙 (C-1, 2026-07-25)

uvicorn은 **단일 이벤트 루프**이므로, `async def` 핸들러 본문에서 동기 SQLAlchemy 쿼리·O(행×컬럼) 병합 루프·대형 JSON 직렬화를 실행하면 웹서버 전체(모든 REST/WS/내부 브로드캐스트)가 동결된다(라이브 실측 7초 freeze). 강제 규칙:

- **await가 필요 없는 핸들러는 `def`(sync)로 작성** → FastAPI가 threadpool에서 실행.
- **await(브로드캐스트 등)가 필요한 핸들러의 동기 구간(crud 호출, `fetch_and_merge_metadata`, ORM 속성 접근/직렬화)은 `run_in_threadpool`로 격리**. 적용 지점: PUT `/data/updates`, `batch_delete`(N+1 → `get_deleted_rows_business_keys_bulk` 벌크 IN 조회로 대체), `POST /rows`, `DELETE /rows/{id}`, priority(단건·배치), sources delete(단건·배치), `/internal/events/*`(audit_cache 갱신·json.dumps).
- 신규 엔드포인트 추가 시 이 원칙을 리뷰 포인트로 명시한다.

### 1.2 import 경로 불변식 (C-2)

모든 프로세스·스크립트는 `server/`를 sys.path에 두고 **최상위 `database.*` / `parsers.*` 경로로만** import한다. `server.database.*` 혼용 import는 동일 모듈 이중 로드 → outbox `before_flush` 리스너 2중 등록 → **전 이벤트 ×2 중복 발행**을 유발한다(상세: [event_driven_backend.md](./event_driven_backend.md) §2.1).

---

## 2. API 엔드포인트 지도 (`main.py`, 3,036줄)

### 데이터 CRUD / 조회
| 메서드 · 경로 | 라인 | 용도 |
|---|---|---|
| `GET /tables` | :538 | 구성된 테이블 목록 |
| `GET /tables/{t}/data` | :857 | 페이징/지연 그리드 조회(q 검색, cols, order_by, filters, tx 필터, target_row_id 점프). 카운트 5초 캐시 |
| `GET /tables/{t}/schema` | :1417 | columns, column_types, business_key, composite_key_source, map_key_columns |
| `GET /tables/{t}/{row_id}` | :1455 | 단건(전 소스 병합 메타 포함) |
| `POST /tables/{t}/rows` | :1543 | 빈 행 N개 생성 |
| `PUT /tables/{t}/data/updates` | :1599 | **통합 배치 업서트**(`crud.apply_batch_updates` 위임, 백그라운드 브로드캐스트) |
| `DELETE /tables/{t}/rows/{row_id}` | :1067 | 단건 삭제 |
| `POST /tables/{t}/rows/batch_delete` | :1088 | 일괄 물리 삭제 |
| `POST /tables/{t}/row_ids/target` | :1134 | 정렬 오프셋의 row_id 해석(점프 스캐너) |
| `GET /tables/{t}/export` | :1222 | 필터/정렬 반영 CSV 스트림(최대 ~100만 행) |

### 이력 / 감사
| 경로 | 라인 |
|---|---|
| `GET /audit_logs/recent` | :586 |
| `GET /audit_logs/transaction/{tx_id}` | :631 |
| `GET /tables/{t}/rows/{id}/history` | :1490 |
| `GET /tables/{t}/rows/{id}/cells/{col}/history` | :1516 |
| `GET /dashboard/summary` | :710 |

### 소스 / 레이어링
| 경로 | 라인 | 용도 |
|---|---|---|
| `GET .../{col}/sources` | :1780 | 셀에 중첩된 전 소스값 + 계산 우선순위 |
| `DELETE .../sources/{source}` | :1823 | 소스 1개 제거 |
| `PUT .../{col}/priority` | :1846 | 표시 소스 수동 핀/해제 |
| `PUT /tables/{t}/cells/priority/batch` | :1902 | 일괄 핀 |
| `POST /tables/{t}/cells/sources/delete/batch` | :1966 | 일괄 소스 삭제 |
| `POST /tables/{t}/cells/sources/query` | :2022 | 다중 셀 소스 조회 |

### 인제션 / 어드민 / 내부 / 맵 / WS
| 경로 | 라인 | 용도 |
|---|---|---|
| `POST /tables/{t}/upload` | :1753 | 클라이언트 파일을 `raws/`로 업로드 |
| `POST /api/graph/sync` | :1693 | GraphSync 워커(:8090)로 프록시 |
| `GET /graph/{stats,neighbors,nodes/search}` | :1863~ | [온톨로지 뷰어] read-only 그래프 조회(웹서버가 `graph_nodes/edges` 직접 조회 — 워커 미경유). stats=label/edge_type 카운트+`last_sync` · neighbors=k-hop(1\|2) 이웃 서브그래프(**노드 limit 하드캡 500, 초과 시 `truncated`**, (from,type)/(to,type) 인덱스 경로만) · search=identity 시작일치 자동완성(LIKE 메타문자 이스케이프) |
| `/admin/outbox/*`, `/admin/file-ingestion/*` | :2106~ | 아웃박스·파일적재 데드레터 관리·재시도 |
| `/admin/chain/rules`, `/admin/mappers/list` | :2484, :2506 | 체인 규칙·맵퍼(AST 파싱) 목록 |
| `/admin/auto-update/{status,run-now}` | :2654, :2678 | 스케줄러 상태·즉시실행 |
| `/admin/reload-configs` | :2425 | 로컬 캐시 리로드(`models.refresh_dynamic_models` — 신규 테이블 **물리 CREATE 포함**, 이슈 #7) + `SYSTEM_RELOAD` 발행. CREATE가 발행보다 선행(웹서버가 1차 DDL 소유자) |
| `/admin/scripts/{list,code}` | :2798~ | 브라우저 코드 에디터(경로 traversal 가드) |
| `POST /internal/events/{batch-refresh,broadcast,file-processed}` | :2717~ | 데몬→웹서버 콜백 |
| `/map-presets`, `/api/map-presets` | :2350~ | 맵 지오메트리 프리셋(`config/maps.json`) |
| `GET /enrichment/rules` | :2688~ | Enrichment 규칙 메타(참조뷰는 label만 노출 — 쿼리 본문 노출 금지). 소스: `config/enrichment_rules.json`(`enrichment_config.py` 로더, 요청 시 재로드) |
| `GET /enrichment/rules/{rule}/references/{i}` | :2707~ | 참조뷰 서버측 실행 — `params`는 decision_key 컬럼만 허용(그 외 400), 파라미터 바인딩 전용(주입 불가), 서버 LIMIT 강제(기본 200/최대 1000), 규칙·인덱스 미존재 404 |
| `WS /ws` | :1741 | `ConnectionManager` 브로드캐스트 허브(:231) |
| `GET /`, `/admin`, `/map-editor`, `/enrichment`, `/{file:path}` | :260~ | SPA 서빙 + fallback (`enrichment.html` 포함) |

---

## 3. 배치 업서트 코어 (`crud.apply_batch_updates`, :921)

모든 데이터 변경(수동 편집·파일 인제션·체인·맵 저장)이 이 함수 하나로 수렴합니다.

1. `transaction_context`(user/tx/source ContextVar)로 래핑.
2. **replace_map 모드**(:937) — 맵 저장 시 `map_key_columns` 기준으로 기존 행·`CellSource`·`CellOverwrite`를 bulk purge 후 신규 활성 칩만 재적재(유령 셀 0%). `deleted_row_ids` 반환.
3. 기존 행을 `row_id`/`business_key_val`로 `row_cache`에 적재하고 소스·오버라이트를 bulk 프리로드(:1015-1082).
4. 셀별 `apply_row_update_internal`(:441) → `CellSource`에 값 기록 → `compute_priority_value`로 승자 재계산 → 네이티브 컬럼 + `CellOverwrite` 갱신. dialect별 `ON CONFLICT` upsert로 flush(:240,272).
5. **collision_merge**(:699-752, :1551-1565) — 비즈니스 키 변경 충돌 시 사용자 오버라이트 보존·병합, `manual_priority_source="collision_merge"` 태깅. → [data_preservation 규율](../guide/data_preservation_and_signature_change.md)
6. 반환: `(results[(row,is_new)], changed_cells, created_logs, deleted_row_ids)`.

> ⚠️ 이 반환 시그니처를 바꾸면 `main.py` 라우터·`chain_ingestion_worker.py`·`server/tests/` 언패킹을 **전수 연쇄 갱신**해야 합니다. → [시그니처 변경 규율](../guide/data_preservation_and_signature_change.md)

---

## 4. 백그라운드 워커

| 워커 | 트리거 | 동작 요약 |
|---|---|---|
| **Directory Watcher** (`directory_watcher.py`) | watchdog 파일 이벤트 | `raws/` 신규 파일 → `scripts/*.py`의 `BasePipelineParser.match()` 매칭 → `parse()` → 정규화 → `apply_batch_updates` 1000행 청크. 성공 시 `archives/`, 실패 시 `err/`. `FileIngestionLog` 기록 |
| **Auto-Update Scheduler** (`run_auto_update.py`) | 5초 틱 + 크론 | `auto_update/*.py` 발견 → 상단 `# schedule:` 크론 파싱 → `exec()`로 `out` 변수 캡처(또는 stdout 폴백) → CSV를 `raws/`에 원자적 드롭. `scheduler_status.json` 갱신 |
| **Chain Ingestion Worker** (`chain_ingestion_worker.py`) | outbox LISTEN/NOTIFY | `processed_chain=False` 폴링(200 배치) → tx별 그룹 → `chain_rules.json` 매칭 규칙의 맵퍼 동적 임포트·실행 → 파생 업데이트를 `chain_*` tx로 적용(루프 방지 필터 :92) → `/internal/events/broadcast`. 3회 재시도 후 FAILED. `load_chain_rules()`는 `enrichment_rules.json`에서 dedup 투영 룰(`enrichment_mapper.map_enrichment_dedup`, is_batch)을 자동 파생·병합하며, `rule` 인자를 선언한 맵퍼에만 룰 dict가 전달된다(기존 맵퍼 시그니처 불변) |
| **Graph Sync Worker** (`graph_sync_worker.py`) | `/api/graph/sync` 수동 호출 | 독립 FastAPI(:8090). dirty 행(`is_graph_synced=False`) → incremental vs rollback_and_replay 판정 → Neo4j Cypher 또는 `virtual_graph.json` 기록 |

공통: Graph Sync를 제외한 워커는 `SYSTEM_RELOAD` outbox 이벤트로 규칙·설정·맵퍼 캐시를 핫리로드하며, 이때 `models.refresh_dynamic_models(engine)`로 **신규 동적 테이블의 물리 CREATE까지 보충**합니다(게이트+checkfirst로 중복 무해 — 웹서버가 1차 소유자, 이슈 #7). Graph Sync 워커만 리로드 경로가 없어 재기동 전까지 신규 테이블을 모릅니다(열린 이슈).

---

## 5. 참고

- 데이터 모델·레이어링 상세: [data_model.md](./data_model.md)
- 설정 파일: [SYSTEM_OVERVIEW §5](../overview/SYSTEM_OVERVIEW.md)
- 배치 스펙: [batch_update_technical_specification](../spec/batch_update_technical_specification.md)
- 실패 관리: [FAILURE_MANAGEMENT_SPEC](../spec/FAILURE_MANAGEMENT_SPEC.md)
