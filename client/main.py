import sys
import os

# Windows DLL load failed workaround for PySide6 in Conda environments
if os.name == 'nt':
    path_envs = os.environ.get("PATH", "").split(os.pathsep)
    # Remove Anaconda/conda paths that might contain conflicting Qt dlls
    cleaned_path = [p for p in path_envs if "conda" not in p.lower() and "anaconda" not in p.lower()]
    os.environ["PATH"] = os.pathsep.join(cleaned_path)
    
    # Also explicitly add PySide6 directory to DLL search path
    pyside_dir = os.path.join(sys.prefix, "Lib", "site-packages", "PySide6")
    if os.path.exists(pyside_dir):
        # os.add_dll_directory is highly effective for PySide6 load errors on Python 3.8+
        os.add_dll_directory(pyside_dir)

from PySide6.QtWidgets import QApplication, QMainWindow, QTableView, QTabWidget, QVBoxLayout, QWidget, QPushButton, QInputDialog, QMenu, QMessageBox
from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QKeySequence, QGuiApplication
from models.table_model import ApiLazyTableModel, ApiSchemaWorker
from ui.panel_history import HistoryDockPanel
from ui.panel_filter import FilterToolBar

class ExcelTableView(QTableView):
    def contextMenuEvent(self, event):
        """우클릭 컨텍스트 메뉴 — 행 삭제 및 계보 조회 기능 제공."""
        menu = QMenu(self)
        lineage_action = menu.addAction("🔍 데이터 계보(Lineage) 조회")
        menu.addSeparator()
        delete_action = menu.addAction("🗑️ 선택된 행 삭제")
        
        selection = self.selectionModel()
        if not selection.hasSelection():
            lineage_action.setEnabled(False)
            delete_action.setEnabled(False)

        action = menu.exec(event.globalPos())
        if action == delete_action:
            self.delete_selected_rows()
        elif action == lineage_action:
            self._request_lineage()
            
    def _request_lineage(self):
        """현재 선택된 셀의 계보를 부모(MainWindow 등)에게 요청."""
        index = self.currentIndex()
        if index.isValid():
            # MainWindow의 history_panel에 직접 비공식적으로 접근하거나 시그널 사용
            # 여기선 편의상 부모 윈도우 메서드 직접 호출 (구조에 따라 시그널 권장)
            main_win = self.window()
            if hasattr(main_win, "history_panel"):
                main_win.history_panel._fetch_cell_lineage(self, index)

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
        """선택된 행들을 서버에서 삭제 요청."""
        selection = self.selectionModel()
        if not selection.hasSelection():
            return
            
        rows = sorted(list(set(index.row() for index in selection.selectedIndexes())), reverse=True)
        if not rows:
            return
            
        reply = QMessageBox.question(
            self, "행 삭제 확인",
            f"선택한 {len(rows)}개의 행을 삭제하시겠습니까?\n이 작업은 되돌릴 수 없습니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            model = self.model()
            # proxy 모델인 경우 소스 모델 추출
            source_model = getattr(model, 'sourceModel', lambda: model)()
            table_name = source_model.table_name
            
            import urllib.request
            for row in rows:
                # row_id 추출 (id 컬럼 기준 - id 컬럼은 0번째라고 가정하거나 col_name으로 검색 가능)
                # 데이터 버퍼에서 직접 가져오는 것이 안전
                if row < len(source_model._data):
                    row_id = source_model._data[row].get("row_id")
                    if row_id:
                        url = f"{source_model.base_api_url}/tables/{table_name}/rows/{row_id}"
                        try:
                            req = urllib.request.Request(url, method="DELETE")
                            with urllib.request.urlopen(req) as response:
                                pass # WebSocket으로 삭제 이벤트 수신하여 로컬 반영 예정
                        except Exception as e:
                            print(f"Failed to delete row {row_id}: {e}")
                            QMessageBox.critical(self, "삭제 오류", f"행 삭제 중 오류 발생: {e}")
    
    def copy_selection(self):
        selection = self.selectionModel()
        if not selection.hasSelection(): return
        indexes = selection.selectedIndexes()
        if not indexes: return
        
        indexes = sorted(indexes, key=lambda idx: (idx.row(), idx.column()))
        
        text = ""
        prev_row = indexes[0].row()
        for i, idx in enumerate(indexes):
            if idx.row() != prev_row:
                text += "\n"
                prev_row = idx.row()
            elif i > 0:
                text += "\t"
            
            value = self.model().data(idx, Qt.ItemDataRole.DisplayRole)
            text += str(value) if value is not None else ""
            
        QGuiApplication.clipboard().setText(text)

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
        clipboard = QGuiApplication.clipboard().text()
        if not clipboard: return
        
        rows = [r.split('\t') for r in clipboard.split('\n') if r]
        if not rows: return
        
        selection = self.selectionModel()
        indexes = selection.selectedIndexes()
        if not indexes: return
        
        start_index = indexes[0]
        start_row = start_index.row()
        start_col = start_index.column()
        
        # proxy 모델인 경우 소스 모델로 bulkUpdateData 호출
        model = self.model()
        source_model = getattr(model, 'sourceModel', lambda: model)()
        if hasattr(source_model, 'bulkUpdateData'):
            source_model.bulkUpdateData(start_row, start_col, rows)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AssyManager - Data Editor")
        self.resize(1200, 750)

        # ── 필터 툴바 (상단) ──────────────────────────────────────────
        self._filter_bar = FilterToolBar(self)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._filter_bar)

        # ── 히스토리 패널 (우측 도킹) ─────────────────────────────────
        self._history_panel = HistoryDockPanel(self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._history_panel)

        # Central Tabs
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.setCentralWidget(self.tabs)

        # ── + 탭 추가 버튼 (FilterToolBar 시그널 연결) ────────────────
        self._filter_bar.addTabRequested.connect(self._add_new_tab)
        # ── + 행 추가 버튼 (FilterToolBar 시그널 연결) ────────────────
        self._filter_bar.addRowRequested.connect(self._on_add_row_requested)

        # ── WebSocket 공유 리스너 (Shared WebSocket) ──────────────────
        print('WEB SOCKET 초기화')
        self._ws_thread: WsListenerThread | None = None
        self._active_models: list[ApiLazyTableModel] = []

        # ── 서버로부터 모든 테이블 목록 조회 및 탭 초기화 ──────────────
        print('TABLE 초기화')
        self._load_all_tables()
        
    def _load_all_tables(self):
        """서버에서 가용한 모든 테이블 목록을 가져와 각각 탭으로 생성합니다."""
        url = "http://127.0.0.1:8000/tables"
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
        ws_url = "ws://127.0.0.1:8000/ws"
        self._ws_thread = WsListenerThread(ws_url)
        self._ws_thread.message_received.connect(self._dispatch_ws_message)
        self._ws_thread.connection_error.connect(lambda err: print(f"[MainWS] CRITICAL: {err}"))
        self._ws_thread.start()
        print(f"[MainWS] Shared Listener Thread started for {ws_url}")
        
        # 앱 종료 시 정리 연결
        QApplication.instance().aboutToQuit.connect(self._ws_thread.stop)

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

    def _on_add_row_requested(self):
        """현재 활성화된 탭의 테이블에 새 행을 추가 요청합니다."""
        current_index = self.tabs.currentIndex()
        if current_index == -1:
            return
            
        tab_widget = self.tabs.widget(current_index)
        model = getattr(tab_widget, "_source_model", None)
        if not model:
            return
            
        table_name = model.table_name
        url = f"{model.base_api_url}/tables/{table_name}/rows"
        
        import urllib.request
        try:
            req = urllib.request.Request(url, method="POST")
            with urllib.request.urlopen(req) as response:
                # server returns the new row, but we wait for WebSocket to sync it.
                pass
        except Exception as e:
            print(f"Failed to add row: {e}")
            QMessageBox.critical(self, "추가 오류", f"행 추가 중 오류 발생: {e}")

        
    def _add_new_tab(self):
        """+ 버튼 클릭 시 테이블 이름을 입력받아 새 탭을 생성합니다."""
        name, ok = QInputDialog.getText(self, "테이블 추가", "테이블 이름:")
        if ok and name.strip():
            self._init_table_tab(name.strip())

    def _close_tab(self, index: int):
        """탭 닫기 — 리스트에서 모델 제거 후 탭 제거."""
        tab_widget = self.tabs.widget(index)
        model = getattr(tab_widget, "_source_model", None)
        if model in self._active_models:
            self._active_models.remove(model)
        self.tabs.removeTab(index)

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

        # ── 히스토리 패널 연결 ──
        self._history_panel.connect_model(model, table_name, table_view)

        layout.addWidget(table_view)

        tab_idx = self.tabs.addTab(tab, table_name)
        print(f"[Debug] Tab {tab_idx} added for {table_name}")
        
        # Select first tab when it arrives if none selected
        if self.tabs.currentIndex() == -1:
            self.tabs.setCurrentIndex(0)

        # ── Agent D v4: 서버에서 스키마 로드 후 데이터 페칭 시작 (Sequential) ──
        self._load_table_schema(model)

    def _load_table_schema(self, model: ApiLazyTableModel):
        """특정 테이블 모델의 스키마를 비동기로 로드합니다."""
        table_name = model.table_name
        schema_url = f"{model.base_api_url}/tables/{table_name}/schema"
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



if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Modern style
    app.setStyle("Fusion")
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
