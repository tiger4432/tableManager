# 2026-07-19 19:35:00 - 격자 맵 에디터 사각 드래그 시 미초기화 빈 셀(undefined) 예외 처리 및 변경 불가 오동작 해결

## 1. 개요 및 동기
* **문제점**: 
  * 사각 드래그를 실행했을 때 파란색 드래그 선택 범위 박스는 정상적으로 나타나지만, 마우스를 뗐을 때 비어있던 셀들의 색상과 텍스트가 실제로 변경되지 않는 버그가 보고되었습니다.
  * 이는 데이터베이스나 로컬 배열에서 한 번도 수정되지 않은 순수 빈 셀들의 좌표 키(`gridData[key]`)가 파이썬/JS 상에서 `undefined` 상태를 가지기 때문이었습니다.
  * 기존 조건식인 `gridData[key] !== ''`는 `undefined !== ''` 조건이 `true`로 해석되어, 빈 셀임에도 불구하고 "이미 값이 들어있는 기존 셀"로 잘못 오인하여 채색 루프를 도중에 즉시 탈출(`return`)해 버린 것이 원인이었습니다.
* **해결 방안**:
  * 비어 있는 셀 상태의 판단 기준을 `gridData[key] || ''`로 정제하여 `undefined` 값도 빈 문자열(`''`)로 엄격하게 안전 변환(Normalization)을 거치도록 수정했습니다.
  * 이로써 빈 셀에 대한 판정이 올바르게 내려져, 마우스를 놓는 즉시 선택 구역 안의 모든 빈 셀들이 지정한 브러쉬 색상으로 완벽하게 일괄 채색되도록 해결했습니다.

---

## 2. 주요 구현 사항

### A. undefined 변동 처리 및 조건 검사 보정 (`client2/src/map_editor.js`)
* 글로벌 마우스 업 핸들러 내부에서 undefined 값을 빈 문자열로 수렴 처리하여 예외를 원천 차단했습니다.

```javascript
      selectedCells.forEach(cell => {
        const key = cell.dataset.key;
        if (cell.classList.contains('cell-outside-wafer')) return;

        // undefined 값도 '' 로 변환하여 기존 값 존재 여부를 정확히 판정!
        const existingVal = gridData[key] || '';
        if (!isSingleClick && existingVal !== '') {
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
```

---

## 3. 아키텍처 영향 보고
* **안정적인 데이터 상태 관리**: 격자 구조의 전체 맵 데이터가 온전히 DB에서 오지 않았거나 초기화되지 않은 상태에서 드래그하여 영역을 칠하더라도, 유실 없이 모든 미할당 메모리 키값들이 동기적으로 생성되어 정상 매핑됩니다.
* **정적 컴파일 완료**: Vite 빌드 최적화가 에러 없이 최종 완료되었습니다.
