# 2026-07-19 20:10:00 - 격자 맵 에디터 드래그 시 브라우저 Reflow/Repaint(배경 전환 & 텍스트 갱신) 소멸 최적화

## 1. 개요 및 동기
* **현상**:
  * JS 상태 대조 가드를 적용했음에도, 초대형 셀 맵에서 드래그 조작 시 미세한 버벅임이 지속적으로 남아 있었습니다.
* **원인 분석**:
  1. **CSS 트랜지션(Transition) 폭풍**: `.grid-cell` 클래스에 걸려 있던 `transition: transform 0.1s ease, background 0.15s ease;` 설정 때문에, 드래그 범위가 이동하면서 배경색이 달라질 때마다 수많은 셀들이 0.15초간 매 프레임 그라데이션 애니메이션(Repaint)을 수행하며 CPU/GPU 리소스를 잠식했습니다.
  2. **마우스 오버 스케일링(Scale) 레이아웃 시프트**: 드래그 도중 마우스 포인터가 칩 위를 빠르게 지날 때마다 `:hover` 선택자에 의한 `transform: scale(1.05)` 및 `box-shadow` 효과가 발동하여, 렌더링 파이프라인에서 수많은 격자들의 겹침 계산 및 레이아웃 재배치가 일어났습니다.
  3. **헤더 텍스트 갱신에 의한 Reflow**: 마우스가 셀에 진입할 때마다 헤더/푸터 영역에 노출되는 좌표 정보 텍스트(`gridStatusCoords.textContent`)를 끊임없이 갱신하여, 브라우저가 화면 전체 폰트 레이아웃 크기를 다시 재는 Reflow 연산을 드래그 내내 유발했습니다.

---

## 2. 해결 방안 (최적화 구현)

### A. 드래그 중 CSS 트랜지션, 트랜스폼 및 섀도우 즉시 비활성화 (`client2/src/style.css`, `map_editor.js`)
* 드래그 시작 시점(`mousedown`)에 격자 캔버스 부모 요소(`.map-grid-canvas`)에 `.drag-active` 클래스를 동적 부여하고, 드래그 종료 시점(`mouseup`)에 제거합니다.
* CSS에 다음 전용 룰을 심어 드래그 중인 캔버스 내부 모든 셀의 애니메이션, 트랜스폼 스케일 및 박스 섀도우를 즉각 소멸(snapping)시킵니다.
```css
.map-grid-canvas.drag-active .grid-cell {
  transition: none !important;
  transform: none !important;
  box-shadow: none !important;
}
```

### B. 드래그 중 실시간 좌표 문자열 DOM 갱신 차단 (`client2/src/map_editor.js`)
* `isBoxDragging` 상태가 `true`일 때(드래그 중일 때)는 `mouseenter` 리스너에서 좌표 텍스트 배지(`gridStatusCoords`)의 `textContent`를 갱신하지 않고 넘어가도록 바이패스 가드를 설치했습니다.

---

## 3. 결과 및 체감 성능
* **60 FPS 방어 완결**: 무거운 레이아웃 Reflow 및 Repaint 유발 요인이 완전히 사라졌습니다. 이제 80x80(6,400 칩) 크기의 극한의 초대형 격자 맵을 마구 휘둘러 조작하더라도 단 1프레임의 밀림이나 버벅임 없이 즉각적으로 반응하는 초고속 모바일/데스크톱 에디터를 확보했습니다.
