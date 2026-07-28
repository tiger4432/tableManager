# `bonding_plan_config.json` 세팅 — M1 본딩 계획 역할 바인딩

> **Status:** 🟢 Living | **Last-verified:** 2026-07-28 | **Owner:** Backend / UI-Map
> 상위: [폴더 인덱스](./README.md) · [CONFIG_GUIDE §3-S6](../CONFIG_GUIDE.md) · [MAP_EDITOR_SPEC §6](../../spec/MAP_EDITOR_SPEC.md)(엔진 계약)

<!-- Loader evidence (2026-07-28):
  load: server/bonding_plan.py:51 load_bonding_plan_config (missing/corrupt -> {} partial operation)
  per-request snapshot: server/main.py:3112
  roles: bonding_plan.py:37 ROLES = (process_history, defect, eds_fail, used_chips, total_chips)
  canonical frame order: bonding_plan.py:44 CANONICAL_FRAME_ROLES = (total_chips, defect, eds_fail)
  binding shape: bonding_plan.py:68 _valid_source ({table:str, columns:dict})
-->

## 1. 언제 이 파일을 만지는가

- **M1 본딩 가용량 화면(core-summary)을 현장 테이블에 연결할 때** — 코드는 테이블명을 하드코딩하지 않으므로 바인딩 교체만으로 원천이 바뀝니다
- fail로 칠 값(`fail_values`)·경고 값(`result_fail_values`)을 현장 코드 체계에 맞출 때
- M2의 `source_config_ref: "bonding_plan"` stage가 이 바인딩을 재사용하므로, **dt stage의 소스를 바꿀 때도 여기**를 만집니다

## 2. 세팅 절차

1. **스냅샷**: `conda run -n assy_manager python server/scripts/backup_config.py snapshot`
2. **전제 확인**: 바인딩할 테이블이 전부 `table_config.json`에 선언돼 있어야 합니다(미선언 = 그 role `missing`). `wafer_map_metadata`만 제품 소유이고, `bonding_log`·`core_defect_map`·`eds_fail_map`·`wafer_process`는 현장 소유 예시명 — **당신의 실제 이름**으로 먼저 선언하십시오 → [table_config.md](./table_config.md).
3. 파일이 없으면 `bonding_plan_config.json.sample`을 확장자 없이 복사한 뒤, `sources.<role>.table`/`.columns`를 실테이블·실컬럼명으로 교체합니다. role은 5종 고정: `process_history` · `defect` · `eds_fail` · `used_chips` · `total_chips`.

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

- 응답의 role별 상태가 **`connected`** 인지 확인합니다.
- `missing` = 바인딩 문제 → ①테이블 미선언 ②컬럼명 오타 ③`{table, columns}` 형태 위반 순으로 의심.
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
| `sources.<role>.table` / `.columns` | `{table: str, columns: {역할키: 물리컬럼}}` — 형태 위반 시 그 role은 `missing`(에러 아님) |
| `sources.<role>.mode` | `"map"` = 좌표 격자 소스 |
| `sources.<role>.fail_values` | 맵 모드에서 fail로 칠 값 목록 |
| `warnings.result_fail_values` | `process_history.result`에서 경고로 표면화할 값 |
| ~~`sources[].align`~~ | 🗑️ 폐지 — 무시됨. 메타 등록으로 대체 ([MAP_EDITOR_SPEC §5.0](../../spec/MAP_EDITOR_SPEC.md)) |
