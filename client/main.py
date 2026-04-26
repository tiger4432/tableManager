import sys
import os
from datetime import datetime

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
from PySide6.QtCore import Qt, QThreadPool, Signal, QTimer
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
        self._active_workers = set() # [GC 방지] 비동기 워커 생존 보장용 참조 저장소

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
        
        # row_id 추출 (Index Drift 방지를 위해 Proxy -> Source 매핑)
        src_index = model.mapToSource(index)
        src_row = src_index.row()
        src_col = src_index.column()
        
        if src_row >= len(source_model._data): return
        row_id = source_model._data[src_row].get("row_id")
        
        # col_name 추출
        col_name = source_model._columns[src_col]
        
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
        loaded_source_rows = set()
        uncached_offsets = set()
        for index in selection.selectedIndexes():
            # [필수] 프록시 인덱스를 소스 인덱스로 변환 (정렬/필터링 무관하게 정확한 데이터 타겟팅)
            src_index = proxy_model.mapToSource(index)
            src_row = src_index.row()
            
            # 가상 로딩(None 패딩 포함) 행인지 체크
            if src_row < len(source_model._data) and source_model._data[src_row] is not None:
                loaded_source_rows.add(src_row)
            else:
                uncached_offsets.add(src_row)

        total_nodes = len(loaded_source_rows) + len(uncached_offsets)
        if total_nodes == 0:
            return
            
        # 2. 삭제 확인 다이얼로그 (언캐시드 포함일 경우 스캐너 동작 안내 추가)
        msg_text = f"선택한 {total_nodes}개의 행을 삭제하시겠습니까?\n이 작업은 되돌릴 수 없습니다."
        if uncached_offsets:
            msg_text += f"\n\n(아직 로드되지 않은 {len(uncached_offsets)}개의 행은 백그라운드 식별자 스캔 후 삭제됩니다.)"
            
        reply = QMessageBox.question(
            self, "행 삭제 확인",
            msg_text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
            
        # 3. 이미 로컬에 로드되어 있는 행들의 row_ids 추출
        loaded_row_ids = []
        for row in loaded_source_rows:
            row_data = source_model._data[row]
            if row_data is not None:
                rid = row_data.get("row_id")
                if rid: loaded_row_ids.append(rid)
        
        # 4. 삭제 워커 실행기 (내부 함수 형태로 스캔 완료시 콜백 연계 가능하도록 구조화)
        def _execute_deletion(final_row_ids):
            if not final_row_ids: 
                print("[Delete] No row IDs to delete. Aborting.")
                return
            
            if hasattr(self.window(), 'statusBar'):
                self.window().statusBar().showMessage(f"서버에 {len(final_row_ids)}개의 행 삭제를 요청 중입니다...", 5000)
            
            from models.table_model import ApiDeleteWorker
            url = config.get_batch_delete_url(table_name)
            worker = ApiDeleteWorker(url, final_row_ids, config.CURRENT_USER)
            
            def _on_finished(res):
                main_win = self.window()
                if hasattr(main_win, 'statusBar'):
                    main_win.statusBar().showMessage(f"삭제 완료: {res.get('deleted_count', 0)}개 행이 제거됨", 3000)
                print(f"[Delete] Successfully deleted: {res}")
                
                # [Fix] 삭제 성공 시 히스토리 패널 즉시 갱신
                if hasattr(main_win, "_history_panel"):
                    main_win._history_panel.refresh_history()
            
            def _on_error(err):
                main_win = self.window()
                if hasattr(main_win, 'statusBar'):
                    main_win.statusBar().showMessage("행 삭제 실패", 3000)
                print(f"[Delete] Error: {err}")
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.critical(self.window(), "삭제 오류", f"행 일괄 삭제 중 오류 발생: {err}")
            
            worker.signals.finished.connect(_on_finished)
            worker.signals.error.connect(_on_error)
            
            # GC 방지 및 실행
            self._active_workers.add(worker)
            def _cleanup():
                if worker in self._active_workers: self._active_workers.remove(worker)
            worker.signals.finished.connect(_cleanup)
            worker.signals.error.connect(_cleanup)
            
            print(f"[Delete] Starting ApiDeleteWorker for {len(final_row_ids)} IDs")
            QThreadPool.globalInstance().start(worker)
            
        # 5. Targeted RowID Scanner 구동 (언캐시드 항목이 있을 경우)
        if uncached_offsets:
            from models.table_model import ApiTargetedRowIdWorker
            scan_url = config.get_target_row_ids_url(table_name)
            
            search_query = getattr(source_model, '_search_query', "")
            order_by = getattr(source_model, '_sort_latest', True)
            order_by_str = "updated_at" if order_by else "id"
            order_desc = order_by
            
            if hasattr(self.window(), 'statusBar'):
                self.window().statusBar().showMessage(f"로딩되지 않은 {len(uncached_offsets)}행의 식별자를 스캔 중입니다...", 0)
            
            search_cols = getattr(source_model, "_search_cols", "")
            cols_str = search_cols if search_cols else ",".join(getattr(source_model, "_columns", []))
            worker = ApiTargetedRowIdWorker(scan_url, list(uncached_offsets), search_query, order_by_str, order_desc, cols=cols_str)
            
            def _on_scan_finished(result: dict):
                scanned_ids = result.get("row_ids", [])
                print(f"[Scanner] Scan finished. Found {len(scanned_ids)} IDs.")
                if hasattr(self.window(), 'statusBar'):
                    self.window().statusBar().showMessage(f"식별자 스캔 완료 ({len(scanned_ids)}개). 삭제를 진행합니다.", 3000)
                # 병합 및 중복 제거
                total_ids = list(set(loaded_row_ids + scanned_ids))
                _execute_deletion(total_ids)
                
            def _on_scan_error(err: str):
                if hasattr(self.window(), 'statusBar'):
                    self.window().statusBar().showMessage("식별자 스캔 실패", 3000)
                print(f"[Scanner] Error: {err}")
                QMessageBox.critical(self, "스캔 오류", f"로딩되지 않은 행 위치 스캔 중 서버 오류 발생:\n{err}")
                
            worker.signals.finished.connect(_on_scan_finished)
            worker.signals.error.connect(_on_scan_error)
            
            # GC 방지 및 실행
            self._active_workers.add(worker)
            def _cleanup_scan():
                if worker in self._active_workers: self._active_workers.remove(worker)
            worker.signals.finished.connect(_cleanup_scan)
            worker.signals.error.connect(_cleanup_scan)
            
            QThreadPool.globalInstance().start(worker)
        else:
            # 캐시된 것밖에 없으면 바로 삭제 시작
            _execute_deletion(loaded_row_ids)
            # 결과는 WebSocket 브로드캐스트를 통해 모든 클라이언트에 자동 반영됨
    
    def copy_selection(self):
        """선택된 영역을 클립보드에 복사 (옵션에 따라 헤더 포함 가능)."""
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
        
        # ── [Phase 2] 헤더 포함 옵션 처리 ──
        main_win = self.window()
        include_header = getattr(main_win, "_include_copy_header", False)
        
        if include_header:
            # 선택된 영역의 고유 컬럼 인덱스 추출 (정렬 순서 유지)
            col_indices = sorted(list(set(idx.column() for idx in indexes)))
            header_cells = []
            for col in col_indices:
                header_text = model.headerData(col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
                header_cells.append(str(header_text) if header_text is not None else "")
            lines.append("\t".join(header_cells))

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
        
        # ── 실시간 부상(Floating) 데이터 추적 스크롤 ──
        if hasattr(model, "rowsMoved"):
            model.rowsMoved.connect(self._on_rows_moved)

    def _on_rows_inserted(self, parent, first, last):
        if first == 0:
            self.scrollToTop()
            self.selectRow(0)

    def _on_rows_moved(self, parent, start, end, destination, row):
        # 행이 부상하여 이동했을 때, 이동된 도착지(row)로 스크롤 및 선택 포커스 추적
        if row == 0:
             self.scrollToTop()
             self.selectRow(0)
        else:
             index = self.model().index(row, 0)
             self.scrollTo(index)
             self.selectRow(row)

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
        self.resize(1400, 850)
        
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
        self._row_count_label = QLabel("Ready")
        
        # ── 디버거 단축키 (Ctrl+Shift+D) ──
        from PySide6.QtGui import QShortcut, QKeySequence
        self._debugger_shortcut = QShortcut(QKeySequence("Ctrl+Shift+D"), self)
        self._debugger_shortcut.activated.connect(self._toggle_fetch_debugger)
        self._fetch_debugger = None
        
        # ── 전역 새로고침 단축키 (F5) ──
        self._refresh_shortcut = QShortcut(QKeySequence("F5"), self)
        self._refresh_shortcut.activated.connect(self._on_global_refresh_requested)
        self._row_count_label.setStyleSheet("color: #fab387; font-weight: bold; margin-right: 15px;") # Peach
        self.statusBar().addPermanentWidget(self._row_count_label)
        self.statusBar().addPermanentWidget(self._ws_status_label)

        # ── 시그널 연결 ─────────────────────────────────────────────
        self._filter_bar.addTabRequested.connect(self._add_new_tab)
        self._filter_bar.addRowRequested.connect(self._on_add_row_requested)
        self._filter_bar.exportRequested.connect(self._on_export_requested)
        self._filter_bar.downloadsRequested.connect(self._on_show_download_manager)
        self._filter_bar.uploadRequested.connect(self._on_upload_requested)
        self._filter_bar.sortLatestChanged.connect(self._on_sort_mode_changed) # [신규] 정렬 토글 연결
        self._filter_bar.batchLoadRequested.connect(self._on_batch_load_requested) # [신규] 일괄 로드 연결
        self._filter_bar.searchRequested.connect(self._on_global_search)
        self._filter_bar.copyHeaderChanged.connect(self._on_copy_header_mode_changed) # [신규] 헤더 복사 토글 연결
        self._dashboard.tableFileDropped.connect(self._execute_file_upload)
        self._dashboard.tableDoubleClicked.connect(self._handle_dashboard_table_open)

        # ── 데이터 모델 매핑 (사이드바 메뉴 ID -> Widget Index) ──
        self._nav_to_index = {"home": 0, "settings": 1}
        self._index_to_table = {}

        # ── WebSocket 공유 리스너 (Shared WebSocket) ──────────────────
        print('WEB SOCKET 초기화')
        self._ws_thread: WsListenerThread | None = None
        self._active_models: list[ApiLazyTableModel] = []
        self._active_workers = set()
        self._include_copy_header = False 
        
        # ── 다운로드 매니저 초기화 ──
        from ui.dialog_downloads import DownloadManagerDialog
        self._download_manager = DownloadManagerDialog(self)

        # ── 서버로부터 모든 테이블 목록 조회 및 초기화 ──────────────
        print('TABLE 초기화')
        self._load_all_tables()
        
        # [Fix] 시작 시 홈(대시보드) 상태를 명시적으로 활성화하여 데이터 페칭 트리거
        self._on_navigation_requested("home")
        self._nav_rail.set_active("home")

        # [NEW] 히스토리 패널 초기 너비 설정 (350px 정도로 넓게)
        self.resizeDocks([self._history_panel], [350], Qt.Horizontal)

    def _toggle_fetch_debugger(self):
        """Fetch 디버깅 윈도우를 토글합니다 (Ctrl+Shift+D)."""
        if self._fetch_debugger is None:
            from ui.fetch_debugger import FetchDebugger
            self._fetch_debugger = FetchDebugger(self)
            
        if self._fetch_debugger.isVisible():
            self._fetch_debugger.hide()
        else:
            self._fetch_debugger.show()
            self._fetch_debugger.raise_()
            self._fetch_debugger.activateWindow()

    def _on_global_refresh_requested(self):
        """F5 입력 시 호출. 히스토리 패널 및 현재 활성화된 화면의 데이터를 서버에서 재동기화합니다."""
        # 1. 히스토리 패널 새로고침
        self._history_panel.refresh_history()
        
        # 2. 현재 화면 새로고침
        idx = self.stacked.currentIndex()
        if idx == 0:
            self._refresh_dashboard()
            self.statusBar().showMessage("🔄 대시보드를 새로고침했습니다.", 3000)
        elif idx == 1:
            pass # 설정 화면은 새로고침할 데이터가 없음
        else:
            page_widget = self.stacked.widget(idx)
            model = getattr(page_widget, "_source_model", None)
            if model and hasattr(model, "refresh_data"):
                # 필터 유지하며 데이터 새로고침
                model.refresh_data()
                
                # QTableView 스크롤 최상단으로 초기화
                from PySide6.QtWidgets import QTableView
                table_view = page_widget.findChild(QTableView)
                if table_view:
                    table_view.verticalScrollBar().setValue(0)
                    table_view.horizontalScrollBar().setValue(0)
                    table_view.clearSelection()
                
                self.statusBar().showMessage("🔄 테이블 데이터를 새로고침했습니다.", 3000)

    def _on_navigation_requested(self, nav_id: str):
        """사이드바 클릭 시 해당 화면으로 전환."""
        if nav_id in self._nav_to_index:
            idx = self._nav_to_index[nav_id]
            self.stacked.setCurrentIndex(idx)
            
            # 필터 툴바 활성 프록시 갱신
            if idx > 1: # 0: Dashboard, 1: Settings
                # [Refactor] nav_id에서 'table:' 접두어를 제거하여 순수 테이블 명으로 프록시 조회
                table_name = nav_id.replace("table:", "")
                proxy = self._filter_bar._proxies.get(table_name)
                self._filter_bar.set_active_proxy(proxy)
            
            # 윈도우 타이틀 및 툴바 표시 업데이트
            if nav_id == "home":
                self.setWindowTitle("AssyManager - Dashboard")
                self._filter_bar.show()
                self._filter_bar.set_active_proxy(None)
                self._refresh_dashboard()
                self._update_row_count_display(0, 0, 0)
            elif nav_id == "settings":
                self.setWindowTitle("AssyManager - Settings")
                self._filter_bar.show()
                self._filter_bar.set_active_proxy(None)
                self._update_row_count_display(0, 0, 0)
            else:
                table_name = nav_id.replace("table:", "")
                page_widget = self.stacked.widget(idx)
                model = getattr(page_widget, "_source_model", None)
                total_text = f" [{model._total_count:,} rows]" if model else ""
                self.setWindowTitle(f"AssyManager - {table_name}{total_text}")
                self._filter_bar.show()
                if model:
                    # [Phase 73.8] 탭 변경 즉시 전체 카운트 표시 업데이트 및 서버 동기화 트리거
                    self._update_row_count_display(model._exposed_rows, model.loaded_count, model._total_count)
                    
                    # 최초 접속이거나 데이터가 없는 상태라면 즉시 갱신 시작
                    if model._total_count == 0:
                        model._refresh_total_count()

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
            tables = result.get("tables", [])
            if not tables:
                self._init_table_tab("inventory_master")
            else:
                # [Phase 1] 자동 로딩 제거: 이제 사용자가 대시보드에서 선택해서 엽니다.
                print(f"[Main] {len(tables)} tables identified. Waiting for user interaction.")
            
            # [Fix] 테이블 목록이 로드된 후 대시보드 카드를 즉시 갱신
            self._refresh_dashboard()
            
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
        self._ws_thread.connected.connect(self._on_ws_connected) # [신규] 재연결 동기화
        self._ws_thread.start()
        
        # 상태바 갱신
        self._ws_status_label.setText("  ● WebSocket: Connected  ")
        self._ws_status_label.setStyleSheet("color: #a6e3a1;") # Green
        
        print(f"[MainWS] Shared Listener Thread started for {ws_url}")
        
        # 앱 종료 시 정리 연결
        QApplication.instance().aboutToQuit.connect(self._ws_thread.stop)

    def _refresh_dashboard(self):
        """서버로부터 최신 대시보드 요약 정보를 가져와 반영합니다."""
        # [Resilience] 잦은 리프레시 방지 (최소 2초 간격)
        now = datetime.now()
        if hasattr(self, "_last_dashboard_refresh"):
            if (now - self._last_dashboard_refresh).total_seconds() < 2:
                return
        self._last_dashboard_refresh = now

        url = config.get_dashboard_summary_url()
        from models.table_model import ApiSchemaWorker
        worker = ApiSchemaWorker(url)
        
        def _on_dashboard_loaded(result):
            self._dashboard.update_dashboard(result)
            if worker in self._active_workers:
                self._active_workers.remove(worker)
                
        def _on_error(err):
            print(f"[Dashboard] Refresh failed: {err}")
            self.statusBar().showMessage(f"대시보드 동기화 실패: {err}", 3000)
            if worker in self._active_workers:
                self._active_workers.remove(worker)

        worker.signals.finished.connect(_on_dashboard_loaded)
        worker.signals.error.connect(_on_error)
        self._active_workers.add(worker)
        QThreadPool.globalInstance().start(worker)

    def _on_ws_error(self, err):
        print(f"[MainWS] Connection lost or error: {err}")
        self._ws_status_label.setText("  ● WebSocket: Reconnecting...  ")
        self._ws_status_label.setStyleSheet("color: #fab387;") # Peach/Orange (Reconnecting)
        self.statusBar().showMessage(f"WebSocket 연결 유실: {err}", 5000)

    def _on_ws_connected(self):
        """[Phase 73.12] 웹소켓 재연결 시 모든 활성 모델의 카운트를 즉시 재동기화 (Self-Healing)."""
        print("[WS] Reconnected. Synchronizing all active models...")
        self.statusBar().showMessage("🌐 웹소켓 연결됨 - 실시간 동기화 복구 중...", 3000)
        
        # [NEW] 연결 성공 즉시 히스토리 패널 새로고침
        if hasattr(self, "_history_panel"):
            self._history_panel.refresh_history()

        for model in self._active_models:
            if hasattr(model, "_refresh_total_count"):
                model._refresh_total_count()
        self._ws_status_label.setText("  ● WebSocket: Connected  ")
        self._ws_status_label.setStyleSheet("color: #a6e3a1;") # Green

    def _dispatch_ws_message(self, data: dict):
        """수신된 WS 메시지를 활성 모델들에 전파하고, 단일 진입점에서 히스토리 로그를 기록합니다."""
        event = data.get("event")
        table_name = data.get("table_name")
        
        print('[WS 수신] ', event)
        # 1. 모든 활성 모델에 데이터 전파 (테이블 뷰 갱신)
        for model in self._active_models:
            model._on_websocket_broadcast(data)
            
        # 2. [통합] 히스토리 패널에 단일 로그 생성 요청
        if event in ["batch_row_create", "batch_row_delete", "batch_row_upsert"]:
            self._history_panel.log_event(data)
        elif event == "batch_refresh_required":
            print("[MainWindow] Batch refresh required: refreshing history panel.")
            self._history_panel.refresh_history()

        # 3. 대시보드 통계 갱신 (행 개수 변화 관련 이벤트인 경우)
        if event in ["batch_row_create", "batch_row_delete", "batch_row_upsert", "batch_refresh_required"]:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(500, self._refresh_dashboard)

    def _handle_dashboard_table_open(self, table_name: str):
        """대시보드 카드 더블 클릭 시 테이블을 열거나 전환합니다."""
        nav_id = f"table:{table_name}"
        if nav_id in self._nav_to_index:
            # 이미 열려있는 경우 전환
            self._on_navigation_requested(nav_id)
            self._nav_rail.set_active(nav_id)
        else:
            # 새로운 탭으로 초기화
            self._init_table_tab(table_name)
        
    def _on_global_search(self, text: str, cols_str: str = ""):
        """
        필터 툴바의 검색어가 변경되었을 때 전체 활성 모델에 서버 사이드 검색을 요청합니다.
        """
        print(f"[MainWindow] Global search requested: '{text}' (cols: {cols_str})")
        for model in self._active_models:
            # col_str가 비어있으면 모델 내부의 기본 컬럼을 사용하도록 위임
            model.set_search_query(text, search_cols=cols_str)

    def _on_sort_mode_changed(self, enabled: bool):
        """
        필터 툴바에서 정렬 토글이 변경되었을 때 모든 활성 모델의 정렬 설정을 동기화합니다.
        """
        print(f"[MainWindow] Sort mode changed: LatestFirst={enabled}")
        for model in self._active_models:
            model.set_sort_latest(enabled)

    def _on_copy_header_mode_changed(self, enabled: bool):
        """툴바에서 헤더 포함 복사 옵션이 변경될 때 상태를 업데이트합니다."""
        print(f"[MainWindow] Copy with Header mode: {enabled}")
        self._include_copy_header = enabled

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

    def _init_table_tab(self, table_name: str, first_fetch = True):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        table_view = ExcelTableView(self)
        table_view.setObjectName(f"table_view")
        table_view.setAlternatingRowColors(True)

        # Connect to REST API data model
        model = ApiLazyTableModel(table_name=table_name)
        tab._source_model = model
        # ── 활성 모델 리스트에 추가 (Shared WS Dispatch 용) ──
        self._active_models.append(model)

        # ── 필터 프록시 ──
        proxy = self._filter_bar.create_proxy(table_name, model)
        table_view.setModel(proxy)

        # ── 행 개수 실시간 업데이트 연결 ──
        model.count_changed.connect(self._update_row_count_display)
        model.batch_fetch_finished.connect(self._filter_bar.reset_batch_btn)
        model.status_message_requested.connect(lambda msg: self.statusBar().showMessage(msg, 3000))

        # ── 드래그 앤 드롭 업로드 연결 ──
        table_view.fileDropped.connect(
            lambda path: self._execute_file_upload(table_name, path)
        )

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
        
        # [Fix] 수동 조작 대신 중앙 내비게이션 메서드를 통해 상단 바/상태 바까지 한 번에 동기화
        self._on_navigation_requested(nav_id)
        self._nav_rail.set_active(nav_id)

        # ── Agent D v4: 서버에서 스키마 로드 후 데이터 페칭 시작 (Sequential) ──
        self._load_table_schema(model, first_fetch = first_fetch  )

    def _load_table_schema(self, model: ApiLazyTableModel, first_fetch = True):
        """[Phase 73.8] 특정 테이블 모델의 스키마를 비동기로 로드합니다. (캐싱 적용)"""
        table_name = model.table_name
        
        # ── Agent Stability: 이미 스키마 정보가 있다면 네트워크 요청 스킵 ──
        if hasattr(model, "_columns") and model._columns:
            print(f"[Schema] Local cache hit for {table_name}. Skipping network fetch.")
            if first_fetch:
                from models.table_model import FetchContext
                model.request_fetch(FetchContext(source="schema_load"))
            return

        schema_url = config.get_table_schema_url(table_name)
        worker = ApiSchemaWorker(schema_url)
        
        def _on_schema_loaded(result):
            cols = result.get("columns", [])
            if cols:
                model.update_columns(cols)
                print(f"[Schema] Successfully updated columns for {table_name}: {cols}")
                # ── 스키마가 확보된 직후 첫 데이터 페칭 시작 (안정성 보장) ──
                if first_fetch:
                    from models.table_model import FetchContext
                    model.request_fetch(FetchContext(source="schema_load"))
            else:
                print(f"[Schema] No columns returned for {table_name}")
            
            # 워커 참조 제거 (GC 허용)
            if worker in self._active_workers:
                self._active_workers.remove(worker)
        
        def _on_schema_error(err):
            print(f"[Schema] Network error loading schema for {table_name}: {err}")
            # Agent D v6: Even if schema fails, try to fetch data with default columns
            if first_fetch:
                from models.table_model import FetchContext
                model.request_fetch(FetchContext(source="schema_load"))
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
        """현재 활성화된 테이블의 검색 조건에 맞는 데이터를 CSV로 추출합니다."""
        idx = self.stacked.currentIndex()
        if idx <= 0: return
        
        table_name = self._index_to_table.get(idx)
        if not table_name: return
        
        page = self.stacked.widget(idx)
        model = getattr(page, "_source_model", None)
        if not model: return

        # 1. 파일 저장 경로 결정
        from datetime import datetime
        default_name = f"{table_name}_extract_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "CSV 저장 (최대 100만 행)", default_name, "CSV Files (*.csv)"
        )
        if not file_path: return

        # 2. 검색 및 정렬 파라미터 추출
        import urllib.parse
        params = {
            "q": model._search_query or "",
            "cols": model._search_cols or "",
            "order_by": "updated_at" if model._sort_latest else "id",
            "order_desc": "true" if model._sort_latest else "false"
        }
        
        # 3. 서버에서 백그라운드 스트리밍 다운로드 시작
        from models.table_model import ApiExportWorker
        import uuid
        task_id = str(uuid.uuid4())[:8]
        
        base_url = config.get_table_export_url(table_name)
        url = f"{base_url}?{urllib.parse.urlencode(params)}"
        
        worker = ApiExportWorker(task_id, url, file_path)
        
        # 다운로드 매니저에 등록 및 표시
        self._download_manager.add_download(task_id, os.path.basename(file_path), worker)
        self._download_manager.show()
        self._download_manager.raise_()
        
        # 메인 윈도우에서는 간략한 상태만 표시
        self.statusBar().showMessage(f"🚀 {table_name} 다운로드 시작 (ID: {task_id})", 3000)
        
        self._active_workers.add(worker)
        QThreadPool.globalInstance().start(worker)

    def _on_show_download_manager(self):
        """다운로드 매니저 창을 소생 시키거나 표시합니다."""
        self._download_manager.show()
        self._download_manager.raise_()
        self._download_manager.activateWindow()




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
            if worker in self._active_workers:
                self._active_workers.remove(worker)
            
        def _on_error(err):
            QMessageBox.critical(self, "실패", f"파일 업로드 중 오류 발생:\n{err}")
            if worker in self._active_workers:
                self._active_workers.remove(worker)

        worker.signals.finished.connect(_on_finished)
        worker.signals.error.connect(_on_error)
        
        # ── Agent Stability: 워커 GC 방지 및 추적 활성화 ──
        if not hasattr(self, "_active_workers"):
            self._active_workers = set()
        self._active_workers.add(worker)
        
        QThreadPool.globalInstance().start(worker)

    def _update_row_count_display(self, exposed: int, loaded: int, total: int):
        """[Phase 73.8] 타이머 지연 제거: 실시간으로 화면 표시 갱신."""
        self._execute_row_count_display(exposed, loaded, total)

    def _execute_row_count_display(self, exposed: int, loaded: int, total: int):
        """하단 상태 표시줄 및 타이틀 바에 실제로 행 개수 정보를 갱신합니다."""
        curr_idx = self.stacked.currentIndex()
        table_name = self._index_to_table.get(curr_idx)
        if not table_name:
            if hasattr(self, "_row_count_label"):
                self._row_count_label.setText("Ready")
            return
            
        if hasattr(self, "_row_count_label"):
            idx = self.stacked.currentIndex()
            page = self.stacked.widget(idx)
            # [Phase 73.8] 용어 표준화: Loaded(데이터 적재) / Exposed(영역 확보) / Total(전체)
            self._row_count_label.setText(f"Loaded: {loaded:,} | Exposed: {exposed:,} | Total: {total:,}")
        
        # 타이틀 바 업데이트 (현재 테이블인 경우에만)
        if self.windowTitle().startswith(f"AssyManager - {table_name}"):
            self.setWindowTitle(f"AssyManager - {table_name} [Total: {total:,}]")

    def _on_batch_load_requested(self, count: int):
        """현재 활성화된 테이블 모델에 일괄 로드를 요청합니다."""
        idx = self.stacked.currentIndex()
        if idx <= 0: return # Home or Dashboard
        
        page = self.stacked.widget(idx)
        source_model = getattr(page, "_source_model", None)
        if source_model and hasattr(source_model, "fetch_batch"):
            source_model.fetch_batch(count)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Modern style
    app.setStyle("Fusion")
    
    # ── 강제 다크 테마 설정 (Catppuccin Mocha 기반) ──
    from PySide6.QtGui import QPalette, QColor
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#1e1e2e"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#cdd6f4"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#11111b"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#181825"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#313244"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#cdd6f4"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#cdd6f4"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#313244"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#cdd6f4"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#f38ba8"))
    palette.setColor(QPalette.ColorRole.Link, QColor("#89b4fa"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#89b4fa"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#1e1e2e"))
    app.setPalette(palette)
    
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
