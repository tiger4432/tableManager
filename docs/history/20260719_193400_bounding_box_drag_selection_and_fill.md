# 2026-07-19 19:34:00 - 격자 맵 에디터 사각 드래그 영역 일괄 채우기(Bounding Box Drag Selection & Bulk Fill) 구현

## 1. 개요 및 동기
* **요구사항**: 사용자가 드래그를 가할 때, 선형 드로잉 방식 대신 시작점과 끝점 사이의 **직사각형(사각 영역) 범위 내 모든 칩들을 단번에 선택하여 일괄 변경(채색)**하는 동작을 요구했습니다.
* **해결 방안**:
  * 마우스 드로잉 메커니즘을 펜 브러쉬에서 **사각 바운딩 박스 드래그 선택 방식(Bounding Box Selection)**으로 변경했습니다.
  * 사용자가 마우스를 좌클릭 후 드래그하는 도중에는 드래그 상자 내부에 포함되는 모든 셀들에 실시간으로 네온 블루 아웃라인과 반투명 배경 하이라이트(`.cell-in-selection`)를 입혀 실시간 시각적 피드백을 제공합니다.
  * 마우스를 뗄 때(`mouseup`), 해당 사각 영역 내에 존재하는 모든 셀을 타겟팅하여 일괄 채우기를 실행합니다.
  * 단, 이때도 이전 요구사항인 **"기존 값은 남겨둠"** 규칙을 완벽히 지키기 위해, 드래그 범위 내 셀 중 비어있지 않은 셀(`gridData[key] !== ''`)은 덮어쓰지 않고 보호하며, 오직 비어있는 셀들만 일괄 변경합니다.
  * 예외적으로 단일 칩만 선택하는 단독 클릭(`isSingleClick`) 시에는 덮어쓰기를 원하는 명시적 클릭이므로 정상 덮어쓰기 오버라이트를 허용합니다.

---

## 2. 주요 구현 사항

### A. 드래그 범위 박스 실시간 하이라이트 알고리즘 (`client2/src/map_editor.js`)
* `mousedown` 시 시작 셀(`boxStartCell`)을 앵커링하고, 드래그 도중 `mouseenter`를 거쳐가는 셀에 맞추어 `min/max` 행과 열 인덱스를 계산하여 사각 영역의 요소들을 밝은 파란색으로 하이라이트합니다.

```javascript
      cell.addEventListener('mousedown', (e) => {
        e.preventDefault();
        if (isOriginMode) {
          handleCellClick(cell, e);
          return;
        }
        const isRight = (e.button === 2 || e.buttons === 2);
        if (isRight) {
          handleCellClick(cell, e);
        } else {
          isBoxDragging = true;
          boxStartCell = cell;
          cell.classList.add('cell-in-selection');
        }
      });

      cell.addEventListener('mouseenter', (e) => {
        el.gridStatusCoords.textContent = `Cursor: (${coords.x}, ${coords.y}) = ${val !== '' ? val : 'Empty'}`;
        
        if (isMouseDown && isRightDrag) {
          handleCellClick(cell); // 우클릭 드래그 지우기
        } else if (isBoxDragging && boxStartCell) {
          // 실시간 사각 영역 범위 계산
          const c1 = parseInt(boxStartCell.dataset.c, 10);
          const r1 = parseInt(boxStartCell.dataset.r, 10);
          const c2 = parseInt(cell.dataset.c, 10);
          const r2 = parseInt(cell.dataset.r, 10);
          
          const minC = Math.min(c1, c2);
          const maxC = Math.max(c1, c2);
          const minR = Math.min(r1, r2);
          const maxR = Math.max(r1, r2);

          const allCells = el.gridCanvas.querySelectorAll('.grid-cell');
          allCells.forEach(child => {
            const cc = parseInt(child.dataset.c, 10);
            const rr = parseInt(child.dataset.r, 10);
            if (cc >= minC && cc <= maxC && rr >= minR && rr <= maxR) {
              child.classList.add('cell-in-selection');
            } else {
              child.classList.remove('cell-in-selection');
            }
          });
        }
      });
```

### B. 전역 마우스 업 시점의 사각 영역 일괄 변경 연산 (`client2/src/map_editor.js`)
```javascript
    if (isBoxDragging && boxStartCell) {
      const selectedCells = el.gridCanvas.querySelectorAll('.grid-cell.cell-in-selection');
      const isSingleClick = (selectedCells.length <= 1);

      selectedCells.forEach(cell => {
        const key = cell.dataset.key;
        if (cell.classList.contains('cell-outside-wafer')) return;

        // 드래그(선택된 셀 2개 이상) 시에는 기존 값 보존 규칙 적용!
        if (!isSingleClick && gridData[key] !== '') {
          return;
        }

        if (activeBrush !== undefined && activeBrush !== null) {
          gridData[key] = activeBrush;
          cell.textContent = activeBrush;
          cell.style.fontSize = '0.8rem';
          cell.style.color = '#fff';
          updateCellStyles(cell, activeBrush);
          cell.title = `좌표: (${cell.dataset.x}, ${cell.dataset.y})\n값: ${activeBrush}`;
          cell.classList.add('has-value');
        }
      });
      // ... 하이라이트 초기화 및 상태 해제 ...
    }
```

### C. 드래그 박스 하이라이트 CSS 스타일링 (`client2/src/style.css`)
```css
/* 드래그 사각 영역 지정 시 하이라이트 */
.grid-cell.cell-in-selection {
  outline: 2px solid #3b82f6 !important; /* neon blue border */
  outline-offset: -2px;
  background: rgba(59, 130, 246, 0.25) !important; /* translucent blue fill */
  z-index: 9;
}
```

---

## 3. 아키텍처 영향 보고
* **직관적인 Wafer Bounding Box UX**: 펜이나 마우스의 작은 움직임으로 점선을 그리는 피로감 없이, 큰 웨이퍼 상의 넓은 행렬 구역을 클릭-드래그-릴리즈만으로 1초 만에 깔끔하게 대칭 채색할 수 있습니다.
* **성능 안정성**: Canvas 요소를 통째로 다시 그리지 않고, 이미 배치된 가상 DOM 격자 상의 클래스 리스트만 스위칭하여 드래그 중인 하이라이팅 퍼포먼스가 최고 속도로 유지됩니다.
* **정적 컴파일 완료**: Vite 빌드 최적화 완료를 검증했습니다.
