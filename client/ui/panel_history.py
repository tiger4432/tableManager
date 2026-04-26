"""
panel_history.py
업데이트 히스토리 패널 (Refactored v2.0 - Logic Separation)

- HistoryDataManager: 데이터 및 실시간 싱크 담당
- HistoryNavigator: 4단계 내비게이션 시퀀스 담당
- HistoryItemData: 데이터 객체화
"""

from __future__ import annotations
from PySide6.QtWidgets import QDockWidget, QListWidget, QListWidgetItem, QWidget, QVBoxLayout, QListView
from PySide6.QtCore import Qt, Slot, QTimer, QModelIndex
from PySide6.QtGui import QColor

from ui.history_logic import HistoryDataManager, HistoryNavigator, HistoryItemData, HistoryListModel


class HistoryDockPanel(QDockWidget):
    """실시간 셀 업데이트 이력을 보여주는 사이드 패널."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__("📋 업데이트 히스토리", parent)
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable |
            QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )

        # ── 컴포넌트 초기화 ──
        self._data_manager = HistoryDataManager(self)
        self._navigator = HistoryNavigator(self)
        
        # ── UI 구성 ──
        self._list = QListView()
        self._model = HistoryListModel(self)
        self._list.setModel(self._model)
        self._list.setSpacing(0)
        self._list.setUniformItemSizes(True)
        
        self._list.setStyleSheet(
            "QListView { background: #1e1e2e; color: #cdd6f4; font-family: 'Consolas', monospace; font-size: 11px; }"
            "QListView::item { padding: 4px;}"
            "QListView::item:hover { background: #313244; }"
            "QListView::item:selected { background: #45475a; }"
        )
        self._list.clicked.connect(self._on_item_clicked)
        self._list.doubleClicked.connect(self._on_item_double_clicked)
        
        self._lineage_list = QListWidget()
        self._lineage_list.setStyleSheet(
            "QListWidget { background: #181825; border-top: 2px solid #45475a; color: #a6adc8; font-size: 10px; }"
        )
        self._lineage_list.hide()
        
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._list, 3)
        layout.addWidget(self._lineage_list, 1)
        
        container = QWidget()
        container.setLayout(layout)
        self.setWidget(container)

        # ── 시그널 연결 ──
        self._data_manager.logsReady.connect(self._render_history)
        self._data_manager.syncError.connect(self._on_sync_error)
        self._navigator.statusRequested.connect(self.set_status)

        # 초기 데이터 로딩
        QTimer.singleShot(500, self.refresh_history)

    # ------------------------------------------------------------------
    # UI Helpers
    # ------------------------------------------------------------------
    def set_status(self, msg: str, timeout: int = 3000):
        main_win = self.window()
        if hasattr(main_win, "statusBar"):
            main_win.statusBar().showMessage(msg, timeout)

    # ------------------------------------------------------------------
    # Public API (Forwards)
    # ------------------------------------------------------------------
    def refresh_history(self):
        self.set_status("🔄 최신 이력을 동기화하는 중...", 0)
        self._data_manager.refresh_history()

    def log_event(self, data: dict):
        self._data_manager.log_event(data)

    # ------------------------------------------------------------------
    # Slot & Internal Logic
    # ------------------------------------------------------------------
    @Slot(list)
    def _render_history(self, data_list: list[HistoryItemData]):
        """HistoryItemData 객체 리스트를 UI에 렌더링합니다."""
        self._model.set_data(data_list)

    @Slot(str)
    def _on_sync_error(self, err_msg):
        self.set_status(f"⚠️ 히스토리 동기화 실패: {err_msg}", 3000)

    @Slot(QModelIndex)
    def _on_item_clicked(self, index: QModelIndex):
        item = self._model.data(index, Qt.ItemDataRole.UserRole)
        if not item: return
        
        if item.is_summary_item and item.data_obj.is_summary:
            return # 다중 건 요약 클릭 시 무시
            
        # 단일 건 또는 자식 상세 항목 클릭 시 뷰포트 이동
        from ui.history_logic import HistoryItemData
        target_data = item.data_obj if item.is_summary_item else HistoryItemData([item.detail_log])
        self._navigator.navigate_to_log(target_data, self)

    @Slot(QModelIndex)
    def _on_item_double_clicked(self, index: QModelIndex):
        self._model.toggle_expand(index.row())

    # ------------------------------------------------------------------
    # Lineage Logic (Remains in UI for now as it directly affects lists)
    # ------------------------------------------------------------------
    def _fetch_cell_lineage(self, table_view, index):
        """특정 셀의 전체 변경 이력을 가져옵니다."""
        model = table_view.model()
        source_model = getattr(model, 'sourceModel', lambda: model)()
        src_index = model.mapToSource(index) if hasattr(model, "mapToSource") else index
        
        if src_index.row() >= len(source_model._data): return
        
        row_id = source_model._data[src_index.row()].get("row_id")
        col_name = source_model._columns[src_index.column()]
        table_name = source_model.table_name
        
        import urllib.request, json, config
        url = config.get_cell_history_url(table_name, row_id, col_name)
        try:
            with urllib.request.urlopen(url) as response:
                logs = json.loads(response.read().decode())
                self._display_lineage(logs, col_name)
        except Exception as e:
            print(f"Failed to fetch lineage: {e}")

    def _display_lineage(self, logs, col_name):
        self._lineage_list.clear()
        if not logs:
            self._lineage_list.hide()
            return
        self._lineage_list.show()
        self._lineage_list.addItem(f"── [{col_name}] Lineage ──")
        for log in logs:
            ts = log["timestamp"][:19].replace("T", " ")
            text = f"[{ts}] {log['old_value']} → {log['new_value']} ({log['source_name']} by {log['updated_by']})"
            self._lineage_list.addItem(QListWidgetItem(text))
