# 2026-07-17 어드민 대시보드 우측 에디터 컨테이너 부모 엘리먼트 맞춤(Fit) 개선

## 1. 개요 및 동기
* **현상**: 우측 상세 영역에 코드 에디터가 소환될 때, 에디터의 최소 높이(`min-height: 450px`) 및 부모의 상속 체인 불통으로 인해 모나코 에디터 창의 실제 크기가 우측 패널 카드 영역보다 더 거대하게 잡혀 삐져나가거나 레이아웃 밖으로 가려지는 결함이 있었습니다.
* **조치 내용**: 
  1. 우측 패널 본문 컨테이너(`.panel-body`)를 Flex 세로 방향 레이아웃으로 변경하고, 내부 자식들의 높이(`height: 100%`) 상속이 올바르게 동작하도록 제어했습니다.
  2. 모나코 에디터의 가두기 부모 박스(`.detail-block-body`)에 `flex: 1` 높이 배정을 강제하고, 에디터 컨테이너 내부의 `min-height: 450px` 하드코딩 속성을 완전히 걷어내어 부모 크기 변화에 유연하게 반응형으로 딱 맞추어(fit) 렌더링되도록 개선했습니다.

---

## 2. 주요 레이아웃 변경 사항 (`client2/admin.html`)

### A. 우측 패널 바디 및 자식 구조 개선
```html
<!-- [수정 전] -->
<div class="panel-body">
  <div id="diagnostics-content" class="detail-section" style="display: none;">
  ...
  <div id="editor-content-wrapper" class="detail-section" style="display: none; height: 100%;">
    <div class="detail-block" style="flex: 1; max-height: none;">

<!-- [수정 후] -->
<div class="panel-body" style="display: flex; flex-direction: column; height: calc(100% - 60px); overflow: hidden; padding: 15px;">
  <div id="diagnostics-content" class="detail-section" style="display: none; height: 100%; flex: 1; flex-direction: column; overflow: auto;">
  ...
  <div id="editor-content-wrapper" class="detail-section" style="display: none; height: 100%; flex: 1; flex-direction: column; overflow: hidden;">
    <div class="detail-block" style="flex: 1; max-height: none; display: flex; flex-direction: column; height: 100%;">
```

### B. 에디터 캔버스 컨테이너 핏화
```html
<!-- [수정 전] -->
<div class="detail-block-body" style="padding: 0; overflow: hidden; position: relative; height: 100%;">
  <div id="monaco-editor-container" style="width: 100%; height: 100%; min-height: 450px;"></div>
</div>

<!-- [수정 후] -->
<div class="detail-block-body" style="padding: 0; overflow: hidden; position: relative; height: 100%; flex: 1;">
  <div id="monaco-editor-container" style="width: 100%; height: 100%;"></div>
</div>
```

---

## 3. 빌드 및 배포 적용
* **Vite 리빌드**: 개선 사항을 마크업에 정상 반영한 뒤 `client2` 디렉토리에서 `npm run build` 번들링 절차를 완수하여 정적 리소스 에셋 컴파일 배포를 마쳤습니다.
