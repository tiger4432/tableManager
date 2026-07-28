# `enrichment_rules.json` 세팅 — 결손 보정 워크리스트 규칙

> **Status:** 🟢 Living | **Last-verified:** 2026-07-28 | **Owner:** 총괄
> 상위: [폴더 인덱스](./README.md) · 스펙 정본은 [ENRICHMENT_QUEUE_SPEC](../../spec/ENRICHMENT_QUEUE_SPEC.md) · 절차 요약은 [CONFIG_GUIDE §3-S7](../CONFIG_GUIDE.md)

<!-- Loader evidence (2026-07-28):
  load/validate: server/enrichment_config.py:250 load_enrichment_rules (missing -> []),
    :231 validate (root must be object), key schema docstring :11-32,
    table registration check :179-182, key contract (composite_key_source subset / business_key in decision_key) :30-32
  chain synthesis: enrichment_config.py:264 -> merged in chain_ingestion_worker.py:296
    (log "[Enrichment] Synthesized N dedup chain rule(s)"; reload on SYSTEM_RELOAD)
  ontology promotion: server/ontology_config.py:218 (RESOLVED_AS)
  web query API per-request: server/main.py:3442
  query_ref dir: enrichment_config.py:43 config/enrichment_queries/<ref>.sql (dir absent by default)
-->

## 1. 언제 이 파일을 만지는가

- **대량 원본 테이블의 결손 필드(사람이 판단해 채우는 값)를 워크리스트로 만들 때** — 규칙 하나가 ① 워크리스트/참조뷰 API ② 체인 dedup 투영(판단키당 1행 upsert) ③ 온톨로지 `RESOLVED_AS` 승격을 동시에 켭니다
- 판단에 참고할 **참조뷰(SQL)** 를 추가/수정할 때

## 2. 세팅 절차

1. **스냅샷**: `conda run -n assy_manager python server/scripts/backup_config.py snapshot`
2. **전제 확인**: `source_table`·`derived_table` 모두 `table_config.json`에 선언돼 있어야 하고, `derived_table`은 **키 계약** — `composite_key_source ⊆ decision_key` 또는 `business_key ∈ decision_key` — 을 만족해야 합니다(위반 시 그 규칙만 조용히 스킵).
3. 파일이 없으면 `enrichment_rules.json.sample` 복사. 루트는 `{규칙명: 규칙}` 객체. 규칙 추가:

   ```json
   "core_wafer_attribution": {
     "source_table": "bonding_log",
     "derived_table": "core_wafer_map",
     "decision_key": ["core_lot", "core_slot"],
     "target_fields": ["wafer_id"],
     "list_columns": ["chip_count"],
     "aggregations": { "chip_count": "count" },
     "enabled": true,
     "reference_views": [
       {
         "label": "lot-slot 웨이퍼 이력",
         "query": "SELECT step, lot, slot, wafer_id, event_time FROM wafer_slot_history WHERE lot = :core_lot AND slot = :core_slot ORDER BY event_time DESC",
         "limit": 200
       }
     ]
   }
   ```

   참조뷰의 `:바인딩`은 **`decision_key` 컬럼만** 허용됩니다. 긴 SQL은 `query_ref`로 `server/config/enrichment_queries/<ref>.sql`에 뺄 수 있습니다(폴더는 직접 생성).
4. 저장 후 **리로드**(체인 파생 + 온톨로지 승격에 필수 — 조회 API만은 리로드 없이도 즉시):

   ```bash
   curl -X POST "http://<host>:8080/admin/reload-configs" -H "X-Admin-Token: <토큰>"
   ```

## 3. 반영 확인

1. `GET /enrichment/rules` — 규칙이 공개 메타에 뜨는지 (여긴 **요청마다 재읽기**라 리로드 전에도 보입니다 — 이것만 보고 파생까지 됐다고 판단하지 마십시오).
2. **체인 워커 로그**에서 파생 확인: `[Enrichment] Synthesized N dedup chain rule(s) from enrichment_rules.json` — 리로드 후 N이 기대만큼 늘었는지.
3. 참조뷰 실행: `GET /enrichment/rules/{name}/references/{index}?params=...`.
4. 원본 테이블에 새 행을 넣어 `derived_table`에 판단키당 1행이 생기는지 왕복 확인.

## 4. 잘못됐을 때

```bash
conda run -n assy_manager python server/scripts/backup_config.py restore enrichment_rules_<yymmdd>.json.bak --yes
```

복원 후 **다시 `reload-configs`** (체인 파생 룰이 옛 상태로 돌아가야 하므로) → [ROLLBACK_PROCEDURE](../ROLLBACK_PROCEDURE.md).

## 5. 키 참조 (`{규칙명: 규칙}`)

| 키 | 필수 | 의미 |
|---|---|---|
| `source_table` | ✔ | 대량 원본 테이블 (`table_config` 등록 필수) |
| `derived_table` | ✔ | 파생 영속 테이블 (등록 + 키 계약 필수) |
| `decision_key` | ✔ | 판단키 컬럼 1..N |
| `target_fields` | ✔ | 사람이 채울 필드 |
| `list_columns` | | 워크리스트 표시 단서 |
| `aggregations` | | 서버 전용 집계 — v1은 `"count"`만 |
| `enabled` | | 기본 `true` |
| `reference_views[]` | | `{label, query, limit}` 또는 `{label, query_ref}` — `query`는 서버에만 존재(클라엔 `label`만), `limit` 기본 200 · 최대 1000 |

- 거부는 규칙 단위 + 조용함 — 워크리스트가 조용히 비면 로그의 검증 에러부터.
- `RESOLVED_AS`를 온톨로지에 중복 선언하지 마십시오(자동 승격).
