# `enrichment_rules.json` 세팅 — 결손 보정 워크리스트 규칙

> **Status:** 🟢 Living | **Last-verified:** 2026-07-30 (**①** `candidate_for` + `auto_confirm` 신설 — §7) | **Owner:** 총괄
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
- **후보가 1개인 항목의 확인 클릭을 없앨 때** — 참조뷰에 `candidate_for`를 선언하고 규칙에 `auto_confirm`을 켭니다(§7)

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
| `auto_confirm` | | **기본 `false`** — 후보가 1개일 때 사람 없이 자동 확정(§7) |
| `reference_views[]` | | `{label, query, limit}` 또는 `{label, query_ref}` — `query`는 서버에만 존재(클라엔 `label`만), `limit` 기본 200 · 최대 1000 |
| `reference_views[].candidate_for` | | `{target_field: 뷰 결과 컬럼}` — 이 뷰의 어느 컬럼이 어느 target의 **후보값**인지 선언(§7). 없으면 그 뷰는 **표시 전용** |

- 거부는 규칙 단위 + 조용함 — 워크리스트가 조용히 비면 로그의 검증 에러부터.
- `RESOLVED_AS`를 온톨로지에 중복 선언하지 마십시오(자동 승격).

## 7. `candidate_for` + `auto_confirm` — 후보가 1개면 판단이 아니라 확인 (2026-07-30, ①)

참조뷰 결과가 **유일한 값 하나**면 사람은 판단하는 게 아니라 **확인**하는 중입니다. 그 확인을 없애는 두 개의 키입니다.

```jsonc
"reference_views": [
  { "label": "lot-slot 웨이퍼 이력",
    "query": "SELECT ... FROM wafer_slot_history WHERE lot = :core_lot AND slot = :core_slot",
    "candidate_for": { "wafer_id": "wafer_id" } },      // ← 이 뷰의 wafer_id 컬럼이 target wafer_id의 후보
  { "label": "같은 lot 전체 슬롯",
    "query": "SELECT ... WHERE lot = :core_lot" }        // ← 선언 없음 = 표시 전용 (후보 아님)
],
"auto_confirm": true                                     // ← 없으면 false (제안만, 쓰지 않음)
```

### 7.1 왜 컬럼명으로 유추하지 않는가 (선언만 인정)

**위 두 뷰는 둘 다 `wafer_id` 컬럼을 가집니다.** 하지만 첫 번째는 lot+slot으로 조회해 후보가 1개, 두 번째는 lot만으로 조회해 **후보가 N개**입니다. 컬럼명이 같다고 후보로 쓰는 구현은 두 번째 뷰까지 후보로 삼아 **그레인 사고로 고른 값을 자동 확정**합니다. 맵 오버레이의 `derive_table_binding`이 첫 데이터 컬럼을 추측해 DECOY를 붙인 것이 라이브에서 실증된 뒤로, 이 시스템에서 바인딩은 **선언만** 인정합니다.

### 7.2 거절은 전부 이름이 있습니다 (무응답 금지)

| 사유 | 뜻 | 결과 |
|---|---|---|
| `not_declared` | 그 target에 `candidate_for`를 선언한 뷰가 없다 | 큐에 남음 |
| `no_candidate` | 선언된 뷰가 돌았지만 비어 있지 않은 값이 없다 | 큐에 남음 |
| `ambiguous` | 서로 다른 값이 2개 이상 — **이게 바로 사람의 판단** | 큐에 남음 |
| `view_error` · `missing_bind` · `candidate_column_missing` | 선언된 뷰를 **평가하지 못했다** | 큐에 남음 |
| `cell_has_provenance` | 그 셀에 이미 어떤 소스든 기록이 있다 | 건드리지 않음 |
| `over_cap` | 작업 단위 상한 초과 | 큐에 남음(다음 인제션이 처리) |

⚠️ **평가하지 못한 뷰는 "값 없음"이 아니라 "모름"입니다.** 선언된 뷰 중 하나라도 실패하면, 살아남은 뷰가 값 1개를 냈더라도 **거절**합니다(실패한 뷰가 모순값을 갖고 있었을 수 있음). 미해결 행은 **눈에 보이게 미해결로 남습니다.**

### 7.3 `auto_confirm`을 켜기 전에 (기본이 OFF인 이유)

M3의 `auto_register_map_meta`와 **같은 형태**입니다 — 부재 시에만 쓰고, 소스 `enrichment_auto_confirm`은 `SOURCE_PRIORITY` **미등재 = 최하위(99)** 라 사람 편집(priority 0)이 항상 이깁니다. 다른 점은 **기본값뿐**이며, 그 근거는:

- 이 값은 **큐 소속을 정의하는 필드**입니다(`queue_filters`: target blank). 자동 확정이 틀리면 그 항목은 워크리스트에서 **빠져서 다시 검토되지 않습니다.**
- **철회 경로가 부분적입니다** — R2(stale 소스 철회, 2026-07-30 착지)로 `enrichment_auto_confirm` 레이어를 되돌릴 수 있지만, 되돌린 뒤 그 셀은 provenance가 남아 재확정되지 않습니다.

그래서 켜는 것은 **명시적 옵트인**입니다. 켠 뒤 무엇이 자동 확정됐는지는 셀의 `priority_source`(= `enrichment_auto_confirm`)와 AuditLog로 확인합니다.

⚠️ **표기 통일을 먼저 확인하십시오.** 여러 뷰를 선언하면 자동 확정은 **데이터가 있는 뷰의 표기를 그대로 채택**합니다. 2026-07-30 실측: `wafer_slot_history`는 `WF-C-21`(단축형) 7행, `wafer_process`는 `WF-LOT-C-21`(전체형) 10,372행으로 **같은 (lot, slot)에 두 표기가 공존**하고, 사람이 채운 `core_wafer_map` 11행에도 두 표기가 섞여 있었습니다. 표기가 섞인 상태로 켜면 자동 확정이 한쪽 표기를 조용히 표준화합니다.

### 7.4 켜기 전에 재보기 — 쓰지 않고 측정

```bash
# 지금 큐에서 몇 건이 사람 없이 해소되는가 (아무것도 쓰지 않음)
conda run -n assy_manager python server/scripts/enrichment_insights.py confirm <규칙> --ignore-knob
# 결손의 원인 분류: 파이프라인 버그 / 기계로 해소 가능 / 진짜 사람 일감
conda run -n assy_manager python server/scripts/enrichment_insights.py classify <규칙>
# 반복된 사람 판단이 규칙이 됐는지 — 제안만, 절대 config를 쓰지 않음
conda run -n assy_manager python server/scripts/enrichment_insights.py propose <규칙> --min-support 3
```

기존 큐(체인 훅은 신규 쓰기만 봅니다)에 소급 적용하려면 `confirm <규칙> --apply` — 단 규칙의 `auto_confirm`이 `true`여야 합니다(노브가 곧 동의입니다).
