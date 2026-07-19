# 2026-07-19 19:18:00 - 격자 맵 에디터 내 X, Y 임의 시작 좌표 기준(Custom Coordinate Start Index) 설정 기능 구현

## 1. 개요 및 동기
* **요구사항**: 단순히 0-based(0부터 시작) 혹은 1-based(1부터 시작)만 토글하는 이분법적 방식에서 벗어나, 사용자가 X축과 Y축의 시작 인덱스 좌표 기준을 임의의 정수(양수, 0, 음수 포함)로 자유롭게 지정하여 격자 데이터를 입력할 수 있게 해달라는 요청이 있었습니다.
* **해결 방안**: 
  * 기존의 1-based 체크박스를 제거하고, `X Start` 및 `Y Start` 입력란을 좌측 폼에 추가했습니다.
  * 좌표 매핑 로직(`getPhysicalCoords`)에서 0-indexed로 정규화된 물리 좌표 `(xp, yp)`에 각각 설정된 `startX` 및 `startY` 오프셋 값을 합산하여 최종 물리 데이터베이스 좌표로 출력하도록 공식을 정밀화했습니다.
  * 기존 데이터를 로드(`loadExistingMap`)할 때도 데이터베이스에서 리턴된 최소 X, Y 좌표 값을 추적하여 `X Start`, `Y Start` 입력박스 값으로 자동 역산 및 주입하도록 하여 사용자 편의성을 높였습니다.

---

## 2. 주요 구현 사항

### A. 기하학적 오프셋 적용 공식 연동 (`client2/src/map_editor.js`)
```javascript
function getPhysicalCoords(colVisual, rowVisual, cols, rows, rotation, side, invertY, startX, startY) {
  // ... visual to physical (xp, yp) 0-indexed 변환 수행 ...
  
  // Handle Y inversion
  if (invertY) {
    yp = (rows - 1) - yp;
  }

  // 사용자가 임의 설정한 시작 인덱스만큼 변위 오프셋 추가
  const x = xp + startX;
  const y = yp + startY;

  return { x, y };
}
```

### B. 불러온 데이터로부터 시작 좌표 역산 자동 감지 (`client2/src/map_editor.js`)
```javascript
    // Guess dimensions & starting indices from loaded coordinates
    let maxX = 0;
    let maxY = 0;
    let minX = 9999;
    let minY = 9999;
    
    // ... data loop ...
    if (xNum < minX) minX = xNum;
    if (yNum < minY) minY = yNum;
    
    // Auto adjust grid sizing and index settings if coords were found
    if (count > 0) {
      el.gridStartX.value = minX;
      el.gridStartY.value = minY;
      
      const widthVal = maxX - minX + 1;
      const heightVal = maxY - minY + 1;
      
      el.gridCols.value = Math.max(widthVal, 10);
      el.gridRows.value = Math.max(heightVal, 10);
    }
```

---

## 3. 아키텍처 영향 보고
* **광범위한 특화 좌표계 수용**: 음수 좌표(-5부터 시작)나 오프셋 좌표(100부터 시작) 등 반도체 제조 기업들의 매우 다양한 설비 고유 원점 및 맵 좌표 규격을 단일 격자 에디터 안에서 완전히 수용할 수 있게 되었습니다.
* **정적 컴파일 완료**: Vite 빌드 최적화가 성공적으로 종료되었습니다.
