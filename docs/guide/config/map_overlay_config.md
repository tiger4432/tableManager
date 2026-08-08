# `map_overlay_config.json` 세팅 — 맵 오버레이 바인딩 + 페인트 잠금 + 프리셋 라우팅

> **Status:** 🟢 Living | **Last-verified:** 2026-08-08 (🔴 **`alignment` 블록의 키 셋이 이 문서에 없었습니다** — `alignment.index.*`·`alignment.value_weights`·`alignment.sides[]`. 셋 다 로더와 경고 경로와 **실제 동작 결과**를 갖고 있고, 특히 `sides`는 잘못 좁히면 정답을 후보에서 지웁니다. §5에 등재) | **Owner:** Backend / UI-Map
> 상위: [폴더 인덱스](./README.md) · 정렬 계약의 정본은 [MAP_EDITOR_SPEC §5](../../spec/MAP_EDITOR_SPEC.md)

<!-- Loader evidence (2026-07-28):
  load: server/map_overlay.py:85 load_overlay_config (missing -> {} = full default operation)
  per-request read (no module cache)
  binding auto-derivation rationale: map_overlay.py:561 / underivable-table error: :680
  paint_lock consumer: GET /api/maps/paint-rules (client applies, no hardcoding)
  [U6] default_legend / value_column_candidates: resolvers map_overlay.py
  resolve_value_column_candidates / get_default_legend, served via same paint-rules endpoint
  [F1/F2 2026-07-28] resolved binding served: resolve_binding_info map_overlay.py:593
  (source: declared|derived|fallback_guess); candidate-miss guess refused in data paths
  [F5 2026-07-30] preset_routing: reader server/map_preset_routing.py
  (resolve_routing_config / resolve_preset_routing), served via
  GET /api/maps/preset-routing?table=&map_key=; preset bodies still come from maps.json
-->

## 1. 언제 이 파일을 만지는가

- **컬럼명이 관례 밖인 테이블을 오버레이에 올릴 때** (예: `dt_log`의 `tx/ty`) — **관례 안이면 만질 필요 없습니다.** 선언 없이도 오버레이는 동작합니다(`table_config`의 `map_key_columns` + x/y/val 후보에서 자동 유도)
  - ⚠️ **값 컬럼도 후보 매칭이 필수**입니다(F2, 2026-07-28): `value_column_candidates`에 하나도 안 맞으면 유도는 **거부**합니다(과거의 "첫 데이터 컬럼 추측"은 데이터 경로에서 제거 — 오버레이는 `source_missing`, 수량 유도는 `missing`으로 정직하게 강등). 값 컬럼명이 후보 밖(대문자 `VAL` 등)이면 `table_bindings`에 선언하십시오.
- **페인트 잠금 규칙을 바꿀 때** — 어떤 값 위에 칠할 수 없는지, 잠금 판정을 어느 오버레이 소스에서 가져올지
- **[U6] 레지스트리 행이 없는 맵의 기본 legend를 선언할 때** (`default_legend`) — 미선언이면 기본 의미론 없음(클라는 bare 값을 팔레트 색으로 렌더)
- **[U6] 값 컬럼 자동 탐지 순서를 바꿀 때** (`value_column_candidates`) — 미선언이면 서버 문서화 기본 적용
- **[F5] 맵을 열 때 적용될 물리 규격(프리셋)을 자동으로 정하고 싶을 때** (`preset_routing`) → **[§2-bis](#2-bis-f5-로드-시-프리셋-라우팅-선언)**. 미선언이면 종전과 같이 패널에 남아 있던 설정이 쓰입니다
- **맵 정렬 화면이 「잠정 순위」라고 말할 때** (`alignment`) — 이 블록이 없어도 서버는 **순위를 냅니다**(2026-08-06 제품 소유자 지시로 뒤집힘). 개발 기본값 **1/1**로 매기고, 판정에 `thresholds_defaulted`와 `잠정 순위 - 판정 기준값 미선언 · 기본값 1`을 실어 **선언으로 매긴 순위와 구별되게** 내보냅니다. 고장이 아니라 선언 요청인 것은 종전과 같고, 달라진 것은 **조작자가 그 요청을 읽는 동안 기계가 멈추지 않는다**는 점입니다.
  - 🔴 **잠정 표가 붙은 순위를 그대로 확정하지 마십시오.** 기본값 1은 「이 격차가 의미 있다」는 주장이 아니라 「아무도 아직 그 기준을 말하지 않았다」는 뜻입니다.
  - 🔴 **여기에 적을 숫자는 옮겨 적는 것이 아니라 유도하는 것입니다.** 기준 맵(유효 다이 floor)이 실제로 프레임을 몇 다이로 가르는지가 상한이고, 그보다 작은 격차는 기준 자신의 분해능 아래라 방위의 증거가 될 수 없습니다. `server/scripts/seed_valid_die_ref_floor.py`(dry-run 기본)가 쓰는 floor에 대해 그 값을 `discriminates: worst N dies`로 보고하므로, 그 N을 출발점으로 삼으십시오. **다른 floor를 쓰면 다시 재십시오.**

## 2. 세팅 절차

1. **스냅샷**: `conda run -n assy_manager python server/scripts/backup_config.py snapshot`
2. **전제 확인**: `table_bindings`·`paint_lock`의 키는 전부 `table_config.json`에 선언된 테이블명이어야 합니다.
3. 파일이 없으면 `map_overlay_config.json.sample` 복사. 관례 밖 컬럼 테이블만 바인딩 선언:

   ```json
   "table_bindings": {
     "dt_log": {
       "columns": { "x": "tx", "y": "ty", "val": "core_lot", "key_columns": ["tape_lot", "tape_slot"] }
     }
   }
   ```
4. 페인트 잠금은 `"*"` 기본 선언 + 테이블별 오버라이드가 **머지**됩니다(기본값은 `F` 잠금):

   ```json
   "paint_lock": {
     "*": { "enabled": true, "blocking_values": ["F"], "from_overlay": [], "message": "이 셀은 잠금 값이라 페인팅할 수 없습니다." },
     "bonding_map": {
       "enabled": true, "blocking_values": ["F"],
       "from_overlay": ["core_defect_map", "eds_fail_map"],
       "message": "불량 칩 위치라 배정할 수 없습니다 (오버레이 기준)."
     }
   }
   ```
5. **정렬(align)은 이 파일에서 세팅하지 않습니다** — `align_overrides`는 폐지(2026-07-27)됐고 남아 있어도 무시됩니다(테스트로 고정). 정렬을 켜는 방법은 소스·타깃 맵의 **`wafer_map_metadata` 메타 등록**입니다.
6. **[U6] 맵 기본값 두 키는 선택 선언**입니다 — 클라는 하드코딩 없이 `GET /api/maps/paint-rules` 응답만 소비합니다:

   ```json
   "default_legend": [
     { "value": "1", "desc": "GOOD", "color": "#10b981", "locked": false }
   ],
   "value_column_candidates": ["val", "value", "leg", "grade", "result", "code", "split", "doe"]
   ```

   - `default_legend`: 레지스트리(`map_split_registry`) 행이 없는 맵이 받는 legend 행. **선언한 배열이 그대로** 쓰입니다(서버가 행을 지어내지 않음). 키가 없으면 응답에 `null` — 기본 의미론 없음.
     - ⚠️ **`default_legend: []`(키는 있고 빈 배열)는 `null`이 아니라 `[]`로 서빙**됩니다 — 클라는 빈 배열을 "선언 행 없음"으로 취급해 시드 폴백(VALUE 1 빈 행 하나)으로 갑니다. 사용자 관찰 동작은 미선언과 같지만 응답 값이 다르니, 반영 확인을 응답 필드로 할 때 혼동하지 마십시오.
   - `value_column_candidates`: 값 컬럼 자동 탐지의 **순서 있는** 후보 목록(앞선 것 우선). 미선언 시 문서화 기본 `[val, value, leg, grade, result, code, split, doe]`. 선언하면 서버의 바인딩 유도(`derive_table_binding`)도 같은 목록을 따릅니다.
7. 저장 — 반영은 자동(**요청마다 재읽기**).

## 2-bis. [F5] 로드 시 프리셋 라우팅 선언

> **이 절이 운영 전달의 유일한 수단입니다.** ①의 제품코드 조회 테이블은 **운영에만 존재**하므로 개발/검증 환경에서는 그 경로를 실제로 켜 볼 수 없습니다. 코드에 환경 분기는 **없습니다** — 코드는 하나이고 **선언만 다릅니다.**

### 무엇을 정하는가

맵을 열 때 **어떤 물리 규격(프리셋)으로 열지**를 자동으로 정합니다. 지금은 운영자가 기억해서 고르거나, 안 고르면 **패널에 남아 있던 이전 맵의 설정**이 그대로 적용됩니다. 틀린 규격으로 열리면 `inside`가 달라지고, `inside`가 달라지면 **저장 가능한 셀 집합이 달라져** 대조 게이트에서 거부됩니다.

**같은 테이블 안에서도 맵 키에 따라 프리셋이 다릅니다** — 제품마다 랏 이름 형식이 다르기 때문입니다. 그래서 라우팅은 테이블 단위가 아니라 **맵 키(의 lot 조각) 단위**로 답합니다.

### 해석 순서 — 순서가 계약입니다

```
맵 키 → (키 컬럼에서 lot 추출) → ① product_lookup(제품코드 조회 테이블) → product_presets → 프리셋
                                      │ 행 없음 (정상!)
                                      ▼
                                  ② rules (순서 있는 텍스트 패턴, 첫 매치 승리) → 프리셋
                                      │ 매치 없음
                                      ▼
                                  ③ 라우팅 없음 — 지금 동작 그대로 (아무 프리셋도 고르지 않음)
```

### 절대 우선순위: 저장된 규격 > 라우팅 > 패널

이미 `wafer_map_metadata`에 규격이 등록된 맵에는 **라우팅이 적용되지 않습니다**(응답 `status: "meta_present"`). 메타가 정렬의 유일한 기준이고, 규격을 덮으면 `inside`가 바뀌기 때문입니다. **서버가 거절하므로 클라가 실수로 덮을 수 없습니다.**

즉 라우팅은 **아직 메타가 없는 맵의 첫 열기 기본값**입니다. 그 맵을 한 번 Push하면 메타가 생기므로 두 번째부터는 자동으로 안 걸립니다 — 별도의 잠금 스위치가 필요 없습니다.

### 선언 (모든 키 선택 — 필요한 것만 쓰십시오)

```json
"preset_routing": {
  "dt_map": {
    "lot_key_part": "lot",

    "product_lookup": {
      "table": "product_master",
      "key_column": "lot",
      "value_column": "product_code"
    },
    "product_presets": {
      "AB12": "CORE",
      "CD34": "BASE"
    },

    "rules": [
      { "name": "tape lots", "match": "prefix", "value": "T",         "preset": "TAPE" },
      { "name": "core lots", "match": "regex",  "value": "^C[0-9]{2}", "preset": "CORE" }
    ]
  }
}
```

- **`product_lookup`은 선택이고, 미선언이 정상 구성입니다.** 조회 테이블이 없는 환경(개발·검증)에서는 이 블록을 **빼십시오.** ②만으로 완전히 동작합니다.
- 운영에서 ①을 켜려면: 조회 테이블이 **`table_config.json`에 등록돼 있어야** 합니다(등록 안 된 테이블은 조용히 건너뛰고 ②로 갑니다).
- **조회가 빗나가는 것도 정상입니다.** 그 테이블은 불완전해서 모든 lot이 들어 있지 않습니다. 경고를 띄우지 않고 조용히 ②로 넘어갑니다.
- `preset` 값은 **`maps.json`의 프리셋 키 또는 `name`** 입니다(키 우선 → 없으면 `name` 정확 일치). `transfer_plan_config`의 `target_map.preset`이 쓰는 것과 같은 참조 형태입니다.
- `lot_key_part` 생략 시 그 테이블 맵 키의 **첫 키 컬럼**을 lot으로 봅니다(`map_key_columns` 또는 `table_bindings[].key_columns`의 첫 항목).

### 규칙(`rules`) 규격

| 키 | 필수 | 의미 |
|---|---|---|
| `name` | 권장 | 응답 `matched_by.rule`에 실려 화면에 표시됩니다. 생략 시 `#0`, `#1` … |
| `match` | **필수** | `equals` \| `prefix` \| `suffix` \| `contains` \| `regex`. **기본값 없음** — 생략하면 그 규칙은 버려집니다(무엇을 뜻했는지 서버가 추측하지 않습니다) |
| `value` | **필수** | 비교할 문자열(또는 `regex`의 패턴). 최대 200자 |
| `preset` | **필수** | `maps.json`의 프리셋 키 또는 `name` |
| `enabled` | 선택 | `false`면 조용히 제외(기본 `true`) |

- **첫 매치가 이깁니다.** 좁은 규칙을 위에, 넓은 규칙을 아래에 두십시오.
- **대소문자를 구분합니다.**
- 잘못된 규칙(알 수 없는 `match`, 컴파일 안 되는 정규식, `preset` 누락 등)은 **버려지고 서버 로그에 사유가 남습니다.** 고쳐 주지 않습니다.
- 규칙이 매치했는데 그 `preset`이 `maps.json`에 없으면 **다음 규칙으로 넘어가지 않고 거절**합니다(`status: "preset_missing"`). 넘어가면 아무도 고른 적 없는 프리셋이 답이 되고 오타가 영원히 안 보입니다.

### ⚠️ 조회 테이블 인덱스 (1,000만 행 대비)

동적 테이블이 자동으로 갖는 인덱스는 `business_key_val`·`updated_at`뿐입니다. `product_lookup.key_column`이 그 밖의 컬럼이면 **순차 스캔**이 됩니다. 조회 테이블이 크면 인덱스를 직접 만드십시오:

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_product_master_lot ON product_master (lot);
```

서버는 이 조회를 **맵 로드당 1회, `LIMIT 1`**로만 수행하며, 최초 사용 시 로그에 인덱스 권고를 1회 남깁니다(경고 아님).

## 3. 반영 확인

1. `GET /api/maps/paint-rules?table=<t>` — 머지된 잠금 규칙이 기대대로인지. **[U6]** 같은 응답의 `value_column_candidates`가 선언(또는 기본) 순서 그대로인지, `default_legend`가 선언 배열 그대로(미선언이면 `null`)인지.
   - **[F1]** 같은 응답의 `binding`이 그 테이블의 RESOLVED 바인딩인지: `{x, y, val, key_columns[], source}`. `source`는 `declared`(table_bindings 선언) > `derived`(table_config 유도), 해석 불가면 `null`. `fallback_guess`는 **값 컬럼이 후보 밖이라 추측만 남은 상태**라는 경고 표지입니다 — 데이터 경로는 이 추측을 거부하므로, 이게 보이면 선언을 추가하십시오. **에디터도 같은 커밋에서 이 필드를 소비하도록 바뀌었습니다**(클라 자체 유도 삭제): 드롭다운이 이 값으로 미리 선택되고, `fallback_guess`는 **로드 경로에서는 경고 후 진행 / 오버레이 경로에서는 거부**입니다. 즉 **선언만 하면 대문자·한글·숫자 시작 테이블명, `tx`/`ty` 좌표도 그대로 로드·오버레이됩니다** — 종전에 "오버레이 설정이 안 먹던" 원인이 바로 이 클라 측 재유도였습니다.
2. `GET /api/maps/overlay?target_table=<t>&target_key=<k>&sources=<src>:<key>` — `overlays[].status`가 `ok`인지, `align_applied.origin`이 `derived`(메타 유도)인지 `identity`(메타 부재)인지.
   - `identity`는 실패가 아니지만 **메타 미등록 신호**입니다 — 정렬이 필요하면 메타부터 등록.
   - `source_missing` = 테이블 미선언/바인딩 해석 실패.
3. 맵 에디터 화면에서 잠긴 셀에 페인팅 시 선언한 `message`가 뜨는지.
4. **[F5] 프리셋 라우팅**: `GET /api/maps/preset-routing?table=<t>&map_key=<k>`

   | 응답 `status` | 뜻 | 해야 할 일 |
   |---|---|---|
   | `ok` | 라우팅됨. `preset_key`·`preset`(본문)·`matched_by{stage, rule, lot, product_code}` | 없음 |
   | `not_declared` | 이 테이블에 `preset_routing` 선언이 없음(또는 전부 버려짐) | 선언 추가 / 서버 로그에서 버려진 사유 확인 |
   | `no_match` | 선언은 있는데 이 lot에 걸리는 것이 없음 | 규칙 추가. **경고가 아니라 사실 고지입니다** |
   | `meta_present` | 이 맵은 **`wafer_map_metadata`에 행이 있음** → 라우팅 미적용(정상) | 라우팅을 검증하려면 **메타가 없는 맵**으로 확인하십시오. 🔴 **판정은 「행이 있는가」이지 「그 행을 쓸 수 있는가」가 아닙니다**(`map_overlay.load_map_meta(...) is not None`) — 2026-08-05 `98b48e9`부터 **클라는 START X,Y를 읽을 수 없는 행을 통째로 버리고 「선언 없음」으로 흘리므로**, 그런 맵에서는 클라가 라우팅을 부르는데 여기서 `meta_present`가 나옵니다. 에러가 아니라 **침묵**입니다(총괄 판정 대기 → [MAP_EDITOR_SPEC §5.8-bis](../../spec/MAP_EDITOR_SPEC.md)) |
   | `preset_missing` | 규칙은 걸렸는데 그 프리셋이 `maps.json`에 없음 | `matched_by.rule`이 가리키는 규칙의 `preset` 오타 수정 |
   | `unresolvable` | 맵 키를 분해할 수 없음(맵 테이블이 아니거나 `lot_key_part`가 키 컬럼이 아님) | `table_bindings`/`map_key_columns` 확인 |

   - **①의 결과는 `lookup` 필드로만 드러납니다**(로그로 소리치지 않습니다): `{declared, status, product_code}`.
     `status`는 `not_declared`(미선언 — 이 환경의 정상) · `hit` · `miss`(행 없음 — **정상**) · `unmapped`(코드는 찾았으나 `product_presets`에 없음) · `table_absent`(선언한 테이블이 등록 안 됨 — **운영 밖에서 정상**) · `column_absent` · `no_key` · `error`(쿼리 자체 실패 — 이것만 경고 로그).
   - **운영 선언을 검증하는 창은 이 필드뿐입니다.** ①이 안 켜지는 것 같으면 `lookup.status`를 먼저 보십시오.

## 4. 잘못됐을 때

```bash
conda run -n assy_manager python server/scripts/backup_config.py restore map_overlay_config_<yymmdd>.json.bak --yes
```

요청마다 재읽으므로 복원 즉시 반영 → [ROLLBACK_PROCEDURE](../ROLLBACK_PROCEDURE.md).

## 5. 키 참조

```
alignment.{min_margin_dies, min_discriminating_dies}
alignment.index.{min_margin_dies, min_discriminating_dies}
alignment.value_weights.<값> = <무게>
alignment.sides[]
table_bindings.<table>.columns.{x, y, val, key_columns[]}
paint_lock."*".{enabled, blocking_values[], from_overlay[], message}
paint_lock.<table>.{enabled, blocking_values[], from_overlay[], message}
default_legend[].{value, desc, color, locked}
value_column_candidates[]
preset_routing.<table>.{enabled, lot_key_part}
preset_routing.<table>.product_lookup.{table, key_column, value_column, enabled}
preset_routing.<table>.product_presets.<product_code> = <preset key|name>
preset_routing.<table>.rules[].{name, match, value, preset, enabled}
```

| 키 | 의미 |
|---|---|
| `alignment.min_discriminating_dies` | 맵 정렬 채점(`GET /api/maps/alignment/view`)이 **결정할 근거가 있다**고 볼 최소 판별 다이 수. 🔴 **미선언 = 잠정 순위**(개발 기본값 1, 판정에 `thresholds_defaulted`·`provisional_text` 동반). 0이 아니라 1인 것이 요점입니다 — 0으로 접으면 「구별 못 함」이 「자신 있는 1등」이 되고, 1은 코드가 이미 깔고 있던 바닥이라 순위를 바꾸지 않고 **출처만** 붙입니다 |
| `alignment.min_margin_dies` | 1위가 2위보다 앞서야 할 최소 다이 수. 위 키와 **서로를 대신하지 않습니다** — 판별 3다이 위의 큰 격차도, 판별 500다이 위의 1다이 격차도 결정이 아닙니다. 단위는 **다이 개수**이며 백분율이 아닙니다(적합도 %는 실측에서 순위를 뒤집었습니다 — `MAP_ALIGNMENT_SPEC` §3) |
| `alignment.index.*` | [2026-08-08 등재] 순번(`dt_index`) 축의 문턱. 🔴 **위 두 키와 일부러 키를 공유하지 않습니다** — 조작자가 다른 문제를 쫓다 점유 문턱을 낮추면(실제로 2026-08-05에 20→1로 내려간 적이 있습니다) 공유 키였다면 그 한 번의 조작이 **순번 축의 안전망까지 같이 걷어 갑니다.** 🔴 **미선언 또는 반쪽 선언 = 이 축은 순위를 가져가지 않습니다**(`ruling.index_axis='reported'` — 수치는 실어 보내되 순위는 안 냅니다). **둘 다 있어야 선언**이고 하나만 적은 것은 절반의 안전망이지 선언이 아닙니다. 판정이 `absent`면 순번을 실은 셀이 아예 없다는 뜻이고, 그때 거절 문구는 마진이 아니라 **값 부재**를 말합니다([MAP_ALIGNMENT_SPEC §6](../../spec/MAP_ALIGNMENT_SPEC.md)). ⚠️ **출하 config는 20/20을 선언하고 있고, 그 20은 이 박스의 *합성* 시드에서 유도됐습니다**(`server/scripts/seed_dt_index_walk.py`의 `SYN-IDX-*`). **운영 측정이 아닙니다** — 운영으로 옮기기 전에 그 데이터에서 **다시 유도**하십시오. 🔴 **낮추지 마십시오**: 20 미만이면 core 보행의 4/88이 순위를 받고, 실측에서 그 1등은 8후보 중 2건에서 **틀린 프레임**이었습니다 |
| `alignment.value_weights` | [2026-08-08 등재] `{값: 무게}`. **선언된 값만** 담고 미선언 값은 기본 1을 받습니다. 🔴 **`0`은 선언이고 없는 키는 선언이 아닙니다** — `{"1": 0}`은 「이 값은 세지 말라」는 주장이고, 둘을 한 낱말로 접으면(`or 1`) 「무시하라」가 조용히 「보통 무게」가 됩니다. 음수·무한·NaN은 선언으로 받지 않습니다(음수는 「맞은 것이 반증」이 되어 합계를 음수로 만듭니다). **문턱과 같은 블록에 사는 것이 설계**입니다 — 정렬 판정을 조율하는 자리가 둘이면 한쪽만 배포되는 날이 옵니다 |
| `alignment.sides[]` | [2026-08-08 등재] 채점할 **면**만 좁힙니다(어휘 `front`/`back`). 🔴 **미선언은 한쪽을 뜻하지 않습니다 — 미선언 = 둘 다**입니다. 탐색 공간을 좁히는 것은 **장비에 대한 주장**이고 주장은 선언에서 나와야지 기본값에서 상속되면 안 됩니다. ⚠️ **이 축의 `back`은 「거울」이지 물리 뒷면이 아닙니다** — 순번 축에서 `rotθ_back`은 「우상단부터 번호를 매기는 설비」와 같은 뜻이라, `["front"]`로 좁히면 **그 설비의 정답이 후보에서 통째로 사라집니다**(실제로 그랬습니다 — [MAP_ALIGNMENT_SPEC §2.4](../../spec/MAP_ALIGNMENT_SPEC.md)). 읽히지 않는 선언(리스트 아님·빈 배열·모르는 면)은 선언이 아니라 **미선언으로 강등**되고 경고가 남습니다. HEAD 실측: 실 config에 **선언 0건** |
| `table_bindings.<table>.columns` | 그 테이블을 맵으로 읽을 때의 좌표/값 컬럼. `key_columns`는 맵 인스턴스 식별 컬럼. 🔴 **정렬 화면에서는 제안(preset)입니다** — `/api/maps/alignment/view`의 `x_col`/`y_col`/`value_col`이 원시 단위이고, 생략했을 때만 이 선언이 채웁니다(응답 `unit.columns`가 `chosen`/`proposed`를 구별) |
| `default_legend[]` | [U6·선택] 레지스트리 행 없는 맵의 기본 legend 행(선언 그대로 서빙, 미선언 = 응답 `null` = 기본 의미론 없음) |
| `value_column_candidates[]` | [U6·선택] 값 컬럼 자동 탐지 순서(앞선 것 우선). 미선언 = 문서화 기본. 응답에는 항상 RESOLVED 값 |
| `paint_lock.<t>.enabled` / `blocking_values[]` | 잠금 on/off · 이 값이 있는 셀은 페인팅 불가 |
| `paint_lock.<t>.from_overlay[]` | 잠금 판정을 자기 셀이 아니라 나열된 오버레이 소스의 셀에서 가져옴 |
| `paint_lock.<t>.message` | 차단 시 사용자 문구 |
| `preset_routing.<t>.product_lookup` | [F5·선택] 제품코드 조회 테이블 선언(①). **미선언이 정상 구성** — 이 환경엔 조회 테이블이 없습니다. 미선언/빗나감/테이블 부재 모두 조용히 ②로 |
| `preset_routing.<t>.product_presets` | [F5·선택] 제품코드 → 프리셋(키 또는 `name`) 사전. ①의 답 |
| `preset_routing.<t>.rules[]` | [F5·선택] **순서 있는** 텍스트 패턴 규칙(②), 첫 매치 승리. `match` 필수(`equals`/`prefix`/`suffix`/`contains`/`regex`), 대소문자 구분 |
| `preset_routing.<t>.lot_key_part` | [F5·선택] 맵 키에서 lot을 담은 키 컬럼. 생략 시 첫 키 컬럼 |
| ~~`align_overrides`~~ | 🗑️ 폐지 — 무시됨 |

- 계획 맵 사본(`transfer_plan_map`)은 폐기 — 계획 캔버스의 잠금은 그 stage의 `target_map` 테이블에 직접 선언.
- `GET /api/maps/overlay`의 `eqp` 파라미터는 no-op 존치.
- 맵 에디터 클라는 `7d931dc` 이후 서버 오버레이 좌표를 소비하지 않고 변환을 자체 수행 — 서버 응답으로 클라 화면을 검증하지 마십시오.
