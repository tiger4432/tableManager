# 2026-07-17 09:50:00 - 어드민 대시보드 실시간 코드 에디팅 및 핫 리로드 전파 시스템 구축

## 1. 개요 및 배경
- **배경**: 이전에는 `mapper`, `file ingestion`, `auto_update` 스크립트들을 수정하기 위해서 로컬 디렉토리에서 수동으로 에디터를 켜서 수정해야 하는 번거로움이 있었습니다.
- **해결 내역**: 어드민 대시보드(`client2/admin.html`)에 웹 기반의 강력한 Monaco Editor를 주입하여, 파일 탐색기 트리를 통해 카테고리별 스크립트 소스를 조회 및 실시간 편집하고, 즉시 저장과 핫 리로드 라이프사이클 전파가 가능하도록 통합 개발을 완료했습니다.

---

## 2. 주요 변경 사항 및 기술적 상세

### A. 백엔드 코드 관리 API 추가 (`server/main.py`)
* `GET /admin/scripts/list`: `mappers/`, `ingestion_workspace/` 하위 파서 및 수집기 스크립트를 동적 스캔하여 카테고리별 트리로 반환합니다.
* `GET /admin/scripts/code`: 지정된 상대 경로의 소스 코드를 읽어옵니다. 경로 조작(`../`) 및 프리픽스 화이트리스트 검사(Surgical 보안 가드)를 수행하여 안전성을 담보합니다.
* `POST /admin/scripts/code`: 편집된 코드를 물리 디렉토리에 덮어쓰고, `DatabaseOutbox`에 `SYSTEM_RELOAD` 이벤트를 commit하여 타 데몬 프로세스들에 핫 리로드 신호를 즉각 브로드캐스트합니다.

### B. 어드민 HTML/JS 에디터 및 탐색기 UI 통합 (`client2`)
* **[admin.html](file:///c:/Users/kk980/Developments/assyManager/client2/admin.html)**: Monaco Editor CDN 로더 주입, 탭 리스트에 **[Code Editor]** 탭 추가, 왼쪽 패널 트리 영역 및 오른쪽 패널 에디터 마운트 영역 배치.
* **[admin.js](file:///c:/Users/kk980/Developments/assyManager/client2/src/admin.js)**: 모나코 에디터를 `vs-dark` 테마 및 Python 포커스로 로드하고, 파일 탐색기 트리 렌더링 및 파일 선택 시 코드를 가져와 에디터에 주입하며, 저장 클릭 시 API POST 처리를 완료했습니다.

---

## 3. 핵심 코드 스니펫 (Code Snippets)

### 백엔드 코드 읽기/쓰기 및 보안 가드 API (`server/main.py`)
```python
@app.get("/admin/scripts/code")
def get_admin_script_code(path: str):
    import os
    
    # Path Traversal & Whitelist check
    clean_path = os.path.normpath(path).replace("\\", "/")
    if clean_path.startswith("../") or "/../" in clean_path or clean_path.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid directory traversal detected")
        
    allowed = False
    for prefix in ["mappers/", "ingestion_workspace/"]:
        if clean_path.startswith(prefix):
            allowed = True
            break
            
    if not allowed:
        raise HTTPException(status_code=400, detail="Access denied to this path prefix")
        
    script_dir = os.path.dirname(os.path.abspath(__file__))
    full_path = os.path.abspath(os.path.join(script_dir, clean_path))
    
    if not full_path.startswith(script_dir):
        raise HTTPException(status_code=400, detail="Invalid path traversal outside project")
        
    if not os.path.exists(full_path) or not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail="File not found")
        
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            code = f.read()
        return {"status": "success", "path": clean_path, "code": code}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")
```

### 프론트엔드 Monaco Editor 데이터 바인딩 및 저장 핸들러 (`client2/src/admin.js`)
```javascript
// Select a file and load its contents into Monaco Editor
async function selectEditorFile(path) {
  activeEditorFilePath = path;
  
  // Highlight active item in tree
  document.querySelectorAll('.tree-file-item').forEach(item => {
    item.classList.toggle('active', item.dataset.path === path);
  });

  try {
    editorFilePath.textContent = '🔄 Loading file...';
    saveCodeBtn.style.display = 'none';

    const res = await fetch(`${API_BASE}/admin/scripts/code?path=${encodeURIComponent(path)}`);
    if (!res.ok) throw new Error('Failed to load file contents');
    const result = await res.json();

    if (window.monacoEditor) {
      window.monacoEditor.setValue(result.code || '');
      const model = window.monacoEditor.getModel();
      if (model) {
        monaco.editor.setModelLanguage(model, 'python');
      }
    }
    
    editorFilePath.textContent = `📝 ${path}`;
    saveCodeBtn.style.display = 'inline-flex';
  } catch (err) {
    console.error('Failed to load code for file', path, err);
    editorFilePath.textContent = '❌ Failed to load file';
    showToast('❌ 파일 코드를 불러오지 못했습니다.', 'error');
  }
}
```
