# 2026-08-14 10:35 — 삭제가 표지만 지우고 기능은 꺼둔 채로 남겼다

> **주제:** `transfer_plan_config.json`의 `dt` stage를 M1 위임(`source_config_ref`)에서
> 인라인 선언으로 옮기고, 위임 경로를 은퇴시켰다. 그리고 같은 날 아침의 수리 하나를
> 정정했다 — 그 정정이 이 기록의 이유다.
> **파일:** `server/config/transfer_plan_config.json`(+`.sample`) · `server/transfer_plan.py` ·
> `server/M1_SOURCE_CONFIG_REF.RETIRED.md`(신규) · 테스트 3종 · 가이드 3종

## 1. 아침의 수리는 옳은 진단 위에 틀린 규칙을 얹었다

`bf65396`이 `bonding.total_chips`의 `"x": "x", "y": "y"`를 지웠다. 진단은 옳았다 —
`dt_map`의 좌표는 `dt_x`/`dt_y`다. 규칙도 그 파일이 2026-08-04에 스스로 적어 둔 것이었다:
**「선언된 역할이 파생을 이기므로, 틀린 철자는 고칠 수 없고 지워야만 고쳐진다.」**

그런데 지운 뒤에도 사용자의 증상이 그대로였다. 실측(`:8080`, 삭제가 반영된 상태):

```
GET /api/transfer-plan/source-summary?stage=bonding&lot=DT_LOT&slot=1&bins=
bins.entries[0] = {"bin":1,"status":"unknown","cells":14,"total":null,"remaining":null,
                   "reason":"총칩 좌표를 알 수 없어 BIN별 총계를 계산할 수 없습니다"}
```

역할 상태는 `connected(column_unresolved:x,y)`에서 **깨끗한 `connected`로 올라갔다.**
즉 **삭제는 유일한 표지를 지웠고 기능은 그대로 꺼져 있었다.** 이것이 원래 결함보다 나쁘다 —
틀린 철자는 적어도 자기가 틀렸다고 말하고 있었다.

## 2. 규칙의 경계는 「필수 역할」이었다

`bonding_plan.resolve_effective_columns`는 **호출자가 `required`로 표시한 역할만** 메운다
(`wanted = [r for r in required if r in DERIVED_ROLE_OF and r not in columns]`).

| 역할 | 해석 시 `required` | 지우면 |
|---|---|---|
| `bin_map.x/y` | `BIN_AXIS_ROLES = (lot, slot, x, y, bin)` — **포함** | 맵 바인딩이 메운다 ✅ 2026-08-04 규칙 성립 |
| `total_chips.x/y` | 모든 사이트가 `("lot","slot")` — **미포함** | 아무도 안 메운다 ❌ 영역·BIN 총계가 `null` |

`DERIVED_ROLE_OF`의 주석이 이미 그렇게 적고 있었다 — "ANY role the caller did not mark
`required` … Absence is only ever filled where absence would otherwise be a refusal."
**「지워라, 고쳐 쓰지 마라」는 필수 역할에 대한 규칙이고, 선택 역할에서는 정반대다.**
그래서 `x: dt_x, y: dt_y`를 **다시 선언했고**, BIN 1이 `total 14 / remaining 14 / reliable`
로 살아났다. 두 config(`.json`과 `.sample`)의 주석이 이제 두 경우를 갈라 적는다.

## 3. `dt`의 다섯 `missing`은 원인이 둘이었다

하나로 설명되지 않는다:

1. **넷 — 테이블이 «선언»되지 않았다.** `core_defect_map`·`eds_fail_map`·`wafer_process`가
   `table_config.json`에 없어 동적 모델이 없다. 셋 다 은퇴한 픽스처다(수집기가
   `auto_update_control.disabled`에 있고, `20260728-005810`과 `20260804` 백업 사이에
   `table_config`를 떠났다). **행은 남아 있다** — 5,152 / 2,576 / 22.
2. **하나 — 테이블은 선언됐고 컬럼이 아니다.** `used_chips`가 가리킨
   `bonding_log.core_lot/core_slot/cx/cy`는 **물리적으로 실재하지만** 그 테이블의
   `table_config` 선언에 없어 ORM 속성이 없다. 게다가 **357,796행 전부 NULL**이라,
   선언을 고쳤어도 조용한 `transferred: 0`이 나왔을 것이다. DT 소모 로그는 `dt_log`다
   (`core_lot` 12,007/13,789, `core_x` 13,789/13,789).

「컬럼이 실재한다」는 참이면서 무관했다. 모델이 보는 것은 물리 테이블이 아니라 선언이다.

## 4. 결과

`dt`는 `core_wafer_map`(총칩)과 `dt_log`의 코어 좌표(전사 로그)에 인라인으로 붙었다.
재기동 없이(config는 요청마다 재읽기) 즉시:

```
dt  total_chips:connected  transfer_log:connected
    process_history:not_declared  origin_log:not_declared
source-summary(dt, CL-2601-001, 03) -> total 121 / transferred 50 / remaining 71
```

독립 대조(SQL): `core_wafer_map` 121행, `dt_log` distinct `(core_x, core_y)` 50 — 일치.

## 5. 은퇴가 «가져간 것»도 적는다

- **core 프레임 fail 원천이 더는 정렬되지 않는다.** M1은 `canonical_basis`로 fail 맵을
  코어 프레임에 사상한 뒤 교차했다. 인라인 엔진의 `_canonical_fail_set`은 `frame:"origin"`
  갈래에서만 불리고 그쪽은 `origin_log`를 요구한다. **카운트는 정렬 불변이라 헤드라인은
  같고**, 어긋나는 것은 영역·BIN의 좌표 교차다. 라이브는 잠복 상태(`dt`가 fail 원천을
  선언하지 않음). `test_core_frame_fail_source_is_not_aligned`가 그 부재를 못 박는다 —
  회전을 바꿔도 결과가 안 변한다는 단언이고, 기능이 돌아오면 뒤집을 자리다.
- **`region_chips.fail_breakdown`이 원천별 키를 잃었다** — `{"defect":n,"eds_fail":m}` →
  `{"all_fail":n}`. `bonding` stage는 처음부터 그랬다. 소비자 0(`client2`에 철자 없음).

## 6. 남은 판정 — M1 라우트는 살아 있고 아무것도 못 센다

제품 소유자의 판정은 **`bonding_plan_config.json` 은퇴**였다. 그런데 소비자가 하나 남아
있다: `GET /api/bonding-plan/core-summary`. 그리고 **그 라우트는 지금 이렇게 답한다**:

```
sources: 다섯 역할 전부 missing
chips:   {"total":0,"defect":0,"eds_fail":0,"used":0,"remaining":0}
```

`remaining: 0`은 「없다」가 아니라 「못 읽었다」다 — 조용한 0. 원인은 §3과 같다.
라우트를 지우는 것은 REST 경로라 경계 계약이므로 **지우지 않고 보고한다.** 선택지는
ⓐ 세 테이블 재등록 + 수집기 재개, ⓑ 라우트와 config를 함께 은퇴.
근거·부활 조건은 `server/M1_SOURCE_CONFIG_REF.RETIRED.md`(map_doe `c0fb735`와
`migrate_map_meta_to_wafer_id.RETIRED.md`가 세운 관례를 따랐다 — 승인·실측 사유·
은퇴가 못 하는 것·부활 조건).

## 7. 검증

`test_transfer_plan` · `test_transfer_plan_derivation` · `test_optional_role_absence` ·
`test_availability_relaxation` · `test_plan_frame_basis` · `test_bonding_plan` ·
`test_binding_refusal` · `test_transfer_untracked` — **234 passed**.

정렬 부재를 못 박는 테스트는 **계기부터 검증했다**: eds의 저장 좌표를 영역 안으로 옮기면
`all_fail`이 1→2로 움직인다(일회용 프로브로 실측 후 제거). 즉 그 테스트는 「닿지 않는
원천」이 아니라 「정렬」을 재고 있다.
