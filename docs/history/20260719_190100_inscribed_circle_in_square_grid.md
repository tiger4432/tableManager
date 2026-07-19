# 2026-07-19 19:01:00 - 격자 맵 에디터 내 사각형 크기와 동일한 내접 원형 테두리 매핑(Inscribed Wafer Circle inside Grid Square)

## 1. 개요 및 동기
* **요구사항**: 이전 구현(내접 사각형 70% 크기 제한) 대신, **전체 큰 사각형(격자 캔버스)의 한 변 길이가 웨이퍼 상징 원의 지름과 완전히 동일**하도록 조정해달라는 변경 요청이 있었습니다.
* **해결 방안**: 
  * 외곽 원형 래퍼(`.map-grid-wrapper`)에 적용되어 있던 패딩 여백(`padding: 30px`)을 `padding: 0`으로 완전 소거했습니다.
  * 내부 그리드 캔버스(`.map-grid-canvas`)의 크기를 래퍼 크기 기준 `100%`로 확장했습니다.
  * 결과적으로, 격자 캔버스의 가로/세로 한 변의 길이는 외곽 상징 원의 지름과 정확히 일치(`500px`)하게 되었으며, 상징 원은 사각형의 네 꼭짓점 바깥이 삐져나오고 네 변의 정중앙에 정확히 접하는 **내접 원(Inscribed Circle)** 형태로 시각화됩니다.

---

## 2. 주요 구현 사항

### A. CSS 패딩 제거 및 100% 스케일업 (`client2/src/style.css`)
```css
.map-grid-wrapper {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 500px;
  height: 500px;
  padding: 0; /* 패딩을 없애 캔버스 가로가 원의 지름과 동일해지도록 설정 */
  background: rgba(255, 255, 255, 0.01);
  border-radius: 50%;
  border: 2px dashed rgba(255, 255, 255, 0.1);
  box-shadow: inset 0 0 20px rgba(255, 255, 255, 0.02);
  transition: transform 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
  box-sizing: border-box;
}

.map-grid-canvas {
  display: grid;
  gap: 2px;
  background: var(--border-color);
  padding: 5px;
  border-radius: 6px;
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
* **표준 기하 표현 충족**: 반도체 다이(Die) 맵핑 도구에서 널리 쓰이는 표준적인 Wafer Mapping 표현 형식(둥근 웨이퍼 경계 원판과 외각으로 미세 돌출되는 격자 칩)을 시각적으로 가장 자연스럽고 크게 배치할 수 있게 되었습니다.
* **정적 컴파일 완료**: Vite를 통한 최적화 빌드가 이상 없이 완료되었습니다.
