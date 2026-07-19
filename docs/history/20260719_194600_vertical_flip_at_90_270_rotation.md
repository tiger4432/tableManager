# 2026-07-19 19:46:00 - 격자 맵 에디터 회전각 90°/270° 상태에서 앞/뒷면 전환 시 수직(위아래) 반전 처리 구현

## 1. 개요 및 동기
* **요구사항**: 
  * 웨이퍼 각도가 90°(Notch가 우측에 위치) 또는 270°(Notch가 좌측에 위치)인 상태에서 앞/뒷면(FRONT/BACK)을 뒤집는 경우, 물리적인 기판 반전 기준상 좌우가 아닌 **수직(위아래) 방향으로 뒤집혀야(Vertical Flip) 마땅합니다.**
  * 기존에는 모든 각도에서 동일하게 가로(좌우) 반전만 고정 적용하고 있어 90°/270° 회전된 웨이퍼를 뒤집을 때 Notch의 상대적 고정 좌표 및 셀 인덱스 매핑이 왜곡되는 문제가 존재했습니다.
* **해결 방안**:
  * 좌표 산출 함수 `getPhysicalCoords()` 내부의 면 반전 연산식을 현재 회전각 상태에 반응하여 달라지도록 개편했습니다:
    * `rotation`이 `90` 또는 `270`일 때: visual Y축에 해당하는 **행 인덱스(`rv = (visualRows - 1) - rv`)를 수직 반전**합니다.
    * `rotation`이 `0` 또는 `180`일 때: visual X축에 해당하는 **열 인덱스(`cv = (visualCols - 1) - cv`)를 가로 반전**합니다.
  * 또한, Notch의 위치를 강제로 바꾸던 이전의 라디오 전환 시 회전각 보정 수식을 제거하여, Notch의 화면상 시각적 위치는 변하지 않은 채 내부 좌표계만 물리 법칙에 맞게 위아래로 정확하게 뒤집히도록 연동 상태를 안정화했습니다.

---

## 2. 주요 구현 사항

### A. 회전각을 반영한 가변축 반전 알고리즘 (`client2/src/map_editor.js`)
* `getPhysicalCoords()` 함수 내에 회전각에 따른 수평/수직 분기 연산식을 삽입했습니다.
```javascript
function getPhysicalCoords(colVisual, rowVisual, cols, rows, rotation, side, invertY, startX, startY) {
  let cv = colVisual;
  let rv = rowVisual;

  const isRotated90or270 = (rotation === 90 || rotation === 270);
  const visualCols = isRotated90or270 ? rows : cols;
  const visualRows = isRotated90or270 ? cols : rows;

  // Mirror if back side (horizontal flip at 0/180, vertical flip at 90/270)
  if (side === 'back') {
    if (rotation === 90 || rotation === 270) {
      rv = (visualRows - 1) - rv; // 90도/270도 상태에서는 수직 반전 (위아래 뒤집힘)
    } else {
      cv = (visualCols - 1) - cv; // 0도/180도 상태에서는 수평 반전 (좌우 뒤집힘)
    }
  }
  // ... 이후 인덱스 매핑 연산 진행 ...
}
```

---

## 3. 아키텍처 영향 보고
* **기하학적 물리 정합성 완성**: 90°/270° 회전 각도 상태에서 FRONT ↔ BACK 토글 시 화면상에서 위아래 대칭축을 중심으로 셀 맵이 완벽하게 상하 반전되어 3차원 공정 장비의 물리적 웨이퍼 뒤집기(Flipping) 운동을 완전무결하게 모사합니다.
* **정적 빌드 완료**: Vite 프로덕션 빌드가 성공했습니다.
