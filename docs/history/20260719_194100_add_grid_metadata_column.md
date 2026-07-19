# 2026-07-19 19:41:00 - 격자 맵 에디터 동적 물리 테이블 내 grid_metadata 컬럼 추가 및 레이아웃 동기화 구현

## 1. 개요 및 동기
* **배경**: 
  * 기존 테이블 구조에서 맵의 너비, 높이, 원점 시작좌표 등은 칩 데이터 좌표의 최솟값/최댓값을 기반으로 자동 역산(Guessing)되어 복원되었습니다. 이로 인해 외곽의 빈 마진 영역 유실, 임의 설정한 원점 및 회전/반전 뷰포트 설정 유실이 발생했습니다.
  * 레이아웃 전용 테이블을 별도로 구성하는 경우, 관리 대상 테이블 삭제 시 관계 동기화 및 외래키 연계 삭제 처리가 복잡해진다는 구조적 불편함이 발생할 수 있습니다.
* **해결 방안**:
  * 테이블을 쪼개지 않는 대신, 동적 물리 테이블인 `bonding_map`에 **`grid_metadata` 컬럼을 직접 추가**해 동일 테이블 안에서 레이아웃 설정 데이터가 칩 데이터와 생명 주기를 완벽하게 함께하도록(Cascaded Delete) 구성했습니다.
  * `table_config.json`의 `bonding_map` 스키마 정의 내에 `"grid_metadata": "string"`을 신설하여, 백엔드 기동 시 자동으로 `ALTER TABLE bonding_map ADD COLUMN grid_metadata VARCHAR` 마이그레이션이 수행되도록 조치했습니다.
  * 데이터 저장 시(`pushMapData`), 에디터의 레이아웃 설정 상태값을 직렬화하여 각 칩 행의 `grid_metadata` 필드에 함께 실어 업서트합니다.
  * 데이터 로드 시(`loadExistingMap`), 가져온 칩 행들로부터 `grid_metadata` 값을 역직렬화(JSON.parse)하여 격자 크기, X/Y 시작 위치, Y축 반전 여부, Notch 방향, 회전각 등의 설정을 한치의 어긋남 없이 안전하게 복원하도록 처리했습니다.

---

## 2. 주요 구현 사항

### A. 맵 스키마 확장 (`server/config/table_config.json`)
```json
  "bonding_map": {
    "business_key": "pkg_id",
    "composite_key_source": ["base", "x", "y"],
    "composite_key_separator": "_",
    "column_types": {
      "pkg_id": "string",
      "base": "string",
      "x": "number",
      "y": "number",
      "leg": "string",
      "grid_metadata": "string"
    },
    "display_columns": [
      "pkg_id",
      "base",
      "x",
      "y",
      "leg",
      "grid_metadata"
    ]
  }
```

### B. 맵 불러올 시 레이아웃 정보 복원 (`client2/src/map_editor.js`)
```javascript
    let loadedGridMeta = null;

    if (result && result.data) {
      result.data.forEach(row => {
        const rowData = row.data || {};
        // ... 생략 ...
        const gridMetaVal = rowData['grid_metadata']?.value;

        if (gridMetaVal && !loadedGridMeta) {
          try {
            loadedGridMeta = JSON.parse(gridMetaVal);
          } catch (e) {
            console.error('Failed to parse grid_metadata:', e);
          }
        }
        // ... 생략 ...
      });
    }

    // 메타데이터 정보가 로드된 경우 해당 레이아웃 설정 값들로 뷰포트 상태 강제 동기화
    if (loadedGridMeta) {
      el.gridCols.value = loadedGridMeta.grid_cols;
      el.gridRows.value = loadedGridMeta.grid_rows;
      el.gridStartX.value = loadedGridMeta.grid_start_x;
      el.gridStartY.value = loadedGridMeta.grid_start_y;
      el.gridYInvert.checked = loadedGridMeta.grid_y_invert;
      currentRotation = loadedGridMeta.rotation || 0;
      currentSide = loadedGridMeta.side || 'front';
    } else if (count > 0) {
      // 메타데이터가 존재하지 않는 기존 맵의 경우 역산(Guessing) 로직을 Fallback으로 사용
      el.gridStartX.value = minX;
      el.gridStartY.value = minY;
      // ...
    }
```

### C. 맵 저장 시 레이아웃 정보 패키징 (`client2/src/map_editor.js`)
```javascript
  // Serialize current grid metadata config if the table supports it
  let gridMetaStr = null;
  if (tableSchema.column_types && tableSchema.column_types['grid_metadata']) {
    const gridMeta = {
      grid_cols: parseInt(el.gridCols.value, 10) || 10,
      grid_rows: parseInt(el.gridRows.value, 10) || 10,
      grid_start_x: parseInt(el.gridStartX.value, 10) || 0,
      grid_start_y: parseInt(el.gridStartY.value, 10) || 0,
      grid_y_invert: el.gridYInvert.checked,
      rotation: currentRotation,
      side: currentSide
    };
    gridMetaStr = JSON.stringify(gridMeta);
  }

  for (const key of Object.keys(gridData)) {
    // ... 칩 데이터 루프 ...
    const rowUpdates = {
      [xCol]: xParsed,
      [yCol]: yParsed,
      [valCol]: valParsed,
      ...metaValues
    };

    if (gridMetaStr) {
      rowUpdates['grid_metadata'] = gridMetaStr;
    }
    // ...
  }
```

---

## 3. 아키텍처 영향 보고
* **종속성 동기화 간결화**: 레이아웃 정보(`grid_metadata`)가 테이블을 구성하는 개별 데이터와 완전히 생명 주기를 같이 하므로, 특정 데이터 삭제/이전 시 다른 설정 테이블을 동반 삭제할 필요 없이 일반적인 SQL `DELETE` 처리만으로 완벽한 동기화 및 동반 삭제가 성립합니다.
* **마이그레이션 자동 처리**: 핫스왑 마이그레이션 모듈이 백엔드 구동 시 스키마를 검출하여 컬럼 추가 처리를 안전하게 완수했습니다.
* **정적 빌드 완성**: Vite 프로덕션 빌드가 성공했습니다.
