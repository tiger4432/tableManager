# `transfer_plan_config.json` 세팅 — M2 Universal Transfer Plan

> **Status:** 🟢 Living | **Last-verified:** 2026-08-04 (`2c2a777`+`101311f`: 보조 역할(`transfer_log`·`origin_log`·`fail_sources`·`process_history`) 선언이 **선택**이 됨 — 키 부재는 `missing`이 아니라 `not_declared`(강등 아님)이고 가용이 숫자로 나가며, 빠진 감산 종류는 `inactive_subtractions`가 명시. `total_chips`는 예외로 계속 필수. 직전 `deed6d2`: self-frame fail 원천의 좌표 없는 바인딩도 `connected(count_only)` 강등 — fail_sources 함정 ⑤) | **Owner:** Backend / UI-Map
> 상위: [폴더 인덱스](./README.md) · **의미론(zone 모델·`stack` string·`bin_map`·`bands` 폐기)의 정본은 [CONFIG_GUIDE §5.8](../CONFIG_GUIDE.md)** · 동작 계약은 [MAP_EDITOR_SPEC §6](../../spec/MAP_EDITOR_SPEC.md)

<!-- Loader evidence (2026-08-04, availability relaxation pass — anchors re-measured):
  load: server/transfer_plan.py:265 load_transfer_plan_config (missing/corrupt -> {})
  per-request snapshot: server/main.py:4366/:4406/:4449
  registry required roles: transfer_plan.py:166 REGISTRY_ROLES = (ref_table, map_key, value, stack, mat_1h, mat_mid, mat_top) / legacy: :169 bands
  source_config_ref allowed: transfer_plan.py:147 M1_SOURCE_REFS = ("bonding_plan",)
  stage role resolution: transfer_plan.py:385 _stage_role_statuses / bin_map lookup: :773 _bin_axis_binding / lot_membership: :1054 _lot_slots
  degradation engine: :488 _status_is_degraded / :511 _degradation_effect / :525 assess_degradation / chips gate: :564 build_chips_block
  relaxation (2026-08-04, 2c2a777 + 101311f): bonding_plan.py:53 STATUS_NOT_DECLARED, :94 role_is_declared (predicate = KEY PRESENCE) / transfer_plan.py:375 _aux_role_status
  inactive_subtractions emit: transfer_plan.py:1796 (slot) / :2030 (scope=lot) / :3458 (validate) / :1133 (M1 reshape) / bonding_plan.py:555 (M1 core-summary)
  inline summary (role consumption): :1293 _summarize_inline / history: :1246 _collect_history / bins: :863 _bins_block / lot rollup: :1918 get_lot_bin_summary
  M1 delegation reshape: :1090 _reshape_m1_summary / stage reverse index: :450 stage_of_table
  validate: :2940 validate_plan (LookupError->404) / painted: :2890 _painted_values / material gate: :2838 _material_identity_rule / _split_material: :2857
  source_region (dormant): :443 status, :605 load_source_region / frame meta: :1165 _canonical_origin_meta, map_overlay.py:458 resolve_align (both-None -> identity)
-->

## 1. 언제 이 파일을 만지는가

- **새 전사 단계(stage)를 켤 때** — stage 선언만으로 코드 무변경 추가
- **처음 세팅하거나 zone 모델(2026-07-28)로 옮길 때** — `plan_store.registry`에 필수 역할키 7종을 채우는 작업
- **BIN별 가용을 켤 때** (`bin_map` 선언), **자재 대장을 연결할 때** (`lot_membership`)
- 자재 토큰이 lot/slot 모양임을 선언할 때 (`material_identity` — 게이트)

## 2. 세팅 절차

1. **스냅샷**: `conda run -n assy_manager python server/scripts/backup_config.py snapshot`
2. **전제 확인**: 참조하는 모든 테이블이 `table_config.json`에 선언돼 있어야 합니다. 특히 계획 저장소 `map_split_registry`는 제품 소유 — 손으로 옮기지 말고 `install_product_tables.py --apply`로 설치하고, **물리 컬럼까지 실존하는지** `information_schema`로 확인하십시오(선언 없이 저장하면 값이 조용히 드롭되고 200이 나갑니다 → [CONFIG_GUIDE §5.8](../CONFIG_GUIDE.md)). `dt_map`·`dt_log`·`bonding_map` 등은 현장 소유 — 실제 이름으로 선언.
3. 파일이 없으면 `transfer_plan_config.json.sample` 복사. **새 stage**는 `stages.<이름>`에 선언:

   ```json
   "dt": {
     "description": "DT: 코어 웨이퍼의 칩을 테이프에 전사.",
     "source_kind": "core",
     "target_kind": "tape",
     "source_config_ref": "bonding_plan",
     "target_map": { "preset": "TAPE", "table": "dt_map" }
   }
   ```

   소스는 둘 중 하나 — ① `"source_config_ref": "bonding_plan"`(M1 바인딩 재사용, 유일 허용값) ② 인라인 `"source": {...}` (역할 목록은 §5, 전체 예시는 `.sample`의 `bonding` stage).
4. **`plan_store`** — 기존 환경이 zone 이전 상태면 라이브 파일에 손으로 역할키를 더해야 합니다(gitignored라 `.sample` 갱신이 따라오지 않음):

   ```json
   "plan_store": {
     "registry": {
       "table": "map_split_registry",
       "columns": {
         "ref_table": "ref_table", "map_key": "map_key", "value": "value",
         "stack": "stack", "mat_1h": "mat_1h", "mat_mid": "mat_mid", "mat_top": "mat_top",
         "bands": "bands"
       }
     },
     "material_identity": { "compose": ["lot", "slot"], "separator": "_" }
   }
   ```
5. **BIN 축이 필요하면** stage(또는 그 `source`) 블록에 선언 — 단 **M1 위임(`source_config_ref`) stage에는 선언해도 무효**이므로 inline `source`로 바꿔야 하고, 신뢰 가능한 잔여에는 `origin_log`까지 필요합니다:

   ```json
   "bin_map": { "table": "<BIN을 지는 맵>", "columns": { "lot": "lot", "slot": "slot", "x": "x", "y": "y", "bin": "<BIN 컬럼>" } }
   ```
6. 저장 — 반영은 자동입니다(**요청마다 재읽기**, 재기동·reload 불필요).

## 3. 반영 확인

1. `GET /api/transfer-plan/stages` — 새 stage가 목록에 뜨고 `total_chips`·`plan_store`가 **`connected`** 인지 (`registry`가 `missing`이면 역할키 7종·테이블 선언부터 재확인). 보조 역할이 **`not_declared`** 로 뜨는 것은 정상입니다 — 그 키를 안 쓴다는 뜻이지 결함이 아닙니다. `missing`은 선언해 놓고 깨졌다는 뜻이므로 이쪽만 고치면 됩니다.
2. `GET /api/transfer-plan/validate?ref_table=<t>&map_key=<k>` — **404면 `plan_store.registry` 역할키 누락**입니다(zone 역할 7종 중 하나라도 빠지면 404 — 조용히 통과시키지 않는 설계).
3. BIN 축을 켰다면 `GET /api/transfer-plan/source-summary?...&bins=...` — `bins.axis: "connected"` 확인 (`unavailable`이면 미선언 또는 M1 위임 stage).
4. 맵 에디터에서 그 `target_map.table`의 맵을 열면 stage가 유도됩니다 — 어느 stage에도 없는 맵은 `stage_unknown` 경고 + `unverified`(404 아님).

## 4. 잘못됐을 때

```bash
conda run -n assy_manager python server/scripts/backup_config.py restore transfer_plan_config_<yymmdd>.json.bak --yes
```

요청마다 재읽으므로 복원 즉시 반영. 단 **`table_config`·물리 컬럼과 얽힌 문제**(zone 컬럼 미선언으로 저장이 드롭된 경우 등)는 config 복원만으로 안 돌아옵니다 → [ROLLBACK_PROCEDURE](../ROLLBACK_PROCEDURE.md).

## 5. 역할 사전 (키 참조)

각 역할이 **어떤 숫자를 만들고, 안 이으면 정확히 무엇이 죽는지**의 사전입니다. 화면 용어 ↔ API ↔ 역할 대응부터:

| 화면에서 보는 것 | API 필드 (`GET /api/transfer-plan/source-summary`) | 만드는 역할 |
|---|---|---|
| 자재 카드의 **가용/잔여** | `chips.remaining` = total − \|fail합집합 ∪ 기전사\| | `total_chips` − `fail_sources.*` − `transfer_log` (정확 감산은 `origin_log`가 있을 때) |
| 총 칩 수 (가용의 분모) | `chips.total` | `total_chips` |
| fail 차감 내역 | `chips.fail_breakdown.<name>` | `fail_sources.<name>` |
| 기전사 차감 | `chips.transferred` | `transfer_log` |
| **BIN별 가용** (`?bins=1,2`) | `bins.entries[]` | `bin_map` |
| 코어별 분해 | `by_core` (+`by_core_origin` 마커) | `origin_log`(정확) / `origin_area_map`(강등) |
| 이력 타임라인 | `history` | `process_history` (+`warnings.result_fail_values`) |
| 로트 전개 (`scope=lot`) | `by_slot`·`slots_origin` | `lot_membership` (폴백: `bin_map`) |
| 부족·초과배정 경고 (`/validate`) | `qty_shortage`·`source_overallocated`·`status` | `plan_store.registry` + `material_identity` |

**공통 규율**: 모든 바인딩은 `{table, columns}` 형태이고, 테이블이 `table_config` 미선언이거나 **필수** 컬럼이 빠지면 그 역할은 통째로 `missing`입니다(부분 해석 없음). **[2026-07-28] 선언했는데 모델에 없는(오타) 비필수 컬럼은 사라지는 대신 `connected(column_unresolved:<역할키들>)`로 강등 표시됩니다** — 전 역할 공통(`bonding_plan._demote_for_unresolved` 공유). 역할 강등은 조용히 지나가지 않습니다 — `warnings[].type: "source_degraded"`로 표면화되고, 감산항(fail·기전사)이 강등되면 `chips.remaining`이 **`null`로 내려갑니다**(`remaining_reliable: false`, total이 살아 있으면 `remaining_upper_bound`만 제공). validate는 강등된 소스에 대해 부족 판정을 **하지 않고** `availability_unreliable`을 냅니다("검사 안 함" ≠ "이상 없음"). 강등 status의 의미 사전은 [CONFIG_GUIDE §5.8](../CONFIG_GUIDE.md)이 정본입니다.

**[2026-08-04 `2c2a777`+`101311f`] 보조 역할 선언은 선택입니다 — 상태는 둘이 아니라 셋입니다.** 판정 기준은 **키가 블록에 있느냐**이지 값이 쓸 만하냐가 아닙니다(`bonding_plan.role_is_declared`).

| config 상태 | 역할 status | `chips.remaining` | 강등인가 |
|---|---|---|---|
| 키가 **아예 없음** | **`not_declared`** | **숫자** — 그 감산항 없이 계산 | 아니오. `source_degraded` 경고 없음 |
| 키는 있는데 깨짐 (`null`·`"None"`·테이블/컬럼 오타) | `missing` / `connected(count_only)` / `connected(column_unresolved:…)` | `null`(+상한) | 예 — 종전 강등 그대로 |
| 키가 있고 정상 | `connected` | 숫자 | 아니오 |

- 대상은 **`transfer_log`·`origin_log`·`fail_sources`·`process_history`** 넷뿐입니다. **`total_chips`는 예외로 계속 필수** — 분모가 없으면 가용이 성립하지 않으므로 부재도 `missing`이고 `remaining`은 `null`입니다. 이 완화를 "이제 다 선택"으로 일반화하지 마십시오.
- **빠진 감산 종류는 응답이 이름으로 말합니다** — 최상위 선택 필드 `inactive_subtractions`(예: `["transfer_log", "origin_log", "fail_sources"]`). 가용 수치를 내는 **모든** 응답에 같은 이름·같은 모양으로 실립니다: 슬롯 요약 · `scope=lot` 요약 · M1 `core-summary` · `POST /api/transfer-plan/validate`. 목록이 비면 필드 자체가 없으므로 **전 역할을 선언한 환경의 응답은 완화 전과 바이트 단위로 동일**합니다. `process_history`는 감산항이 아니므로 이 목록에 안 들어갑니다.
- **`transferred`·`used`는 `null`인데 `remaining`은 숫자입니다.** 소모 로그가 없으면 몇 개를 썼는지는 미상이지만(가짜 `0` 금지), 그 감산항이 존재하지 않는다는 것은 사이트의 선언이므로 잔여는 미지수가 아닙니다. 신뢰도의 권위는 여전히 `remaining_reliable` **하나**이고, 이 경로에서는 `true`입니다.
- **`validate`의 판정(`status`)은 이 때문에 바뀌지 않습니다** — 미선언은 결함이 아니라 선언이라 `ok`는 계속 `ok`입니다. 서버가 하는 일은 총량이 순량 행세를 못 하게 "무엇을 빼지 않았는지" 말하는 것뿐입니다.
- **라이브 config는 손댈 것이 없습니다.** 그 부속 테이블을 애초에 선언한 적 없는 사이트는 곧바로 숫자를 받고, 강등을 피하려고 일부러 깨진 바인딩을 넣어 둔 사이트는 이제 그 **키를 지우면** 됩니다.
- 클라가 이 자격을 어떻게 그리는지(가용·잔여 셀의 `*` 각주 표시와 역할명 노출)는 [MAP_EDITOR_SPEC §6.2-ter](../../spec/MAP_EDITOR_SPEC.md)가 정본입니다.

### 5.1 stage 키 (`stages.<이름>`)

**`description`** (필수) · **`source_kind`/`target_kind`**
- 역할: `/stages` 응답과 소스 요약에 그대로 실리는 **표시 라벨**입니다.
- 함정: `source_kind`를 바꿔도 **계산 경로는 안 바뀝니다** — core-kind(M1 위임) 여부는 `source_config_ref` 유무가 정합니다.

**`target_map: {preset, table}`**
- 만드는 판정: **맵 테이블 → stage 역인덱스**. 맵 에디터에서 `table`의 맵을 열면 stage가 유도되고, `/validate`도 이걸로 stage를 찾습니다. `preset`은 에디터 표시용.
- 미선언/오타: 그 테이블은 어느 stage에도 안 속함 → validate가 `stage_unknown` 경고 + **수량·가용·fail 검증 전부 생략**(status `unverified` — 404 아님. "경고 없음 = 이상 없음"이 아닙니다).
- 함정: 두 stage가 같은 `table`을 선언하면 **먼저 선언된 stage가 이깁니다**(첫 매치).

**`source_config_ref: "bonding_plan"`** (유일 허용값)
- 만드는 숫자: 소스 가용을 **M1 `bonding_plan_config`의 바인딩으로 위임** — `chips`는 M1 core-summary(코어 total − defect − eds_fail − 기전사)를 재성형한 것이고, `/stages`의 역할 상태도 M1의 `total_chips`·`used_chips`(→`transfer_log`로 개명)·`process_history`·`defect`·`eds_fail`로 표시됩니다.
- 미연결: ref도 inline `source`도 없으면 `total_chips`가 `missing`이라 `chips.total=0`·`remaining=null`입니다(보조 역할은 `not_declared`로 뜹니다 — 죽인 것은 분모입니다).
- **[2026-08-04] M1 위임 경로도 보조 역할이 선택입니다** — `bonding_plan_config`에서 `defect`·`eds_fail`·`used_chips`·`process_history` 키를 빼면 `not_declared`이고, M1의 산술은 변하지 않은 채(부재 역할은 종전에도 0을 기여했습니다) 상태 문자열과 `inactive_subtractions`만 달라집니다. 재성형 시 M1 어휘가 M2 어휘로 개명됩니다(`used_chips` → `transfer_log`).
- 함정: **이 경로에서 `bin_map`은 선언해도 무효** — 좌표 집합을 넘겨받지 않아 `bins.axis: "unavailable"` 고정. BIN이 필요하면 inline `source`로 전환.

**`bin_map`** (선택 — stage 블록 또는 `source` 블록, stage 쪽 우선)
- 만드는 숫자: `?bins=` 요청 시 `bins.entries[]` — BIN별 **가용**(= 그 BIN 셀들로 스코프한 remaining)·`cells`·`bin_absent`/`unknown` 판정. `lot_membership` 미선언 시 로트 전개의 강등 슬롯 원천이기도 합니다.
- 바인딩: `{"table": "<BIN을 지는 맵>", "columns": {"lot", "slot", "x", "y", "bin"}}`
- 미선언: `bins.axis: "unavailable"` + `bin_axis_unavailable` 경고. `bins=`를 안 붙인 기본 응답은 **아무 영향 없음**.
- 함정: ① `origin_area_map`의 `val` 재사용 금지(출신 코어 식별자일 수 있음 — 서버는 BIN 컬럼을 추측하지 않습니다). ② BIN 값은 층 경계와 같은 정수 판정기 — `'1'`·`'01'`·`' 1 '`은 한 BIN, 비정수 셀은 버리지 않고 `unbinned_cells`로 계수. ③ 소스 집계가 **강등**이면(예: `origin_log`를 선언해 놓고 테이블/컬럼이 깨진 경우) **BIN 전부 `unknown` + `remaining=null`로 강등**됩니다 — BIN 축만 이어도 소용없습니다. **[2026-08-04] 반면 `origin_log` 키가 아예 없으면 강등이 아니므로 BIN은 `ok` + 숫자로 나갑니다**(감산항 없이 계산, `transferred`만 `null`). 단 이 경우 BIN별 총계는 `total_chips`의 `x`/`y`에서 오므로 그 좌표를 바인딩해야 합니다 — 없으면 `total_pts`를 못 만들어 다시 `unknown`입니다.

### 5.2 inline `source` 역할

**`identity: {compose}`** (기본 `["lot","slot"]`)
- 역할: 출신(core) 맵 ID 합성 규칙 — `compose`를 `_`로 이어 `wafer_map_metadata.map_id`를 조회하는 키.
- 미선언: 기본값 사용, 죽는 것 없음.
- 함정: 메타의 `map_id` 합성 관례와 어긋나면 메타 조회가 빗나가 frame=`origin` fail이 `align_unavailable`로 강등됩니다.
- **[2026-07-29 7b] 합성·바인드 값은 선언 타입으로 캐노니컬화됩니다** — 조회 대상 테이블의 `table_config` 선언 타입이 `number`인 컬럼은 `'01'`·`' 1 '`·`1.0`이 전부 `'1'`로 합성/바인드되고(단일 정수 판정기 의미론 — 운영 실증: number 선언 slot이 `1`을 저장해 메타가 `LOT_1`로 등록됐는데 토큰 `LOT_01`이 빗나가던 결함), `string` 선언은 공백만 제거하고 원문 유지(패딩이 유의미). 구현은 `map_overlay.canonical_key_value` **하나**이며 모든 pool lot/slot 바인드(총칩·기전사·origin_log·fail·이력·bin_map·lot_membership·source_region)와 `map_id` 합성(`_origin_map_id`·M1 `get_core_summary`)·`map_key` 분해(`build_key_filters`)가 이것을 경유합니다. 읽을 수 없는 값은 지어내지 않고 원문(트림)으로 조회가 정직하게 빗나갑니다.

**`map_metadata`**
- 만드는 판정: 프레임 정렬(회전·면·y반전·start)의 유도 원천 — 출신 코어 fail 좌표를 canonical 프레임으로 옮기는 근거. 정렬이 적용되면 `sources`에 `connected(aligned:180)` 마커.
- 바인딩: `{"table": "wafer_map_metadata", "columns": {"target_table", "map_id", "grid_metadata"}}`
- 미연결: **소스 맵만** 메타가 있으면 그 fail 원천이 `connected(align_unavailable)`(fail=0 + remaining 신뢰 불가 — 비대칭 지식은 identity로 가정하지 않음). **양쪽 다** 메타가 없으면 identity로 간주해 그대로 붙습니다(실패 아님 — 단 회전 미보정 위험은 남습니다).
- 함정: 메타를 한쪽 맵에만 등록하면 등록 안 한 것보다 오히려 강등됩니다(위 비대칭 규칙).

**`total_chips`**
- 만드는 숫자: `chips.total` — **가용의 분모**. `(lot, slot)` 행 수 count.
- 바인딩: `{"table": "dt_log", "columns": {"lot": "tape_lot", "slot": "tape_slot", "x": "tx", "y": "ty"}}` — `x`/`y`는 선택이지만 `origin_log`가 없을 때 영역·BIN 집계의 총칩 좌표에 필요.
- 미연결: **분모 자체가 불명** — `total_unknown` 강등으로 `remaining=null`(상한도 없음), validate는 그 소스의 모든 수요를 `availability_unreliable`로 내림(부족 판정 전면 생략). 이 역할이 죽으면 화면의 가용은 전부 미상입니다.
- 🔴 **[2026-08-04] 이 역할만 완화의 예외입니다** — 다른 보조 역할과 달리 **키를 지워도 `not_declared`가 아니라 `missing`**입니다(`_aux_role_status`를 타지 않습니다). 분모가 없으면 뺄 대상 자체가 없어 가용이 성립하지 않기 때문입니다. "이제 선언이 다 선택"이라고 읽고 이 키를 지우면 그 stage의 가용이 통째로 미상이 됩니다.
- 함정: "행 수 = 칩 수"(칩당 1행 유일)를 가정합니다 — 중복 행이면 total이 과대인데 **현재 미표면화**(알려진 한계).

**`transfer_log`**
- 만드는 숫자: `chips.transferred` — **기전사 차감**. `x`/`y`가 있으면 distinct `(x,y)` 칩 수, 없으면 행 count.
- 바인딩: `{"table": "bonding_log", "columns": {"lot", "slot", "x", "y"}}`
- **[2026-07-29 7c] `"transfer_log": "none"` — 소모 기록이 없다는 선언**: 사이트에 전사(소모) 로그 자체가 없으면 정확히 문자열 `"none"`을 선언하십시오. 상태는 `connected(untracked)`(강등 아님 — `source_degraded` 없음), `transferred=null`(0 아님 — 미상), `remaining=null` + `remaining_upper_bound`(= total − fail) + **전용 경고 `transfer_untracked`**(effect `remaining_upper_bound`) — 클라는 미상 대신 `≤N`으로 표시할 수 있습니다. `by_core`의 used/remaining은 null, `?bins=`의 각 항목도 `transfer_untracked: true` + `remaining_upper_bound`(= bin∩총 − bin∩fail)로 나갑니다. **값이 있는데 그 값이 아닌 형태**(JSON `null`·`"None"` 등)는 전부 종전 그대로 `missing`입니다(null은 실수 삭제와 구분 불가 — 의도는 문자열로만 선언). ⚠️ **[2026-08-04 정정] 「키 부재」는 이제 여기 속하지 않습니다** — 아래 참조. 두 선언은 답이 다릅니다: `"none"`은 "추적하지 않는다 → 상한만 안다", 키 부재는 "그 표 자체가 없다 → 그 감산 없이 센다".
- **미선언(키 부재) — [2026-08-04]**: 상태 `not_declared`, 강등 아님. `remaining`은 기전사 감산 **없이 계산된 숫자**로 나가고(`remaining_reliable: true`, 상한 아님), `transferred`는 `null`(가짜 0 금지), `inactive_subtractions`에 `"transfer_log"`가 실립니다. `?bins=`의 각 항목도 같은 규율(`remaining` 숫자, `transferred: null`)이고, `by_core`의 `used`도 `null`입니다.
- **미연결(선언했는데 깨짐)**: `transferred=0`으로 감산이 빠져 remaining 과대 위험 → `remaining=null` + `remaining_upper_bound`(total 정상일 때) + `source_degraded(remaining_overstated)`. total·이력은 안 죽습니다. 화면에서 잔여가 미상이면 키를 지운 것이 아니라 **깨진 것**입니다.
- 함정: **`x`/`y`까지 바인딩하십시오** — 좌표 없이 count만 되면 **[2026-07-28 `1fefd12`] `connected(count_only)`로 강등**됩니다: `transferred` 카운트는 진짜라 유지되지만 칩 정체를 몰라 집합 감산이 불가능하므로 `remaining=null` + 진짜 상한만 제공되고, `by_core`의 used/remaining도 log·area_map **양 경로 모두 `null`**입니다(가짜 0 금지). 종전에는 이 상태가 `connected`로 통과해 기전사 차감이 빠진 remaining이 정상처럼 표시됐습니다(유령 잔여 — +101 재현 실증). 화면에서 잔여가 `미상`이고 기전사 숫자만 보이면 이 강등부터 의심하십시오.

**`origin_log`**
- 만드는 숫자 셋: ① **정확 remaining**(합집합 감산 — fail·기전사 이중 차감 없음) ② `by_core` 분해(fail 포함, `by_core_origin: "log"`) ③ frame=`origin` fail을 타깃 좌표로 투영하는 다리.
- 바인딩: `columns` 8종 전부 필수 — `{lot, slot, x, y, origin_lot, origin_slot, origin_x, origin_y}`.
- **미선언(키 부재) — [2026-08-04]**: 상태 `not_declared`, 강등 아님. remaining은 감산식 폴백(`total − Σfail − used`)으로 **숫자**로 나가고 `inactive_subtractions`에 `"origin_log"`가 실립니다. `?bins=`도 정상 숫자(위 `bin_map` 함정 ③ 참조). `by_core`는 `origin_area_map` 경로로 내려가고, 그것도 없으면 `by_core` 필드 자체가 빠집니다.
- **미연결(선언했는데 깨짐)**: frame=`origin` fail 전부 `unavailable(origin_missing)`(fail=0), remaining은 M1식 감산 폴백이지만 강등 자체가 `remaining_overstated`라 **`remaining=null`**(상한만). `by_core`는 `origin_area_map` 강등 경로로. `?bins=` 요청 시 **전 BIN `unknown` 강등**. 안 죽는 것: total·transferred·frame=`self` fail·이력.
- 함정: ① 컬럼 하나만 빠져도 역할 전체가 `missing`입니다. ② **[2026-08-04] 선언 간 모순은 계속 표면화됩니다** — `origin_log`가 `not_declared`여도 `frame: "origin"`으로 **선언된** fail 원천이 있으면 그 원천은 종전대로 `unavailable(origin_missing)` 강등이고, 그 강등 때문에 `remaining`은 `null`이 됩니다. 완화는 "안 쓴다"에만 적용되지 "쓴다고 선언해 놓고 다리가 없다"에는 적용되지 않습니다.

**`origin_area_map`** (선택)
- 만드는 숫자: `origin_log` 미연결 시의 `by_core` **강등 경로** — 영역 귀속 분해(total/used만, **fail은 null** — 좌표 대응이 없어 0으로 위장하지 않음). `by_core_origin: "area_map"`, 상태 `connected(area_only)`. remaining에는 영향 없음(`by_core_degraded`).
- 바인딩: `{"table": "dt_map", "columns": {"lot", "slot", "x", "y", "val"}}` — `val` = 코어 식별자.
- 미선언: `origin_log`가 살아 있으면 아예 소비되지 않음(영향 0). 둘 다 죽으면 `by_core` 필드 자체가 응답에서 빠집니다.
- 함정: `core_id`는 영역 맵의 원시 값(불투명) — `core_lot`/`core_slot`은 null이고 log 경로의 `core_id`와 문자열 일치를 가정하면 안 됩니다.

**`process_history`**
- 만드는 것: `history` 배열(최근 50건, 시간 오름차순) — 이력 타임라인. `warnings.result_fail_values`에 걸리는 result는 `result_fail` 경고(validate에서는 `source_history_fail`로 승격).
- 바인딩: `columns {lot, slot, step, eqp, result, time, recipe, knobs}`.
- **미선언(키 부재) — [2026-08-04]**: 상태 `not_declared`, `history`는 빈 배열이고 **경고는 나가지 않습니다**(`history_incomplete` 없음 — 없는 표는 결함이 아닙니다). 감산항이 아니므로 `inactive_subtractions`에도 안 실립니다.
- **미연결(선언했는데 깨짐)**: `history` 빈 배열 + `source_degraded(history_incomplete)` — **가용 숫자는 안 죽습니다**.
- 함정: `time`을 안 바인딩하면 정렬 없는 임의 50건이 됩니다. `knobs`는 JSON 파싱 실패 시 raw 문자열 폴백(에러 아님).

**`fail_sources.<name>`** (이름 자유 — 응답 키·경고에 그대로 노출)
- 만드는 숫자: `chips.fail_breakdown.<name>` — **fail 차감 축**. `frame: "origin"`은 출신 코어 fail을 `origin_log` 조인 + 메타 정렬로 타깃 좌표에 투영, `frame: "self"`는 자기 좌표 직접 카운트.
- 바인딩: `{"frame": "origin"|"self", "table", "columns": {lot, slot, x, y, val}, "fail_values": ["D"]}`
- **미선언(`fail_sources` 키 자체가 없음) — [2026-08-04]**: 강등 아님. fail 감산 없이 `remaining`이 **숫자**로 나가고 `inactive_subtractions`에 `"fail_sources"`가 실립니다(개별 원천 이름이 아니라 이 역할명 하나로).
- **미연결(선언한 원천이 깨짐)**: 그 이름의 fail=0 → 감산 과소 → `remaining=null`(+상한) + `source_degraded`. `frame: "origin"`인데 `origin_log`가 없으면 `unavailable(origin_missing)`.
- 🔴 **`fail_sources` 키가 있는데 값이 쓰레기면**(`null`·`"None"`·리스트·숫자) **선언한 것으로 칩니다** — 완화 대상이 아니고, `inactive_subtractions`에도 안 실립니다(선언한 역할을 "미선언"이라 부르는 것이 이 필드가 절대 해선 안 되는 거짓말입니다). 해석되는 원천이 없어 fail 항이 산술에서 빠지는 것은 완화 이전과 동일한 동작입니다.
- 함정: ① `fail_values` 미선언(또는 `val` 미바인딩)이면 **그 테이블 전 행이 fail로 계산**됩니다. ② **[2026-07-28 `1fefd12`] `fail_values`를 선언했는데 `val` 컬럼명이 오타면**(모델에서 미해석) 필터 없는 전 행 count를 **거부하고 fail=0 + `connected(column_unresolved:val)` 강등**합니다 — 상한 불변식(강등된 항은 과소 기여만 허용) 때문에 과대 계상 대신 0을 택합니다. self·origin 양 경로 동일. 선언한 `x`/`y`가 오타일 때도 일반 `missing`이 아니라 `connected(column_unresolved:x,y)`로 오타를 지목합니다. ③ `frame` 생략 시 기본값이 고정이 아닙니다 — `origin_log` 연결 여부에 따라 `"origin"`/`"self"`로 바뀌므로 **명시하십시오**. ④ 구 `align` 선언은 폐지 — 무시되며, 변환은 `wafer_map_metadata` 델타에서 유도. ⑤ **[2026-07-28 `deed6d2`] `frame: "self"` 원천도 `x`/`y`까지 바인딩하십시오** — `origin_log`가 connected인 집합 감산 경로에서 self fail 원천이 좌표 없이 count만 제공하면 `transfer_log`와 같은 **`connected(count_only)` 강등**입니다: count는 `fail_breakdown`에 진짜라 유지되지만 fail 합집합에 칩을 못 넣어(종전에는 이 상태가 `connected`로 통과해 remaining이 과대 표시 — 256/256 fail인데 remaining 209 `reliable: true` 재현) `remaining=null` + 진짜 상한, `by_core`의 fail·remaining도 null(used는 유지)입니다. count를 대신 감산하지 않는 이유는 상한 불변식(겹침을 모르는 감산은 과대 감산 위험) 때문이고, `origin_log` 없는 폴백 감산 경로에서는 count 감산이 정확해 강등하지 않습니다.

**`warnings: {result_fail_values}`**
- 역할: 이력 result가 이 목록(문자열 완전 일치)에 있으면 `result_fail` 경고 발화.
- 미선언: 이력 fail 경고만 침묵 — 다른 것은 안 죽습니다.

**`lot_membership`** (선택)
- 만드는 것: `scope=lot`(자재 토큰이 로트만 적을 때) 전개의 **슬롯 대장** — `by_slot` 목록과 `map_exists` 진단("전산에는 있는데 맵이 없는 슬롯" = `lot_slot_map_missing`)의 원천. 이 진단이 이 역할의 존재 이유입니다(로트 스플릿 후 잔재 교정면).
- 바인딩: `{"table": "<자재 대장>", "columns": {"lot", "slot"}}`
- 미선언: `bin_map`의 distinct 슬롯으로 강등 폴백(`slots_origin: "map"` + `lot_membership_degraded`) — **맵 없는 슬롯이 안 보여 진단이 성립하지 않습니다**. `bin_map`도 없으면 `slots: null`·`slots_status: "unknown"` + `lot_membership_unknown`, bins도 `unavailable`.
- 함정: 로트의 슬롯이 50(`MAX_LOT_SLOTS`) 초과면 부분합을 지어내지 않고 합산 전체를 거부합니다.

### 5.3 `plan_store` 역할

**`registry`** (필수)
- 만드는 판정: **계획(legend/DOE) 저장소** — `/validate`가 `(ref_table, map_key)`로 행을 읽어 zone 컬럼(`stack`·`mat_1h`·`mat_mid`·`mat_top`)에서 수요를 **유도**합니다(`total = painted(값) × layers`, `share = ceil(total / 자재 수)`). `doe_count`·`qty_shortage`·`source_overallocated`·V1~V5 판정 전부 이 행들에서 나옵니다.
- 바인딩: 필수 역할키 7종(`ref_table`·`map_key`·`value`·`stack`·`mat_1h`·`mat_mid`·`mat_top`) — §2의 스니펫 참조. 🗄️ `bands`는 선택·읽기 전용.
- 미연결(역할키 하나만 빠져도): **`/validate` 404**. `/stages`에 `plan_store.registry: "missing"`. `source-summary`는 registry를 안 읽으므로 영향 없음.
- 함정: ① `map_split_registry.stack`은 `table_config`에서 **`"string"`**(“number”로 바꾸면 저장 실패/조용한 변조). ② 폐기 계획(`bands` blob)이 남은 사이트는 `bands` 역할키를 **유지**하십시오 — 빼면 그 행들이 "계획 없음"으로 보이고, 다음 legend 저장(replace_map)이 옛 계획을 빈 집합으로 덮을 수 있습니다. 표현 불가한 옛 배치는 접지 않고 거부됩니다(`not_convertible`).

**`material_identity: {compose, separator}`**
- 만드는 판정: **게이트 전용** — "이 배포의 자재 문자열이 lot/slot 모양"이라는 선언. 실제 분해는 config가 아니라 공유 토큰 문법(`lot[_slot][:BIN]`, `parse_material_token`)이 합니다 — 클라는 config를 못 읽으므로 파싱 규칙을 여기 두면 양쪽이 갈립니다.
- 바인딩: `{"compose": ["lot", "slot"], "separator": "_"}` — `compose`에 `lot`·`slot`이 둘 다 없으면 미선언 취급.
- 미선언: **모든 자재가 `source_unresolved`** → 수량 검증 전면 생략 → 계획 status `unverified`. `/stages`에 `material_identity: "missing"`.
- 함정: `separator`/`compose` 값을 바꿔도 파싱은 안 바뀝니다(게이트일 뿐) — 이 키의 은퇴/재정의는 총괄 결정 대기.

**`source_region`** (선택 · ⚠️ 휴면 — 총괄 지시로 보류)
- 만드는 숫자(활성화 시): 자재별 "쓰기로 한 사용 영역" 셀 집합 → `region_chips`(영역 내 가용).
- 바인딩: `columns {ref_table, map_key, source_lot, source_slot, x, y}`.
- 미선언: `region_chips`가 응답에 없을 뿐 — 결함 아님(라이브 config가 일부러 미선언).
- 함정: 선언만 하고 테이블이 없으면 `/stages`에 `missing` 소음만 만듭니다.

zone·마커 0·V1~V6·`bands` 이관의 전체 의미론은 [CONFIG_GUIDE §5.8](../CONFIG_GUIDE.md)이 정본.
