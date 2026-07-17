# 2026-07-17 어드민 대시보드 모나코 에디터 전체화면 토글 및 폰트 크기 개선

## 1. 개요 및 동기
* **개선 배경**: 어드민 상세 Diagnostics 패널에서 인라인으로 코드를 편집할 때, 폰트 글자 크기가 작아 가독성이 저하되고, 고정된 우측 패널 레이아웃 너비(Width) 때문에 복잡한 파이썬 로직을 정밀 코딩하기에 작업 영역이 좁아 답답한 사용성 이슈가 존재했습니다.
* **조치 내용**:
  1. 모나코 에디터 폰트 크기 상향 조정 (`fontSize: 13` -> `15`)
  2. 에디터 헤더 영역에 전체화면 토글 버튼(`🖥️ Fullscreen`)을 추가하고, 클릭 시 즉각 화면의 전 영역(100vw, 100vh)을 쾌적하게 덮는 풀스크린 레이아웃 토글 상태 엔진 구축.

---

## 2. 주요 구현 사항

### A. 에디터 전체화면 CSS 스타일 정의 (`client2/admin.html`)
전체화면 토글 시 에디터 카드 블록이 최상위 z-index 레이어로 화면을 채우도록 고농도 스타일을 설계했습니다.

```css
/* client2/admin.html */
#editor-content-wrapper.fullscreen-mode {
  position: fixed !important;
  top: 0 !important;
  left: 0 !important;
  width: 100vw !important;
  height: 100vh !important;
  z-index: 10000 !important;
  background: #0b0e14 !important;
  padding: 30px !important;
  gap: 0 !important;
}
```

### B. 전체화면 온오프 제어 및 에디터 layout 갱신 스크립트 (`client2/src/admin.js`)
* 전체화면 토글 시 버튼 텍스트를 `☀️ Exit Fullscreen` 으로 토글 표기합니다.
* 캔버스의 너비/높이가 뷰포트 전체로 변경됨에 따라, 모나코 에디터 레이아웃을 강제로 리사이징 레이아웃 갱신(`window.monacoEditor.layout()`)하여 코드 그리기 화면 깨짐 현상을 차단했습니다.
* 폰트 크기 매개변수를 15로 키워 시인성을 확보했습니다.

```javascript
// client2/src/admin.js
if (editorFullscreenBtn) {
  editorFullscreenBtn.addEventListener('click', () => {
    const isFullscreen = editorContentWrapper.classList.toggle('fullscreen-mode');
    editorFullscreenBtn.textContent = isFullscreen ? '☀️ Exit Fullscreen' : '🖥️ Fullscreen';
    if (window.monacoEditor) {
      setTimeout(() => {
        window.monacoEditor.layout();
      }, 80);
    }
  });
}

// Monaco Editor initialization
// ...
fontSize: 15,
// ...
```

---

## 3. 빌드 및 배포 적용
* **Vite 번들링**: 수정을 끝마치고 `client2` 디렉토리에서 `npm run build` 컴파일을 성공적으로 끝내 빌드 아티팩트 `dist/assets/admin-*.js` 파일에 신규 전체화면 및 폰트 개선 사항을 완벽히 주입 배포했습니다.
