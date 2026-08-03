# `bonding_plan_config.json` 세팅 — M1 본딩 계획 역할 바인딩

> **Status:** 🟢 Living | **Last-verified:** 2026-08-04 | **Owner:** Backend / UI-Map
> 상위: [폴더 인덱스](./README.md) · [CONFIG_GUIDE §3-S6](../CONFIG_GUIDE.md) · [MAP_EDITOR_SPEC §6](../../spec/MAP_EDITOR_SPEC.md)(엔진 계약)

<!-- Loader evidence (2026-08-04, availability relaxation pass — anchors re-measured):
  load: server/bonding_plan.py:69 load_bonding_plan_config (missing/corrupt -> {} partial operation)
  per-request snapshot: server/main.py:4232
  roles: bonding_plan.py:41 ROLES = (process_history, defect, eds_fail, used_chips, total_chips)
  canonical frame order: bonding_plan.py:62 CANONICAL_FRAME_ROLES = (total_chips, defect, eds_fail)
  binding shape: bonding_plan.py:86 _valid_source ({table:str, columns:dict})
  aggregate: bonding_plan.py:305 get_core_summary / remaining arithmetic: :539
  relaxation (2026-08-04, 2c2a777): :53 STATUS_NOT_DECLARED / :55 SUBTRACTION_ROLES = (defect, eds_fail, used_chips)
    / :94 role_is_declared (predicate = KEY PRESENCE) / branches :358 map roles, :452 used_chips, :485 process_history
    / inactive_subtractions emit: :552 (total_chips excluded — the denominator stays required)
-->

## 1. 언제 이 파일을 만지는가

- **M1 본딩 가용량 화면(core-summary)을 현장 테이블에 연결할 때** — 코드는 테이블명을 하드코딩하지 않으므로 바인딩 교체만으로 원천이 바뀝니다
- fail로 칠 값(`fail_values`)·경고 값(`result_fail_values`)을 현장 코드 체계에 맞출 때
- M2의 `source_config_ref: "bonding_plan"` stage가 이 바인딩을 재사용하므로, **dt stage의 소스를 바꿀 때도 여기**를 만집니다

## 2. 세팅 절차

1. **스냅샷**: `conda run -n assy_manager python server/scripts/backup_config.py snapshot`
2. **전제 확인**: 바인딩할 테이블이 전부 `table_config.json`에 선언돼 있어야 합니다 — **바인딩해 놓고** 그 테이블이 `table_config`에 없으면 그 role은 `missing`(깨진 선언)입니다. 애초에 그 role 키를 안 쓰는 것과는 다릅니다(§5의 세 상태 표). `wafer_map_metadata`만 제품 소유이고, `bonding_log`·`core_defect_map`·`eds_fail_map`·`wafer_process`는 현장 소유 예시명 — **당신의 실제 이름**으로 먼저 선언하십시오 → [table_config.md](./table_config.md).
3. 파일이 없으면 `bonding_plan_config.json.sample`을 확장자 없이 복사한 뒤, `sources.<role>.table`/`.columns`를 실테이블·실컬럼명으로 교체합니다. role 어휘는 5종 고정: `process_history` · `defect` · `eds_fail` · `used_chips` · `total_chips`. **[2026-08-04] 이 중 필수는 `total_chips` 하나이고 나머지 넷은 선택입니다** — 현장에 그런 표가 없으면 **키를 아예 쓰지 마십시오**(§5). 안 쓰는 role을 억지로 채워 놓는 것이 가장 나쁜 선택입니다.

   ```json
   "used_chips": {
     "table": "<당신의 본딩 로그 테이블>",
     "columns": { "lot": "core_lot", "slot": "core_slot", "x": "cx", "y": "cy" }
   },
   "eds_fail": {
     "mode": "map",
     "table": "<당신의 EDS fail 맵 테이블>",
     "columns": { "lot": "lot", "slot": "slot", "x": "x", "y": "y", "val": "val" },
     "fail_values": ["F"]
   }
   ```
4. 저장합니다(이 파일은 watcher 대상이 아니라 저장 방식 무관).
5. **좌표계가 다른 맵에 `align`을 선언하지 마십시오** — 폐지(2026-07-27)됐고 남아 있어도 무시됩니다. 대신 **각 맵을 `wafer_map_metadata`에 등록**합니다(변환은 두 맵의 메타 델타에서 유도, canonical 프레임은 메타가 등록된 첫 맵 모드 역할: `total_chips` → `defect` → `eds_fail`).
6. 반영은 자동입니다 — **다음 요청부터 디스크 재읽기**(요청당 1회 스냅샷). 재기동·reload 불필요.

## 3. 반영 확인

```
GET /api/bonding-plan/core-summary?lot=<lot>&slot=<slot>
```

- `total_chips`가 **`connected`** 인지 먼저 확인합니다(분모).
- `missing` = **선언해 놓고 깨진** 바인딩 → ①테이블 `table_config` 미선언 ②컬럼명 오타 ③`{table, columns}` 형태 위반 순으로 의심.
- **[2026-08-04] `not_declared`** = 그 role 키를 안 썼다는 뜻으로, **결함이 아니라 정상**입니다. 그 감산항 없이 집계하고, 빠진 종류는 응답의 `inactive_subtractions`가 이름으로 말합니다. `missing`과 헷갈리면 있지도 않은 결함을 쫓게 됩니다 — 둘을 구별하는 것이 이 상태의 존재 이유입니다.
- `connected(align_unavailable)` = 바인딩은 됐는데 격자 규격이 없음 → `wafer_map_metadata` 행부터 확인 (**카운트는 0으로 나옵니다** — raw 좌표로 조용히 계산하지 않는 명시 실패).
- HTTP 200 + 숫자 0 + 에러 없음은 정상 형태의 부분 가동입니다 — 상태 필드를 읽어야 원인이 보입니다 ([CONFIG_GUIDE §6-I](../CONFIG_GUIDE.md)).

## 4. 잘못됐을 때

```bash
conda run -n assy_manager python server/scripts/backup_config.py restore bonding_plan_config_<yymmdd>.json.bak --yes
```

요청마다 재읽으므로 복원 즉시 다음 요청부터 옛 동작입니다. 코드까지 얽히면 [ROLLBACK_PROCEDURE](../ROLLBACK_PROCEDURE.md)(순서: config → 코드 → 재기동).

## 5. 키 참조

| 키 | 의미 |
|---|---|
| `core_identity.compose` | 코어 정체성 구성 컬럼, 기본 `["lot","slot"]` |
| `map_metadata` | 맵 메타 조회 바인딩 `{table, columns: {target_table, map_id, grid_metadata}}` — region 클램프·정렬 유도의 원천 |
| `sources.<role>.table` / `.columns` | `{table: str, columns: {역할키: 물리컬럼}}` — **선언해 놓고** 형태를 위반하면 그 role은 `missing`(에러 아님) |
| `sources.<role>.mode` | `"map"` = 좌표 격자 소스 |
| `sources.<role>.fail_values` | 맵 모드에서 fail로 칠 값 목록 |
| `warnings.result_fail_values` | `process_history.result`에서 경고로 표면화할 값 |
| ~~`sources[].align`~~ | 🗑️ 폐지 — 무시됨. 메타 등록으로 대체 ([MAP_EDITOR_SPEC §5.0](../../spec/MAP_EDITOR_SPEC.md)) |

### 5.1 보조 역할은 선택입니다 — 상태는 둘이 아니라 셋 (2026-08-04 `2c2a777`)

현장은 lot별 fail·소모 부속 테이블을 두지 않고 **불량 맵을 겹쳐 그려 맵 위에서 차감**합니다. 종전 엔진은 그런 사이트의 키 부재를 깨진 바인딩과 같은 `missing`으로 접어 강등시켰고, 결과적으로 **모든 자재의 가용이 미상**이었습니다. 이제 판정 기준은 **키가 `sources`에 있느냐**이지 그 값이 쓸 만하냐가 아닙니다(`bonding_plan.role_is_declared`).

| config 상태 | role status | 집계 | 강등인가 |
|---|---|---|---|
| 키가 **아예 없음** | **`not_declared`** | 그 감산항 없이 계산 (부재 role은 종전에도 0을 기여했으므로 **숫자는 안 바뀝니다**) | 아니오 |
| 키는 있는데 깨짐 (테이블 부재·컬럼 오타·형태 위반) | `missing` 등 | 종전 그대로 | 예 |
| 키가 있고 정상 | `connected` | 종전 그대로 | 아니오 |

- 대상은 **`process_history`·`defect`·`eds_fail`·`used_chips`** 넷입니다. 🔴 **`total_chips`는 예외로 계속 필수** — 분모가 없으면 가용이 성립하지 않으므로 부재도 `missing`입니다. "이제 다 선택"으로 일반화하면 그 코어의 가용이 통째로 미상이 됩니다.
- **`inactive_subtractions`** — 감산에서 빠진 종류의 이름 목록(예: `["defect", "used_chips"]`)이 `core-summary` 응답의 최상위 선택 필드로 나갑니다. 비면 필드 자체가 없으므로 **전 역할 선언 환경의 응답은 완화 전과 바이트 단위로 동일**합니다. 감산항만 실리므로 `process_history`는 들어가지 않습니다.
- **M1의 산술은 안 바뀌었습니다** — `remaining = total − defect − eds_fail − used`이고 미선언 role은 종전에도 0이었습니다. 달라진 것은 상태 문자열과 이 새 필드뿐입니다.
- M2가 이 바인딩을 위임받는 dt stage에서는 어휘가 개명돼 실립니다(`used_chips` → `transfer_log`). 그 경로에서는 `transferred`가 `null`로 나갑니다(로그가 없으므로 미상 — 가짜 `0` 금지). 전체 의미론과 클라 표기 계약은 [MAP_EDITOR_SPEC §6.2-ter](../../spec/MAP_EDITOR_SPEC.md)가 정본입니다.
- **라이브 config는 손댈 것이 없습니다.** 강등을 피하려고 일부러 깨진 바인딩을 넣어 둔 사이트는 이제 그 **키를 지우면** 됩니다.
