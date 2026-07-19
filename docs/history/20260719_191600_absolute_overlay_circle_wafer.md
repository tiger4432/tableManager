# 2026-07-19 19:16:00 - 격자 맵 에디터 원형 오버레이 절대 배치 기법(Overlay Wafer Circle)을 이용한 100% 매칭 내접 정렬 구현

## 1. 개요 및 동기
* **문제점**: 
  * 캔버스 사각형과 원의 지름 크기를 맞추려고 시도했으나, 래퍼의 보더 두께(3.5px) 및 그리드 캔버스의 안쪽 패딩(`padding: 5px`)으로 인해 사각형 격자 영역이 여전히 외각 원형 테두리 라인보다 미세하게 작게 맞물리는 시각적 격차가 미약하게 남아있었습니다.
* **해결 방안**:
  * 그리드 캔버스(`.map-grid-canvas`)의 패딩을 `0`으로 완전 제거하고 테두리 둥글기(`border-radius`)를 배제하여 셀들이 사각형 바운더리 외곽 끝점까지 빈틈없이 차지하게 만들었습니다.
  * 상징 원형 테두리는 `::after` 가상 요소를 생성하여 **그리드 캔버스 바로 윗단에 겹쳐지도록 절대 배치 오버레이(Absolute Overlay, z-index: 12)**로 구현했습니다.
  * 결과적으로 원형 라인은 격자 칩들의 윗면에 얹혀 테두리를 그리게 되며, 사각형 외각 끝점과 원의 지름 끝점의 너비와 높이가 소수점 1픽셀 오차도 없이 **100% 정확하게 맞닿아 일치**하게 되었습니다.
  * 오버레이 가상 요소에는 `pointer-events: none`을 정의해 하단 격자 셀 클릭 인터랙션을 완벽히 보호했습니다.

---

## 2. 주요 구현 사항

### A. CSS 가상 요소 및 마진/패딩 배제 개편 (`client2/src/style.css`)
```css
.map-grid-wrapper {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: min(780px, 82vh, 82vw);
  height: min(780px, 82vh, 82vw);
  padding: 0;
  background: rgba(255, 255, 255, 0.01);
  border-radius: 50%;
  transition: transform 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
  box-sizing: border-box;
}

/* 웨이퍼 원형 테두리 라인을 최상위에 오버레이로 얹어 셀들과 정확히 내접 정렬 */
.map-grid-wrapper::after {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  border-radius: 50%;
  border: 3.5px solid rgba(255, 255, 255, 0.45); /* 선명한 솔리드 흰색 반투명 테두리 */
  box-shadow: inset 0 0 20px rgba(0, 0, 0, 0.6), 0 0 15px rgba(255, 255, 255, 0.15); /* 은은한 백색 광원 효과 */
  pointer-events: none; /* 클릭 이벤트가 하단 셀로 전달되도록 방어 */
  z-index: 12;
}

.map-grid-canvas {
  display: grid;
  gap: 2px;
  background: var(--border-color);
  padding: 0; /* 패딩을 소거하여 셀들이 사각형 가장자리까지 꽉 차도록 설정 */
  border-radius: 0; /* 원형 오버레이에 맞추기 위해 외각 둥글기 제거 */
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
  user-select: none;
  transition: transform 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
  width: 100%;
  height: 100%;
  box-sizing: border-box;
}
```

---

## 3. 아키텍처 영향 보고
* **시각적 경계선 정밀 결합**: 사각형 격자 다이의 네 바운더리 모서리 엣지가 최상위 원형 데코레이션 선에 정확하게 중첩하여 맞물리므로, 테두리가 칩보다 크거나 작아 들뜨는 왜곡 현상이 종결되었습니다.
* **정적 컴파일 완료**: Vite를 통한 배포 빌드가 완료되었습니다.
