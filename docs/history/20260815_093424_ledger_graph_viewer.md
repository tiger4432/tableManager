# Ledger Graph viewer

## 변경

- `GET /api/ledger/explore`: LOT 혈통의 해결 전 분기 전체를 최대 20홉 그래프로 투영한다.
- `ledger-graph.html`: `Ontology`/`Lineage` 두 모드, 중앙 캔버스, 선택 상세, 노드/관계 필터, pan/zoom/Fit을 제공한다.
- 우측 검색 목록의 노드를 누르면 그 노드 시작 서브그래프로 전환한다. LOT은 서버에 새 20홉 요청, 나머지는 유계 응답 안에서 양방향 BFS로 재중심한다.
- 캔버스 노드를 직접 끌어 배치할 수 있고, 수동 위치는 필터 재계산 뒤에도 보존한다.
- 깊이·노드·엣지 상한은 숨기지 않고 `truncated`로 전달한다.

## 설계 경계

- 은퇴한 지식 그래프 저장소와 `/graph/*` API는 사용하지 않는다.
- 새 SQL 걷기를 만들지 않고 `ledger_trace.SqlClaimLookup.neighbourhood`와 어휘의 걷기 선언을 재사용한다.
- 전체 구조는 새 전량 쿼리를 만들지 않고 기존 `/api/ledger/structure`의 선언×원자 센서스를 탐색형 그래프로 투영한다. 기본은 원자 1건 이상인 흐름이며 `원자 0인 선언 포함`으로 선언 전수를 복원한다.
- 인스턴스 모드에서 값/공정 전량을 그래프 노드로 만들지 않는다. 이 화면은 LOT lineage와 그 annotation을 읽는다.

## 검증

- Backend focused: 4 passed.
- Client pure harness: 29 assertions.
- Vite production build: 97 modules, `dist/ledger-graph.html` 생성.
- Browser 1920×1080: Ontology 18 nodes/14 flowing predicates, Recipe 검색→3 nodes/2 edges 서브그래프, 노드 drag 이동 확인.
