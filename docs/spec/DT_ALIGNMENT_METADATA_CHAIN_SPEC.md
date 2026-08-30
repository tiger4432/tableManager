# DT alignment metadata chain

> **Status:** Living · **Last-verified:** 2026-08-30 (**§S2 머리 한 줄만** — 이 규칙이 오늘 모든 배치에서 거절한다) · 직전 2026-08-09 · **Owner:** Lead PM

## 목적

정렬된 DT frame을 `frame_confirmation` 이력에 기록하지 않는다. `dt_log`의 `dt_job`별 DT map metadata를
`wafer_map_metadata(target_table="dt_log", map_id=dt_job)`에 기록한다. `dt_map`은 이 단계의 대상이 아니라
나중에 표준 좌표로 재생성할 파생 projection이다.

```text
dt_log transaction (one dt_job)
  -> dt_log_to_dt_alignment_metadata chain
  -> alignment-view service (same payload contract as GET /api/maps/alignment/view)
  -> map_alignment.confirmed_meta_for
  -> wafer_map_metadata(dt_log/dt_job).grid_metadata
  -> dt_metadata_to_dt_inventory chain (explicit opt-in second hop)
  -> dt_inventory(dt_job).dt_frame (the same serialized JSON metadata)
```

## S2: metadata -> inventory identity projection

> 🔴 **[2026-08-30 measured] `enabled` is not `running`.** This rule refuses on every
> batch as shipped — its job column can be neither declared nor derived — so the
> paragraph below describes the contract, not what happens today. Mechanism and the
> pending ruling: [architecture/DT_CORE_FRAME_CHAINS "Active chains" 2](../architecture/DT_CORE_FRAME_CHAINS.md).

`dt_metadata_to_dt_inventory` is an enabled batch rule from `wafer_map_metadata`
to `dt_inventory`. It accepts only metadata rows whose `target_table` is `dt_log`,
uses `map_id` as `dt_job`, and copies the JSON object in `grid_metadata` as a
canonical serialized JSON string to `dt_inventory.dt_frame`. `table_config` has
no native `json` dynamic-column type: `dt_frame` is deliberately declared
`string` and stored as PostgreSQL `text`. A malformed payload, another metadata target, or a
duplicate job in one batch is a no-op.

The generic chain worker normally rejects every event whose source is
`chain_ingestion`. S2 declares `allow_chain_trigger: true` explicitly. The worker
filters chain-produced events per rule (not merely per trigger table), and rejects
a cycle made of opt-in edges while loading the rule configuration. The approved
graph is therefore finite: `dt_log -> wafer_map_metadata -> dt_inventory`.

No S2 write derives `dt_map`, changes a coordinate, or removes anything from a
map — neither `replace_map` nor `retract`.  (`retract` added 2026-08-13: it is the
strategy S3 uses on `dt_map`, and this boundary statement covers it too.)

## 규칙

`server/config/chain_rules.json`의 `dt_log_to_dt_alignment_metadata`가 배치 체인이다.

- 정렬 규칙, source map table, metadata target table은 rule 설정으로 선언한다.
- 현재 선언: `alignment_rule=dt_frame_confrimation`, `map_table=dt_log`, `metadata_target_table=dt_log`.
- 유효다이 reference는 rule의 `reference_by_job_pattern` 순서 목록에서 선택한다. 현재 `dt_job`에
  `SYN`이 포함되면 `valid_die_ref:PRD-A_DT13`을 사용한다. 이는 `wafer_map_metadata`에 저장된 PRD map_id와 정확히 같은 키다. 매칭하지 않는 job은 기준을 추측하지 않고 no-op이다.
- 같은 `dt_job` ingest는 한 transaction으로 outbox에 들어온다는 전제에서, mapper는 batch의 완전한
  decision key만 처리한다. 불완전한 key는 범위를 넓혀 추측하지 않고 no-op이다.
- 결과 쓰기는 `source_name="chain_ingestion"`이다. 따라서 `user` metadata는 기존 source priority로
  더 높은 우선순위를 유지한다.

## 자동 확정 gate

다음 조건을 모두 만족한 alignment-view만 metadata로 투영한다.

- `state == "scored"` 및 winner 존재
- `ruling.metric == "index"`, `ruling.index_axis == "ranking"`
- `geometry_assumed == false`, `thresholds_defaulted == false`
- source/reference/score payload가 truncated되지 않음
- 완전한 reference metadata 및 valid-die cells 존재

따라서 `dt_index`가 비어 `index_axis="absent"`가 된 실행은 margin을 낮추어 통과시키지 않으며,
`confirmed_meta_for()`도 호출하지 않는다.

### Reference-geometry bootstrap exception

Only the S1 rule may opt into `geometry_bootstrap: "reference_only"`. It permits
`geometry_assumed == true` solely when every source-map geometry is absent and a
resolved, explicit `reference_spec` is present. It does not permit partial source
geometry, a missing/implicit reference, defaulted thresholds, truncation, or any
failure of the other gates. This bootstrap for a new `dt_job` does not weaken
normal automatic confirmation.

## 구현 경계

- `server/alignment_view_service.py`는 public API route와 mapper가 공유하는 read-only facade다.
  HTTP loopback을 사용하지 않아 같은 DB snapshot에서 UI와 동일한 scoring payload를 얻는다.
- `server/mappers/dt_alignment_metadata_mapper.py`는 gitignore된 live mapper이며, 추적되는
  `.sample`과 byte-identical이어야 한다.
- frame/placement/origin 계산은 mapper가 재구현하지 않고 `map_alignment.confirmed_meta_for()`만 사용한다.
- S2 `dt_inventory.dt_frame` serialized-JSON metadata 복제는 이 계약의 일부다. `dt_log + dt_inventory -> dt_map` 파생은 아직 아니다 — 그쪽은 S3이고, **`replace_map`이 아니라 `retract`을 쓴다**(2026-08-13 `4d5198c`. 이 줄은 그전까지 `replace_map`이라 적고 있었다). 계약은 [architecture/DT_CORE_FRAME_CHAINS](../architecture/DT_CORE_FRAME_CHAINS.md).
