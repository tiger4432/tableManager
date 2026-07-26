# QA 적대적 재검수 — Universal Transfer Plan M2 (2차, 병합 가부 판정)

- 검수: qa-reviewer (2026-07-26) · 대상: 현재 working tree 전체(미커밋 + untracked) · 1차 NO-GO 이후 수정본
- 1차 리뷰: `agent_workspace/reports/QA_transfer_plan_m2_review.md`
- 대조 산출물: `Server_transfer_plan_m2_report.md`, `Client_transfer_plan_m2_report.md`
- 실행: conda `assy_manager` + `PYTHONIOENCODING=utf-8`. 라이브 재기동 없음(신규 라우트 3종은 404 → **함수 단·DB 직접 호출로 검증**).
- 라이브 시드: `qa_m2b_*` 4행 삽입 후 **스크립트 내에서 삭제 완료** — 잔여 0건 실측(§8).

---

## 1. 판정: **GO-WITH-FIXES**

**근거 한 줄**: 1차 NO-GO의 7개 사유(F1·C1·C2·C3·C4·C9·C10)가 코드와 실측으로 **전부 닫혔고**, "서버가 모른다고 한 것을 클라가 이상 없음으로 바꾸는 경로"는 **0건**이다. 다만 신규 표면(범용 오버레이·DOE 층 저장)에서 **새 결함 3건**이 생겼고 그중 2건은 1차에 닫았던 결함과 **같은 계열의 재발**(잠금 우회·유령 행)이라 병합 전 소폭 수정이 필요하다.

### 1-1. 병합 차단 사유 (3건 — 전부 국소 수정)

| # | 결함 | 왜 차단인가 | 예상 수정 규모 |
|---|---|---|---|
| **B1** | **C5 잠금이 무력화 가능** — 페인팅 중 X/Y/Val 컬럼 드롭다운을 건드리면 `renderMetadataInputs()`가 메타 입력을 통째로 재생성해 `readOnly`와 주입된 `plan_id`가 **둘 다 소실**된다 | 1차 NO-GO 사유(C5, 타 계획 셀 전량 삭제)가 **그대로 재개통**된다 | 2~5줄 |
| **B2** | **DOE 층 행이 절대 정리되지 않는다** — 범위를 줄이거나 단일층으로 접어도 잔재 층 행이 남아 validate 수요에 **유령으로 영구 누적** (라이브 재현) | 1차 필수 수정 C4(유령 DOE)와 **동일 계열이 층 테이블에 그대로 남았다**. 사용자가 지울 방법이 없는 오염이 DB에 축적된다 | `pruneServerDoes` 복제 수준 |
| **B3** | **오버레이 정렬이 조용히 거울상으로 틀리는 조합이 있다** (side 상이 + 타깃 rot 90/270 → 64조합 중 16개, status는 `ok`) | 핵심가치 #3 정면 — "조용히 안 맞음". **완전 수정 대신 해당 조합을 `align_unavailable`로 거절하는 가드 2줄**로도 해제 가능 | 가드 2줄 (수학 수정은 백로그) |

### 1-2. 후속 백로그 (병합 차단 아님)

O2(격자 치수 규약 불일치 → 과도한 `align_unavailable`) · O3(시작좌표 차이 무시) · P1/P2(페인트 잠금 기본값 변경·오버레이 의존) · S1(`bonding_map.base` 인덱스 부재) · N1(remaining 음수) · `source_region` 휴면 코드 · 저심각 4건(§4). 1차 백로그(F2~F7, F9~F13, C6~C8, C11~C14) 중 **F1·F4·F6·F2는 이번에 해소**, 나머지는 유지.

> **총괄 통지 반영**: `source_region` 엔진·테스트 6종은 **의도된 휴면**임을 전제로 평가했다. `plan_store` 4종(plan/doe/map/doe_layer) 확인, `load_source_region`이 None을 반환해 `region_chips` 미방출을 라이브 함수 호출로 실증. **병합 차단 아님 — 후속 정리 항목**으로 분류한다(의견은 §7).

---

## 2. 1차 NO-GO 사유의 실제 폐쇄 여부 (전항 코드+실측 대조)

| # | 1차 지적 | 현재 상태 | 실증 근거 |
|---|---|---|---|
| **F1** | 강등 시 `remaining` 조용히 과대 | **닫힘** | `server/transfer_plan.py:214-297` `_status_is_degraded`/`_degradation_effect`/`assess_degradation`/`build_chips_block`. 강등 시 `remaining=None` + `remaining_reliable=false` + `warnings[source_degraded]{role,status,effect,detail}`. `total`까지 강등이면 `remaining_upper_bound`조차 싣지 않는다(`294-296`) — 상한이 아닌 값을 상한이라 부르지 않음 |
| **F1-b** | `validate`가 오염된 `remaining`으로 "부족 없음" | **닫힘** | `transfer_plan.py:1215-1231` — `remaining_reliable=false`면 `qty_shortage`/`source_fail_chips` 판정을 **`continue`로 건너뛰고** `availability_unreliable`(필요량 + 상한 명시)을 낸다. `1293-1303` — DOE가 있는데 하나도 판정에 도달 못 하면 `status="unverified"` |
| **C1** | 클라가 status 5종을 "미연결" 한 덩어리로 뭉갬 | **닫힘** | `client2/src/transfer_plan.js:415-440` `classifySourceStatus`가 ok/degraded/missing/unknown 4등급 + 원문 보존. `connected(` 접두는 ok, `unavailable(`·`align_unavailable`은 degraded, 미지 상태는 `unknown`으로 **원문 그대로 노출**. 배지 `title`에 `role: status — note` 전문 |
| **C2** | validate 파싱 실패가 "경고 없음 ✓" 초록으로 뒤집힘 | **닫힘** | `transfer_plan.js:717-727` — `.catch(()=>null)` 제거, 파싱 실패/`warnings` 배열 부재를 `{broken:true, brokenReason}`으로 승격. `:690-691`이 붉은 "**서버 검증 결과를 읽지 못했습니다**"를 렌더. `:653` `trusted = !verificationSkipped && !validateBroken` |
| **C3** | `stage_unknown`에도 자체 초록 배지 | **닫힘** | `transfer_plan.js:680-683` 전용 `tp-skip-banner`("🚨 서버 검증이 수행되지 않았습니다 … 검증 통과가 아니라 미검증"). `:665` 수량 배지가 `검증 스킵`, `:670` FAIL 배지가 `warn`으로 강등. `:694` 경고 0건 + unverified면 초록 대신 경고문. 경고는 `WARN_SEVERITY`로 critical/high/normal/unknown 4등급 정렬 렌더(`:480-506`) |
| **C4** | DOE 삭제·개명이 서버에 유령으로 잔존 | **닫힘** | `transfer_plan.js:1320-1348` `pruneServerDoes` — plan_id 하위 조회 → `keepValues` diff → `batch_delete`. **`data.total > rows.length`면 정리를 생략하고 사유를 반환**(부분 조회로 오삭제 방지, `:1328-1330`). 실패 시 `:1447` 경고 토스트로 사용자 고지 |
| **C9** | 헤더/DOE 부분 실패 시 서버·화면 분기 | **닫힘(부수 효과)** | `transfer_plan.js:1424-1439` — DOE → layer → prune → **헤더를 마지막에 커밋**. "먼저 확정하면 DOE 실패 시 서버/화면이 갈라진다"는 주석대로 순서 역전 |
| **C10** | 취소 토스트가 거짓("미반영") | **닫힘** | `map_editor.js:3628,3650`이 `pushed`를 onCancel에 전달 → `transfer_plan.js:1194-1201`이 "⚠️ 취소했지만 이미 [⚡ Push]로 서버에 저장된 뒤였습니다 — 자동 되돌림은 없습니다" + 서버 재조회 |
| **C5** | 페인팅 중 맵 키 입력 미잠금 | **부분** → **B1** | `map_editor.js:3526-3540` `lockPlanMetaInputs` 신설, `:3614` 진입 시 잠금 / `:3645` 이탈 시 해제. push 확인문에 `대상 맵 키`(`:2749`) 명시. **그러나 잠금이 우회 가능 — §3 B1** |
| **F4** | 소스 합산 초과배정 미검출 | **닫힘** | `transfer_plan.py:1235-1242`(누적), `:1278-1291` `source_overallocated`. 단독 DOE 소스는 `qty_shortage`가 같은 사실을 말하므로 제외(`:1280`) — 중복 경고 방지 타당 |
| **F6** | align에 `dst_grid` 미전달 | **닫힘** | 신규 `map_overlay.py:305`는 `make_align_transform(align, src_grid, target_grid)`로 3인자 호출. 치수 가드가 실제로 작동함을 라이브 재현(§3 O2) |
| **F2** | 캡 절단 무표기 | **닫힘** | `remaining_reliable` 경로에 `WARN_RESULT_TRUNCATED` 편입, 클라 `transfer_plan.js:454-457`이 `truncated`/`by_core_truncated`를 신뢰도 사유로 수집. 오버레이도 `truncated`+`cap` 명시(`map_overlay.py:325-329`) |
| **F3** | 행 수 vs distinct 칩 | **제외(근거 있는 보류)** — 후속 티켓 동의 |

**결론**: "서버가 모른다고 한 것을 클라가 이상 없음으로 바꾸는 경로"를 재탐색한 결과 **0건**. `remaining=null`·`remaining_reliable:false`·`status:"unverified"`·`availability_checked:false` 4개 신호가 각각 독립적으로 클라 초록을 차단하며(`transfer_plan.js:449-464`, `:645-653`, `:663-673`), 어느 하나만 살아도 초록이 뜨지 않는 **다중 방어**다.

---

## 3. 확인된 결함 (심각도순)

### [높음 · 병합 차단] B1 — 페인팅 중 맵 키 잠금이 컬럼 드롭다운 한 번으로 풀린다 (C5 재개통)

`client2/src/map_editor.js:435-446`(드롭다운 핸들러) → `:743-746`(`renderMetadataInputs`) vs `:3526-3540`(`lockPlanMetaInputs`), `:3608-3614`(잠금 대상)

```js
// :435-446  — 페인팅 모드에서도 살아 있는 핸들러
el.colMapX.addEventListener('change', () => { renderMetadataInputs(); ... });
// :746 — 컨테이너를 통째로 비우고 새 input을 만든다 (readOnly·value 둘 다 소실)
container.innerHTML = '';
```

진입 시 봉인 대상은 `tableSelect`(`:3608`)와 `btnLoadMap`(`:3609`)뿐이고 **X/Y/Val 컬럼 드롭다운은 열려 있다**. `renderMetadataInputs()`에는 `planPaint` 인지가 전혀 없어 재생성된 `meta-input-plan_id`는 **빈 값 + 편집 가능** 상태가 된다.

**실패 시나리오**: 계획 `bonding__TAPE-A_01`을 페인팅하다 val 컬럼을 잘못 골랐다고 생각해 드롭다운을 바꾼다 → 맵 키 입력이 빈 칸이 되고 잠금 해제 → 사용자가 `bonding__TAPE-A_02`를 타이핑(자동완성/직전 기억) → ⚡Push → `crud.py:971-1009`가 `map_key_columns=["plan_id"]` 기준으로 **`TAPE-A_02` 계획의 셀 전량 + CellSource/CellOverwrite를 삭제 후 재기록**. 1차 C5와 동일 결과다.
(비운 채로 Push하면 다른 메타 컬럼이 없을 때 `:2647` alert로 막히지만, 이는 우연한 방어일 뿐 `plan_id`를 다시 채우는 순간 무효다.)

**권장**: ① `renderMetadataInputs()` 말미에 `if (planPaint) lockPlanMetaInputs(true)` 재적용 + 계획 키 값 재주입, **또는** ② 페인팅 모드에서 `el.colMapX/Y/Val`도 `disabled` 처리(tableSelect와 동일 대우). ①이 더 견고하다 — 잠금 소유권을 렌더러에 두면 향후 재렌더 경로가 늘어도 새지 않는다.

---

### [높음 · 병합 차단] B2 — DOE 층 배정 행이 정리되지 않아 유령 층 수요가 영구 누적

`client2/src/transfer_plan.js:1395-1437`(층 PUT만, prune 없음) vs `:1320-1348`(DOE만 prune) · `server/transfer_plan.py:1022-1053`(층 로드), `:1170-1182`(수요 생성)

클라는 현재 UI의 층만 `PUT`한다(`:1407-1419`). **범위 축소·단일층 접기·층 삭제에 대한 삭제 경로가 없다.** 서버는 `doe_key LIKE '{plan_id}|%'`로 **테이블에 남아 있는 모든 층 행**을 읽어(`:1030-1032`) DOE당 수요로 펼친다(`:1172-1182`).

**라이브 재현** (`qa_m2b_*` 시드, `validate_plan` 직접 호출 — 정리 완료):

| 단계 | DOE 선언 | 층 테이블 행 | validate 수요 |
|---|---|---|---|
| 1) 층 1–3 저장 | `layer_from=1, layer_to=3` | 3 | `@L1 @L2 @L3` (정상) |
| 2) 범위를 1–2로 축소 후 재저장 | `layer_to=2` | **3 (층3 잔재)** | `@L1 @L2 @L3` — **층3 유령** |
| 3) 단일층(1)으로 접기 후 재저장 | `layer_from=layer_to=1` | **3 (층2·3 잔재)** | `@L1 @L2 @L3` — **유령 2건** |

3단계에서 실제 소요는 셀 2 × 1층 = **2**인데 validate는 **6**으로 보고, 존재하지 않는 층 2건에 대해 `qty_shortage`를 내고 `source_overallocated`가 "DOE 3건(@L1,@L2,@L3)의 필요 합계 6"이라고 단언한다. 사용자는 화면에 없는 층에 대한 경고를 **지울 방법이 없다** — 1차 C4와 정확히 같은 형태다.

부수: 층 커버리지도 잔재 층을 `covered`에 넣으므로(`transfer_plan.py:1121-1124`) 실제로 비어 있는 층이 "배정됨"으로 계산돼 `layer_coverage_gap`이 침묵한다 — 이쪽은 **거짓 초록** 방향이다.

**권장**: `savePlanToServer`에서 `pruneServerDoes`와 동일 패턴으로 `transfer_plan_doe_layer`도 정리(현 `plan_id` 하위 `layer_key` 조회 → 이번에 쓴 bk 집합과 diff → `batch_delete`). 부분 조회 가드(`total > rows.length` 시 생략 + 고지)도 동일하게 둘 것. 삭제된 DOE의 층 행도 함께 제거해야 재사용된 DOE 이름에 과거 층이 되살아나지 않는다.

---

### [높음 · 병합 차단(가드로 해제 가능)] B3(O1) — 오버레이 정렬 유도가 조용히 거울상으로 틀리는 조합

`server/map_overlay.py:148-162`(유도) · `server/bonding_plan.py:187-206`(합성) · 검증: 물리 좌표 경유 정답과 전수 대조

`rel_rot = (source.rotation − target.rotation) mod 360` + `flip = 'x' if side 상이`를 **하나의 변환기**(`WaferMapCoordinateTransformer(rotation=rel_rot, side=back-if-flip)`)에 넣어 합성한다. 그런데 `cell_to_physical`의 back 반전 축은 **자기 프레임의 회전에 따라 달라진다**(`coordinate_transformer.py:55-59` — 90/270이면 행 반전, 아니면 열 반전). 상대 회전 하나로는 두 프레임 각각의 반전 축을 표현할 수 없다.

**전수 대조 결과** (정답 = `T_target.physical_to_cell(T_source.cell_to_physical(c))`, 4 rot × 2 side × 4 rot × 2 side = 64조합):

| 격자 | 틀린 조합 | 패턴 |
|---|---|---|
| 정방 5×5 | **16/64** | **`target.rotation ∈ {90,270}` AND `source.side ≠ target.side`** 전부 |
| 비정방 6×4 | **16/64** | 동일 패턴 (전 셀 오배치) |

예: `source(rot 90, front)` → `target(rot 90, back)`. 유도 결과 `(rotation 0, flip x)`, `status: "ok"`. 소스 셀 (1,1)이 **(5,1)**로 그려지지만 정답은 **(1,5)** — 24/25 셀이 틀린다. 응답 어디에도 흔적이 없다.

**라이브 노출도**: `wafer_map_metadata` 실측에 `side=back`(bonding_map 3건, sample_map 1건)과 `rotation=270`(bonding_map 1건, sample_map 1건)이 **둘 다 실재**한다. 다만 현재 페인트 잠금이 소비하는 조합(`transfer_plan_map` ← `core_defect_map` rot0/front + `eds_fail_map` rot180/front, 40×40 정방)은 **이 패턴에 해당하지 않아 오늘 당장의 오배정 위험은 없다**. 위험은 사용자가 back면 맵이나 rot 270 캔버스를 겹치는 순간 발화한다.

**테스트가 이 구멍을 덮고 있다**: `server/tests/test_map_overlay.py`의 align 테스트 6종은 **전부 6×6 정방 + 타깃 rot 0**이고, flip 테스트(`:181-201`)는 `source(rot 0, back) → target(rot 0, front)` — 정확히 **정답이 나오는 쪽**만 고른다. 초록불이 안전을 보증하지 않는다.

**권장(병합용 최소 조치)**: `resolve_align`에서 `flip != 'none'` **AND** `target.rotation ∈ {90,270}`이면 유도를 포기하고 `align_unavailable`(사유: "면 반전과 타깃 회전이 겹쳐 변환을 유도할 수 없음")을 낸다 — 조용한 오답이 소리 나는 거절로 바뀐다. 근본 수정(각 프레임을 물리 좌표로 각각 사상 후 합성)은 백로그.

---

### [중] O2 — `grid_cols/rows` 규약 불일치: 유도 정렬이 비정방+90/270에서 **항상** `align_unavailable`

`server/map_overlay.py:100-111`(`_grid_of`) → `server/bonding_plan.py:172-185`

맵 에디터가 기록하는 `grid_cols/grid_rows`는 **물리(비회전) 치수**다(`map_editor.js:838-841` — `visualCols = isRotated90or270 ? rows : cols`, 즉 입력 cols/rows가 물리축). 반면 `make_align_transform`은 `src_grid`를 **소스 프레임(DOM) 치수**로 보고 90/270에서 스왑한다(`bonding_plan.py:173-176`). 두 규약이 어긋나 이중 스왑이 발생한다.

**라이브 재현** (`bonding_map` 4B12 = rot270/front 27×21, 4B13 = rot0/back 27×21):

```
target=4B12 ← source=4B13 : status=align_unavailable
  detail: 격자 규격 비호환: align frame dims mismatch: source 27x21 rotated 90
          maps to 21x27, but canonical grid is 27x21
```

두 맵 모두 27×21로 **정합하게 선언돼 있는데도** 거절된다. 모듈 docstring이 "`align_unavailable`은 치수 모순 등 계산 불가일 때만"이라 적었으나 실제로는 **정상 선언을 코드 자신의 규약 불일치로 거절**한다 → 판정이 **과도**한 쪽이다.

역방향 위험: 타깃에 메타가 없으면 `dst_cols/dst_rows = 0`이 되어 치수 가드가 **통째로 건너뛰어지고**(`bonding_plan.py:181`) 전치된 좌표가 `status: "ok"`로 나간다 — 이때는 **과소** 판정(조용한 오답)이다.

**권장**: `_grid_of`가 맵 **자신의** rotation이 90/270이면 cols/rows를 스왑해 프레임 치수로 정규화한 뒤 넘길 것. 또는 `grid_cols/rows`의 의미(물리 vs 프레임)를 스펙 문서에 못박고 양쪽을 그 규약으로 통일. **정방 격자(현행 40×40 계측 맵)에서는 무해**하므로 백로그로 충분하다.

---

### [중] O3 — identity 지름길이 `grid_start_x/y` 차이를 무시한다

`server/map_overlay.py:159-160`

```python
if rel_rot == 0 and flip == "none":
    return None, ALIGN_ORIGIN_IDENTITY, None      # start 차이를 보지 않는다
```

비-identity 경로는 `make_align_transform`이 `dst_start_x/y`로 시작좌표를 보정하는데(`bonding_plan.py:166-167, 204`), identity 지름길만 이 보정을 건너뛴다.

**대조 실증**: 소스 start (0,0) / 타깃 start (1,1), 동일 rot·side → 전 셀이 **(1,1)만큼 어긋난 채** `status: "ok"`. 라이브 메타는 현재 전부 start=(1,1)이라 미발화하나, 인제션 생성기와 에디터의 기본 start가 다르면(에디터 `standard` 선택 시 startX/Y=0 — `map_editor.js:2391-2392`) 즉시 발화한다.

**권장**: identity 판정에 `source.start == target.start` 조건을 추가하거나, start가 다르면 offset만 갖는 align을 만들어 정규 경로로 보낼 것.

---

### [중] P1 — 페인트 잠금 기본값이 뒤집혔다 (총괄이 사용자에게 확인할 항목)

`client2/src/map_editor.js:35-38, 84-99` · `server/map_overlay.py:360-379` · `server/config/map_overlay_config.json(.sample)`

클라의 `'F'` 하드코딩이 제거되고 **선언이 없으면 잠금 없음**이 기본이 됐다. **조용히 동작이 바뀌는 지점 3곳**:

1. **재기동 전 구간(지금)**: `/api/maps/paint-rules`가 404 → `paintLockConfig = {...NO_PAINT_LOCK, source:'unsupported'}`(`:89`) → **모든 맵에서 F 셀 보호가 사라진다**. 사용자 고지가 전혀 없다(잠금이 켜졌을 때만 `console.info`, 꺼졌을 때는 침묵). ⚠️ **클라만 배포하고 서버를 재기동하지 않으면 그 사이 F 보호가 통째로 없는 상태로 운영된다.**
2. **신규/타 환경**: `.sample`은 `"*": {"enabled": false, "blocking_values": []}`로 배포된다 — **샘플로 부트스트랩한 환경은 F 잠금이 꺼진 채 시작**한다. (현재 라이브 `map_overlay_config.json`은 `"*": {"enabled": true, "blocking_values": ["F"]}`로 손질돼 있어 재기동 후에는 기존 동작이 보존된다 — 실측 확인.)
3. **`transfer_plan_map`만 F가 빠진다**: `get_paint_rules`가 `merged.update(specific)`의 **얕은 병합**(`map_overlay.py:372-373`)이라 테이블별 `blocking_values: []`가 와일드카드의 `["F"]`를 **대체**한다. 계획 맵에서는 F 값 자체로는 잠기지 않고 오버레이 기준으로만 잠긴다 — 설정 의도대로지만 "F는 못 칠한다"는 기존 기대와 다르다.

**총괄 확인 요청**: (a) 재기동 전까지 F 보호 공백을 감수할지(→ 클라·서버 동시 배포 권장), (b) `.sample`의 `*`를 `enabled:true, ["F"]`로 맞춰 신규 환경 기본을 기존 동작과 일치시킬지, (c) 계획 맵에서 F 값 잠금이 빠지는 것이 의도인지.

---

### [중] P2 — `from_overlay` 잠금은 오버레이를 **띄웠을 때만** 걸린다 (선언과 실효의 괴리)

`client2/src/map_editor.js:50-56`

```js
function isOverlayLocked(key) {
  if (!paintLockConfig.enabled) return false;
  const from = ...paintLockConfig.from_overlay...;
  if (from.length === 0) return false;
  return overlayLayers.some(o => from.includes(o.sourceTable) && o.cells && o.cells.has(key));
}
```

라이브 config는 `transfer_plan_map`에 `from_overlay: ["core_defect_map","eds_fail_map"]`, 메시지 "불량 칩 위치라 배정할 수 없습니다"를 선언한다. 그러나 사용자가 오버레이를 **로드하지 않으면 `overlayLayers`가 비어 잠금이 0건**이다.

**실패 시나리오**: 사용자가 계획 페인팅에 바로 들어가 불량 칩 위에 DOE를 배정한다 → 아무 경고 없이 통과 → 서버 validate도 이 규칙을 검사하지 않는다(`transfer_plan.py` 어디에도 `paint_lock` 참조 없음 — 전수 확인). **선언된 보호가 UI 조작에 의존해 조용히 미적용**된다.

**권장**: `from_overlay`가 선언돼 있는데 해당 오버레이가 로드되지 않았으면 페인팅 화면에 "불량 기준 잠금이 선언돼 있으나 오버레이 미로드 — 보호 미적용" 배너를 띄우거나, 계획 페인팅 진입 시 선언된 오버레이를 자동 로드할 것. 근본적으로는 **서버 validate가 같은 규칙을 재검사**하는 것이 옳다(클라 화면 상태에 무결성을 의존하지 않는 원칙).

---

### [중] S1 — 오버레이가 `bonding_map` 175만 행을 **풀스캔**한다 (인덱스 부재)

`server/map_overlay.py:317` · 라이브 `map_overlay_config.json`의 `table_bindings.bonding_map.key_columns = ["base"]`

```
EXPLAIN (ANALYZE, BUFFERS) SELECT x,y,leg FROM bonding_map WHERE base='0f22e3…' LIMIT 20001
  Parallel Seq Scan on bonding_map  (rows removed by filter: 585,091 × 3 workers)
  Buffers: shared hit=169 read=51984      Execution Time: 214.5 ms
```

`bonding_map`의 인덱스는 `row_id`/`business_key_val`/`created_at`/`updated_at`뿐이고 **`base` 인덱스가 없다**. 오버레이 1종당 1회 풀스캔, 요청당 최대 8종 → **1.7초/요청**(현 규모). 1,000만 행 규율에서는 선형 악화한다. `setup_transfer_plan_indexes.py`에도 이 인덱스가 없다.

또한 `transfer_plan_doe_layer`는 스크립트에 `idx_transfer_plan_doe_layer_doe`가 선언돼 있으나(`:31`) **라이브에는 아직 없다**(`row_id`만) — 스크립트 재실행이 필요하다.

**권장**: `bonding_map(base)` 인덱스 추가 + 스크립트에 편입, 그리고 오버레이 config에 바인딩을 선언할 때 **키 컬럼 인덱스 존재 확인을 절차로** 둘 것. `bonding_log(base_id)` 바인딩도 동일 점검 필요(미확인 — §6).

---

### [중] N1 — `remaining`이 음수인데 `remaining_reliable: true`, 전 역할 `connected`, 경고 0건

`server/transfer_plan.py:280-297`, `241-277`

라이브 실측 (`get_stage_source_summary` 직접 호출):

```
LOT-D/05 stage=bonding
  sources : 전부 "connected"
  chips   : total=0, fail={defect:0, eds_fail:0}, transferred=22,
            remaining=-22, remaining_reliable=True, upper_bound=None
  warnings: [] (이력 경고 2건만)
```

`assess_degradation`은 **상태 문자열만** 본다. 역할이 정상 연결됐지만 그 (lot, slot)에 행이 0건이면 `total=0`이 되고, 다른 역할은 22행을 찾아 `remaining = 0 − 22 = −22`가 된다. 산출 모델의 전제가 깨졌다는 **가장 명백한 증거(음수)** 를 아무도 검사하지 않는다.

방향은 **보수적**(가용을 과소 보고 → `qty_shortage` 발화)이라 거짓 초록은 아니다. 그래서 차단 사유는 아니지만, `total == 0 && transferred > 0` 또는 `remaining < 0`을 `remaining_reliable=false`로 내리는 **불변식 검사 3줄**이면 이 계열 전체를 잡는다.

**권장**: `build_chips_block`에 불변식 가드 추가(`remaining < 0` → 신뢰 불가 + `warnings[source_degraded]{effect:"model_violated"}`).

---

### [낮음] 그 밖

| # | 지적 | 위치 |
|---|---|---|
| L1 | `doe_key LIKE '{plan_id}|%'`의 **plan_id를 이스케이프하지 않는다**. plan_id에 `_`가 흔하므로(`bonding__TAPE-A_01`) LIKE 와일드카드로 해석돼 **타 계획의 층 행을 끌어올 수 있다**(`bonding__TAPE-AX01`이 매칭). `ESCAPE` 절 또는 `like(..., escape='\\')` 필요 | `server/transfer_plan.py:1031` |
| L2 | `_key_filters`가 `map_key`를 `_`로 분해하며 **마지막 컬럼이 나머지를 흡수**한다. 주석은 "랏 이름에 `_`가 있는 경우 방어"라 적었으나 흡수 대상이 slot이라 정반대 — `LOT_D` + `05` → `lot='LOT', slot='D_05'`로 **0건 조회 → `no_data`**(라이브 언더스코어 랏 0건이라 미발화) | `server/map_overlay.py:222-239` |
| L3 | 클라 주석의 오버레이 계약이 **실제와 다르다** — `source_table=&source_key=` 단일 파라미터, `align_applied: bool`이라 적혀 있으나 실제는 `sources=<csv>`, `align_applied`는 객체. 코드는 실제 계약대로 동작하므로 주석만 stale | `client2/src/map_editor.js:3660-3663` |
| L4 | `recomputeLockedCells()`는 `loadedFCells`에 **추가만** 하고 제거하지 않는다. 맵을 유지한 채 잠금 선언이 다른 테이블로 전환하면 이전 잠금이 잔류 | `client2/src/map_editor.js:102-106`, `:704` |
| L5 | `fetchPaintRules(tableName)`가 `await` 없이 호출된다(`:704`). 맵 로드가 규칙 도착보다 빠르면 그 순간 잠금 셀 판정이 비어 있다(이후 `recomputeLockedCells`로 수렴하므로 실해는 작음) | `client2/src/map_editor.js:704` |
| L6 | `source_alloc`이 label 중복을 dedupe하므로(`:1241`) 같은 label 수요가 2건이면 `does` 길이가 1로 남아 `source_overallocated` 임계(`len < 2`)에 걸리지 않는다. 현 bk 규칙상 발생 난이도는 높다 | `server/transfer_plan.py:1241, 1280` |

---

## 4. 반증 시도했으나 안전한 항목

| 가설 | 반증 결과 |
|---|---|
| 서버 강등 신호를 클라가 다시 뭉갠다(1차 C1 재발) | **안전.** `classifySourceStatus`가 4등급 + 원문 보존, `title`에 전문. 서버 5종 → 화면 4구별 + 원문 노출 |
| 어딘가에 초록으로 새는 우회로가 남아 있다 | **안전.** `broken`/`unverified`/`availabilityChecked===false`/`skipWarns` 4경로가 모두 `trusted`를 끈다(`:645-653`). 배지 3종·validate 문구가 전부 `trusted`에 종속(`:663-673`, `:694-695`) |
| `remaining=None`을 클라가 0으로 표시 | **안전.** `layerStats:518-522`가 `remaining !== null && !== undefined`일 때만 `remainingKnown`, 아니면 `shortageUnverifiable`(`:529-530`) — "충족"이라 단정하지 않는다 |
| `pruneServerDoes`가 부분 조회로 **살아있는 DOE를 오삭제** | **안전.** `data.total > rows.length`면 정리 자체를 생략하고 사유 반환(`:1328-1330`). `row_id` 누락 시에도 생략(`:1338`) |
| 오버레이가 기존 맵 편집/push 경로를 오염 | **안전.** `overlayLayers`는 `gridData`/`gridCells2D`와 별도 자료구조이고 `pushMapData`는 후자만 순회. 기준 맵 재로드 시 오버레이 자동 해제 + 고지(`map_editor.js:2266-2270`). 격자 규격 변경 시 `rawCells`에서 재배치(`:3822-3843`) — 조용한 어긋남 방지 |
| 오버레이가 좌표를 **이중 변환** | **안전.** `overlayCellsToPhysMap`(`:3702-3718`)은 기존 맵 로드와 동일한 "논리 → 캔버스 셀 → 물리 키" 배치만 수행하고 회전·반전을 적용하지 않는다 |
| 오버레이 실패가 조용히 원본 좌표로 그려진다 | **안전.** `status !== 'ok'`면 **그리지 않고** 사유 반환(`:3765-3771`), 404/405/파싱실패/빈응답 전부 개별 사유(`:3741-3761`). `align_unavailable`을 "데이터 없음이 아님"이라 명시 |
| 오버레이 캡 초과가 조용히 절단 | **안전.** `limit(cap+1)` 후 초과 시 `truncated:true` + `cap` 명시(`map_overlay.py:317, 325-329`), 클라가 layer에 보존(`:3789-3790`) |
| `limit` 파라미터로 캡을 넘길 수 있다 | **안전.** `min(int(limit), MAX_OVERLAY_CELLS)` 클램프(`main.py` 신규 라우트), 비정수는 400 |
| `sources` 개수 무제한 | **안전.** 9개째에서 `ValueError` → 400 (실측: `sources exceed limit (8)`) |
| 오버레이 라우트가 이벤트 루프를 블로킹 | **안전.** 신규 5개 라우트 전부 `def`(sync) → FastAPI 스레드풀. 다만 S1의 풀스캔은 워커 점유 시간 문제로 남는다 |
| config 손상이 기동을 막는다 | **안전.** `load_overlay_config`가 FileNotFoundError·파싱실패·비-dict를 전부 `{}`로 흡수(`map_overlay.py:57-68`) |
| 신규 라우트가 M1 계약을 변경 | **안전.** `git diff server/main.py` = **2982행 이후 순수 추가 115줄**, 기존 라우트 무수정. `bonding_plan.py`도 `git status` 무수정 |
| 삭제된 `bonding_plan.js/css` 잔존 참조 | **안전.** `client2/src`·`*.html` 전수 검색 히트 2건 모두 무해(`M1_DRAFT_PREFIX` localStorage 마이그레이션 키, `LEGACY_STAGE_ALIASES`). `import`/`<script>` 참조 0건 |
| dist 빌드가 최신 src를 반영 못 함 | **안전.** `dist/map_editor.html` → `map_editor-C8ExVFUO.js`/`-BAnKN4-M.css` 실재, 구 해시 삭제. 문자열 마커 전수 확인: `계획 페인팅 중에는 맵 키를 변경할 수 없습니다`·`삭제·개명 DOE 정리 실패`·`정렬 근거가 없어`·`transfer_plan_doe_layer`·`paint-rules`·`remaining_reliable` **전부 존재** |
| 클라 문법 오류 | **안전.** `node --check` 양쪽 OK |
| `source_region` 휴면 코드가 응답을 오염 | **안전.** 라이브 `plan_store` 4종에 `source_region` 없음 → `load_source_region`이 None → `region_chips` 미방출. `plan_id`를 붙여도 응답 무변화(실측) |
| 인덱스 셋업 스크립트가 트랜잭션 오염 | **안전.** information_schema 존재 게이트 + 실패 시 즉시 rollback (1차 확인 유지). 미존재 `transfer_plan_source_region`은 게이트에서 건너뛴다 |
| 테스트 기준선 주장이 거짓 | **안전.** 직접 실행 **339 passed / 1 failed** — 실패는 기허용 `test_api.py::test_map_presets_api` 1건. 총괄 정정 통지 및 서버 보고서 최종 수치와 일치 |
| M1 하위호환 회귀 | **안전.** `test_transfer_plan.py` 47종에 M1 reshape 검증 포함(`test_dt_stage_reshapes_m1_summary` 등), 전부 통과 |

---

## 5. 런타임 검증 필요 (재기동 후 — 코드만으로 단정 불가)

1. **신규 라우트 5종 실응답** — `/api/maps/overlay`, `/api/maps/paint-rules`, `/api/transfer-plan/{stages,source-summary,validate}`. 특히 paint-rules가 라이브 config의 `*`=`["F"]`를 반환해 **기존 F 잠금이 복구되는지**(P1-1).
2. **`setup_transfer_plan_indexes.py` 재실행** — `idx_transfer_plan_doe_layer_doe`가 라이브에 아직 없다(실측). 실행 후 존재 확인.
3. **`bonding_map(base)` 인덱스 추가 후 오버레이 지연 재측정** — 현재 214ms/1.75M행 풀스캔(S1).
4. **`bonding_log(base_id)` 인덱스 유무** — overlay config가 바인딩을 선언했으나 본 검수에서 미확인.
5. **B1 수정 후 페인팅 재검증** — 컬럼 드롭다운 변경 → 맵 키 잠금·값 유지 확인, 완료/취소 양쪽 원복.
6. **B2 수정 후 층 왕복** — 3층 저장 → 1층으로 접기 → validate에 `@L2/@L3`이 사라지는지(현재 재현 절차 그대로).
7. **B3 가드 후 오버레이** — back면 맵 ↔ rot270 캔버스 조합이 `align_unavailable`로 **거절**되는지(조용히 그려지지 않는지).
8. **M1 초안 마이그레이션 수락 경로** — 1차에서 미검증으로 남은 항목, 수동 1회 필요.

---

## 6. 문서 정합 — 불일치·과장

| # | 지적 | 근거 |
|---|---|---|
| D1 | **`docs/architecture/CODE_MAP.md`에 신규 모듈 3종 부재 여부 재확인 필요** — `server/transfer_plan.py`(1,313줄), `server/map_overlay.py`(379줄), `client2/src/transfer_plan.js`(1,745줄). 1차 D1 미해소 시 병합 배치에 doc-keeper 동반 필요 | 1차 D1 |
| D2 | **`PROJECT_STATUS.md` 명칭 불일치** (1차 D2) — 실 구현은 `transfer_plan`/`_doe`/`_map`/`_doe_layer` | 1차 D2 |
| D3 | **`map_overlay.py` 모듈 docstring이 실제보다 강하다** — "`align_unavailable`은 변환을 계산할 근거가 없을 때만"이라 단언하나, 실제로는 정합하게 선언된 27×21 쌍을 코드 자신의 치수 규약 불일치로 거절한다(O2). 또한 "두 맵 메타 차이로 유도된다"는 서술이 side 상이 + 타깃 90/270에서 성립하지 않는다(B3) | `map_overlay.py:7-27` |
| D4 | **클라 코드 주석의 오버레이 계약이 stale** — 실제 API와 파라미터·응답 형태가 다르다(L3) | `map_editor.js:3660-3663` |
| D5 | **`test_map_overlay.py` 문서화된 커버리지가 실제보다 넓게 읽힌다** — "정렬은 메타 차이에서 자동 유도"를 검증한다고 적었으나 전 케이스가 정방 6×6 + 타깃 rot 0이다. 비정방·타깃 회전·side×회전 결합이 **0건** | `test_map_overlay.py:1-10, 114-201` |
| D6 | 서버 보고서 최종 수치(**339 passed / 1 allowed fail**)는 **실측과 일치**. 중간 로그의 297/298/307/333은 시점별 값이며 §1·§13이 최종값으로 정리돼 자기 불일치 없음 — 1차 D6 해소 | 직접 실행 |
| D7 | **`.sample`과 라이브 config의 `paint_lock.*` 기본값이 반대**(`enabled:false` vs `true`). 어느 쪽이 정본인지 스펙에 명문화 필요 | `map_overlay_config.json(.sample)` |

---

## 7. 총괄 질의에 대한 회신

**`source_region` 휴면 코드 — 의견: 병합 차단 아님, "선언된 휴면"으로 표기 후 유지 권장.**

- 실증상 **완전 무해**하다: `plan_store`에 키가 없으므로 `_resolve`가 None을 반환하고 `region_chips`는 어떤 입력으로도 방출되지 않는다. 테스트 6종은 자체 픽스처라 라이브와 무관하다.
- 되돌리는 것이 새 변경이라는 판단에 동의한다. **다만 "죽은 코드"와 "보류된 코드"는 다음 검수자에게 구별되어야 한다** — 지금 상태로는 `load_source_region`을 본 사람이 "배선 누락 결함"으로 재보고할 가능성이 높다(내가 그럴 뻔했다).
- **권장(후속, 1줄)**: `load_source_region` docstring 첫 줄에 `[보류 — 모델 재설계 대기. plan_store.source_region 선언을 의도적으로 두지 않음(총괄 2026-07-26)]`를 명시. `setup_transfer_plan_indexes.py:33`의 `transfer_plan_source_region` 항목도 같은 주석으로 표시(게이트에서 건너뛰므로 동작상 무해).

---

## 8. 라이브 데이터 영향 / 정리

- 삽입: `qa_m2b_bonding__QAM2B-T_01` (transfer_plan 1행, transfer_plan_doe 1행, transfer_plan_doe_layer 3행, transfer_plan_map 2행) — **스크립트 종료 시 전량 삭제 완료**.
- 삭제 후 실측: 4개 테이블 모두 `LIKE 'qa_m2b%'` **0건**. → **총괄이 정리할 항목 없음.**
- `crud` 경유가 아닌 직접 모델 삽입이라 `cell_overwrites`/`CellSource` 부작용 없음.
- **참고(총괄 판단 사항)**: 라이브 `transfer_plan`에 `TP-SMOKE-1`(서버 스모크)과 `bonding__AABB`(클라 검증) 2행이 남아 있다. 본 검수는 삭제하지 않았다.
- 검증 스크립트는 전부 세션 스크래치패드에만 생성(프로젝트 트리 무접촉). 코드 수정 0건.

---

## 9. 교훈 제안 (총괄 검수 후 `agent_workspace/memory/qa-reviewer.md` 반영 후보)

1. **함정**: 좌표 변환/정렬 로직은 테스트가 초록이어도 **정방 격자·무회전 타깃만 골라 검증**하고 있을 수 있다. 대칭성이 높은 입력에서는 틀린 합성도 정답과 일치한다.
   **올바른 방법**: 변환 검수는 케이스 몇 개가 아니라 **(회전 × 면 × 격자비) 전수 행렬을 독립 정답 함수와 대조**한다. 정답은 "정방향 사상 후 역사상"처럼 **검수자가 별도로 구성**해야 하며, 구현이 쓰는 함수를 그대로 정답으로 쓰면 아무것도 검증되지 않는다.
2. **함정**: 한 결함 계열(유령 행·잠금 우회)을 한 테이블/한 입력에서 고치면 닫혔다고 읽힌다 — 같은 계열의 **형제 테이블·형제 입력**이 그대로 남는다(DOE는 prune했으나 DOE-layer는 안 함, 맵 키는 잠갔으나 재렌더 경로는 안 막음).
   **올바른 방법**: 수정 확인 시 "이 수정이 **적용되지 않은 형제**는 무엇인가"를 반드시 한 줄 적고, 그 형제를 직접 재현해 본다.
3. **함정**: "하드코딩 제거 → config 선언으로 이관"은 설계상 개선이지만, **config 기본값이 기존 동작과 다르면 조용한 회귀**다. 특히 서버 재기동 전 구간과 `.sample`로 부트스트랩한 신규 환경에서 갈린다.
   **올바른 방법**: 기본값 이관 검수는 ①코드 기본값 ②`.sample` ③라이브 config ④API 미지원(404) 폴백 **네 값을 표로 나열**하고 각각이 이전 동작과 같은지 대조한다.
4. **함정**: 새 API가 임의 테이블을 조회하도록 설계되면(범용 인프라), **인덱스 규율이 config 작성자에게 조용히 전가**된다 — 코드 리뷰에서는 보이지 않는다.
   **올바른 방법**: 범용 조회 API는 config에 선언된 **모든 바인딩 키에 대해 `EXPLAIN`을 실제로 돌려** 본다. 선언 시점에 인덱스 확인을 강제하는 절차가 없으면 그것 자체가 결함이다.
5. **함정**: 산출 모델의 전제가 깨졌다는 **명백한 증거(음수·total 0인데 소비 있음)** 를 상태 문자열 기반 신뢰도 판정이 놓친다 — 문자열은 "연결됨"이라고 말한다.
   **올바른 방법**: 신뢰도 판정에 **값의 불변식**(비음수, 부분합 ≤ 전체)을 반드시 함께 넣는다. 메타데이터가 정상이어도 값이 불가능하면 그 값은 신뢰 불가다.
