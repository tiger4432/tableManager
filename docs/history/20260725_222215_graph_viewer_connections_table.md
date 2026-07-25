# 그래프 뷰어 — 노드 클릭 Connections 테이블 + 행 클릭 검색 시드 연동

- **일시**: 2026-07-25 (커밋 `18218da`)
- **작업자**: Client PM (지시: 총괄 PM)
- **지시서**: `agent_workspace/tasks/Client_graph_viewer_node_table_task.md` · 보고서: `agent_workspace/reports/Client_graph_viewer_node_table_report.md`

## 배경

서브그래프 뷰어(graph.html)의 기존 인터랙션은 "노드 클릭 = 즉시 중심 재조회"라서, 노드 주변 관계를 표 형태로 훑어보거나 캔버스 맥락을 유지한 채 상세를 확인할 수 없었다. 노드 선택 시 연결 관계를 테이블로 제시하고, 테이블 행에서 곧바로 다음 탐색으로 이어지는 흐름을 추가했다.

## 변경 내용

### 인터랙션 모델 변경 (⚠️ 기존 UX와 다름 — 사용자 공지 권장)

| 동작 | 이전 | 이후 |
|---|---|---|
| 캔버스 노드 클릭 | 즉시 중심 재조회 | **선택 + 우측 Connections 테이블** (캔버스 맥락 유지) |
| 중심 이동 | 클릭 | **더블클릭** / 패널 "🔍 이 노드 중심으로 탐색" 버튼 / 테이블 행 클릭 |
| 테이블 행 클릭 | (없음) | **검색 시드 연동**: `explore()` 동일 경로 — 재로드 + URL push + 검색바 반영 |

### Connections 테이블 (Node Inspector 내 신설 블록)

- 선택 노드 정보(라벨 칩·identity·Props) 하단에 관계 테이블 — 컬럼: `관계`(→ out / ← in / ⟲ self + 엣지 type) · `노드`(라벨 + identity + 대표 props 2개 + event_time).
- 데이터 소스 2단계: ① 로드된 서브그래프에서 즉시 추출("서브그래프 단면" 배지) → ② 비중심 노드는 `GET /graph/neighbors?label=&identity=&depth=1&limit=200` 재호출로 전체 이웃 보강. 실패 시 로컬 단면 유지 + "단면 · 조회 실패" 배지.
- user provenance 엣지는 `--overwrite` 토큰으로 강조(`.conn-user`).
- 성능: 정렬(type→label→identity) 후 **80행 단위 렌더 + "더 보기"**(`CONN_PAGE=80`), 테이블 자체 스크롤. 이웃 199개 노드에서 프리징 없음.

```javascript
// client2/src/graph_viewer.js — 선택 상태 확립 + 비중심 노드 보강 (커밋 18218da 기준 ~645)
function selectNode(node, opts = {}) {
  S.selectedId = node.id;
  if (opts.expand !== false && S.panelCollapsed) setPanelCollapsed(false);
  const isCenter = node.id === S.centerId;
  S.connSeq++; // 이전 노드의 in-flight 재조회 무효화
  S.conn = {
    nodeId: node.id,
    rows: connectionRows(node.id, S.edges, S.nodesById),
    shown: CONN_PAGE,
    partial: !isCenter,   // 비중심: 로드된 서브그래프의 단면일 수 있음
    loading: !isCenter,
    ...
  };
  renderNodePanel(node); renderCanvas();
  if (!isCenter) fetchNodeConnections(node); // depth-1 재조회로 전체 이웃 보강
}
```

### URL 히스토리 연동 (신규)

```javascript
// client2/src/graph_viewer.js (~243)
function syncUrl(label, identity, mode) {
  if (mode === 'none') return; // popstate 복원은 push 안 함
  const next = `${window.location.pathname}?label=${encodeURIComponent(label)}&identity=${encodeURIComponent(identity)}`;
  if (window.location.pathname + window.location.search === next) return; // 동일 중심 재조회 → 히스토리 오염 방지
  if (mode === 'replace') window.history.replaceState({ label, identity }, '', next);
  else window.history.pushState({ label, identity }, '', next);
}
```

- `explore(label, identity, opts)` 성공 시 `?label=&identity=` push(`opts.history: 'push'|'replace'|'none'`), `popstate` 리스너로 뒤로가기 복원(파라미터 없으면 Stats 뷰). trace.html 크로스링크 관례(`?label=&identity=`) 그대로 유지.

### 패널 접기

- 패널 헤더 `»`/`«` 토글(`#panel-collapse-btn`) → `.node-panel.collapsed`(46px). 접힌 상태에서 노드 클릭 시 자동 펼침. 패널 폭 320→360px.

### 변경 파일

- `client2/src/graph_viewer.js` — 신규 `syncUrl/selectNode/connectionRows/propsSummary/fetchNodeConnections/renderConnBlock/setPanelCollapsed`, 수정 `explore/onNodeClick/renderNodePanel/initCanvasEvents/init` (927 → 1,143줄)
- `client2/graph.html` — 접기 버튼·Connections CSS(전부 tokens.css 시맨틱 토큰)
- `client2/dist/**` — `npm run build` 산출물

## 아키텍처 영향

- 서버 무접촉 — 기존 `GET /graph/neighbors` 재사용(비중심 보강도 label+identity 파라미터, node_id API 신설 없음). 경계 계약 불변.
- URL 스킴이 페이지 내 탐색에도 일관 적용되어 뷰어↔추적 리포트 크로스링크 규약(`?label=&identity=`)이 뷰어 히스토리와 통합됨.

## 검증

라이브 :8080 DOM/JS 평가 11개 시나리오 통과(199-이웃 테이블, 더 보기, 행 클릭 시드, history.back, 비중심 depth-1 보강, 더블클릭 재중심, 자동완성·Stats·테마 회귀, 콘솔 에러 0) — 상세는 보고서 §3.

## 다음 단계

- 클릭/더블클릭 UX 변경 사용자 공지.
- G2.5 이후 §7.5c 탐색 정책 엔진 도입 시 Connections 재조회(depth-1)도 정책 계층 경유로 전환 검토.
