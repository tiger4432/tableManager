# 2026-07-19 19:50:00 - 격자 맵 에디터 회전각/앞뒷면 무관 화면 좌표계 고정 (Visual Screen Coords Mapping) 구현

## 1. 개요 및 동기
* **요구사항**:
  * 웨이퍼의 회전 각도(0°, 90°, 180°, 270°) 및 앞/뒷면(FRONT/BACK) 반전 여부와 무관하게, 에디터 화면에 보이는 격자의 좌표계 설정(X축, Y축)은 항상 사용자가 눈으로 보는 방향 그대로 일치되어 계산 및 저장되기를 요청했습니다.
  * 기존에는 회전이나 플립이 가해지면 physical 매핑 수식에 의해 내부 X, Y 좌표가 회전하고 뒤집혀, 화면 좌상단의 인덱스가 startX, startY가 아닌 다른 물리적 원천 좌표로 변형되었습니다.
* **해결 방안**:
  * 좌표 변환 연산 함수 `getPhysicalCoords()`를 획기적으로 간소화하여, 화면상의 visual 컬럼 인덱스(`colVisual`)와 visual 행 인덱스(`rowVisual`)에 직접 시작 변위(`startX`, `startY`) 및 Y축 반전(Invert Y)만 바인딩하도록 강제했습니다.
  * 회전 및 반전은 화면상의 Notch 데코레이션, 원형 아웃라인 바운더리 검사, CSS 3D 플립 연출에만 시각적 효과로 기여하며, **각 셀에 기입되는 실데이터 좌표 (X, Y)는 어떠한 회전/반전 속에서도 항상 화면 눈에 보이는 그대로 (가로 = X축 증가, 세로 = Y축 증가/감소) 매핑**됩니다.

---

## 2. 주요 구현 사항

### A. 화면 시각 지향적 좌표 매핑 함수 간소화 (`client2/src/map_editor.js`)
* 회전각 및 뒤집기 변위 연산을 배제하고 화면 좌표축 정렬을 우선하도록 수정했습니다.

```javascript
function getPhysicalCoords(colVisual, rowVisual, cols, rows, rotation, side, invertY, startX, startY) {
  const isRotated90or270 = (rotation === 90 || rotation === 270);
  const visualCols = isRotated90or270 ? rows : cols;
  const visualRows = isRotated90or270 ? cols : rows;

  // 회전각 및 FRONT/BACK 무관하게 화면에 보이는 그대로 X/Y 인덱스 매핑
  const xp = colVisual;
  let yp = rowVisual;

  // Y축 반전 옵션 체크 시 화면 높이(visualRows) 기준으로만 상하 대칭 변환
  if (invertY) {
    yp = (visualRows - 1) - yp;
  }

  const x = xp + startX;
  const y = yp + startY;

  return { x, y };
}
```

---

## 3. 아키텍처 영향 보고
* **직관적인 좌표계 운용**: 회전 및 기판 뒤집기 조작을 수행하더라도 칩 내부의 좌표 및 데이터베이스 적재 데이터는 **언제나 화면 뷰포트의 좌상단 -> 우하단 증감축 규칙**을 엄격히 준수하므로, 물리적 좌표 계산의 혼선이 완전히 종식되었습니다.
* **정적 빌드 완료**: Vite 빌드 최적화가 에러 없이 최종 통과되었습니다.
