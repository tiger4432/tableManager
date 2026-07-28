# `enrichment_rules.json` 세팅 — 결손 보정 워크리스트 규칙

> **Status:** 🟢 Living | **Last-verified:** 2026-07-28 | **Owner:** 총괄
> 상위: [폴더 인덱스](./README.md) · 스펙 정본은 [ENRICHMENT_QUEUE_SPEC](../../spec/ENRICHMENT_QUEUE_SPEC.md) · 절차 요약은 [CONFIG_GUIDE §3-S7](../CONFIG_GUIDE.md)

<!-- Loader evidence (2026-07-28):
  load/validate: server/enrichment_config.py:250 load_enrichment_rules (missing -> []),
    :231 validate (root must be object), key schema docstring :11-32,
    table registration check :179-182, key contract (composite_key_source subset / business_key in decision_key) :30-32
  decision_key contract (re-measured 2026-07-28):
    both-sides same-name existence check :183-190 (src :185-187, drv :188-190; against table_config column_types),
    no column-name mapping anywhere in loader (membership check only),
    decision_key/target_fields overlap :157-159,
    addressability code :202-216 (composite_key_source branch :205-211, business_key elif :212-216),
    reference view SQL/bind validation :81-100 (bind error :96-99), view drop log :123 (view-level, rule survives),
    rule skip log format :243 "[Enrichment:{name}] rule skipped: {err}"
  chain synthesis: enrichment_config.py:264 -> merged in chain_ingestion_worker.py:296
    (log "[Enrichment] Synthesized N dedup chain rule(s)"; reload on SYSTEM_RELOAD)
  ontology promotion: server/ontology_config.py:218 (RESOLVED_AS)
  web query API per-request: server/main.py:3442
  query_ref dir: enrichment_config.py:43 config/enrichment_queries/<ref>.sql (dir absent by default)
  worked example source: server/config/enrichment_rules.json.sample (bonding_wafer_attribution)
-->

## 1. 언제 이 파일을 만지는가

- **대량 원본 테이블의 결손 필드(사람이 판단해 채우는 값)를 워크리스트로 만들 때** — 규칙 하나가 ① 워크리스트/참조뷰 API ② 체인 dedup 투영(판단키당 1행 upsert) ③ 온톨로지 `RESOLVED_AS` 승격을 동시에 켭니다
- 판단에 참고할 **참조뷰(SQL)** 를 추가/수정할 때

## 2. `decision_key` 계약 — source와 derived에서 같아야 하는가?

**예, 완전히 같아야 합니다.** 규칙 하나에 `decision_key`는 컬럼명 목록 **하나**뿐이고, 그 목록의 모든 컬럼이 `source_table`과 `derived_table` **양쪽에 같은 이름으로** 존재해야 합니다(`table_config.json`의 `column_types` 선언 기준, `enrichment_config.py:185-190`). 소스 `eqp_id` ↔ 파생 `equipment` 같은 **이름 매핑 기능은 없습니다.**

**실무 처방**: 소스 테이블 컬럼명은 인제션 스키마라 바꾸기 어렵지만, **파생 테이블은 사이트가 `table_config.json`에 직접 선언하는 테이블**입니다. 파생 테이블을 만들 때 판단키 컬럼명을 **소스 쪽에 맞춰** 지으십시오 — 반대 방향(규칙에서 이름을 바꿔치기)은 존재하지 않습니다.

위반한 규칙은 **조용히 스킵**되고 서버 로그에만 남습니다. 워크리스트가 비면 이 형식으로 grep:

```
[Enrichment:<규칙명>] rule skipped: <사유>
```

계약은 네 가지입니다:

| # | 계약 | 위반 시 `rule skipped:` 뒤에 오는 사유 |
|---|---|---|
| ① | `decision_key` 모든 컬럼이 **소스에** 존재 | `decision_key column(s) missing in source table: [...]` |
| ① | `decision_key` 모든 컬럼이 **파생에** 존재 (같은 이름) | `decision_key column(s) missing in derived table: [...]` |
| ② | `decision_key` ∩ `target_fields` = ∅ (`:157-159`) | `decision_key and target_fields must not overlap: [...]` |
| ③ | `composite_key_source ⊆ decision_key` **또는** `business_key ∈ decision_key` (`:30-32`, `:202-216`) | `derived table composite_key_source must be a subset of decision_key (violation: [...])` 또는 `derived table must declare composite_key_source ⊆ decision_key or business_key ∈ decision_key (dedup upsert key contract)` |
| ④ | 참조뷰 `:바인딩`은 `decision_key` 컬럼만 (`:81-100`) | *(규칙이 아니라 그 뷰만 제거)* `reference view '<label>' dropped: bind params must be decision_key columns only; invalid: [...]` |

- **② 왜**: `target_fields`는 사람이 앞으로 채울 결손 필드입니다. 판단 시점에 비어 있는 값이 판단 근거(키)일 수는 없습니다.
- **③ 왜**: 판단 1건은 파생 행 **정확히 1개**에 내려앉아야 합니다. dedup mapper는 `decision_key` 값만으로 파생 행의 `business_key_val`을 결정론적으로 조립해 upsert하는데, 파생 테이블의 키가 `decision_key` 밖 컬럼을 요구하면 판단이 자기 행을 주소지정할 수 없습니다 — 어느 행을 갱신할지 정할 수 없는 판단이 됩니다.
- **④ 주의**: ④만 규칙 전체가 아니라 **해당 뷰 하나만** 탈락합니다(`view ... dropped`, 규칙과 나머지 뷰는 생존). 로그 키워드가 `rule skipped`가 아니라 `dropped`입니다.

### 예제 (`.sample`의 `bonding_wafer_attribution`)

`decision_key: ["equipment", "event_time"]`, 소스 `bonding_log` → 파생 `bonding_job_inventory`:

| 컬럼 | `bonding_log` (소스) | `bonding_job_inventory` (파생) |
|---|---|---|
| `equipment` | ✔ 필요 (①) | ✔ 필요 (①) — 같은 이름 |
| `event_time` | ✔ 필요 (①) | ✔ 필요 (①) — 같은 이름 |
| `wafer_id` (target) | — | ✔ 필요, 단 판단키엔 못 넣음 (②) |
| `chip_count`, `lot_hint` (list_columns) | — | 있으면 표시, 없으면 그 컬럼만 경고 후 제외 |
| 키 선언 | — | `composite_key_source`가 `["equipment","event_time"]`(부분집합) 등 (③) |

**틀린 버전**: 소스가 컬럼을 `eqp_id`로 선언하고 파생만 `equipment`라면 — 규칙 전체가 스킵되고 정확히 이 로그가 남습니다:

```
[Enrichment:bonding_wafer_attribution] rule skipped: decision_key column(s) missing in source table: ['equipment']
```

고치는 방향은 하나입니다: 파생 테이블 컬럼을 `eqp_id`로 다시 선언하고 `decision_key: ["eqp_id", "event_time"]`로 — 규칙에서 이름을 매핑할 수는 없습니다.

## 3. 세팅 절차

1. **스냅샷**: `conda run -n assy_manager python server/scripts/backup_config.py snapshot`
2. **전제 확인**: `source_table`·`derived_table` 모두 `table_config.json`에 선언돼 있어야 하고, `decision_key`·키 계약은 **§2** 를 만족해야 합니다(위반 시 그 규칙만 조용히 스킵).
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

   참조뷰의 `:바인딩`은 **`decision_key` 컬럼만** 허용됩니다(§2-④). 긴 SQL은 `query_ref`로 `server/config/enrichment_queries/<ref>.sql`에 뺄 수 있습니다(폴더는 직접 생성).
4. 저장 후 **리로드**(체인 파생 + 온톨로지 승격에 필수 — 조회 API만은 리로드 없이도 즉시):

   ```bash
   curl -X POST "http://<host>:8080/admin/reload-configs" -H "X-Admin-Token: <토큰>"
   ```

## 3-bis. 큐 진입 조건 — 빈 판단키 행은 큐에 노출되지 않는다

워크리스트·어드민 결손 카운트·메인 그리드 배지는 모두 서버가 `/enrichment/rules` 응답에 조성해 주는 **`queue_filters`**(모든 `target_fields` blank **AND** 모든 `decision_key` notBlank) 하나를 사용합니다 (`enrichment_config.to_public_rule`). 판단키가 빈 행은 사람이 해소할 수 없으므로 큐에서 제외됩니다 — 세 소비처의 수치가 항상 일치합니다. 체인 mapper와 백필은 빈 판단키 조합을 애초에 만들지 않지만(스킵·집계), 그리드 빈 행 추가나 판단키 없는 직접 편집으로 생긴 행은 이 필터가 표시에서 걸러냅니다(데이터는 삭제하지 않음 — 테이블 원본 그리드에서는 그대로 보입니다).

## 4. 반영 확인

1. `GET /enrichment/rules` — 규칙이 공개 메타에 뜨는지 (여긴 **요청마다 재읽기**라 리로드 전에도 보입니다 — 이것만 보고 파생까지 됐다고 판단하지 마십시오).
2. **체인 워커 로그**에서 파생 확인: `[Enrichment] Synthesized N dedup chain rule(s) from enrichment_rules.json` — 리로드 후 N이 기대만큼 늘었는지.
3. 참조뷰 실행: `GET /enrichment/rules/{name}/references/{index}?params=...`.
4. 원본 테이블에 새 행을 넣어 `derived_table`에 판단키당 1행이 생기는지 왕복 확인.

## 4-bis. 소급 적용 (백필) — 규칙보다 먼저 들어온 원본 행

인리치먼트는 **증분(outbox) 구동**입니다. 규칙을 선언하기 **전에** 인제션된 원본 행은 이벤트가 다시 발생하지 않는 한 파생 행을 만들지 않습니다 — 워크리스트에는 영원히 안 잡힙니다. 역할 분담은 이렇습니다:

- **값 결손**(파생 행은 있는데 target이 빈 것) → **큐(워크리스트)** 의 일. 백필은 절대 기존 파생 행을 건드리지 않습니다.
- **행 부재**(판단키 조합 자체가 파생에 없는 것) → **백필 스크립트**의 일.

```bash
# 1) 반드시 dry-run 먼저 — 아무것도 쓰지 않고 수치만 보고
conda run -n assy_manager python server/scripts/backfill_enrichment.py <규칙명>

# 2) 보고 수치(new)가 기대와 맞으면 적용. 첫 운영 실행은 --limit로 소량 검증 권장
conda run -n assy_manager python server/scripts/backfill_enrichment.py <규칙명> --apply --limit 100
conda run -n assy_manager python server/scripts/backfill_enrichment.py <규칙명> --apply
```

- dry-run 보고: 스캔 행수 · blank 판단키 스킵수 · 유니크 조합수 · 기존 파생(불가침) · 신규(생성 예정).
- 실행 경로는 체인과 **완전히 동일**합니다(실제 mapper `map_enrichment_dedup` + `crud.apply_batch_updates`) — 그룹핑/집계/키 조립의 별도 구현이 없습니다. `target_fields`는 절대 쓰지 않고 빈 채로 생성되어 워크리스트에 잡힙니다.
- 생성 셀의 소스명은 `enrichment_backfill`(우선순위 99) — 사용자 편집(0)을 절대 이길 수 없고, 이후 체인 증분(`chain_ingestion`, 4)이 집계·단서를 자연히 갱신합니다.
- outbox를 정상 경로로 발화하므로 그래프 워커가 새 행을 그대로 승격합니다. 파생 테이블 이벤트는 규칙의 트리거(소스 테이블)와 다르므로 같은 규칙을 재점화하지 않습니다.
- 멱등: 적용 후 재실행하면 `new 0`. 비활성(`enabled: false`) 규칙은 `--force-disabled` 없이 거부되고, 로더가 거부한 규칙은 그 사유와 함께 즉시 실패합니다.

## 5. 잘못됐을 때

```bash
conda run -n assy_manager python server/scripts/backup_config.py restore enrichment_rules_<yymmdd>.json.bak --yes
```

복원 후 **다시 `reload-configs`** (체인 파생 룰이 옛 상태로 돌아가야 하므로) → [ROLLBACK_PROCEDURE](../ROLLBACK_PROCEDURE.md).

## 6. 키 참조 (`{규칙명: 규칙}`)

| 키 | 필수 | 의미 |
|---|---|---|
| `source_table` | ✔ | 대량 원본 테이블 (`table_config` 등록 필수) |
| `derived_table` | ✔ | 파생 영속 테이블 (등록 + 키 계약 필수) |
| `decision_key` | ✔ | 판단키 컬럼 1..N — 소스·파생 **양쪽에 같은 이름으로** 존재 (§2) |
| `target_fields` | ✔ | 사람이 채울 필드 |
| `list_columns` | | 워크리스트 표시 단서 |
| `aggregations` | | 서버 전용 집계 — v1은 `"count"`만 |
| `enabled` | | 기본 `true` |
| `reference_views[]` | | `{label, query, limit}` 또는 `{label, query_ref}` — `query`는 서버에만 존재(클라엔 `label`만), `limit` 기본 200 · 최대 1000 |

- 거부는 규칙 단위 + 조용함 — 워크리스트가 조용히 비면 로그의 검증 에러부터.
- `RESOLVED_AS`를 온톨로지에 중복 선언하지 마십시오(자동 승격).
