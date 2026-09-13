# 완료 보고: Universal Transfer Plan M2 — 서버부 (전사 프레임워크 + DOE 영속화 + fake DT 데이터)

> 지시서: `agent_workspace/tasks/Server_transfer_plan_m2_task.md`
> 작업 위치: 메인 트리. **커밋 없음. 재기동 없음. client2/ 무접촉.**
> 기반: 스펙 §7.5b DT 계층 + M1 보고서/코드(`server/bonding_plan.py`)
> ⚠️ 세션 중도 종료(모델 한도) 후 재개 — 재개 시점 상태 점검 결과는 §9.

---

# 📋 §0. 클라부 전달 계약 (총괄이 클라 지시서로 그대로 옮길 부분)

> 스위트 **339 passed / 1 allowed fail**. 신규 라우트는 **재기동 후 활성화**된다.
>
> ⚠️ **총괄 기대치(333)와 6건 차이 — 사유**: 소스 영역(②) 엔진 코드와 테스트 6종이 **보류 지시가 도착하기 전에 이미 완성**돼 있었다. 되돌리는 것 자체가 새 코드 변경이라 **코드는 그대로 두고 config 선언만 제거**해 기능을 완전히 휴면 상태로 만들었다(§16-0). 테스트는 자체 픽스처를 쓰므로 라이브와 무관하게 통과한다.

## 0-1. 범용 맵 오버레이 — `GET /api/maps/overlay`

**계획 전용이 아니다.** 임의의 맵을 임의의 맵 캔버스 위에 정렬해 겹치는 맵 인프라이며, 계획 UI는 소비자 중 하나다.

```
GET /api/maps/overlay
  ?target_table=<맵 테이블>       # 캔버스가 될 맵
  &target_key=<map_id>            # 관례: "<lot>_<slot>" 등 wafer_map_metadata.map_id
  &sources=<csv>                  # "table" 또는 "table:key" (키 생략 시 target_key 승계), 최대 8종
  [&eqp=<장비명>]                 # by_eqp align 선택용(선택)
  [&limit=<셀 상한>]              # 기본·최대 20,000
```

응답:
```jsonc
{
  "target": { "table": "core_defect_map", "key": "LOT-A_05",
              "grid": {"cols":40,"rows":40,"start_x":1,"start_y":1} },
  "cell_cap": 20000,
  "overlays": [
    {
      "source_table": "eds_fail_map",
      "source_key": "LOT-A_05",
      "cells": [ {"x": 1, "y": 1, "val": "F"} ],   // ★ 타깃 프레임 좌표로 이미 정렬됨
      "count": 1288,
      "truncated": false,                          // true면 cap 필드 동반
      "align_applied": { "rotation": 180, "flip": "none",
                         "offset": {"x":0,"y":0},
                         "origin": "derived",      // declared|default|derived|identity
                         "note": "..." },          // 선택 — 폴백 사유 등 정보성
      "status": "ok"                               // ok|align_unavailable|source_missing|no_data
    }
  ]
}
```

**클라가 지켜야 할 것**
- `cells`는 **이미 타깃 좌표계**다. 클라가 추가로 회전/반전하면 안 된다(이중 변환).
- `val`은 **원시 값**이다. 색·라벨 매핑은 클라 몫.
- `status !== "ok"`면 그 오버레이는 **표시하지 말고 사유를 알려라**. `align_unavailable`은 "정렬 근거가 없어 못 붙임"이지 "데이터 없음"이 아니다. `no_data`는 정상인데 셀이 0건.
- `truncated: true`면 **일부만 그려졌음을 반드시 표기**하라(조용히 그리면 F1 계열 결함 재발).
- `align_applied.origin`으로 "180° 정렬됨(맵 규격에서 유도)" 같은 안내를 띄울 수 있다.

## 0-2. 페인트 잠금 선언 — `GET /api/maps/paint-rules?table=<맵 테이블>`

```jsonc
{ "table": "transfer_plan_map",
  "rules": { "enabled": true,
             "blocking_values": [],                        // 이 맵 자신의 값 중 잠금 대상
             "from_overlay": ["core_defect_map","eds_fail_map"], // 이 오버레이에 셀이 있으면 잠금
             "message": "불량 칩 위치라 배정할 수 없습니다 (오버레이 기준)." } }
```

**계약: 잠금 값은 서버 config가 정본이다. 클라는 `"F"` 같은 값을 하드코딩하지 마라.**
`enabled: false`(기본)면 잠금 없음. `blocking_values`는 대상 맵 자신의 셀 값 기준, `from_overlay`는 해당 오버레이에 셀이 존재하는 좌표를 잠근다. `message`는 사용자 안내 문구.

## 0-3. 소스 가용 응답의 신뢰도 필드 (F1 — 이미 반영, 재확인용)

`GET /api/transfer-plan/source-summary`의 `chips`:
- `remaining_reliable: false`이면 **`remaining`은 `null`**이고 `remaining_upper_bound`(있을 때)만 온다. **null을 0이나 상한으로 대체 표시하지 마라** — "미상"으로 표기.
- `warnings[]`에 `source_degraded`(role/status/effect/detail)와 `result_truncated`가 온다. `effect: "remaining_overstated"`는 "이 수치는 실제보다 클 수 있다"는 뜻.
- `by_core_truncated: true` / `truncated: [...]`도 표기 대상.

`GET /api/transfer-plan/validate`:
- `status`는 `ok` | `warnings` | **`unverified`** 3값. **`unverified`는 "이상 없음"이 아니라 "검사하지 못함"**이다 — 초록 배지 금지.
- `availability_checked: false`면 수량·fail 검증이 수행되지 않았다.
- 신규 경고 타입: `availability_unreliable`(판정 불가), `source_overallocated`(소스별 합산 초과 — `required_total`/`available`/`doe_values`).

## 0-4. ~~소스 사용 영역 (②)~~ — **보류 (총괄 지시)**

> 계획 모델 재정의 논의로 **보류**. 아래 계약은 재설계 확정 후 재검토 대상이며 **현재 비활성**이다.
> 클라부는 이 절을 구현하지 마라. (엔진 코드는 존재하나 config 선언이 없어 동작하지 않는다 — §16-0)

<details><summary>보류된 계약 (참고용)</summary>

`transfer_plan_source_region` 테이블(**총괄 적용 대기 — §14-5 config 전문**). bk `plan_id|source_lot|source_slot|x|y`.

- **저장 정본은 셀 집합**이다. rect는 "빠른 사각 선택" UX 보조로만 쓰고, 저장할 때는 **선택 결과를 셀로 정규화**해 push하라. 자유 페인팅과 rect 선택이 같은 형태로 저장돼야 한다.
- 저장은 기존 맵 push 경로 그대로(`transfer_plan_map`과 동일 패턴). `map_key_columns`가 `["plan_id","source_lot","source_slot"]`이라 **맵 에디터가 (계획 × 소스)마다 하나의 페인팅 캔버스**로 연다.
- 조회 시 영역 내 가용을 받으려면 `plan_id`를 붙인다:

```
GET /api/transfer-plan/source-summary?stage=&lot=&slot=&plan_id=<계획>
```

응답에 `region_chips`가 추가된다:
```jsonc
"region_chips": {
  "cells": 4,              // 저장된 영역 셀 수
  "total": 4,              // 영역 내 총 칩
  "fail_breakdown": { "defect": 1, "eds_fail": 1 },   // tape 경로는 {"all_fail": N} 단일 항목
  "transferred": 2,
  "remaining": 1,          // 영역 내 가용 (전체와 동일한 합집합 의미론)
  "reliable": true         // false면 remaining과 동일 규율로 신뢰 불가
}
```
- `plan_id` 없으면 `region_chips` 자체가 없다(기존 계약 불변).
- 영역 미저장이면 `cells: 0`, `remaining: 0`이다 — **"영역 없음"과 "영역 내 가용 0"을 구분해 표시**하려면 `cells`를 보라.
- **`reliable: false`면 `remaining`을 그대로 쓰지 마라**(F1과 동일 규율).

</details>

## 0-5. DOE 층별 세분화 (S3) — 저장 형태

`transfer_plan_doe_layer` 테이블(**총괄 적용 대기 — §14-3 config 전문**). bk `doe_key|layer`.
- DOE 행의 `source_lot/slot`·`qty_per_unit`·`layer_from/to`는 **기본값/요약**이다.
- 층 배정 행이 하나라도 있으면 **그 DOE의 수량 계산은 층 배정이 정본**이 된다(층마다 다른 소스/수량 가능). 층 행의 `source_lot/slot`·`qty`가 비면 DOE 기본값을 승계한다(부분 선언 허용).
- 저장은 기존 제네릭 `PUT /tables/transfer_plan_doe_layer/data/updates` 사용(신규 CRUD 없음).
- `validate`의 `qty_shortage`는 층 단위로 나오며 `demand` 필드가 `"<DOE>@L<층>"` 형태다.

---

## 1. 요약 (판정: 완료 — 단 §7 총괄 적용 필요 config 2건 + §8 escalation 1건)

| 지시서 항목 | 결과 |
|---|---|
| A. Stage 선언 config | `transfer_plan_config.json`(+`.sample` tracked) 신설 — stage별 source/target kind, 역할 바인딩, **fail 투영**(frame: origin/self), 타깃 맵 규격. M1 config는 `source_config_ref`로 **하위호환 재사용**(§3-1) |
| B-2. `GET /api/transfer-plan/stages` | 신설 — stage 목록 + 역할별 연결 상태(행 조회 없음, 바인딩 해석만) |
| B-3. `GET /api/transfer-plan/source-summary` | 신설 — 공통 형태 + tape 소스 `by_core` 분해(dt_log 조인 1순위 / dt_map 영역 귀속 강등). M1 `core-summary`는 dt stage 인스턴스로 **내부 통합, 외부 계약 불변**(§3-2) |
| B-4. history knob | M1 규율 그대로 승계(소스가 core든 tape든 `process_history` 역할 바인딩) |
| C-5. 동적 테이블 3종 | **config 전문 §7-1로 보고(미적용 — 지시서 지시대로 사용자 config 직접 수정 안 함)**. 테스트는 자체 픽스처(`tp_test_*`)로 전 경로 검증 |
| C-6. 저장/로드 + validate | **신규 CRUD API 0건** — 기존 제네릭 배치 업데이트/맵 push로 충분(근거 §4). 검증 API `GET /api/transfer-plan/validate` 1개만 신설 |
| C-7. 온톨로지 매핑 | **전문 §7-2로 보고(미적용)** — ExperimentPlan + DOE(SplitCondition 확장) + PLANS_USE/ON_TARGET/DEFINED_IN, description 필수 규율 준수 |
| D. Fake DT 데이터 | `dt_map`/`dt_log` 신설(핫리로드 CREATE + 물리 확인) + 수집기 2개 + 테이프 3장 시딩(각 256칩, 불량 포함) + TAPE 프리셋/맵 메타 등록. 데모 서사 §6 |
| 테스트 | 기준선 **278 passed / 1 allowed fail** → 최종 **307 passed / 1 allowed fail(동일 건)** — 신규 29개 전부 통과 |
| **QA NO-GO 대응(F1)** | **해소** — 역할 강등을 `warnings`로 표면화 + 신뢰 불가 시 `remaining: null`(+조건부 상한) + `validate`의 오염값 판정 차단(`status: unverified`). QA 실측 3종(256/226/236 과대) 라이브 재현으로 차단 확인. 문제의 테스트 assert 교체 + 회귀 10종 추가(§8-ter) |
| 라이브 검증 | 엔진 함수를 실 PG에 직접 호출 + 원시 SQL 대조 **전항 일치**(§5). 계획 테이블 적용 후 validate·온톨로지 승격 라이브 스모크 통과(§8-bis). 라우트는 재기동 대기(§10) |
| 총괄 회신 조치 | 인덱스 6종 생성 / by_core 형태 정규화(키 집합 동일 + `by_core_origin` 마커) / 온톨로지 승격 스모크 — **전부 완료**(§8-bis). 신규 escalation 1건(stage 어휘 불일치, §8-bis-(4)) |

## 2. 변경 파일

**신규 (git 추적 대상, 미커밋)**
- `server/transfer_plan.py` — stage 로더 + 가용 엔진(투영/by_core) + validate 코어
- `server/tests/test_transfer_plan.py` — 19 tests (`tp_test_*` 접두 격리)
- `server/scripts/setup_transfer_plan_indexes.py` — DT/계획 인덱스 6종 멱등 셋업 (DT 3종 생성 완료, 계획 3종은 테이블 미적용이라 skip)
- `server/config/transfer_plan_config.json.sample`

**수정 (git 추적, 미커밋)**
- `server/main.py` — **순수 추가 61줄**(라우트 3개, bonding-plan 섹션 뒤 ~L2985, catch-all보다 선등록). 기존 코드 무수정 — 병렬 클라부 작업분과 무충돌.

**사용자 영역 (gitignored — 본 작업이 직접 적용한 것은 §D 데모 범위 한정)**
- `server/config/transfer_plan_config.json` (전문 §3)
- `server/config/table_config.json` — `dt_map`/`dt_log` 신설 (in-place 재기록 → watcher 발화 + `/admin/reload-configs` → **information_schema로 물리 CREATE 확인**)
- `server/config/maps.json` — TAPE 프리셋(`tape_std`) 라이브 POST 등록
- `server/ingestion_workspace/dt_log/auto_update/generate_dt_log.py` (신규)
- `server/ingestion_workspace/dt_map/auto_update/generate_dt_map.py` (신규)

**미접촉 확인**: `client2/*` (병렬 클라부 소유 — `map_editor.js`/`transfer_plan.js`/`transfer_plan.css` 변경분은 내 산출물 아님), CODE_MAP/docs, `server/bonding_plan.py`(M1 코드 무수정 — 하위호환 보장의 근거).

## 3. 배포 config 전문 (`server/config/transfer_plan_config.json`)

```json
{
  "stages": {
    "dt": {
      "description": "DT(Die Transfer): 코어 웨이퍼의 칩을 테이프에 전사하는 단계. 소스 가용 = M1 core-summary.",
      "source_kind": "core", "target_kind": "tape",
      "source_config_ref": "bonding_plan",
      "target_map": { "preset": "TAPE", "table": "dt_map" }
    },
    "bonding": {
      "description": "Bonding: 테이프 위의 칩을 base에 본딩. 테이프에는 여러 코어 칩이 혼재하고 불량도 섞여 있다 — 코어 fail은 dt_log 조인으로 테이프 좌표에 투영된다.",
      "source_kind": "tape", "target_kind": "base",
      "source": {
        "identity": { "compose": ["lot", "slot"] },
        "map_metadata": { "table": "wafer_map_metadata",
          "columns": { "target_table": "target_table", "map_id": "map_id", "grid_metadata": "grid_metadata" } },
        "total_chips":  { "table": "dt_log",      "columns": { "lot": "tape_lot", "slot": "tape_slot", "x": "tx", "y": "ty" } },
        "transfer_log": { "table": "bonding_log", "columns": { "lot": "core_lot", "slot": "core_slot", "x": "cx", "y": "cy" } },
        "origin_log":   { "table": "dt_log",      "columns": { "lot": "tape_lot", "slot": "tape_slot", "x": "tx", "y": "ty",
                            "origin_lot": "core_lot", "origin_slot": "core_slot", "origin_x": "cx", "origin_y": "cy" } },
        "origin_area_map": { "table": "dt_map",   "columns": { "lot": "lot", "slot": "slot", "x": "x", "y": "y", "val": "val" } },
        "process_history": { "table": "wafer_process",
          "columns": { "step": "step", "eqp": "eqp_id", "result": "result", "time": "start_time",
                       "recipe": "recipe_id", "knobs": "knobs", "lot": "lot", "slot": "slot" } },
        "fail_sources": {
          "defect":   { "frame": "origin", "table": "core_defect_map",
                        "columns": { "lot": "lot", "slot": "slot", "x": "x", "y": "y", "val": "val" }, "fail_values": ["D"] },
          "eds_fail": { "frame": "origin", "table": "eds_fail_map",
                        "columns": { "lot": "lot", "slot": "slot", "x": "x", "y": "y", "val": "val" }, "fail_values": ["F"],
                        "align": { "default": { "rotation": 180, "flip": "none", "offset": { "x": 0, "y": 0 } }, "by_eqp": {} } }
        },
        "warnings": { "result_fail_values": ["FAIL"] }
      },
      "target_map": { "preset": "BASE", "table": "bonding_map" }
    }
  },
  "plan_store": {
    "plan": { "table": "transfer_plan", "columns": { "plan_id": "plan_id", "stage": "stage",
              "target_lot": "target_lot", "target_slot": "target_slot", "status": "status", "memo": "memo" } },
    "doe":  { "table": "transfer_plan_doe", "columns": { "plan_id": "plan_id", "doe_value": "doe_value",
              "source_lot": "source_lot", "source_slot": "source_slot", "qty_per_unit": "qty_per_unit",
              "layer_from": "layer_from", "layer_to": "layer_to", "knobs": "knobs", "description": "description" } },
    "map":  { "table": "transfer_plan_map", "columns": { "plan_id": "plan_id", "x": "x", "y": "y", "val": "val" } }
  }
}
```

### 3-1. 하위호환 방식 — `source_config_ref`(명시적 이관 아님, 재사용)

지시서 §A-1의 "하위호환 유지 또는 명시적 이관 중 택일"에서 **하위호환 유지**를 택했다. 근거:
- M1 `bonding_plan_config.json`은 **코어 소스 역할 바인딩의 유일한 원천**이고, 이관하면 동일 바인딩이 두 파일에 중복돼 드리프트(한쪽만 고치는 사고)가 발생한다.
- `server/bonding_plan.py`를 **한 줄도 수정하지 않았다** — M1 API가 물리적으로 영향받을 수 없다(회귀 위험 0). 대신 M2가 M1을 호출해 응답을 재성형한다.
- 신규 stage가 코어 소스를 쓰면 `"source_config_ref": "bonding_plan"` 한 줄로 붙는다.

### 3-2. M1 내부 통합의 정확한 의미 (외부 계약 불변 증거)

| 관점 | M1 `GET /api/bonding-plan/core-summary` | M2 `source-summary?stage=dt` |
|---|---|---|
| 응답 `chips` | `{total, defect, eds_fail, used, remaining}` (M1 계약 그대로) | `{total, fail_breakdown{defect,eds_fail}, transferred, remaining}` (M2 공통 형태) |
| 코드 경로 | `bonding_plan.get_core_summary` | 같은 함수 호출 → `_reshape_m1_summary`로 재성형 |
| 회귀 검증 | `test_m1_core_summary_contract_unchanged`(신규) + 기존 M1 테스트 18개 전부 통과 | 라이브 수치 동일성 assert(§5-2) |

## 4. §C-6 근거 — 신규 CRUD API를 만들지 않은 이유

지시서 "기존 배치 업데이트·맵 push 경로 재사용 우선, 신규 CRUD는 부족분만"에 대해 **부족분 0**으로 판단했다.

| 필요 동작 | 재사용 경로 | 선례 |
|---|---|---|
| 계획 헤더 생성/수정 | `PUT /tables/transfer_plan/data/updates` (`business_key_val` 명시) | `map_split_registry` 저장과 동일 패턴 |
| DOE 정의 CRUD | `PUT /tables/transfer_plan_doe/data/updates` (복합 bk `plan_id\|doe_value`) | 〃 |
| 페인팅 결과 저장 | 맵 에디터 기존 push 경로 (`transfer_plan_map`을 맵 테이블로 등록 + `wafer_map_metadata` 메타) | `bonding_map`/`dt_map`과 동일 |
| 계획 조회/목록 | `GET /tables/{t}/data` (filters equals) | 〃 |
| **검증** | **없음 → `GET /api/transfer-plan/validate` 신설** | — |

즉 레이어링(CellSource/우선순위)·감사 로그·WS 브로드캐스트를 전부 기존 제네릭 경로가 그대로 제공하므로, 전용 CRUD를 만들면 레이어링 우회 위험만 생긴다.

## 5. 검증 증거

### 5-1. 기준선·최종 스위트
1. **기준선 선측정**(착수 시): `278 passed, 1 failed` — 실패는 `test_map_presets_api`(기허용 #4).
2. **최종 전수**: **`307 passed, 1 failed`** (= 278 + 신규 29). 실패 1건은 기준선과 **동일 원인** — assert 대상이 기본 프리셋 `std_300_12x13` 부재이고, 내가 추가한 `tape_std`는 응답에 정상 포함되나 assert 대상이 아니다(실패 메시지로 직접 확인). **"고쳐졌다" 판단 없음.**
3. 신규 29 tests: stage 로더(3) / core-kind reshape·404(2) / tape-kind 투영·by_core·align 대조군·align_unavailable·강등 2종·키집합 동일성·미존재 조합(8) / **강등 표면화(6 — QA F1)** / validate(9, 강등 차단 3 포함) / M1 계약 불변(1).

> **[정정 — QA D6]** 본 보고서 초판 §5-1이 "297 passed"로 §1·§8-bis(298)와 자기 불일치했다. QA 실측 정답은 당시 **298**이었고, F1 수정으로 신규 10개가 추가돼 현재 **307**이다. 수치는 매 실행 직후 갱신했어야 했다.

### 5-2. 라이브 교차검증 (엔진 함수를 실 PG에 직접 호출 + 원시 SQL 대조)

| 항목 | 원시 SQL | 엔진 | 판정 |
|---|---|---|---|
| dt stage LOT-A/05 재성형 | M1 원본 `{total 1288, defect 334, eds 124, used 410, remaining 420}` | 동일 5항 전부 | ✅ 계약 불변 |
| TAPE-A/01 total | 256 | 256 | ✅ |
| defect 투영(dt_log 조인) | 30 | 30 | ✅ |
| **eds 투영(align 180)** | 20 (수동 `41 - stored` 역변환 조인) | 20 | ✅ |
| **align 네거티브 대조군** | 26 (변환 없이 조인) | — | ✅ align이 실제로 작동 |
| by_core | `LOT-A/05 128, LOT-A/07 128` | 동일 + fail 29/18 | ✅ |
| 미존재 테이프 | — | 전 항목 0, by_core `[]` | ✅ |
| 미선언 stage / plan_store 미구성 | — | KeyError / LookupError (→404) | ✅ |

**합집합 의미론 실증**: fail_breakdown 합 = 30 + 20 = 50인데 `remaining` = 256 − 47 이다. by_core fail 합(29 + 18 = 47)과 정확히 일치 — defect·eds가 겹치는 칩 3개를 **이중 감산하지 않는다**. (M1 감산식 `total − Σfail − used`였다면 209가 아니라 206으로 과소 표기됐다.)

### 5-3. 물리 DDL / 인덱스
- information_schema 실측: `dt_map`(13 cols), `dt_log`(18 cols) CREATE 확인. table_config **in-place 재기록**으로 watcher 발화 경로 사용(에이전트 Edit의 원자적 쓰기는 on_modified 미발화 — 교훈 파일 준수).
- 인덱스 `idx_dt_log_tape_lot_slot`/`idx_dt_log_core_lot_slot`/`idx_dt_map_lot_slot` 생성 완료. 계획 테이블 3종 인덱스는 `[skip] table not found`(config 미적용 상태 — 의도됨).

## 6. Fake DT 데모 서사 및 수집기 설계

**서사(기존 `bonding_log` 데모와의 의미 충돌 정리)**: 실물류는 `Core →(DT)→ Tape →(bonding)→ Base`다. 그런데 기존 `bonding_log` fake의 `core_lot/slot`은 `LOT-*`(코어 표기)로 이미 대량 존재한다. 이를 **"DT 공정 도입 이전 세대의 과거 직행 본딩"** 으로 간주한다 — 신규 테이프(`TAPE-*` 별도 네임스페이스)는 아직 본딩 소진이 0이라 `transferred = 0`으로 보이는 것이 서사상 정합적이다(라이브 §5-2에서 실제로 0). 향후 테이프 identity로 기록되는 신규 본딩이 쌓이면 자연히 증가한다.

- `generate_dt_log.py` (*/3 cron, 정본): 테이프 3장 고정(`TAPE-A/01`, `TAPE-A/02`, `TAPE-B/01`). covered 코어(defect 맵 존재, 정렬 순)를 테이프당 2장씩 결정적 배정, 테이프 유효 셀을 (y,x) 정렬로 반분해 **코어별 연속 밴드**로 채운다. **칩 선별 없이 블록 전사 — 불량 칩도 그대로 전사**(fail 투영 실증의 핵심). 사이클당 1테이프 백필(기존 테이프 스킵 — 멱등), 전량 커버 후 생성 0.
- `generate_dt_map.py` (*/3 cron, 파생): dt_log를 좌표 투영해 테이프 맵 생성(`val = "<core_lot>_<core_slot>"` — 맵 에디터에서 코어별 영역 귀속이 색으로 보인다) + `wafer_map_metadata`에 TAPE 격자 규격 업서트(API 경유 — 레이어링 보존).
- 규격: TAPE 프레임 20×20(start 1,1), chip 15×15mm, dia 300, margin 3 → 유효 256칩/테이프. CORE 프레임은 M1 그대로 40×40/7mm.
- 두 수집기 모두 교훈 준수: 마스크는 `PhysicalWaferEngine` 재사용(실패 시 동일 4-코너 산식 폴백), **진단 출력은 stderr 전용**(subprocess 폴백 모드 CSV 오염 방지), 스케줄러 exec 분리 네임스페이스 대응(평문 루프만).
- 라이브 시딩 실적: `dt_log` 768행 / `dt_map` 768행(테이프 3장 × 256칩), 맵 메타 3건(`dt_map_TAPE-A_01` 등), 출신 코어 6종(`LOT-A/05,07,12`, `LOT-B/01,03`, `LOT-C/02`).

## 7. ⚠️ 총괄 적용 필요 config 전문 (지시서 지시대로 미적용)

### 7-1. `server/config/table_config.json` 추가 전문 (계획 테이블 3종)

```json
"transfer_plan": {
  "business_key": "plan_id",
  "column_types": {
    "plan_id": "string", "stage": "string", "target_lot": "string",
    "target_slot": "string", "status": "string", "memo": "string",
    "updated_by": "string", "eventtime": "string"
  },
  "display_columns": ["plan_id", "stage", "target_lot", "target_slot", "status", "memo", "updated_by", "eventtime"]
},
"transfer_plan_doe": {
  "business_key": "doe_key",
  "composite_key_source": ["plan_id", "doe_value"],
  "composite_key_separator": "|",
  "column_types": {
    "doe_key": "string", "plan_id": "string", "doe_value": "string",
    "source_lot": "string", "source_slot": "string", "qty_per_unit": "number",
    "layer_from": "number", "layer_to": "number", "knobs": "string",
    "description": "string", "updated_by": "string", "eventtime": "string"
  },
  "display_columns": ["doe_key", "plan_id", "doe_value", "source_lot", "source_slot",
                      "qty_per_unit", "layer_from", "layer_to", "knobs", "description",
                      "updated_by", "eventtime"]
},
"transfer_plan_map": {
  "business_key": "cell_key",
  "composite_key_source": ["plan_id", "x", "y"],
  "composite_key_separator": "|",
  "column_types": {
    "cell_key": "string", "plan_id": "string", "x": "number", "y": "number", "val": "string"
  },
  "display_columns": ["cell_key", "plan_id", "x", "y", "val"],
  "map_key_columns": ["plan_id"]
}
```

설계 근거:
- **분리자 `"|"`**: `plan_id`·`doe_value`가 자연어/식별자라 `_`를 포함할 수 있어 역파싱이 모호해진다. `map_split_registry`가 확립한 선례를 따른다.
- `transfer_plan_map.map_key_columns = ["plan_id"]`: 맵 에디터 테이블 셀렉터에 노출되어 **페인팅 캔버스로 열린다**(BASE/TAPE 프리셋 규격). `transfer_plan`/`transfer_plan_doe`는 맵이 아니므로 의도적 부재.
- `knobs`는 `"string"`(JSON 문자열) — M1 `wafer_process.knobs`와 동일 관례, 엔진이 파싱 실패 시 raw 폴백.
- `display_columns ⊇ column_types + bk 소스` 규율 준수.
- 적용 후 `server/scripts/setup_transfer_plan_indexes.py` 재실행 시 계획 인덱스 3종이 생성된다(현재 skip 상태).

### 7-2. `server/config/ontology_mapping.json` 추가 전문

```json
"transfer_plan": {
  "description": "전사(轉寫) 실험계획의 헤더 — 어느 단계(stage)의 어느 타깃(lot/slot)에 대한 계획인지와 확정 상태를 기록한다. 실제 배정 조건은 transfer_plan_doe(DOE), 공간 분포는 transfer_plan_map(페인팅)에 있다",
  "node": {
    "label": "ExperimentPlan",
    "identity": "plan_id",
    "props": ["stage", "status", "target_lot", "target_slot", "memo"]
  },
  "edges": [
    {
      "type": "ON_TARGET",
      "target_label": "Wafer",
      "target_identity_from": ["target_lot", "target_slot"],
      "description": "이 계획이 대상으로 삼는 타깃 개체(테이프/base 등 — lot|slot 표기 기준)"
    }
  ]
},
"transfer_plan_doe": {
  "description": "전사 실험계획의 DOE 조건군 정의 — 페인팅 value 하나가 곧 하나의 실험 조건군이며 소스(어느 코어/테이프에서), 층 범위, 개당 수량, knob 계획, 자연어 설명을 갖는다. map_split_registry의 SplitCondition을 계획 도메인으로 확장한 것",
  "node": {
    "label": "SplitCondition",
    "identity": "doe_key",
    "props": ["doe_value", "description", "knobs", "qty_per_unit", "layer_from", "layer_to"]
  },
  "edges": [
    {
      "type": "DEFINED_IN",
      "target_label": "ExperimentPlan",
      "target_identity_from": ["plan_id"],
      "description": "이 DOE 조건군이 속한 전사 실험계획"
    },
    {
      "type": "PLANS_USE",
      "target_label": "Wafer",
      "target_identity_from": ["source_lot", "source_slot"],
      "description": "이 DOE가 칩을 가져다 쓰기로 계획된 소스 개체(코어 웨이퍼 또는 테이프 — lot|slot 표기 기준)"
    }
  ]
}
```

- `description` 필수 규율: 테이블 2건 + 엣지 3건 전부 서술 포함.
- **DOE = SplitCondition 확장**(지시서 §C-7 지정): `map_split_registry`와 동일 label을 공유해 "value ↦ 실험 조건" 의미론이 한 라벨로 수렴한다 — G3에서 "어느 DOE에서 불량 군집" 질의가 계획/실적 양쪽을 한 체인으로 탄다.
- `transfer_plan_map`은 **노드 매핑하지 않는다**(칩 셀 수만큼 노드가 생겨 그래프 폭발 — 공간 분포는 테이블 질의로 충분). §7.5c 슈퍼 허브 규율과 같은 취지.
- §7.5c `node_class`는 현행 `ontology_mapping.json` 어느 항목에도 아직 없어(로더 미지원 가능성) 넣지 않았다 — 도입 시 ExperimentPlan/SplitCondition 모두 `dynamic`이다.

## 8-bis. 총괄 회신 조치 결과 (2차 — config 적용 후)

총괄 지시 3건 전부 처리 완료. 스위트 **298 passed / 1 allowed fail**(신규 20).

### (1) 계획 인덱스 3종 생성 + validate 404 해소 확인
- `setup_transfer_plan_indexes.py` 재실행 → **6종 전부 `[ok]`** (`idx_transfer_plan_stage`, `idx_transfer_plan_doe_plan`, `idx_transfer_plan_map_plan` 신규 생성).
- `list_stages().plan_store` = `{plan: connected, doe: connected, map: connected}` — 404 경로 해소 확인.
- `validate_plan("TP-SMOKE-1")` 라이브 정상 반환(§8-bis-3).

### (2) §8 escalation 결정 반영 — by_core 형태 정규화

| 항목 | 조치 |
|---|---|
| 키 집합 동일화 | 양 경로 모두 `{core_id, core_lot, core_slot, total, fail, used, remaining}` — 정본 경로도 `core_id` 채움(`f"{lot}\|{slot}"`, 상수 `CORE_ID_SEP`) |
| 경로 마커 | 응답 top-level `by_core_origin: "log" \| "area_map"` 추가. by_core 미동봉 시 마커도 함께 부재 |
| `fail: null` | 유지(0 위장 금지) |
| 회귀 테스트 | `test_by_core_key_set_identical_across_paths` 신설 — 두 경로 **키 집합 완전 일치 + 마커 값 + core 개수 일치** assert. 기존 2개 테스트에도 마커/`core_id`/`core_lot is None` assert 추가 |

라이브 확인: `by_core_origin: "log"`, `by_core[0] = {"core_id": "LOT-A|05", "core_lot": "LOT-A", "core_slot": "05", "total": 128, "fail": 29, "used": 0, "remaining": 99}`, key set = 7개 동일.

**클라 주의(문서화 필요)**: `area_map` 경로의 `core_id`는 영역 맵의 **원시 값**(config가 정하는 불투명 식별자, 데모에선 `"LOT-A_05"`)이라 `log` 경로의 `"LOT-A|05"`와 **문자열이 다르다**. 두 경로는 상호배타(동시 등장 불가)이므로 `core_id`는 **응답 내 그룹 키로만** 쓰고 경로 간 조인 키로 쓰면 안 된다. lot/slot 추측 파싱은 근거가 없어 하지 않았다(null 유지).

### (3) 온톨로지 승격 라이브 스모크 — 전항 통과

기존 제네릭 배치 업데이트(`PUT /tables/{t}/data/updates`)만으로 투입 — **신규 CRUD API 0건 주장(§4) 실증**.

| 대상 | 결과 |
|---|---|
| 노드 | `ExperimentPlan(TP-SMOKE-1)` props 5종 / `SplitCondition(TP-SMOKE-1\|SMOKE-A, \|SMOKE-B)` props 6종 |
| 엣지 | `DEFINED_IN` ×2 (DOE→Plan), `ON_TARGET` ×1 (Plan→`Wafer(TAPE-A\|01)`), `PLANS_USE` ×2 (DOE→`Wafer(TAPE-A\|01)`) — **전부 `source_name: user`** |
| validate 경고 | `undefined_doe_value`(SMOKE-UNDEF), `layer_coverage_gap`(1..3 중 2층 공백), `source_fail_chips` ×2(defect 30 + eds 20), **`qty_shortage`**(필요 300 = 칩1×층1×개당300 > 가용 209) |

`qty_shortage`는 최초 시드(qty 200 ≤ 가용 209)에서 정상적으로 **발화하지 않았고**, qty를 300으로 올린 뒤 발화했다 — 임계 동작까지 라이브 확인.

**관찰 1 — `identity_key`의 `\|` 이스케이프는 기존 선례와 일치**: `SplitCondition` 노드 identity가 `TP-SMOKE-1\|SMOKE-A`로 저장된다(materializer가 값 내부 `|`를 복합 identity 조인자와 구분하려 이스케이프). 기존 `map_split_registry` 노드도 동일(`sample_map\|fdgfd\|F`) — **내가 도입한 편차가 아니라 확립된 관례**다. 다만 `/graph/neighbors?label=SplitCondition&identity=...` 조회 시 **이스케이프된 형태**를 써야 한다(클라/문서 주의점).

**관찰 2 — 시드 정리 목록**: 아래는 내 스모크 데이터다. 불필요 시 삭제 가능(운영 데이터 아님).
- `transfer_plan`: `TP-SMOKE-1`
- `transfer_plan_doe`: `TP-SMOKE-1|SMOKE-A`, `TP-SMOKE-1|SMOKE-B`
- `transfer_plan_map`: `TP-SMOKE-1|1|1`, `TP-SMOKE-1|2|1`, `TP-SMOKE-1|3|1`, `TP-SMOKE-1|4|1`
- 대응 그래프 노드/엣지(`identity_key LIKE 'TP-SMOKE%'`) — 행 삭제 시 정리 정책은 스펙 §8 미결 항목.

### (4) ⚠️ 신규 escalation — stage 어휘 불일치 (타 에이전트 시드에서 발견)

계획 테이블에 **내 것이 아닌 행**이 있다: `transfer_plan.plan_id = "bonding_plan__TESTPLAN_M2VERIFY_01"`, `stage = "bonding_plan"`, DOE 2건(`D1`/`D2`, `source_lot = "TAPE_A"/"TAPE_B"`). 병렬 클라부 또는 총괄 검증 시드로 보이며 **삭제하지 않았다**(내 소유 아님).

문제는 그 `stage` 값이다:
- 선언된 stage는 `dt` / `bonding`인데 이 행은 `"bonding_plan"` — `validate`가 `stage_unknown` 경고를 내고 **소스 가용 검증(수량·fail)을 통째로 건너뛴다**. 실제 라이브 확인: 경고가 `stage_unknown` 1건뿐.
- `source_lot`도 `TAPE_A`(언더스코어)로 실 데이터 `TAPE-A`(하이픈)와 불일치 — stage가 맞았어도 소스 조회가 0을 반환했을 것이다.

**총괄 판단 요청**: 클라가 stage 값을 어디서 얻는지 확인이 필요하다. `GET /api/transfer-plan/stages`의 `name`이 **유일한 정본 어휘**이며(`dt`/`bonding`), 클라가 `plan_id` 접두사나 config 파일명(`bonding_plan`)에서 유추하고 있다면 계약 위반이다. 서버측 완화안 2가지 중 택일 요청:
- (A) 현행 유지 — `stage_unknown` 경고로 조기에 드러내고 클라를 `/stages` 기반으로 교정(권장: 어휘 단일 원천 유지).
- (B) config에 stage 별칭(`aliases: ["bonding_plan"]`) 허용 — 관대하지만 어휘가 둘로 늘어 드리프트 재발 여지.

## 8-ter. QA NO-GO 대응 (3차 — F1 병합 차단 사유 해소)

> QA 판정 근거: `agent_workspace/reports/QA_transfer_plan_m2_review.md` §2 F1 / §6-1 항목 4.
> 스위트 **307 passed / 1 allowed fail**(신규 29 — F1 관련 10개 추가).

### (1) 지적의 타당성 — 전면 수용

QA 지적은 정확하다. `_summarize_inline`의 `warnings_out`에는 이력 경고만 담기고, 역할이 무너져 fail 집계가 0이 되는 경로 **어디에도** 경고가 없었다. `sources` 문자열에 흔적은 남지만 그것은 **부가 필드**이고, 소비자가 그걸 읽지 않으면 과대값을 정상값과 구별할 수 없다. 게다가 `validate`가 그 오염된 `remaining`으로 `qty_shortage`를 판정하므로 **안전망이 같은 원인으로 동시에 무너진다**. "빠르지만 가끔 조용히 안 맞음"의 교과서적 사례로, 병합 차단이 옳은 판단이다.

특히 **`test_transfer_plan.py:481`이 과대값 5를 정답으로 고정**하고 있었던 점이 가장 뼈아프다. 내가 작성한 테스트가 결함을 스펙으로 굳혀 후속 검수자를 오도할 뻔했다.

### (2) 조치 — 3층 방어

| 층 | 조치 | 구현 |
|---|---|---|
| ① 표면화 | 강등 역할을 `warnings`에 명시 항목으로 | `assess_degradation()` — `{type:"source_degraded", role, status, effect, detail}` |
| ② 값 자체 | 신뢰 불가 시 **`remaining: null`** + `remaining_reliable: false` + (조건부) `remaining_upper_bound` | `build_chips_block()` |
| ③ 검증 | degraded 입력에서 `qty_shortage` 판정 금지 → `availability_unreliable` 명시 + `status: "unverified"` | `validate_plan()` |

**설계 근거 — 왜 플래그가 아니라 `remaining: null`인가**: 총괄이 "소비자가 분기 없이 오표시할 수 없는 형태"를 요구했다. `remaining_reliable: false` **플래그만 두면 그 필드를 읽지 않는 클라는 여전히 과대값을 그대로 렌더한다**(실제로 QA C1이 지적한 대로 클라는 상태 신호를 뭉갠다). `remaining`을 `null`로 내리면 클라는 렌더 단계에서 반드시 null을 만나고, 이미 `by_core.fail: null → "미상"` 처리 관례가 있으므로 자연스럽게 "미상"으로 떨어진다. 플래그는 **보조**로 함께 둔다.

**`remaining_upper_bound`의 조건부 제공**: 감산항(fail/기전사)만 과소한 경우 계산값은 진짜 잔여의 **상한**이 맞다. 그러나 `total_chips`까지 강등되면 분모 자체가 불명이라 상한이 아니므로 **필드를 아예 싣지 않는다**(`total_unknown` 효과 분리). 상한이라 부를 수 없는 값을 상한이라 부르지 않는 것이 요점이다.

**효과 분류로 과잉 강등 방지**: 모든 비-`connected` 상태를 강등으로 뭉치면 `connected(aligned:180)`(정상 align)까지 경고가 되어 상시 오탐이 되고, 그것은 QA 교훈 4가 지적한 "진짜 경고를 가리는" 역효과를 낳는다. 따라서 효과를 4종으로 분리했다 — `remaining_overstated`(fail/기전사/origin_log) / `total_unknown`(total_chips) / `by_core_degraded`(origin_area_map) / `history_incomplete`(process_history). **뒤 둘은 `remaining` 신뢰도를 떨어뜨리지 않는다.**

### (3) 라이브 재현 — QA 실측 3종 전부 차단

| 시나리오 | QA 실측(수정 전) | 수정 후 `remaining` | `remaining_upper_bound` | 강등 경고 |
|---|---|---|---|---|
| 정상 | 209 | **209** (reliable: true) | (없음) | **0건 — 오탐 없음** |
| origin_log 파손 | **256** (경고 `[]`) | **null** | 256 | defect/eds_fail/origin_log `remaining_overstated` + origin_area_map `by_core_degraded` |
| align meta 부재 | **226** (경고 `[]`) | **null** | 226 | eds_fail `remaining_overstated` |
| defect 원천 파손 | **236** (경고 `[]`) | **null** | 236 | defect `remaining_overstated` |

`validate` 라이브(`TP-SMOKE-1`): 정상 → `status=warnings`, `availability_checked=true`, `qty_shortage` 발화. origin_log 파손 → `status=unverified`, `availability_checked=false`, **`qty_shortage` 미발화 + `availability_unreliable` 발화**.

### (4) 회귀 테스트 (신규 10 — QA 요구 3가지 각각)

- `test_tape_origin_missing_falls_back_to_area_map` — **문제의 `assert remaining == 5`를 교체**: `remaining is None` + `remaining_reliable false` + `upper_bound == 5` + `source_degraded` 발생.
- 강등 표면화 6종: align meta 부재 / fail 원천 파손 / **정상 경로 대조군(오탐 0 고정)** / core-kind(M1 reshape) 경로 / `total` 강등 시 상한 미제공 / 이력 강등은 remaining 무영향.
- validate 3종: `test_validate_refuses_to_judge_on_degraded_source`(정상에선 `qty_shortage` 발화 → 강등에선 미발화 + `availability_unreliable`, 대조 구조), `stage_unknown`은 `unverified`, 정상은 `availability_checked=true`.

### (5) 미조치 — 한계로 명시 (총괄 "무리면 한계로 명시" 허용 범위)

- **F7 쿼리 왕복 N+1**: 수정하지 않았다. QA §6-2가 "병합 후 즉시(후속 티켓 분리 가능)"로 분류했고, F1 수정의 정확성 검증에 남은 예산을 쓰는 편이 옳다고 판단했다. **정확한 현황**: fail 투영이 코어마다 grid meta 1회 + fail 좌표 1회를 조회해 **O(코어수 × fail원천수)** — 2코어 2원천에 SQL 10문. 구체적 수정안은 fail 원천별 `(lot,slot) IN (involved_cores)` 단일 쿼리 + grid meta `(target_table, map_id) IN (...)` 배치 후 dict 캐시(원천당 2문으로 축소).
- **F2/F3**(하드캡 절단 무표기, 중복 행): 미조치. 다만 §5 계약 서술과 모듈 docstring에 "①전 역할 connected ②캡 미도달 ③칩당 1행 유일" 3조건을 명시해 **정확성 단서를 코드에 남겼다**(QA D7 대응).
- `plan_id` 클라 합성: 총괄 결정대로 현행 유지. **계약 명문화**: 서버는 `plan_id`를 **파싱하지 않는다** — `validate_plan`은 컬럼 equals 조회만 하고 `stage`는 별도 컬럼에서 읽는다. 이 불변식을 `transfer_plan.py` 모듈 docstring에 못박았다.

## 8-quater. QA F4·F6·F2 수정 (4차)

스위트 **333 passed / 1 allowed fail**.

### F6 — align `dst_grid` 미전달 (오답 경로)

M1은 `make_align_transform(align, src_grid, canonical_grid)`로 dst를 넘기는데 M2는 생략했다. 그러면 ①dst `start_x/y`가 소스 자신의 start로 폴백해 원점이 어긋나고 ②치수 불일치 `ValueError` 가드가 **통째로 무력화**된다.

- `_canonical_origin_grid()` 신설 — **align을 선언하지 않은 core-frame fail 원천**(대개 defect 맵)의 grid meta를 canonical로 잡는다. M1이 쓰는 것과 동일한 정의.
- 코어당 1회 캐시(`canonical_grid_cache`)라 F7 왕복도 일부 완화된다.
- 회귀 테스트 2종: 스파이로 **`dst_grid`가 실제로 전달되는지 직접 확인**(None이면 실패), 치수 모순 시 `align_unavailable` 명시 실패.
- **부수 발견**: 테스트 시드에 canonical(defect) 맵 메타가 없어 dst가 None이었다 — 라이브에는 `generate_core_defect.py`가 등록하므로 존재한다. 시드에 추가해 라이브와 동형으로 맞췄다. **라이브 정상 경로는 수정 전후 209로 불변**(회귀 없음).

### F4 — 소스 합산 초과배정

`source_alloc`에 (lot,slot)별 `required`를 누적해 루프 종료 후 판정한다.
- **DOE가 2건 이상 공유하는 소스만** 경고한다 — 단독 DOE는 `qty_shortage`가 이미 정확히 같은 사실을 말하므로 중복 노이즈가 된다.
- **강등 소스는 누적 자체를 하지 않는다**(F1 규율 — 오염된 가용치로 합산 판정 금지). 테스트로 고정.
- 회귀 3종: 검출(각 1·2 ≤ 2인데 합 3 > 2) / 단독 DOE 중복 경고 없음 / 강등 시 미판정.

### F2 — 하드캡 절단 표면화 (F1과 같은 계열이라 포함)

캡에 걸려도 로그만 남고 응답은 정상과 **구별 불가**했다. `total`은 `count()`라 절단되지 않아 분자·분모의 모집단이 어긋난다.
- `_fetch_pairs`가 `(pts, truncated)`를 반환하도록 바꾸고 origin_log·transfer_log·fail 원천·area_map·by_core의 캡 도달을 `truncations`로 수집.
- 카운트에 영향 있는 절단은 **`remaining_reliable=false`로 강등**(F1과 동일 취급) + `result_truncated` 경고 + 응답 `truncated: [...]`.
- `by_core` 절단은 `by_core_truncated: true` + `by_core_degraded` 효과(remaining은 오염 안 됨 — 과잉 강등 방지).
- 회귀 3종: 캡을 낮춰 재현 / by_core 절단 플래그 / **캡 미도달 대조군(오탐 0)**.

### F3 — 평가 후 미조치 (보고만)

`total`은 행 수인데 `blocked`는 distinct 칩이라 중복 행에서 `remaining`이 과대해진다. **평가 결과 이번 배치에서 제외**한 근거:
- 수정하려면 `total`을 `distinct (x,y)` 카운트로 바꿔야 하는데, 이는 1,000만 행 규모에서 `count(*)`를 **distinct 서브쿼리로 격상**시켜 성능 특성이 바뀐다. 확장성 규율과 정면 충돌하므로 성급히 넣을 수 없다.
- **더 옳은 해법은 데이터 계약 쪽**이다 — `dt_log`에 `(tape_lot, tape_slot, tx, ty)` 유니크 인덱스를 걸어 중복을 애초에 막는 것. 이건 운영 도메인 확인이 필요하다(재작업 기록을 별도 행으로 남기는 운용인지).
- 현재는 모듈 docstring에 "③total_chips 원천이 칩당 1행 유일할 때만 정확"을 **명시 단서로 남겼다**.
- **후속 티켓 권장**: 도메인 확인 → 유니크 인덱스 or `origin_rows` (tx,ty) dedup.

### F7 — 한계로 명시 (총괄 지시대로 후속)

fail 투영이 **O(코어수 × fail원천수)** 왕복이다(2코어 2원천 = SQL 10문). canonical grid 캐시로 일부만 줄었다. 수정안: 원천별 `(lot,slot) IN (involved_cores)` 단일 쿼리 + grid meta 배치 조회 → 원천당 2문.

## 9-bis. S1'/S2/S3 — 사용자 UX 요구 구현

### S1' 범용 맵 오버레이 (`server/map_overlay.py` 신설)

**설계 판단 — align을 어디에 두는가 (총괄 검토 요청 항목)**

계획 config에 align을 적어두면 그 계획에서만 붙으므로 범용성이 깨진다. 그런데 **각 맵은 이미 `wafer_map_metadata.grid_metadata`에 자기 좌표계(`rotation`, `side`)를 선언**하고 있다. 따라서 별도 선언 없이 두 맵의 메타 차이로 변환이 유도된다:

```
상대 회전 = (source.rotation − target.rotation) mod 360
상대 플립 = source.side ≠ target.side 이면 x 반전
```

이것이 "map meta가 달라도 align해서 붙게"의 가장 자연스러운 구현이고, **마이그레이션이 필요 없다** — 기존 수집기들이 이미 메타에 rotation을 넣고 있기 때문이다(`eds_fail_map`은 180, `core_defect_map`은 0). 라이브에서 그대로 동작함을 확인했다(아래). 예외 보정(offset·장비별 편차)만 `map_overlay_config.json`의 `align_overrides`로 선언한다. 기존 계획 config의 align은 **무수정 — 하위호환 유지**(transfer_plan은 여전히 자기 config의 align을 쓴다).

**align 판정 규율 (총괄 확정 반영)**
| 상황 | 처리 | origin |
|---|---|---|
| override 선언 있음 | 선언대로 | `declared` |
| `by_eqp`에 장비 키 없음 | `default`로 폴백 + note (**차단 안 함**) | `default` |
| 선언 없음 + 두 맵 메타 있음 | 메타 차이로 유도 | `derived` |
| 선언·메타 근거 없음 | **identity로 그대로 붙임** | `identity` |
| 비-identity인데 격자 규격 비호환/부재 | `align_unavailable` **명시 실패** | — |

즉 `align_unavailable`은 "각도를 모른다"가 아니라 **"변환을 계산할 근거가 없다"**일 때만 낸다.

**라이브 검증** (`core_defect_map/LOT-A_05` 캔버스에 `eds_fail_map` 오버레이):
- `align_applied: {rotation: 180, origin: "derived"}` — **선언 없이 메타에서 자동 유도**
- F셀 **124개가 수동 `(41−x, 41−y)` 역변환 SQL과 정확히 일치**
- 무변환 raw 좌표와는 **불일치** → 정렬이 실제로 동작함을 증명
- `core_defect_map` 자기 자신 오버레이는 `origin: "identity"`, 좌표 불변

테이블명 하드코딩 0 — 좌표/키 컬럼이 관례와 다른 맵(`dt_log`의 `tx/ty/tape_lot`)은 config `table_bindings`로 붙인다. 테스트 14종(자동 유도·flip 유도·선언 우선·by_eqp 폴백·임의 바인딩·다른 키·캡 절단·미존재 테이블·파라미터 400).

### S2 페인트 잠금 config화

**조사 결과: 서버에는 잠금 로직이 전혀 없다.** 서버의 `fail_values`는 **집계 카운트 전용**이며(`bonding_plan.py:393`, `transfer_plan.py:384`), 페인팅을 막는 코드는 서버 어디에도 없다 — grep으로 확인. 즉 "F면 색칠 못함"은 **전적으로 클라 하드코딩**이다.

따라서 서버에 **선언의 정본**을 만들었다: `GET /api/maps/paint-rules?table=`. 맵 단위 설정이라 S1'의 범용성과 정합한다(특정 오버레이/계획에 종속되지 않음). `*` 와일드카드 + 테이블별 override 병합. **기본값은 잠금 없음** — "F면 못 칠한다"가 코드에 박혀 있으면 사용자가 바꿀 수 없다는 것이 이번 요구의 출발점이기 때문이다.

### S3 DOE 층별 세분화

**설계**: 총괄 권장안(`transfer_plan_doe_layer` 신설)을 채택했다. 대안(DOE 행을 층마다 복제)은 bk가 `plan_id|doe_value`라 같은 DOE의 층을 표현할 수 없고, DOE=조건군이라는 의미론도 깨진다.

- DOE 행의 `source_lot/slot`·`qty_per_unit`·`layer_from/to`는 **기본값/요약**, 층 배정 행이 있으면 **그것이 정본**.
- 층 행의 소스·수량이 비면 DOE 기본값 승계(**부분 선언 허용**).
- validate가 DOE를 **수요(demand) 목록으로 정규화**해 층마다 별도 판정하고, F4 소스별 합산이 층을 가로질러 자연히 누적된다(`A@L1` + `A@L2`가 같은 소스면 합산).
- 층 커버리지 검사도 층 배정 행을 포함한다.
- 테스트 5종 포함.

## 13-bis. 5차 조치 (총괄 회신 반영) — 인덱스 + 소스 영역 영속화

스위트 **339 passed / 1 allowed fail**(+6).

### (1) 인덱스
`setup_transfer_plan_indexes.py`에 2종 추가 후 실행:
- `idx_transfer_plan_doe_layer_doe (doe_key)` → **`[ok]` 생성 완료**(층 테이블 적용 확인).
- `idx_transfer_plan_region_plan_src (plan_id, source_lot, source_slot)` → `[skip]`(영역 테이블 미적용 — §14-5 적용 후 재실행하면 생성).

### (2) 소스 사용 영역 영속화 (②)

**엔진 배선**: `get_stage_source_summary(..., plan_id=)` → `load_source_region()`으로 셀 집합을 읽어 `region_chips`를 산출. 전체 집계와 **동일한 합집합 의미론**(`total − |fail ∪ transferred|`)을 영역으로 좁힌 것이라 두 수치의 해석이 일관된다.

**core-kind(dt stage) 지원이 관건이었다.** M1 `get_core_summary`는 rect만 받아 셀 집합을 넘길 수 없는데, `bonding_plan.py` 무수정 불변식은 지켜야 했다. 해법: M1 config의 역할 바인딩을 M2 어댑터 형태로 읽어 좌표 집합을 직접 구성하는 `_core_region_counts()`를 두고, **align은 기존 `_canonical_fail_set`을 재사용**해 canonical 사상 후 교차한다. 결과적으로 M1 코드는 여전히 한 줄도 건드리지 않았다.

- 회귀 테스트 6종: tape 영역 스코프(합집합 의미론 유지 검증) / `plan_id` 없으면 필드 부재 / 빈 영역은 0(필드는 존재) / **core 영역 + align 적용**(eds canonical (1,1) 검출) / **align 미선언 대조군**(eds 0 — 정렬 실효 증명) / plan_store 바인딩 노출.
- `reliable` 필드를 동봉해 F1 규율(강등 시 신뢰 불가)을 영역 수치에도 적용했다.

**라이브 검증 한계**: 영역 테이블이 아직 config 미적용이라 라이브 실측은 못 했다. 적용 후 `GET /api/transfer-plan/source-summary?stage=bonding&lot=TAPE-A&slot=01&plan_id=<계획>`으로 확인 필요(재기동 후).

**알려진 한계 (tape 경로)**: `region_chips.fail_breakdown`이 tape 경로에서는 원천별로 분해되지 않고 `{"all_fail": N}` 단일 항목이다. 전체 집계 단계에서 원천별 좌표 집합을 보관하지 않고 합집합만 유지하기 때문이다(메모리 규율). 원천별 분해가 필요하면 fail 집합을 원천별로 보관하도록 소폭 확장하면 된다 — core 경로는 이미 원천별로 나온다.

## 14. 총괄 적용 필요 config 전문 (추가분)

### 14-3. `table_config.json` — `transfer_plan_doe_layer` (S3)

```json
"transfer_plan_doe_layer": {
  "business_key": "layer_key",
  "composite_key_source": ["doe_key", "layer"],
  "composite_key_separator": "|",
  "column_types": {
    "layer_key": "string", "doe_key": "string", "layer": "number",
    "source_lot": "string", "source_slot": "string", "qty": "number",
    "note": "string", "updated_by": "string", "eventtime": "string"
  },
  "display_columns": ["layer_key", "doe_key", "layer", "source_lot", "source_slot",
                      "qty", "note", "updated_by", "eventtime"]
}
```
적용 후 `setup_transfer_plan_indexes.py`에 `idx_transfer_plan_doe_layer_doe (doe_key)` 추가 실행 권장(현재 스크립트 미포함 — 테이블 적용 후 함께 넣는 편이 안전).

### 14-5. `table_config.json` — `transfer_plan_source_region` (②)

```json
"transfer_plan_source_region": {
  "business_key": "region_key",
  "composite_key_source": ["plan_id", "source_lot", "source_slot", "x", "y"],
  "composite_key_separator": "|",
  "column_types": {
    "region_key": "string", "plan_id": "string",
    "source_lot": "string", "source_slot": "string",
    "x": "number", "y": "number", "val": "string",
    "updated_by": "string", "eventtime": "string"
  },
  "display_columns": ["region_key", "plan_id", "source_lot", "source_slot",
                      "x", "y", "val", "updated_by", "eventtime"],
  "map_key_columns": ["plan_id", "source_lot", "source_slot"]
}
```

설계 근거:
- **`transfer_plan_map`과 동일 패턴**(요건 ⓐ): 셀 집합 + 복합 bk + `|` 분리자. 저장·이력·레이어링·WS를 전부 기존 제네릭 경로로 얻는다(**신규 CRUD API 0** 유지).
- **요건 ⓑ**: bk와 컬럼에 `plan_id` + `source_lot|source_slot`이 모두 들어가 "어느 계획의 어느 소스 영역"이 유일하게 식별된다. 코어·테이프 어느 쪽이든 같은 형태다(stage에 따라 소스 종류만 달라짐).
- **요건 ⓒ**: `map_key_columns = ["plan_id","source_lot","source_slot"]` → 맵 에디터 셀렉터에 노출되고 **(계획 × 소스)마다 하나의 캔버스**로 열린다. 맵 메타는 소스 맵(코어/테이프)의 격자 규격을 그대로 등록하면 된다(관례 `map_pk = <table>_<map_id>`).
- `val`은 선택 — 영역 안에서 용도를 더 나누고 싶을 때 쓴다(현재 엔진은 좌표만 소비).
- 적용 후 `setup_transfer_plan_indexes.py` 재실행 시 `idx_transfer_plan_region_plan_src`가 생성된다(현재 `[skip]` 상태).

**현행 region(rect) 경로와의 관계 정리 (요건 ⓓ)**

| 경로 | 입력 | 저장 | 용도 |
|---|---|---|---|
| M1 `GET /api/bonding-plan/core-summary?region=` | rect JSON(쿼리스트링) | **없음(휘발)** | 즉석 조회. **계약 불변 — 유지** |
| M2 `source-summary?plan_id=` | 저장된 셀 집합 | `transfer_plan_source_region` | **영속 정본** |

rect는 UX 보조로 남기되 **저장은 셀 집합으로 정규화**한다. 근거: 자유 페인팅은 rect로 표현 불가이고, cells를 쿼리스트링에 실으면 수천 셀에서 페이로드 규율과 충돌한다. 두 경로는 공존하되 정본은 후자다.

### 14-4. `ontology_mapping.json` — 층 배정 (**총괄 미적용 결정 — 참고용 보존**)

> 총괄 결정: 같은 label에 이질적 정체가 섞이는 기존 결함(`Wafer` label에 wafer_id와 lot|slot이 공존)과 동형 패턴을 하나 더 만들게 되므로 **미적용**. 층은 별도 label(`PlanLayer`)로 §7.5c `node_class` 도입 작업에서 정리한다. **동의한다** — `SplitCondition`에 층을 얹으면 identity 체계가 두 종류(`plan|value`와 `plan|value|layer`)로 갈려 같은 label의 노드가 서로 다른 입도를 갖게 된다. S3 기능은 그래프 승격 없이 정상 동작한다(아래 전문은 향후 `PlanLayer` 설계 시 출발점으로만 보존).

```json
"transfer_plan_doe_layer": {
  "description": "전사 실험계획 DOE의 층별 배정 — 한 DOE 조건군 안에서 층마다 다른 소스/수량을 쓸 때의 세분화 행",
  "node": { "label": "SplitCondition", "identity": "layer_key",
            "props": ["layer", "qty", "note"] },
  "edges": [
    { "type": "LAYER_OF", "target_label": "SplitCondition",
      "target_identity_from": ["doe_key"],
      "description": "이 층 배정이 속한 DOE 조건군" },
    { "type": "PLANS_USE", "target_label": "Wafer",
      "target_identity_from": ["source_lot", "source_slot"],
      "description": "이 층에서 칩을 가져다 쓰기로 계획된 소스 개체" }
  ]
}
```
**주의**: 같은 label(`SplitCondition`)에 DOE와 층이 함께 들어간다. 층 수가 많으면 노드가 늘어나므로 **적용은 총괄 판단** — 미적용해도 S3 기능은 정상 동작한다(그래프 승격만 없음).

## 15. 클라 UI 재설계 관련 의견 (착수 안 함 — 총괄 요청 의견만)

② **코어별 사용 영역 영속화** — `parse_region`의 rect 확장 vs 소스 영역 테이블:
**소스 영역 테이블을 권장**한다. rect는 자유 페인팅 셀 집합을 표현할 수 없고, cells 모드로 확장하면 URL 파라미터에 셀 배열이 실려 페이로드 상한 규율과 충돌한다(GET 쿼리스트링에 수천 셀). 이미 `transfer_plan_map`이 "계획 셀 집합"을 저장하는 정확히 같은 형태이므로, **동일 패턴의 영역 테이블**(bk `plan_id|source|x|y` 또는 `transfer_plan_map`에 소스 컬럼 추가)이 일관적이고, 영속화·이력·레이어링을 전부 기존 경로로 얻는다. rect는 "빠른 사각 선택" UX 보조로만 남기고 저장은 셀 집합으로 정규화하는 것이 옳다.

①(정렬된 fail 좌표 반환)은 **이번에 S1'로 이미 구현됐다** — `GET /api/maps/overlay`가 정렬된 좌표를 영역 스코프 없이 캡(20,000) 기반으로 반환한다. 영역 스코프가 필요하면 쿼리 파라미터로 rect를 추가하는 소폭 확장으로 충분하다.

---

# §17. QA 재검수 대응 (6차 — B3/S1/N1)

> 대상: `QA_transfer_plan_m2_review2.md`. 스위트 **352 passed / 1 allowed fail**(+13).

## B3 [병합 차단] 오버레이 정렬의 조용한 거울상 오답 — 가드로 해제

**지적 수용.** 원인은 QA 분석대로다: `rel_rot + 단일 flip`을 **하나의 변환기**로 합성하는데, `cell_to_physical`의 back 반전 축이 **그 프레임 자신의 회전에 따라 달라진다**(90/270이면 행, 아니면 열). 상대 회전 하나로는 두 프레임 각각의 반전 축을 표현할 수 없다.

- **조치**: `resolve_align`에서 `flip != "none"` **AND** `target.rotation ∈ {90,270}`이면 유도를 포기하고 `origin: "unresolvable"` → 호출부가 **`align_unavailable`로 거절**(셀 0건). 조용한 오답이 소리 나는 실패가 된다.
- **선언 override는 가드를 우회한다**(의도) — 사용자가 명시 선언한 변환은 탈출구로 남긴다. 유도 경로만 막는다.
- **라이브 실증**: 실제 메타에 `side=back` 4건(bonding_map 3·sample_map 1), `rot 270` 2건이 실재한다. `sample_map/aa123_a`(rot 270) 캔버스에 `bonding_map/4B13`(back)을 겹치면 **`align_unavailable` + `origin: unresolvable`**로 거절됨을 확인했다(이전엔 조용히 거울상으로 그려졌을 조합).
- **회귀 테스트 13종 추가**: `target_rot ∈ {90,270}` × `source_rot ∈ {0,90,180,270}` 8조합 파라미터 거절 검증 + **대조군 3종**(타깃 0/180은 정상 처리, 동일 side는 거절 안 함 — 과잉 거절 방지) + **비정방 격자 + 회전** 케이스(그렸다면 타깃 격자 범위 안인지 assert). 근본 수정 시 이 테스트가 기준이 된다.
- **수학 자체의 수정은 백로그**(각 프레임을 물리 좌표로 각각 사상 후 합성).
- 모듈 docstring의 과장(QA D3)도 정정 — "알려진 한계" 3항(B3/O2/O3)을 명시했다.

## S1 [성능] 인덱스 2건

- `idx_bonding_map_base` + `idx_sample_map_base` 추가 후 실행. **EXPLAIN ANALYZE 실측: 175만 행 Seq Scan(214ms) → Bitmap Index Scan 0.345ms** (~600배). 요청당 소스 8종까지 반복되므로 체감이 크다.
- `idx_transfer_plan_doe_layer_doe`는 **`pg_indexes` 직접 조회로 물리 반영 확인**(스크립트 `[ok]`만 믿지 않음 — 교훈 파일 규율).
- `transfer_plan_source_region` 인덱스는 `[skip]` 유지(테이블 보류).

## N1 [불변식] `remaining` 음수 가드

`build_chips_block`에 3줄 가드: `remaining < 0`이면 **원천 간 모집단 불일치**(마스크 밖 좌표·중복 행·프레임 불일치·백필 과도기)이므로 `remaining_reliable=false` + `remaining=None` + `negative_remaining` 경고(`effect: population_mismatch`). **음수는 상한으로서도 무의미하므로 `remaining_upper_bound`도 싣지 않는다.** 원인별 개별 수정 없이 계열 전체를 막는다.

⚠️ **라이브 재현 불가 — 정직한 보고**: QA가 지목한 `LOT-D/05`는 현재 `remaining 1125`(양수)다. 수집기 백필이 진행되며 데이터가 바뀌었다(eds_fail 124→71, transferred 410→22). 따라서 **라이브로 가드 발화를 실증하지 못했고 단위 테스트로만 고정**했다. 가드 자체는 경로 무관이라 동작에 의심은 없으나, "라이브 확인 완료"라고 쓰지 않는다.

## `source_region` 휴면 코드 표기

`load_source_region` docstring에 **"보류 중 — 계획 모델 재설계 대기(총괄 지시)"** 와 "배선 누락 결함이 아니다"를 명시했다(QA가 "다음 검수자가 결함으로 재보고할 뻔했다"고 지적한 건).

---

# §16. 마감 (배치 착지 상태)

## 16-0. 소스 영역(②) 보류 처리 방식

보류 지시 도착 시점에 엔진 코드·테스트가 이미 완성돼 있었다. **코드 제거는 그 자체가 새 변경**이므로 다음과 같이 처리했다:

| 대상 | 처리 |
|---|---|
| `transfer_plan_config.json`의 `plan_store.source_region` 선언 | **제거**(+ `.sample` 동기화) — 선언이 남으면 `/stages`에 `source_region: "missing"`이 떠 결함처럼 보인다 |
| 엔진 코드(`load_source_region`·`_core_region_counts`·`region_chips`·`plan_id` 파라미터) | **존치, 완전 휴면**. 바인딩 미선언 → `load_source_region`이 None 반환 → `region_chips` 미방출. `plan_id`를 붙여도 응답 무변화 |
| 테스트 6종 | **존치**(자체 픽스처로 자기 config를 씀 — 라이브와 무관) |
| `table_config` 영역 테이블 | **미적용 유지**(전문만 §14-5에 보고) |
| 인덱스 | `idx_transfer_plan_region_plan_src`는 `[skip]` 상태 유지 |

**되돌리려면**: `server/transfer_plan.py`에서 해당 함수 3개와 `plan_id` 파라미터, `main.py` 라우트의 `plan_id`, 테스트 6종을 제거하면 된다. 재설계 후 살릴 가능성이 있어 남겨두는 편이 낫다고 판단했으나, 총괄이 깨끗한 diff를 원하면 제거 지시를 달라.

## 16-1. 최종 스위트

**339 passed / 1 allowed fail**. 실패 1건은 착수 시점부터 동일한 `test_map_presets_api`(기본 프리셋 `std_300_12x13` 부재 — 본 작업 무관, "고쳐졌다" 판단 없음).

| 단계 | 수치 |
|---|---|
| 착수 기준선 | 278 / 1 |
| M2 기본 구현 | 298 / 1 |
| QA F1 수정 | 307 / 1 |
| F4·F6·F2 + S1'·S2·S3 | 333 / 1 |
| 소스 영역(휴면) | **339 / 1** |

## 16-2. 재기동 후 검증 체크리스트 (총괄/QA용)

**전제**: 신규 라우트 5종은 재기동 전까지 비활성이다.

1. `GET /api/transfer-plan/stages` → dt/bonding 2건, 역할 전부 `connected`, `plan_store` = plan/doe/map/doe_layer 4종 `connected`(`source_region` 키는 **없어야 정상**).
2. `GET /api/transfer-plan/source-summary?stage=bonding&lot=TAPE-A&slot=01` → `total 256, defect 30, eds_fail 20, remaining 209, remaining_reliable: true`, `by_core` 2건, `by_core_origin: "log"`, `by_core_truncated: false`, `truncated` 필드 **부재**, 강등 경고 **0건**.
3. `GET /api/transfer-plan/source-summary?stage=dt&lot=LOT-A&slot=05` → M1 `core-summary`와 동일 수치(`total 1288, defect 334, eds_fail 124, transferred 410, remaining 420`).
4. `GET /api/bonding-plan/core-summary?lot=LOT-A&slot=05` → **M1 계약 형태 그대로**(`chips`에 `defect/eds_fail/used/remaining` — `fail_breakdown` 아님). 계약 불변 확인.
5. `GET /api/transfer-plan/validate?plan_id=TP-SMOKE-1` → `status: "warnings"`, `availability_checked: true`, 경고에 `qty_shortage`(필요 300 > 가용 209)·`undefined_doe_value`·`layer_coverage_gap`·`source_fail_chips` 포함.
6. 미선언 stage → **404**. 미존재 plan_id → **404**(detail에 `not found`).
7. `GET /api/maps/overlay?target_table=core_defect_map&target_key=LOT-A_05&sources=eds_fail_map` → `align_applied: {rotation: 180, origin: "derived"}`, F셀 **124개**, `truncated: false`.
8. `GET /api/maps/paint-rules?table=transfer_plan_map` → `enabled: true`, `from_overlay: ["core_defect_map","eds_fail_map"]`. 다른 테이블은 `enabled: false`.
9. 맵 에디터에서 `dt_map` 열기 → TAPE 프리셋(20×20) 규격으로 코어별 영역 색 분포.

**응답이 JSON인지 확인할 것** — 라우트 부재 시 정적 catch-all이 HTML 200을 반환할 수 있다(QA는 현행 catch-all이 `api/` 접두를 404로 배제한다고 확인했으나, 프록시 개입 시 재현 가능).

## 16-3. [재설계 입력물] 계획 모델 재정의 영향 평가 (간략)

> 사용자 재정의: **"계획 = 맵 자체"** — `bonding_map`을 열어 편집하면 그게 BONDING PLAN, `dt_map`을 열면 DT PLAN. 계획 정체 = `(맵 테이블, map_key)`, stage는 맵 테이블에서 유도. 별도 `plan_id`·헤더·stage 선택기 없음.
> 아래는 **깊이 파지 않은 1차 판정**이며, 재설계 논의의 출발점이다.

### 생존/폐기 판정

| 산출물 | 판정 | 근거 |
|---|---|---|
| **가용 엔진**(`_summarize_inline`·fail 투영·`by_core`·align·강등/절단 규율) | 🟢 **100% 생존** | 입력이 `(stage, lot, slot)`뿐이고 계획 개념을 모른다. 모델과 완전 무관 |
| **오버레이 API**(`/api/maps/overlay`) | 🟢 **100% 생존 — 오히려 적합도 상승** | 이미 맵 네임스페이스에 있고 계획을 모른다. "맵을 열고 코어 fail을 겹쳐 본다"가 새 모델의 정확한 용법 |
| **paint-rules** | 🟢 **100% 생존** | 맵 단위 선언이라 새 모델과 직결 |
| **F1/F2/F4/F6 규율** | 🟢 **생존** | 엔진 내부 품질 장치 |
| **stage 선언 config** | 🟡 **대부분 재사용** | **현행 config에 이미 `target_map.table`이 있다**(dt→`dt_map`, bonding→`bonding_map`). 맵 테이블 → stage **역인덱스만 만들면 끝**이고, `GET /api/transfer-plan/stages` 응답이 이미 `target_map`을 노출하므로 **신규 API도 불필요**하다. 스키마 변경 거의 없음 |
| **validate 로직** | 🟡 **로직 생존, 입력 로딩부만 교체** | 수량 부족·층 커버리지·DOE-맵 정합·소스 fail·합산 초과·강등 차단은 전부 유효. 바뀌는 건 ①계획 조회 키(`plan_id` → `(ref_table, map_key)`) ②`painted` group-by 대상(`transfer_plan_map` → **대상 맵 테이블 자신**) |
| **`transfer_plan`(헤더)** | 🔴 **폐기** | 정체가 `(맵 테이블, map_key)`로 대체됨. `status`/`memo`만 잔존 가치가 있는데, 필요하면 `(ref_table, map_key)` 단위 소형 레지스트리나 `wafer_map_metadata` 확장으로 흡수 |
| **`transfer_plan_map`** | 🔴 **폐기 — 이게 "따로 논다"의 정체** | 페인팅 결과가 곧 **대상 맵 자체의 셀 값**이 된다. 별도 계획 맵이 존재할 이유가 소멸 |
| **`transfer_plan_doe`** | 🟡 **내용 생존, 키 교체** | 필드(source·qty·layer·knobs·description)는 그대로 유효. bk만 `plan_id\|doe_value` → `ref_table\|map_key\|value` |
| **`transfer_plan_doe_layer`** | 🟡 **생존, 키 교체** | 상동(`doe_key` 정의만 바뀜) |
| **소스 영역(②)** | ⚪ **보류가 옳았다** | 새 모델에선 "소스 영역"도 **소스 맵 자체를 열어 칠하는 것**으로 표현될 수 있어 별도 테이블이 불필요할 가능성이 크다 |

### DOE 저장 위치 권고

새 키 `(ref_table, map_key, value)`는 **`map_split_registry`가 이미 쓰는 패턴과 완전히 동일**하다(분리자 `|`까지).

| 안 | 장점 | 단점 |
|---|---|---|
| **A. `map_split_registry` 확장** (source·qty·layer·knobs 컬럼 추가) | 키·테이블 하나로 통합. **맵 에디터 legend UI가 곧 DOE 편집기**가 되어 "따로 논다" 불만이 구조적으로 해소. 온톨로지 `SplitCondition` 이미 매핑됨 | legend(모든 맵 공통, 색·서술)와 DOE(계획 맵 한정)가 한 테이블 → **대부분 행에서 DOE 컬럼이 NULL**. QA가 F5(`total_layers`)에서 지적한 "죽은 컬럼" 패턴 재생산 |
| **B. 형제 테이블** `map_doe_registry` (동일 키 패턴) | 관심사 분리, 컬럼이 전부 의미 있음. 키가 같아 legend와 1:1 조인 자명 | 같은 키로 테이블 2개 유지, 클라가 두 번 저장 |

**권고: B(형제 테이블), 단 클라는 legend 패널 하나에서 둘을 함께 편집**하고 동일 키로 조인해 보여준다. 사용자 체감은 하나이고, 스키마는 깨끗하다. A의 NULL 범람은 이번 QA에서 실제로 문제로 지적된 패턴이라 반복을 피하는 편이 낫다.

**마이그레이션 부담은 사실상 0**: A는 ALTER(기존 행 무영향), B는 신규 CREATE(무영향). 이관할 `transfer_plan_doe` 라이브 행도 스모크 몇 건뿐이다.

### 라이브 `transfer_plan*` 4종 정리 방안

**남겨도 물리적으로는 무해**하지만(아무도 읽지 않음) 세 가지 부작용이 있다: ①`table_config`에 있으면 그리드 테이블 목록·맵 셀렉터에 노출되어 사용자 혼란 ②온톨로지 매핑이 살아 있으면 materializer가 계속 `ExperimentPlan`/`SplitCondition` 노드를 생성 ③후속 검수자를 오도하는 죽은 테이블.

**권고 순서** (새 모델 확정 후):
1. `ontology_mapping.json`에서 `transfer_plan`/`transfer_plan_doe` 선언 제거 → 기존 그래프 노드·엣지 정리
2. `table_config.json`에서 4종 선언 제거 → `/admin/reload-configs`
3. 물리 테이블 DROP — **데이터 삭제라 사용자 승인 필요**

⚠️ **주의**: `sync_dynamic_tables_schema`는 ALTER 전용이라 **선언을 지워도 물리 테이블은 자동 DROP되지 않는다**(안전 설계). 수동 DROP이 필요하며, 그때까지는 "선언 없는 유령 테이블"로 남는다.

### 새 모델의 잠재 쟁점 (재설계 논의 시 확인 필요)

**계획값과 실적값이 같은 테이블에 섞인다.** `bonding_map`을 계획 캔버스로 쓰면 계획으로 칠한 셀과 실제 본딩 결과가 같은 컬럼에 들어간다. 다만 **레이어링이 이미 답을 갖고 있다** — `CellSource.source_name`으로 `user`(계획) vs `pipeline_parser`(실적)가 구분되고 `compute_priority_value`가 우선순위를 정한다. 계획/실적 대조(M3 예정 기능)를 이 레이어 차이로 구현할 수 있는지가 재설계의 핵심 검증 포인트로 보인다.

---

## 8. ⚠️ Escalation — 총괄 판단 요청 1건 (1차 — (2)로 해소됨)

**`origin_area_map`(dt_map 영역 귀속) 역할을 config 스키마에 추가했다.** 지시서 §B-3이 by_core 산출 근거를 "(dt_map 영역 귀속 + dt_log 조인)"으로 병기했는데, 실측상 **두 원천의 능력이 다르다**:
- `dt_log`(칩 단위): 테이프 좌표 ↔ 코어 좌표 대응이 있어 **fail 투영까지 가능** → by_core의 `fail` 산출 가능. 정본.
- `dt_map`(영역 귀속): 셀별 `val = 코어 식별`만 있고 코어 좌표가 없어 **fail 투영 원리적 불가**.

따라서 dt_log를 1순위로 하고, dt_log 미해석 시에만 dt_map으로 강등해 `total/used/remaining`만 제공하고 **`fail`은 `null`** 로 반환한다(0으로 위장하지 않음 — QA F2 "조용한 오답 금지" 취지). 이때 `by_core` 항목 형태가 달라진다:

| 경로 | by_core 항목 |
|---|---|
| origin_log (정본) | `{core_lot, core_slot, total, fail, used, remaining}` |
| origin_area_map (강등) | `{core_id, core_lot: null, core_slot: null, total, fail: null, used, remaining}` |

**클라 표시 계약에 영향**이 있어 총괄 확인이 필요하다. (대안: 강등 경로를 아예 빼고 dt_log 없으면 by_core 미동봉 — 이 경우 `origin_area_map` 블록을 config에서 제거하면 코드 변경 없이 동작한다. 두 경로 모두 테스트로 고정돼 있다.)

> **[해소됨 — 총괄 결정 반영]** 강등 경로 존치 + 두 경로 키 집합 동일화 + `by_core_origin` 마커 추가로 조치 완료. 위 표의 "형태가 달라진다"는 더 이상 유효하지 않다 — 현행 계약은 §8-bis-(2) 참조.

## 9. 세션 재개 시점 상태 점검 결과 (총괄 지시 1~3)

중도 종료 직전 작업("TAPE 프리셋 등록 + 스케줄러 재스캔 + dt_log 수집기 즉시 실행")은 **전부 실제 반영돼 있었다**:
- `git status`: `server/transfer_plan.py`·`test_transfer_plan.py`·`transfer_plan_config.json.sample` 신규, `server/main.py` 수정(61줄 순수 추가). `client2/*` 변경분은 **병렬 클라부 소유로 확인하고 미접촉**.
- 라이브: `dt_log` 768행 / `dt_map` 768행(테이프 3장 × 256칩), 맵 메타 3건, 프리셋 `tape_std` 등록 확인, 스케줄러에 `dt_log`/`dt_map` 수집기 SUCCESS 등재.
- 따라서 §D는 재실행하지 않고, 잔여 범위(§B by_core 영역귀속 보강 / §C config·온톨로지 전문 / 인덱스 / 라이브 교차검증 / 전수 스위트)만 진행했다.

### 지시서 A~D 대비 잔여 체크리스트

| # | 항목 | 상태 |
|---|---|---|
| A-1 | stage 선언 config + 하위호환 근거 | ✅ 완료 (§3, §3-1) |
| B-2 | `/stages` | ✅ 완료 (라우트는 재기동 대기) |
| B-3 | `/source-summary` + by_core | ✅ 완료 (강등 경로 §8 확인 요청) |
| B-4 | history knob | ✅ 완료 (M1 규율 승계) |
| C-5 | 계획 테이블 3종 | ✅ **총괄 적용 완료** — 물리 테이블 3개 + 인덱스 3종 생성, 배치 업데이트 경로로 스모크 통과(§8-bis) |
| C-6 | 저장/로드 + validate | ✅ 완료 (신규 CRUD 0, §4 — 스모크로 실증) |
| C-7 | 온톨로지 매핑 | ✅ **총괄 적용 완료** — 노드 3·엣지 5 승격 라이브 확인(§8-bis-3) |
| D-8 | fake DT 데이터 | ✅ 완료 (§6) |
| 테스트 | 신규 + 전수 | ✅ 298 passed / 1 allowed fail |

## 10. 라이브 검증 한계 (재기동 후 확인 항목)

신설 라우트 3개는 웹서버 재기동이 필요하다(핫리로드 범위 밖 — 지시서 예외 인정). 현재 라이브 :8080에는 라우트가 없어 **정적 catch-all이 HTML 200을 반환**하므로(교훈 파일 기지 함정) 클라이언트는 "응답이 JSON인지" 가드가 필요하다. 재기동 후 체크리스트:
1. `GET /api/transfer-plan/stages` → dt/bonding 2건 + 역할 전부 `connected` + `plan_store` 3종 `connected`.
2. `GET /api/transfer-plan/source-summary?stage=bonding&lot=TAPE-A&slot=01` → §5-2와 동일 수치 JSON(total 256, defect 30, eds 20, remaining 209, by_core 2건, `by_core_origin: "log"`).
3. `GET /api/transfer-plan/source-summary?stage=dt&lot=LOT-A&slot=05` → M1 수치와 동일.
4. 미선언 stage 404 / `GET /api/transfer-plan/validate?plan_id=TP-SMOKE-1` → §8-bis-3의 경고 5건.
5. 맵 에디터에서 `dt_map` 열기 → TAPE 프리셋 규격으로 코어별 영역 색 분포 확인. `transfer_plan_map`이 맵 셀렉터에 노출되는지(페인팅 캔버스) 확인.

## 11. 미해결·후속 (M3 후보 포함)

- ~~§8-bis-(4) stage 어휘 불일치~~ → **해소**(QA D5): 문제의 `bonding_plan__TESTPLAN_M2VERIFY_01` 행은 클라부가 정리 완료(라이브 잔여 0). 원인도 규명됐다 — 미커밋 클라 파일의 이전 리비전이 `dt_plan`/`bonding_plan`을 stage id로 쓰던 시점의 산물이며, 현재는 어휘가 교정되고 `LEGACY_STAGE_ALIASES` 가드까지 있다. 서버측은 stage 어휘 정본을 docstring에 명문화하는 것으로 마무리.
- 스모크 시드 `TP-SMOKE-1`(plan 1 / doe 2 / map 4행) 정리 여부 — 총괄 판단(§8-bis-3 관찰 2).
- **QA §6-2 후속 티켓**: F2(캡 절단 표기)·F3(중복 행)·F4(소스 합산 초과배정)·F5(`total_layers` 3자 배선)·F6(`dst_grid` 전달)·F7(N+1 배치화)·F9(비결정 절단)·F10(`qty 0` 승격). 그중 **F4·F6은 오답을 낳는 부류**라 우선순위가 높다고 본다.
- `identity_key` 이스케이프(`\|`) — 그래프 조회 시 주의점을 클라 문서/리빙 문서에 반영 필요(doc-keeper).
- ~~§7 config 2건 총괄 적용 + §8 escalation 판단~~ → **완료**(§8-bis).
- `transfer_plan_map` 페인팅 UX(클라부 병렬 산출물)와의 통합 스모크 — 재기동 후.
- `by_eqp` 장비별 align 적용은 여전히 미적용(M1과 동일 — 파싱만 통과). `eds_fail_map.metro_eqp` 데이터는 이미 있어 착수 가능.
- 기전사(`transfer_log`) 소진이 테이프 identity로 쌓이기 시작하면 §6 서사대로 `transferred`가 증가한다 — 신규 본딩 fake를 테이프 기준으로 전환할지는 데모 정책 결정 사항.
- M3: 실적 대조(계획 vs 실제 bonding_log)·중복 배정 감지·EDS 연동.
- history 앵커 문서/CODE_MAP 갱신은 지시서 금지(문서 총괄 일괄) — §12 초안 참조.

## 12. 히스토리 초안 (총괄 통합 시 사용)

> feat(transfer-plan): M2 서버부 — Universal Transfer Plan 전사 프레임워크(`transfer_plan_config.json` stage 선언 + `server/transfer_plan.py`) + API 3종(`/api/transfer-plan/stages|source-summary|validate`). 모든 전사 단계를 `(stage, 타깃 맵 페인팅, assignments)` 프리미티브의 인스턴스로 일반화 — 신규 단계는 config 선언만으로 추가. 코어 fail의 **dt_log 조인 투영**으로 "테이프에도 불량 섞임"을 처리하고(align 180 실증: 투영 20 vs 무변환 대조군 26), by_core 출신별 분해는 dt_log 1순위 / dt_map 영역 귀속 강등(fail=null). remaining은 fail∪transferred 합집합 의미론으로 이중 감산 제거. M1 `core-summary`는 dt stage 인스턴스로 내부 통합하되 `bonding_plan.py` 무수정으로 외부 계약 불변. fake DT 원천 2종(dt_log/dt_map 핫리로드 온보딩, 테이프 3장×256칩 — 불량 칩 포함 블록 전사) + TAPE 프리셋·맵 메타 + 인덱스 3종. 신규 CRUD API 0(기존 제네릭 경로 재사용). 테스트 297 passed(+19)/1 allowed fail(#4). 라우트는 재기동 대기.

## 13. 교훈 제안 (server-pm.md 반영 후보)

1. **함정**: 스탠드얼론 검증 스크립트에서 `database.SessionLocal`만 임포트하면 `models.DYNAMIC_TABLES`가 비어 있어 **역할 바인딩이 전부 `missing`으로 나온다** — config·데이터가 멀쩡한데도 "미연결"로 오진하게 된다(본 작업에서 실제로 1회 오진).
   **올바른 방법**: 라이브 함수 단 검증 스크립트는 웹서버 기동 경로와 동일하게 `models.init_dynamic_models(table_config)`를 먼저 호출하고, 스크립트 첫 줄에서 `len(DYNAMIC_TABLES)`와 대상 테이블 존재를 출력해 게이트로 삼는다.
2. **함정**: "출신별 분해"처럼 원천이 2종(칩 단위 로그 / 영역 귀속 맵) 병기된 요구는 두 원천의 **능력이 비대칭**일 수 있다 — 영역 맵에는 좌표 대응이 없어 fail 투영이 원리적으로 불가한데, 같은 응답 필드에 0을 채우면 "불량 없음"으로 조용히 오독된다.
   **올바른 방법**: 강등 경로에서 산출 불가한 지표는 `0`이 아니라 `null`로 반환하고 상태 문자열(`connected(area_only)`)로 능력 차이를 명시한다.
3. **함정**: 좌표 투영 조인을 "코어마다 전체 칩 목록을 훑는" 이중 루프로 짜면 O(코어수 × 칩수)라 테이프당 수백 코어 규모에서 폭발한다 — 소규모 데모 데이터에서는 테스트가 전부 통과해 드러나지 않는다.
   **올바른 방법**: 조인 키(출신 코어)별 버킷 인덱스를 1회 구축해 **메모리 루프**를 선형화한다.
   **단, 이것만으로 "선형화 완료"라고 쓰면 과장이다** — 초판 보고서가 그렇게 적었고 QA(D3)가
   실측으로 반증했다. 쿼리 왕복은 여전히 **O(코어수 × fail원천수)**(2코어 10문)다. 확장성
   주장은 "무엇을 줄였고 무엇이 남았는지"를 축(메모리 연산 vs 쿼리 왕복)별로 분리해 쓴다.
4. **함정**: "부분 가동(graceful degradation)"은 그 자체로 미덕처럼 보이지만, 역할이 무너져
   **감산항이 0이 되면 잔여 수량이 조용히 부푼다** — 상태를 `sources` 같은 부가 필드에만
   적어두면 소비자는 정상과 구별하지 못하고, 그 값을 쓰는 검증 API까지 동시에 무력화된다
   (QA F1: 209 → 256/226/236이 `warnings: []`로 반환).
   **올바른 방법**: ①강등을 **`warnings`에 명시 항목**으로 싣고 ②신뢰 불가한 수치는 **`null`로
   내려** 소비자가 분기 없이는 표시조차 못 하게 하며(플래그만으로는 무시 가능) ③상한이
   의미 있는 경우에만 `*_upper_bound`를 별도 필드로 준다. 그리고 **"검사 안 함"과 "이상 없음"을
   같은 status 값으로 내지 않는다**(`ok` vs `unverified`).
5. **함정**: 강등 경로 테스트가 초록불이어도 그 assert가 **결함 동작을 정답으로 고정**하고 있을
   수 있다 — 본 작업의 `assert remaining == 5`가 정확히 과대값을 스펙으로 박아, 후속 검수자가
   초록불을 보고 안전하다고 오판할 뻔했다.
   **올바른 방법**: 실패·강등 경로 테스트는 상태 문자열뿐 아니라 **"핵심 수치가 어느 방향으로
   틀리며 그것이 사용자에게 고지되는가"** 를 assert한다. 정상 경로 대조군도 함께 둬서 과잉
   강등(상시 오탐)이 생기지 않는지 고정한다.
