"""
panel_history.py
업데이트 히스토리 패널 (Refactored v2.0 - Logic Separation)

- HistoryDataManager: 데이터 및 실시간 싱크 담당
- HistoryNavigator: 4단계 내비게이션 시퀀스 담당
- HistoryItemData: 데이터 객체화
"""

from __future__ import annotations
from PySide6.QtWidgets import QDockWidget, QListWidget, QListWidgetItem, QWidget, QVBoxLayout
from PySide6.QtCore import Qt, Slot, QTimer
from PySide6.QtGui import QColor

from ui.history_logic import HistoryDataManager, HistoryNavigator, HistoryItemData


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
        self._list = QListWidget()
        self._list.setStyleSheet(
            "QListWidget { background: #1e1e2e; color: #cdd6f4; font-family: 'Consolas', monospace; font-size: 11px; }"
            "QListWidget::item:hover { background: #313244; }"
            "QListWidget::item:selected { background: #45475a; }"
        )
        self._list.itemClicked.connect(self._on_item_clicked)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        
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
        self._list.clear()
        
        if not data_list:
            self._list.addItem("이력이 없거나 데이터를 불러올 수 없습니다.")
            return

        for data in data_list:
            # 1. 중복 컬럼 요약 추출
            cols = []
            for log in data.logs:
                c = log.get("column_name")
                if c and c not in cols: cols.append(c)
            
            col_count = len(cols)
            if col_count > 5:
                summary = ", ".join(cols[:5]) + f" 외 {col_count - 5}건"
            else:
                summary = ", ".join(cols)

            # 2. 메인 텍스트 구성 (객체 메서드 사용 및 색상 적용)
            item = QListWidgetItem(self._list)
            item.setText(f"{data.get_display_text()}\n   → Fields: {summary}")
            item.setForeground(QColor(data.get_color()))
            
            # 3. 툴팁 상세 (최대 20개까지만 상세 표시)
            details = []
            for i, log in enumerate(data.logs):
                if i >= 20:
                    details.append(f"... (총 {len(data.logs)}건 중 {len(data.logs)-20}건 생략됨)")
                    break
                details.append(f"[{log.get('column_name')}] {str(log.get('old_value'))[:20]} -> {str(log.get('new_value'))[:20]}")
            
            item.setToolTip("\n".join(details))
            
            # [중요] 내비게이션 기능을 위한 데이터 객체 보존
            item.setData(Qt.UserRole, data)
            self._list.addItem(item)

    @Slot(str)
    def _on_sync_error(self, err_msg):
        self.set_status("⚠️ 히스토리 동기화 실패", 3000)
        if self._list.count() == 0:
            item = QListWidgetItem(f"⚠️ 로딩 실패 ({err_msg})")
            item.setForeground(QColor("#f38ba8"))
            self._list.addItem(item)

    @Slot(QListWidgetItem)
    def _on_item_clicked(self, item: QListWidgetItem):
        """항목 클릭 시 Navigator에게 내비게이션을 위임합니다."""
        data = item.data(Qt.UserRole)
        if not data or data.is_summary: return
        self._navigator.navigate_to_log(data, self)

    @Slot(QListWidgetItem)
    def _on_item_double_clicked(self, item: QListWidgetItem):
        """요약 항목 더블 클릭 시 상세 내역을 펼칩니다."""
        data = item.data(Qt.UserRole)
        if not data or not data.is_summary: return
        
        is_expanded = data.is_expanded
        current_row = self._list.row(item)
        tx_id = data.tx_id

        if not is_expanded:
            # 펼치기
            for i, log in enumerate(data.logs):
                col = log.get("column_name", "?")
                val = log.get("new_value", "null")
                row_id = log.get("row_id", "")
                
                detail_text = f"  └─ {col}: {val} (ID:{row_id[:8]}...)"
                sub_item = QListWidgetItem(detail_text)
                sub_item.setForeground(QColor("#9399b2"))
                # 상세 항목 데이터 설정 (개별 내비게이션 가능하게)
                sub_data = HistoryItemData([log])
                sub_item.setData(Qt.UserRole, sub_data)
                self._list.insertItem(current_row + 1 + i, sub_item)
            
            data.is_expanded = True
            item.setText(item.text().replace("📦", "📂"))
        else:
            # 접기
            next_row = current_row + 1
            while next_row < self._list.count():
                next_item = self._list.item(next_row)
                n_data = next_item.data(Qt.UserRole)
                if n_data and not n_data.is_summary and n_data.tx_id == tx_id:
                    self._list.takeItem(next_row)
                else:
                    break
            data.is_expanded = False
            item.setText(item.text().replace("📂", "📦"))

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
