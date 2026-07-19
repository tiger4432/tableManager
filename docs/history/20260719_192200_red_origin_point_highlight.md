# 2026-07-19 19:22:00 - 격자 맵 에디터 내 원점 셀 빨간색 하이라이트(Red Origin Cell Highlight) 연산식 보완 구현

## 1. 개요 및 동기
* **요구사항**: 처음 화면이 기동될 때(1-based default: X Start=1, Y Start=1 등)처럼 격자 안에 실제 물리 주소 `(0, 0)` 좌표를 가진 셀이 존재하지 않는 경우에도 원점 하이라이트가 누락되지 않아야 합니다. 클릭 여부와 관계없이 설정된 `X Start` 및 `Y Start` 좌표 기준값을 활용해 해당 시점의 기준점(Origin) 셀을 자동으로 빨간색 하이라이트하도록 보완했습니다.
* **해결 방안**:
  * 격자 내에 물리 주소 `(0, 0)`이 포함되는지 여부를 `hasZeroZero = (startX <= 0 && ...) && (startY <= 0 && ...)` 공식으로 판단합니다.
  * 격자 내에 물리 주소 `(0, 0)`이 존재할 경우 기존처럼 `(0, 0)` 셀을 빨간색으로 표시합니다.
  * 만약 1-based 좌표계나 오프셋 좌표계처럼 격자 내에 `(0, 0)` 셀이 부재할 경우, 시작 기준점인 `(startX, startY)` 셀(물리 index `0, 0`에 해당하는 시작 좌표 칩)을 즉시 빨간색 원점 셀로 식별 및 강조 처리합니다.

---

## 2. 주요 구현 사항

### A. fallback이 탑재된 원점 연산 루프 (`client2/src/map_editor.js`)
```javascript
  // Check if coordinate grid contains (0,0) based on start coordinates and dimensions
  const hasZeroZero = (startX <= 0 && (startX + cols - 1) >= 0) && (startY <= 0 && (startY + rows - 1) >= 0);

  // ... cell render loop ...
  // Check if this cell is the origin point (falls back to start cell if (0,0) is outside the grid bounds)
  const isOriginCell = hasZeroZero 
    ? (coords.x === 0 && coords.y === 0) 
    : (coords.x === startX && coords.y === startY);

  if (isOriginCell) {
    cell.classList.add('cell-is-origin');
  }
```

---

## 3. 아키텍처 영향 보고
* **안정적인 원점 가시성 확보**: 0-based, 1-based, 음수 오프셋 등 그 어떤 시작 기준 조건 하에서도 첫 로드 단계부터 예외 없이 **그리드 내부의 정확한 시작 앵커 칩(원점)**이 빨갛게 활성화되어 좌표계의 기준점을 시각적으로 즉시 파악할 수 있습니다.
* **정적 컴파일 완료**: Vite 빌드 최적화가 안전하게 종료되었습니다.
