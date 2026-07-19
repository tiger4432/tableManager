# 2026-07-19 19:52:00 - 격자 맵 에디터 저장 시 모든 활성 좌표 저장 및 빈 셀 NULL 바인딩 구현

## 1. 개요 및 동기
* **요구사항**: 
  * 에디터에서 맵 데이터를 적재(Push)할 때, 칠해진 칩 데이터가 존재하는 셀뿐만 아니라 **화면에 표시된 모든 유효 좌표(Wafer 원형 마스크 내부 영역의 모든 셀)를 NULL 값을 포함하여 통째로 저장**해야 합니다.
  * 기존에는 값이 없는 빈 셀(`val === ''`)의 경우 업데이트 컬럼 페이로드에서 단순히 생략(`continue`)하도록 처리되어 있었습니다. 이 경우, 이미 DB에 등록되어 있던 칩을 에디터에서 지우고 저장하더라도 DB 상에는 삭제(NULL로 변경) 내용이 반영되지 않고 기존 값 그대로 방치되는 문제와, 미할당 영역의 레코드 생성이 누락되는 문제가 공존했습니다.
* **해결 방안**:
  * 맵 저장 함수 `pushMapData()`의 데이터 수집 루프를 기존 `gridData` 키 순회 방식에서 **화면상의 유효 그리드 행/열 루프 방식**으로 전면 전환했습니다.
  * 웨이퍼 마스크 원 안의 셀(`.cell-inside-wafer`)에 해당하는 모든 좌표에 대해:
    * 값이 칠해진 셀: 해당 BIN 번호(또는 등급 코드)를 기입합니다.
    * 값이 없는 빈 셀(Empty / Erased): **데이터베이스 `NULL` 값**으로 매핑하여 수집합니다.
  * 이로써 전체 격자 내부 칩의 상태(NULL 업데이트 포함)가 한 번의 Push만으로 완벽히 동기화 및 덮어쓰기됩니다.

---

## 2. 주요 구현 사항

### A. 화면상의 모든 웨이퍼 셀 루프 및 NULL 수집 처리 (`client2/src/map_editor.js`)
* 마스크 외부를 제외한 모든 디스크립터 셀을 대상으로 `null` 값을 할당해 updates 배열을 생성합니다.

```javascript
  const cols = parseInt(el.gridCols.value, 10) || 10;
  const rows = parseInt(el.gridRows.value, 10) || 10;
  const startX = parseInt(el.gridStartX.value, 10) || 0;
  const startY = parseInt(el.gridStartY.value, 10) || 0;
  const invertY = el.gridYInvert.checked;

  const isRotated90or270 = (currentRotation === 90 || currentRotation === 270);
  const visualCols = isRotated90or270 ? rows : cols;
  const visualRows = isRotated90or270 ? cols : rows;

  for (let r = 0; r < visualRows; r++) {
    for (let c = 0; c < visualCols; c++) {
      // 1. 웨이퍼 원형 경계선 마스크 내부 검사
      const u1 = (2 * c - visualCols) / visualCols;
      const u2 = (2 * (c + 1) - visualCols) / visualCols;
      const v1 = (2 * r - visualRows) / visualRows;
      const v2 = (2 * (r + 1) - visualRows) / visualRows;

      const maxU2 = Math.max(u1 * u1, u2 * u2);
      const maxV2 = Math.max(v1 * v1, v2 * v2);
      const dMax2 = maxU2 + maxV2;

      const completelyInside = (dMax2 <= 1.0);
      if (!completelyInside) continue; // 마스크 외부 빈 셀 차단

      const coords = getPhysicalCoords(c, r, cols, rows, currentRotation, currentSide, invertY, startX, startY);
      const key = `${coords.x}_${coords.y}`;
      const val = gridData[key] || '';

      // 2. 빈 칸은 DB에 NULL로 반영하기 위해 null 대입
      let valParsed = null;
      if (val !== '') {
        valParsed = valType === 'number' ? Number(val) : val;
      }

      let xParsed = xType === 'number' ? parseInt(coords.x, 10) : String(coords.x);
      let yParsed = yType === 'number' ? parseInt(coords.y, 10) : String(coords.y);

      const rowUpdates = {
        [xCol]: xParsed,
        [yCol]: yParsed,
        [valCol]: valParsed,
        ...metaValues
      };

      if (gridMetaStr) {
        rowUpdates['grid_metadata'] = gridMetaStr;
      }

      const updateItem = {
        updates: rowUpdates,
        source_name: 'user',
        updated_by: CURRENT_USER
      };
      updates.push(updateItem);
    }
  }
```

---

## 3. 아키텍처 영향 보고
* **안전한 지우기 동기화**: 격자 맵 에디터에서 드래그 지우개 기능으로 지운 칩들이 이제 `null` 값으로 DB에 정확히 업서트되어 기존 레코드에 잔류하던 이전 칩 정보가 안전하게 덮어쓰여지고 초기화됩니다.
* **정적 빌드 완료**: Vite 빌드 최적화가 에러 없이 최종 통과되었습니다.
