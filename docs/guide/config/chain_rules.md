# `chain_rules.json` 세팅 — 체인 인제션 룰

> **Status:** 🟢 Living | **Last-verified:** 2026-09-05 (§5 키 표에 `source_table`·`allow_chain_trigger`·`allow_map_metadata_upsert` 세 행 추가 — 그중 마지막이 «둘째 엣지»다) · 직전 2026-08-13 (§5 키 표에 **제거 전략 옵트인 둘**(`allow_replace_map`·`allow_retraction`)과 **`*_job_column` 명시 선언** 행 추가 — `4d5198c`. 셋 다 표에 없어서, `dt_map`처럼 맵 키가 둘인 타깃에서 왜 체인이 이름을 대며 거절하는지 이 문서만으로는 알 수 없었다) | **Owner:** Ingester
> 상위: [폴더 인덱스](./README.md) · 동작 원리 정본은 [chain_ingestion_guide](../chain_ingestion_guide.md) · 절차 요약은 [CONFIG_GUIDE §3-S8](../CONFIG_GUIDE.md)

<!-- Loader evidence (2026-07-28):
  worker load: server/chain_ingestion_worker.py:278 load_chain_rules (RULES_PATH :111; missing file -> warning + empty)
    called at startup :787 and re-called on SYSTEM_RELOAD :862; enrichment-derived rules merged :296
  web view reads file per request: server/main.py:3367 (GET /admin/chain/rules :3361, admin-gated)
  mapper cache purge on reload: main.py reload-configs (mappers.* module cache)
-->

## 1. 언제 이 파일을 만지는가

- **테이블 A의 변경이 테이블 B를 자동 갱신하게 만들 때** (trigger→target→mapper 체인)
- 기존 룰을 끄거나(`enabled: false`) 배치/단건 모드를 바꿀 때
- enrichment dedup 투영 룰은 **여기 쓰지 않습니다** — `enrichment_rules.json`에서 자동 파생·병합됩니다

## 2. 세팅 절차

1. **스냅샷**: `conda run -n assy_manager python server/scripts/backup_config.py snapshot`
2. **맵퍼 함수 먼저**: `server/mappers/<module>.py`에 함수를 배치합니다(어드민 Monaco 에디터로 `.py` 편집 가능 — `POST /admin/scripts/code`는 `ASSY_ADMIN_TOKEN` 미설정 시 503).
3. **전제 확인**: `trigger_table`·`target_table`이 `table_config.json`에 선언돼 있어야 합니다.
   🔴 **`allow_map_metadata_upsert`를 쓸 룰이면 표가 «셋»입니다** — 그 룰은 맵 메타데이터 표
   (`wafer_map_metadata`)에도 쓰고, 그 쓰기가 **자기 체인 이벤트를 냅니다.** 즉 그 표를
   `trigger_table`로 삼는 룰이 깨어나므로 **순환 검사의 꼭짓점**이기도 합니다(§5 표 참조).
4. 파일이 없으면 `chain_rules.json.sample` 복사. `rules[]` 배열에 항목 추가:

   ```json
   {
     "name": "production_to_inventory_reservation_batch",
     "trigger_table": "production_plan",
     "target_table": "inventory_master",
     "mapper_module": "mappers.production_mapper",
     "mapper_function": "reserve_materials_batch_df",
     "is_batch": true,
     "enabled": true
   }
   ```
5. 저장 후 **리로드가 필수**입니다 — 워커는 기동 시 + SYSTEM_RELOAD 시에만 룰을 다시 읽습니다:

   ```bash
   curl -X POST "http://<host>:8080/admin/reload-configs" -H "X-Admin-Token: <토큰>"
   ```

   (`mappers.*` 모듈 캐시도 함께 퍼지되므로 맵퍼 코드 수정도 이걸로 반영됩니다.)

## 3. 반영 확인

1. `GET /admin/chain/rules` (`X-Admin-Token` 필요) — 룰이 보이는지. ⚠️ 이 뷰는 **파일을 요청마다 직접 읽으므로** 리로드 전에도 보입니다 — 워커 반영의 증거가 아닙니다.
2. **워커 반영의 증거는 체인 워커 로그**: 리로드 후 룰 재로드/enrichment 병합 로그(`[Enrichment] Synthesized ...` 등)가 새로 찍히는지.
3. `GET /admin/mappers/list` — 맵퍼 모듈·함수가 열거되는지.
4. 왕복 검증: trigger 테이블에 행을 넣어 target 테이블이 갱신되는지 + `GET /admin/outbox/failed`에 실패가 쌓이지 않는지.

## 4. 잘못됐을 때

```bash
conda run -n assy_manager python server/scripts/backup_config.py restore chain_rules_<yymmdd>.json.bak --yes
```

복원 후 **다시 `reload-configs`** (워커가 옛 룰로 돌아가야 하므로). 이미 잘못 전파된 target 데이터는 룰 복원으로 돌아오지 않습니다 → [ROLLBACK_PROCEDURE](../ROLLBACK_PROCEDURE.md).

## 5. 키 참조 (`rules[]` 항목)

| 키 | 의미 |
|---|---|
| `name` | 룰 식별자(로그·관리 화면 표기) |
| `trigger_table` | 이 테이블의 변경이 체인을 발화. 🔴 **순환 검사 그래프의 «엣지 출발점»이 이 칸이다** |
| `target_table` | 맵퍼가 갱신할 테이블. 그래프의 «엣지 도착점» |
| `source_table` | 🔴 **맵퍼가 데이터를 «읽는» 표 — 엣지가 «아니다».** `trigger_table`과 뜻이 겹쳐 보여 바꿔 읽기 쉽고, 바꿔 읽으면 그래프를 틀리게 그린다 |
| `mapper_module` / `mapper_function` | `server/mappers/` 하위 모듈 경로와 함수명 |
| `is_batch` | `true` = 배치(DataFrame) 모드 |
| `enabled` | `false`면 룰 비활성. **생략하면 켜짐.** 꺼진 룰은 순환 검사 그래프에 **안 들어간다** |
| `allow_chain_trigger` | 체인이 만든 이벤트(`source_name: "chain_ingestion"`)를 이 룰이 **받겠다는 옵트인.** 선언 없으면 그런 이벤트는 그냥 지나간다. 🔴 **로드 시점 순환 검사가 보는 것은 «이 옵트인이 걸린 엣지»뿐이다** |
| `allow_map_metadata_upsert` | 맵퍼가 **맵 메타데이터 봉투**(`map_metadata_updates`)를 낼 수 있게 하는 옵트인. 🔴 **[2026-09-04] 이 칸이 곧 «두 번째 엣지»다** — 그 쓰기는 `wafer_map_metadata`에 착지하고 **자기 체인 이벤트를 낸다.** 종전 순환 검사가 이 엣지를 못 봐서 **살아 있는 순환이 통과**했다 → [chain_ingestion_guide 「Target-map metadata within a chain」](../chain_ingestion_guide.md) |
| `allow_replace_map` | 맵퍼가 **맵 단위 전량 교체** 봉투를 낼 수 있게 하는 옵트인. 선언 없이 그 봉투를 내면 워커가 거부한다 |
| `allow_retraction` | (2026-08-13 `4d5198c`) 맵퍼가 **출처 단위 철회** 봉투(`retract`)를 낼 수 있게 하는 옵트인. 🔴 **한 배치에 `replace_map`과 `retract`을 함께 실으면 거부된다** — purge가 먼저 돌면 형제 출처의 셀을 구할 기회가 없다. 어느 쪽을 쓸지는 취향이 아니라 **그 맵의 생산자가 하나인가 여럿인가**가 정한다 → [chain_ingestion_guide](../chain_ingestion_guide.md) |
| `*_job_column` (`trigger_`/`source_`/`target_`/`inventory_`) | 잡 컬럼 이름의 **명시 선언**. 미선언이면 `table_config`에서 유도한다. 🔴 **유도는 「한 컬럼짜리 `map_key_columns`」에 기대므로, `map_key_columns`가 둘 이상인 타깃은 반드시 선언해야 한다** — `dt_map`이 2026-08-13에 그 상태가 됐고 `dt_inventory_to_standard_dt_map`은 `target_job_column`을 선언한다 → [DT_CORE_FRAME_CHAINS_GUIDE §1-bis](../DT_CORE_FRAME_CHAINS_GUIDE.md) |
