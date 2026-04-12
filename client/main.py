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
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QGuiApplication
from models.table_model import ApiLazyTableModel
from ui.panel_history import HistoryDockPanel
from ui.panel_filter import FilterToolBar

class ExcelTableView(QTableView):
    def contextMenuEvent(self, event):
        """우클릭 컨텍스트 메뉴 — 행 삭제 기능 제공."""
        menu = QMenu(self)
        delete_action = menu.addAction("🗑️ 선택된 행 삭제")
        delete_action.triggered.connect(self.delete_selected_rows)
        menu.exec(event.globalPos())

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

        # Initialize first tab
        self._init_table_tab("raw_table_1")
        
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
        """탭 닫기 — WS 리스너 정리 후 탭 제거."""
        tab_widget = self.tabs.widget(index)
        # 모델 참조를 tab에 저장해 둔 경우 WS 종료
        model = getattr(tab_widget, "_source_model", None)
        if model is not None:
            model.stop_ws_listener()
            try:
                QApplication.instance().aboutToQuit.disconnect(model.stop_ws_listener)
            except RuntimeError:
                pass  # 이미 해제된 경우 무시
        self.tabs.removeTab(index)

    def _init_table_tab(self, table_name: str):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        table_view = ExcelTableView()
        table_view.setAlternatingRowColors(True)

        # Connect to REST API data model (source model, NOT modified)
        model = ApiLazyTableModel(table_name=table_name)
        # 탭 위젯에 모델 참조를 보관 → _close_tab에서 WS 정리에 활용
        tab._source_model = model

        # ── 필터 프록시: 원본 모델을 감싸 실시간 필터링 (스킬 규칙 2번) ──
        proxy = self._filter_bar.create_proxy(model)
        table_view.setModel(proxy)

        # Trigger first fetch; 빈 테이블 감지를 위해 콜백 연결
        if model.canFetchMore():
            # 첫 fetch 완료 후 total=0이면 탭 레이블을 갱신
            tab_index_holder = [None]

            def _on_first_fetch_done():
                if model._total_count == 0:
                    idx = tab_index_holder[0]
                    if idx is not None:
                        self.tabs.setTabText(idx, f"{table_name} (빈 테이블)")
                # 일회성 연결 해제
                try:
                    model.rowsInserted.disconnect(_on_first_fetch_done)
                    model.modelReset.disconnect(_on_first_fetch_done)
                except RuntimeError:
                    pass

            model.rowsInserted.connect(_on_first_fetch_done)
            model.modelReset.connect(_on_first_fetch_done)
            model.fetchMore()

        # WebSocket 실시간 수신 리스너 시작 (Agent D 구현분 활성화)
        model.start_ws_listener()
        # 앱 종료 시 스레드 안전하게 정리
        QApplication.instance().aboutToQuit.connect(model.stop_ws_listener)

        # ── 히스토리 패널 연결: dataChanged → 로그 prepend (스킬 규칙 3번) ──
        self._history_panel.connect_model(model, table_name, table_view)

        layout.addWidget(table_view)

        tab_idx = self.tabs.addTab(tab, table_name)
        tab_index_holder[0] = tab_idx
        self.tabs.setCurrentIndex(tab_idx)



if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Modern style
    app.setStyle("Fusion")
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
