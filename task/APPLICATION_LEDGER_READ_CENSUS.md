# 원장 가상화 확인 1 · 2 — 원장을 읽는 자리 · 원장에만 있는 이력 (응용 C, 2026-10-27)

지시: `task/DESIGN_ORDERS.md` 맨 위(e377ca07a) «10-27 묶음»의 C 절. 읽기만 했다. 안 · 결론은 없다.

```
기준     origin/main 69db078e3 (server · client2/src 는 0c3a181ca 와 같음)
범위     server/ 시험 제외 · client2/src. 마이그레이션 · 스크립트는 맨 끝에 수만
계기     git grep (추적 파일만) + scratchpad 의 AST 도구(줄 -> 감싼 함수, git show 로 읽음)
카나리아  def walk_relation = 1 · class WorldNames = 1 · def create_ledger_sql 안 «{names.ledger} (» = 1 ·
         def create_audit_log = 1 · rnd_board/api.js 의 «subgraph» = 18 — 모두 >0 을 보고 셈
```

원장 쪽 물리 자리는 넷: **원자 표**(`names.ledger`, occurred_at 로 월 분할) · **row_ref**(어느 물리 행이 어느 원자를 냈나 + 그때의 행 지문) ·
**cursor**(소스별 번역 진행 · 행 센서스 · 거절 사유) · **펼친 보기** `ledger_atom_rows`(원자 × row_ref, 그리드용).
원자 표 이름은 `WorldNames.ledger` 하나로만 철자된다 — 세는 명령:

```
git grep -n -E "\.ledger\}|\.ledger\b[^_(]|\.row_ref\b|\.cursor\b[^_(]|atom_rows_view_name|walk_relation|LEDGER_TABLE" origin/main -- server ':!server/tests'
```

«표에서 바로 걸으면» 칸은 그 자리가 원장에서 «표에 그 꼴로 없는 것»을 무엇을 읽는지 적었다. 판단은 안 적었다.

---

## 1. 원장을 «읽는» 자리 전수

### 1-가. 함수 — 원자 표를 읽음

| 자리 | 읽는 것 | 표에서 바로 걸으면 |
|---|---|---|
| `SqlEvidenceLookup` ledger_subgraph.py :766 (`walk_relation` :777) | 걷기의 SQL 읽기 «유일»(만드는 곳 trace_router :759 하나, InMemory 0). 프런티어의 원자 · 시간 쪽 · 사건 시각 아님 수 · 타입별 주어 | 행 → 원자 번역(bind)이 읽는 때에. 원장 전용 칸 여섯을 읽음 — 2 절 표 |
| `gaps.measure` :359 · `_nodes_of_type_sql` :248 · `_has_predicate_sql` :334 | 타입별 노드 · 술어가 있나 (subject_keys · object keys · min occurred_at) | 노드 = 원자의 주어 · 목적 키. 표에선 선언의 키 칸 |
| `trace_router.ledger_key_values` :825 (`walk_relation` :872) | 접두어로 노드 찾기(키 값 훑기) | 같음 — 표의 키 칸 훑기 |
| `trace_router._evidence_graph` :736 | 위 `SqlEvidenceLookup` 을 만들고 걷기 | — (위와 같음) |
| `store.atoms_for_refs` :803 · `refs_plan` :822(EXPLAIN) | 거둘 원자 수 · 계획 | 거둘 원자가 없음 |
| `backfill.count_orphan_atoms` :573 · `_stale_atoms` :1329 · `index_existing_refs` :1998 | 원자의 source_raw_ref 와 오늘 표 · 선언의 어긋남 | 어긋남 = 번역 뒤 표가 바뀐 것. 대상 자체가 원장 |
| `replay.full_reset` :1726 (:1758) | 소스별 원자 수(지우기 미리보기 칸) | 칸 하나 |
| `schema.world_deletion` :1221 | 세상의 원자 수(세상 지우기 미리보기) | 칸 하나 |
| `store.atom_count` :1027 · `census` :1038 | — 서버 비시험 부르는 곳 0 (`\.census\(` 1 hit 은 `rule_census`, 다른 것) | — |
| `ledger_atom_rows` 보기 → `schema.world_relation` :428 → `main.grid_model` :2441 | 그리드가 보기를 표처럼(부르는 곳 main.py 9) | 보기 자체가 원장 |

### 1-나. 함수 — row_ref · cursor 를 읽음 (원자 아님)

| 자리 | 표 | 읽는 것 |
|---|---|---|
| `store.row_refs_for` :776 → `backfill.withdraw_deleted_rows` :2117 · `rescope` :655 | row_ref | 지운 · 바뀐 행이 낸 원자의 ref |
| `store.indexed_row_ids` :838 → `count_excluded_but_indexed` :2399 | row_ref | 지금은 거르는데 원자가 있는 행 |
| `store.sources_by_row` :862 → `main._attach_ledger_sources` :2326 | row_ref | 그리드 행마다 «어느 소스가 읽었나» |
| `backfill.rows_missing_from_the_index` :1175 · `rows_gone_from_the_source` :1264 · `withdraw_stale_atoms` :1359 · `rows_not_yet_translated` :1434 | row_ref (+cursor) | 번역 안 된 행 · 사라진 행 |
| `backfill._drift_from` :1582 | row_ref.row_fingerprint | 번역 때 지문 vs 오늘 행 — 그리드 «changed» |
| `store.read_cursor` :277 → `worker` :512 · `backfill._person_counts` :1766 | cursor | 소스 진행 |
| `admin.ingestion_view` :1239 | cursor | 소스별 네 상태 (docstring: «IT READS cursor, NOT THE LEDGER») |
| `trace_router._row_census_by_source` :1154 | cursor | 소스별 행 센서스 |

### 1-다. 라우트

| 라우트 | 읽는 자리 | 대상 |
|---|---|---|
| GET · POST `/api/ledger/subgraph` (trace_router :406) | `evidence_subgraph` :116 | 원자 |
| GET `/api/ledger/key-values` :824 | `ledger_key_values` | 원자 |
| GET `/api/ledger/gaps` :1100 | `gaps.measure` | 원자 |
| GET `/api/ledger/declaration` :1185 | `_row_census_by_source` | cursor |
| GET `/admin/ledger/sources` (main.py) | `admin.sources_view` → `ingestion_view` | cursor |
| 그리드 라우트(표 = `ledger_atom_rows`) | `grid_model` | 보기 |
| 그리드 행 쪽 (`grid_page` :2609) | `_attach_ledger_sources` + `_drift_from` | row_ref |
| DELETE `/worlds/{world}` (ontology_config_explorer_router :61) | `world_deletion` | 원자 수 |
| 소급 작업 넷 (admin/retroactive.py `_count_ledger_backfill` :426 · `_count_ledger_rescope` :590 · `_rescope` :782 · `_count/_run_delete_every_row` :1503 · :1555) | backfill · `full_reset` | 원자 · row_ref · cursor |

### 1-라. 체인 (맵퍼 · 워커)

| 자리 | 지나는 길 | 대상 |
|---|---|---|
| 맵퍼 `contrast_walk` (`_route` :39) | `evidence_subgraph` | 원자 |
| 맵퍼 `agent_walk` (`_hop` :168 · `_meaning_lines` :285) | `walk_cards.key_values` → `ledger_key_values`, `text_links._walked` · `walk_context` → `_evidence_graph` | 원자 |
| 리포트 `report_reads._walk` :1176 | `evidence_subgraph` | 원자 |
| `mapper_sdk.ask_links` (known= 줄 때) | `text_links._known` :576 → `_walked` → `_evidence_graph` | 원자 |
| 원장 따라가기 `followup._follow` :383 | `withdraw_deleted_rows` :409 · `rescope` :466 | row_ref · 원자 |
| 원장 워커 `worker.py` :512 · `_restamp_moved_fingerprints_sync` :466 | `read_cursor` | cursor |
| `replay.full_reset` | 원자 수 | 원자 |

### 1-마. 화면 (client2/src)

| 화면 | 파일 | 라우트 |
|---|---|---|
| walk.html | walk/main.js — `createWalkBoxWalk` · `fetchKeyValues` · `fetchTimePage` | subgraph · key-values |
| rnd-board.html | rnd_board/main.js — `fetchSubgraph` | subgraph |
| admin.html | gap_catalogue.js · admin.js | gaps |
| admin.html | ledger_sources_panel.js · overview_status.js · admin.js | /admin/ledger/sources |
| index.html 그리드 | grid_ledger_column.js (grid.js · state.js 가 부름) | 행의 ledger_sources · ledger_rows |
| 여러 화면 | `ledger/declaration` 을 든 파일 8 | declaration (cursor 센서스) |

```
화면 셈   git grep -l -F "<라우트 조각>" origin/main -- client2/src
곁에 본 것 rnd_board/api.js ROUTES 의 composition · trends · siblings 는 서버 라우트 hit 0 (server/ git grep)
```

마이그레이션 · 스크립트: 원장 표 이름을 든 파일 8 (`git grep -l -E "LEDGER_TABLE|world_names\(|\.ledger\b" origin/main -- server/scripts server/migrations`).

---

## 2. 원장에만 있는 이력

먼저 원장이 «잃는» 것 — 거두기는 지움이다:
`store._withdraw_refs` :641 = `DELETE FROM <ledger> WHERE source_who = %s AND source_raw_ref = ANY(%s)`.
`followup` docstring: 따라가는 사건 `CREATE · EDIT · DELETE`; EDIT 은 `rescope` 가 row_ref 로 옛 원자를 거두고 다시 씀, DELETE 는 `withdraw_deleted_rows`.

| 무엇 | 원장에 남나 | 표 쪽 | 그것을 읽는 자리 |
|---|---|---|---|
| 지운 행의 값 | 따라가기가 그 사건을 거두기 «전»까지만 | audit_logs 에 «row deleted» 줄 (old_value 없음, `crud.record_row_deletions` :6143) + 그 전 칸별 old · new | `count_orphan_atoms` · `rows_gone_from_the_source` |
| 바뀐 값(옛 값) | EDIT 을 거두기 «전»까지만. 아웃박스를 안 지난 변경은 거둘 때까지 | audit_logs old_value · new_value (칸별, `truncate_audit_value` 상한) | `_drift_from`(지문) · `_stale_atoms` · `withdraw_stale_atoms` |
| 한 주어 · `one` 술어의 여러 값 | 행마다 원자로 남음 — 걷기가 최신 occurred_at 을 현재로 (runtime_v2 :463 판정, `_not_current_clause`) | 그 행들 그대로 | `SqlEvidenceLookup` |
| occurred_at | 원자 칸 | 행의 시각 칸, 없으면 행 `created_at` (`OCCURRED_AT_BASIS_COLUMNS`) | 걷기 · gaps · 분할 |
| 원자 id (uuid7 = 기록 시각) | **원장 전용** | — | 이어 걷기 as_of (`_recorded_clause`, ledger_subgraph :3217–:3221) · 시간 쪽 순서 동률 |
| source_translator_ver | **원장 전용** | — | `trace.claim_basis` :548 (`#<derivation>` 꼬리) |
| source_event_id · state | **원장 전용** | — | `EvidenceAtom` :681 (사건 묶음) · `_subgraph_contract_state` |
| occurred_at_basis | 원자 칸 (소스 선언에서 찍음, runtime_v2 :657) | 선언 | `count_not_event_time` · 엣지 시각 표시 :1692 · :3028 |
| source_who · source_raw_ref | 원자 칸 | 소스 이름 = 선언, 행 = row_id | `trace.resolve` 등록 우선 :486 · 엣지 basis :1694 |
| row_ref (행 → 원자, 지문) | **원장 전용** | — | 1-나 표 |
| cursor (진행 · 센서스 · 거절 사유) | **원장 전용** | — | 1-나 표 |
| 세상별 사본 | 세상마다 원장 (`walk_relation` 이 world 칸을 붙임) | 표는 하나 | `SqlEvidenceLookup` |

```
센 명령  git grep -n "<칸 이름>" origin/main -- server/ledger_api/ledger_subgraph.py server/ledger/trace.py server/ledger/trace_router.py
        (칸마다 파일별 수: source_who 11 · 8 · 0, source_event_id 5 · 0 · 2, occurred_at_basis 5 · 0 · 0, source_translator_ver 2 · 4 · 0)
모르는 것  이 박스 · 운영의 «드레인 전 창»의 길이와 거기 남은 원자 수 — 재지 않았다
```
