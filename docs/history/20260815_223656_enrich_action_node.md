# Enrich Action 노드와 Evidence Graph 걷기 연결

## 현상

DT/Bonding frame, output LOT·SLOT처럼 객체의 정체를 이루는 Claim이 아직 없을 때 기존 Enrichment는
derived table의 빈 target으로만 일감을 표현했다. 이 결손은 원장 그래프에서 보이지 않았고,
그래프 걷기가 Claim에서 끝나면 연구원은 “관계가 원래 없음”과 “필수 Claim이 없어 더 못 감”을
구별할 수 없었다.

또한 Claim을 공급할 source가 아직 선언되지 않은 경우 row마다 같은 미해결 항목을 만드는 것은
연구원에게 해결 불가능한 일감을 폭주시킨다. 이 경우 첫 행동은 값을 채우는 일이 아니라
Enrichment/translator/source 계약을 만드는 Meta Action이다.

## 판정

1. Enrich Action은 Domain Entity도, append-only 원장 Claim도 아니다. Enrichment 선언과 현재 derived
   row에서 다시 만드는 read projection이다.
2. 그래프에 따로 끼워 넣지 않고 실제 근거 Claim에서 `needs_enrichment` 엣지로 도달해야 한다.
3. `claim_resolution`은 공급 source가 선언된 결손 target에 대해 decision key당 하나다.
4. `source_contract`는 공급 source 부재 또는 rule 배포 계약 실패에 대해 rule당 하나다.
5. 자동 BFS는 Action에서 멈춘다. Action의 opaque ID를 직접 seed로 넣는 명시적 재조회는 허용한다.
6. Evidence Graph 조회 중 reference-view candidate SQL은 실행하지 않는다. 후보 조회·확정은 사용자의
   다음 행동이고, 그래프 렌더링이 그 판단을 몰래 수행하지 않는다.
7. table 배포 검증에 실패한 rule은 derived row를 읽지 않는다. 그 실패 자체를
   `repair_enrichment_contract` Action으로 보인다.

## 구현

- `server/enrichment_actions.py`
  - canonical `ledger-enrich-action:v1:` ID
  - `EnrichAction`, pure/in-memory/SQL lookup
  - 정확한 Claim anchor matching과 bounded `business_key_val IN (…)` row read
  - derived business key가 decision key의 진부분집합일 때 같은 row 상태를 모든 decision context에 보존
  - per-key resolve Action과 deduplicated rule-level Meta Action
- `server/enrichment_config.py`
  - 기존 rule에 선택적 `claim_contract` validator 가산
  - anchor, slots, sources를 선언으로만 해석하며 이름 추론 금지
  - anchor/slot predicate는 canonical ledger vocabulary에 없는 철자를 거절
  - 잘못된 계약은 rejection을 남기고 계약만 버리며 legacy rule은 유지
- `server/ledger_subgraph.py`
  - Claim → `needs_enrichment` → Action
  - Action seed decode/re-evaluation, action budget/truncation/provenance
  - schema version 3
- `server/ledger_trace_router.py`
  - `/subgraph`, `/subgraph/table`에 `enrich_actions=true` 기본 파라미터
- `client2/src/ledger_graph/main.js`
  - Action 육각형, 결손 target·예상 Claim·공급 source 상세, 재중심
  - CSV/graph 요청 모두 Action projection을 명시
- 기존 세 live/sample/reference Enrichment rule에 `claim_contract`를 선언했다.

## API 결과

```text
Claim --needs_enrichment--> Enrich Action
```

Action은 `state`, `action_kind`, `missing_targets`, `expected_claims`, `supply_sources`,
`suggested_action`을 낸다. 표 투영의 `nodes`/`properties`에도 그대로 나타나고, provenance에는
`additive_sources: ["enrichment_action_projection"]`이 붙는다.

## 검증

- `test_enrichment_actions.py + test_ledger_subgraph.py`: **19 passed, 1 skipped**
- 기존 Enrichment 회귀(라이브 config 자체를 고정하는 1개 제외): **126 passed, 1 deselected**
- `ledger_graph_harness.mjs`: **42 assertions, 0 failed**
- 전체 client harness gate: **51 gated green, 기존 known-red 5 불변**
- clipboard convention + contracts: **7 contracts, no divergence**
- Python `py_compile`: 성공
- Vite 임시 outDir build: **103 modules**, 성공. 기존 `client2/dist`는 덮지 않았다.

## 알려진 배포 장애

현재 라이브 `server/config/table_config.json`은 `{}`이고 gitignored 사용자 설정이다. 따라서
세 Enrichment rule은 문법 선언으로는 읽히지만 `known_tables=crud.TABLE_CONFIG` 검증에서는 모두
미배포다(`declared=3`, `deployed=0`). 이 변경은 그 상태에서 row 값을 읽거나 정상 Action을
발명하지 않고 rule-level `repair_enrichment_contract` Meta Action을 낸다.

이번 작업은 사용자의 설정을 추정 복구하지 않았다. 정상 per-key `resolve_claim` Action을 보려면
`dt_log`, `dt_core_view`, `dt_job_attribution`, `dt_inventory`의 table 계약을 먼저 정본 config로
복구하고 서버를 재기동해야 한다.

## 아직 하지 않은 것

- 통합 `GET /enrichment/worklist` 집계 API
- coverage/due/dependency/cardinality와 contested/candidate 상태
- Action에서 candidate reference view를 실행하는 명시적 UI 흐름
- target edit/auto-confirm 결과의 canonical Claim 발행
