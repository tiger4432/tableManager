# 📖 체인 인제션 DB 세션 활용 데이터 조회 및 계산 가이드

> **Status:** 🟢 Living | **Last-verified:** 2026-08-11 (**§5.6 신설 — 「측정하지 않았다」가 닫혔고, 세 연산 중 *둘*이 같은 결함이었다**(`ffb23d6` R3 · `53f9187` R2). 소급 패스는 아웃박스 이벤트를 **낸다**(변경 *행*마다 `EDIT` 하나 — 셀마다 아님, `--chunk-size`는 커밋·NOTIFY만 움직인다). 🔴 **결함은 개수가 아니라 라벨**이었다: `user`/`system`+이벤트마다 uuid4로 나가 사람의 그리드 편집과 구별되지 않아 하류 매퍼 전원이 깨어났다. 지금은 둘 다 `chain_ingestion` 라벨 + 실행당 tx id 하나이고 🔴 **억제가 아니라 옵트인**이다. 🔴 **라벨(`request_source`)과 층(`update_item.source_name`)은 다른 필드**이고, R2에서는 **삭제 술어**가 파라미터로 짜여 라벨과 경로가 없다는 것을 생존 집합 sha256으로 확인했다. 🔴 **R2의 WS 프레임 4→0은 손실이 아니다** — 클라는 실제로 바뀐 셀을 전후 어느 쪽에서도 못 듣고 있었고, 없어진 것은 엉뚱한 캐스케이드 통지다. ⚠️ **R1은 라벨이 구성상 옳지만 tx id가 *페이지당* 하나로 남아 있다**(같은 비용의 약한 형태 — 미수리). §1 매퍼 계약 절과 쓰기 능력 표에 **R3 행 + 라벨=채널 규율**을 함께 실었다. 직전 **§5.5 신설 — Chain Replay에 세 번째 연산 R3(`resolve`)가 들어왔다.** 저장된 층을 하나도 바꾸지 않고 **「그중 무엇이 이기는가」만 다시 답해** materialise된 표시 컬럼을 고친다 — R1(매퍼 재실행·새 층 쓰기)도 R2(주장 삭제)도 답할 수 없던 질문이다. 층이 2개 미만인 셀은 **구조적으로** 손대지 않고(0개면 컬럼을 비워 버린다), 값이 움직인 셀마다 `resolution_recompute` 감사 행이 남는다(**CLI 전용** — 어드민 소급 등록부에 없다). ✅ ~~**「아웃박스 이벤트를 안 낸다」는 문장은 일부러 적지 않았다** — 전역 `before_flush`가 dirty 행마다 `EDIT`을 실을 것으로 읽히고 측정되지 않았다(총괄 확인 대기).~~ **적지 않은 것이 옳았고, 그 읽기가 맞았다** — 위 §5.6 참조. 계기가 된 해결 순서 수리는 [data_model §2.1](../architecture/data_model.md). 직전 **§1 — 컬럼 이름 해석 계약 신설**: 맵퍼는 정체성 컬럼 이름을 리터럴로도 기본값으로도 갖지 않는다. `server/chain_bindings.py`가 `룰 선언 > table_config 유도 > 이름을 대고 거절`로 해석하며, `dt_job` 기본값은 전부 삭제됐다. `replace_map` 경계 절에 **스코프 철자가 틀렸을 때 실제로 무엇이 지워지는가**를 실측표로 추가 — 명시 스코프는 삭제 전에 거절하고, 유도 경로는 map_key가 둘 이상일 때 필터를 조용히 빼서 **삭제를 넓힌다**. 직전 2026-08-05 **§1 — 트래킹되는 `.sample`이 셋으로 늘었습니다**: 트리거 테이블 밖을 읽는 맵퍼의 참조 구현 `cross_table_lookup_mapper.py.sample` 추가. "둘뿐"이라 적혀 있던 문장을 교정하고, virtual join과의 경계·세션 소유권·SAVEPOINT 격리 진입점을 링크했습니다. 맵퍼 호출 계약 자체는 변화 없음. 직전 2026-07-31 **§5 머리에 운영자 진입점 링크 추가** — 소급 경로 다섯 개의 운영자 정본은 [BACKFILL_GUIDE](./BACKFILL_GUIDE.md)로 신설됐고 이 절은 **개발자 계약**으로 남습니다. 서술 변경 없음. 직전 2026-07-30 **§4.4 ① 자동 확정** + **§5 Chain Replay R1/R2** 신설 — 맵퍼 계약 변화 없음) | **Owner:** Ingester | **Source-of-truth:** `server/chain_ingestion_worker.py`, `server/mappers/`, `server/enrichment_config.py`, `server/enrichment_mapper.py`, `server/enrichment_candidates.py`, `server/chain_replay.py`, `server/keyset_scan.py` · 상위 [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md)

체인 인제션 파서 및 맵퍼 모듈을 작성할 때, 단순히 유입되는 파일의 값뿐만 아니라 **데이터베이스의 기존 테이블(예: 재고 정보, 설비 마스터 등)을 직접 검색 및 조인(Join)하여 파생 컬럼을 계산**해야 하는 경우가 많습니다.

본 가이드는 SQLAlchemy DB 세션(`db`)을 활용하여 기존 데이터를 조회하고 가공하는 실전적인 예제와 구현 절차를 안내합니다.

---

## Mapper call contract (canonical payload; verified 2026-08-09)

Every custom chain mapper is invoked in one of these forms:

```python
def mapper(db, payload, rule=None):          # is_batch: false
    ...

def mapper(db, payloads, rule=None):         # is_batch: true
    ...
```

- `db`: worker-owned SQLAlchemy session. A mapper may read through it, but must
  not commit or write target rows directly.
- `payload`: one trigger row when `is_batch` is `false`.
- `payloads`: every trigger row of the current outbox transaction group for the
  trigger table, when `is_batch` is `true`.
- `rule`: the complete matching `chain_rules.json` object. The worker passes it
  only if the function declares `rule` or accepts `**kwargs`; `(db, payload)`
  remains valid for legacy mappers.

### Source-row payload: one contract everywhere

Live per-row events, collapsed-event expansion, and `chain_replay` use the
same column contract. Read source values only from
`payload["data"][column]["value"]`:

```python
{
  "row_id": "...",
  "business_key": "...",
  "data": {
    "dt_job": {"value": "SYN-TR-...", "is_overwrite": False,
               "updated_by": "system"},
    "dt_index": {"value": 1, "is_overwrite": False,
                 "updated_by": "system"}
  },
  "transaction_id": "...",
  "updated_by": "...",
  "source_name": "...",
  "timestamp": "..."
}
```

`data.<column>.value` is the sole column-value contract. Do not read a flat
field such as `payload.get("dt_job")`: it is not in the outbox contract and
causes live/replay divergence. Replay can omit non-column envelope metadata;
mapper logic that needs an input value must therefore rely on `data`.

### Column names: read them, never spell them (2026-08-11)

🔴 **A mapper must not contain a column-name literal for the identity it reads or
writes, and must not carry a default for one either.** `server/chain_bindings.py`
resolves every such name with one precedence:

```
rule declaration  >  table_config derivation  >  refuse by name
```

There is no convention fallback — the same rule `68db020` established for map
coordinate bindings. `chain_bindings.resolve_column(rule, key, table, purpose)`
returns the name or raises `ColumnBindingRefused` (a `ValueError`, so the worker
aborts the transaction and the API layer answers 400) with a message naming the
rule, the config key, the table and the column.

**Why a default is worse than nothing here.** `rule.get("job_column", "dt_job")`
is correct on the machine that wrote it, so nobody ever has to declare the real
name — and both ends of the chain then fail *silently* on a deployment that
spells it differently:

- **reading** — `_value(payload, "dt_job")` returns `None` for a name the payload
  does not carry, the mapper skips the row and returns an empty batch, and the
  worker records SUCCESS. The loud `source.dt_job` `AttributeError` a few lines
  below is unreachable, because the silent read already returned.
- **writing** — `crud.apply_batch_updates` DROPS an `updates` key the target
  table does not declare in `column_types`, warns once per `(table, column)` per
  process, and the write still returns success.

**Ask each table separately.** One mapper reads a TRIGGER payload, queries a
SOURCE table and writes a TARGET table. Those are three tables and each states
its own name, which a single literal cannot express. The optional rule keys are
`trigger_job_column`, `source_job_column`, `target_job_column`,
`inventory_job_column`, plus the pre-existing `job_column`,
`reference_job_column` and `derivation_source_column`. All of them are
**overrides**: with none declared, each name is derived from that table's own
`table_config` (a single-column `map_key_columns`, or a single-column
`business_key` on a table that declares no `composite_key_source`).

Regression net: `server/tests/test_job_column_from_config.py` — every table in it
spells the job column `jobcol_test_job_id`, because a test written on `dt_job`
cannot tell the working code from the broken code.

Return updates; batching, commits, outbox staging, and client notification are
worker-owned:

```python
return {
  "updates": [{
    "business_key_val": "target identity",
    "updates": {"target_column": "derived value"},
    "source_name": "chain_ingestion",
    "updated_by": "mapper_name"
  }]
}
```

Return `{"updates": []}` for an intentional no-op. Chain-created events reach
a downstream mapper only when that downstream rule explicitly sets
`allow_chain_trigger: true`.

This opt-in is keyed on ONE thing: the outbox payload's `source_name` being
`chain_ingestion` (`_rule_accepts_event`). Any automated pass that writes rows
without going through the chain worker must therefore label its writes, or its
events are read as a human edit and wake every rule a human wakes — that is the
defect `ffb23d6` fixed in R3 and `53f9187` in R2 (§5.6). 🔴 **The label is a CHANNEL, not
provenance**: it is `request_source` (a context var whose only reader is
`database._outbox_envelope`), NOT `update_item.source_name` (the per-item field
that creates a `cell_sources` layer). Setting the label does not create a layer.

## Write capability matrix: chain, enrichment, replay, and map replacement

All normal writes ultimately use `crud.apply_batch_updates`, so they are
**upserts**: an existing business key is updated and a missing one is created.
Each written cell retains source provenance and the visible value is selected by
the established source-priority rules; a lower-priority automated source cannot
silently replace a user value.

| Path                             | Can do                                                                                                                                                                          | Cannot do                                                                                                        | Notes                                                                                                                                              |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| Custom chain mapper              | Upsert returned updates; read declared/current DB state through `db`; intentionally return no updates | Commit directly; write raw target rows outside the worker batch; request an unapproved purge; **emit a row whose key columns are not filled** (see below) | Normal returns are upserts. Scoped replacement requires the batch envelope and `allow_replace_map: true`. A rule may explicitly authorize metadata for its own target map with `allow_map_metadata_upsert: true`. |
| Enrichment dedup                 | Upsert**one derived decision row per declared `decision_key`**                                                                                                          | Fill`target_fields` itself; arbitrarily update source rows; delete a decision row                              | `enrichment_mapper` deliberately projects only the identity/list fields. It does not assert a candidate result.                                  |
| Enrichment auto-confirm          | Fill a declared, currently unresolved`target_field` when the configured reference views yield exactly one candidate and both global and per-rule `auto_confirm` are enabled | Overwrite any cell that already has provenance; choose among multiple/no candidates; retract a past auto-confirm | Writes with source`enrichment_auto_confirm`; ambiguity and refusal stay visible in the queue/logs.                                               |
| Chain replay R1                  | Re-run a chosen enabled rule over current trigger-table rows, dry-run by default; apply the mapper's nonblank upserts                                                           | Reconstruct deleted trigger rows; cause a live cascade; treat mapper absence as a blank write                    | Replay sends the same canonical payload shape. Its`chain_ingestion` writes are not recursively consumed by the live worker.                      |
| Source withdrawal R2             | Dry-run or remove one named non-user source claim from selected cells, then reveal the next source and audit the change                                                         | Delete a whole row/map; withdraw source`user`; override a `manual_priority_source` pin                       | Use this when a prior derived assertion must be retracted. It is layer-level retraction, not a new mapper result. Outbox events labelled `chain_ingestion` since `53f9187` — the deletion predicate is built from the source_name PARAMETER and is untouched by the label (§5.6.2). |
| Display recompute R3             | Re-resolve which ALREADY-STORED layer wins and rewrite the materialised display column; audit every moved cell                                                                  | Create, alter or delete any `cell_sources` row; touch a cell with fewer than 2 layers; run without `--apply` writing anything | It changes the ANSWER, never a stored fact. Its outbox events are labelled `chain_ingestion`, so downstream rules consume them only under the same `allow_chain_trigger` opt-in R1 has (§5.6). |
| Direct batch/API map replacement | Replace the rows in one validated map scope when`GeneralUpdateBatch.replace_map=True`                                                                                         | Purge an arbitrary table population or a scope outside the table's map-key contract                              | This is a separate, explicit destructive operation. The scope is derived from or supplied as validated map-key values.                             |

### A chain may not emit an unkeyed row (`chain_key_gate`, 2026-08-11)

A mapper that cannot resolve an identity for a row **returns nothing for it**. Do not
emit the row and let the write path sort it out: a blank key column writes nothing
(`818c9c0`), so the row lands with `business_key_val` NULL, no upsert can ever address
it, and every re-delivery of the same data creates another one. One such row made
`GET /api/maps/alignment/worklist` answer 500 for the whole request (`c4a3159`) — a single
row was enough.

> 🔴 **여기 있던 「운영 실측 ~170,000행」은 술어가 반대였다.** 그 수는
> `add_business_key_unique_index.py`의 `duplicate_census` **`surplus`**이고
> (`dup_rows − groups`, **양쪽 다 `WHERE business_key_val IS NOT NULL`**), 곧
> **키가 «있는데» 중복된** 행의 수다. 키 «없는» 행 수는 같은 census의 **다른 필드**
> (`null_keys`/`nullbk`)이고 그 운영 값은 추적되는 산출물 어디에도 없다.
> 바꿔 넣을 수가 없으므로 **수를 빼고 메커니즘만 남긴다** — 논증은 원래 수가 필요 없었다.

**You do not have to write this guard.** It is enforced centrally in
[`server/chain_key_gate.py`](file:///c:/Users/kk980/Developments/assyManager/server/chain_key_gate.py),
on the two funnels every chain-emitted row already passes through — the
`write_batches` loop in `chain_ingestion_worker` and `chain_replay._apply_replay_batch`.
A guard written inside a mapper would not deploy at all, because `server/mappers/*.py`
is gitignored and only `*.py.sample` ships.

- **Which columns count as the key** is read from the declaration, never spelled: a
  table's `composite_key_source` when it has one, otherwise its `business_key`. Same
  discipline as §"Column names: read them, never spell them" — the 2026-08-11 incident
  was a hardcoded `dt_job` where production's column is `dt_job_id`.
- **Blankness** is `crud.is_blank_value`, the predicate the writer itself uses
  (`contracts/blank_predicate`). A coordinate of `0` is a value, not a blank.
- **An item that carries `row_id` or `business_key_val` is never refused**, so updating
  an existing row is unaffected.
- **A refusal is never a deletion.** If the gate empties a `replace_map` batch, the
  batch is skipped entirely rather than purging the scope and writing nothing. A
  *declared* empty replace (explicit `scope`, empty payload) still works.
- **Refusals are countable and attributable**: `(table, column)` counters for the life
  of the process, published through the chain worker's heartbeat note (the channel
  `/health` already reads for `crud.undeclared_column_drops()`), plus a log line naming
  the rule, the table, the columns and the count. `chain_replay` additionally reports
  `unkeyed_rows_refused` / `unkeyed_key_columns` in its run stats.
- **This is not a policy for ingestion or the grid.** Those may still produce a
  keyless row, and NULL remains its accepted shape (`818c9c0`, `data_model` §3.1-bis).

### `replace_map` boundary

`replace_map=True` validates that the replacement scope is a whole map according
to the target table's map-key contract, then deletes that scope before writing.

For a chain, it is an explicit opt-in batch envelope:

```python
return {"batches": [{"target_table": "dt_map", "replace_map": True,
                      "scope": {"dt_job": job_id}, "updates": cells}]}
```

The worker accepts it only when the matching rule declares
`allow_replace_map: true`; target redirection, empty scope, and non-replace
batches are refused. One envelope entry becomes one `GeneralUpdateBatch`, so
two maps cannot be combined. `dt_inventory_to_standard_dt_map` uses declared
scope `dt_map.map_key_columns=["dt_job"]`; other chains remain upserts.

The scope key above is spelled from `chain_bindings.resolve_column(...,
target_table, ...)`, not typed — it is the one output key whose name decides a
DELETE.

#### What a wrongly-spelled scope actually deletes (measured 2026-08-11)

The two resolution paths of `crud.derive_replace_map_scope` behave **oppositely**,
and only one of them is safe. Measured directly against the function:

| Path | Input | Result |
|---|---|---|
| **Explicit `scope`** (every chain — the worker requires a non-empty scope) | key the table does not declare | **`ValueError`, before any DELETE is composed.** `crud.py` validates every key against `column_types`, the map-key contract, the model, and non-emptiness. |
| **Derived** (no explicit scope — the API/map-push path) | single-column `map_key_columns`, payload misspells it | `None` → `apply_batch_updates` refuses. Safe. |
| **Derived** | **two-or-more `map_key_columns`, payload misspells/omits/blanks one** | 🔴 **the filter is silently DROPPED and the remaining filters are returned.** One filter short is a WIDER delete — e.g. `{ref_table, map_key}` degrades to `{ref_table}`, which purges every map of that ref table instead of one. |

The explicit path documents "a dropped filter would WIDEN a DELETE, so nothing is
silently skipped on this path"; the derived path does exactly that skip
(`crud.py` `derive_replace_map_scope`, the `for target_col in target_cols` loop
`continue`s on a payload miss). It is a pre-existing hazard, it does **not** reach
`dt_map` or `core_usage_map` (both declare a single map key, so a miss empties the
filter set and refuses), and it is **not** fixed here. Any table with two or more
`map_key_columns` — `map_split_registry` and `map_doe` declare
`(ref_table, map_key)` — is exposed if a payload can reach it with one key
missing.

### Target-map metadata within a chain

A mapper must not write `wafer_map_metadata` directly. A rule may instead return
`map_metadata_updates` and declare `allow_map_metadata_upsert: true`:

```python
return {
  "map_metadata_updates": [{
    "business_key_val": "dt_map_JOB-1",
    "updates": {"target_table": "dt_map", "map_id": "JOB-1",
                "grid_metadata": "<JSON>"},
    "source_name": "chain_ingestion", "updated_by": "mapper_name",
  }],
  "batches": [...],
}
```

The worker validates that the metadata target equals the rule's target table and
writes it before that rule's map cells. This is an ancillary write inside the
same chain rule, not a third chain hop.

## 💡 실전 예시 시나리오: 생산 부족 수량 자동 계산

- **상황**: `production_plan` (생산 계획) 데이터가 인입될 때,
- **목표**: `inventory_master` (재고 마스터) 테이블에서 동일한 자재 코드(`material_code`)의 **현재 가용 재고(`current_stock`)**를 조회(Join/검색)합니다.
- **계산**: `생산 요구 수량(plan_qty) - 현재 재고(current_stock)`를 계산하여 **부족 수량(`shortage_qty`)** 컬럼 값을 자동으로 도출해 채워 넣습니다.

---

## 🛠️ 1. 맵퍼(Mapper) 함수 구현 예제

맵퍼 스크립트는 `server/mappers/` 디렉토리 하위에 작성되며, 가공 실행 시점에 SQLAlchemy 데이터베이스 세션(`db: Session`) 객체를 인자로 전달받아 직접 자유로운 SQL 쿼리 및 ORM 조작을 수행할 수 있습니다.

### `calculate_shortage.py` (예제 — 저장소에 없는 파일입니다)

> ⚠️ 아래는 **직접 만들어 보는 템플릿**이지 저장소에 있는 파일이 아닙니다. `server/mappers/*`는 gitignored(사용자 커스텀 영역)이고 트래킹되는 것은 `*.sample`뿐(`production_mapper.py.sample` · `dt_map_mapper.py.sample` · `cross_table_lookup_mapper.py.sample`)이므로, 각 환경의 실제 맵퍼 구성은 **디렉터리를 직접 확인**해야 합니다. 이 파일명을 그대로 Read하려 하지 마십시오.
>
> 📎 **트리거 테이블이 아닌 다른 테이블을 읽어야 한다면** [`cross_table_lookup_mapper.py.sample`](file:///c:/Users/kk980/Developments/assyManager/server/mappers/cross_table_lookup_mapper.py.sample)가 정본 참조 구현입니다. 맨 앞에 **"이 도구가 틀린 경우"** 절이 있습니다 — 다른 테이블의 컬럼을 **그대로 보여 주기만** 하면 되는 경우는 virtual join(선언)이 정답이고 맵퍼 조회는 그것의 열등한 두 번째 철자입니다. 맵퍼가 정당해지는 조건은 값이 **계산**돼야 하거나 파생 시점에 **동결**돼야 할 때입니다(그 밖에 오른쪽이 조인 키로 유일할 수 없거나, 아직 존재하지 않는 행을 만들어야 할 때). 세션·트랜잭션 소유권, SAVEPOINT 격리(실패한 문장이 트랜잭션을 오염시킨다), N+1 회피, 부재 어휘(`not_declared`/`mapping_unavailable`)가 그 파일에 근거와 함께 들어 있고, `server/tests/test_mapper_sample_cross_table_lookup.py`가 그 `.sample`을 실제 워커 진입점(`execute_custom_mapper`)으로 실행해 못박습니다.
>
> 🔴 **`.sample`은 씨앗이지 거울이 아니다 — 그리고 룰이 가리키는 모듈이 없어도 아무도 말해 주지 않는다.** `chain_rules.json`의 `mapper_module`은 **로드 시점에 검증되지 않는다**. 유일하게 import를 시도하는 곳은 워커 웜업(`chain_ingestion_worker.py:630-639`)인데 ⓐ `enabled:false` 룰은 **건너뛰고** ⓑ 실패해도 `[Warmup] Mapper pre-import failed` **경고 한 줄 뒤 계속 기동**한다. 그래서 룰이 존재하지 않는 모듈을 가리켜도 활성화 전까지는 완전히 조용하고, 활성화하면 그때부터 해당 트랜잭션 그룹이 통째로 실패한다. 2026-08-02에 `mappers.dt_map_mapper`가 실제로 그 상태였다(`.sample`만 있고 `.py`가 없었다). 그리고 라이브와 `.sample`을 동기화하는 장치는 **없다** — `production_mapper.py`와 그 `.sample`은 이미 서로 다른 파일이다(함수 구성도 다름). 라이브를 고칠 때 샘플을 따라 고칠지는 **사람이 결정**해야 합니다.

```python
import logging
from sqlalchemy.orm import Session
from sqlalchemy import text

# 통합 로거 활용
logger = logging.getLogger("Chain.calculate_shortage")

def map_production_plan_shortage(row_data: dict, db: Session) -> dict:
    """
    생산 계획 행 데이터에 대해 재고 마스터 테이블을 조회하여 
    가용 재고를 기반으로 부족 수량(shortage_qty)을 실시간으로 조인 및 계산합니다.
  
    :param row_data: 인입된 신규 생산 계획 행 (dict 형태)
    :param db: SQLAlchemy 데이터베이스 세션 객체
    :return: 가공/계산이 완료된 갱신된 행 데이터 (dict 형태)
    """
    material_code = row_data.get("material_code")
    plan_qty = float(row_data.get("plan_qty") or 0)
  
    if not material_code:
        row_data["shortage_qty"] = 0
        row_data["inventory_note"] = "자재 코드 누락"
        return row_data

    try:
        # ---------------------------------------------------------
        # [DB 조회 예시 1] ORM 모델을 활용한 검색 및 조인
        # ---------------------------------------------------------
        # database.models에 등록되어 있는 dynamic model을 가져옵니다.
        from database.models import get_dynamic_model_class
      
        # 'inventory_master' 테이블 클래스 동적 획득
        InventoryMaster = get_dynamic_model_class("inventory_master")
      
        if InventoryMaster:
            # 동일 자재 코드의 재고 행을 검색 (가장 최근 갱신된 내역 기준)
            inv_record = db.query(InventoryMaster).filter(
                InventoryMaster.material_code == material_code
            ).order_by(InventoryMaster.updated_at.desc()).first()
          
            if inv_record:
                current_stock = float(inv_record.current_stock or 0)
                location = inv_record.storage_location or "미지정"
            else:
                current_stock = 0.0
                location = "재고 정보 없음"
        else:
            # ---------------------------------------------------------
            # [DB 조회 예시 2] ORM 모델이 없을 때 Raw SQL 활용 쿼리
            # ---------------------------------------------------------
            # ORM 모델이 동적으로 로드되지 않는 극초기 단계이거나, 복잡한 조인이 필요할 때 안전한 폴백입니다.
            sql_query = text("""
                SELECT current_stock, storage_location 
                FROM inventory_master 
                WHERE material_code = :mat_code 
                ORDER BY updated_at DESC LIMIT 1
            """)
            result = db.execute(sql_query, {"mat_code": material_code}).fetchone()
            if result:
                current_stock = float(result[0] or 0)
                location = result[1] or "미지정"
            else:
                current_stock = 0.0
                location = "재고 정보 없음"

        # ---------------------------------------------------------
        # [비즈니스 로직 연산] 부족 수량 계산
        # shortage_qty = 생산 필요 수량 - 가용 재고
        # ---------------------------------------------------------
        shortage_qty = max(0.0, plan_qty - current_stock)
      
        # 가공된 데이터 행에 계산 결과 바인딩
        row_data["shortage_qty"] = shortage_qty
        row_data["inventory_note"] = f"현재고: {current_stock}개 (창고: {location})"
      
        logger.info(f"[ShortageCalc] Material={material_code} -> Plan={plan_qty}, Stock={current_stock} -> Shortage={shortage_qty}")
      
    except Exception as e:
        logger.error(f"Failed to calculate shortage for material '{material_code}': {e}")
        row_data["shortage_qty"] = 0
        row_data["inventory_note"] = f"재고 계산 오류: {str(e)}"
      
    return row_data
```

---

## ⚙️ 2. 체인 룰 설정 파일에 맵퍼 등록

가공 연산이 정의된 파이썬 함수를 실제 인제션 파이프라인 흐름에 바인딩하기 위해 체인 룰 설정 파일에 맵퍼 모듈 정보를 기재합니다.

### [chain_rules.json](file:///c:/Users/kk980/Developments/assyManager/server/config/chain_rules.json)

```json
[
  {
    "rule_name": "Production Plan Shortage Ingestion",
    "source_table": "production_plan_raw",
    "target_table": "production_plan",
    "active": true,
    "mappers": [
      {
        "module": "mappers.calculate_shortage",
        "function": "map_production_plan_shortage"
      }
    ]
  }
]
```

---

## 💡 개발 시 주의해야 할 3대 Best Practices

1. **별도 트랜잭션 Commit 금지 (`db.commit()` 수행 자제)**:
   - 워커 메인 루프가 하나의 트랜잭션 단위로 전체 행 처리를 래핑하고 있습니다.
   - 맵퍼 내에서 성급하게 `db.commit()`을 호출하면 트랜잭션 원자성이 깨져 에러 발생 시 부분 롤백이 불가능해지므로, 맵퍼 내부에서는 오직 데이터 **조회 및 할당**만 수행하고 커밋은 상위 워커 엔진에게 일임하십시오.
2. **N+1 쿼리 최소화 (Batching or Caching)**:
   - 인제션되는 행 수가 대량(수천~수만 건)인 경우, 매 행마다 `db.query()`를 날리면 네트워크/디스크 부하가 심각해집니다.
   - 대량 인제션이 예상되는 경우, `calculate_shortage.py` 모듈 초기화 시점에 `inventory_master` 전체 리스트를 한 번에 긁어 메모리 딕셔너리에 캐시해 두고 룩업(Lookup)을 도는 형태의 배칭 최적화를 권장합니다.
3. **스키마 동적 로드 시점 고려**:
   - `database.models.get_dynamic_model_class(table_name)`는 DB 초기화 이후 동작합니다. 안전을 위해 맵퍼 내부에서 모델 임포트 시 `from database.models import ...`를 함수 내부에서 지연 임포트(Lazy Import)하는 것이 안전합니다.

> ℹ️ **[M3 · 2026-07-29] 맵 테이블에 쓰는 체인 룰은 메타 자동 등록을 유발합니다.** 타깃 테이블이 `map_key_columns`를 선언하고 좌표 바인딩이 해석되면, 워커가 트랜잭션 그룹 처리 후 그 배치의 각 distinct 맵 키에 대해 **부재 시에만** `wafer_map_metadata` 행을 만듭니다(기존 행은 절대 덮지 않음). **맵퍼 코드는 바꿀 것이 없고** 실패해도 체인 적재는 정상 완료됩니다. 계약·끄는 법(`auto_register_map_meta`)은 [INGESTION_GUIDE §1.10](./INGESTION_GUIDE.md)이 정본입니다.

---

## 🧩 4. Enrichment Queue 규칙 작성 (dedup 투영 — 자동 파생 체인 룰)

> 기준 스펙: [ENRICHMENT_QUEUE_SPEC.md](../spec/ENRICHMENT_QUEUE_SPEC.md) · 구현: `server/enrichment_config.py`, `server/enrichment_mapper.py`

**맵퍼 코드를 쓸 필요가 없습니다.** `server/config/enrichment_rules.json`(사용자 영역, gitignored — 형식은 `enrichment_rules.json.sample` 참조)에 규칙을 선언하면, 체인 워커의 `load_chain_rules()`가 규칙마다 dedup 투영 체인 룰(`enrichment_mapper.map_enrichment_dedup`, `is_batch: true`)을 자동 파생하여 기존 체인 파이프라인(HOL 가드·SLO 계측·재시도·warmup)을 그대로 태웁니다.

### 4.1 규칙 스키마

```jsonc
// server/config/enrichment_rules.json — {규칙명: 규칙}
{
  "bonding_wafer_attribution": {
    "source_table":  "bonding_log",              // 필수: 대량 원본 테이블
    "derived_table": "bonding_job_inventory",    // 필수: 파생 영속 테이블 — table_config.json에 등록되어 있어야 함
    "decision_key":  ["equipment", "event_time"],// 필수: 판단키(사람이 1회 판단하는 단위)
    "target_fields": ["wafer_id"],               // 필수: 사람이 채울 필드 — 맵퍼는 이 필드를 절대 쓰지 않음
    "list_columns":  ["chip_count", "lot_hint"], // 선택: 워크리스트 표시 단서(배치 내 대표값)
    "aggregations":  { "chip_count": "count" },  // 선택(서버 전용): v1은 count만 — 영향 키 한정 재계산(멱등)
    "enabled": true,
    "reference_views": [
      { "label": "lot event",
        "query": "SELECT lot_id, event_time FROM lot_events WHERE equipment = :equipment", // 인라인 SQL
        "limit": 200 },
      { "label": "lot-slot 이력", "query_ref": "lot_slot_history" }  // config/enrichment_queries/<ref>.sql
    ]
  }
}
```

### 4.2 필수 전제·제약 (위반 시 규칙이 로그와 함께 **스킵**됨)

1. **파생 테이블 등록**: `derived_table`은 `table_config.json`의 보통 테이블이어야 합니다(레이어링·AuditLog·WS·그리드 편집이 공짜로 적용되는 이유). `decision_key`·`target_fields`·`list_columns`는 파생 테이블 컬럼이어야 하고, `decision_key`는 원본 테이블 컬럼이기도 해야 합니다.
2. **파생 테이블 키 계약**: 파생 테이블 config는 `composite_key_source ⊆ decision_key` 이거나 `business_key ∈ decision_key` 여야 합니다(맵퍼가 판단키로 business_key_val을 결정론적으로 조립 — 키당 1행 upsert의 근거).
3. **참조뷰 SQL**: 단일 SELECT(또는 WITH)만, `;` 다중문 금지, 바인드 파라미터(`:col`)는 decision_key 컬럼명만. 쿼리 본문은 서버에만 존재하며 클라이언트에는 label만 노출됩니다. LIMIT은 서버가 강제(기본 200, 최대 1000).
4. **[확장성] count 집계 인덱스**: `aggregations: count`는 "영향받은 판단키 한정" `GROUP BY` 재계산(500키 청킹)을 수행합니다. 원본 테이블이 대규모(수백만 행 이상)라면 **decision_key 컬럼 복합 인덱스**를 생성하십시오(미생성 시 청크당 스캔 발생).

### 4.3 동작 요약 (불변식)

- 원본 변경 이벤트 배치 → decision_key 유니크 조합 추출(**증분** — 이벤트 행만, 풀스캔 없음) → 파생 테이블에 키당 1행 upsert.
- **신규 키**: 행 생성, `target_fields`는 NULL(결손) → blank 필터 워크리스트에 잡힘.
- **기존 키**: 집계·단서 컬럼만 갱신. 맵퍼는 `target_fields`를 updates에 아예 포함하지 않으며(1차 방어), 설령 포함되더라도 source `chain_ingestion`(우선순위 최하)는 user(priority 0)를 이길 수 없습니다(2차 방어 — 레이어링).
- 규칙 반영: 웹서버는 요청 시마다 재로드(무중단), 워커는 `SYSTEM_RELOAD`(`/admin/reload-configs`) 시 재파생.

### 4.4 후보가 1개면 자동 확정 (① `candidate_for` + `auto_confirm`, 2026-07-30)

참조뷰에 `candidate_for: {target_field: 뷰_결과_컬럼}`을 선언하면, 그 뷰가 판단키에 대해 **유일한 값 하나**를 낼 때 체인 워커가 그 값을 **부재 시에만** 채웁니다(규칙별 `auto_confirm`, 기본 OFF). 소스명은 `enrichment_auto_confirm` = `SOURCE_PRIORITY` 미등재 = **최하위(99)** 이므로 사람 편집이 항상 이깁니다. **맵퍼 코드는 바꿀 것이 없습니다** — 훅은 M3 맵 메타 훅 바로 뒤, 체인 쓰기 이후에 붙고 실패해도 체인 적재는 정상 완료됩니다. 선언·거절 사유·측정 절차의 정본은 [config/enrichment_rules §7](./config/enrichment_rules.md)입니다.

⚠️ **컬럼명으로 유추하지 않습니다.** 같은 규칙의 두 뷰가 모두 `wafer_id` 컬럼을 가질 수 있고(하나는 판단키 전체로, 하나는 일부로 조회), 후자는 후보가 N개입니다. 선언한 뷰만 후보 원천입니다.

## 🔁 5. Chain Replay — 룰 재적용 (R1) / 낡은 소스 철회 (R2) / 표시값 재계산 (R3)

> 🧭 **이 절은 개발자 계약입니다.** 「지금 무엇을 돌려야 하나」가 필요한 운영자는 **[BACKFILL_GUIDE](./BACKFILL_GUIDE.md)**로 가십시오 — R1/R2/R3를 포함한 소급 경로를 증상→도구 결정표로 묶어 놓았습니다(인리치먼트 2종·그래프 고아 스윕 포함).

> **세 연산을 가르는 한 줄** — R1은 **매퍼를 다시 돌려 새 층을 씁니다**, R2는 **한 층의 주장을 지웁니다**, R3는 **저장된 것을 하나도 바꾸지 않고 「그중 무엇이 이기는가」만 다시 답합니다.** 앞의 둘이 답할 수 없는 질문이 셋째이고, 그것이 세 번째 연산이 있는 이유입니다.

체인 인제션은 **증분(outbox) 구동**입니다. 룰을 바꿔도 과거 데이터는 옛 룰이 남긴 상태 그대로입니다. R1은 트리거 테이블의 **현재 내용**을 키셋 페이지로 훑어 **실제 맵퍼·실제 쓰기 경로**로 다시 흘려보냅니다. `backfill_enrichment.py`(규칙 1개 전용)를 **모든 체인 룰로 일반화**한 것이고, 기본값도 같습니다 — `--apply` 없이는 아무것도 쓰지 않습니다.

```bash
conda run -n assy_manager python server/scripts/chain_replay_cli.py list          # 룰 + 재적용 순서
conda run -n assy_manager python server/scripts/chain_replay_cli.py replay <룰>    # dry-run
conda run -n assy_manager python server/scripts/chain_replay_cli.py replay <룰> --apply
conda run -n assy_manager python server/scripts/chain_replay_cli.py replay-all     # 의존 순서대로 각 1회
```

### 5.1 왜 맵퍼를 그대로 재실행할 수 있는가 (측정된 전제)

맵퍼는 **payload의 순수 함수**입니다 — `mappers/base.py`는 `payloads_to_df`만 제공하고, 실 맵퍼 진입점(`reserve_materials_from_plan(db, payload)` / `reserve_materials_batch_df(db, payloads)`)에 **파일 경로 인자도, `open()`도, `pd.read_*`도 없습니다.** 그래서 원본 파일 없이 재적용이 성립합니다. 새 맵퍼를 쓸 때 이 성질을 깨지 마십시오(payload 밖의 파일·전역 상태를 읽으면 재적용 결과가 라이브와 갈립니다).

> **[OUTBOX-④ 2026-08-07] 맵퍼가 받는 payload의 모양은 그대로이고, 그 payload가 **어디서 오는지**가 바뀌었다.**
> 대량 인제션의 outbox 이벤트는 값을 나르지 않고 `row_ids`를 지목한다(축약 — [event_driven_backend §2.4](../architecture/event_driven_backend.md)). 체인 워커는 매퍼를 부르기 **전에** `outbox_expand.expand_events`로 **본 테이블을 다시 읽어** 종전과 같은 중첩 payload를 합성한다. 즉 **라이브 경로가 R1(replay)과 같은 방식으로 파생하게 됐고**, 위 문단의 「payload의 순수 함수」 전제는 그래서 더 강해진다(같은 합성 함수, 같은 모양).
> 🔴 **대신 payload는 이제 사건 시점의 스냅샷이 아니라 소비 시점의 현재 상태다.** 같은 행이 빠르게 두 번 바뀌면 두 이벤트가 모두 최종 상태에서 파생한다(멱등). 소비 전에 행이 삭제되면 **아무것도 파생하지 않고**, 그 사실은 WARNING으로 남는다(조용한 스킵 아님). 맵퍼가 "이 행의 그 순간 값"에 의존하도록 쓰면 안 된다.

### 5.2 세 겹의 루프 가드 (자기 트리거 룰이 있으므로 필수)

현 `chain_rules.json`은 `production_plan → inventory_master`와 **`inventory_master → inventory_master`(트리거 = 타깃)** 를 갖습니다. 자기 트리거가 실재하므로 가드는 선택이 아닙니다.

| 겹 | 무엇                                                                                                                                                                     | 어디                                                                       |
| -- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------- |
| ① | **시작 시점 스냅샷 경계** — 트리거 = 타깃이면 시작 시점 `max(row_id)`까지만 읽어, 스캔이 **자기 산출물을 다시 만나지 않습니다**                           | `chain_replay.replay_rule` → `keyset_scan.iter_pages(max_row_id=...)` |
| ② | **룰당 정확히 1회** — `replay-all`은 캐스케이드 재발화를 하지 않습니다                                                                                          | `chain_replay.replay_all`                                                |
| ③ | **라이브 워커의 기존 필터** — 재적용 쓰기는 `source_name="chain_ingestion"`이고 워커는 그 이벤트를 이미 버립니다. **새 가드가 아니라 기존 가드의 재사용** | `process_chain_transaction_group`                                        |

**재적용 순서**는 계약입니다: 생산자(`→ inventory_master`)가 소비자보다 먼저 갑니다. 자기 간선은 순서에서 제외하고 ①로 다룹니다. **서로 다른 테이블 사이의 순환**은 올바른 순서가 없으므로 순환 경로를 이름으로 밝히며 **거부**합니다.

### 5.3 R1이 절대 하지 않는 두 가지

- **사람 값을 덮지 않습니다.** 쓰기 소스는 라이브 워커와 같은 `chain_ingestion`(우선순위 4)이고 사람은 `user`(0)입니다 — 레이어링이 이미 처리하므로 R1에 특례 코드가 없습니다. dry-run 보고에 **`cells a human protects`** 수치가 함께 나옵니다(안전성을 말이 아니라 수로 제시).
- **빈 값을 쓰지 않습니다.** "이 셀에 룰이 더는 값을 만들지 않는다"는 **빈 값과 다른 진술**이고, 그 진술을 할 수 있는 것은 R2뿐입니다. R1은 그런 셀을 **철회 후보**로 보고만 하고 넘어갑니다.

### 5.4 R2 — 낡은 소스 철회 (레이어 단위, 행 단위 아님)

```bash
conda run -n assy_manager python server/scripts/chain_replay_cli.py withdraw <테이블> <소스> --columns col1,col2
conda run -n assy_manager python server/scripts/chain_replay_cli.py withdraw <테이블> <소스> --columns col1 --apply
```

`cell_sources` 행 **하나**를 지우고 남은 소스로 `compute_priority_value`를 다시 계산해 표시값을 되돌립니다 — 두 소스가 있었다면 **아래 레이어가 드러나고, 구멍이 남지 않습니다.** 이것이 H2-b(소스가 과거에 주장했으나 더는 주장하지 않는 것은 남겨두지 않고 적극 제거)를 **셀 버전 단위**로 옮긴 것입니다. 행 삭제나 컬럼 NULL 처리는 다른 소스의 기여까지 파괴하므로 하지 않습니다.

🔴 **사람 값을 지울 수 있는 경로가 없습니다 — 두 거절로 보장합니다.**

| 거절                                                          | 이유                                                                                                                                 |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `user` 소스 철회 요구                                       | 사람이 입력한 값입니다. 도구가 지우지 않습니다 — 셀을 편집하십시오                                                                  |
| 그 소스를 사람이**핀**한 셀(`manual_priority_source`) | 핀은 "이 소스를 보여 달라"는 사람의 선택입니다. 조용히 철회하면 그 선택을 뒤집습니다 →`pinned_skipped`로 건너뛰고 이유를 남깁니다 |

**철회는 무음이 아닙니다.** 표시값이 바뀐 셀마다 `AuditLog`에 소스 `chain_replay_withdraw` · `updated_by="withdraw:<소스명>"` · old/new 값이 남습니다. 클라의 **기존 셀 이력 타임라인**이 AuditLog를 읽으므로, 빈칸을 발견한 운영자가 그 셀을 눌러 "어느 소스가 사라졌는지"를 봅니다(신규 이벤트·신규 화면 없음).

🔴 **철회가 내는 아웃박스 이벤트의 라벨은 §5.6.2가 소유합니다** — `53f9187` 전까지 이 연산은 이벤트를 `user`로 내보내 **사람의 그리드 편집처럼** 하류를 깨웠고, **어드민 소급 라우트에 있어 R3보다 도달하기 쉬웠습니다.** 삭제 술어는 그때도 지금도 라벨과 무관합니다(파라미터로 짜입니다).

### 5.5 R3 — 표시값 재계산 (`recompute_display_values`, 2026-08-11)

```bash
conda run -n assy_manager python server/scripts/chain_replay_cli.py resolve <테이블>
conda run -n assy_manager python server/scripts/chain_replay_cli.py resolve <테이블> --columns col1,col2
conda run -n assy_manager python server/scripts/chain_replay_cli.py resolve <테이블> --list-all
conda run -n assy_manager python server/scripts/chain_replay_cli.py resolve <테이블> --apply
```

플래그 전수: `--columns` · `--limit`(훑는 **행** 수 상한) · `--chunk-size`(기본 1000) · `--list-all`(보고서에서 20건 절단을 풀기) · `--apply`.

**왜 R1도 R2도 이것을 못 하는가.** 이긴 값은 **materialise**됩니다 — `apply_row_update_internal`이 마지막에 `setattr(row, col, new_val)`을 하고 이후의 모든 조회는 층이 아니라 그 컬럼을 읽습니다. 그래서 `crud.compute_priority_value`를 고치면 **그 뒤에 쓰이는 셀만** 고쳐집니다. 과거에 잘못 해결된 셀은 무엇인가가 다시 배달해 줄 때까지 그대로인데, **다시 배달해 줄 그것이 정확히 결함이 버리던 것**입니다(해결값이 안 움직이면 `has_changed`가 거짓이고 그 가드가 컬럼 쓰기·감사·아웃박스를 한꺼번에 막습니다). R1은 **룰이 필요하고 새 층을 쓰며**, R2는 **주장을 지웁니다** — 저장된 것을 바꾸지 않고 「무엇이 이기는가」만 다시 답하는 연산이 셋째입니다.

- 🔴 **`cell_sources` 행을 하나도 만들지 않고 지우지 않고 고치지 않습니다.** 움직이는 것은 표시 컬럼뿐입니다.
- 🔴 **층이 2개 미만인 셀은 절대 건드리지 않으며, 최적화가 아니라 안전 속성입니다.** 층이 하나면 가를 동점이 없고, 층이 **0개**면 해결 결과가 `(None, None)`이라 **다른 쓰기 경로가 소유한 컬럼을 이 패스가 비워 버립니다.** 이 관문이 「전체 테이블 실행이 자기가 이해하지 못하는 데이터를 파괴할 수 없다」의 근거입니다.
- **무음이 아닙니다.** 표시값이 움직인 셀마다 `AuditLog`에 소스 `resolution_recompute` · `updated_by="resolved:<이긴 소스명>"` · old/new가 남습니다 — R2와 같은 자세이고, 클라의 기존 셀 이력 타임라인이 그대로 읽습니다. **기록 없이 바뀌는 값**은 지금 수리 중인 결함과 같은 계급이므로 감사 쓰기는 선택이 아니고, `--apply`는 **둘 다 하거나 둘 다 안 합니다.**
- **사람의 핀은 존중됩니다.** 핀은 **어느 층이 이기는가**를 정하는 것이지 표시 컬럼을 얼리는 것이 아니므로, 핀이 걸린 셀은 **핀이 지목한 층의 값으로** 해결됩니다. 보고서의 `of which human-pinned`는 「핀을 무시했다」가 아니라 **「화면이 사람이 고른 층에서 멀어져 있었고 그것을 되돌렸다」**입니다.
- **신규 이벤트 타입도 신규 화면도 만들지 않습니다** — R2와 같은 자세이고, 설명은 기존 셀 이력 타임라인이 합니다. **CLI 전용 연산**이며 어드민 API 등록부(`server/retroactive.py`의 `OPERATIONS`)에도 **없습니다**(2026-08-11 실측 — ⓐ~ⓔ 다섯만 등재).
- **dry-run이 곧 열거입니다.** `--apply` 없이 돌리면 바뀔 셀을 그대로 찍습니다(기본 20건, `--list-all`로 전량). 보고서의 두 사유를 구분해 읽으십시오 — **`tie broken by recency`**(동점이 있었다 = 이 결함의 지문) vs **`already out of step`**(층과 표시 컬럼이 애초에 어긋나 있었다). 인메모리 목록에는 상한이 있고 초과 시 그 사실을 말합니다 — **완전한 기록은 `--apply`가 쓴 `AuditLog` 행들**입니다.
- 페이지 단위 커밋 + 키셋 순회(`keyset_scan.iter_pages`)라 대량 실행을 중간에 끊어도 되고, 끊기면 진행 중이던 페이지 하나만 잃습니다. 레이어링 관점의 계약은 [architecture/data_model §2.2-ter](../architecture/data_model.md).

---

### 5.6 세 연산이 내는 아웃박스 이벤트 — 라벨과 그룹핑 (`ffb23d6` + `53f9187`, 2026-08-11)

> ✅ 종전 §5.5에는 「**정적 판독이고 측정하지 않았습니다 — 총괄 확인 대기**」가 있었습니다. 측정이 끝났고 **정적 판독이 맞았습니다.** 아래는 확정 서술입니다.
>
> 🔴 **넷째 연산을 만들기 전에 이 절을 읽으십시오.** 세 연산이 **각자** 이 문제를 만났고 둘은 같은 결함이었습니다 — 「저장된 것을 바꾸는가」 축(§5 서두)과 **독립인 두 번째 축**입니다.

| | 라벨 | transaction id | 상태 |
|---|---|---|---|
| **R1** 재적용 | ✅ **구성상 옳다** — `apply_batch_updates`가 항목의 `source_name`(=`chain_ingestion`)을 컨텍스트로 복사한다 | ⚠️ **페이지당 하나**(`chain_replay_{run_id}_{page:06d}`) | **라벨은 닫혔고 그룹핑은 열려 있다** |
| **R2** 철회 | ✅ `53f9187` — `chain_ingestion` / `chain_replay_withdraw` | ✅ 실행당 하나 | 닫힘 |
| **R3** 재계산 | ✅ `ffb23d6` — `chain_ingestion` / `resolution_recompute` | ✅ 실행당 하나 | 닫힘 |

- ⚠️ **R1의 남은 결함은 같은 비용의 약한 형태입니다** — 페이지당 tx id는 실행당 하나보다 **페이지 수만큼 많은 직렬 그룹**을 만듭니다. **라벨이 맞다고 그룹핑도 맞은 것이 아닙니다**(두 필드는 같은 엔벨로프에 있을 뿐 서로를 함의하지 않습니다). 미수리 — 총괄 판정 대기.

#### 5.6.1 R3에서 측정된 것 (`ffb23d6`)

- **이벤트는 납니다. 단위는 *행*입니다.** `setattr(row, col, ...)`이 동적 테이블 행을 dirty로 만들고 `database.auto_stage_database_outbox`가 **모든 `Session`에 걸린 전역 `before_flush`**로 `session.dirty`를 걸으므로, **변경된 행마다 `EDIT` 하나**입니다 — 셀마다가 아닙니다(한 행에서 세 컬럼이 움직여도 이벤트는 하나). 🔴 **`--chunk-size`는 커밋과 NOTIFY 횟수를 움직이지만 이벤트 수는 한 건도 움직이지 않습니다** — 이벤트 수를 줄이려고 청크를 키우지 마십시오.
- 🔴 **결함은 개수가 아니라 *라벨*이었습니다.** 그 이벤트들은 `source_name="user"` · `updated_by="system"` · **이벤트마다 새 uuid4**를 달고 나갔고, 하류에서 이것은 **사람이 그리드에서 친 것과 구별되지 않습니다.** 격리 `assy_qa` 실측 — `dt_log` 행의 셀 하나를 수리했을 때:

  | | 종전 | `ffb23d6` 이후 |
  |---|---|---|
  | 이벤트 | 5 | 5 |
  | 라벨 | `user` / `system` | **`chain_ingestion` / `resolution_recompute`** |
  | transaction id | 5 | **1** |
  | 수락한 룰 | 5 | **0** |
  | 파생 쓰기가 닿은 테이블 | 4 | **0** |

  수리 한 번이 인리치먼트 매퍼 둘을 돌리고 두 테이블에 체인 배치를 쓰고 자동 확정 패스까지 돌았습니다(438 ms · 422 ms 2회 측정).
- 🔴 **이것은 억제가 아니라 옵트인입니다.** `chain_ingestion` 라벨은 R1이 이미 지나는 **룰별 옵트인**(`_rule_accepts_event`, `chain_ingestion_worker.py:328`)에 R3를 함께 세웁니다 — `allow_chain_trigger: true`를 선언한 룰은 **여전히 이 이벤트를 받습니다.** 「이벤트를 안 내보낸다」로 고쳤다면 그 선언이 조용히 무의미해졌을 것이고, **침묵과 동의는 다른 물건**입니다(뮤테이션 채점에서 억제형 「수리」가 첫 가드를 통과하고 둘째에서 죽습니다 — 가드가 둘인 이유가 그것입니다).
- 🔴 **transaction id 붕괴가 비싼 절반입니다.** 체인 워커는 **transaction id로 묶어** 처리하므로, 이벤트마다 id가 다르면 N개 수리 행이 **N개의 직렬 그룹**이 됩니다 — 그룹당 ~430 ms면 10,000행이 약 72분이고 그동안 라이브 인제션이 뒤에 줄을 섭니다.
- 🔴 **라벨과 층은 다른 필드이고 섞이지 않습니다.** **층**을 만드는 것은 `update_item.source_name`(항목별 pydantic 필드)이고, **라벨**은 `request_source`(컨텍스트 변수 — 서버 트리 전체에서 읽는 곳은 `database._outbox_envelope` 하나)입니다. 둘이 만나는 곳은 배치 경로가 배치의 소스명을 컨텍스트로 복사하는 **정확히 한 줄**이고 **R3는 그 줄을 지나지 않습니다.** 그래서 라벨을 바꿔도 수리된 셀에 `chain_ingestion` 층이 생기지 않으며, 이것은 논증이 아니라 실측입니다(대상 행 `cell_sources` 스냅샷의 sha256이 전후 동일 · `test_recompute_creates_no_cell_sources_layer`가 고정). **이 구분이 무너지면 지금 고친 결함보다 나쁜 결함이 되고, 초록 테스트에서는 안 보입니다.**
- ⚠️ **R3는 `_apply_replay_batch`를 지나지 않습니다 — 그 헬퍼는 R1의 것입니다.** 「페이지마다 tx id 하나」는 그 헬퍼의 성질이고 R3에 대입하면 틀립니다. R3의 이벤트는 전역 `before_flush`에서 나오고 세 필드는 `_outbox_envelope`가 읽는 **컨텍스트 기본값**에서 옵니다 — 컨텍스트를 아무도 안 세우면 `request_transaction_id.get() or str(uuid.uuid4())`가 **이벤트마다 새 uuid4**를 낳던 그 자리입니다.
- **컨텍스트의 범위는 커밋이 아니라 페이지 루프 전체입니다** — 다음 페이지의 키셋 질의에서 일어나는 autoflush만으로도 이벤트가 스테이징되기 때문입니다.
- ⚠️ **측정은 격리 `assy_qa`에서 했습니다 — 비율과 기제는 전이되지만 절대 수치는 아닙니다.**
- **운영자에게 약속하는 문장은 그대로입니다: 「즉시 갱신을 보장하지 않는다 · 안 바뀌어 보이면 새로고침」.** 라벨 수리는 **하류 캐스케이드를 끈 것**이지 화면 푸시를 켠 것이 아닙니다(워커는 체인이 **쓴 것**을 방송하고, 아무것도 안 쓴 그룹은 즉시 처리 완료로 도장됩니다).

#### 5.6.2 R2도 같은 결함이었고 닫혔습니다 (`53f9187`) — **버튼 뒤에 있던 쪽**

`ffb23d6` 시점에는 R2가 같은 결함을 그대로 갖고 있었고, **R3보다 급했습니다** — R3는 사람이 CLI 앞에 앉아야 하지만 **R2는 어드민 소급 라우트에서 도달 가능**합니다. 수리는 `withdraw_source`를 `crud.transaction_context(R2_AUDIT_SOURCE, tx_id, R1_SOURCE_NAME)`으로 감싼 것이고, **`git diff -w` 기준 소스 한 줄**입니다.

| | 종전 | `53f9187` 이후 |
|---|---|---|
| 이벤트 | 4 | 4 |
| 라벨 | `user` / `system` | **`chain_ingestion` / `chain_replay_withdraw`** |
| transaction id | 3 | **1** |
| 수락한 대상 테이블 | 4 | **0** |
| 클라가 받은 WebSocket 프레임 | 4 | **0** |

- 🔴 **R3와 달리 R2는 층을 *지웁니다* — 그래서 「무엇이 지워지는가」를 따로 물었고, 상속하지 않았습니다.** 삭제 술어(`_claimed_filter`와 DELETE의 `CellSource.source_name == source_name`)는 **`source_name` 파라미터**로 짜이고 라벨은 컨텍스트 변수입니다. 두 개념이 이름을 공유할 뿐 **한쪽에서 다른 쪽으로 가는 경로가 없습니다.** 논증이 아니라 실측입니다 — 컨텍스트를 no-op 시킨 실행과 출하 실행이 **같은 4개 층을 지우고 생존 집합의 sha256이 동일**합니다.
- 🔴 **`PROTECTED_SOURCES`와 사람의 핀은 두 진입점 모두에서 동일합니다** — 라이브러리와 **어드민 소급 라우트** 양쪽을 실제로 몰아 확인했습니다(`ReplayRefused`/`RetroactiveRefused`·`pinned_skipped=1`·핀 걸린 층과 표시값 무손상). **수리가 버튼에까지 닿았다**는 뜻이고, 라이브러리만 고치고 끝내면 정확히 이 확인이 빠집니다.
- 🔴 **WebSocket 프레임 4 → 0은 운영자에게서 무언가를 뺀 것이 아닙니다 — 이 구분을 정확히 적는 이유가 있습니다.** 읽는 사람은 반대로 가정합니다(철회는 **표시값을 바꾸므로** 「그럼 화면 통지가 사라진 것 아닌가」는 진짜 질문입니다). 측정된 답: **클라는 실제로 바뀐 `dt_log` 셀에 대해 전후 어느 쪽에서도 통지받은 적이 없습니다.** 워커는 체인이 **쓴 것**(대상 테이블)을 방송하지 이벤트가 나온 테이블을 방송하지 않으므로, 종전의 그 4개 프레임은 **아무도 아무것도 철회하지 않은 `dt_job_attribution`**의 것이었습니다. 없어진 것은 **엉뚱한 캐스케이드 통지**이지 철회 통지가 아닙니다. 철회를 이해하려고 운영자가 읽는 것은 여전히 `AuditLog` 행이고, 그 행은 `chain_replay_withdraw`를 그대로 답니다 — **아웃박스 `source_name`은 순환 필터의 채널이지 provenance 기록이 아닙니다.**
- ⚠️ **차등(differential) 테스트 하나가 강해 보였고 눈이 멀어 있었습니다.** 「라벨을 켜든 끄든 같은 층이 지워진다」만 단언하는 테스트는 **양팔을 똑같이 움직이는 변이를 볼 수 없습니다**(픽스처가 갖지도 않은 소스를 지우게 만드는 변이는 양팔이 여전히 일치합니다). 기존 테스트 둘은 그 변이에 죽었는데 이 변경을 위해 쓴 테스트만 살아남았습니다 — **절대 단언**(정확한 생존 집합 + `pinned_skipped == 1`)을 더해 고쳤습니다.

---

## 🗺️ 6. 파생 맵(dt_log → dt_map) — 세 트리거 · 세 겹 게이트 · 철회 (2026-08-04)

`dt_map`은 **파생 테이블**입니다. `dt_log`가 기록이고 맵은 그 투영이므로 손으로 쓰면 다음 리플레이가 조용히 어긋납니다. 판단은 전부 [`server/dt_map_derivation.py`](file:///c:/Users/kk980/Developments/assyManager/server/dt_map_derivation.py)에 있고 [`mappers/dt_map_mapper.py`](file:///c:/Users/kk980/Developments/assyManager/server/mappers/dt_map_mapper.py)는 **어느 행을 넘길지만** 정하는 얇은 어댑터입니다.

🔴 **세 룰 모두 `enabled: false`로 나갑니다.** 켜는 것은 근거와 함께 내리는 별도의 결정입니다.

### 6.1 트리거가 왜 셋인가 — 룰 하나에 `trigger_table`은 하나뿐이다

`chain_ingestion_worker`는 `r["trigger_table"] == table_name`으로 룰을 고릅니다(`:394`). **목록을 받지 않습니다.** 대신 **같은 `mapper_module`·`mapper_function`·`target_table`을 가리키는 룰 여러 개**는 문제없이 공존하고, 워커가 매칭된 룰을 맵퍼에 넘겨주므로(`execute_custom_mapper(..., rule=rule)` — 맵퍼가 `rule` 인자를 선언한 경우) 맵퍼가 셋을 구분합니다.

| 룰                                  | `trigger_table`         | 다시 파생하는 대상                 |
| ----------------------------------- | ------------------------- | ---------------------------------- |
| `dt_log_to_dt_map`                | `dt_log`                | 방금 들어온 행                     |
| `dt_job_attribution_to_dt_map`    | `dt_job_attribution`    | 그`dt_job`의 모든 행             |
| `eqp_frame_attribution_to_dt_map` | `eqp_frame_attribution` | 그`dt_eqp`+`product`의 모든 행 |

2·3번은 편의 기능이 아닙니다. 귀속과 프레임 귀속은 **자기 일정으로 도착**하므로, 그것에 게이트된 행은 `dt_log` 시점에 보류되고 **다시 들여다보는 장치가 없으면 영원히 안 봅니다** — 결번 40%가 일시적 손실이 아니라 영구 손실이 되는 경로가 이것입니다.

트리거 테이블이 소스 테이블이 아니므로(페이로드가 귀속 행입니다) 룰이 `derivation_source_table`·`derivation_source_column`·`derivation_value_columns`·`derivation_origin_columns`를 **선언**합니다. 워커는 모르는 룰 필드를 그대로 통과시킵니다(`load_chain_rules`가 `data["rules"]`를 그대로 반환).

⚠️ **스케줄러나 스윕을 만들지 않은 이유**: "언제 도는가"가 "언젠가"가 되기 때문입니다. 트리거를 요구한 목적이 바로 그것이었습니다.

### 6.2 세 겹 게이트 — 셋 다 풀려야 행이 생긴다

확정 lot · 확정 slot · `dt_frame`. 하나라도 없으면 **행을 만들지 않습니다.** `dt_log` 행이 기록이므로 잃는 것이 없고, 반대로 빈 맵 키를 가진 행은 **어느 맵에도 안 나타난 채 쌓여** 나중에 버그인지 정상인지 아무도 구분하지 못합니다.

**절대 완화하면 안 되는 거절 셋**

| 거절                                                 | 이유                                                                                                                                                                                                                                                                                                                                 |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 저장된`dt_lot`/`dt_slot`으로 **폴백 금지** | `virtual_join_rules.json`이 스스로 적어 둔 사실 — 결번 40%, **있는데 틀린 것 10%**. 맵 키에서 이것은 품질 문제가 아니라 **오염**입니다: 틀린 lot은 셀을 **다른 lot의 맵**에 써 넣고, 셀 개수는 양쪽이 동일합니다. `_forbidden_fallback_columns`가 투영 허용목록에서 아예 제외해 **구조적으로** 막습니다 |
| `core_frame`으로 **대체 금지**               | 다른 프레임입니다(사용자 판정). 옆 축에서 값을 빌려 오는 것이 바로 "완벽히 정렬됐는데 값이 전부 틀린 화면"을 만든 그 대체입니다                                                                                                                                                                                                      |
| 증거가**엇갈리면 고르지 말고 거절**            | `frame_disagreement`. `html_topology_parser`가 앵커 둘을 지키고 엇갈리면 거절하는 규율과 같습니다                                                                                                                                                                                                                                |

보류는 **이름 붙은 집계**이고 행 단위로는 조용합니다. 그리고 이유가 **쪼개져** 나옵니다 — `attribution_missing`과 `frame_missing`은 **서로 다른 수리**라서 합친 숫자는 어느 쪽을 고쳐야 하는지 알려 주지 못합니다. 두 숫자는 0일 때도 찍힙니다(빠진 이유는 "검사하지 않았다"와 구분되지 않으므로).

### 6.3 정체성 — `dt_job`은 **출처**이지 키가 아니다

셀의 정체성은 **맵 키(`map_key_columns`) + 좌표**입니다. `dt_job`은 값과 함께 실려 다니는 **출처**입니다. 그래야 같은 물리 다이가 같은 행이 되어 레이어링·우선순위·**사람 교정을 덮지 않는 규칙**이 그대로 적용됩니다. `dt_job`이 키에 있으면 한 다이 위의 두 잡이 **영원히 합쳐지지 않는 두 행**이 되고, 맵 뷰는 존재하지도 않는 "어느 잡이 이기는가" 규칙을 필요로 하게 됩니다.

컬럼 이름은 **어디에도 하드코딩하지 않습니다** — 정체성은 타깃의 `map_key_columns`, 좌표는 `composite_key_source`에서 정체성을 뺀 나머지, 확정 컬럼과 프레임은 가상 조인 규칙의 `expose`, 조인 키는 그 규칙의 `join_key`에서 **호출 시점에** 읽습니다. 맵 정체성 문자열은 `map_meta_registrar.compose_map_id`가 만듭니다(등록과 조회가 같은 정체성을 만들어야 하므로 두 번 구현하지 않습니다).

🔴 **가상 조인은 `load_verified_rules`로만 읽습니다.** `load_virtual_join_rules`는 선언의 *모양*만 봅니다. 유일 인덱스가 검증되지 않은 규칙은 팬아웃할 수 있고, 여기서의 팬아웃은 느린 질의가 아니라 **임의의 lot 하나가 정체성을 차지하는 것**입니다.

### 6.4 좌표 — 변환은 하나뿐

`dt_log`의 좌표는 장비가 쓴 8개 프레임 중 하나(`dt_frame`)에 있고, 맵의 정본 프레임은 그 맵의 `wafer_map_metadata`가 선언합니다. 그 사이를 옮기는 것은 **`map_overlay.make_frame_transform` 하나**입니다(사본이 `bonding_plan.py`에 있었다가 같은 이유로 삭제됐습니다). 소스 메타는 타깃 메타에서 **회전과 면만** 바꾼 것입니다 — 같은 물리 웨이퍼이고, 격자 치수나 phys 서명이 다르면 변환기가 거절하므로 강제입니다.

타깃 메타가 없으면 **정본 프레임을 지어내지 않고 보류**합니다(`target_meta_missing`). "첫 쓰기가 정본을 정한다"는 정본 프레임을 **도착 순서의 부산물**로 만듭니다.

### 6.5 철회 — 체인이 못 하는 일(퍼지)의 답

체인은 맵 셀을 **업서트만** 할 수 있고 **퍼지는 못 합니다** — `replace_map`은 배치에 있는데 `chain_ingestion_worker`가 배치를 직접 만들면서 절대 설정하지 않습니다(`:437-441`). **이것이 이 룰이 꺼져 있던 이유였습니다.**

🔴 **`replace_map`은 답이 아닙니다.** `crud.derive_replace_map_scope`는 모든 스코프 키가 **맵 키 계약 안**일 것을 강제하므로 퍼지는 **맵 전체 단위로만** 잡힙니다. 확정된 정체성에서는 **한 lot/slot 맵을 여러 `dt_job`이 먹일 수 있으므로**, 맵 단위 퍼지는 첫 잡을 고치려다 둘째 잡의 셀을 지웁니다.

답은 `graph_stale_edges`가 이미 쓰는 모양 — **그 소스가 소유한 것의 적극 선택**입니다. `dt_job`이 모든 파생 셀에 실려 있으므로 "이 잡이 어떤 셀을 찍었나"가 평범한 인덱스 술어가 됩니다.

```python
plan = dt_map_derivation.plan_retraction(db, "dt_map", "dt_job", job, derived_keys)
print(dt_map_derivation.format_retraction_summary(plan))   # 기본 dry-run
dt_map_derivation.apply_retraction(db, plan)               # 계획한 것만, 다시 계산하지 않음
```

| 보증                               | 방법                                                                                                                   |
| ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| 기본 dry-run                       | `plan_retraction`은 아무것도 쓰지 않습니다                                                                           |
| 사람 교정은**삭제하지 않음** | `cell_overwrites`에 걸린 행은 `protected`로 빠집니다 — 덮지 않는 규칙을 **삭제로 확장**한 것입니다          |
| 예산 가드                          | 소유분의`max_fraction`을 넘으면 `declined` + 이유. 틀린 프레임·틀린 귀속이 정확히 "거의 전부가 낡음"처럼 보입니다 |
| 계획과 실행의 불일치 없음          | `apply_retraction`은 `delete_row_ids`만 지우고 재계산하지 않습니다. 달라질 수 있는 dry-run은 장식입니다            |

⚠️ 철회는 **체인 워커에 배선되어 있지 않습니다.** 워커가 배치를 직접 만들기 때문이며, 의도적으로 **직접 호출**하는 연산입니다.

### 6.6 규모 — 켜기 전에 필요한 것

🔴 **프레임 트리거의 팬아웃을 먼저 재십시오.** `eqp_frame_attribution`은 (장비, 제품)으로 키가 잡혀 있어 **한 행이 그 조합의 모든 잡을 다시 변환**합니다. 개발 픽스처 실측(2026-08-04): 한 행이 **`dt_log` 2,892행 · 40잡 = 테이블의 33%**. `expand_trigger`가 가져오기 **전에** `frame_trigger_scope`로 크기를 재고 `SCOPE_ROW_CAP`을 넘으면 `scope_too_large`로 거절합니다.

🔴 **인덱스 전제가 아직 충족되지 않았습니다.** `dt_log`에는 `dt_job` 인덱스도 `(dt_eqp, product)` 인덱스도 없습니다(2026-08-04 실측 — `business_key_val`과 `row_id`뿐). 1,000만 행 기준에서 두 리비지트 트리거는 전부 순차 스캔입니다. [`server/migrations/add_dt_log_trigger_indexes.sql`](file:///c:/Users/kk980/Developments/assyManager/server/migrations/add_dt_log_trigger_indexes.sql)이 셋을 추가하며 **아직 실행되지 않았습니다.**

⚠️ `business_key_val`(= `dt_job_dt_x_dt_y`)의 접두 검색으로 대신할 수 없습니다. 접두 술어는 **C 콜레이션에서만** 평범한 btree를 씁니다.

### 6.7 배포 형태 — `mappers/`는 gitignore입니다

추적되는 것은 `.sample`뿐이고 살아 있는 `dt_map_mapper.py`는 **이 머신에만, 어느 저장소에도 없이** 존재합니다(보드 O7). 둘은 **바이트 동일**하게 유지하며 `test_the_mapper_is_kept_byte_identical_with_its_sample`가 그것을 못박습니다 — 아무것도 동기화해 주지 않으므로 `diff`로 볼 수 있게 만드는 것이 최선입니다. 한쪽만 고치면 **그 변경은 이 머신 밖에 존재하지 않습니다.**
