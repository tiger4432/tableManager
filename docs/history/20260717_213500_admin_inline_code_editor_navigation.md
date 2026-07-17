# 2026-07-17 어드민 대시보드 인라인 코드 에디팅 바로가기 내비게이션 구축

## 1. 개요 및 동기
* **현상 및 문제점**: 기존 어드민 대시보드에서는 코드를 편집하려면 무조건 별도의 `📝 Code Editor` 탭으로 이동하여 복잡한 디렉토리 트리 메뉴에서 파일 경로를 일일이 찾아들어가야 하는 UX적 비효율이 존재했습니다.
* **개선 방향**: 사용자가 모니터링 중인 특정 탭(Workspace, Chain Rule, Auto Update 등)의 상세 보기 Diagnostics 영역에서, 클릭 한 번으로 매핑된 실제 파이썬 소스코드 편집기(Monaco Editor)로 직행할 수 있는 **인라인 코드 에디팅 내비게이션(Inline Editor Navigation)** 브릿지를 설계하여 접근 편의성을 극대화했습니다.

---

## 2. 주요 구현 및 아키텍처

### A. 인라인 에디팅 및 복원 내비게이션 헬퍼 (`client2/src/admin.js`)
* **`openInlineEditor(path)`**: Diagnostics 패널을 숨기고 Monaco Editor 영역을 활성화한 뒤, 매핑된 소스 파일의 코드를 즉시 비동기 로딩합니다. 인라인 진입 시 우측 상단에 `🔙 Back to Details` 버튼을 동적으로 활성화합니다.
* **`closeInlineEditor()`**: Monaco Editor 영역을 닫고Diagnostics 패널을 복원한 후, 기존에 선택되어 있던 상세 항목을 기억하여 에러/메타데이터를 화면에 재활성화 복구합니다.

```javascript
// client2/src/admin.js
function openInlineEditor(path) {
  if (!isMonacoLoaded) {
    showToast('⚠️ Monaco Editor가 아직 로딩 중입니다.', 'warning');
    return;
  }
  diagnosticsContent.style.display = 'none';
  diagnosticsEmpty.style.display = 'none';
  editorContentWrapper.style.display = 'flex';
  if (editorBackBtn) {
    editorBackBtn.style.display = 'inline-flex';
  }
  document.querySelectorAll('.tree-file-item').forEach(item => {
    item.classList.remove('active');
  });
  selectEditorFile(path);
}

function closeInlineEditor() {
  editorContentWrapper.style.display = 'none';
  diagnosticsContent.style.display = 'flex';
  if (editorBackBtn) {
    editorBackBtn.style.display = 'none';
  }
  // 복원 로직...
}
```

### B. 각 탭별 스크립트 물리 경로 유추 및 주입 바인딩
* **Auto Update 탭**: 수집기 스크립트 파일 물리 경로(`ingestion_workspace/<table_name>/auto_update/<script_name>`)를 계산해 `🛠️ Edit Collector Script` 버튼 주입.
* **Chain Rule 탭**: `rule.mapper_module` 의 모듈명(`mappers.production_mapper`)을 읽어 맵퍼 소스 경로(`server/mappers/production_mapper.py`)로 유추한 뒤 `🛠️ Edit Mapper Code` 버튼 주입.
* **Workspace 탭**: 워크스페이스가 가지는 복수의 커스텀 파서 스크립트 목록을 읽어, 각 파서 리스트 아이템마다 `🛠️ Edit Parser` 버튼을 동적 생성 바인딩.

---

## 3. 빌드 및 배포 적용
* **Vite 번들링**: 수정 후 `client2` 패키지 디렉토리에서 `npm run build` 번들링 빌드 처리를 완료하여 실서버 서비스 파일인 `dist/admin.html` 및 `dist/assets/admin-*.js` 파일에 신규 UI/UX 개선 기능을 안전하게 주입 배포했습니다.
