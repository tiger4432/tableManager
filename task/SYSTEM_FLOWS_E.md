# SYSTEM_FLOWS — 2차 실측 네 흐름 (③ 배치 업서트 · ④ 변경 이력 · ⑤ 가상 조인 · ⑥ 값 제안)

> **입력:** `docs/architecture/SYSTEM_FLOWS.md` §1 칸 정의 · §3 채우는 규칙 그대로.
> **범례:** ✅ 이어짐 / ⚠️ 반쪽 / 🔴 끊김 / ⚰️ 죽은 갈래
> **측정 리비전:** 🔴 **측정 «중»에 HEAD 가 `6bb4e79a` → `907c8995` 로 움직였다.** 움직인 커밋이 하필
> 이 파일의 측정 대상이다 — `ee1e5d74` 「nine builders become one」이 `batch_refresh_required` 의
> 손수 작성 아홉을 `event_constants.batch_refresh_message()` 하나로 접었다.
> **이 문서의 모든 수치는 `907c8995` 에서 «다시 재서» 확정했다.** 앞판에서 잰 「손수 작성 9」는
> 이 문서에 «그대로 싣지 않았다» — 대신 §③-B 에 그 착지가 «무엇을 닫고 무엇을 안 닫았는지»를 적었다.
> **읽은 문서 먼저:** `docs/spec/batch_update_technical_specification.md`(623줄, 전량) ·
> `docs/guide/config/virtual_join_rules.md` · `docs/guide/config/audit_history_config.md` ·
> `docs/guide/config/suggest_config.md` · `docs/architecture/data_model.md` ·
> `CODE_MAP.md` §1.1-ter · §1.2 · §1.3 · §2 · §5-A · §5-C · §5-D · §7.

---

## 🔴 먼저 — 이 저장소에서 «검색이 못 보는» 파일이 둘 있다 (측정 위생)

```
client2/src/enrichment.js       62,726 바이트 중 NUL «1»
client2/src/map2/authoring.js   19,063 바이트 중 NUL «1»
=> grep 이 이 둘을 "Binary file … matches" 로 처리하고 «줄을 안 보여 준다»
   `grep -a` 를 안 붙이면 이 두 파일의 히트는 «0으로 세어진다»
```
🔴 **이 문서를 쓰는 동안 제가 그 함정에 «한 번» 빠졌습니다** — `effort` 를 싣는 쓰기 자리를 세면서
`enrichment.js:868` 을 놓쳤고, 그래서 「5 중 5」로 잘못 셀 뻔했습니다(실제는 아래의 10 중 7).
1차 실측이 「검색이 못 보는 2,610줄」이라 적은 것이 이 부류이고, **이 문서의 모든 client2 계수는
`grep -a` 로 다시 셌습니다.**

⚠️ 그리고 그 확인 과정에서 제가 «두 번째» 실수를 했습니다 — `grep -rl $'\0'` 로 세려 했는데
bash 가 `$'\0'` 를 «빈 문자열»로 만들어 **client2/src 전 파일이 히트**했습니다. 계기가 자기 고장에서
눈이 먼 자리라, 파이썬으로 바이트를 직접 세어 «둘»로 확정했습니다.

---

# ③ 배치 업서트 (그리드 편집 → `crud.apply_batch_updates` → 표 → outbox)

## ③-A 이음매 표

| # | 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 (실측) | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|---|
| B-1 | AG-Grid 셀 편집 | `client2/src/api.js::handleCellEdit`(374) | `grid.js:1238` `onCellValueChanged` → `await handleCellEdit(event)` | 함수 인자 | 구조분해 **넷**: `{data, colDef, newValue, oldValue}`(api.js:375). 편집기 핸들도 「후보에서 골랐나」도 «안 온다» | 1 (`grid.js:1239`) | 🔊 숫자형 거절은 `alert()` + `❌ Invalid number format`(api.js:396·408) | ✅ |
| B-2 | `api.js:463` | **`PUT /tables/{t}/data/updates`** (`main.py:2903`) | 위 | HTTP PUT 바디 | 조립되는 최상위 키 **셋**: `updates:[{row_id, updates:{col:value}, source_name:'user', updated_by}]` · `silent:false` · `effort: snapshot()`(api.js:445–460) | 라우트 핸들러 1 | 🔊 `!res.ok` → `alert('수정 사항 저장 실패: …')` + 그리드 값 «롤백»(api.js:508–521) | ✅ |
| B-3 | 클라 쓰기 자리 **열** | 같은 라우트 | 각기 다른 사람 행위 | HTTP PUT | 🔴 **`effort` 를 싣는 것은 «7»**(api.js:459 · clipboard.js:594·853 · enrichment.js:868 · main.js:2232 · map_editor.js:6261 · ui.js:243). **안 싣는 것 «3»**(map_editor.js:4429 스플릿 레지스트리 · 6237 헤더 메타 · 9886 맵 규격 저장) | 서버 1 | — | ✅ **셋 다 «의도»다** — 소스 주석이 「한 사람 행위를 세 번 청구하지 않기 위해」라고 각 자리에 적혀 있고, 그 한 번은 6261 이 낸다 |
| B-4 | `apply_batch_updates_endpoint` | `main._validate_effort`(2823) | 핸들러 «첫 문장» | 함수 인자 | 허용 키 **정확히 다섯**: `session_id·key·mouse·nav·nav_preserved`. 클라 `snapshot()`(effort_meter.js:454–464)이 내는 것도 **같은 다섯** — 이름·개수 일치 | 1 | 🔊 **로그에만**: `logger.error("[EffortMetric] table=… ")`. 응답에는 `effort_error` 로 실린다 | ⚠️ (B-11 참조) |
| B-5 | 엔드포인트 | `crud.refuse_virtual_join_columns`(crud.py:3337) | `apply_batch_updates` «첫 문장» | 함수 인자 | `virtual_join_executor.virtual_only_columns(db, table)` 로 얻은 집합과 배치의 컬럼 교집합. 배치 단위라 **위반 컬럼을 한 번에 전부 이름으로 부른다** | 1 (`crud.py:3612`) | 🔊 `ValueError` → **400** → B-2 의 `alert()`. 문안: 「… 가상 조인으로 조회 시점에 계산되는 값이라 저장할 수 없습니다 … 조인 원본 테이블에서 수정하세요」 | ✅ **거절이 «다음 행동»까지 말한다** |
| B-6 | `crud.apply_batch_updates` | 데이터 표 + `cell_sources` + `cell_overwrites` | 위 | DB bulk upsert | `BULK_CHUNK_SIZE = 1000`(crud.py:1717) 청킹 · `_pg_multirow_upsert` 멀티행 VALUES · 실패 시 per-chunk VALUES 폴백(crud.py:1752) | — | 🔊 업무키 중복은 **409** + 「다른 프로세스가 방금 같은 키를 저장했을 수 있습니다 — 새로고침 후 다시 시도하세요」(main.py) | ✅ 확장성 규율 준수 |
| B-7 | 데이터 표 행 쓰기 | `database_outbox` | **`@event.listens_for(Session,"before_flush")`** (`database/database.py:127`) | DB 행 + `NOTIFY` | per-row(`stage_event`): `{row_id, business_key, data{col:{value,is_overwrite:False,updated_by:"system"}}, transaction_id, updated_by, source_name, timestamp}` · collapsed(`stage_collapsed_event`): `{row_ids[≤1000], row_count, table_name, transaction_id, updated_by, source_name, timestamp}` | 리스너 등록 1 (전역 Session) · outbox 를 읽는 비시험 모듈 **11** (최다: `chain_ingestion_worker` 31히트) | 🔇 **`NOTIFY` 실패는 통째로 삼킨다** — `except Exception: pass`(database.py:339–341). 대가는 유실이 아니라 폴백 폴링 | ✅ |
| B-8 | `request_outbox_mode` | 위 리스너의 갈래 | 설정자 **하나** | contextvar | `OUTBOX_MODE_COLLAPSED` 를 «세우는 곳»은 `parsers/directory_watcher.py:2658` **하나**. 즉 **그리드 편집·붙여넣기·맵 Push 는 언제나 per-row** | 갈래 2, 설정자 1 | — | ⚠️ 접기 이득이 «파일 인제션에만» 간다. 2만 셀 맵 Push 는 여전히 per-row 2만 행 |
| B-9 | 엔드포인트 | `fetch_and_merge_metadata(..., include_sources=**False**)` (`main.py:2995`) | 브로드캐스트 항목 조립 | 함수 인자 | 🔴 **레이어링 이음매가 여기서 «좁아진다»** — §③-C 전체가 이 한 칸이다 | 1 | 🔇 조용 | ⚠️ |
| B-10 | 엔드포인트 | `crud.record_interaction_effort`(crud.py:1580) | 🔴 **`created_logs` 에 `source_name == "user"` 인 항목이 «있을 때만»**(main.py:3121–3126) | 함수 인자 → `interaction_effort_logs` 행 | `(tx_id, session_id, key, mouse, nav, nav_preserved)`. `created_logs` dict 가 `source_name` 을 «실제로 싣는다»(crud.py:1445) — 이 조건은 «참이 될 수 있다» | 1 | 🔊 `IntegrityError` → False(재시도, 첫 기록이 이김) · 그 외 → `print("[EffortMetric] failed …")` + False | ✅ |
| B-11 | HTTP 응답 **9키** | 클라 | 같은 요청 | JSON 바디 | `status·updated_count·change_count·deleted_row_ids·created_logs·total_log_count·effort_recorded·effort_error·scope`(main.py:3138–3161) | 🔴 **읽는 것 «3», 안 읽는 것 «5»** — §③-D 표 | 🔇 조용 | ⚠️ |
| B-12 | `background_tasks.add_task(async_broadcast)` | `manager.broadcast` | HTTP 200 **뒤** | WebSocket JSON | `batch_row_upsert` 를 **500개 청크**로 쪼개 발사(main.py:3070–3086). 상한 초과면 대신 `batch_refresh_required` 한 발 | 클라 1 (`websocket.js:382`) | 🔇 **조용.** 브로드캐스트 실패는 200 이 이미 나간 뒤다 | ✅ |
| B-13 | `batch_row_upsert` 발사 자리 **6** | `websocket.js:382` | 각기 다른 라우트 | WS JSON | 🔴 **손수 작성 «여섯», 모양 «넷»** — §③-B 표 | 클라 «하나»가 넷을 다 받는다 | 🔇 조용 | ⚠️ |
| B-14 | `batch_refresh_required` 발사 자리 **9** | `websocket.js:479` | 각기 다른 라우트/워커 | WS JSON | ✅ **`907c8995` 부터 «전부» `event_constants.batch_refresh_message()` 를 통과한다**(손수 작성 리터럴 **0**) | 클라 1 | 🔇 조용 | ✅ **(오늘 `ee1e5d74` 가 닫았다)** |
| B-15 | `websocket.js:382` 핸들러 | AG-Grid `applyTransaction` | WS 메시지 도착 | 함수 인자 | 읽는 것: `msg.items` 와 항목별 `row_id·created_at·updated_at·data`. **`data` 는 «행 전체»를 통으로 병합한다**(`{...oldRowData.data, ...item.data}`, websocket.js:397–401) | 1 | 🔇 조용 | ✅ |

## ③-B 「캐노니컬 빌더」 이음매 — 🔴 **착지가 «읽히지 않는 쪽»에 났다**

지시서가 「다른 레인이 캐노니컬 빌더를 도입 중이니 이음매를 재기만 하라」고 했다. 재 봤더니
**빌더는 이미 착지했고, 착지한 쪽이 클라가 «안 읽는» 페이로드다.**

```
batch_refresh_required   발사 9 · 손수 작성 «0» · 전부 batch_refresh_message() 경유   ✅ 닫힘
batch_row_upsert         발사 6 · 손수 작성 «6» · 빌더 «없음» · 모양 «넷»            ⚠️ 열림
```

### `batch_row_upsert` 여섯 자리의 «최상위 키» 전건 (실측, `907c8995`)

| 자리 | 무엇이 발사하나 | 최상위 키 | 수 |
|---|---|---|---|
| `main.py:3078` | `PUT /tables/{t}/data/updates` (**이 흐름**) | `event·table_name·items·change_count·updated_by·transaction_id·created_logs` | 7 |
| `main.py:3352` | `DELETE …/{c}/sources/{s}` | `event·table_name·items·change_count` | 4 |
| `main.py:3398` | `PUT …/{c}/priority` (Pin) | `event·table_name·items·change_count` | 4 |
| `main.py:3495` | `PUT /tables/{t}/cells/priority/batch` | `event·table_name·items·change_count·created_logs` | 5 |
| `main.py:3558` | `POST /tables/{t}/cells/sources/delete/batch` | `event·table_name·items·change_count·created_logs` | 5 |
| `chain_ingestion_worker.py:1093` | 체인 워커 | `event·table_name·items·updated_by·transaction_id·created_logs·total_log_count` | 7 |

🔴 **체인 워커의 것만 `change_count` 가 «없다».** 나머지 다섯은 전부 싣는다.
그리고 `batch_refresh_message` 의 docstring 이 바로 그 키에 대해 이렇게 적어 두었다 —
「**`change_count` IS ALWAYS PRESENT, INCLUDING WHEN IT IS 0**. `{change_count: 0}` 과
키가 없는 것은 다른 객체다」. **접힌 쪽에서는 그 규율이 강제되고, 안 접힌 쪽에서는 이미 깨져 있다.**

### 왜 지금은 «안 터지나» — 그리고 그것이 왜 안심할 근거가 아닌가
```
클라가 batch_row_upsert 에서 읽는 것   items · items[].row_id/created_at/updated_at/data   (websocket.js:382–425)
클라가 «안 읽는» 것                    change_count · updated_by · transaction_id · total_log_count
=> 오늘 여섯 모양이 «같은 화면»을 낸다. 차이가 «보이지 않는다»
```
🔴 그래서 이건 「무해」가 아니라 **「무증상」**이다. `change_count` 를 읽는 소비자가 «하나라도»
생기는 날, 여섯 중 하나가 `undefined` 를 내고 **그 하나가 체인 워커 경로**다 — 사람이 안 누르는,
그래서 개발 중에 제일 늦게 밟히는 자리.

📌 **총괄 판정 요청 (경계 계약이라 제가 못 정합니다):** `batch_row_upsert` 에도 같은 빌더를
   낼 것인가. 낸다면 `change_count` 를 체인 워커 자리에 «더하는» 것은 순수 추가라 계약 불변이지만,
   **더할지 말지는 경계 계약 결정**이라 여기서 멈춥니다.

## ③-C 🔴 레이어링 이음매 — 「**`priority_source` 를 «두 규칙»이 만든다**」 (핵심가치 넷)

`fetch_and_merge_metadata`(main.py:817)는 행 페이로드의 **유일한 직렬화 지점**이다(소스 주석이
그렇게 단언하고, 가상 조인도 여기서 붙는다). 그런데 **그 안에 갈래가 둘이다.**

```python
# main.py:895-909
if not include_sources:                      # 싼 길
    if manual_pin == "collision_merge" or updated_by == "collision_merge":  priority_source = "collision_merge"
    elif is_ow or updated_by == "user" or manual_pin == "user":             priority_source = "user"
    else:                                                                   priority_source = None
else:                                        # 선언된 길
    _, priority_source = crud.compute_priority_value(col_srcs, manual_pin, table_name,
                                                     ingested_at_by_source=ingested_map.get(key))
```

### 어느 라우트가 어느 길을 타나 — 호출부 **여섯** 전건

| 호출부 | 라우트 | `include_sources` |
|---|---|---|
| `main.py:1986` | **`GET /tables/{t}/data`** — 그리드 본 화면 | **False** (싼 길) |
| `main.py:2995` | **`PUT /tables/{t}/data/updates`** — 이 흐름의 WS 항목 | **False** (싼 길) |
| `main.py:2647` | `GET /tables/{t}/{row_id}` — 단일 행 | True |
| `main.py:3377` | `PUT …/{c}/priority` | True |
| `main.py:3453` | `PUT /tables/{t}/cells/priority/batch` | True |
| `main.py:3525` | `POST /tables/{t}/cells/sources/delete/batch` | True |

### 그래서 무엇이 «말해질 수 없게» 되나
```
선언된 서열   crud.SOURCE_PRIORITY (crud.py:619) — user 0 · collision_merge 1 · pipeline_parser 2
                                                 · custom_script 3 · chain_ingestion 4   => «다섯»
싼 길이 낼 수 있는 값                              user · collision_merge · None          => «셋»
=> pipeline_parser · custom_script · chain_ingestion 는 «그리드 본 화면»에 도달할 수 없다
   그리고 sources 도 {} 로 비어 나간다
```

🔴 **판별 사례 — 두 길이 «실제로 어긋나는» 입력이 있다.** 어떤 셀에 `pipeline_parser` 소스만
있고 사용자 덮어쓰기가 없는 경우:
```
싼 길(그리드)      ow_info 없음 -> is_ow=False, updated_by="system", manual_pin=None -> priority_source = None
선언된 길(단일 행)  compute_priority_value({pipeline_parser: v}) ->               priority_source = "pipeline_parser"
=> «같은 셀»이 어느 라우트로 왔느냐에 따라 다른 답을 낸다
```

### ✅ 그런데 핵심가치 넷 자체는 «지켜지고 있다» — 이 판정이 이 절에서 제일 중요하다
```
그리드가 그 값에 «묻는 질문»은 둘뿐이다:
   grid.js:676  'cell-collision-merge'  <- priority_source === 'collision_merge'
   grid.js:684  'cell-overwrite'        <- priority_source === 'user'
=> 싼 길이 낼 수 있는 셋이 «정확히» 그 두 질문에 답하는 데 필요한 전부다
   「사람이 쓴 것이 기계를 이긴다」는 그리드에서 «옳게» 그려진다
```
🔴 **그러므로 이 칸의 발견은 「레이어링이 깨졌다」가 «아니다».** 발견은 이것이다 —
**한 계약 필드가 두 규칙으로 채워지고, 둘이 어긋나는 입력이 존재하며, 그 어긋남을 «아무것도 안 알린다».**
오늘 그리드가 그 차이를 안 묻기 때문에 무증상이고, `enrichment.js:166` 처럼 **`priority_source` 를
«문자열 그대로» 화면에 내놓는 소비자**가 이미 있어서 — 그 화면은 같은 셀을 「pipeline_parser」로도
「(빈칸)」으로도 그릴 수 있다.

### ⚠️ 그리고 «머신 소스에 핀을 꽂으면» 어느 길로도 안 보인다
`PUT …/{c}/priority` 로 `source_name="pipeline_parser"` 를 핀하면:
- 선언된 길: `priority_source = "pipeline_parser"` → 두 CSS 규칙 «둘 다» 거짓 → **표시 없음**
- 싼 길: `manual_pin` 이 `"user"` 도 `"collision_merge"` 도 아니므로 → `None` → **표시 없음**
- 다만 `is_overwrite`(=`has_overwrite`)는 `manual_pin is not None` 이라 **True** — 읽는 CSS 가 없다

🔴 **사람이 명시적으로 핀을 꽂았는데 그리드에 «아무 표시도» 안 난다.** 조용하다.

## ③-D 응답 9키의 소비자 — 「읽는 것 3, 안 읽는 것 5」

| 응답 키 | 세우는 자리 | client2 읽는 곳 (`grep -a`) | 판정 |
|---|---|---|---|
| `change_count` | main.py:3141 | **5** — api.js:479 · clipboard.js:864 · main.js:2273 · ui.js:254 (+harness) | ✅ |
| `effort_recorded` | main.py:3156 | **1** — effort_meter.js:495 (`commitIfRecorded`) | ✅ |
| `updated_count` | main.py:3140 | **2** — map_editor.js:6351·6354 (둘 다 폴백 표현) | ✅ |
| `status` | main.py:3139 | **0** (이 응답에 대해) | ⚠️ |
| `deleted_row_ids` | main.py:3142 | **0** | ⚠️ WS `batch_row_delete` 가 대신 나른다. 단 `silent:true` 면 그 WS 가 «안 나간다» |
| `created_logs` | main.py:3150 | **0** — 소스 주석이 「No consumer reads it」이라 «맞게» 적혀 있다 | ⚠️ 정직 |
| `total_log_count` | main.py:3152 | **0** | 🔴 아래 |
| `effort_error` | main.py:3159 | **0** | 🔴 아래 |
| `scope` | main.py:3161 | **0** (`result.scope` 0히트, `delete_ids_omitted` 0히트) | 🔴 아래 |

### 🔴 이 셋은 «소스 주석이 자기 소비자를 지어냈다»
세 자리 모두 소스가 **소비자의 존재를 전제로 설계 근거를 적어 두었다.** 그 소비자가 없다.

| 자리 | 주석이 단언하는 것 | 실측 |
|---|---|---|
| `main.py:3143–3152` | 「the honest total rides alongside **so a caller can detect truncation as `len(created_logs) < total_log_count`**」 | `total_log_count` 를 읽는 클라 **0**. 500건 절단이 화면에 «안 뜬다» |
| `main.py:2948–2955`(`delete_ids_omitted`) | 「**NOT a silent truncation**: the count rides the refresh signal **and the response's `scope.delete_ids_omitted`**」 | 두 나르개 «둘 다» 독자 0 — `deleted_row_ids_omitted`(WS) 0 · `delete_ids_omitted`(응답) 0. **문장이 단언하는 술어가 거짓이다** |
| `main.py:3157–3160`(`effort_error`) | F7 수리의 산출물 — 오타 난 키 이름을 «응답에» 실어 운영자가 알게 한다 | 읽는 클라 **0**. 살아 있는 청중은 `logger.error("[EffortMetric] …")` «서버 로그»뿐 |

⚠️ **「소비자 0」의 두 뜻을 가릅니다** — 판별 질문은 「이게 없으면 무엇을 «말할 수 없게» 되나」:
```
effort_error       없으면: 운영자가 «자기 계기가 죽은 것»을 영원히 모른다 (서버 로그를 여는 사람만 안다)
                   -> «퍼뜨리기». 빼는 게 아니라 읽는 쪽을 만들어야 하는 부류
total_log_count    없으면: 「이력 500건에서 잘렸다」를 말할 자리가 «사라진다»
                   -> «퍼뜨리기». 그리고 이건 ④ 변경 이력 흐름의 이음매이기도 하다
scope.*            없으면: replace_map 이 «무엇을 지웠는지»를 호출자가 못 확인한다
                   -> «퍼뜨리기». 특히 맵 Push 가 이 라우트를 replace_map:true 로 쓴다
=> 셋 다 「아무도 안 쓴다(빼기)」가 «아니다». 셋 다 마지막 홉이 없는 것이다
```

## ③-E ⚠️ 클라 두 쓰기 경로가 «같은 칸»을 다르게 낙관 갱신한다
```
api.js:485-488          단건 편집   data[col].value / .is_overwrite = true / .priority_source = 'user'
main.js:2250-2258       tx 모드 적용 data[col].value / .is_overwrite = true    <- priority_source «없음»
```
`grid.js:684` 의 `cell-overwrite` 는 **`priority_source === 'user'`** 를 본다(`is_overwrite` 가 아니다 —
`grid.js:837` 주석이 그렇게 적어 두었다). 그래서 **tx 모드로 적용한 셀은 덮어쓰기 표시가 «안 난다»** —
곧 도착하는 WS 델타가 덮어써 자가 치유하지만, **WS 가 끊긴 동안에는 안 난다.** 조용하다.

## ③-F 문서 정정 — `batch_update_technical_specification.md`

| 자리 | 적힌 것 | 실측 |
|---|---|---|
| §2 시퀀스 다이어그램 | `Client->>WS: POST /api/v1/tables/{table}/batch-update` | 🔴 **그런 라우트가 없다.** 실제는 `PUT /tables/{table_name}/data/updates`(main.py:2902). `/api/v1` 접두어도 없다. 문서 머리가 「코드 블록은 축약된 옛 사본」이라 자백하는데 **다이어그램은 그 면책에 안 들어 있다** — 그림이 산문보다 먼저 읽힌다 |
| §2 다이어그램 참여자 | `Client as Watcher/Worker Daemon` | ⚠️ 이 라우트의 실제 호출자 «열»은 전부 «브라우저»다. 워처·워커는 `crud` 를 직접 부른다(스키마 주석 `schemas.py:238` 이 그렇게 적는다) — 다이어그램이 «반대»를 그린다 |
| §3.1 제목 링크 | `crud.py#L506` | ⚠️ `apply_batch_updates` 는 현재 **crud.py:3601 근처**(`refuse_virtual_join_columns` 호출이 3612). 문서가 이미 「라인은 정본이 아니다」를 적고 있으나 링크는 그대로다 |
| §2 마지막 줄 | `WS-->>Client: 200 OK & Broadcast WebSocket Toast` | ⚠️ 순서가 «반대»다. 실측: 200 이 «먼저» 나가고 브로드캐스트는 `background_tasks.add_task(async_broadcast)`(main.py:3088)로 **그 뒤**에 돈다 |
| §3.0 (가상 조인 거부) | 「`apply_batch_updates` 의 첫 문장」 | ✅ **참이다** (crud.py:3612). 이 절은 정확하다 |

---

# ⑥ 값 제안 셀 에디터 (타이핑 → 후보 → 확정)

## ⑥-A 이음매 표

| # | 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 (실측) | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|---|
| V-1 | `grid.js:713` `buildColumnDefs` | `value_suggest.js:503` `SuggestCellEditor.init` | AG-Grid 가 `colDef.cellEditor = SuggestCellEditor` 를 인스턴스화. 등록 관문 `else if (!isSystem && colType === 'string')`(grid.js:704) | 함수 인자 (AG-Grid `params`) | 읽는 것: `params.column.getColId()`(511) · `cellStartedEdit`(556) · `eventKey`(557) · `value`(567) · `eGridCell`(858) · `stopEditing()`(802). **표 이름은 `params` 가 «안 나른다»** — 싱글턴 `state.currentTable`(510)에서 온다 | 1 | 🔇 **조용.** AG-Grid 가 기본 텍스트 편집기로 폴백하고 셀은 그냥 편집된다 (모듈 머리 vs.js:43–48 이 의도라고 적는다) | ✅ |
| V-2 | `value_suggest.js:574` `onInput` | `value_suggest.js:733` `runQuery` | `eInput.addEventListener('input', onInput)`(581); ArrowDown 재진입(950) | 함수 호출 + `setTimeout` | 후행 디바운스 `DEBOUNCE_MS = 90`(93). 발사 «전» 관문 셋(순서대로): `suppressUntilInput`(678) → `suggestible()`(679) → 로컬 좁히기(691) | 1 | 🔇 조용 — `closeList()` | ✅ |
| V-3 | `value_suggest.js:386` `requestValues` | **`GET /tables/{t}/columns/{c}/values`** (`main.py:2604`) | `runQuery` 가 `requestValues(table, column, prefix, REQUEST_LIMIT)`(736). `REQUEST_LIMIT = 12`(136) | HTTP GET 쿼리스트링 | 조립되는 쿼리 키 **정확히 둘**: `prefix` · `limit`(vs.js:390). ✅ **서버가 받는 것도 정확히 둘**(main.py:2611–2612) — **차이 0** | 1 | 🔇 사용자에겐 조용 — `catch` 가 `{ok:false}` 를 돌려주고 「Not a user-facing event」라 적혀 있다 | ✅ |
| V-4 | `main.py:2623` | `value_suggest.suggest_values`(vs.py:727) | 핸들러 본체 | 함수 인자 | `suggest_values(db, table, column, prefix=prefix, limit=limit)` — **`settings=` 는 «안 넘긴다»** → 요청마다 `resolve_settings(load_config())`(737–738) | 비시험 호출자 1 | 🔊 **거절 문안 «일곱»**이 각자 status 를 들고 나간다: 404 「선언되지 않은 테이블입니다」(560) · 400 「선언되지 않은 컬럼입니다」(563) · 400 「날짜/시간 컬럼은 값 제안을 지원하지 않습니다」(572) · 404 「모델이 준비되지 않은 테이블입니다」(577) · 400 「물리 테이블에 아직 없는 컬럼입니다」(580) · 400 「최소 {n}자를 입력해야」(745) · 400 「limit은 정수여야」(751) | ✅ |
| V-5 | `suggest_values` 결과 dict | HTTP 200 바디 | 반환(808·824·844) | JSON | 세우는 키 **아홉**: `table·column·prefix·values·truncated·limit·unavailable_reason·elapsed_ms·slow_reason`(vs.py:754–767) | 🔴 **읽는 것 «3»** | 서버 로그에만 🔊 (`[Suggest] … unavailable/deadline/slow`, vs.py:807·822·876) · 클라엔 🔇 (HTTP 는 200) | ⚠️ |
| V-6 | HTTP 바디 | `value_suggest.js:437–454` | `await res.json()`(427) | JSON | 읽는 것: `unavailable_reason`(437·442·443) · `values`(451) · `truncated`(452). **안 읽는 것 여섯**: `table·column·prefix·limit·elapsed_ms·slow_reason` | 2 (vs.js · map_editor.js) | 🔇 조용 — `console.debug` 한 줄 | ⚠️ |
| V-7 | `grid.js:998` `suppressKeyboardEvent` | `value_suggest.js:922` `onKeyDown` | `defaultColDef.suppressKeyboardEvent`(998) → `if (params.editing && isSuggestEditorActive())`(1011) → `handleEditorKey(event)`(1012) | 함수 인자 (`KeyboardEvent`) | 세 값 판정이 되돌아온다: `'suppress'`→`true`(1013) · `'accepted'`→`false`(1014) · `'pass'`→통과. Enter/Tab 은 `acceptHighlight()` 가 `eInput.value` 를 **동기적으로** 쓰고(916) `getValue()` 가 그 «맨 문자열»을 낸다(613–615) | 1 | 🔊 **동작으로만** — 어긋나면 Enter 가 두 번 든다. 하니스 `value_suggest_keys_harness.mjs`(1,903줄)가 **키 누른 횟수**로 못 박는다 | ✅ |
| V-8 | 확정된 문자열 | `PUT /tables/{t}/data/updates` | `grid.js:1238` `onCellValueChanged` → `api.js:374` | HTTP PUT | 🔴 **여기서 「후보에서 골랐다」가 «증발한다»** — §⑥-C | 1 | 🔊 저장 실패는 `alert()` | 🔴 (출처 정보만) |
| V-9 | `value_suggest.py:192` `SYSTEM_PREFIX_INDEX_TARGETS = ()` | `value_suggest.py:1162` `for table, column in …:` | — | — | 없음 (반복 «0회») | 독자 1, 외연 **0** | — | ⚰️ **소스가 자기 묘비를 적어 두었다**(186–191) |
| V-10 | `value_suggest.py:1105` `index_targets` | `server/scripts/setup_db_performance.py:410` | 사람이 `python scripts/setup_db_performance.py` 를 돌린다 | 함수 인자 | `index_targets(table_config, settings, row_counts)`, settings 는 `resolve_settings(load_config())`(setup:389) | 비시험 호출자 1 | 🔊 stdout `Step 3.9: Verifying suggestion index PLAN SHAPE (F7)...` | ✅ **다른 흐름** — §⑥-D |

## ⑥-B 응답 아홉 중 «여섯»이 안 읽힌다 — 그리고 그 여섯이 F7 수리의 산출물이다

```
읽힘(3)    values · truncated · unavailable_reason
안 읽힘(6)  table · column · prefix · limit · elapsed_ms · slow_reason
```
🔴 **`slow_reason` / `elapsed_ms` 는 `client2/src` + `client2/tests` 전량에서 «0 히트»다**
(제가 직접 재확인했다 — `grep -arn "slow_reason\|slowReason"` 빈 결과).
그런데 `vs.py:141–169` 와 `suggest_config.md:59·91–92` 는 **소비자 계약을 길게 서술한다** —
「소비자는 값을 그대로 써야」 · 「백오프·경고 표시 판단에는 `elapsed_ms` 를」.
`slow_warn_ms` 라는 설정 손잡이가 **독자가 0인 필드를 채우려고** 존재한다.

⚠️ 다만 «완전히» 조용하진 않다: `logger.warning("[Suggest] …")` 가 컬럼당 한 번(`_slow_warned` 래치,
vs.py:851) 서버 로그에 남는다. 청중이 **바깥 로그**이지 화면이 아니다.

## ⑥-C 🔴 「후보에서 골랐다」가 «전선을 못 건넌다» — 그리고 공수 계기가 그것을 «거절한다»

이 흐름의 존재 이유는 `vs.js:9–17` 이 적어 둔 부등식 하나다 — **후보를 고르면 N타 대신 P+1타로 끝난다.**
그 부등식이 참인지 «로그에서 반증할 방법이 없다.**

```
① getValue() 가 내는 것        this.eInput.value — «맨 문자열»(613-615). 친 것과 고른 것이 «같은 모양»
② acceptHighlight() 의 true    onKeyDown 안에서 «죽는다»(997)
③ handleCellEdit 이 받는 것     {data, colDef, newValue, oldValue} — 편집기 핸들이 «없다»(api.js:375)
④ 업서트 페이로드 6키           row_id·updates·source_name·updated_by·silent·effort — 출처 칸 «0»
⑤ interaction_effort_logs 8칸   id·key_count·mouse_count·nav_count·nav_preserved_count
                               ·session_id·timestamp·transaction_id — 출처 칸 «0»
⑥ value_suggest.js 가 effort_meter 에서 import 하는 것   «없음»
```
🔴 **그리고 ⑦ 이 결정적이다 — 지금 이 칸을 «더하면» 계기가 통째로 죽는다.**
`main.py:2867–2871` 이 모르는 키를 만나면 **effort blob 전체를 버린다**:
> `effort has unknown field(s): … - the whole effort blob was discarded (the correction was still applied). Allowed: session_id, key, mouse, nav, nav_preserved.`

즉 클라가 스키마 변경 «없이» 출처를 실으면, 그 요청의 공수는 **0이 아니라 «미계측»이 된다.**
그 규율 자체는 옳다(소스가 그 이유를 길게 적는다 — 모르는 키를 삼키면 기준선이 조용히 썩는다).
문제는 **그래서 이 흐름의 효과가 «구조적으로 측정 불가»**라는 것이다.

### 간접 채널은 있다 — 그런데 «원인»을 못 가른다
`effort_meter.js:590–604` 가 `document` 의 모든 `keydown` 을 캡처 단계에서 센다. 그래서 제안의
«효과»는 `key_count` 가 낮아지는 것으로 «나타난다». 하지만 계기는
「짧은 값을 다 쳤다」와 「긴 값을 골랐다」를 **구별할 수 없다.**

📌 **총괄 판정 요청:** 이 흐름의 효과를 재려면 «허용 키 목록»을 넓혀야 합니다 — 그건
   `interaction_effort_logs` 스키마와 `_validate_effort` 의 계약을 함께 움직이는 일이고,
   **경계 계약이라 제가 못 정합니다.** 「지금은 안 잰다」도 정당한 답입니다 —
   다만 그때는 `vs.js:9–17` 의 부등식이 «주장으로 남는다»는 것을 알고 남기는 것이 다릅니다.

## ⑥-D 🔴 이건 한 흐름이 아니라 «셋»이다 (§2 판별식: 흐름은 «물음»이지 기능이 아니다)

| 물음 | 구현 | 상한 | 디바운스 | 빈 접두 | 끊기면 |
|---|---|---|---|---|---|
| **「이 셀에 다음에 뭘 칠까」** | `value_suggest.js` `SuggestCellEditor` (AG-Grid 편집기) | 12 (vs.js:136) | 90ms (93) | **거절**(`MIN_PREFIX_LEN=1`, 85·666) | 🔇 조용 (설계) |
| **「이 컬럼에 어떤 값들이 있나」** | `map_editor.js:10194` `populateColumnValueDatalist` (네이티브 `<datalist>`) | 50 (`COLUMN_VALUE_LIST_LIMIT`, 10003) | 120ms (`KEY_SUGGEST_DEBOUNCE_MS`, 10000) | **허용**(10199) | 🔊 **시끄럽다** — 「값 제안을 사용할 수 없습니다 · {사유}」 · 「값 목록을 읽지 못했습니다 (HTTP {n}) — 값은 직접 입력할 수 있습니다」 · 「값이 많아 앞의 N개만 내려왔습니다」 |
| **「어느 컬럼에 접두 인덱스를 만들어야 하나」** | `value_suggest.index_targets` → `setup_db_performance.py:410` | — | — | — | 🔊 stdout |

🔴 **같은 라우트, 같은 모듈 이름, «다른 물음 셋».** 그리고 그 셋이 **끊길 때 다르게 운다** —
같은 서버 고장이 그리드에선 침묵하고 맵 에디터에선 문장 셋을 띄운다.
📎 셋째는 HTTP 도 사용자도 없고, `text_seek_query`·`classify_seek_plan`·`PLAN_OK`·`INDEX_PREFIX` 의
**유일한** 소비자다 — 다른 둘과 공유하는 심볼이 «0» 이다.

## ⑥-E 죽은 갈래·미배선

| 자리 | 판정 | 근거 |
|---|---|---|
| `value_suggest.py:1162` 루프 | ⚰️ | `SYSTEM_PREFIX_INDEX_TARGETS = ()`(192). 반복 0회. grep 히트 2로 «살아 보인다» |
| `min_prefix_length` 400 갈래(vs.py:744–746) | ⚰️ **오늘** | 기본값 `0`(128)이고 `server/config/suggest_config.json` 이 **없다** → `load_config()` 가 `{}`(229–230) → `len(prefix) < 0` 은 영원히 거짓. ⚠️ 설정으로 «되살아날 수» 있다 — 죽은 코드가 아니라 «꺼진» 갈래 |
| `_numeric_values`(vs.py:794) | ⚰️ **이 흐름에서는** | `declared == "number"` 일 때만 뽑히는데 `grid.js:702` 가 number 를 `agNumberCellEditor` 로 보내고 `grid.js:704` 가 제안 편집기를 `string` 으로 관문한다. **⑥-D 의 둘째 흐름에서는 관문이 없다**(map_editor.js:1348–1350) |
| `permanent` 필드(vs.js:403·421·423·429·444·454) | ⚠️ | 쓰는 자리 **6**, 읽는 자리 **0**. `runQuery`(736–751)가 `.seq·.ok·.values·.truncated` 만 구조분해한다 |
| `prefix_conditions` · `db_fold` | ⚠️ | `value_suggest.py` **밖** 호출자 «0» (서버 8히트 전부 자기 참조) |

## ⑥-F 문서 정정

| 자리 | 적힌 것 | 실측 |
|---|---|---|
| `architecture/backend.md:416`(·216) | 응답 = `{table, column, prefix, values[], truncated, limit, unavailable_reason}` — **7키** | 🔴 **9키.** `elapsed_ms`·`slow_reason` 이 계약 서술에서 «빠져 있다» — 같은 파일 §2.1 표와 `suggest_config.md` 는 그 둘을 길게 설명하는데 |
| `architecture/backend.md:445–446` | 「`/graph/nodes/search` 가 이 술어를 그대로 재사용한다」 · 「소비자 2에는 파이썬 재검사가 없어서」 | 🔴 **그 라우트가 없다**(main.py grep 0). `prefix_upper_bound` 의 근거가 «존재하지 않는 두 번째 소비자»에 서 있다. 이건 역사 블록이 아니라 «살아 있는» §2.1 규율 표다 |
| `CODE_MAP.md:4542`(§8-ter) | 「`/graph/nodes/search` 가 같은 술어를 쓰며 그 교체로 `_escape_like_term` 이 삭제됐다」 | 🔴 **같은 문서의 §5-A:2145 가 정반대를 «맞게» 적는다** — 「모듈 밖 호출자는 0이다」. 한 문서, 두 답 |
| `CODE_MAP.md:3744`(§7) | 하니스가 `prebuild` 게이트에 걸려 있다 | 🔴 `client2/package.json:12` `prebuild` = `check:clipboard && check:contracts && check:harnesses`. **`check:suggest-keys`(:10)는 정의돼 있으나 사슬에 «없다».** CODE_MAP:3560 은 이 정정을 이미 적었고 §7 만 안 고쳐졌다 |
| `CODE_MAP.md:3717–3720` | grid.js 앵커 `~15 · ~323 · ~389 · ~402` | 🔴 실측 **19 · 713 · 998 · 1011**. **±20 허용치를 «한참» 벗어난다**(+390·+609·+609). grid.js 가 871→**1,304**줄로 자란 결과 |
| `CODE_MAP.md:3580·3744` | 하니스 **1,901**줄 | **1,903** |
| `guide/config/suggest_config.md:36` | 샘플 JSON 에 `"slow_warn_ms": 200` | 🔴 **`server/config/sample/suggest_config.json.sample` 이 그 키를 «선언하지 않는다».** 샘플 8키 / 코드가 읽는 것 9키. 문서가 제일 길게 설명한 그 키가 샘플에 없다 — 「라이브에만 선언하면 출하본은 가드가 꺼진 채로 돈다」의 그 부류 |
| `guide/config/suggest_config.md:2·26` | 「`suggest_config.json.sample` 을 `suggest_config.json` 으로 복사합니다」 | ⚠️ 샘플은 `server/config/**sample/**` 밑에 있다. 적힌 경로가 «존재하지 않는다» |
| `guide/config/suggest_config.md:11` vs `:126·129` | `index_targets` 소비를 「Step 3.8」/「Step 3.9」로 «둘 다» 부른다 | ⚠️ 실측 호출은 `setup_db_performance.py:410`, 검증은 Step 3.9. 한 파일 안에서 두 이름 |

### ✅ 맞았던 것도 적는다
`CODE_MAP.md` §7 `value_suggest.js` 심볼 표의 앵커 **28개 전건 정확**(85·93·136·343·356·358·375·386·
484·495·502·503·602·606·613·617·633·658·669·722·733·754·769·821·847·856·895). `server/value_suggest.py`
**1,166**줄 · `client2/src/value_suggest.js` **1,003**줄 — 둘 다 지도와 일치. 이 패스에서 «제일 정확한
문서 블록»이다.

---

# ④ 변경 이력 · 타임라인 (쓰기 → 이력 → 화면)

> ⚠️ **앵커 주의:** 이 절의 `main.py` 줄 번호는 **HEAD `907c8995` 에서 다시 확정했다.**
> `ee1e5d74` 가 466행 근처에서 26줄을 걷어내 그 뒤가 전부 **−4** 밀렸다.

## ④-A 이음매 표

| # | 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 (실측) | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|---|
| H-1 | `crud.apply_row_update_internal` (`source_name=="user"`) | `audit_logs` 행 | 사람의 셀 확정 → `_apply_batch_updates_once` → `apply_row_update_internal`(crud.py:3891) | DB INSERT | crud.py:2928–2935 — 컬럼 **10칸 전건**: `table_name·row_id·column_name·old_value·new_value·source_name('user')·updated_by·transaction_id·timestamp·business_key` (`id` 는 DB) | `bulk_insert_audit_logs` 호출부 **5**(crud.py:3978·4143·4202·4360·4724) | 🔊 쓰기 자체 실패는 400/500 | ✅ |
| H-2 | 기계 쓰기 여섯 (`directory_watcher:2690` · `chain_ingestion_worker:906` · `enrichment_backfill:435` · `enrichment_candidates:759` · `map_meta_registrar:371` · `frame_confirmation:351`) | `audit_logs` 행 **행당 1건** | 같은 함수, `source_name != "user"` 갈래 | DB INSERT | 🔴 crud.py:2956–2965 — `column_name` 자리에 **리터럴 `"ROW_UPDATE"`**, `new_value` 는 `", ".join(f"{col}: {val}")` **렌더된 문장**(NULL 은 한국어 「비어있음」) | 같은 5 | 🔇 **컬럼별 기록이 영원히 없다** — 셀 이력 라우트의 `column_name == col` 필터에 안 걸린다 | ⚠️ |
| H-3 | 🔴 **일반 쓰기 중 collision_merge** | (없음) | 중복 업무키 병합 | — | 🔴 crud.py:3094 가 `create_audit_log(...)` 를 부르는데 **반환을 안 받고 `logs_to_cache.append` 도 안 한다**. 그리고 `add_to_cache=(logs_to_cache is None)` 인데 **유일한 운영 호출자**(crud.py:3891)가 `logs_to_cache=[]`(3865)를 넘긴다 → 언제나 False → `db.add` 도 생략 | **0** | 🔇 **값은 바뀌는데 이력이 «어디에도» 없다.** `cell_overwrites` 마커(crud.py:3081–3090)만 남아 **그리드는 병합 배지를 그리는데 타임라인은 빈칸** | 🔴 |
| H-4 | 🔴 **`replace_map` 삭제 구간** (맵 Push · legend 저장) | (없음) | `PUT /tables/{t}/data/updates?replace_map=true` | — | crud.py:3697–3713(purge) · 4009–4021(diff) 둘 다 `.delete()` + `CellSource`/`CellOverwrite` 삭제. **`create_audit_log` 호출 0**. 남는 것은 로그 한 줄 `"[Map Diff] … Removed: {n}"`(4024) | **0** | 🔇 응답 `scope.deleted` 와 서버 로그에만. 🔴 **`crud.delete_rows_batch` 는 «같은 행위»에 `"DELETE"` 감사를 남긴다**(4193) — 한 결과에 계약이 둘 | 🔴 |
| H-5 | `crud.compute_priority_value` | `audit_logs.source_name` | 쓰기 때 레이어 승자 판정 | — | 🔴 `new_val, top_src = compute_priority_value(...)`. **`top_src` 는 crud.py 전체에서 대입 «3»(2833·4323·4473) / 참조 «0»** — 제가 직접 재확인했다 | **0** | 🔇 감사 행의 `source_name` 은 「누가 썼나」이지 「어느 레이어가 이겼나」가 아니다 | ⚰️ |
| H-6 | `audit_logs` | `audit_cache.AuditCache` | `main.get_recent_audit_logs` 가 `load_initial` + `refresh_if_stale` 호출(main.py:1115–1117) | 파이썬 객체 | `_discover_groups` — `(timestamp, id)` keyset 걸음. 상한 `recent_max_scan_rows=500,000` · 청크 `20,000` · 그룹당 `500` · 델타 임계 `2,000` | 2 | 🔊 **서버 stdout 에만**: `[AuditCache] recent scan gave up after {n:,} rows with {g}/{limit} transaction groups …` (audit_cache.py:403). `refresh_if_stale`/`add_logs_batch` 의 꼬리 절단은 **로그 없이** `truncated=True` | ✅ |
| H-7 | `audit_cache` | **`GET /audit_logs/recent`** (main.py:1084) | 클라 fetch | HTTP JSON + 헤더 | 바디 키 **5**: `groups·truncated·next_cursor·limit_groups·returned`. 헤더 **2**: `X-Audit-Truncated`(1120) · `X-Audit-Next-Cursor`(1122) | 🔴 헤더 소비자 **0** (`grep -rn "X-Audit" client2/` 0건). 게다가 **`expose_headers`(main.py:174)에 둘 다 «없어»** 교차 출처(:5173)에선 브라우저가 지운다 | — | ⚠️ |
| H-8 | `GET /audit_logs/recent` | `timeline.js` 전역 탭 | `loadHistory()` — 실호출자 **8**(api.js:147 · grid.js:1135 · main.js:402·551·565·575 · timeline.js:657·910) | HTTP JSON | 🔴 timeline.js:21 `fetch(...)` — **`res.ok` 검사 없음**. timeline.js:29 `const { logs: groups } = readHistoryPage(await res.json(), 'groups')` — **`truncated`·`next_cursor` 를 구조분해에서 버린다**(제가 직접 확인) | 1 | 🔴 **조용이 «두 겹»** — §④-C | 🔴 |
| H-9 | `audit_logs` | `GET /tables/{t}/rows/{r}/history` · `…/cells/{c}/history` | 클라 fetch | HTTP JSON | 공유 헬퍼 `_history_page`(main.py:2660) → `AuditHistoryPage` **7키**: `logs·truncated·next_cursor·limit·returned·row_history_total·row_history_truncated`(2711). `limit+1` 조회로 `truncated` 판정 · 커서는 base64url `"{iso}|{id}"` · `default_limit=200`/`max_limit=1000`, 초과는 **거절 아니라 clamp** | 2 (timeline.js:60·710) | 🔊 커서 불가 → `CursorError` → **400** → 클라가 잡아 버튼 문자열 **「위치 만료 · 새로고침」**(timeline.js:683). 기타 실패 → **「조회 실패 · 재시도」**(674) | ✅ |
| H-10 | `AuditHistoryPage` | 셀/행 탭 DOM | `readHistoryPage`(141) → `renderTimeline`(543) → `renderHistoryMore`(627) | JS 객체 | 읽는 키 **5**(145·147·149·152·155) · **안 읽는 키 2**(`limit`·`returned`). `truncated` 는 `!!truncated && !!nextCursor` 로 접힌다 | 3 | 🔊 **절단이 DOM 문자열이 된다**: 「일부만 (N건) · 더 보기」(641). 빈칸 두 상태도 갈린다 — 「기록 없음」(589) vs 「이 셀 기록 없음」(597) + 「행 이력 N건 (이상) 보기」(608) | ✅ |
| H-11 | `GET /audit_logs/transaction/{tx_id}`(main.py:1171) | 전역 탭 그룹 펼침 | `toggleExpand`(timeline.js:418), `group.logs.length <= 1 && group.total_count > 1` 일 때만 | HTTP JSON | 서버 키 **4**: `transaction_id·total_count·summary_columns·logs`(기본 `limit=20000`). 클라가 읽는 것은 `txDetail.logs` **하나**(427) | 1 | ⚠️ **우연히 시끄럽다** — `res.ok` 검사 없음. 404/500 이면 `logs===undefined` → `logs.slice` 가 TypeError → 같은 catch → 「Failed to load details.」(436). 상태코드 «판정»이 아니라 «예외 덕»이다 | ⚠️ |
| H-12 | 커밋 후 브로드캐스트 | `websocket.js:342` `appendHistoryLocally` | 쓰기 커밋 직후 | WS JSON | `msg["created_logs"]` — 상한 **5000**(main.py:463) 또는 `MAX_NOTIFY_CREATED_LOGS`=500. 로그 dict 11키, **`id` 는 리터럴 `0`**(crud.py:1440) | 2 | 🔇 **5000 초과 배치는 `created_logs` 키가 «아예 안 실린다».** 클라는 「로그가 없었다」와 「너무 많아 안 보냈다」를 **구별 못 한다** — HTTP 응답엔 `total_log_count` 짝이 있는데 **WS 에는 없다** | ⚠️ |

## ④-B 「모든 쓰기가 이력을 남기나」 — **아니다. 둘은 «전혀» 안 남기고, 넷은 «컬럼별로» 안 남긴다**

| 쓰기 경로 | 감사 행 | `column_name` | `source_name` |
|---|---|---|---|
| 수동 셀 편집 | ✅ 셀당 1 | 실제 컬럼명 | `user` |
| 업무키 컬럼 수동 변경 | ✅ | key 컬럼명 | `user` |
| 맵 Push (**upsert 부분**) | ✅ 셀당 1 | 실제 컬럼명 | `user` |
| 일괄 행 삭제 | ✅ 행당 1 | `"DELETE"` | `system` |
| 빈 행 생성 | ✅ 행당 1 | `"CREATE"` | `system` |
| 셀 소스 삭제 | ✅ 바뀐 셀만 | 실제 컬럼명 | `delete_source:{s}` |
| 우선순위 Pin | ✅ 바뀐 셀만 | 실제 컬럼명 | `set_priority:{s}` |
| **Pin 중** collision_merge | ✅ | 실제 컬럼명 | `collision_merge` |
| 체인 리플레이 R2·R3 | ✅ | 실제 컬럼명 | `chain_replay_withdraw` · `resolution_recompute` |
| 파일 인제션 | ⚠️ 행당 1 | **`ROW_UPDATE`** | 파일 basename |
| 체인 인제션 | ⚠️ 행당 1 | **`ROW_UPDATE`** | `chain_ingestion` |
| enrichment 백필 | ⚠️ 행당 1 | **`ROW_UPDATE`** | `enrichment_backfill` |
| enrichment 자동확정 | ⚠️ 행당 1 | **`ROW_UPDATE`** | `enrichment_auto_confirm` |
| 🔴 **일반 쓰기 중 collision_merge** | **없음** | — | — |
| 🔴 **`replace_map` 삭제 구간** | **없음** | — | — |

🔴 **H-3 은 「열 중 하나」다.** `create_audit_log` 호출 사이트 **10**(crud.py:2928·2956·3094·3245·4133·4193·4347·4497·4603·4711) 중 **아홉이 `log_dict = …` 로 받아 `logs_to_cache.append(log_dict)` 를 하고, 3094 «하나»만 안 한다.** 그리고 **Pin 경로의 collision_merge(4603)는 append 를 한다** — 같은 사건이 «어느 라우트로 왔느냐»에 따라 이력이 남기도 하고 안 남기도 한다.

### 컬럼 집합은 갈리지 않는다 — 이건 «맞았던 것»이다
persist 기제는 **둘**뿐(`db.add(models.AuditLog(...))` crud.py:1424 · `bulk_insert_mappings` 1475)이고 **컬럼 집합이 동일**하다(10칸 명시 + DB 할당 `id`). 「한 이음매에 모양이 둘」 결함은 **여기 없다.**

## ④-C 🔴 절단 — 「행·셀은 보이고, «전체»는 안 보인다」

```
행/셀 이력   truncated -> readHistoryPage(152) -> state.cellRowHistoryTruncated(65)
                       -> renderHistoryMore(628) -> DOM 「일부만 (N건) · 더 보기」(641)   ✅ 끝까지 간다
             그리고 페이저도 «실제로» 돈다 — loadMoreHistory(687)가 ?cursor= 로 «이어붙인다»

전역 이력    truncated -> main.py:1116 바디 + 1120 헤더 -> timeline.js:29 에서 «버려진다»   🔴 여기서 끊긴다
             화면에 도달하는 유일한 수: timeline.js:822 `${globalHistoryData.length}건 중 ${shown.length}`
             => 500,000행 상한에 걸려 12그룹만 온 화면과, «진짜로 12그룹뿐인» 화면이 «같다»
```
🔴 **그리고 그물이 그 폐기를 «단언»한다** — `client2/tests/history_paging_harness.mjs:746–750` (H2c)가
`[truncated, next_cursor, groups, returned]` 가 전부 `undefined` 임을 못 박는다. **게이트가 초록인 채로
결함이 고정돼 있다.** 이것이 「내 게이트는 내가 떠올린 것만 잰다」의 실물이다.

### 두 번째 침묵 — 500 이 「기록 없음」으로 읽힌다
`timeline.js` 의 `fetch` 는 **다섯**(21·58·424·703·1093)인데 `res.ok` 검사는 **둘**(59·709)뿐이다(직접 계수).
`/audit_logs/recent` 가 500 을 내면 `{"detail": …}` 가 `readHistoryPage(body,'groups')` 에 들어가
`logs=[]` → **`No database history recorded.`**(805). **이력이 가득한 DB 가 「기록 없음」으로 보인다.**

## ④-D 레이어링 — 「어느 소스가 왜 이겼나」를 타임라인이 «말하지 않는다»

```
승자는 실제로 «계산된다»   crud.py:2833  new_val, top_src = compute_priority_value(...)
                        규칙: ① 선언 서열 ② 날짜 있는 레이어 우선 ③ 최신순 ④ 이름 사전순
그런데 top_src 는          대입 3 · 참조 0. 감사에도 응답에도 로그에도 «안 들어간다»
감사 행이 나르는 것        source_name = 「누가 이 쓰기를 발행했나」
이유를 담는 예외 셋         set_priority:{s} · delete_source:{s} · withdraw/resolved (리플레이)
                        => «사람이 직접 개입한 순간»만 이유가 남고, 파이프라인 승부는 안 남는다
클라                     grep -c priority_source client2/src/timeline.js = «0»
```
🔴 **타임라인과 그리드가 같은 셀에 대해 «다른 질문»에 답하고 서로를 참조하지 않는다.** 그리드는
「지금 누가 이겼나」(`priority_source`, §③-C)를 그리고, 타임라인은 「누가 썼나」를 그린다.
**「왜 이겼나」에 답하는 자리가 «양쪽 다» 없다.**

## ④-E 🔴 이건 한 흐름이 아니라 «넷»이다 — 그리고 **절단 계약이 셋**이다

| 물음 | 라우트 | 화면 | 절단 공시 |
|---|---|---|---|
| **「이 셀은 뭐가 바뀌었나」** | `…/cells/{c}/history` | Cell 탭 | ✅ 봉투 + 페이저. ⚠️ 다만 기계 쓰기는 `ROW_UPDATE` 라 **구조적으로 못 답한다** — `row_history_total` 로 「못 보여준다」까지만 말한다 |
| **「이 행은 뭐가 바뀌었나」** | `…/rows/{r}/history` | Row 탭 | ✅ 봉투 + 페이저 |
| **「이 트랜잭션은 뭘 했나」** | `/audit_logs/transaction/{tx}` | 그룹 펼침 | 🔴 **봉투가 «아니다».** `limit=20000` 상한이 있는데 절단 신호가 없다. `total_count` 는 오는데 클라가 안 읽는다 |
| **「최근 시스템 전체에 뭐가」** | `/audit_logs/recent` | 전역 탭 | 🔴 봉투인데 **클라가 봉투를 버린다.** 필터도 「이미 받은 것」 위에서만 돈다(timeline.js:745) |

🔴 **한 화면 안에 절단 계약이 셋이다** — 봉투+페이저 / 봉투 없음 / 봉투를 버림.

## ④-F 안 읽히는 것 — 바디 키 **6** + 헤더 **2**

| 키 | 세우는 자리 | 실독 |
|---|---|---|
| `limit`(AuditHistoryPage) | main.py:2711 | **0** |
| `returned`(양쪽 봉투) | main.py:2711 · 1169 | **0** |
| `limit_groups` | main.py:1168 | **0** (1히트는 요청 URL 문자열) |
| `summary_columns` | main.py:1154·1205·1248 | **0 read / 5 write** — timeline.js:930·931·933·934·941 은 전부 클라가 «자기» 그룹 객체에 쓰는 코드 |
| `/transaction` 의 `transaction_id` | main.py:1203 | **0** |
| `/transaction` 의 `total_count` | main.py:1204 | **0** (418·436 은 `/recent` 그룹의 것) |
| `X-Audit-Truncated` | main.py:1120 | **0** + `expose_headers`(174) 미등재 |
| `X-Audit-Next-Cursor` | main.py:1122 | **0** + 미등재 |

## ④-G 문서 정정

| 자리 | 적힌 것 | 실측 |
|---|---|---|
| `CODE_MAP.md:3763` | 「**전역 이력 탭은 이번에 손대지 않았다** — 여전히 `/audit_logs/recent` 의 **맨 배열**을 순회한다(그 라우트가 **헤더로만** truncation 을 흘리는 이유)」 | 🔴 **거짓.** timeline.js:29 가 `readHistoryPage(…, 'groups')` 로 봉투를 «연다». main.py:1084 `response_model=schemas.AuditLogGroupPage`. 🔴 **같은 문서 `CODE_MAP.md:800` 이 정반대(정확한) 서술을 한다** — 한 문서, 두 답 |
| `CODE_MAP.md:3779` | `readHistoryPage(body)` — 인자 1 | 실제 `readHistoryPage(body, listKey='logs')`(timeline.js:141). 같은 절 머리(3761)는 옳게 적는다 — **한 절 안에 두 철자** |
| `CODE_MAP.md:3759` · `:122` | `timeline.js` **1,185**줄 / 드리프트 표는 **1,008** | 실측 **1,182**. 표와 §7 헤더가 서로도 안 맞는다 |
| `CODE_MAP.md:3502` | `models.py` **1,079**줄 | 실측 **1,222** (+143) |
| `data_model.md:20` | `AuditLog` 컬럼 **9개** 열거 | 🔴 실제 **11개** — `id` 와 **`business_key`** 가 빠졌다. `business_key` 는 모든 쓰기가 채우고 main.py:2697 이 삭제된 행 폴백까지 하는 **살아 있는** 컬럼 |
| `data_model.md:20` | AuditLog = 「**셀 단위** 변경 이력」 | ⚠️ 절반만 참. 같은 저장소 `schemas.py:61–68` 이 「239,786행 중 225,586(94.08%)이 `ROW_UPDATE`」를 들고 있는데 data_model 이 안 옮겼다 |
| `guide/config/audit_history_config.md:60` | 「헤더 둘이 CORS `expose_headers` 에 아직 없다(`main.py:164`)」 | ✅ **사실은 오늘도 참**. ⚠️ 앵커만 낡음 — 실제 174 |
| `guide/config/audit_history_config.md:61` | 「공용 리더가 `truncated:true / next_cursor:null` 을 false 로 접는다 — **오늘은 전역 탭이 페이저를 안 그리기 때문에만 정확하다**」 | ⚠️ **결론이 약하다.** 접기는 정확한데 그 «위» 호출자(timeline.js:29)가 `truncated` 를 **아예 버린다**. 「페이저가 없어서 무해」가 아니라 **절단 사실이 화면에 없다**가 오늘의 상태 |
| `guide/config/audit_history_config.md:90` | 「`.sample` 이 `recent_*` 네 키를 안 적고 있다」 | ✅ **여전히 참** — 샘플은 `default_limit`/`max_limit` 둘뿐 |
| `architecture/backend.md:239` | 「클라가 `row_history_total`/`row_history_truncated` 를 읽고 두 상태로 그린다」 | ✅ **참** (timeline.js:149·155·586–610) |

### 🔴 문서에 «아예 없는» 사실 셋 (docs 전체 grep 0건)
```
① 일반 쓰기의 collision_merge 감사 행이 운영에서 «절대 저장되지 않는다»
② replace_map 삭제가 감사 행을 «안 남긴다» — 같은 「행 사라짐」을 delete_rows_batch 는 남기는데
③ top_src(레이어 승자)가 계산 후 «버려진다»
```

## ④-H 못 밝힌 것
- `audit_cache.py:317` `cursor is None` 갈래 — 소스가 스스로 「도달 불가로 기대된다」고 «선언»하고 시험을 일부러 안 붙였다고 적는다. **선언은 검증이 아니다** — 실행으로 확인하지 못했다.

---

# ⑤ 가상 조인 컬럼 (선언 → 조회 시점 결합 → 소스 표시)

## ⑤-A 이음매 표

| # | 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 (실측) | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|---|
| J-1 | `server/config/virtual_join_rules.json` | `virtual_join_config.load_virtual_join_rules`(:431) | `load_verified_rules`(:623) · `config_resolve_report._resolve_virtual_join`(:463) | 파일 read + `json.load` | 검증기가 «읽는» 키 **7**: `enabled·left_table·right_table·join_cardinality·join_key[].{left,right}·expose·unresolved_label`. 🔴 **미지 키 거절이 «없다»** — `_validate_join` 이 입력 dict 를 한 번도 열거하지 않는다 | 2 | 🔊 로그+거절기록 `"…could not be read (…) — NO virtual join is in effect"`. 🔇 그러나 결과는 `[]` = 조인 없음 · **HTTP 200** | ⚠️ 오타 난 선택 키 = 조용한 기본값 |
| J-2 | `load_verified_rules` | PostgreSQL `pg_index` 카탈로그 | `_verified_by_left_table` 캐시 미스(executor:130) · `dt_map_derivation.join_rule`(:246) · `verification_report`(:660) | DB SELECT | `x.indisunique AND x.indisvalid AND x.indpred IS NULL AND x.indexprs IS NULL`(config:553–564) + 부분집합 검사 `set(cols) <= target` | 3 | 🔊 `logger.warning("[VirtualJoin:%s] rejected: no unique index covers %s(%s)")` + **`required_index_ddl` 를 사실로 실어 준다**. 🔴 **비-PostgreSQL 이면 `return None` → 모든 선언 거절**(config:546) | ✅ |
| J-3 | `load_verified_rules` | `_RULES_CACHE`(executor:90) | `rules_for(db, left_table)`(:143) | 모듈 dict | `VerifiedJoinDescriptor`(frozen Mapping) + 주입 `verified=True`, `verification_basis="physical_unique_index"`. **TTL 5.0초**(:88) | 내부 호출자 **5**(185·233·327·407·579) · 외부 0 | 🔇 `except Exception` → `by_left={}` + `logger.error("[VirtualJoin] verified rules unavailable, NO join is in effect: %s")`. **요청은 200, 컬럼만 사라진다** | ✅ |
| J-4 | `main.fetch_and_merge_metadata`(main.py:817) | `virtual_join_executor.attach`(:570) | 🔴 **`fetch_and_merge_metadata` 호출부 «여섯» 전부** — 즉 §③-C 의 그 여섯 | 함수 인자 | `attach(db, table_name, data_list)` — main.py:**959**. 반환 `touched:int` 는 **버려진다** | 운영 호출자 **1** | 🔇 바깥 try/except(main.py:957–961)가 `"[VirtualJoin] attach failed on '{t}', columns omitted: {e}"` 로그. **HTTP 200, 그리드는 머리만 그리고 칸은 빈다** | ✅ |
| J-5 | `attach` | 왼쪽+오른쪽 표 | 규칙마다 `execute_rule(db, rule, row_ids)`(:629) | DB SELECT, 청킹 | `SELECT l.row_id, r.row_id, r.<expose…> FROM left l LEFT OUTER JOIN right r ON <onclause> WHERE l.row_id IN (:chunk)`. **`CHUNK_SIZE = 1000`**(:79). 🔴 **한 번에 «한 페이지»만**(row_ids 가 이미 조회된 페이지, :586) — 기본 `limit=500`. **전량 로드 없음** | 1 | 🔊 규칙마다 `logger.error("[VirtualJoin] rule '%s' could not be built on '%s'; its columns %s are omitted and **every OTHER rule's columns are unaffected**: %s")` 후 `continue` | ✅ 확장성 규율 준수 |
| J-6 | `attach._resolve_one` | 행 페이로드의 셀 dict | `attach` 판정 루프(:661–712) | 메모리 변형 | `virtual_only`: **7키를 쓴다**(:706–711) — `value·is_overwrite:False·is_collision_merge:False·sources:{virtual_join: …}·updated_by:"system"·manual_priority_source:None·priority_source:"virtual_join"`. `collide`: 기존 7키 중 **4개만** 변형(:691–700). 왼쪽 값이 비지 않았으면 **바이트 동일, 아무 표시도 안 남긴다**(:675–679) | 🔴 클라의 `priority_source` 독자 **3**(grid.js:658·676·684) 중 **`'virtual_join'` 을 읽는 것 «0»** | 🔇 **완전히 조용.** 클래스도 아이콘도 툴팁도 없다. `grid.js:834–842` 가 그 사실을 «자백»한다 — 「would be permanently false」 | ⚠️ |
| J-7 | `main.get_table_schema`(main.py:2478) | 클라 `state` | `GET /tables/{t}/schema` | HTTP JSON | `virtual_columns`(2589) 엔트리 키 **6**: `name·type·editable:False·right_table·rule·unresolved_label`. `join_resolved_columns`(2594) 키 **5**: `name·kind∈{collide,virtual_only}·rule·right_table·unresolved_label` | 클라 2 (api.js:180·186) | 🔇 `except` 가 로그만 남기고 키는 `[]` 로 나간다 · **HTTP 200** | ✅ |
| J-8 | `main.narrowed_table_query` | `virtual_join_executor.resolved_expression`(:360) | `VirtualColumnBinder.expr()` ← `apply_column_filters` · `apply_search_filter` | SQLAlchemy 질의 변형 | main.py:**1532**. 규칙마다 `query.outerjoin(aliased(right), onclause)` 를 더하고 `func.coalesce(*parts, label)` 반환. 모든 조각이 `crud.column_text_sql` 을 통과 | 각 1 | 🔊 **필터는 400** — 「'{t}'의 가상 조인 컬럼 '{col}'에 대한 필터를 만들 수 없습니다(조인 대상 테이블이 로드되지 않았습니다). **필터 없이 전체를 돌려주지 않습니다.**」 · 🔇 바인더 «생성» 실패는 로그만 | ✅ |
| J-9 | `main.export_table_csv`(2217) | CSV 스트림 | `GET /tables/{t}/export` | 스트리밍 CSV | 헤더 = `business_cols + virtual_only_cols + [created_at, updated_at]`. `collide` 이름은 SELECT 엔티티가 **binder.expr 로 교체**된다. 헤더/엔티티 개수 검사 있음 | 1 | 🔊 **500 으로 «거절»**: 「… 컬럼이 밀린 CSV 를 내보내지 않습니다」 · 「… 추출 헤더(N)와 컬럼(M) 수가 다릅니다」 | ✅ |
| J-10 | `crud._apply_batch_updates_once` | `crud.refuse_virtual_join_columns`(crud.py:3337) | **깔때기의 첫 문장**(3612) — `transaction_context`(3619)보다 앞, `replace_map` 소거(3628)보다 앞 | 함수 인자 → `ValueError` | `virtual_only_columns` 로 얻은 집합과의 교집합. 배치 단위라 위반 컬럼을 한 번에 전부 부른다 | `virtual_only_columns` 운영 소비자 **1** | 🔊 **400** + 다음 행동까지 말하는 문안. 🔴 **다만 선언을 «못 읽으면» 아무것도 거부하지 않고 반환한다**(3367–3373) → 미선언 컬럼 게이트가 값을 **드롭하고 200** | ✅ (예외 하나는 아래) |
| J-11 | `POST /admin/reload-configs` | `virtual_join_executor.reset_cache`(:108) | `system_reload.reload_local_process_cache`(system_reload.py:54) | 함수 호출 | `_RULES_CACHE["at"]=0.0; ["by_left"]=None` | 1 | 🔴 **완전히 조용** — `try/except Exception: pass`(system_reload.py:55–56). ImportError 면 리로드가 **로그 한 줄 없는 no-op**. 워커 프로세스엔 훅이 «없다» — TTL 5초를 기다린다 | ⚠️ |
| J-12 | `state.currentVirtualColumns` | AG-Grid 컬럼 정의(grid.js:738–844) | `buildColumnDefs()` | in-process | `virtual_only`: 머리 `${COL}` + 고리 기호 (781) · `editable:false`(783) · `cellClass:'cell-system-readonly'`(833, **시스템 컬럼과 같은 회색**) · 필터 6옵션(`blank`/`notBlank` 제거). 🔴 **`collide` 는 «필터 교체만» 받는다** — 고리도 회색도 «없다» | `isVirtualColumn` 6 · `joinResolvedColumn` 3 | 🔇 서버가 키를 안 보내면 `[]` → 컬럼이 그냥 안 그려진다 | ✅ virtual_only · ⚠️ **`collide` 는 평범한 저장 컬럼과 «구별 불가»** |
| J-13 | 페이로드 `cell.sources={virtual_join:…}` | 셀 소스 모달 | 운영자가 «소스 보기» → `refreshSourcesList`(main.js:1529) | `GET /tables/{t}/{r}/{c}/sources`(main.py:3281) | 🔴 라우트는 **`models.CellSource` 만** 읽는다(3294). 가상 조인은 일부러 `CellSource` 를 «안 쓴다»(executor:53–54) | **0** — 페이로드의 `sources` 를 이 모달로 잇는 것이 아무것도 없다 | 🔴 **시끄러운데 «틀리게» 시끄럽다**: `virtual_only` 이름은 `hasattr(table_model, col_name)` 가 False → **404 「Cell not found」**(main.py:3289–3290, 제가 직접 확인) → 화면에 붉은 **「Failed to load sources.」**. `collide` 는 200 이지만 **`virtual_join` 을 빠뜨린다** | 🔴 |
| J-14 | `dt_map_derivation.join_rule`(:224) | `load_verified_rules` | `dt_map_derivation.py:561–562` · `mappers/dt_map_mapper.py:128` | 함수 호출 | 리터럴 이름으로 찾는다: `"dt_log_confirmed_attribution"` · `"dt_log_frame_attribution"`. 🔴 **선언은 그것을 `_retired_…` 로 «밑줄 접두»해 두었고, 밑줄 이름은 주석으로 «건너뛴다»**(config:418) | 2 | 🔊 `DerivationRefused(REFUSE_JOIN_RULE_MISSING, "virtual join rule '%s' is absent or was not verified; the gate cannot be resolved without it.")` | 🔴 **설정으로 끊겨 있다 — 다만 거절이 «이름을 부른다»** |
| J-15 | 감사·이력 경로 | — | — | — | `grep "virtual_join" server/audit_history.py server/audit_cache.py server/ledger_trace.py` = **0** | 0 | — | ⚰️ **구조적 부재** — 안 쓰이니 안 남는다. 옳지만 **문서에 없다** |

## ⑤-B 선언의 «자유도» — 검증기가 읽는 7키, 정규화가 내는 15키, 그중 죽은 셋

```
정규화 dict 가 내는 키   15 (config:377-403)
그중 «어디에서도» 안 읽히는 것   3
   "left_columns"  (:382)  운영 독자 0 (test_dt_map_derivation 픽스처만)
   "folded"        (:387)  운영 독자 0 (test_notation_normalization:345 만)
   "collide"       (:393)  자기 다음 줄에서 virtual_only 를 유도하는 데만 쓰인다
그리고 실행기 쪽              "matched"(executor:523) 운영 독자 0 — attach 는 hit["values"] 만 읽는다
                            attach 반환 touched:int 도 버려진다
```
⚠️ `"matched"` 의 docstring(:466–474)은 **소비자 둘**을 이름으로 든다. 두 번째(「이 계약 위에 올라올 레인들」)는 **존재하지 않는다** — `server/ledger/` 에 `"matched"` grep 0.

## ⑤-C 셀 모양 — 「같은 7키, 반대 인구」

```
✅ 키 집합은 «동일»하다
   실제 셀   main.py:918-926   value·is_overwrite·is_collision_merge·sources·updated_by·manual_priority_source·priority_source
   가상 셀   executor:706-711  «같은 7개, 같은 삽입 순서» (소스 주석이 바이트 동일 의도를 적는다)

🔴 그런데 «인구»가 반대다
   그리드 페이지는 include_sources=False (main.py:1986)
      -> 실제 셀은 sources: {}          (비어 있다)
      -> 가상 셀은 sources: {virtual_join: <렌더된 값>}   (차 있다)
   그리고 조인이 이긴 collide 셀은 is_overwrite 가 «강제로 False»(:700) — user 레이어가 sources 에 살아 있어도
```
📎 §③-C 와 합치면 이렇게 된다 — **`priority_source` 한 칸에 값을 넣는 규칙이 «셋»이다**:
```
① 싼 길 (그리드·WS)      user | collision_merge | None
② 선언된 길 (단일행·Pin)  compute_priority_value 가 내는 다섯 중 하나
③ 가상 조인 (attach)     "virtual_join"   <- 읽는 CSS 가 «0»
```

## ⑤-D 표면별 존재/부재

| 표면 | `virtual_only` | `collide` |
|---|---|---|
| `GET /tables/{t}/schema` | ✅ 별도 키 `virtual_columns` (`columns` 에 «안» 섞는다) | ✅ 이미 `columns` 에 · `join_resolved_columns` 에도 |
| `GET /tables/{t}/data` | ✅ | ✅ 값이 교체된다 |
| `GET /tables/{t}/data/count` | ✅ **정확히 세어진다** — 같은 바인더·같은 조인. 오른쪽이 UNIQUE 라 행 수가 못 바뀐다 | ✅ |
| `?filters=` · `?q=` | ✅ 못 만들면 **400** | ✅ |
| **`?order_by=` 서버 정렬** | 🔴 **없다** — 라우트가 `updated_at·id` 외엔 `row_id` 로 떨어뜨린다. 🔴 그런데 **colDef 는 `sortable: true`**(grid.js:784) → **«로드된 페이지 안»에서만 정렬된다** | 🔴 같음 |
| CSV export | ✅ 헤더 슬롯 + SELECT 엔티티 | ✅ 저장 엔티티가 **교체**된다 |
| 감사·이력 | ⚰️ 없다 (안 쓰이니 안 남는다) | ✅ 평범한 저장 컬럼으로 |
| **셀 소스 모달** | 🔴 **404 「Cell not found」** → 「Failed to load sources.」 | ⚠️ 200 이지만 `virtual_join` 이 **빠진다** |
| `crud.SOURCE_PRIORITY` | 일부러 없다(executor:55–57) | — |

🔴 **`?order_by` 행이 이 표에서 제일 조용하다.** 머리를 클릭하면 «정렬된 것처럼 보이는데» 정렬된 것은
현재 페이지 500행뿐이다. 오류도 배너도 없다.

## ⑤-E 죽은 갈래

| 자리 | 판정 | 근거 |
|---|---|---|
| `virtual_only is None` 갈래 **셋**(executor:190·234·331) | ⚰️ | 유일 진입 `rules_for` → `_verified_by_left_table` 이 `known_tables=crud.TABLE_CONFIG`(모듈 싱글턴, 절대 None) 를 넘긴다 → `collide` 도 `virtual_only` 도 «언제나 리스트». **세 docstring 이 스스로 그것을 인정한다** |
| `_validate_join` 의 `facts` 반환 슬롯 | ⚰️ | `return` **21개 전부** 4번째 원소로 `None` 을 넘긴다 → `_record(..., facts=facts)`(:424)가 언제나 `facts={}` → `config_resolve_report.virtual_join_detail` 의 구조화 문장 갈래(:436)가 **모양 경로에서 절대 발화 못 한다** |
| `export_table_csv:2342` 500 갈래 | ⚠️ **못 밝힘** | 주석이 스스로 전제가 바뀌었다고 적는다. 두 호출이 «다른 캐시 읽기»라 5초 TTL 경계를 걸치면 도달 가능할 수 있다 — 실행으로 확인 못 했다 |

## ⑤-F 🔴 이건 한 흐름이 아니라 «넷»이다

| 물음 | 경로 | 상태 |
|---|---|---|
| **「이 셀은 지금 뭘 보여주나」** | `attach` → 페이로드 → 그리드 | ✅ |
| **「어느 행이 이 조건에 맞나」** | `resolved_expression` → SQL COALESCE → 필터·`q`·count·CSV | ✅ 이되 **엔진이 다르다**(SQL vs 파이썬). 두 반쪽을 잇는 것은 `crud.column_text_sql` 의 못 박힌 텍스트 계약뿐 |
| **「이 DT 행은 어느 lot/frame 에 속하나」** | `dt_map_derivation.join_rule` → `load_verified_rules` **직행**(실행기를 통째로 우회) | 🔴 **설정으로 죽어 있다**(J-14) |
| **「원장 v2 소스 준비기가 어떤 조인을 물려받나」** | `VerifiedJoinDescriptor` → `ledger/setup_registry` · `setup_bundle` · `source_preparation` | ✅ 이되 **`attach()` 의 「없을 때만·미상·셀 표시」 계약을 «일부러 안 물려받는다»** |

🔴 **같은 «선언 파일»이 네 물음에 답하고, 그중 하나는 실행기를 우회하며, 하나는 계약을 일부러 안 받는다.**
`verified_join_contract.py:190–240` 의 프레임 검사 발급자가 존재하는 이유가 바로 이것이다 —
**한 값을 나누되 한 뜻을 나누지 않기 위해서.**

## ⑤-G 문서 정정 — 그리고 🔴 **운영자에게 나가는 «거짓 문장»이 하나 있다**

| 자리 | 적힌 것 | 실측 |
|---|---|---|
| 🔴 **`server/config_resolve_report.py:493–494`** (**운영자 화면에 나가는 «코드» 문자열**) | 「그리고 **조인을 실행하는 코드가 아직 없어**, 승인되더라도 지금은 이 선언이 **어디에서도 사용되지 않습니다.**」 | 🔴 **거짓이다.** `virtual_join_executor.attach` 가 «모든 읽기»에서 돈다(main.py:959). 이건 문서가 아니라 **운영 코드 안의 낡은 문장**이고, `GET /admin/config/resolve?domain=virtual_join` 으로 **운영자에게 배달된다.** 제가 직접 확인했다 |
| `virtual_join_rules.md:355`(§8 함정) | 「**가상 컬럼은 CSV 추출에 없다.** 보고서 재료로 쓰지 말 것」 | 🔴 **거짓이고, 같은 파일이 자기를 반박한다** — §9(:377–382)가 수리를 기록한다. 코드: main.py:2297–2346 |
| `virtual_join_rules.md:3`·§2-ter | 「10,000행 한 페이지가 **왕복 20회**(선언 둘 × 청크 10)」 · 「노출 넷이 전부 `virtual_only`」 | ⚠️ 선언이 바뀌었다. 지금은 **활성 선언 둘이 «서로 다른» 왼쪽 표**에 붙는다. 산술의 전제(한 표에 규칙 둘)가 «오늘의 모양이 아니다» |
| `virtual_join_rules.md:347` | 「`POST /admin/reload-configs` 가 즉시 무효화한다」 | ⚠️ 참이되 **약하다** — 무효화는 `system_reload.py:52–56` 에 살고 **`except Exception: pass`** 에 싸여 있다. 실패는 **로그 없는 no-op** |
| `CODE_MAP.md` §5-D 줄 수·앵커 | `virtual_join_executor.py` **631**줄 · `resolved_expression`@300 · `execute_rule`@390 · `_resolve_one`@440 · `attach`@475 | 🔴 실측 **713**줄 · **360** · **459** · **529** · **570**. 앵커가 전부 **60~95줄** 어긋난다 — ±20 허용치를 넘는다 |
| `CODE_MAP.md` §5-D 소비자 목록 | `main.reload_local_process_cache`(3883) 포함 | 🔴 **그 함수는 `main.py` 를 «떠났다»** — 지금은 `system_reload.py:33`. 그리고 목록에 `main.py:2550 resolved_column_announcements` 가 **빠져 있다** |
| `CODE_MAP.md` §5-D 심볼표 | `attach` 의 「제안 맵의 키 `(row_id, col)`」 | 🔴 코드가 **정반대를 명시**한다 — executor:595–599 「`(row_id, col)` 튜플 키를 쓰지 않는다」, 컬럼당 dict 하나 |
| `CODE_MAP.md` §5-C 시그니처 | `unique_index_covering(db, table, columns)` · `required_index_name(table, columns)` | ⚠️ 둘 다 `folds=None` 인자가 **늘었다**(:521 · :174) |
| `data_model.md` | — | 🔴 **가상 조인 절이 «아예 없다».** 그리고 셀 계약 `{value, is_overwrite, priority_source}` 를 문서화하면서 **`priority_source` 가 `"virtual_join"` 일 수 있다는 말이 없다** |
| `virtual_join_executor.py:16–17` · `main.py:951–952` (**코드 주석**) | 「오른쪽은 승인 조건이던 **UNIQUE 인덱스를 그대로 탄다**」 | ⚠️ `virtual_join_rules.md` §2(:118–122)가 **이미 둘 다 거짓이라 표시했다**(실측 계획은 `Hash Left Join` + 오른쪽 `Seq Scan`). **그런데 코드의 사본 둘은 그대로다** |

## ⑤-H 설정 위생 — 이번엔 «샘플이 맞다»
```
샘플이 선언하는 키 8 (left_table·right_table·join_key·expose·unresolved_label
                    ·join_cardinality·enabled·__comment)
코드가 읽는 키    7   (__comment 만 안 읽는다 — 주석 관례)
=> 🔴 「코드가 읽는데 샘플에 없는 키」가 «0» 이다. 이 도메인은 그 병이 없다
   (⑥ 값 제안의 slow_warn_ms 와 «정반대»다)
```

## ⑤-I 못 밝힌 것
- `export_table_csv` 의 500 갈래가 TTL 경계를 걸쳐 도달 가능한가 — 코드 경로만 봤고 돌려 보지 않았다.
- `notation_norm.join_pair_rules` 접기가 살아 있는 선언 위에서 어떻게 도는가 — 실행 미확인.

---

# 🔴 횡단 ① — 「**흐름은 «물음»이지 기능이 아니다**」가 이번에도 걸렸다

지시서가 건 판별식을 네 흐름 전부에 걸었더니 **넷이 열넷이 됐다.**

| 목록의 이름 | 실제로 답하는 물음 | 수 |
|---|---|---|
| ③ 배치 업서트 | 「이 교정을 적용하라」 · 「이 스코프를 «통째로 갈아라»(`replace_map`)」 · 「이 교정이 사람에게 얼마나 들었나(공수)」 | **3** |
| ④ 변경 이력 | 「이 셀은」 · 「이 행은」 · 「이 트랜잭션은」 · 「최근 시스템 전체는」 | **4** |
| ⑤ 가상 조인 | 「이 셀이 지금 뭘 보여주나」 · 「어느 행이 이 조건에 맞나」 · 「이 DT 행은 어디 속하나」 · 「원장 준비기가 뭘 물려받나」 | **4** |
| ⑥ 값 제안 | 「다음에 뭘 칠까」 · 「이 컬럼에 어떤 값들이 있나」 · 「어느 컬럼에 인덱스가 필요한가」 | **3** |
| | | **14** |

🔴 **그리고 갈라진 자리마다 «계약이 달랐다»** — 이게 이 판별식이 실제로 잡는 것이다:
```
④ 한 화면에 절단 계약 «셋»    봉투+페이저 / 봉투 없음 / 봉투를 받고 «버림»
⑥ 같은 라우트에 거절 계약 «둘»  그리드는 «침묵», 맵 에디터는 «문장 셋»
⑤ 같은 선언에 소비 계약 «넷»   하나는 실행기를 «우회»하고, 하나는 계약을 «일부러» 안 받는다
③ 같은 라우트에 응답 계약 «둘»  replace_map 이면 `scope` 9키, 아니면 `scope: null`
```
📌 §2 의 「인벤토리는 «기능»의 목록이지 «흐름»의 목록이 아니다」가 2차에서도 참이었다.
**다만 1차와 «다른 방식»으로 참이다** — 1차는 「목록에 없는 흐름 넷」을 찾았고,
2차는 **「목록에 있는 흐름 넷이 사실은 열넷」**임을 찾았다. 나누는 칼이 같다.

---

# 🔴 횡단 ② — 「**`priority_source` 한 칸을 «세 규칙»이 채운다**」

이게 이번 실측의 제일 큰 발견이고, 흐름 ③·⑤ 를 «가로지르며» ④ 에도 닿는다.

```
① 싼 길      main.py:895-902   CellOverwrite 만 보고 유도    -> user | collision_merge | None
             타는 라우트: GET /tables/{t}/data (그리드 본 화면) · PUT …/data/updates 의 WS 항목
② 선언된 길   main.py:907-909   compute_priority_value       -> SOURCE_PRIORITY 다섯 중 하나
             타는 라우트: 단일 행 · Pin · Pin 배치 · 소스삭제 배치
③ 가상 조인   executor:706-711  attach 가 직접 박는다         -> "virtual_join"
             타는 라우트: 위 «여섯 전부» (attach 는 fetch_and_merge_metadata 안에 있다)
```
### 이 셋이 만드는 세 가지 사실
```
🔴 ①과 ②는 «어긋나는 입력»이 있다   pipeline_parser 만 있는 셀 -> ① None · ② "pipeline_parser"
🔴 ③은 «읽는 CSS 가 0»            grid.js 는 'user'/'collision_merge' 만 묻는다
✅ 그런데 핵심가치 넷은 «지켜진다»   ①이 낼 수 있는 셋이 그리드의 두 물음에 정확히 답한다
                                「사람이 쓴 것이 기계를 이긴다」는 옳게 그려진다
```
🔴 **그래서 이 항목의 판정은 「레이어링이 깨졌다」가 아니라 「한 계약 필드에 저자가 셋인데
아무것도 그 사실을 알리지 않는다」**이다. 오늘 무증상인 이유는 «읽는 쪽이 세 값만 묻기» 때문이고,
`enrichment.js:166` 처럼 **그 문자열을 그대로 화면에 내놓는 소비자**가 이미 하나 있다.

📌 **총괄 판정 요청:** 이 칸의 «값 어휘»를 어디에 선언할 것인가. 지금은 `crud.SOURCE_PRIORITY`(다섯) ·
   싼 길의 리터럴 셋 · `executor` 의 `"virtual_join"` 이 **세 파일에 흩어져 있고**, 어느 것도
   「이 칸이 가질 수 있는 값의 전부」를 말하지 않는다. **경계 계약이라 제가 못 정합니다.**

---

# 🔴 횡단 ③ — 「**절단이 화면에 닿는 것은 «여섯 중 둘»**」

네 흐름에서 「너무 많아 잘랐다」를 나르는 자리를 전수로 세었다.

| 나르개 | 어디서 잘리나 | 화면까지 가나 |
|---|---|---|
| `AuditHistoryPage.truncated` + `next_cursor` | 행·셀 이력 | ✅ 「일부만 (N건) · 더 보기」 + **페이저가 실제로 돈다** |
| `suggest` 응답의 `truncated` | 값 제안 | ✅ 맵 에디터 쪽만 — 「값이 많아 앞의 N개만 내려왔습니다」. ⚠️ 그리드 편집기도 읽지만(vs.js:452) **캐시 정책에만 쓴다**(「완전한 결과만 캐시」, :251) — 운영자에게 «말하지는» 않는다 |
| `X-Audit-Truncated` · `X-Audit-Next-Cursor` | 전역 이력 | 🔴 독자 0 + **CORS `expose_headers` 미등재** |
| `AuditLogGroupPage.truncated` (바디) | 전역 이력 | 🔴 timeline.js:29 가 **구조분해에서 버린다**. 그물이 그 폐기를 «단언»한다 |
| 응답 `total_log_count` (배치 업서트) | `created_logs` 500건 절단 | 🔴 독자 0 — 소스 주석은 「caller can detect truncation」이라 적는다 |
| WS `total_log_count` (체인 워커만) | 같은 절단 | 🔴 독자 0. 그리고 **main.py 경로의 WS 에는 그 키가 «아예 없다»** |
| `/audit_logs/transaction/{tx}` `limit=20000` | 트랜잭션 상세 | 🔴 **나르개 자체가 없다** |

```
=> 절단을 «말할 자리»가 있는 나르개 7 · 화면까지 가는 것 «2»
   그리고 «막을 나르개조차 없는 것» 1 (트랜잭션 상세)
```
🔴 **1차 실측의 「잘림 가드 다섯이 목록을 세지 않고 버린다」와 같은 병이고, 이번엔 «세고 있는데
읽는 쪽이 없는» 쪽이다.** 두 병 다 결과가 같다 — **짧은 목록이 완전한 목록과 구별이 안 된다.**

---

# 📋 §4 규칙대로 뽑은 체크리스트 — 2차 네 흐름분 (발명 없음)

### ㉠ 선언된 것이 «실제로» 지나가나 — 아니오
```
🔴 「후보에서 골랐다」가 확정 경로에서 «증발»한다 — 그리고 공수 blob 에 더하면 계기가 통째로 죽는다
🔴 `batch_row_upsert` 여섯 자리 중 «하나»(체인 워커)가 `change_count` 를 안 싣는다
🔴 기계 쓰기 넷이 `column_name` 자리에 «리터럴 ROW_UPDATE» 를 실어 셀 이력이 구조적으로 못 답한다
🔴 `top_src`(레이어 승자)가 «계산되고 버려진다» — 대입 3 · 참조 0
🔴 `?order_by` 가 가상 조인 컬럼을 «안 받는다» — 그런데 colDef 는 sortable:true
⚠️ `priority_source` 를 채우는 규칙이 «셋»이고 둘은 어긋나는 입력이 있다
```
### ㉡ 받는 쪽이 «있나» — 아니오
```
🔴 응답 `effort_error` 독자 0    — 운영자가 자기 계기가 죽은 것을 «영원히» 모른다 (서버 로그만 안다)
🔴 응답 `total_log_count` 독자 0 · WS `total_log_count` 독자 0
🔴 응답 `scope.delete_ids_omitted` 독자 0 · WS `deleted_row_ids_omitted` 독자 0
   -> 소스 주석이 「NOT a silent truncation … rides the refresh signal AND the response」라 «단언»한다
🔴 헤더 `X-Audit-Truncated` · `X-Audit-Next-Cursor` 독자 0 + CORS 미노출
🔴 `priority_source: "virtual_join"` 을 읽는 CSS/코드 0 — 가상 셀이 화면에서 «출처를 못 말한다»
🔴 셀 소스 모달이 페이로드의 `sources.virtual_join` 을 «못 본다» (404 로 답한다)
🔴 응답 `slow_reason` · `elapsed_ms` 독자 0 — `slow_warn_ms` 손잡이가 그 둘을 위해 존재한다
🔴 이력 응답 키 «여섯» + 헤더 «둘» 미독
⚠️ 「소비자 0」의 두 뜻 — 위 전부가 «퍼뜨리기»(마지막 홉 없음)이지 «빼기»가 아니다
   판별 질문 「이게 없으면 무엇을 말할 수 없게 되나」에 전부 답이 있었다
```
### ㉢ 끊기면 «시끄러운가» — 아니오(조용함)
```
🔴 일반 쓰기의 collision_merge 가 «이력을 한 줄도 안 남긴다» — 그리드는 병합 배지를 그리는데
🔴 replace_map 삭제가 «이력을 안 남긴다» — 같은 행위를 delete_rows_batch 는 남긴다
🔴 전역 이력 절단이 화면에 «없다» — 짧은 목록과 완전한 목록이 «같아 보인다» (그물이 폐기를 단언)
🔴 `/audit_logs/recent` 의 500 이 「No database history recorded.」로 그려진다
🔴 머신 소스에 «핀을 꽂으면» 그리드에 아무 표시도 안 난다 (어느 길로 와도)
🔴 `reset_cache` 실패가 «로그 한 줄 없는» no-op (except Exception: pass)
⚠️ tx 모드 적용이 priority_source 를 안 세워 WS 가 오기 전까지 덮어쓰기 표시가 «없다»
⚠️ 5000건 넘는 배치는 WS 에 `created_logs` 키가 «아예 안 실린다» — 「없었다」와 구별 불가
⚠️ NOTIFY 실패를 통째로 삼킨다 (except Exception: pass) — 대가는 폴백 폴링
```
### ⚰️ 도달 불가 — 죽은 갈래
```
value_suggest       SYSTEM_PREFIX_INDEX_TARGETS 루프(외연 0) · min_prefix_length 400 갈래(설정으로 꺼짐)
                    · _numeric_values(이 흐름에선 관문에 막힘) · permanent 필드(6 write / 0 read)
virtual_join        virtual_only is None 갈래 «셋» · _validate_join 의 facts 슬롯(21 return 전부 None)
                    · "matched"(운영 독자 0) · attach 의 touched 반환(버려짐)
                    · dt_map_derivation 이 찾는 규칙 둘이 «밑줄 접두»라 영원히 안 잡힌다
history             collision_merge 감사 쓰기(crud.py:3094) · top_src
=> 2차 네 흐름 합계: 「반쪽/끊김」 «29» · 그중 «죽은 갈래 13»
```

### 🔴 우선순위 — 「기록이 사라지는 것」 > 「거짓을 말하는 것」 > 「안 들리는 것」
```
🔴🔴 기록 소실   collision_merge 이력 «0» · replace_map 삭제 이력 «0»
                -> 이력은 이 제품의 «정본»이고, 정본에 사건이 없으면 되돌릴 수 없다
                -> 그리고 문서에도 «둘 다 없다»(docs 전체 grep 0) — 아는 사람이 없다
🔴  거짓 발화    전역 이력이 잘린 것을 안 말함 · 500 이 「기록 없음」으로 · 운영자에게 나가는
                「조인 실행 코드가 없습니다」(config_resolve_report:493) · 가상 컬럼 정렬 ·
                batch_update 스펙의 «없는 라우트» 다이어그램
🔴  안 들림      effort_error · total_log_count · scope.* · X-Audit-* · virtual_join 출처 ·
                slow_reason/elapsed_ms · top_src
```

---

# 🚧 총괄 판정이 필요한 것 (경계 계약 — 제가 못 정합니다)

```
① batch_row_upsert 에도 캐노니컬 빌더를 낼 것인가
   -> refresh 쪽은 오늘 닫혔다. upsert 쪽은 «클라가 실제로 읽는» 페이로드인데 손수 작성 6·모양 4
   -> 체인 워커에 change_count 를 더하는 것은 순수 추가지만, 더할지는 계약 결정

② priority_source 의 «값 어휘»를 어디에 선언할 것인가
   -> 지금 세 파일에 흩어져 있고 어느 것도 전체 목록을 말하지 않는다

③ 값 제안의 효과를 «잴 것인가»
   -> 재려면 _validate_effort 허용 키 + interaction_effort_logs 스키마를 함께 움직여야 한다
   -> 「안 잰다」도 정당한 답이다. 다만 그때 vs.js:9-17 의 부등식은 «주장»으로 남는다

④ collision_merge · replace_map 삭제의 이력 부재 — «결함인가 설계인가»
   -> 저는 결함으로 읽었다: 같은 사건이 Pin 경로(4603)에서는 «남고» 일반 경로(3094)에서는 «안 남는다»
   -> 다만 되돌릴 수 없는 부류라 착수 전에 판정이 필요하다
```

---

# 📌 이 문서의 측정 위생 — 스스로 밝히는 것

```
① HEAD 가 «측정 중에» 움직였다 (6bb4e79a -> 907c8995). 전건 재측정했고, 앵커를 다시 확정했다
   -> ③④⑤ 의 main.py 줄 번호는 «다시 잰» 값이다. ⑥ 의 value_suggest 앵커는 그 커밋이 안 건드렸다
② client2 계수는 전부 `grep -a`. NUL 바이트를 든 파일 «둘»(enrichment.js · map2/authoring.js)이
   평범한 grep 에 «안 보인다» — 제가 한 번 빠졌고 파이썬으로 바이트를 세어 확정했다
③ 하위 실측 셋(값제안·가상조인·이력)의 «판정을 좌우하는» 주장은 제가 직접 재확인했다:
   slow_reason 0히트 · SYSTEM_PREFIX_INDEX_TARGETS=() · permanent 6/0 · 응답 9키 ·
   crud.py:3094 의 미-append(형제 아홉과 대조) · apply_row_update_internal 운영 호출자 1 ·
   top_src 3/0 · timeline.js:29 의 구조분해 · get_cell_sources 의 hasattr 관문 ·
   config_resolve_report:493 의 문장
④ 운영 데이터는 «한 줄도» 인용하지 않았다. 이 문서의 모든 수는 «선언·코드·커밋된 시험»에서 나왔다
   (schemas.py:61-68 의 94.08% 는 «저장소에 커밋된» 주석의 인용이고, 제가 잰 값이 아니다 — 그렇게 표시했다)
⑤ 못 밝힌 것은 각 절의 「못 밝힌 것」에 적었다. 넷이다
```
