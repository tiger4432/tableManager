# 2026-07-19 메인 UI 데이터 그리드와 히스토리 사이드바 간 스플릿 리사이저 드래그 조절 기능 구현

## 1. 개요 및 동기
* **개선 배경**: 메인 화면의 데이터 그리드 영역(`myGrid`)과 우측 상세 패널(`aside.history-sidebar`) 사이의 가로 비율을 마우스로 자유롭게 조절할 수 있도록 스플릿 리사이저(Resizer Drag Bar)를 탑재하여 대시보드 커스터마이징 및 사용성 편의를 개선했습니다.

---

## 2. 주요 구현 및 마크업 변경 사항

### A. 메인 마크업 개정 (`client2/index.html`)
* 데이터 그리드가 포함된 `section.grid-section` 과 우측 상세 이력 영역인 `aside.history-sidebar` 경계선 사이에 아래의 리사이저 드래그 바 마크업을 신규 탑재했습니다:
  ```html
  <!-- Main Layout Split Resizer -->
  <div id="main-split-resizer" class="split-resizer"></div>
  ```

### B. 스타일시트 고도화 (`client2/src/style.css`)
* `.grid-section` 우상단 및 우하단에 씌워져 있던 기본 우측 border를 제거하여 리사이저 바 경계선과의 2중 테두리 중첩 현상을 방지했습니다.
* 마우스 오버 및 드래그 동작 시 사이언 네온 컬러 하이라이팅 효과를 제공하는 `.split-resizer` 스타일 클래스 및 드래그 가로채기 방지용 `resizing-active` 관련 스타일 규칙을 적용했습니다.

### C. 자바스크립트 드래그 로직 및 리액터 바인딩 (`client2/src/main.js`)
* `setupEventListeners` 함수 최하단에 메인 레이아웃 리사이징 마우스 드래그 이벤트 리스너를 구현했습니다.
* 마우스 위치 좌표에 대응하여 우측 패널의 너비(최소 300px ~ 최대 컨테이너 너비 - 350px 내)를 실시간 반영 조절하도록 계산식을 제어했습니다.
* 드래그 조절 시 AG-Grid 가로 크기가 찌그러지거나 잘리지 않도록 `state.gridApi.sizeColumnsToFit()` API 호출을 매끄럽게 동기화하여 반응형 리사이징을 구현했습니다.

---

## 3. 빌드 및 배포
* `client2` 디렉토리 하위에서 `npm run build` 번들링 작업을 무사히 완수하여 정적 에셋 컴파일 배포 처리를 마무리했습니다.
