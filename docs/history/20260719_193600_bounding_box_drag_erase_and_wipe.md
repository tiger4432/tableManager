# 2026-07-19 19:36:00 - 격자 맵 에디터 사각 드래그 지우기(Bounding Box Drag Erase & Wipe) 기능 구현

## 1. 개요 및 동기
* **요구사항**: 사각 일괄 드로잉 채우기 기능의 탑재에 힘입어, **드래그를 통해 사각 영역 내 모든 칩들을 한꺼번에 지울(Erase/Empty) 수 있도록** 하는 사각 영역 지우기 기능도 함께 요청되었습니다.
* **해결 방안**:
  * 마우스 좌클릭 드래그 시에는 파란색 상자 채우기(Fill)가 작동하며,
  * **마우스 우클릭 드래그 시에는 빨간색 상자 지우기(Erase)**가 활성화되도록 구조를 대칭 개편했습니다.
  * 우클릭 드래그 중인 영역에는 실시간으로 네온 레드 아웃라인과 반투명 레드 하이라이트(`.cell-in-selection-erase`)가 기입되어 지워질 대상을 식별하게 돕습니다.
  * 마우스 우클릭을 해제하면, 빨갛게 감싸진 사각 영역 내에 존재하던 모든 칩 값들이 에디터 로컬 데이터 및 화면 격자 UI에서 일제히 깨끗하게 소거(Wipe)되어 초기화됩니다.

---

## 2. 주요 구현 사항

### A. 우클릭 드래그 식별 및 빨간색 사각박스 하이라이트 (`client2/src/map_editor.js`)
* 마우스 `mousedown` 시 우클릭 여부(`isRight = e.button === 2`)에 맞추어 `cell-in-selection-erase` 혹은 `cell-in-selection`을 셀 노드에 가변 주입하고, `mouseenter`를 통해 하이라이트 클래스를 조율합니다.

```javascript
      cell.addEventListener('mousedown', (e) => {
        e.preventDefault();
        if (isOriginMode) {
          handleCellClick(cell, e);
          return;
        }
        const isRight = (e.button === 2 || e.buttons === 2);
        isBoxDragging = true;
        boxStartCell = cell;
        if (isRight) {
          cell.classList.add('cell-in-selection-erase');
        } else {
          cell.classList.add('cell-in-selection');
        }
      });
```

### B. 전역 마우스 업 시점의 사각 영역 일괄 소거 연산 (`client2/src/map_editor.js`)
```javascript
  window.addEventListener('mouseup', () => {
    isMouseDown = false;
    isRightDrag = false;

    if (isBoxDragging && boxStartCell) {
      // 1. 빨간색 지우기 상자가 활성화된 경우
      const selectedEraseCells = el.gridCanvas.querySelectorAll('.grid-cell.cell-in-selection-erase');
      if (selectedEraseCells.length > 0) {
        selectedEraseCells.forEach(cell => {
          const key = cell.dataset.key;
          gridData[key] = '';
          cell.textContent = `${cell.dataset.x},${cell.dataset.y}`;
          cell.style.fontSize = '0.65rem';
          cell.style.color = 'var(--text-dim)';
          updateCellStyles(cell, '');
          cell.title = `좌표: (${cell.dataset.x}, ${cell.dataset.y})\n값: Empty`;
          cell.classList.remove('has-value');
        });
      } else {
        // 2. 파란색 채우기 상자가 활성화된 경우 (기존 코드 적용)
        // ...
      }
      // ... 초기화 및 해제 ...
    }
  });
```

### C. 사각 소거 하이라이트 CSS 스타일링 (`client2/src/style.css`)
```css
/* 드래그 사각 영역 지우기 하이라이트 */
.grid-cell.cell-in-selection-erase {
  outline: 2px solid #ef4444 !important; /* neon red border */
  outline-offset: -2px;
  background: rgba(239, 68, 68, 0.25) !important; /* translucent red fill */
  z-index: 9;
}
```

---

## 3. 아키텍처 영향 보고
* **직관적인 양방향 드래그 조작계 구축**:
  * 마우스 좌버튼 드래그 = 파란색 박스 (빈 칩 일괄 세팅)
  * 마우스 우버튼 드래그 = 빨간색 박스 (기존 칩 일괄 지우기)
  * 이로써 칩들을 하나하나 정밀 클릭해 지울 필요 없이, 임의의 대형 영역을 1초 만에 초기화하고 새로 드로잉을 할 수 있는 극상의 조작 생산성이 확보되었습니다.
* **정적 컴파일 완료**: Vite 빌드 최적화가 에러 없이 성공적으로 마감되었습니다.
