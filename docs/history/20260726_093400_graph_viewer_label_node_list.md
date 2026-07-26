# feat(graph): 뷰어 stats 라벨 카드 클릭 → 노드 리스트 + 검색 연동

- **일시**: 2026-07-25 (커밋) / 2026-07-26 (문서화)
- **커밋**: `df63f3a`
- **작업자**: client-pm (+ 서버 search API 확장)

## 배경

뷰어 첫 화면(stats 카운트 카드)에서 라벨별 노드 총수는 보이지만 **그 라벨의 노드 목록으로 들어갈 진입로가 없었다** — identity를 이미 알아야 검색이 가능했다. 라벨 카드를 목록 진입점으로 승격.

## 변경 내용

### 서버 — `GET /graph/nodes/search` 확장 (main.py)

- **빈 `q` + `label` = 라벨 전체 리스팅**(identity 오름차순, limit/offset 페이지네이션).

```python
GRAPH_LABEL_LIST_LIMIT_CAP = 200     # 빈 q + label 리스팅 페이지 하드캡 (뷰어 200 규율과 동일)
...
cap = GRAPH_SEARCH_LIMIT_CAP if term else GRAPH_LABEL_LIST_LIMIT_CAP   # 자동완성 캡 50 불변
```

- 전 테이블 덤프 금지 유지(label 없는 빈 q는 종전대로 거부). 테스트 4건 추가(그래프 API 16 passed).

### 클라 — `client2/src/graph_viewer.js`

- 라벨 카드 클릭 → 노드 테이블(Connections 스타일 재사용): `openLabelNodes`/`fetchLabelNodesPage`(서버 페이지 200 + "더 보기", 로드수/총수 헤더, seq 가드)/`renderLabelNodesBlock`. 행 클릭 → `explore` 중심 탐색 연동, back → Stats 복귀(`closeLabelNodes`).
- `LABEL_LIST_PAGE = 200`(서버 캡과 동일 상수).

## 아키텍처 영향

- 경계 계약: 기존 엔드포인트의 **하위호환 확장**(빈 q 의미 추가 + 캡 200 신설) — 자동완성 계약(캡 50) 불변.
- 스위트 233 passed / 1 allowed fail. 구 서버 graceful(빈 안내) 확인.

## 다음 단계

- 신 리스팅 실서버 e2e 1회 확인(재기동 후 — 이후 드릴 재기동으로 서빙 중 상태).
