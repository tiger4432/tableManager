# 2026-07-19 19:31:00 - 격자 맵 에디터 드래그 페인팅 시 기존 칩 값 보존(Protect Existing Values on Drag Painting) 연산 구현

## 1. 개요 및 동기
* **요구사항**: 
  * 마우스 드래그를 통해 넓은 영역의 빈 셀(Empty cell)을 일괄적으로 드로잉(채색)할 수 있도록 지원하되,
  * 이미 개별적으로 세팅해 둔 기존 셀의 중요 값(Leg/Bin 값)들이 드래그 붓질 도중에 실수로 덮어쓰여(Overwrite) 훼손되지 않도록 보호해달라는 기능 보완 요구사항이 있었습니다.
* **해결 방안**:
  * 마우스 드래그 이벤트가 수행될 때(`mouseenter` 시점의 `handleCellClick(cell)` 호출로, 두 번째 인자인 `event` 객체가 넘어가지 않음), 해당 셀의 상태를 먼저 체크합니다.
  * 드래그 중인 셀의 데이터가 비어있지 않다면(`gridData[key] !== ''`), 브러쉬 업데이트 적용을 즉시 건너뛰고 기존 값을 완전 보존(`return`)하도록 로직을 세분화했습니다.
  * 단, 단일 칩을 정확하게 타겟팅하여 직접 좌클릭하는 단독 클릭(`click` 혹은 `mousedown` 시점에 `event` 객체가 주입됨)의 경우에는 사용자의 명시적 덮어쓰기 의도로 판단하여 정상 오버라이트 수용합니다.
  * 더불어 우클릭 드래그 지우기(Erase) 역시 대단위 초기화를 원하는 사용자의 액션이므로 예외 없이 시원하게 지워집니다.

---

## 2. 주요 구현 사항

### A. 드래그 조작 판별 및 기존값 우회 분기 추가 (`client2/src/map_editor.js`)
```javascript
function handleCellClick(cell, event) {
  // ... 원점 모드 등 선행 체크 ...

  let isRight = isRightDrag;
  if (event) {
    isRight = (event.button === 2 || event.buttons === 2);
  }

  const key = cell.dataset.key;
  if (isRight) {
    // 우클릭 지우기는 드래그/클릭 불문하고 기존값 삭제 허용
    gridData[key] = '';
    // ... 셀 UI 비우기 ...
  } else {
    // Draw cell
    if (activeBrush !== undefined && activeBrush !== null) {
      // 마우스 '드래그 드로잉' 중(event 객체가 없음)이고, 
      // 해당 셀에 이미 다른 값이 기입되어 있다면 기존값 안전 보존!
      if (!event && gridData[key] !== '') {
        return;
      }
      
      gridData[key] = activeBrush;
      // ... 셀 UI 브러쉬 입히기 ...
    }
  }
}
```

---

## 3. 아키텍처 영향 보고
* **안전한 일괄 드로잉 지원**: 사용자는 이미 마킹해 놓은 다른 BIN 코드를 지워버릴 걱정 없이, 빈 격자 영역에 마우스를 대고 넓게 원을 그리거나 선을 그어 드래그 방식으로 안전하게 일괄 빈 칩 데이터만 대량 변경할 수 있습니다.
* **정적 컴파일 완료**: Vite 빌드 최적화가 무결하게 완료되었습니다.
