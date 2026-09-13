# Server — 전사 계획 모델 v2 구현 + 오버레이 라이브 버그 수정

> **작성:** server-pm / 2026-07-26 (**개정 5 — QA 재검수 NO-GO A1 대응: 프레임 좌표계 규격 보정**)
> **스위트:** 기준선 381 passed / 1 allowed fail → **413 passed / 1 allowed fail** (+32)
> **커밋 없음 · 재기동 없음 · client2 무접근**

> ### 📌 개정 5 요약 (QA A1 차단 해소)
> **지적 전면 수용.** B1 수정이 부분 수정이었고, 결함이 bbox 계층으로 내려갔을 뿐이다.
> - **`_frame_transformer`의 엔진을 프레임 좌표계 규격으로 생성** — 회전 90/270에서 칩 피치 스왑, back에서 offset x 부호 반전. **표를 신뢰하지 않고 `cell_to_physical`에서 직접 유도해 8조합 전부 확인**했다(§1-11).
> - **`_oracle_bbox`를 진짜 독립으로 재작성** — `PhysicalWaferEngine`을 쓰지 않고 원 판정 산술을 직접 구현. 이전 오라클은 bbox 계층에서 검증 대상의 복사본이었다.
> - **결함 축을 살린 픽스처 추가** — `chip_x ≠ chip_y`(이방성) × rot 90/270 × back × 크롭. 기존 `PHYS_STD`/`PHYS_CROP`은 둘 다 `chip_x == chip_y`라 스왑 축이 죽어 있었다.
> - **25,760 순서쌍 재대조: SILENT-WRONG 0 + `LOUD→SILENT` 전이 0** (두 조건 동시).
> - 내 오라클이 직전 코드에 **84**를 매겨 QA 수치와 정확히 일치 — 상호 교차검증됐다.
> - 라이브 5케이스 전부 오라클 MATCH, `bonding_map/EXP1`의 `x=-1` 격자 밖 셀 **0건**으로 해소.
> - ⚠️ **REST 재검증은 재기동 필요**(§1-13) — 실행 중 서버는 아직 구 코드다.

> ### 📌 개정 4 요약 (QA B1 차단 해소)
> **QA 지적 전면 수용.** 셀 x/y는 단순 `셀인덱스+start`가 아니라 **웨이퍼 원으로 자른 바운딩박스 상대 좌표**인데(`xv = c - box.minC + start_x`) 그 항을 빼고 되돌려, 거울이 끼면 `2·minC`만큼 어긋났다.
> - **좌표 왕복을 손으로 쓰지 않고** `WaferMapCoordinateTransformer`의 **visual 계층**(`visual_to_physical`/`physical_to_visual`)을 그대로 쓴다 — 클라가 미러링하는 그 알고리즘이므로 bbox·start·y반전 세 항이 규약과 자동 일치한다.
> - **phys 규격이 없으면 명시 실패**(bbox 재현 불가 → 좌표 보증 불가). 조용히 그리지 않는다.
> - **M4**: `frame_axes`에 격자 치수 + phys 서명을 넣어 지름길이 규격 불일치를 우회하지 못하게 했다.
> - **회귀를 독립 오라클 대조로 교체** — 자기 왕복 검사는 균일 오프셋을 원리적으로 못 잡는다(§1-8).
> - **라이브 전수 재대조: 조용한 오답 108 → 0**, 명시 실패 건수는 5596으로 **불변**(커버리지를 되팔지 않았다).
> - 인덱스 3종 실행 완료(`pg_indexes` 실측 확인).

> ### 📌 개정 3 요약 (사용자 요구: "회전, 거울상, Y축 뒤집힘, START X,Y 모두 고려")
> 네 축을 **하나의 변환 파이프라인**으로 통합했다(§1-5). 핵심은 축 추가 자체보다 **지름길 조건을 좁힌 것**이다.
> - **`grid_y_invert`를 프레임↔물리 매핑에 편입** — 반전 축 길이는 **회전 반영 후** 프레임 행 수다(비정방 격자에서 갈린다).
> - **`grid_start_x/y` 정규화를 지름길에도 강제** — 변환 자체는 이미 start를 처리하고 있었고, 진짜 구멍은 **identity 지름길이 통째로 건너뛰던 것**이었다.
> - **지름길은 네 축이 전부 같을 때만** (`frame_axes()` 튜플 완전 일치). 표시용 요약이 identity로 보여도 derived면 **반드시 합성**한다.
> - ⚠️ **라이브에서 실제 오답이 나던 쌍 2건을 찾았다**(§1-6) — 가설이 아니라 실측이다.
> - 회귀 +14 (축 단독 2 · 조합 8 · 전수 대조 1024쌍 1 · 비정방 1 · 전축 동시 1 · 지름길 조건 1).

> ### 📌 개정 2 요약 (총괄 반려 대응)
> `map_doe` bk가 `(ref_table, map_key, doe_value)`라 **값당 구간 1개**만 담기던 문제(E1)를 해소했다.
> - **DOE 행의 단위를 `(값, STACK 구간)`으로 바꿨다** — bk에 구간 차원 추가.
> - **구간 정체는 `band_seq`(정수 서수), 표기는 `stack_band`(자유 텍스트 비키 컬럼)로 분리했다.**
>   자유 텍스트를 키에 넣으면 안 되는 이유를 코드로 확인했다(§3-3) — 라벨 수정이 곧 re-key라 자재가 고아가 된다.
> - **자재 묶음(`map_doe_source`)을 구간 아래로 옮겼다** — 구간마다 다른 묶음이 가능하다(스케치의 `A|H1~H2 → DT-A`).
> - **`description`/`color`는 `map_doe`에서 뺐다** — `map_split_registry`가 이미 같은 키 앞부분으로 갖는다(중복 저장 회피).
> - 신규 회귀 4건 포함 총 +10.

---

## §0. 클라이언트에 넘길 계약 (Client PM 인계 — 여기만 읽어도 배선 가능)

### 0-1. REST 계약 변경 (3건)

| 엔드포인트 | 구 | 신 |
|---|---|---|
| `GET /api/transfer-plan/validate` | `?plan_id=<stage>__<target>` | **`?ref_table=<맵테이블>&map_key=<맵키>`** |
| `GET /api/transfer-plan/source-summary` | `&plan_id=` (영역 스코프용, 선택) | **`&ref_table=&map_key=`** (선택, 둘 다 있어야 영역 스코프 적용) |
| `GET /api/transfer-plan/stages` → `plan_store` | `{plan, doe, map, doe_layer?, source_region?}` | **`{doe, doe_source?, source_region?}`** — `plan`·`map` 역할 소멸 |

`GET /api/maps/overlay` · `GET /api/maps/paint-rules` · `GET /api/bonding-plan/core-summary` · `GET /api/transfer-plan/source-summary`의 **응답 형태는 불변**이다.

### 0-2. `validate` 응답 형태 변경

```jsonc
// 구
{ "plan_id": "...", "plan": {plan_id, stage, target_lot, target_slot, status, memo},
  "doe_count": 1, "painted_values": {...}, "status": "...", "availability_checked": true,
  "warnings": [...] }

// 신 (v2)
{ "ref_table": "bonding_map",      // 열려 있는 맵 테이블 (요청 그대로)
  "map_key":   "aa123_a",          // 맵 키 (요청 그대로)
  "stage":     "bonding",          // ★ 유도값 — 클라가 보낼 필요 없다. 미선언 맵이면 null
  "map_status": "connected",       // ★ 신규: 대상 맵의 좌표 바인딩 해석 상태(connected|missing)
  "doe_count": 1,
  "painted_values": { "1": 137, "2": 11, "F": 39 },   // ★ 출처가 **대상 맵 자신**
  "status": "ok|warnings|unverified",
  "availability_checked": true,
  "warnings": [...] }
```

- `plan` 블록 소멸(`plan_id`/`target_lot`/`target_slot`/`status`/`memo` 없음). 계획 헤더 테이블 자체가 폐기됐다.
- **`stage`는 서버가 유도한다** — `stages.*.target_map.table` 역인덱스. 클라의 stage 셀렉트는 제거 대상이고, 표시는 서버 응답의 `stage`를 그대로 쓰면 된다.
- **404 조건이 바뀌었다.** 구: `plan_id` 미존재 → 404. 신: **계획 미존재라는 개념이 없다**(빈 계획일 뿐 → 200 + `doe_count:0`). 404는 `plan_store.doe` 바인딩 미구성 **단 하나**다.
- **전사 대상이 아닌 맵도 200이다** — `stage: null` + `stage_unknown` 경고 + `status: "unverified"`. 임의의 맵을 편집 대상으로 열 수 있어야 하므로 거절하지 않는다.

### 0-2-bis. ⭐ DOE 행의 단위와 `band_seq` (클라 저장 로직의 핵심)

**DOE 행 1건 = `(값, STACK 구간)`** 이다. 사용자 스케치대로 한 값이 구간을 여러 개 갖는다:

```
VALUE | STACK   | 자재            저장되는 행
A     | H1~H2   | TAPE-X          map_doe(doe_value=A, band_seq=1, stack_band="H1~H2")
A     | H2~H3   | TAPE-Y          map_doe(doe_value=A, band_seq=2, stack_band="H2~H3")
B     | H1~H3   | TAPE-X          map_doe(doe_value=B, band_seq=1, stack_band="H1~H3")
```

**클라가 지켜야 할 규칙 3가지:**

1. **`band_seq`는 클라가 부여하는 정수 서수**(1부터). 같은 `(ref_table, map_key, doe_value)` 안에서만 유일하면 된다. 새 구간 추가 = `max(band_seq)+1`. **구간을 지워도 서수를 재정렬하지 마라** — 재정렬하면 `map_doe_source` 행들이 전부 re-key된다.
2. **`stack_band`(자유 텍스트 표기)는 절대 키에 넣지 마라.** 라벨은 언제든 수정 가능한 표시값이고, 수정해도 그 구간의 자재 묶음이 그대로 붙어 있어야 한다.
3. **자재 묶음은 값이 아니라 구간에 붙는다** — `map_doe_source`에 `doe_value`와 **`band_seq`를 함께** 써야 한다. 빠뜨리면 그 구간의 묶음이 조회되지 않아 `source_unresolved`가 뜬다.

`description`/`color`는 **`map_doe`에 없다** — 기존 `map_split_registry`(`ref_table|map_key|value`)가 정본이다. 클라는 지금처럼 legend를 그 테이블에 저장하고, 전사 확장 필드만 `map_doe`에 쓰면 된다. (값 하나에 legend 1행 : DOE N행의 1:N 조인)

### 0-3. 경고 계약 (타입은 전부 불변, 의미만 이동)

| 타입 | 변화 |
|---|---|
| `qty_shortage` | `demand` 라벨이 `A@L2`(층) → **`A[2-11]@TAPE-A\|01`(값[구간]@자재)** 로 바뀜 |
| `source_overallocated` | `doe_values`가 층 라벨 → **`값[구간]@자재` 라벨** 목록. 판정 자체는 불변(같은 자재를 쓰는 수요 합산 — 이제 **구간을 가로질러** 누적된다) |
| `layer_coverage_gap` / `layer_range_invalid` | 입력이 `layer_from/to` 숫자 → **`stack_band` 자유 텍스트**. 수치로 읽히는 표기(`1`, `2-11`, `3~5`)만 참여하고 `H1~H2`·`바닥`은 조용히 불참(경고 신설 없음). `layer_range_invalid`에 `band` 필드 추가(어느 구간인지 식별용) |
| `source_unresolved` | "소스 lot/slot 미지정" 외에 **"자재 묶음 미선언"** 케이스 추가. `band` 필드 추가 |
| 그 외(`undefined_doe_value`, `doe_value_unpainted`, `source_fail_chips`, `source_history_fail`, `availability_unreliable`, `source_degraded`, `result_truncated`, `negative_remaining`, `stage_unknown`) | **불변** |

### 0-4. 오버레이 계약 (형태 불변, 동작만 개선)

- `align_applied.origin`에 **`"unresolvable"`이 더 이상 나오지 않는다.** 예전엔 `면 반전 + 타깃 회전 90/270` 조합을 거절했는데(§1-3), 이제 올바르게 그린다. 클라에 `unresolvable` 분기가 있으면 죽은 가지가 된다(제거해도 되고 둬도 무해).
- `align_applied.{rotation, flip}`은 이제 **표시용 요약**이다(실제 좌표 합성은 두 맵 메타로 별도 수행). "180° 정렬됨" 배지 용도로는 그대로 쓰면 된다.
- ⚠️ **`origin: "derived"`인데 `rotation: 0, flip: "none"`인 응답이 정상적으로 존재한다** — y반전이나 시작좌표만 다른 경우다. 클라가 "회전 0 = 정렬 안 함"으로 읽으면 안 된다. **`origin`으로 판단하라**(`identity`만 무보정). 무엇이 보정됐는지는 `align_applied.note`에 한글로 담기고(`프레임 정규화 적용: 시작좌표(1,1)→(-10,-12)`), 순수 평행이동일 때는 `offset`에 실수치가 실린다(회전이 섞이면 평행이동이 아니므로 `offset`은 0으로 두고 note만 신뢰할 것).
- **선언 없는 맵도 겹쳐진다.** `map_overlay_config.table_bindings`에서 `bonding_map`/`test`/`sample_map`/`transfer_plan_map` 선언을 제거했고, `table_config`에서 자동 유도된다. 클라가 "이 테이블은 오버레이 소스로 쓸 수 있나"를 미리 알 필요가 없어졌다.

### 0-5. ⚠️ 클라 몫으로 남긴 버그 (서버는 손대지 않음)

`client2/src/map_editor.js:2334-2337`이 `wafer_map_metadata`를 **`map_id`만으로 필터**한다. 라이브에 같은 `map_id`가 여러 테이블에 실재하므로(`AAA` → `bonding_map_AAA`(rot 0) · `test_AAA`(rot 270) / `aa123_a` → `bonding_map_aa123_a`(rot 0·back) · `sample_map_aa123_a`(rot 270·front)) **남의 회전 규격을 집는다.** 사용자 증상 *"test/AAA는 270도인데 0도로 불러와지고 좌표가 삐져나간다"* 는 **정확히 이 클라 버그**다. 필터를 `(target_table, map_id)` 쌍 또는 `map_pk === \`${table}_${mapId}\`` 로 고쳐야 한다.

---

## §1. 라이브 버그 — 검증 결과와 실제 원인

### 1-1. ⚠️ 지시서/총괄 가설은 **서버에 대해서는 성립하지 않는다** (증거 첨부)

지시는 "서버의 맵 메타 조회가 `target_table`을 무시하고 `map_id`만으로 매칭한다"였고 총괄이 이를 "확정"으로 전달했으나, **서버 코드에는 `map_id` 단독 조회가 존재하지 않는다.** 전수 grep + 라이브 실행으로 확인했다.

| 근거 | 내용 |
|---|---|
| ① 코드 | `server/map_overlay.py:113-116` — `filter(target_table == …, map_id == …)` **쌍으로 필터** |
| ② 코드 | `server/bonding_plan.py:287-291` (`load_grid_meta`) — 동일하게 쌍 필터. `wafer_map_metadata`를 읽는 서버 지점은 이 둘뿐 |
| ③ 인덱스 | `setup_bonding_plan_indexes.py:23` — `idx_wafer_map_metadata_target_map (target_table, map_id)`. 쌍 조회를 전제로 이미 색인돼 있다 |
| ④ **라이브 실행** | 수정 전 상태에서 엔진을 실 PG에 직접 호출 → `meta bonding_map → rotation 0` / `meta test → rotation 270` / `meta sample_map → rotation 270`. **각자 자기 규격을 정확히 반환** |
| ⑤ **결정적 반증** | 수정 전 실패 메시지가 `align frame dims mismatch: source 29x25 **rotated 270**`이었다. 서버가 `bonding_map_AAA`(rot 0)를 집었다면 상대 회전이 0이 되어 **변환 시도 자체가 없었을 것**이다. 270이 나왔다는 사실이 곧 `test_AAA`를 읽었다는 증거다 |

`sample_map_aa123_a`(270)와 `test_AAA`(270)의 회전이 **우연히 같아** 응답의 `rotation: 270`이 sample_map에서 온 것처럼 보인 것이 오인의 출처로 보인다.

지시서는 "검증 단계를 건너뛰고 바로 수정해도 된다"고 했으나, 고칠 결함이 그 자리에 없으므로 **없는 결함을 고치는 대신 실제 원인을 고쳤다.** 총괄이 요구한 회귀 테스트는 (원인과 무관하게 가치가 있으므로) 그대로 추가했다 — `test_same_map_id_in_two_tables_uses_each_own_spec`.

### 1-2. 실제 원인 — **물리 치수 vs 프레임 치수 혼동**

`wafer_map_metadata.grid_cols/grid_rows`는 **물리(canonical) 치수**다. 셀에 저장된 `x/y`는 **프레임(visual) 좌표**이며 그 치수는 맵 자신의 회전이 90/270이면 물리의 스왑이다(`WaferMapCoordinateTransformer.visual_cols/visual_rows` 규약). 라이브 데이터로 검증했다:

| 맵 | 메타(물리) | 회전 | 프레임(기대) | 실측 x/y 최대 |
|---|---|---|---|---|
| `bonding_map/4B13` | 27x21 | 0 | 27x21 | 23, 17 ✅ |
| `bonding_map/4B12` | 27x21 | 270 | **21x27** | 17, 23 ✅ |
| `sample_map/aa123_a` | 29x25 | 270 | **25x29** | 21, 25 ✅ |

그런데 `map_overlay._grid_of`가 메타 값을 **그대로** `bonding_plan.make_align_transform(src_grid=…)`에 넘겼다. 그 함수는 `src_grid`를 **프레임 치수**로 해석하므로, 회전 270 맵에서 정상 조합이 치수 모순으로 오판됐다:

```
align frame dims mismatch: source 29x25 rotated 270 maps to 25x29, but canonical grid is 29x25
→ status: align_unavailable   (사용자가 본 그 실패)
```

이는 구 M2 보고서 §S1'의 "알려진 한계 2"로 이미 문서화돼 있었으나 **라이브에서 발화할 수 있다는 점이 과소평가**돼 있었다.

### 1-3. 조치 — 프레임 합성(구 QA B3 한계의 근본 수정)

치수만 스왑해 넘기는 국소 수정으로도 이 케이스는 풀리지만, 같은 뿌리에서 나온 **더 큰 결함**(QA B3: `면 반전 + 타깃 회전 90/270` 16조합을 명시 거절)이 남는다. 그래서 M2 보고서가 백로그로 남겨 둔 **근본 수정**을 했다:

```
(x,y)_src ──src.cell_to_physical──▶ (xp,yp)_물리 ──dst.physical_to_cell──▶ (x,y)_dst
```

각 맵을 **자기 메타로** 물리 좌표에 사상한 뒤 타깃 프레임으로 역사상한다. 각 프레임의 반전 축(`back`이 90/270이면 행, 아니면 열)이 자기 메타로 각각 처리되므로 조합 폭발이 사라진다. 신규 `map_overlay.make_frame_transform(source_meta, target_meta)`.

- **거절 가드(`ALIGN_ORIGIN_UNRESOLVABLE`) 제거** — 과잉 거절이었다. 상수 자체는 클라 호환을 위해 남겼으나 응답에 나오지 않는다.
- **선언(override) 경로는 유지**하되 `_frame_grid_of`로 프레임 치수를 넘기도록 고쳤다(같은 결함 계열).
- `align_applied`는 표시용 요약으로 계속 산출한다(계약 불변).
- **물리 치수가 서로 다른 두 맵**(같은 웨이퍼 규격이 아님)은 여전히 `align_unavailable`로 명시 실패한다.

**라이브 실증** (`server/map_overlay.py` 직접 호출, 재기동 없음):

| | 수정 전 | 수정 후 |
|---|---|---|
| `test:AAA → bonding_map/aa123_a` | `align_unavailable` | **`ok`** (align 270/x, origin derived) |

### 1-4. 회귀 테스트

- `test_side_mismatch_with_rotated_target_is_refused` (8 파라미터) → **`…_composes_correctly`로 전환.** 구현을 되풀이하지 않는 **불변식 3종**으로 검증: ①타깃 격자 범위 내 ②소스 프레임 전역이 **단사** 사상 ③**왕복 항등**(거울상이면 깨진다). 구 테스트 docstring이 "근본 수정 시 이 테스트가 기준이 된다"고 예고한 대로다.
- `test_frame_compose_golden_rot90_back_target` — 손계산 골든 1건.
- `test_same_map_id_in_two_tables_uses_each_own_spec` — 총괄 요구 회귀(라이브 데이터 조합 재현).

### 1-5. 네 축 통합 파이프라인 (개정 3)

```
(x,y)_src ─start 정규화─▶ ─y반전 해제─▶ (c,r)_src셀
          ─src.cell_to_physical(회전·면)─▶ (xp,yp)_물리
          ─dst.physical_to_cell(회전·면)─▶ (c,r)_dst셀
          ─y반전 적용─▶ ─start 부여─▶ (x,y)_dst
```

축마다 분기를 두지 않고 한 경로에 꿴다. `start_x/start_y`는 셀 인덱스의 원점, `grid_y_invert`는 그 프레임이 행을 뒤집어 표기한다는 선언(변환기의 `invert_y`와 같은 의미)이며 **둘 다 프레임 고유 속성**이라 물리 좌표로 나가기 전/들어온 뒤에 각 맵의 선언대로 각각 처리한다.

**반전 축 길이 주의**: y반전은 **회전 반영 후 프레임 행 수**(`transformer.visual_rows`) 기준이다. 물리 `rows`를 쓰면 비정방 격자에서 어긋난다(회귀 `test_nonsquare_grid_y_invert_uses_rotated_row_count`가 6x4 물리를 90° 돌린 4x6 프레임으로 고정).

### 1-6. ⚠️ 진짜 구멍은 축이 아니라 **지름길**이었다 (라이브 실측)

`make_frame_transform`은 개정 1 시점부터 이미 start를 처리하고 있었다. 실제로 새던 곳은 `resolve_align`의 identity 지름길이 **회전·면만 비교**한 것이다:

```python
if rel_rot == 0 and flip == "none":        # ← y반전·start를 안 본다
    return None, ALIGN_ORIGIN_IDENTITY, None
```

회전과 면이 같고 start만 다른 두 맵은 **변환 없이 그대로** 그려졌다 — 전 셀이 균일하게 어긋나는데 `status: ok`. 조치는 세 곳:

1. `frame_axes(meta)` = `(회전, 면, y반전, start_x, start_y)` — 지름길은 이 튜플이 **완전 일치**할 때만.
2. `get_overlay`가 `origin == derived`면 **표시용 요약이 identity로 보여도 반드시 합성**한다(예전엔 `align.is_identity`를 보고 건너뛰었다 — 같은 함정이 한 겹 더 있었다).
3. 회전·면 밖의 축이 보정되면 `align_applied.note`에 명시하고, **순수 평행이동일 때만** `offset`에 실수치를 싣는다(회전이 섞이면 평행이동이 아니므로 틀린 수치를 표시하지 않는다).

**라이브 실측 — 가설이 아니다.** 전 메타 161건을 쌍으로 대조해 "회전·면 동일 + y반전/start 상이"인 조합을 찾았다:

```
지름길 오답 가능 쌍: 2건
  ('test','QQ')        (270,'back',False, 1,  1)
  ('bonding_map','QQ') (270,'back',False,-10,-12)
  ('bonding_map','AAA')(270,'back',False, 1,  1)  vs 위 QQ
```

`test/QQ → bonding_map/QQ` 실행 결과 (셀 80건):

| | 결과 |
|---|---|
| 구 코드 | `origin: identity`, 좌표 **무보정 통과** |
| 신 코드 | `origin: derived`, `offset {x:-11, y:-13}`, note `시작좌표(1,1)→(-10,-12)` |
| 어긋남 | 전 셀 균일하게 **(-11, -13)** — 예: `(1,1)→(-10,-12)`, `(5,7)→(-6,-6)`, `(12,3)→(1,-10)` |

과잉 보정도 확인했다 — `QQ → QQ`는 여전히 `identity`(네 축 동일)로 지름길을 탄다.

> **정직한 단서**: 라이브 메타의 `grid_y_invert`는 161건 전부 `false`라 **y반전은 라이브 실증이 없다**(테스트로만 고정). 또한 총괄이 전달한 "start 0/1/2/-1 혼재"와 내 실측(160건이 `(1,1)`, 1건이 `(-10,-12)`)은 다르다 — 사용자가 맵을 편집 중이라 메타가 움직이는 것으로 보인다(첫 측정엔 `test/QQ`·`bonding_map/AAA`·`QQ`가 없었다). 어느 스냅샷이든 **비기본 start가 실재하고 오답 쌍이 나온다**는 결론은 같다.

### 1-7. 회귀 테스트 (개정 3 신규 14)

| 테스트 | 고정하는 것 |
|---|---|
| `test_y_invert_alone_is_applied` | y반전 단독 — 손계산 골든 `(1,2)→(1,5)` + origin이 identity가 아님 |
| `test_start_offset_alone_is_applied` | start 단독 — 손계산 골든 `(2,3)→(3,4)` + `offset {1,1}` 실수치 |
| `test_identity_shortcut_requires_all_four_axes` | 축 5종 각각 하나만 달라도 `derived` |
| `test_all_four_axes_compose_without_silent_error` | **전수 대조**: 32프레임 × 32프레임 = 1024쌍 × 36셀 — 단사 + 타깃 격자 범위 + 왕복 항등 |
| `test_y_invert_combined_with_rotation` (×4) | y반전 × 회전 4종 |
| `test_start_offset_combined_with_rotation` (×4) | start × 회전 4종 |
| `test_nonsquare_grid_y_invert_uses_rotated_row_count` | 비정방 격자에서 반전 축 길이 |
| `test_start_offset_survives_mirror_and_rotation_end_to_end` | 네 축 동시 상이 — HTTP 경유, 격자 범위 + 셀 충돌 없음 |

검증 방식은 기존 규율 유지 — 구현을 되풀이하지 않고 **물리 좌표 경유 불변식**(단사·범위·왕복 항등)으로 대조한다.

### 1-8. [QA B1] 바운딩박스 항 — 차단 해소

**지적 전면 수용.** 클라 저장 규약이 정본이고, 내 구현은 그 규약의 한 항을 빼먹었다.

**원인**: `cell_to_visual`은 `xv = c - box.minC + start_x`인데(box = phys 파라미터로 웨이퍼 원 밖 셀을 제외한 바운딩박스) 내 역변환은 `c = x - start_x`였다. 두 항은 **합성 선형부가 +1일 때만** 상쇄되고, 면 반전·회전 조합으로 부호가 뒤집히면 **가산되어 `2·minC`만큼** 어긋난다.

**조치**: 좌표 왕복을 손으로 쓰는 것을 그만두고 변환기의 visual 계층을 그대로 쓴다.

```python
def to_target(x, y):
    return dst_tf.physical_to_visual(*src_tf.visual_to_physical(int(x), int(y)))
```

`WaferMapCoordinateTransformer`를 **phys 엔진과 함께** 생성하므로 bbox·start·y반전이 규약과 자동 일치한다. 손으로 옮기면 y반전 하나만 해도 규약은 `max_r - (yv - start_y)`인데 `(rows-1) - r`로 쓰기 쉽고, **실제로 내가 그렇게 썼다**(개정 3의 잠재 결함 — bbox가 0일 때만 우연히 같았다).

**추가 명시 실패**: phys 규격(6개 필드)이 하나라도 없으면 bbox를 재현할 수 없으므로 `align_unavailable`로 거절한다. 라이브 161건은 전부 보유해 영향 없다.

**성능**: bbox 산출이 격자 전 셀을 훑으므로 프레임 서명 단위 캐시(`_FRAME_TF_CACHE`, 512개 상한)를 뒀다. 소스 8종 × 왕복에서 재계산이 사라진다.

**[M4] 지름길 조건 확장**: `frame_axes`에 **격자 치수 + phys 서명**을 추가했다. 이전엔 치수가 달라도 회전·면·start가 같으면 지름길로 통과해 변환 경로의 치수 검사를 우회했다.

### 1-9. 라이브 전수 재대조 (요구 #3 — 수치 증명)

독립 오라클(클라 규약을 산술 그대로 옮긴 것, `map_overlay` 미호출)로 **구/신 구현을 나란히** 채점했다. 변환은 프레임 서명에만 의존하므로 서명 단위로 접어 평가하고 라이브 메타 쌍 수로 되펼쳤다(161건 → 고유 서명 11종, 순서쌍 25,760).

| derived 쌍 판정 | **구 구현** | **신 구현** |
|---|---|---|
| CORRECT | 10,086 | **10,194** |
| SILENT-WRONG | **108** (20 서명조합) | **0** |
| align_unavailable(명시 실패) | 5,596 | **5,596** (불변) |

- **조용한 오답 108 → 0.**
- **명시 실패 건수가 바뀌지 않았다(5,596 = 5,596)** — 이번엔 "소리 나는 실패를 조용한 오답으로 바꾸는" 거래를 하지 않았음의 증거다. 오답 108건이 그대로 CORRECT로 이동했다(10,086 + 108 = 10,194).
- 구 구현 오답 예: `sample_map/base → bonding_map/aa123_a` 전 셀 `(+4, 0)`, `sample_map/aa123_a → sample_map/base` 전 셀 `(+6, +2)`.

> QA는 12건, 나는 108건으로 셌다 — **세는 단위가 다르다**(QA: 서명/대표 쌍, 나: 라이브 메타 순서쌍 가중). 20개 서명조합이 161건 메타에 퍼진 결과다. 결함 판정은 동일하다.

### 1-10. 회귀 테스트를 독립 오라클 대조로 교체 (요구 #2)

**왜 기존 테스트가 못 잡았는지 확인했다 — QA 분석이 정확하다.** `test_all_four_axes_compose_without_silent_error`는 단사·범위·**왕복 항등**만 봤는데 셋 다 **같은 함수의 자기 대조**다. `f`가 통째로 `+4` 밀려 있어도 단사이고, 역함수도 같은 결함을 공유하므로 왕복 항등도 참이다. **바깥 정답과 한 번도 맞춰본 적이 없었다.**

교체 내역:
- `oracle_overlay()` — 클라 규약(`c - minC + start_x`, phys 엔진 bbox)을 **산술 그대로** 옮긴 정답지. `map_overlay`를 일절 호출하지 않는다.
- `test_transform_matches_independent_oracle_all_axis_combos` — 32프레임 × 32프레임 1024쌍을 오라클과 좌표 일치로 대조(구 왕복 검사 대체).
- `test_transform_matches_oracle_when_wafer_circle_crops_the_grid` — **B1 직격**. 칩 60mm로 원이 격자를 실제로 자르게 만들어(`minC > 0`) 거울 조합까지 대조.
- `test_missing_phys_spec_fails_explicitly` — bbox 재현 불가 시 명시 실패(요구 #4).
- `test_identity_shortcut_blocked_by_grid_dim_mismatch` / `..._by_phys_spec_mismatch` — M4.

**테스트가 결함을 실제로 잡는지 증명했다**(통과만 하는 테스트는 회귀 테스트가 아니다). 구 구현을 주입해 재실행:

```
FAILED test_transform_matches_oracle_when_wafer_circle_crops_the_grid
1 failed, 1 passed
```

> **정직한 단서**: 이때 `..._all_axis_combos`(1024쌍)는 **통과했다**. 그 픽스처(300mm 웨이퍼 / 7mm 칩 / 6x6)는 격자가 원 안에 통째로 들어가 `minC = minR = 0`이라 bbox 항이 사라지기 때문이다. **B1을 잡는 것은 크롭 픽스처 하나**이며, 축 조합을 아무리 늘려도 크롭이 없으면 이 결함은 영원히 안 잡힌다. 회귀의 무게는 조합 수가 아니라 **픽스처가 결함 축을 활성화하는가**에 있다.

### 1-11. [QA A1] 프레임 좌표계 규격 — 차단 해소

**지적 전면 수용.** 위임 방향은 옳았으나 변환기에 물려주는 엔진을 **메타의 물리 규격 그대로** 만들었다. `is_cell_inside_wafer(c, r, cols, rows)`의 `(c, r)`은 **프레임** 인덱스이므로 `chip_x`는 프레임 x축의 피치여야 하는데, 회전 90/270에서는 그 축이 물리 y축이다.

**표를 신뢰하지 않고 유도해 확인했다.** `cell_to_physical`이 정의하는 frame→physical 사상에 엔진의 mm 식을 대입해 항별로 맞췄다. rot 90 예시:

```
frame(c,r) → phys(r, VC-1-c)
  x_phys = (cr-r)*cx + Ox      y_phys = (c-cc)*cy + Oy
엔진이 프레임에서 계산하는  X = (c-cc)*chip_x + off_x  ↔ y_phys
                          Y = (cr-r)*chip_y + off_y  ↔ x_phys
  ⟹ (chip_x, chip_y) = (cy, cx),  (off_x, off_y) = (Oy, -oox)
```

노름은 성분 부호에 불변이므로 부호는 상쇄 항으로만 남는다. **4회전 × front/back 8조합 전부** 이 방식으로 검산했고 QA 표와 완전히 일치했다.

| rotation | (chip_x, chip_y) | (off_x, off_y) |
|---|---|---|
| 0 | (cx, cy) | ( oox, ooy) |
| 90 | (cy, cx) | ( ooy, −oox) |
| 180 | (cx, cy) | (−oox, −ooy) |
| 270 | (cy, cx) | (−ooy, oox) |

`oox`는 back에서 부호 반전(`cell_to_physical`이 회전 **전에** 면 반전을 적용해 물리 x축을 뒤집는다). 보정은 **`map_overlay._frame_phys_params` 안에 가뒀다** — `WaferMapCoordinateTransformer`/`PhysicalWaferEngine`은 손대지 않았다(`bonding_plan.py`가 공유, QA 권고 ②).

**저장 데이터로 독립 검증 (어느 규격이 옳은지는 데이터가 정한다)**

| 맵 | 실제 저장 | 현행 서버 예측 | 스왑 적용 예측 |
|---|---|---|---|
| `sample_map/aa123_a` (n=184) | x[1,21] y[1,25] | x[1,25] y[1,21] ✗ | x[1,21] y[1,25] **EXACT** |
| `bonding_map/4B12` (n=177) | x[1,17] y[1,23] | x[1,21] y[1,17] ✗ | x[1,17] y[1,23] **EXACT** |
| `test/QQ` (n=80) | x[1,21] y[1,25] | x[1,25] y[1,21] ✗ | x[1,21] y[1,25] **EXACT** |
| `test/AAA` (부분 도색) | y 최대 23 | 상한 21 ✗ **반증** | 상한 25 ✓ |
| rot 0 대조군 3종 | — | EXACT | EXACT (불변) |

8개 맵 중 모순 없는 건수: **현행 3 / 스왑 8**. QA 판정과 동일하다.

### 1-12. 라이브 전수 재대조 — 두 조건 동시 증명 (요구 #4)

독립 오라클 v2(`PhysicalWaferEngine` 미사용, 클라 산술 직접 이식)로 세 버전을 동시 채점. 오라클 자기검증(11개 서명 전부 자기쌍 항등) 통과.

```
=== 총계 (라이브 가중, 25,760 순서쌍) ===
  OLD    CORRECT  10124 · LOUD_FAIL  5596 · SILENT-WRONG   70
  PREV   CORRECT  10110 · LOUD_FAIL  5596 · SILENT-WRONG   84   ← QA 수치와 일치
  NEW    CORRECT  10194 · LOUD_FAIL  5596 · SILENT-WRONG    0

=== OLD → NEW 전이 (서명쌍 / 라이브 가중) ===
  CORRECT      -> CORRECT        12 / 10124
  LOUD_FAIL    -> LOUD_FAIL      86 /  5596
  SILENT-WRONG -> CORRECT        12 /    70

LOUD_FAIL -> SILENT-WRONG : 0   (요구: 0)  ✅
NEW SILENT-WRONG 총계      : 0   (요구: 0)  ✅
```

- **두 조건 동시 충족.** `LOUD→SILENT` 전이가 0이고, `LOUD_FAIL`은 5,596으로 **세 버전 모두 동일** — 커버리지를 되팔지 않았다.
- `CORRECT → LOUD_FAIL`·`CORRECT → SILENT-WRONG` 전이도 **0** (기존 정상 경로 무회귀).
- **교차검증**: 내 오라클이 직전 코드(PREV)에 매긴 **84**가 QA 보고 수치와 정확히 일치한다. 서로 독립으로 만든 두 오라클이 같은 답을 냈다는 뜻이라 이번 오라클은 신뢰할 만하다.

> **정직한 단서**: 표의 `OLD`는 git HEAD가 아니라 **개정 3 코드를 프로세스 내에서 재구성한 것**이다(HEAD 체크아웃은 워킹트리를 건드리므로 하지 않았다). QA의 HEAD 기준 전이표와 셀 값이 다른 것은 이 때문이며, 판정에 쓰이는 수치는 `PREV`(직전 워킹트리)와 `NEW`다.

### 1-13. 라이브 케이스 (요구 #5)

QA 지목 4건 + 대조군 1건을 수정 코드로 실행해 오라클과 대조:

| 케이스 | 결과 |
|---|---|
| `bonding_map/aa123_a ← sample_map:aa123_a` (184셀) | **MATCH** |
| `sample_map/aa123_a ← bonding_map:aa123_a` (187셀) | **MATCH** |
| `bonding_map/AAA ← test:AAA` (44셀) | **MATCH** |
| `bonding_map/EXP1 ← sample_map:aa123_a` (184셀) | **MATCH** · **격자 밖 셀 0건** (`x=-1` 해소) |
| `bonding_map/aa123_a ← bonding_map:EXP1` (232셀, 대조군) | MATCH (무회귀) |

> ⚠️ **REST 재검증은 재기동이 필요하다.** 실행 중인 :8080 서버는 개정 4 코드라 위 4건이 여전히 구 응답을 낸다(대조군만 일치). 재기동 금지 지시로 내가 확인할 수 없으므로, 총괄이 재기동 후 §5-4 체크리스트로 확인해야 한다. **"REST로 검증 완료"라고 쓰지 않는다.**

### 1-14. 회귀 테스트 — 오라클 독립성 + 결함 축 활성화 (요구 #2·#3)

**내가 §1-10에 쓴 교훈이 내 픽스처에 적용되지 않았다는 QA 지적이 정확하다.**

1. **오라클 독립성 회복**: `_oracle_bbox`가 `PhysicalWaferEngine`을 **같은 파라미터로** 만들고 있었다 → 합성 계층만 독립이고 bbox 계층은 검증 대상의 복사본. 원 판정 산술(`(x±hw)² + (y±hh)² ≤ R²`)을 직접 구현으로 교체했다.
2. **결함 축 활성화**: `PHYS_STD`/`PHYS_CROP`이 둘 다 `chip_x == chip_y`라 스왑 유무가 결과에 영향을 주지 않았다. `PHYS_ANISO`(40/70) + `PHYS_ANISO_OFF`(오프셋 부호 항까지) 추가.
3. 신규 4종: 이방성×회전×면 2종(파라미터), 비정방 격자×이방성, 규격 변환표 직접 대조.
4. **픽스처가 축을 살리는지 테스트 자신이 확인한다** — `assert bbox(rot0) != bbox(rot90)`로 죽은 픽스처를 구조적으로 차단했다.

**결함 버전 주입 재실행으로 검출력 증명**:
```
FAILED test_anisotropic_chip_pitch_swaps_on_rotated_frames[PHYS_ANISO]
FAILED test_anisotropic_chip_pitch_swaps_on_rotated_frames[PHYS_ANISO_OFF]
FAILED test_nonsquare_grid_with_anisotropic_pitch
FAILED test_frame_phys_params_match_independent_derivation
4 failed, 2 passed
```
> 통과한 2건이 기존 `oracle`/`crop` 테스트다 — **등방성 픽스처로는 이 결함을 원리적으로 못 잡는다**는 QA 분석이 실행으로 확인됐다.

---

## §2. 오버레이 바인딩 자동 유도 (universal 요구 해소)

`table_bindings`에 선언된 맵만 겹칠 수 있는 구조가 "모든 맵을 universal하게 오버레이"와 어긋났다(사용자 1차 증상 *"소스 맵을 찾을 수 없습니다"* 의 원인).

**신규 `map_overlay.derive_table_binding(table)`** — `table_config`에서 유도:

| 항목 | 규칙 |
|---|---|
| `key_columns` | `map_key_columns` 정본 → 미선언이면 `lot`/`slot`이 **둘 다** 있을 때만 관례 폴백 |
| `x`/`y` | 리터럴 `x`/`y` 컬럼. 없으면 **유도 실패** |
| `val` | 후보 우선순위 `val, value, leg, grade, result, code, split, doe` → 없으면 키·좌표·bk·시스템 컬럼이 아닌 첫 컬럼 |

우선순위는 **config 선언 > 유도**이며, 둘 다 실패하면 관례로 추측하지 않고 **명시 실패**한다(`source_missing` + 무엇을 선언해야 하는지 알려주는 detail). 라이브 유도 결과:

```
bonding_map     -> {x, y, val: leg,      key: [base]}      ✅
test            -> {x, y, val: leg,      key: [base]}      ✅  ← 선언 0으로 해소
sample_map      -> {x, y, val: val,      key: [base]}      ✅
dt_map          -> {x, y, val: val,      key: [lot, slot]} ✅
core_defect_map -> {x, y, val: val,      key: [lot, slot]} ✅
eds_fail_map    -> {x, y, val: val,      key: [lot, slot]} ✅
dt_log          -> None → 선언 경로 유지 {tx, ty, core_lot, [tape_lot, tape_slot]} ✅
bonding_log     -> None → 선언 경로 유지 ✅
```

**`map_overlay_config.json` 정리(적용 완료 — 사용자 config)**: `bonding_map`/`test`/`sample_map`/`transfer_plan_map` `table_bindings` 선언 제거(중복 선언은 유도 경로가 실제로 동작하는지 가려버린다), `paint_lock.transfer_plan_map` 제거. 남은 선언은 좌표 컬럼명이 관례 밖인 `dt_log`/`bonding_log`뿐이다.

> ⚠️ **총괄 판단 요청**: 제거한 `paint_lock.transfer_plan_map`이 갖고 있던 `from_overlay: [core_defect_map, eds_fail_map]`("불량 칩 위치라 배정할 수 없습니다")는 v2에서 **실맵(`bonding_map`/`dt_map`)으로 옮겨야 의미가 산다.** 새 페인트 규칙을 서버가 임의로 만들지 않고 제거만 했다 — 어느 맵에 붙일지 지시 바람.

---

## §3. 계획 모델 v2 — 구현 내역

### 3-1. 정체성 이동

| | v1 | v2 |
|---|---|---|
| 계획 정체 | `plan_id`(클라 합성 `<stage>__<target>`) + `transfer_plan` 헤더 행 | **`(ref_table, map_key)`** — 별도 개체 없음 |
| stage | 헤더 컬럼(사용자가 선택) | **`stage_of_table()` 역인덱스**(`stages.*.target_map.table`) |
| 페인팅 저장 | `transfer_plan_map` 사본 | **대상 맵 자신**(`_painted_values`가 group-by) |
| DOE 행 단위 | `값` 1행 | **`(값, STACK 구간)`** — 한 값이 구간 N개 |
| DOE 키 | `plan_id\|doe_value` | **`ref_table\|map_key\|doe_value\|band_seq`** (앞 3요소는 `map_split_registry` 관례와 동일 → legend 1:N 조인) |
| 층 배정 | `doe_key\|layer` (한 구간에 소스 1개) | **소멸.** 층 차이는 DOE 행의 `stack_band`(자유 텍스트 라벨)가 표현 |
| 소스 | DOE 행의 `source_lot/slot` 1쌍 | **묶음(pool)** — `map_doe_source` 행 N개, bk에 **구간 차원 + 소스 차원** |
| 설명·색 | `transfer_plan_doe.description` | **`map_split_registry`** (값 단위 legend가 정본 — 중복 저장 없음) |

### 3-2. 소스 묶음(pool) 수량 의미론

사용자 확정 *"몇 층에 뭐가 들어갈지 정확히 예측 불가 → 한 매당 500칩이면 4매 묶어서 투입"* 에 따라 **매별 소요는 지정 대상이 아니다**:

- `map_doe.qty_total` = 이 **구간**의 총 소요 칩 수(절대값). 구 `qty_per_unit × 칩수 × 층수` 산식은 폐기.
- 매별 required = `ceil(qty_total / 묶음 매수)` — **올림 배분**(부족을 과소평가하지 않기 위해).
- `map_doe_source.qty`가 있으면 그것이 우선(부분 선언 허용 — 구 층 배정 규율 승계).
- F4 합산 초과배정 판정은 **자재 단위로 자연히 누적**된다(같은 자재를 여러 값·여러 구간이 쓰면 전부 합산).

### 3-3. STACK 구간 — 자유 텍스트를 키에서 뺀 이유 (총괄 질의 응답)

**결론: 자유 텍스트 `stack_band`는 키에 쓰기에 안전하지 않다. 정규화로도 못 고친다.** 정수 서수 `band_seq`를 키로 쓰고 표기는 비키 컬럼에 뒀다. 근거 2가지를 코드로 확인했다:

**① bk 조립이 구분자를 이스케이프하지 않는다** — `server/database/crud.py:1577-1579`
```python
vals = [clean_str_value(getattr(row, col, None)) for col in composite_src]
new_bk_val = composite_sep.join(vals)      # ← 이스케이프 없음
```
구분자가 `|`인데 라벨에 `|`가 섞이면 키가 모호해진다: `value="A", band="1|2"` 와 `value="A|1", band="2"` 가 **같은 bk**를 만든다. 정규화(치환)로 막으면 이번엔 서로 다른 라벨이 같은 키로 충돌한다 — 어느 쪽이든 조용한 덮어쓰기다.

**② 키 컬럼이 바뀌면 행이 re-key된다** — `server/database/crud.py:1576-1591`
```python
if composite_src and key_col and col_name in composite_src:
    ...
    if current_bk != new_bk_val:      # ← business_key_val을 새로 만든다
```
라벨이 키에 있으면 `2-11` → `2-12` 로 **고치는 순간 DOE 행의 정체가 바뀐다.** 그런데 하위 `map_doe_source` 행들은 자기 키에 옛 라벨을 박아 두고 있으므로 **자재 묶음 전체가 고아**가 된다. 사용자는 "구간 이름만 고쳤는데 자재가 사라졌다"를 겪는다. 이건 정규화로 해결 불가능한 **구조적** 문제다.

그래서: **정체 = `band_seq`(클라 부여 정수 서수), 표기 = `stack_band`(자유 텍스트, 비키)**. 구 `transfer_plan_doe_layer`가 bk에 정수 `layer`를 쓰던 관례와도 일치한다. 라벨은 `1` / `2-11` / `H1~H2` / `바닥` 무엇이든 자유이며 **정규화 규칙이 필요 없다**(회귀 테스트 `test_pipe_in_band_label_does_not_corrupt_identity`가 `|` 포함 라벨을 고정).

수치 해석은 표시·검증용으로만 한다 — `_band_range()`가 `1` / `2-11` / `3~5` / `4..6`을 읽고 `H1~H2`·`바닥`은 **조용히 불참**한다. 커버리지/역전 경고는 수치로 읽히는 구간에만 적용되며 **새 경고 타입은 만들지 않았다**(지시: 검증 확장 금지).

### 3-3-bis. 가용/집계의 구간 단위 합산

- 수요(demand)는 **DOE 행(= 값×구간)마다** 생성되고, 매별 required = `ceil(qty_total / 묶음 매수)`.
- F4 합산 초과배정은 `(source_lot, source_slot)` 키로 누적하므로 **구간·값을 가로질러 자연히 합산**된다. 같은 테이프를 `A[1]`과 `A[2-3]`이 나눠 쓰면 합쳐서 판정된다(회귀 `test_bands_of_same_value_aggregate_on_shared_material`).
- 소스 가용 조회는 `(lot, slot)`당 1회 캐시라 구간이 늘어도 왕복이 늘지 않는다.

### 3-4. 확장성 규율

- DOE·자재 조회는 `(ref_table, map_key)` **equality**다. 구 `doe_key LIKE '<plan_id>|%'` 접두 스캔을 제거했다.
- 페인팅 값 분포는 **group-by 집계만** — 맵 셀 전량 로드 없음(맵 1장이 수만 셀).
- 하드캡: `MAX_DOE_PER_PLAN`(500) × `MAX_SOURCES_PER_DOE`(64, 구 `MAX_PLAN_LAYERS` 개명).
- 인덱스 스크립트 갱신(`setup_transfer_plan_indexes.py`): `idx_map_doe_ref_map`, `idx_map_doe_source_ref_map`, `idx_map_source_region_ref_map_src` 추가 / 구 `transfer_plan*` 4종 제거. **총괄이 config 적용 후 실행**해야 생성된다.

### 3-5. 수정 파일

| 파일 | 내용 |
|---|---|
| `server/map_overlay.py` | 프레임 합성 변환(`make_frame_transform`·`_frame_grid_of`), 바인딩 자동 유도(`derive_table_binding`), 거절 가드 제거, `_table_binding`→`resolve_binding`·`_key_filters`→`build_key_filters` 공개(타 모듈 재사용) |
| `server/transfer_plan.py` | `stage_of_table` 신설, `_painted_values` 신설, `_band_range` 신설, `validate_plan` 시그니처·본문 v2 전환, `_plan_store_statuses`·`load_source_region`·`get_stage_source_summary` 키 이동, 모듈 docstring 재작성 |
| `server/main.py` | `/api/transfer-plan/validate` · `/source-summary` 파라미터 전환 |
| `server/scripts/setup_transfer_plan_indexes.py` | 인덱스 목록 v2 전환 |
| `server/config/transfer_plan_config.json` (사용자 config) | `plan_store` v2 전환 — **적용 완료** |
| `server/config/map_overlay_config.json` (사용자 config) | 중복·죽은 선언 제거 — **적용 완료** |
| `server/tests/test_map_overlay.py` | 8건 전환 + 신규 5건 (31 passed) |
| `server/tests/test_transfer_plan.py` | 픽스처·validate 블록 v2 전면 전환 + 신규 (49 passed) |
| `docs/guide/CONFIG_GUIDE.md` | M2 §S6·§5.8 v2 반영 |

---

## §4. ⚠️ 총괄 적용 필요 — config 전문 (관례대로 미적용)

### 4-1. `server/config/table_config.json` — 신규 2종 추가

```json
  "map_doe": {
    "business_key": "doe_key",
    "composite_key_source": ["ref_table", "map_key", "doe_value", "band_seq"],
    "composite_key_separator": "|",
    "column_types": {
      "doe_key": "string",
      "ref_table": "string",
      "map_key": "string",
      "doe_value": "string",
      "band_seq": "number",
      "stack_band": "string",
      "qty_total": "number",
      "knobs": "string",
      "note": "string",
      "updated_by": "string",
      "eventtime": "string"
    },
    "display_columns": [
      "doe_key", "ref_table", "map_key", "doe_value", "band_seq", "stack_band",
      "qty_total", "knobs", "note", "updated_by", "eventtime"
    ]
  },
  "map_doe_source": {
    "business_key": "source_key",
    "composite_key_source": ["ref_table", "map_key", "doe_value", "band_seq", "source_lot", "source_slot"],
    "composite_key_separator": "|",
    "column_types": {
      "source_key": "string",
      "ref_table": "string",
      "map_key": "string",
      "doe_value": "string",
      "band_seq": "number",
      "source_lot": "string",
      "source_slot": "string",
      "qty": "number",
      "note": "string",
      "updated_by": "string",
      "eventtime": "string"
    },
    "display_columns": [
      "source_key", "ref_table", "map_key", "doe_value", "band_seq",
      "source_lot", "source_slot", "qty", "note", "updated_by", "eventtime"
    ]
  },
```

**컬럼 배치 근거 (중복 저장 회피 — 총괄 지시)**

| 속성 | 어디에 | 왜 |
|---|---|---|
| `split_desc`(설명) · `color` | **`map_split_registry`** (기존, `ref_table\|map_key\|value`) | 값 단위 속성이고 **전 맵 공통 legend**다. `map_doe`에 두면 같은 값의 구간 N개에 같은 설명이 N번 복제된다 |
| `stack_band` · `qty_total` · `knobs` · `note` | **`map_doe`** (구간 단위) | 구간마다 다를 수 있는 값. `knobs`를 값 단위로 올리면 "1층만 조건이 다르다"는 실제 요구를 표현할 수 없다 |
| `source_lot/slot` · `qty` | **`map_doe_source`** (구간 아래 묶음) | 구간마다 다른 자재 조합. 매수가 예측 불가한 축이라 행으로 분리 |

`map_doe`에 값 단위 컬럼이 하나도 남지 않으므로 **값 단위 전용 테이블은 만들지 않았다**(빈 껍데기 방지). 값 단위 정보가 필요하면 `map_split_registry`를 조인한다 — 키 앞 3요소가 동일해 조인이 자명하다.

**적용 방법**: 신규 테이블이므로 `create_missing_dynamic_tables` 경로 — `POST /admin/reload-configs`로 CREATE된다(`sync_dynamic_tables_schema`는 ALTER 전용이라 신규 CREATE를 하지 않는다 — 교훈 파일 §27). 적용 후 `information_schema`로 물리 생성을 직접 확인할 것.

**적용 전까지의 상태(정상 degradation, 확인 완료)**: `plan_store: {doe: "missing", doe_source: "missing"}`, `validate` → 404 `plan store is not configured`. 나머지 API(stages/source-summary/overlay/paint-rules)는 전부 정상.

### 4-2. `server/config/ontology_mapping.json`

**제거**: `transfer_plan`(ExperimentPlan) · `transfer_plan_doe`(SplitCondition). 남겨 두면 materializer가 죽은 테이블에서 계속 노드를 만든다.

**추가 후보 — 총괄 판단 요청 1건**:
```json
  "map_doe": {
    "description": "계획 맵(= 편집 중인 맵)의 DOE 조건군 — 페인팅 value 하나가 곧 하나의 실험 조건군이며 STACK 구간·총 소요·knob 계획·설명을 갖는다. map_split_registry의 legend와 동일 키(ref_table|map_key|value)의 두 얼굴이다",
    "node": { "label": "SplitCondition", "identity": "doe_key",
              "props": ["doe_value", "stack_band", "qty_total", "knobs", "description"] },
    "edges": []
  },
  "map_doe_source": {
    "description": "DOE가 쓰기로 계획한 자재(소스 웨이퍼/테이프) 1매 — 한 DOE에 여러 매가 묶음으로 붙는다",
    "node": null,
    "edges": [
      { "type": "PLANS_USE", "source_label": "SplitCondition", "source_identity_from": ["ref_table", "map_key", "doe_value"],
        "target_label": "Wafer", "target_identity_from": ["source_lot", "source_slot"],
        "description": "이 DOE가 칩을 가져다 쓰기로 계획된 자재" }
    ]
  },
```
⚠️ **쟁점**: `map_doe.doe_key`와 `map_split_registry.split_key`는 **완전히 같은 문자열**(`ref_table|map_key|value`)이고 라벨도 `SplitCondition`이다 → 두 테이블이 **같은 그래프 노드**에 props를 쓰게 된다. 설계 의도("legend와 DOE는 한 행의 두 얼굴")와는 일치하지만, materializer의 props 병합/충돌 의미론을 확인하지 않았다. **`map_doe_source`의 edge 문법(`source_label`/`source_identity_from`)이 현행 materializer에 존재하는지도 미확인**이므로, 위 블록은 **초안**이며 총괄이 온톨로지 담당과 확인 후 적용하기 바란다. (검증 없이 "적용하면 된다"고 쓰지 않는다.)

### 4-3. 라이브 `transfer_plan*` 4종 정리 — **권고 순서**

⚠️ **선언을 지워도 물리 테이블은 DROP되지 않는다**(안전 설계 — `sync_dynamic_tables_schema`는 ALTER 전용). 아래 1~3은 총괄이, 4는 **사용자 승인 후** 총괄이 실행한다.

| 순서 | 작업 | 이유 |
|---|---|---|
| 1 | `ontology_mapping.json`에서 `transfer_plan`·`transfer_plan_doe` 선언 제거 → 기존 `ExperimentPlan`/`SplitCondition` 노드·엣지 정리 | 선언이 살아 있으면 materializer가 계속 노드를 만든다. **table_config보다 먼저** 해야 롤백 경로가 남는다 |
| 2 | `table_config.json`에 `map_doe`·`map_doe_source` 추가 → `POST /admin/reload-configs` → `information_schema`로 물리 CREATE 확인 | **신규를 먼저 만든다** — 구 선언 제거보다 앞서야 계획 기능 공백이 없다 |
| 3 | `table_config.json`에서 `transfer_plan`·`transfer_plan_doe`·`transfer_plan_map`·`transfer_plan_doe_layer` 선언 제거 → 리로드 | 그리드 테이블 목록·맵 셀렉터에서 사라져 사용자 혼란이 제거된다 |
| 4 | 물리 `DROP TABLE` 4종 | **데이터 삭제 — 사용자 명시 승인 필요.** 그때까지는 "선언 없는 유령 테이블"로 무해하게 잔존 |
| 5 | `conda run -n assy_manager python server/scripts/setup_transfer_plan_indexes.py` | 신규 인덱스 2종 생성(2 이후 아무 때나). 구 인덱스는 테이블 DROP과 함께 사라진다 |

라이브 잔존 행 확인 결과 스모크 수준이라 **이관할 데이터는 사실상 없다**(구 계획은 데모 몇 건).

---

## §5. 검증 증거

### 5-1. 스위트

```
기준선  : 1 failed, 381 passed   (test_api.py::test_map_presets_api — allowed fail)
최종    : 1 failed, 413 passed   (동일 1건만 실패 — 신규 실패 0)
  test_map_overlay.py    : 53 passed  (18 → 31 → 45 → 49 → 53)
  test_transfer_plan.py  : 53 passed
```

**인덱스 (요구 — 실행 완료)**
```
[ok] idx_map_doe_ref_map        ON map_doe (ref_table, map_key)
[ok] idx_map_doe_source_ref_map ON map_doe_source (ref_table, map_key)
[skip] map_source_region 미적용 (휴면 — 정상)
```
`pg_indexes` 직접 조회로 물리 반영 확인(스크립트 `[ok]`만 믿지 않음).

**개정 2 신규 회귀 4건 (E1 고정)**

| 테스트 | 고정하는 것 |
|---|---|
| `test_one_value_can_have_multiple_stack_bands` | 스케치 그대로 `A[H1~H2]`·`A[H2~H3]`·`B[H1~H3]` 3행이 살아 있고, **A의 두 구간이 서로 다른 자재를 본다**(묶음이 값이 아니라 구간에 붙는 증거). 값당 1행으로 뭉개지면 `doe_count`가 2로 떨어져 실패한다 |
| `test_bands_of_same_value_aggregate_on_shared_material` | 같은 자재를 여러 구간이 나눠 쓸 때 **구간을 가로질러** 합산 초과배정이 잡힌다 |
| `test_band_label_is_not_part_of_identity` | 라벨만 수정해도 자재 묶음이 따라온다(고아가 되면 `source_unresolved`로 바뀌어 실패) |
| `test_pipe_in_band_label_does_not_corrupt_identity` | 구분자 `\|`가 섞인 라벨도 안전 |

### 5-2. 라이브 (실 PG 직접 호출 — 재기동 없음)

| 항목 | 결과 |
|---|---|
| `test:AAA → bonding_map/aa123_a` 오버레이 | 수정 전 `align_unavailable` → **`ok`** |
| 메타 쌍 조회 | `bonding_map`→rot 0 / `test`→rot 270 / `sample_map`→rot 270 (각자 자기 규격) |
| 바인딩 유도 | 라이브 맵 6종 전부 **선언 0으로** 해석 / 로그 2종은 선언 경로 유지 |
| stage 역인덱스 | `bonding_map`→`bonding`, `dt_map`→`dt`, `test`→`None` |
| 페인팅 값 분포 | `bonding_map/aa123_a` → `{1:137, 2:11, F:39}`, `test/AAA` → `{1:1, F:43}` (대상 맵 자신에서) |
| 미적용 degradation | `plan_store {doe: missing, doe_source: missing}` + validate 404 (설계대로) |

### 5-2-bis. 라이브 (개정 3 — 좌표축)

| 항목 | 결과 |
|---|---|
| 메타 전수(161건) 축 분포 | `(start_x, start_y, y_invert)` = `(1,1,False)` 160건 + `(-10,-12,False)` 1건(`bonding_map/QQ`) |
| 지름길 오답 가능 쌍 탐색 | **2건 발견** — `test/QQ`↔`bonding_map/QQ`, `bonding_map/AAA`↔`bonding_map/QQ` (회전·면 동일, start 상이) |
| `test/QQ → bonding_map/QQ` | 구: `identity` 무보정 → 신: `derived` + `offset(-11,-13)` + note. 전 셀 균일 어긋남 해소(80셀) |
| `bonding_map/QQ → aa123_a` | `ok`, note `시작좌표(-10,-12)→(1,1)`, 16셀 전부 타깃 격자(29x25) 안 |
| 과잉 보정 대조군 | `QQ → QQ` = `identity` (네 축 동일 시 지름길 유지) |

### 5-3. 검증하지 못한 것 (정직한 한계)

- **`map_doe`/`map_doe_source`의 라이브 동작** — table_config 미적용이라 sqlite 픽스처로만 고정했다. 총괄 적용 후 §5-4 체크리스트 실행 필요.
- **온톨로지 매핑 초안** — materializer 문법·props 병합을 확인하지 않았다(§4-2).
- **HTTP 레이어 재기동 검증** — 재기동 금지 지시로 실행 중인 웹서버는 구 코드다. 라이브 검증은 엔진 함수 직접 호출로 했다.
- **`grid_y_invert`의 라이브 실증 없음** — 메타 161건 전부 `false`라 실데이터로 발화시킬 수 없었다. 단위/조합 테스트(비정방 격자 포함)로만 고정했다. **`true`인 맵이 처음 생기는 시점이 실검증 기회**다.
- **메타가 움직인다** — 사용자가 맵을 편집 중이라 측정 시점마다 메타 집합이 달라졌다(총괄 전달값과 내 실측이 불일치한 이유). 위 수치는 최종 측정 시점 기준이다.

### 5-4. 재기동/적용 후 체크리스트 (총괄·QA용)

1. `GET /api/transfer-plan/stages` → `plan_store == {"doe":"connected","doe_source":"connected"}`
1-bis. 같은 값에 `band_seq` 1·2 두 행을 시딩 후 `validate` → `doe_count == 2`이고 두 구간이 각자 자재를 본다(값당 1행으로 뭉개지지 않음)
2. `GET /api/transfer-plan/validate?ref_table=bonding_map&map_key=aa123_a` → 200, `stage:"bonding"`, `painted_values` 3종, `map_status:"connected"`
3. `GET /api/transfer-plan/validate?ref_table=test&map_key=AAA` → 200, `stage:null`, `status:"unverified"`, `stage_unknown` 경고 (404 아님)
4. `GET /api/maps/overlay?target_table=bonding_map&target_key=aa123_a&sources=test:AAA` → `status:"ok"`, 셀 좌표가 29x25 격자 안
5. `GET /api/maps/overlay?target_table=sample_map&target_key=aa123_a&sources=bonding_map:b1` → 구 `unresolvable` 조합이 이제 `ok`
5-bis. `GET /api/maps/overlay?target_table=bonding_map&target_key=QQ&sources=test:QQ` → `origin:"derived"`, `offset:{-11,-13}`, `note`에 `시작좌표` 포함 (구 코드는 `identity`로 무보정 통과했다)
6. 인덱스 스크립트 실행 후 `pg_indexes`로 `idx_map_doe_ref_map` 물리 확인(스크립트 `[ok]`만 믿지 않는다)

---

## §6. 미해결 / Escalation

| # | 항목 | 판단 요청 |
|---|---|---|
| ~~E1~~ | ~~한 value에 STACK 구간이 여러 개~~ → **개정 2에서 해소.** bk에 `band_seq` 추가로 `(값, 구간)`이 행 단위가 됐고 자재 묶음이 구간 아래로 내려갔다. 별도 테이블 없이 2종 유지(§4-1). 회귀 4건 고정 | ✅ 완료 |
| E2 | `paint_lock.transfer_plan_map`의 `from_overlay` 규칙을 어느 실맵에 옮길지(§2 말미) | 총괄 지시 |
| E3 | `map_doe`와 `map_split_registry`가 **같은 그래프 노드**를 공유하는 온톨로지 설계(§4-2) | 온톨로지 담당 확인 |
| E4 | `total_layers`(총 층수)의 소속 — 시안 §8-③ 미해결. 계획 헤더가 사라져 주인이 없다. 후보: `wafer_map_metadata` 확장 / base 노드 속성 / stage config | 총괄 |
| E5 | 소스 사용 영역(`load_source_region`)은 **휴면 유지**. 키만 v2로 이동했고 라이브 바인딩은 여전히 미선언. 자재 맵 왕복 UX 확정 후 살릴지 결정 | 총괄 |
| E6 | `validate` 확장·경고 신설·교차 초과배정 판정은 **지시대로 하지 않았다**(기존 것만 새 키로 재배선) | — |
| **A2** | **선언(override) 경로는 여전히 구 산술**이다 — `bonding_plan.make_align_transform`(`:199-204`)에 바운딩박스 항이 없다. 라이브는 `__example_` 오버라이드뿐이라 휴면이지만 **오버라이드를 한 줄 선언하는 순간 부활**한다. QA 지정 후속 백로그(이번 범위 밖) | 별도 배치로 처리 필요 |
| A3 | REST 재검증 미완 — 실행 중 서버가 구 코드다(§1-13). 재기동 후 §5-4 확인 필요 | 총괄 |

---

## §7. 히스토리 초안 (총괄 통합 시 사용)

**파일명 후보**: `docs/history/20260726_HHMMSS_transfer_plan_v2_map_identity_and_overlay_frame_compose.md`

> 전사 계획을 별도 개체에서 **"지금 열어 편집 중인 맵"** 으로 재정의했다(사용자 확정). 계획 정체성이 `plan_id`에서 `(ref_table, map_key)`로 이동하고, stage는 `stages.*.target_map.table` 역인덱스로 유도되며, 페인팅 결과가 곧 대상 맵 자신의 셀이 되어 계획 헤더(`transfer_plan`)와 계획 맵 사본(`transfer_plan_map`)이 폐기됐다. DOE는 `map_split_registry`와 같은 키 관례를 이어받은 형제 테이블 `map_doe`로 옮겼는데, 행의 단위는 값이 아니라 **`(값, STACK 구간)`** 이다 — 한 값이 여러 구간을 갖는 것이 사용자 요구의 기본형이기 때문이다(`A|H1~H2`, `A|H2~H3`). "한 매당 500칩이면 4매 묶어 투입"이라는 실제 운용에 맞춰 소스를 **묶음(pool)** 으로 모델링하고 `map_doe_source`를 구간 아래에 뒀다(구간마다 다른 자재 조합이 가능하다). 구간 정체는 정수 서수 `band_seq`가 지고 자유 텍스트 표기 `stack_band`는 비키 컬럼으로 뺐다 — 키 조립이 구분자를 이스케이프하지 않고 키 컬럼 변경이 곧 re-key라, 라벨을 키에 두면 구간 이름을 고치는 순간 자재 묶음이 고아가 되기 때문이다.
> 함께 라이브 오버레이 실패를 고쳤다. 원인은 지목됐던 "메타 조회가 map_id만 매칭"이 **아니라**(서버는 이미 `(target_table, map_id)` 쌍 조회였다 — 그 결함은 클라 `map_editor.js`에 있다), `wafer_map_metadata.grid_cols/rows`가 **물리 치수**인데 변환기에 **프레임 치수**로 넘어가 회전 270 맵이 치수 모순으로 오판된 것이었다. 국소 수정 대신 각 맵을 자기 메타로 물리 좌표에 사상 후 합성하는 방식으로 바꿔, 구 QA B3의 "면 반전 + 타깃 회전 90/270 명시 거절" 한계(16조합)까지 함께 해소했다. 오버레이 좌표 바인딩도 `table_config`에서 자동 유도하도록 바꿔, 선언 없는 맵이 조용히 실패하던 구조를 없앴다.

---

## §8. 교훈 제안 (`agent_workspace/memory/server-pm.md` 반영 후보 — 총괄 검수 후)

- **함정**: 상위 에이전트/사용자가 원인을 "확정"으로 전달해도 그 결함이 코드에 없을 수 있다. 지목된 자리를 고치면 진짜 원인이 남고, 무해한 수정이 "고쳤다"는 오해까지 만든다(본 건: 메타 조회는 이미 쌍 필터였고 실제 원인은 격자 치수 규약 혼동이었다 — 두 맵의 회전이 우연히 같아 오인이 성립했다).
  **올바른 방법**: 수정 전에 **실패 메시지 자체를 원인 가설의 반증에 쓴다.** "그 가설이 맞다면 이 에러는 나올 수 없다"가 성립하면 가설을 버린다. 검증 생략 지시가 있어도 5분짜리 라이브 재현은 한다.
- **함정**: 좌표계 메타에 "치수"가 하나뿐이면 물리(canonical)와 프레임(visual) 중 어느 쪽인지가 호출부마다 갈리고, 정방 격자·무회전 데이터에서는 **오래도록 발현하지 않다가** 회전 맵이 하나 생기는 순간 정상 조합이 거절된다.
  **올바른 방법**: 치수를 넘기는 함수는 시그니처·docstring에 **어느 좌표계의 치수인지 명시**하고, 변환 헬퍼(`_grid_of` vs `_frame_grid_of`)를 이름으로 분리한다.
- **함정**: "선언된 것만 동작"하는 config 게이트는 범용 기능(임의의 맵을 겹친다)과 구조적으로 충돌한다 — 신규 대상이 생길 때마다 조용히 실패하고 사용자는 기능이 고장 났다고 느낀다.
  **올바른 방법**: 이미 있는 선언(`table_config`)에서 **유도를 정본으로** 삼고 config 선언은 **예외 보정용**으로 강등한다. 유도 실패는 관례로 추측하지 말고 "무엇을 선언해야 하는지" 알려주는 명시 실패로 낸다.
- **함정**: "조용한 오답 대신 명시 거절" 가드는 옳지만, 근본 수정 없이 오래 두면 **정상 조합까지 거절**해 사용자에게는 버그로 보인다.
  **올바른 방법**: 거절 가드를 넣을 때 그 가드를 해제할 **근본 수정의 기준 테스트**를 함께 남긴다(본 건은 구 테스트 docstring이 그 역할을 해서 전환이 즉시 가능했다).
- **함정**: 사용자가 편집하는 **자유 텍스트를 복합 business key에 넣으면** 두 가지가 동시에 터진다 — ①`crud`의 bk 조립이 구분자를 이스케이프하지 않아 값에 구분자가 섞이면 서로 다른 행이 같은 키가 되고 ②키 컬럼이 바뀌면 행이 re-key되므로 **라벨을 고치는 순간 하위 자식 행이 전부 고아**가 된다. 정규화(치환)는 ①을 ②의 충돌로 바꿀 뿐 해결이 아니다.
  **올바른 방법**: 정체성은 **불변 서수/코드**(정수 `*_seq` 등)가 지고, 사람이 읽는 표기는 **비키 컬럼**에 둔다. 새 복합 키를 설계할 때 "이 컬럼을 사용자가 나중에 수정하는가"를 먼저 묻고, 답이 예면 키에서 뺀다.
- **함정**: 저장 좌표의 규약을 **일부만** 역산하면(예: `start`는 되돌리고 바운딩박스 크롭은 빠뜨림) 두 항이 우연히 상쇄되는 조합에서는 정답이 나와 오래 안 들킨다. 거울·회전으로 부호가 뒤집히는 순간에만 가산되어 틀린다.
  **올바른 방법**: 좌표 왕복은 **손으로 옮겨 쓰지 말고** 저장 측과 동일한 변환기 함수를 호출한다(`visual_to_physical`/`physical_to_visual`). 규약이 세 항 이상이면 손으로 옮긴 버전은 반드시 한 항을 빠뜨린다 — 실제로 y반전 항도 `max_r - (yv-start)`를 `(rows-1) - r`로 잘못 옮겼고 bbox가 0일 때만 우연히 같았다.
- **함정**: **단사·범위·왕복 항등은 균일 오프셋을 원리적으로 검출하지 못한다.** 전부 같은 함수의 자기 대조라 `f`가 통째로 밀려 있어도 참이다. 조합 수(1024쌍)를 늘려도 검출력은 0이다.
  **올바른 방법**: 좌표 변환 회귀는 **구현 밖에서 온 정답**(저장 규약을 독립 서술한 오라클)과 대조한다. 그리고 **결함 버전을 주입해 테스트가 실제로 실패하는지 증명**한다 — 통과만 하는 테스트는 회귀 테스트가 아니다.
- **함정**: 회귀 픽스처가 결함 축을 **활성화하지 않으면** 조합을 아무리 늘려도 못 잡는다(300mm/7mm 6x6은 웨이퍼 원이 격자를 안 잘라 `minC=0` → bbox 항이 사라진다).
  **올바른 방법**: 픽스처를 고를 때 "이 값에서 문제의 항이 0이 되는가"를 먼저 확인하고, 0이 아닌 픽스처를 **반드시 하나** 넣는다. 나아가 **테스트가 자기 픽스처의 유효성을 스스로 검사**하게 한다(`assert bbox(rot0) != bbox(rot90)`) — 죽은 픽스처를 구조적으로 차단한다.
- **함정**: "오라클을 만들었다"가 곧 독립을 뜻하지 않는다. **어느 한 계층에서라도 검증 대상과 같은 코드/파라미터를 쓰면 그 계층의 결함은 원리적으로 통과**한다(본 건: 모듈 함수는 안 불렀지만 `PhysicalWaferEngine`을 같은 인자로 생성 → bbox 계층이 복사본이었고 결함이 정확히 거기 있었다).
  **올바른 방법**: 오라클은 **호출 그래프 전체가 분리**돼야 한다. "무엇을 import 하는가"를 목록으로 확인하고, 공유 클래스가 있으면 산술을 직접 옮겨 쓴다. 그리고 **결함 버전을 주입해 오라클이 실제로 잡는지** 매번 증명한다.
- **함정**: 대칭 파라미터(`chip_x == chip_y`, offset 0, 정방 격자)는 축 스왑·부호 반전 결함을 전부 가린다 — "조합을 다 돌았다"는 착각을 만든다.
  **올바른 방법**: 좌표계 회귀 픽스처는 **모든 축을 비대칭으로** 잡는다(이방성 피치 · 0이 아닌 오프셋 · 비정방 격자 · 비대칭 start). 대칭 값은 대조군으로만 쓴다.
- **함정**: 같은 결함이 **한 계층 아래로 이동**할 수 있다(좌표 합성 → bbox 산출 → 엔진 파라미터). 상위에서 고쳤다고 계열이 닫히지 않는다.
  **올바른 방법**: 수정 후 "이 값이 어디서 오는가"를 **최종 입력까지** 따라가 계층마다 규약 일치를 확인한다. 저장 규약이 있는 값은 **저장된 실데이터로 예측을 반증**해 보는 것이 가장 확실하다(본 건: 저장 좌표 범위가 서버 예측을 반증했다).
- **함정**: Windows에서 Python 텍스트 모드로 파일을 재기록하면 줄바꿈이 CRLF로 조용히 바뀐다 — `git diff`는 autocrlf로 정규화해 "변경 없음"으로 보여주는데 디스크 바이트는 달라져 있다.
  **올바른 방법**: 원복 목적의 재기록은 `newline=""` 또는 바이너리 모드로 하고, 원복 검증은 `git diff`가 아니라 `git status`로 한다(본 건은 `git checkout --`로 정리).
- **함정**: 좌표 변환에서 **빠른 경로(identity 지름길)의 판정 조건이 변환 본체보다 좁으면**, 본체가 이미 처리하는 축까지 통째로 건너뛴다. 본체 코드만 읽으면 "start를 처리하고 있다"로 보여 결함이 안 보인다(본 건: `make_frame_transform`은 start를 처리했는데 `resolve_align`의 지름길이 그 호출 자체를 없앴다 — 게다가 같은 함정이 `get_overlay`의 `align.is_identity` 검사로 한 겹 더 있었다).
  **올바른 방법**: 지름길 조건은 **변환이 보는 축 전부**를 하나의 튜플(`frame_axes()`)로 만들어 완전 일치로만 판정한다. 축을 추가할 때 그 튜플 한 곳만 고치면 모든 지름길이 자동으로 좁아진다.
- **함정**: "축이 누락됐다"는 보고를 받으면 축 처리 코드부터 찾게 되는데, 실제로는 **누가 그 코드를 안 부르는가**가 원인일 수 있다.
  **올바른 방법**: 라이브 메타를 **쌍으로 전수 대조**해 "결함이 발현하는 조합이 실제로 존재하는가"를 먼저 센다(본 건: 161건 중 오답 쌍 2건을 특정해 수정 전후 좌표 차이를 실측으로 제시할 수 있었다).
- **함정**: 사용자 요구 스케치의 **행 반복**(같은 값이 여러 줄에 등장)을 "값 단위 1행"으로 축약해 스키마를 잡으면, 라이브 테이블을 만든 직후 키를 다시 바꿔야 한다.
  **올바른 방법**: 스키마 확정 전 요구 스케치에서 **무엇이 행의 단위인가**(어느 컬럼 조합이 반복되는가)를 먼저 못 박는다. 시안 문서의 본문 예시(§3.3의 값당 1구간)와 상세 예시(§3.5의 값당 N구간)가 어긋나면 **더 넓은 쪽**을 스키마 기준으로 삼는다 — 넓은 키를 좁히는 것은 쉽고 그 반대는 마이그레이션이다.
