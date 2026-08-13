# ⚙️ AssyManager 설정 가이드 (Config Guide)

> **Status:** 🟢 Living | **Last-verified:** 2026-08-13 | **Owner:** Lead / Backend
>
> ### 이번 라운드 (2026-08-13 2차 · 리빙 문서 동기화 · `c0fb735`+`346aa88`+`f896020`+`272da5b`)
> - 🗄️ **§5.8-ter의 `map_doe`·`map_doe_source` 두 행을 걷었습니다**(`c0fb735` — 선언·설치기에서 은퇴). ⚠️ **운영자의 `table_config.json`에는 아직 남아 있을 수 있고**(gitignore라 배포가 안 덮습니다) 남아 있어도 새로 쓰는 코드는 없습니다. 물리 삭제 절차는 [OPERATOR_RUNBOOK §5](../process/OPERATOR_RUNBOOK.md). `--overwrite-drift`가 이 둘을 **되살린** 전례(🚨 항목)는 그대로 유효합니다.
> - **§5.8-ter에 void 기능 행 신설**(`346aa88`) — `inspection_run`+`void_obs`. 🔴 **켜는 순서가 있고**(선언 → 리로드 → 인덱스 → 파서 shim → 파일) 🔴 **둘 다 `map_key_columns`를 선언하지 않으며** 🔴 **등급·면적 컬럼을 추가하면 안 됩니다.**
> - **§1 표에 `ledger_config.json` 신설**(`f896020`+`bee1aeb`) — 🔴 **`occurred_at_*` 셋은 필수이고 빠지면 소스 전체를 거절**합니다(도착 시각 대용 금지). 🔴 **`occurred_at_timezone`은 naive 텍스트에만 적용**되고 자기 오프셋을 가진 값은 이미 자기 순간을 말했습니다. `vocabulary`의 관례 선언은 **`source_translator_ver`에 해시**돼 원자마다 출처가 남습니다.
> - 🔴 **§6에 함정 A-4 신설 — 「.sample과 실 파일은 조용히 갈라지고, 깨진 선언을 받을 사람은 새 박스뿐이다」**(`272da5b`). 추적되는 `.sample`의 `core_wafer_map.map_key_columns`가 R3를 위반했고, **희소한 비키 컬럼으로 스코프한 purge는 200을 내고 아무것도 안 지웁니다.** 라이브는 처음부터 옳았고 **그래서 이 박스에서는 아무도 못 봤습니다.** 🔴 **눈에 띈 하나만 고치지 말고 규칙을 전 테이블에 다시 돌릴 것.** ⚠️ 라이브에 없는 `.sample` 선언 넷의 채택은 **레인들이 착지한 뒤로 대기 중**입니다.
>
> ### 직전 라운드 (2026-08-11 · 리빙 문서 동기화)
> - 🗄️ 🔴 **§S9의 4행이 *은퇴한 키*의 세팅 절차를 가르치고 있었습니다 — `alignment.sides`.** `db1ee42`가 후보의 두 번째 축을 **면에서 걸음의 시작 모서리로** 바꾸면서 그 키를 읽는 코드가 사라졌습니다(HEAD 실측 `load_alignment_sides` 0건). **선언하면 조용히 무시되고 경고도 없습니다** — 「썼는데 아무 일도 안 일어난다」의 전형이라 **행을 지우지 않고 은퇴 표시**했습니다. 키 상세는 [config/map_overlay_config](./config/map_overlay_config.md), 후보 공간의 정본은 [spec/MAP_ALIGNMENT_SPEC §2.4](../spec/MAP_ALIGNMENT_SPEC.md).
>
> ### 직전 라운드 (2026-08-06 · 리빙 문서 동기화)
> - **§3에 시나리오 S9 신설 — 「맵 정렬 화면(좌표계 확정)을 켤 때」.** 그 화면을 켜는 선언이 **config 파일 셋에 흩어져** 있었고 어느 문서도 한자리에 모으지 않았습니다. 하나만 빠져도 화면은 **에러를 내지 않고** 비거나 「순위 없음」만 냅니다. ⚠️ **선언만 다룹니다** — 조작 절차는 화면이 매일 바뀌는 중이라 일부러 안 적었습니다. 🔴 **실측 결과 이 저장소의 `alignment: true`가 정렬하지 않는 규칙에 붙어 있습니다**(총괄 판정 대상).
> - 🔴 **§4.2-bis의 「`enrichment` 도메인 *하나*가 등록돼 있습니다」가 거짓이 됐습니다** — `enrichment` · `virtual_join` · `notation` 셋이고, **고치면서 수를 다시 적지 않았습니다**(그 자리가 낡은 방식이 정확히 그것이었습니다).
> - 🔴 **운영자가 복사해 붙이는 `curl`의 포트가 `8000`이었습니다** — 런처가 띄우는 포트는 **8080**입니다. 같은 오타가 [config/enrichment_rules](./config/enrichment_rules.md)·[config/transfer_plan_config](./config/transfer_plan_config.md)에도 있었고 함께 고쳤습니다. `:8000`은 `uvicorn`을 직접 쳤을 때의 기본값이라 **선언 문제로 오독되기 딱 좋은 실패**입니다.
>
> ### 직전 라운드 (2026-08-04 · 리빙 문서 동기화 `ce5ccb8..f7ac005`)
> - 🔴 **`notation_rules.json`의 모델이 뒤집혔습니다(`8d306a5`) — §1 표의 그 행과 §5.6-quater를 전부 다시 썼습니다.** `92b8d6f`가 출하한 **파생 컬럼 `<컬럼>_norm`**은 **아무도 소비하기 전에** 철회됐고, 지금 선언은 「이 컬럼의 표기가 정규화됐다」 한 줄이며 **아무것도 저장하지 않습니다**(소비자가 조회 시점에 비교의 양쪽을 접습니다). **「층 셋」·재파생 스크립트·쓰기 거부 400은 전부 소멸했습니다.** 🔴 **접힌 키는 함수 인덱스를 요구합니다** — 평범한 UNIQUE는 접힌 키의 유일성을 증명하지 못합니다(정확성 문제). 정본은 [config/notation_rules_config](./config/notation_rules_config.md).
>
> ### 직전 라운드 (2026-08-04 · 앞선 배치)
> - **새 config 파일 `notation_rules.json`**(`92b8d6f`) — 위 항목이 대체했습니다.
> - **`table_config.json`에 새 키 `version_column`**(`092b83f` — 버전 게이트). 「같은 키의 행이 항상 최신본이어야 한다」를 선언하면 **기계가 기존 행을 덮어쓸 때 버전이 더 클 때만** 반영합니다. **오늘 선언한 테이블은 없어 전부 무동작**이고, 켜는 것은 운영자입니다. 절차·판정표·로그 읽는 법의 정본은 [config/table_config §7](./config/table_config.md).
> - 🔴 **§6에 함정 P 추가** — 버전 게이트를 건 테이블이 동시에 **체인/결손보정 타깃**이면 그 파생 쓰기가 전부 거절됩니다. 선언 **전에** 확인해야 하고, 확인하는 한 줄은 그 문서 §7.2에 있습니다.
>
> ### 직전 라운드 (2026-08-02)
> - **짝 문서 신설: [CONFIG_ROLLOUT_GUIDE](./CONFIG_ROLLOUT_GUIDE.md)** — 이 문서가 「무엇을 설정하나」의 **지도**라면 그쪽은 「빈 환경에 선언 한 벌을 **어떤 순서로** 올리고 **각 단계가 먹었음을 어떻게 증명**하나」의 런북입니다. **§4의 리로드 매트릭스·watcher 발화 조건·물리 검증은 계속 이 문서가 정본**이고 런북은 링크만 합니다 — 그쪽에 사본을 만들지 마십시오.
> - 🔴 **§4.4의 「`on_moved`+`on_created`도 처리한다」가 여전히 옳다는 것을 재확인했습니다**(`46a67c7`, 2026-07-29). 「config watcher는 원자적 쓰기를 놓친다」는 서술이 아직 돌아다니는데 **현 트리에서 거짓**입니다. 인용 전 §4.4를 보십시오.
> 
> 🔴 **이 헤더에 라운드를 쌓지 마십시오.** 이전 기록은 [`docs/history/`](../history/)에 있습니다.

**이 문서의 역할 = "설정 관점의 지도".** "무엇을, 어디에, 어떤 순서로 넣고, 어떻게 검증하는가"에만 답합니다.
**파일 하나를 실제로 세팅하는 절차·키 사전은 [config/ 폴더](./config/README.md)** (파일당 가이드 1개)로,
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
| **`database.json`** | DB 접속 정보(이름·비번·호스트) — 우선순위: 환경변수 `DATABASE_URL` > 이 파일 > 코드 기본값 | 사용자 | ignored (`.sample` 有) | **재기동**(핫리로드 없음 — 커넥션 문자열) | 전 프로세스 + 런처(DB 도달성 프로브) |
| **`ontology_mapping.json`** | 그래프 노드/엣지 매핑 v2 (`description` 필수) | 사용자 | ignored (`.sample` 有) | `POST /admin/reload-configs` (웹서버 캐시 무효화) | web, graph_sync_worker |
| **`enrichment_rules.json`** | 결손 보정 워크리스트 규칙(`decision_key`/`target_fields`/`reference_views`) + **① 자동 확정 선언**(`reference_views[].candidate_for`, 규칙별 `auto_confirm` — 기본 OFF, 2026-07-30) | 사용자 | ignored (`.sample` 有) | 조회 API는 즉시 / 체인 파생 룰은 `reload-configs` | web, chain_ingestion_worker |
| **`virtual_join_rules.json`** | **저장하지 않는 조인 선언**(`left_table`/`right_table`/`join_key`/`expose`) + **팬아웃 가드**. 🔴 **승인 조건은 하나 — 조인 키를 덮는 유효한 UNIQUE 인덱스**(사용자 판정 2026-07-31 「인덱스 없으면 거절해」). 인덱스는 config가 아니라 DB에 살아 영속이므로 등급·스냅샷·예산이 없다. 무효(`indisvalid=false`)·부분(`indpred`)·표현식(`indexprs`) 인덱스는 불인정. 거부는 만들어야 할 `CREATE UNIQUE INDEX` DDL을 함께 준다. 실측 근거: 같은 두 테이블을 `(lot,slot,x,y)`로 이으면 103,040행, `(lot,slot)`로 이으면 132,715,520행. ✅ **조인은 실행된다**(`d70a33d` — `server/virtual_join_executor.py`가 읽기 경로에서 `expose` 컬럼을 붙인다). 🔴 **`expose` 이름이 왼쪽과 겹치는 것은 거부가 아니다** — **왼쪽이 비었을 때만 채우고**(있으면 그대로, 둘 다 없으면 `미상`) 조인이 만든 셀에만 `sources.virtual_join`이 붙는다. 왼쪽에 실재하지 않는 컬럼(`virtual_only`)으로 가는 쓰기는 `crud.apply_batch_updates` 첫 문장에서 400으로 거부되고, 겹친 컬럼은 **의도적으로 계속 쓸 수 있다**(그 쓰기가 조인 값을 고치는 유일한 방법). ✅ **가상 전용 컬럼도 그리드에 뜬다**(`9200f20`+`4b50135` — `/schema`가 **별도 키 `virtual_columns`로** 알리고 그리드가 저장 컬럼 뒤에 덧붙인다. `columns`에는 합치지 않는다). ✅ **검색·필터·CSV 추출이 화면과 같은 값을 본다**(`cd3e0f4` — 해석값이 SQL 표현식이 되어 내려간다. `미상` 행은 `equals 미상`으로 찾는다) ✅ **`number` 타입 컬럼도 노출 가능**(2026-08-04 N7 — 이전에는 PostgreSQL 타입 오류로 조회가 500이었다. 비교 철자는 INT 접기: `3.0`은 `3` → [config/virtual_join_rules §4-ter](./config/virtual_join_rules.md)). ⏳ 미해결 1건(사람이 비운 셀과 원래 빈 셀이 구별 안 됨 — 사용자 판정으로 기록된 성질)은 [config/virtual_join_rules §9](./config/virtual_join_rules.md)가 단독 소유 → [§4-bis](./config/virtual_join_rules.md) | 사용자 | ignored (`.sample` 有) | 조회 즉시(승인 선언은 짧은 TTL 캐시 + `reload-configs` 즉시 무효화. 그 훅이 없는 워커는 TTL이 지나야 바뀐다) | web(선언 검증·보고 **+ 읽기 경로 실행**) · **쓰기 거부는 `apply_batch_updates`를 지나는 전 프로세스**(web·watcher·chain) |
| **`notation_rules.json`** | **표기 정규화 선언**(`columns: {테이블: {컬럼: true}}` + 규칙 `separator`/`case`/~~`zero_pad`~~). 「이 컬럼의 **표기가 정규화됐다**」 한 줄이고, **아무것도 저장하지 않는다** — 소비자가 **조회 시점에 SQL에서 비교의 양쪽을** 접는다. 🔴 **[2026-08-04 `8d306a5` 정정] 파생 컬럼 `<컬럼>_norm` 모델은 철회됐다** — 이 칸은 하루 전 그것을 계약으로 적고 있었다. 함께 소멸: `table_config` 파생 컬럼 단계 · `display_columns` 가시성 · 쓰기 거부 400 · 거절 `would_rewrite_raw`/`key_column`(둘 다 **쓰기**를 막던 것이라 주어가 없어졌다) · 재파생 스크립트(**삭제**). 🔴 **어느 한쪽만 선언해도 조인은 양쪽이 접힌다**(`join_pair_rules` — 한쪽만 접으면 이미 맞고 있던 매치를 조용히 잃는다. 실측: `dt_log.core_lot` 병합군 15, `core_wafer_map.core_lot` 0). 🔴 **접힌 키는 함수 인덱스를 요구한다** — 평범한 UNIQUE는 접힌 키의 유일성을 **증명하지 못한다**(정확성 문제이지 성능 문제가 아니다) → [config/virtual_join_rules](./config/virtual_join_rules.md). 켠 다음 볼 것은 **병합군**(`GET /admin/config/notation/preview`). 맵 키는 **안 건드린다**(여전히 원본) → [config/notation_rules_config](./config/notation_rules_config.md) | 사용자 | ignored (`.sample` 有 — **출하 시 `"columns": {}`로 무동작**) | 저장 후 **TTL 5초**(watcher 대상 아님) 또는 `POST /admin/reload-configs` | 접기는 **조회 경로**(web — virtual join) · 보고는 web |
| **`chain_rules.json`** | 체인 인제션 룰(trigger→target→mapper) | 사용자 | ignored (`.sample` 有) | `POST /admin/reload-configs` | chain_ingestion_worker, web(조회) |
| **`auto_update_control.json`** | 수집기 비활성 목록(= active 토글) | 사용자 (**API로 쓰기 권장**) | ignored (`.sample` 有) | 즉시(매 사이클 재조회) | run_auto_update, web |
| **`ingestion_settings.json`** | 인제션 런타임 노브 — `heavy_file_mb`(P1 heavy 레인 임계, 기본 10) · `dedup_by_signature`(P2 동일 파일 skip, 기본 true) · `resume_from_checkpoint`(P2 오프셋 재개, 기본 true) · **`dedup_by_path_stat`**(tier-1 경로+`(mtime,size)` 스킵 — 해시 없이, 기본 true. 실측 22,626파일에서 39.4초→1.0초) · **`archive_processed_files`**(처리된 파일을 `archives/`·`err/`로 **옮길지**, 기본 true=종전. `false`면 파일이 제자리에 남고 재처리 방지·실패 기록을 전부 원장이 든다 — 🔴 마이그레이션 `add_ingestion_ledger_path_stat.sql` 선행) · `flatten_nested_dirs`(폴더 드롭 처리, 기본 true — 🔴 **`600b49d`에서 이름은 그대로 뜻만 바뀜**: 승격 → **제자리 적재**. §5.6) · `auto_register_map_meta` · `enrichment_auto_confirm_*` | 사용자 | ignored (`.sample` 有) | 즉시(**다음 파일 / 다음 폴더 트리거부터**) | watcher |
| **`map_overlay_config.json`** | **범용 맵 오버레이** — `table_bindings`(맵 좌표 컬럼, 미선언 시 `table_config`에서 **키마다** 유도 — 2026-08-11 `68db020`부터 관례 상수 폴백 삭제, 생략한 키는 이름을 대며 거절하거나 파생된 값으로 상속) · `paint_lock`(페인트 잠금 **정본**) · [U6] `default_legend`(레지스트리 무행 맵의 기본 legend, 미선언=없음) · `value_column_candidates`(값 컬럼 탐지 순서, 미선언=문서화 기본) — 뒤 둘은 `GET /api/maps/paint-rules`로 서빙(클라 하드코딩 금지) · **[F5] `preset_routing`**(로드 시 프리셋 라우팅 — `GET /api/maps/preset-routing`로 서빙, 미선언=라우팅 없음). ~~`align_overrides`~~는 **2026-07-27 폐지**(§5.8-bis) | 사용자 | ignored (`.sample` 有) | 즉시(**요청당 1회 스냅샷**) | web |
| **`maps.json`** | 웨이퍼 물리 규격/오프셋 **프리셋** | 사용자 (**API로 쓰기**) | ignored (`.sample` 有) | 즉시(요청마다 디스크 읽기) | web |
| **`bonding_plan_config.json`** | M1 본딩 실험계획 — 역할(role)→실테이블 바인딩 | 사용자 | ignored (`.sample` 有) | 즉시(**요청당 1회 스냅샷**) | web |
| **`transfer_plan_config.json`** | M2 Universal Transfer Plan — stage 선언 + plan_store | 사용자 | ignored (`.sample` 有) | 즉시(**요청당 1회 스냅샷**) | web |
| **`effort_metric.json`** | **V1 정본 계기** — 상호작용 점수 배점(`weights.key/mouse/nav/nav_preserved`, 기본 1/3/5/**0**) + `context_preserving_transitions`(유지 전이 허용목록, **기본 빈 배열 = 모든 이동이 상실로 계산됨**, 정확 일치·**와일드카드 거절**). `GET /api/effort/config`로 서빙(클라 하드코딩 금지) | 사용자 | ignored (`.sample` 有) | 즉시(다음 조회부터, 집계는 60초 캐시) | web |
| **`suggest_config.json`** | **입력 제안(고유값 조회) 노브** — 목록 길이(`default_limit`/`max_limit`)·최소 접두 길이·프로브 예산·타임아웃·**느린 응답 경보(`slow_warn_ms`)** + **접두 인덱스 대상 선정**(`index_min_rows`/`index_columns`/`index_exclude`). 조회 노브는 즉시, `index_*`는 **`setup_db_performance.py` 재실행이 유일한 반영 경로** | 사용자 | ignored (`.sample` 有) | 조회 노브 = 즉시(**요청당 1회 스냅샷**) / `index_*` = 스크립트 재실행 | web + `scripts/setup_db_performance.py` |
| **`audit_history_config.json`** (2026-08-11 신설) | **감사 이력 조회 상한** — 행/셀 이력 페이지 크기(`default_limit`/`max_limit`) + **전역 「최근」 패널 discovery 걸음의 하드 천장**(`recent_max_scan_rows`/`recent_scan_chunk_rows`/`recent_logs_per_group`/`recent_refresh_max_delta_rows`). `audit_cache`가 `audit_history.load_config()`를 재사용 — 두 번째 로더가 아니다. 🔴 **인덱스 없이는 이 config만으로 아무것도 안 빨라진다** — §5.6-quinquies 참조 | 사용자 | ignored (`.sample` 有 — ⚠️ **`recent_*` 넷이 아직 안 실려 있다**, §5.6-quinquies) | 즉시(**요청당 1회 스냅샷**) | web |
| **`ledger_config.json`** (2026-08-13 신설 · `f896020`) | **정준 원장 번역기 선언 — 소스 하나당 항목 하나.** 🔴 **`occurred_at_*` 셋은 필수**이고 하나라도 빠지면 번역기가 **그 소스를 통째로 거절**합니다(도착 시각으로 대신하지 않습니다). 🔴 **`occurred_at_timezone`은 「이 소스의 naive 텍스트가 무슨 뜻인가」의 선언**입니다 — 2026-08-13 제품 소유자 판정으로 `Asia/Seoul`(fab는 현지시간, ISO 8601 `T`). **자기 오프셋을 가진 문자열은 이미 자기 순간을 말했으므로 이 존을 덧씌우지 않습니다.** `vocabulary`는 이벤트 타입별 관례 선언(`lineage`·`slot_pairing`·`emit_*`)이고 **`source_translator_ver`에 해시되어** 원자마다 「어느 관례가 만들었는가」가 남습니다. 그 밖에 `batch.molecules_per_transaction`(**사건 «전체» 단위 — 절대 분수 아님**) · `partitioning.interval`(월) · `lag.probe_interval_seconds` | 사용자 | ignored (`.sample` 有) | 번역기 실행 시 재독 | `server/ledger/*`(백필·번역기). ⚠️ **웹서버·워커는 부팅 시 이것을 읽지 않습니다** |
| `scheduler_status.json` | 스케줄러→UI 텔레메트리 | **시스템(자동 생성)** | ignored | — | run_auto_update가 씀, web이 읽음 |
| `supervisor_status.json` | **[운영]** 자식 프로세스 감시 상태(자식별 state·재시작 횟수·실패 사유, `updated_at`=감시자 생존 신호) | **시스템(자동 생성)** | ignored | — | `run_decoupled_app`이 씀, `/health`가 읽음 |
| `worker_heartbeats/<worker>.json` | **[운영]** 워커 진행 박동(`watcher`·`chain`·`graph`·`scheduler` — **수를 적지 않습니다**) | **시스템(자동 생성)** | ignored | — | 각 워커가 씀, `/health`가 읽음 |
| **`<이름>_<yymmdd>.json.bak`** | **[운영] C3 주간 config 스냅샷** — 롤백 단계 2의 복원 원본 | **시스템(자동 생성)** | ignored | — | `run_auto_update`가 씀, `/health`가 신선도를 읽음 |
| `*.json.bak.<ts>`, `*.bak-<ts>`, `*.v1.bak` | 설치 이력·수동 백업 잔재 | 스크립트/사용자 | ignored | — | 아무도 안 읽음 |

> `table_config.json.bak_enrich` · `ontology_mapping.json.v1.bak` 같은 파일은 **코드가 읽지 않습니다**. 파일명이 정확히 일치해야만 로드됩니다.

#### `.bak`가 세 종류다 — 날짜 위치로 구분한다

```
table_config_260728.json.bak          ← ① 주간 스냅샷 (날짜가 확장자 앞)
table_config.json.bak.20260727-225922 ← ② 제품 테이블 설치 이력 (날짜가 확장자 뒤)
ontology_mapping.json.v1.bak          ← ③ 손으로 남긴 잔재 (날짜 없음)
```

**롤백 때 되돌릴 원본은 ①뿐입니다.** ②는 `install_product_tables.py`가 실행된 순간에만 생기므로 **배포 이력이 아니라 설치 이력**이고, 어드민 UI나 에디터로 한 수정은 거기에 없습니다. 판단 기준 전문은 [ROLLBACK_PROCEDURE §3.1 / §3.1-bis](ROLLBACK_PROCEDURE.md).

①의 규격 — 주 1회 전량, 파일당 1개, **1개월 FIFO**(최신 4개는 나이 무관 보존), 같은 날 두 번째는 내용이 다를 때만 `_260728b`로 글자가 붙습니다(**덮어쓰지 않음**). `yymmdd`가 사전순 = 시간순이라 `ls`의 마지막 줄이 최신입니다.

```bash
conda run -n assy_manager python server/scripts/backup_config.py list|check|snapshot
conda run -n assy_manager python server/scripts/backup_config.py restore <파일> --yes
```

> **대상 선정 규칙**: `server/config/` 바로 아래에서 이름이 정확히 `.json`으로 끝나는 파일 전량. 그래서 `.sample`·`.bak` 계열이 자동으로 빠지고(백업의 백업이 생기지 않음), **새 config 파일은 등록 없이 자동 포함**됩니다. 예외는 산출물인 `scheduler_status.json`·`supervisor_status.json` 2개뿐입니다.

> ⚠️ **백업이 멈추면 `/health`가 말합니다** — `checks.config_backup`이 `missing`/`stale`이면 `problems`에 뜨고 상태가 `degraded`(HTTP 200 유지)가 됩니다. 판정 근거는 작업이 자기 손으로 쓴 "마지막 실행" 기록이 아니라 **디스크의 스냅샷 파일 자체**입니다.

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
| 환경변수 | `DATABASE_URL`(기본 `postgresql://postgres:admin@localhost:5432/assy_manager`), **`ASSY_DATA_ROOT`**(config·워크스페이스·프로세스 로그의 단일 이동점, 미설정 시 `server/`), `ASSY_API_PORT`(런처가 띄우는 uvicorn 포트, 기본 8080), `DECOUPLED`, `TESTING`, `API_BASE_URL`(기본 `http://127.0.0.1:8080`), `GRAPH_SYNC_PORT`(8090), `GRAPH_MATERIALIZER_ENABLED`(true), `NEO4J_*`, `ASSY_API_BASE`, **`ASSY_ADMIN_TOKEN`**(어드민 공유 토큰 — 미설정 시 코드 쓰기·즉시실행 2개 라우트가 503, 나머지 `/admin/*`은 열림 → [DEPLOY_SETUP §1-4](./DEPLOY_SETUP.md). 기동 배너의 `token fingerprint`로 프로세스 간 일치를 눈으로 확인한다), **`NO_PROXY`**(우리 변수는 아니지만 운영에서 반드시 본다 — 사내 프록시가 `127.0.0.1` 요청을 가로채 **403**을 돌려준 장애가 있었다. 코드 측은 프로세스 간 호출에서 프록시를 아예 참조하지 않도록 막았고, 셸에는 `NO_PROXY=127.0.0.1,localhost`를 권장한다 → [DEPLOY_SETUP §1-5](./DEPLOY_SETUP.md)) | **전부 재기동 필요** (import 시점 1회 읽음. ⚠️ 예외: `ASSY_ADMIN_TOKEN`은 요청마다 다시 읽히지만, 프로세스 환경을 바깥에서 바꿀 수는 없으므로 **운영상으로는 동일하게 재기동이 필요**하다) |
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
| 1 | `server/config/table_config.json`에 테이블 항목 추가(§5.1 스니펫). **비-ASCII/공백 컬럼명은 피할 것** | JSON 파싱 확인 — 파싱 실패는 이제 **로그로 드러나고 기동을 막습니다**(§6-A) |
| 2 | 저장 방식은 무관 (in-place / 같은 폴더 temp+rename / **다른 폴더** temp+rename 모두 watcher가 발화. 연속 저장도 버려지지 않음 — 반영은 마지막 쓰기 후 약 1초 → §4.4·§6-B) | — |
| 3 | 물리 테이블 생성 확인 | `psql -U postgres -d assy_manager -c "\d <table>"` 또는 `SELECT column_name FROM information_schema.columns WHERE table_name='<table>'` |
| 4 | 안 만들어졌으면 `POST /admin/reload-configs` (신규 CREATE 전용) | 다시 3번 |
| 5 | 워크스페이스 자동 생성 확인 — `server/ingestion_workspace/<table>/{raws,archives,err,auto_update,scripts,config}` | `GET /admin/file-ingestion/workspaces` |
| 6 | 폴더명 ≠ 테이블명이면 `table_config` 항목에 `"workspace_name": "<폴더명>"` 추가 | 별칭이 **다른 실존 테이블명과 동명**이거나 **복수 테이블이 같은 별칭**을 쓰면 무시 + ERROR 로그 |
| 7 | (선택) 커스텀 파서 불필요 → 표준 파서가 헤더 일치 CSV/TSV/TXT를 그대로 적재. 커스텀 변환에 의존한다면 `"std_parse": false` 명시 | [INGESTION_GUIDE §1.5](./INGESTION_GUIDE.md) |
| 8 | (선택) 주기 수집 필요 → S3 |
| 9 | (선택) 그래프에 올릴 것 → S4 |
| 10 | (선택) 파생/보정 필요 → S6·S7 |
| 11 | 실제 파일 1건을 `raws/`에 넣어 왕복 검증 | `GET /admin/file-ingestion/logs` + `GET /tables/<table>/data` |
| 12 | (선택) 같은 키가 **항상 최신본**이어야 하고 파일에 그것을 말하는 컬럼이 있다면 → `"version_column"` 선언. 🔴 **선언 전에 파생 타깃 확인 한 줄을 먼저** | 절차·확인 명령·판정표는 [config/table_config §7](./config/table_config.md) · 함정은 §6-P |

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
| 6 | `plan_store.registry` — 계획 저장 테이블 바인딩. **M2.6(2026-07-27)부터 테이블은 `map_split_registry` 하나**이고, **[ZONE 2026-07-28] 필수 역할키는 `ref_table`·`map_key`·`value`·`stack`·`mat_1h`·`mat_mid`·`mat_top`**입니다(코드 정본 `transfer_plan.REGISTRY_ROLES`). v1 역할 `plan`(헤더)·`map`(계획 맵 사본)·`doe_layer`에 이어 **v2의 `doe`·`doe_source`도 폐기**됐습니다 — 계획 정체성이 `(ref_table, map_key)`, 즉 *지금 열어 편집 중인 그 맵*이고 페인팅 결과가 곧 그 맵 자신의 셀이기 때문입니다. **zone 역할이 하나라도 빠지면 `validate`는 조용히 통과시키지 않고 404를 냅니다.** 🗄️ `bands`는 **선택**(폐기·읽기 전용) — 없어도 200이며, 폐기 계획을 못 읽을 뿐입니다(§5.8) |
| 7 | `plan_store.material_identity` — 자재 ID 원문을 `(lot, slot)`으로 푸는 **선언된 규칙**(`compose: ["lot","slot"]` + `separator`). 서버는 자재 문자열을 파싱하는 관례를 코드에 두지 않습니다. 미선언이면 모든 자재가 `source_unresolved`가 되고 계획은 `unverified`로 남습니다 |
| 8 | 검증: `GET /api/transfer-plan/stages` → `GET /api/transfer-plan/validate?ref_table=&map_key=` → `GET /api/transfer-plan/source-summary` |

> **stage는 고르는 것이 아니라 유도됩니다(v2).** `stages.*.target_map.table`의 역인덱스이므로 `bonding_map`을 열면 `bonding`, `dt_map`을 열면 `dt`입니다. 어느 stage의 `target_map.table`도 아닌 맵은 `stage_unknown` 경고 + `status: unverified`로 표면화되며 **404가 아닙니다**(임의의 맵도 편집 대상으로 열 수 있어야 하므로).

> **align 실패는 M1·M2 모두 "명시 실패"입니다.** 격자 규격(`wafer_map_metadata`)을 못 찾아 변환을 만들 수 없으면, **raw 좌표로 조용히 계산하지 않고** 해당 role 상태를 `connected(align_unavailable)`로 바꾸고 **카운트를 0으로** 둡니다. (2026-07-27부터 `align` **선언 자체가 없으므로**, 이 상태의 원인은 항상 "메타 미등록/조회 실패" 한 가지입니다.)
> 따라서 상태별 해석은 이렇습니다 — **`not_declared`** = 그 역할 **키 자체가 없음**(= 「우리 현장엔 그런 표가 없다」는 선언. 강등이 아니며 가용은 그 감산 없이 **숫자로** 나갑니다. 2026-08-04 신설, §5.8) · `missing` = **선언은 있는데** 바인딩이 깨짐(테이블 부재·오타·필수 컬럼 결측) · `connected(align_unavailable)` = 바인딩은 됐는데 격자 규격이 없음(→ `wafer_map_metadata` 행부터 확인) · **`connected(count_only)`** = `transfer_log` 또는 self-frame fail 원천에 쓸 만한 x/y가 없어 카운트만(→ x/y 컬럼 바인딩 확인) · **`connected(column_unresolved:<roles>)`** = 선언한 컬럼이 모델에 없음(→ config의 컬럼명 오타 확인. 2026-07-28 신설, §5.8) · `connected` = 정상.

### S7. 결손 보정(enrichment) 규칙 추가할 때

| # | 할 일 |
|---|---|
| 1 | `enrichment_rules.json`에 `{규칙명: {...}}` 추가 (§5.3). 루트는 **객체**여야 함 |
| 2 | `source_table`·`derived_table` 모두 `table_config.json`에 등록돼 있어야 함 (아니면 그 규칙 거부) |
| 3 | `derived_table`은 `decision_key`를 `composite_key_source`로 갖는 키 계약을 만족해야 함 |
| 4 | `reference_views[].query`는 **서버에만 존재**하며 클라이언트에 노출되지 않습니다. 파라미터는 `:decision_key_컬럼` 바인딩만 허용 |
| 5 | `POST /admin/reload-configs` — 체인 dedup 룰 자동 파생 + 온톨로지 `RESOLVED_AS` 자동 승격 |
| 6 | 검증: `GET /enrichment/rules` (공개 메타), `GET /enrichment/rules/{name}/references/{index}?params=...` |
| 7 | (선택 · 2026-07-30 ①) **후보가 1개인 항목의 확인을 없애려면** — 후보를 나르는 뷰에 `candidate_for: {target: 뷰_컬럼}`을 선언하고 규칙에 `auto_confirm: true`. **선언 없는 뷰는 표시 전용**이고 컬럼명 유추는 하지 않습니다. 켜기 전에 반드시 측정: `enrichment_insights.py confirm <규칙> --ignore-knob`(아무것도 쓰지 않음) → [config/enrichment_rules §7](./config/enrichment_rules.md) |
| 8 | (선택) **결손 원인 분류·룰 승격 제안**(읽기 전용): `enrichment_insights.py classify <규칙>` / `propose <규칙>` — 사람이 갚고 있는 파이프라인 버그와 진짜 일감을 분리하고, 반복된 판단을 규칙 제안으로 뽑습니다 |

상세: [ENRICHMENT_QUEUE_SPEC](../spec/ENRICHMENT_QUEUE_SPEC.md)

### S8. 체인 규칙 추가할 때

| # | 할 일 |
|---|---|
| 1 | `server/mappers/<module>.py`에 맵퍼 함수 작성 |
| 2 | `chain_rules.json`의 `rules[]`에 `{name, trigger_table, target_table, mapper_module, mapper_function, is_batch, enabled}` 추가 |
| 3 | `POST /admin/reload-configs` — `mappers.*` 모듈 캐시 무효화 + 워커 룰 재로드 |
| 4 | 검증: `GET /admin/chain/rules`, `GET /admin/mappers/list` |

상세: [chain_ingestion_guide](./chain_ingestion_guide.md)

### S9. **맵 정렬 화면(좌표계 확정)을 켤 때** (2026-08-06 신설)

> **왜 이 절이 생겼나:** `map_editor2.html`(맵 정렬 화면)은 조작자가 **처음부터 끝까지 쓰는 화면**이 됐는데, 그것을 켜는 데 필요한 선언이 **config 파일 세 개에 흩어져** 있고 어느 문서도 한자리에 모아 놓지 않았습니다. 하나라도 빠지면 화면은 **에러를 내지 않고 비어 있거나 「순위 없음」만** 냅니다 — 그리고 그것은 config 공백이지 결함이 아닙니다.
> ⚠️ **이 절은 *선언*만 다룹니다.** 화면 자체의 조작 절차(무엇을 어느 순서로 고르는가)는 **아직 문서가 없습니다** — 화면이 매일 바뀌는 중이라 절차서를 여기 적으면 그 자리에서 낡습니다. 설계 계약의 정본은 [spec/MAP_ALIGNMENT_SPEC](../spec/MAP_ALIGNMENT_SPEC.md), 층 경계는 [architecture/frontend §4.2](../architecture/frontend.md)입니다.

| # | 어느 파일 · 어느 키 | 없으면 화면이 어떻게 되나 |
|---|---|---|
| 1 | `enrichment_rules.json` → `<규칙>.alignment: true` (**JSON boolean만**, `"true"`·`1`은 선언이 아님 — `map_push_ok`와 같은 규율) | **화면이 아무 규칙도 고르지 못해 통째로 빕니다.** 🔴 **이 표시가 붙어야 하는 규칙은 「무엇을 확정하는가」로 고릅니다** — `target_fields`가 **프레임**인 규칙입니다. 이름에 `frame`이 들어간다는 것은 근거가 아니고, 서버는 이 값을 **유도하지 않습니다**(§5.3 · [config/enrichment_rules](./config/enrichment_rules.md)) |
| 2 | 같은 규칙의 `decision_key` · `target_fields` · `source_table` | 결정 단위와 쓰는 자리가 정해지지 않습니다. 확정은 **단위 전체에 대해서만** 성립하므로 `decision_key`가 덜 채워진 요청은 400으로 거절됩니다 |
| 3 | `map_overlay_config.json` → `alignment.min_margin_dies` · `alignment.min_discriminating_dies` | **순위는 나옵니다 — 다만 「잠정」이라는 표를 달고 나옵니다**(2026-08-06 제품 소유자 지시로 뒤집힘). 미선언이면 서버가 **개발 기본값 1/1**로 매기고, 판정에 `ruling.thresholds_defaulted`(사칭된 키 목록)와 `ruling.provisional_text`(`잠정 순위 - 판정 기준값 미선언 · 기본값 1`)를 싣습니다. 🔴 **여전히 0으로 접지는 않습니다** — 0이면 「구별 못 함」이 「자신 있는 1등」이 되고, 1은 격차 비교가 이미 `max(1, ...)`으로 깔고 있는 바닥이라 **선언 `{1,1}`과 한 후보도 다르게 판정하지 않습니다**. 즉 미선언이 바꾸는 것은 「무엇이 이기는가」가 아니라 「이겼다고 말해도 되는가」뿐입니다. 🔴 **잠정 순위를 그대로 확정하지 마십시오** — 값은 **쓰는 기준 맵의 실제 분해능에서 다시 유도**하십시오(옮겨 적지 마십시오). 종전 사유 코드 `no_thresholds`는 **서버가 더 이상 내지 않습니다** |
| ~~4~~ | 🗄️ **[2026-08-11 은퇴] ~~`map_overlay_config.json` → `alignment.sides`~~** | **선언하지 마십시오 — 읽는 코드가 0건입니다**(`db1ee42`). 후보의 두 번째 축이 **면에서 걸음의 시작 모서리로** 바뀌면서 이 키와 그 로더가 함께 사라졌습니다. 선언하면 **조용히 무시**됩니다(경고도 없습니다). 지금 후보는 **4회전 × {좌상단, 우상단} 시작 · 면은 전부 `front`** → [spec/MAP_ALIGNMENT_SPEC §2.4](../spec/MAP_ALIGNMENT_SPEC.md) · 행 상세 [config/map_overlay_config](./config/map_overlay_config.md) |
| 5 | (선택) `map_overlay_config.json` → `alignment.index.*` | 순번 축이 **수치는 실어 보내되 순위를 가져가지 않습니다**(`ruling.index_axis='reported'`). 🔴 **위 3의 키와 일부러 공유하지 않습니다** — 다른 문제를 쫓다가 저쪽을 낮추는 조작이 이 축의 안전망까지 걷어 가면 안 되기 때문입니다(2026-08-05에 실제로 20→1로 내려간 적이 있습니다) |
| 6 | `map_overlay_config.json` → `table_bindings.<맵테이블>.columns.{x,y,val,key_columns}` | 좌표 컬럼 드롭다운에 제안이 안 뜹니다. ⚠️ **정렬 화면에서 이 값은 *제안*입니다** — 조작자가 확인하거나 바꿔야 「선언」으로 올라갑니다(§5.8-bis) |
| 7 | `table_config.json` → `<맵테이블>.map_key_columns` | 그 테이블이 **「맵이다」로 인정되지 않아** 대상 테이블 목록에 없습니다. `table_bindings`에 좌표를 적어도 이 줄을 대신하지 못합니다(§5.1의 그 행) |
| 8 | 기준(유효 다이) 맵 — `table_config.json`의 `valid_die_ref` 선언 + 그 맵의 **물리 규격 행** | 기준을 안 고르는 것 자체는 **정상**입니다(그러면 소스 맵이 자기 `valid_die_ref`를 따라갑니다). 그러나 **규격 행이 없는 소스 맵**을 채점하려면 기준 맵의 물리 규격이 선언돼 있어야 빌려 올 것이 있습니다 — 없으면 서버가 「고쳐야 할 것은 소스 맵이 아니라 **기준 맵 한 장**입니다」라고 이름을 대며 거절합니다 |
| 9 | `table_config.json` → `wafer_map_metadata` 선언 | 확정이 **좌표계를 그 표에 되쓰는 절반**(2026-08-06 [D7])이 조용히 멈춥니다 — 확정 기록은 남고 로그 경고만 뜹니다 |

**켠 뒤 확인:** `GET /enrichment/rules`가 그 규칙에 `alignment`를 실어 보내는지 → 화면의 대상 테이블 드롭다운이 채워지는지 → 워크리스트에 단위가 뜨는지. **셋 중 어디서 멈추는지가 위 표의 어느 줄인지를 말해 줍니다.**

> 🔴 **실측 2026-08-06 — 이 저장소의 config는 1번이 어긋나 있습니다.** `alignment: true`가 **`dt_job_lot_slot_attribution`**(`decision_key: ["dt_job"]`, `target_fields: ["dt_lot_confirmed","dt_slot_confirmed"]` — **로트·슬롯 추론** 규칙이라 정렬하는 것이 없습니다)에 붙어 있고, 프레임 규칙 **`eqp_product_frame_attribution`**(`decision_key: ["dt_eqp","product"]`, `target_fields: ["core_frame","dt_frame"]`)에는 **없습니다.** 이 표시가 막으라고 만들어진 실패가 정확히 이것입니다. **config 수정은 이 문서의 소관이 아니라 총괄 판정 대상이므로 여기에는 사실만 적습니다.**

---

## 4. 적용·검증 규율 ★

### 4.1 리로드 매트릭스

| 변경 | 반영 방법 | 재기동? |
|---|---|---|
| `table_config` — **신규 테이블 추가** | config watcher(저장 방식 무관, §4.4) 또는 `POST /admin/reload-configs` | 불필요 |
| `table_config` — **기존 테이블에 컬럼 추가(ALTER)** | **config watcher 경로만** (`sync_dynamic_tables_schema`) | 불필요 — 마지막 쓰기 후 약 1초 |
| `table_config` — **컬럼 삭제 / 타입 변경** | 어떤 리로드 경로도 하지 않음 | **재기동 필요**(+ 필요 시 수동 마이그레이션) |
| `ontology_mapping` / `chain_rules` / `enrichment_rules` | `POST /admin/reload-configs` | 불필요 |
| `bonding_plan_config` / `transfer_plan_config` / `map_overlay_config` | 없음 — **요청마다 디스크 재읽기** | 불필요 |
| `ingestion_settings` | 없음 — **파일 이벤트마다 재읽기** | 불필요 |
| `effort_metric` | 없음 — 조회마다 재읽기(대시보드 집계는 60초 TTL 캐시 뒤) | 불필요 |
| `suggest_config` — **조회 노브**(`default_limit`·`min_prefix_length`·`timeout_ms`·`slow_warn_ms` 등) | 없음 — 요청마다 재읽기(**요청당 1회 스냅샷**) | 불필요 |
| `suggest_config` — **`index_*` 대상 선정** | 어떤 리로드 경로도 하지 않음 — `python server/scripts/setup_db_performance.py` **재실행이 유일한 반영 경로** | 불필요(단 스크립트 실행 필수) |
| `auto_update_control` | 없음 — 스케줄러가 매 사이클 재읽기 + API가 실시간 계산 | 불필요 |
| `maps.json` | 없음 — 요청마다 재읽기 | 불필요 |
| 워크스페이스 `config.json`(deprecated) | **핸들러 인스턴스 수명 동안 캐시** | 재기동 |
| 환경변수 전부 / CORS | — | **재기동** |

> 🚨 **반영 시점이 다르다는 것은 곧 롤백 순서 제약입니다.** "요청마다 재읽기"인 config는 즉시 반영되는데 코드는 재기동까지 고정이므로, **config를 먼저 바꾸면 코드만 되돌려서 복구할 수 없습니다** — config가 이미 새 형태라 옛 코드가 읽지 못합니다.
> 배포는 **코드 → 재기동 → config**, 롤백은 **config → 코드 → 재기동**입니다. 목록을 거꾸로 읽은 것이 아닙니다 — **재기동이 배포에서는 가운데, 롤백에서는 맨 마지막**입니다(재기동 시점에 config가 이미 옛 형태여야 정확한 상태로 올라옵니다).
> 전체 절차·실측 소요 시간은 **[ROLLBACK_PROCEDURE](./ROLLBACK_PROCEDURE.md)** (2026-07-28 격리 스택에서 드릴 실행). 실제 사례는 [DEPLOY_SETUP §7](./DEPLOY_SETUP.md).

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

> 🔴 **그리고 이 라우트는 무엇이 먹었는지 아무것도 돌려주지 않습니다.** `{"status":"success"}` 하나뿐입니다 — 캐시를 갱신했다는 뜻이지 여러분의 선언이 효과를 냈다는 뜻이 아닙니다. **§4.2-bis가 그 질문에 답하는 자리입니다.**

### 4.2-bis 「내가 쓴 게 먹었나」 — 선언의 효과 조회 (2026-07-30, [F9])

```bash
curl -H "X-Admin-Token: $ASSY_ADMIN_TOKEN" http://127.0.0.1:8080/admin/config/resolve
```

> 🔴 **[2026-08-06 정정] 종전 이 줄은 `localhost:8000`이었고 그 주소에는 아무도 없습니다.** 런처가 띄우는 uvicorn 포트는 **8080**(`ASSY_API_PORT`, §2 환경변수 행)이고, `:8000`은 `uvicorn main:app --reload`를 **직접** 쳤을 때의 uvicorn 기본값입니다 — 운영자가 이 줄을 복사해 붙이면 「연결 거부」를 받고 그것을 **설정 문제로 읽습니다.** 같은 오타가 [config/enrichment_rules](./config/enrichment_rules.md)·[config/transfer_plan_config](./config/transfer_plan_config.md)에도 있었고 함께 고쳤습니다.

서버가 선언을 모집단으로 나눠 돌려줍니다(**아래 표가 목록이고, 그 옆에 수를 다시 적지 않습니다** — 정본은 `config_resolve_report.POPULATIONS`). 사유는 닫힌 어휘이고, 사람이 읽을 문장(`detail`)은 **서버가 만들며 화면은 그것을 그대로 보여줍니다**(계약).

> ✅ **화면이 착지했습니다** (2026-07-31 `93610cb`). **어드민 → Overview 탭의 세 번째 계기 줄**에서 읽으십시오. 위 `curl`은 이제 **대조용**입니다 — 화면에 뜬 문장은 응답의 `detail`에 **글자 그대로** 있어야 하고, 없으면 클라가 문장을 지은 것이라 그 자체가 결함입니다(`contracts/config_resolve_report/client_harness.mjs`가 양쪽을 채점합니다).
> - `Reload Configs`를 누르면 **즉시 다시 읽습니다**(평소에는 1분 스로틀). 두 버튼은 **짝으로** 씁니다 — 하나는 쓰고, 하나는 무엇이 먹었는지 답합니다.
> - ⚠️ **읽기에 실패하면 「설정이 멀쩡하다」가 아니라 대시(―)와 사유가 뜹니다.** 그 사유가 「관리자 게이트가 아닌 응답입니다」라면 **토큰 문제가 아니라 그 포트 앞에 무엇이 답하고 있는가**의 문제입니다(사내 프록시 전례 — [DEPLOY_SETUP §1-5](./DEPLOY_SETUP.md)).

| 모집단 | 뜻 |
|---|---|
| `effective` | 선언이 효과를 내고 있다 |
| `ineffective` | 선언은 있는데 **효과가 없다** + 명명된 사유 |
| `rejected` | 파싱/검증에 실패해 아예 반영되지 않았다 + 사유 |

| 사유 | 뜻 |
|---|---|
| `not_declared` | 효과에 필요한 선언이 없다 (노브가 꺼져 있거나, 짝이 되는 선언이 빠졌다) |
| `mapping_unavailable` | 선언을 읽지/검증하지 못해 반영하지 않았다 |
| `not_reached` | 상위 스위치가 꺼져 이 선언까지 도달하지 않는다 |
| `scope_unresolved` (경고) | 선언은 동작하지만 그 범위가 판단을 고정하지 못한다 |

그리고 `settings`가 **지금 실효 중인 값과 그 값이 온 파일**을 말합니다 — 파일이 없어 기본값인 경우까지 포함해서. (실측 2026-07-30: `ingestion_settings.json`은 **존재하지 않고** `.sample`만 있습니다. 그래서 전역 스위치는 기본값 `true`인데 아무 데서도 그 사실을 말해 주지 않았습니다.)

> **범위:** 🔴 **[2026-08-06 정정] 종전 이 줄은 「2026-07-30 현재 `enrichment` 도메인 *하나*가 등록돼 있습니다」였고 그것은 이제 거짓입니다.** 등록된 도메인은 **`enrichment` · `virtual_join` · `notation`**입니다(`server/config_resolve_report._RESOLVERS`). **수는 다시 적지 않습니다** — 이 자리가 낡은 방식이 정확히 그것이었고, 정본은 그 dict이며 응답 자신도 `vocabulary.populations`/`reasons`와 함께 도메인 목록을 실어 옵니다. 나머지 config는 같은 틀(등록기 하나)로 이어 붙입니다 — 응답은 도메인 목록이라 도메인이 늘어도 소비자는 바뀌지 않습니다.
> `?domain=` 인자로 하나만 골라 읽을 수 있고, **한 도메인의 해석 실패가 나머지를 삼키지 않습니다**(그 도메인만 `mapping_unavailable` 항목으로 내려옵니다).
>
> ⚠️ 이것은 **선언의 해석**이지 물리 반영의 증거가 아닙니다. 스키마 DDL의 증거는 여전히 §4.3의 `information_schema`입니다.

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
- **`on_modified` + `on_moved` + `on_created`** 를 처리합니다(2026-07-29, #9/H3). 저장 형태에 따라 오는 이벤트가 다르기 때문입니다 — ①제자리 쓰기 → `modified` ②**같은** 디렉터리 temp + rename → `deleted`+`moved`(`dest_path`로 판정) ③**다른** 디렉터리 temp + rename → `deleted`+`created`, **`moved`가 아예 없음**. `tempfile.mkstemp()`의 기본이 시스템 temp 디렉터리라 ③은 드문 경우가 아닙니다. (`on_deleted`는 처리하지 않습니다 — ②③의 `deleted`는 뒤따르는 이벤트가 대신 받고, 진짜 삭제에 대해 빈 config로 리로드를 시도할 이유가 없습니다.)
- **디바운스는 트레일링 엣지(재무장)입니다** — 이벤트마다 타이머를 리셋하고 **마지막 이벤트 후 1초**에 1회 발화합니다. 즉 저장 1회가 여러 이벤트로 쪼개져도 리로드는 1회이고, **저장 2회는 어느 것도 버려지지 않습니다.** 2026-07-29 이전의 리딩 엣지(창 안 첫 이벤트만 처리, 나머지 폐기)는 0.3초 간격 저장 2회에서 **두 번째를 통째로 버렸고**, 느린 비원자적 쓰기에서는 **잘린 파일을 읽고 abort한 뒤 완료 이벤트를 버렸습니다.**
- 반영이 불가능하면(파싱 실패·읽기 실패로 빈 config) **조용히 넘어가지 않고** `Config reload ABORTED: ...` ERROR를 남기고 기존 상태를 그대로 둡니다.
- ⚠️ **그래도 물리 반영의 증거는 §4.3의 `information_schema`입니다.** watcher가 발화했다는 것과 DDL이 성공했다는 것은 다릅니다.
- 프로세스별로 동작이 다릅니다: 웹서버는 engine을 갖고 시작하므로 **CREATE + ALTER**를 수행하지만, watcher/chain 워커 프로세스는 `engine=None`으로 시작해 **ORM만 갱신하고 물리 DDL은 하지 않습니다.**

---

## 5. 파일별 상세 → `config/` 폴더

> **[2026-07-28 이관]** 파일별 **세팅 절차·키 사전·반영 확인 방법**은 [**config/ 폴더**](./config/README.md)로 옮겼습니다(파일당 가이드 1개). 아래 §5.x는 링크 스텁이며, **§5.8(전사 계획 의미론)과 §5.8-ter(기능별 테이블 체크리스트)만 이 문서가 정본**으로 남습니다.

### 5.1 `table_config.json`

세팅 절차(스냅샷→in-place 저장→watcher 로그·`information_schema` 확인)와 키 사전(`business_key`·`composite_key_*`·`column_types`·`display_columns`·`map_key_columns`·`map_push_ok`·**`version_column`**·`workspace_name`·`std_parse`·`source_priority`)은 → [**config/table_config.md**](./config/table_config.md)

> **`version_column`(2026-08-04 `092b83f`)은 그 문서 §7이 정본입니다.** 「같은 키의 행이 항상 최신본이어야 한다」를 선언하는 키로, 선언하면 **기계가 기존 행을 덮어쓸 때 버전이 더 클 때만** 반영합니다(사람의 교정은 규칙 밖 — 더 높은 버전도 밀지 못합니다). **오늘 선언한 테이블은 없어 전부 무동작**입니다. 🔴 **켜기 전에 §7.2의 확인 한 줄을 반드시 돌리십시오** — 아래 §6-P.

### 5.2 `ontology_mapping.json`

세팅 절차(리로드 필수·재동기화)와 키 사전(`description` 필수·`node`·`edges`·spatial props) → [**config/ontology_mapping.md**](./config/ontology_mapping.md)

> 🔴 **[2026-08-11 `68db020`] `node.identity`는 이제 생략(전체 상속)하거나 `@map_key_columns` 토큰으로 부분 상속할 수 있다** — `table_config.map_key_columns`를 두 번째로 철자하지 마라. 상세는 위 링크 §5-bis.

### 5.3 `enrichment_rules.json`

세팅 절차(키 계약·리로드 두 갈래)와 키 사전(`decision_key`·`target_fields`·`reference_views`·**`candidate_for`/`auto_confirm`** 등) → [**config/enrichment_rules.md**](./config/enrichment_rules.md)

### 5.4 `chain_rules.json`

세팅 절차(맵퍼 배치→룰 선언→리로드)와 키 사전 → [**config/chain_rules.md**](./config/chain_rules.md)

### 5.5 `auto_update_control.json`

**API 전용 쓰기** — 토글·run-now 절차 → [**config/auto_update_control.md**](./config/auto_update_control.md)

### 5.6 `ingestion_settings.json`

heavy 임계·dedup·체크포인트 재개·폴더 트리 적재·맵 메타 자동 등록·Enrichment 자동 확정 노브 → [**config/ingestion_settings.md**](./config/ingestion_settings.md)

> 🔴 **`flatten_nested_dirs`는 이름이 그대로인데 뜻이 바뀌었습니다** (`600b49d` · 2026-07-30). `true`(기본)의 동작이 「파일을 `raws/` 루트로 **승격**」에서 「파일을 **자기 중첩 경로 그대로** 적재」로 바뀌었습니다. **키를 개명하지 않은 것은 의도**입니다 — 개명하면 운영자가 이미 `false`로 넣어 둔 off 스위치가 **조용히 무력화**되고, 그 순간 손대지 않기로 했던 폴더가 적재되기 시작합니다. 설정 파일을 고칠 필요는 없습니다.
>
> 함께 정정된 것: `false`일 때의 로그 문구가 **"그 안의 파일은 적재되지 않는다"**고 명시합니다. 종전 문구는 폴더만 안 건드린다고 읽혀서, 운영자가 파일은 처리되는 줄 알 수 있었던 부분입니다.
>
> ⚠️ **`filename_rules`는 이 파일의 키가 아닙니다.** 폴더 이름을 컬럼으로 바꾸는 선언은 **워크스페이스별 파서 설정**(`ingestion_workspace/<table>/config/*.json`)에 있고, 규격의 정본은 [INGESTION_GUIDE §1.9-bis](./INGESTION_GUIDE.md)입니다(허용 키·명명 상태 4종·로드 시점 거절·**우선순위 `filename < header < row`**).

### 5.6-bis `effort_metric.json`

V1 정본 계기의 배점·전이 선언 → [**config/effort_metric.md**](./config/effort_metric.md)

> ⚠️ **배점을 바꾸면 과거 데이터까지 새 배점으로 다시 읽힙니다**(원시 카운트만 저장하고 점수는 조회 시점 계산 — 의도된 설계). 뒤집어 말하면 **배점 변경 전후의 숫자는 직접 비교할 수 없습니다.** 기준선 측정 중에는 고정하십시오.

### 5.6-ter `suggest_config.json`

입력 제안(고유값 조회)의 길이·타임아웃 노브 + **접두 인덱스 대상 선정** + **느린 응답 경보(`slow_warn_ms`)·계획 형태 검사** → [**config/suggest_config.md**](./config/suggest_config.md)

⚠️ **운영 수칙(2026-07-30 F7)**: 테이블이 `index_min_rows`(기본 10,000)를 넘어간 뒤 `setup_db_performance.py`를 다시 돌리지 않으면 그 테이블의 제안 조회는 **정답을·완전한 모양으로·느리게** 답합니다. 데이터가 늘어나는 테이블이 있으면 적재 후 스크립트 재실행을 절차에 넣으십시오.

> ⚠️ **이 파일은 인덱스를 만들지 않습니다.** `index_min_rows`/`index_columns`/`index_exclude`는 **선언**이고, 실제 생성은 `server/scripts/setup_db_performance.py`(Step 3.8)가 합니다 — 값을 바꾸고 스크립트를 돌리지 않으면 **아무 일도 일어나지 않습니다.** 반대로 인덱스가 없는 컬럼은 조용히 느려지지 않고 `unavailable_reason`으로 꺼집니다(사유가 인덱스 이름과 실행할 명령을 지목합니다).

### 5.6-quinquies `audit_history_config.json` (2026-08-11 신설 · `dab9152`+`2630790`)

감사 이력 조회 상한 — 행/셀 이력 페이지 크기 + 전역 「최근」 패널 discovery 걸음의 천장 → [**config/audit_history_config.md**](./config/audit_history_config.md)

> 🔴 **이 config는 인덱스 없이는 아무것도 안 빨라집니다 — `suggest_config.json`과 같은 계급의 함정입니다.** `default_limit`/`max_limit`을 아무리 낮춰도, DB가 이미 조회를 마친 뒤에 잘라내는 것이 아니라 **스캔 자체가 테이블 전체에 비례해 자랍니다.** 실제로 빠르게 만드는 것은 **세 인덱스**(`idx_audit_recent_groups` · `idx_audit_row_history` · `idx_audit_cell_history`)이고, `create_all`은 **이미 있는 테이블에 인덱스를 추가하지 않으므로** 기존 배포는 두 마이그레이션 파일을 손으로 한 번 돌려야 합니다 — **[DEPLOY_SETUP §6 단계 8-ter](./DEPLOY_SETUP.md)** 참조.
>
> ⚠️ **`.sample`이 `recent_*` 넷을 아직 안 적고 있습니다** — 코드(`server/audit_cache.py`의 `RECENT_DEFAULTS`)는 이미 이 파일을 읽도록 배선돼 있고, [config/audit_history_config.md](./config/audit_history_config.md)가 그 코드 사실의 정본입니다. `.sample`을 보고 "이 키는 없다"고 판단하지 마십시오 — 코드가 갖고 있다면 그 키는 유효합니다.

### 5.6-quater `notation_rules.json` (2026-08-04 `92b8d6f` 신설 → **`8d306a5` 전면 재설계**)

표기 정규화 선언 — 규칙 사전·거절·확인 절차·소비자 → [**config/notation_rules_config.md**](./config/notation_rules_config.md)

> 🔴 **[2026-08-04 정정] 종전 이 절이 적고 있던 「층 셋」은 거짓이 됐습니다.** `92b8d6f`가 출하한 **물리 파생 컬럼(`<컬럼>_norm`)**은 `8d306a5`에서 **아무도 소비하기 전에** 제거됐습니다(사용자 확정). 함께 사라진 것: `table_config.json`의 파생 컬럼 선언 단계 · `display_columns` 가시성 결정 · 쓰기 거부 400 · 재파생 스크립트(`server/scripts/rederive_notation_norm.py` **삭제**).
>
> **지금은 한 단계입니다.** 이 파일의 `columns.<테이블>` 아래에 컬럼을 `true`로 적으면 끝이고, **저장되는 것은 없습니다** — 소비자가 **조회 시점에 비교의 양쪽을 SQL에서** 접습니다. 전제는 그 컬럼이 `table_config.json`에 **`"string"`으로** 선언돼 있는 것뿐입니다(`number`는 `not_text`로 거절 — 숫자에는 표기가 없습니다).
>
> 🔴 **선언 다음에 반드시 볼 것은 「무엇이 합쳐지는가」입니다** — `GET /admin/config/notation/preview`가 **병합군**으로 답합니다(그 문서 §3). 규칙이 틀렸으면 이 파일만 고치면 되고 **되돌릴 데이터가 없습니다.**
>
> 🔴 **오늘의 유일한 소비자는 가상 조인의 키 비교이고, 그 조인의 승인 인덱스가 바뀝니다** — 접힌 키에서는 평범한 UNIQUE 인덱스가 **후보에서 배제되고 함수 인덱스가 필요합니다.** 이유가 성능이 아니라 **정확성**입니다(원본으로 다른 두 행이 접히면 한 값이라, 컬럼 UNIQUE가 있어도 접힌 키로는 중복이고 그 중복이 곧 팬아웃입니다) → [config/virtual_join_rules](./config/virtual_join_rules.md).

### 5.7 `bonding_plan_config.json`

역할 바인딩 교체 절차·키 사전·`align` 폐지 경위 → [**config/bonding_plan_config.md**](./config/bonding_plan_config.md)

> **`sources[].align`이 사라진 자리** — canonical 프레임은 메타가 등록된 **첫 맵 모드 역할**(`total_chips` → `defect` → `eds_fail` 순)이고, 나머지 맵은 자기 메타와의 델타로 그 프레임에 투영됩니다. 실제로 라이브 `eds_fail`에 선언돼 있던 `rotation: 180`은 `eds_fail_map` 메타의 rotation과 **정확히 같은 값**이었습니다 — 선언이 메타의 손수 관리하는 복사본이었다는 뜻입니다. 복사본이 정본과 어긋나면 어느 쪽이 참인지 알 방법이 없어 폐지했습니다.

### 5.8 `transfer_plan_config.json` — stage 선언 발췌

> 운영 서버 **세팅 절차·반영 확인·키 사전**은 [**config/transfer_plan_config.md**](./config/transfer_plan_config.md). **이 절은 의미론(zone 모델·마커 0·`stack` string·`bin_map`·`bands` 폐기)의 정본**으로 남습니다.

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
    "registry": {
      "table": "map_split_registry",
      "columns": {
        "ref_table": "ref_table", "map_key": "map_key", "value": "value",
        "stack": "stack", "mat_1h": "mat_1h", "mat_mid": "mat_mid", "mat_top": "mat_top",
        "bands": "bands"
      }
    },
    "material_identity": {
      "compose": ["lot", "slot"],
      "separator": "_"
    }
  }
}
```

> **DOE 행의 단위는 `값` 하나입니다.** legend 행 하나가 곧 DOE 조건 하나이고 bk는 `ref_table|map_key|value`입니다.
>
> **[ZONE 모델 2026-07-28 — band 모델을 대체합니다]** 한 값의 층 구조는 **숫자 하나와 구역 셋**입니다:
>
> | 컬럼 | 뜻 |
> |---|---|
> | `stack` | 그 값의 **총 층수**. **[U9 2026-07-28] `0`(또는 `"0"`)은 높이가 아니라 마커 선언**입니다 — 그 값은 층 배정이 아닌 **상태 표시 값**(예: BASE FAIL)이며, 구역이 구성적으로 없고 얼마를 칠해도 소요가 0이고 롤업에 행 자체가 없습니다(0이 아니라 **부재**). 공백은 마커로 접히지 않습니다 — 공백은 「아직 안 적음」(V5 차단), 0은 선언입니다. 음수는 여전히 invalid |
> | `mat_1h` | **1층** |
> | `mat_top` | **STACK층** |
> | `mat_mid` | **그 사이 전부** — 1H가 비면 1층부터, TOP이 비면 STACK층까지 |
>
> 세 구역이 `1..STACK`을 **구성적으로** 덮으므로 겹침·구멍·`FROM>TO`는 완화된 것이 아니라 **말할 수 없는 상태**가 됐습니다. 그 검사가 코드에 없는 것은 누락이 아닙니다. `dt_map`은 `STACK=1`, MID만인 **퇴화형**이며 **조용히 통과해야 합니다**.
>
> ⚠️ **`stack`은 `"string"`으로 선언합니다 — `"number"`가 아닙니다.** 한 커밋 동안 `number`였고, 물리 컬럼이 `double precision`으로 만들어지자 `crud.cast_value_by_type`가 `'0x10'`·`'nope'`에서 **예외를 던져 저장 자체가 실패**했고 `'7.5'`는 조용히 `7.5`로 고쳐져 다음 읽기에서 7층이 됐습니다. 읽을 수 없는 STACK은 **왕복에서 살아남아야** 합니다(V5가 그것을 근거로 차단하고, 사용자는 자기가 적은 글자를 화면에서 봅니다). 판독 여부는 컬럼 타입이 아니라 **정수 판정기 하나**(`transfer_plan._int_state` / 클라 `bandToState`)가 정합니다.
>
> ⚠️ **`mat_*` 세 컬럼은 원문 토큰의 JSON 배열**(`["MID1","MID3"]`)이지 분리자로 이은 문자열이 아닙니다. 로트 이름에는 `:`도 `_`도 합법이라 안전한 분리자가 없습니다. 서버는 읽을 때 **JSON을 먼저** 시도하고(그것이 writer가 쓰는 형태), JSON이 아니면 사람이 손으로 적은 텍스트로 보고 줄바꿈/쉼표로 나눕니다.
>
> **파생값은 저장하지 않습니다** — 구역 소요 = `칠한 셀 수 × 그 구역의 층 수`, 매당 소요 = `ceil(구역 소요 / 자재 수)`를 매번 계산합니다. 저장된 총량은 누군가 셀을 하나 더 칠하는 순간 조용히 어긋납니다.
>
> **차단 규칙은 V1~V6 여섯 개**이고 정본은 `contracts/doe_band_rules/vectors.json` v3(클라 하네스와 서버 테스트가 **같은 파일**을 채점)입니다. V5(STACK 판독 불가)가 **가장 먼저** 판정됩니다 — 다른 모든 판정이 계산할 수 없는 층 수에서 유도되기 때문입니다. **V6은 마커 모순**(STACK 0인데 구역에 자재가 있음)이며, **마커 행이 답하는 유일한 규칙**입니다 — 마커의 자재는 조회도 소요도 되지 않으므로 V4를 함께 내면 한 행에 모순된 두 지시(토큰을 고쳐라 vs 자재를 지워라)가 되고, V3의 풀 스캔에도 참여하지 않습니다(소요 없는 토큰은 아무것도 이중 계산할 수 없습니다). 모든 규칙과 같이 **권고이지 저장 게이트가 아닙니다**.
>
> **자재 ID는 사용자가 입력한 원문 그대로가 정체입니다.** 토큰 문법 `lot["_"slot][":"BIN]`은 **공유 계약**이고 구현은 `transfer_plan.parse_material_token` 하나입니다. 분리자 없는 `MID1`은 해석 실패가 아니라 **그 로트 전체**를 뜻하며, 진짜 malformed한 토큰(`ABC_`·`_01`·`_`·BIN 실패)만 거부합니다(V4). ⚠️ `material_identity`는 이제 **게이트로만** 씁니다 — 클라는 config를 읽지 못하므로 파싱 규칙이 config에 살면 양쪽이 갈리고, 갈리는 순간 한 화면에 두 개의 가용치가 생깁니다. 미선언이면 아무것도 조회하지 않고 `source_unresolved`로 보고합니다.
>
> **BIN 축은 `bin_map` 선언으로만 켜집니다 — 미선언은 결함이 아니라 「아직 배선되지 않음」입니다.** 🚨 **단, `source_config_ref`(M1 위임) stage에는 `bin_map`을 선언해도 축이 켜지지 않습니다** — 위임 경로는 좌표 집합을 만들지 않아 `get_stage_source_summary`가 bins 요청에 무조건 `unavailable`("core-kind(M1 위임) 소스는 …")로 답합니다(2026-07-28 격리 환경 E2E로 확인). BIN 축이 필요한 stage는 **inline `source` 블록으로 선언**해야 하며, 이때 신뢰 가능한 잔여를 얻으려면 `origin_log`까지 connected여야 합니다(미선언 = missing 강등 → 전 BIN unknown·remaining null. 루트 소스는 자기 자신으로의 self-join 선언이 성립합니다). 선언 형태 `bin_map: {table, columns: {lot, slot, x, y, bin}}` 자체는 격리 스택(:8081)에서 실측 검증됐습니다 — 선언 즉시 `axis:"connected"` + BIN별 `{cells, total, fail_breakdown, transferred, remaining}`이 독립 대조 계산과 일치했습니다. `lot_slot:BIN` 토큰의 BIN별 가용을 세려면 stage 블록(또는 그 `source` 블록)에 `bin_map: {table, columns: {lot, slot, x, y, bin}}`을 선언해야 합니다. 선언이 없으면 서버는 **BIN 컬럼을 추측하지 않고**(`transfer_plan._bin_axis_binding` — 같은 `dt_map.val`이 이미 `origin_area_map`의 **출신 코어 식별자**로 선언돼 있어, "맵의 val이 곧 BIN"으로 박으면 라이브에서 즉시 틀립니다) 축을 `axis: "unavailable"`로 보고하며, 클라 롤업의 해당 칸은 `미상`으로 남습니다(`0`이 아닙니다). 동작 계약은 [MAP_EDITOR_SPEC §6.1-bis](../spec/MAP_EDITOR_SPEC.md)가 정본입니다.
>
> ℹ️ **로트 전체 토큰은 `validate`가 값을 매기지 않습니다**(`source_scope_unpriced`). `scope=lot` 응답에 `chips`가 없는 것과 같은 이유입니다 — 로트 하나의 `remaining` 숫자를 지어내지 않습니다. "조회 못 함"도 "이상 없음"도 아닌 **"판정하지 않았다"**로 나갑니다.
>
> **[2026-07-28 `1fefd12`] 강등 status 어휘 둘 추가 — config 문제가 사라지는 대신 이름을 얻습니다.**
> - **`connected(count_only)`** — `transfer_log`가 바인딩은 됐는데 **쓸 만한 x/y가 없어** 칩 정체 없이 행 count만 제공하는 상태. `transferred` 카운트는 진짜라 유지되지만, 집합 감산이 불가능하므로 **`remaining`은 `null` + 진짜 상한(`remaining_upper_bound`)**으로 내려가고 `by_core`의 used/remaining도 log·area_map 양 경로 모두 `null`입니다. 종전에는 이 상태가 `connected`로 통과해 **기전사 차감이 빠진 remaining이 정상처럼 표시**됐습니다(유령 잔여 — +101 재현으로 실증된 결함). **[2026-07-28 `deed6d2`] 같은 강등이 `frame: "self"`인 `fail_sources` 원천에도 적용됩니다** — `origin_log`가 connected인 집합 감산 경로에서 self fail 원천에 쓸 만한 x/y가 없으면, count는 `fail_breakdown`에 그대로 남되 fail 합집합에 칩을 기여하지 못해 remaining이 과대 계상되므로(재현: 256/256 칩 fail인데 remaining 209가 `reliable: true`) `connected(count_only)`로 강등 — remaining null + 상한, `by_core`의 fail·remaining null(used는 used_set 기반이라 실물 유지). **count를 대신 감산하지 않는 이유**: 칩 정체를 몰라 used·다른 fail과 겹치면 과대 감산이 되어 상한 불변식(강등 항은 과소 기여만 허용)이 깨집니다. `origin_log` 없는 폴백(count 기반 감산) 경로에서는 count 감산이 정확하므로 **강등하지 않습니다**.
> - **`connected(column_unresolved:<roles>)`** — **선언한 컬럼이 모델에 없는**(config 오타) 상태. 종전에는 선언이 조용히 사라져 역할이 멀쩡해 보였는데, 지금은 어느 역할키가 안 풀렸는지 이름을 붙여 강등합니다. 특히 `fail_sources`의 `fail_values`가 선언됐는데 `val`이 안 풀리면 **필터 없는 전 행 count를 거부하고 0 + 강등**합니다 — **상한 불변식**(강등된 항은 과소 기여만 허용 — fail을 과대 계상하면 `remaining_upper_bound`가 상한이 아니게 됨) 때문입니다. `align_unavailable`의 "0 + 강등"과 같은 규율입니다.
>
> 두 status 모두 강등 판정(`_status_is_degraded`)에 들어가므로 신뢰 표기 3층 방어(remaining null·validate 생략·`unverified` — [MAP_EDITOR_SPEC §6.2](../spec/MAP_EDITOR_SPEC.md))가 그대로 작동합니다. 역할별 발화 조건은 [config/transfer_plan_config.md §5](./config/transfer_plan_config.md)의 사전 참조.
>
> **[2026-08-04 `2c2a777` 완화] 보조 역할 선언은 선택입니다 — 세 번째 상태 `not_declared`.**
> 현장은 `transfer_log`·`origin_log`·`fail_sources`·`process_history` 같은 부속 테이블을 두지 않고 **맵 자체에 차감을 표기**합니다(불량 맵을 겹쳐 그린 뒤 그 위에서 뺍니다). 종전 엔진은 **키가 없는 것**과 **선언이 깨진 것**을 같은 `missing`으로 접어 강등시켰고, 그 결과 그런 현장에서는 모든 자재의 가용이 `미상`이 됐습니다. 이제 config 경계에 상태가 **셋**입니다:
>
> | 선언 | status | 가용 | 뜻 |
> |---|---|---|---|
> | **키 자체가 없음** | `not_declared` | **숫자로 나감**(그 감산항 없이) | 「우리 현장엔 그 표가 없다」는 **사이트의 선언**. 감춰진 데이터가 아니라 그 사이트가 가진 최선의 지식이므로 강등하지 않습니다 |
> | **키는 있는데 깨짐**(null·오타·테이블 부재) | `missing` 등 종전 강등 | `null` | 완화는 **부재에만** 적용됩니다 — 고칠 수 있는 결함은 계속 결함으로 말합니다 |
> | `transfer_log: "none"` | 종전 `untracked` | `null` + 상한 | 7c 규약 그대로(「추적하지 않는다」는 명시 선언) |
>
> ⚠️ **`total_chips`는 분모라 예외입니다** — 없으면 가용이 성립하지 않으므로 종전대로 `missing`입니다.
>
> 🔑 **총량이 순량 행세를 하는 침묵은 필드 하나가 막습니다 — `inactive_subtractions`.** 감산에서 빠진 종류의 이름 목록(예: `["transfer_log", "origin_log", "fail_sources"]`)이며, **가용 수치를 내는 모든 응답에 같은 이름·같은 모양으로** 붙습니다: 슬롯 요약 · `scope=lot` 요약 · M1 `core-summary` · **그리고 그 수치로 판정을 내는 `GET /api/transfer-plan/validate`까지**(2026-08-04 QA B1 — 판정 라우트만 이 필드를 모른 채 숫자를 읽고 있었습니다). **목록이 비면 필드 자체가 없으므로**, 전 역할을 선언한 환경의 응답은 완화 전과 한 바이트도 다르지 않습니다.
>
> ℹ️ **`validate`의 판정 문자열(`status`)은 이 필드 때문에 바뀌지 않습니다.** 미선언은 결함이 아니라 선언이므로 `ok`는 계속 `ok`입니다 — 서버가 하는 일은 **무엇을 빼지 않았는지 말하는 것**이고, 그 `ok`를 어떻게 그릴지(단서 뱃지·툴팁 등)는 소비자가 정합니다.
>
> ⚠️ **이름 충돌 주의 — §4.2-bis의 `not_declared`와 철자가 같습니다.** 두 곳 모두 술어는 같습니다(**「필요한 선언이 없다」 → 그 효과가 비활성**). 다만 **축이 다릅니다**: §4.2-bis의 것은 `config_resolve_report`의 **사유(reason)**로 `ineffective` 모집단에 붙고, 여기의 것은 계획 소스의 **역할 status**로 `sources.<role>`에 붙습니다. 페이로드 자리가 다르므로 서로 대체할 수 없습니다 — §5.8의 상태를 §4.2-bis 표에서 찾지 마십시오(반대도 마찬가지).
>
> 🗄️ **폐기된 `bands`는 필수 역할이 아니지만 계속 읽습니다.** 실계획이 아직 그 컬럼에 남아 있고, legend 저장은 `replace_map`이라 **읽지 못하면 그 맵을 여는 순간 화면이 비고 다음 편집 한 번이 계획을 빈 집합으로 지웁니다.** 서버는 `bands_to_zones`로 옮기며, 세 구역으로 표현할 수 없는 배치(구간 4개·읽을 수 없는 `to`·역전·1층에서 시작하지 않는 첫 구간)는 **접지 않고 거부**합니다(`layer_range_invalid` / `reason: not_convertible`). 접은 결과를 되쓰면 서버의 진짜 계획이 그 손실 읽기로 덮입니다. 새 writer를 만들지 마십시오.

> **`.sample`은 위 발췌와 일치합니다(2026-07-28 zone 모델 반영).** `transfer_plan_config.json.sample`의 `plan_store`에서 폐기된 `doe`·`doe_source` 역할과 그 컬럼(`doe_value`·`band_seq`·`stack_band`·`qty_total`·`qty`)을 제거하고, 코드가 실제로 요구하는 `registry`(**필수** `ref_table`·`map_key`·`value`·`stack`·`mat_1h`·`mat_mid`·`mat_top`, **선택** `bands`) + `material_identity` 선언으로 교체했습니다. 🚨 **기존 환경은 라이브 파일에 zone 역할 넷을 손으로 더해야 합니다** — 하나라도 없으면 `validate`가 404입니다. 반대로 `bands`는 이제 없어도 200입니다(폐기 계획을 못 읽을 뿐). `registry`가 가리키는 `map_split_registry`는 **제품 소유 저장소**라 `table_config.json.sample`에 함께 선언돼 있습니다 — `.sample` 3종(`table_config`·`transfer_plan_config`·`map_overlay_config`)을 복사하면 `plan_store`는 바로 `connected`입니다.
>
> 🚨 **이미 쓰던 환경이라면 `transfer_plan_config.json`(라이브)도 같이 고쳐야 합니다.** 라이브 파일은 gitignored라 `.sample` 갱신이 자동으로 따라가지 않습니다. 옛 `doe`/`doe_source` 바인딩만 남아 있으면 `validate`가 **404**입니다.
>
> ⚠️ **`table_config.json`에 `map_split_registry`의 `knobs`·`stack`·`mat_1h`·`mat_mid`·`mat_top` 선언이 있어야 하고, 물리 컬럼이 실제로 존재해야 합니다.** 선언이 없으면 클라이언트가 보낸 값이 **드롭되고 HTTP 200이 나갑니다**(§6 함정 M) — 그리고 legend 저장은 `replace_map`이라 그 200이 **층 구조 없는 행으로 계획 전체를 갈아치웁니다.** 실제로 M2.6 클라가 착지한 뒤 `bands` 선언이 없어 쓰기가 조용히 버려지고 있었고, zone 착지 때도 같은 자리에서 물리 ALTER가 밀려 있었습니다.
>
> 기존 테이블에 컬럼을 더하는 것은 **BLOCKING drift**이므로 `install_product_tables.py --apply --overwrite-drift`가 필요합니다(§5.8-ter). ALTER를 수행하는 것은 **config watcher 뿐**이며 `/admin/reload-configs`는 하지 않습니다(§4.2). 🚨 **물리 반영은 `/tables/{t}/schema`가 아니라 `information_schema.columns`로 확인하십시오** — 스키마 API는 config 싱글턴을 읽으므로 200에 컬럼이 보여도 증거가 아닙니다(§4.3). 클라이언트는 이 상태를 스스로 감지해 저장을 **보류**합니다(실제 행의 셀 키 집합을 봅니다 — `probeZoneColumns`) — 컬럼이 나타나면 다음 ⚡ Push 시도에서 재확인해 풀립니다(자동 저장은 `b35bc9f`에서 삭제됐고 Push가 유일한 기록자입니다).
>
> `map_overlay_config.json.sample`에서도 폐기 테이블 `transfer_plan_map`의 `table_bindings`·`paint_lock` 항목을 제거했습니다 — 계획 캔버스의 잠금은 그 stage의 `target_map` 테이블(`bonding_map`/`dt_map` 등)에 직접 선언합니다.
>
> **`source_region`(자재별 사용 영역 스코프)은 휴면이라 `.sample`에 넣지 않았습니다.** 미선언은 결함이 아니며(`plan_store`에 키 자체가 안 나옵니다), 선언만 하고 테이블이 없으면 도리어 `missing` 소음이 됩니다. 켜려면 `plan_store.source_region`에 `(ref_table, map_key, source_lot, source_slot, x, y)` 바인딩을 추가하고 그 테이블을 `table_config.json`에 선언하십시오.

### 5.8-bis `map_overlay_config.json`

세팅 절차(선언 없이도 동작·페인트 잠금 머지)와 키 구조·검증 방법 → [**config/map_overlay_config.md**](./config/map_overlay_config.md)

> 🆕 **[F5 2026-07-30] `preset_routing`** — 맵을 열 때 적용할 **물리 규격(프리셋)**을 맵 키에서 자동 결정합니다. 해석 순서가 계약입니다: ①`product_lookup`(제품코드 조회 테이블) → `product_presets` → ②`rules`(순서 있는 텍스트 패턴, 첫 매치 승리) → ③라우팅 없음(지금 동작 그대로). **①의 조회 테이블은 운영에만 있으므로 미선언이 정상 구성**이고, 선언해도 조회가 빗나가면(테이블이 불완전합니다) **경고 없이 조용히 ②로** 갑니다. **절대 우선순위는 `wafer_map_metadata`(저장된 규격) > 라우팅 > 패널**이며, 이미 규격이 등록된 맵은 서버가 `meta_present`로 거절하므로 라우팅이 메타를 덮을 수 없습니다. 선언 절차·검증(`GET /api/maps/preset-routing`)·조회 테이블 인덱스 요구는 → [**config/map_overlay_config.md §2-bis**](./config/map_overlay_config.md#2-bis-f5-로드-시-프리셋-라우팅-선언)
>
> 프리셋 **본문**은 여전히 `maps.json`에 삽니다(§5.9). 라우팅이 `maps.json`이 아니라 여기 사는 이유: `maps.json`은 `POST/DELETE /api/map-presets`가 **파일 전체를 다시 쓰는 API 관리 파일**이라 손으로 적은 운영 규칙을 둘 자리가 아니고, 교차 테이블 선언 조회(`table_bindings`)가 이미 이 파일에 있기 때문입니다.

> 🗑️ **[폐지 2026-07-27] `align_overrides`** — 남아 있어도 서버가 무시합니다(테스트로 고정). 정렬의 유일한 근거는 **`wafer_map_metadata`**이며, 정렬을 켜는 올바른 방법은 오버라이드 선언이 아니라 **소스·타깃 맵의 메타 등록**입니다 → [MAP_EDITOR_SPEC §5.0](../spec/MAP_EDITOR_SPEC.md).

> ⚠️ `7d931dc` 이후 **맵 에디터 클라는 서버 오버레이 좌표를 소비하지 않고 변환을 자체 수행**합니다(선언 probe 관문 `probeAlignDeclaration`과 실패 status 2종 `align_unconfirmed`·`align_override_declared`도 함께 삭제 — REST 왕복 1회 감소).

### 5.8-ter 기능별 필요 테이블 체크리스트

> **바인딩 config는 `table_config.json`에 선언된 테이블만 해석합니다.** 미선언 테이블을 가리키는 **바인딩(= 키는 있고 테이블이 없는 경우)**은 조용히 죽지 않고 해당 역할이 `missing`으로 표면화됩니다(`bonding_plan._resolve_model_columns`). ⚠️ **역할 키가 아예 없는 것은 이것과 다릅니다** — 보조 역할(`transfer_log`·`origin_log`·`fail_sources`·`process_history`)의 키 부재는 `not_declared`이고 강등이 아닙니다(§5.8). 그래서 기능을 켜는 순서는 항상 **① `table_config.json`에 테이블 선언 → ② 바인딩 config의 `table`/`columns`를 그 이름에 맞춤**입니다.

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
> python server/scripts/install_product_tables.py --sync-comments --overwrite-drift --apply   # __comment까지 갱신
> ```
>
> - **현장 항목은 재직렬화하지 않습니다** — 원본 텍스트에 바이트 스플라이스로 끼워 넣으므로 키 순서·들여쓰기·줄바꿈·개행문자가 보존됩니다. `json.load`/`json.dump` 왕복은 건드리면 안 될 항목까지 재포맷합니다.
> - 없으면 추가 / 동일하면 **무기록** / **다르면 드리프트로 보고만 하고 손대지 않음**(`--overwrite-drift` 필요).
> - **`__comment`는 기본적으로 드리프트로 세지 않습니다** — 운영자가 주석을 달았을 수 있는 유일한 부분이라 함부로 덮지 않습니다. 다만 **낡은 주석은 적극적으로 오해를 만듭니다**(폐기된 바인딩 이름을 계속 가리키는 등). 갱신하려면 `--sync-comments`를 켜십시오(여전히 `--overwrite-drift` 필요, dry run 기본·백업·미접촉 항목 바이트 재대조는 그대로).
> - `--apply`는 타임스탬프 백업을 먼저 쓰고, 반영 후 손대지 않은 항목을 바이트 대조해 **어긋나면 백업을 복원**합니다.
> - **DDL은 하지 않습니다.** 선언이 물리 테이블이 되는 것은 §4.1 리로드 경로의 일이며, 스크립트가 어느 경로가 필요한지 출력합니다.
> - 종료코드: `0` 할 일 없음 · `1` 조치 필요 · `2` 오류.
>
> 🚨 **`--overwrite-drift`는 항목 단위가 아니라 전부에 걸립니다.** 드리프트 하나를 고치려고 돌리면 **미선언 항목까지 함께 추가**됩니다 — 2026-07-28에 `map_split_registry`의 zone 컬럼을 넣으면서 폐기 2종(`map_doe`·`map_doe_source`)이 같이 선언되고 물리 테이블까지 새로 만들어졌습니다(운영자가 이전에 지워 둔 것이었습니다). **dry run의 `[ADD]` 줄을 먼저 읽으십시오.**
>
> ⚠️ **컬럼 타입을 바꾸는 것은 이 경로로 되지 않습니다.** `sync_dynamic_tables_schema`는 **없는 컬럼을 추가만** 하고 기존 컬럼의 타입은 건드리지 않습니다. 잘못된 타입으로 이미 만들어졌다면 `DROP COLUMN` 후 다시 sync해야 하며, **그 컬럼에 데이터가 있으면 지워집니다** — 먼저 `SELECT count(*) ... WHERE <col> IS NOT NULL`로 확인하십시오.

| 테이블 | 역할 | bk 규칙 |
|---|---|---|
| `map_split_registry` | 맵 값(legend) 레지스트리 — `split_desc`·`color`의 정본이자 **DOE 그 자체**. 값 하나 = 행 하나 = DOE 조건 하나이며, 층 구조는 **zone 컬럼 넷**(`stack`·`mat_1h`·`mat_mid`·`mat_top`, 2026-07-28)에 있다(`knobs`·`split_desc`는 온톨로지가 소비하므로 **평면 컬럼으로 남긴다**). 🗄️ `bands`는 폐기됐지만 실계획이 남아 있어 **읽기 전용**으로 계속 선언한다 — 새 writer 금지 | `ref_table\|map_key\|value` (구분자 `\|`) |
| `wafer_map_metadata` | 격자 규격(`grid_metadata`) | `target_table_map_id` |
| `valid_die_ref` | 유효 다이 맵의 저장 테이블 — **한 행 = 한 맵의 한 셀**. 🔴 **행의 존재 자체가 「이 다이가 유효하다」의 답**이므로 그런 뜻의 컬럼을 새로 만들지 마십시오(둘이 어긋나면 화면이 어느 쪽이 이겼는지 말하지 못합니다). 사용자 절차는 [VALID_DIE_MAP_GUIDE](./VALID_DIE_MAP_GUIDE.md) | `product_type_x_y` (구분자 `_`, `map_key_columns = (product, type)`) |

> 🗄️ **[2026-08-13 `c0fb735`] `map_doe`·`map_doe_source`는 은퇴했습니다 — 이 표에서도, `.sample`에서도, `product_tables.py`에서도 사라졌습니다.** 2026-07-27(M2.6) 폐기 이후 「읽기용 선언만 남긴다」 상태였고, 코드 주석이 「DROP TABLE은 운영자 승인 필요」라 적고 기다리던 것을 제품 소유자가 승인했습니다. **운영 물리 삭제 절차는 [process/OPERATOR_RUNBOOK §5](../process/OPERATOR_RUNBOOK.md)**(마이그레이션은 **비어 있지 않으면 거절**하고, 이미 없으면 조용히 통과합니다).
> - ⚠️ **당신의 `table_config.json`에는 아직 그 두 선언이 남아 있을 수 있습니다** — 이 파일은 gitignore라 배포가 덮지 않습니다. 남아 있어도 새로 쓰는 코드는 없습니다. 선언을 지우면 **기존 행을 읽을 수 없게 되므로** 물리 삭제와 같은 순서로 판단하십시오.
> - 🔴 **`--overwrite-drift`로 그 둘이 «되살아난» 전례가 있습니다**(아래 🚨 항목) — 은퇴 이후에도 그 함정 자체는 유효합니다.

> 위 표의 테이블들은 **`composite_key_separator`를 바꾸지 마십시오.** `map_key`가 `_` 조인 문자열이고 테이블명에도 `_`가 흔해 `_` 구분자로는 키가 모호해집니다(클라이언트의 `SPLIT_KEY_SEP`와도 일치해야 합니다).

> `table_config.json.sample`의 나머지 엔트리(`bonding_map`, `inventory_master`, `production_plan`, `parts`, `large_table_100`)는 **동작 예시**입니다 — 제품이 이름을 강제하는 저장소가 아니므로 현장 테이블로 교체하거나 지워도 됩니다.

**기능을 켜려면 아래 테이블을 당신의 실제 이름/컬럼으로 `table_config.json`에 선언한 뒤, 바인딩의 `table`/`columns`를 그 이름으로 맞추십시오.**

| 기능 | 바인딩 config | 현장 소유 테이블 (역할) |
|---|---|---|
| **전사 계획 (M2)** — stage 소스 가용·validate | `transfer_plan_config.json` | `dt_map`(DT 타깃 맵) · `dt_log`(테이프↔코어 전사 로그 = tape stage의 `total_chips`/`origin_log`) · `bonding_map`(BONDING 타깃 맵) · `bonding_log`(기전사 로그) · `core_defect_map` · `eds_fail_map`(fail 원천) · `wafer_process`(이력) |
| **본딩 가용량 (M1)** — core-summary | `bonding_plan_config.json` | `bonding_log`(기사용 칩) · `core_defect_map` · `eds_fail_map` · `wafer_process` |
| **결손 보정 (enrichment)** | `enrichment_rules.json` | `source_table`로 쓸 원천(샘플 예: `bonding_log`) · `derived_table`로 쓸 파생(샘플 예: `bonding_job_inventory`, `decision_key`를 `composite_key_source`로 갖는 키 계약 필요) |
| **맵 오버레이** | `map_overlay_config.json` | 겹쳐 볼 맵 테이블 전부. **단 선언 없이도 동작합니다**(`table_config`에서 자동 유도) — 컬럼명이 관례와 다를 때만 선언 |
| **[F5] 프리셋 라우팅** | `map_overlay_config.json` (`preset_routing`) | 라우팅할 맵 테이블. ①을 켤 때만 **제품코드 조회 테이블**(운영 소유, 예: `product_master`)이 `table_config.json`에 추가로 선언돼야 합니다 — **미선언이 정상 구성**이고 그때는 패턴 규칙만으로 동작합니다 |
| **void(보이드) 관측** (2026-08-13 `346aa88`) | 없음 — 선언이 곧 전부입니다 | `inspection_run`(**분모** — 스캔이 있었다) · `void_obs`(관측). **`.sample`에 두 선언이 그대로 실려 있으니 손복사**하십시오(제품 소유 테이블이 아니므로 `install_product_tables.py`는 이것을 옮기지 않습니다). 🔴 **켜는 순서가 있습니다 — 선언 → 리로드(테이블 생성) → 인덱스 → 파서 shim → 파일**: [process/OPERATOR_RUNBOOK §4](../process/OPERATOR_RUNBOOK.md). 🔴 **둘 다 `map_key_columns`를 선언하지 않습니다**(런은 웨이퍼 격자가 아니고 보이드는 연속 좌표의 점입니다) — 선언하면 이유 없이 `replace_map` purge 스코핑과 [R3](../architecture/SCHEMA_CANON.md)의 사고 반경에 들어갑니다. 🔴 **등급·면적 컬럼을 «추가하지 마십시오»** — 합불은 레시피 임계에 달렸고 면적은 식 인덱스가 답합니다([data_model §1.2-bis](../architecture/data_model.md)) |

> 위 표의 이름(`dt_log`, `bonding_log` …)은 **`.sample`이 쓰는 예시일 뿐 표준이 아닙니다.** 현장 테이블명이 다르면 그 이름 그대로 선언하고 바인딩만 맞추면 됩니다 — 코드는 실테이블명을 하드코딩하지 않습니다.

> 검증: `GET /api/transfer-plan/stages`의 `roles`·`plan_store` / `GET /api/bonding-plan/core-summary`의 role 상태가 `connected`인지 확인하십시오. `missing`이면 ①테이블 미선언 ②바인딩의 컬럼명 오타 ③필수 역할키 누락 순으로 의심하십시오.

### 5.9 `maps.json` (**UI/API로 관리 권장**)

프리셋 등록 절차(API 경로·손편집 주의)와 키 사전 → [**config/maps.md**](./config/maps.md)

> **[F5] 프리셋을 참조하는 곳** — `transfer_plan_config.target_map.preset`, 그리고 `map_overlay_config.preset_routing`(§5.8-bis). **수를 적지 않습니다 — 참조처는 늘어납니다.** 둘 다 **프리셋 키 또는 `name`**으로 참조하므로, 프리셋을 지우거나 이름을 바꾸면 그 참조가 끊깁니다(라우팅은 끊긴 참조를 `preset_missing`으로 **거절**합니다 — 다른 프리셋으로 대체하지 않습니다).

---

## 6. 함정 모음 ★

**A. `table_config.json` JSON 문법 오류** — ✅ **2026-07-29 수정됨(#13). 이제 조용하지 않습니다.**
예전에는 로더가 파싱 실패 시 **로그 없이 `{}`** 를 반환했고, 그래서 손상된 config로 **재기동하면 모든 테이블이 조용히 사라졌습니다**. 지금은 두 갈래로 나뉩니다.

- **기동 시점**: 웹서버가 **뜨지 않습니다**(fail-fast). `[Boot] Refusing to start - table_config.json is not valid JSON: '<경로>' -> line N column M ...` 를 남기고 종료합니다. 빈 화면으로 뜨는 것보다 안 뜨는 편이 낫습니다 — 빈 화면은 데이터 유실처럼 보이는데 로그가 깨끗해서 실마리가 없습니다.
- **가동 중(핫리로드)**: 종전처럼 `{}`를 반환해 **기존 싱글턴을 지키되**, `[Config] table_config.json is not valid JSON: '<경로>' -> line N column M ...` ERROR를 남깁니다. 스키마 편집이 반영되지 않았다는 사실이 로그에 드러납니다.

> ⚠️ fail-fast는 **파싱 실패에만** 적용됩니다. 파일이 없거나(신규 설치), 읽기에 실패했거나(락·권한), JSON으로는 유효한데 선언이 이상한 경우에는 **기동을 막지 않습니다.** 의미 수준 불만으로 운영 서버가 안 뜨는 것은 그 불만보다 큰 사고입니다.

**A-2. BOM은 손상이 아닙니다 — 그런데 예전엔 손상 취급이었습니다** — ✅ **2026-07-29 수정됨(H1).**
로더가 엄격한 `utf-8`로 디코딩해서, **BOM이 붙은 멀쩡한 config가 파싱 실패가 되고 위 A의 fail-fast와 곱해져 웹서버가 영영 안 뜨는** 상태를 만들었습니다. Windows에서 BOM은 예외가 아니라 **기본값**입니다 — PowerShell 5.1의 `Set-Content -Encoding utf8`·`Out-File`이 UTF-8 BOM을, `>` 리다이렉트가 UTF-16 LE를 씁니다. 메모장에도 "UTF-8 with BOM"이 있습니다. **파일은 모든 에디터에서 완벽해 보이는데 다음 재기동에 서버가 안 뜹니다.**
지금은 UTF-8 BOM · UTF-16 LE/BE · UTF-32 BOM을 인식해 **쓰인 인코딩으로 읽습니다.** 관용이 아닙니다 — **BOM 없는 잘못된 인코딩(BOM 없는 cp949 등)은 그대로 거부**합니다.

**A-3. 최상위가 객체가 아닌 JSON(`[]`·`null`)** — ✅ **2026-07-29 수정됨(H5).**
게이트가 `json.loads` 결과를 검사 없이 통과시켰습니다. 측정: `[]` → `init_dynamic_models`가 `AttributeError` → main의 광범위 `except`가 잡음 → **동적 모델 0개로 부팅, ERROR 한 줄.** UI는 비어 보이고 로그는 거의 깨끗합니다 — **A의 fail-fast가 없애려던 실패 그 자체**입니다. `null`은 더 나빴습니다(프로세스 수명 내내 `TABLE_CONFIG`가 `None`). 최상위 타입 검사는 의미 수준 트집이 아니라 **"이 문서는 테이블 맵이 아니다"** 이므로 파싱 실패와 같은 급으로 다룹니다. 빈 파일도 같습니다(잘림과 구분할 수 없습니다).

**A-4. `.sample`과 실 파일은 «조용히» 갈라지고, 깨진 선언을 받을 사람은 «새 박스뿐»입니다** (2026-08-13 `272da5b`)
`server/config/*`가 gitignore인 것은 **설계**입니다 — 배포가 운영자의 조정본을 덮어쓰면 안 되니까요. 그 설계가 사는 실패 양식이 정확히 이것입니다: 둘이 갈라져도 **아무도 통보받지 않고**, 깨진 `.sample`은 **이 박스에서 영원히 무해**하며 **처음 설치되는 환경에서만** 발현합니다.
- **실제 사례**: `core_wafer_map.map_key_columns`가 추적되는 `.sample`에서 [R3](../architecture/SCHEMA_CANON.md)를 위반하고 있었습니다(`[wafer_id]`가 `composite_key_source`에 없음). 규칙 위반보다 나쁜 것은 **그 컬럼이 세 줄 위 주석에 「의도적으로 희소하다 — 부재가 곧 보정 작업 항목이다」라고 적혀 있다**는 점입니다. **희소한 비키 컬럼으로 스코프한 purge는 아무것도 스코프하지 못하므로**, 아직 보정되지 않은 모든 행에 대해 `replace_map`이 200을 내고 **아무것도 지우지 않습니다.** 라이브 config는 처음부터 옳은 `[core_lot, core_slot]`을 들고 있었고 — **그래서 이 박스에서는 아무도 못 봤습니다.**
- 🔴 **눈에 띈 테이블 하나만 고치지 말고 규칙을 «전 테이블에» 다시 돌리십시오** — 한 테이블에만 적용한 규칙은 적용되지 않은 규칙입니다. 검출기는 `server/scripts/audit_schema_canon.py`.
- **`map_overlay_config.json.sample`에 `core_usage_map`의 바인딩이 빠져 있었습니다.** 그 테이블은 **양쪽 table_config 모두에 선언돼 있어** 새 박스는 테이블을 받고 칠할 방법은 못 받습니다 — 컬럼이 이름공간을 타서(`core_x`/`core_y`/`used_count`) **유도가 닿지 못하는**, 그 파일 자신의 `__derived_note`가 「반드시 선언하라」고 적은 바로 그 경우입니다.
- **이유는 라이브 파일에도 주석 키로 함께 옮겼습니다** — 운영자의 박스는 `.sample`을 **읽지 않으므로**, 안 그러면 올바른 값을 들고 **그것이 무엇을 막고 있는지에 대한 기록은 없는** 상태가 됩니다.
- ⚠️ **아직 안 한 것(대기 중)**: 라이브 `table_config.json`에 `.sample`이 가진 선언 넷이 없습니다(`dt_job_attribution`·`eqp_frame_attribution`·그리고 은퇴한 `map_doe`/`map_doe_source`). 채택은 **돌고 있는 모든 프로세스가 읽는 것을 바꾸므로** 측정 중인 레인이 착지한 뒤로 미뤘습니다.
- ✅ **함께 확인하고 무해했던 것**: 라이브 `ingestion_settings.json`이 `.sample`이 선언한 키 열다섯을 생략하고 있으나 **모든 기본값이 선언값과 같습니다** — 파일이 아니라 **코드에** 물어서 확인했습니다.

**B. 에디터의 "원자적 저장"(temp + rename)** — ✅ **2026-07-29 수정됨(#9 + H3).**
예전 watcher는 `on_modified`만 처리해서, temp 파일에 쓰고 rename하는 도구(일부 에디터·에이전트 Edit 도구)로 `table_config.json`을 고치면 **ALTER가 조용히 누락**됐습니다. 2026-07-29 1차 수정이 `on_moved`를 넣었지만 **그것으로 계급이 닫히지 않았습니다** — rename의 원본 temp가 **다른 디렉터리**에 있으면 `moved`가 아예 없고 `deleted`+`created`만 옵니다(`tempfile.mkstemp()`의 기본이 시스템 temp 디렉터리입니다). `on_created`까지 넣은 지금 세 형태 모두 반영됩니다(§4.4).
→ 그래도 **확인 자체는 여전히 §4.3의 `information_schema`로** 하십시오. 아래 D가 그대로 유효하기 때문입니다.

**B-2. 연속 저장 / 느린 저장** — ✅ **2026-07-29 수정됨(H2).**
디바운스가 **리딩 엣지**(창 안 첫 이벤트만 처리, 나머지 폐기)였습니다. 측정된 결과 두 가지 — ⓐ **0.3초 간격 저장 2회에서 두 번째가 통째로 소실**(디스크는 3컬럼, 물리 테이블은 2컬럼, 로그에는 성공 줄만) ⓑ **느린 비원자적 쓰기**에서 잘린 파일을 읽고 abort한 뒤, 1초 안에 들어온 **완료 이벤트를 버림**(`crud.update_table_config`가 평범한 `open(w)`이라 제품 자신의 쓰기 경로였습니다). 지금은 **트레일링 엣지**라 이벤트마다 재무장하고 마지막 이벤트 후 1초에 발화합니다 — 버려지는 저장이 없습니다.
→ 반영은 **마지막 쓰기로부터 약 1초 뒤**입니다. 저장 직후 즉시 확인하면 아직 안 보일 수 있습니다.

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
테이블이 없거나 컬럼명이 틀리면 **에러가 아니라 `missing`** 이고, HTTP는 200으로 나옵니다. **[2026-08-04] 보조 role이 아예 빠진 것은 `missing`이 아니라 `not_declared`입니다** — 그때는 가용이 감춰지지 않고 그 감산 없이 **숫자로** 나오며, 빠진 감산 종류는 응답의 `inactive_subtractions`가 말합니다(§5.8). **숫자가 0인데 에러가 없다면 응답의 `sources` 상태부터 확인**하십시오 — `missing`(바인딩 문제)인지 `connected(align_unavailable)`(격자 규격 없음)인지 `connected(count_only)`/`connected(column_unresolved:...)`(좌표 없는 로그·fail 원천 / 컬럼명 오타 — §5.8)인지에 따라 고칠 곳이 다릅니다.

**J. `.sample`을 편집해도 아무 일도 일어나지 않습니다.**
코드는 확장자 없는 정확한 파일명만 읽습니다. `.bak` / `.v1.bak`도 마찬가지입니다.

**K. `scheduler_status.json`은 입력이 아니라 출력입니다.**
스케줄러가 매 사이클 덮어씁니다. 손으로 고쳐도 무의미하며, `active` 필드는 API가 `auto_update_control.json`에서 실시간으로 다시 계산해 덮어씁니다.

**L. `server/config/*.json`은 어드민 UI에서 편집할 수 없습니다.**
Monaco 코드 에디터는 `.py`(맵퍼·인제션·수집기 스크립트)만 다룹니다. 예외적으로 맵 프리셋과 수집기 토글만 전용 API가 있습니다.

**M. `table_config`에 없는 컬럼은 저장에서 조용히 버려지고 HTTP는 200입니다.** ★
`crud`는 미선언 컬럼을 드롭한 뒤 성공을 반환합니다 — 컬럼 오타·config 누락이 **저장 성공처럼 보입니다.** 실제로 `map_doe`가 이 경로로 `eventtime`을 잃고 있었습니다.
2026-07-27부터 **`(테이블, 컬럼)`당 1회** `[Schema]` 경고가 남습니다(핫패스라 반복 경고는 접습니다). 값이 안 들어갈 때 의심 순서: ①`table_config`에 그 컬럼이 있는가 ②철자 ③리로드 경로(§4.1).
> ✅ 이 경고는 **워처 프로세스의 로그 파일에도 남습니다**(2026-07-27 `d56e7e2` — 그 전까지는 `logging.lastResort`로 떨어져 파일에 안 남았습니다).

**N. 격리 환경에서 config를 고쳤는데 운영이 안 바뀝니다(그리고 그 반대도).**
`ASSY_DATA_ROOT`가 걸려 있으면 config 트리 전체가 `dev_env/config`입니다. 어느 쪽을 고쳤는지 헷갈리면 `python server/scripts/dev_env/devenv.py status`로 확인하십시오 → [DEPLOY_SETUP §5](./DEPLOY_SETUP.md).

**O. 선언을 되돌려도 물리 테이블·컬럼은 남습니다 — 선언은 한 방향 문입니다.** ★
watcher는 새 선언을 `CREATE TABLE`로, 새 컬럼을 `ALTER TABLE ADD COLUMN`으로 바꾸지만 **지우는 경로는 없습니다.** 선언을 되돌리면 조회·인제션·화면에서는 사라지지만 **물리 객체는 그대로 남아, 어디에도 선언되지 않은 채** 남습니다(2026-07-27 `map_band_registry` 실사례 — 폐기된 밴드 모델의 선언을 되돌렸는데 빈 테이블이 남았습니다).
찾는 방법(읽기 전용, DDL 없음 — `DROP` 문을 출력만 합니다):

```bash
conda run -n assy_manager python server/scripts/list_undeclared_tables.py
```

**비어 있는** 미선언 테이블은 되돌린 선언의 잔여물일 가능성이 높고, **행이 있는** 것은 config 이전의 레거시일 가능성이 높습니다 — 후자는 감으로 지우지 마십시오. 판단과 실행은 사람이 합니다 → [ROLLBACK_PROCEDURE §5](./ROLLBACK_PROCEDURE.md).

**P. `version_column`을 파생 타깃 테이블에 걸면 그 파생 경로가 멈춥니다.** ★ (2026-08-04 `092b83f`)
버전 게이트를 건 테이블에는 **버전 컬럼을 들고 오는 기계만** 기존 행을 덮어쓸 수 있습니다. 파일 인제션은 파일에 그 컬럼이 있으니 들고 오고, 사람의 편집은 면제이며, 맵 메타 자동 등록은 부재 행만 만들어 안전합니다. **그런데 체인 워커·체인 재적용 R1·결손 보정 자동 확정은 자기 매퍼가 만든 컬럼만 씁니다** — 버전 컬럼이 없으니 **기존 행에 대한 파생 쓰기가 전부 `version_missing`으로 거절**됩니다.
조용하지는 않습니다(`[VersionGate]` WARNING + 배치마다 INFO). 다만 **선언한 뒤에야 드러나고**, 화면상 증상은 「체인이 멈춘 것 같다」입니다.
**선언 전에 그 테이블이 `chain_rules.json`의 `target_table`이거나 `enrichment_rules.json`의 `derived_table`인지 확인하십시오** — 명령 한 줄과 실측 예, 나왔을 때 할 일은 [config/table_config §7.2](./config/table_config.md). 체인 룰이 `enabled:false`여도 **없는 것으로 세지 마십시오**(켜는 순간 같은 문제가 됩니다).

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
