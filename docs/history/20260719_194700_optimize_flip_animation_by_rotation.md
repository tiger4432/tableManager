# 2026-07-19 19:47:00 - 격자 맵 에디터 FRONT/BACK 전환 시 CSS 3D 플립 애니메이션 각도별 최적화 (수직/수평 전환)

## 1. 개요 및 동기
* **문제점**: 
  * 회전각이 90° 또는 270°인 상태에서 면 전환 시 물리적인 좌표 맵은 정상적으로 수직(위아래)으로 정렬되었으나, CSS 애니메이션이 여전히 수평(좌우) 반전(`scaleX(-1)`)으로만 고정되어 실행되다 보니 화면이 돌아가는 도중에 시각적으로 칩들이 어긋나서 뒤집히는 이질적인 느낌(Jarring Visual Mismatch)이 존재했습니다.
* **해결 방안**:
  * 회전각에 상응하는 CSS 3D 반전 가상 클래스(`.flipped-vertical`)를 신설했습니다.
  * `currentRotation`이 `90°` 또는 `270°`일 때는 캔버스에 수직 3D 플립(`scaleY(-1)`)을 가하고, `0°` 또는 `180°`일 때는 기존처럼 수평 3D 플립(`scaleX(-1)`)을 부여하도록 렌더러와 스타일시트를 정렬했습니다.
  * 반전 시 내부 텍스트가 거꾸로 보이지 않도록 역반전(Reverse-Scale) 처리 역시 수평/수직 각각의 축에 맞춰 완전 보정했습니다.

---

## 2. 주요 구현 사항

### A. 회전축 대응형 가상 클래스 동적 분기 (`client2/src/map_editor.js`)
* `renderGridCanvas`에서 현재 면(Side)과 각도(Rotation)를 조회하여 최적의 플립 애니메이션 클래스를 캔버스 노드에 바인딩합니다.
```javascript
  // Mirror effect animation class based on rotation
  if (currentSide === 'back') {
    if (currentRotation === 90 || currentRotation === 270) {
      el.gridCanvas.classList.add('flipped-vertical');
      el.gridCanvas.classList.remove('flipped');
    } else {
      el.gridCanvas.classList.add('flipped');
      el.gridCanvas.classList.remove('flipped-vertical');
    }
  } else {
    el.gridCanvas.classList.remove('flipped');
    el.gridCanvas.classList.remove('flipped-vertical');
  }
```

### B. 수평 및 수직 반전 애니메이션 CSS 분기 구성 (`client2/src/style.css`)
```css
/* 뒷면(Back) 좌우 대칭 반전 스타일 (0도, 180도) */
.map-grid-canvas.flipped {
  transform: scaleX(-1);
}
.map-grid-canvas.flipped .grid-cell {
  transform: scaleX(-1);
}
.map-grid-canvas.flipped .grid-cell:hover {
  transform: scaleX(-1) scale(1.05);
}

/* 뒷면(Back) 상하 대칭 반전 스타일 (90도, 270도) */
.map-grid-canvas.flipped-vertical {
  transform: scaleY(-1);
}
.map-grid-canvas.flipped-vertical .grid-cell {
  transform: scaleY(-1);
}
.map-grid-canvas.flipped-vertical .grid-cell:hover {
  transform: scaleY(-1) scale(1.05);
}
```

---

## 3. 아키텍처 영향 보고
* **시각 효과와 데이터의 100% 정합**: 전환 트랜지션 애니메이션과 백엔드 물리 좌표계 정렬이 동일하게 수직 축으로 완전히 통일되어, 전환 순간 및 전환 후의 조작이 물 흐르듯 직관적으로 연결됩니다.
* **정적 빌드 완료**: Vite 프로덕션 컴파일이 성공적으로 수행되었습니다.
