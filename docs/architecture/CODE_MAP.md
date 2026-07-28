# 🗺️ CODE_MAP — 압축 구조 지도 (파일 전량 읽기 방지용)

> **Status:** 🟢 Living | **Last-verified:** 2026-07-28 (**HEAD `6db517d`의 커밋된 blob 실측** — 워킹트리 아님. [§0 측정 기준](#0-묘비-목록--소스에-존재하지-않는-이름)) | **Owner:** 전 에이전트 공용 | **Source-of-truth:** 각 표의 코드 경로
> 상위: [SYSTEM_OVERVIEW (SSOT)](../overview/SYSTEM_OVERVIEW.md)

**⚠️ 사용 규칙 — 이 문서가 존재하는 이유:**
- **소스 파일을 통째로 Read하지 말 것.** 이 지도에서 함수·라인을 찾은 뒤 **해당 섹션만** `Read(offset, limit)`로 읽는다.
- 라인 앵커는 **±20줄 오차 허용**. 정확 위치는 Grep으로 확정. ⚠️ **오차 허용은 "가까운 줄로 가면 된다"가 아니다** — 실측 사례: `_band_to`가 65줄 밀리자 그 앵커 자리에 **`_band_materials`라는 실재하는 다른 함수**가 들어앉았다. 도착지가 멀쩡해 보이므로 아무것도 이상해 보이지 않는다. **함수명으로 Grep해 확인하고 나서 읽어라.**
- `client2/*` 앵커는 **`client2/src/`**(원본) 기준이다 — `client2/dist/assets/map_editor-*.js`는 vite 산출물이라 파일명 해시가 빌드마다 바뀐다. **dist 번들명을 문서에 고정 인용하지 말 것.**
- 이 문서는 **지도이지 교과서가 아니다** — 구현 설명은 각 리빙 문서([backend](./backend.md)·[data_model](./data_model.md)·[frontend](./frontend.md)·[event_driven_backend](./event_driven_backend.md)) 참조.

**유지보수 규율:** 코드맵 갱신은 **code-mapper 전담**(2026-07-27 문서 에이전트 분할 — 리빙 문서·`PRIMITIVES.md`는 doc-keeper, 히스토리는 doc-historian, 정합 감사는 doc-auditor). code-mapper는 **커밋된 소스와 직접 대조**해 갱신한다(보고서 요약이 아니라 `git show <hash>:<path>` 실측 — 워킹트리는 타 에이전트가 동시 편집 중일 수 있다). 구현 에이전트는 맵을 직접 수정하지 않고 보고서에 변경 함수/시그니처 목록만 남긴다. 라인은 보조 식별자이고 **함수명·시그니처가 1차 식별자**다.

---

## 0. 묘비 목록 — 소스에 **존재하지 않는** 이름

> **이 목록의 존재 이유**: 삭제된 심볼이 문서 어딘가에 살아남으면 **다른 에이전트가 없는 것을 찾으러 간다.** 더 나쁜 실패는 한 절이 "이 이름은 삭제됐다"고 경고하면서 다른 절이 그 이름을 **현행 앵커로 쓰는** 것이다 — 그 경고가 "이 파일은 감사됐다"는 증거로 읽히기 때문이다(2026-07-27 실제 발생: §7이 경고하고 §8이 사용했다).
>
> **그래서 이 목록은 단언이 아니라 검사다.** 아래 명령의 기대 결과까지 적어 둔다 — 결과가 달라지면 **이 절이 낡은 것이다**(명령이 틀린 게 아니라).
>
> ⚠️ **명령에 리비전을 박지 않는다 — 의도적이다.** 초판은 `0f8d35f`에 고정돼 있었고, 그래서 **구조적으로 초록불이었다**: 얼어붙은 스냅샷을 검사하는 명령은 파일이 썩어도 영원히 통과한다. 실제로 그 상태에서 두 라운드가 더 들어와 `_parse_bands`의 시그니처가 3-튜플이 되고 `_band_materials`가 **다른 함수의 앵커 자리(1188)를 차지**했지만 §0은 여전히 초록이었다. **검사는 지금 파일을 읽어야 검사다.** 그 대신 **라인 앵커와 §0은 서로 다른 보증**이라는 점을 알아 둘 것 — 앵커는 아래 "측정 기준"의 스냅샷이고, §0은 실행 시점의 트리다.
>
> ```bash
> # ① 클라 저장 기계장치 — 히트 0건이어야 한다
> git grep -n "putUpdates\|adoptServerDoe\|doeRowKey\|doeSourceRowKey\|doeServerLoaded\|serverRows\|deleteUnsent\|pruneScoped\|serverKeys\|DRAFT_PREFIX" -- client2/src
> # ② 서버 심볼 — 히트 0건이어야 한다
> git grep -n "_doe_get\|def _num\|_band_range" -- server/transfer_plan.py
> # ③ layer_coverage_gap — 정확히 2건이고 **둘 다 묘비**다 (2026-07-28 재측정: 테스트
> #    주석은 b35bc9f의 테스트 재작성과 함께 사라졌다):
> #    server/transfer_plan.py             삭제 사유 주석(zone 모델에선 구멍이 표현 불가)
> #    client2/src/transfer_plan.js        __HELD_WARN_SEVERITY의 사문 키 (보류 구역, 호출자 없음)
> git grep -c "layer_coverage_gap" -- server client2
> # ④ 이 문서 안 — 히트는 전부 묘비 문맥이어야 한다(살아있는 앵커 0건)
> grep -n "adoptServerDoe\|doeRowKey\|deleteUnsent\|_doe_get\|layer_coverage_gap" docs/architecture/CODE_MAP.md
> ```
>
> **측정 기준 (라인 앵커가 가리키는 상태)**: **전 절이 HEAD `6db517d`의 커밋된 blob 실측**이다(`git show 6db517d:<path>` 기준, 2026-07-28). 검증용 blob 해시(`git rev-parse 6db517d:<path>` 선두 7자):
> `server/transfer_plan.py` = `6740e30` · `contracts/band_arithmetic/vectors.json` = `861a031` · `client_harness.mjs` = `ebd25cc` · `client2/src/map_editor.js` = `083c24d` · `client2/src/transfer_plan.js` = `4f8110f` · **`client2/src/doe_bands.js` = `bfb49cb`(이번 패스에 추가 — zone 코어라 앵커 밀도가 높다)** (`git hash-object <path>`로 대조). **이 값이 다르면 해당 절의 라인 앵커는 재측정 대상**이고, 함수명으로 Grep해서 쓰라.
>
> 💡 **이 해시가 실제로 일한 기록**: 한 패스에서는 `vectors.json`이 도중에 바뀌어(`17698dd`→`8696ea7`) 막 적은 서술이 즉시 낡은 것을 잡았고, 한 패스(2026-07-28 오전)에서는 다섯 해시 전부가 불일치로 나와 **다섯 파일 전체 재측정**의 근거가 됐다 — zone 모델 착지(`b35bc9f`)로 `transfer_plan.py`가 1,815→3,019줄, `map_editor.js`가 4,873→5,466줄이 됐고, 같은 날 후속 패스(`2baf9ff` U9 marker + `6db517d` H1/H2)에서는 계약 파일 둘만 일치하고 소스 셋이 전부 불일치라 재측정 범위를 정확히 그 셋(+`doe_bands.js`)으로 좁혀 줬다. 검사는 통과할 때도 실패할 때도 일을 한다.
>
> ⚠️ **해시가 보증하지 않는 것**: 이 다섯 파일 밖의 앵커는 해시로 지켜지지 않으므로 **패스마다 다시 재야 한다.** 실사례(2026-07-27 패스): 그 범위가 **건드리지도 않은** 파일들이 이미 밀려 있었다 — `directory_watcher.py` 최대 +53줄, `process_supervisor.py`는 선언 431줄 대비 실제 **709줄**. 실사례(2026-07-28 패스): `main.py`는 이번 범위(`b35bc9f`·`280ebf0`)에 없지만 앞선 `ec75d4c`·`269b39e`로 **최대 +72줄** 밀려 있었다. 커밋 diff만 따라가는 갱신은 이런 것을 영원히 못 본다.
>
> ⚠️ **왜 "커밋된 blob"이라고 못박는가 — 2026-07-27 패스에서 실제로 일어난 일**: 착수 시점에 워킹트리가 클린이었으나, 그 절을 쓰는 동안 다른 에이전트들이 `server/main.py`·`crud.py`·`models.py`·`schemas.py`를 **동시 편집**해 트리가 갈라졌다. 앵커를 워킹트리에서 쟀다면 **아무도 리뷰하지 않은 중간 상태**가 지도에 박혔을 것이다. 그래서 이 지도의 모든 앵커는 `git show <Last-verified HEAD>:<path>` 기준이다 — 라인이 아니라 **함수명으로 Grep하라**는 규율이 특히 동시 편집이 잦은 파일들에 적용된다.
>
> ⚠️ **`plan_store.doe`는 예외적으로 소스에 남아 있다** — 폐기된 `map_doe`의 `__comment` 안(`product_tables.py:105` 및 그것이 생성한 `table_config.json.sample`)에서 "historical description" 구간의 일부다. **낡은 주석이 운영자를 능동적으로 오도하는** 바로 그 사례이며, `install_product_tables.py --sync-comments`가 그래서 생겼다(`tests/test_install_product_tables.py:231`이 이 시나리오를 이름으로 기술한다).

| 삭제된 이름 | 있던 곳 | 대체물 (현행) |
|---|---|---|
| `putUpdates` · `scheduleServerSave` · `saveDoeToServer` · `loadDoeFromServer` · **`adoptServerDoe`** · `doeRowKey` · `doeSourceRowKey` · `S.doe` · `S.doeServerLoaded` · **`S.serverRows`** · **`S.deleteUnsent`** · `S.loadSeq` · `DRAFT_PREFIX` · `cannotExpress` · `planTablesSupported` · `blankBand` · `summaryStatusOf` | `client2/src/transfer_plan.js` (구 DOE 저장 기계장치) | **`map_editor.js`의 Split Registry 블록** — 권한은 **`legendReplaceScope`**, 동시성은 **`legendConflict`**(M2.6 추가: upsert로 **강등하지 않고 거부**한다), 쓰기는 `saveLegendToServer`(호출자는 `pushMapData` 하나), 초안은 `saveDoeDraft`/`applyDoeDraftRecord`. 패널 측 관문은 `commitRow` → `controller.updateLegendRow`. (`DRAFT_VERSION`은 `map_editor.js`에 **되살아났다** — 초안 레코드 버전 상수, 현재 `3`) |
| **`scheduleLegendServerSave`** (legend 디바운스 자동 저장) | `client2/src/map_editor.js` | **자동 저장 자체가 삭제**됐다(사용자 지시 2026-07-28) — 서버 쓰기는 **⚡ Push(`pushMapData` → `saveLegendToServer`) 하나**뿐이고, 편집 경로는 전부 `scheduleCellDraft`(로컬 초안)로만 흐른다. 묘비 주석이 ~2899에 있다 |
| `fetchLegendFromServer` · `loadLegend` | 〃 (구 legend 서버 로드) | `fetchRegistryRows`/`readRegistryScope`/`applyRegistryRowsToLegend` — **map_key 스코프 읽기만** 남았다(`REGISTRY_SCOPES=['map']`). 테이블 전체 어휘 시드는 `269b39e` 결함(남의 맵 DOE 전파)의 원인이라 삭제, 계약은 `contracts/legend_map_scope/` |
| `bandTo` · `bandLayers` · `bandTotal` · `bandShare` · `commitBands` · `commitKnobs` · `bandsOf` · `knobsOf` · `validateBands` · `sortBands` · `nextBandSeq` · `cloneBand` | `client2/src/transfer_plan.js` (구 band 편집기 산술) | **zone 모델로 이전** — 산술은 `doe_bands.js`의 `zoneLayers`/`zoneDemand`/`materialRollupRows`, 쓰기 관문은 `commitRow`. `bandToState`·`prevTo`만 레거시 `bands` 읽기용으로 잔존(export ~232). **`contracts/band_arithmetic/client_harness.mjs`가 앞 4개의 부재를 능동 단언**한다(되살아나면 exit 2) |
| `pruneScoped` · `S.serverKeys` | 〃 (구 클라측 차집합-후-삭제) | `replace_map`(`crud.apply_batch_updates`) — `3ebd38e`에서 제거 |
| `_doe_get` · `_num` · `_band_range` | `server/transfer_plan.py` | `_reg_get`(중첩) · (수량이 유도라 저장 수치 파싱 자체가 없다) · `_band_to`/`_prev_to` |
| `WARN_LAYER_COVERAGE_GAP` / `layer_coverage_gap` | 〃 (경고 타입) | **개명이 아니라 삭제.** 커버리지가 정의상 연속이라 공백이 표현 불가. 구조 결함은 `layer_range_invalid`(+`reason`) |
| `plan_store.doe` · `plan_store.doe_source` | `transfer_plan_config.json` 역할키 | **`plan_store.registry`** + **`plan_store.material_identity`** |
| `map_doe` · `map_doe_source` (테이블) | `product_tables.PRODUCT_TABLES` | **`map_split_registry`** — 선언은 DEPRECATED 표기로 남아 있으나(운영자 수동 이관용) **어떤 코드도 읽고 쓰지 않는다.** 새 소비자 금지, 물리 DROP은 승인 대기 |
| ~~`server/run_api.py`~~ | (문서에만 존재했다) | 그런 파일은 **없다** — `run_decoupled_app.py`의 `main()`이 uvicorn을 직접 띄운다([§6](#6-기타-서버-모듈-한줄-요약)) |

> ⚠️ **이 문서 밖의 같은 패턴**: `MAP_EDITOR_SPEC §6.3`이 위 1행의 삭제된 API를 **load-bearing 안전 계약으로** 기술하고 있다(기원은 `cdcddee`). 그 파일은 **doc-keeper 소관**이라 여기서 고치지 않았다.

---

## 목차

| 파일 | 라인수 | 섹션 |
|---|---|---|
| **묘비 목록 (소스에 없는 이름)** | — | [§0](#0-묘비-목록--소스에-존재하지-않는-이름) |
| `server/main.py` | ~4,184 | [§1](#1-servermainpy--api--ws-허브) |
| **`server/admin_auth.py`** (어드민 토큰 게이트) | ~219 | [§1.6](#16-serveradmin_authpy--어드민내부-토큰-게이트-90e284f-신설) |
| `server/database/crud.py` | ~1,952 | [§2](#2-serverdatabasecrudpy--레이어링-코어) |
| `server/parsers/directory_watcher.py` | ~1,764 | [§3](#3-serverparsersdirectory_watcherpy--파일-인제션) |
| `server/chain_ingestion_worker.py` | ~977 | [§4](#4-serverchain_ingestion_workerpy--체인-워커) |
| 소형 서버 모듈 (models/std_parser/enrichment_*/ingestion_activity/ingestion_checkpoint/bonding_plan/**map_overlay**/**transfer_plan**) + 그래프 트랙(graph_sync_worker/graph_materializer/ontology_config) + **운영 6종**(paths/process_supervisor/health/heartbeat/product_tables/**config_backup**) | ~9,700 | [§5](#5-소형-서버-모듈) |
| 기타 서버 모듈 (한줄 요약) + 설치·개발환경 스크립트 + **교차 구현 계약 `contracts/`** | — | [§6](#6-기타-서버-모듈-한줄-요약) |
| `client2/src/*` | ~21,400 (js 18,656 + css 2,731) | [§7](#7-client2src--웹-클라이언트) |
| 주요 호출 흐름 | — | [§8](#8-주요-호출-흐름-요약) |

> **경로의 단일 원천 (2026-07-27):** `server/config/**`·`server/ingestion_workspace/**`·프로세스 로그는 이제 전부 **`server/paths.py`**([§5](#5-소형-서버-모듈))를 경유한다. 소스에서 `os.path.dirname(__file__)`로 config/워크스페이스 경로를 조립하는 코드를 보면 **누락**이다. 이 맵의 경로 표기는 모두 `paths.*` 기준.

---

## 1. `server/main.py` — API + WS 허브

FastAPI 웹서버. 모든 REST/WS의 단일 진입점. 워커·워처와는 outbox + `/internal/events/*`로 통신.

### 1.1 기동·미들웨어·공용 헬퍼

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `config_path = paths.config_path("table_config.json")` / `logger.info(paths.describe())` | 부팅 첫 줄에 데이터 루트를 찍는다 — 로그만 보고 이 프로세스가 격리 환경인지 라이브인지 판별 가능 | ~41/42 |
| **`from admin_auth import require_admin_token, require_admin_token_strict`** | **[`90e284f` 신설]** `/admin/*`·`/internal/*` 게이트 의존성 import([§1.6](#16-serveradmin_authpy--어드민내부-토큰-게이트-90e284f-신설)) | ~38/39 |
| `db_context_middleware(request, call_next)` | 요청별 DB 세션 수명 관리 미들웨어. **읽는 헤더는 `X-User`/`X-Transaction-ID`/`X-Source`뿐** — 토큰 헤더명(`X-Admin-Token`)이 여기와 겹치지 않는 것이 감사 행 유출 차단의 근거([§1.6](#16-serveradmin_authpy--어드민내부-토큰-게이트-90e284f-신설)) | ~63 |
| `startup_event()` | 기동: 테이블 준비, 워처 스레드, 콜백 배선, 캐시 워밍. **[`90e284f`] `admin_auth.startup_banner()`를 1회만 로깅**(`_admin_auth_banner_logged` ~183 가드 — reload마다 재발화하면 배너가 소음이 된다), 호출부 ~196–198 | ~187 |
| ├ `trigger_ws_refresh(table_name, count, created_logs, total_log_count)` | (내부·임베디드 모드 전용) 인제션 완료 → WS 갱신 브로드캐스트 콜백 (⚠️ C-5 절단 미적용 레거시 경로 — 드릴 관찰, 저순위) | ~275 |
| ├ `trigger_ws_file_processed(table_name, filename, status, error_msg)` | (내부) 파일 처리 상태 → WS 통지 콜백 | ~295 |
| └ `trigger_ingestion_state(state)` | [P1] 비-DECOUPLED 시 HTTP 없이 `ingestion_activity_registry`에 직접 반영, file-processed 시 제거 | ~331 |
| `shutdown_event()` | 종료 정리 | ~368 |
| `class ConnectionManager` — `connect/disconnect/broadcast` | WS 연결 풀 + 전체 브로드캐스트 | ~383 |
| `invalidate_table_cache(table_name)` | 테이블 count 캐시 무효화 | ~450 |
| `inject_system_columns(row)` | 응답 행에 시스템 컬럼 주입 | ~484 |
| `fetch_and_merge_metadata(db, table_name, rows, user_cols, include_sources=True) -> list` | 행들에 CellSource/Overwrite 메타 병합 → 셀 객체 `{value,is_overwrite,priority_source}` 생성 (조회 응답의 핵심) | ~569 |
| `get_deleted_row_business_key(db, table_name, row_id)` / `..._bulk(...) -> dict` | 삭제 행의 비즈니스 키 역추적(감사 표시용) | ~697/720 |
| `check_rows_exist(db, row_keys) -> set` | (table,row_id) 존재 일괄 확인 | ~758 |
| `from ingestion_activity import registry as ingestion_activity_registry` | [P1] 진행 스냅샷 레지스트리 싱글턴 import([§5](#5-소형-서버-모듈)). 바로 위 ~775가 `MAX_NOTIFY_CREATED_LOGS` import | ~777 |
| `get_column_filter_condition(table_model, col_name, f_info)` | 컬럼 필터 → SQLAlchemy 조건 변환(타입별) | ~992 |
| `reload_local_process_cache()` | 웹서버 config 핫리로드 — `models.refresh_dynamic_models(engine)` 위임(싱글턴·ORM·신규 테이블 물리 CREATE, 이슈 #7) + `crud._ontology_cache` 무효화 | ~2913 |
| `load_maps_config() / save_maps_config(data)` | 맵 프리셋 JSON 파일 IO (`MAPS_CONFIG_PATH = paths.config_path("maps.json")` ~2996) | ~2998/3007 |

### 1.1-bis 헬스 블록 (`8117456` 신설 — 파일 상단 ~93–180)

**등록 위치가 계약이다.** FastAPI는 등록 순서로 매칭하므로 이 블록은 파일 맨 아래 SPA catch-all `@app.get("/{file_name:path}")`(~4067)보다 **위에** 있어야 한다. 이 라우트가 없던 시절 `/health`는 catch-all로 떨어져 **HTML을 200으로** 반환했다 — 외부 모니터가 죽은 서버를 살아 있다고 불렀다. `tests/test_health_endpoint.py`가 양쪽(‌`/health`는 JSON · 엉뚱한 경로는 여전히 HTML)을 단언하므로, 재배치로 라우트가 다시 가려지면 조용히 죽지 않고 테스트가 깨진다.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `_HEALTH_DB_TIMEOUT_SEC=2.0` / `_health_probe_inflight` | DB 프로브 시간 상한 / **동시 프로브 1개 제한** — DB가 멎으면 `wait_for`는 요청만 놓아주고 워커 스레드는 못 놓아준다. 10초 폴링 모니터가 행마다 스레드를 쌓지 않도록 하는 플래그(해제는 대기를 포기한 요청이 아니라 **스레드 자신**이 한다) | ~108/113 |
| `_health_probe_db_sync()` / `_health_probe_and_release()` | 동기 DB 프로브(+`health.probe_outbox`) / inflight 해제 래퍼 | ~116/129 |
| GET `/health` → `health_check()` | `heartbeat.read_all()` + `process_supervisor.read_status()` + DB/outbox 프로브를 `health.compute_health`에 넘겨 **JSONResponse + 실제 HTTP 상태**(unhealthy면 503)로 반환. ⚠️ **게이트 없음** — 외부 모니터가 토큰 없이 폴링해야 하므로 의도적으로 열려 있다(`/admin/*`이 아니라 `/health`다) | ~137/138 |

### 1.2 API 라우트 표 — 데이터 조회/편집

| 메서드 경로 | 핸들러 | 역할 | 라인 |
|---|---|---|---|
| GET `/` | `read_root` | index 서빙 | ~412 |
| GET `/api/download/client` | `download_desktop_client` | 데스크톱 셸 배포 | ~425 |
| GET `/tables` | `list_tables` | 테이블 목록 | ~690 |
| GET `/tables/{t}/data` | `get_table_data` | **메인 조회** — 페이지네이션+필터+정렬+메타 병합 | ~1095 |
| GET `/tables/{t}/schema` | `get_table_schema` | 스키마 계약(`table_config.json` 기반) | ~1666 |
| GET `/tables/{t}/{row_id}` | `get_row_data` | 단일 행 조회 | ~1704 |
| GET `/tables/{t}/export` | `export_table_csv` | CSV 스트리밍 export | ~1471 |
| POST `/tables/{t}/rows` | `create_row` | 빈 행 N개 생성(+WS 통지) | ~1792 |
| PUT `/tables/{t}/data/updates` | `apply_batch_updates_endpoint` | **메인 편집** — crud.apply_batch_updates 호출 후 병합·브로드캐스트. 배치의 `replace_map:true`(schemas.py ~87)는 **동일 맵 기존 행 클린 삭제 후 재기록** — 맵 Push와 **[M2.6] legend/DOE 저장(`map_split_registry`)**이 이 연산을 쓴다([§7 map_editor.js](#7-client2src--웹-클라이언트)) | ~1854 |
| DELETE `/tables/{t}/rows/{row_id}` | `delete_row` | 단일 삭제 | ~1305 |
| POST `/tables/{t}/rows/batch_delete` | `delete_rows_batch_endpoint` | 일괄 삭제(+WS) | ~1328 |
| POST `/tables/{t}/row_ids/target` | `get_target_row_ids` | 필터 조건 → row_id 목록(범위 작업용) | ~1383 |
| POST `/tables/{t}/upload` | `upload_file` | 파일 업로드 → 워크스페이스 투입(`paths.workspace_path(table,"raws")` ~2373) | ~2366 |

### 1.3 API 라우트 표 — 이력/레이어링(소스·우선순위)

| 메서드 경로 | 핸들러 | 역할 | 라인 |
|---|---|---|---|
| GET `/audit_logs/recent` | `get_recent_audit_logs` | 최근 트랜잭션 그룹 이력 | ~779 |
| GET `/audit_logs/transaction/{tx_id}` | `get_transaction_logs` | 트랜잭션 상세 로그 | ~824 |
| GET `/dashboard/summary` | `get_dashboard_summary` | 대시보드 통계 (+`_get_recorrection_stat` ~914 — [`ec75d4c` 핵심가치 #1 계측] 재수정률 통계) | ~944 |
| GET `/tables/{t}/rows/{r}/history` | `get_row_history` | 행 이력 | ~1739 |
| GET `/tables/{t}/rows/{r}/cells/{c}/history` | `get_cell_history` | 셀 이력 (⚠️ ~2521에 동일 경로 중복 정의 — 선등록인 ~1765이 유효) | ~1765 |
| GET `/tables/{t}/{r}/{c}/sources` | `get_cell_sources` | 셀의 레이어(소스) 목록 | ~2392 |
| DELETE `/tables/{t}/{r}/{c}/sources/{s}` | `delete_cell_source` | 단일 소스 삭제(+재계산·WS) | ~2436 |
| PUT `/tables/{t}/{r}/{c}/priority` | `set_cell_priority` | 단일 셀 수동 우선순위(Pin) | ~2469 |
| PUT `/tables/{t}/cells/priority/batch` | `set_cell_priority_batch_endpoint` | Pin 일괄 | ~2533 |
| POST `/tables/{t}/cells/sources/delete/batch` | `delete_cell_source_batch_endpoint` | 소스 삭제 일괄 | ~2604 |
| POST `/tables/{t}/cells/sources/query` | `query_cells_sources` | 셀 범위 소스 일괄 조회 | ~2665 |

### 1.4 API 라우트 표 — 어드민/운영/그래프/맵·인리치먼트

> 🔒 **[`90e284f`] `/admin/*` 16개 + `/internal/events/*` 4개 = 20개 라우트가 데코레이터에 `dependencies=[Depends(require_admin_token)]`을 달고 있다.** 그중 **2개만 `..._strict`**(토큰 미설정 시 503). 게이트 자체는 [§1.6](#16-serveradmin_authpy--어드민내부-토큰-게이트-90e284f-신설). **아래 표에서 🔒 = `require_admin_token` · 🔒! = `require_admin_token_strict`.** 새 `/admin` 라우트를 게이트 없이 추가하면 `tests/test_admin_auth.py`가 앱의 라우트 목록을 훑어 실패시킨다(목록을 손으로 관리하지 않는다).

| 메서드 경로 | 핸들러 | 역할 | 라인 |
|---|---|---|---|
| POST `/api/graph/sync` | `manual_graph_sync` | 그래프 **백필/복구** 트리거(:8090 프록시 — 주 경로는 materializer). ⚠️ `/admin` 접두어가 아니라 **게이트 대상이 아니다** | ~1955 |
| 🔒 POST `/admin/outbox/retry-failed` | `retry_failed_outbox_events` | outbox 실패 재시도 | ~2749 |
| 🔒 GET `/admin/outbox/failed` | `get_failed_outbox_events` | outbox 실패 목록(페이징) | ~2788 |
| 🔒 GET `/admin/file-ingestion/logs` · `/failed` | `get_file_ingestion_logs` 등 | 파일 인제션 로그/실패 목록 | ~2858/2893 |
| 🔒 GET `/admin/file-ingestion/active` | `get_active_file_ingestions` | **[P1]** 진행 중 인제션 스냅샷(레지스트리 `snapshot()` — 인메모리, TTL 퇴거 포함) — admin File 탭/헬스 스트립 소비 | ~2899 |
| 🔒 POST `/admin/file-ingestion/retry-failed` | `retry_failed_file_ingestion` | 아카이브 파일 재처리(동기 콜백 배선 포함, 내부 `sync_refresh_callback` ~3535) — 워크스페이스는 `resolve_workspace_root` 역조회(별칭 대응) | ~3502 |
| 🔒 GET `/admin/file-ingestion/workspaces` | `get_ingestion_workspaces` | 워크스페이스 현황 — 표시 table_name에 글로벌 별칭(`find_workspace_alias`) 우선 적용 | ~3281 |
| 🔒 POST `/admin/reload-configs` | `reload_system_configs` | config 핫리로드 — 동기 CREATE(1차 DDL 소유자)가 outbox 발화보다 선행 (+SYSTEM_RELOAD outbox 발화) | ~2947 |
| 🔒 GET `/admin/chain/rules` · `/admin/mappers/list` | `get_chain_rules` / `get_mappers` | 체인 룰·맵퍼 목록 | ~3361/3382 |
| 🔒 GET `/admin/auto-update/status` | `get_auto_update_status` | 스케줄러 상태 — 항목별 `active` 부가(제어 파일 실시간 계산) | ~3611 |
| 🔒 POST `/admin/auto-update/toggle` | `toggle_auto_update_script` | 수집기 active 토글 — `config/auto_update_control.json` 갱신(핫 반영, 404/400 명시) | ~3644 |
| **🔒! POST `/admin/auto-update/run-now`** | `trigger_auto_update_run_now` | 즉시 실행(**active 무관** — 수동 실행은 명시적 의도). **strict인 이유: 스케줄러에게 임의 파이썬 파일을 실행시킨다**(아래 `scripts/code`와 짝) | ~3679 |
| 🔒 GET `/admin/scripts/list` · GET `/admin/scripts/code` | `list_admin_scripts` / `get_admin_script_code` | Monaco 에디터용 스크립트 조회 (경로 검사 `_resolve_admin_script_path` ~3929 — 격리 서버가 라이브 트리에 쓰려 하면 **403**. ⚠️ 이 403은 **게이트가 낸 것이 아니라 핸들러가 낸 것**이라 `WWW-Authenticate`가 없다. 클라가 둘을 구분하는 근거 → [§7 `admin.js` `isGateRejection`](#7-client2src--웹-클라이언트)) | ~3869/3972 |
| **🔒! POST `/admin/scripts/code`** | `save_admin_script_code` | 스크립트 저장. **strict인 이유: `mappers/`·`ingestion_workspace/`에 임의 파이썬 파일을 쓴다** | ~4009 |
| GET/POST/DELETE `/map-presets` (+`/api/` 별칭) | `_save_map_preset_impl` 등 | 맵 프리셋 CRUD | ~3029–3092 |
| GET `/api/bonding-plan/core-summary` | `get_bonding_plan_core_summary` | **[본딩 M1]** 코어(lot,slot) 역할별 집계 — `bonding_plan.get_core_summary` 위임([§5](#5-소형-서버-모듈)), `region` 파라미터(rects — 현 클라 미사용), 잘못된 region 400 | ~3097 |
| GET `/api/maps/overlay` | `get_map_overlay(target_table, target_key, sources, eqp=None, limit=None)` | **[M2 신설 · 맵 인프라]** 임의의 맵들을 타깃 맵 프레임 좌표로 정렬해 `overlays[]` 반환. `sources`는 `table` 또는 `table:key`의 CSV(키 생략 시 target_key 승계, 최대 8종). `map_overlay.get_overlay` 위임([§5](#5-소형-서버-모듈)), `parse_sources` ValueError → 400, 셀 상한 `MAX_OVERLAY_CELLS=20,000`(초과 시 `truncated:true`). ⚠️ **`eqp` 쿼리 파라미터는 no-op으로 존치** — `map_overlay.get_overlay`의 `eqp` 인자는 `by_eqp` 분기와 함께 삭제됐다(축소는 총괄 승인 사항). **맵 에디터 클라는 이 엔드포인트를 호출하지 않는다** | ~3130 |
| GET `/api/maps/paint-rules` | `get_map_paint_rules(table=None)` | **[M2 신설]** 페인트 잠금 선언 정본(**기존엔 클라 하드코딩 `'F'`**) — `map_overlay.get_paint_rules`. 응답 `{table, rules{enabled, blocking_values, from_overlay, message}}` | ~3168 |
| GET `/api/transfer-plan/stages` | `get_transfer_plan_stages` | **[M2 신설]** 선언된 전사 stage 목록 + 역할 연결 상태(config 해석만 — 행 조회 없음). `transfer_plan.list_stages` | ~3182 |
| GET `/api/transfer-plan/source-summary` | `get_transfer_plan_source_summary(stage, lot, slot=None, ref_table=None, map_key=None, bins=None, scope="slot")` | 단계별 소스 가용 집계 — 미선언 stage 404, **칩 좌표 목록은 반환하지 않는다**(집계만). `(ref_table, map_key)` 지정 시 `region_chips` 동봉. **[`269b39e` BIN 축]** `bins=1,2` → `bins` 블록 동봉(맵에 없는 BIN은 `status:"bin_absent"` — **절대 0이 아니다**), `bins=`(빈 값) → 전 BIN 나열, 생략 → 블록 없음(기존 소비자 무영향). **`scope=lot`**(자재 토큰 `MID1:2` = 로트 전체)은 `slot` 동반 시 400, 응답에 `chips` 없음 — `transfer_plan.get_lot_bin_summary` 위임. `scope=slot`은 `get_stage_source_summary` | ~3196 |
| GET `/api/transfer-plan/validate` | `validate_transfer_plan(ref_table, map_key)` | 계획 검증 — **계획 정체성 = 지금 열어 편집 중인 맵**(`plan_id` 폐기). stage는 `stages.*.target_map.table` 역인덱스로 유도, 미선언 맵은 404가 아니라 `stage_unknown` 경고 + `status:"unverified"`. **`plan_store.registry` 미구성만 404**. **[`b35bc9f` zone 모델] validate는 이제 zone 컬럼(`stack`/`mat_*`)을 읽고 `bands`는 레거시 읽기 전용** — [§5 transfer_plan.py](#5-소형-서버-모듈) | ~3253 |
| GET `/enrichment/rules` · `.../references/{index}` | `get_enrichment_rules` / `get_enrichment_reference` | 인리치먼트 규칙 공개본·참조 뷰 조회 | ~3434/3445 |
| WS `/ws` | `websocket_endpoint` | WS 접속(ConnectionManager). ⚠️ **WS 라우트는 게이트 대상이 아니다** — `Depends`가 HTTP 라우트에만 걸리므로 `test_admin_auth.py`도 WS와 mount는 건너뛴다 | ~2354 |
| 🔒 POST `/internal/events/batch-refresh` · `/broadcast` · `/file-processed` | `internal_event_*` | **워커/워처 → 웹서버 브로드캐스트 위임 (경계 계약)** — 수신부는 `total_log_count`(실건수) 우선 + `MAX_NOTIFY_CREATED_LOGS` 방어 절단(인시던트 `cc57b64`). [P1] batch-refresh는 msg 재구성 시 `total_log_count` 동봉(~3760 — 체인 passthrough 경로와 대칭화), broadcast는 `file_ingestion_progress`를 레지스트리에 인터셉트(~3783), file-processed는 레지스트리 제거 인터셉트(~3848). **[`90e284f`] 게이트 추가 — `/internal`이 `/admin`과 같이 묶인 이유는 `broadcast`가 임의 dict를 전 WS 클라이언트에 중계하고 audit_cache에 주입하기 때문**(읽기 전용 admin은 잠그고 이건 열어 두는 것이 거꾸로였다) | ~3734–3854 |
| 🔒 POST `/internal/events/ingestion-state` | `internal_event_ingestion_state` | **[P1]** watcher → 진행 스냅샷 push(QUEUED/PROCESSING/FINISHED — heavy 파일만 명시 통지). **WS 브로드캐스트 없음** — 레지스트리 전용 내부 이벤트 | ~3855 |
| GET `/admin`·`/admin.html` | `serve_admin_page` | **어드민 HTML 자체는 게이트 없이 서빙된다** — 페이지가 떠야 토큰을 물어볼 수 있다. `test_admin_auth.PUBLIC_ADMIN_PATHS`가 **이 둘만** 면제로 허용한다(이름으로 고정) | ~4088 |
| GET `/map-editor`·`/enrichment` | `serve_map_editor_page` / `serve_enrichment_page` | 정적 페이지 서빙 | ~4105/4122 |
| GET `/{file_name:path}` | **`serve_static_or_index`** | SPA catch-all. **[`90e284f`] 격리(containment) 경계** — 아래 §1.4-bis. **catch-all이 파일 최하단인 것이 계약** — `/health`가 이보다 위에 등록돼야 한다(§1.1-bis) | ~4139/4140 |

### 1.4-bis `serve_static_or_index` — SPA catch-all이자 **파일시스템 격리 경계** (`90e284f`)

⛔ **이것은 "정적 파일 핸들러"가 아니다.** 인증 없이 도달 가능한 이 함수가 곧 **프로세스가 읽을 수 있는 모든 파일과 외부 사이의 유일한 경계**다. 격리 검사가 없던 시절 `os.path.join(client2_dist_path, file_name)`이 그대로 서빙돼 `/../../server/config/table_config.json` · `/../../../../../../Windows/win.ini` · `/../../server/admin_auth.py`가 **전부 200을 반환**했다. 그 상태에서는 `GET /admin/scripts/code`·`/admin/chain/rules`·`/admin/file-ingestion/workspaces`에 건 게이트가 **장식**이다 — 지키려던 바이트를 옆문으로 읽을 수 있었고, 읽히는 파일 어딘가에 토큰이 있었다면 그것까지 함께 나갔다.

| 구간 | 라인 | 내용 |
|---|---|---|
| 접두어 목록 (`tables`/`ws`/`audit_logs`/`dashboard`/`admin`/`map-editor`/`map_editor`/`map-presets`/`enrichment/`/`api`) | ~4145–4155 | **API 섀도잉 방지장치이지 보안 경계가 아니다** — 소스 주석이 그렇게 명시한다. 경로 **시작**만 보므로 `../../server/config/table_config.json`은 `admin`과 조금도 닮지 않아 그대로 통과한다 |
| **격리 검사** | **~4171–4175** | `dist_base = os.path.abspath(client2_dist_path)` → `target_path = os.path.abspath(os.path.join(dist_base, file_name))` → **`target_path`가 `dist_base` 자신이거나 `dist_base + os.sep`로 시작하지 않으면 거부.** `_resolve_admin_script_path`와 **같은 모양**이다 |
| 서빙/폴백 | ~4177–4183 | 통과한 실파일만 `FileResponse`, 그 외 `index.html` |

**이 형태를 "단순화"하지 마라 — 세 가지가 전부 의도다:**
- **먼저 resolve하고 나서 검사한다.** 문자 denylist(`..` 금지 등)로는 못 막는다 — `os.path.join`은 두 번째 인자가 절대경로(`/C:/Windows/win.ini`)거나 **윈도우 드라이브 상대경로(`C:foo`)면 base를 통째로 버린다.** 해석된 결과만 검사하는 것이 유일하게 건전한 방법이다.
- **거부는 403이 아니라 404다**(~4102 주석) — 정적 라우트가 "그 탈출 경로는 파싱됐다"고 확인해 주면 안 된다.
- **접두어 목록을 격리 검사로 착각하지 마라.** 위 표의 첫 줄이 그 오해를 막으려고 소스 주석에 박혀 있다.

`tests/test_admin_auth.py::TestStaticFallbackCannotServeArbitraryFiles`가 이 경계를 지킨다.

### 1.5 그래프 조회 구간 (read-only — `graph_nodes/edges` 직접 조회, 워커 미경유)

| 메서드 경로 | 핸들러 | 역할 | 라인 |
|---|---|---|---|
| (상수) | `GRAPH_NEIGHBOR_NODE_CAP=500` / `GRAPH_LABEL_LIST_LIMIT_CAP=200` / `GRAPH_TRACE_NODE_CAP=1000` / `GRAPH_TRACE_DEPTH_CAP=3` 등 | 하드캡(C-7 무제한 로드 금지) | ~2005–2010 |
| (헬퍼) | `_escape_like_term(term)` | LIKE 메타문자 이스케이프 | ~2014 |
| (헬퍼) | `_expand_graph_subgraph(db, seed_nodes, depth, node_cap, edge_types=None, time_from=None, time_to=None)` | 뷰어/추적 **공용 BFS 코어** — 방향별 (from,type)/(to,type) 인덱스 2쿼리, 홉·방향당 엣지 페치 캡 2000, 노드 500청크 IN, 캡 절단 시 dangling 엣지 제외 | ~2019 |
| (헬퍼) | `_serialize_graph_nodes(nodes)` | 노드 `{id,label,identity_key,props}` 직렬화 | ~2112 |
| GET `/graph/stats` | `get_graph_stats` | label/edge_type GROUP BY 카운트 + last_sync | ~2120 |
| GET `/graph/neighbors` | `get_graph_neighbors` | k-hop(1\|2) 서브그래프 — `_expand_graph_subgraph([center])` 위임, truncated | ~2145 |
| GET `/graph/nodes/search` | `search_graph_nodes` | identity 시작일치 ILIKE 자동완성(limit 캡 50) + **빈 q + label = 라벨 전체 리스팅**(identity 오름차순, limit/offset, 캡 200. 전 테이블 덤프 금지 유지) | ~2180 |
| (헬퍼) | `_parse_trace_time(value, field)` | ISO 8601 파싱(`Z` 허용), 실패 시 400 | ~2241 |
| POST `/graph/trace` | `post_graph_trace(req: GraphTraceRequest, db)` | **[G2]** 멀티 시드 BFS 합집합 — 시드 순서보존 dedup→(label,identity) 인덱스 조회→missing_seeds 분리→공용 BFS. depth 1..3, 시간·타입 필터, 의미 검증 400 | ~2253 |
| GET `/graph/mapping-summary` | `get_graph_mapping_summary` | `ontology_config.load_ontology_mappings(known_tables=crud.TABLE_CONFIG)` — materializer와 동일 신호원, 요청 시 디스크 로드 | ~2330 |

---

## 1.6 `server/admin_auth.py` — 어드민/내부 토큰 게이트 (`90e284f` 신설)

219줄. **로그인 시스템이 아니다** — 사용자도 세션도 비밀번호 저장소도 없다. 환경변수에서 읽는 **비밀 하나**를 요청 헤더로 제시한다. 프로덕션이 소수 인원의 인트라넷 공유라는 전제에서 의도적으로 이 크기다.

**이 모듈이 생긴 이유**: 그전까지 `/admin/*` 전 라우트가 **패킷을 보낼 수 있는 누구에게나** 열려 있었고 그중 둘은 임의 코드 실행으로 이어진다 — `POST /admin/scripts/code`가 `mappers/`·`ingestion_workspace/`에 파이썬 파일을 쓰고 `POST /admin/auto-update/run-now`가 그것을 실행시킨다. `GET`도 단순 정보가 아니다(소스 코드를 반환하고 파이프라인 표면을 열거한다).

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `ADMIN_TOKEN_ENV="ASSY_ADMIN_TOKEN"` / `ADMIN_TOKEN_HEADER="X-Admin-Token"` | 운영자가 세팅하는 환경변수명 / 제시 헤더명. **헤더명이 `X-User`/`X-Transaction-ID`/`X-Source`와 다른 것이 계약** — 컨텍스트 미들웨어가 읽는 이름과 겹치지 않아야 토큰이 `AuditLog` 행에 실려 들어가지 못한다 | ~64/68 |
| **`GATE_CHALLENGE_HEADER="WWW-Authenticate"`** / `_GATE_HEADERS` | **게이트 자신이 낸 거부에만 붙는 마커.** 상태코드만으로는 부족하다 — `_resolve_admin_script_path`도 403을 내는데(격리 서버가 라이브 트리에 쓰려 할 때) 그건 토큰과 무관하다. 이 헤더가 없던 시절 어드민 페이지는 그 403을 "토큰이 틀렸다"로 읽고 **멀쩡한 저장 토큰을 덮어썼다** | ~83/84 |
| `_raw_token()` / **`token_is_unusable()`** | env 원문(strip) / **토큰이 설정됐지만 절대 인증될 수 없는 상태**(비-ASCII). HTTP 헤더는 latin-1로 디코딩돼 오므로 비-ASCII 비밀은 왕복에서 살아남지 못한다 — 모든 정답 시도가 "틀렸다"로 답해지는데 기동 배너는 "잠겼다"고 안심시킨다. **토큰이 아예 없는 것보다 나쁜 실패**라 요청 시점에 맡기지 않고 명시적으로 탐지한다 | ~87/91 |
| **`configured_token()`** | 운영자의 비밀 \| **`None`**. import 시점이 아니라 **호출 시점에 읽는다**(테스트가 `main`을 재import하지 않고 env를 monkeypatch할 수 있게). 공백만 있는 값은 미설정 취급 — 빈 문자열을 export한 운영자는 아무것도 설정하지 않은 것이고, 그걸 진짜 토큰으로 치면 **아무 요청이나 맞힐 수 있는 비밀**이 된다. 비-ASCII도 `None`으로 떨어져 **미설정 상태**(코드 실행만 거부, 나머지는 개방)에 착지한다 — 아무도 제시할 수 없는 비밀로 강제하면 **어드민 16개 라우트가 전부 벽돌**이 되고 복구는 변수를 지우고 재시작하는 길뿐이다 | ~104 |
| `_matches(presented, expected)` | **상수 시간 비교**(`secrets.compare_digest`). **절대 raise하지 않고 어느 쪽 피연산자도 노출하지 않는다** — 깨진 헤더 값이 `TypeError` 트레이스백에 값을 실어 나가지 않도록 통째로 감쌌다 | ~126 |
| `_enforce(request, fail_closed)` | 판정 본체 — 미설정 시 `fail_closed`면 **503**, 아니면 통과. 설정 시 헤더 없으면 **401**, 불일치면 **403**(둘 다 `_GATE_HEADERS` 동봉). **거부 detail은 전부 상수 문자열**이라 제시된 값을 되비추지 않는다 | ~138 |
| **`require_admin_token(request)`** | 일반 게이트 — **`/admin/*` 14곳 + `/internal/events/*` 4곳 = 18 라우트**. 토큰 설정 시 강제, 미설정 시 개방 — 이 빌드로 처음 재시작한 운영자가 릴리스 노트를 읽기도 전에 어드민 페이지 전체에서 잠기지 않게 한다 | ~153 |
| **`require_admin_token_strict(request)`** | 코드 실행에 닿는 **2 라우트 전용**(`POST /admin/scripts/code` · `POST /admin/auto-update/run-now`). 토큰 미설정이면 **503으로 거부**한다 — 비밀 설정을 잊은 것이 구멍을 열어 두는 결과가 되면 안 된다. **이 둘은 절대 개방되지 않는다** | ~162 |
| **`ADMIN_GATES = (require_admin_token, require_admin_token_strict)`** | 이 모듈이 제공하는 의존성 전량. `tests/test_admin_auth.py`가 **FastAPI 앱의 라우트를 직접 훑어** 각 `/admin`·`/internal` 라우트가 이 둘 중 하나로 해석되는지 단언한다 — 나중에 추가된 무방비 라우트는 배포되지 않고 스위트에서 깨진다(**손으로 관리하는 목록이 아니다**) | ~174 |
| **`internal_event_headers()`** | 워커가 `/internal/events/*`를 호출할 때 붙일 헤더 dict. 워커는 `run_decoupled_app.py`의 자식이고 `process_supervisor`가 각 자식 env를 `os.environ.copy()`(~357)로 만들므로 **런처에 한 번 세팅하면 충분**하다. 토큰 미설정 시 빈 dict(게이트가 열려 있는 상태와 대칭) | ~177 |
| `startup_banner() -> (level, message)` | 기동 로그 한 줄. **3상태**: 비-ASCII → `error`(가장 시끄럽다 — 운영자가 잠겼다고 **믿고** 있다) / 설정됨 → `info` / 미설정 → `warning`(**무엇이 멈추는지 이름으로 말한다**). `main.py`가 `_admin_auth_banner_logged`(~183)로 1회만 찍는다 | ~190 |

> **두 상태의 분할이 설계의 핵심**: `ASSY_ADMIN_TOKEN` **설정** → `/admin/*`·`/internal/*` 전량이 헤더 필수(읽기 포함). **미설정** → 코드 실행 2종만 503으로 거부(fail closed)하고 나머지 admin 라우트는 계속 서빙. 새 빌드로 재시작한 운영자가 전면 잠금을 당하지 않으면서, **다칠 수 있는 정확히 그 둘만 잃는다.**
>
> **왜 config 파일이 아니라 환경변수인가**: `server/config/`는 gitignored라 커밋 안전성은 같지만, ① 저장소에 이미 운영자 비밀·위치의 관례가 있고(`DATABASE_URL`·`ASSY_DATA_ROOT`·`ASSY_API_PORT`) ② 환경변수만이 **저장소 안 디스크에 전혀 남지 않는** 유일한 선택지이며 ③ `server/config/**`를 격리 데이터 루트로 복제하는 스냅샷 도구(`devenv.py bootstrap`)에 **딸려 가지 않는다**(비밀이 두 번째 트리에 복제되지 않는다).
>
> **누출 규율 (전부 의도)**: 쿼리 파라미터가 아니라 헤더다(uvicorn 액세스 로그에 안 남는다) · 거부 detail은 상수 문자열이다 · 헤더 선언을 `Header(...)`가 아니라 `Request`로 하는 것도 이 규율이다(FastAPI 검증 에러가 **문제의 값을 422 본문에 렌더링**해 버린다).
>
> 🧪 `tests/test_admin_auth.py` — `PUBLIC_ADMIN_PATHS={"/admin","/admin.html"}`(허용된 면제는 이 둘뿐, 이름으로 고정) · `GATED_PREFIXES=("/admin","/internal")` · `STRICT_ADMIN_ROUTES={("POST","/admin/scripts/code"),("POST","/admin/auto-update/run-now")}`. 클래스 축: 라우트 전수 커버리지 · 토큰 강제 · 미설정 시 fail-closed 범위 · **토큰 무유출** · **정적 폴백 격리**(§1.4-bis) · 비-ASCII 처리 · 거부의 기계 판독성 · `/internal` 게이팅 · conftest가 앰비언트 셸 변수를 격리하는지.

---

## 2. `server/database/crud.py` — 레이어링 코어

셀 단위 소스 레이어링(CellSource/CellOverwrite/priority) + 배치 업서트의 단일 구현. **시그니처 변경 시 전수 Grep 연쇄 갱신 필수**([규율](../guide/data_preservation_and_signature_change.md)).

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `transaction_context(user, tx_id, source)` | 컨텍스트매니저 — 감사·outbox용 트랜잭션 식별 주입 | ~8 |
| `_warn_audit_truncation_once(table_name, col_name)` | [P2] 감사 값 절단 경고 dedup(테이블·컬럼당 1회). 호출부 ~294 | ~43 |
| **`_warn_undeclared_column_once(table_name, col_name)`** | **[`08d2b12` 신설] 미선언 컬럼 드롭의 침묵을 없앤다.** `column_types`에 없는 컬럼은 종전대로 **조용히 버려졌다** — 쓰기는 성공을 반환하므로 호출자는 데이터가 사라진 줄 몰랐다. **드롭 동작 자체는 의도적으로 그대로**(거부하면 뒤처진 config가 장애가 된다) — 고친 것은 침묵뿐. 경고는 (테이블,컬럼)당 **프로세스 1회**. 레지스트리 키가 페이로드에서 오므로(깨진 헤더 행·값을 헤더로 뱉는 파서) 테이블당 `_MAX_UNDECLARED_WARNED_PER_TABLE=64`(~73) 상한이 있고, **포화 시 다시 침묵한다는 사실 자체를 1회 경고**한다. 호출부는 `apply_row_update_internal` 내부 ~608 | ~76 |
| `class LightCellSource` / `LightCellOverwrite` | ORM 미경유 경량 메타 객체(성능) | ~97/108 |
| `sanitize_to_utf8(data)` | cp949 등 오염 문자열 정화 | ~141 |
| `load_table_config()` / `update_table_config(new_config)` | table_config.json IO | ~163/172 |
| `cast_value_by_type(value, col_type, col_name)` / `clean_str_value(val)` | 컬럼 타입 캐스팅 | ~188/205 |
| `get_row_by_business_key(db, table_name, key_value)` | 비즈니스 키로 행 조회 | ~215 |
| `resolve_priority_map(table_name=None) -> dict` / `get_source_priority(source_name, table_name=None) -> int` | **소스 서열 단일 원천**(테이블별 오버라이드 포함) — compute_priority_value·graph materializer 공용. `SOURCE_PRIORITY`에 `chain_ingestion: 4` 등재 | ~229/244 |
| `compute_priority_value(sources, manual_priority_source, table_name)` | **표시값 결정** — user:0 < collision_merge:1 < pipeline_parser:2 < custom_script:3 < chain_ingestion:4 + 수동 Pin | ~249 |
| `create_audit_log(db, ..., transaction_id, business_key, add_to_cache)` | 감사 로그 1건 생성. [P2] `old_val`/`new_val`은 `event_constants.truncate_audit_value`로 **4096자 상한** — 절단본이 DB 저장본과 통지 dict **양쪽에** 동일 적용되고, 절단 사실은 값 내부 마커(`…[truncated: 총 N자]`)로 명시 | ~271 |
| `bulk_insert_audit_logs(db, logs)` | 감사 로그 벌크 삽입 | ~330 |
| `bulk_upsert_cell_sources(db, mappings)` / `bulk_upsert_cell_overwrites(db, mappings)` | 메타 테이블 벌크 업서트(ON CONFLICT) | ~350/382 |
| `bulk_delete_cell_overwrites(db, delete_keys)` | overwrite 벌크 삭제 | ~415 |
| `_get_or_create_row(db, table_model, update_item, row_cache, table_name) -> (row, is_new)` | row_id/비즈니스키로 행 확보(캐시 활용) | ~431 |
| `_update_row_business_key(row, key_col, update_item, row_cache)` | 비즈니스 키 갱신 | ~467 |
| `_load_metadata_row_cell(...) -> (sources_list, overwrite)` | 셀 메타 로드(캐시·업서트 큐 연동) | ~487 |
| `apply_row_update_internal(db, table_name, update_item, row_cache, sources_cache, overwrites_cache, transaction_id, logs_to_cache, cell_sources_to_upsert, cell_overwrites_to_upsert, cell_overwrites_to_delete, deleted_row_ids) -> (row, is_new, changed_cols)` | **[통합 코어]** 단일 행 업데이트 + 레이어링 재계산. 모든 쓰기 경로가 여기로 수렴. 미선언 컬럼 드롭 지점 ~605–609 | ~551 |
| `apply_batch_updates(db, table_name, batch: GeneralUpdateBatch)` | **배치 진입점** — tx 컨텍스트, 캐시 프리로드, 행별 코어 호출, 벌크 flush, outbox 발화. 반환 `(results, changed_cells, created_logs, deleted_row_ids)`. [P2] 워처가 이 함수의 commit에 오프셋 갱신을 동승시킨다. **`batch.replace_map`(~1050)** — 지정 시 `updates[0]`이 정하는 스코프의 기존 행을 클린 삭제 후 재기록(**차집합 계산 없는 집합 교체** 연산. 소비자: 맵 Push·DOE 저장) | ~1034 |
| `create_empty_row(s)_batch(db, table_name, count, user_name)` | 빈 행 생성 | ~1227/1232 |
| `delete_row(db,...)` / `delete_rows_batch(db, table_name, row_ids, user_name)` | 행 삭제(+감사·메타 정리) | ~1276/1280 |
| `delete_cell_source_batch(db, table_name, cells, source_name)` | 소스 레이어 일괄 삭제 + 표시값 재계산 | ~1344 |
| `delete_cell_source(db, ...)` | 단일 소스 삭제(배치 위임) | ~1500 |
| `set_cell_manual_priority_batch(db, table_name, updates, source_name, updated_by)` | 수동 Pin 일괄(§크고 복잡 — 표시값 재계산·감사 포함) | ~1505 |
| `set_cell_manual_priority(db, ...)` | 단일 Pin(배치 위임) | ~1864 |
| `get_ontology_mapping()` / `check_needs_rollback(table_name, modified_cols)` | 그래프 보조 — v2 검증+enrichment 승격 적용 결과 캐시 / v2 매핑 인식 rollback 신호(v1 폴백) | ~1873/1915 |

---

## 3. `server/parsers/directory_watcher.py` — 파일 인제션

워크스페이스별 폴더 감시 → 파서 실행 → **HTTP 아닌 직접 DB**(`crud.apply_batch_updates`) 업서트 → 웹서버에 `/internal/events/*` 콜백. 2026-07-25 std parser(무스크립트 표준 파싱)·기동/주기 스윕 통합, **워크스페이스 config.json 폐지**(`5fac5f0`).

> **경로 (2026-07-27):** config·워크스페이스 루트는 전부 `paths.config_path(...)` / `paths.WORKSPACE_DIR` 경유다.
>
> ⚠️ **앵커 재측정 (2026-07-27, HEAD `90e284f`)** — 앞판은 `be58210` 실측이었고 그 뒤 **이 절이 밀린 채 방치됐다**(파일 1,714 → **1,764줄**, 앵커 최대 **+53**). 이 파일은 `0f8d35f..90e284f` 범위에서 **한 줄도 바뀌지 않았다** — 즉 커밋 diff를 따라가는 갱신 방식으로는 영원히 안 잡히는 종류의 드리프트다.
>
> 🫀 **[신설] 진척 비트가 "루프"가 아니라 "작업 단위"에 걸린다** — `process_with_retry`(~739)와 `process_archived_file_sync`(~1005)는 이제 **얇은 래퍼**이고, 각각 `heartbeat.work_claim(HEARTBEAT_NAME, …)`(~750/~1017)로 감싼 뒤 실제 본체 `_process_with_retry`(~754)·`_process_archived_file_sync`(~1022)에 위임한다. 파일 1건의 인제션 전체가 하나의 claim이고, 그 안에서 찍히는 비트가 claim의 진척을 갱신한다([§5 `heartbeat.py`](#5-소형-서버-모듈)의 `DEFAULT_STALL_AFTER_SEC`). **`_` 접두 본체를 직접 부르면 claim 없이 돌아 `/health`가 그 인제션을 보지 못한다.**

- **[P1] heavy 레인**(`4fd8ac9`+`8b0fd03`) — 크기 임계(기본 10MB, `config/ingestion_settings.json` 파일 경계 핫리로드) 초과 파일을 전용 큐/워커로 이관해 observer 디스패치 스레드 HOL 제거. 워크스페이스 내 FIFO는 backlog 카운터+직렬화 락+논블로킹 재라우팅 3중 장치로 보존.
- **[P2] 체크포인트 재개 + 해시 dedup**(`f78ab0a`) — 파일 전체 sha256 시그니처(`sha256:<size>:<digest>`)를 계산해 ① 동일 시그니처 `DONE`이면 skip ② 미완이면 오프셋 재개. 저장소는 신규 테이블 `file_ingestion_checkpoints`([`ingestion_checkpoint.py` §5](#5-소형-서버-모듈)). **오프셋 갱신은 청크 upsert와 같은 트랜잭션** — "커밋된 행 수 == 기록된 오프셋"이 원자적으로 성립. 재개는 시그니처+`total_rows`+`source_kind`+오프셋 범위가 **전부** 일치할 때만. heavy/normal·스윕·관리자 재시도 4경로 동일 동작.
- 통지 로그 상한 `MAX_NOTIFY_CREATED_LOGS`는 `event_constants.py` 공용 상수 import.
- 테스트: `tests/test_workspace_config_deprecation.py`(21개) · `tests/test_heavy_lane.py`(27개, `hvy_test_*`) · `tests/test_ingestion_checkpoint.py`.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `load_global_table_config() -> dict` | table_config.json 로드 (`paths.config_path` ~79) | ~74 |
| `warn_legacy_workspace_config(config_path)` | 레거시 config.json 발견 시 경로당 1회 deprecation WARNING | ~92 |
| `_log_alias_conflict_once` / `warn_invalid_std_parse_once` | 별칭 충돌·std_parse 비-bool 경고 dedup(키별 1회 — QA D5/D6) | ~116/124 |
| `DEFAULT_HEAVY_FILE_MB=10` / `INGESTION_SETTINGS_PATH` | [P1] heavy 임계 기본값·설정 파일 경로 — `paths.config_path("ingestion_settings.json")`(`.sample` tracked) | ~142/144 |
| `load_ingestion_settings()` / `warn_invalid_heavy_threshold_once` / `get_heavy_threshold_bytes()` | [P1] 임계 로더 — **파일 이벤트(라우팅 결정)당 1회 디스크 읽기**(파일 경계 핫리로드), 양수만 유효·그 외 기본 10MB+1회 경고 | ~147/161/173 |
| `DEFAULT_DEDUP_BY_SIGNATURE=True` / `DEFAULT_RESUME_FROM_CHECKPOINT=True` / `_bool_setting(key, default)` | [P2] dedup·재개 기본값과 설정 판독기(같은 `ingestion_settings.json`) | ~187/188/191 |
| `dedup_by_signature_enabled()` / `resume_from_checkpoint_enabled()` | [P2] 게이트 — `dedup_by_signature: false`가 **전역 강제 재처리 스위치**(파일명 `__force__`와 관리자 재시도가 나머지 2경로) | ~206/214 |
| `get_workspace_serial_lock(workspace_path) -> Lock` | [P1] **워크스페이스 직렬화 락 — 모듈 레벨 경로 키 레지스트리**(핸들러 복수여도 공유). heavy 워커/인라인/run_watcher 재처리 폴러가 공용 | ~228 |
| `class HeavyIngestionLane` — `submit/_ensure_running/_worker_loop/stop` | [P1] FIFO `queue.Queue` + 데몬 워커 스레드 `watcher-heavy-lane` **1개**(첫 제출 시 지연 기동). WorkspaceWatcher가 1개 생성해 전 핸들러 주입. heavy끼리는 직렬(escalation §6-3) | ~238–290 |
| `find_workspace_alias(folder_name, table_config) -> str\|None` | 폴더명↔`workspace_name` 명시 별칭 매칭 — 섀도잉·중복 선언 별칭은 무효+ERROR 1회(QA D3) | ~292 |
| `resolve_workspace_root(base_dir, table_name, table_config) -> str` | 테이블→워크스페이스 루트 **역조회 공용 함수**(별칭 포함) — 결과 기반 경로 검사(base 직속 자식만, 드라이브 상대경로 탈출 차단, QA D2). main.py `retry-failed`·run_watcher 폴러가 사용 | ~333 |
| `resolve_workspace_table(folder_name, table_config) -> str\|None` | 폴더→테이블 해석: 별칭 > 폴더명 규약 | ~366 |
| `_register_legacy_import_shim()` | 구식 사용자 파이프라인 스크립트의 import 호환 shim | ~380 |
| `class IngestionHandler(FileSystemEventHandler)` | **워크스페이스 1개 담당 핸들러** — 생성자(~458) 말단 kwargs `on_ingestion_state_callback`/`heavy_lane`(기본 None=종전 인라인 경로, 하위호환) | ~454 |
| ├ `_load_legacy_config()` | [deprecated] 레거시 워크스페이스 config.json 파싱(이것만 캐시) | ~485 |
| ├ `_resolve_table_name(global_cfg)` | 테이블명 해석: 글로벌 `workspace_name` 별칭 > 레거시 `table_name` > 폴더명 규약 | ~507 |
| ├ `_snapshot_table_context() -> (t_name, table_info)` | **파일당 1회 config 스냅샷**(QA D1) | ~522 |
| ├ `_std_parse_enabled_for(t_name, table_info) -> bool` | std_parse 게이트: 글로벌(JSON bool만 유효) > 레거시 폴백 > 기본 true | ~533 |
| ├ `table_name` / `std_parse_enabled` / `errors_path` (property) | 즉석 해석 래퍼 — **글로벌 조회 비캐시**(핫리로드 반영) | ~553–565 |
| ├ `on_created/on_moved → _handle_event(file_path)` | 파일 이벤트 수신(processing_files check-then-add 락 원자화) → [P1] `_route_and_process` 위임으로 재구성 | ~568–578 |
| ├ `_classify_lane(abs_path)` / `_heavy_backlog_nonzero()` | [P1] 이벤트 시점 `os.stat` 1회 크기 분류 / 워크스페이스 heavy backlog 잔여 확인 | ~608/622 |
| ├ `_route_and_process(abs_path, uploader) -> bool` | [P1] **레인 라우팅 본체** — heavy(크기)·backlog(>0이면 크기 무관 큐 후미=FIFO 보존)·인라인은 직렬화 락 **논블로킹 try-acquire**(실패 시 큐 후미 재라우팅 — HOL 방지+순서 보존 동시 만족) | ~626 |
| ├ `_submit_to_heavy_lane(abs_path, uploader, lane, size_bytes)` | [P1] 큐 제출 — QUEUED 통지를 **submit 이전 선발신**(드릴 결함1: 즉시 픽업 역전 경합 제거), submit 실패 시 FINISHED 정리 통지 후 인라인 폴백. `lane`은 분류 실값(재라우팅 소형은 "normal" — QA F4) | ~660 |
| ├ `_run_lane_job(...)` / `_notify_ingestion_state(state)` | [P1] heavy 워커 잡 본체(직렬화 락 획득→`process_with_retry`→finally 정리) / 상태 push 콜백 래퍼 | ~698/728 |
| ├ **`process_with_retry(file_path, uploader, retries=3, delay=1.0)`** | **[신설 구조] `heartbeat.work_claim`(~750) 래퍼일 뿐** — 실제 처리는 `_process_with_retry`(~754) | ~739 |
| ├ `_process_with_retry(...)` | 처리 본체 — 스냅샷→파싱→[P2] 시그니처 계산(~772)→dedup skip→`_plan_checkpoint`(~794)→`_send_to_upsert`→`_finalize_checkpoint`→아카이브/에러 이동, 재시도 | ~754 |
| ├ `_compose_detail(skipped_no_key, plan)` (staticmethod) | [P2] 완료 통지 `detail` 조립 — 키 결측 스킵 수 + 재개/재시작 사유 | ~849 |
| ├ `_try_dedup_skip(file_path, basename, t_name, signature) -> bool` | [P2] 동일 시그니처 `DONE`이면 skip — **무음 skip 금지**: WARNING + archive + `FileIngestionLog(status="SKIPPED")` + 콜백 status는 `"SUCCESS"`(수신부가 비-SUCCESS를 실패로 렌더링하므로 오표기 방지) + 사유 detail | ~858 |
| ├ `_plan_checkpoint(...)` / `_finalize_checkpoint(plan, processed_rows)` | [P2] `ingestion_checkpoint.plan_ingestion` 게이트 래퍼(실패 시 `CheckpointPlan.disabled(note=...)`) / `mark_done` — 실패 시 "dedup will not apply" 경고 | ~912/938 |
| ├ `_log_ingestion_record(...)` / `_log_ingestion_failure/success(..., t_name=None)` | FileIngestionLog 기록(직접 DB, 스냅샷 테이블명). `error_message`는 SUCCESS/SKIPPED에서 **detail 슬롯**으로 겸용 | ~951/976/981 |
| ├ `_retry_should_restart(t_name, signature) -> bool` | [P2] 재시도 시 완료 체크포인트가 있으면 처음부터 재시작 판정 | ~989 |
| ├ **`process_archived_file_sync(log_entry, db, uploader)`** | 어드민 재처리 경로. **이것도 `work_claim`(~1017) 래퍼**이고 본체는 `_process_archived_file_sync`(~1022) — 스냅샷 진입점, 내부에서 락 안 잡음. [P2] 체크포인트는 태우되 **dedup skip은 미적용**(재시도는 명시적 의도) | ~1005 |
| ├ `_move_to_err_folder` / `_archive_file` | 파일 이동 | ~1065/1093 |
| ├ `_discover_and_execute_pipeline(file_path, meta=None) -> list[dict]\|None` | 사용자 파이프라인 스크립트(pipeline_*.py) 탐색·실행 | ~1120 |
| ├ `_resolve_rows(file_path, t_name=None, table_info=None, ...)` | **파서 라우팅** — 파이프라인 우선, 없으면 std parser 폴백(스냅샷 인자 전파). `source_kind`(`"std"` / `"pipeline:<Class>"`)의 산출처 | ~1214 |
| ├ `_try_std_parse(file_path, t_name, table_info)` / `_extract_user_from_filename(filename)` | std_parser 호출 래퍼(게이트·에러 처리) / 파일명에서 업로더 유도 | ~1252/1282 |
| └ `_send_to_upsert(rows, uploader, filename, total_rows, t_name=None, table_info=None, checkpoint=None)` | list 또는 스트리밍 이터레이터 → 청킹 → `crud.apply_batch_updates` 직접 호출 + 진행률 콜백. [P2] `checkpoint`로 `resume_from` 스킵(~1349)·오프셋 초과 경고(~1356)·**청크마다 `record_chunk_progress`(~1415, 같은 트랜잭션)**, created_logs는 `MAX_NOTIFY_CREATED_LOGS` 잔여분만 누적(~1427) | ~1293 |
| `class WorkspaceWatcher` | 전체 워크스페이스 관리자 — [P1] `HeavyIngestionLane` 1개 생성(~1468)·전 핸들러 주입 + `on_ingestion_state_callback` 배선 | ~1460 |
| ├ `_provision_workspaces()` | 폴더 스캐폴딩 — **config.json 신설 중단**(폴더만 보충), `workspace_name` 별칭 폴더명 지원(unsafe 별칭 무시) | ~1488 |
| ├ `_register_workspace(raws_root, table_config)` | 핸들러 등록(+`handlers_by_raw_path` 레지스트리, `heavy_lane` 주입) — 레거시 config 발견 시 1회 경고(QA D4) | ~1517 |
| ├ `discover_and_watch()` / `sync_new_workspaces()` | 기동 스캔·신규 워크스페이스 동기화(신규 raws는 등록 직후 스윕) | ~1576/1592 |
| ├ `sweep_existing_files(raw_paths)` / `_sweep_safely` / `sweep_existing_files_async(...)` | **[Startup Sweep]** raws/ 직속 기존 파일을 mtime 오름차순으로 `_handle_event` 경로 재사용 처리 — [P1] 스윕도 자동으로 heavy 라우팅을 탐. (mtime,size) 시그니처로 무한 재시도 차단, err/·하위 dir 제외 | ~1622/1683/1689 |
| ├ `_periodic_sweep_loop()` / `_ensure_periodic_sweep_running()` | 이벤트 유실 안전망 — 300s 주기 잔류 재스캔 데몬 | ~1698/1702 |
| └ `_ensure_observer_running()` / `stop()` / `start(blocking)` | watchdog Observer 수명 관리 — start()가 observer 기동 후 기동 스윕+주기 스윕 킥, stop()이 heavy 레인도 정지 | ~1711/1727/1733 |

---

## 4. `server/chain_ingestion_worker.py` — 체인 워커

outbox LISTEN/NOTIFY 소비 → 체인 룰 매칭 → 맵퍼 실행 → 파생 테이블 업서트 → `/internal/events/broadcast`로 WS 위임. 지연 SLO 100ms(2026-07-25 F1–F3 + warmup 완료).

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `class OutboxListener` — `_ensure_connection/_reset_connection/_wait_blocking/wait(timeout)/close` | psycopg2 LISTEN 전용 커넥션 + async 대기 | ~27–107 |
| `_get_http_session()` / **`post_event_async(endpoint, payload) -> bool`** | 웹서버 `/internal/events/*` POST(커넥션 재사용). **[`90e284f`] `headers=admin_auth.internal_event_headers()`(~151, 지연 import ~148)** — `/internal/events/*`가 게이트 뒤로 들어갔으므로 이게 없으면 워커의 브로드캐스트가 401로 조용히 죽는다([§1.6](#16-serveradmin_authpy--어드민내부-토큰-게이트-90e284f-신설)) | ~118/134 |
| `purge_expired_outbox_sync(db_session_factory, retention_days, ...)` | 처리 완료 outbox 보존기간 청소 | ~173 |
| `_stamp_broadcast_at_sync(db_session_factory, event_ids)` | 브로드캐스트 완료 스탬프(F1 전달 확정) | ~213 |
| `_dispatch_broadcasts(pending_broadcasts, db_session_factory)` | 커밋 후 인라인 브로드캐스트 발사 + 스탬프 | ~234 |
| `load_chain_rules()` | chain_rules 설정 로드(+enrichment 룰 병합) | ~278 |
| `_mapper_accepts_rule(mapper_func) -> bool` | 맵퍼가 rule 인자를 받는지 시그니처 검사 | ~307 |
| `execute_custom_mapper(module_name, function_name, db, payload, rule=None)` | mappers/ 동적 로드·실행 | ~318 |
| `_group_target_tables(events_in_tx, rules)` | tx 내 이벤트 → 타깃 테이블 그룹핑 | ~336 |
| `process_chain_transaction_group(tx_id, events, db, rules) -> (ok, err, broadcast_messages)` | **핵심** — 순환 차단(source=chain_ingestion 제외), 맵퍼 실행, 업서트, 브로드캐스트 큐 반환. broadcast 구성부(~474)는 created_logs를 **직렬화 전** `MAX_NOTIFY_CREATED_LOGS`(500)로 절단 + `total_log_count`(실건수) 동봉 — 양 분기(`batch_refresh_required`/`batch_row_upsert`) 공통(인시던트 `cc57b64`, C-5 계약 확장) | ~359 |
| `reload_worker_process_cache()` | SYSTEM_RELOAD 수신 시 config 캐시 리로드 | ~526 |
| `warmup_worker(rules, db_session_factory)` | 콜드스타트 제거 — 맵퍼·커넥션 프리로드 | ~542 |
| `process_pending_groups(db, group_order, groups, rules, db_session_factory, batch_wake_ts)` | 배치 내 그룹 순차 처리 — 실패 그룹 skip(HOL 블로킹 제거, F5) | ~590 |
| `sweep_undelivered_broadcasts(db, rules, db_session_factory)` | 통지 미확정 행 안전망 스윕(F1) | ~707 |
| `start_chain_ingestion_worker(db_session_factory)` | **메인 루프** — LISTEN 대기, 리로드 체크(1s 간격), 스윕, purge 스케줄. SYSTEM_RELOAD 블록에서 `models.refresh_dynamic_models(engine)`(지연 import) 호출 — 신규 테이블 CREATE 보충 안전망(이슈 #7). **[`8117456`] 루프 안에서 `heartbeat.beat("chain")`(~827)** — `/health`가 "살아 있음"이 아니라 **"진척이 있음"**으로 판정하는 근거(`server/utils/heartbeat.py`, [§5](#5-소형-서버-모듈)) | ~785 |

---

## 5. 소형 서버 모듈

### `server/paths.py` (70줄) — 데이터 루트 단일 오버라이드 지점
**`4ba13ae` 신설.** `DATABASE_URL`이 DB를 갈아끼울 수 있게 하듯, 디스크 위의 사용자 소유 트리를 갈아끼운다. **약 21개 모듈이 각자 `os.path.dirname(__file__)`로 조립하던 경로를 전부 여기로 모았다** — 데이터가 어디 있는지 결정하는 곳이 정확히 하나다.

| 심볼 | 역할 | 라인 |
|---|---|---|
| `SERVER_DIR` | 이 파일의 위치 = server 패키지 디렉터리 | ~33 |
| **`DATA_ROOT`** | `os.environ["ASSY_DATA_ROOT"]` **또는** `SERVER_DIR`. **미설정이 프로덕션이고 그때 레이아웃은 바이트 단위로 종전과 같다** | ~36 |
| `CONFIG_DIR` / `WORKSPACE_DIR` | `<DATA_ROOT>/config` / `<DATA_ROOT>/ingestion_workspace` | ~38/39 |
| `IS_ISOLATED` | `normcase(DATA_ROOT) != normcase(SERVER_DIR)` — 격리 환경 판별 | ~42 |
| `config_path(*parts)` / `workspace_path(*parts)` | 하위 경로 조립 | ~45/50 |
| `log_path(filename)` | 프로세스 로그는 **데이터 루트 직속**(종전 `server/server.log` 자리 그대로). 격리 프로세스가 사용자의 라이브 로그에 append하지 않게 하는 것이 요점 — 인시던트를 재구성하려고 읽는 파일에 드릴의 줄이 섞이면 안 된다 | ~55 |
| `describe()` | `data_root=… isolated=… db=…` 한 줄 — 각 프로세스가 부팅 로그에 찍는다 | ~68 |

> **의도적 제외**: `server/mappers/**`는 데이터가 아니라 **코드**이고 `sys.path`의 `mappers` 패키지로 해석되므로 이 모듈이 다루지 않는다.
> import 규약은 `event_constants.py`와 동일 — 모든 엔트리포인트에서 `server/`가 `sys.path`에 있으므로 `import paths`로 해석된다(그렇지 않을 수 있는 호출자는 `crud.py`와 같은 try/except 폴백).

### `server/process_supervisor.py` (**709줄** — 종전 지도의 431줄은 낡은 값) — 자식 프로세스 감독
**`8117456` 신설.** 구 `run_decoupled_app.py`는 5프로세스를 띄우고 `while True: time.sleep(1)`을 돌았다 — 워처나 체인 워커가 죽어도 **아무도 탐지하지 않고 아무도 재시작하지 않았다.** 웹서버는 살아 있으니 UI는 멀쩡해 보이고 데이터만 조용히 멎었다. 테스트: `tests/test_process_supervisor.py`.

> ⚠️ **2026-07-27 재측정에서 이 절이 가장 크게 밀려 있었다** — 선언 431줄 대비 실제 **709줄**이고 앵커는 최대 **+330**. 그 사이에 들어온 것이 아래 **공유원인(correlated) 실패** 축인데 지도에 **한 줄도 없었다.**

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `BACKOFF_BASE_SEC=2.0` / `BACKOFF_MAX_SEC=60.0` / `MAX_CONSECUTIVE_FAILURES=5` | **재시도 예산** — 연속 n번째 실패는 `min(base·2^(n-1), max)` 대기, 예산 초과 시 `FAILED`로 **영구 정지**(배너 로그 + `/health` 비-200). 즉사하는 자식을 무한 재시작하면 CPU를 태우고 로그를 덮고 **무엇보다 감독이 동작하는 것처럼 보인다** | ~97–99 |
| `HEALTHY_UPTIME_SEC=60.0` / `POLL_INTERVAL_SEC=1.0` / `STATUS_REFRESH_SEC=5.0` / `MAX_EVENTS=100` | 이만큼 살아 있었다면 크래시 루프가 아니므로 **연속 카운터를 리셋**한다 — 이게 없으면 한 달에 한 번 재시작하는 시스템이 결국 아무것도 재시작하지 않게 된다 / 폴 주기·상태파일 갱신 주기·이벤트 링버퍼 상한 | ~101/102/104/106 |
| **`CORRELATION_WINDOW_SEC=120.0` / `CORRELATED_MIN_CHILDREN=2` / `CORRELATED_BACKOFF_SEC=60.0`** | **[신설] 공유원인 실패 판정.** 상관은 **exit code가 아니라 시간으로** 정의한다 — 윈도우에선 미처리 파이썬 예외가 전부 exit 1이라 코드 시그니처는 아무 쌍이나 상관으로 부르고 아무것도 증명하지 못한다. 규칙은 **창 안에서 서로 다른 자식 2개 이상이 죽었는가**. 창이 120초인 것은 **예산 1사이클보다 길어야** 하기 때문(2+4+8+16+32초 ≈ 첫 죽음 후 80초에 판정이 나고, 그 시점에 동료들의 마지막 실패는 20–40초 전이다) | ~119/123/126 |
| `STATE_RUNNING\|BACKOFF\|FAILED\|STOPPED` / **`STATE_RETRYING_CORRELATED`** / `_WAITING_STATES` | 자식 상태 어휘. **`retrying_correlated` = 예산은 소진했지만 혼자가 아니다 → 영구 실패시키지 않고 계속 재시도** | ~128–131/133/136 |
| `status_path()` | `paths.config_path("supervisor_status.json")` | ~139 |
| `_database_endpoint(url=None)` / **`shared_dependency_down(url=None, timeout=2.0) -> (down, detail)`** | **[신설] 환경이 깨졌다는 직접 증거.** 왜 동료실패 규칙만으론 부족한가 — PostgreSQL 불통 콜드스타트 실측에서 **죽는 자식은 정확히 하나**다(import가 `Base.metadata.create_all`을 도는 웹서버). 워커 4개는 자기 루프에서 에러를 삼키고 살아남는다. 즉 "재부팅 후 DB가 늦게 떴다"의 가장 흔한 실제 형태가 **고립된 자식 1개**이고, 동료만 세는 규칙은 94초 뒤 웹서버를 영구 실패시킨 뒤 DB가 돌아와도 안 살린다. **TCP 도달성만** 본다(인증·스키마 결손은 재시도가 못 고치는 설정 결함). **모르면 healthy** — 이 프로브는 증거를 **더하기만** 할 뿐 실패시킬 능력을 빼앗지 않는다 | ~143/163 |
| `psutil_status()` / `_psutil_or_warn(log=None)` | 손자 정리 무장 여부를 **기동 시 1회 announce**. 정리 경로가 조용히 퇴화하는 것이 고아 수집기 프로세스가 몇 주씩 쌓이는 경위라, 종료 때 발견하지 않고 부팅 때 말한다 | ~195/216 |
| `_descendant_pids(pid, log=None)` / `_kill_pids(pids, log=None)` | 종료 시 손자 프로세스까지 수거 | ~233/251 |
| `class ChildSpec(name, cmd, cwd, env=None, restartable=True, heartbeat=None, start_delay=0.0)` | 자식 1개의 기동법 + 죽었을 때의 처분. **`restartable=False`는 "이게 죽으면 전체를 멈춘다"**(데스크톱 창 닫기), **`heartbeat=`는 그 자식이 발행하는 비트 이름** — `/health`가 프로세스 관점(감독자)과 진척 관점(비트)을 조인하는 열쇠 | ~269/276 |
| `class _ChildState(spec)` | 자식 1개의 런타임 상태(상태·연속 실패수·시작시각·이벤트) | ~290 |
| `class Supervisor(specs, status_file, log, spawn, clock, sleep, environment_probe, …)` | `spawn`/`clock`/`sleep` 주입 가능 — **실제 프로세스를 띄우지 않고 실제 초를 기다리지 않고** 재시작 정책을 결정론적으로 테스트하기 위함(프로덕션은 아무것도 넘기지 않는다). **`environment_probe`는 기본값이 `shared_dependency_down`**(~344) | ~310/318 |
| ├ `_default_spawn` / `_find` / `_record(child, event, **fields)` / `_backoff_for(n)` | 기본 spawn / 이름 조회 / 이벤트 링버퍼 기록 / 백오프 계산 | ~356/362/368/375 |
| ├ **`_peers_failed_recently(child, now)`** | 창 안에서 **다른** 자식이 몇이나 실패했는지 — 상관 판정의 계수기 | ~378 |
| ├ `start_all()` / `_start(child)` | 순차 기동(+`start_delay`). **spawn 예외도 즉사와 동일한 실패로 계산**한다 — 아니면 잘못된 커맨드라인에서 영원히 돈다 | ~395/402 |
| ├ `_register_failure(child, exit_code, reason=None)` | **정책 본체** — uptime ≥ `healthy_uptime`이면 연속 카운터 리셋, 아니면 +1. 예산 초과 시 **혼자면 `_fail_permanently`, 아니면(동료 실패 ∨ 환경 프로브 down) `_enter_correlated`** | ~420 |
| ├ `_fail_permanently(child, exit_code, reason)` / **`_enter_correlated(child, now, peers, exit_code, env_detail=None)`** | 영구 정지 / **`STATE_RETRYING_CORRELATED`로 진입해 `CORRELATED_BACKOFF_SEC` 간격으로 계속 재시도** — 이미 힘든 DB를 두들기지 않을 만큼 길고, 원인이 걷히면 1분 안에 자동 복구될 만큼 짧다 | ~477/504 |
| ├ `poll_once()` / `run()` | 1틱 점검(종료 감지·백오프 만료 재기동·상태 파일 갱신) / **`run_decoupled_app.py`의 sleep 루프를 대체한 메인 루프** | ~551/591 |
| ├ `stop_all(timeout=3.0)` / `snapshot()` | 종료(자손 포함) / `/health`가 읽는 상태 dict | ~600/644 |
| └ `write_status(force=False)` | `supervisor_status.json` 기록. **`updated_at`이 감독자 자신의 생존 신호** — 감독자가 죽으면 자식들은 계속 비트를 찍지만 이 타임스탬프가 멈추고 `/health`가 그걸 말한다 | ~684 |
| `read_status(path=None)` | 상태 파일 판독(`main.py` 헬스가 소비) | ~702 |

> 미드-인제션 워처를 재시작해도 안전하다는 것이 이 설계의 전제다 — P2 체크포인트 재개가 10만 행 중 3만 행 지점 `taskkill /F` 하에서 드릴됐고 커밋된 오프셋이 실제 행수와 정확히 일치했다(`agent_workspace/reports/QA_p2_drills_isolated.md` §2). **자동 재시작이 허용되는 근거는 그것 하나다.**

### `server/health.py` (**384줄**) — `/health` 판정표 (순수 함수 + config 백업 프로브)
**`8117456` 신설, `b35bc9f`에서 `checks.config_backup` 추가.** 테스트: `tests/test_health_endpoint.py`.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `STATUS_OK\|DEGRADED\|UNHEALTHY` / `HTTP_OK=200` / `HTTP_UNHEALTHY=503` | 상태 어휘와 HTTP 사상 | ~45–47/49/50 |
| `STARTUP_GRACE_SEC=60.0` | 갓 뜬 워커는 모듈 import 후 루프에 닿아야 비트를 찍는다. 이 유예가 없으면 부팅마다 503이 나가고, **부팅 때마다 틀리는 헬스체크는 무시당한다** | ~55 |
| `OUTBOX_AGE_DEGRADED_SEC=300` / `OUTBOX_AGE_UNHEALTHY_SEC=900` / `OUTBOX_COUNT_CAP=10000` | **백로그는 크기가 아니라 나이로 잰다.** 정상적인 10만 행 인제션 1건이 outbox 약 11.6만 행을 만든다(P2 드릴 실측) — 멎은 워커를 잡을 만큼 낮은 크기 임계는 대용량 파일마다 오발화한다. "바쁨"과 "멈춤"을 가르는 건 큐가 **빠지는가**이고, 빠지고 있으면 뒤에 몇 행이 쌓였든 가장 오래된 미처리 행은 젊게 유지된다 | ~62/63/66 |
| **`BACKUP_PROBE_CACHE_SEC=60.0` / `probe_config_backups(now=None)`** | **[`b35bc9f` 신설]** `config_backup.probe()`를 60초 캐시로 감싼 래퍼 — 10초 폴링 모니터가 매번 디스크 스캔을 유발하지 않게 한다. import 실패·예외는 `status:"unknown"`으로 보고(확인 불가를 이상 없음으로 내지 않는다) | ~70/80 |
| `_iso(ts)` | 타임스탬프 직렬화 헬퍼 | ~103 |
| **`compute_health(db_result, heartbeats, supervisor_status, outbox_result, stale_after, now=None, backup_result=_PROBE) -> (payload, http_status)`** | **판정표 본체 — I/O 없음**(순수성 유지: 테스트는 `backup_result=None`으로 백업 검사를 스킵. **`backup_result`만은 생략 시 자체 프로브를 돈다** — 순부가 인자라 main.py 호출부 무수정). 내부 `escalate(level)`이 최악 상태를 끌어올린다. 워커 판정은 감독자 뷰 × 비트 뷰의 조인: `not running→down` · `running + 비트 낡음→wedged` · `running + 비트 없음 + 어림→starting` · `running + 비트 신선→ok`. **비트의 pid가 감독 대상 pid와 다르면 비트를 없는 것으로 친다** — 유령 워커/제2 스택이 wedged된 진짜 워커를 가리는 것이 실제로 관측됐다. **[`b35bc9f`] `checks.config_backup`**: `missing`/`stale`/`unknown` → **degraded, 절대 503 아님**(백업 부재는 "다음 인시던트가 어려워진다"이지 "지금 장애"가 아니다 — 503이면 모니터가 멀쩡한 스택을 재시작한다) | ~107 |
| `probe_outbox(db)` | 백로그 나이 + (상한된) 크기. 둘 다 부분 인덱스 `idx_outbox_unprocessed`를 타고, 나이는 `ORDER BY id ASC LIMIT 1`로 **테이블 크기와 무관한 O(1)**, 카운트는 `LIMIT cap+1`로 감싸 1천만 행 테이블에서도 ~1만 인덱스 엔트리를 넘지 않는다 | ~354 |

### `server/config_backup.py` (**379줄**) — 주간 config 스냅샷 + FIFO 보존 (`b35bc9f` 신설)
**C3 — 롤백 절차(B4)의 빠져 있던 의존성.** `server/config/*.json`을 파일별로 `config_<yymmdd>.json.bak`(동일 날짜 2회째부터 `b`,`c`,… 접미)으로 스냅샷. **신선도는 cron 슬롯이 아니라 디스크의 최신 스냅샷 나이로 판정**한다(놓친 주가 다음 틱에 자가 치유). 소비자 3곳: `run_auto_update.MultiDiscoveryScheduler.maybe_backup_configs`(주기 실행) · `health.probe_config_backups`(`/health` 프로브) · `scripts/backup_config.py`(CLI). 테스트: `tests/test_config_backup.py`(370줄).

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `INTERVAL_DAYS=7` / `STALE_AFTER_DAYS=10` / `RETENTION_DAYS=31` / **`RETENTION_MIN_KEEP=4`** / `CHECK_INTERVAL_SEC=1800` | 주기·신선 임계·FIFO 보존창·**최신 4개 바닥**(31일 FIFO가 어떤 이유로든 몰아서 지워도 최근 4개는 남는다) / 스케줄러 틱 게이트 | ~96–109 |
| `RUNTIME_FILES` / `SUFFIX=".json.bak"` / `_SNAPSHOT_RE` | 스냅샷 제외 런타임 파일 목록 / 스냅샷 이름 문법(`<stem>_<yymmdd><seq>.json.bak`) | ~114/119/122 |
| `snapshot_name` / `source_files` / `list_snapshots` / `newest` | 이름 조립 / 대상 열거 / 스냅샷 열거(오래된 순) / 파일별 최신 | ~131/137/167/188 |
| `_same_bytes(a, b)` / `_prune(entries, config_dir, now)` | 바이트 동일하면 새 스냅샷 무쓰기 / FIFO 퇴거(+4개 바닥) | ~202/212 |
| **`take_snapshot(config_dir=None, now=None)`** / `due` / **`probe`** / **`run_scheduled`** | 스냅샷 1회 실행 / 디스크 기준 기한 판정 / `/health`용 상태(`ok\|missing\|stale\|unknown`) / 스케줄러용 due-체크+실행 래퍼 | ~234/297/306/350 |

### `server/utils/heartbeat.py` (**303줄** — 종전 지도의 174줄은 낡은 값) — 워커 진척 비트 + **작업 단위 claim**
**`8117456` 신설.** 프로덕션 인시던트는 이벤트 루프 프리즈였다 — 프로세스는 내내 살아 있었고 수십 초간 아무것도 서빙하지 못했다. **pid 점검은 그걸 healthy라고 답한다.** 그래서 워커는 **자기 루프 안에서** 진척을 발행한다.

> **[신설] "루프가 돈다"와 "일이 진척된다"는 다른 사실이라 따로 잰다.** 비트는 전자, `work_claim`은 후자다. 파일 1건의 인제션처럼 **한 번에 몇 분씩 걸리는 작업 단위**는 루프 비트만으로는 진척을 증명하지 못한다.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `HEARTBEAT_DIRNAME="worker_heartbeats"` / `heartbeat_dir()` / `heartbeat_path(name)` | 저장 위치 — **`paths.config_path("worker_heartbeats")/<name>.json`** | ~79/137/141 |
| `MIN_WRITE_INTERVAL_SEC=1.0` | 워커당 초당 1회 초과 디스크 접촉 금지(비트 1건 ≈ 200바이트 원자 replace) | ~83 |
| `DEFAULT_STALE_AFTER_SEC=60.0` | **감으로 고른 숫자가 아니다** — 자연 루프 주기(워처 3.0s · 체인 2.0s · 그래프 2.0s · 스케줄러 5.0s) 기준 **가장 느린 루프로도 연속 12회 이상 결번**. 1회 결번으로 알람이 울리면(GC 정지·느린 디스크) 헬스체크는 음소거되고, 그건 없느니만 못하다 | ~102 |
| **`DEFAULT_STALL_AFTER_SEC=300.0`** | **[신설] claim된 작업이 진척 없이 버틸 수 있는 상한.** `STALE`보다 의도적으로 훨씬 크다 — **두 수가 다른 것을 재기 때문**이다. 비트 결번은 2–5초 루프가 안 돌았다는 뜻이지만, claim 진척 결번은 **실제 작업 청크가 안 끝났다**는 뜻이고 청크는 균일하지 않다. 라이브 10만 행 heavy 인제션 실측(35MB·893초)에서 청크 간격 p50 9.20s · p95 9.70s · **max 12.50s**(단일청크 구간 42건). 바닥을 정한 건 **계측할 수 없는 쪽**이다 — 커스텀 파이프라인 파서는 파일 하나를 불투명한 한 번의 호출로 읽고 그동안 아무 보고도 하지 않는 사용자 스크립트라, 큰 워크북에서 몇 분이 정당하게 걸리고 그 안에서는 비트를 찍을 수단이 없다. 300s는 실측 청크 케이던스의 24배이면서 진짜 멈춘 인제션은 5분 안에 드러낸다. **편향은 침묵 쪽이고 그것이 의도다** — 이건 운영자 대시보드에 503을 띄우고, 사람들이 가장 신경 쓰는 바로 그 작업 중에 늑대를 외치는 헬스체크는 음소거된다 | ~125 |
| `_state` / **`_claims` / `_claim_seq`** | 워커별 비트 상태 / claim 레지스트리 — **시간이 아니라 진행 중 작업 수로 유계**(레인당 1개, 모든 claim이 finally에서 제거된다) | ~128/133/134 |
| `beat(name, note=None, force=False)` | **워커의 실제 작업 루프 안에서 반복마다 호출.** 반환값은 테스트용이고 호출자는 무시한다. 고정 temp 파일명 + `os.replace`로 **원자적**(독자가 부분 파일을 보지 않는다). **모니터링 기능이 새 장애 모드가 되면 안 되므로 모든 디스크 오류는 삼키고 카운트만 한다** — 워커 루프로 예외를 올리지 않는다 | ~145 |
| `_work_snapshot_locked(name)` | 그 워커의 **가장 오래 진척 없는 claim**. **나이가 아니라 절대 타임스탬프를 publish**한다 — 독자가 비트가 쓰인 시점이 아니라 **지금**에서 stall을 재게 하기 위함 | ~198 |
| **`work_claim(name, what)` (contextmanager)** | **작업 단위 1건 선언.** 파일 1건의 인제션 전체를 감싸고 그 안에서 `beat(name)`을 부르면 같은 스레드의 비트가 claim 진척을 갱신한다. **실패 경로 포함 항상 해제**된다 — 크래시한 잡이 남긴 claim은 영원한 stall과 구분되지 않는다. 진입 시 `force=True` 비트를 한 번 찍어 **다음 폴러 틱을 기다리지 않고** 즉시 보이게 한다. 소비자: `directory_watcher.process_with_retry`(~750)·`process_archived_file_sync`(~1017) | ~217 |
| `open_claims()` | 이 프로세스의 열린 claim 전량(테스트·진단용) | ~242 |
| `read_all(stale_after=DEFAULT_STALE_AFTER_SEC, now=None, stall_after=DEFAULT_STALL_AFTER_SEC)` | 전 비트 판독(+`age_seconds`/`stale`). **읽을 수 없거나 깨진 파일은 건너뛰지 않고 `error` 필드를 단 stale로 보고한다** — 침묵은 헬스체크가 절대 주면 안 되는 답이다 | ~248 |

> **비트 이름 4종 (2026-07-28 `280ebf0` 실측)**: `watcher`(`run_watcher.poll_pending_retries` ~151 안 **~167**) · `chain`(`chain_ingestion_worker.start_chain_ingestion_worker` ~785 안 **~827**) · `graph`(`graph_sync_worker.run_graph_materializer_loop` ~555의 `while True` ~622 안 **~625**) · `scheduler`(`run_auto_update.MultiDiscoveryScheduler.run` ~605 안 **~636** — `b35bc9f`의 `maybe_backup_configs` 삽입으로 +31·+36 이동). 이 이름이 `run_decoupled_app.py`의 `ChildSpec(heartbeat=…)`와 짝을 이룬다.
>
> ⚠️ **`scheduler` 앵커는 이미 두 번 밀렸다**(`~515`→`600`→`636`). 이것이 이 문서 상단이 경고하는 함정의 **교과서적 실례**다 — 낡은 앵커 자리에는 늘 실재하는 다른 함수가 들어앉아 도착지가 멀쩡해 보인다. 함수명으로 Grep하지 않으면 아무것도 이상해 보이지 않는다.
>
> ⚠️ **`graph` 비트는 `_run_one_batch`(~586) 안이 아니라 그 바깥 `while True`(~622) 안이다** — 배치 본체는 `asyncio.to_thread`로 격리돼 있고, 비트는 **루프가 도는 것**을 증명해야 하므로 격리된 스레드 안에 있으면 안 된다.

### `server/product_tables.py` (201줄) — 제품 소유 테이블 선언 정본
**`8e80fcc` 신설.** 소유권 경계: **제품 소유**(assyManager 자신의 저장소 — 이름·컬럼을 제품이 정하고 사이트가 바꿀 이유가 없다)는 여기 선언, **사이트 소유**(고객 공장 데이터 — 배포마다 이름이 다르다)는 여기 절대 등재하지 않고 설치기도 건드리지 않는다.

| 심볼 | 역할 | 라인 |
|---|---|---|
| `ANNOTATION_KEYS = ("__comment",)` | 문서용 키. `models.init_dynamic_models`가 읽지 않으므로 런타임 동작을 바꿀 수 없다 → 설치기는 이 키의 차이를 **drift가 아니라 note**로 처리한다(주석 한 줄 고친다고 기존 사이트 전부가 drift로 뜨면 안 된다) | ~35 |
| **`PRODUCT_TABLES`** | **4종**: `wafer_map_metadata`(~39, 맵 격자 규격 정본 — bk `target_table_map_id`) · **`map_split_registry`(~60 — legend 행 = DOE 1건. bk `ref_table\|map_key\|value`, 분리자 `\|`. `split_desc`·`knobs`는 온톨로지 소비 대상이라 **플랫 컬럼 유지**. [`269b39e`+`b35bc9f` ZONE 모델] `stack`·`mat_1h`·`mat_mid`·`mat_top` 컬럼 추가, `bands`는 **폐기됐지만 여전히 선언**(아래). `map_key_columns=(ref_table, map_key)`가 `replace_map` 스코프)** · ~~`map_doe`~~(~104) · ~~`map_doe_source`~~(~145) — **뒤 둘은 `0f8d35f`에서 DEPRECATED 표기**(`__comment` 선두에 명시). 아무 코드도 쓰지 않으며 선언만 남은 이유는 운영자가 손으로 데이터를 옮기는 동안 읽을 수 있게 하기 위함이다. **새 소비자를 붙이지 마라.** 물리 DROP은 사용자 승인 대기. 딕셔너리 순서가 config 파일에 append되는 순서다 | ~38 |
| `PRODUCT_TABLE_NAMES` | `tuple(PRODUCT_TABLES.keys())` | ~190 |
| `effective_declaration(entry)` | 주석을 걷어낸 **동작 유발 부분**만 남긴다(drift 판정용) | ~193 |

> **왜 두 번째 JSON이 아니라 Python 모듈인가**: `server/config/**`는 gitignored(`*.sample`만 tracked)라 그 안의 정본 JSON은 배포되지 않는다. 이 모듈은 코드이고 tracked이며 소비자는 정확히 둘 — ① `scripts/install_product_tables.py` ② `config/table_config.json.sample`(같은 설치기가 `--sample --apply`로 **생성**하고 `tests/test_install_product_tables.py`가 둘의 일치를 단언하므로 샘플이 조용히 어긋날 수 없다).
>
> ✅ **ZONE 모델 착지 (`269b39e` 선언 + `b35bc9f` 엔드투엔드)** — 값 하나의 층 구조는 **숫자 하나가 함의하는 고정 3구역**이다: `stack` = 총 층수, `mat_1h` = 1층, `mat_top` = `stack`층, `mat_mid` = 그 사이 전부. FROM도 TO도 구간 행도 없다 — **세 구역이 `1..stack`을 구성적으로 덮으므로 겹침·구멍 검사는 옮겨진 게 아니라 어길 방법이 없어졌다.** 정본 서술은 `map_split_registry.__comment`, 스펙은 `docs/spec/DOE_ZONE_MODEL.md`, 클라 미러는 `client2/src/map_editor.js` ~210–230 주석.
> - **`stack`은 `string` 선언이고 그것이 load-bearing이다** (`b35bc9f` — number였던 것을 **첫 실데이터 전에** 정정): number 선언은 물리 컬럼이 `double precision`으로 나왔고, `crud.cast_value_by_type`가 `'0x10'`엔 raise(읽을 수 없는 STACK 하나가 계획 전체 저장을 막았다), `'7.5'`는 조용히 수리 후 다음 읽기에서 **7로 절단**했다 — 화면은 멀쩡하고 숫자만 모자라는 바로 그 결함. 읽을 수 없는 STACK은 왕복에서 **살아남아야** 한다(V5가 차단하고, 패널이 원문을 보여 주고, Excel로 원문이 돌아간다). 가독성 판정은 컬럼 타입이 아니라 **단일 정수 판독기**(`transfer_plan._int_state` / 클라 `bandToState`)가 한다.
> - **세 `mat_*` 컬럼은 원문 토큰의 JSON 배열**(`["MID1:1","MID3:1"]`)이다 — 분리자로 이어붙이지 않는다: lot 이름에 `:`도 `_`도 합법이라 안전한 문자가 없고, 분리자를 가정했다가 서로 다른 두 풀이 한 행으로 합쳐진 사고가 있다(`doe_bands.js`의 `materialPoolKey` 주석). 토큰 문자열 자체가 정체이고 `lot[_slot][:BIN]` 파싱은 나중의 **선언된** 단계다.
> - **파생값은 저장하지 않는다.** 특히 자재당 수치는 **배분이 아니라 충분성 검사**다 — 웨이퍼는 아무도 기록하지 않는 순서로 한 장씩 소모되므로 균등 나눗셈은 "이 풀로 충분한가"만 답한다.
> - **`bands`는 폐기됐지만 여전히 선언돼 있다(의도)** — `transfer_plan.REGISTRY_LEGACY_ROLE`이 폐기 계획을 읽는 데 쓰고, 이 컬럼만 먼저 빼면 리더가 갱신되기 전까지 validate가 전 사이트 404가 된다. 새 writer 금지.
> - **`updated_by` 컬럼이 없는 것은 의도**다 — `crud.py`의 `system_cols`에 들어 있어 제네릭 테이블 API로는 영원히 쓰이지 않는다(구 `map_doe`의 전 행이 NULL이었다). '누가'는 `cell_sources`/`cell_overwrites.updated_by`가 이미 나른다.
>
> ⚠️ zone 규칙(V1–V6)·토큰 문법·수요 산술은 **양쪽 구현이 공유 벡터로 고정**돼 있다 — [§6-2 `contracts/doe_band_rules/`](#6-2-교차-구현-계약-contracts) 참조 (레거시 `bands` 산술은 `contracts/band_arithmetic/`). **[`2baf9ff` U9] `stack`의 명시적 `'0'`은 marker(상태 표시 값)** — 층·구역·수요 없는 조건 선언이고, 구역 자재와 공존하면 V6이 차단한다(blank와 다르다 — blank는 V5).

### `server/database/models.py` (~529줄) — ORM + 동적 모델/런타임 DDL
정적 ORM 클래스(`AuditLog` ~11 / `DatabaseOutbox` ~30 / `FileIngestionLog` ~98 / `FileIngestionCheckpoint` ~112 / `CellOverwrite` ~159 / `CellSource` ~176)와 **그래프 3모델**, config 주도 동적 테이블 관리 함수.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `class GraphNode` | 그래프 노드 — `(label, identity_key)` UNIQUE, props JSONB | ~198 |
| `class GraphEdge` | 그래프 엣지 — (from,type)/(to,type) 인덱스, `(from,type,to,source_name)` UNIQUE, `idx_graph_edges_row_ref(source_row_ref)` | ~215 |
| `class GraphSyncState` | materializer outbox 소비 커서(id=1 단일 행, `last_outbox_id`) | ~243 |
| `DYNAMIC_TABLES` | 동적 테이블 싱글턴(`sys._dynamic_tables_singleton`) | ~259 |
| `init_dynamic_models(config_dict)` | config → 동적 ORM 클래스 생성·등록. `column_types`/`business_key`/`composite_key_*`만 읽는다(그 외 키는 무시 — `product_tables.ANNOTATION_KEYS`의 근거) | ~264 |
| `sync_dynamic_tables_schema(engine)` | ⚠️ 이름과 달리 **존재하는 테이블의 ALTER 전용**(`has_table` 아니면 skip — 신규 CREATE 안 함). 부팅 경로에서만 호출 | ~351 |
| `_runtime_ddl_lock` | in-process DDL 직렬화 락(watchdog 스레드 vs reload-configs 요청 스레드) | ~388 |
| `create_missing_dynamic_tables(engine) -> list[str]` | **신규 테이블 한정 물리 CREATE**(이슈 #7) — information_schema 게이트 + `checkfirst=True` + 테이블별 독립 트랜잭션(실패 자체 rollback). 기존 테이블 런타임 ALTER는 범위 밖(C-8) | ~391 |
| `ensure_graph_tables(engine) -> list` | 그래프 3테이블 생성(#7 패턴: 게이트+checkfirst+락+실패 격리) | ~432 |
| `ensure_ingestion_checkpoint_table(engine)` | [P2] `file_ingestion_checkpoints` 생성(동일 패턴) | ~469 |
| `refresh_dynamic_models(engine=None) -> list[str]` | **핫리로드 공용 진입점** — config 디스크 재로드 → `crud.TABLE_CONFIG` 싱글턴 갱신(빈/손상 config 시 기존 보존) → `init_dynamic_models` → engine 지정 시 물리 CREATE(+그래프 테이블 보장). 호출처: main `reload_local_process_cache` / config_watcher(간접) / run_watcher·chain worker·graph worker SYSTEM_RELOAD | ~502 |

### `server/ontology_config.py` (~305줄) — 온톨로지 매핑 v2 로더/검증
| 시그니처 | 역할 | 라인 |
|---|---|---|
| `validate_ontology_mapping(raw_config, known_tables=None) -> dict` | v2 검증 — description 필수(테이블/엣지), 컬럼 존재 검증, 테이블 단위 스킵, 공간 속성 파싱, v1/`__`키 무시 | ~179 |
| `synthesize_enrichment_mappings(mappings, enrichment_rules) -> dict` | enrichment rule → `RESOLVED_AS` 엣지 자동 승격(`source_override="user"`, 사용자 정의 우선) | ~218 |
| `load_ontology_mappings(path=None, known_tables=None, include_enrichment=True) -> dict` | 로드 진입점(materializer·`/graph/mapping-summary` 공용 신호원) | ~280 |

### `server/graph_materializer.py` (~575줄) — 그래프 승격 코어
| 시그니처 | 역할 | 라인 |
|---|---|---|
| `compose_identity(values) -> str\|None` | identity 조립 — `"\|"` 조인 + 이스케이프(`\`→`\\`, `\|`→`\\\|`) + float 정수 안정화 | ~54 |
| `flatten_payload_data(data)` / `extract_graph_items(table_name, rows, mapping, ...)` | 이벤트 행 → 노드/엣지 산출. 엣지 소스 = source_override 또는 식별 컬럼 winner들의 **최저 서열(보수적)** | ~89/100 |
| `bulk_upsert_nodes(db, node_map, chunk_size=1000) -> dict` | 방언별 ON CONFLICT + props shallow-merge(PG `\|\|`) | ~208 |
| `_retarget_stale_edges(db, rows, chunk_size) -> int` | 재교정 시 `(from_node, type, source_row_ref)` 스코프 stale 타깃 삭제 | ~249 |
| `bulk_upsert_edges(db, edges, node_ids, chunk_size=1000) -> int` | 엣지 벌크 UPSERT | ~301 |
| `materialize_rows(...)` / `materialize_events(db, events, mappings, chunk_size) -> stats` | 증분 소비 본체(DELETE 스킵+카운트) | ~358/373 |
| `_load_best_cell_sources(...)` / `attach_col_sources(db, table_name, rows, mapping)` | provenance 결정 단일 지점 — CellSource winner 로드(crud 서열, row_id IN 청킹). 증분·resync 공용 | ~441/473 |
| `resync_table(db, table_name, mappings, chunk_size=1000, row_ids=None, chunk_hook=None, stamp_synced=True) -> stats` | 백필/복구 — 키셋 청킹(C-7), row_ids 슬라이스 모드, Neo4j 청크 훅 | ~491 |

### `server/graph_sync_worker.py` (~1,007줄) — 그래프 워커 (materializer 루프 + 백필 API :8090)
| 시그니처 | 역할 | 라인 |
|---|---|---|
| `ONTOLOGY_PATH` / **`VIRTUAL_GRAPH_PATH`** | `paths.config_path("ontology_mapping.json")` / **`<paths.DATA_ROOT>/database/virtual_graph.json`**. 후자가 `paths` 경유인 것은 이 파일이 **쓰기 대상**이기 때문 — `save_virtual_graph()`(~293)가 통째로 덮어쓰므로, `__file__`에서 조립하던 종전 코드로는 격리 워커가 **라이브 파일을 덮어썼다** | ~16/282 |
| `post_event_async(endpoint, payload)` | 웹서버 `/internal/events/*` POST. **[`90e284f`] `headers=admin_auth.internal_event_headers()`(~469, 지연 import ~467)** | ~459 |
| `_load_graph_mappings()` / `_get_or_init_graph_cursor(db)` / `_advance_graph_cursor(db, last_id)` / `_reload_graph_worker_configs()` | 매핑 로드 / 커서 초기화(최초=현재 최대 outbox id) / 커서 전진 / SYSTEM_RELOAD 리로드(이슈 #8) | ~484/492/515/531 |
| `run_graph_materializer_loop()` | **메인 루프** — LISTEN/NOTIFY + keyset 커서, 배치 본체 `_run_one_batch`(~586)를 `asyncio.to_thread` 격리, `[GraphLatency]` 계측. **`while True`(~622) 진입 직후 `heartbeat.beat("graph")`(~625) — 격리 스레드 밖이다** | ~555 |
| `get_row_data_for_sync(db, table_name, row_ids)` | ⚠️ DEPRECATED(신규 배선 금지) | ~655 |
| `_neo4j_chunk_hook_factory(table_name)` | Neo4j 병행 경로 청크 훅(G3 인터페이스 보존) | ~835 |
| `execute_manual_sync(table_name, row_ids) -> dict` | `/sync` 백필 — 키셋 청킹 + 테이블당 `batch_refresh_required` 1건 + to_thread, `"all"` 지원 | ~858 |
| `startup_event()` | TABLE_CONFIG 동기화 + `ensure_graph_tables` + 루프 기동(`GRAPH_MATERIALIZER_ENABLED`) | ~977 |

### `server/parsers/std_parser.py` (~222줄) — 무스크립트 표준 파서
| 시그니처 | 역할 | 라인 |
|---|---|---|
| `is_std_supported(file_path) -> bool` | 확장자 게이트(csv/tsv/txt) | ~31 |
| `_resolve_delimiter` / `_build_header_map` / `_resolve_key_groups` / `_row_has_key` / `_map_record` | 구분자 추정·헤더↔컬럼 매핑·키 검증 | ~36–127 |
| `_iter_rows(file_path, encoding, delimiter, header_map, key_groups)` | 스트리밍 행 이터레이터 | ~144 |
| `parse_std_file(file_path, table_info, table_name) -> (row_iter, total_rows, skipped_no_key)` | **진입점** — 키 결측 행은 스킵 카운트(파일 전체 거부 안 함), 헤더 실패 시 ValueError | ~155 |

### `server/enrichment_config.py` (~299줄) — 인리치먼트 규칙 로더/검증
| 시그니처 | 역할 | 라인 |
|---|---|---|
| `_resolve_view_query` / `_validate_view_sql(sql, decision_key)` | 참조 뷰 SQL 검증(SELECT 전용 등) | ~59/81 |
| `_normalize_reference_views` / `_validate_rule(name, raw, known_tables)` | 규칙 정규화·검증 | ~103/139 |
| `validate_enrichment_rules(raw_config, known_tables) -> list` | 전체 검증 진입점 | ~231 |
| `load_enrichment_rules(path, known_tables)` / `load_enrichment_chain_rules(...)` | 로드 / **체인 룰 형태로 변환**(rule["enrichment"] 내장) | ~250/264 |
| `to_public_rule(rule) -> dict` | 클라이언트 공개용 필드만 추출 | ~286 |

### `server/enrichment_mapper.py` (~177줄) — 인리치먼트 dedup 맵퍼
| 시그니처 | 역할 | 라인 |
|---|---|---|
| `_recount_affected_keys(db, source_table, decision_key, key_raw_values) -> dict` | 영향 키의 소스 행 재집계 | ~33 |
| `map_enrichment_dedup(db, payloads, rule=None)` | **진입점**(체인 워커가 호출) — 배치 payload → decision_key당 1행 upsert 목록 생성 | ~64 |

### `server/ingestion_activity.py` (~149줄) — [P1 신규] 인제션 진행 스냅샷 레지스트리
웹서버 인메모리(스레드 안전). 유입 3종: ① `/internal/events/ingestion-state`(heavy 명시 통지) ② `file_ingestion_progress` 브로드캐스트 인터셉트(normal 엔트리는 이 경로로만 생성 — lane 비오염) ③ file-processed 시 제거. 파일명 키는 `get_basename` 정규화로 일치. 모듈 싱글턴 `registry`.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `STALE_ENTRY_TTL_SECONDS=30분` / `STALE_QUEUED_TTL_SECONDS=24h` | 고아 퇴거 TTL — 상태별 차등(QA F1: QUEUED는 24h, watcher 재기동 스윕이 자가 치유) | ~25/33 |
| `class IngestionActivityRegistry` | 레지스트리 본체(생성자에 ttl 주입 가능 — 테스트용) | ~36 |
| ├ `apply_state(state)` | QUEUED/PROCESSING/FINISHED 상태 반영(FINISHED=제거, 멱등) | ~67 |
| ├ `apply_progress(table_name, filename, progress, processed_rows, total_rows)` | 진행률 병합(없으면 normal 엔트리 생성) | ~95 |
| ├ `remove(table_name, filename)` | 멱등 제거 | ~115 |
| └ `_ttl_for(entry)` / `snapshot() -> list` / `clear()` | 상태별 TTL / **조회 스냅샷(+TTL 퇴거)** — `/admin/file-ingestion/active`가 서빙 / 초기화 | ~122/126/143 |

### `server/bonding_plan.py` (~442줄) — [본딩 M1] 역할 바인딩 config 로더 + 집계 코어
`paths.config_path("bonding_plan_config.json")`(gitignored, `.sample` tracked) — 역할(process_history/defect/eds_fail/used_chips/total_chips)→실테이블·컬럼 바인딩. 테스트: `tests/test_bonding_plan.py`(20개, `bdp_test_*`).

> **좌표 변환은 이 모듈에 없다 (2026-07-27 일원화).** 구 `normalize_align`/`make_align_transform`/`align_status_label`은 **삭제**됐고 정렬은 `map_overlay.resolve_map_transform`(메타 델타 유도)을 경유한다. `sources[].align` config 선언도 폐기 — 정렬의 근거는 `wafer_map_metadata` 하나뿐이다.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `ROLES` / `HISTORY_LIMIT=50` / `MAX_REGION_RECTS=50` / `MAX_REGION_POINTS=100k` | 역할 어휘·이력 상한·region 하드캡 | ~37–40 |
| `CANONICAL_FRAME_ROLES` (상수) | canonical(CORE) 프레임 후보 순서 `("total_chips","defect","eds_fail")` — **좌표를 바인딩한 첫 역할**이 기준을 정의하며 그 역할에 메타가 없으면 canonical은 None(뒤 역할로 넘어가지 않는다 — 넘어가면 회전된 계측 맵이 기준을 참칭해 조용히 identity가 된다) | ~44 |
| `load_bonding_plan_config(path=None) -> dict` / `_valid_source(src)` | config 로드·검증(미연결 역할은 부분 가동) | ~51/68 |
| `parse_region(region_str)` / `clamp_rects(rects, grid)` / `_point_in_rects(x, y, rects)` | region rects 파서(잘못된 형식 → 400 소재) / canonical 메타 치수로 클램프(완전 밖 rect 제거) / 점 포함 판정 | ~80/106/126 |
| `load_map_meta(db, config, target_table, map_id, cache=None)` | wafer_map_metadata의 **grid_metadata 원본 dict** 조회(config `map_metadata` 바인딩 경유). 정렬 유도의 근거이므로 격자 치수만 잘라 쓰면 안 된다. `cache`는 요청 경계 스냅샷(N+1 금지) | ~137 |
| `load_grid_meta(db, config, target_table, map_id, cache=None)` | 격자 규격만 필요한 호출자용 축약(region rect 클램프 전용) | ~182 |
| `_resolve_model_columns(source_cfg, required)` / `_fetch_points(db, cols, filters, distinct_pairs=False)` | 바인딩 해석 / 좌표 페치(하드캡 적용) | ~197/216 |
| `get_core_summary(db, lot, slot, rects=None, config=None) -> dict` | **집계 진입점** — 역할별 카운트(맵 모드 fail_values 필터, used_chips distinct), `remaining = total − defect − eds_fail − used`(음수 가능 — 과도기), history 50건+warnings, region 교차(좌표 하드캡 100k, 응답 미포함). 좌표 정렬은 `map_overlay.resolve_map_transform`(~293) + `map_overlay.align_status_label`(~306) 위임 | ~227 |

> ✅ **A2 해소 (2026-07-27)** — bbox 항 없는 사본은 삭제됐다. 착수 전제였던 "휴면"은 사실이 아니었다 — `bonding_plan_config.json`·`transfer_plan_config.json` 둘 다 `eds_fail`에 `rotation:180`을 라이브로 선언하고 있었고, 그 값은 `eds_fail_map` 메타의 rotation과 동일했다(선언이 메타의 중복). 라이브 규격(40×40)은 bbox가 0이라 두 구현 결과가 1288셀 전건 일치 → **가용량 수치 변화 없음**. [히스토리](../history/20260727_004500_align_consolidation_meta_single_source.md)

### `server/ingestion_checkpoint.py` (~258줄) — [P2 신규] 오프셋 체크포인트 + 파일 해시 dedup
저장소는 신규 테이블 **`file_ingestion_checkpoints`**(`UNIQUE(table_name, file_signature)` = `idx_fic_identity`). `FileIngestionLog`에 컬럼을 붙이지 않은 이유는 `create_all`이 ALTER를 하지 않아 **조회 프로세스보다 먼저 도는 마이그레이션**이 필요해지기 때문(운영 DB `UndefinedColumn` 500 회피 — 총괄 승인 판단). 테스트: `tests/test_ingestion_checkpoint.py`.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `SIGNATURE_ALGO="sha256"` / `STATUS_IN_PROGRESS` / `STATUS_DONE` / `FORCE_REINGEST_TOKEN="__force__"` | 시그니처 알고리즘·상태 어휘·강제 재처리 파일명 토큰 | ~51/53/54/58 |
| `compute_file_signature(file_path) -> str\|None` | **전체 파일** 1MB 스트리밍 해시 → `sha256:<size>:<digest>`. 샘플링 아님 — 500MB 0.535초 실측(드릴 총 415초의 0.004%)이라 정확성을 택했다. `OSError`면 경고 후 None(체크포인트·dedup 비활성), `PermissionError`는 **재raise**(호출자 재시도 경로로) | ~61 |
| `is_force_reingest(filename) -> bool` | 파일명에 `__force__` 토큰(대소문자 무시) | ~88 |
| `class CheckpointPlan` (+`disabled(note)` classmethod, `is_resume` property) | 파일 1건의 계획 값 객체 — 비활성 사유(note)도 detail·이력에 노출 | ~93/116/122 |
| `find_checkpoint(db, table_name, file_signature)` / `find_completed_ingestion(...)` | UNIQUE 인덱스 단일행 조회 / 동일 내용 `DONE` 여부(dedup 판정) | ~132/142 |
| `plan_ingestion(db, table_name, file_signature, filename, filepath, total_rows, source_kind, force_restart=False) -> CheckpointPlan` | **재개 판정** — `force_restart` 아님 ∧ `status != DONE` ∧ `source_kind` 일치 ∧ `total_rows` 일치 ∧ `0 ≤ processed_rows ≤ total_rows`가 **전부** 성립할 때만 `resume_from = processed_rows`. 하나라도 어긋나면 0부터 + `[resume-abort] … 사유:` note를 WARNING·`row.note`에 남긴다(조용한 재처리 금지) | ~150 |
| `record_chunk_progress(db, plan, processed_rows, chunk_index)` | **청크 적재와 같은 세션·같은 트랜잭션**에서 오프셋 Core UPDATE — "커밋된 행 수 == 기록된 오프셋" 원자성의 근거 | ~218 |
| `mark_done(db, plan, processed_rows=None, note=None)` | 성공 확정(`status=DONE`) — 이후 dedup skip 대상 | ~243 |

### `server/map_overlay.py` (~695줄) — [M2 신규] 범용 맵 오버레이 (계획 전용 아님 — 맵 인프라)
`paths.config_path("map_overlay_config.json")`(gitignored, `.sample` tracked) — 키 구조만: `table_bindings.{table}.columns{x,y,val,key_columns}`, `paint_lock.{"*"|table}{enabled,blocking_values,from_overlay,message}`. `APIRouter` 없음 — `main.py`가 `@app.get`으로 직접 등록해 위임한다. 테스트: `tests/test_map_overlay.py`.

> **삭제된 선언 레이어 (2026-07-27, `4ba13ae`)** — `align_overrides`(config 선언)·`by_eqp` 분기·`align_override_declared` status·`_frame_grid_of`가 **전부 제거**됐다. 정렬의 근거는 이제 `wafer_map_metadata` 하나뿐이며 `resolve_align`은 **메타만** 받는다. config에 `align_overrides`나 `sources[].align`을 다시 쓰는 코드를 보면 그것은 부활이 아니라 **오류**다.

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `MAX_OVERLAY_CELLS=20,000` / `MAX_OVERLAY_SOURCES=8` | 오버레이 1종당 셀 상한(초과 시 `truncated:true`) / 요청당 소스 상한 | ~70/71 |
| `STATUS_OK` / `STATUS_ALIGN_UNAVAILABLE` / `STATUS_SOURCE_MISSING` / `STATUS_NO_DATA` | 엔트리 status 어휘 | ~73–76 |
| `ALIGN_ORIGIN_DERIVED` / `ALIGN_ORIGIN_IDENTITY` | align 결정 출처 마커 — **둘뿐이다.** `DECLARED`/`DEFAULT`는 선언 레이어와 함께 삭제됐다 | ~78/79 |
| `ALIGN_ORIGIN_UNRESOLVABLE` | 구 QA-B3 가드 유물 — **프레임 합성(A1) 도입 후 더 이상 발화하지 않는다**(상수만 잔존) | ~82 |
| `load_overlay_config(path=None)` / `load_map_meta(db, target_table, map_id)` | config 로드(부재·손상 시 `{}` — 에러 아님) / `wafer_map_metadata`(`META_TABLE` ~103)의 `grid_metadata` 조회 | ~85/106 |
| `_rotation_of` / `_grid_of` / `_side_of` / `_y_invert_of` / `PHYS_KEYS` / `_phys_signature` | 메타 정규화 헬퍼 — `_grid_of`는 메타 선언 그대로의 **물리(canonical) 격자 규격**, `_phys_signature`는 `phys_*` 6값 튜플(하나라도 없으면 None = bbox 재현 불가) | ~128/135/150/154/158/162 |
| `frame_axes(meta)` | 프레임 정의 8축 튜플 `(rot, side, y_invert, start_x, start_y, cols, rows, phys_sig)` — identity 지름길 판정·transformer 캐시 키 | ~172 |
| **`_frame_phys_params(meta)`** | **[A1]** 물리 규격 → **프레임 축 규격**. `is_cell_inside_wafer(c, r, …)`는 프레임 인덱스를 받으므로 rot 90/270에서 **칩 피치를 스왑**하고 back에서 `off_x` 부호를 뒤집는다. 유일 호출자는 `_frame_transformer`. **보정을 이 모듈 안에 가둔 것이 계약** — `WaferMapCoordinateTransformer`·`PhysicalWaferEngine`은 무수정(`bonding_plan.py`가 같은 클래스를 공유) | ~190 |
| `_FRAME_TF_CACHE` / `_frame_transformer(meta, grid)` | transformer(+engine) 생성 후 `frame_axes` 키로 캐시(상한 512 초과 시 전체 clear) | ~237/241 |
| `make_frame_transform(source_meta, target_meta)` | **소스 프레임 → 물리 → 타깃 프레임** 합성 변환기(내부 `to_target(x, y)` ~314). 메타/격자/phys 부재·물리 치수 불일치 시 `ValueError` | ~271 |
| `_align_summary(rotation, flip)` / `align_status_label(align)` | 표시용 요약 dict(변환에는 안 쓰인다) / 상태 문자열 마커 `aligned:180` 등 — **`bonding_plan`에서 이관**(변환 소유 모듈이 마커도 소유). 소비자: `bonding_plan.get_core_summary` ~306 · `transfer_plan._canonical_fail_set` ~620 | ~324/335 |
| `resolve_align(source_meta, target_meta) -> (align\|None, origin, note)` | **align 결정 규율 — 인자는 메타 둘뿐이다.** 메타 델타 유도 > **identity**(메타 부재는 실패가 아니라 등록 누락 신호). origin은 `derived`/`identity` 둘뿐 | ~354 |
| **`resolve_map_transform(source_meta, target_meta) -> (transform\|None, align, origin, note)`** | **서버의 단일 좌표 변환 진입점.** 오버레이(그리기)와 가용량 산출(`bonding_plan`/`transfer_plan`)이 **같은 이 함수**를 쓴다. transform None = identity, 계산 불가 시 `ValueError`(호출자가 `align_unavailable`로 표면화) | ~394 |
| `_pure_translation(source_meta, target_meta, origin)` / `align_applied_payload(align, origin, note=None, translation=None)` | derived이고 rot/side/y_invert/격자/phys가 전부 같을 때만 `(dx,dy)` / 클라 표시용 `{rotation, flip, offset, origin, note?}` | ~413/429 |
| `parse_sources(spec) -> [(table, key\|None)]` | `"table"` / `"table:key"` CSV 파싱 — 8종 초과·빈 값은 `ValueError`(→400) | ~452 |
| `VAL_CANDIDATES` / `_SYSTEM_COLUMNS` / `derive_table_binding(table)` / `resolve_binding(cfg, table)` | `table_config`에서 x/y/val·key_columns 자동 유도(후보 순, 시스템 컬럼 제외) / **선언 우선 + 유도 폴백** | ~475/478/484/522 |
| `build_key_filters(model, binding, map_key)` | `_` 조인 복합 map_key를 key_columns로 분해해 ORM equality 필터 생성(마지막 컬럼이 나머지 흡수) | ~534 |
| `get_overlay(db, cfg, target_table, target_key, sources, cell_cap=MAX_OVERLAY_CELLS) -> dict` | **메인 진입점** — 소스별 바인딩·align 해결 → 셀 조회 → 타깃 프레임 좌표 변환 → `{target, overlays[], cell_cap}`. **`eqp` 인자는 `by_eqp` 분기와 함께 삭제됐다**(엔드포인트 쿼리 파라미터만 no-op으로 존치 — 축소는 총괄 승인 사항) | ~559 |
| `get_paint_rules(cfg, table=None) -> dict` | `paint_lock`의 `"*"` 기본 + 테이블별 선언 머지 → `{enabled, blocking_values, from_overlay, message}` | ~676 |

> `resolve_binding`·`build_key_filters`는 **`transfer_plan.py`도 재사용**한다(모듈 간 공용 헬퍼 2개).
>
> **소비자 지도 (2026-07-27 정렬 일원화 이후)**: 이 모듈의 정렬 함수군을 쓰는 것은 ① `/api/maps/overlay` 엔드포인트 ② **`bonding_plan.get_core_summary`** ③ **`transfer_plan._canonical_fail_set`** ④ `test_map_overlay.py`다. ②③이 이번에 배선됐고(구 A2), 그 결과 **정확한 구현이 운영 소비자를 갖게 됐다** — 종전에는 맞는 구현이 엔드포인트에서만 돌고 가용량은 안 고쳐진 사본으로 계산됐다. **맵 에디터 클라는 이 엔드포인트를 더 이상 호출하지 않는다**(변환은 클라 단일 구현 — [§7 `map_editor.js`](#7-client2src--웹-클라이언트)). `transfer_plan.py`는 정렬 함수 외에 바인딩·config 헬퍼 3개(`resolve_binding`/`build_key_filters`/`load_overlay_config`)도 쓴다.
>
> **구현 개수**: 서버 1(이 모듈) + 클라 1(렌더) = **2**. 가용량이 서버에서 계산되는 한 이것이 하한이다.

### `server/transfer_plan.py` (~3,080줄) — [M2] Universal Transfer Plan 엔진 (v2 = 계획 정체성이 곧 맵 정체성, **`b35bc9f` zone 모델 · `2baf9ff` U9 marker**)
`paths.config_path("transfer_plan_config.json")`(gitignored, `.sample` tracked) — `stages.{name}.{source_kind, target_kind, target_map{table,preset}, source{...} \| source_config_ref}` + **`plan_store.{registry, material_identity, source_region?}`**. 테스트: `tests/test_transfer_plan.py` + **`tests/test_doe_zone_model.py`(471줄, `b35bc9f` 신설·`2baf9ff` 확장 — V1–V6을 `contracts/doe_band_rules` 벡터로 채점, 뮤테이션 런 29/30 킬 + marker 축 9/9 킬)**.

> **[`b35bc9f`] validate가 zone 컬럼을 읽는다** — `REGISTRY_ROLES = ("ref_table","map_key","value","stack","mat_1h","mat_mid","mat_top")`(~146). **하나라도 빠지면 `validate`가 404**다. **`bands`는 `REGISTRY_LEGACY_ROLE`(~149)로 강등** — 선택 역할이라 미선언 사이트도 404가 되지 않고, 선언돼 있으면 폐기 band 계획을 계속 읽어 `bands_to_zones`로 zone에 사상한다(마이그레이션 창).
> - **`material_identity`** — 테이블 바인딩이 **아니라** 문자열 해석 규칙. 자재 ID 원문을 소스로 푸는 **선언된** 관례이며 코드에 박힌 관례는 없다. 미선언이면 모든 자재가 `source_unresolved` → 계획 전체 `unverified`.
> - `source_region` — 선택·**휴면**(라이브 config 미선언. 미선언은 결함이 아니다).
>
> **수량은 저장되지 않고 유도된다** — `zone_layers`(1H=1층·TOP=1층·MID=`stack−이웃 수`) × `painted(값)` = `zone_demand`, 자재당 = `ceil(total / n)`(**배분이 아니라 충분성 검사**). 그래서 페인팅 분포 읽기(`_painted_values`)가 **load-bearing**이고, 실패 시 모든 required가 0이 되어 부족이 영원히 발화하지 않는다 → `painted_reliable`(~2739)이 유도 전체를 게이트한다.
>
> **[`2baf9ff` U9] STACK 0 = marker(상태 표시 값)** — 명시적 `0`은 층수가 아니라 **조건 선언**(예: BASE FAIL)이다. `stack_state`만 `marker`로 승격하고(`_int_state`는 무수정 — band `to`·BIN은 여전히 0 거부), marker 행은 구역 전부 `[]`(구성적 0층)·수요 0·롤업 부재·V3 풀 스캔 제외이며 **V6 하나에만 답한다**(구역에 자재가 있으면 그 모순을 차단으로 보고). blank는 marker로 접히지 않는다 — blank는 "아직 안 적음"(V5), 0은 선언이다.
>
> **좌표 변환 사본 없음** — 이 모듈은 `map_overlay.resolve_map_transform` **하나만** 쓴다(~1059). **zone 산술·규칙은 클라 `doe_bands.js`와 공유 벡터로 고정** — [§6-2 `contracts/doe_band_rules/`](#6-2-교차-구현-계약-contracts). 레거시 `bands` 산술(`to` 3상태, prevTo 걷기)은 종전대로 [`contracts/band_arithmetic/`](#6-2-교차-구현-계약-contracts).

| 시그니처 | 역할 | 라인 |
|---|---|---|
| `MAX_*` 하드캡 **15종** + `CORE_ID_SEP="\|"` | `MAX_ORIGIN_POINTS/MAX_FAIL_POINTS=100k` · `MAX_BY_CORE=500` · `MAX_DOE_PER_PLAN=500` · `MAX_PLAN_VALUES=1000` · `MAX_SOURCES_PER_DOE=64` · `MAX_BANDS_PER_PLAN=2000` · `MAX_DEMANDS_PER_PLAN=5000` · `MAX_SOURCES_PER_PLAN=200` · `MAX_BANDS_BLOB_BYTES=256KiB`(**`json.loads`보다 먼저** 재는 유일한 캡) · `MAX_LAYER=2^53` · `MAX_REGION_CELLS=100k` + **[`269b39e` BIN 축] `MAX_BIN_VALUES=200` · `MAX_BIN_CELLS=200k` · `MAX_LOT_SLOTS=50`**. 팬아웃 차단: 수요 총량과 서로 다른 소스 수를 따로 묶는다(실측: 1.53MB blob 1행이 128,000 수요를 냈다) | ~104–125 |
| **`REGISTRY_ROLES` / `REGISTRY_LEGACY_ROLE="bands"`** | 필수 역할 7종(zone) / 폐기 모델 읽기 전용 선택 역할 | ~146/149 |
| `WARN_*` **22종** | validate·강등 경고 타입(`grep -c "^WARN_" = 22`) — `qty_shortage`(~152) · **`layer_range_invalid`(~167 — 이제 **폐기 모델(`bands`)에서만** 나온다. zone 컬럼엔 "구조를 못 읽는" 상태가 없다. **`reason` 3종**: `unreadable` \| `not_a_band` \| **`not_convertible`(세 구역으로 표현 불가 — 구간 4개·`to` 불량·역전·1층 미시작, `detail` 동봉. 🔴 접어서 통과시키지 않는다** — 뭉갠 읽기를 `replace_map`으로 되쓰면 서버의 진짜 계획이 덮인다). 구 reason `incomplete`/`not_increasing`은 **거부(`not_convertible`)로 승격**)** · **`zone_rule_violation`(~170 — V1–V6 차단, `rule` 필드. 클라 `doe_bands.validateZonePlan`과 같은 판정)** · **`zone_rule_advisory`(~173 — 차단 아님: W-DUP-MAT 등 파생 수치를 움직이는 것)** · **`source_scope_unpriced`(~178 — `MID1`=로트 전체 토큰: 해석 실패가 아니라 "판정 안 함". 0으로 접으면 "다 썼다"로 읽힌다)** · `undefined_doe_value` · `painted_unavailable`(~183 — [B2] 페인팅 분포를 못 읽었다. 유도 모델의 새 의존) · `doe_value_unpainted` · `source_fail_chips` · `source_history_fail` · `stage_unknown` · `source_unresolved` · `source_degraded` · `availability_unreliable` · `source_overallocated` · `result_truncated` · `negative_remaining` · **[BIN 축] `bin_axis_unavailable`(~200) · `bin_population_mismatch`(~202)** · **[로트 전개] `lot_membership_unknown`(~205) · `lot_membership_degraded`(~207) · `lot_slot_map_missing`(~209)**. ⚠️ **~~`layer_coverage_gap`~~은 개명이 아니라 삭제** — zone은 구성적으로 `1..stack`을 덮어 구멍이 **표현 불가**(근거 주석 ~165) | ~152–209 |
| `EFFECT_*` **7종** | 효과 분류 — `population_mismatch`(~198) / `bin_axis_unavailable`(~203) / `lot_expansion_partial`(~210) / `remaining_overstated`(~222) / `total_unknown`(~223) / `by_core_degraded`(~224) / `history_incomplete`(~225) | ~198–225 |
| **`BIN_OK/BIN_ABSENT/BIN_UNKNOWN` · `BIN_SCOPE_SLOT/LOT`** | BIN 항목 status 어휘 — **`0`은 이 셋 중 어느 것도 대신할 수 없다**(`0`="다 썼다", `bin_absent`="그 BIN이 여기 없다" — 사용자 행동이 다르다. DOE_BAND_MODEL §4-bis) | ~215–219 |
| `load_transfer_plan_config(path=None)` / `get_stages(cfg)` / `_valid_binding(src)` | config 로드(부재·손상 시 부분 가동) / stages dict 추출 | ~232/249/254 |
| `_resolve(src_cfg, required)` / `_binding_status(...)` / `_stage_role_statuses(stage_cfg)` / `_plan_store_statuses(cfg)` | 바인딩 → (model, 컬럼맵) / `connected`\|`missing` / stage 역할별·plan_store 역할별 상태(`registry` + `material_identity` 고정 + `source_region` 선언 시에만) | ~263/275/282/313 |
| **`stage_of_table(cfg, ref_table)`** | **[v2 핵심] `stages.*.target_map.table` 역인덱스** — 열린 테이블에서 stage를 유도한다 | ~342 |
| `list_stages(cfg)` | `GET /api/transfer-plan/stages` 응답 `{stages[], plan_store}` | ~359 |
| `_status_is_degraded` / `_degradation_effect(role, fail_roles)` / `assess_degradation(statuses, fail_roles)` | **[QA F1 1층]** 역할 강등 탐지 → `(경고 리스트, remaining_reliable, total_reliable)` | ~380/393/407 |
| `build_chips_block(...)` | **[QA F1 3층]** chips 블록 조립 + **음수 remaining 불변식**. 신뢰불가면 `remaining: null`(오표시 구조 차단), `total_reliable ∧ remaining≥0`일 때만 `remaining_upper_bound` | ~446 |
| `load_source_region(...)` / `_region_block(...)` / `_core_region_counts(...)` | 소스 사용 영역 로드(**현재 휴면**) / 영역 내 집계 / core-kind 어댑터 | ~487/521/547 |
| **[BIN 축 `269b39e`]** `parse_bin_request(raw)` / `_bin_axis_binding` / `_bins_unavailable` / `_bin_universe` / `_bin_cell_sets` / **`_bins_block(...)`** / `_merge_bins_over_slots` / `_lot_slots` | `bins=` 파라미터 파싱 / stage의 BIN 축 바인딩 / 불가 블록(`bin_axis_unavailable`) / 맵의 distinct BIN 열거(캡 200, ORDER BY로 재현성) / BIN별 좌표 집합 / **BIN별 total·fail·used·remaining 분해**(requested BIN은 전부 답을 받는다 — 부재는 `bin_absent`, 절대 0 아님) / `scope=lot` 슬롯 합산 / 로트→슬롯 전개(대장 조회, 캡 50) | ~629/651/668/678/713/740/824/903 |
| `_reshape_m1_summary(m1, stage_name, stage_cfg)` | M1 `bonding_plan.get_core_summary` 응답을 M2 공통 형태로 재성형 | ~937 |
| `_fetch_pairs(...)` / `_origin_map_id(...)` | 좌표쌍 페치(캡 적용) / origin map_id 조립 | ~973/989 |
| `_canonical_origin_meta(...)` / `_canonical_fail_set(...)` | origin-frame 원천의 canonical 맵 메타(첫 원천이 기준, 메타 없으면 None — 뒤로 넘어가지 않는다) / fail 좌표를 `map_overlay.resolve_map_transform`(~1059)으로 canonical 프레임에 사상 | ~995/1032 |
| `_collect_history(db, source_cfg, lot, slot)` | process_history 최근 N건 + result fail 경고 | ~1074 |
| **`_summarize_inline(db, stage_name, stage_cfg, lot, slot, region=None, bins=None)`** | **가용 엔진 정본(tape-kind)** — `origin_log` 연결 시 `remaining = total − \|fail_union ∪ used_set\|`, 미해석 시 M1식 감산 폴백. `by_core` 7키 + `by_core_origin` 마커 `"log"`\|`"area_map"`(`fail=None`으로 0 위장 금지). `bins` 요청 시 `_bins_block` 동봉 | ~1121 |
| `_bin_warnings(bins)` / `get_stage_source_summary(db, cfg, stage_name, lot, slot, bp_config=None, ref_table=None, map_key=None, bins=None)` / **`get_lot_bin_summary(db, cfg, stage_name, lot, bins=None)`** | BIN 블록 경고 승격 / **핸들러 진입점(scope=slot)** — 미선언 stage `KeyError`(→404) / **[`269b39e`] scope=lot 진입점** — 슬롯 전개 후 BIN 합산, **`chips` 없음**(로트 단위 헤드라인 잔여를 지어내지 않는다) | ~1492/1522/1575 |
| `_plan_store_binding(cfg, role, required)` | plan_store 역할 바인딩 (⚠️ `_num`은 삭제된 채 유지 — 저장 수치 파싱 없음) | ~1686 |
| **`_parse_bands(raw) -> (밴드[], 읽었는가, 거부된_원소_수)`** | **[레거시 `bands` 경로]** 3-튜플(호출부 `bands, readable, dropped = …` ~2684). **"못 읽음"과 "구간 없음"을 절대 합치지 않는다.** 객체가 아닌 원소는 거부하되 조용히 버리지 않는다(세어서 `layer_range_invalid reason:"not_a_band"`로 표면화). 크기 검사가 `json.loads`보다 **먼저** | ~1692 |
| `_band_seq(raw)` / `_band_materials(band)` / `_assign_band_seqs(bands)` | [레거시] 선언 `seq` 판독(정수값 float 허용 — `JSON.parse`가 먼저 접으므로 클라는 물리적으로 거부 불가) / 자재 목록 정규화(문자열 아님 거부) / 계획 내 `seq` 유일화 | ~1729/1761/1790 |
| `BAND_TO_OK/BLANK/INVALID` · **`STACK_MARKER`** · **`_int_state(raw)`** · `_band_to(band)` · **`_bin_of(raw)`** · `_prev_to(bands, i)` | 판정 어휘 3종(~1819–1821) + **[`2baf9ff` U9] `STACK_MARKER="marker"`(~1825 — STACK 전용 제4상태.** `_int_state`에서 절대 나오지 않고 **`stack_state`만 명시적 0을 승격**한다 — band `to`·BIN은 여전히 0 거부. 클라 `stackState`의 `'marker'` 미러) · **[`b35bc9f` 신설] 단일 정수 판독기** — `stack`과 `to`가 **같은 판독기**를 쓴다(클라 `bandToState` 미러. `'7.5'`→invalid — 컬럼 타입이 아니라 이것이 가독성을 결정) · `to` 판정(_int_state 위임) · BIN 라벨 판독 · prevTo 걷기(blank·invalid 동일 스킵, invalid는 보고) | ~1819–1825/1830/1872/1882/1901 |
| **[zone 코어 `b35bc9f`·`2baf9ff` — `doe_bands.js` 미러, 정본은 `contracts/doe_band_rules`]** `parse_material_list(raw)` / `_zone_tokens` / `stack_state(row)` / `mid_zone(row)` / `zone_layers(row, zone)` / `zone_demand(row, zone, painted)` / `parse_material_token(raw)` / **`material_pool_key(tok)`** / `validate_zone_plan(rows)` / `material_rollup_rows(rows, painted_of)` / `remaining_state(availability, used)` / **`bands_to_zones(bands)`** | mat_* JSON 배열 판독 / 행별 토큰 수집(비문자열 거부) / **`stack` 4상태(ok·blank·invalid·marker — 명시적 0만 marker, 음수는 invalid로 값 보존)** / MID 구간 유도(marker는 `{size:0, known:true}` — E행의 0층과 같은 "진짜 0") / 구역 층수(1H=1·TOP=1·MID=stack−이웃, **marker는 전 구역 `[]`**) / 구역 수요 = painted×layers / 토큰 → `{lot, slot?, bin?, scope}` 문법 / **풀 정체 키 — 분리자 조인이 아니라 튜플**(U+001F 조인이 디스크에서 분리자를 잃고 두 풀을 합산한 사고의 재발 방지) / **V1–V6 차단 규칙**(+W-DUP-MAT advisory — **marker 행은 V6 하나에만 답한다**: V6 블록 ~2225, V3 풀 스캔 제외 ~2306) / MAT×BIN 롤업 행(**marker 행은 부재** ~2363 — "사용 0" 행이 아니라 아예 없음) / 잔여 판정(신뢰 불가 가용은 잔여를 억제) / **레거시 band 계획 → zone 사상**(불가하면 `not_convertible`로 거부 — 손실 접기 금지) | ~1923/1949/1999/2023/2047/2070/2090/2143/2178/2345/2398/2422 |
| **`_material_identity_rule(cfg)` / `_split_material(material_id, rule)`** | 자재 ID → 소스 `(lot, slot)`. 규칙은 **`plan_store.material_identity` 선언으로만** 성립. 분해는 뒤에서부터(클라 `splitMaterialId`와 방향 동일, `map_overlay.build_key_filters`는 반대). **분리자가 없으면 거부** | ~2486/2505 |
| `_painted_values(db, ref_table, map_key, overlay_cfg)` | 대상 맵 자신의 셀 값 분포 group-by(`ORDER BY` — 절단 재현성). 반환 `({값: 셀수}, 상태, 절단여부)` — 세 번째 값이 [B2]의 핵심 | ~2538 |
| `validate_plan(db, cfg, ref_table, map_key, overlay_cfg=None)` | **핸들러 진입점** — **`plan_store.registry` 미구성은 `LookupError`(→404)**. 레지스트리 1회 조회(`ORDER BY value` ~2631 — 절단 재현성). **[zone] 행별로 `stack`/`mat_*`를 먼저 읽고**(내부 `_reg_get` ~2639, zone_row 조립 ~2657), zone이 비어 있으면 레거시 `bands`를 `bands_to_zones`로 사상(~2684 — `REGISTRY_LEGACY_ROLE` 미선언이면 그마저 없음). **`validate_zone_plan` 호출 ~2765가 V1–V6을 채점**하고 위반은 `zone_rule_violation`으로. marker 행은 수요 유도에서도 자연 소멸(`zone_layers`가 `[]` — 자재 해석·조회·수요 0, 주석 ~2881). **[B2] `painted_reliable`(~2739)이 유도 전체를 게이트.** `remaining_reliable=False`면 부족·fail 판정 전부 생략 + `availability_unreliable`만. 캡 절단은 `result_truncated`를 역할·캡별로 각각 발행. **`structural_refusal`(~2648, 세트 ~2666/2690/2722)이 `availability_checked`에 AND로 물린다**(~3041). 최종 `status`는 `ok`/`warnings`/**`unverified`**(~3063) 3값 — "검사 안 함"과 "이상 없음"을 같은 값으로 내지 않는다 | ~2588 |

---

## 6. 기타 서버 모듈 (한줄 요약)

라인 앵커 미수록 — 필요 시 해당 파일에서 Grep.

| 파일 | 책임 |
|---|---|
| `server/database/models.py` | ORM — 정적 + `DYNAMIC_TABLES` + 런타임 DDL(핫리로드 CREATE) — **함수 앵커는 [§5](#5-소형-서버-모듈)**. [P2] `class FileIngestionCheckpoint`(~112, `__tablename__="file_ingestion_checkpoints"` ~132) — `table_name/file_signature/filename/filepath/source_kind/total_rows/processed_rows/chunk_index/status/note/started_at/updated_at`, `Index("idx_fic_identity", table_name, file_signature, unique=True)`(~154) + `idx_fic_signature`. 준비 함수 `ensure_ingestion_checkpoint_table(engine)`(~469, information_schema 게이트 + `checkfirst` + `_runtime_ddl_lock`) |
| `server/audit_cache.py` | 최근 감사 로그 인메모리 캐시. [P2/이슈 #10] `add_logs_batch(logs_list, message_total_count=None)`(~109) — 인자 의미가 "이 메시지 1건이 나르는 **절단 전 실건수**"이고 `group["total_count"] += contribution`으로 **누적**한다(구 `override_total_count`는 SET 대입이라 멀티 target-table tx에서 마지막 메시지가 총계를 지웠다). 한 배치에 tx가 2개 이상 섞이면 귀속 불가로 `len(logs)` 폴백 + 1회 경고 |
| `server/database/schemas.py` | Pydantic — `GeneralUpdateItem/Batch` 등 API·배치 계약 |
| `server/database/database.py` | 엔진·SessionLocal·outbox 발화(`database_outbox` + NOTIFY) |
| `server/database/config_watcher.py` | table_config.json 변경 감시 → 동적 테이블 재구성. engine 분기(~44)에서 `create_missing_dynamic_tables` 선(先)호출 후 기존 sync(ALTER) — 직접 파일 편집 경로의 신규 테이블 CREATE(이슈 #7) |
| `server/graph_sync_worker.py` · `graph_materializer.py` · `ontology_config.py` | 온톨로지 그래프 트랙 — **함수 앵커는 [§5](#5-소형-서버-모듈)** |
| **`server/run_auto_update.py`** (700줄) | 스케줄 기반 사용자 스크립트 자동 실행. 매 틱 제어 파일(`auto_update_control.json`)을 읽어 disabled 수집기는 실행 스킵+`last_status="SKIPPED"`+next_run 전진(핫 반영, 재활성화 시 백로그 폭주 없음). run-now는 active 무관 실행. 함수 앵커: `class GenericScriptRunnerCollector`(~78)·**`execute()`(~105)**·`parse_script_comments`(~302)·`class MultiDiscoveryScheduler`(~331)·`discover_and_load_collectors`(~348)·`_write_status_file`(~458)·`run_collector_on_demand`(~490)·`execute_collector`(~504)·`check_and_run_schedules`(~531)·**`maybe_backup_configs()`(~574 — [`b35bc9f` C3] 틱마다 30분 게이트(`config_backup.CHECK_INTERVAL_SEC`)로 `config_backup.run_scheduled()` 호출. cron식이 아니라 `due()`가 디스크의 최신 스냅샷 나이로 판정 — 놓친 주가 다음 틱에 자가 치유. 백업 실패는 절대 수집기 실행을 멈추지 않는다)**·**`run()`(~605, 루프 안 `heartbeat.beat("scheduler")` ~636)**.<br>**[`512dca7` 재작성 — `execute()`의 실패 계약] "확인할 수 없었다"를 "이상 없다"로 보고하지 않는다.** 판정은 세 로컬(`out_data`·**`out_declared`**(~147)·**`exec_error`**(~148))의 조합이고 **함수 밖에 헬퍼가 없다** — 4상태: ① `out` 미정의 + 무예외 → stdout 수집기이며 폴백이 **정상 경로**(INFO) ② `out = None` **대입** → 스크립트가 줄 게 없다고 선언한 것이므로 **즉시 FAIL, stdout 재실행 없음**(~199, 이런 스크립트는 네트워크 페치의 에러 핸들러라 재실행하면 외부 호출만 반복한다) ③ `out`은 있는데 비었음 → 이번 주기에 수집할 게 없다, SUCCESS ④ 실행이 **raise** → ERROR + 트레이스백, 폴백은 시도하되 **그것도 비면 raise해서 FAIL**(~283). ①과 ④가 종전엔 같은 WARNING 한 줄로 뭉개져 **크래시해서 0행을 모은 실행이 깨끗한 성공으로 보고됐다**. ②가 ①과 구분 불가였던 것은 `.get("out")`이 "None 대입"과 "미정의"를 구분하지 못하기 때문이다.<br>**`SystemExit` 처리(~176)**: `sys.exit(0)`으로 끝나는 수집기는 정상 완료이므로 `out`을 존중한다. `SystemExit`는 `BaseException`이라 잡지 않으면 `execute_collector`·`check_and_run_schedules`(둘 다 `Exception`만 잡는다)를 **관통해 스케줄러 데몬을 종료시킨다**. 0/None이 아닌 코드는 `exec_error`로 강등 후 폴백 시도.<br>**`exec(code_content, script_ns)` — globals/locals에 같은 dict 하나(~170)**: 서로 다른 두 dict를 넘기면 클래스 바디 스코핑이 돼 모듈 레벨 `def`/`import`가 locals에만 바인딩되고 **함수 본문은 `LOAD_GLOBAL`이라 그것을 못 본다** → 다른 함수에서 호출된 헬퍼가 `NameError`로 죽고 수집기는 조용히 아무것도 못 모은다(모듈 레벨 호출은 `LOAD_NAME`이라 locals를 보므로 **일부 수집기만 고장 나 보였다**). 테스트: `tests/test_auto_update_script_exec.py`(21건 — `TestSingleNamespace`·`TestStdoutFallback`·`TestFailuresAreLoud`·`TestOutAssignedNone`·`TestOutFormattingFailure`·`TestSystemExitContainment`) |
| `server/event_constants.py` (51줄) | 프로세스 간 내부 이벤트(`/internal/events/*`) 공용 상수 — `MAX_NOTIFY_CREATED_LOGS=500`(~14, 발신측 created_logs 절단 상한: 워처 `directory_watcher:1427` · 체인 워커 `chain_ingestion_worker:474` · 수신 `main.py:3754/3802` 공유 — 2026-07-28 재측정, main.py 앵커만 +72 이동) · [P2] `MAX_AUDIT_VALUE_CHARS=4096`(~22)과 `truncate_audit_value(value, max_chars)`(~25 — 반환 `(값, 절단여부)`, str은 `…[truncated: 총 N자]` 마커, dict/list는 타입·길이 플레이스홀더)를 `crud.create_audit_log`가 소비 |
| `server/scripts/setup_ingestion_checkpoint.py` | [P2] `file_ingestion_checkpoints`를 **프로세스 재기동 없이** 미리 생성(멱등) — 직접 SQL 없이 `models.ensure_ingestion_checkpoint_table(engine)` 호출 후 컬럼·인덱스 출력 |
| `server/scripts/setup_transfer_plan_indexes.py` (68줄) | [M2] 전사 계획 엔진 진입 필터용 인덱스 **9종**(`INDEXES` 리스트 ~30) `CREATE INDEX IF NOT EXISTS`(테이블별 information_schema 존재 게이트) — `dt_log(tape_lot,tape_slot)`·`dt_log(core_lot,core_slot)`·`dt_map(lot,slot)`·**`map_split_registry(ref_table,map_key)`([M2.6 신설] `validate_plan`이 계획을 통째로 읽는 진입점. 행 수가 맵 수 × legend 값 수로 자란다)**·~~`map_doe(ref_table,map_key)`~~·~~`map_doe_source(ref_table,map_key)`~~(**둘 다 폐기 테이블용 — 물리 DROP과 함께 이 두 줄도 지운다**)·`map_source_region(...)`(휴면)·**`bonding_map(base)`**(Seq Scan 214ms → 0.345ms)·`sample_map(base)`. 뒤 둘은 단일 컬럼이라 "복합"이 아니다. M1 인덱스는 `setup_bonding_plan_indexes.py` 담당 |
| `server/utils/auto_update_control.py` | auto-update 수집기 active 제어 파일(`config/auto_update_control.json`, gitignored) 공용 IO — `read_disabled_scripts`(fail-open)/`set_script_active`(tmp+`os.replace` 원자적 쓰기)/`validate_script_key`(경로 탈출 차단)/`resolve_script_file`. 웹서버 toggle·스케줄러 공유 |
| `run_decoupled_app.py`(루트) / `server/run_watcher.py` / `run_chain_worker.py` / `run_graph_sync.py` / `run_auto_update.py` | 프로세스 런처(5-프로세스 토폴로지). **API 서버는 전용 런처 파일이 없다** — `run_decoupled_app.py`의 `main()`(~27)이 `server_cmd = [python_exe, "-m", "uvicorn", "main:app", "--host", api_host, "--port", api_port]`(~52)를 직접 띄우며, 포트는 **`ASSY_API_PORT`**(기본 `"8080"`, ~37), **[`269b39e` 신설] 호스트는 `ASSY_API_HOST`(기본 `"0.0.0.0"`, ~51)** — uvicorn 기본 loopback이 LAN 배포 가이드와 어긋나 있었다. 노출 방어는 bind 주소가 아니라 어드민 토큰 + 정적 경로 격리 검사임을 소스 주석이 명시한다. ~~`server/run_api.py`~~는 **존재하지 않는다**(2026-07-26 정정). **[`8117456`] sleep 루프가 `Supervisor`로 대체됐다** — `specs`(~64)는 `ChildSpec(..., heartbeat=…)` 5개(+ 비-server-only일 때 `restartable=False`인 데스크톱 셸), `supervisor.start_all()`(~117) 후 `supervisor.run()`(~125). `psutil_status`를 import(~11)해 손자 정리 무장 여부를 부팅 시 announce. **[`90e284f`] `ASSY_ADMIN_TOKEN`은 여기서 상속된다** — `process_supervisor`가 자식 env를 `os.environ.copy()`(~357)로 만들므로 런처 프로세스에 한 번 세팅하면 5자식 전부가 `admin_auth.internal_event_headers()`로 토큰을 실어 보낼 수 있다([§1.6](#16-serveradmin_authpy--어드민내부-토큰-게이트-90e284f-신설)). run_watcher(312줄): `post_event`(~51, **[`90e284f`] `headers=admin_auth.internal_event_headers()` ~60**) · `trigger_ws_refresh`(~66) · `trigger_ws_file_processed`(~88) · `trigger_ws_progress`(~99) · `trigger_ws_ingestion_state`(~118 — [P1] 파일명 정규화 후 `/internal/events/ingestion-state` push) · 재처리 폴러 `poll_pending_retries`(~151, 루프 안 `heartbeat.beat("watcher")` **~167**)는 `refresh_dynamic_models(engine)` 보충(이슈 #7) + `resolve_workspace_root` 역조회(별칭 대응) + 재처리를 `get_workspace_serial_lock`으로 감쌈([P1 QA F3] heavy와 순서 계약 편입) |
| `server/utils/physical_wafer_engine.py` · `coordinate_transformer.py` | 웨이퍼 물리 좌표 엔진(맵 에디터 서버측) |
| `server/utils/logger.py` (145줄) | 프로세스별 로거 — `class ColoredProcessFormatter`(~16) · `get_process_logger(process_name, log_filename)`(~77)의 파일 핸들러가 **`paths.log_path(log_filename)`**(~125)를 쓴다. 격리 프로세스가 사용자의 라이브 로그에 append하지 않는 근거 |
| `server/mappers/*` (gitignored) | 사용자 커스텀 체인 맵퍼 — **전수 Grep 시 반드시 포함**. ⚠️ **`paths.py`가 의도적으로 다루지 않는 트리**(데이터가 아니라 코드 — `sys.path`의 패키지로 해석) |
| `server/config/*.json` (gitignored) | table_config·chain_rules·enrichment_rules·ontology_mapping(v2 — `.sample`은 tracked) 등 사용자 설정. 실값을 이 문서에 옮겨 적지 말 것 — 구조만 기술한다 |

### 6-1. 설치·개발환경 스크립트 (`8e80fcc`·`4ba13ae`·`47c20f3` 신설)

| 파일 | 책임 |
|---|---|
| `server/scripts/install_product_tables.py` (661줄) | **[제품 소유 테이블 설치기]** `product_tables.PRODUCT_TABLES`를 사이트의 라이브 `table_config.json`에 설치한다. 대상이 **gitignored 사용자 자산**이라 규칙 전부가 그 파일을 지키기 위해 존재한다 — 사이트 소유 엔트리는 **재직렬화하지 않고 바이트 단위 스플라이스**로만 편집해(키 순서·들여쓰기·개행까지 보존) 스크립트가 추가하지 않은 것은 바이트 동일하게 나온다. 부재→추가 / 동일→**무쓰기** / 다름→drift 보고 후 방치(`--overwrite-drift` 필요). **드라이런이 기본**이고 쓰기는 `--apply`, 쓰기 전 타임스탬프 백업, 쓴 뒤 재스캔해 미변경 멤버를 원본과 바이트 비교하고 어긋나면 **백업 복원**. DDL·DB 접속·재기동은 하지 않는다(어느 리로드 경로가 적용되는지 안내만 출력). 종료코드 `0` 할 일 없음 / `1` 조치 필요 / `2` 오류. 핵심 함수: `scan_top_level_members`(~141) `detect_style`(~197) `apply_edits`(~221) `diff_declaration`(~258) **`evaluate(parsed, definitions=None, strict=False)`(~295)** **`build_edits(text, scan, statuses, overwrite_drift, definitions=None)`(~330)** `verify_untouched`(~521) **`run(path, apply_mode=False, overwrite_drift=False, out=None, strict=False)`(~544)** `main(argv=None)`(~617). `--sample --apply`는 tracked 템플릿 `config/table_config.json.sample`을 **생성**한다.<br>**[`0f8d35f` 신설] `--sync-comments`(~637)** — `__comment` 차이도 drift로 취급한다(**실행하려면 `--overwrite-drift`가 함께 필요**). 기본 off인 이유는 주석이 운영자가 손댈 수 있는 유일한 부분이라서이고, 그럼에도 스위치가 필요한 이유는 **낡은 주석이 능동적으로 오도**하기 때문이다(예: 폐기된 바인딩을 여전히 지목). 구현상 `strict = args.sample or args.sync_comments`(~657)이고 `strict`는 정확히 "주석 포함 엔트리 전체 비교"를 뜻한다 — `.sample`이 늘 요구하던 그 판정이다 |
| **`server/scripts/backup_config.py`** (162줄, `b35bc9f` 신설) | **[config 백업 CLI]** `config_backup.py`([§5](#5-소형-서버-모듈))의 운영자 표면 — 서브커맨드 **4종**: `list`(~40, 전 스냅샷 오래된 순) · `check`(~57, 최신 스냅샷 신선도 — 낡았으면 **exit 1**, 모니터링 훅용) · `snapshot`(~73, 즉시 1회) · **`restore`(~90, 스냅샷을 라이브 config 위로 복원 — 덮기 전 현재본을 자동 스냅샷)**. `main()`(~139) |
| **`server/scripts/list_undeclared_tables.py`** (301줄, `b35bc9f` 신설) | **[롤백 진단 — 읽기 전용]** `table_config.json`이 더는 선언하지 않는 **물리 스키마 잔재**를 보고한다. 선언은 one-way door다 — config 워처는 CREATE/ALTER만 하고 **아무것도 DROP하지 않으므로**, 선언을 되돌리면 물리 객체가 어디에도 선언되지 않은 채 남는다(실사례: 폐기 모델의 `map_band_registry`가 빈 테이블로 잔존). 보고 3종: `UNDECLARED TABLE`(빈 것=되돌린 선언 / 채워진 것=레거시 — 함부로 DROP 금지) · `UNDECLARED COLUMN` · `DECLARED BUT MISSING`. DROP문은 **출력만** 하고 실행하지 않는다. `run(db_url, schema, out)`(~172)·`main`(~283). 테스트: `tests/test_undeclared_schema_report.py`(168줄) |
| `server/scripts/dev_env/devenv.py` (372줄) | **[격리 개발환경 CLI]** `DEV_ROOT=<repo>/dev_env`, `isolated_env()`(~71)가 `ASSY_DATA_ROOT`+격리 DB URL을 조립한다. 포트는 `ASSY_DEV_API_PORT`(기본 8081)·`ASSY_DEV_GRAPH_PORT`(기본 8091). 동사: `cmd_bootstrap`(~108, config/워크스페이스 복제 — `SKIP_CONTENT_DIRS={raws,archives,err}`는 구조만 뜨고 내용은 안 뜬다) `cmd_snapshot`(~145) `cmd_up`/`cmd_down`(~217/249) **`cmd_watcher_up`/`cmd_watcher_down`(~256/311 — 워처만 별도 기동)** `cmd_status`(~316) `cmd_env`(~335) |
| `server/scripts/dev_env/iso_watcher.py` (308줄) | **[격리 게이트]** 워처를 띄우기 **전에** 격리를 단언하고, 어긋나면 기동을 거부한다(`EXIT_REFUSED=9`, `REFUSED_MARKER` ~51). `check_static_isolation(...)`(~94, data_root·config·workspace 경로가 `server/` 밖인지) + `check_live_isolation(live_database, engine_url)`(~146, 실제 접속된 DB 이름이 `PRODUCTION_DB_NAMES={"assy_manager"}` ~55에 걸리는지 · 포트가 `PRODUCTION_API_PORTS={"8080","8090"}` ~58인지). 통과 시에만 `GATE_PASSED_MARKER`(~50)를 찍고 `_start_watcher`(~250) |
| `server/scripts/dev_env/snapshot_db.py` (420줄) | **[DB 스냅샷]** 라이브 → QA DB 복제. `open_source_readonly(url)`(~65)로 **소스는 읽기 전용 세션**, `CHUNK=1000`(~42) 라운드트립(10M행 규율 — 테이블 전량 로드 금지), `EMPTY_TABLES={"database_outbox"}`(~48)는 스키마만, `ROW_SCOPED`(~53)는 행 한정 복제. `build_target_schema`(~153) `copy_rows`(~181) `fix_sequences`(~217) `run`(~242) |
| `server/scripts/dev_env/manifest.py` (188줄) | **[변경 매니페스트]** 드릴 전후 파일·DB 상태를 떠서 비교 — `capture_files(root, label)`(~41, `CHURN_DIR_NAMES={raws,archives,err}` ~30 제외) `capture_db(db_url)`(~68) `cmd_capture`(~93) `cmd_diff`(~115) |

### 6-2. 교차 구현 계약 (`contracts/`)

**`0f8d35f` 신설 — 루트 최상위 디렉터리, 현재 3계약.** `server/`도 `client2/`도 아닌 곳에 있는 이유가 곧 정의다: **어느 한쪽의 테스트 자산이 아니라 양쪽이 각각 대조당하는 명세**다. 서버와 클라를 서로 대조하면 둘 다 틀렸을 때 통과한다. 하니스 공통 규율: 대상 함수가 module-private이므로 소스 텍스트에서 함수 선언을 잘라내 `node:vm` 샌드박스에서 평가하고, **추출 실패는 exit 2로 시끄럽게 죽는다**(함수를 못 찾고도 조용히 통과하는 하니스의 초록불은 "양쪽이 일치한다"는 증거로 인용되기 때문). 종료코드 `0` 일치 / `1` divergence / `2` 하니스 자체 실패.

| 파일 | 책임 |
|---|---|
| `contracts/band_arithmetic/vectors.json` (243줄) | **[레거시 `bands` 산술의 정본 명세.]** 폐기 모델이지만 `map_split_registry.bands`에 실계획이 남아 있고 서버가 여전히 이 규칙으로 읽는다(`bands_to_zones` 마이그레이션 경로 포함). 벡터 **37건 / 5그룹**: `to_cases`(7) `sequence_cases`(7) `normalization_cases`(5) `materials_cases`(7) `material_split_cases`(11). **의도적으로 좁힌 계약이며 JS 강제변환의 이식이 아니다.** `NaN`/`Infinity`는 JSON이 표현하지 못해 저장 컬럼으로 도달 불가라 일부러 빠져 있다. 소비자 둘: **pytest** `server/tests/test_transfer_plan.py` · **node 하니스**(아래). ⚠️ `material_split_cases.no_separator`에 **`$superseded` 마커**가 붙었다(`269b39e`) — `splitMaterialId`에는 여전히 맞지만 후속 토큰 문법(doe_band_rules)에서는 맨 식별자가 로트 전체다. **`splitMaterialId`를 지우는 같은 커밋에서 지워야 한다** |
| `contracts/band_arithmetic/client_harness.mjs` (288줄) | **클라 측 대조기 — 읽기 전용.** **[`b35bc9f` 재편]** 추출 대상 **4종**: `transfer_plan.js`의 `bandToState`·`prevTo`·`splitMaterialId` + `map_editor.js`의 `normalizeBands`. **은퇴 4종(`bandTo`·`bandLayers`·`bandTotal`·`bandShare`)은 이제 부재를 능동 단언한다**(`RETIRED_CLIENT_FNS` ~75 — transfer_plan.js에 되살아나면 exit 2. 층 산술의 두 번째 구현이 곧 이 계약이 막는 divergence다 — 그 커버리지는 `doe_band_rules`의 `demand_cases`로 이전됐다). 실행: `node contracts/band_arithmetic/client_harness.mjs [--json]` |
| **`contracts/doe_band_rules/vectors.json`** (563줄, `269b39e` 신설 · `b35bc9f` 확장 · **`2baf9ff` v3 = marker 축**) | **[ZONE 모델의 정본 명세, `"version": 3`.]** **131건 / 11그룹**: `stack_cases`(13 — 0/`'0'`→`marker` 포함) `zone_extent_cases`(8) `plan_cases`(17 — **차단 규칙 V1–V6**: bare marker는 SILENT, marker+구역 자재는 V6) `material_token_cases`(21 — `lot[_slot][:BIN]` 문법) `demand_cases`(9 — ceil을 round·floor 양쪽과 대조해 고정) `rollup_cases`(6 — marker 부재 포함) `remaining_cases`(7) `tsv_cases`(15) `paste_cases`(15) **`roundtrip_cases`(9 — Excel 왕복: TSV→모델→TSV 동일, marker는 canonical `'0'` export)** `legacy_band_cases`(11 — `bands_to_zones` 사상·`not_convertible` 거부). 소비자 둘: **pytest** `server/tests/test_doe_zone_model.py` · **node 하니스**(아래) |
| **`contracts/doe_band_rules/client_harness.mjs`** (449줄) | 클라 zone 모델 대조기 — `doe_bands.js`에서 잘라낸 함수들 + `transfer_plan.js`의 `bandToState`·`prevTo`(단일 정수 판독기·단일 레거시 걷기를 **재타이핑하지 않고 추출** — 사본 하니스는 앱과 어긋나도 통과한다). V1–V6, zone 기하, 토큰 문법, 수요 산술, **Excel 왕복**을 채점. **[`2baf9ff`] fixture 불활성 가드**(~229–231): `plan_cases`에 bare-marker SILENT 케이스와 V6 모순 케이스가 **둘 다** 없으면 exit 2 — 한쪽만 있으면 "0은 여전히 invalid" 또는 "V6 불발" 회귀가 전 케이스를 통과한다 |
| **`contracts/legend_map_scope/client_harness.mjs`** (645줄, `269b39e` 신설) | **[legend map-key 스코프 계약 — 벡터 파일 없음, 하니스 단독.]** 단언: 맵이 열려 있을 때 화면의 legend와 **특히 그것으로 지은 `replace_map` 페이로드**는 이 맵이 보증하는 값만 담는다. 기원 결함: 테이블 전체 읽기(map_key 필터 없음, 값 dedup)로 legend를 시드해 **남의 맵 값이 이 맵의 계획으로 저장**됐다(프로덕션에서 `elle` 1값이 bonding_map 4키로 전파). **시드는 삭제됐다**(2026-07-28) — 패널 오픈은 이 맵의 registry 행 \| 빈 DOE 1행(`vocab: true` 플레이스홀더) 두 갈래뿐. 하니스는 `map_editor.js`에서 const(`SPLIT_KEY_SEP`·`FP_UNIT`·`FP_ROW`·`SPLIT_REGISTRY_TABLE`·`REGISTRY_SCOPES`·`ZONE_COLUMNS`·`LEGEND_PAYLOAD_COLUMNS`)와 쓰기 경로 함수들을 추출해 **실제 페이로드 조립을 끝까지 돌려** 검사한다 |

> **왜 이 계약들이 존재하는가 (실제 사고)**: ① 같은 JSON에서 클라와 서버가 다른 숫자를 유도했다 — `Number("  ")`는 0이라 `prevTo` 걷기를 멈췄고 `float("  ")`는 예외라 건너뛰어서, `[10, "  ", 20]`이 화면에서 20층·서버에서 10층이 됐다. ② 클라 `normalizeBands`가 자체 `Number()`를 돌려 `"0x10"`을 16으로 고쳐 저장했다(오류가 이미 데이터가 돼 화면에 안 보였다). ③ zone 모델에서도 같은 계열이 재발했다 — U+001F로 조인한 자재 풀 키가 디스크에서 분리자를 잃어 `MID1_12:3`과 `MID11_2:3`이 한 롤업 행으로 합산됐다(230 assertion이 아니라 **뮤테이션 테스트**가 잡았다).

---

## 7. `client2/src/` — 웹 클라이언트

Vite + Vanilla ESM + AG-Grid. 멀티페이지 **6엔트리**(index/admin/map_editor/enrichment/graph/trace). 상태는 `state.js` 싱글턴(리액티브 아님 — 변조 후 명시적 리프레셔 호출).

### `state.js` (~49줄) — 전역 싱글턴
- `state` 객체: gridApi, currentTable/Columns/Types, 비즈니스키(`currentBusinessKey`/`currentCompositeKeySources`), ws, 셀 선택(`selectedCell`/`selectedCellsMap`/드래그), 이력 탭 데이터, 페이징(`currentSkip`/`pageCache`/`viewMode`), 트랜잭션 모드(`txModeActive`/`pendingTxEdits`), `isDesktop`.
- export: `updateVisibleColIndexMap()` (~37).

### `main.js` (~1,784줄) — index 페이지 오케스트레이터
- 진입 `init()`(~66, `initTraceEntry()` 호출 포함) → `setupEventListeners()`(~101, 거대 — 툴바·모달·키보드 전체 배선), `setupDragAndDrop()`(~1013).
- 셀 범위 `getSelectedCells()`(~1098), 소스 모달 `openSourcesModal/refreshSourcesList`(~1145/1170).
- 스마트 페이스트 `smartPasteViaIngestion()`(~1418) + `showClipboardTypeModal`(~1511).
- 트랜잭션 모드 커밋/롤백 `applyPendingTxEdits()`/`discardPendingTxEdits()`(~1685/1758).
- export 없음(엔트리) — 다른 모듈을 소비만 한다.
- ⛔ **[`90e284f`] 키보드 배선에서 Ctrl+C 분기가 삭제됐다 — 되돌리지 마라**(~421에 그 자리를 지키는 주석이 있다). 복사는 `clipboard.js`의 `copy` 리스너(~560)가 `e.clipboardData`로 처리하므로 **`navigator.clipboard`가 없는 비보안 컨텍스트(평문 HTTP)에서도 동작한다.** 구 분기는 `navigator.clipboard.writeText`를 썼고 사내 평문 HTTP 배포에서는 그것이 `undefined`다 — 즉 삭제된 코드가 하던 일은 **작동하는 경로를 가로채 아무 일도 안 하는 것**이었다. `getRangeSelectedTSV` import도 함께 빠졌다(이 파일에서 더는 안 쓴다 — 여전히 `clipboard.js`가 export한다).

### `api.js` (~422줄) — REST 소비 계층 (경계 계약의 클라이언트측)
- export: `checkServerHealth`(~11) `loadTables`(~28) `switchTable`(~56, 말미에 `refreshTraceEntry()` fire-and-forget) `loadSchema`(~96) `fetchData(resetSkip)`(~124, 메인 조회+세션가드) `handleCellEdit(event)`(~217, 셀 편집→PUT updates) `addRows`(~364) `deleteSelectedRows`(~383).
- 소비 API: `/tables*`, `/tables/{t}/data`, `/schema`, PUT `/data/updates`, POST `rows`, `batch_delete`.

### `grid.js` (~526줄) — AG-Grid 구성
- export: `updateGridSortState`(~17) `updateLoadedCount`(~42) `updateViewModeUI`(~66) `updatePaginationUI`(~74) **`ensureCellObject(dataObj, colId)`**(~94, 셀 형태 `{value,is_overwrite,priority_source}` 정규화 — 셀 계약의 단일 관문) `buildColumnDefs`(~112) `renderGrid(initialRows)`(~254).

### `websocket.js` (~255줄) — 실시간 수신
- export: `initWebSocket`(~11, 재접속 백오프) `handleWebSocketMessage(msg)`(~72).
- 소비 이벤트: `file_ingestion_progress`(~73) `file_ingestion_completed`(~84) `batch_row_create`(~131) `batch_row_upsert`(~147) `batch_row_delete`(~229) `batch_refresh_required`(~244) → 델타 반영(`applyTransaction`)·페이지캐시 갱신.

### `ui.js` (~408줄) — 그리드 밖 UI 갱신
- export: `setupBeforeUnloadWarning`(~8) `updateSelectedCellUI`(~18) `updateTxModeUI`(~33) `setTransactionFilter`(~79) `applyValueToSelectedRange(newValue)`(~106, 범위 일괄 적용→배치 PUT) `updatePageCacheOnUpsert`(~260) `updateEnrichmentBadge`(~331) `notifyEnrichmentTableEvent`(~381) `updatePageCacheOnDelete`(~391).

### `clipboard.js` (~800줄) — 엑셀형 범위 선택/복붙
- export: `isCellInRange`(~13) `refreshRange`(~34) `refreshSelectedRangeDiff`(~62) `clearRangeSelection`(~97) `commitDragSelection`(~149) `getRangeSelectedTSV`(~177) `setupClipboardHandlers`(~289, copy/paste 이벤트 본체) `clearSelectedCells`(~629).
- **[`b35bc9f`]** TSV 인용/파싱은 자체 구현 대신 **`tsv.js`의 `parseTsv`/`serializeTsv`** import(~11).

### `timeline.js` (~718줄) — 이력 타임라인 + 내비게이션
- export: `loadHistory`(~9) DOM 빌더 `createTimelineItemDom`/`createGlobalTimelineItemDom`(~50/103) 증분 렌더 `renderTimeline*`(~271–346) `renderSubDetails`(~362) `appendHistoryLocally`(~445) 로그→셀 점프 `navigateToLog`(~507)+`navigatorStep2/3`/`navigatorFinalScroll`/`releaseNavigationGuard`(~566–709).
- 소비 API: `/audit_logs/recent`, `/audit_logs/transaction/{tx}`.

### `map_editor.js` (~5,505줄) — 웨이퍼 맵 에디터 (단일 페이지 스크립트, export 없음 — 단 `import`는 있다: `transfer_plan.js`의 `bandToState`, **`doe_bands.js`의 `parseMaterialList`·`bandsToZones`**)
- 좌표 변환 코어: `getPhysicalCoords`(~1278) `getCellFromPhysicalCoords`(~1328) `getCellFromVisualCoords`(~1368) `getVisualCoords`(~1437) `getTransformedPhysicalConfig`(~1452) `getWaferBoundingBox`(~1385) `getScreenShift`(~1487) `isCellInsideWaferFast`/`isCellInsideWafer`(~1513/1551) — 회전/면반전 불변식은 [MAP_EDITOR_SPEC](../spec/MAP_EDITOR_SPEC.md).
  - **[7d931dc] 프레임 창(frame window)** — `physFrameOverride`(~1251) + `physNum`(~1254)/`gridDimNum`(~1263)/`withPhysFrame(frame, fn)`(~1272). 변환 함수가 규격을 DOM에서 읽는 지점을 잠깐 갈아끼우는 장치로, **주입 지점은 `getTransformedPhysicalConfig`·`getWaferBoundingBox` 두 곳뿐**이다. `withPhysFrame`은 **동기 전용**(내부 `await` 금지 — `try/finally` 복원이 새면 조용한 오답). 기존 `parseFloat(v) || dflt` 규약(0 → 기본값) 보존.
- 캔버스 렌더: `renderGridCanvas`(~1903, 본체 — 오버레이 마커 호출 ~2065) `scheduleRenderGridCanvas`(~1866) `fitGridToWorkspace`(~1888) `updateNotchPosition`(~2247).
- 데이터 IO(REST — WS 아님): `loadExistingMap(opts={})`(~3363 — **[`280ebf0`] `{quiet}` 옵션**은 last-open 부트 복원용. **[`6db517d` H1] 로드 경로는 legend 채택 시점에 초안을 저장하지 않는다** — 구 `saveLegendToStorage()` 즉시 호출이 방금 로드한 **서버 상태**를 초안 위에 덮어써 리로드마다 칠한 셀 초안을 전멸시켰다(사유 주석 ~3663–3666). 저장은 초안 우선순위 판정이 끝난 뒤 registry 블록 안에서 **1회**만. 복구된 초안은 여전히 미저장 편집이므로 `legendDirty = true` ~3713) `pushMapData`(~3809, 저장 본체 — **[`b35bc9f`] legend/DOE 저장의 유일한 트리거이기도 하다**: 내부에서 `saveLegendToServer` 호출 ~4053. **[`6db517d` H2] 대비 관문(contrast guard) ~3924–3941**: 직렬화된 페이로드의 비어 있지 않은 셀 수 < 화면의 비어 있지 않은 셀 수면 **confirm 이전에 적재 거부** — `replace_map`은 맵 행 전체를 지우고 다시 쓰므로 프레임이 덮지 못한 셀은 누락이 아니라 **삭제**된다(QA 실측 1293→379, 메타 없는 맵 + 기본 프레임). 데이터 보호 관문 3형제의 셋째(zone 컬럼 부재·레거시 판독 불가와 같은 패턴 — 직렬화하지 않은 것을 지우는 쓰기를 막는다). 계산은 루프와 같은 공백 술어라 사용자가 지운 셀은 양쪽에서 상쇄) `fetchGridMetaFor(table, mapId)`(~3330) 프리셋 `fetchAndRenderPresets`/`saveCustomPreset`/`deleteCustomPreset`(~1608/1714/1764) + `applyPresetObject`(~1664, `loadSelectedPreset` ~1697에서 추출한 공용 함수).
  - `fetchGridMetaFor`는 **404/405만 "규격 미등록"(null)**으로 읽고 그 외 실패는 **throw**한다(`[M2 fix]` — 종전엔 모든 실패가 null이라 오버레이가 조용히 identity로 폴백했다). `loadExistingMap`의 셀 레벨 `grid_metadata` 폴백은 **폐기 스킴**이며 어떤 맵 테이블도 스키마에 그 컬럼을 노출하지 않아 라이브에서 사문이다.
- 레전드/브러시: `renderLegendTable`(~2971) `selectBrush`(~3159 — **[`280ebf0` 입력 랙 수정] 선택은 DOE 리스트 재구성·전 그리드 카운트 스캔을 유발하지 않는다**(의도 주석 ~3173): mousedown이 innerHTML 재구성을 유발해 커서 밑 input이 분리되던 결함) + `saveLegendToStorage`(~2322). `getCurrentMapKey`(~2532)는 **로드된 맵이 아니라 현재 메타 입력 필드**를 읽는다(오버레이 관문 F2의 근원). 서버 레지스트리 IO는 아래 전용 블록 참조.
- **Split Registry = DOE의 유일한 기록자**(~176–470 선언 · ~2564–2967 IO). **[`269b39e`+`b35bc9f` ZONE 모델]** legend 행 = DOE 1건 = `{value, desc, color, knobs, stack, mat_1h[], mat_mid[], mat_top[]}` — zone 계약 정본 주석 ~210–230(`bands`는 **폐기됐지만 읽기 전용으로 생존**: 서버에 band 계획이 남아 있고 저장이 `replace_map`이라, 안 읽으면 다음 키 입력이 그 계획을 빈 집합으로 지운다). `SPLIT_REGISTRY_TABLE='map_split_registry'`(~179) · **`SPLIT_KEY_SEP='\|'`(~182)** · `buildSplitKey`(~207).
  - 정규화 순수 함수: `parseJsonCol`(~231) **`normalizeBands`(~237 — 하니스 검증 대상, 레거시 읽기 전용. `to` 해석은 `transfer_plan.js`의 `bandToState` **하나만** 쓴다. 읽을 수 없는 값은 **원문 그대로 보존**)** `normalizeKnobs`(~270) `knobsToObject`(~282) `serializeKnobs`(~291) `normalizeLegendItem`(~322 — zone 필드 포함) **`cloneLegend`(~343 — 깊은 복사. 배열 필드를 얕게 넘기면 프레임 스냅샷과 화면이 같은 배열을 공유한다)**. (~~`serializeBands`~~는 band 편집기와 함께 삭제)
  - 동시성 장치: **`legendReplaceScope`(~195 — `{table, mapKey, fingerprint}`. `replace_map` **권한**이자 동시성 검사의 **기준선**)** · **`legendVocabularySeed`(~199 — [`269b39e` 신설] 플레이스홀더 시드 시점의 행 서명 Map. `reconcileVocabClaims`가 "사용자가 이 행을 바꿨다"를 **유도**하게 한다)** · **`legendConflict`(~203 — 다른 세션이 바꿨다. 리로드 전까지 그 맵의 registry 쓰기 전량 차단. upsert 강등 금지)** · `legendSaveState`(~205). 지문 계산 `LEGEND_PAYLOAD_COLUMNS`(~368)/`canonRegistryRow`(~389)/`FP_UNIT`·`FP_ROW`(~396–397)/`registryFingerprint`(~398) — **`contracts/legend_map_scope` 하니스가 이 상수·함수들을 이름으로 추출**한다.
  - 페이로드 순수 함수: **`buildLegendRegistryUpdates(refTable, mapKey, legendArr, user, nowStr)`(~413)** / **`parseLegendRegistryRows(result, dedupeByValue)`(~462)**.
  - 서버 IO: `REGISTRY_SCOPES=['map']`(~2564 — **테이블 전체 어휘 시드는 삭제됐다**, `269b39e` 결함의 원인) `fetchRegistryRows`(~2565, `limit=500` — **부분 읽기는 읽은 게 아니라 throw**) `readRegistryScope`(~2590) `legendRowSignature`(~2601) `reconcileVocabClaims`(~2622) `applyRegistryRowsToLegend`(~2647) **`saveLegendToServer(mapKeyOverride)`(~2726 — 쓰기 단위가 **한 맵의 값 전체 집합**이라 `replace_map:true`. 지운 값·구간·자재는 집합에 없다는 것만으로 서버에서 삭제된다. 쓰기 **전에** ① `probeZoneColumns` 게이트(~2844, `ZONE_COLUMNS` ~2843 — 물리 zone 컬럼이 없으면 **거부**: crud가 페이로드에서 zone을 떨어뜨린 채 replace_map이 나가면 계획 전체가 층 구조 없이 대체된다) ② 재조회+지문 비교(불일치면 `legendConflict`로 거부). **참조는 정확히 2곳 — 정의 + `pushMapData`(~4053)**)** `LEGEND_SAVE_MESSAGE`(~2872) `applyLegendSaveResult`(~2885) `getPlanSaveState`(~2912) `persistLegend`(~2925) **`scheduleCellDraft`(~2946 — 400ms 디바운스로 `saveDoeDraft`+`notifyLegendChanged`. 페인팅·드래그·fill·paste·legend 개명까지 **호출 10곳**(1018/2230/3136/3267/3317/3803/4239/4266/4288/5379 — 2026-07-28 재계수) — 모든 편집 경로가 새로고침을 견딘다)** `renderLegendMetaOnly`(~2954). ⚠️ **~~`scheduleLegendServerSave`~~(자동 저장)는 삭제** — 묘비 주석 ~2899, 서버 쓰기는 ⚡ Push 하나뿐([§0](#0-묘비-목록--소스에-존재하지-않는-이름)).
  - 로컬 초안(**[`b35bc9f`] 셀까지 나른다**): `seedEmptyDoe`(~2308 — 행 없는 맵의 빈 DOE 1행, `vocab:true`) `doeDraftKey`(~2330, `map_doe_draft::<table>::<mapKey>`) `DRAFT_VERSION=3`(~2352) `cellsDigest`(~2356, FNV-1a) `draftBase`(~2368 — 열었을 때 서버가 갖고 있던 것의 지문) **`saveDoeDraft`(~2370 — DOE(zone·knob 있는 행만)+`cells`+기반 지문을 함께 저장 — 초안 지문 우선순위의 근거)** `readDoeDraft`(~2407, v3 미만은 "기반 미상"으로 수용) `clearDoeDraft`(~2420) `applyDoeDraftRecord`(~2479 — **우선순위 판정은 호출부**, 이 함수는 적용만. **[`6db517d` H1] "applied"의 의미가 "내용이 있었다"→"화면을 바꿨다"로 교체**됐다(~2482–2508, before/after JSON 비교): 초안은 registry 저장 직후에도 재저장되므로 Push+새로고침 뒤 초안 = 서버 행인데, 그것을 "복구"로 보고하면 계획 있는 맵을 리로드할 때마다 유령 미저장 칩·토스트가 부활한다) `applyDraftCells`(~2516).
  - **[`280ebf0`] last-open 복원**: `LAST_OPEN_KEY='map_editor_last_open'`(~2428) `recordLastOpenMap`(~2430 — **depth-0 정체성만**: 자재 프레임은 여정이지 집이 아니다. 기록 지점은 로드 성공 ~3757·Push 성공 ~4038) `restoreLastOpenMap`(~2449 — 부트 1회 호출 ~609. **수동 경로 그대로**(switchTable+메타 입력+`loadExistingMap({quiet})`)를 걷는다 — 초안 우선순위·missing-key 동작이 별도 복원 경로가 아니라 같은 코드. 테이블이 사라졌으면 조용히 초기 화면).
  - 패널 관문(컨트롤러가 부르는 쓰기 3종): `addLegendRowForPanel`(~3194) **`updateLegendRowForPanel(value, patch)`(~3207 — DOE 변조의 유일 관문. 배열 필드는 **새 배열로 통째 교체**, 제자리 수정 금지)** `deleteLegendRowForPanel`(~3252). + `fetchMapKeyColumns`(~3273) `probeMapExists`(~3291 — **존재를 추측하지 않는다**) `remapGridValues`(~3308).
- 편집 도구: `fillGrid`(~3779) `getEdgeClassification`(~4093) `selectEdgeCells`(~4173) `autoPaintE1E2`(~4200) `copyGridToExcel`(~4291).
- 프레임 스택: `snapshotEditorState`(~4463) `restoreEditorState`(~4519) `openMapFrame`(~4743 — `allowEmpty`로 빈 그리드 오픈 허용, 키는 Push에서 생성) `popMapFrame`(~4797). **복원 대상에 `overlayLayers`·캔버스 스크롤이 포함된다**(~4455 주석).
- **[M2] 페인트 잠금**(~36–160, 서버 선언 소비 — 구 `'F'` 하드코딩 대체): `NO_PAINT_LOCK`(~41) `isLockedValue`(~45) `isOverlayLocked`(~55) **`isProtectedFCell`(~67 — 편집 불가 판정의 단일 관문, 전 편집 경로가 여기로 수렴)** `applyPaintLockConfig`(~72) `fetchPaintRules`(~96, GET `/api/maps/paint-rules`) `updatePaintLockIndicator`(~130) `recomputeLockedCells`(~147). 404/405만 "선언 없음"(해제)이고 네트워크·5xx는 **직전 잠금 유지** + `source:'stale'` + 툴바 칩. ⚠️ **[QA C4 미해소] 콜드 스타트는 여전히 fail-open** — "직전 값"이 페이지 로드 직후엔 기본값 `NO_PAINT_LOCK{enabled:false}`라 첫 조회가 실패하면 강제 지점이 열린 채 시작한다(칩은 뜨므로 **조용한** fail-open은 아님). 테이블 전환 시 실패하면 **이전 테이블의 잠금 값**을 새 테이블에 계속 적용한다(fail-closed 방향이라 안전하나 의미상 부정확).
- **[7d931dc] 오버레이 레이어**(~4840–5505) — **변환은 클라 단일 구현**이다. 계약은 [MAP_EDITOR_SPEC §5](../spec/MAP_EDITOR_SPEC.md). ⚠️ **[`280ebf0`] `.overlay-box`/`.ov-*` CSS는 `b35bc9f`의 transfer_plan.css 재작성이 떨어뜨렸다가 원문 그대로 복원**됐다(마크업은 계속 그 클래스를 쓰고 있었다):
  - 상태 `OVERLAY_COLORS`(~4840) / `overlayLayers`(~4841) / `activeOverlayLayers`(~4842) / `overlaySeq`(~4843) / `recomputeActiveOverlays`(~4845, 렌더 루프 내 재계산 금지) / `drawOverlayMarkers`(~4850, 렌더 호출 ~2065).
  - **프레임 계산**: `frameFromMeta(meta)`(~4874, `grid_metadata` JSON → 프레임 기술자. **없는 물리 항목은 undefined로 남겨** 현재 화면 값 폴백) / `currentFrame()`(~4901) / `resolveFrame(frame)`(~4914, 축 전부를 실값으로 확정) / `frameAxesKey(rf)`(~4931, 회전·면·y반전·START·치수·물리 6종 = identity/derived 판정의 유일한 근거).
  - **`projectCellsToPhys(cells, frame)`(~4942)** — `getCellFromVisualCoords` → `getPhysicalCoords`를 **소스 프레임을 씌운 채** 호출한다. `loadExistingMap` 셀 루프와 **같은 함수·같은 인자 순서** — **오버레이 전용 기하식은 0줄**이다.
  - `pushFailedOverlay`(~4961) — 실패도 목록 행으로 남긴다(같은 소스 중복은 갱신).
  - 소스 읽기: `OVERLAY_CELL_LIMIT=2000`(~4982, 메인 로드와 동일 상한) `fetchTableSchemaCached`(~4985) `OVERLAY_SYSTEM_COLS`/`OVERLAY_VAL_CANDIDATES`(~4994/4996) `deriveMapBinding(schema)`(~5000) `buildKeyFilters(keyColumns, mapKey)`(~5017, 서버 `build_key_filters`와 동일 — 마지막 컬럼이 나머지 흡수).
  - `addOverlayLayer(sourceTable, sourceKey, targetOverride)`(~5037) — **메인 로드와 코드 경로 완전 분리**. 흐름: ① 바인딩 유도 → ②③ `Promise.allSettled`로 셀 + 소스/타깃 메타 병렬 조회 → ④ 프레임 확정 → ⑤ `cols×rows` 호환성 관문 → ⑥ 정렬 요약 + 격자 밖 셀 카운트. 명명된 실패 status **4종**: `binding_unavailable` `meta_unavailable` `no_data` `align_unavailable` (+ IO 실패는 일반 `error`). **이 함수는 `/api/maps/overlay`를 호출하지 않는다**.
  - `removeOverlayLayer`(~5231) `toggleOverlayLayer`(~5238) `clearOverlayLayers`(~5247).
  - `overlayGeomSig`(~5260) / `currentGeomSignature`(~5262) / `syncOverlayGeometry`(~5279, 서명 변경 시 `rawCells`+`o.frame`에서 재투영. 훅 2곳 — 렌더 ~1942 · 프레임 복원 ~4561). ✅ **[QA C7 해소]** 서명이 화면 7축 + **물리 6종**을 담는다(소스 메타 완비 시 재투영은 항등 — 6종이 실제로 일하는 곳은 물리 규격 미등록 폴백 경로뿐).
  - `overlayAlignChip(o)`(~5302) — 정렬 상태 칩. 판정은 **`align.origin`으로만**.
  - `importOverlayToGrid(id)`(~5333) — 유일한 의도적 교차: 오버레이 셀을 `gridData`로만(**서버 쓰기 없음**, `isProtectedFCell` 존중, 웨이퍼 밖 셀 스킵). `ensureLegendValues`(~5390)는 **로컬 legend 캐시만** 갱신.
  - `renderOverlayList`(~5405) `handleAddOverlayClick`(~5459) `CORE_CANONICAL_TABLE='core_defect_map'`(~5488) `addOverlayForSource(sourceTable, lot, slot)`(~5490) `listOverlayLayers`(~5499) — 뒤 둘은 `transfer_plan.js`에 넘기는 컨트롤러 표면.
  - **오버레이 해제 지점은 2곳이다** — 테이블 전환 `switchTable`(호출 ~1118, 토스트) · **맵 로드 `loadExistingMap`(호출 ~3406, 토스트)**. 둘 다 `overlayLayers.length > 0`일 때만 실행한다. ⚠️ **`openMapFrame`은 오버레이를 해제하지 않는다** — 프레임 스택은 반대로 오버레이를 **보존**한다(~4455 주석). 툴바 버튼(`#btn-clear-overlays`) 배선은 ~765.
- **전사 계획 배선**: `initTransferPlan({...})`(~569, import ~6 — `bandToState`도 여기서 들여온다) + `notifyMapContext`(1126/3756/4037/4785/4792/4809 = **6곳**) `notifyLegendChanged`(2896/2949/2955/2972 = **4곳** — ⚠️ `selectBrush`엔 의도적으로 없다, 주석 ~3173) `notifyPaintCounts`(~1818). rect 영역 선택 모드는 **전면 폐기**(값 페인팅이 정본 — 코드 부재).
  - **컨트롤러 표면(~569–)** — 패널에 넘기는 함수 묶음이 곧 경계 계약이다: `getLegend`(**`cloneLegend` 깊은 복사**) `getPlanSaveState` `getActiveBrush` `getCounts` `setBrush` `addLegendRow` **`updateLegendRow`** `deleteLegendRow` `getMapContext`(`{table, mapKey, loaded, depth, parent}`) `openMapFrame` `goBack` `addOverlayForSource` `listOverlays` `removeOverlay` `toggleOverlay` `clearOverlays` `fetchMapKeyColumns` `probeMapExists`.

### `transfer_plan.js` (~1,368줄) — 「2. Legend & DOE」 패널 (map_editor.html에서 소비, **`b35bc9f` zone 편집기로 재작성 · `2baf9ff` U9 marker/U8 피드백**)
**「계획 = 지금 열어 편집 중인 그 맵」.** 계획 정체성은 `(ref_table, map_key)`이며 `plan_id`도 계획 맵 사본도 없다. 스타일은 `transfer_plan.css`. (구 M1 `bonding_plan.js`/`.css`는 삭제 — 파일 자체가 없으므로 앵커를 달지 말 것.)

> ⭐ **이 파일은 서버에 쓰지 않는다.** 값 하나 = `map_split_registry` 행 하나 = DOE 하나이고, 그 행의 **유일한 기록자는 `map_editor.js`**다. 이 파일은 `controller.getLegend()`로 읽고 `controller.updateLegendRow(value, patch)`로만 쓴다 — 저장·삭제·동시성 가드는 전부 그 한 경로에 있다. **band 편집기는 은퇴했다**(2026-07-28) — 구간 목록 대신 **ZONE 3열(1H/MID/TOP) + STACK 숫자 하나**를 편집한다. 순수 산술·규칙·TSV 계약은 전부 **`doe_bands.js`**에 있고 이 파일은 렌더·바인딩·서버 요약 조회만 한다.
> ⭐ **파생값은 저장하지 않는다** — 구역 총 소요 = 칠한 셀 수 × 구역 층수, 자재당 = `ceil(총 소요 / 자재 수)`(충분성 검사이지 배분이 아니다).

- 상태 `S`(~70–86): `stages`/`stagesStatus` · `ctx{table,mapKey,loaded,depth,parent}` · **`legendRows`(= DOE 그 자체. `{value, desc, color, knobs:[{k,v}], stack, mat_1h:[str], mat_mid:[str], mat_top:[str]}`의 **읽기 전용 미러**)** · **`blocks`(마지막 검증의 차단 목록)** · `counts` · `activeBrush` · `summaries`(풀 키 → 요약) · `matMapState` · `keyColumns` · `matSeq` · `flash` · `navBusy`. 상수 `BUILTIN_STAGES`(~56) `SOURCE_TABLE_FALLBACK`(~62) `SOURCE_OVERLAY_SUGGESTIONS`(~65).
- **레거시 band 판독기 2종 — [§6-2 계약](#6-2-교차-구현-계약-contracts) 추출 대상**: **`bandToState(b)`(~203 — 유일한 정수 분류기 `{state:'blank'\|'ok'\|'invalid', value}`. `map_editor.normalizeBands`와 STACK 판독이 모듈 경계를 넘어 이것을 쓴다 — STACK의 `marker` 승격은 이 위에 얹힌 `doe_bands.stackState`가 한다)** · `prevTo(bands, i)`(~252 — `doe_bands.bandsToZones`가 걷는 유일한 레거시 걷기). **둘만 export**(~237). ~~`bandTo`/`bandLayers`/`bandTotal`/`bandShare`~~ 등 band 산술 일습은 **부재가 하니스로 단언**된다([§0](#0-묘비-목록--소스에-존재하지-않는-이름)). `paintedOf`(~260) `splitMaterialId(id)`(~276 — 분리자 없으면 `{lot:null, slot:null}`, **추측하지 않는다**)는 잔존.
- **legend 접근·변조**: `rowOf`(~287) / **쓰기 관문 하나** — **`commitRow(value, patch)`(~301)** → `controller.updateLegendRow` 위임, 실패 시 토스트만. **이 파일에 저장 코드는 없다.**
- stage 유도: `normalizeStage`(~112) `stageOfTable`(~129, 서버 `stage_of_table`의 클라 미러) `sourceTableOf`(~142) `sourceTableOfStage`(~158) `fetchStages`(~160, GET `/api/transfer-plan/stages`).
- 소스 요약(**풀 단위**): `poolCacheId`(~319) `summaryKeyFor`(~323) `getPoolSummary(pool, force)`(~328, GET `/api/transfer-plan/source-summary` — BIN·scope 파라미터 포함) `availabilityOfPool`(~373) `isPlainNotFound`(~413) `materialMetaValues`(~420) `probeMaterialMap`(~439) `refreshMaterials(force=false)`(~1125 — **[`2baf9ff` U8] `force=true`는 [↻ 가용] 버튼 단 하나의 경로**이고, 그때만 완료 토스트를 낸다: 전 풀 정상이면 info, 미상이 있으면 **최빈 사유 1줄** warning — 종전엔 서버가 BIN 축을 거부해 전부 미상이면 같은 미상 셀만 다시 칠해져 버튼이 죽은 것으로 보였다. 셀별 사유는 종전대로 미상 툴팁, 클라측 폴백 계산 없음) `rewardAfterReturn`(~1098 — 복귀 시 그 자재만 재조회).
- 렌더(zone 그리드): `renderPlanHead`(~453) `zoneCellHtml`(~537) `ZONE_PLACEHOLDER`(~569) `zoneIsInapplicable`(~581 — **[`2baf9ff` U9] marker 행(STACK 0)은 전 구역 `inapplicable`**: `해당 없음` 렌더 + fix 문구 `'STACK 0 = 상태 표시 값 (층 없음)'` — 구조적 부재 셀과 같은 취급) `materialChipHtml`(~609) `planOf`(~623) `renderDoeList`(~627 — STACK 입력의 `bad` 클래스는 `ok`·`marker` 둘 다 아님일 때만, 푸터 노트에 marker 안내 1줄) `refreshRowZones`(~712 — **행 단위 갱신**: 전체 리스트 재구성이 입력 랙의 원인이었다, `280ebf0`) `focusedRowValue`/`focusedColumnId`(~742/748) `bindDoeList`(~757 — keystroke 배지도 `marker`를 오류로 칠하지 않는다 ~797) `rollupRows`(~838) `renderMaterialPane`(~850) `knobChipsFor`(~959) `renderAll`(~1163) `buildWorkspace`(~1169). **[`280ebf0`] DOE 입력·라벨 한 단계 확대**(.68→.82rem — Excel 붙여넣기 계약은 index 기반이라 무영향).
- **Excel 클립보드(6열 TSV 계약 — `tsv.js` + `doe_bands.js` 소비)**: `planClipboardActive`(~984) `onPlanPaste`(~991 — `parseTsv`→`mapPastedGrid`→행별 `commitRow`) `onPlanCopy`(~1049 — `planToGrid`→`serializeTsv`). 왕복 동일성은 `contracts/doe_band_rules`의 `roundtrip_cases`가 고정한다.
- 이동 허브: `openMaterial(id)`(~1066) — **맵 간 이동의 유일 지점**(프레임 스택). **[`280ebf0` LOAD-parity]** `(lot, slot)`으로 분해되지 않는 id도 **라우팅한다**(~1073–1086): 첫 키 컬럼 필터 `{firstKeyColumn: rawId}`로 폴백 — 「1. Map Search & Load」에서 그 필드 하나만 치는 것과 같은 경로. 행 없는 키는 빈 그리드로 열리고 ⚡ Push에서 생성된다. **`probeMaterialMap`은 이런 id에 계속 null(미상)을 반환한다** — 내비게이션 추측은 되지만 존재 주장은 안 된다.
- 진입/통지 export: `notifyMapContext(info={})`(~1207 — 여기서 서버 조회를 하지 않는다: legend 로드·채택·가드는 전부 `map_editor`의 registry 경로) `notifyLegendChanged`(~1227) `notifyPaintCounts(counts)`(~1239, **`textContent`만 패치**) `initTransferPlan(paintController)`(~1265). (+ 순수 함수 `bandToState`·`prevTo` export ~237)
- ⚠️ **`__held_*` 함수군(~1287–1368)은 명시적 보류 구역** — 호출자 없음. 검증/경고 UI는 사용자 지시로 미구현. ⚠️ `__HELD_WARN_SEVERITY`(~1337)에 **`layer_coverage_gap` 키가 남아 있으나 서버에서 삭제된 경고 타입이라 사문**이다.

### `doe_bands.js` (~722줄) — DOE ZONE 모델 순수 코어 (`269b39e` 신설, `b35bc9f` 확장, **`2baf9ff` U9 marker** — 무DOM, `contracts/doe_band_rules` 채점 대상)
**서버 `transfer_plan.py`의 zone 블록(~1923–2484)과 짝을 이루는 클라 측 정본.** export(~713): `ZONES`/`ZONE_LABEL`(~50/55) · `boundState`(~60)/**`stackState`(~73 — `bandToState` 위임 위에 **4상태**: 명시적 0만 `'marker'` 승격(~76), 음수는 invalid로 값 보존. 서버 `stack_state`+`STACK_MARKER`의 미러)** · `formatLayerRuns`(~83) · **`parseMaterialList`(~103 — 유일한 자재 목록 정규화기: 패널 입력도 저장 계층도 이것을 쓴다. 화면의 자재 수와 `ceil(total/n)`의 분모가 두 숫자가 될 수 없게)** · `serializeMaterialList`(~125) · `parseMaterialToken`(~153, `lot[_slot][:BIN]` 문법) · **`materialPoolKey`(~201 — ⚠️ 분리자 조인 금지의 실사례 주석: U+001F 조인 키가 디스크에서 분리자를 잃어 두 풀이 합산됐다)** · `midZone`(~212 — marker는 `{size:0, known:true}` ~219)/`zoneLayers`(~229 — **marker는 전 구역 `[]`** ~234)/`zoneLabel`(~247) · **`validateZonePlan`(~270 — V1–V6 차단 + advisory. **marker 행은 V6 하나에만 답한다**: V6 블록 ~287–302, V3 풀 스캔 제외 ~372)** · `zoneDemand`(~405 — **은퇴한 `bandTotal`/`bandShare`의 후계**) · `materialRollupRows`(~427 — marker 행은 롤업에 **부재** ~435) · `remainingState`(~478) · **6열 TSV/Excel 계약**: `DOE_COLUMNS`(~494) `IGNORED_HEADERS`(~511) `columnIdByHeader`(~513) `looksLikeHeader`(~524) `leadingBlankColumnDropped`(~553) `mapPastedGrid`(~579) `planRowToRecord`(~620 — 읽을 수 없는 STACK도 **원문 그대로** Excel로 돌려보내되, **marker는 판독 가능이라 canonical `'0'`으로 export** ~627) `planToGrid`(~638) `rollupToGrid`(~647) · **`bandsToZones`(~681 — 레거시 band 계획 → zone 사상. 표현 불가면 거부)**.

### `tsv.js` (~121줄) — TSV 파서/직렬화기 (`b35bc9f` 신설)
Excel 클립보드 왕복의 공용 저층 — export `parseTsv`/`serializeTsv`/`quoteField`(~121). 소비자 둘: `clipboard.js`(그리드 복붙) · `transfer_plan.js`(DOE 6열 계약). 인용부호·개행 처리를 한 곳으로 모은 것이 존재 이유다.

### `admin.js` (~2,805줄) — 어드민 페이지 (2026-07-25 전면 재작성 — 파이프라인 5탭, export 없음)

> 🔑 **[`90e284f`] 파일 최상단이 토큰 블록이다(~16–143).** 서버가 `/admin/*`을 공유 비밀 뒤로 옮겼으므로([§1.6](#16-serveradmin_authpy--어드민내부-토큰-게이트-90e284f-신설)) 이 페이지는 **로그인 화면도 사용자 모델도 없이** 토큰 하나를 묻고, 보관하고, 헤더로 붙인다. 서버에 토큰이 설정돼 있지 않으면 게이트 라우트가 정상 응답하므로 **아무것도 묻지 않고 이 장치는 보이지 않는다** — 프롬프트는 **게이트가 낸 거부**에만 뜬다.
>
> ⚠️ **`grep "fetch(\`${API_BASE}/admin/"`가 0건이어야 한다.** 히트가 있으면 그 호출부는 `adminFetch`를 우회한 것이고, 미설정 서버에선 잘 돌다가 **프로덕션에서만 401**이 된다.

| 심볼 | 역할 | 라인 |
|---|---|---|
| `ADMIN_TOKEN_HEADER='X-Admin-Token'` / `ADMIN_TOKEN_KEY='assy.adminToken'` | 헤더명(서버 `admin_auth.ADMIN_TOKEN_HEADER`와 짝) / localStorage 키 | ~28/29 |
| `getAdminToken()` / `storeAdminToken(value)` | localStorage 읽기·쓰기. **둘 다 try/catch** — 프라이빗 모드·스토리지 비활성이면 토큰이 이 페이지 수명만큼만 산다 | ~31/35 |
| **`adminTokenGeneration`** | **토큰이 바뀔 때마다 증가.** 토큰 교체 시점에 이미 날아가 있던 응답은 **낡은 증거**라 새 토큰에 대해 아무것도 말하지 않으므로 두 번째 프롬프트를 띄우면 안 된다. 이것이 없으면 "동시 7요청에 프롬프트 1회"가 타이밍 운에 좌우되고, 실제로 모달이 몇 초 열려 있는 동안 도착한 응답들이 **멀쩡한 토큰을 틀렸다고 몰아세웠다** | ~48 |
| `adminTokenDeclined` / `tokenPromptInFlight` | 운영자가 취소했음(30초 리프레시마다 영원히 다시 묻는 것은 수정이 아니라 함정 — 새로고침하면 다시 묻는다) / 진행 중 프롬프트 1개 공유 | ~51/52 |
| **`isGateRejection(res)`** | **게이트가 낸 거부만 true.** 상태코드만으론 부족하다 — `_resolve_admin_script_path`도 403을 내는데 토큰과 무관하다. 그것을 인증 실패로 취급했더니 페이지가 토큰을 요구하고 **맞는 저장 토큰을 덮어썼다.** 판정 근거는 `WWW-Authenticate: X-Admin-Token` 헤더 | ~62 |
| `askForAdminToken(message)` | `window.prompt` 1회(진행 중이면 공유). **`setTimeout(…, 0)`로 한 틱 미룬다** — 같은 `Promise.all`의 형제 핸들러들이 모달이 스레드를 막기 전에 이 프라미스에 붙게 하기 위함. **취소는 저장 토큰을 지우지 않는다**(구 코드는 취소를 `storeAdminToken('')`로 바꿔 **작동하던 토큰을 삭제했다**) | ~69 |
| `withAdminToken(init)` | fetch init에 헤더 주입. **쿼리 파라미터가 아니라 헤더인 이유는 쿼리스트링이 서버 액세스 로그에 남기 때문** | ~97 |
| **`adminFetch(url, init)`** | **`/admin/*` 전용 fetch — 이 파일의 모든 어드민 호출이 여기를 지난다.** ① **503이면 본문 `detail`을 토스트로 띄우고 그대로 반환**(~117 — 미설정 서버가 코드 실행 라우트를 거부하는 상태다. 본문이 변수명과 재시작 방법을 말해 주는데 호출부에 맡기면 "저장 중 오류 발생"이 된다) ② 게이트 거부가 아니면 통과 ③ **세대가 바뀌었으면 조용히 새 토큰으로 1회 재시도**(~129) ④ 프롬프트 후 **딱 한 번만 재시도**(~141 — 두 번째 거부는 호출자에게 돌려줘 운영자를 모달에 가두지 않는다) | ~109 |

- 라우팅: `parseRoute`(~368) `applyRoute`(~380) — `#overview/#file/#chain/#autoupdate/#enrichment` + 구 별칭(`#outbox→chain` 등) + `#editor=<path>`. `switchTab(tabName, opts)`(~425, 해시 동기·Overview 전폭 레이아웃). `setSectionCount`(~351).
- 탭 데이터: `fetchData(options)`(~745, 탭당 병렬 fetch를 한 seq로 묶어 stale 렌더 차단 — [P1] File 탭은 `/admin/file-ingestion/active`도 병렬 수집 ~759) → 각 `render*Table` + 섹션 카운트 배지, `clearSelections`(~1697)/`clearRowHighlights`(~1709).
- [P1] File 탭 진행 중 섹션: `renderActiveIngestions`(~1053, `#sec-active-ingestions` — HEAVY=badge-warning/normal=badge-success 배지·진행률 바·행 카운트·경과 + **재기동 경고 배너**, 항목 0이면 섹션 숨김) `scheduleActiveRefresh`(~1035, 진행 항목 존재+File 탭 표시 중 한정 5s 경량 타이머 — `document.hidden` 시 스킵) `formatElapsed`(~1023). 헬스 스트립 File 카드 warn·Overview 카드 진행 메트릭 통합.
- Overview: `fetchOverview`(~1481) `renderOverview`(~1610, 4카드+최근 이벤트+딥링크) + **[`ec75d4c` 핵심가치 #1 계측] `renderRecorrection`(~1440 — `/dashboard/summary`의 재수정률 통계 표시)**.
- 유기 연계: `renderLinkedFailTable`(~1340, AutoUpdate §오류 — 산출물 인제션 실패 교집합) `showEventDiagnostics`(~2181, +Edit Mapper 딥링크) `selectFileRow`(~1958, 파서 편집 딥링크).
- AutoUpdate 토글: `renderAutoUpdateTable`(~1259, 수집기별 Active 스위치·비활성 행 dim) `toggleCollectorActive`(~1854, POST `/admin/auto-update/toggle` — 낙관 갱신+실패 원복, fetchSeq 가드 table+script 키 재조회) `runAutoUpdateNow`(~1827, active 무관+툴팁 — **strict 게이트 라우트라 토큰 미설정 서버에선 503 토스트가 뜬다**). Overview 카드·헬스 스트립에 active/total 표기.
- Enrichment 탭: `renderEnrichmentTable`(~1369) `fetchEnrichmentStatus`(~2626, 15s TTL 캐시 — 스트립·탭·Overview 3소비처 공용).
- 에디터(공용 뷰): `initMonacoEditor`(~2345, pending open) `populateEditorPicker`(~2402) `selectEditorFile`(~2448, dirty confirm) `openInlineEditor`(~2528, 저장은 **strict 게이트** POST `/admin/scripts/code` ~2507). (구 좌측 파일트리 `renderEditorTree` 일습은 피커로 대체·삭제됨)
- 소비 API: `/admin/*` 전역(**전부 `adminFetch` 경유**) + `/enrichment/rules` + `/tables/{t}/data`(결손 카운트).

### `enrichment.js` (~754줄) — 인리치먼트 컨베이어 페이지 (export 없음)
- 규칙: `loadRules`(~69) `selectRule`(~116) `rebuildGrid`(~151). 워크리스트: `fetchWorklist`(~190) `fetchTotalAll`(~241) `refillIfNeeded`(~257).
- 입력 흐름: `renderDetail`(~310) `onInputKeydown`(~384) `moveSelection`(~402) `saveCurrent`(~427, PUT `/data/updates`).
- 참조 패널: `initReferencePanel`(~517) `loadActiveReference`(~580) `renderRefTable`(~637).
- 소비 API: `/enrichment/rules`, `/enrichment/rules/{r}/references/{i}`, `/tables/{t}/data`, PUT `/data/updates`.

### `graph_viewer.js` (~1,244줄) — 지식그래프 서브그래프 뷰어 (graph.html 엔트리, 무라이브러리)
- 조회·URL: `syncUrl`(~343, `?label=&identity=` pushState — 동일 URL 중복 push 방지) `explore(label, identity, opts)`(~354, `/graph/neighbors` 조회→BFS 동심원 레이아웃. `opts.history: 'push'|'replace'|'none'`) `renderStats`(~158, `/graph/stats` 카운트 카드+라벨 색 팔레트 — **라벨 카드 클릭 → 노드 리스트**).
- **라벨 노드 리스트**(`df63f3a` 신설): `openLabelNodes`(~220) `closeLabelNodes`(~228, back → Stats 복귀) `fetchLabelNodesPage`(~234, 빈 q + label 서버 리스팅 — `LABEL_LIST_PAGE=200`(~24, 서버 캡과 동일)·offset "더 보기"·seq 가드) `renderLabelNodesBlock`(~264, 로드수/총수 헤더·행 클릭 → `explore` 연동). `showStatsView/showGraphView`(~315/321).
- 렌더: `layoutGraph`(~432) `renderCanvas`(~537, 캔버스 본체 — 테마 색 1회 캐싱+`themechange` 재캐싱, 상시 rAF 없음).
- **Connections 테이블**(`18218da` 신설): `connectionRows(nodeId, edges, nodesById)`(~707) `propsSummary`(~731) `selectNode(node, opts)`(~745, 선택 확립+`connSeq` stale 가드) `fetchNodeConnections`(~766, 비중심 노드 depth-1 재조회 보강 — label+identity 파라미터) `renderConnBlock`(~796, `CONN_PAGE=80` 단위 "더 보기"·행 클릭 시드 연동) `renderNodePanel`(~864) `setPanelCollapsed`(~933, 패널 접기).
- 이벤트: `onNodeClick`(~963, **선택만** — 중심 이동은 더블클릭/시드 버튼) `initCanvasEvents`(~967, 팬·줌·dblclick 재중심) `exploreFromInput`(~1129) `initSearchBar`(~1161, `/graph/nodes/search` 자동완성+200ms debounce+seq 가드) `init`(~1197, popstate 복원·접기 버튼·초기 쿼리 replaceState — trace 크로스링크).
- user provenance 엣지는 `--overwrite` 색 강조(테이블은 `.conn-user`). truncated 배지. 소비 API: `/graph/stats·neighbors·nodes/search`.

### `trace_core.js` (~234줄) — G2 추적 순수 로직 (무의존, node 테스트 가능)
- export: `SEED_CAP=20`(~10) `composeIdentity`(~38, 서버 G1 `compose_identity` 미러 — `|` 조인+이스케이프+float 안정화) `capSeeds`(~57) `parseSeedsParam`(~73) `normalizeMissingSeeds`(~98) `buildTraceRequest`(~128) `groupNodesByLabel`(~146) `splitTimeline`(~187) 표시 헬퍼(`propsSummary`/`fmtEventTime` 등, ~211–228).

### `trace.js` (~454줄) — 추적 리포트 (trace.html 엔트리)
- `runTrace`(~103, POST `/graph/trace`, seq 가드, 실패 시 기존 리포트 유지+토스트) → `renderReport`(~213, 라벨별 그룹 테이블 100행 청크 + event_time 타임라인 300건 청크, user provenance 강조, 구조 엣지 접이식) `initControls`(~403, 시드 칩·depth 즉시 재실행·시간범위 재실행 버튼) `init`(~425, URL `replaceState` 동기화).

### `trace_launch.js` (~107줄) — index 「🕸️ 추적」 진입점
- export: `updateTraceEntryVisibility`(~25) `refreshTraceEntry`(~35, `GET /graph/mapping-summary`로 활성 판정) `openTraceForSelection`(~54, 선택 행→identity 조립 시드, 상한 20 토스트, 새 탭) `initTraceEntry`(~96).

### 보조 모듈
| 파일 | 책임 |
|---|---|
| `theme.js` (~92) | 라이트/다크 토큰 전환 — export `getTheme/applyTheme/toggleTheme/syncAgGridThemeClasses/initTheme` |
| `tokens.css` (~290) | 디자인 토큰(색·타이포·간격) — 듀얼 테마 CSS 변수의 SSOT. 2026-07-25 다크 세트 심화(Ground L* 9.2, WCAG AA 유지) |
| `style.css` (~1,848) | index 페이지 스타일 본체(맵 에디터와 공유). app-header는 `position:relative; z-index:200` — split-resizer(z:100) 위 스태킹 보장. **[`280ebf0`] `.glass-input` transition을 `all 0.3s`→`border-color/box-shadow 0.1s`로 국소화**(DOE 입력 랙의 2차 원인 — 토큰은 무변경) |
| `transfer_plan.css` (~593) | 전사 계획 사이드바 스타일 — tokens.css 시맨틱 토큰만 사용(듀얼 테마 자동 대응). **[`b35bc9f`] zone 편집기용으로 전면 재작성**(826→593줄) — 그 재작성이 `.overlay-box`/`.ov-*` 룰셋을 떨어뜨렸고 **[`280ebf0`]에서 원문 그대로 복원**됐다(마크업은 계속 그 클래스를 쓰고 있었다) |
| `utils.js` (~337) | `getLocalTimeString`(~2) / **전역 토스트 재작성**(~29–164) / `getCleanFilename`(~166) / **[`269b39e`] 인제션 진행 카드 상한** — `MAX_VISIBLE_PROGRESS_CARDS=3`(~187)·`collapseProgressOverflow`(~194, 초과분은 숨기고 "…N건" 한 줄로 집계 — 숨은 카드도 계속 갱신되며 앞 카드가 끝나면 표면화)·`dismissProgressCard`(~219, 카드 제거 로직 단일화) / 진행 토스트 `showIngestionProgress`(~237)·`finishIngestionProgress`(~298). **토스트 규율(전 페이지 영향)**: 만료는 **벽시계 `expireAt`** 기준(`sweepToasts`가 `now >= expireAt` 비교 — 백그라운드 탭 `setTimeout` 스로틀링으로 무한 누적되던 원인 제거, 타이머는 스윕을 깨우는 힌트일 뿐) · 상한 `TOAST_MAX_VISIBLE=4`(~29)이고 퇴거는 **비-에러 오래된 것 우선**, 방금 삽입분은 `keep` 인자로 면제 · TTL `{info:5s, success:5s, warning:9s, error:15s}`(~30 — **에러 15초는 성공 알림에 밀려나지 않게 하는 의도적 예외**) · 스윕 트리거는 타이머 + `visibilitychange` + `window.focus` + 삽입 전후(~101–105) · `dedupeKey` 합치기는 **에러 제외**(건별 원인이 중요), 같은 키+타입이면 `count+=1`·만료 연장·`… · N건` 표기 · 본문은 `textContent`(HTML 해석 금지) |
| `dom.js` (~57) | DOM 참조 일원화 — `elements` 게터 객체(+`traceBtn`/`menuTrace`) |
| `config.js` (~5) | `API_BASE`/`CURRENT_USER`/`pageLimit` |
| `clipboard.js`·`counter.js` | counter.js는 Vite 템플릿 잔재(미사용) |

---

## 8. 주요 호출 흐름 요약

> 🔒 **[`90e284f`] 아래 흐름 중 `/internal/events/*`를 지나는 것(1·3·8)은 전부 `X-Admin-Token` 헤더를 실어 나른다** — 워커측은 `admin_auth.internal_event_headers()`, 서버측은 `Depends(require_admin_token)`. 토큰 미설정이면 양쪽 다 무동작이라 흐름이 종전과 동일하다. **토큰을 웹서버에만 설정하고 런처에 안 하면 워커의 브로드캐스트가 전부 401이 되어 WS 갱신이 조용히 멎는다**(데이터는 계속 들어가고 화면만 안 바뀐다).

1. **파일 인제션**: 폴더 투입 → `IngestionHandler._handle_event` → **[P1] `_route_and_process`**(임계 초과·backlog 잔여 → heavy 큐 / 인라인은 직렬화 락 try-acquire, 실패 시 큐 재라우팅) → `process_with_retry` → `_snapshot_table_context`(파일당 1회 config 스냅샷 — 테이블 해석은 글로벌 별칭 > 레거시 config.json > 폴더명) → `_resolve_rows`(파이프라인 우선 → std parser 폴백) → **[P2] `compute_file_signature` → `_try_dedup_skip`(동일 시그니처 `DONE`이면 skip+archive+`SKIPPED` 로그) → `_plan_checkpoint`(재개 오프셋 결정)** → `_send_to_upsert` → **`crud.apply_batch_updates` 직접 호출**(HTTP 아님, 청크마다 `record_chunk_progress`가 **같은 트랜잭션**에 동승) → `_finalize_checkpoint(mark_done)` → 웹서버 `/internal/events/batch-refresh|file-processed` → WS 브로드캐스트.
   - [P1] 진행 가시화(push-캐시-서빙): watcher `_notify_ingestion_state` → `run_watcher.trigger_ws_ingestion_state` → POST `/internal/events/ingestion-state` → `IngestionActivityRegistry`(+ 기존 progress/file-processed 인터셉트) → GET `/admin/file-ingestion/active` → admin File 탭 진행 섹션·재기동 경고. WS 이벤트 계약 무변경.
2. **수동 편집**: client `handleCellEdit`/`applyValueToSelectedRange` → PUT `/tables/{t}/data/updates` → `apply_batch_updates_endpoint` → `crud.apply_batch_updates` → outbox 발화 + WS `batch_row_upsert` → 전 클라이언트 `handleWebSocketMessage` 델타 반영.
3. **체인 인제션**: `apply_batch_updates`의 outbox 발화 → NOTIFY → `start_chain_ingestion_worker` 루프 → `process_pending_groups` → `process_chain_transaction_group`(맵퍼 실행, 예: `map_enrichment_dedup`) → 파생 테이블 `apply_batch_updates`(source=chain_ingestion, 순환 차단) → `_dispatch_broadcasts` → `/internal/events/broadcast`(created_logs 500건 절단 + `total_log_count` 실건수) → WS.
4. **조회**: client `fetchData` → GET `/tables/{t}/data` → `get_table_data` → `get_column_filter_condition` + `fetch_and_merge_metadata`(셀 객체 병합) → client `ensureCellObject` 정규화 → AG-Grid.
5. **레이어링 조작**: 소스 모달/Pin → `/tables/{t}/cells/*` 라우트 → `crud.delete_cell_source_batch`/`set_cell_manual_priority_batch` → `compute_priority_value` 재계산 → WS 반영.
6. **설정 핫리로드**: 어드민 `reloadSystemConfigs` → POST `/admin/reload-configs` → 웹서버 `reload_local_process_cache` → `models.refresh_dynamic_models(engine)`(싱글턴·ORM·**신규 테이블 물리 CREATE** — 1차 DDL 소유자, outbox 발화보다 선행) → SYSTEM_RELOAD outbox → 워커들 `reload_worker_process_cache` + `refresh_dynamic_models`(게이트+checkfirst로 무해한 보충 안전망). 직접 파일 편집 시엔 `config_watcher`가 동일 CREATE 수행. graph 워커도 배치 내 SYSTEM_RELOAD 감지로 매핑·테이블 리로드(이슈 #8 해소).
7. **맵 에디터**: (부트 시 **[`280ebf0`] `restoreLastOpenMap`**이 `map_editor_last_open` localStorage를 읽어 **수동 LOAD 경로 그대로** 마지막 맵을 재오픈) → `loadExistingMap`(**[`6db517d` H1] 로드 시점에 초안을 덮어쓰지 않는다** — 초안 우선순위 판정 후 1회만 저장) → GET `/tables/{t}/data`(REST) → 편집 → `pushMapData`(**[`6db517d` H2] 프레임이 화면의 비어 있지 않은 셀을 전부 못 담으면 confirm 전에 거부** — replace_map 절단 방지) → PUT `/data/updates`. 프리셋은 `/map-presets` CRUD. 페인트 잠금은 기동 시 GET `/api/maps/paint-rules` → `applyPaintLockConfig` → 전 편집 경로가 `isProtectedFCell` 단일 관문 통과. (WS 미사용)
   - **[7d931dc] 오버레이(맵 인프라 — 계획 전용 아님) — 변환은 클라 단일 구현**: `handleAddOverlayClick`/`addOverlayForSource` → `addOverlayLayer` → ① GET `/tables/{src}/schema`(`deriveMapBinding`) → ②③ GET `/tables/{src}/data`(**원본 좌표**) + `wafer_map_metadata` 소스/타깃 2건 병렬 → ④ `frameFromMeta`로 프레임 확정(부재 시 현재 화면 = identity 폴백) → ⑤ `cols×rows` 관문 → ⑥ `projectCellsToPhys`(소스 프레임 → 물리 키) → 캔버스 마커. 화면 규격이 바뀌면 `syncOverlayGeometry`가 `rawCells`에서 재투영. `importOverlayToGrid`만 `gridData`로 넘어온다(서버 쓰기 없음).
     - ⚠️ **구 선행 단계였던 GET `/api/maps/overlay?…&limit=1`(보정 **선언** 관문 `probeAlignDeclaration`)은 삭제됐다**(2026-07-27) — 서버 선언 레이어가 없어져 물어볼 대상이 사라졌다. 오버레이 추가 경로에서 이 엔드포인트를 호출하는 코드를 보면 그것은 되살아난 것이 아니라 **오류**다.
     - **서버 경로는 삭제되지 않았다** — `map_overlay.get_overlay`(`resolve_map_transform` + `make_frame_transform` + `_frame_phys_params`)는 엔드포인트에서 그대로 살아 있고 `test_map_overlay.py`가 계약을 지킨다. 바뀐 것은 **맵 에디터가 그 좌표를 소비하지 않는다**는 것뿐이다. 2026-07-27부터 `bonding_plan.py`·`transfer_plan.py`의 **가용량 산출이 이 서버 구현을 소비**한다(자체 사본은 삭제) — 서버 구현은 하나뿐이다.
   - **[zone 모델 `b35bc9f`] 전사 계획(계획 = 그 맵 자체, DOE = legend 행)**: 맵 로드(`loadExistingMap`) → `readRegistryScope`가 GET `/tables/map_split_registry/data`를 **map_key 필터로** 읽고(`REGISTRY_SCOPES=['map']` — 테이블 전체 어휘 시드는 `269b39e` 결함으로 삭제, 행이 없으면 `seedEmptyDoe`의 빈 DOE 1행) `applyRegistryRowsToLegend` + `legendReplaceScope{table, mapKey, fingerprint}` 확립 → `notifyMapContext` → `transfer_plan.js`가 `stage_of_table` 역인덱스로 stage 유도 → GET `/api/transfer-plan/{stages,source-summary}` → 패널에서 STACK·1H/MID/TOP·자재 편집 → `commitRow` → `controller.updateLegendRow` → **`scheduleCellDraft`(로컬 초안만 — 자동 서버 저장 없음)** → 사용자가 **⚡ Push**(`pushMapData`) → `saveLegendToServer` → **PUT `/tables/map_split_registry/data/updates` with `replace_map: true`**(맵 하나의 **값 전체 집합 1회 쓰기** — 지운 값·구역·자재는 집합에 없다는 것만으로 삭제된다. 별도 삭제 단계 없음).
     - ⚠️ **구 `PUT /tables/map_doe|map_doe_source/data/updates`는 클라의 쓰기 경로가 아니다** — 두 테이블은 `0f8d35f`에서 폐기됐고 `transfer_plan.js`에는 **저장 코드 자체가 없다**. 이 경로를 호출하는 코드를 보면 되살아난 것이 아니라 **오류**다.
     - 쓰기를 막는 장치: **권한**(`legendReplaceScope` — 이 맵의 행에서 온 legend만 그 행을 대체할 수 있고, 페이로드 단계에서 `reconcileVocabClaims`가 미변조 플레이스홀더를 걸러낸다 — `contracts/legend_map_scope`가 이 경로를 끝까지 돌려 검사) · **절단**(부분 읽기는 읽은 게 아니라 `throw` — 미확인 화면에서의 upsert는 못 본 계획을 덮는다) · **동시성**(쓰기 직전 재조회 → 지문 불일치면 `legendConflict`로 **거부**) · **스키마**(`probeZoneColumns` — 물리 zone 컬럼이 없으면 거부: crud가 zone을 떨어뜨린 replace_map은 계획을 층 구조 없이 대체한다).
     - 검증은 GET `/api/transfer-plan/validate?ref_table=&map_key=` → `status: ok|warnings|unverified`. 수량은 **저장에서 읽지 않고** `painted × zone_layers`로 유도된다. V1–V6 차단 규칙은 서버 `validate_zone_plan` ↔ 클라 `doe_bands.validateZonePlan`이 공유 벡터(`contracts/doe_band_rules`)로 고정(**STACK 0 = marker**: 구역·수요·롤업 없음, V6만 답한다 — `2baf9ff` U9).
     - ⚠️ **배포 순서 위험(`0f8d35f` 기록, zone 컬럼에도 동일)**: `stack`·`mat_*` 컬럼은 `install_product_tables.py --apply`로 라이브 `table_config`에 선언되고 config 워처가 재기동 없이 ALTER를 적용하지만, **웹서버는 코드를 다시 읽으려면 재기동이 필요**하다 — 그전까지 `validate`는 404다. config를 먼저 바꿨으므로 **코드만 되돌려서는 복구되지 않는다.**
8. **그래프 자동 승격**: `apply_batch_updates`의 outbox 발화 → `run_graph_materializer_loop`(keyset 커서) → `materialize_events` → `attach_col_sources`(provenance=식별 컬럼 winner 최저 서열) → `extract_graph_items` → 노드/엣지 UPSERT + `_retarget_stale_edges` → 커서 전진. 백필은 POST `/api/graph/sync` → `execute_manual_sync` → `resync_table`.
9. **그래프 조회/추적**: index 그리드 선택 → `openTraceForSelection`(`composeIdentity` 시드) → `trace.html` `runTrace` → POST `/graph/trace`(`_expand_graph_subgraph` 공용 BFS) → 그룹+타임라인 렌더. 뷰어는 `graph.html` `explore` → GET `/graph/neighbors`. 양방향 크로스링크(`?label=&identity=`).
10. **[`8117456`] 감독 + 헬스 (프로세스 생존 ≠ 진척)**: `run_decoupled_app.main()` → `ChildSpec(…, heartbeat=)` 5종 → `Supervisor.start_all()` → `Supervisor.run()` 폴 루프 → 자식 종료 감지 시 `_register_failure`(백오프 재기동, 예산 초과 시 `FAILED` 영구 정지) → `write_status()`가 `config/supervisor_status.json` 갱신.
    - 병렬로 각 워커가 **자기 루프 안에서** `heartbeat.beat(name)` → `config/worker_heartbeats/<name>.json` 원자적 replace.
    - GET `/health` → `heartbeat.read_all()` + `process_supervisor.read_status()` + DB/outbox 프로브 → **`health.compute_health`(순수 함수)** → `{status, problems[], checks{database,workers,outbox,supervisor,config_backup}}` + unhealthy면 **503**. 워커 판정은 두 신호의 조인이므로 `down`/`wedged`/`starting`/`foreign_beat`/`ok`를 구분해 이름 붙일 수 있다. **[`b35bc9f`] `config_backup` 검사는 compute_health 내부에서 `probe_config_backups`(60초 캐시)로 채워지며 `missing`/`stale`/`unknown` → degraded, 절대 503 아님.**
11. **[`4ba13ae`] 격리 개발환경**: `devenv.py bootstrap`(config·워크스페이스 **구조만** 복제) → `snapshot_db.py`(라이브 → QA DB, 읽기 전용 소스·1000행 청크) → `devenv.py up`이 `ASSY_DATA_ROOT=<repo>/dev_env` + QA DB URL로 프로세스 기동(API :8081, graph :8091) → 모든 모듈이 `paths.py`를 통해 격리 트리를 읽고 쓴다. 워처만은 `iso_watcher.py` 게이트를 지나며, **정적(경로)·라이브(실접속 DB 이름·포트) 단언에 하나라도 걸리면 기동을 거부**한다(exit 9). 드릴 전후 비교는 `manifest.py capture|diff`.
12. **[`90e284f`] 어드민 접근 (공유 비밀 1개 — 로그인 아님)**: 운영자가 `ASSY_ADMIN_TOKEN`을 **런처 프로세스 환경에** 설정 → `run_decoupled_app.main()` → `process_supervisor`가 자식 env를 `os.environ.copy()`로 상속 → 5자식 전부가 같은 토큰을 본다.
    - **기동**: `main.startup_event` → `admin_auth.startup_banner()` 1회 로깅(설정=info / 미설정=warning **무엇이 멈추는지 명시** / 비-ASCII=error **잠긴 줄 알고 있는 상태라 가장 시끄럽다**).
    - **사람 경로**: 브라우저가 `/admin`(게이트 없음 — 페이지가 떠야 물어볼 수 있다) → `admin.js`의 `adminFetch`가 저장 토큰을 `X-Admin-Token`으로 첨부 → 게이트 거부(401/403 + `WWW-Authenticate`)면 `askForAdminToken` 1회 → **한 번만** 재시도. 503이면 프롬프트가 아니라 **서버 본문을 그대로 토스트**(토큰 미설정 + 코드 실행 라우트).
    - **워커 경로**: 워처·체인·그래프 워커가 `admin_auth.internal_event_headers()`를 `/internal/events/*` POST에 붙인다.
    - **거부 지점 3종**: 미설정+strict → **503** · 설정+헤더없음 → **401** · 설정+불일치 → **403**(constant-time 비교, 세 detail 모두 상수 문자열).
    - **이 흐름과 무관하게 항상 열려 있는 것**: `/health`(외부 모니터) · `/admin`·`/admin.html` 페이지 HTML · `/api/*`·`/tables/*`(데이터 평면 — 이번 범위의 대상이 아니다).
