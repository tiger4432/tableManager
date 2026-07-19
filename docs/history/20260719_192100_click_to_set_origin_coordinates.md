# 2026-07-19 19:21:00 - 격자 맵 에디터 내 클릭 기반 원점 (0,0) 지정 기능(Click to Set Origin) 구현

## 1. 개요 및 동기
* **요구사항**: 시작 좌표 X Start, Y Start 값을 직접 텍스트로 치는 것도 좋지만, 사용자가 **격자 상의 특정 칩을 클릭해 해당 셀을 즉시 (0,0) 원점으로 설정**할 수 있도록 클릭 기반 원점 지정 기능을 구현해달라는 요청이 있었습니다.
* **해결 방안**: 
  * 상단 툴바에 `📍 Set Origin (0,0)` 토글 모드 버튼을 추가했습니다.
  * 해당 모드가 활성화되었을 때 (`isOriginMode = true`):
    * 원 밖 영역을 포함해 **전체 모든 격자 셀을 클릭할 수 있도록** 임시적으로 포인터 이벤트를 차단 해제(`pointer-events: auto !important`)하여 편의성을 보장했습니다.
    * 임의의 셀 클릭 시 해당 셀의 내부 인덱스(0-indexed)에 대한 음수 오프셋을 역산하여 `X Start` 및 `Y Start` 입력 필드에 자동 역주입하고 맵을 즉각 재렌더링합니다.
    * 지정이 끝나는 즉시 원점 지정 모드는 자동 비활성화(Self-Dismiss)됩니다.

---

## 2. 주요 구현 사항

### A. 원점 역산 인터셉터 로직 (`client2/src/map_editor.js`)
```javascript
function handleCellClick(cell, event) {
  if (isOriginMode) {
    const c = parseInt(cell.dataset.c, 10);
    const r = parseInt(cell.dataset.r, 10);
    const cols = parseInt(el.gridCols.value, 10) || 10;
    const rows = parseInt(el.gridRows.value, 10) || 10;
    const invertY = el.gridYInvert.checked;

    // 0-indexed 물리 좌표를 역산 구함 (startX=0, startY=0 기준)
    const rawCoords = getPhysicalCoords(c, r, cols, rows, currentRotation, currentSide, invertY, 0, 0);

    // 해당 클릭 셀이 (0,0)이 되도록 시작점 오프셋 변위값 결정
    const newStartX = -rawCoords.x;
    const newStartY = -rawCoords.y;

    // 입력 필드 주입
    el.gridStartX.value = newStartX;
    el.gridStartY.value = newStartY;

    // 모드 해제 및 원상 복구
    isOriginMode = false;
    el.btnSetOrigin.classList.remove('active');
    el.btnSetOrigin.style.borderColor = '';
    el.btnSetOrigin.style.color = '';
    el.gridCanvas.classList.remove('origin-mode-active');

    // 갱신 렌더링
    renderGridCanvas();
    return;
  }
  
  // ... 일반 그리기 / 지우기 로직 ...
}
```

### B. 원점 설정 모드 시 포인터 이벤트 일시 강제 개방 CSS (`client2/src/style.css`)
```css
/* 원점 설정 모드 작동 시, 원 밖의 셀도 일시적으로 조작/클릭이 가능해지도록 스타일 우회 */
.map-grid-canvas.origin-mode-active .grid-cell.cell-outside-wafer {
  pointer-events: auto !important;
  cursor: cell !important;
}
```

---

## 3. 아키텍처 영향 보고
* **원점 조율 편의성 극대화**: 마우스 클릭 단 한 번만으로 웨이퍼의 물리적 중심점이나 특정 원점을 (0,0)으로 즉시 앵커링할 수 있어, 복잡한 인덱스 계산 없이 직관적인 좌표 맵 드로잉이 보장됩니다.
* **정적 컴파일 완료**: Vite 최적화 빌드가 차질 없이 수행되었습니다.
