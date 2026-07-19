# 2026-07-19 19:45:00 - 격자 맵 에디터 FRONT/BACK 면 반전 시 회전각(Rotation) 물리 상태 연동 처리 구현

## 1. 개요 및 동기
* **배경 및 요구사항**: 
  * 3차원 형태의 칩/웨이퍼 구조상, 웨이퍼를 앞면(FRONT)에서 뒷면(BACK)으로 뒤집는 경우(좌우 대칭 변환), 물리적 회전각 상태(Notch의 위치) 역시 대칭적으로 변환됩니다.
  * 예를 들어, Notch가 우측에 있던 상태(90° 회전)에서 웨이퍼를 좌우로 뒤집으면 Notch가 좌측(270° 회전)으로 이동해야 물리적인 Notch 방향과 일치합니다.
  * 따라서, 앞/뒷면 전환(FRONT <-> BACK) 발생 시 현재 활성화된 회전각(Rotation)의 물리적 위치 변화를 대칭적으로 고려하여 자동 반전 처리되도록 개선 요청이 있었습니다.
* **해결 방안**:
  * 면 전환 라디오 단추(`wafer-side`)의 값이 바뀔 때, 현재 적용된 `currentRotation` 상태값을 동적으로 가공하도록 개편했습니다:
    * `90° (우측 Notch)` ↔ `270° (좌측 Notch)` 상태를 양방향 자동 반전 변환합니다.
    * `0° (하단 Notch)` 및 `180° (상단 Notch)`는 좌우 뒤집기 시에도 위치가 변하지 않으므로 보존합니다.
  * 물리 상태 변화에 맞춰 화면 내 4개 각도 조작 버튼(`.btn-rot`)의 활성화 상태(`active` 클래스)도 동적으로 스위칭되도록 수정하여 시인성을 일치시켰습니다.
  * 또한 기존 맵 정보 로딩 시 복원되는 면/회전 정보도 UI 컨트롤 폼에 동적으로 반영되도록 Sync 블록을 확립했습니다.

---

## 2. 주요 구현 사항

### A. 면 전환 이벤트 연동 및 회전각 대칭 변환 (`client2/src/map_editor.js`)
```javascript
  // Wafer Side Radios
  document.querySelectorAll('input[name="wafer-side"]').forEach(radio => {
    radio.addEventListener('change', (e) => {
      const oldSide = currentSide;
      const newSide = e.target.value;
      if (oldSide !== newSide) {
        currentSide = newSide;

        // FRONT/BACK 플립 시 Notch 대칭 방향 반전: 90° ↔ 270° (0°와 180°는 불변)
        if (currentRotation === 90) {
          currentRotation = 270;
        } else if (currentRotation === 270) {
          currentRotation = 90;
        }

        // 회전 버튼 UI 상태 스위칭 동기화
        document.querySelectorAll('.btn-rot').forEach(btn => {
          const rotVal = parseInt(btn.dataset.rot, 10);
          if (rotVal === currentRotation) {
            btn.classList.add('active');
          } else {
            btn.classList.remove('active');
          }
        });

        renderGridCanvas();
      }
    });
  });
```

### B. 데이터 로딩 시 UI 폼 값 바인딩 동기화 (`client2/src/map_editor.js`)
* 기존 DB 데이터 로드 시 복원된 회전각/면 설정 상태가 화면 컨트롤러와 싱크를 이루도록 폼 조작 코드를 추가했습니다.
```javascript
    if (loadedGridMeta) {
      el.gridCols.value = loadedGridMeta.grid_cols;
      el.gridRows.value = loadedGridMeta.grid_rows;
      el.gridStartX.value = loadedGridMeta.grid_start_x;
      el.gridStartY.value = loadedGridMeta.grid_start_y;
      el.gridYInvert.checked = loadedGridMeta.grid_y_invert;
      currentRotation = loadedGridMeta.rotation || 0;
      currentSide = loadedGridMeta.side || 'front';

      // 라디오 버튼 선택상태 갱신
      document.querySelectorAll('input[name="wafer-side"]').forEach(radio => {
        if (radio.value === currentSide) {
          radio.checked = true;
        }
      });

      // 회전각 버튼 active 상태 갱신
      document.querySelectorAll('.btn-rot').forEach(btn => {
        const rotVal = parseInt(btn.dataset.rot, 10);
        if (rotVal === currentRotation) {
          btn.classList.add('active');
        } else {
          btn.classList.remove('active');
        }
      });
    }
```

---

## 3. 아키텍처 영향 보고
* **정합성 높은 물리 모델 확립**: 웨이퍼 공정의 실제 거동(기판 반전)과 콘솔 시뮬레이션의 동작 방식이 100% 기하학적으로 일치하므로 현장 작업 시의 인지 왜곡이 제거되었습니다.
* **정적 빌드 완료**: Vite 프로덕션 빌드가 에러 없이 정상 종료되었습니다.
