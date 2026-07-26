# QA 적대적 검수 — Universal Transfer Plan M2 (서버부 + 클라부 합본)

- 검수: qa-reviewer (2026-07-26) · 대상: 현재 working tree 미커밋 변경 전체 · 병합 전 최종 검수
- 대조 산출물: `agent_workspace/reports/Server_transfer_plan_m2_report.md`, `Client_transfer_plan_m2_report.md`
- 실행 환경: conda `assy_manager`, `PYTHONIOENCODING=utf-8`. 라이브 DB는 **SELECT 전용**. 시드 삽입 **없음**(정리 대상 0건).

---

## 1. 판정: **NO-GO** (분할 병합 시 — 서버부만 **GO-WITH-FIXES**)

- **서버부: GO-WITH-FIXES.** 핵심 도메인 로직(가용 합집합 의미론, fail 투영, align)은 **원시 SQL 대조로 전항 실증 일치**하고 M1 계약도 물리적으로 불변이다. 역할 강등 시 `remaining`이 조용히 과대 산출되는 경로 3종(F1)이 있으나, 최소한 `sources` 문자열에는 흔적이 남는다.
- **클라부: NO-GO.** 서버가 남긴 그 유일한 흔적을 **클라가 지운다**(C1). 게다가 검증 실패를 **"서버 검증 경고 없음 ✓" 초록으로 뒤집고**(C2), `stage_unknown`(=검증 통째 스킵)일 때도 자체 초록 배지 "수량 부족 0"을 그대로 띄운다(C3). 삭제·개명한 DOE가 서버에 영구 잔존해 계획 저장소를 오염시키고(C4), 맵 키 입력이 잠기지 않아 **타 계획의 셀 전량이 삭제될 수 있다**(C5).

즉 합본을 그대로 병합하면 **사용자가 보는 화면이 "이상 없음"인데 실제 수치는 틀린** 상태가 성립한다. 핵심가치 #3("빠르지만 가끔 조용히 안 맞음"은 "느리지만 항상 맞음"보다 나쁘다)의 정면 위반이며, 이것이 NO-GO의 유일한 근거다. 기능 구조·계약 준수·테스트 품질 자체는 우수하므로 **§7 필수 항목 수정 후 재검수하면 빠르게 GO 가능**하다.

> **판정 주의**: 클라 검수 보조가 최우선 블로커로 든 "`limit=2000` + `replace_map` 데이터 소실"은 **본 변경분이 만든 회귀가 아니다** — `git show HEAD:client2/src/map_editor.js`의 2144행(`limit=2000`)·2668행(`replace_map: true`)에 이미 존재하는 **기존 시스템 결함**이다(§2 C6). 마찬가지로 `CURRENT_USER` 빌드 시점 고정도 `config.js`/`vite.config.js` 무수정 = 기존 결함이다. 회귀와 기존 결함을 섞지 않기 위해 분리 표기했다.

---

## 2. 확인된 결함

### [높음] F1 — 역할 강등 시 `remaining`이 조용히 과대 산출된다 (응답 `warnings` 비어 있음)

`server/transfer_plan.py:470-476`, `404-468`

`_summarize_inline`의 `warnings_out`에는 **`_collect_history`의 이력 경고만** 들어간다(`556-559`). 소스 역할이 무너져 fail 집계가 0이 되는 경로 어디에도 경고가 추가되지 않는다. 라이브 실측(TAPE-A/01, 정답 `remaining=209`):

| 시나리오 | `sources` 표기 | `fail_breakdown` | **`remaining`** | `warnings` |
|---|---|---|---|---|
| 정상 | 전부 connected | defect 30 / eds 20 | **209** | `[]` |
| `origin_log` 미해석 | `defect/eds_fail: "unavailable(origin_missing)"` | 0 / 0 | **256** (+47) | **`[]`** |
| align grid meta 부재 | `eds_fail: "connected(align_unavailable)"` | 30 / **0** | **226** (+17) | **`[]`** |
| fail 원천 1종 테이블 파손 | `defect: "missing"` | **0** / 20 | **236** (+27) | **`[]`** |

**실패 시나리오**: `wafer_map_metadata`에 특정 코어의 eds 격자 메타가 누락된다(신규 코어 온보딩 중 흔함) → 엔진은 `connected(align_unavailable)`을 `sources`에만 적고 eds fail 20칩을 **0으로 집계** → `remaining` 209→226 → 계획자가 226칩을 배정 → 실투입에서 17칩 부족.

**안전망도 같이 무너진다**: `validate_plan`의 `qty_shortage`는 `available = summary.chips.remaining`(`transfer_plan.py:790`)을 그대로 쓰고, `source_fail_chips`는 `fail_breakdown`(`800-802`)을 쓴다. 둘 다 오염된 값이므로 **부족 경고가 발화하지 않는다**. 즉 조용한 과대 산출이 검증 단계까지 그대로 통과한다.

**더 나쁜 점 — 테스트가 이 동작을 정답으로 고정했다**: `server/tests/test_transfer_plan.py:481` `assert body["chips"]["remaining"] == 5` (origin_log 파손 시. origin 정상이면 정답은 2). 경고 부재를 검증하는 assert는 없다. 후속 검수자가 초록불을 보고 안전하다고 오판한다.

**권장 조치**: `_summarize_inline`이 `statuses` 값 중 `missing` / `unavailable(` / `align_unavailable` / `area_only`를 스캔해 `warnings_out`에 `{"type": "source_degraded", "role": ..., "status": ..., "detail": "... fail 집계 누락 — remaining이 과대일 수 있음"}`을 추가하고, 응답 최상위에 `chips.remaining_reliable: false` 같은 불리언 플래그를 둘 것. `validate_plan`은 이 플래그가 false면 `qty_shortage` 대신 `availability_unreliable` 경고를 내야 한다.

---

### [높음] F2 — 하드캡 절단이 `sources` 전부 `connected` 상태로 조용히 오답을 낸다

`server/transfer_plan.py:374-376`(origin_log), `209-216`(`_fetch_pairs`), `509-511`·`549`(`MAX_BY_CORE`)

캡에 걸려도 로그 한 줄(`logger.warning`)만 남고 **응답에는 어떤 흔적도 없다**. `total`은 `count()`라 캡의 영향을 받지 않는데(`335`) `origin_rows`만 잘리므로 **분자와 분모가 서로 다른 모집단**이 된다.

라이브 실측(`MAX_ORIGIN_POINTS`를 100으로 낮춰 재현, 실제 테이프 256칩):

```
sources : {"total_chips":"connected","origin_log":"connected","defect":"connected","eds_fail":"connected(aligned:180)"}
chips   : {"total": 256, "fail_breakdown": {"defect": 16, "eds_fail": 8}, "remaining": 235}
warnings: []          by_core: 2개 → 1개 (코어 하나가 통째로 사라짐)
```

정답(209)과 26칩 차이인데 응답만 보면 **정상 응답과 완전히 구별 불가**하다. `by_core`도 2코어 → 1코어로 줄었는데 마커·경고 없음.

**실패 시나리오**: `transfer_log` 역할은 `_fetch_pairs(..., cap=MAX_ORIGIN_POINTS)`(`352-353`)로 `bonding_log`(운영 규모 수백만 행)를 친다. config가 이 역할을 (lot, slot) 카디널리티가 낮은 테이블에 바인딩하는 순간 — 또는 단순히 대형 웨이퍼/재배정 이력이 쌓이는 순간 — 10만 행을 넘겨 조용히 절단된다. `MAX_BY_CORE=500` 절단도 마찬가지이며 area_map 경로(`549`)는 **로그 경고조차 없다**.

**권장 조치**: 캡 도달 시 응답에 `truncated: {role: cap}`을 싣고 `warnings`에 항목 추가. 최소한 `by_core` 절단은 `by_core_truncated: true`로 표기. 그리고 `sum(by_core.total)`이 `chips.total`과 어긋날 수 있음을 계약에 명시.

---

### [중] F3 — `total`은 행 수, `blocked`는 distinct 칩 → 중복 행에서 `remaining` 과대

`server/transfer_plan.py:335` vs `471-474`, `486-499`

- `total = db.query(model).filter(...).count()` — **행 수**
- `transferred` = `_fetch_pairs(..., distinct=True)` — **distinct 칩**
- `remaining = total - len(fail_union | used_set)` — 분모는 행 수, 감산항은 distinct 집합

`dt_log`의 business_key는 `dt_id`(단일)이고, 라이브 `pg_indexes` 실측 결과 **`(tape_lot, tape_slot, tx, ty)`에 유니크 제약이 없다**. 즉 같은 테이프 좌표에 대한 2번째 DT 이벤트(재작업·정정 기록·인제션 중복)가 정상적으로 삽입된다.

**실패 시나리오**: TAPE-A/01의 (tx=5, ty=5)에 재전사 기록이 1행 추가된다 → `total` 256→257, `fail_union|used_set`은 집합이라 불변 → `remaining` 209→**210**(존재하지 않는 유령 칩 1개). `by_core.total`도 `a["total"] += 1`(`491`)이라 함께 부풀고, 그 칩이 fail이면 `fail`도 2로 세어 `by_core`가 자기모순(`total 129, fail 30, remaining 99`)에 빠진다.

**권장 조치**: `total_chips` 역할도 좌표가 바인딩돼 있으면 `distinct (x,y)`로 세거나, `origin_rows`를 `(tx,ty)` 기준으로 dedup한 뒤 `by_core`를 집계할 것. 최소한 계약 문서에 "칩당 1행 유일성은 config 작성자 책임"을 명시하고 `dt_log`에 유니크 인덱스를 추가할 것.

---

### [중] F4 — validate: 같은 소스를 공유하는 복수 DOE의 **합산 초과배정**을 검출하지 못한다

`server/transfer_plan.py:751-798`

`_get_summary`는 (lot, slot)당 결과를 캐시할 뿐이고, `qty_shortage` 비교(`789-791`)는 **DOE마다 독립적으로** `required > available`을 본다. 여러 DOE가 같은 소스를 나눠 쓰는 것이 DOE 계획의 정상 형태인데, 그 합이 가용을 넘는지는 아무도 보지 않는다.

**실패 시나리오** (TAPE-A/01, 실측 가용 209):
- DOE-A: 칩 100 × 층 1 × 개당 1 = 필요 100 ≤ 209 → 경고 없음
- DOE-B: 칩 150 × 층 1 × 개당 1 = 필요 150 ≤ 209 → 경고 없음
- 합계 250 > 209 → **41칩 초과배정인데 `qty_shortage` 0건**

수량 검증은 validate의 존재 이유에 해당하는 검사인데 가장 흔한 초과 형태를 놓친다. 라이브 `TP-SMOKE-1`이 우연히 단일 DOE 초과(300 > 209)만 만들어 발화했기 때문에 서버부 §8-bis-3 스모크에서 드러나지 않았다.

**권장 조치**: DOE 루프를 (source_lot, source_slot)별로 `required` 누적 → 소스 단위 합계 대 `available` 비교 경고(`WARN_SOURCE_OVERALLOCATED`) 추가.

---

### [중] F5 — 총괄이 추가한 `total_layers`를 서버·클라 **양쪽 다 쓰지 않는다** (층 커버리지 검증이 상단 결손을 원리적으로 못 잡음)

`server/transfer_plan.py:732-742`, `server/config/transfer_plan_config.json`(plan_store.plan.columns), `client2/src/transfer_plan.js:233`

- 라이브 `table_config.json`의 `transfer_plan`에 `total_layers: "number"`가 있고 DB 컬럼도 실재(`TP-SMOKE-1`은 NULL).
- 그러나 `transfer_plan_config.json`의 `plan_store.plan.columns`에 `total_layers` 매핑이 **없고**, `validate_plan`은 이 값을 읽지 않는다.
- 커버리지 계산은 `max_layer = max(covered)`(`736`) — **선언된 DOE 자신에서 최댓값을 유도**한다. 라이브 경고 "1..3 중 [2]층"이 그 증거.
- 클라는 `total_layers`를 초안 직렬화(`transfer_plan.js:233`)에만 담고 서버 컬럼에 쓰지 않는다(클라 보고서 §5-2가 "컬럼 부재"라 적었는데 총괄이 이후 추가 — **보고서와 현 상태가 어긋나 있다**).

**실패 시나리오**: 사용자가 총 5층 계획을 세우고 DOE는 1~3층만 배정한다 → `covered = {1,2,3}`, `max_layer = 3`, `missing = []` → **`layer_coverage_gap` 미발화**. 4·5층이 통째로 비었는데 "층 커버리지 정상"으로 보인다. 이 검사는 구조적으로 **내부 구멍만** 잡고 상단 결손은 절대 못 잡는다.

**권장 조치**: `plan_store.plan.columns`에 `total_layers`를 매핑하고 `max_layer = max(declared_total_layers, max(covered))`로 계산. 클라는 저장 payload에 `total_layers`를 포함. (셋 중 하나라도 빠지면 이 컬럼은 계속 죽은 컬럼이다.)

---

### [중] F6 — align 변환에 `dst_grid`를 넘기지 않아 M1이 갖는 프레임 정합 검증이 M2에서 소실

`server/transfer_plan.py:243` — `bonding_plan.make_align_transform(align, src_grid)` (dst_grid 생략)
대조: `server/bonding_plan.py:409` — `make_align_transform(align, src_grid, canonical_grid)`

`make_align_transform`(`bonding_plan.py:165-185`)에서 `dst_grid`가 없으면 ①`dst_start_x/y`가 **소스 자신의 start로 폴백**하고 ②치수 불일치 `ValueError` 가드(`181-185`)가 **통째로 건너뛰어진다**.

**실패 시나리오**: 어떤 코어의 `eds_fail_map` 격자 메타가 `grid_start_x: 0`으로 등록되고 canonical(core) 프레임은 `grid_start_x: 1`이다 → 변환 결과가 양축 1칸 어긋난 좌표를 canonical로 반환 → 투영 조인이 대부분 빗나가 fail이 급감(최악 0) → `sources`에는 정상인 `connected(aligned:180)`이 찍힌다. F1과 결합하면 경고 한 줄 없이 `remaining`만 부풀어 오른다. 비정방 격자(40×30을 90도 회전)에서도 M1은 ValueError로 막지만 M2는 조용히 통과한다.

**권장 조치**: `_canonical_fail_set`에서 canonical 프레임(align 미선언 fail 원천 또는 `total_chips`)의 grid meta를 1회 로드해 `dst_grid`로 전달.

---

### [중] F7 — fail 투영이 **코어당 N+1 쿼리**이며, 보고서의 "선형화" 주장은 메모리 루프에만 해당

`server/transfer_plan.py:445-446`(코어 루프) → `_canonical_fail_set`(`219-253`)이 코어마다 grid meta 1회 + fail 좌표 1회 조회

실측: 코어 2장 / fail 원천 2종 테이프 1건 요청에 **SQL 10문**. 스케일:
- `MAX_BY_CORE=500` 코어 × fail 2종 × 2쿼리 ≈ **2,000 왕복 / 1 요청**
- `validate_plan`은 distinct 소스마다 `_get_summary`를 부른다(`751-756`) → 소스 20종 계획이면 **약 40,000 왕복 / 1 HTTP 요청**

같은 코어의 grid meta가 fail 원천마다 재조회되고(캐시 없음), 라우트가 동기 `def`라 워커 스레드를 그동안 점유한다. 1,000만 행 규율의 실제 병목은 인덱스가 아니라 **왕복 수**다.

서버 보고서 §13 교훈 3은 "조인 키별 버킷 인덱스를 1회 구축해 선형화"라고 적었는데, 그것은 in-memory 이중 루프만 해결한 것이고 **쿼리 수는 여전히 O(코어수 × fail원천수)**다. 보고서 서술이 실제보다 강하다.

**권장 조치**: fail 원천별로 `(lot, slot) IN (involved_cores)` 단일 쿼리로 묶어 코어별 set을 한 번에 구성 + grid meta는 `(target_table, map_id) IN (...)` 배치 조회 후 dict 캐시.

---

### [중] F8 — 클라: 미인식 stage를 **말없이 첫 stage로 재배정**한다

`client2/src/transfer_plan.js:211-216`

```js
if (!S.stages.some(x => x.id === S.stage)) {
  const alias = LEGACY_STAGE_ALIASES[S.stage];
  S.stage = (alias && S.stages.some(x => x.id === alias)) ? alias : S.stages[0].id;
}
```

미선언 값이 서버로 나가는 것을 막는다는 목적 자체는 옳고, `stage="bonding_plan"` 사고의 재발을 실제로 봉쇄한다(라이브 DB에서 해당 행은 이미 정리되어 잔여 0 — 실측 확인). 다만 **사용자 고지가 전혀 없다**.

**실패 시나리오**: `/stages`가 실패해 `BUILTIN_STAGES`(dt/bonding 하드코딩, `48-53`)로 폴백한 상태에서, config가 신규 stage `probe`를 선언하고 사용자 초안이 `probe`였다면 → 조용히 `dt`로 바뀌고, `plan_id`가 `<stage>__<lot>_<slot>` 규칙(클라 자체 결정)이라 **plan_id까지 달라져 별개 계획으로 저장**된다. 원본 계획은 화면에서 사라진 것처럼 보인다.

**권장 조치**: 강등 시 사용자에게 명시 배너("계획의 stage 'probe'는 서버 미선언 — 'dt'로 표시 중, 저장하면 stage가 바뀝니다"). 그리고 `/stages` 실패 상태에서는 저장 자체를 막는 편이 안전하다.

---

### [높음] C1 — 클라가 `sources` 상태 5종을 **전부 "미연결" 한 덩어리로 뭉갠다** (F1의 유일한 신호 소멸 + 정상 상태 오보)

`client2/src/transfer_plan.js:1046-1050`

```js
`<span class="bp-src ${s.status !== 'connected' ? 'missing' : ''}">${esc(s.role)}${s.status !== 'connected' ? ' · 미연결' : ''}</span>`
```

`status` 원문이 화면에도 `title` 속성에도 남지 않는다. 결과:

| 서버 status | 실제 의미 | 화면 표기 |
|---|---|---|
| `missing` | 미연결 | 미연결 |
| `unavailable(origin_missing)` | **fail 집계 누락 — remaining 과대** | 미연결 |
| `connected(align_unavailable)` | **fail 집계 누락 — remaining 과대** | 미연결 |
| `connected(area_only)` | 연결됨(by_core만 강등) | **미연결 (오보)** |
| `connected(aligned:180)` | **정상 연결 + align 적용** | **미연결 (오보)** |

**실패 시나리오**: 라이브 TAPE-A/01의 `eds_fail`은 **정상**(`connected(aligned:180)`)인데 화면엔 "eds_fail · 미연결"로 뜬다 → 사용자가 상시 오탐에 둔감해진다 → 진짜 `align_unavailable`(remaining 17칩 과대)이 발생해도 똑같이 보이므로 **구별 불가**. F1이 남긴 유일한 신호가 여기서 소멸한다.

전파 범위: `renderStageInfo()` `:541-543` 동일 코드, `doeStats().missing` `:491-493`이 같은 필터를 써서 DOE 행에 `"역할 미연결"` 경고칩(`:706`)까지 오탐으로 띄운다.

**권장**: `esc(s.status)`를 배지 `title`(최소) 또는 텍스트에 노출하고, `connected(` 접두 상태는 `missing` 클래스에서 제외. `unavailable(`/`align_unavailable`은 **별도 경고 등급**으로 격상.

---

### [높음] C2 — validate 응답 파싱 실패가 **"서버 검증 경고 없음 ✓"** 초록으로 뒤집힌다

`client2/src/transfer_plan.js:664` → `:665-666` → `:642`

```js
const data = await res.json().catch(() => null);   // :664
```
`data`가 null이면 `warns = []`가 되고, `:642`가 경고 0건 = **"서버 검증 경고 없음 ✓"** 를 렌더한다.

**실패 시나리오**: 프록시/게이트웨이가 `/api/transfer-plan/validate`에 HTML 오류 페이지를 200으로 반환하거나 응답이 잘린다 → 파싱 실패 → 사용자는 **초록 체크마크**를 보고 계획을 확정한다. 실제로는 검증이 한 번도 수행되지 않았다.

부수 결함: `isPlainNotFound` `:370`이 `detail === 'Not Found'`만 "미지원"으로 판정하므로, **미저장 계획의 정상적인 404**(`plan 'X' not found` — 서버 `transfer_plan.py:641`이 의도적으로 내는 detail)가 `:669`에서 붉은 `"validate 조회 실패 (HTTP 404)"`로 렌더된다. 초안 로드마다 발생(`:1629`). 서버가 준 detail은 버려진다.

**권장**: `.catch(() => null)` 제거 → 파싱 실패를 `warnings: [{type:'client_parse_error'}]`로 승격. 404는 detail 문자열로 "미저장 계획" / "미지원"을 구분.

---

### [높음] C3 — `stage_unknown`이 목록에 묻히고, 클라 자체 초록 배지가 **거짓 안심**을 준다

`client2/src/transfer_plan.js:638-642`(경고 렌더), `:625-630`(상단 배지)

```js
warns.map(w => `<span>⚠️ ${esc(typeof w === 'string' ? w : JSON.stringify(w))}</span>`)
```

서버 경고는 `{type, detail}` 객체인데 **`JSON.stringify` 원문 덤프**가 나열된다. `w.type`별 분기·강조·정렬이 전무해, "소스 가용 검증이 통째로 스킵됨"을 뜻하는 `stage_unknown`이 `doe_value_unpainted` 같은 경미 경고와 시각적으로 동일하다.

**더 나쁜 점**: 상단 배지 4종(`:625-630`)은 **클라 자체 계산**이라 `stage_unknown`으로 서버 검증이 전부 스킵된 상태에서도 초록 **"수량 부족 0 / FAIL 이력 0"** 을 그대로 표시한다.

**실패 시나리오**: config에 신규 stage가 선언되기 전 계획을 만든다 → 서버는 `stage_unknown` 하나만 내고 수량·fail 검증을 건너뛴다(`transfer_plan.py:658-665`, `758`) → 화면엔 JSON 덤프 한 줄 + **초록 "수량 부족 0"** → 사용자는 검증 통과로 읽는다. 총괄이 지적한 "조용한 통과 오인" 위험이 **실제로 성립한다**.

**권장**: `w.type === 'stage_unknown'`(및 `source_unresolved`)이면 상단 전용 배너로 격상하고, 그 상태에서는 자체 초록 배지를 "검증 스킵"으로 무력화.

---

### [높음] C4 — DOE 삭제·개명이 서버에 전파되지 않아 **유령 DOE가 계획 저장소에 영구 잔존**

`client2/src/transfer_plan.js:821-823`(삭제 = `S.does.splice()` 로컬만), `:783-801`(개명), `savePlanToServer` `:1435-1476`(업서트 `PUT .../updates`만, DELETE 경로 없음)

- DOE 삭제: 로컬 배열에서만 제거 → `transfer_plan_doe`의 해당 행은 **그대로 남는다**.
- DOE value 개명: `doe_key = plan_id|newValue` **새 행**이 생기고 구 행과 공존한다(복합 bk가 value를 포함하므로 필연).

**실패 시나리오**: 사용자가 DOE `D1`을 만들어 저장 → 이름을 `D1-rev2`로 바꿔 재저장 → 서버에는 `PLAN|D1`과 `PLAN|D1-rev2` **두 행**. 이후 `validate`가 `PLAN|D1`에 대해 `doe_value_unpainted`(맵에 없음) + `source_fail_chips` + 잘못된 `qty_shortage`를 영구히 발화한다. 사용자는 화면에 없는 DOE에 대한 경고를 지울 방법이 없다. 삭제도 동일.

이는 §4 F4(소스 합산 미검출)와 결합해 **validate 출력을 신뢰 불가**로 만든다.

**권장**: 저장 시 서버의 `plan_id` 하위 DOE 목록을 조회해 diff → 제거분에 `POST /tables/transfer_plan_doe/rows/batch_delete`. 또는 서버에 계획 단위 replace 경로 신설.

---

### [높음] C5 — 페인팅 모드에서 **맵 키(`plan_id`) 입력이 잠기지 않아** 타 계획 셀 전량 삭제 가능

`client2/src/map_editor.js:3439-3440`(주입), `:3473-3474`(잠금 대상에서 누락), `server/database/crud.py:960-1009`

```js
const planInput = document.getElementById(`meta-input-${planCol}`);
if (planInput) planInput.value = opts.planId;      // 평범한 편집 가능 input — readOnly 미설정
```

페인팅 모드는 `tableSelect`(`:3473`)와 `btnLoadMap`(`:3474`)은 `disabled` 처리하면서 **정작 파괴력이 가장 큰 맵 키 입력은 열어둔다**. 이 값은 `pushMapData:2522-2534`가 수집해 push payload에 싣고, 서버 `crud.py:971-1009`가 `map_key_columns = ["plan_id"]` 기준으로 **그 plan_id의 전 행 + CellSource + CellOverwrite를 삭제 후 재기록**한다(`replace_map: true`, `map_editor.js:2675`).

**실패 시나리오**: 사용자가 계획 `bonding__TAPE-A_01`을 페인팅하다 메타 입력란의 plan_id를 실수로 `bonding__TAPE-A_02`로 고친다(자동완성·오타·복붙) → ⚡Push → **`TAPE-A_02` 계획의 페인팅 전량과 셀 이력이 삭제**되고 현재 그리드 내용으로 대체된다. 확인 다이얼로그(`:2631`)는 **테이블명만 말하고 plan_id를 표시하지 않아** 마지막 방어선도 없다.

**권장**: 페인팅 모드 동안 `planInput.readOnly = true`(+ 시각적 잠금) — `tableSelect`와 동일 대우. push 확인문에 대상 `plan_id`를 명시.

---

### [높음/기존] C6 — `limit=2000` 로드 + `replace_map: true` push = 초과분 영구 삭제 (**M2 회귀 아님**)

`client2/src/map_editor.js:3254`(신규 계획맵 로드, limit 2000) → `:3466` `applyCellsToGrid` → `:2675` `replace_map: true` → `server/database/crud.py:989-1009` 전 행 삭제 후 재삽입

**메커니즘 확인**: `replace_map`은 `map_key_columns` 일치 행을 **전량 삭제**하고 그리드 내용만 재기록한다. 그리드는 2000행까지만 채워졌고, 응답의 `total`은 어디서도 검사하지 않는다(서버 `main.py:958`은 `limit` 상한 없음). → **2001번째 이후 셀이 셀 이력·오버라이트와 함께 영구 소실.**

**단, 이것은 기존 결함이다**: `git show HEAD:client2/src/map_editor.js` 2144행에 `limit=2000`, 2668행에 `replace_map: true`가 **이미 존재**한다 — `dt_map`/`bonding_map` 등 모든 맵이 동일 위험에 노출돼 있었다. M2는 같은 안티패턴을 `transfer_plan_map`용 신규 경로(`:3254`)에 **복제**했을 뿐 새로 만들지 않았다.

**현실 규모**: 현행 프리셋은 TAPE 20×20=400, CORE 40×40=1600, BASE 29×25=725로 전부 2000 미만이라 **당장 발화하지 않는다**. 50×50 이상 규격이 등장하는 순간 터진다.

**권장**: 별건 시스템 티켓으로 승격(전 맵 공통). 응답 `total > 반환행수`면 push 봉인. M2 범위에서는 최소한 `:3254`에 동일 가드를 넣을 것.

### [중] C7 — `plan_id` 합성 시 `|` → `_` 치환이 **서로 다른 계획을 조용히 병합**한다

`client2/src/transfer_plan.js:127-130`, `:1426`

```js
const t = S.target.trim().replace(/\|/g, '_');
return `${S.stage}__${t}`;
```

`transfer_plan_map`의 복합 bk가 `plan_id|x|y`라 `|`를 못 쓰는 것은 타당하나, target `"A|B"`와 `"A_B"`가 **동일 plan_id** `bonding__A_B`로 합쳐진다. 그런데 `target_lot`/`target_slot`은 `parseSource(target)` `:1426`이 **원본 `|` 기준**으로 분할하므로, 같은 plan_id 행에 서로 다른 `target_lot`/`target_slot`이 덮어씌워진다.

**총괄 판단 요청 ⓐ에 대한 답**: 서버는 `plan_id`를 **파싱하지 않는다**(`transfer_plan.py:639`는 컬럼 equals 조회, `:647`은 `stage` 컬럼을 별도로 읽음). 따라서 클라 자체 규칙이라는 사실 자체는 **계약 위반이 아니고 위험도 낮다**. 실제 위험은 위 충돌과, `plan_id`가 stage를 접두로 포함하는 탓에 **stage 강등(C8)이 일어나면 plan_id까지 바뀌어 별개 계획이 되는** 결합 효과다. DOE bk(`:1451` `` `${planId}|${value}` ``)는 value의 `|`를 전혀 이스케이프하지 않아 역파싱 불가한 bk가 생길 수 있다(입력 검증은 중복/공백만, `:783-792`).

### [중] C8 — `fetchStages()`를 await하지 않아 stage 가드가 저장 경로보다 늦게 선다

`client2/src/transfer_plan.js:1930-1944`. `S.stage = LEGACY_STAGE_ALIASES[last.stage] || last.stage`(`:1935`)로 localStorage 값을 **원본 그대로** 세팅하고 패널 버튼 바인딩·`renderAll()` 후 `fetchStages()`를 **await 없이** 호출(`:1944`). 별칭에 없는 미지 stage가 초안에 남아 있으면 fetch 왕복(수십~수백 ms) 동안 [서버 저장]을 누른 값이 그대로 나간다 — `:213`의 방어벽이 저장 경로보다 늦게 선다. 좁은 창이지만 `stage="bonding_plan"` 사고와 정확히 같은 형태의 재발 경로다. 아울러 F8(강등 무고지)과 결합한다.

### [중] C9 — 계획 헤더/DOE 부분 실패 시 서버·화면 상태 분기

`client2/src/transfer_plan.js:1475-1478`. header PUT → DOE PUT 순차 실행. DOE PUT이 실패하면 header는 이미 `status='confirmed'`로 커밋됐는데 `S.status = nextStatus`(`:1478`)는 실행되지 않아 **서버=확정 / 화면=draft**로 갈라진다. 롤백·재조회 없음. 사용자는 draft로 보고 다시 확정을 누르며, 그 사이 `validate`는 DOE 없는 확정 계획을 본다.

### [중] C10 — 페인팅 "취소" 토스트가 거짓 안내 (이미 push된 경우)

`client2/src/map_editor.js:3486-3509`, `:2694`, `client2/src/transfer_plan.js:1381`. 페인팅 중 ⚡Push를 누르면 `planPaint.pushed = true`로 **서버 기록이 이미 완료**된다. 그 뒤 [취소]를 누르면 `finishPlanPaint(true)`가 `pushed` 플래그를 onCancel에 넘기지 않아 `'페인팅을 취소했습니다 (맵 변경 미반영).'`을 띄운다. **서버엔 반영돼 있고 롤백도 없다.** 사용자는 되돌려졌다고 믿는다.

### [중] C11 — 페인팅 셀 수 대조가 층수를 빼먹는다 (다층 stage 상시 오탐)

`client2/src/transfer_plan.js:499` `paintMismatch = (painted !== qty)`. 바로 위 `:481`의 소요는 `need = qty × units(층수)`인데 페인팅 대조만 `qty_per_unit`과 직접 비교한다. bonding stage(다층)에서는 `:1080`/`:706`이 **항상** 불일치 경고를 띄우고, DT(units=1)에서만 우연히 맞는다. C1과 함께 "상시 켜진 경고" 를 늘려 진짜 경고를 가린다.

### [낮음/기존] C12 — `CURRENT_USER`가 빌드 시점에 고정되어 감사 추적이 무의미

`client2/src/config.js:4` + `client2/vite.config.js:7-8`. `VITE_USER`가 **빌드 머신의 `USERNAME`**으로 치환되며, 실제 번들 `dist/assets/utils-DqWd5E8W.js`에서 문자열 `kk980` 인라인 확인. 누가 저장하든 `cell_overwrites.updated_by`에 동일 값이 찍힌다.

**F11의 결론을 보강한다**: `updated_by`가 null이라는 클라 보고서 §5-4의 의심은 **기각**(라이브에 `tp_smoke` 등 값이 실재)이나, 웹 클라 경유 저장은 전부 한 사람으로 기록된다. **`config.js`/`vite.config.js` 모두 본 diff에서 무수정 = 기존 결함**이며 M2 회귀가 아니다. 별건 티켓.

### [낮음] C13 — 서버 로드 실패가 조용한 백지화로 끝난다

`client2/src/transfer_plan.js:1515`(무가드 `.json()`) → catch `:1586` → `return 'error'` → `activatePlan` `:1616-1618`이 `'error'`를 `'none'`과 **동일 취급** → 토스트·배너 없이 초안 폴백, 초안도 없으면 `resetPlanState()` `:1641`로 패널 백지화. 저장해 둔 계획이 사라진 것처럼 보인다.

### [낮음] C14 — 응답 절단을 어느 호출도 사용자에게 알리지 않는다

`transfer_plan.js`의 모든 fetch에 limit은 있으나(`:1506` 1 / `:1526` 500 / `:1560` 500 / `:1296` 2000 / `:1692` 15) **어느 것도 응답 `total`을 검사하지 않는다**. DOE 500 절단은 서버 `MAX_DOE_PER_PLAN=500`과 값은 같지만 정합 보장이 없고(서버는 501행을 읽어 초과 판정), 초과 시 화면에서 DOE가 조용히 사라진다. 서버 `main.py:958`이 `limit` 상한을 두지 않으므로 클라가 유일한 방어선인데 그 방어선이 침묵한다.

---

### [낮음] F9 — `painted` group-by에 ORDER BY 없는 LIMIT (비결정 절단)

`server/transfer_plan.py:687-690`. `group_by(val).limit(MAX_PLAN_VALUES)`에 정렬이 없어 distinct DOE 값이 1,000을 넘으면 **어느 1,000개가 남는지 실행마다 달라진다** → `undefined_doe_value`/`doe_value_unpainted` 경고가 새로고침마다 바뀐다. 현실 규모에선 도달하기 어려우나 결정성 원칙 위반.

### [낮음] F10 — `qty_per_unit = 0`이 1로 승격

`server/transfer_plan.py:780` `qty = _num(..., default=1) or 1`. 명시적 0(=이 DOE는 소비 없음)이 1로 바뀌어 `required`가 부풀고 오탐 `qty_shortage`가 난다. `None`과 `0`을 구분할 것.

### [낮음] F11 — `transfer_plan.updated_by` 컬럼은 항상 NULL이지만 **감사 추적 결함은 아니다** (총괄 판단 요청 ⓒ에 대한 답)

라이브 실측: `cell_overwrites`에 `transfer_plan` / `_doe` / `_map` 전 컬럼의 수정자가 정상 기록돼 있다(예: `('transfer_plan_map', 'val', 'tp_smoke', None, 4)`). **실제 감사 추적은 레이어링 계층이 담당하며 정상 작동한다.** NULL인 것은 `table_config`에 선언된 **업무 컬럼** `updated_by`로, 아무도 쓰지 않는 죽은 컬럼이다.

→ **심각도 낮음.** 다만 "수정자 컬럼인데 항상 비어 있다"는 오해를 부르므로 **채우거나 `table_config`에서 제거**할 것. 클라 보고서 §5-4의 "감사 추적 영향" 우려는 과장이다.

### [낮음] F12 — `GET /tables/{t}/schema`가 미존재 테이블에도 200 반환 (총괄 판단 요청 ⓑ)

`server/main.py:1525-1559`. `crud.TABLE_CONFIG`·`DYNAMIC_TABLES` 어디에도 없으면 `columns = []`가 되지만 그 뒤 시스템 컬럼 5종이 무조건 append되어(`1542-1545`) **항상 200 + 스켈레톤**을 반환한다. 404 경로가 없다.

**본 변경분과 무관한 기존 결함이다**(diff는 `main.py`에 61줄 순수 추가만 했고 이 라우트는 무수정). 클라가 이미 `GET /tables/{t}/data`(404) 게이트로 우회했으므로 M2 병합을 막을 사유는 아니다. → **별건 후속 티켓** 권장(비어 있는 `columns`/`business_key`면 404).

### [낮음] F13 — `transfer_log` 역할에 align 지원이 없다 (M1 승계 한계)

`server/transfer_plan.py:350-353`. `fail_sources`는 프레임 변환을 하는데 `transfer_log`는 raw 좌표로 `used_set`을 만들어 타깃 프레임과 직접 교집합한다. 본딩 장비가 회전된 프레임으로 기록하면 `used_set`이 조용히 빗나가 `transferred`가 과소·`remaining`이 과대가 된다. M1 `used_chips`(`bonding_plan.py:455-460`)와 동일한 한계라 **신규 회귀는 아니다**. 실 운영 데이터 투입 전 프레임 확인 필요.

---

## 3. 반증 시도했으나 안전한 항목

| 가설 | 반증 결과 (안전 근거) |
|---|---|
| 가용 합집합 의미론이 경로마다 다르다 | **안전.** 라이브 원시 SQL 대조 완전 일치: defect 30 / eds(align 180) 20 / **UNION 47** → `remaining = 256 − 47 = 209`, 엔진 동일. `by_core` fail 29+18=47도 합집합과 일치 — 중복 칩 3개 이중 감산 없음 |
| align이 실제로는 무동작이고 수치가 우연히 맞는다 | **안전.** 무변환 대조군 raw SQL = **26**, `(41−x, 41−y)` 역변환 조인 = **20**, 엔진 = **20**. 구현자 주장(20 vs 26) 재현 확인 |
| fail 투영이 코어 프레임/테이프 프레임을 혼동한다 | **안전.** `_canonical_fail_set`은 fail 좌표만 canonical(core)로 사상하고 `origin_log`의 `(ox, oy)`와 비교, 결과는 `(tx, ty)`로 담는다(`452-456`). 프레임이 섞이지 않는다 |
| 미해석 좌표(NULL)에서 과대/과소 산출 | **안전.** `_fetch_pairs`(`216`)·origin_rows(`377-381`)가 NULL 좌표 행을 배제 |
| `by_core` 두 경로 키 집합이 다르다 | **안전.** 라이브 7키 동일 확인 + `test_by_core_key_set_identical_across_paths`가 회귀 고정 |
| `core_id` 형식 차이(`LOT-A\|05` vs `LOT-A_05`)가 클라 오조인 유발 | **안전.** 두 경로는 상호배타이고 클라는 `core_id`를 표시명/그룹 키로만 사용(`by_core_origin` 기반 뱃지 분기). 조인 코드 없음 |
| 클라가 미선언 stage를 서버로 보낼 잔여 경로 | **대체로 안전(고지 부재 F8 / 레이스 C8 제외).** stage 송신 지점은 `transfer_plan.js:1435`(저장)·`:384`(source-summary) 2곳뿐이고 둘 다 `S.stage` 원본. `normalizeStage()`(`:167`)는 서버 값을 변형하지 않는다. **`plan_id`·파일명에서 stage를 유추하는 코드 0건**(`split('__')` 전무). `:213-216` 가드 + 폴백 상수도 `dt`/`bonding`(`:51-52`). 라이브 DB에 미선언 stage 행 **잔여 0** 실측 |
| `stage="bonding_plan"` 오염 행을 누가 만들었나 | **규명됨.** `git show HEAD:client2/src/bonding_plan.js \| grep stage` → **0건** — M1 클라는 `stage` 컬럼을 쓴 적이 없다. 현재 파일이 들고 있는 `LEGACY_STAGE_ALIASES = { dt_plan:'dt', bonding_plan:'bonding' }`(`:56`)가 자백 — **이 미커밋 파일의 이전 리비전**(BUILTIN_STAGES id가 `dt_plan`/`bonding_plan`이던 시점)이 쓴 것. 클라부가 이후 어휘를 교정하고 오염 행 15건을 정리 완료(잔여 0 실측). **단 코드에 기존 행 정정 로직은 없다** — 향후 오염 행이 생기면 수동 정정 필요 |
| 페인팅 push가 **타 맵 테이블**(`dt_map`/`bonding_map`)을 오염시킨다 | **안전.** `selectedTable = PLAN_MAP_TABLE` 강제(`map_editor.js:3436`) + `tableSelect.disabled = true`(`:3473`). `serverMapAvailable === false`면 `btnPushMap.disabled = true`(`:3475-3477`)로 봉인되고, push 트리거는 `:325` 클릭 리스너 **하나뿐**(키보드 단축키·자동저장 없음), 재활성화는 `:2718`/`:3501`뿐이라 봉인이 새지 않는다. (**타 `plan_id` 오염은 열려 있다 — C5**) |
| 계획 맵 로드에 `plan_id` 필터가 없다 | **안전.** `fetchPlanMapData` `map_editor.js:3253` — `{[planCol]: equals planId}` 필터 적용 |
| 페인팅 진입이 기존 편집물을 파괴한다 | **안전.** `snapshotEditorState()` `:3087` → `restoreEditorState()` `:3126`으로 테이블·규격·legend·잠금 전부 원복. 클라부 라이브 검증에서 완료/취소 양쪽 원복 PASS 기록. (진입 확인 프롬프트 부재·`:3129` 드롭다운 잔류는 경미) |
| `bonding_plan.js\|css` 삭제 후 잔존 참조·빌드 누락 | **안전.** `client2/` 전수 검색 결과 `bonding_plan` 히트 4곳 전부 무해(주석 2 + `M1_DRAFT_PREFIX` localStorage 마이그레이션 키 + `LEGACY_STAGE_ALIASES`). `import`/`<script>`/`<link>` 참조 **0건**. `vite.config.js` 엔트리는 html 단위라 수정 불필요. `bonding-plan-root`→`transfer-plan-root`, `btn-bonding-plan`→`btn-transfer-plan` src·dist 양쪽 동기화 |
| 클라 문법 오류 | **안전.** `node --check client2/src/transfer_plan.js` OK, `node --check client2/src/map_editor.js` OK |
| 클라가 `by_core.fail: null`을 0으로 표시 / `core_id`로 조인 | **안전.** `numTd()` `:957-960`이 null → `미상`(0은 정상 `0`). `coreDisplayName()` `:941-948`은 `core_lot`/`core_slot` 우선, 없으면 `core_id` **표시용 폴백**. `by_core` 참조는 `:1119` 1곳뿐이고 조인·파싱·문자열 비교 없음. `by_core_origin`은 `:952-955` **배지 문구 선택에만** 사용(데이터 분기 없음 = 단일 렌더러) — 총괄 계약 그대로 |
| catch-all이 HTML 200을 반환해 클라가 깨진다 | **안전(현행 라우트 한정).** `main.py:3860` catch-all이 `api`/`tables` 접두를 404로 배제하므로 재현되지 않는다. 서버 보고서 §10의 "HTML 200" 경고는 현행 코드에선 성립하지 않는다. 단 프록시 개입 시 C2·C13이 그대로 터진다 |
| 신규 CRUD API 0건 주장이 거짓 | **안전.** `main.py` diff는 GET 3종 + 주석 = 61줄 순수 추가. 계획 저장은 `cell_overwrites`에 기록이 남은 것으로 보아 제네릭 배치 경로 사용 실증 |
| M1 `bonding_plan.py` 수정 / `core-summary` 계약 변경 | **안전.** `git status`상 `bonding_plan.py` **무수정**. `test_m1_core_summary_contract_unchanged` 포함 전 스위트 통과 |
| 라우트가 async 핸들러에서 동기 DB 호출로 이벤트 루프 블로킹 | **안전.** 3종 모두 `def`(sync) — FastAPI가 스레드풀에서 실행. 다만 F7의 왕복 수는 워커 스레드 점유 시간 문제로 남는다 |
| 기동 시 config 손상이 서버를 죽인다 | **안전.** `load_transfer_plan_config`(`69-83`)가 FileNotFoundError·파싱 실패·비-dict 루트를 전부 `{}`로 흡수 |
| 인덱스가 실제 쿼리 식과 불일치(표현식 캐스트) | **안전.** 진입 필터가 전부 컬럼 동치(`cols["lot"] == lot`)이고 `idx_dt_log_tape_lot_slot`·`idx_dt_log_core_lot_slot`·`idx_dt_map_lot_slot`이 라이브 `pg_indexes`에 실재 확인. 계획 3종도 생성됨 |
| 인덱스 셋업 스크립트가 트랜잭션을 오염시킨다 | **안전.** `setup_transfer_plan_indexes.py:37-50` — information_schema 존재 게이트 + 실패 시 즉시 rollback (교훈 준수) |
| 응답에 칩 좌표 목록이 실려 페이로드 폭발 | **안전.** 좌표는 내부 연산에만 쓰이고 응답은 집계·`by_core`(≤500)·`history`(≤50)로 한정 |
| 신규 테스트가 형식적이다 | **안전.** align 무변환 대조군, 합집합 vs 감산식 구분 assert(`remaining == 2`, 감산식이면 1), 두 경로 키 집합 동일성, `by_core` 미동봉 vs 빈 배열 구분 등 실질 경계 검증. **단 F1 지적대로 강등 시 과대 `remaining`을 정답으로 고정한 assert 존재** |
| 테스트 기준선 재현 실패 | **안전.** 직접 실행: **1 failed, 298 passed** — 실패는 기허용 `test_api.py::test_map_presets_api` 1건. 보고서 주장과 일치 |
| dist 자산 해시 불일치(빌드 누락) | **안전.** `dist/map_editor.html`이 참조하는 `map_editor-CpDKxzFD.js` / `map_editor-C_8Nraqu.css`가 신규 파일로 실재. 구 해시 2개는 삭제됨 |

---

## 4. 런타임 검증 필요 (코드만으로 단정 불가)

1. **재기동 후 REST 3종 실응답** — 서버 보고서 §10 체크리스트 1~5 그대로. 특히 `by_core_origin`/`fail: null` 렌더와 `stage_unknown` 미발생 확인. (JSON 가드 자체는 §2 C2·C13으로 코드 판정 완료 — 추가 조사 불요.)
2. **F7 왕복 수의 실측 지연** — 다코어 테이프(수십~수백 코어) 1건에 대한 `/source-summary` p50/p99. 계획 소스 다수인 `/validate`도 함께.
3. **F2 캡 도달 여부** — 운영 `bonding_log`에서 단일 (lot, slot)의 distinct 칩이 10만에 근접하는 조합이 실재하는지.
4. **F3 중복 행 실재 여부** — 운영 DT 로그에 동일 `(tape_lot, tape_slot, tx, ty)` 재작업 기록이 쌓이는 운용인지 (도메인 확인 사항).
5. **C5 수정 후 페인팅 push 재검증** — plan_id 잠금 적용 상태에서 완료/취소 양쪽 원복과 plan_id 파티션 유지 재확인.
6. **M1 초안 마이그레이션 수락 경로** — 클라 보고서 §7-4가 거절 경로만 실검증했다고 자인. 수동 1회 필요.
7. **C6 규모 한계** — 운영에서 단일 계획/맵의 셀 수가 2000을 넘는 규격이 도입될 시점. 넘는 즉시 데이터 소실이 시작되므로 프리셋 확대 전에 반드시 선조치.

---

## 5. 문서 정합 — 불일치·과장

| # | 지적 | 근거 |
|---|---|---|
| D1 | **`docs/architecture/CODE_MAP.md`에 "transfer" 문자열 0건.** 신규 모듈 `server/transfer_plan.py`(823줄)·`client2/src/transfer_plan.js`(1,945줄)가 코드맵에 부재하고, 삭제된 `bonding_plan.js`가 남아 있을 수 있다. StableDevelopmentProtocol의 문서 동기화 규율상 **병합 조건** | `grep -c transfer docs/architecture/CODE_MAP.md` = 0 |
| D2 | **`PROJECT_STATUS.md`가 M2를 "다음 할 일"로 기재**하고 있고, 계획 테이블명을 `bonding_experiment_plan`/`bonding_plan_layer`, 온톨로지를 `ExperimentPlan·PlanLayer·TransferEvent`로 적었다. 실제 구현은 `transfer_plan`/`_doe`/`_map`, `ExperimentPlan·SplitCondition`. **명칭이 전부 대체됨** | `PROJECT_STATUS.md:64` |
| D3 | **서버 보고서 §13 교훈 3 "선형화" 주장 과장.** 메모리 이중 루프만 제거했고 쿼리 수는 여전히 O(코어수 × fail원천수) — 실측 2코어에 10문 (F7) | `transfer_plan.py:445-446` |
| D4 | **클라 보고서 §5-2 "`total_layers` 컬럼 부재"가 현 상태와 불일치** — 총괄이 이미 추가했다(라이브 `table_config` + DB 컬럼 실재). 그런데 서버·클라 어느 쪽도 쓰지 않아 죽은 컬럼이 됐다 (F5) | `table_config.json` transfer_plan |
| D5 | **서버 보고서 §8-bis-(4) escalation은 이미 해소됨** — 문제의 `bonding_plan__TESTPLAN_M2VERIFY_01` 행은 클라부가 정리 완료했고 라이브 `transfer_plan`에는 `TP-SMOKE-1`(stage=`bonding`, 선언 어휘) 1건만 남아 있다. 보고서 §11 "미해결" 목록에서 내려야 한다 | 라이브 SELECT 실측 |
| D6 | 서버 보고서 §5-1이 "297 passed", §1 표와 §8-bis가 "298 passed"로 **자기 불일치**. 실측 정답은 **298** | 직접 실행 |
| D7 | `transfer_plan.py` 모듈 docstring이 `remaining` 계약을 "칩 단위 정확 집계"라고 단정 — F1/F2/F3의 강등·절단·중복 조건에서 성립하지 않으므로 단서 필요 | `transfer_plan.py:311-313` |

---

## 6. 병합 조건

### 6-1. 병합 전 필수 (NO-GO 해제 조건)

**"거짓 초록" 계열 — 이 4건이 NO-GO의 실질 사유다**

| # | 조치 | 위치 |
|---|---|---|
| 1 | **C2** — validate `.catch(() => null)` 제거. 파싱 실패를 경고로 승격해 "경고 없음 ✓"가 뜨지 않게 한다 | `transfer_plan.js:664` |
| 2 | **C3** — `w.type === 'stage_unknown'`(및 `source_unresolved`)을 전용 배너로 격상하고, 그 상태에선 클라 자체 초록 배지를 "검증 스킵"으로 무력화 | `transfer_plan.js:625-642` |
| 3 | **C1** — `sources` status 원문을 최소 `title`에 노출. `connected(` 접두는 `missing` 클래스에서 제외하고, `unavailable(`/`align_unavailable`은 별도 경고 등급 | `transfer_plan.js:1046-1050`, `:541-543`, `:491-493` |
| 4 | **F1** — 서버가 강등 상태를 응답 `warnings` + 신뢰도 플래그(`remaining_reliable`)로 내보내고, `validate`가 오염된 `remaining`으로 "이상 없음"을 내지 않게 차단. `test_transfer_plan.py:481` assert에 "경고 발생" 조건 추가 | `transfer_plan.py:470-476`, `556-559`, `790` |

**데이터 무결성 계열**

| # | 조치 | 위치 |
|---|---|---|
| 5 | **C5** — 페인팅 모드 동안 `meta-input-{planCol}`을 `readOnly` 처리(`tableSelect`와 동일 대우) + push 확인문에 `plan_id` 명시 | `map_editor.js:3439-3440`, `:2631`, `:3473` |
| 6 | **C4** — DOE 삭제·개명을 서버에 전파(저장 시 서버 DOE 목록 diff 후 batch_delete). 미조치 시 유령 DOE가 validate 출력을 영구 오염 | `transfer_plan.js:821-823`, `:783-801`, `:1435-1476` |
| 7 | **C10** — `planPaint.pushed`를 onCancel에 전달해 "미반영" 거짓 안내 제거 | `map_editor.js:3486-3509`, `transfer_plan.js:1381` |

### 6-2. 병합 후 즉시 (후속 티켓 분리 가능)

- **F2** 캡 도달 응답 표기(`truncated`/`by_core_truncated`) · **F4** 소스 합산 초과배정 검출 · **F5** `total_layers` 3자 배선(서버 config 매핑 + validate + 클라 전송 — 셋 다 해야 산다) · **F6** `dst_grid` 전달 · **F7** N+1 배치화 · **F8**/**C8** stage 강등 고지 + `fetchStages()` await · **C7** plan_id `|` 충돌 · **C9** 부분 실패 상태 분기 · **C11** 페인팅 대조 층수 누락 · **C13**/**C14** 조용한 실패·절단 고지 · **F9**/**F10**
- **D1·D2 문서 동기화**(doc-keeper) — 커밋과 같은 배치에 넣는 것이 규율상 옳다.

### 6-3. 별건 (본 변경분 무관 — 기존 시스템 결함)

- **C6** `limit=2000` + `replace_map: true` 데이터 소실 — **전 맵 공통**(HEAD 2144/2668행에 이미 존재). 응답 `total` 검사 후 초과 시 push 봉인. 현행 프리셋(최대 1600셀)에선 미발화지만 규격 확대 시 즉시 터진다.
- **C12** `CURRENT_USER` 빌드 시점 고정(`config.js`/`vite.config.js` 무수정) — 웹 클라 경유 저장이 전부 한 사람으로 기록.
- **F12** `GET /tables/{t}/schema`가 미존재 테이블에도 200 (총괄 판단 요청 ⓑ) — **심각도 낮음**. 클라가 이미 `GET /tables/{t}/data`(404) 게이트로 우회했고 M2 병합을 막을 사유가 아니다.

### 6-4. 총괄 판단 요청 3건에 대한 회신

| | 항목 | 판정 |
|---|---|---|
| ⓐ | `plan_id` 합성을 클라가 자체 결정 | **위험 낮음 — 현행 유지 가능.** 서버는 `plan_id`를 파싱하지 않는다(`transfer_plan.py:639`는 컬럼 equals, stage는 별도 컬럼). 실질 위험은 `\|`→`_` 충돌(C7)과 stage 강등 시 plan_id 동반 변경(C8 결합)이며, 둘 다 국소 수정으로 해결된다. **다만 규칙을 스펙 문서에 명문화**해 서버가 향후 파싱하지 않을 것을 계약으로 못박을 것 |
| ⓑ | `/schema`가 미존재 테이블에 200 | **낮음 · 별건.** 기존 결함이고 클라가 이미 우회했다. 후속 티켓(빈 `columns`/`business_key`면 404) |
| ⓒ | `updated_by` null 저장 = 감사 추적 영향 | **기각 후 재분류 — 낮음.** 실제 감사 추적은 `cell_overwrites`가 담당하며 **정상 작동한다**(라이브 실측: `('transfer_plan_map','val','tp_smoke',None,4)` 등 전 컬럼 기록). NULL인 것은 아무도 쓰지 않는 **업무 컬럼** `transfer_plan.updated_by`다 → 채우거나 `table_config`에서 제거. 별개로 **C12(빌드 시점 사용자 고정)가 진짜 감사 추적 문제**이며 이쪽이 기존 결함이다 |

## 7. 라이브 데이터 영향

- 본 검수는 **SELECT만** 수행. 시드 삽입 0건 → **정리 대상 없음**.
- 검증 스크립트는 스크래치패드에만 생성(프로젝트 트리 무접촉).
- 참고: 라이브 `transfer_plan` 잔여는 서버부 스모크 `TP-SMOKE-1`(plan 1 / doe 2 / map 4행)뿐이며 삭제 여부는 총괄 판단 사항.

## 8. 교훈 제안 (총괄 검수 후 `agent_workspace/memory/qa-reviewer.md` 반영 후보)

1. **함정**: "부분 가동(graceful degradation)" 설계를 검수할 때 정상 경로 수치만 대조하면 통과한다 — 정작 위험은 **역할 하나가 무너졌을 때 숫자가 조용히 커지는** 방향이다.
   **올바른 방법**: 역할 바인딩을 하나씩 in-memory config로 파괴하며 **핵심 수치의 변화 방향과 `warnings` 동반 여부**를 표로 대조한다. 경고 없이 값만 바뀌면 그 자체가 결함이다.
2. **함정**: 하드캡(`limit(N)`)이 있으면 "확장성 규율 준수"로 읽히지만, 캡 도달이 로그로만 남고 응답에 흔적이 없으면 **정상 응답과 구별 불가능한 오답**이 된다.
   **올바른 방법**: 캡 상수를 검수 중 인위적으로 낮춰(테스트 데이터가 캡을 넘도록) 실제로 응답이 어떻게 달라지는지 실측하고, 절단 사실이 응답 계약에 실리는지 확인한다.
3. **함정**: 테스트가 초록불이어도 그 assert가 **결함 동작을 정답으로 고정**하고 있을 수 있다(강등 시 과대 `remaining`을 기대값으로 박은 사례).
   **올바른 방법**: 강등·실패 경로 테스트는 "상태 문자열이 맞는가"뿐 아니라 "**핵심 수치가 어느 방향으로 틀리며 그것이 사용자에게 고지되는가**"를 assert하는지 본다.
4. **함정**: 서버가 힘들게 만든 상태 신호(`connected(align_unavailable)` 등)를 **클라가 이진값으로 뭉개면** 전 계층의 관측 가능성이 한 줄에서 소멸한다. 서버만, 클라만 따로 검수하면 양쪽 다 "신호는 있다/처리는 한다"로 통과한다.
   **올바른 방법**: 상태 문자열류 계약은 **서버 산출 → 클라 렌더까지 한 줄로 추적**해 "화면에 몇 가지로 구별되는가"를 세어 본다. 서버 5종이 화면 2종이면 그 자체가 결함이다.
5. **함정**(자기 규율 재확인 — 이번에 실제로 갈렸다): 검수 보조/서브에이전트가 올린 최우선 블로커가 **기존 결함**인데 회귀로 보고될 수 있다(`limit=2000` + `replace_map` 사례).
   **올바른 방법**: 보조의 블로커는 **반드시 `git show HEAD:<file>`로 기존 존재 여부를 직접 확인**한 뒤 판정에 반영한다. 기존/신규를 섞으면 NO-GO 사유가 부풀려져 총괄의 우선순위 판단이 왜곡된다.
