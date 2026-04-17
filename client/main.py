import sys
import os

# ── Windows DLL 로드 워크어라운드 (환경 원천 격리) ──
if os.name == 'nt':
    is_frozen = getattr(sys, 'frozen', False)
    
    if is_frozen:
        # [빌드 환경] 시스템 PATH를 완전히 세척하여 외부(특히 base 콘다) DLL 혼입 원천 차단
        # 오직 번들 폴더와 Windows 기본 시스템 경로(System32)만 허용
        bundle_dir = sys._MEIPASS
        os.environ["PATH"] = bundle_dir + os.pathsep + os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32")
        
        # 번들 내부의 모든 가능성 있는 DLL 경로 등록
        pyside_internal_dirs = [
            bundle_dir,
            os.path.join(bundle_dir, "PySide6"),
            os.path.join(bundle_dir, "PySide6", "Qt", "bin"),
            os.path.join(bundle_dir, "shiboken6")
        ]
        for d in pyside_internal_dirs:
            if os.path.exists(d):
                os.add_dll_directory(d)
    else:
        # [개발 환경] Conda 경로 필터링 및 DLL 디렉토리 등록
        path_envs = os.environ.get("PATH", "").split(os.pathsep)
        cleaned_path = [p for p in path_envs if "conda" not in p.lower() and "anaconda" not in p.lower()]
        os.environ["PATH"] = os.pathsep.join(cleaned_path)
        
        pyside_dir = os.path.join(sys.prefix, "Lib", "site-packages", "PySide6")
        if os.path.exists(pyside_dir):
            os.add_dll_directory(pyside_dir)
            bin_dir = os.path.join(pyside_dir, "Qt", "bin")
            if os.path.exists(bin_dir):
                os.add_dll_directory(bin_dir)
# ──────────────────────────────────────────────────────────

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTableView, QStackedWidget, 
    QVBoxLayout, QHBoxLayout, QWidget, QPushButton, QInputDialog, 
    QMenu, QMessageBox, QFileDialog, QStatusBar, QLabel
)
from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtGui import QKeySequence, QGuiApplication, QIcon

import config
from models.table_model import ApiLazyTableModel, ApiSchemaWorker, ApiUploadWorker
from ui.panel_history import HistoryDockPanel
from ui.panel_filter import FilterToolBar
from ui.dialog_source_manage import CellSourceManageDialog
from ui.navigation_rail import NavigationRail
from ui.panel_dashboard import DashboardPanel
from ui.panel_settings import SettingsPanel

class ExcelTableView(QTableView):
    fileDropped = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setFixedWidth(50)
        self.verticalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            for url in urls:
                file_path = url.toLocalFile()
                if file_path:
                    self.fileDropped.emit(file_path)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)
    def contextMenuEvent(self, event):
        """우클릭 컨텍스트 메뉴 — 행 삭제 및 계보 조회 기능 제공."""
        menu = QMenu(self)
        lineage_action = menu.addAction("🔍 데이터 계보(Lineage) 조회")
        sources_action = menu.addAction("📚 데이터 원천(Sources) 관리")
        menu.addSeparator()
        delete_action = menu.addAction("🗑️ 선택된 행 삭제")
        
        selection = self.selectionModel()
        if not selection.hasSelection():
            lineage_action.setEnabled(False)
            sources_action.setEnabled(False)
            delete_action.setEnabled(False)

        action = menu.exec(event.globalPos())
        if action == delete_action:
            self.delete_selected_rows()
        elif action == lineage_action:
            self._request_lineage()
        elif action == sources_action:
            self._open_source_manager()
            
    def _open_source_manager(self):
        """현재 선택된 셀의 원천 데이터 관리 다이얼로그 개시."""
        index = self.currentIndex()
        if not index.isValid(): return
        
        # 모델에서 테이블 정보 추출
        model = self.model()
        source_model = getattr(model, 'sourceModel', lambda: model)()
        table_name = source_model.table_name
        
        # row_id 추출 (id 컬럼이 0번째라고 가정하거나 col_name으로 검색 가능)
        row = index.row()
        if row >= len(source_model._data): return
        row_id = source_model._data[row].get("row_id")
        
        # col_name 추출
        col_name = source_model._columns[index.column()]
        
        if not row_id: return
        
        dialog = CellSourceManageDialog(table_name, row_id, col_name, self.window())
        dialog.exec()

    def _request_lineage(self):
        """현재 선택된 셀의 계보를 부모(MainWindow 등)에게 요청."""
        index = self.currentIndex()
        if index.isValid():
            # MainWindow의 history_panel에 직접 비공식적으로 접근하거나 시그널 사용
            # 여기선 편의상 부모 윈도우 메서드 직접 호출 (구조에 따라 시그널 권장)
            main_win = self.window()
            if hasattr(main_win, "_history_panel"):
                main_win._history_panel._fetch_cell_lineage(self, index)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selection()
        elif event.matches(QKeySequence.StandardKey.Paste):
            self.paste_selection()
        elif event.key() == Qt.Key.Key_Delete:
            self.delete_selected_rows()
        else:
            super().keyPressEvent(event)

    def delete_selected_rows(self):
        """선택된 행들을 서버에서 삭제 요청. 정렬/필터링 및 가상 로딩 대응 완료."""
        selection = self.selectionModel()
        if not selection.hasSelection():
            return
            
        proxy_model = self.model()
        source_model = getattr(proxy_model, 'sourceModel', lambda: proxy_model)()
        table_name = source_model.table_name

        # 1. 선택된 인덱스들로부터 고유한 소스 행 인덱스 추출
        source_rows = set()
        uncached_selected = False
        for index in selection.selectedIndexes():
            # [필수] 프록시 인덱스를 소스 인덱스로 변환 (정렬/필터링 무관하게 정확한 데이터 타겟팅)
            src_index = proxy_model.mapToSource(index)
            src_row = src_index.row()
            
            # 가상 로딩(Placeholder) 행인지 체크
            if src_row < len(source_model._data):
                source_rows.add(src_row)
            else:
                uncached_selected = True

        if not source_rows:
            if uncached_selected:
                QMessageBox.warning(self, "삭제 불가", "아직 로드되지 않은 행(Loading...)은 삭제할 수 없습니다.\n데이터가 로드된 후 다시 시도하십시오.")
            return
            
        # 2. 삭제 확인 다이얼로그
        reply = QMessageBox.question(
            self, "행 삭제 확인",
            f"선택한 {len(source_rows)}개의 행을 삭제하시겠습니까?\n이 작업은 되돌릴 수 없습니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # 3. row_ids 추출
            row_ids = []
            for row in source_rows:
                rid = source_model._data[row].get("row_id")
                if rid: row_ids.append(rid)
            
            if not row_ids: return
            
            # 4. 비동기 워커를 통한 삭제 요청 (UI 프리징 방지)
            from models.table_model import ApiDeleteWorker
            url = config.get_batch_delete_url(table_name)
            worker = ApiDeleteWorker(url, row_ids, config.CURRENT_USER)
            
            def _on_error(err):
                QMessageBox.critical(self, "삭제 오류", f"행 일괄 삭제 중 오류 발생: {err}")
            
            worker.signals.error.connect(_on_error)
            QThreadPool.globalInstance().start(worker)
            # 결과는 WebSocket 브로드캐스트를 통해 모든 클라이언트에 자동 반영됨
    
    def copy_selection(self):
        """선택된 영역을 클립보드에 복사 (헤더 제외, 데이터만)."""
        selection = self.selectionModel()
        if not selection.hasSelection(): return
        indexes = selection.selectedIndexes()
        if not indexes: return
        
        # 행/열 순서대로 정렬
        indexes = sorted(indexes, key=lambda idx: (idx.row(), idx.column()))
        
        model = self.model()
        prev_row = indexes[0].row()
        row_cells = []
        lines = []
        
        for idx in indexes:
            if idx.row() != prev_row:
                lines.append("\t".join(row_cells))
                row_cells = []
                prev_row = idx.row()
            
            value = model.data(idx, Qt.ItemDataRole.DisplayRole)
            row_cells.append(str(value) if value is not None else "")
        
        if row_cells:
            lines.append("\t".join(row_cells))
            
        QGuiApplication.clipboard().setText("\n".join(lines))

    def setModel(self, model):
        super().setModel(model)
        # ── Agent E v4: 행 추가 시 최상단으로 자동 스크롤 ──
        if hasattr(model, "rowsInserted"):
            model.rowsInserted.connect(self._on_rows_inserted)

    def _on_rows_inserted(self, parent, first, last):
        if first == 0:
            self.scrollToTop()
            self.selectRow(0)

    def paste_selection(self):
        """클립보드 데이터를 현재 선택 영역에 붙여넣음 (정렬/필터링 및 유령 문자 대응)."""
        clipboard = QGuiApplication.clipboard().text()
        if not clipboard: return
        
        # 1. 클립보드 데이터 정형화 (strip을 통한 \r 제거)
        raw_rows = [r for r in clipboard.replace('\r\n', '\n').split('\n') if r]
        parsed_matrix = [[cell.strip() for cell in r.split('\t')] for r in raw_rows]
        if not parsed_matrix: return
        
        selection = self.selectionModel()
        indexes = selection.selectedIndexes()
        if not indexes: return
        
        # 2. 실제 왼쪽 상단 시작점(Anchor) 찾기
        min_row = min(idx.row() for idx in indexes)
        min_col = min(idx.column() for idx in indexes)
        
        # 3. Proxy-to-Source 맵핑을 통한 정밀 업데이트 리스트 생성
        proxy_model = self.model()
        source_model = getattr(proxy_model, 'sourceModel', lambda: proxy_model)()
        
        # {row_id: {col_name: value}} 형태로 데이터 재구성
        mapped_updates = {}
        
        for r_offset, row_values in enumerate(parsed_matrix):
            visual_row = min_row + r_offset
            if visual_row >= proxy_model.rowCount(): break
            
            # [핵심] 인덱스가 아닌 Row ID를 직접 호출 (절대 좌표 타겟팅)
            row_id = proxy_model.data(proxy_model.index(visual_row, 0), Qt.ItemDataRole.UserRole + 2)
            if not row_id: continue
            
            if row_id not in mapped_updates:
                mapped_updates[row_id] = {}
                
            for c_offset, value in enumerate(row_values):
                visual_col = min_col + c_offset
                if visual_col >= proxy_model.columnCount(): break
                
                # [개선] 컬럼명도 UserRole을 통해 내부 Key 매핑 정합성 확보
                col_name = proxy_model.headerData(visual_col, Qt.Orientation.Horizontal, Qt.ItemDataRole.UserRole)
                if not col_name: continue
                
                # 시스템 컬럼 제외
                if col_name in ["created_at", "updated_at", "row_id", "id", "updated_by"]:
                    continue
                    
                mapped_updates[row_id][col_name] = value

        # 4. 소스 모델에 식별자 기반 데이터 전달
        if hasattr(source_model, 'applyMappedUpdates'):
            source_model.applyMappedUpdates(mapped_updates)
        elif hasattr(source_model, 'bulkUpdateData'):
            # 하위 호환성을 위해 기존 함수 재호출 가능하나, 
            # 인덱스가 매핑된 상태이므로 table_model의 bulkUpdateData 로직 수정 필요
            source_model.bulkUpdateData(min_row, min_col, parsed_matrix, is_already_mapped=True)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AssyManager - Enterprise Edition")
        self.resize(1300, 850)
        
        # ── 프로그램 아이콘 설정 ──
        icon_path = os.path.join(os.path.dirname(__file__), "assets", "app_icon.png")
        print(f'[ICON] {icon_path}')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path.replace('\\', '/')))

        # ── 메인 컨테이너 및 레이아웃 ────────────────────────────────
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.main_h_layout = QHBoxLayout(central_widget)
        self.main_h_layout.setContentsMargins(0, 0, 0, 0)
        self.main_h_layout.setSpacing(0)

        # ── 1. 좌측 내비게이션 바 (Sidebar) ──────────────────────────
        self._nav_rail = NavigationRail(self)
        self._nav_rail.navigateRequested.connect(self._on_navigation_requested)
        self._nav_rail.closeRequested.connect(self._on_table_close_requested)
        self.main_h_layout.addWidget(self._nav_rail)

        # ── 2. 우측 콘텐츠 영역 ──────────────────────────────────────
        self.content_v_layout = QVBoxLayout()
        self.content_v_layout.setContentsMargins(0, 0, 0, 0)
        self.content_v_layout.setSpacing(0)
        self.main_h_layout.addLayout(self.content_v_layout)

        # ── 필터 툴바 (상단 고정) ──
        self._filter_bar = FilterToolBar(self)
        self.content_v_layout.addWidget(self._filter_bar)

        # ── 중앙 스택 위젯 (Dashboard + Tables) ──
        self.stacked = QStackedWidget()
        self.content_v_layout.addWidget(self.stacked)

        # ── 대시보드 추가 (Index 0) ──
        self._dashboard = DashboardPanel()
        self.stacked.addWidget(self._dashboard)

        # ── 설정 패널 추가 (Index 1) ──
        self._settings_page = SettingsPanel()
        self.stacked.addWidget(self._settings_page)

        # ── 히스토리 패널 (우측 도킹) ─────────────────────────────────
        self._history_panel = HistoryDockPanel(self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._history_panel)
        
        # ── 하당 상태바 ──
        self.setStatusBar(QStatusBar())
        self.statusBar().setStyleSheet("background-color: #11111b; color: #9399b2; border-top: 1px solid #313244;")
        self._ws_status_label = QLabel("  ● WebSocket: Disconnected  ")
        self._ws_status_label.setStyleSheet("color: #f38ba8;") # Red
        self.statusBar().addPermanentWidget(self._ws_status_label)

        # ── 시그널 연결 ─────────────────────────────────────────────
        self._filter_bar.addTabRequested.connect(self._add_new_tab)
        self._filter_bar.addRowRequested.connect(self._on_add_row_requested)
        self._filter_bar.exportRequested.connect(self._on_export_requested)
        self._filter_bar.uploadRequested.connect(self._on_upload_requested)
        self._filter_bar.sortLatestChanged.connect(self._on_sort_mode_changed) # [신규] 정렬 토글 연결
        self.addToolBar(self._filter_bar)
        self._filter_bar.searchRequested.connect(self._on_global_search)

        # ── 데이터 모델 매핑 (사이드바 메뉴 ID -> Widget Index) ──
        self._nav_to_index = {"home": 0, "settings": 1}
        self._index_to_table = {}

        # ── WebSocket 공유 리스너 (Shared WebSocket) ──────────────────
        print('WEB SOCKET 초기화')
        self._ws_thread: WsListenerThread | None = None
        self._active_models: list[ApiLazyTableModel] = []
        self._active_workers = set()

        # ── 서버로부터 모든 테이블 목록 조회 및 초기화 ──────────────
        print('TABLE 초기화')
        self._load_all_tables()

    def _on_navigation_requested(self, nav_id: str):
        """사이드바 클릭 시 해당 화면으로 전환."""
        if nav_id in self._nav_to_index:
            idx = self._nav_to_index[nav_id]
            self.stacked.setCurrentIndex(idx)
            
            # 필터 툴바 활성 프록시 갱신
            if idx > 1: # 0: Dashboard, 1: Settings
                proxy_idx = idx - 2
                if proxy_idx < len(self._filter_bar._proxies):
                    self._filter_bar.set_active_proxy(self._filter_bar._proxies[proxy_idx])
            
            # 윈도우 타이틀 및 툴바 표시 업데이트
            if nav_id == "home":
                self.setWindowTitle("AssyManager - Dashboard")
                self._filter_bar.hide()
            elif nav_id == "settings":
                self.setWindowTitle("AssyManager - Settings")
                self._filter_bar.hide()
            else:
                table_name = nav_id.replace("table:", "")
                self.setWindowTitle(f"AssyManager - {table_name}")
                self._filter_bar.show()

    def _on_table_close_requested(self, nav_id: str):
        """테이블 종료 요청 처리 — 리소스 해제 및 UI 제거."""
        if nav_id not in self._nav_to_index:
            return
            
        idx = self._nav_to_index.pop(nav_id)
        table_name = nav_id.replace("table:", "")
        
        # 1. Stacked Widget에서 제거
        widget = self.stacked.widget(idx)
        self.stacked.removeWidget(widget)
        widget.deleteLater()
        
        # 2. 모델 관리 리스트에서 제거
        model = getattr(widget, "_source_model", None)
        if model and model in self._active_models:
            self._active_models.remove(model)
            
        # 3. 사이드바 아이템 제거
        self._nav_rail.remove_nav_item(nav_id)
        
        # 4. 인덱스 매핑 갱신 (제거된 인덱스 보다 큰 인덱스들은 -1씩 당겨짐)
        new_nav_to_index = {"home": 0}
        new_index_to_table = {}
        for nid, old_idx in self._nav_to_index.items():
            if old_idx > idx:
                new_idx = old_idx - 1
            else:
                new_idx = old_idx
            new_nav_to_index[nid] = new_idx
            if nid.startswith("table:"):
                new_index_to_table[new_idx] = nid.replace("table:", "")
        
        self._nav_to_index = new_nav_to_index
        self._index_to_table = new_index_to_table
        
        # 5. 현재 화면이 닫혔다면 홈으로 이동
        if self.stacked.count() == 0 or idx == self.stacked.currentIndex():
            self._on_navigation_requested("home")
            self._nav_rail.set_active("home")

    def _load_all_tables(self):
        """서버에서 가용한 모든 테이블 목록을 가져와 각각 탭으로 생성합니다."""
        url = config.get_tables_list_url()
        # 초기화 시점이므로 간단히 ApiSchemaWorker (JSON 패치용) 재사용
        from models.table_model import ApiSchemaWorker
        worker = ApiSchemaWorker(url)
        
        def _on_tables_loaded(result):
            print(f"[Debug] Tables loaded from server: {result}")
            tables = result.get("tables", [])
            if not tables:
                print("[Debug] No tables found, initializing default")
                self._init_table_tab("inventory_master")
            else:
                from PySide6.QtCore import QTimer
                # Stagger tab initialization to prevent network burst and race conditions
                for i, table in enumerate(tables):
                    self._init_table_tab(table)
            
            # Agent D v6: Start Shared WS immediately to listen for updates as tabs load
            self._start_shared_ws()
            
            # 워커 참조 제거 (GC 허용)
            if worker in self._active_workers:
                self._active_workers.remove(worker)
        
        def _on_tables_error(err):
            print(f"[Debug] Tables loading error: {err}. Fallback to default tab.")
            self._init_table_tab("inventory_master")
            # Ensure WS starts even if tables listing fails
            self._start_shared_ws()
            
            # 워커 참조 제거
            if worker in self._active_workers:
                self._active_workers.remove(worker)

        worker.signals.finished.connect(_on_tables_loaded)
        worker.signals.error.connect(_on_tables_error)
        
        # Agent D v6: Ensure worker is not GC'd before finished
        if not hasattr(self, "_active_workers"):
            self._active_workers = set()
        self._active_workers.add(worker)
        
        QThreadPool.globalInstance().start(worker)

    def _start_shared_ws(self):
        """단일 공유 WebSocket 리스너를 시작합니다."""
        if self._ws_thread and self._ws_thread.isRunning():
            print('skip socket')
            return
            
        from models.table_model import WsListenerThread
        ws_url = config.WS_BASE_URL
        # ── WebSocket 공유 리스너 (Shared WebSocket) ──────────────────
        self._ws_thread = WsListenerThread(ws_url)
        self._ws_thread.message_received.connect(self._dispatch_ws_message)
        self._ws_thread.connection_error.connect(self._on_ws_error)
        self._ws_thread.start()
        
        # 상태바 갱신
        self._ws_status_label.setText("  ● WebSocket: Connected  ")
        self._ws_status_label.setStyleSheet("color: #a6e3a1;") # Green
        
        print(f"[MainWS] Shared Listener Thread started for {ws_url}")
        
        # 앱 종료 시 정리 연결
        QApplication.instance().aboutToQuit.connect(self._ws_thread.stop)

    def _on_ws_error(self, err):
        print(f"[MainWS] CRITICAL: {err}")
        self._ws_status_label.setText("  ● WebSocket: Error  ")
        self._ws_status_label.setStyleSheet("color: #f38ba8;") # Red

    def _dispatch_ws_message(self, data: dict):
        """수신된 WS 메시지를 모든 활성 모델에 전달합니다."""
        print(f"[MainWS] Dispatching message to {len(self._active_models)} active models: {data.get('event')}")
        for model in self._active_models:
            # table_model.py 의 _on_websocket_broadcast 호출
            model._on_websocket_broadcast(data)
        
    def _on_global_search(self, text: str):
        """
        필터 툴바의 검색어가 변경되었을 때 전체 활성 모델에 서버 사이드 검색을 요청합니다.
        """
        print(f"[MainWindow] Global search requested: '{text}'")
        for model in self._active_models:
            model.set_search_query(text)

    def _on_sort_mode_changed(self, enabled: bool):
        """
        필터 툴바에서 정렬 토글이 변경되었을 때 모든 활성 모델의 정렬 설정을 동기화합니다.
        """
        print(f"[MainWindow] Sort mode changed: LatestFirst={enabled}")
        for model in self._active_models:
            model.set_sort_latest(enabled)

    def _on_add_row_requested(self):
        """현재 활성화된 화면의 테이블에 새 행(들)을 일괄 추가 요청합니다."""
        curr_idx = self.stacked.currentIndex()
        if curr_idx <= 0: return # Dashboard
        
        # 1. 생성할 행 개수 입력 받기 (1~10000)
        count, ok = QInputDialog.getInt(
            self, "행 일괄 추가", "생성할 행의 개수를 입력하세요 (1~10,000):",
            value=1, minValue=1, maxValue=10000
        )
        if not ok: return

        table_name = self._index_to_table.get(curr_idx)
        if not table_name: return
        
        page_widget = self.stacked.widget(curr_idx)
        model = getattr(page_widget, "_source_model", None)
        if not model: return
            
        table_name = model.table_name
        # API 호출 (count 및 user_name 파라미터 포함)
        import urllib.parse
        params = urllib.parse.urlencode({
            "count": count,
            "user_name": config.CURRENT_USER
        })
        url = f"{config.get_row_create_url(table_name)}?{params}"
        
        import urllib.request
        try:
            req = urllib.request.Request(url, method="POST")
            with urllib.request.urlopen(req) as response:
                pass # WebSocket(batch_row_create)을 통해 UI에 반영됨
        except Exception as e:
            print(f"Failed to add rows: {e}")
            QMessageBox.critical(self, "추가 오류", f"행 일괄 추가 중 오류 발생: {e}")

        
    def _add_new_tab(self):
        """+ 버튼 클릭 시 실시간으로 서버의 테이블 목록을 가져와 드롭다운으로 제시합니다."""
        url = config.get_tables_list_url()
        from models.table_model import ApiSchemaWorker
        
        # 중복 요청 방지 (워커가 이미 돌아가고 있는지 확인 - 옵션)
        worker = ApiSchemaWorker(url)
        self._active_workers.add(worker)
        
        def _on_tables_fetched(result):
            # 워커 정리
            if worker in self._active_workers:
                self._active_workers.remove(worker)
                
            tables = result.get("tables", [])
            if not tables:
                QMessageBox.information(self, "정보", "서버에 사용 가능한 테이블이 없습니다.")
                return
                
            # 드롭다운 다이얼로그 (실시간 목록 기반 + 직접 입력 가능)
            name, ok = QInputDialog.getItem(
                self, "새 탭 추가", "연결할 테이블 선택 또는 입력:", 
                sorted(tables), 0, True # editable = True
            )
            if ok and name:
                # 이미 열려있는 테이블인지 확인 (사이드바 매핑 사용)
                nav_id = f"table:{name}"
                if nav_id in self._nav_to_index:
                    self._on_navigation_requested(nav_id)
                    self._nav_rail.set_active(nav_id)
                    return
                self._init_table_tab(name)
        
        def _on_error(err):
            if worker in self._active_workers:
                self._active_workers.remove(worker)
            QMessageBox.critical(self, "오류", f"테이블 목록 조회 실패: {err}")

        worker.signals.finished.connect(_on_tables_fetched)
        worker.signals.error.connect(_on_error)
        QThreadPool.globalInstance().start(worker)

    def _close_tab(self, index: int):
        """(사이드바 체제에서는 '닫기' 대신 '제거' 버튼이 필요할 때 사용 가능)"""
        # (구현 생략 - 필요 시 사이드바에서 특정 테이블 우클릭 메뉴 등으로 구현 가능)
        pass

    def _init_table_tab(self, table_name: str):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        table_view = ExcelTableView()
        table_view.setAlternatingRowColors(True)

        # Connect to REST API data model
        model = ApiLazyTableModel(table_name=table_name)
        tab._source_model = model
        # ── 활성 모델 리스트에 추가 (Shared WS Dispatch 용) ──
        self._active_models.append(model)

        # ── 필터 프록시 ──
        proxy = self._filter_bar.create_proxy(model)
        table_view.setModel(proxy)

        # ── 드래그 앤 드롭 업로드 연결 ──
        table_view.fileDropped.connect(
            lambda path: self._execute_file_upload(table_name, path)
        )

        # ── 히스토리 패널 연결 ──
        self._history_panel.connect_model(model, table_name, table_view)

        layout.addWidget(table_view)

        tab_idx = self.stacked.addWidget(tab)
        nav_id = f"table:{table_name}"
        
        # ── 스마트 아이콘 매핑 로직 (반도체/패키징 공정 도메인 강화) ──
        icon_map = {
            "chat": "💬",
            # 생산 및 물류
            "inventory": "📦", "stock": "📦", "wip": "🔄", "lot": "🏷️",
            "production": "🏭", "plan": "📅", "schedule": "⏰", "ship": "🚚",
            # 반도체 공정 (Wafer & Fab)
            "wafer": "📀", "fab": "🏫", "foundry": "💠", "clean": "🧤",
            # 패키징 및 조립 (Assy & Pkg)
            "assy": "🔧", "package": "🧩", "pkg": "📦", "bonding": "🔗", "substrate": "🔲", "bump": "🟢",
            # 테스트 및 품질 (Test & QA)
            "test": "🧪", "yield": "📈", "bin": "🗑️", "defect": "🔍", "inspection": "🧐", "ng": "❌", "qa": "🛡️",
            # 설비 및 센서
            "equipment": "⚙️", "tool": "🛠️", "mc": "🏗️", "sensor": "🌡️", "temp": "🌡️", "metric": "⚡",
            # 시스템류
            "log": "📜", "master": "👤", "user": "👥", "config": "⚙️"
        }
        
        icon_str = "📄" # 기본 아이콘
        for keyword, emoji in icon_map.items():
            if keyword in table_name.lower():
                icon_str = emoji
                break
                
        self._nav_rail.add_nav_item(nav_id, icon_str, table_name, is_table=True)
        
        # 매핑 저장 (기존 Dashboard(0), Settings(1) 이후에 위치)
        self._nav_to_index[nav_id] = tab_idx
        self._index_to_table[tab_idx] = table_name
        
        print(f"[Debug] Page {tab_idx} added for {table_name}")
        
        # 새 화면으로 즉시 이동
        self.stacked.setCurrentIndex(tab_idx)
        self._nav_rail.set_active(nav_id)
        self._filter_bar.show()

        # ── Agent D v4: 서버에서 스키마 로드 후 데이터 페칭 시작 (Sequential) ──
        self._load_table_schema(model)

    def _load_table_schema(self, model: ApiLazyTableModel):
        """특정 테이블 모델의 스키마를 비동기로 로드합니다."""
        table_name = model.table_name
        schema_url = config.get_table_schema_url(table_name)
        worker = ApiSchemaWorker(schema_url)
        
        def _on_schema_loaded(result):
            cols = result.get("columns", [])
            if cols:
                model.update_columns(cols)
                print(f"[Schema] Successfully updated columns for {table_name}: {cols}")
                # ── 스키마가 확보된 직후 첫 데이터 페칭 시작 (안정성 보장) ──
                if model.canFetchMore():
                    model.fetchMore()
            else:
                print(f"[Schema] No columns returned for {table_name}")
            
            # 워커 참조 제거 (GC 허용)
            if worker in self._active_workers:
                self._active_workers.remove(worker)
        
        def _on_schema_error(err):
            print(f"[Schema] Network error loading schema for {table_name}: {err}")
            # Agent D v6: Even if schema fails, try to fetch data with default columns
            if model.canFetchMore():
                model.fetchMore()
            if worker in self._active_workers:
                self._active_workers.remove(worker)

        worker.signals.finished.connect(_on_schema_loaded)
        worker.signals.error.connect(_on_schema_error)
        
        # 워커가 GC되지 않도록 멤버 변수에 보관
        if not hasattr(self, "_active_workers"):
            self._active_workers = set()
        self._active_workers.add(worker)
        
        QThreadPool.globalInstance().start(worker)

    def _on_export_requested(self):
        """현재 활성화된 테이블의 데이터를 CSV로 익스포트합니다."""
        idx = self.stacked.currentIndex()
        if idx <= 0: return
        
        table_name = self._index_to_table.get(idx)
        if not table_name: return
        
        # 파일 저장 다이얼로그 (Default: 테이블명_추출_시각.csv)
        from datetime import datetime
        default_name = f"{table_name}_extract_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "CSV 저장", default_name, "CSV Files (*.csv)"
        )
        
        if not file_path:
            return
            
        # 서버에서 CSV 다운로드
        import urllib.request
        url = config.get_table_export_url(table_name)
        
        try:
            with urllib.request.urlopen(url) as response:
                content = response.read()
                with open(file_path, "wb") as f:
                    f.write(content)
            QMessageBox.information(self, "추출 완료", f"데이터가 성공적으로 저장되었습니다:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "추출 실패", f"데이터 추출 중 오류 발생: {e}")


    def _on_upload_requested(self):
        """현재 화면의 테이블 인제션 워크스페이스로 파일 업로드를 수행합니다."""
        idx = self.stacked.currentIndex()
        if idx <= 0: return
        
        page = self.stacked.widget(idx)
        source_model = getattr(page, "_source_model", None)
        if not source_model:
            return
        
        # 1. 파일 선택 Dialog
        file_path, _ = QFileDialog.getOpenFileName(
            self, "업로드할 로그 파일 선택", "", "Log Files (*.log *.csv *.txt);;All Files (*)"
        )
        if file_path:
            self._execute_file_upload(source_model.table_name, file_path)

    def _execute_file_upload(self, table_name, file_path):
        """실제 파일 업로드를 수행합니다 (버튼/드롭 공통 로직)."""
        # 2. 업로드 워커 생성
        upload_url = config.get_table_upload_url(table_name)
        worker = ApiUploadWorker(upload_url, file_path)
        
        def _on_finished(result):
            QMessageBox.information(self, "성공", f"파일 업로드 완료: {result.get('filename')}\n서버에서 곧 파싱을 시작합니다.")
            
        def _on_error(err):
            QMessageBox.critical(self, "실패", f"파일 업로드 중 오류 발생:\n{err}")

        worker.signals.finished.connect(_on_finished)
        worker.signals.error.connect(_on_error)
        
        QThreadPool.globalInstance().start(worker)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Modern style
    app.setStyle("Fusion")
    
    # ── Windows 작업 표시줄 아이콘 활성화 (AppUserModelID 설정) ──
    if os.name == 'nt':
        import ctypes
        myappid = 'tiger.assymanager.enterprise.v2'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    
    # ── 프로그램 아이콘 설정 ──
    icon_path = os.path.join(os.path.dirname(__file__), "assets", "app_icon.png")
    print(f'[ICON] {icon_path}')
    app.setWindowIcon(QIcon(icon_path.replace('\\', '/')))


    window = MainWindow()
    window.show()
    sys.exit(app.exec())
