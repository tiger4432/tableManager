# Ledger Evidence Graph와 외부 표 투영

## 현상

기존 원장은 Entity 관계와 값 주장을 저장하고 있었지만 그래프 화면이 Claim을 직접 선으로 접어 버려
다음 질문에 답하기 어려웠다.

- 이 관계를 주장한 **원자**는 무엇인가?
- 여러 원자가 같은 원천 레코드/분자에서 함께 발화됐는가?
- Entity가 아닌 Claim/Event에서 다시 주변 증거를 펼칠 수 있는가?
- Spotfire·Excel이 캔버스 JSON을 각자 다르게 flatten하지 않고 같은 결과를 표로 받을 수 있는가?

또한 그래프 자체를 분석 화면으로 쓰려는 방향은 R&D 연구원의 실제 흐름과 맞지 않았다. 연구원에게 필요한
기본 표면은 Trend·Map·Process·Measurement·Candidate 표이며, 그래프는 결론의 근거를 감사하는 마지막
drill-down이어야 한다.

## 근본 원인

원자의 `source_raw_ref`와 `source_who`만으로는 같은 소스 발화가 낸 원자 묶음을 무손실로 복원할 수 없다.
과거 원자를 내용 유사성으로 다시 묶으면 그럴듯하지만 발화하지 않은 Event를 발명한다. 반대로 Claim을
1급 노드로 보존하지 않으면 경쟁·정정 전 원자와 원문 근거를 그래프에서 검사할 수 없다.

외부 도구 호환성 문제는 그래프에 있지 않고 projection 계약 부재에 있었다. 각 도구가 중첩 JSON을 직접
펴면 숫자/문자열/NULL/list/unit 해석이 갈리고, 새 payload key가 생길 때마다 wide column 스키마가 흔들린다.

## 판정

1. `ledger_events`가 계속 유일한 증거 저장소다. 별도 graph node/edge 저장소나 materializer는 만들지 않는다.
2. Source Event는 세계의 공정 Event가 아니라 **원천 발화 경계**다. resolver·Candidate 점수는 읽지 않는다.
3. 새 적재는 writer가 결정적 `source_event_id`를 기록한다. 과거 원장은 필요할 때만 원자 1개를
   `legacy_atom` Event 1개로 보존하며 유사성 regroup을 금한다.
4. Evidence Graph 문법은 `Event -asserts→ Claim -subject/original predicate→ Entity|Value`다.
5. 어떤 Entity/Event/Claim/Value 불투명 ID도 다시 seed가 된다. 결과는 유계 BFS이며 모든 절단을 이름 댄다.
6. 연구원과 Spotfire·Excel에 보이는 기본 계약은 표다. 그래프와 표는 같은 BFS snapshot에서 나온다.
7. 동적 온톨로지 속성은 새 열이 아니라 typed long `properties` 행으로 나타난다.

## 구현

### 쓰기와 물리 스키마

`server/ledger/envelope.py`가 동일 source/time/molecule reference로 결정적 UUIDv5 Source Event identity를
만들고 `server/ledger/store.py`가 모든 신규 원자에 기록한다.

```python
event_id, event_state = source_event_identity(
    atom.source_who,
    atom.occurred_at,
    molecule_ref=atom.molecule_ref,
    source_raw_ref=atom.source_raw_ref,
)
```

`source_event_id`, `source_event_state`와 두 소비 인덱스를 추가했다. 기존 파티션 인덱스는 parent 전체를
동기 빌드하지 않고 child별 `CREATE INDEX CONCURRENTLY` 후 attach한다.

### 증거 API

`server/ledger_subgraph.py`는 frontier를 Entity/Event/Claim별 batch exact query로 인출한다. 노드별 N+1이나
JSON 전체 문자열 검색을 하지 않는다.

```text
GET /api/ledger/subgraph
  ?id=<opaque-node-id>
  &hops=1..40
  &direction=outgoing|incoming|both
  &include_values=true|false
  &node_limit=10..1000
  &edge_limit=20..3000
  &shape=graph|tables
  &property_limit=100..20000
```

`raw_claims:true`, `resolver_applied:false`가 이 응답의 의미다. 해결된 혈통은 `/trace`, 집단 비교와 원인
후보는 `/selection/resolve`가 계속 소유한다.

### Spotfire·Excel 표 계약

한 snapshot은 다음 세 표로 투영된다.

| 표 | grain | join |
|---|---|---|
| `nodes` | 노드 1개/행 | `node_id` |
| `edges` | 엣지 1개/행 | `source_id`, `target_id` → `nodes.node_id` |
| `properties` | 동적 scalar 1개/행 | `node_id` |

`properties`는 `value_text`, `value_number`, `value_boolean`, `is_null`을 분리한다. 한 장씩 받는
`/api/ledger/subgraph/table?table=...&format=json|csv`도 추가했다. CSV는 UTF-8 BOM/CRLF이며 문자열
formula 시작 문자를 중립화하고 실제 숫자는 숫자로 보존한다.

속성 상한은 Properties만 자른다. Nodes를 함께 자르면 Edges의 외래 join key가 사라지는 결함을 회귀
검사에서 발견해, 노드 표는 끝까지 유지하고 `truncated.properties=true`만 표시하도록 고쳤다.

### Viewer

`/ledger-graph.html`은 두 모드다.

- `Ontology`: 선언과 실제 유형 흐름
- `Evidence`: Entity·Source Event·Claim·Value raw evidence

오른쪽 Entity Catalog는 등록을 요구하는 모든 타입의 검색 가능 목록을 보여 준다. 캔버스 더블클릭 또는
노드 목록 클릭으로 임의 evidence node를 다시 seed로 연다. 최대 40홉, 방향, Value 표시, 노드/엣지 상한,
절단 사유를 노출한다. Nodes/Edges/Properties CSV는 화면과 같은 seed·홉·방향을 사용한다.

## 사이드 이펙트 점검

- **기존 resolver/selection:** Source Event를 읽지 않으므로 승자·후보 결과 불변.
- **좌표/DPR/hit-test:** 노드 도형만 Event diamond/Claim rounded square로 확장했고 기존 world↔screen 변환,
  ResizeObserver, drag/pan/zoom 경로는 유지했다.
- **비동기:** 현재 graph request는 AbortController+request serial로 stale 응답을 폐기한다.
- **대용량:** 기본 400 nodes/1200 edges/claim cap, 최대 1000/3000/5000. exact expression indexes와 batch
  frontier query를 사용한다. 깊은 OFFSET이나 전량 로드는 없다.
- **외부 표:** property cap이 nodes/edges join 완전성을 깨지 않도록 별도 회귀검사를 추가했다.
- **과거 데이터:** 개발 DB 220,771 원자는 호환 확인을 위해 `legacy_atom`으로 백필했지만 권장 운영 경로는
  새 원장 재적재다. 과거 Event 복원에 더 투자하지 않는다.

## 검증

- `test_ledger_subgraph.py + test_ledger_l1_unit.py + test_ledger_explorer.py`: **103 passed, 1 skipped**.
- `test_ledger_subgraph.py`: **9 passed, 1 skipped**. 임의 seed, 방향, 상한, typed property, join 완전성,
  route/CSV formula 안전 포함.
- `ledger_graph_harness.mjs`: **39 assertions, 0 failed**.
- Vite production build: **103 modules**, 성공.
- 변경 Python 파일 `py_compile`: 성공.
- PostgreSQL 전용 3파일: **1 passed, 82 skipped** — 이 실행 환경에 선언된 격리 테스트 DB가 없어 skip.
- 개발 DB 읽기 smoke: 3홉/90노드 한도에서 Entity·Event·Claim·Value 90 nodes/89 edges,
  절단 없이 Claim 60건 확인.

## 제한과 다음 단계

1. `supersedes`는 Claim 속성으로 보존되지만 대상 `occurred_at`이 원자에 없어 숨은 cross-partition scan 없이
   자동 edge를 만들 수 없다.
2. `shape=tables` 한 요청은 snapshot 일관성이 있지만 CSV 세 요청은 append-only 신규 원자 사이에 서로 다른
   `generated_at`을 가질 수 있다.
3. Graph Viewer는 원인 탐색 첫 화면이 아니다. 다음 우선순위는 Candidate·Process·Measurement·Map projection도
   같은 stable table/mark/evidence ID 계약으로 통일하고 Candidate 클릭에서 해당 Claim/Event로 drill-down하는 것이다.

## 관련 문서

- `docs/spec/LEDGER_EVIDENCE_SUBGRAPH_SPEC.md`
- `docs/spec/RND_ONTOLOGY_USE_CASES.md`
- `docs/architecture/backend.md` §2
- `docs/architecture/frontend.md` §6.3-bis
- `docs/guide/LEDGER_GUIDE.md` §1.2
- `docs/process/OPERATOR_RUNBOOK.md` §6
