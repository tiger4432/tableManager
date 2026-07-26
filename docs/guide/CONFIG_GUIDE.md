# ⚙️ AssyManager 설정 가이드 (Config Guide)

> **Status:** 🟢 Living | **Last-verified:** 2026-07-27 (정렬 선언 레이어 폐지 · 제품 테이블 설치기 · 데이터 루트 반영) | **Owner:** Lead / Backend | **Source-of-truth:** `server/config/*`, `server/product_tables.py`, `server/paths.py`, `server/database/crud.py`, `server/database/config_watcher.py`, `server/parsers/directory_watcher.py`, `server/map_overlay.py` · 상위 [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md)

**이 문서의 역할 = "설정 관점의 지도".** "무엇을, 어디에, 어떤 순서로 넣고, 어떻게 검증하는가"에만 답합니다.
각 서브시스템의 **동작 원리·내부 구조는 여기 쓰지 않고** 해당 리빙 가이드로 링크합니다 → [INGESTION_GUIDE](./INGESTION_GUIDE.md) · [AUTO_UPDATE_GUIDE](./AUTO_UPDATE_GUIDE.md) · [chain_ingestion_guide](./chain_ingestion_guide.md) · [ONTOLOGY_GRAPH_SPEC](../spec/ONTOLOGY_GRAPH_SPEC.md) · [ENRICHMENT_QUEUE_SPEC](../spec/ENRICHMENT_QUEUE_SPEC.md) · [MAP_EDITOR_SPEC](../spec/MAP_EDITOR_SPEC.md)

---

## 1. 한눈에 보기

모든 실 설정 파일은 `server/config/` 아래에 있고 **전부 gitignored**입니다. `.gitignore`:

```gitignore
# 운영 환경 고유 설정 및 인제션 워크스페이스
server/config/*
!server/config/*.sample
server/mappers/*
!server/mappers/*.sample
server/ingestion_workspace/
server/database/virtual_graph.json
```

즉 **git에 올라가는 것은 `*.sample`뿐**이고, 실제 값은 각 운영 환경의 로컬 자산입니다. 새 환경을 세팅할 때는 `.sample`을 확장자 없이 복사해 시작합니다.

| 파일 (`server/config/`) | 목적 | 소유 | git | 적용 방법 | 소비 프로세스 |
|---|---|---|---|---|---|
| **`table_config.json`** | 동적 테이블 스키마 **SSOT** — 모든 테이블의 컬럼/키/표시 정의 | 사용자 | ignored (`.sample` 有) | 신규 테이블·컬럼 = 핫(§4) / 컬럼 삭제·타입 변경 = **재기동** | 전 프로세스(web·watcher·chain·graph) |
| **`ontology_mapping.json`** | 그래프 노드/엣지 매핑 v2 (`description` 필수) | 사용자 | ignored (`.sample` 有) | `POST /admin/reload-configs` (웹서버 캐시 무효화) | web, graph_sync_worker |
| **`enrichment_rules.json`** | 결손 보정 워크리스트 규칙(`decision_key`/`target_fields`/`reference_views`) | 사용자 | ignored (`.sample` 有) | 조회 API는 즉시 / 체인 파생 룰은 `reload-configs` | web, chain_ingestion_worker |
| **`chain_rules.json`** | 체인 인제션 룰(trigger→target→mapper) | 사용자 | ignored (`.sample` 有) | `POST /admin/reload-configs` | chain_ingestion_worker, web(조회) |
| **`auto_update_control.json`** | 수집기 비활성 목록(= active 토글) | 사용자 (**API로 쓰기 권장**) | ignored (`.sample` 有) | 즉시(매 사이클 재조회) | run_auto_update, web |
| **`ingestion_settings.json`** | 인제션 런타임 노브 — `heavy_file_mb`(P1 heavy 레인 임계, 기본 10) · `dedup_by_signature`(P2 동일 파일 skip, 기본 true) · `resume_from_checkpoint`(P2 오프셋 재개, 기본 true) | 사용자 | ignored (`.sample` 有) | 즉시(**다음 파일부터**) | watcher |
| **`map_overlay_config.json`** | **범용 맵 오버레이** — `table_bindings`(맵 좌표 컬럼, 미선언 시 `table_config`에서 자동 유도) · `paint_lock`(페인트 잠금 **정본**). ~~`align_overrides`~~는 **2026-07-27 폐지**(§5.8-bis) | 사용자 | ignored (`.sample` 有) | 즉시(**요청당 1회 스냅샷**) | web |
| **`maps.json`** | 웨이퍼 물리 규격/오프셋 **프리셋** | 사용자 (**API로 쓰기**) | ignored (`.sample` 有) | 즉시(요청마다 디스크 읽기) | web |
| **`bonding_plan_config.json`** | M1 본딩 실험계획 — 역할(role)→실테이블 바인딩 | 사용자 | ignored (`.sample` 有) | 즉시(**요청당 1회 스냅샷**) | web |
| **`transfer_plan_config.json`** | M2 Universal Transfer Plan — stage 선언 + plan_store | 사용자 | ignored (`.sample` 有) | 즉시(**요청당 1회 스냅샷**) | web |
| `scheduler_status.json` | 스케줄러→UI 텔레메트리 | **시스템(자동 생성)** | ignored | — | run_auto_update가 씀, web이 읽음 |
| `supervisor_status.json` | **[운영]** 자식 프로세스 감시 상태(자식별 state·재시작 횟수·실패 사유, `updated_at`=감시자 생존 신호) | **시스템(자동 생성)** | ignored | — | `run_decoupled_app`이 씀, `/health`가 읽음 |
| `worker_heartbeats/<worker>.json` | **[운영]** 워커 진행 박동 4종(`watcher`·`chain`·`graph`·`scheduler`) | **시스템(자동 생성)** | ignored | — | 각 워커가 씀, `/health`가 읽음 |
| `*.bak`, `*.v1.bak` | 수동 백업 잔재 | 사용자 | ignored | — | 아무도 안 읽음 |

> `table_config.json.bak_enrich` · `ontology_mapping.json.v1.bak` 같은 파일은 **코드가 읽지 않습니다**. 파일명이 정확히 일치해야만 로드됩니다.

> ⚠️ **위 경로의 기준점은 `server/config/`가 아니라 `paths.CONFIG_DIR`입니다.** `ASSY_DATA_ROOT`를 걸면 config 트리 전체가 통째로 이동합니다(아래 "파일이 아닌 설정 원천"). 새 config를 읽는 코드는 **반드시 `server/paths.py`를 경유**하십시오 — `__file__`에서 경로를 다시 조립하면 격리가 샙니다(실제로 로그·`virtual_graph.json`이 그렇게 샜습니다).

> **감시·박동 파일은 "설정"이 아니라 산출물입니다.** 손으로 고쳐도 다음 틱에 덮어써지고, **없는 것이 정상 상태**입니다(첫 사용 시 생성). 그래서 이 두 경로의 부재가 곧 "그 스택은 아직 돌지 않았다"의 증거로 쓰입니다.

### DB에 저장되는 "설정성" 데이터

파일이 아니라 DB 행으로 관리되는 것도 있습니다 — 파일 config와 혼동하지 마십시오.

| 대상 | 저장 위치 | 편집 경로 |
|---|---|---|
| 맵 지오메트리 프리셋 | `server/config/maps.json` (**파일**) | 맵 에디터 UI → `GET/POST/DELETE /api/map-presets` |
| **웨이퍼별 실제 격자 규격** | DB 테이블 `wafer_map_metadata` (**행**) | 수집기 스크립트가 `POST /tables/wafer_map_metadata/data/updates`로 적재. 키 관례 `map_pk = <table>_<map_id>`, `map_id = <lot>_<slot>` |

`wafer_map_metadata`는 `table_config.json`에 등록된 평범한 동적 테이블이지만, **워크스페이스 자동 생성 대상에서는 제외**됩니다(`AUTO_PROVISION_EXCLUDED_TABLES`).

### 폐지된 것 — 워크스페이스 `config.json`

> 🗑️ **[Deprecated 2026-07-25]** `server/ingestion_workspace/<ws>/config/config.json`
> `table_name`/`std_parse` 두 필드는 글로벌 `table_config.json`의 `workspace_name`/`std_parse`로 **흡수**되었습니다.
> - 기존 파일은 **하위호환으로 계속 읽히지만** deprecation WARNING이 남습니다.
> - **충돌 시 `table_config.json`이 승리**합니다.
> - 신규 워크스페이스에는 더 이상 생성되지 않습니다.
> - ⚠️ 이 파일만은 **핫리로드되지 않습니다**(핸들러 인스턴스 수명 동안 캐시). 마이그레이션하십시오. 상세: [INGESTION_GUIDE §1.5](./INGESTION_GUIDE.md)

### 파일이 아닌 설정 원천

| 원천 | 무엇 | 변경 시 |
|---|---|---|
| 환경변수 | `DATABASE_URL`(기본 `postgresql://postgres:admin@localhost:5432/assy_manager`), **`ASSY_DATA_ROOT`**(config·워크스페이스·프로세스 로그의 단일 이동점, 미설정 시 `server/`), `ASSY_API_PORT`(런처가 띄우는 uvicorn 포트, 기본 8080), `DECOUPLED`, `TESTING`, `API_BASE_URL`(기본 `http://127.0.0.1:8080`), `GRAPH_SYNC_PORT`(8090), `GRAPH_MATERIALIZER_ENABLED`(true), `NEO4J_*`, `ASSY_API_BASE` | **전부 재기동 필요** (import 시점 1회 읽음) |
| 수집기 스케줄 | 수집기 `.py` **주석**의 `schedule`(cron) / `filename_prefix` — JSON 아님 | 스케줄러가 주석 변경을 감지해 핫 반영 → [AUTO_UPDATE_GUIDE](./AUTO_UPDATE_GUIDE.md) |
| 파이프라인 플러그인 등록 | 레지스트리 파일 없음. `<workspace>/scripts/*.py` **파일 존재 자체가 등록** | `POST /admin/reload-configs`가 `pipeline_plugin_*` 모듈 캐시 무효화 |
| 커스텀 맵퍼 등록 | `server/mappers/*.py` 파일 + `chain_rules.json`의 `mapper_module`/`mapper_function` | 위와 동일(`mappers.*` 캐시 무효화) |
| CORS 허용 오리진 | `server/main.py`에 하드코딩(`localhost:5173`) | 코드 수정 + 재기동 |
| 워크스페이스 하위 폴더 구조 | 상수 `("raws","archives","err","auto_update","scripts","config")` | 코드 상수(설정 불가) |

> ℹ️ **어드민 코드 에디터(Monaco)는 `.py`만 편집합니다** — `server/mappers/`, `<ws>/scripts/`, `<ws>/auto_update/`. **`server/config/*.json`은 UI에서 편집할 수 없습니다.** 반드시 디스크에서 직접 편집하십시오(예외: 맵 프리셋·수집기 토글은 전용 API 있음).

---

## 2. 의존 순서 (무엇이 무엇을 전제하는가)

```
table_config.json  ← 모든 것의 뿌리 (테이블/컬럼이 여기 없으면 나머지가 전부 검증 실패)
     │
     ├─→ 워크스페이스 자동 생성 (폴더명=테이블명 또는 workspace_name 별칭)
     │        └─→ <ws>/scripts/*.py (커스텀 파서)  ·  <ws>/auto_update/*.py (수집기)
     │                                                      └─→ auto_update_control.json (토글)
     ├─→ chain_rules.json        (trigger_table / target_table 이 등록돼 있어야 함)
     ├─→ enrichment_rules.json   (source_table / derived_table + 컬럼 존재 검증)
     │        └─→ 체인 dedup 룰 자동 파생 + 온톨로지 RESOLVED_AS 엣지 자동 승격
     ├─→ ontology_mapping.json   (미등록 테이블/컬럼이면 로드 거부)
     ├─→ bonding_plan_config.json / transfer_plan_config.json (role→table 바인딩)
     └─→ wafer_map_metadata 행 + maps.json 프리셋 (맵 계열)
```

**규칙: `table_config.json`을 먼저, 나머지는 그 다음.** 하위 config는 대부분 `table_config`에 등록되지 않은 테이블/컬럼을 참조하면 로드 시점에 거부되거나 `missing`으로 부분 가동됩니다.

---

## 3. 시나리오별 체크리스트 ★

### S1. 새 테이블 하나 추가할 때

| # | 할 일 | 검증 |
|---|---|---|
| 1 | `server/config/table_config.json`에 테이블 항목 추가(§5.1 스니펫). **비-ASCII/공백 컬럼명은 피할 것** | JSON 파싱 확인 — 파싱 실패 시 **로그 없이 조용히 `{}`가 되어 전 테이블이 사라집니다**(§6-A) |
| 2 | 저장은 **in-place 쓰기**로 (에디터의 원자적 temp+rename은 watcher를 발화시키지 않음 → §6-B) | — |
| 3 | 물리 테이블 생성 확인 | `psql -U postgres -d assy_manager -c "\d <table>"` 또는 `SELECT column_name FROM information_schema.columns WHERE table_name='<table>'` |
| 4 | 안 만들어졌으면 `POST /admin/reload-configs` (신규 CREATE 전용) | 다시 3번 |
| 5 | 워크스페이스 자동 생성 확인 — `server/ingestion_workspace/<table>/{raws,archives,err,auto_update,scripts,config}` | `GET /admin/file-ingestion/workspaces` |
| 6 | 폴더명 ≠ 테이블명이면 `table_config` 항목에 `"workspace_name": "<폴더명>"` 추가 | 별칭이 **다른 실존 테이블명과 동명**이거나 **복수 테이블이 같은 별칭**을 쓰면 무시 + ERROR 로그 |
| 7 | (선택) 커스텀 파서 불필요 → 표준 파서가 헤더 일치 CSV/TSV/TXT를 그대로 적재. 커스텀 변환에 의존한다면 `"std_parse": false` 명시 | [INGESTION_GUIDE §1.5](./INGESTION_GUIDE.md) |
| 8 | (선택) 주기 수집 필요 → S3 |
| 9 | (선택) 그래프에 올릴 것 → S4 |
| 10 | (선택) 파생/보정 필요 → S6·S7 |
| 11 | 실제 파일 1건을 `raws/`에 넣어 왕복 검증 | `GET /admin/file-ingestion/logs` + `GET /tables/<table>/data` |

> ⚠️ **기존 테이블에 컬럼을 추가**하는 경우: CREATE가 아니라 **ALTER**이므로 경로가 다릅니다. `/admin/reload-configs`는 ALTER를 하지 않습니다 → §4 표를 반드시 확인.

### S2. 새 **맵** 테이블 추가할 때

S1을 전부 수행한 뒤 추가로:

| # | 할 일 | 비고 |
|---|---|---|
| 1 | `table_config` 항목에 `"map_key_columns": [...]` 지정 | 맵 교체(replace) 시 **삭제 범위를 한정**하는 키. 지정하면 그 목록만 필터로 쓰고, 없으면 "전 컬럼 − 하드코딩 스킵셋(`x,y,col_x,col_y,val,code,die_id,grid_metadata,leg`)" 폴백 |
| 2 | 좌표 컬럼을 `column_types`에 `number`로 선언 | |
| 3 | 격자 규격 행을 `wafer_map_metadata`에 적재 | 수집기가 `POST /tables/wafer_map_metadata/data/updates`. 관례: `map_pk = <table>_<map_id>`, `map_id = <lot>_<slot>` |
| 4 | 맵 에디터에서 물리 규격 프리셋 등록(필요 시) | `POST /api/map-presets` — `maps.json`에 저장. 수동 편집 말고 UI 사용 권장 |
| 5 | 계획 엔진에서 쓸 맵이면 role 바인딩 추가 | → S6 |

> `maps.json` 프리셋(재사용 가능한 지오메트리 템플릿) ≠ `wafer_map_metadata`(웨이퍼별 실제 격자) ≠ `align`(소스↔canonical 좌표 보정). **세 곳이 서로 다른 개념**입니다.

### S3. 수집기(auto_update) 추가 / 토글할 때

| # | 할 일 | 검증 |
|---|---|---|
| 1 | `server/ingestion_workspace/<table>/auto_update/<name>.py` 배치 | 파일 존재 자체가 등록. JSON 등록 불필요 |
| 2 | 스크립트 **주석**에 `schedule`(cron), `filename_prefix` 선언 | [AUTO_UPDATE_GUIDE](./AUTO_UPDATE_GUIDE.md) |
| 3 | 스케줄러 인식 확인 | `GET /admin/auto-update/status` |
| 4 | 켜기/끄기 | **`POST /admin/auto-update/toggle`** `{"script":"<table>/<name>.py","active":false}` |
| 5 | 즉시 1회 실행 | `POST /admin/auto-update/run-now` — **`active=false`여도 실행됩니다**(수동 실행은 명시적 의도) |

> `auto_update_control.json`을 **손으로 편집하지 마십시오.** API가 락 + 원자적 쓰기로 갱신합니다. 키 형식은 `<워크스페이스>/<파일명>.py` 하나뿐이며(공백·한글 파일명 허용) 형식이 어긋나면 400입니다. `active`는 상태 파일이 아니라 **항상 이 제어 파일에서 실시간 계산**되므로 토글은 즉시 반영됩니다.

### S4. 그래프에 올릴 때

| # | 할 일 | 검증 |
|---|---|---|
| 1 | `ontology_mapping.json`에 `{테이블명: {description, node, edges}}` 추가 (§5.2) | 루트는 반드시 **객체** `{table: mapping}` — 배열이면 거부 |
| 2 | **`description`은 필수** — 노드·엣지 모두. LLM 그라운딩 계약 | [ONTOLOGY_GRAPH_SPEC §3](../spec/ONTOLOGY_GRAPH_SPEC.md) |
| 3 | 참조하는 테이블·컬럼이 `table_config`에 실존하는지 확인 | 미등록이면 해당 매핑이 **통째로 스킵**됨 |
| 4 | 엣지 타깃은 `target_label` + `target_identity_from: [컬럼...]` | |
| 5 | `POST /admin/reload-configs` | 웹서버의 `_ontology_cache` 무효화 + 워커에 SYSTEM_RELOAD 전파 |
| 6 | 매핑 반영 확인 → 재동기화 → 그래프 조회 | 조회는 `GET /graph/neighbors?label=..&identity=..` (**`node_id` 파라미터는 없습니다 — 422**) |

> enrichment 규칙은 **`RESOLVED_AS` 엣지로 자동 승격**되므로 `ontology_mapping.json`에 중복 선언할 필요가 없습니다.
> 구 v1 형식(`default`/`tables` 래퍼)은 v2 로더가 **무시**합니다.

### S5. 대형 파일 임계(heavy 레인) 조정할 때

| # | 할 일 |
|---|---|
| 1 | `server/config/ingestion_settings.json.sample`을 `ingestion_settings.json`으로 **복사** |
| 2 | `"heavy_file_mb": <양수>` 설정 |
| 3 | 저장 즉시 반영 — **다음 파일 이벤트부터**. 재기동·reload 불필요 |

- **파일이 없으면 기본 10 MB**입니다. (현 저장소 상태: 실제 파일 없음 = 10 MB로 동작 중)
- 값이 `bool`이거나 숫자가 아니거나 `<= 0`이면 **경고 후 10 MB로 폴백**합니다.
- 임계 이상 파일은 전용 heavy 워커로 라우팅되어 다른 테이블의 소형 파일을 막지 않습니다. 단, **같은 워크스페이스에 heavy 백로그가 있으면 소형 파일도 순서 보존을 위해 큐 뒤로** 갑니다.

### S6. 본딩/전사 계획 원천을 실환경 테이블로 바꿀 때 (**코드 무변경**)

계획 엔진은 테이블명을 하드코딩하지 않습니다. **역할(role) → 실테이블 바인딩 교체만으로** 원천이 바뀝니다.

**M1 (본딩 실험계획) — `bonding_plan_config.json`**

| # | 할 일 |
|---|---|
| 1 | `sources.<role>.table` / `.columns`를 실제 테이블·컬럼명으로 교체. role: `process_history`, `defect`, `eds_fail`, `used_chips`, `total_chips` |
| 2 | 각 바인딩은 `{"table": "<str>", "columns": {<역할키>: <물리컬럼>}}` 형태여야 유효. 아니면 그 role은 **`missing`(부분 가동 — 에러 아님)** |
| 3 | 맵 모드 소스는 `"mode": "map"` + `fail_values` |
| 4 | **좌표계가 달라도 `align`을 선언하지 않습니다(2026-07-27).** 소스 좌표계→canonical 좌표계 변환은 두 맵의 `wafer_map_metadata` **델타에서 유도**됩니다. ~~`sources[].align`~~은 폐지됐고 파일에 남아 있어도 서버가 무시합니다 — 대신 **각 맵을 `wafer_map_metadata`에 등록**하십시오 |
| 5 | `core_identity.compose`(기본 `["lot","slot"]`), `map_metadata` 바인딩, `warnings.result_fail_values` 확인 |
| 6 | 검증: `GET /api/bonding-plan/core-summary?lot=..&slot=..` — 응답의 role별 상태가 `connected`인지 |

**M2 (Universal Transfer Plan) — `transfer_plan_config.json`**

| # | 할 일 |
|---|---|
| 1 | `stages.<stage명>`을 선언만 하면 새 단계가 추가됩니다(코드 무변경) |
| 2 | 필수: `description`, `source_kind`, `target_kind`, `target_map: {preset, table}` |
| 3 | 소스는 **둘 중 하나** — ① `"source_config_ref": "bonding_plan"`(M1 바인딩 재사용, 현재 유일 허용값) ② 인라인 `"source": {...}` |
| 4 | 인라인 소스 역할: `identity.compose`, `map_metadata`, `total_chips`, `transfer_log`, `origin_log`, `origin_area_map`, `process_history`, `fail_sources`, `warnings` |
| 5 | `fail_sources.<name>.frame` — `"origin"`=출신 프레임 fail을 `origin_log` 조인으로 타깃 좌표에 투영 / `"self"`=자기 프레임에서 계산 |
| 6 | `plan_store.{doe,doe_source}` — 계획 저장 테이블 바인딩. **v2에서 `plan`(헤더)·`map`(계획 맵 사본) 역할은 폐기**됐습니다 — 계획 정체성이 `(ref_table, map_key)`, 즉 *지금 열어 편집 중인 그 맵*이고 페인팅 결과가 곧 그 맵 자신의 셀이기 때문입니다 |
| 7 | 검증: `GET /api/transfer-plan/stages` → `GET /api/transfer-plan/validate?ref_table=&map_key=` → `GET /api/transfer-plan/source-summary` |

> **stage는 고르는 것이 아니라 유도됩니다(v2).** `stages.*.target_map.table`의 역인덱스이므로 `bonding_map`을 열면 `bonding`, `dt_map`을 열면 `dt`입니다. 어느 stage의 `target_map.table`도 아닌 맵은 `stage_unknown` 경고 + `status: unverified`로 표면화되며 **404가 아닙니다**(임의의 맵도 편집 대상으로 열 수 있어야 하므로).

> **align 실패는 M1·M2 모두 "명시 실패"입니다.** 격자 규격(`wafer_map_metadata`)을 못 찾아 변환을 만들 수 없으면, **raw 좌표로 조용히 계산하지 않고** 해당 role 상태를 `connected(align_unavailable)`로 바꾸고 **카운트를 0으로** 둡니다. (2026-07-27부터 `align` **선언 자체가 없으므로**, 이 상태의 원인은 항상 "메타 미등록/조회 실패" 한 가지입니다.)
> 따라서 상태별 해석은 이렇습니다 — `missing` = 바인딩 선언/테이블 없음 · `connected(align_unavailable)` = 바인딩은 됐는데 격자 규격이 없음(→ `wafer_map_metadata` 행부터 확인) · `connected` = 정상.

### S7. 결손 보정(enrichment) 규칙 추가할 때

| # | 할 일 |
|---|---|
| 1 | `enrichment_rules.json`에 `{규칙명: {...}}` 추가 (§5.3). 루트는 **객체**여야 함 |
| 2 | `source_table`·`derived_table` 모두 `table_config.json`에 등록돼 있어야 함 (아니면 그 규칙 거부) |
| 3 | `derived_table`은 `decision_key`를 `composite_key_source`로 갖는 키 계약을 만족해야 함 |
| 4 | `reference_views[].query`는 **서버에만 존재**하며 클라이언트에 노출되지 않습니다. 파라미터는 `:decision_key_컬럼` 바인딩만 허용 |
| 5 | `POST /admin/reload-configs` — 체인 dedup 룰 자동 파생 + 온톨로지 `RESOLVED_AS` 자동 승격 |
| 6 | 검증: `GET /enrichment/rules` (공개 메타), `GET /enrichment/rules/{name}/references/{index}?params=...` |

상세: [ENRICHMENT_QUEUE_SPEC](../spec/ENRICHMENT_QUEUE_SPEC.md)

### S8. 체인 규칙 추가할 때

| # | 할 일 |
|---|---|
| 1 | `server/mappers/<module>.py`에 맵퍼 함수 작성 |
| 2 | `chain_rules.json`의 `rules[]`에 `{name, trigger_table, target_table, mapper_module, mapper_function, is_batch, enabled}` 추가 |
| 3 | `POST /admin/reload-configs` — `mappers.*` 모듈 캐시 무효화 + 워커 룰 재로드 |
| 4 | 검증: `GET /admin/chain/rules`, `GET /admin/mappers/list` |

상세: [chain_ingestion_guide](./chain_ingestion_guide.md)

---

## 4. 적용·검증 규율 ★

### 4.1 리로드 매트릭스

| 변경 | 반영 방법 | 재기동? |
|---|---|---|
| `table_config` — **신규 테이블 추가** | config watcher(on_modified) 또는 `POST /admin/reload-configs` | 불필요 |
| `table_config` — **기존 테이블에 컬럼 추가(ALTER)** | **config watcher 경로만** (`sync_dynamic_tables_schema`) | 불필요 — 단, watcher 미발화면 재기동 |
| `table_config` — **컬럼 삭제 / 타입 변경** | 어떤 리로드 경로도 하지 않음 | **재기동 필요**(+ 필요 시 수동 마이그레이션) |
| `ontology_mapping` / `chain_rules` / `enrichment_rules` | `POST /admin/reload-configs` | 불필요 |
| `bonding_plan_config` / `transfer_plan_config` / `map_overlay_config` | 없음 — **요청마다 디스크 재읽기** | 불필요 |
| `ingestion_settings` | 없음 — **파일 이벤트마다 재읽기** | 불필요 |
| `auto_update_control` | 없음 — 스케줄러가 매 사이클 재읽기 + API가 실시간 계산 | 불필요 |
| `maps.json` | 없음 — 요청마다 재읽기 | 불필요 |
| 워크스페이스 `config.json`(deprecated) | **핸들러 인스턴스 수명 동안 캐시** | 재기동 |
| 환경변수 전부 / CORS | — | **재기동** |

### 4.2 `/admin/reload-configs`가 하는 일 / **안 하는 일**

**하는 일**
1. `table_config.json` 디스크 재로드 → 동적 ORM 모델 재초기화
2. **신규 테이블 물리 CREATE** (`create_missing_dynamic_tables` — information_schema 게이트 + `checkfirst`)
3. 온톨로지 캐시 무효화, `mappers.*` / `pipeline_plugin_*` 모듈 캐시 퍼지
4. 신규 워크스페이스 동기화
5. outbox에 `SYSTEM_RELOAD` 삽입 + `NOTIFY` → 워커/워처 데몬에 전파

**안 하는 일**
- ❌ **기존 테이블 ALTER를 하지 않습니다.** (락 컨보이 방지 — 의도된 설계)
- ❌ 컬럼 삭제·타입 변경을 반영하지 않습니다. 동적 모델 핫스왑은 **컬럼 append만** 합니다.
- ❌ `bonding_plan_config` / `transfer_plan_config` / `map_overlay_config` / `maps` / `ingestion_settings` / `auto_update_control`은 애초에 캐시가 없어 건드릴 게 없습니다.

**안전장치:** 재로드 시 config가 비었거나 손상됐으면 **기존 싱글턴을 유지**하고 아무것도 바꾸지 않습니다.

### 4.3 물리 반영 검증 — 정확한 방법

> 🚨 **`GET /tables/{t}/schema` 200 응답은 물리 반영의 증거가 아닙니다.** 이 엔드포인트는 **config 싱글턴을 읽습니다.** config에만 있고 DB에는 없는 컬럼도 그대로 200으로 보입니다.

```sql
-- 유일하게 신뢰할 수 있는 확인
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = '<table>'
ORDER BY ordinal_position;
```

```bash
psql -U postgres -d assy_manager -c "\d <table>"
```

### 4.4 config watcher 발화 조건

- 감시 대상은 `server/config/` 디렉터리, **비재귀**.
- **파일명이 정확히 `table_config.json`인 경우에만** 동작합니다. 다른 config 파일은 아무 것도 트리거하지 않습니다.
- **`on_modified` 이벤트만** 처리합니다(`on_created`/`on_moved` 핸들러 없음). 1초 디바운스.
- 프로세스별로 동작이 다릅니다: 웹서버는 engine을 갖고 시작하므로 **CREATE + ALTER**를 수행하지만, watcher/chain 워커 프로세스는 `engine=None`으로 시작해 **ORM만 갱신하고 물리 DDL은 하지 않습니다.**

---

## 5. 최소 예시 스니펫

모두 실제 `.sample` / 실 config에서 발췌한 것입니다. **허구 필드 없음.**

### 5.1 `table_config.json` — 테이블 1개

```json
{
  "bonding_map": {
    "business_key": "pkg_id",
    "composite_key_source": ["base", "x", "y"],
    "composite_key_separator": "_",
    "column_types": {
      "pkg_id": "string",
      "base": "string",
      "x": "number",
      "y": "number",
      "leg": "string"
    },
    "display_columns": ["pkg_id", "base", "x", "y", "leg"],
    "map_key_columns": ["base"]
  }
}
```

| 키 | 의미 |
|---|---|
| `business_key` | 사용자 관점 키 컬럼명(필수) |
| `composite_key_source` | 복합 bk를 구성할 컬럼 목록. 지정 시 `business_key` 값이 이들의 조합으로 자동 생성됨 |
| `composite_key_separator` | 조합 구분자 — **기본 `"_"`** |
| `column_types` | `"string"` / `"number"` / `"datetime"` — 그 외 값은 전부 `String`으로 처리. `created_at`·`updated_at`·`is_graph_synced`·`needs_graph_rollback`·`graph_synced_at`는 시스템 컬럼이라 여기 쓰지 않음 |
| `display_columns` | 그리드 표시 순서 + **표준 파서의 헤더 검증·적재 대상 집합**. 생략 시 ORM 컬럼 introspection 폴백 |
| `map_key_columns` | 맵 replace 시 삭제 범위 한정 키(맵 테이블 전용) |
| `workspace_name` | 폴더명 ≠ 테이블명일 때의 폴더 별칭 |
| `std_parse` | 표준 파서 폴백 on/off. **JSON boolean만 유효** — 문자열 `"false"`는 무시+경고 |
| `source_priority` | (선택) 전역 소스 우선순위 맵의 테이블별 오버라이드 |

### 5.2 `ontology_mapping.json` — 테이블 1개

```json
{
  "wafer_slot_history": {
    "description": "wafer가 공정 step을 통과한 이력 (wafer_id 기준 실개체 노드의 소스)",
    "node": {
      "label": "Wafer",
      "identity": "wafer_id",
      "props": ["lot", "slot"]
    },
    "edges": [
      {
        "type": "WENT_THROUGH",
        "target_label": "Step",
        "target_identity_from": ["step"],
        "props": ["event_time", "lot", "slot"],
        "description": "wafer가 이 공정 step을 통과한 이벤트"
      }
    ]
  }
}
```

`identity`는 단일 컬럼명(`"wafer_id"`) 또는 복합(`["core_lot","core_slot"]`) 모두 가능합니다. `props` 항목은 문자열이거나 `{"col": "bx", "spatial": {"coord_system": "base_grid", "axis": "x"}}` 형태의 객체일 수 있습니다.

### 5.3 `enrichment_rules.json` — 규칙 1개

```json
{
  "core_wafer_attribution": {
    "source_table": "bonding_log",
    "derived_table": "core_wafer_map",
    "decision_key": ["core_lot", "core_slot"],
    "target_fields": ["wafer_id"],
    "list_columns": ["chip_count", "eventtime"],
    "aggregations": { "chip_count": "count" },
    "enabled": true,
    "reference_views": [
      {
        "label": "lot-slot 웨이퍼 이력",
        "query": "SELECT step, lot, slot, wafer_id, event_time FROM wafer_slot_history WHERE lot = :core_lot AND slot = :core_slot ORDER BY event_time DESC",
        "limit": 200
      }
    ]
  }
}
```

### 5.4 `chain_rules.json`

```json
{
  "rules": [
    {
      "name": "production_to_inventory_reservation_batch",
      "trigger_table": "production_plan",
      "target_table": "inventory_master",
      "mapper_module": "mappers.production_mapper",
      "mapper_function": "reserve_materials_batch_df",
      "is_batch": true,
      "enabled": true
    }
  ]
}
```

### 5.5 `auto_update_control.json`

```json
{ "disabled": ["bonding_map/fetch_data.py"] }
```

### 5.6 `ingestion_settings.json`

```json
{ "heavy_file_mb": 10 }
```

### 5.7 `bonding_plan_config.json` — 발췌

```json
{
  "core_identity": { "compose": ["lot", "slot"] },
  "map_metadata": {
    "table": "wafer_map_metadata",
    "columns": { "target_table": "target_table", "map_id": "map_id", "grid_metadata": "grid_metadata" }
  },
  "sources": {
    "used_chips": {
      "table": "bonding_log",
      "columns": { "lot": "core_lot", "slot": "core_slot", "x": "cx", "y": "cy" }
    },
    "eds_fail": {
      "mode": "map",
      "table": "eds_fail_map",
      "columns": { "lot": "lot", "slot": "slot", "x": "x", "y": "y", "val": "val" },
      "fail_values": ["F"]
    }
  },
  "warnings": { "result_fail_values": ["FAIL"] }
}
```

> **`sources[].align`이 사라진 자리** — canonical 프레임은 메타가 등록된 **첫 맵 모드 역할**(`total_chips` → `defect` → `eds_fail` 순)이고, 나머지 맵은 자기 메타와의 델타로 그 프레임에 투영됩니다. 실제로 위 예시의 `eds_fail`에 선언돼 있던 `rotation: 180`은 `eds_fail_map` 메타의 rotation과 **정확히 같은 값**이었습니다 — 선언이 메타의 손수 관리하는 복사본이었다는 뜻입니다. 복사본이 정본과 어긋나면 어느 쪽이 참인지 알 방법이 없어 폐지했습니다.

### 5.8 `transfer_plan_config.json` — stage 선언 발췌

```json
{
  "stages": {
    "dt": {
      "description": "DT(Die Transfer): 코어 웨이퍼의 칩을 테이프에 전사하는 단계.",
      "source_kind": "core",
      "target_kind": "tape",
      "source_config_ref": "bonding_plan",
      "target_map": { "preset": "TAPE", "table": "dt_map" }
    }
  },
  "plan_store": {
    "doe": {
      "table": "map_doe",
      "columns": {
        "ref_table": "ref_table", "map_key": "map_key", "doe_value": "doe_value",
        "band_seq": "band_seq", "stack_band": "stack_band", "qty_total": "qty_total",
        "knobs": "knobs", "note": "note"
      }
    },
    "doe_source": {
      "table": "map_doe_source",
      "columns": {
        "ref_table": "ref_table", "map_key": "map_key", "doe_value": "doe_value",
        "band_seq": "band_seq", "source_lot": "source_lot", "source_slot": "source_slot",
        "qty": "qty", "note": "note"
      }
    }
  }
}
```

> **DOE 행의 단위는 `(값, STACK 구간)`입니다.** 한 값이 구간을 여러 개 가질 수 있어(`A|H1~H2`, `A|H2~H3`) bk가 `ref_table|map_key|doe_value|band_seq`이고, 자재 묶음(`doe_source`)은 **그 구간 아래에** 붙습니다 — 구간마다 다른 묶음이 가능합니다.
>
> ⚠️ **구간 정체는 `band_seq`(정수 서수)가 지고, 사람이 읽는 표기 `stack_band`는 비키 컬럼입니다.** 자유 텍스트를 키에 넣으면 ①bk 조립이 구분자 `|`를 이스케이프하지 않아 라벨에 `|`가 섞이면 키가 모호해지고 ②키 컬럼이 바뀌면 행이 **re-key**되므로 라벨을 고치는 순간 하위 자재 행이 고아가 됩니다. 라벨은 `1`/`2-11`/`H1~H2`/`바닥` 무엇이든 자유이며 정규화가 필요 없습니다.
>
> 매별 소요는 지정 대상이 아니라 구간 `qty_total`의 **균등 배분**(올림)이며, `doe_source.qty`가 있으면 그것이 우선합니다. 값 단위 속성(설명·색)은 `map_split_registry`가 정본이라 `map_doe`에 중복 저장하지 않습니다.

> **`.sample`은 위 발췌와 일치합니다(2026-07-26 정정 완료).** `transfer_plan_config.json.sample`의 `plan_store`에서 v1 잔재 역할(`plan`/`map`/`doe_layer`)과 폐기 컬럼(`plan_id`·`layer_from`·`layer_to`·`qty_per_unit`)을 제거하고, 코드가 실제로 요구하는 `doe`(필수 `ref_table`·`map_key`·`doe_value`·`band_seq`) / `doe_source`(필수 위 4개 + `source_lot`·`source_slot`) 바인딩으로 교체했습니다. 두 바인딩이 가리키는 `map_doe`·`map_doe_source`는 **제품 소유 저장소**라 `table_config.json.sample`에 함께 선언돼 있습니다 — `.sample` 3종(`table_config`·`transfer_plan_config`·`map_overlay_config`)을 복사하면 `plan_store`는 바로 `connected`입니다.
>
> `map_overlay_config.json.sample`에서도 폐기 테이블 `transfer_plan_map`의 `table_bindings`·`paint_lock` 항목을 제거했습니다 — 계획 캔버스의 잠금은 그 stage의 `target_map` 테이블(`bonding_map`/`dt_map` 등)에 직접 선언합니다.
>
> **`source_region`(자재별 사용 영역 스코프)은 휴면이라 `.sample`에 넣지 않았습니다.** 미선언은 결함이 아니며(`plan_store`에 키 자체가 안 나옵니다), 선언만 하고 테이블이 없으면 도리어 `missing` 소음이 됩니다. 켜려면 `plan_store.source_region`에 `(ref_table, map_key, source_lot, source_slot, x, y)` 바인딩을 추가하고 그 테이블을 `table_config.json`에 선언하십시오.

### 5.8-bis `map_overlay_config.json` — 키 구조

> 실값은 각 환경의 로컬 자산이므로 **키 구조만** 수록합니다.

```
table_bindings.<table>.columns.{x, y, val, key_columns[]}
paint_lock."*".{enabled, blocking_values[], from_overlay[], message}
paint_lock.<table>.{enabled, blocking_values[], from_overlay[], message}
```

> 🗑️ **[폐지 2026-07-27] `align_overrides`** (`<table>.default` · `<table>.by_eqp.<eqp_id>`)
> 정렬의 유일한 근거는 **`wafer_map_metadata`**입니다. 계측으로 잰 어긋남도 별도 선언이 아니라 **그 맵의 메타에 기록**합니다.
> - 파일에 키가 남아 있어도 **서버는 무시합니다** — 지우십시오(무시된다는 사실이 테스트로 고정돼 있습니다).
> - 왜 지웠나: 근거가 둘이면 메타와 선언이 어긋났을 때 **어느 쪽이 참인지 알 수 없습니다.** 라이브 선언 하나는 실제로 해당 맵 메타의 rotation과 값이 같은 **손수 관리하는 복사본**이었습니다.
> - **정렬을 켜는 올바른 방법은 오버라이드 선언이 아니라 소스·타깃 맵의 메타 등록입니다** → [MAP_EDITOR_SPEC §5.0](../spec/MAP_EDITOR_SPEC.md).

| # | 할 일 |
|---|---|
| 1 | **아무것도 선언하지 않아도 오버레이는 동작합니다** — `table_bindings`는 `table_config`의 `map_key_columns` + x/y/val 후보에서 자동 유도되고, align은 `wafer_map_metadata` 델타(rotation·side·y반전·start·치수·phys)에서 유도됩니다 |
| 2 | 컬럼명이 관례 밖일 때만(`dt_log`의 `tx/ty` 등) `table_bindings`를 선언합니다 |
| 3 | `paint_lock`은 **`"*"` 기본 선언 + 테이블별 오버라이드**가 머지됩니다. 기본값은 `F` 잠금 |
| 4 | 검증: `GET /api/maps/paint-rules?table=<t>` → `GET /api/maps/overlay?target_table=&target_key=&sources=<t>:<key>` 응답의 `overlays[].status`와 `align_applied.origin`(`derived`/`identity`) 확인 |

> **`align_unavailable`은 "선언이 없다"가 아니라 "변환을 계산할 근거가 없다"입니다.** 메타 부재는 실패가 아니며 identity로 붙습니다(다만 **미등록은 정상이 아니라 누락 신호**입니다). 자세한 계약은 [MAP_EDITOR_SPEC §5](../spec/MAP_EDITOR_SPEC.md).

> ⚠️ **위 표는 서버 엔드포인트(`/api/maps/overlay`) 기준입니다.** `7d931dc` 이후 **맵 에디터 클라는 이 좌표를 소비하지 않고 변환을 자체 수행**합니다. 선언 레이어가 사라지면서 클라의 선언 probe 관문(`probeAlignDeclaration`)과 그 산물인 실패 status 2종(`align_unconfirmed`·`align_override_declared`)도 함께 삭제됐습니다 — 오버레이 추가의 REST 왕복이 하나 줄었습니다.
>
> `GET /api/maps/overlay`의 `eqp` 쿼리 파라미터는 **no-op으로 존치**돼 있습니다(`by_eqp` 전용이었음). 넘겨도 아무 일도 일어나지 않습니다.

### 5.8-ter 기능별 필요 테이블 체크리스트

> **바인딩 config는 `table_config.json`에 선언된 테이블만 해석합니다.** 미선언 테이블을 가리키는 바인딩은 조용히 죽지 않고 해당 역할이 `missing`으로 표면화됩니다(`bonding_plan._resolve_model_columns`). 그래서 기능을 켜는 순서는 항상 **① `table_config.json`에 테이블 선언 → ② 바인딩 config의 `table`/`columns`를 그 이름에 맞춤**입니다.

테이블은 **누가 스키마를 정하는가**로 갈립니다.

| 구분 | 뜻 | `.sample` 취급 |
|---|---|---|
| **제품 소유** | assyManager 자신의 저장소. 이름·컬럼을 제품이 정하며 현장이 바꿀 이유가 없습니다 | `table_config.json.sample`에 **선언돼 있습니다** — 그대로 쓰십시오 |
| **현장 소유** | 고객 공장의 실 데이터. **운영 환경마다 테이블명·컬럼명이 다릅니다** | **선언하지 않습니다.** 예시 스키마를 박으면 표준이 있는 것처럼 오해되기 때문입니다 — 당신의 실제 이름으로 직접 선언하십시오 |

**제품 소유(`table_config.json.sample`에 이미 선언됨 — 그대로 쓰십시오):**

> **정의의 원본은 `server/product_tables.py` 하나입니다(2026-07-27).** `.sample`조차 그 모듈에서 생성된 산출물이라 두 번째 목록이 존재하지 않습니다.
> **이미 쓰던 `table_config.json`에 넣을 때는 손으로 옮기지 말고 설치 스크립트를 쓰십시오.**
>
> ```bash
> python server/scripts/install_product_tables.py            # dry run (기본)
> python server/scripts/install_product_tables.py --apply    # 반영(백업 후)
> python server/scripts/install_product_tables.py --sample --apply   # .sample 재생성
> ```
>
> - **현장 항목은 재직렬화하지 않습니다** — 원본 텍스트에 바이트 스플라이스로 끼워 넣으므로 키 순서·들여쓰기·줄바꿈·개행문자가 보존됩니다. `json.load`/`json.dump` 왕복은 건드리면 안 될 항목까지 재포맷합니다.
> - 없으면 추가 / 동일하면 **무기록** / **다르면 드리프트로 보고만 하고 손대지 않음**(`--overwrite-drift` 필요).
> - `--apply`는 타임스탬프 백업을 먼저 쓰고, 반영 후 손대지 않은 항목을 바이트 대조해 **어긋나면 백업을 복원**합니다.
> - **DDL은 하지 않습니다.** 선언이 물리 테이블이 되는 것은 §4.1 리로드 경로의 일이며, 스크립트가 어느 경로가 필요한지 출력합니다.
> - 종료코드: `0` 할 일 없음 · `1` 조치 필요 · `2` 오류.

| 테이블 | 역할 | bk 규칙 |
|---|---|---|
| `map_doe` | 전사 계획 DOE 정의 | `ref_table\|map_key\|doe_value\|band_seq` (구분자 `\|`) |
| `map_doe_source` | DOE 구간의 자재(소스) 묶음 | 위 + `\|source_lot\|source_slot` |
| `map_split_registry` | 맵 값(legend) 레지스트리 — `split_desc`·`color`의 정본 | `ref_table\|map_key\|value` (구분자 `\|`) |
| `wafer_map_metadata` | 격자 규격(`grid_metadata`) | `target_table_map_id` |

> 위 네 테이블의 **`composite_key_separator`를 바꾸지 마십시오.** `map_key`가 `_` 조인 문자열이고 테이블명에도 `_`가 흔해 `_` 구분자로는 키가 모호해집니다(클라이언트의 `SPLIT_KEY_SEP`와도 일치해야 합니다).

> `table_config.json.sample`의 나머지 엔트리(`bonding_map`, `inventory_master`, `production_plan`, `parts`, `large_table_100`)는 **동작 예시**입니다 — 제품이 이름을 강제하는 저장소가 아니므로 현장 테이블로 교체하거나 지워도 됩니다.

**기능을 켜려면 아래 테이블을 당신의 실제 이름/컬럼으로 `table_config.json`에 선언한 뒤, 바인딩의 `table`/`columns`를 그 이름으로 맞추십시오.**

| 기능 | 바인딩 config | 현장 소유 테이블 (역할) |
|---|---|---|
| **전사 계획 (M2)** — stage 소스 가용·validate | `transfer_plan_config.json` | `dt_map`(DT 타깃 맵) · `dt_log`(테이프↔코어 전사 로그 = tape stage의 `total_chips`/`origin_log`) · `bonding_map`(BONDING 타깃 맵) · `bonding_log`(기전사 로그) · `core_defect_map` · `eds_fail_map`(fail 원천) · `wafer_process`(이력) |
| **본딩 가용량 (M1)** — core-summary | `bonding_plan_config.json` | `bonding_log`(기사용 칩) · `core_defect_map` · `eds_fail_map` · `wafer_process` |
| **결손 보정 (enrichment)** | `enrichment_rules.json` | `source_table`로 쓸 원천(샘플 예: `bonding_log`) · `derived_table`로 쓸 파생(샘플 예: `bonding_job_inventory`, `decision_key`를 `composite_key_source`로 갖는 키 계약 필요) |
| **맵 오버레이** | `map_overlay_config.json` | 겹쳐 볼 맵 테이블 전부. **단 선언 없이도 동작합니다**(`table_config`에서 자동 유도) — 컬럼명이 관례와 다를 때만 선언 |

> 위 표의 이름(`dt_log`, `bonding_log` …)은 **`.sample`이 쓰는 예시일 뿐 표준이 아닙니다.** 현장 테이블명이 다르면 그 이름 그대로 선언하고 바인딩만 맞추면 됩니다 — 코드는 실테이블명을 하드코딩하지 않습니다.

> 검증: `GET /api/transfer-plan/stages`의 `roles`·`plan_store` / `GET /api/bonding-plan/core-summary`의 role 상태가 `connected`인지 확인하십시오. `missing`이면 ①테이블 미선언 ②바인딩의 컬럼명 오타 ③필수 역할키 누락 순으로 의심하십시오.

### 5.9 `maps.json` — 프리셋 1개 (**UI로 관리 권장**)

```json
{
  "presets": {
    "core_std": {
      "name": "CORE",
      "phys_wafer_dia": 300.0,
      "phys_chip_x": 7.0,
      "phys_chip_y": 7.0,
      "phys_offset_x": 0.0,
      "phys_offset_y": 0.0,
      "phys_edge_margin": 3.0,
      "rotation": 0,
      "side": "front",
      "is_custom": true
    }
  }
}
```

---

## 6. 함정 모음 ★

**A. `table_config.json` JSON 문법 오류는 조용히 전 테이블을 날립니다.**
로더는 파싱 실패 시 **로그 없이 `{}`** 를 반환합니다. 저장 직후 반드시 유효 JSON인지 확인하십시오.
(다행히 `refresh_dynamic_models`는 빈 config면 기존 싱글턴을 유지하므로 가동 중 서버는 즉사하지 않지만, **재기동하면 모든 테이블이 사라집니다.**)

**B. 에디터의 "원자적 저장"(temp + rename)은 config watcher를 발화시키지 않습니다.**
watcher는 `on_modified`만 처리합니다. temp 파일에 쓰고 rename하는 도구(일부 에디터·에이전트 Edit 도구)로 `table_config.json`을 고치면 **ALTER가 조용히 누락**됩니다.
→ 저장 후 §4.3의 `information_schema` 확인을 습관화하고, 미발화 시 **in-place 재기록**으로 발화시키십시오.

**C. `/admin/reload-configs`는 ALTER를 하지 않습니다.**
"리로드했는데 컬럼이 안 생겼다"의 대부분이 이것입니다. 신규 테이블 CREATE는 되고, 기존 테이블 컬럼 추가는 **config watcher 경로**입니다.

**D. `GET /tables/{t}/schema`가 200이어도 물리 반영 증거가 아닙니다.** (§4.3)
config 싱글턴을 읽을 뿐입니다. 또한 **전역 `/schema` 경로는 존재하지 않습니다** — 없는 경로는 정적 catch-all이 **HTML을 200으로** 반환해 성공처럼 보입니다. 응답이 JSON인지 확인하십시오.

**E. `"std_parse": "false"`(문자열)는 옵트아웃이 아닙니다.**
JSON boolean `false`만 유효합니다. 문자열은 무시 + 경고 후 기본값 `true`로 동작합니다.

**F. 컬럼 삭제·타입 변경은 어떤 핫리로드 경로도 반영하지 않습니다.**
동적 모델 갱신은 **컬럼 append 전용**이고, 물리 스키마 동기화도 `ADD COLUMN` 전용입니다. 삭제/재타입은 재기동 + 수동 마이그레이션 영역입니다.

**G. `workspace_name` 별칭 섀도잉.**
별칭이 다른 실존 테이블명과 같으면(자기 자신 제외) 무시 + ERROR 로그. 복수 테이블이 같은 별칭을 선언해도 전부 무효화. 경로 구분자·드라이브 접두(`C:foo`)처럼 워크스페이스 루트의 **직속 자식으로 해석되지 않는 별칭**도 거부됩니다.

**H. 하위 config가 참조하는 테이블/컬럼은 `table_config`에 반드시 실존해야 합니다.**
`ontology_mapping` / `enrichment_rules`는 미등록 참조를 만나면 해당 항목을 **통째로 스킵**합니다 — 조용히 그래프 노드가 안 생기거나 워크리스트가 비는 형태로 드러납니다.

**I. 계획 config는 "부분 가동"이 정상 동작입니다.**
role이 빠지거나 테이블이 없으면 **에러가 아니라 `missing`** 이고, HTTP는 200으로 나옵니다. **숫자가 0인데 에러가 없다면 응답의 `sources` 상태부터 확인**하십시오 — `missing`(바인딩 문제)인지 `connected(align_unavailable)`(격자 규격 없음)인지에 따라 고칠 곳이 다릅니다.

**J. `.sample`을 편집해도 아무 일도 일어나지 않습니다.**
코드는 확장자 없는 정확한 파일명만 읽습니다. `.bak` / `.v1.bak`도 마찬가지입니다.

**K. `scheduler_status.json`은 입력이 아니라 출력입니다.**
스케줄러가 매 사이클 덮어씁니다. 손으로 고쳐도 무의미하며, `active` 필드는 API가 `auto_update_control.json`에서 실시간으로 다시 계산해 덮어씁니다.

**L. `server/config/*.json`은 어드민 UI에서 편집할 수 없습니다.**
Monaco 코드 에디터는 `.py`(맵퍼·인제션·수집기 스크립트)만 다룹니다. 예외적으로 맵 프리셋과 수집기 토글만 전용 API가 있습니다.

**M. `table_config`에 없는 컬럼은 저장에서 조용히 버려지고 HTTP는 200입니다.** ★
`crud`는 미선언 컬럼을 드롭한 뒤 성공을 반환합니다 — 컬럼 오타·config 누락이 **저장 성공처럼 보입니다.** 실제로 `map_doe`가 이 경로로 `eventtime`을 잃고 있었습니다.
2026-07-27부터 **`(테이블, 컬럼)`당 1회** `[Schema]` 경고가 남습니다(핫패스라 반복 경고는 접습니다). 값이 안 들어갈 때 의심 순서: ①`table_config`에 그 컬럼이 있는가 ②철자 ③리로드 경로(§4.1).
> ⚠️ 이 경고가 **워처 프로세스의 로그 파일에는 아직 안 남습니다** — [PRODUCTION_READINESS](../process/PRODUCTION_READINESS.md) B3.

**N. 격리 환경에서 config를 고쳤는데 운영이 안 바뀝니다(그리고 그 반대도).**
`ASSY_DATA_ROOT`가 걸려 있으면 config 트리 전체가 `dev_env/config`입니다. 어느 쪽을 고쳤는지 헷갈리면 `python server/scripts/dev_env/devenv.py status`로 확인하십시오 → [DEPLOY_SETUP §5](./DEPLOY_SETUP.md).

---

## 7. 새 환경 부트스트랩 (요약)

1. `server/config/*.sample` → 확장자 제거해 복사 (필요한 것만).
2. `table_config.json`을 실제 스키마로 채운다. **이미 쓰던 파일이 있으면** 제품 소유 4종은 `install_product_tables.py --apply`로 병합한다(§5.8-ter).
3. 서버 기동 → 부팅 시 물리 스키마 정합(create_all + ADD COLUMN 동기화)이 1회 수행됨.
4. `information_schema`로 테이블·컬럼 확인(§4.3).
5. 워크스페이스 자동 생성 확인 → 파서/수집기 배치.
6. 필요에 따라 S4·S6·S7·S8.
7. `GET /health`가 **JSON 200**인지 확인한다(워커 4종이 `ok`인지 포함) → [backend §1.3](../architecture/backend.md).

환경 구성 자체는 [CONDA_SETUP_GUIDE](./CONDA_SETUP_GUIDE.md) · [NATIVE_POSTGRES_SETUP_GUIDE](./NATIVE_POSTGRES_SETUP_GUIDE.md) · [SERVER_STARTUP_GUIDE](./SERVER_STARTUP_GUIDE.md) 참조.
