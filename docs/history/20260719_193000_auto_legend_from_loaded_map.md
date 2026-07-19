# 2026-07-19 19:30:00 - 격자 맵 에디터 데이터 로드 시 기존 칩 값(leg) 분석 기반 범례(Value Legend) 자동 생성 및 붓 연동 구현

## 1. 개요 및 동기
* **요구사항**: 서버로부터 기존 맵 데이터를 불러올 때(Load Map), 데이터베이스 레코드 내에 적재되어 있던 실제 칩 값(leg)들을 분석하여 범례(Value Legend)와 드로잉 브러쉬 리스트를 자동으로 구성하도록 고도화해달라는 요청이 있었습니다.
* **해결 방안**:
  * `loadExistingMap()` 함수 내에서 데이터베이스로부터 로드된 모든 좌표의 실제 밸류 값(예: `leg` 컬럼 값) 중 비어있지 않은 유니크한 값들을 실시간 수집(`uniqueVals = new Set()`)합니다.
  * 수집된 유니크한 값들을 바탕으로 범례 배열(`legend`)을 즉석에서 재구성합니다:
    * 이미 이전 범례 정의에 존재하던 값은 기존의 커스텀 설명(Description)과 사용자 지정 색상(Color)을 그대로 유지합니다.
    * 새롭게 발견된 값은 12가지 활기차고 뚜렷한 프리셋 색상 칩 목록 중 미사용된 색상을 골라 매핑하고 기본 설명(`BIN X` 혹은 `GOOD`/`FAIL`)을 부여합니다.
  * 범례 목록을 자동으로 영속화하고 새로고침하여, 로딩된 데이터의 첫 번째 범례 항목을 활성 드로잉 브러쉬(`activeBrush`)로 자동 선택해 줍니다.

---

## 2. 주요 구현 사항

### A. 유니크 밸류 수집 및 자동 범례 생성 알고리즘 (`client2/src/map_editor.js`)
```javascript
    // Guess dimensions and collect unique leg values from loaded coordinates
    const uniqueVals = new Set();
    // ... 데이터 로딩 루프 ...
    if (strVal !== '') {
      uniqueVals.add(strVal);
    }
    // ...

    // Auto detect legend from unique values
    if (uniqueVals.size > 0) {
      const predefinedColors = ['#10b981', '#ef4444', '#3b82f6', '#ec4899', '#f59e0b', '#8b5cf6', '#14b8a6', '#f43f5e', '#06b6d4', '#84cc16', '#a855f7', '#6b7280'];
      const newLegend = [];
      const usedColors = new Set();

      // 1. 기존 범례에 매칭되는 값이 있으면 설정된 설명/색상 보존
      uniqueVals.forEach(v => {
        const existingItem = legend.find(item => item.value === v);
        if (existingItem) {
          newLegend.push(existingItem);
          usedColors.add(existingItem.color);
        }
      });

      // 2. 새로운 고유 값에 대해 비중복 프리셋 색상 및 기본 명칭(BIN X) 지정
      let colorIdx = 0;
      uniqueVals.forEach(v => {
        const exists = newLegend.some(item => item.value === v);
        if (!exists) {
          let chosenColor = '';
          while (colorIdx < predefinedColors.length) {
            const candidate = predefinedColors[colorIdx++];
            if (!usedColors.has(candidate)) {
              chosenColor = candidate;
              break;
            }
          }
          if (!chosenColor) {
            chosenColor = '#' + Math.floor(Math.random()*16777215).toString(16).padStart(6, '0');
          }
          
          usedColors.add(chosenColor);
          newLegend.push({
            value: v,
            desc: v === '1' ? 'GOOD' : (v === '0' ? 'FAIL' : `BIN ${v}`),
            color: chosenColor
          });
        }
      });

      // 범례 배열 교체, 영속화, 붓 자동 선택 및 리렌더링
      legend = newLegend;
      saveLegendToStorage();
      
      if (legend.length > 0) {
        activeBrush = legend[0].value;
      } else {
        activeBrush = '';
      }
      renderLegendTable();
    }
```

---

## 3. 아키텍처 영향 보고
* **동적 맵 범례 동기화**: 맵 파일마다 칩 종류(양품 1/불량 0, 혹은 수십 가지의 Bin 코드로 구성된 맵 등)가 상이하더라도 사용자가 수동으로 범례 단계를 추가할 필요 없이, `Load Existing Map` 버튼 클릭 즉시 해당 맵의 데이터 속성에 완벽히 동기화된 전용 범례 툴바가 자동으로 즉석에서 빌드되어 제공됩니다.
* **정적 컴파일 완료**: Vite 최적화 빌드가 무사 통과되었습니다.
