import sys
import os

# ── 프록시 간섭 차단 (보안 환경 루프백 통신 보장) ──
os.environ["NO_PROXY"] = "127.0.0.1,localhost"

# ── 원격 개발자 도구 디버깅 포트 설정 (Chrome 브라우저에서 http://localhost:9222 접속 가능) ──
os.environ["QTWEBENGINE_REMOTE_DEBUGGING"] = "9222"

import httpx
import getpass
from PySide6.QtCore import QUrl, Qt, QObject, QEvent
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QWidget
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtNetwork import QNetworkProxy
from PySide6.QtGui import QShortcut, QKeySequence

# ── 드래그 앤 드롭 이벤트를 가로채기 위한 Qt 이벤트 필터 ──
class DropEventFilter(QObject):
    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self.callback = callback
        
    def eventFilter(self, watched, event):
        if event.type() == QEvent.DragEnter:
            if event.mimeData().hasUrls():
                event.acceptProposedAction()
                return True
        elif event.type() == QEvent.DragMove:
            if event.mimeData().hasUrls():
                event.acceptProposedAction()
                return True
        elif event.type() == QEvent.Drop:
            if event.mimeData().hasUrls():
                urls = event.mimeData().urls()
                for url in urls:
                    file_path = url.toLocalFile()
                    if file_path:
                        self.callback(file_path)
                event.acceptProposedAction()
                return True
        return super().eventFilter(watched, event)

class DevToolsWindow(QMainWindow):
    def __init__(self, devtools_page, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Developer Tools (Chrome Inspector)")
        self.setGeometry(150, 150, 1000, 700)
        self.web_view = QWebEngineView(self)
        self.web_view.setPage(devtools_page)
        self.setCentralWidget(self.web_view)

class HybridDesktopClient(QMainWindow):
    def __init__(self, web_url):
        super().__init__()
        self.setWindowTitle("AssyManager Enterprise - Desktop Client")
        self.setGeometry(100, 100, 1400, 900)
        self.web_url = web_url

        # 드래그 앤 드롭 활성화
        self.setAcceptDrops(True)

        self.web_view = QWebEngineView(self)
        self.web_view.setUrl(QUrl(self.web_url))
        
        # 권한 자동 승인 (클립보드 읽기 권한 등)
        self.web_view.page().permissionRequested.connect(lambda request: request.grant())
        
        # 보안 설정 및 로컬 파일 접근 허용 등
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)

        self.setCentralWidget(self.web_view)

        # F12 개발자 도구 단축키 등록
        self.shortcut_f12 = QShortcut(QKeySequence("F12"), self)
        self.shortcut_f12.activated.connect(self.toggle_devtools)
        self.devtools_window = None

        # F5 / Ctrl+R 새로고침 단축키 등록
        self.shortcut_f5 = QShortcut(QKeySequence("F5"), self)
        self.shortcut_f5.activated.connect(self.web_view.reload)
        self.shortcut_ctrl_r = QShortcut(QKeySequence("Ctrl+R"), self)
        self.shortcut_ctrl_r.activated.connect(self.web_view.reload)

        # ── 드래그 앤 드롭 가로채기 필터 주입 ──
        self.drop_filter = DropEventFilter(self.upload_file_natively, self)
        self.web_view.installEventFilter(self.drop_filter)
        
        # 렌더 위젯이 생성되는 시점에 맞춰 동적으로 자식 위젯들에 필터 설치
        self.web_view.loadFinished.connect(lambda _: self.install_filter_to_children(self.web_view))
        self.install_filter_to_children(self.web_view)

    def install_filter_to_children(self, widget):
        widget.setAcceptDrops(True)
        widget.installEventFilter(self.drop_filter)
        for child in widget.findChildren(QWidget):
            child.setAcceptDrops(True)
            child.installEventFilter(self.drop_filter)

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
        try:
            current_user = getpass.getuser()
        except Exception:
            current_user = "unknown_user"

        filename = os.path.basename(file_path)
        print(f"[Desktop Wrapper] OS Drag & Drop detected: {file_path} for user: {current_user}")
        self.web_view.page().runJavaScript(
            "window.currentTable", 
            0, 
            lambda table_name: self._do_upload(table_name, file_path, filename, current_user)
        )

    def _do_upload(self, table_name, file_path, filename, user_name):
        if not table_name:
            QMessageBox.warning(self, "경고", "먼저 화면에서 대상을 업로드할 테이블을 선택하세요.")
            return

        # FastAPI 백엔드 포트 8080 사용
        api_url = f"http://127.0.0.1:8080/tables/{table_name}/upload"
        
        try:
            with open(file_path, 'rb') as f:
                files = {'file': (filename, f, 'text/plain')}
                params = {'user': user_name}
                response = httpx.post(api_url, files=files, params=params, timeout=30.0)
                
            if response.status_code == 200:
                res_data = response.json()
                saved_path = res_data.get("path", "")
                saved_filename = os.path.basename(saved_path) if saved_path else filename
                print(f"[Desktop Wrapper] Upload successful. RAW file: {saved_filename}")
                
                # 웹앱 화면에 성공 토스트 알림창 호출
                js_code = f"if (typeof showToast === 'function') {{ showToast('📤 드롭 업로드 완료! (RAW 파일: {saved_filename})', 'success'); }}"
                self.web_view.page().runJavaScript(js_code)
            else:
                print(f"[Desktop Wrapper] Upload failed with status code: {response.status_code}")
                self.web_view.page().runJavaScript(f"if (typeof showToast === 'function') {{ showToast('❌ 업로드 실패 (HTTP {response.status_code})', 'error'); }}")
        except Exception as e:
            print(f"[Desktop Wrapper] Exception during upload: {e}")
            self.web_view.page().runJavaScript(f"if (typeof showToast === 'function') {{ showToast('❌ 파일 업로드 중 오류 발생', 'error'); }}")

    def toggle_devtools(self):
        if self.devtools_window and self.devtools_window.isVisible():
            self.devtools_window.hide()
            return
            
        if not self.devtools_window:
            devtools_page = QWebEnginePage(self.web_view.page().profile(), self)
            self.web_view.page().setDevToolsPage(devtools_page)
            self.devtools_window = DevToolsWindow(devtools_page, self)
            
        self.devtools_window.show()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Qt 전역 프록시 해제 (루프백 통신 강제)
    #QNetworkProxy.setApplicationProxy(QNetworkProxy(QNetworkProxy.NoProxy))
    
    # Vite 개발 서버가 작동 중인지 감지 (5173 포트가 열려있으면 Dev 모드로 간주)
    import socket
    def is_port_open(host, port):
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            return False
            
    if is_port_open("127.0.0.1", 5173):
        url = "http://localhost:5173/"
        print("[Desktop Wrapper] Vite dev server detected on port 5173. Loading development URL.")
    else:
        url = "http://localhost:8080/"
        print("[Desktop Wrapper] Vite dev server not detected. Loading integrated FastAPI URL on port 8080.")
        
    window = HybridDesktopClient(url)
    window.show()
    sys.exit(app.exec())
