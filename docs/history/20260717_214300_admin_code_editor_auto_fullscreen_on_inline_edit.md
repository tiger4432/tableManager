# 2026-07-17 어드민 대시보드 인라인 편집 소환 시 즉각 전체화면 확장 자동화 적용

## 1. 개요 및 동기
* **현상**: 상세 진단(Diagnostics) 패널에서 인라인 편집 단추(`🛠️ Edit Parser` / `🛠️ Edit Mapper Code` / `🛠️ Edit Collector Script`)를 클릭했을 때, 우측의 좁은 공간 내에 모나코 에디터가 소환되어 코드를 정밀 편집하기가 여전히 답답한 문제가 발견되었습니다. (더욱이 브라우저 캐시 잔재 등으로 인해 전체화면 버튼이 간헐적으로 정상 등장하지 못하는 정합성 이슈가 병행되었습니다.)
* **개선책**: 사용자의 인라인 편집 의도를 적극 저격하여, 인라인 에디팅 진입 시 **별도의 전체화면 버튼 클릭 조작을 할 필요 없이 자동으로 100vw, 100vh 풀스크린 모드가 발동하도록 구조를 전면 고도화**했습니다.

---

## 2. 주요 연동 조치 사항

### A. 인라인 소환 시 자동 풀스크린 클래스 주입 (`client2/src/admin.js`)
* `openInlineEditor` 함수 내에 `editorContentWrapper.classList.add('fullscreen-mode')` 구문을 전진 주입하여 에디터 뷰 활성화 시점에 자동으로 레이아웃이 화면 가득 확장되도록 제어했습니다.
* 버튼들의 가시성 스타일(`display: inline-flex`)을 강제로 지정 매칭하여, 어떤 캐시 오염 상황에서도 저장(`Save Code`), 복귀(`Back to Details`), 수동 크기 조절(`Fullscreen`) 단추들이 100% 무결하게 시각 노출을 보장받도록 보강했습니다.

```javascript
// client2/src/admin.js
function openInlineEditor(path) {
  if (!isMonacoLoaded) {
    showToast('⚠️ Monaco Editor가 아직 로딩 중입니다.', 'warning');
    return;
  }
  
  diagnosticsContent.style.display = 'none';
  diagnosticsEmpty.style.display = 'none';
  
  // 에디터 활성화 및 인라인 편집 시 자동 전체화면(Auto Fullscreen) 강제 적용
  editorContentWrapper.style.display = 'flex';
  editorContentWrapper.classList.add('fullscreen-mode');
  
  // 제어 단추 가시성 강제 부여 보장
  if (editorBackBtn) {
    editorBackBtn.style.display = 'inline-flex';
  }
  if (editorFullscreenBtn) {
    editorFullscreenBtn.style.display = 'inline-flex';
    editorFullscreenBtn.textContent = '☀️ Exit Fullscreen';
  }
  if (saveCodeBtn) {
    saveCodeBtn.style.display = 'inline-flex';
  }
  
  // 파일 트리 강조 해제 및 코드 로드
  document.querySelectorAll('.tree-file-item').forEach(item => {
    item.classList.remove('active');
  });
  selectEditorFile(path);
  
  // 리사이즈 갱신
  if (window.monacoEditor) {
    setTimeout(() => {
      window.monacoEditor.layout();
    }, 100);
  }
}
```

### B. 복귀(Close) 시 자동 해제
* 쾌적한 코딩을 마친 유저가 `🔙 Back to Details` 버튼을 눌러 인라인 에디터를 이탈할 때, 자동으로 에디터 카드에 묻은 `fullscreen-mode` 스타일 클래스를 복구 해제해 줌으로써 다시 차분한 2분할 대시보드 레이아웃으로 완벽히 돌아오도록 닫기 헬퍼도 대칭 갱신했습니다.

---

## 3. 빌드 및 배포 적용
* **Vite 리빌드**: 수정 완료 후 `client2` 패키지 디렉토리에서 `npm run build` 번들링 빌드 처리를 완료하여 실서버 서비스 파일인 `dist/admin.html` 및 `dist/assets/admin-*.js` 파일에 신규 자동 전체화면 조치 사항을 안전하게 주입 배포했습니다.
