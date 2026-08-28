# server/ 파일 지도 — 하는 일과 «진입점에서 닿는가»

> 총괄 실측 2026-08-28. 파일 «151» · 닿음 «99» · 안 닿음 «52» (547,415 B)
> 뿌리: main · run_chain_worker · run_watcher · run_auto_update · chain_ingestion_worker
>       parsers/directory_watcher · ledger/backfill · ledger/setup · setup/*
> ⚠️ tests · scripts · migrations 는 «뿌리가 아니라» 별도 실행 도구입니다
> 🔴 상대 임포트(`from .store import …`)를 패키지 경로로 «풀어서» 셌습니다 — 안 풀면 쓰기 경로가 고아로 찍힙니다


## (최상위)

| | 파일 | 크기 | 수정 | 하는 일 |
|---|---|---:|---|---|
| ✅ | `admin_auth` | 22,249 | 2026-07-31 | Shared-token gate for the ``/admin/*`` surface. |
| ✅ | `alignment_view_service` | 4,146 | 2026-08-19 | Shared, read-only alignment-view service for HTTP routes and chain mappers. |
| ✅ | `audit_cache` | 33,076 | 2026-08-11 | The in-memory projection behind `GET /audit_logs/recent`. |
| 🔴 | `audit_changeset` | 20,442 | 2026-08-18 | The CHANGESET shape of an audit row: one row per WRITE, not one per COLUMN. |
| ✅ | `audit_history` | 12,149 | 2026-08-11 | Row/cell audit history paging - the ceiling on `/history` fetches. |
| ✅ | `bonding_plan` | 55,845 | 2026-08-05 | 본딩 실험계획(M1) — 역할 바인딩 config 로더 + 코어 집계 코어. |
| 🔴 | `chain_bindings` | 11,455 | 2026-08-11 | Which column of a table carries the DT job identity — READ, never assumed. |
| ✅ | `chain_ingestion_worker` | 88,253 | 2026-08-27 |  |
| ✅ | `chain_key_gate` | 10,848 | 2026-08-12 | A chain may not emit a row whose key columns are not filled. ONE gate, not seven. |
| ✅ | `chain_replay` | 57,743 | 2026-08-13 | Chain Replay R1 (rule re-application) + R2 (stale source withdrawal) |
| ✅ | `column_filter` | 9,921 | 2026-08-05 | The AG-Grid filter DSL -> SQLAlchemy translator, in a module every process can import. |
| ✅ | `config_backup` | 17,487 | 2026-08-16 | Weekly snapshots of ``server/config/``, and the check that says one is missing. |
| ✅ | `config_resolve_report` | 59,213 | 2026-08-27 | 「내 config가 먹었는가」 — 선언을 세 모집단으로 나눠 **이름으로** 답한다. |
| ✅ | `db_safety` | 22,203 | 2026-08-13 | A test process must not be able to reach a real database. [board #16a] |
| 🔴 | `dt_frame_transform` | 4,040 | 2026-08-10 | Derive portable X/Y/sign/offset equations from confirmed DT frame metadata. |
| ✅ | `dt_map_derivation` | 43,842 | 2026-08-25 | The dt_log -> dt_map derivation: the gate, the identity, the frame, the retraction. |
| ✅ | `effort_metric` | 7,752 | 2026-07-29 | Interaction-effort instrument — config side. |
| 🔴 | `enrichment_actions` | 17,472 | 2026-08-15 | Project open Enrichment work into bounded, walkable ontology action nodes. |
| ✅ | `enrichment_analysis` | 36,619 | 2026-08-05 | Read-only enrichment analytics: [④] why a gap exists, [②] which judgement |
| ✅ | `enrichment_backfill` | 22,966 | 2026-08-16 | Retroactive enrichment backfill - apply an enrichment rule to source rows |
| ✅ | `enrichment_candidates` | 50,823 | 2026-08-05 | [Enrichment ①] A single candidate is a confirmation, not a judgement. |
| ✅ | `enrichment_config` | 89,781 | 2026-08-27 | Enrichment Queue 규칙 로더/검증기 (docs/spec/ENRICHMENT_QUEUE_SPEC.md §5). |
| ✅ | `enrichment_mapper` | 16,896 | 2026-08-05 | Enrichment Queue generic dedup mapper (docs/spec/ENRICHMENT_QUEUE_SPEC.md §6). |
| ✅ | `event_constants` | 12,456 | 2026-08-07 | 프로세스 간 이벤트 공용 상수 — 내부 이벤트(POST /internal/events/*) + 아웃박스 제어 이벤트. |
| ✅ | `frame_confirmation` | 46,945 | 2026-08-16 | 좌표계 확정 기록 — 맵 정렬 스펙 §0.2 층 ⑧ (사슬에서 **쓰는 유일한 층**). |
| ✅ | `health` | 18,091 | 2026-07-28 | The /health contract. |
| ✅ | `ingestion_activity` | 7,063 | 2026-07-26 | [Heavy Lane P1] 진행 중 파일 인제션 스냅샷 레지스트리 (웹서버 프로세스 인메모리). |
| ✅ | `ingestion_checkpoint` | 28,513 | 2026-08-13 | [P2] 파일 인제션 오프셋 체크포인트 + 파일 시그니처 dedup. |
| ✅ | `internal_event_client` | 16,431 | 2026-08-04 | The one way a process on this box talks to the web server on this box. |
| ✅ | `keyset_scan` | 3,449 | 2026-08-16 | The ONE keyset page walk over a dynamic table. |
| 🔴 | `launcher_args` | 9,675 | 2026-08-04 | Command-line parsing for ``run_decoupled_app.py`` - the refusal half. |
| ✅ | `ledger` | 1,683 | 2026-08-13 | The canonical ledger - `ledger_events` and the translators that feed it. |
| ✅ | `ledger_admin` | 45,754 | 2026-08-27 | admin으로 소스를 원장에 잇고 어휘를 늘린다 — 문법 검증과 저장(1단·3단). |
| ✅ | `ledger_api` | 1,305 | 2026-08-23 | Read-side modules behind the ledger console's HTTP routes. |
| ✅ | `ledger_explorer` | 7,215 | 2026-08-27 | Bounded, read-only graph projection of the canonical ledger lineage. |
| ✅ | `ledger_trace` | 84,223 | 2026-08-27 | Lot lineage trace over the canonical ledger — the resolver, the lookup, the walk. |
| ✅ | `ledger_trace_router` | 13,803 | 2026-08-27 | The ledger read routes — ten of them, and none is the pair this line used to name. |
| ✅ | `main` | 305,779 | 2026-08-27 |  |
| ✅ | `map_alignment` | 471,436 | 2026-08-25 | 맵 정렬 채점 — 후보 8개를 **한 번에** 채점해 한 payload로 낸다 (스펙 §0.2 층 ⑤·⑥·⑦). |
| ✅ | `map_meta_registrar` | 16,312 | 2026-08-06 | Auto-registration of `wafer_map_metadata` rows for ingestion-created maps (M3). |
| ✅ | `map_overlay` | 163,825 | 2026-08-25 | 범용 맵 오버레이 (S1') — 임의의 맵을 임의의 맵 캔버스 위에 정렬해 겹쳐 보는 인프라. |
| ✅ | `map_preset_routing` | 25,070 | 2026-07-30 | [F5] Load-time preset routing — WHICH physical spec a map opens with. |
| 🔴 | `mappers` | 33 | 2026-06-07 |  |
| 🔴 | `migrations` | 61 | 2026-06-13 |  |
| ✅ | `notation_norm` | 39,702 | 2026-08-04 | WF/lot/slot notation normalization - a DECLARATION about a column, applied at |
| ✅ | `outbox_expand` | 14,168 | 2026-08-16 | [OUTBOX-4] Turning a collapsed outbox event back into rows. |
| ✅ | `paths` | 7,493 | 2026-08-16 | Single override point for the server's **data root**. |
| ✅ | `process_supervisor` | 52,933 | 2026-08-04 | Child-process supervision for the decoupled launcher. |
| 🔴 | `product_tables` | 11,492 | 2026-08-16 | Product-owned table declarations — **the** single definition. |
| ✅ | `retroactive` | 24,432 | 2026-08-16 | Retroactive (backfill) operation registry. |
| ✅ | `run_auto_update` | 43,993 | 2026-08-16 |  |
| ✅ | `run_chain_worker` | 2,497 | 2026-07-29 |  |
| ✅ | `run_watcher` | 18,276 | 2026-08-04 |  |
| ✅ | `schema_drift` | 41,987 | 2026-08-19 | Does this database carry the schema this build expects? |
| 🔴 | `source_fixtures` | 436 | 2026-08-16 | Deterministic source-table fixtures used before ingestion. |
| 🔴 | `trace_fixture` | 1,000 | 2026-08-01 | Synthetic core-material trace fixture (docs/spec/TRACE_FIXTURE_SPEC.md). |
| ✅ | `transfer_plan` | 218,352 | 2026-08-14 | Universal Transfer Plan (M2) — 전사(轉寫) 프레임워크: stage 선언 로더 + 가용 엔진 + 계획 검증. |
| ✅ | `value_suggest` | 56,927 | 2026-08-18 | Unique-value lookup (F3) — the primitive every input suggestion sits on. |
| ✅ | `verified_join_contract` | 8,548 | 2026-08-17 | Immutable hand-off produced only after virtual-join physical verification. |
| ✅ | `virtual_join_config` | 41,453 | 2026-08-17 | Virtual join 선언 로더/검증기 ― **UNIQUE 인덱스가 없으면 거부한다.** |
| ✅ | `virtual_join_executor` | 38,108 | 2026-08-12 | Virtual join 실행기 ― 선언을 **LEFT 조인 한 방**으로 바꾸고 행 페이로드에 붙인다. |

## database/

| | 파일 | 크기 | 수정 | 하는 일 |
|---|---|---:|---|---|
| ✅ | `database/config_watcher` | 8,237 | 2026-07-29 |  |
| ✅ | `database/context` | 2,430 | 2026-08-07 |  |
| ✅ | `database/crud` | 253,584 | 2026-08-18 |  |
| ✅ | `database/database` | 16,444 | 2026-08-17 |  |
| ✅ | `database/models` | 69,951 | 2026-08-18 |  |
| ✅ | `database/schemas` | 17,711 | 2026-08-12 |  |

## ledger/

| | 파일 | 크기 | 수정 | 하는 일 |
|---|---|---:|---|---|
| ✅ | `ledger/backfill` | 39,052 | 2026-08-21 | The backfill drivers - cursor loops that never cut a molecule in half. |
| 🔴 | `ledger/chain_mapper` | 16,279 | 2026-08-18 | Trusted Chain-mapper calls for the existing Ledger-owned execution loop. |
| ✅ | `ledger/column_stats` | 13,124 | 2026-08-19 | What the physical table ACTUALLY holds, for the authoring screen's column pickers. |
| ✅ | `ledger/config` | 66,080 | 2026-08-27 | `ledger_config.json` - the translator declarations, loaded and VALIDATED. |
| ✅ | `ledger/config_authoring` | 107,196 | 2026-08-27 | What one declaration FORCES, and what a person still genuinely has to answer. |
| ✅ | `ledger/config_drafts` | 37,757 | 2026-08-22 | Filesystem working drafts for the Ledger v2 ontology explorer. |
| ✅ | `ledger/config_explorer` | 63,337 | 2026-08-21 | Immutable read model for the Ledger v2 ontology configuration explorer. |
| ✅ | `ledger/config_explorer_service` | 48,100 | 2026-08-21 | Cached application service for the ontology config explorer. |
| ✅ | `ledger/dry_run` | 10,795 | 2026-08-18 | 「이 선언이 낳을 원자」 - the REAL translators, over a connection that cannot write. |
| ✅ | `ledger/envelope` | 15,851 | 2026-08-27 | The 7-field envelope of `CANONICAL_LEDGER_DESIGN.md` §3, as one Python object. |
| 🔴 | `ledger/examples` | 82 | 2026-08-16 | Copyable ledger translator examples; no module here is runtime-registered. |
| ✅ | `ledger/gate` | 30,156 | 2026-08-27 | The translation gate: it refuses at the door, and it COUNTS. |
| ✅ | `ledger/implementations` | 8,284 | 2026-08-19 | Discover the executable implementations the repository actually ships. |
| ✅ | `ledger/ledger_frame` | 11,935 | 2026-08-17 | The one pandas boundary between a Chain mapper and the existing Ledger gate. |
| ✅ | `ledger/observability` | 19,334 | 2026-08-16 | Heartbeat note and lag report - birth conditions, not follow-ups. |
| 🔴 | `ledger/profile_chain_mapper` | 19,620 | 2026-08-17 | Canonical Profile evaluation inside the registered Chain-mapper boundary. |
| 🔴 | `ledger/profile_lookup_adapters` | 4,650 | 2026-08-17 | Registered read-only lookup capabilities for canonical Profile execution. |
| ✅ | `ledger/roleframe` | 59,484 | 2026-08-23 | Ledger v2 Stage 4 EventFrame -> RoleFrame -> LedgerFrame compiler. |
| ✅ | `ledger/runtime_v2` | 15,762 | 2026-08-21 | Ledger v2 Stage 6 execution adapter over the existing gate/store transaction. |
| ✅ | `ledger/schema` | 23,407 | 2026-08-18 | Physical DDL for `ledger_events` and the translator cursor. ONE spelling, here. |
| ✅ | `ledger/setup` | 14,926 | 2026-08-19 | The Ledger setup boundary: load one config, compile one snapshot, hand over registries. |
| ✅ | `ledger/setup_bundle` | 106,509 | 2026-08-27 | Pure Ledger authoring bundle schema and single-file loader. |
| ✅ | `ledger/setup_registry` | 45,810 | 2026-08-22 | Pure Ledger v2 registry compiler and immutable setup snapshot. |
| ✅ | `ledger/source_contract` | 16,060 | 2026-08-27 | Compile one ledger source into the contract an operator actually needs. |
| ✅ | `ledger/source_preparation` | 48,328 | 2026-08-22 | Ledger v2 Stage 5 pandas source-preparation boundary. |
| ✅ | `ledger/source_profile` | 59,138 | 2026-08-21 | Public Source Ontology Profile model and validation contract. |
| ✅ | `ledger/source_profile_builtins` | 6,655 | 2026-08-27 | Built-in registration data for Source Ontology Profile schema version 1. |
| ✅ | `ledger/store` | 26,566 | 2026-08-21 | Writing atoms and moving the cursor - in ONE transaction, per the brief's risk 1. |
| ✅ | `ledger/uuid7` | 5,300 | 2026-08-13 | Monotonic UUIDv7 (RFC 9562 §5.7) - the ledger's `id`, and therefore its watermark. |

## ledger_api/

| | 파일 | 크기 | 수정 | 하는 일 |
|---|---|---:|---|---|
| ✅ | `ledger_api/entity_references` | 8,685 | 2026-08-27 | 「이 die 는 어느 통에 담겨 있나」 — read from the DECLARATION, never decided here. |
| ✅ | `ledger_api/finding_kinds` | 15,230 | 2026-08-27 | The finding-kind registry: what a defect kind IS, as data rather than as a branch. |
| ✅ | `ledger_api/ledger_subgraph` | 41,735 | 2026-08-28 | Unified, bounded evidence subgraph over evidence and physical referents. |
| ✅ | `ledger_api/mechanism_gate` | 16,518 | 2026-08-23 | The MECHANISM gate — 「그 요인에서 이 불량으로 가는 경로가 선언돼 있는가」. |
| ✅ | `ledger_api/ontology_config_explorer_router` | 10,220 | 2026-08-21 | Admin API for the Ledger v2 ontology config explorer. |

## mappers/

| | 파일 | 크기 | 수정 | 하는 일 |
|---|---|---:|---|---|
| 🔴 | `mappers/base` | 558 | 2026-06-09 |  |
| 🔴 | `mappers/core_alignment_mapper` | 11,326 | 2026-08-11 | Config-driven primary-core automatic core-frame confirmation. |
| 🔴 | `mappers/core_usage_mapper` | 8,358 | 2026-08-11 | dt_inventory core equations -> scoped physical-core usage-map replacements. |
| 🔴 | `mappers/dt_alignment_metadata_mapper` | 10,090 | 2026-08-11 | dt_log -> wafer_map_metadata automatic DT-frame chain mapper. |
| 🔴 | `mappers/dt_inventory_metadata_mapper` | 5,615 | 2026-08-11 | wafer_map_metadata(dt_log/dt_job) -> dt_inventory.dt_frame identity mapper. |
| 🔴 | `mappers/dt_map_mapper` | 11,248 | 2026-08-11 | dt_log -> dt_map chain mapper: the adapter for THREE trigger rules, one derivation. |
| 🔴 | `mappers/dt_standard_map_mapper` | 10,460 | 2026-08-13 | dt_inventory equations -> one source-retracted standard-coordinate dt_map batch. |
| 🔴 | `mappers/inv_man` | 1,208 | 2026-07-28 |  |
| 🔴 | `mappers/ledger_dt_job_mapper` | 1,542 | 2026-08-19 | Ledger v2 Role mapper for one dt_job's worth of dt_log rows. |
| 🔴 | `mappers/ledger_v2_dt_job_mapper` | 2,146 | 2026-08-21 | Ledger v2 Role mapper for one dt_job's worth of dt_log rows. |
| 🔴 | `mappers/ledger_v2_lot_event_role_mapper` | 15,346 | 2026-08-21 | Ledger v2 Role mapper for one prepared ``lot_event`` source event. |
| 🔴 | `mappers/production_mapper` | 2,257 | 2026-07-28 |  |
| 🔴 | `mappers/utils` | 906 | 2026-06-09 |  |

## migrations/

| | 파일 | 크기 | 수정 | 하는 일 |
|---|---|---:|---|---|
| 🔴 | `migrations/add_business_key_unique_index` | 35,195 | 2026-08-13 | D3 - make "one row per business key" an invariant the DATABASE enforces. |
| 🔴 | `migrations/add_frame_confirmation` | 11,067 | 2026-08-06 | 좌표계 확정 기록(스펙 §0.2 층 ⑧)의 물리 스키마 — **추가 전용 · 멱등**. |
| 🔴 | `migrations/add_ledger_entity_catalog_indexes` | 2,706 | 2026-08-15 | Indexes for the global Ledger Graph entity catalogue and entity subgraph. |
| 🔴 | `migrations/add_ledger_events` | 4,410 | 2026-08-13 | Physical schema for the canonical ledger - **additive only, idempotent, partitioned**. |
| 🔴 | `migrations/add_ledger_occurred_at_basis` | 4,146 | 2026-08-18 | Give the ledger a place to say WHERE an atom's time came from. |
| 🔴 | `migrations/add_ledger_refusal_reasons` | 6,585 | 2026-08-13 | `ledger_translator_cursor.refusal_reasons` - the breakdown of a number that already |
| 🔴 | `migrations/add_ledger_source_events` | 9,463 | 2026-08-15 | Add first-class source-event identity to the canonical ledger, safely. |
| 🔴 | `migrations/align_indexes_to_declarations` | 18,774 | 2026-08-14 | Make an EXISTING database's dynamic-table indexes match what `table_config.json` |
| 🔴 | `migrations/drop_graph_storage` | 10,069 | 2026-08-14 | Retire the old graph branch's STORAGE: drop `graph_nodes`, `graph_edges` and |
| 🔴 | `migrations/drop_redundant_layering_indexes` | 21,795 | 2026-08-13 | Retire indexes on `cell_sources` / `cell_overwrites` / `audit_logs` that no |
| 🔴 | `migrations/migrate_jsonb_numeric` | 5,106 | 2026-06-01 |  |
| 🔴 | `migrations/normalize_schema` | 14,840 | 2026-07-25 | JSONB → Normalized Schema Migration Script |

## parsers/

| | 파일 | 크기 | 수정 | 하는 일 |
|---|---|---:|---|---|
| 🔴 | `parsers/advanced_ingester` | 25,051 | 2026-08-16 |  |
| 🔴 | `parsers/custom_parser_template` | 2,234 | 2026-08-19 | [함수형 커스텀 파서] 이 파일의 계약은 **`parse_file(file_path) -> list[dict]` 함수 하나**다. |
| ✅ | `parsers/directory_watcher` | 178,031 | 2026-08-19 |  |
| 🔴 | `parsers/html_topology_parser` | 35,639 | 2026-08-04 |  |
| 🔴 | `parsers/pipeline_base` | 5,172 | 2026-08-19 |  |
| 🔴 | `parsers/std_parser` | 10,704 | 2026-07-25 | 표준 파서 (Std Parser) — 무스크립트 기본 인제션 경로. |
| 🔴 | `parsers/void_sat_format` | 29,405 | 2026-08-18 | The SAT void format, and the gate that refuses a row it cannot key. |
| 🔴 | `parsers/voids_json_format` | 20,936 | 2026-08-18 | Parse the external ``WAFERID/WORK_DATETIME/voids.json`` feed. |

## setup/

| | 파일 | 크기 | 수정 | 하는 일 |
|---|---|---:|---|---|
| ✅ | `setup/init_db` | 2,592 | 2026-07-26 |  |
| ✅ | `setup/reset_db` | 2,455 | 2026-07-26 |  |
| ✅ | `setup/seed_data` | 5,260 | 2026-07-26 |  |
| ✅ | `setup/setup_workspace` | 1,370 | 2026-07-26 |  |

## source_fixtures/

| | 파일 | 크기 | 수정 | 하는 일 |
|---|---|---:|---|---|
| 🔴 | `source_fixtures/lot_split_merge` | 12,916 | 2026-08-16 | Generate exact-schema ``lot_event`` and ``process_event`` source rows. |

## trace_fixture/

| | 파일 | 크기 | 수정 | 하는 일 |
|---|---|---:|---|---|
| 🔴 | `trace_fixture/baseline_trace` | 7,976 | 2026-08-02 | A baseline reasoner over what the system ACTUALLY knows, for scoring. |
| 🔴 | `trace_fixture/emit` | 6,524 | 2026-08-01 | Writes a generated batch out: ingestion CSVs, and the five oracle files. |
| 🔴 | `trace_fixture/frames` | 4,806 | 2026-08-01 | The eight coordinate frames (4 rotations x 2 flips), and what they can hide. |
| 🔴 | `trace_fixture/scoring` | 7,675 | 2026-08-02 | Scores an answer set against the oracle. |
| 🔴 | `trace_fixture/world` | 36,424 | 2026-08-01 | Builds one batch of the trace fixture world. |

## utils/

| | 파일 | 크기 | 수정 | 하는 일 |
|---|---|---:|---|---|
| ✅ | `utils/auto_update_control` | 4,496 | 2026-07-26 | Auto Update 수집기 active 상태 제어 파일(auto_update_control.json)의 공용 IO 모듈. |
| ✅ | `utils/coordinate_transformer` | 10,233 | 2026-07-23 |  |
| ✅ | `utils/heartbeat` | 12,927 | 2026-07-27 | Progress heartbeats for the background worker processes. |
| ✅ | `utils/logger` | 10,059 | 2026-08-07 |  |
| ✅ | `utils/payload_helper` | 1,240 | 2026-07-21 |  |
| ✅ | `utils/physical_wafer_engine` | 4,182 | 2026-07-21 |  |
| ✅ | `utils/time_format` | 4,621 | 2026-08-12 | Timestamp formatting shared by the web server and the background workers. |