import sys
import os

# ── 프록시 간섭 차단 (보안 환경 루프백 통신 보장) ──
# Baseline only. It is set here, before httpx and Qt are imported, because both read
# proxy configuration eagerly. It assumes loopback - so when the resolved server host
# is NOT loopback this list no longer covers it, and __main__ extends it via
# extend_no_proxy(). Keep the loopback baseline regardless: it stays the common case.
os.environ["NO_PROXY"] = "127.0.0.1,localhost"

# ── 원격 개발자 도구 디버깅 포트 설정 (Chrome 브라우저에서 http://localhost:9222 접속 가능) ──
os.environ["QTWEBENGINE_REMOTE_DEBUGGING"] = "9222"

import httpx
import getpass
import json
from PySide6.QtCore import QUrl, Qt, QObject, QEvent
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QWidget, QFileDialog
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage, QWebEngineDownloadRequest
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtNetwork import QNetworkProxy
from PySide6.QtGui import QShortcut, QKeySequence

# ==============================================================================
#  Server address resolution - the single origin of "which server is this shell for"
# ==============================================================================
#  Precedence:  --server argument  >  ASSY_SERVER env var  >  client_settings.json
#               >  default 127.0.0.1:8080
#
#  Why that order (do not "simplify" it away):
#   - The argument is highest because attaching this shell to a different server once
#     must not require editing a file.
#   - The env var is next, for deployment scripts and desktop shortcuts.
#   - client_settings.json is next: it is the existing authority and the place a human
#     edits. But it is *tracked in git*, so an operator editing the repo copy dirties
#     the working tree - which is precisely why the argument and env var outrank it.
#   - The default is last, so an absent or empty settings file behaves exactly like the
#     hardcoded 127.0.0.1:8080 this replaced. Zero regression.
#
#  Deliberately NOT reused: run_decoupled_app.py's ASSY_API_HOST / ASSY_API_PORT are the
#  server's *bind* declaration, not a connect target - ASSY_API_HOST defaults to 0.0.0.0,
#  which is not an address a client can dial. ASSY_SERVER is the client-side name for the
#  same idea and stays separate for that reason.
#
#  A declaration that is present but invalid is REFUSED, never silently downgraded to the
#  default: an operator who mistypes a port must not end up quietly attached to a
#  different server with nothing telling them. (미상 != 0 - an unknown port is not 0.)
#  An *absent* declaration is normal configuration and takes the default silently.
# ==============================================================================

DEFAULT_SERVER_HOST = "127.0.0.1"
DEFAULT_SERVER_PORT = 8080
SETTINGS_FILENAME = "client_settings.json"


class ServerTargetError(Exception):
    """A present-but-invalid server declaration. Its text is the reason shown to the operator."""


def settings_file_path():
    """Absolute path of client_settings.json.

    Frozen build: AssyManagerClient.spec ships `datas=[]`, so the json is NOT bundled
    into the exe - the operator's copy sits next to the exe. Source run: next to this
    file. Returns the first existing candidate; if none exists, the primary candidate,
    so messages can still name a concrete path.
    """
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(os.path.join(os.path.dirname(os.path.abspath(sys.executable)), SETTINGS_FILENAME))
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), SETTINGS_FILENAME))
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return candidates[0]


def _coerce_port(value, origin):
    """Return `value` as a valid TCP port or raise ServerTargetError naming `origin`."""
    if isinstance(value, bool):
        # bool is an int subclass in Python - reject it before the int branch accepts True as 1.
        raise ServerTargetError(f"{origin} is a boolean ({value!r}); a port must be a number.")
    if isinstance(value, int):
        port = value
    else:
        text = str(value).strip()
        if not text.isdigit():
            raise ServerTargetError(f"{origin} is not a number: {value!r}.")
        port = int(text)
    if not 1 <= port <= 65535:
        # 미상 != 0: port 0 is "unknown", not a valid target, so it is refused like any
        # other bad value. Refusal texts stay ASCII on purpose - they are printed, and this
        # process's stdout is a cp949 pipe when run_decoupled_app.py supervises it, where a
        # non-ASCII print raises UnicodeEncodeError and replaces the refusal with a traceback.
        raise ServerTargetError(f"{origin} is out of range: {port} (allowed 1-65535; unknown is not 0).")
    return port


def _parse_host_port(raw, origin):
    """Parse 'host', 'host:port' or 'http://host:port' into (host, port_or_None)."""
    text = (raw or "").strip()
    if not text:
        raise ServerTargetError(f"{origin} is empty; give a host or host:port (e.g. 10.0.0.5:8080).")
    if "://" in text:
        scheme, _, remainder = text.partition("://")
        if scheme.lower() != "http":
            # Refuse rather than strip: silently downgrading https to http would attach the
            # operator to something other than what they declared.
            raise ServerTargetError(
                f"{origin}={raw!r} uses scheme {scheme!r}; this shell speaks http only.")
        text = remainder
    text = text.split("/", 1)[0].strip()  # tolerate a trailing path or slash
    if text.startswith("["):
        raise ServerTargetError(f"{origin}={raw!r}: IPv6 literals are not supported; use a hostname.")
    if ":" in text:
        host, _, port_text = text.rpartition(":")
        port = _coerce_port(port_text, f"{origin} port")
    else:
        host, port = text, None
    host = host.strip()
    if not host:
        raise ServerTargetError(f"{origin}={raw!r} has no host part.")
    return host, port


def _target_from_settings(path):
    """(host, port) as declared in client_settings.json; each may be None if not declared.

    Absent file -> (None, None) silently: not declaring a server is a normal
    configuration. A whitespace-only file is treated the same way (the user-stated rule
    is that a missing or empty file behaves exactly as before). A file that *does*
    declare something invalid raises ServerTargetError instead of falling through.
    """
    if not os.path.isfile(path):
        return None, None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        raise ServerTargetError(f"{path} could not be read: {exc}")
    if not text.strip():
        return None, None
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ServerTargetError(f"{path} is not valid JSON: {exc}")
    if not isinstance(data, dict):
        raise ServerTargetError(f"{path} must hold a JSON object, got {type(data).__name__}.")

    host = None
    if "server_host" in data:
        raw_host = data["server_host"]
        if not isinstance(raw_host, str) or not raw_host.strip():
            raise ServerTargetError(f"{path}: server_host is empty or not a string ({raw_host!r}).")
        host = raw_host.strip()

    port = None
    if "server_port" in data:
        port = _coerce_port(data["server_port"], f"{path}: server_port")

    return host, port


def _server_arg(argv):
    """Value of `--server VALUE` / `--server=VALUE`, or None.

    Hand-scanned rather than argparse'd on purpose: register_uri_scheme() installs an
    HKCU handler that launches this script with the clicked assymanager:// URL as
    argv[1], and argparse would exit(2) on that unknown positional. Hand-scanning leaves
    every other argument as harmless as it was before.
    """
    for index, item in enumerate(argv):
        if item == "--server":
            if index + 1 < len(argv) and not argv[index + 1].startswith("-"):
                return argv[index + 1]
            # `--server --print-target` must not resolve to the host "--print-target".
            raise ServerTargetError("--server was given without a value (e.g. --server 10.0.0.5:8080).")
        if item.startswith("--server="):
            return item.split("=", 1)[1]
    return None


def resolve_server_target(argv=None, env=None, settings_path=None):
    """Return (host, port, source) - the resolved server, and which level declared it.

    `source` is one of 'arg', 'env', 'client_settings.json', 'default'. It exists so the
    startup line can be checked against what the operator believes they configured; a
    resolved address alone cannot tell them their edit was ignored.
    Arguments are injectable so the precedence can be scored without a process launch.
    """
    argv = sys.argv[1:] if argv is None else list(argv)
    env = os.environ if env is None else env

    raw_arg = _server_arg(argv)
    if raw_arg is not None:
        host, port = _parse_host_port(raw_arg, "--server")
        return host, DEFAULT_SERVER_PORT if port is None else port, "arg"

    raw_env = env.get("ASSY_SERVER")
    if raw_env is not None and raw_env.strip():
        # An empty ASSY_SERVER counts as unset, not as a malformed declaration: `set
        # ASSY_SERVER=` is how Windows clears a variable, and scripts leave empties behind.
        host, port = _parse_host_port(raw_env, "ASSY_SERVER")
        return host, DEFAULT_SERVER_PORT if port is None else port, "env"

    path = settings_file_path() if settings_path is None else settings_path
    settings_host, settings_port = _target_from_settings(path)
    if settings_host is not None or settings_port is not None:
        return (DEFAULT_SERVER_HOST if settings_host is None else settings_host,
                DEFAULT_SERVER_PORT if settings_port is None else settings_port,
                SETTINGS_FILENAME)

    return DEFAULT_SERVER_HOST, DEFAULT_SERVER_PORT, "default"


def base_url(host, port):
    """The one place a server address becomes a URL string.

    Every consumer appends its own path to this: the shell page (`/?client=desktop`) and
    the native drag-and-drop upload (`/tables/{table}/upload`). Two call sites building
    the same string independently is how one identifier in this repo ended up with three
    implementations giving three answers.
    """
    return f"http://{host}:{port}"


def extend_no_proxy(host):
    """Add the resolved host to NO_PROXY so a proxy cannot swallow the connection.

    The module header pins NO_PROXY to loopback, which stops covering us the moment the
    resolved host is a LAN address - and a proxy eating the connection looks exactly like
    "the server is down". This covers the httpx upload path (httpx reads NO_PROXY per
    request). It does NOT reliably cover QtWebEngine on Windows, where Chromium takes
    proxy settings from the OS rather than from this variable; the Qt-side lever for that
    is QNetworkProxy.setApplicationProxy(NoProxy), kept commented out in __main__.
    """
    entries = [item.strip() for item in os.environ.get("NO_PROXY", "").split(",") if item.strip()]
    if host and host not in entries:
        entries.append(host)
        os.environ["NO_PROXY"] = ",".join(entries)
    return os.environ["NO_PROXY"]


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
    def __init__(self, server_base):
        super().__init__()
        self.setWindowTitle("AssyManager Enterprise - Desktop Client")
        self.setGeometry(100, 100, 1400, 900)
        # Both consumers hang off this one resolved base: the page below and the native
        # upload in _do_upload(). Do not re-derive the address in either of them.
        self.server_base = server_base
        self.web_url = f"{server_base}/?client=desktop"

        # 드래그 앤 드롭 활성화
        self.setAcceptDrops(True)

        self.web_view = QWebEngineView(self)
        self.web_view.setUrl(QUrl(self.web_url))
        
        # 권한 자동 승인 (클립보드 읽기 권한 등)
        self.web_view.page().permissionRequested.connect(lambda request: request.grant())
        
        # 다운로드 요청 처리 핸들러 연결
        self.web_view.page().profile().downloadRequested.connect(self.handle_download_request)
        
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

        # Same resolved base as the loaded page - see HybridDesktopClient.__init__.
        api_url = f"{self.server_base}/tables/{table_name}/upload"
        
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

    def handle_download_request(self, download):
        suggested_name = download.suggestedFileName()
        
        # OS 네이티브 파일 저장 다이얼로그 팝업
        filepath, _ = QFileDialog.getSaveFileName(
            self, 
            "Save CSV File", 
            suggested_name, 
            "CSV Files (*.csv);;All Files (*)"
        )
        
        if filepath:
            # 다운로드 경로 및 파일명 지정 후 승인
            download.setDownloadDirectory(os.path.dirname(filepath))
            download.setDownloadFileName(os.path.basename(filepath))
            download.accept()
        else:
            # 다이얼로그에서 취소 시 다운로드 취소 처리
            download.cancel()

    def toggle_devtools(self):
        if self.devtools_window and self.devtools_window.isVisible():
            self.devtools_window.hide()
            return
            
        if not self.devtools_window:
            devtools_page = QWebEnginePage(self.web_view.page().profile(), self)
            self.web_view.page().setDevToolsPage(devtools_page)
            self.devtools_window = DevToolsWindow(devtools_page, self)
            
        self.devtools_window.show()

def register_uri_scheme():
    import platform
    if platform.system() != "Windows":
        return
    try:
        import winreg
        import sys
        import os
        
        python_exe = sys.executable
        script_dir = os.path.dirname(os.path.abspath(__file__))
        wrapper_path = os.path.abspath(os.path.join(script_dir, "desktop_wrapper.py"))
        
        # 브라우저에서 assymanager:// 호출 시 실행할 커맨드 라인
        cmd_str = f'"{python_exe}" "{wrapper_path}" "%1"'
        
        # HKCU\\Software\\Classes\\assymanager 에 등록 (관리자 권한 불필요)
        key_path = r"Software\Classes\assymanager"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "URL:AssyManager Protocol")
            winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
            
        cmd_key_path = r"Software\Classes\assymanager\shell\open\command"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, cmd_key_path) as cmd_key:
            winreg.SetValueEx(cmd_key, "", 0, winreg.REG_SZ, cmd_str)
            
        print(f"[Desktop Wrapper] Registered custom protocol 'assymanager://' to HKCU: {cmd_str}")
    except Exception as e:
        print(f"[Desktop Wrapper] Failed to register custom protocol: {e}")

if __name__ == "__main__":
    # `--print-target` is a headless mode: resolve, report, exit. It exists so the
    # precedence chain can be verified without starting the GUI (and without touching
    # HKCU, since resolution runs before register_uri_scheme()).
    headless = "--print-target" in sys.argv[1:]

    # Resolve first, before the registry write and before any network stack is built, so
    # a refusal costs no side effects.
    try:
        server_host, server_port, server_source = resolve_server_target()
    except ServerTargetError as exc:
        print(f"[Desktop Wrapper] Refusing to start: {exc}", file=sys.stderr)
        if not headless:
            # console=False in AssyManagerClient.spec means stdout/stderr go nowhere in the
            # packaged exe. A refusal nobody can read is a silent failure, so the reason is
            # also shown in a dialog - the only channel the operator actually has.
            try:
                # Held in a named local, not an inline temporary: a temporary QApplication can
                # be collected mid-dialog (the GC hazard the protocol bans for signal lambdas).
                # It is deliberately not deleted - it stays alive until the process exits.
                error_app = QApplication(sys.argv)  # noqa: F841
                QMessageBox.critical(
                    None,
                    "AssyManager - 서버 주소 설정 오류",
                    f"서버 주소 설정이 잘못되어 실행을 중단했습니다.\n\n{exc}")
            except Exception as dialog_exc:
                print(f"[Desktop Wrapper] (dialog unavailable: {dialog_exc})", file=sys.stderr)
        sys.exit(2)

    resolved_base = base_url(server_host, server_port)
    extend_no_proxy(server_host)
    print(f"[Desktop Wrapper] Server target: {resolved_base} (source: {server_source})")

    if headless:
        # Second line only in the dry run: it makes the NO_PROXY wiring observable without
        # adding noise to the one-line startup log of a real launch.
        print(f"[Desktop Wrapper] NO_PROXY={os.environ.get('NO_PROXY', '')}")
        sys.exit(0)

    # URL Scheme 프로토콜 자동 등록
    register_uri_scheme()

    app = QApplication(sys.argv)

    # Qt 전역 프록시 해제. Kept as documentation, not as an accident: this is the Qt-side
    # lever that extend_no_proxy() cannot pull, because Chromium on Windows reads proxy
    # settings from the OS instead of NO_PROXY. Enable it only with the same deliberation.
    #QNetworkProxy.setApplicationProxy(QNetworkProxy(QNetworkProxy.NoProxy))

    window = HybridDesktopClient(resolved_base)
    window.show()
    sys.exit(app.exec())
