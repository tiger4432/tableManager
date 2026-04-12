"""
panel_history.py
업데이트 히스토리 패널 (PanelUIExpert 스킬 규칙 준수)

- QDockWidget 상속 → HistoryDockPanel
- dataChanged 시그널 수신 → 로그 항목 prepend
- is_overwrite=True : 노란색 텍스트 / False : 회색 텍스트
- 항목 클릭 → 해당 탭 포커스 및 행 scrollTo()
"""

from __future__ import annotations
from datetime import datetime

from PySide6.QtWidgets import QDockWidget, QListWidget, QListWidgetItem, QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QModelIndex, Signal, Slot
from PySide6.QtGui import QColor


class HistoryDockPanel(QDockWidget):
    """실시간 셀 업데이트 이력을 보여주는 사이드 패널."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__("📋 업데이트 히스토리", parent)
        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )

        self._list = QListWidget()
        self._list.setStyleSheet(
            "QListWidget { background: #1e1e2e; color: #cdd6f4; font-family: 'Consolas', monospace; font-size: 11px; }"
            "QListWidget::item:hover { background: #313244; }"
            "QListWidget::item:selected { background: #45475a; }"
        )
        self._list.itemClicked.connect(self._on_item_clicked)
        
        # ── Lineage 세션 추가 ──
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

        # {id(QListWidgetItem): (table_view, row_index)} 매핑
        # PySide6의 QListWidgetItem은 unhashable이므로 id()를 키로 사용
        self._item_meta: dict[int, tuple] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def connect_model(self, model, table_name: str, table_view):
        """
        ApiLazyTableModel 의 dataChanged 시그널을 이 패널 슬롯에 연결합니다.
        model      : ApiLazyTableModel 인스턴스
        table_name : 탭 레이블 문자열 (로그 표시용)
        table_view : 해당 탭의 QTableView (scrollTo 대상)
        """
        # 클로저로 context 를 바인딩하여 dataChanged 에 연결
        def _on_data_changed(top_left: QModelIndex, bottom_right: QModelIndex, roles: list):
            self._handle_data_changed(
                top_left, bottom_right, roles, model, table_name, table_view
            )

        model.dataChanged.connect(_on_data_changed)

        # Agent D v2: WS 원격 이벤트 전용 Signal 연결
        if hasattr(model, 'ws_data_changed'):
            model.ws_data_changed.connect(
                lambda data: self._log_ws_event(data, table_name, table_view)
            )

    # ------------------------------------------------------------------
    # Private slots / helpers
    # ------------------------------------------------------------------

    def _handle_data_changed(
        self,
        top_left: QModelIndex,
        bottom_right: QModelIndex,
        roles: list,
        model,
        table_name: str,
        table_view,
    ):
        """dataChanged 수신 → 로그 항목을 목록 최상단에 추가."""
        if Qt.ItemDataRole.DisplayRole not in roles:
            return

        now = datetime.now().strftime("%H:%M:%S")
        columns = model._columns

        for row in range(top_left.row(), bottom_right.row() + 1):
            for col in range(top_left.column(), bottom_right.column() + 1):
                if row >= len(model._data):
                    continue

                row_data = model._data[row]
                row_id = row_data.get("row_id", "unknown")
                cell_data = row_data.get("data", {})
                col_name = columns[col] if col < len(columns) else str(col)
                item_info = cell_data.get(col_name, {})
                is_overwrite = item_info.get("is_overwrite", False)
                value = item_info.get("value", "")

                suffix = "MANUAL_FIX (수동교정)" if is_overwrite else "AUTO_UPDATE (자동업데이트)"
                text = f"[{now}] {table_name} / {col_name} / row_id:{row_id} → {value}  |  {suffix}"

                list_item = QListWidgetItem(text)
                if is_overwrite:
                    list_item.setForeground(QColor("#f9e2af"))   # 노란색
                else:
                    list_item.setForeground(QColor("#6c7086"))   # 회색

                # 메타 저장: id(item)을 키로 사용 (QListWidgetItem은 unhashable)
                self._item_meta[id(list_item)] = (table_view, model.index(row, 0))

                self._list.insertItem(0, list_item)  # prepend

    def _log_ws_event(self, data: dict, table_name: str, table_view):
        """WS 브로드캐스트 이벤트 전용 로그 항목 추가. 🌐 [원격] 접두어로 구분."""
        now = datetime.now().strftime("%H:%M:%S")
        row_id = data.get("row_id", "unknown")
        col_name = data.get("column_name", "?")
        value = data.get("value", "")
        updated_by = data.get("updated_by", "unknown")

        text = (
            f"🌐 [원격] [{now}] {table_name} / {col_name} / "
            f"row_id:{row_id} → {value}  |  by:{updated_by}"
        )

        list_item = QListWidgetItem(text)
        list_item.setForeground(QColor("#89dceb"))  # 하늘색: 원격 이벤트 구분

        # scrollTo 는 row_id 기반 조회가 필요하므로 best-effort로 meta 저장
        m = table_view.model()
        if m is not None and hasattr(m, '_build_row_id_map'):
            row_id_map = m._build_row_id_map()
            row_idx = row_id_map.get(row_id)
            if row_idx is not None:
                self._item_meta[id(list_item)] = (table_view, m.index(row_idx, 0))

        self._list.insertItem(0, list_item)

    @Slot(QListWidgetItem)
    def _on_item_clicked(self, item: QListWidgetItem):
        """항목 클릭 → 해당 테이블뷰로 포커스 + 스크롤."""
        meta = self._item_meta.get(id(item))
        if meta is None:
            return
        table_view, model_index = meta
        if table_view and model_index.isValid():
            table_view.setFocus()
            table_view.scrollTo(model_index, table_view.ScrollHint.PositionAtCenter)
            table_view.setCurrentIndex(model_index)
            
            # 항목 클릭 시 해당 셀의 상세 계보 자동 조회
            self._fetch_cell_lineage(table_view, model_index)

    def _fetch_cell_lineage(self, table_view, index):
        """특정 셀의 전체 변경 이력을 API에서 가져와 하단에 표시합니다."""
        model = table_view.model()
        source_model = getattr(model, 'sourceModel', lambda: model)()
        row = index.row()
        col = index.column()
        
        if row >= len(source_model._data): return
        
        row_id = source_model._data[row].get("row_id")
        col_name = source_model._columns[col]
        table_name = source_model.table_name
        
        import urllib.request
        import json
        url = f"{source_model.base_api_url}/tables/{table_name}/rows/{row_id}/cells/{col_name}/history"
        
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
            item = QListWidgetItem(text)
            self._lineage_list.addItem(item)
