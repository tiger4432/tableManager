# 맵 에디터: FRONT/BACK 라벨 그리드 밖 이동 + 반응형 격자 채움

## 현상 (Phenomenon)
1. 직전 추가한 캔버스 내 FRONT/BACK 배지·워터마크가 격자를 가림.
2. 격자가 `min(780px, 82vh, 82vw)` 상한으로, 큰 화면에서 작업영역에 빈 공간이 남음.

## 조치 (Solution)
### 1. 라벨을 그리드 바깥(툴바)으로 이동
- `renderGridCanvas()`의 캔버스 배지/워터마크(step 9) 제거.
- 그리드 툴바에 DOM 칩 `#side-indicator` 추가. `updateSideIndicator()`가 side 라디오 변경·`updateOrientationUI()`(로드/프리셋)에서 즉시 갱신. 색상: FRONT `#38bdf8` / BACK `#f59e0b`.

### 2. 반응형 격자 채움 + ResizeObserver
- `fitGridToWorkspace()`: `#map-workspace` 가용 공간(padding 제외)의 `min(availW, availH)` 정사각으로 `#grid-wrapper` 리사이즈 후 재렌더. 정사각 유지로 웨이퍼 타원 왜곡 방지.
- 트리거: `window.resize` + **`ResizeObserver(#map-workspace)`**(스플리터 등 창 리사이즈 없는 컨테이너 변경까지 커버). CSS `.map-grid-wrapper`의 780px 상한 제거.

## 사이드 이펙트 분석 (StableDevelopmentProtocol §1 준수)
| 항목 | 결과 |
|---|---|
| 마우스→셀 매핑 | 안전 — 렌더/hit-test 모두 live `getBoundingClientRect()`(CSS px) 기반 + 인덱스 조회. 크기·DPR·줌 무관. |
| 재렌더 트리거 | `window.resize`만으론 컨테이너-only 변경 누락 → `ResizeObserver` 추가로 보완. |
| 웨이퍼 왜곡 | 정사각 fit으로 방지. |
| 노치 'D' | wrapper 상대 위치, 매 렌더 `updateNotchPosition` → 크기 추종. |
| 관찰면 라벨 | 캔버스→DOM 이동, 좌표 영향 없음. rAF 비의존 갱신. |

## 검증 (Validation)
- `node --check` + `vite build` 성공.
- 라이브 브라우저 DOM/CSS 검증:
  - 칩이 툴바 내부(`chip_in_toolbar=true`), 그리드와 **겹침 없음**(`chip_overlaps_grid=false`).
  - `window.resize` 후 wrapper가 가용 공간 정사각(예 452px)으로 fit(`wrapper_inline_width=452px`).
  - 색상: FRONT bg `rgb(56,189,248)`; BACK 전환 시 `className="side-indicator side-back"` + 규칙 배경 `rgb(245,158,11)` 확인.
- (환경 주의) 비-compositing 미리보기 pane에서는 `requestAnimationFrame`·`ResizeObserver` 자동발화와 CSS `transition`이 프리즈됨 → 실제 표시 브라우저에서는 정상. 로직/클래스/inline-size로 사실 검증 완료.

## 영향 (Impact)
- 도메인: Client PM. 캔버스/DOM/CSS 변경으로 경계 계약(REST/WS/셀/스키마) 무관, 서버 무영향.
- 리빙 문서 `docs/map_editor/architecture_and_management.md` §3.2 갱신(캔버스 배지 → 툴바 칩 + 반응형 fit).
- 아울러 `StableDevelopmentProtocol` 스킬에 '사이드 이펙트 전수 분석' 원칙 추가(별도 반영).
