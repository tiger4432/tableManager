# `transfer_plan_config.json` 세팅 — M2 Universal Transfer Plan

> **Status:** 🟢 Living | **Last-verified:** 2026-08-06 — **서술·심볼 기준**(🔴 **이 날짜가 무엇을 덮는지 명시합니다.** 2026-08-06 라운드는 ① `curl` 포트 ② 상단 Loader evidence 블록의 **라인 앵커 전면 삭제 + 심볼 전수 재확인**을 했습니다. **라인 번호는 이제 이 문서에 없습니다** — 있던 ~35개가 전부 낡아 있었고 그중 `bonding_plan.py` 계열은 **일률적으로 +156**이었습니다. ⚠️ **직전 헤더는 「anchors re-measured by grep on this tree」라고 적은 채 그 앵커들이 낡아 있었습니다 — 검증했다는 *거짓* 주장은 주장이 없는 것보다 나쁩니다. 다음 독자가 확인을 멈추기 때문입니다.**) (§3 dry-run `curl`의 포트를 **8000 → 8080**으로 정정 — 런처가 띄우는 포트는 `ASSY_API_PORT` 기본 8080이고 `:8000`은 `uvicorn` 직접 실행의 기본값입니다. 직전 2026-08-04 `12c1d2e` 거절이 자기 사유를 이름으로 말함 + `8817dde` **좌표/값 컬럼 유도** + `GET /admin/transfer-plan/dry-run`. 이 라운드에 문서를 **재작성**했습니다 — 기존 문서를 읽은 사용자가 그대로 `"x": "x"`를 써서 라이브가 멈췄기 때문입니다) | **Owner:** Backend / UI-Map
> 상위: [폴더 인덱스](./README.md) · **의미론(zone 모델·`stack` string·`bin_map`·`bands` 폐기)의 정본은 [CONFIG_GUIDE §5.8](../CONFIG_GUIDE.md)** · 동작 계약은 [MAP_EDITOR_SPEC §6](../../spec/MAP_EDITOR_SPEC.md)

<!-- Loader evidence — SYMBOLS, NOT LINE NUMBERS.
  🔴 2026-08-06: this block used to carry ~35 line anchors and claimed "anchors re-measured by
     grep on this tree" (2026-08-04). By 2026-08-06 essentially all of them had drifted — the
     bonding_plan.py anchors uniformly by +156, which is the signature of a block written once
     while the source grew underneath it. Nobody was careless; a line number is a fact about a
     file's CURRENT shape and every unrelated edit above it invalidates it silently, with
     nothing going red. So the numbers are stripped and the symbols kept: a symbol is greppable,
     survives every edit that does not rename it, and a rename that breaks it is exactly the
     change a reader needs to notice.
  ✅ Every symbol below was re-verified present by grep on 2026-08-06 (working tree). The
     block's CONCLUSIONS were all sound the whole time — only the addresses were wrong, which
     is the worst combination for a document whose value proposition is measured locations.

  load:                 `load_transfer_plan_config` (missing/corrupt -> {})  [server/transfer_plan.py]
                        per-request snapshot in `server/main.py`
  role tuples (the `required` catalog)  [server/transfer_plan.py]:
                        REGISTRY_ROLES / IDENTITY_ROLES / ORIGIN_LOG_ROLES / ORIGIN_AREA_MAP_ROLES
                        / SOURCE_REGION_ROLES / MAP_METADATA_ROLES / BIN_AXIS_ROLES
                        / LOT_MEMBERSHIP_ROLES / _STAGE_SOURCE_ROLES
  derivation  [server/bonding_plan.py]:
                        DERIVED_ROLE_OF {x,y,val,bin} / _overlay_config_snapshot (memo on mtime_ns,size)
                        / _map_binding_for (fallback_guess val refused)
                        / resolve_effective_columns (absent-only, identity return) / deletion_hints
  refusal vocabulary  [server/bonding_plan.py]:
                        BINDING_NOT_DECLARED / BINDING_MAPPING_UNAVAILABLE / BINDING_COLUMN_MISSING
                        / BINDING_NOT_REACHED
  refusal sentences:    `explain_binding_refusal` [bonding_plan.py]
                        / `_refusal` · `_bin_axis_refusal` · `_lot_membership_refusal` [transfer_plan.py]
  screen path:          `_bins_unavailable` [transfer_plan.py] -> "BIN별 가용을 계산할 수 없습니다 ― {detail}"
                        -> `client2/src/transfer_plan.js` renders `detail` verbatim -> `unknownCellHtml` title
  dry-run:              `_role_dry_run` · `dry_run` [transfer_plan.py]
                        / route GET /admin/transfer-plan/dry-run (require_admin_token) [main.py]
  source_config_ref:    🗄️ RETIRED 2026-08-14 — `M1_SOURCE_REFS` and its five branch sites are
                        gone. `server/M1_SOURCE_CONFIG_REF.RETIRED.md` (approval, measured
                        cause, revival). A config still carrying the key now falls through
                        to the inline branch and reads its own `source` block.
  degradation engine:   `_status_is_degraded` · `_degradation_effect` · `assess_degradation`
                        / chips gate `build_chips_block`  [transfer_plan.py]
  relaxation (2c2a777 + 101311f):  STATUS_NOT_DECLARED · `role_is_declared` (predicate = KEY PRESENCE)
                        [bonding_plan.py] / `_aux_role_status` [transfer_plan.py]
  inline summary:       `_summarize_inline` / bins `_bins_block` / lot rollup `get_lot_source_summary`
                        (`_lot_slots`) / validate `validate_plan`  [transfer_plan.py]
-->

---

## 0. 🔴 이 문서에서 가장 중요한 한 문장

```json
"columns": { "x": "x" }
```

**왼쪽 `"x"`는 시스템이 정한 역할 이름이고, 오른쪽 `"x"`는 당신 테이블에 실제로 존재해야 하는 컬럼 이름입니다.** 둘은 아무 관계가 없습니다. 우연히 철자가 같으면 이 줄은 동어반복처럼 **맞아 보이고**, 그래서 검토를 통과합니다.

2026-08-04 라이브에서 정확히 이 일이 일어났습니다. `dt_log`에는 `x`라는 컬럼이 없습니다(좌표는 `dt_x`/`dt_y`). 결과:

- `bin_map`은 **선언돼 있었고**, 형태도 옳았고, 테이블도 선언된 것이었고, 필수 역할 다섯을 전부 이름 붙였습니다. 틀린 것은 **컬럼 철자 둘**뿐이었습니다.
- 그런데 화면은 「`bin_map`이 선언돼 있지 않습니다」라고 말했습니다. **거짓말이었습니다.**
- 같은 파일의 `source.total_chips`는 네 이름이 **전부** 틀려 있었고, 그것은 가용의 **분모**라 본딩 stage의 잔여 수치가 통째로 미상이었습니다.

`12c1d2e` 이후 거절은 자기 사유를 이름으로 말합니다(§6). 그리고 `8817dde` 이후 **좌표/값 컬럼은 대부분 쓰지 않아도 됩니다**(§1) — 안 쓰면 틀릴 수 없기 때문입니다.

---

## 1. 대부분은 안 써도 됩니다 — 유도가 먼저입니다

`map_overlay_config.json`은 이미 이렇게 선언돼 있습니다:

```json
"dt_log": { "columns": { "x": "dt_x", "y": "dt_y", "val": "c_bn", "key_columns": ["dt_job"] } }
```

이 사실을 `transfer_plan_config`에 **다시 쓰라고 요구했던 것**이 사고의 원인이었습니다. 같은 사실의 세 번째 사본입니다. 그래서 이제 서버가 그쪽에 물어봅니다(`map_overlay.resolve_binding_info` — 새 기계장치를 만들지 않았습니다).

`map_overlay_config`의 자기 주석이 이 규율의 정본입니다:

> Declare a binding ONLY where the coordinate columns depart from the x/y/val convention … a duplicate declaration only hides whether the derivation path still works.

**중복 선언은 유도 경로가 아직 살아 있는지를 가립니다.** 그래서 「일단 다 적어 두자」는 안전한 선택이 아닙니다.

### 1.1 새로 쓰는 사람의 `bin_map` 짧은 형태

```json
"bin_map": {
  "table": "dt_log",
  "columns": {
    "lot": "dt_lot",
    "slot": "dt_slot"
  }
}
```

**이게 전부입니다.** `x`·`y`·`bin`은 `dt_log`의 맵 바인딩에서 `dt_x`·`dt_y`·`c_bn`으로 유도됩니다.
(dry-run 실측 — `origin: "derived"`, `derived_from: "map_overlay_declared"`, `accepted: true`.)

새 사람은 `dt_log`의 컬럼 접두사를 **알 필요조차 없습니다**. 짧은 형태는 `{table, lot, slot}`입니다.

### 1.2 유도되는 것 · 절대 유도되지 않는 것

| | |
|---|---|
| **유도 대상 역할은 넷뿐** | `x` · `y` · `val` · `bin` (거절 문장이 그대로 알려 줍니다: `(유도 대상 역할: bin, val, x, y)`) |
| **키(`lot`/`slot` 등)는 절대 유도 안 됨** | 오버레이는 `dt_log`를 `dt_job`으로 키잉하고, 계획은 `dt_lot`/`dt_slot`으로 키잉합니다. **그 차이는 중복이 아니라 목적에 관한 정보**입니다. 그래서 키는 항상 손으로 씁니다 |
| **`origin_x`/`origin_y`는 유도 안 됨** | 같은 테이블 위의 **두 번째 좌표쌍**입니다. 맵 바인딩은 한 쌍만 서술하므로 어느 쪽인지 말할 수 없습니다 |
| **`fallback_guess` 값 컬럼은 값 역할에 안 씀** | 오버레이가 자기 데이터 경로에서도 배제하는 추측입니다. 가용 **수치**가 새어 들어올 자리가 아닙니다. 그 바인딩의 좌표는 여전히 선언·실측이므로 쓸 수 있습니다 |
| 🔴 **`required`가 아닌 역할은 절대 유도 안 됨** | **이 문서에서 두 번째로 중요한 항목입니다 → §2** |

### 1.3 명시 선언이 항상 이깁니다 — 그래서 오타의 수리법이 「지우기」입니다

선언을 쓰면 유도보다 **먼저** 적용됩니다. 전 역할을 선언한 config는 유도가 들어오기 전과 **바이트 단위로 동일한** 응답을 냅니다(md5 동일성으로 채점됨). 손댈 것이 없습니다.

뒤집으면: **철자가 틀린 선언도 계속 이깁니다.** 유도가 있어도 구조받지 못합니다. 그래서 `"x": "x"`의 올바른 수리는 `"x": "dt_x"`로 **고치는 것**이 아니라 그 줄을 **지우는 것**입니다(둘 다 동작합니다만, 지우면 다음번 테이블 개편 때 또 틀릴 자리가 사라집니다).

서버가 그 말을 직접 해 줍니다 — 거절 문장 끝과 dry-run의 `removable_declarations`가 **지웠을 때 무엇이 유도될지**까지 알려 줍니다(§6).

---

## 2. 🔴 지워도 되는 줄 / 지우면 기능이 사라지는 줄

**유도는 `required` 역할의 부재만 메웁니다.** 그리고 어떤 역할이 필수인지는 **역할 이름이 아니라 그 줄이 들어 있는 블록**이 정합니다.

```json
"bin_map":     { "columns": { "x": "..." } }   ← x는 필수 → 지우면 유도됨   (지우는 것이 정답)
"total_chips": { "columns": { "x": "..." } }   ← x는 선택 → 지우면 그냥 없어짐 (지우면 안 됨)
```

**두 줄은 글자가 똑같고, 올바른 조치가 정반대입니다.** 선택 역할에서 부재는 결함이 아니라 **상태**입니다 — `transfer_log`가 좌표 없이 선언되면 `connected(count_only)`로 읽혀 집합 감산 대신 카운트 감산을 하고, canonical frame 후보에서도 빠집니다. 그것을 유도가 메우면 **아무도 요청하지 않은 숫자 변화**가 조용히 일어납니다. 그래서 유도는 「부재가 곧 거절이 되는 자리」에서만 메웁니다.

### 2.1 종이 위에서 판정하는 표 (2026-08-04 코드 실측)

| 블록 | 필수 역할 | 그중 **유도되는 것**(지워도 됨) | 선택 역할 — **절대 유도 안 됨**(지우면 기능이 사라짐) |
|---|---|---|---|
| `bin_map` | `lot, slot, x, y, bin` | **`x` `y` `bin`** | — |
| `origin_log` | `lot, slot, x, y, origin_lot, origin_slot, origin_x, origin_y` | **`x` `y`** | — |
| `origin_area_map` | `lot, slot, x, y, val` | **`x` `y` `val`** | — |
| `plan_store.source_region` | `ref_table, map_key, source_lot, source_slot, x, y` | **`x` `y`** | — |
| `total_chips` | `lot, slot` | 없음 | `x` `y` |
| `transfer_log` | `lot, slot` | 없음 | `x` `y` |
| `fail_sources.<name>` | `lot, slot` | 없음 | `x` `y` `val` |
| `process_history` | `lot, slot` | 없음 | `step` `eqp` `result` `time` `recipe` `knobs` |
| `lot_membership` | `lot, slot` | 없음 | — |
| `map_metadata` | `target_table, map_id, grid_metadata` | 없음 | — |
| `plan_store.registry` | `ref_table, map_key, value, stack, mat_1h, mat_mid, mat_top` | 없음 | `bands`(폐기·읽기 전용) |

**한 문장 요약**: `x`를 지워도 되는 곳은 **`bin_map`·`origin_log`·`origin_area_map`·`source_region`** 넷뿐입니다. 나머지 블록의 `x`는 손으로 정확히 써야 합니다.

### 2.2 종이를 못 믿겠으면 — 기계에게 물어보는 법 (권장)

dry-run(§3)에서 그 줄의 `derivable` 플래그 **하나만** 보면 됩니다.

| dry-run이 그 역할에 대해 말하는 것 | 뜻 | 철자가 틀렸을 때 할 일 |
|---|---|---|
| `"required": true, "derivable": true` | 좌표/값 역할이고 이 블록에서 **필수** | **지운다.** `removable_declarations`가 지웠을 때 유도될 컬럼을 알려 줍니다 |
| `"required": true, "derivable": false` | 키 역할 또는 `origin_*` — 유도 불가 | **고친다.** 지우면 `not_declared`로 거절됩니다 |
| `"required": false, "derivable": false` | 선택 역할 — **부재가 상태** | **고친다.** 지우면 조용히 그 기능만 사라집니다 |

### 2.3 ⚠️ 이 함정에서 dry-run도 완벽하지 않습니다

선택 좌표를 **이미 지운 뒤에는** dry-run의 `columns`에서 그 줄이 그냥 **없어질 뿐**이고, `accepted`는 `true`로 남습니다. 실측:

```
D  total_chips {lot, slot, x: dt_x, y: dt_y}  -> accepted=true, columns: lot slot x y
E  total_chips {lot, slot}                    -> accepted=true, columns: lot slot        ← 경고 없음
```

**둘 다 초록입니다.** 그러니 `derivable` 플래그는 **지우기 전에** 봐야 합니다. 지운 뒤에 그 결정을 되짚을 계기는 없고, 남는 증상은 「숫자가 여전히 그럴듯한데 영역 스코프 집계만 사라짐」입니다(각 역할의 정확한 손실은 §8 사전에 적혀 있습니다).

---

## 3. dry-run — 「내가 쓴 게 먹었나」를 묻는 자리

```bash
curl -s -H "X-Admin-Token: $ASSY_ADMIN_TOKEN" \
  http://<서버>:8080/admin/transfer-plan/dry-run | python -m json.tool
```

> 🔴 **[2026-08-06 정정] 종전 이 줄의 포트는 `8000`이었습니다** — 런처가 띄우는 uvicorn 포트는 **8080**(`ASSY_API_PORT`)이고 `:8000`은 `uvicorn`을 직접 쳤을 때의 기본값입니다.

읽기 전용입니다 — 모델·컬럼 **해석만** 하고 **행을 조회하지 않으며** 파라미터가 없습니다(선례: `GET /admin/enrichment/auto-confirm/dry-run`). `GET /api/transfer-plan/stages`는 역할마다 `connected`/`missing` **한 단어**를 냅니다. 그 단어로는 config를 고칠 수 없습니다.

### 3.1 역할 1건이 답하는 것

```jsonc
{
  "role": "bin_map",
  "where": "stages.bonding.bin_map",     // 어느 줄을 읽었는지 (구체 경로)
  "declared": true,
  "table": "dt_log",
  "accepted": false,
  "reason": "candidate_column_missing",  // 닫힌 어휘 — §6의 표
  "detail": "...",                       // 화면에 그대로 나가는 한국어 문장
  "required": ["lot","slot","x","y","bin"],
  "columns": {
    "x": { "column": "x", "origin": "declared", "required": true,
           "derivable": true, "derived_from": null, "exists_on_table": false }
  },
  "removable_declarations": [{"role":"x","would_derive":"dt_x"}]
}
```

- **`origin`** — `declared`(내가 쓴 철자가 이김) / `derived`(유도됨) / `absent`. 유도도 **조용히 틀릴 수 있으므로** 「됐다」가 아니라 「어느 철자가 이겼다」를 봅니다.
- **`exists_on_table`** — 그 컬럼이 테이블에 실제로 있는가. `false`면 §0의 사고입니다.
- **`derived_from`** — `map_overlay_declared`(오버레이 선언에서) / `map_overlay_derived`(`table_config`의 x/y 관례에서).
- **`columns`는 필수 역할 ∪ 내가 쓴 역할 전부**를 싣습니다 — 자기가 적은 줄이 화면에서 절반만 보이면 안 되기 때문입니다.
- **`counts`** — `total`/`accepted`/`rejected`/`not_declared`/`not_reached`/`derived_columns`/`removable_declarations`. 배포 후 한 번 찍어 두면 다음 사람이 대조할 기준선이 됩니다.

### 3.2 라이브 파일을 그대로 채점한 결과 (2026-08-04, 수리 전)

```
counts: {"total":18,"accepted":2,"rejected":2,"not_declared":7,"not_reached":7,
         "derived_columns":0,"removable_declarations":2}

stage dt        bin_map          not_declared
                (source 역할 7종) not_reached    -> bonding_plan config에 위임됨
stage bonding   bin_map          candidate_column_missing   removable: x->dt_x, y->dt_y
                map_metadata     ACCEPTED
                total_chips      candidate_column_missing
                (나머지 5종)      not_declared
plan_store      registry         ACCEPTED
                source_region    not_declared
```

🗄️ **`not_reached`는 이제 나오지 않습니다** (2026-08-14). 그것은 위임(`source_config_ref`) stage의 상태였고 — 「채워도 읽히지 않는다」 — 위임 경로가 은퇴했습니다(`server/M1_SOURCE_CONFIG_REF.RETIRED.md`). 모든 stage가 자기 `source` 블록을 읽으므로 미선언 역할은 `not_declared`입니다. 어휘 자체(`bonding_plan.BINDING_NOT_REACHED`)는 향후 위임자를 위해 남아 있습니다.

### 3.3 같은 파일, 2026-08-14 (dt 인라인 전환 + `total_chips` x/y 복원 이후)

```
counts: {"total":18,"accepted":6,"rejected":0,"not_declared":12,"not_reached":0,
         "derived_columns":2,"absent_optional_columns":0,"removable_declarations":0}

stage dt        total_chips      ACCEPTED        (core_wafer_map)
                transfer_log     ACCEPTED        (dt_log, core_x/core_y)
                (나머지 6종)      not_declared
stage bonding   bin_map          ACCEPTED        <- x/y는 유도(derived_columns 2의 정체)
                map_metadata     ACCEPTED
                total_chips      ACCEPTED        <- x/y는 «선언». 유도되지 않습니다
                (나머지 5종)      not_declared
plan_store      registry         ACCEPTED
                source_region    not_declared
```

🔴 **`derived_columns: 2`가 §1.1의 규칙을 눈으로 보여 줍니다.** 유도된 두 컬럼은 `bonding.bin_map`의 `x`/`y`입니다(BIN_AXIS_ROLES가 required로 표시). `bonding.total_chips`와 `dt.total_chips`의 `x`/`y`는 **선언돼 있고 유도 대상이 아닙니다** — 지우면 채워지는 것이 아니라 영역·BIN 총계가 `null`이 됩니다. 2026-08-14에 실제로 그렇게 됐습니다(§1.1 경고 참조).

---

## 4. 세팅 절차

1. **스냅샷**: `conda run -n assy_manager python server/scripts/backup_config.py snapshot`
2. **전제 확인** — 참조하는 모든 테이블이 `table_config.json`에 선언돼 있어야 합니다. 계획 저장소 `map_split_registry`는 **제품 소유**이므로 손으로 옮기지 말고 `install_product_tables.py --apply`로 설치하고, **물리 컬럼까지 실존하는지** `information_schema`로 확인하십시오(선언 없이 저장하면 값이 조용히 드롭되고 200이 나갑니다 → [CONFIG_GUIDE §5.8](../CONFIG_GUIDE.md)). `dt_map`·`dt_log`·`bonding_map` 등은 현장 소유 — 실제 이름으로 선언.
3. **좌표를 쓰는 테이블이면 `map_overlay_config.json`을 먼저 봅니다.** 컬럼명이 관례(`x`/`y`/`val`)와 다르면 거기에 **한 번만** 선언하십시오 → [config/map_overlay_config](./map_overlay_config.md). 그러면 이 파일에서 좌표를 다시 쓸 필요가 없어집니다.
4. 파일이 없으면 `transfer_plan_config.json.sample` 복사. **새 stage**는 `stages.<이름>`에 선언:

   ```json
   "dt": {
     "description": "DT: 코어 웨이퍼의 칩을 테이프에 전사.",
     "source_kind": "core",
     "target_kind": "tape",
     "source": {
       "total_chips": { "table": "core_wafer_map",
         "columns": { "lot": "core_lot", "slot": "core_slot", "x": "core_x", "y": "core_y" } },
       "transfer_log": { "table": "dt_log",
         "columns": { "lot": "core_lot", "slot": "core_slot", "x": "core_x", "y": "core_y" } }
     },
     "target_map": { "preset": "TAPE", "table": "dt_map" }
   }
   ```

   🗄️ **소스 선언 형태는 이제 하나뿐입니다** — 인라인 `"source": {...}`. 예전에는 `"source_config_ref": "bonding_plan"`으로 M1 바인딩을 재사용할 수 있었고, 위 `dt` 예시가 바로 그 stage입니다. 그 경로는 2026-08-14에 은퇴했습니다 — 이유와 부활 조건은 `server/M1_SOURCE_CONFIG_REF.RETIRED.md`. ⚠️ **`x`/`y`를 `total_chips`에 반드시 쓰십시오**: 유도는 호출자가 `required`로 표시한 역할만 메우는데, `total_chips`는 어느 사이트에서도 `("lot", "slot")`만 요구합니다(§1.1 참조).
5. **`plan_store`** — 기존 환경이 zone 이전 상태면 라이브 파일에 손으로 역할키를 더해야 합니다(gitignored라 `.sample` 갱신이 따라오지 않음). 유도 대상이 아니므로 **7종 전부** 씁니다:

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
6. **BIN 축이 필요하면** stage(또는 그 `source`) 블록에 §1.1의 짧은 형태로 선언합니다. 신뢰 가능한 잔여에는 `origin_log`까지 필요합니다. (예전에는 「M1 위임 stage에는 선언해도 무효」라는 단서가 여기 있었습니다 — 그 위임 경로가 사라졌으므로 이제 어느 stage에서든 유효합니다.)
7. 저장 — 반영은 자동입니다(**요청마다 재읽기**, 재기동·reload 불필요). `map_overlay_config.json`도 저장하면 즉시 반영됩니다(파일 mtime 기준 메모).
8. 🔴 **저장 직후 dry-run을 찍습니다**(§3). 이것이 반영 확인의 **1순위**입니다 — 아래 §5는 그다음입니다.

### 4.1 검증된 예시 한 벌 (이 환경에서 dry-run 수용 실측)

```json
"bonding": {
  "description": "Bonding: 테이프 위의 칩을 base에 본딩하는 단계.",
  "source_kind": "tape",
  "target_kind": "base",

  "bin_map": {
    "table": "dt_log",
    "columns": { "lot": "dt_lot", "slot": "dt_slot" }
  },
  "source": {
    "identity": { "compose": ["lot", "slot"] },
    "map_metadata": {
      "table": "wafer_map_metadata",
      "columns": { "target_table": "target_table", "map_id": "map_id",
                   "grid_metadata": "grid_metadata" }
    },
    "total_chips": {
      "table": "dt_log",
      "columns": { "lot": "dt_lot", "slot": "dt_slot", "x": "dt_x", "y": "dt_y" }
    },
    "transfer_log": {
      "table": "bonding_log",
      "columns": { "lot": "dt_lot", "slot": "dt_slot", "x": "dt_x", "y": "dt_y" }
    },
    "warnings": { "result_fail_values": ["FAIL"] }
  },
  "target_map": { "preset": "BASE", "table": "bonding_map" }
}
```

**이 한 벌에서 왜 `bin_map`만 짧고 나머지는 좌표를 적었는지가 §2의 전부입니다.** `bin_map`의 `x`/`y`/`bin`은 필수라 유도되고, `total_chips`·`transfer_log`의 `x`/`y`는 **선택이라 유도되지 않으므로** 손으로 정확히 씁니다. 지우면 `total_chips`는 영역·BIN 스코프 집계를 잃고, `transfer_log`는 `connected(count_only)`로 강등돼 `remaining`이 `null`이 됩니다.

⚠️ **이 예시는 이 시뮬레이션 환경의 테이블·컬럼 이름입니다.** 현장 이름으로 바꿔 쓰고, 바꾼 뒤 dry-run을 찍으십시오. [config_reference/](../config_reference/README.md)의 스냅샷은 **현재 이 환경에서 해석되지 않습니다** — 거기서 복사하지 마십시오.

⚠️ **`transfer_log`를 선언하면 `remaining`의 뜻이 바뀝니다**(소모 감산이 들어옵니다). 이것은 패치가 아니라 **결정**입니다 — 선언 전에 그 stage의 소모 로그가 실제로 `bonding_log`인지 확인하십시오.

---

## 5. 반영 확인

1. **`GET /admin/transfer-plan/dry-run`** — §3. 여기서 초록이 아니면 아래는 볼 필요가 없습니다.
2. `GET /api/transfer-plan/stages` — 새 stage가 목록에 뜨고 `total_chips`·`plan_store`가 **`connected`** 인지 (`registry`가 `missing`이면 역할키 7종·테이블 선언부터 재확인). 보조 역할이 **`not_declared`** 로 뜨는 것은 정상입니다 — 그 키를 안 쓴다는 뜻이지 결함이 아닙니다. `missing`은 선언해 놓고 깨졌다는 뜻이므로 이쪽만 고치면 됩니다.
3. `GET /api/transfer-plan/validate?ref_table=<t>&map_key=<k>` — **404면 `plan_store.registry` 역할키 누락**입니다(zone 역할 7종 중 하나라도 빠지면 404 — 조용히 통과시키지 않는 설계).
4. BIN 축을 켰다면 `GET /api/transfer-plan/source-summary?...&bins=...` — `bins.axis: "connected"` 확인.
5. 맵 에디터에서 그 `target_map.table`의 맵을 열면 stage가 유도됩니다 — 어느 stage에도 없는 맵은 `stage_unknown` 경고 + `unverified`(404 아님).

---

## 6. 🔴 화면에 이 문장이 뜨면 — 무엇을 고치는가

거절 사유는 **닫힌 어휘 셋**(+위임을 뜻하는 넷째)이고, 각 사유는 dry-run의 `reason`과 화면 문장이 같은 생성기에서 나옵니다(문장 생성기는 하나뿐입니다).

아래는 **실제로 emit된 문장**입니다(2026-08-04 이 트리에서 실행해 받은 문자열 그대로). 화면에서는 자재 카드의 가용/잔여 칸이 **`미상`**으로 뜨고, 그 칸의 **툴팁(마우스 오버)** 에 이 문장이 그대로 실립니다.

> ⚠️ **화면 문장에는 `stages.<stage>.bin_map` 처럼 `<stage>` 자리표시자가 들어갑니다**(런타임 거절은 stage 이름을 문장에 넣지 않습니다). **dry-run은 `stages.bonding.bin_map`처럼 구체 경로**를 줍니다 — 그래서 고칠 줄을 특정할 때는 dry-run을 봅니다.

### ① `candidate_column_missing` — 선언은 있는데 그 이름의 컬럼이 없다 (가장 흔함)

```
BIN별 가용을 계산할 수 없습니다 ― `bin_map`의 필수 역할이 가리키는 컬럼이 테이블 `dt_log`에
없습니다 (읽는 자리: stages.<stage>.bin_map 또는 stages.<stage>.source.bin_map):
x → `x`, y → `y`. `dt_log`의 실제 컬럼: business_key_val, c_bn, core_lot, core_slot,
core_wafer, core_x, core_y, created_at, dt_cell_key, dt_eqp, dt_job, dt_lot, dt_slot,
dt_x, dt_y, ... 이 역할들은 선언을 **지우면** 유도로 해결됩니다: x → `dt_x`, y → `dt_y`
(`dt_log`의 맵 바인딩에서 유도).
```

**할 일**: 문장이 지목한 역할의 줄을 **지웁니다**(문장 끝이 지우면 무엇이 유도되는지 말해 줍니다). 「지우면 …」 꼬리가 **없으면** 그 역할은 유도 대상이 아니므로 **철자를 고칩니다** — 실제 컬럼 목록이 문장 안에 있습니다.

### ② `not_declared` (A) — 블록 자체가 없다

```
`lot_membership` 선언이 없습니다 (읽는 자리: stages.<stage>.source.lot_membership).
이 축을 쓰려면 `table`과 `columns`(lot, slot)를 선언해야 합니다.
```

**할 일**: 그 축을 **쓸 생각이면** 선언합니다. 안 쓸 것이면 **아무것도 하지 않습니다** — 부재는 결함이 아니라 사이트의 선언이고, 보조 역할은 이 상태에서 강등되지 않습니다(§8 서두).

### ③ `not_declared` (B) — 블록은 있는데 필수 역할 키가 빠졌다

```
`bin_map`의 `columns`에 필수 역할 slot이(가) 없습니다 (읽는 자리: stages.<stage>.bin_map
또는 stages.<stage>.source.bin_map). 선언된 역할: lot / 필요한 역할: lot, slot, x, y, bin.
(유도 대상 역할: bin, val, x, y)
```

**할 일**: 지목된 역할을 씁니다. 괄호의 「유도 대상 역할」에 그 이름이 **없으면**(= 키 역할) 반드시 손으로 써야 합니다.

### ④ `mapping_unavailable` (A) — 테이블이 `table_config.json`에 없다

```
`bin_map`이(가) 가리키는 테이블 `wafer_process`이(가) table_config.json에 선언돼 있지
않습니다 (읽는 자리: ...). 선언된 테이블: bonding_log, bonding_map, core_wafer_map,
dt_job_attribution, dt_log, dt_map, ...
```

**할 일**: **테이블 먼저, 규칙은 그다음**입니다 → [CONFIG_ROLLOUT_GUIDE §4](../CONFIG_ROLLOUT_GUIDE.md). 문장이 선언된 테이블 목록을 통째로 줍니다.

> ⚠️ **위 문장은 «메시지 모양의 예시»이지 현재 상태가 아닙니다.** 하필 예시로 쓴 `wafer_process`는 **2026-08-14 `50a21c7`에 재등재**됐습니다 — 그 표는 2026-07-28~08-04 사이 선언에서 이탈했고 **행은 PostgreSQL에 그대로 살아 있었습니다**(실측 3,022행). 그동안 `process_history` 역할은 `not_declared`였습니다. **선언에서 사라진 표는 「없는 표」가 아니라 「아무도 못 읽는 표」**이고, 이 오류 문구가 정확히 그 상태를 잡는 자리입니다.

### ⑤ `mapping_unavailable` (B) — 생략했는데 유도도 못 했다

```
`bin_map`의 필수 역할 x, y, bin이(가) 선언돼 있지 않고 유도도 되지 않았습니다
(읽는 자리: ...). `wafer_map_metadata`의 맵 바인딩(map_overlay_config.json의
`table_bindings`, 없으면 table_config.json의 x/y 관례)에서 x, y, val을(를) 찾지
못했습니다. 해당 역할을 직접 선언하거나 `wafer_map_metadata`의 맵 바인딩을 선언하세요.
```

**할 일**: 둘 중 하나 — ⓐ 이 파일에 역할을 직접 씁니다, ⓑ `map_overlay_config.json`에 그 테이블의 바인딩을 선언합니다(**여러 config가 같은 테이블의 좌표를 쓴다면 ⓑ가 옳습니다**). **유도 실패는 절대 조용하지 않습니다** — 이 문장이 없으면 유도는 성공한 것입니다.

### ⑥ `mapping_unavailable` (C) — 형태가 읽을 수 없다

`columns`가 객체가 아니거나, `table`이 빈 문자열/누락이거나, 블록 자체가 객체가 아닌 경우입니다. 문장이 **읽힌 값을 그대로 인용**하므로(JSON), 무엇을 썼는지 되짚을 필요가 없습니다.

### ⑦ 🗄️ `not_reached` — 은퇴했습니다 (2026-08-14)

이 사유는 위임(`source_config_ref`) stage만이 받았고, 그 경로가 사라졌습니다
(`server/M1_SOURCE_CONFIG_REF.RETIRED.md`). 지금 그 키가 남아 있는 config는 키가
**조용히 무시되고** stage가 자기 `source` 블록을 읽습니다 — 비어 있으면 `not_declared`
입니다. 어휘(`bonding_plan.BINDING_NOT_REACHED`)는 `BINDING_REFUSALS`에 남아 있으므로
향후 위임자가 같은 단어를 쓸 수 있습니다.

예전 문장(참고용 — 이제 나오지 않습니다):

```
이 stage는 소스 역할을 `bonding_plan` config에 위임합니다(`source_config_ref`) ―
`stages.dt.source.total_chips`은 읽히지 않습니다. 이 역할은 bonding_plan_config.json에서
선언하세요.
```

**할 일**: `bonding_plan_config.json`을 고칩니다. **여기를 채우면 안 됩니다** — 채워도 아무 일도 일어나지 않습니다. (이 사유는 dry-run에서만 나오며 런타임 거절 문장에는 등장하지 않습니다.)

### 그 밖에 화면에서 만나는 문장

| 화면 문장(접두) | 뜻 |
|---|---|
| `로트 전체 가용을 계산할 수 없습니다 ― 슬롯을 셀 원천이 둘 다 없습니다. ① … ② …` | `scope=lot`인데 `lot_membership`도 `bin_map`도 못 읽음. **①과 ②가 각자의 사유를 따로** 말합니다 — 하나로 뭉치면 「자재 대장을 안 쓰는 정상 사이트」와 「`bin_map` 컬럼 오타」가 같은 글자로 보고됩니다 |
| 🗄️ `core-kind(M1 위임) 소스는 BIN별 감산을 계산할 좌표 집합을 갖지 않습니다.` | **더 이상 나오지 않습니다** (2026-08-14 위임 경로 은퇴). 같은 상황은 이제 `bin_map` 미선언 사유로 나옵니다 — 선언하면 동작합니다 |
| `BIN 분포 조회에 실패했습니다: …` / `BIN 좌표 조회에 실패했습니다: …` | config가 아니라 **질의 실패**입니다(이 경우 `reason`은 비어 있습니다 — 닫힌 어휘 밖의 원인에 억지로 단어를 붙이지 않습니다) |
| `로트 '<lot>'의 슬롯이 상한(50)을 넘어 전체를 합산할 수 없습니다.` | `MAX_LOT_SLOTS` 초과 — 부분합을 지어내지 않습니다 |

---

## 7. 잘못됐을 때 (복구)

```bash
conda run -n assy_manager python server/scripts/backup_config.py restore transfer_plan_config_<yymmdd>.json.bak --yes
```

요청마다 재읽으므로 복원 즉시 반영. 단 **`table_config`·물리 컬럼과 얽힌 문제**(zone 컬럼 미선언으로 저장이 드롭된 경우 등)는 config 복원만으로 안 돌아옵니다 → [ROLLBACK_PROCEDURE](../ROLLBACK_PROCEDURE.md).

---

## 8. 역할 사전 (키 참조)

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

**공통 규율**: 모든 바인딩은 `{table, columns}` 형태이고, 테이블이 `table_config` 미선언이거나 **필수** 컬럼이 (선언으로도 유도로도) 해석되지 않으면 그 역할은 통째로 `missing`입니다(부분 해석 없음). **[2026-07-28] 선언했는데 모델에 없는(오타) 비필수 컬럼은 사라지는 대신 `connected(column_unresolved:<역할키들>)`로 강등 표시됩니다** — 전 역할 공통(`bonding_plan._demote_for_unresolved` 공유). 역할 강등은 조용히 지나가지 않습니다 — `warnings[].type: "source_degraded"`로 표면화되고, 감산항(fail·기전사)이 강등되면 `chips.remaining`이 **`null`로 내려갑니다**(`remaining_reliable: false`, total이 살아 있으면 `remaining_upper_bound`만 제공). validate는 강등된 소스에 대해 부족 판정을 **하지 않고** `availability_unreliable`을 냅니다("검사 안 함" ≠ "이상 없음"). 강등 status의 의미 사전은 [CONFIG_GUIDE §5.8](../CONFIG_GUIDE.md)이 정본입니다.

**[2026-08-04 `2c2a777`+`101311f`] 보조 역할 선언은 선택입니다 — 상태는 둘이 아니라 셋입니다.** 판정 기준은 **키가 블록에 있느냐**이지 값이 쓸 만하냐가 아닙니다(`bonding_plan.role_is_declared`).

| config 상태 | 역할 status | `chips.remaining` | 강등인가 |
|---|---|---|---|
| 키가 **아예 없음** | **`not_declared`** | **숫자** — 그 감산항 없이 계산 | 아니오. `source_degraded` 경고 없음 |
| 키는 있는데 깨짐 (`null`·`"None"`·테이블/컬럼 오타) | `missing` / `connected(count_only)` / `connected(column_unresolved:…)` | `null`(+상한) | 예 — 종전 강등 그대로 |
| 키가 있고 정상 | `connected` | 숫자 | 아니오 |

- 대상은 **`transfer_log`·`origin_log`·`fail_sources`·`process_history`** 넷뿐입니다. **`total_chips`는 예외로 계속 필수** — 분모가 없으면 가용이 성립하지 않으므로 부재도 `missing`이고 `remaining`은 `null`입니다. 이 완화를 "이제 다 선택"으로 일반화하지 마십시오.
- **빠진 감산 종류는 응답이 이름으로 말합니다** — 최상위 선택 필드 `inactive_subtractions`(예: `["transfer_log", "origin_log", "fail_sources"]`). 가용 수치를 내는 **모든** 응답에 같은 이름·같은 모양으로 실립니다: 슬롯 요약 · `scope=lot` 요약 · M1 `core-summary` · `POST /api/transfer-plan/validate`. 목록이 비면 필드 자체가 없으므로 **전 역할을 선언한 환경의 응답은 완화 전과 바이트 단위로 동일**합니다. `process_history`는 감산항이 아니므로 이 목록에 안 들어갑니다.
- **`transferred`·`used`는 `null`인데 `remaining`은 숫자입니다.** 소모 로그가 없으면 몇 개를 썼는지는 미상이지만(가짜 `0` 금지), 그 감산항이 존재하지 않는다는 것은 사이트의 선언이므로 잔여는 미지수가 아닙니다. 신뢰도의 권위는 여전히 `remaining_reliable` **하나**이고, 이 경로에서는 `true`입니다.
- **`validate`의 판정(`status`)은 이 때문에 바뀌지 않습니다** — 미선언은 결함이 아니라 선언이라 `ok`는 계속 `ok`입니다.
- 클라가 이 자격을 어떻게 그리는지(가용·잔여 셀의 `*` 각주 표시와 역할명 노출)는 [MAP_EDITOR_SPEC §6.2-ter](../../spec/MAP_EDITOR_SPEC.md)가 정본입니다.

### 8.1 stage 키 (`stages.<이름>`)

**`description`** (필수) · **`source_kind`/`target_kind`**
- 역할: `/stages` 응답과 소스 요약에 그대로 실리는 **표시 라벨**입니다.
- 함정: `source_kind`는 표시 라벨일 뿐 **계산 경로의 스위치가 아닙니다.** 2026-08-14부터 모든 stage가 같은 인라인 엔진을 타며, 가르는 것은 선언된 역할입니다(`origin_log`가 있으면 집합 감산, 없으면 `total − Σfail − used`). 예전에는 `source_config_ref` 유무가 경로를 갈랐습니다.

**`target_map: {preset, table}`**
- 만드는 판정: **맵 테이블 → stage 역인덱스**. 맵 에디터에서 `table`의 맵을 열면 stage가 유도되고, `/validate`도 이걸로 stage를 찾습니다. `preset`은 에디터 표시용.
- 미선언/오타: 그 테이블은 어느 stage에도 안 속함 → validate가 `stage_unknown` 경고 + **수량·가용·fail 검증 전부 생략**(status `unverified` — 404 아님. "경고 없음 = 이상 없음"이 아닙니다).
- 함정: 두 stage가 같은 `table`을 선언하면 **먼저 선언된 stage가 이깁니다**(첫 매치).

🗄️ **`source_config_ref`** — **RETIRED 2026-08-14**
- 무엇이었나: 소스 가용을 M1 `bonding_plan_config.json`의 바인딩으로 위임하는 키였고, 허용값은 `"bonding_plan"` 하나였습니다. 그 경로를 쓰던 유일한 stage(`dt`)의 역할 다섯이 전부 `missing`이었고, 원인은 M1 config가 **`table_config.json`에서 빠진 테이블**과 **선언에서 빠진 컴럼**을 가리키고 있었기 때문입니다. 근거·부활 조건은 `server/M1_SOURCE_CONFIG_REF.RETIRED.md`.
- 지금 이 키가 남아 있으면: **조용히 무시**되고 stage가 자기 `source` 블록을 읽습니다. 비어 있으면 전부 `not_declared`이고 `total_chips`가 없어 `chips.total=0`·`remaining=null`입니다. **지우십시오.**
- 대체: 인라인 `"source": {...}`. 더 표현력이 놓습니다 — `origin_log`·원천별 `frame`을 가진 `fail_sources`·`bin_map`·`lot_membership`은 위임 경로가 도달할 수 없던 것들입니다.
- ⚠️ **M1 자체는 은퇴하지 않았습니다** — `GET /api/bonding-plan/core-summary`와 `bonding_plan_config.json`은 살아 있습니다. 다만 **그 라우트도 같은 이유로 역할 다섯이 `missing`이고 `remaining: 0`을 냅니다**(2026-08-14 실측). 총괄 판정 대기 — `bonding_plan_config` 가이드 참조.

**`bin_map`** (선택 — stage 블록 또는 `source` 블록, stage 쪽 우선)
- 필수 역할: `lot, slot, x, y, bin` — 그중 **`x`·`y`·`bin`은 유도됩니다**. 짧은 형태는 `{table, lot, slot}`(§1.1).
- 만드는 숫자: `?bins=` 요청 시 `bins.entries[]` — BIN별 **가용**(= 그 BIN 셀들로 스코프한 remaining)·`cells`·`bin_absent`/`unknown` 판정. `lot_membership` 미선언 시 로트 전개의 강등 슬롯 원천이기도 합니다.
- 미선언: `bins.axis: "unavailable"` + `bin_axis_unavailable` 경고. `bins=`를 안 붙인 기본 응답은 **아무 영향 없음**.
- 함정: ① `origin_area_map`의 `val` 재사용 금지(출신 코어 식별자일 수 있음 — 서버는 BIN 컬럼을 **추측하지 않습니다**. 유도는 그 테이블의 **선언된** 맵 바인딩 `val`에서 오는 것이지 추측이 아니며, `fallback_guess`는 거부됩니다). ② BIN 값은 층 경계와 같은 정수 판정기 — `'1'`·`'01'`·`' 1 '`은 한 BIN, 비정수 셀은 버리지 않고 `unbinned_cells`로 계수. ③ 소스 집계가 **강등**이면(예: `origin_log`를 선언해 놓고 테이블/컬럼이 깨진 경우) **BIN 전부 `unknown` + `remaining=null`로 강등**됩니다 — BIN 축만 이어도 소용없습니다. **[2026-08-04] 반면 `origin_log` 키가 아예 없으면 강등이 아니므로 BIN은 `ok` + 숫자로 나갑니다.** 단 이 경우 BIN별 총계는 `total_chips`의 `x`/`y`에서 오므로 **그 좌표를 바인딩해야 합니다**(그쪽 `x`/`y`는 선택이라 유도되지 않습니다 — §2) — 없으면 `total_pts`를 못 만들어 다시 `unknown`입니다.

### 8.2 inline `source` 역할

**`identity: {compose}`** (기본 `["lot","slot"]`)
- 역할: 출신(core) 맵 ID 합성 규칙 — `compose`를 `_`로 이어 `wafer_map_metadata.map_id`를 조회하는 키.
- 미선언: 기본값 사용, 죽는 것 없음.
- 함정: 메타의 `map_id` 합성 관례와 어긋나면 메타 조회가 빗나가 frame=`origin` fail이 `align_unavailable`로 강등됩니다.
- **[2026-07-29 7b] 합성·바인드 값은 선언 타입으로 캐노니컬화됩니다** — 조회 대상 테이블의 `table_config` 선언 타입이 `number`인 컬럼은 `'01'`·`' 1 '`·`1.0`이 전부 `'1'`로 합성/바인드되고, `string` 선언은 공백만 제거하고 원문 유지(패딩이 유의미). 구현은 `map_overlay.canonical_key_value` **하나**이며 모든 pool lot/slot 바인드와 `map_id` 합성·`map_key` 분해가 이것을 경유합니다.

**`map_metadata`** — 필수 `target_table, map_id, grid_metadata` · **유도 대상 없음**
- 만드는 판정: 프레임 정렬(회전·면·y반전·start)의 유도 원천 — 출신 코어 fail 좌표를 canonical 프레임으로 옮기는 근거. 정렬이 적용되면 `sources`에 `connected(aligned:180)` 마커.
- 미연결: **소스 맵만** 메타가 있으면 그 fail 원천이 `connected(align_unavailable)`(fail=0 + remaining 신뢰 불가 — 비대칭 지식은 identity로 가정하지 않음). **양쪽 다** 메타가 없으면 identity로 간주해 그대로 붙습니다(실패 아님).
- 함정: 메타를 한쪽 맵에만 등록하면 등록 안 한 것보다 오히려 강등됩니다.

**`total_chips`** — 필수 `lot, slot` · 🔴 **`x`/`y`는 선택이고 유도되지 않습니다**
- 만드는 숫자: `chips.total` — **가용의 분모**. `(lot, slot)` 행 수 count.
- 🔴 **`x`/`y`를 지우지 마십시오.** 이 블록의 좌표는 `bin_map`의 좌표와 **글자만 같고 규칙이 반대**입니다(§2). 없으면 영역 스코프 집계와 BIN별 총칩 좌표(`total_pts`)가 사라지는데, **`total` 숫자 자체는 그럴듯하게 남아** 사라진 것을 알기 어렵습니다. dry-run은 이 블록의 `x`를 `"required": false, "derivable": false`로 표시합니다.
- 미연결: **분모 자체가 불명** — `total_unknown` 강등으로 `remaining=null`(상한도 없음), validate는 그 소스의 모든 수요를 `availability_unreliable`로 내림. 이 역할이 죽으면 화면의 가용은 전부 미상입니다.
- 🔴 **[2026-08-04] 이 역할만 완화의 예외입니다** — 다른 보조 역할과 달리 **키를 지워도 `not_declared`가 아니라 `missing`**입니다(`_aux_role_status`를 타지 않습니다).
- 함정: "행 수 = 칩 수"(칩당 1행 유일)를 가정합니다 — 중복 행이면 total이 과대인데 **현재 미표면화**(알려진 한계).

**`transfer_log`** — 필수 `lot, slot` · **`x`/`y`는 선택이고 유도되지 않습니다**
- 만드는 숫자: `chips.transferred` — **기전사 차감**. `x`/`y`가 있으면 distinct `(x,y)` 칩 수, 없으면 행 count.
- **[2026-07-29 7c] `"transfer_log": "none"` — 소모 기록이 없다는 선언**: 사이트에 전사(소모) 로그 자체가 없으면 정확히 문자열 `"none"`을 선언하십시오. 상태는 `connected(untracked)`(강등 아님), `transferred=null`, `remaining=null` + `remaining_upper_bound`(= total − fail) + **전용 경고 `transfer_untracked`**. **값이 있는데 그 값이 아닌 형태**(JSON `null`·`"None"` 등)는 전부 `missing`입니다. ⚠️ 「키 부재」는 여기 속하지 않습니다 — 두 선언은 답이 다릅니다: `"none"`은 "추적하지 않는다 → 상한만 안다", 키 부재는 "그 표 자체가 없다 → 그 감산 없이 센다". (dry-run은 `"none"`을 `accepted: true`로 채점하고 detail에 「소비를 기록하지 않는다고 **선언**돼 있습니다」라고 적습니다.)
- **미선언(키 부재)**: 상태 `not_declared`, 강등 아님. `remaining`은 기전사 감산 **없이 계산된 숫자**(`remaining_reliable: true`), `transferred`는 `null`, `inactive_subtractions`에 `"transfer_log"`가 실립니다.
- **미연결(선언했는데 깨짐)**: `transferred=0`으로 감산이 빠져 remaining 과대 위험 → `remaining=null` + `remaining_upper_bound` + `source_degraded(remaining_overstated)`.
- 🔴 함정: **`x`/`y`까지 바인딩하십시오** — 좌표 없이 count만 되면 **[2026-07-28 `1fefd12`] `connected(count_only)`로 강등**됩니다: `transferred` 카운트는 진짜라 유지되지만 칩 정체를 몰라 집합 감산이 불가능하므로 `remaining=null` + 상한만 제공되고, `by_core`의 used/remaining도 **양 경로 모두 `null`**입니다. **이 좌표는 유도되지 않습니다**(선택 역할) — 정확히 이 강등이 「부재가 정보인 자리」의 실례이고, 유도가 그것을 메우면 아무도 요청하지 않은 숫자 변화가 일어납니다.

**`origin_log`** — 필수 8종 `lot, slot, x, y, origin_lot, origin_slot, origin_x, origin_y` · **`x`/`y`만 유도됨**
- 만드는 숫자 셋: ① **정확 remaining**(합집합 감산 — fail·기전사 이중 차감 없음) ② `by_core` 분해(`by_core_origin: "log"`) ③ frame=`origin` fail을 타깃 좌표로 투영하는 다리.
- ⚠️ **`origin_x`/`origin_y`는 유도되지 않습니다** — 같은 테이블 위의 두 번째 좌표쌍이라 맵 바인딩이 어느 쪽인지 말할 수 없습니다. 짧은 형태는 `{table, lot, slot, origin_lot, origin_slot, origin_x, origin_y}`이고 `x`/`y`만 생략 가능합니다(dry-run 실측 수용).
- **미선언(키 부재)**: 상태 `not_declared`, 강등 아님. remaining은 감산식 폴백(`total − Σfail − used`)으로 **숫자**, `inactive_subtractions`에 `"origin_log"`. `by_core`는 `origin_area_map` 경로로 내려가고, 그것도 없으면 `by_core` 필드 자체가 빠집니다.
- **미연결(선언했는데 깨짐)**: frame=`origin` fail 전부 `unavailable(origin_missing)`, remaining은 폴백이지만 강등이라 **`remaining=null`**. `?bins=` 요청 시 **전 BIN `unknown` 강등**.
- 함정: ① 필수 8종 중 하나만 빠져도(그리고 유도로도 안 메워지면) 역할 전체가 `missing`입니다. ② **선언 간 모순은 계속 표면화됩니다** — `origin_log`가 `not_declared`여도 `frame: "origin"`으로 **선언된** fail 원천이 있으면 그 원천은 `unavailable(origin_missing)` 강등이고 `remaining`은 `null`이 됩니다. 완화는 "안 쓴다"에만 적용되지 "쓴다고 선언해 놓고 다리가 없다"에는 적용되지 않습니다.

**`origin_area_map`** (선택) — 필수 `lot, slot, x, y, val` · **`x`·`y`·`val` 유도됨**
- 만드는 숫자: `origin_log` 미연결 시의 `by_core` **강등 경로** — 영역 귀속 분해(total/used만, **fail은 null**). `by_core_origin: "area_map"`, 상태 `connected(area_only)`.
- 미선언: `origin_log`가 살아 있으면 아예 소비되지 않음(영향 0). 둘 다 죽으면 `by_core` 필드 자체가 응답에서 빠집니다.
- 함정: `core_id`는 영역 맵의 원시 값(불투명) — log 경로의 `core_id`와 문자열 일치를 가정하면 안 됩니다.

**`process_history`** — 필수 `lot, slot` · 나머지 전부 선택 · **유도 대상 없음**
- 만드는 것: `history` 배열(최근 50건, 시간 오름차순). `warnings.result_fail_values`에 걸리는 result는 `result_fail` 경고(validate에서는 `source_history_fail`로 승격).
- 바인딩: `columns {lot, slot, step, eqp, result, time, recipe, knobs}` — `lot`/`slot` 외에는 전부 선택이며 **하나도 유도되지 않습니다**.
- **미선언(키 부재)**: 상태 `not_declared`, `history`는 빈 배열이고 **경고는 나가지 않습니다**. 감산항이 아니므로 `inactive_subtractions`에도 안 실립니다.
- **미연결(선언했는데 깨짐)**: `history` 빈 배열 + `source_degraded(history_incomplete)` — **가용 숫자는 안 죽습니다**.
- 함정: `time`을 안 바인딩하면 정렬 없는 임의 50건이 됩니다. `knobs`는 JSON 파싱 실패 시 raw 문자열 폴백(에러 아님).

**`fail_sources.<name>`** (이름 자유) — 필수 `lot, slot` · 🔴 **`x`/`y`/`val`은 선택이고 유도되지 않습니다**
- 만드는 숫자: `chips.fail_breakdown.<name>` — **fail 차감 축**. `frame: "origin"`은 출신 코어 fail을 `origin_log` 조인 + 메타 정렬로 타깃 좌표에 투영, `frame: "self"`는 자기 좌표 직접 카운트.
- 바인딩: `{"frame": "origin"|"self", "table", "columns": {lot, slot, x, y, val}, "fail_values": ["D"]}`
- 🔴 **`val`을 생략하지 마십시오.** `bin_map`의 `bin`과 달리 **유도되지 않습니다.**
- 🔴 **[2026-08-04 `5d35337` · N14] `fail_values`는 있는데 `val`이 없으면 이제 *거절*합니다 — `connected(fail_value_column_absent)`.** `fail_values`는 **어느 값이** fail인지를 말하고 `val`은 **어디서 읽는지**를 말합니다. `val` 없이는 「이 행이 fail인가」가 **답할 수 없는 질문**이고, **답할 수 없음은 YES가 아닙니다.** 술어 없이 세면 풀 전체가 fail이 되어 감산이 과대 계상되고, 가용량 엔진 전체가 딛고 선 **상한 불변식이 깨집니다.** 그래서 거절하고 **0을 서빙하고 강등**합니다(`align_unavailable`과 같은 규율). 실측된 결함: `dt_log`/`DT-2601-001` slot 22에서 **풀 144행 · fail_values 일치 0행 · 144행 전부가 fail로 계상**됐고, 응답은 그러면서 `reliable: true`라고 말했습니다.
  - ⚠️ **`connected(column_unresolved:val)`과 다른 단어인 것이 요점입니다.** 저쪽은 「컬럼 이름을 댔는데 그 테이블에 없다」(수리: 이름을 고치거나 지운다), 이쪽은 「이름이 아예 없다」(수리: 하나 선언한다). **결과는 같고 지시가 다릅니다.**
- **미선언(`fail_sources` 키 자체가 없음)**: 강등 아님. fail 감산 없이 `remaining`이 **숫자**로 나가고 `inactive_subtractions`에 `"fail_sources"`가 실립니다(개별 원천 이름이 아니라 이 역할명 하나로).
- **미연결(선언한 원천이 깨짐)**: 그 이름의 fail=0 → 감산 과소 → `remaining=null`(+상한) + `source_degraded`. `frame: "origin"`인데 `origin_log`가 없으면 `unavailable(origin_missing)`.
- 🔴 **`fail_sources` 키가 있는데 값이 쓰레기면**(`null`·`"None"`·리스트·숫자) **선언한 것으로 칩니다** — 완화 대상이 아니고 `inactive_subtractions`에도 안 실립니다.
- 함정: ① **`fail_values` 자체를 선언하지 않으면** 필터가 없으므로 **그 테이블 전 행이 fail로 계산**됩니다 — 이쪽은 N14가 안 건드립니다(「전부가 fail이다」는 선언으로 읽힙니다). 거절은 **`fail_values`를 선언해 놓고 `val`을 안 준 경우**뿐입니다. ② **`fail_values`를 선언했는데 `val` 컬럼명이 오타면** 필터 없는 전 행 count를 **거부하고 fail=0 + `connected(column_unresolved:val)` 강등**합니다 — 상한 불변식 때문에 과대 계상 대신 0을 택합니다. ③ `frame` 생략 시 기본값이 고정이 아닙니다 — `origin_log` 연결 여부에 따라 바뀌므로 **명시하십시오**. ④ 구 `align` 선언은 폐지 — 무시되며 변환은 `wafer_map_metadata` 델타에서 유도. ⑤ **[`deed6d2`] `frame: "self"` 원천도 `x`/`y`까지 바인딩하십시오** — `origin_log`가 connected인 집합 감산 경로에서 self fail이 좌표 없이 count만 제공하면 `transfer_log`와 같은 **`connected(count_only)` 강등**입니다(`remaining=null` + 상한). count를 대신 감산하지 않는 이유는 상한 불변식이고, `origin_log` 없는 폴백 감산 경로에서는 count 감산이 정확해 강등하지 않습니다.

**`warnings: {result_fail_values}`**
- 역할: 이력 result가 이 목록(문자열 완전 일치)에 있으면 `result_fail` 경고 발화.
- 미선언: 이력 fail 경고만 침묵 — 다른 것은 안 죽습니다.

**`lot_membership`** (선택) — 필수 `lot, slot` · **유도 대상 없음**
- 만드는 것: `scope=lot` 전개의 **슬롯 대장** — `by_slot` 목록과 `map_exists` 진단("전산에는 있는데 맵이 없는 슬롯" = `lot_slot_map_missing`)의 원천. 이 진단이 이 역할의 존재 이유입니다.
- 미선언: `bin_map`의 distinct 슬롯으로 강등 폴백(`slots_origin: "map"` + `lot_membership_degraded`) — **맵 없는 슬롯이 안 보여 진단이 성립하지 않습니다**. `bin_map`도 없으면 `slots: null`·`slots_status: "unknown"`(§6의 `① … ②` 문장이 이 경우입니다).
- 함정: 로트의 슬롯이 50(`MAX_LOT_SLOTS`) 초과면 부분합을 지어내지 않고 합산 전체를 거부합니다.

### 8.3 `plan_store` 역할

**`registry`** (필수) — 필수 역할키 7종 · **유도 대상 없음**
- 만드는 판정: **계획(legend/DOE) 저장소** — `/validate`가 `(ref_table, map_key)`로 행을 읽어 zone 컬럼에서 수요를 **유도**합니다(`total = painted(값) × layers`, `share = ceil(total / 자재 수)`). `doe_count`·`qty_shortage`·`source_overallocated`·V1~V5 판정 전부 이 행들에서 나옵니다.
- 바인딩: `ref_table`·`map_key`·`value`·`stack`·`mat_1h`·`mat_mid`·`mat_top` — §4의 스니펫 참조. 🗄️ `bands`는 선택·읽기 전용.
- 미연결(역할키 하나만 빠져도): **`/validate` 404**. `/stages`에 `plan_store.registry: "missing"`. `source-summary`는 registry를 안 읽으므로 영향 없음.
- 함정: ① `map_split_registry.stack`은 `table_config`에서 **`"string"`**("number"로 바꾸면 저장 실패/조용한 변조). ② 폐기 계획(`bands` blob)이 남은 사이트는 `bands` 역할키를 **유지**하십시오 — 빼면 그 행들이 "계획 없음"으로 보이고, 다음 legend 저장(replace_map)이 옛 계획을 빈 집합으로 덮을 수 있습니다.

**`material_identity: {compose, separator}`**
- 만드는 판정: **게이트 전용** — "이 배포의 자재 문자열이 lot/slot 모양"이라는 선언. 실제 분해는 config가 아니라 공유 토큰 문법(`lot[_slot][:BIN]`, `parse_material_token`)이 합니다 — 클라는 config를 못 읽으므로 파싱 규칙을 여기 두면 양쪽이 갈립니다.
- 미선언: **모든 자재가 `source_unresolved`** → 수량 검증 전면 생략 → 계획 status `unverified`.
- 함정: `separator`/`compose` 값을 바꿔도 파싱은 안 바뀝니다(게이트일 뿐).

**`source_region`** (선택 · ⚠️ 휴면 — 총괄 지시로 보류) — 필수 `ref_table, map_key, source_lot, source_slot, x, y` · **`x`·`y` 유도됨**
- 만드는 숫자(활성화 시): 자재별 "쓰기로 한 사용 영역" 셀 집합 → `region_chips`(영역 내 가용).
- 미선언: `region_chips`가 응답에 없을 뿐 — 결함 아님(라이브 config가 일부러 미선언).
- 함정: 선언만 하고 테이블이 없으면 `/stages`에 `missing` 소음만 만듭니다.

zone·마커 0·V1~V6·`bands` 이관의 전체 의미론은 [CONFIG_GUIDE §5.8](../CONFIG_GUIDE.md)이 정본.
