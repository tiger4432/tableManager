# Server — `.sample` config v1 잔재 정정 (transfer_plan / map_overlay)

- 담당: Server PM
- 일자: 2026-07-26
- 범위: `server/config/transfer_plan_config.json.sample`, `server/config/map_overlay_config.json.sample`, `docs/guide/CONFIG_GUIDE.md` §5.8 주석 1개
- 라이브 config(비-sample) **무수정**, 파일 삭제 **없음**, DB 쓰기 **없음**, 커밋 **없음**, `server/transfer_plan.py` **무수정**

---

## 1. 계약의 출처 (라이브 config 미참조)

샘플 값은 **코드에서 역산**했다. 근거:

| 요구 | 출처 |
|---|---|
| `doe` 필수 `(ref_table, map_key, doe_value, band_seq)` | `server/transfer_plan.py:209-210`, `:1138-1139` |
| `doe_source` 필수 `(ref_table, map_key, doe_value, band_seq, source_lot, source_slot)` | `server/transfer_plan.py:213-217`, `:1178-1181` |
| `source_region` 필수 `(ref_table, map_key, source_lot, source_slot, x, y)` | `server/transfer_plan.py:218-221`, `:383-385` |
| 선택 역할 실제 소비 지점 | `_doe_get`: `doe_value`·`band_seq`·`stack_band`·`qty_total` (`:1215,1236-1237,1288-1290`) / `_sget`: `source_lot`·`source_slot`·`qty`·`note` (`:1196-1203`) |
| 테이블명 `map_doe` / `map_doe_source` / `map_source_region` | `server/scripts/setup_transfer_plan_indexes.py:33-35` (커밋된 코드) |
| 컬럼 형태 | `server/tests/test_transfer_plan.py:88-113` `TP_TABLES` (커밋된 테스트) |

> `doe.knobs` / `doe.note`는 `transfer_plan.py`가 **읽지 않는다**(DOE 테이블의 사용자 편집 컬럼일 뿐). `CONFIG_GUIDE.md §5.8` 발췌가 이미 그 형태이므로 **샘플-가이드 무발산**을 우선해 그대로 유지했다. 미해석 선택 컬럼은 `bonding_plan._resolve_model_columns:321-326`이 조용히 드롭하므로 무해하다.

## 2. 변경 전후 키 대조표

### 2-1. `transfer_plan_config.json.sample` → `plan_store`

| 역할 | before (v1 잔재) | after | 판정 |
|---|---|---|---|
| `plan` | `transfer_plan` / `plan_id, stage, target_lot, target_slot, status, memo` | **제거** | 코드가 읽지 않음 (계획 헤더 폐기) |
| `map` | `transfer_plan_map` / `plan_id, x, y, val` | **제거** | 계획 맵 사본 폐기 |
| `doe_layer` | `transfer_plan_doe_layer` / `doe_key, layer, source_lot, source_slot, qty, note` | **제거** | "층마다 소스 1개" 차원 소멸 |
| `doe` | `transfer_plan_doe` / `plan_id, doe_value, source_lot, source_slot, qty_per_unit, layer_from, layer_to, knobs, description` — **필수 4개 전부 부재 → `missing`** | `map_doe` / `ref_table, map_key, doe_value, band_seq, stack_band, qty_total, knobs, note` | 필수 4/4 충족 |
| `doe_source` | **키 없음** | `map_doe_source` / `ref_table, map_key, doe_value, band_seq, source_lot, source_slot, qty, note` | 필수 6/6 충족 |
| `source_region` | **키 없음** | `map_source_region` / `ref_table, map_key, source_lot, source_slot, x, y, val` | 필수 6/6 충족 (선택·휴면) |

`plan_store.__comment` 1건 + `source_region.__comment` 1건 추가 — 구 환경에서 올라오는 사람이 사라진 키를 추적할 수 있게 폐기 사유·폐기 테이블명·폐기 컬럼명을 명시. (`_plan_store_statuses`는 `store.get(role)`만 보고, `_valid_binding`/`_resolve_model_columns`는 `table`·`columns`만 보므로 `__comment` 키는 무해하다.)

### 2-2. `map_overlay_config.json.sample`

| 위치 | before | after |
|---|---|---|
| `table_bindings.transfer_plan_map` | `x,y,val` + `key_columns:["plan_id"]` (폐기 테이블) | **제거** |
| `paint_lock.transfer_plan_map` | `blocking_values:["F"]`, `from_overlay:[core_defect_map, eds_fail_map]` | 키명을 `__example_bonding_map`으로 변경 (파일 내 기존 관례 `align_overrides.__example_eds_fail_map`와 동일) |
| 루트 `__comment` | — | v1 제거 사유 1줄 추가 |

`paint_lock`은 `map_overlay.py:688-691`에서 **정확한 테이블명 키 조회**이므로 `__example_` 접두 키는 어떤 테이블에도 매칭되지 않는다 → **동작 변화 0**, 예시 문서 가치는 보존. 실제 잠금이 필요하면 사용자가 stage의 `target_map` 테이블명으로 키를 바꿔 쓴다. (여기서 `bonding_map`을 **활성** 항목으로 만들면 신규 환경에 페인트 차단 정책을 임의로 강제하게 되므로 하지 않았다.)

### 2-3. `docs/guide/CONFIG_GUIDE.md`

`:468`의 doc-keeper 경고("`.sample`이 코드보다 오래됐습니다 … 총괄 판단 대기")를 **정정 사실 기술**로 교체. 교체문에는 (a) 제거된 v1 역할/컬럼, (b) 세 역할의 필수 키, (c) `source_region`은 선택·휴면이라 안 쓰면 키를 지우라는 안내, (d) `map_overlay` 폐기 항목 제거와 v2에서의 대체 위치를 담았다. 이어서 **남은 진짜 경고 1건**(§4-A: `table_config.json.sample` 미등록 테이블 문제)을 별도 단락으로 유지했다.

## 3. 검증 실행 결과

라이브 config를 건드리지 않기 위해 `.sample`을 스크래치패드로 복사해 로더에 주입했다.

```
harness: <scratchpad>/verify_sample.py   (conda run -n assy_manager python …)
경로:   .sample → tmp/transfer_plan_config.json → transfer_plan.load_transfer_plan_config(path)
        → transfer_plan._plan_store_statuses(cfg)
테이블: models.init_dynamic_models({map_doe, map_doe_source, map_source_region})  ← 코드 계약에서 구성
```

```
[1] map_overlay_config.json.sample parses OK
    table_bindings keys : ['bonding_log', 'bonding_map', 'dt_log']
    paint_lock keys     : ['*', '__example_bonding_map']

[2] _plan_store_statuses(corrected sample) =
    {"doe": "connected", "doe_source": "connected", "source_region": "connected"}
[2] PASS — doe / doe_source / source_region 전부 non-missing

[3] drop doe.columns.band_seq        -> doe=missing
[3] drop doe_source.columns.source_lot -> doe_source=missing
[3] drop source_region.columns.x     -> source_region=missing
[3] PASS — 네거티브 대조군 전부 missing

[4] PASS — v1 잔재 역할(plan/map/doe_layer)·컬럼(plan_id/layer_from/layer_to/qty_per_unit) 없음

ALL CHECKS PASSED
```

네거티브 대조군([3])을 넣은 이유: `connected`만 찍고 끝내면 "검사가 항상 통과하는 것"과 구분되지 않는다. 필수 키를 하나씩 빼면 즉시 `missing`으로 뒤집히므로 [2]의 PASS가 실효적이다.

회귀: `conda run -n assy_manager python -m pytest server/tests/test_transfer_plan.py -q` → **53 passed**. (테스트는 `.sample`을 읽지 않아 영향은 없으나 계약 무변경 확인 목적.)

폐기 테이블 잔여 참조 전수 Grep(`transfer_plan_map|transfer_plan_doe_layer|"transfer_plan"`, gitignored 사용자 영역 포함): 코드 히트는 `client2/src/map_editor.js:3478`(주석)과 `server/transfer_plan.py`(독스트링)뿐 — **살아있는 의존 없음**.

## 4. 다른 `.sample`에서 관찰된 유사 문제 (보고만 — 수정하지 않음)

### A. [높음 · 이번 수정의 실효를 막는 블로커] `table_config.json.sample`이 최소 세트

`table_config.json.sample`이 선언하는 테이블은 `bonding_map`, `inventory_master`, `production_plan`, `parts`, `wafer_map_metadata` **5개뿐**이다. 바인딩은 `models.DYNAMIC_TABLES`(= `table_config.json`) 조회로 해석되므로(`bonding_plan.py:317`), 다른 `.sample`들이 참조하는 테이블이 여기 없으면 **정정된 샘플조차 `missing`으로 뜬다.**

| `.sample` | 참조 테이블 | `table_config.json.sample`에 존재? |
|---|---|---|
| `transfer_plan_config` | `bonding_map`, `wafer_map_metadata` | 있음 |
| `transfer_plan_config` | `dt_map`, `dt_log`, `core_defect_map`, `eds_fail_map`, `wafer_process`, `map_doe`, `map_doe_source`, `map_source_region` | **없음 (8종)** |
| `bonding_plan_config` | `bonding_log`, `core_defect_map`, `eds_fail_map`, `wafer_process` | **없음 (4종)** |
| `enrichment_rules` | `bonding_log`, `bonding_job_inventory` | **없음 (2종)** |
| `map_overlay_config` | `dt_log`, `bonding_log`, `bonding_map` | `bonding_map`만 있음 |
| `chain_rules` | `inventory_master` | 있음 |

즉 이번 수정은 "샘플이 **코드 계약**과 맞다"까지만 보장한다. **신규 환경 부팅이 실제로 성사되려면 `table_config.json.sample`에 최소한 `map_doe`·`map_doe_source`가 추가돼야 한다.** 이는 스키마 계약(`table_config.json` → `GET /tables/{t}/schema`)이라 **경계 계약 — 총괄 승인 없이 단독 변경하지 않았다.** `map_source_region`은 물리 테이블도 없고 코드 경로도 휴면이므로 등록 여부는 별도 판단 사항이다.

### B. [중간] `source_region`은 선언 즉시 `missing`으로 노출된다

지시대로 바인딩 형태를 넣었으나, `map_source_region`이 `table_config`에 없는 환경에서는 `GET /api/transfer-plan/stages`의 `plan_store.source_region`이 `missing`으로 뜬다. `transfer_plan.py:212` 주석은 **미선언이 결함이 아니라고** 명시하므로, "선언했는데 missing"은 "미선언"보다 신규 사용자에게 시끄럽다. 완화책으로 해당 키에 `__comment`(휴면·미사용 시 키 삭제 안내)를 달았으나, **총괄이 조용한 기본값을 원하면 `source_region` 키를 통째로 빼는 편이 깨끗하다.** 판단 요청.

### C. [낮음] `transfer_plan_config.json.sample`의 `stages` 자체는 손대지 않았다

`stages.dt`/`stages.bonding`이 참조하는 테이블(4-A의 8종 중 다수)도 신규 환경에서는 해석되지 않아 역할 상태가 `missing`이 된다. 다만 지시 범위는 `plan_store`와 폐기 테이블 참조였고, stage 선언 자체는 v1 잔재가 아니라 **정상적인 예시**(사용자가 자기 테이블명으로 바꿔 쓰는 템플릿)이므로 미변경.

### D. [정보] 그 밖의 `.sample`

`auto_update_control` / `ingestion_settings` / `maps` / `ontology_mapping` / `chain_rules`에서는 테이블 참조 기준의 드리프트를 발견하지 못했다. (`ontology_mapping`은 키 구조가 달라 테이블 참조 스캔만 수행 — 전수 정합 감사는 하지 않았다.)

## 5. 인계 요약

- **변경 파일**: `server/config/transfer_plan_config.json.sample`, `server/config/map_overlay_config.json.sample`, `docs/guide/CONFIG_GUIDE.md`
- **검증**: `_plan_store_statuses` 실행 3/3 `connected` + 네거티브 대조군 3/3 `missing`, `test_transfer_plan.py` 53 passed, 폐기 테이블 잔여 참조 전수 Grep 클린
- **미해결(총괄 판단 필요)**: ①`table_config.json.sample`에 `map_doe`·`map_doe_source` 추가 여부(경계 계약) ②`source_region` 바인딩을 샘플에 남길지 여부(§4-B)
- **다음 단계 제안**: ①이 승인되면 같은 작업에서 `table_config.json.sample` 갱신 + 본 검증 하네스를 `server/tests/`에 상설 회귀(샘플 ↔ 코드 계약 드리프트 감지)로 승격
- **히스토리 초안** (총괄이 통합 시 기록): "`.sample` config v1 잔재 정정 — `transfer_plan_config` `plan_store`를 v2 계약(`doe`/`doe_source`/`source_region`)으로 교체, `map_overlay`의 폐기 `transfer_plan_map` 항목 제거, `CONFIG_GUIDE` 경고→정정 교체. 잔여 블로커: `table_config.json.sample` 미등록 테이블."
- **교훈 제안(memory/server-pm.md)**: "`.sample` 정합성은 자기 파일만으로 판정할 수 없다 — 바인딩 샘플은 `table_config.json.sample`에 테이블이 등록돼야 실제로 해석된다. 샘플 수정 시 **참조 테이블의 등록 여부까지 함께 확인**할 것."
