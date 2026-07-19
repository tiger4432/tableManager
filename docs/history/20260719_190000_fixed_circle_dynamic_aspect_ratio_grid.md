# 2026-07-19 19:00:00 - 격자 맵 에디터 내 고정 외곽 원 및 동적 셀 비율 조절(Fixed Wafer Circle & Dynamic Grid Sizing) 기능 구현

## 1. 개요 및 동기
* **배경**: 기존 2D 그리드 레이아웃은 개별 격자 셀의 크기가 고정(`min-width: 32px`, `aspect-ratio: 1`)되어 있어, X축/Y축 격자 수가 늘어나거나 줄어들 때 전체 그리드 캔버스의 크기가 변하고, 이로 인해 외곽의 웨이퍼 상징 원형 테두리가 함몰되거나 찌그러지며 그리드 바깥으로 넘쳐나는 문제가 있었습니다.
* **해결 방안**: 외곽 원(`.map-grid-wrapper`)의 크기를 절대 고정(`width: 500px; height: 500px`)하고, 그리드 캔버스(`.map-grid-canvas`)의 크기는 이 원의 최대 내접 사각형 크기 비율인 `70%`로 한정시킨 뒤, 셀들이 그 크기 안에서 **행/열 수에 맞추어 유연하게 크기와 비율(Aspect Ratio)이 조절되면서 딱 맞게 채워지도록** CSS 및 레이아웃을 리팩토링했습니다.

---

## 2. 주요 구현 사항

### A. CSS 레이아웃 구조 변경 (`client2/src/style.css`)
* **웨이퍼 원형 테두리 (`.map-grid-wrapper`)**: `display: inline-block`을 제거하고 `display: flex`와 고정 폭/높이(`500px`)를 부여하여 중앙 정렬의 기반을 잡았습니다.
* **그리드 캔버스 (`.map-grid-canvas`)**: 최대 내접 사각형 비율인 가로/세로 `70%` 크기로 제한하여, 격자가 원을 뚫고 삐져나가는 현상을 원천 배제했습니다.
* **격자 셀 (`.grid-cell`)**: 고정 가로/세로 크기(`min-width`, `min-height`) 및 1:1 종횡비(`aspect-ratio: 1`) 제약을 모두 소거하고 `width: 100%; height: 100%`로 처리하여, 그리드 영역 내부를 꽉 채우도록 설정했습니다.

```css
.map-grid-wrapper {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 500px;
  height: 500px;
  padding: 30px;
  background: rgba(255, 255, 255, 0.01);
  border-radius: 50%;
  border: 2px dashed rgba(255, 255, 255, 0.1);
  box-shadow: inset 0 0 20px rgba(255, 255, 255, 0.02);
  box-sizing: border-box;
}

.map-grid-canvas {
  display: grid;
  gap: 2px;
  background: var(--border-color);
  padding: 5px;
  border-radius: 6px;
  width: 70%;
  height: 70%;
  box-sizing: border-box;
}

.grid-cell {
  background: rgba(30, 41, 59, 0.8);
  border: 1px solid rgba(255, 255, 255, 0.05);
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  box-sizing: border-box;
  overflow: hidden;
  border-radius: 2px;
}
```

### B. JS 그리드 행/열 분할 연동 (`client2/src/map_editor.js`)
* 열(Columns) 개수 분할(`gridTemplateColumns`)뿐만 아니라, **행(Rows) 개수 분할(`gridTemplateRows`)** 역시 Uvicorn 핫 리로드 및 렌더링 시점에 균등 분배(1fr)하도록 스크립트를 변경했습니다.

```javascript
  // renderGridCanvas() 함수 내부
  el.gridCanvas.style.gridTemplateColumns = `repeat(${visualCols}, 1fr)`;
  el.gridCanvas.style.gridTemplateRows = `repeat(${visualRows}, 1fr)`;
```

---

## 3. 아키텍처 영향 보고
* **시각적 완성도 극대화**: X축, Y축의 행/열 비율이 다를 경우(예: Strip Map 12x4 등)에도, 외곽 웨이퍼 원형 테두리 크기는 흐트러지지 않으며, 내부의 개별 셀 비율만 가로형/세로형 직사각형으로 유연하게 스트레칭되어 캔버스 크기(350px X 350px)를 딱 맞춰 가득 메웁니다.
* **정적 빌드 완료**: Vite 번들러 컴파일이 성공적으로 종료되어 `dist/assets/map_editor-NsYscg9k.js` 및 CSS 파일이 정상 갱신되었습니다.
