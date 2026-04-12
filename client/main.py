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

from PySide6.QtWidgets import QApplication, QMainWindow, QTableView, QTabWidget, QVBoxLayout, QWidget, QPushButton, QInputDialog, QMenu, QMessageBox, QFileDialog
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
        
        # 선택된 고유 컬럼 목록을 순서대로 추출
        cols_in_order = []
        seen_cols = set()
        for idx in indexes:
            if idx.column() not in seen_cols:
                cols_in_order.append(idx.column())
                seen_cols.add(idx.column())
        
        model = self.model()
        
        # 1행: 컬럼 헤더
        header_cells = []
        for col in cols_in_order:
            header = model.headerData(col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
            header_cells.append(str(header) if header is not None else "")
        text = "\t".join(header_cells) + "\n"
        
        # 2행~: 데이터
        prev_row = indexes[0].row()
        row_cells = []
        for i, idx in enumerate(indexes):
            if idx.row() != prev_row:
                text += "\t".join(row_cells) + "\n"
                row_cells = []
                prev_row = idx.row()
            value = model.data(idx, Qt.ItemDataRole.DisplayRole)
            row_cells.append(str(value) if value is not None else "")
        
        if row_cells:
            text += "\t".join(row_cells)
            
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
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(self.tabs)

        # ── + 탭 추가 버튼 (FilterToolBar 시그널 연결) ────────────────
        self._filter_bar.addTabRequested.connect(self._add_new_tab)
        # ── + 행 추가 버튼 (FilterToolBar 시그널 연결) ────────────────
        self._filter_bar.addRowRequested.connect(self._on_add_row_requested)
        # ── 📥 CSV 추출 버튼 (FilterToolBar 시그널 연결) ──────────────
        self._filter_bar.exportRequested.connect(self._on_export_requested)

        # ── WebSocket 공유 리스너 (Shared WebSocket) ──────────────────
        print('WEB SOCKET 초기화')
        self._ws_thread: WsListenerThread | None = None
        self._active_models: list[ApiLazyTableModel] = []

        # ── 서버로부터 모든 테이블 목록 조회 및 탭 초기화 ──────────────
        print('TABLE 초기화')
        self._load_all_tables()
        

    def _on_tab_changed(self, index):
        self._filter_bar.set_active_proxy(self._filter_bar._proxies[index])    

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

    def _on_export_requested(self):
        """현재 활성화된 테이블의 데이터를 CSV로 익스포트합니다."""
        idx = self.tabs.currentIndex()
        if idx < 0: return
        
        table_name = self.tabs.tabText(idx)
        
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
        url = f"http://127.0.0.1:8000/tables/{table_name}/export"
        
        try:
            with urllib.request.urlopen(url) as response:
                content = response.read()
                with open(file_path, "wb") as f:
                    f.write(content)
            QMessageBox.information(self, "추출 완료", f"데이터가 성공적으로 저장되었습니다:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "추출 실패", f"데이터 추출 중 오류 발생: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Modern style
    app.setStyle("Fusion")
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
