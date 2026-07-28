# `transfer_plan_config.json` 세팅 — M2 Universal Transfer Plan

> **Status:** 🟢 Living | **Last-verified:** 2026-07-28 | **Owner:** Backend / UI-Map
> 상위: [폴더 인덱스](./README.md) · **의미론(zone 모델·`stack` string·`bin_map`·`bands` 폐기)의 정본은 [CONFIG_GUIDE §5.8](../CONFIG_GUIDE.md)** · 동작 계약은 [MAP_EDITOR_SPEC §6](../../spec/MAP_EDITOR_SPEC.md)

<!-- Loader evidence (2026-07-28):
  load: server/transfer_plan.py:232 load_transfer_plan_config (missing/corrupt -> {})
  per-request snapshot: server/main.py:3189
  registry required roles: transfer_plan.py:146 REGISTRY_ROLES = (ref_table, map_key, value, stack, mat_1h, mat_mid, mat_top)
  source_config_ref allowed: transfer_plan.py:127 M1_SOURCE_REFS = ("bonding_plan",)
  stage role resolution: transfer_plan.py:282 / bin_map lookup: :661 / lot_membership: :921
  material_identity gate: transfer_plan.py:2486 / source_region (dormant): :487
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

1. `GET /api/transfer-plan/stages` — 새 stage가 목록에 뜨고 `roles`·`plan_store`가 **`connected`** 인지 (`registry`가 `missing`이면 역할키 7종·테이블 선언부터 재확인).
2. `GET /api/transfer-plan/validate?ref_table=<t>&map_key=<k>` — **404면 `plan_store.registry` 역할키 누락**입니다(zone 역할 7종 중 하나라도 빠지면 404 — 조용히 통과시키지 않는 설계).
3. BIN 축을 켰다면 `GET /api/transfer-plan/source-summary?...&bins=...` — `bins.axis: "connected"` 확인 (`unavailable`이면 미선언 또는 M1 위임 stage).
4. 맵 에디터에서 그 `target_map.table`의 맵을 열면 stage가 유도됩니다 — 어느 stage에도 없는 맵은 `stage_unknown` 경고 + `unverified`(404 아님).

## 4. 잘못됐을 때

```bash
conda run -n assy_manager python server/scripts/backup_config.py restore transfer_plan_config_<yymmdd>.json.bak --yes
```

요청마다 재읽으므로 복원 즉시 반영. 단 **`table_config`·물리 컬럼과 얽힌 문제**(zone 컬럼 미선언으로 저장이 드롭된 경우 등)는 config 복원만으로 안 돌아옵니다 → [ROLLBACK_PROCEDURE](../ROLLBACK_PROCEDURE.md).

## 5. 키 참조

**`stages.<stage명>`**: `description`(필수) · `source_kind`/`target_kind` · `source_config_ref`(`"bonding_plan"`) 또는 `source` · `target_map: {preset, table}`(stage 유도의 역인덱스) · `bin_map`(선택)

**`stages.<stage>.source` 역할**: `identity.compose` · `map_metadata` · `total_chips` · `transfer_log` · `origin_log` · `origin_area_map` · `process_history` · `fail_sources.<name>{frame: "origin"|"self", table, columns, fail_values}` · `warnings` · `bin_map`(선택) · `lot_membership`(선택 — 미선언 시 BIN 맵 슬롯으로 강등 폴백 + `lot_membership_degraded`) — 각 바인딩은 `{table, columns}` 형태, 위반 시 그 역할 `missing`.

**`plan_store`**: `registry`(필수 역할키 7종 `ref_table`·`map_key`·`value`·`stack`·`mat_1h`·`mat_mid`·`mat_top`, 🗄️ `bands`는 선택·읽기 전용) · `material_identity{compose, separator}`(게이트 전용 — 미선언 시 전 자재 `source_unresolved`) · `source_region`(선택·휴면).

주의 —

- `map_split_registry.stack`은 `table_config`에서 **`"string"`** 선언(“number”로 바꾸면 저장 실패/조용한 변조).
- `fail_sources[].align`은 폐지 — 무시됨. 변환은 `wafer_map_metadata` 델타에서 유도.
- `origin_area_map`의 `val`을 `bin_map`에 재사용 금지 — 출신 코어 식별자일 수 있어 서버는 BIN 컬럼을 추측하지 않습니다.
- zone·마커 0·V1~V6·`bands` 이관의 전체 의미론은 [CONFIG_GUIDE §5.8](../CONFIG_GUIDE.md)이 정본.
