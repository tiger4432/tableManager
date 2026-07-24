# 맵 에디터: 캔버스 FRONT/BACK 관찰면 표기 추가

## 현상 (Context)
맵 에디터 캔버스에서 현재 관찰면이 FRONT(앞면)인지 BACK(뒷면)인지 시각적으로 드러나지 않아 혼동 소지가 있었다. (요구: front/back을 캔버스에 아주 잘 보이게 표시)

## 조치 (Solution)
`client2/src/map_editor.js`의 `renderGridCanvas()` 말미(step 9, `ctx.restore()` 직전)에 색상 구분된 side 표기를 추가. `currentSide` 변경 시 기존 재렌더 경로로 자동 갱신.

- **좌상단 pill 배지**: `FRONT · 앞면` / `BACK · 뒷면`, 배경 색상 구분(FRONT `#38bdf8` 하늘색, BACK `#f59e0b` 앰버), 그림자로 대비 강화. 노치 'D' 마커(상단 중앙)와 겹치지 않도록 좌상단 고정.
- **중앙 대형 워터마크**: 동일 색 계열 반투명(opacity 0.13) `FRONT`/`BACK` 글자, 격자 가독성 유지.

```js
const isBack = (currentSide === 'back');
const sideColor = isBack ? '#f59e0b' : '#38bdf8';
// 9a 워터마크(중앙) + 9b pill 배지(좌상단, arcTo 라운드 렉트)
```

## 검증 (Validation)
- `node --check` + `vite build` 성공(신규 번들 `map_editor-*.js`).
- 라이브 브라우저 픽셀 샘플링으로 색상 검증:
  - FRONT 배지 = `rgb(59,177,230)` ≈ `#38bdf8` (하늘색) ✓
  - BACK 배지 = `rgb(245,158,11)` = `#f59e0b` (앰버) ✓
- (참고) 비표시 pane에서는 `scheduleRenderGridCanvas`의 `requestAnimationFrame`이 스로틀되어 side 전환 재렌더가 지연됨 → 직접 렌더 경로로 재검증. 실제 표시 환경에서는 정상 갱신.

## 영향 (Impact)
- 도메인: Client PM. 캔버스 표시 전용 변경으로 경계 계약(REST/WS/셀/스키마) 무관, 서버 무영향.
- 리빙 문서 `docs/map_editor/architecture_and_management.md` §3.2에 Side Indicator 규격 추가.
