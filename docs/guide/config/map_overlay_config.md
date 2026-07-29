# `map_overlay_config.json` 세팅 — 맵 오버레이 바인딩 + 페인트 잠금

> **Status:** 🟢 Living | **Last-verified:** 2026-07-28 | **Owner:** Backend / UI-Map
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
-->

## 1. 언제 이 파일을 만지는가

- **컬럼명이 관례 밖인 테이블을 오버레이에 올릴 때** (예: `dt_log`의 `tx/ty`) — **관례 안이면 만질 필요 없습니다.** 선언 없이도 오버레이는 동작합니다(`table_config`의 `map_key_columns` + x/y/val 후보에서 자동 유도)
  - ⚠️ **값 컬럼도 후보 매칭이 필수**입니다(F2, 2026-07-28): `value_column_candidates`에 하나도 안 맞으면 유도는 **거부**합니다(과거의 "첫 데이터 컬럼 추측"은 데이터 경로에서 제거 — 오버레이는 `source_missing`, 수량 유도는 `missing`으로 정직하게 강등). 값 컬럼명이 후보 밖(대문자 `VAL` 등)이면 `table_bindings`에 선언하십시오.
- **페인트 잠금 규칙을 바꿀 때** — 어떤 값 위에 칠할 수 없는지, 잠금 판정을 어느 오버레이 소스에서 가져올지
- **[U6] 레지스트리 행이 없는 맵의 기본 legend를 선언할 때** (`default_legend`) — 미선언이면 기본 의미론 없음(클라는 bare 값을 팔레트 색으로 렌더)
- **[U6] 값 컬럼 자동 탐지 순서를 바꿀 때** (`value_column_candidates`) — 미선언이면 서버 문서화 기본 적용

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

## 3. 반영 확인

1. `GET /api/maps/paint-rules?table=<t>` — 머지된 잠금 규칙이 기대대로인지. **[U6]** 같은 응답의 `value_column_candidates`가 선언(또는 기본) 순서 그대로인지, `default_legend`가 선언 배열 그대로(미선언이면 `null`)인지.
   - **[F1]** 같은 응답의 `binding`이 그 테이블의 RESOLVED 바인딩인지: `{x, y, val, key_columns[], source}`. `source`는 `declared`(table_bindings 선언) > `derived`(table_config 유도), 해석 불가면 `null`. `fallback_guess`는 **값 컬럼이 후보 밖이라 추측만 남은 상태**라는 경고 표지입니다 — 데이터 경로는 이 추측을 거부하므로, 이게 보이면 선언을 추가하십시오. **에디터도 같은 커밋에서 이 필드를 소비하도록 바뀌었습니다**(클라 자체 유도 삭제): 드롭다운이 이 값으로 미리 선택되고, `fallback_guess`는 **로드 경로에서는 경고 후 진행 / 오버레이 경로에서는 거부**입니다. 즉 **선언만 하면 대문자·한글·숫자 시작 테이블명, `tx`/`ty` 좌표도 그대로 로드·오버레이됩니다** — 종전에 "오버레이 설정이 안 먹던" 원인이 바로 이 클라 측 재유도였습니다.
2. `GET /api/maps/overlay?target_table=<t>&target_key=<k>&sources=<src>:<key>` — `overlays[].status`가 `ok`인지, `align_applied.origin`이 `derived`(메타 유도)인지 `identity`(메타 부재)인지.
   - `identity`는 실패가 아니지만 **메타 미등록 신호**입니다 — 정렬이 필요하면 메타부터 등록.
   - `source_missing` = 테이블 미선언/바인딩 해석 실패.
3. 맵 에디터 화면에서 잠긴 셀에 페인팅 시 선언한 `message`가 뜨는지.

## 4. 잘못됐을 때

```bash
conda run -n assy_manager python server/scripts/backup_config.py restore map_overlay_config_<yymmdd>.json.bak --yes
```

요청마다 재읽으므로 복원 즉시 반영 → [ROLLBACK_PROCEDURE](../ROLLBACK_PROCEDURE.md).

## 5. 키 참조

```
table_bindings.<table>.columns.{x, y, val, key_columns[]}
paint_lock."*".{enabled, blocking_values[], from_overlay[], message}
paint_lock.<table>.{enabled, blocking_values[], from_overlay[], message}
default_legend[].{value, desc, color, locked}
value_column_candidates[]
```

| 키 | 의미 |
|---|---|
| `table_bindings.<table>.columns` | 그 테이블을 맵으로 읽을 때의 좌표/값 컬럼. `key_columns`는 맵 인스턴스 식별 컬럼 |
| `default_legend[]` | [U6·선택] 레지스트리 행 없는 맵의 기본 legend 행(선언 그대로 서빙, 미선언 = 응답 `null` = 기본 의미론 없음) |
| `value_column_candidates[]` | [U6·선택] 값 컬럼 자동 탐지 순서(앞선 것 우선). 미선언 = 문서화 기본. 응답에는 항상 RESOLVED 값 |
| `paint_lock.<t>.enabled` / `blocking_values[]` | 잠금 on/off · 이 값이 있는 셀은 페인팅 불가 |
| `paint_lock.<t>.from_overlay[]` | 잠금 판정을 자기 셀이 아니라 나열된 오버레이 소스의 셀에서 가져옴 |
| `paint_lock.<t>.message` | 차단 시 사용자 문구 |
| ~~`align_overrides`~~ | 🗑️ 폐지 — 무시됨 |

- 계획 맵 사본(`transfer_plan_map`)은 폐기 — 계획 캔버스의 잠금은 그 stage의 `target_map` 테이블에 직접 선언.
- `GET /api/maps/overlay`의 `eqp` 파라미터는 no-op 존치.
- 맵 에디터 클라는 `7d931dc` 이후 서버 오버레이 좌표를 소비하지 않고 변환을 자체 수행 — 서버 응답으로 클라 화면을 검증하지 마십시오.
