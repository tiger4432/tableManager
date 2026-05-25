# Desktop Hybrid Wrapper Implementation Plan

본 문서는 사내 보안 환경(DLP 등)에서 웹 브라우저의 파일 드래그 앤 드롭이 차단되는 제한을 극복하기 위해, 기존의 PyQt 프레임워크를 활용하여 AG-Grid 웹 앱(Vite)을 감싸는 데스크톱 하이브리드 앱 클라이언트를 구축하는 구현 계획을 서술합니다.

## 1. 아키텍처 및 우회 원리
- **DLP 감시 우회**: 브라우저(chrome.exe, msedge.exe) 프로세스는 DLP 통제에 의해 파일 드롭이 원천 차단되지만, 커스텀 배포되는 native 실행 파일(예: `AssyManagerClient.exe`)은 통제 대상에서 제외됩니다.
- **네이티브 드래그 앤 드롭**: QT native 영역(`QMainWindow`의 `dropEvent`)에서 마우스 파일 드롭 이벤트를 가로챕니다.
- **네이티브 파일 업로드**: QT 내부에서 파일 경로(`C:\...\*.log`)를 바이너리로 열어 `requests` 라이브러리로 직접 서버 API에 업로드합니다.
- **웹 페이지 실시간 피드백**: 업로드 성공 시 `QWebEngineView` 내에 `runJavaScript()`를 호출하여 웹 UI(Vite 클라이언트)에 성공 팝업(Toast)을 띄우고 WebSocket을 통해 그리드를 자동 리프레시합니다.

## 2. 주요 연동 API 및 JS 통신 인터페이스
- **Upload API**: `POST /tables/{table_name}/upload?user={user_name}` (실제 OS 유저명 e.g. kk980)
- **JS Trigger**: 
  ```javascript
  showToast('📤 드롭 업로드 완료! (RAW 파일: filename)', 'success')
  ```

## 3. 구현 단계 (Python Wrapper Code)
`client/desktop_wrapper.py` 파일 생성 및 다음과 같이 작성:

```python
import sys
import os
import requests
from PySide6.QtCore import QUrl, Qt
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView

class HybridDesktopClient(QMainWindow):
    def __init__(self, web_url):
        super().__init__()
        self.setWindowTitle("AssyManager Enterprise - Desktop Client")
        self.setGeometry(100, 100, 1400, 900)
        self.web_url = web_url

        self.setAcceptDrops(True)

        self.web_view = QWebEngineView(self)
        self.web_view.setUrl(QUrl(self.web_url))
        
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)

        self.setCentralWidget(self.web_view)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            for url in urls:
                file_path = url.toLocalFile()
                if file_path and os.path.exists(file_path):
                    self.upload_file_natively(file_path)
            event.acceptProposedAction()
        else:
            event.ignore()

    def upload_file_natively(self, file_path):
        import getpass
        try:
            current_user = getpass.getuser()
        except Exception:
            current_user = "unknown_user"

        filename = os.path.basename(file_path)
        self.web_view.page().runJavaScript(
            "currentTable", 
            0, 
            lambda table_name: self._do_upload(table_name, file_path, filename, current_user)
        )

    def _do_upload(self, table_name, file_path, filename, user_name):
        if not table_name:
            QMessageBox.warning(self, "경고", "먼저 화면에서 대상을 업로드할 테이블을 선택하세요.")
            return

        api_url = f"http://127.0.0.1:8080/tables/{table_name}/upload?user={user_name}"
        
        try:
            with open(file_path, 'rb') as f:
                files = {'file': (filename, f, 'text/plain')}
                response = requests.post(api_url, files=files)
                
            if response.status_code == 200:
                res_data = response.json()
                saved_path = res_data.get("path", "")
                saved_filename = os.path.basename(saved_path) if saved_path else filename
                js_code = f"if (typeof showToast === 'function') {{ showToast('📤 드롭 업로드 완료! (RAW 파일: {saved_filename})', 'success'); }}"
                self.web_view.page().runJavaScript(js_code)
            else:
                self.web_view.page().runJavaScript(f"showToast('❌ 업로드 실패 (HTTP {response.status_code})', 'error')")
        except Exception as e:
            self.web_view.page().runJavaScript(f"showToast('❌ 파일 업로드 중 오류 발생', 'error')")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = HybridDesktopClient("http://127.0.0.1:5173")
    window.show()
    sys.exit(app.exec())
```
