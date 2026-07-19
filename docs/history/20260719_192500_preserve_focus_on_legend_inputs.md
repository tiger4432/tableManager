# 2026-07-19 19:25:00 - 격자 맵 에디터 범례 입력란 포커스 이탈(Focus Theft) 방지 및 이벤트 반응형 최적화

## 1. 개요 및 동기
* **문제점**: 
  * 범례 값(`inputVal`)을 수정하거나 브러쉬를 바꿀 때마다 `renderLegendTable()`이 호출되어 테이블 DOM 전체가 삭제된 후 처음부터 재생성되었습니다.
  * 이 때문에 사용자가 엔터를 치거나 마우스 클릭을 다르게 할 때 인풋의 포커스가 완전히 증발(이탈)해 연속적인 텍스트 수정 및 탭(Tab) 키를 이용한 포커스 이동이 불가능한 심각한 조작성 훼손이 있었습니다.
* **해결 방안**:
  * 입력 시 전체 테이블 DOM을 무너뜨리는 비효율적인 전체 재렌더링 방식을 완전히 배제했습니다.
  * 범례 값을 수정해도 DOM 재생성 없이 텍스트 필드의 포커스가 그대로 유지되도록 처리했고, 브러쉬 선택 시에도 DOM 훼손 없이 기존 행 요소들의 `.legend-row-active` 클래스만 유연하게 전환(class toggling)하도록 로직을 리팩토링했습니다.

---

## 2. 주요 구현 사항

### A. DOM 재생성 없는 유연한 브러쉬 클래스 전환 (`client2/src/map_editor.js`)
* `selectBrush` 실행 시 `renderLegendTable()` 대신 기존 요소들의 `dataset.value`를 추적해 액티브 테두리 클래스만 토글하도록 교정했습니다.

```javascript
function selectBrush(val) {
  activeBrush = val;
  
  // 브러쉬 정보 바 갱신
  const item = legend.find(l => l.value === val);
  if (item) {
    el.activeBrushVal.textContent = `${item.value} (${item.desc})`;
    el.activeBrushVal.style.color = item.color;
  } else {
    el.activeBrushVal.textContent = 'None';
    el.activeBrushVal.style.color = 'var(--text-dim)';
  }

  // DOM 파괴 없이 기존 tr 노드들의 클래스명만 토글하여 포커스 보존
  const rows = el.legendList.querySelectorAll('.legend-row');
  rows.forEach(row => {
    if (row.dataset.value === val) {
      row.classList.add('legend-row-active');
    } else {
      row.classList.remove('legend-row-active');
    }
  });
}
```

### B. 변경 이벤트 리팩토링 (`client2/src/map_editor.js`)
* `inputVal` 내용 수정 시 테이블을 다시 그리지 않고, `dataset.value` 속성값만 업데이트한 후 백그라운드 스토리지 및 와이퍼 캔버스만 재렌더링하여 포커스를 완벽히 가둡니다.

```javascript
    inputVal.addEventListener('change', (e) => {
      // ... 중복 체크 등 수행 ...
      item.value = newVal;
      remapGridValues(oldVal, newVal);
      if (activeBrush === oldVal) {
        activeBrush = newVal;
        row.dataset.value = newVal;
        el.activeBrushVal.textContent = `${newVal} (${item.desc})`;
      } else {
        row.dataset.value = newVal;
      }
      saveLegendToStorage();
      renderGridCanvas(); // 범례 테이블은 건드리지 않고 캔버스만 갱신
    });
```

---

## 3. 아키텍처 영향 보고
* **포커스 보존형 디자인 확보**: 연속적인 범례 텍스트 수정 및 탭(Tab) 이동이 한 템포도 끊김 없이 부드럽게 이어집니다.
* **정적 컴파일 완료**: Vite 프로덕션 빌드가 성공적으로 종료되었습니다.
