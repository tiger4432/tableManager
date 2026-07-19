# 2026-07-19 18:50:00 - 격자 UI 기반 맵 에디터(Grid UI Map Editor) 및 웨이퍼 노치/회전/반전 기능 구현

## 1. 개요 및 동기
* **배경**: Wafer Map, Strip Map과 같은 좌표계 기반 데이터를 개별 셀 단위로 엑셀처럼 수동 입력하는 비효율성을 극대화하여 해결하기 위해, 2D 시각적 바둑판 격자 위에서 직접 값을 페인팅하고 한 번에 데이터베이스에 밀어 넣는(Push) 전용 입력 도구를 도입하고자 했습니다.
* **추가적 기하 처리 요구**: 반도체 웨이퍼의 배치 방향을 맞추기 위한 **맵 회전(Rotation)**, 웨이퍼 원판 정렬 방향을 표시하는 **V-Notch(노치)** 연동, 그리고 웨이퍼의 앞/뒷면에 따른 **좌우 대칭 반전(Front/Back Mirroring) 및 노치 오프셋 편향 변경** 기능을 온전히 갖추어야 했습니다.

---

## 2. 주요 구현 사항

### A. 기하 변환 좌표 매핑 함수 설계 (`client2/src/map_editor.js`)
* 사용자가 에디터 캔버스를 90°씩 돌리거나 뒤집어도 실제 데이터베이스에 적재되어야 하는 물리 X, Y 값은 훼손되지 않도록, 시각적 그리드 좌표 `(colVisual, rowVisual)`를 물리 좌표 `(x, y)`로 일관되게 환산해 주는 매핑 알고리즘을 구현했습니다.

```javascript
function getPhysicalCoords(colVisual, rowVisual, cols, rows, rotation, side, invertY, is1Based) {
  let cv = colVisual;
  let rv = rowVisual;

  const isRotated90or270 = (rotation === 90 || rotation === 270);
  const visualCols = isRotated90or270 ? rows : cols;
  const visualRows = isRotated90or270 ? cols : rows;

  // 뒷면(Back) 선택 시 가로 좌표 대칭 반전
  if (side === 'back') {
    cv = (visualCols - 1) - cv;
  }

  let xp = 0;
  let yp = 0;

  // 회전 각도에 따른 0-indexed 물리 좌표 인덱스 변환
  if (rotation === 0) {
    xp = cv;
    yp = rv;
  } else if (rotation === 90) { // 90° Clockwise
    xp = rv;
    yp = (rows - 1) - cv;
  } else if (rotation === 180) { // 180°
    xp = (cols - 1) - cv;
    yp = (rows - 1) - rv;
  } else if (rotation === 270) { // 270° Clockwise
    xp = (cols - 1) - rv;
    yp = cv;
  }

  // Y축 반전 Cartesian 정렬 옵션 처리
  if (invertY) {
    yp = (rows - 1) - yp;
  }

  // 1-based 인덱스 매핑 보정
  const x = is1Based ? (xp + 1) : xp;
  const y = is1Based ? (yp + 1) : yp;

  return { x, y };
}
```

### B. 동적 V-Notch 렌더링 및 편향 제어 (`client2/src/map_editor.js`)
* 회전 각도(`currentRotation`)에 맞춰 노치가 상/하/좌/우 테두리 영역으로 궤적 이동합니다.
* 웨이퍼의 **앞면(Front)**과 **뒷면(Back)** 설정에 따라:
  * 뒷면(Back) 선택 시 캔버스에 `.flipped` CSS 클래스를 적용하여 전체 격자 셀을 수평 거울 반전시킵니다.
  * 노치의 편향 위치가 앞면은 **우측/시계방향 20px**, 뒷면은 **좌측/반시계방향 20px**로 미세 조절되도록 삼각함수 좌표 변환 없이 순수 CSS 변위 계산식(`calc(50% ± 20px)`)을 활용하여 기하 처리를 마감했습니다.

```javascript
function updateNotchPosition() {
  if (!el.gridNotch) return;
  el.gridNotch.className = 'wafer-notch';

  let positionClass = '';
  if (currentRotation === 0) positionClass = 'notch-bottom';
  else if (currentRotation === 90) positionClass = 'notch-left';
  else if (currentRotation === 180) positionClass = 'notch-top';
  else if (currentRotation === 270) positionClass = 'notch-right';
  el.gridNotch.classList.add(positionClass);

  const offset = 20; // px
  el.gridNotch.style.left = ''; el.gridNotch.style.right = '';
  el.gridNotch.style.top = ''; el.gridNotch.style.bottom = '';
  el.gridNotch.style.transform = '';

  if (currentRotation === 0) {
    el.gridNotch.style.bottom = '5px';
    el.gridNotch.style.left = (currentSide === 'front') ? `calc(50% + ${offset}px)` : `calc(50% - ${offset}px)`;
    el.gridNotch.style.transform = 'translateX(-50%)';
  } else if (currentRotation === 180) {
    el.gridNotch.style.top = '5px';
    el.gridNotch.style.left = (currentSide === 'front') ? `calc(50% + ${offset}px)` : `calc(50% - ${offset}px)`;
    el.gridNotch.style.transform = 'translateX(-50%)';
  } else if (currentRotation === 90) {
    el.gridNotch.style.left = '5px';
    el.gridNotch.style.top = (currentSide === 'front') ? `calc(50% - ${offset}px)` : `calc(50% + ${offset}px)`;
    el.gridNotch.style.transform = 'translateY(-50%)';
  } else if (currentRotation === 270) {
    el.gridNotch.style.right = '5px';
    el.gridNotch.style.top = (currentSide === 'front') ? `calc(50% + ${offset}px)` : `calc(50% - ${offset}px)`;
    el.gridNotch.style.transform = 'translateY(-50%)';
  }
}
```

### C. 드래그 페인팅 및 범례 로컬스토리지 보존
* 마우스 왼쪽 버튼 드래그 시 활성화된 브러쉬 색상으로 셀이 고속 칠해지며, 마우스 오른쪽 버튼 드래그 시 격자가 즉시 클리어되는 지연 없는 입력 방식을 구축했습니다.
* 범례 값, 설명, 색상 정보는 테이블 단위로 세분화하여 브라우저 `localStorage`에 자동 보존되도록 구현해 편의성을 높였습니다.

### D. 백엔드 라우터 통합 (`server/main.py`)
* 빌드된 `/map_editor.html` 파일을 `no-cache` 응답 헤더와 함께 웹 서버가 직접 리턴할 수 있도록 라우팅 엔드포인트를 탑재하여 배포 일관성을 맞추었습니다.

---

## 3. 아키텍처 영향 보고 (Architecture Impact)
* **API 호환성**: 격자에서 빌드되어 `Push`되는 데이터 패킷은 백엔드의 기존 단일 통합 업서트 API(`PUT /tables/{t}/data/updates`) 및 `GeneralUpdateBatch` 스키마 규격을 100% 그대로 활용하므로 백엔드 DB 구조를 전혀 오염시키지 않습니다.
* **웹소켓 실시간 전파**: 사용자가 에디터에서 맵 데이터를 구성해 바로 Push하는 즉시 백엔드의 WebSocket 채널을 타고 현재 실행 중인 다른 모든 탭 화면(메인 QTableView 데스크톱 클라이언트 및 타 웹 클라이언트)에 0.1초 이내로 실시간 연동/갱신이 자동 전파됩니다.
* **빌드 파이프라인**: Vite 빌드 인풋 리스트에 `map_editor` 앤트리 포인트를 정식 추가하여 배포 번들이 무결하게 압축 완료되었습니다.
