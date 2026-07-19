# 2026-07-19 19:15:00 - 격자 맵 에디터 외각 미포함 칩 완전 차단 및 원 테두리 시인성 개선

## 1. 개요 및 동기
* **요구사항**: 
  1. 웨이퍼 원판 경계선에서 벗어난 영역(원 밖으로 나갔거나 경계에 걸쳐 불완전하게 포함된 셀)을 시각적 및 기능적으로 **클린하게 차단(완전 비가시화 및 조작 금지)**해 달라는 요청이 있었습니다.
  2. 웨이퍼 원 테두리의 시인성을 강화하여 선명하게 잘 보이도록 조정해 달라는 요구가 추가되었습니다.
* **해결 방안**: 
  * 원 안에 완전히 들어오지 않는 칩(`.cell-outside-wafer`)에 `visibility: hidden` 및 `pointer-events: none` 스타일을 강제 부여하여 격자 구성을 해치지 않으면서도 화면에서 흔적 없이 숨기고 조작을 원천 금지했습니다.
  * 원판 테두리(`.map-grid-wrapper`)에 두껍고 명료한 솔리드 흰색 반투명 테두리(`3.5px solid`)와 그림자 글로우(`box-shadow`) 효과를 가미해 백색 광원 형태로 테두리를 뚜렷하게 도식화했습니다.

---

## 2. 주요 구현 사항

### A. 미포함 영역 클래스 주입 (`client2/src/map_editor.js`)
* 내접 분석 조건식(`completelyInside`)에 부합하지 않는 셀에 대해서는 `.cell-outside-wafer` 클래스를 동적으로 분기 적용했습니다.

```javascript
      const completelyInside = (dMax2 <= 1.0);

      if (completelyInside) {
        cell.classList.add('cell-inside-wafer');
      } else {
        cell.classList.add('cell-outside-wafer');
      }
```

### B. 미포함 영역 완전 은폐 및 테두리 광원 추가 CSS (`client2/src/style.css`)
```css
.map-grid-wrapper {
  /* ... 기존 속성 유지 */
  border: 3.5px solid rgba(255, 255, 255, 0.45); /* 선명한 솔리드 흰색 반투명 테두리 */
  box-shadow: inset 0 0 20px rgba(0, 0, 0, 0.6), 0 0 15px rgba(255, 255, 255, 0.15); /* 은은한 백색 광원 효과 */
}

/* 웨이퍼 원판 영역 밖의 셀 숨김 및 비활성화 */
.grid-cell.cell-outside-wafer {
  visibility: hidden !important;
  pointer-events: none !important;
}
```

---

## 3. 아키텍처 영향 보고
* **동적 맵 형태 시각화**: 원 바깥 영역의 사각형 픽셀들이 깔끔히 사라져 오직 원 형태의 실제 반도체 Wafer Die 맵 형태로 레이아웃이 렌더링되며, 클릭 미스로 엉뚱한 바깥 좌표가 적재되는 오작동을 근본 예방합니다.
* **정적 컴파일 완료**: Vite 빌드 최적화가 완벽하게 마감되었습니다.
