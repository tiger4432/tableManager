# 완료 보고: 그래프 뷰어 — 노드 클릭 시 Connections 테이블 + 검색 시드 연동

- 담당: client-pm / 일자: 2026-07-25
- 지시서: `agent_workspace/tasks/Client_graph_viewer_node_table_task.md`
- 상태: **완료** (빌드 성공 + 라이브 DOM 검증 통과, 커밋은 총괄 검수 대기)

## 1. 구현 요약

### 인터랙션 모델 변경 (지시서 해석 반영)
| 동작 | 이전 | 이후 |
|---|---|---|
| 캔버스 노드 클릭 | 즉시 중심 재조회 | **선택 + 우측 Connections 테이블** (캔버스 맥락 유지) |
| 중심 이동 | 클릭 | **더블클릭** / 패널 "🔍 이 노드 중심으로 탐색" 버튼 / **테이블 행 클릭** |
| 테이블 행 클릭 | (없음) | **검색 시드 연동**: `explore()` 동일 경로 — 서브그래프 재로드 + URL `?label=&identity=` push + 검색바(label 셀렉트·identity 입력) 반영 |

### Connections 테이블 (Node Inspector 내 신설 블록)
- 배치: 선택 노드 자체 정보(라벨 칩·identity·Props 전체) **하단**에 테이블 — 지시서 1항 충족.
- 컬럼: `관계`(방향 → out / ← in / ⟲ self + 엣지 type) · `노드`(라벨 dot + identity + 라벨명 · 대표 props 2개 요약 · event_time).
- 데이터 소스 2단계: ① 로드된 서브그래프에서 즉시 추출("서브그래프 단면" 배지) → ② 비중심 노드는 `GET /graph/neighbors?label=&identity=&depth=1&limit=200` 재호출로 전체 이웃 보강(파라미터는 label+identity — node_id 아님). 실패 시 로컬 단면 유지 + "단면 · 조회 실패" 배지.
- user provenance 엣지는 `--overwrite` 토큰으로 type 강조(`.conn-user`).
- 성능: 정렬(type→label→identity) 후 **80행 단위 렌더 + "더 보기"** 버튼, 테이블 자체 `max-height` 스크롤. LOT-A|05(이웃 199) 프리징 없음.

### URL 히스토리 연동 (신규)
- `syncUrl()`: explore 성공 시 `?label=&identity=` `pushState` (동일 URL 중복 push 방지 / 초기 쿼리 진입은 `replaceState` / popstate 복원은 push 없음).
- `popstate` 리스너: 뒤로가기 → 이전 중심 재조회, 파라미터 없으면 Stats 뷰. trace.html 크로스링크 관례(`?label=&identity=`) 그대로 유지.

### 패널 접기 (캔버스 잠식 방지)
- 헤더 `»`/`«` 토글 버튼 → `.node-panel.collapsed`(46px). 접힌 상태에서 노드 클릭 시 자동 펼침. 캔버스는 기존 ResizeObserver가 재조정. 패널 폭 320→360px(≤1100px: 300px).

## 2. 변경 파일 (client2/ 한정 — 2개 + dist)
- `client2/src/graph_viewer.js`
  - 신규: `syncUrl` `selectNode` `connectionRows` `propsSummary` `fetchNodeConnections` `renderConnBlock` `setPanelCollapsed`, 상수 `CONN_PAGE=80`, 상태 `S.conn/connSeq/panelCollapsed`
  - 수정: `explore(label, identity, opts)`(히스토리 모드), `onNodeClick`(선택만), `renderNodePanel`(시드 버튼 + conn-block 삽입), `initCanvasEvents`(dblclick), `init`(popstate·접기 버튼·초기 쿼리 replace)
- `client2/graph.html`: 패널 헤더 접기 버튼(`#panel-collapse-btn`)·`#node-panel` id, Connections/접기/시드 버튼 CSS(전부 tokens.css 시맨틱 토큰 — 하드코딩 색 0), 힌트 문구 갱신
- `client2/dist/**`: `npm run build` 산출물 (graph-BFQ7Swjm.js 22.76 kB)

## 3. 검증 증거 (라이브 :8080, DOM/JS 평가 — 스크린샷 비의존)
빌드: `cd client2 && npm run build` ✅ (747ms, 에러 0)

| # | 시나리오 | 결과 |
|---|---|---|
| 1 | `?label=Wafer&identity=LOT-A%7C05` 진입 | 중심 패널 + `Connections · 199` + `LIMIT 200` 배지, 80행 렌더, 첫 행 `←BONDED_FROM Chip:BL-0001 · bx=1 by=1 · 2026-07-25 11:11:26` ✅ |
| 2 | "더 보기" 클릭 | 80 → 160행 ✅ |
| 3 | 행 클릭(Chip BL-0001) | URL `?label=Chip&identity=BL-0001` push + 검색바 `Chip`/`BL-0001` 반영 + 재로드(`3 nodes · 2 edges`) ✅ |
| 4 | `history.back()` | Wafer LOT-A|05 복원 (URL·검색바·그래프) ✅ |
| 5 | 캔버스 **비중심 노드 클릭**(합성 이벤트, 링 r=2268 적중) | 선택만(URL·입력 불변) + 로컬 단면 1행 + "전체 이웃 조회 중…" → depth-1 보강 후 2행(`Wafer`, 서브그래프 밖 `Base:BASE-01` 포함) + 배지 제거 + 시드 버튼 표시 ✅ |
| 6 | 시드 버튼 클릭 | BL-0001 중심 재조회 + URL push ✅ |
| 7 | 접기 토글 | collapsed 클래스/`«`·aria-expanded 왕복 ✅ |
| 8 | 더블클릭 중심 이동 | `Base:BASE-01` 중심 + URL push ✅ |
| 9 | 회귀: 자동완성 | `LOT` → LOT-A|05/07/12, LOT-B|01/03 (라벨 필터 동작 포함) ✅ |
| 10 | 회귀: Stats 뷰/복귀, 테마 토글(light↔dark) | 정상, 토큰 해석 정상 ✅ |
| 11 | 콘솔 에러 | **0건** ✅ |

참고: 미리보기 pane 뷰포트 0×0(비-compositing)이라 캔버스 클릭은 "cssW=0 → fitView 스킵 → view 항등변환" 성질을 이용해 월드좌표(링 반지름 199노드≈2280.6 / 2노드=130)로 합성 이벤트를 적중시켜 검증했다.

## 4. 남긴 것 / 총괄 확인 요청
- **커밋 금지 준수** — working tree에 소스+dist 변경 대기. docs/·server/ 무접촉, 히스토리·gen_index 미실행(문서는 doc-keeper 정비 중).
- 히스토리 초안: `feat(graph): 노드 클릭 → Connections 테이블(로컬 단면+depth-1 보강, 80행 페이지) + 행 클릭 검색 시드 연동(URL pushState/popstate) + 패널 접기 · 중심 이동은 더블클릭/시드 버튼으로 이전 · Stats 라벨 카드 → 노드 리스트 테이블(서버 /graph/nodes/search 빈 q+label 리스팅·offset 페이지네이션, 캡 200, 테스트 4건)`
- 단일 클릭 → 즉시 재조회였던 기존 UX가 "클릭=테이블, 더블클릭=이동"으로 바뀜 — 캔버스 힌트·패널 힌트 문구로 안내했으나 사용자 공지 권장.

---

# 추가 작업: Stats "Nodes by Label" 카드 → 노드 리스트 테이블 (총괄 추가 지시, 2026-07-25)

사용자 원문: "처음 stats 창에서 노드 by label 클릭하면 어떤 node들이 있는지 알 수 있어야 한다는 의도였음."

## A. 구현 요약
- **Stats 화면**: 라벨 카드 클릭 → 카드 그리드 아래 `#label-nodes-block`에 그 라벨의 노드 리스트 테이블(라벨 dot + identity, Connections 테이블 스타일 `.conn-row`/`.conn-table`/`.conn-more` 재사용). 헤더에 `로드 수 / stats 총 카운트`, 닫기(✕) 버튼. 카드 클릭 시 label-select 동기화(기존 동작)는 유지하되 identity-input 강제 포커스는 제거.
- **행 클릭/Enter** → 기존과 동일 `explore()` 경로: 그래프 뷰 전환 + 서브그래프 로드 + URL `?label=&identity=` push + 검색바 반영. 뒤로가기 시 파라미터 없는 URL → Stats 뷰 복귀(기존 popstate 핸들러가 처리).
- **페이지네이션**: 서버 페이지 200개(`LABEL_LIST_PAGE`, 서버 캡과 동일) + "더 보기" 버튼(응답 < 200이면 done). stale 가드 `S.labelListSeq`(카드 연타·라벨 전환 안전). 페치 실패 시 이미 로드된 행 유지 + "더 보기"가 재시도 역할.

## B. 서버 최소 수정 (`/graph/nodes/search` — 허용 범위 내)
- 확인 결과 기존 구현은 빈 q에서 무조건 `{"results": []}` → **확장 필요**했음.
- `server/main.py`:
  - `GRAPH_LABEL_LIST_LIMIT_CAP = 200` 신설 (뷰어 200 규율과 정렬; 자동완성 캡 50은 그대로).
  - `search_graph_nodes`: `q` 기본값 `""`·`offset` 파라미터 추가. **빈 q + label → 라벨 전체 리스팅**(identity 오름차순), **빈 q + label 없음 → 기존대로 빈 결과**(전 테이블 덤프 금지). offset은 두 모드 공통(음수 0 클램프). 프리픽스 이스케이프(`_escape_like_term`)·정렬 경로 불변.
- `server/tests/test_graph_viewer_api.py` 신규 4개: 빈 q+label 리스팅(공백 q·q 생략 포함) / 리스팅 offset 페이지네이션(음수 클램프 포함) / 프리픽스 모드 offset / 리스팅 하드캡 클램프(monkeypatch).

## C. 검증 증거
- 그래프 API 테스트 파일: **16 passed** (기존 12 + 신규 4).
- 전체 스위트: **233 passed / 1 failed** — 기준선 229+신규4 유지, fail은 기존 허용 fail `test_api.py::test_map_presets_api` 그대로.
- `cd client2 && npm run build` ✅ (graph-l_REypu6.js 25.54 kB).
- 라이브(:8080) DOM 검증:
  1. 카드 클릭(Chip) → 블록 표시 + label-select='Chip' + 제목 `Nodes · Chip` ✅
  2. **구 서버 응답([]) graceful**: "이 라벨의 노드가 없습니다" + `0 / 1,920 loaded` (에러·프리징 없음) ✅
  3. 신 서버 응답 모사(`window.fetch` 스텁, 총 237개): 1페이지 200행(BL-0001~0200) + "더 보기" → 237행 + 버튼 소멸(done 판정) ✅
  4. 행 클릭(BL-0001, **실서버** neighbors 호출) → 그래프 뷰 + URL push + 검색바 반영 + Connections 테이블 ✅
  5. `history.back()` → 파라미터 없는 URL → Stats 뷰 복귀(리스트 보존) ✅ / 닫기(✕) ✅ / 콘솔 에러 0 ✅

## D. 라이브 검증 한계 (재기동 금지 준수)
라이브 서버는 구 서버 코드로 구동 중이라 **빈-q 리스팅의 실서버 end-to-end는 미검증** — 서버 신규 로직은 pytest(TestClient)로, 클라 배선은 신 응답 모사 스텁으로 각각 검증했다. **서버 재기동 후** 카드 클릭 → 실데이터 리스팅 1회 확인을 권장한다(총괄 재기동 시점에).

## 5. 교훈 제안 (client-pm.md 반영 후보)
- **함정**: 미리보기 pane은 `window.innerWidth=0`(뷰포트 0×0)이라 `getBoundingClientRect` 기반 캔버스 좌표 클릭이 전부 빗나간다 (`resize_window`로도 복구 불가).
  **올바른 방법**: 캔버스 히트테스트 검증은 앱의 뷰 변환 상태(0×0이면 fitView 스킵 → 항등변환)를 역이용해 월드좌표로 합성 MouseEvent(clientX/Y는 음수 허용, offsetX/Y 자동 계산됨)를 쏜다.
- **함정**: `javascript_tool`은 top-level `await`가 불가(async 함수 아님 에러).
  **올바른 방법**: 비동기 완료 검증은 "트리거 호출 → 별도 호출로 결과 폴링" 2단계로 나눈다.
