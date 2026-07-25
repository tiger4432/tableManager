# 보고서: 서브그래프 미니 뷰어 — Client 구현 (ui-designer)

> 지시서: `agent_workspace/tasks/Ontology_subgraph_viewer_task.md` (Client 섹션)
> 브랜치: `worktree-agent-a54292dc36c3c4a1c` · 커밋 `eea929d` (main 병합·push·빌드 안 함)
> 서버 코드는 읽지 않음 — 지시서의 API 계약만 사용.

## 1. 변경 요약

신규 페이지 **`graph.html` + `src/graph_viewer.js`** (vite 5번째 엔트리). 첫 화면은 `/graph/stats`
카운트 카드(그래프가 쌓이는지 즉시 확인), 검색바(label 셀렉트 + identity 자동완성 + 1/2-hop 토글)로
`/graph/neighbors` 서브그래프를 캔버스에 렌더. 외부 라이브러리 없이 **BFS 동심원 레이아웃** 수제 구현
(≤200 노드 상정, 부모 각도 정렬로 링 간 교차 완화). 노드 클릭 = 그 노드 중심 재조회(탐색 이동) +
우측 Node Inspector에 props/서브그래프 차수 표시.

## 2. 수정 파일

| 파일 | 내용 |
|---|---|
| `client2/graph.html` | 신규 페이지. FOUC 스니펫, Outfit/JetBrains Mono, 시맨틱 토큰만 참조하는 페이지 CSS, 로딩·빈·오류 상태 전부 마크업 포함 |
| `client2/src/graph_viewer.js` | 신규 엔트리 모듈(약 800줄). stats/검색/자동완성/레이아웃/캔버스 렌더/팬·줌/Inspector |
| `client2/vite.config.js` | `graph: resolve(__dirname, 'graph.html')` 엔트리 추가 (1줄) |
| `client2/index.html` | Menu 드롭다운에 `🕸️ Knowledge Graph` 링크 1줄 추가 (Enrichment ↔ Admin 사이) |

## 3. 설계·규율 준수 포인트

- **토큰**: `tokens.css` 미수정, 시맨틱 토큰만 참조. 라벨 색 팔레트는 토큰 7종
  (`--accent/--accent-2/--success/--orange/--info/--danger/--warning`) 순환 배정 — stats 응답 순서로
  세션 내 고정이라 카드/레전드/캔버스 색이 항상 일치.
- **Provenance 강조**: `source_name='user'` 엣지는 `--overwrite`(그리드의 사용자 오버라이트와 동일
  의미색) + 굵은 선 + 큰 화살촉. 레전드에 "user provenance" 범례 병기.
- **truncated**: `--warning` 배지 `⚠ LIMIT 200 — 일부 노드 생략됨` 명시 표시.
- **렌더 성능(map_editor 교훈)**: 렌더 경로에서 `getComputedStyle`/스타일 리드 0회 — 테마 색은 1회
  캐싱 후 `themechange` 이벤트에서만 재캐싱 + 캔버스 1회 재렌더. **상시 rAF 루프 없음**(이벤트 구동
  렌더만) — 비-compositing 환경(이슈 #3)에서도 프리즈 영향 없음. DOM 오버레이(레전드·메타·카드)는
  CSS `var()` 참조라 테마 자동 추종.
- **스케일 안전**: `limit=200` 하드캡 고정, 자동완성 `limit=20` + 200ms debounce + 시퀀스 가드
  (stale 응답 폐기 — neighbors도 동일 가드).
- **밀도/노이즈 제어**: 축소 상태(scale<0.55)에서 엣지 타입 라벨 생략, scale<0.5에선 identity 라벨을
  중심/선택/호버 노드만 표시. 같은 노드쌍 다중 엣지는 곡률 분리(±26px)로 겹침 방지.
- **접근성**: 자동완성 combobox/listbox aria + ↑↓/Enter/Esc 키보드 지원, depth 토글 `aria-pressed`,
  라벨 카드 tabindex+Enter/Space, 포커스 링은 tokens.css 공통 규칙 상속.
- **XSS 방어**: DB 유래 identity/label/type/props는 전부 `esc()` 이스케이프 후 DOM 삽입.
- **z-order 교훈 준수**: 헤더 z:200, 자동완성 팝업 z:1000, 캔버스 오버레이 z:5~8.

## 4. 검증 결과

- `node --check src/graph_viewer.js` / `vite.config.js` — 통과.
- 정적 하니스(스크래치패드에 tokens/theme/utils 사본 + config 심 + `/graph/*` 3종 fetch mock,
  `python -m http.server 8899`, 실브라우저 pane)에서 시각 확인:
  - stats 첫 화면(라이트/다크): hero 3카드 + 라벨 카드(색 점) + edge_type 바 + last_sync 포맷 ✔
  - 자동완성 드롭다운(라벨 점·라벨 태그·목록 z-order) → 선택 시 즉시 탐색 ✔
  - 1-hop 렌더: 동심원, 라벨색 노드+identity, 엣지 타입 라벨·화살촉, user 엣지 amber 강조 ✔
  - 노드 클릭 재조회(EQUIPMENT 재중심) + Inspector props/차수 갱신 + 검색바 동기화 ✔
  - 2-hop: 37노드 2링(부모 방위 군집), truncated 배지 표시 ✔
  - 다크 전환: themechange 재캐싱으로 캔버스 즉시 재도색, 전 오버레이 토큰 추종 ✔
  - 휠 줌 + 드래그 팬 동작, 전 과정 콘솔 에러 0건 ✔
- 미검증(총괄 몫): 실 API 연동(서버 재기동 후), `npm run build`(worktree엔 node_modules 없음 — 교훈 준수).

참고: 미리보기 pane에서 진입 애니메이션이 중간 프레임으로 찍히는 현상은 기존 교훈(비-compositing
프리즈)과 동일 — computed opacity 1 확인으로 코드 결함 아님을 검증했음.

## 5. 사이드 이펙트 체크 (기존 페이지 회귀 없음 근거)

- 신규 파일 2개 + **추가만 있는** 기존 파일 2개(vite 엔트리 1줄, 메뉴 `<a>` 1줄). 기존 4엔트리의
  코드·스타일·계약은 미접촉.
- 공용 모듈(`tokens.css/theme.js/utils.js/config.js`)은 임포트만 하고 수정 없음. 셀 계약·WS 이벤트
  경로와 무관(REST GET 3종만 소비).
- 캔버스 좌표계는 페이지 지역 상태로 완결(DPR 반영 backing store + ResizeObserver 재측정) —
  타 페이지 좌표계와 공유 없음.

## 6. Client PM 이관 항목 (로직 변경 필요 시)

- 없음 — 본 작업은 신규 표현 계층 + 지시서 계약 소비뿐. 단, `search` 응답의 정확한 형태(배열 vs
  `{nodes:[...]}`)는 방어적으로 양쪽 파싱하게 해두었으니, 실 API 확인 후 한쪽으로 고정하면 코드가
  더 단순해짐(선택 사항).

## 7. 교훈 제안 (총괄 검수용)

- **제안**: 미리보기 pane 스크린샷은 진입 애니메이션(opacity keyframe)이 중간 프레임으로 고정 촬영될
  수 있다 — "흐릿함"을 스타일 결함으로 오진하지 말고 `getComputedStyle(...).opacity`로 실제 상태를
  확인한 뒤 재촬영할 것 (이슈 #3의 스크린샷 판정 버전).
