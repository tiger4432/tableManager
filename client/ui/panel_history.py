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
        self._item_meta: dict[int, tuple] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def connect_model(self, model, table_name: str, table_view):
        """
        ApiLazyTableModel 의 dataChanged(로컬 수정) 시그널만 직접 연결합니다.
        WS 이벤트는 MainWindow 에서 통합 관리합니다.
        """
        def _on_data_changed(top_left, bottom_right, roles):
            self._handle_local_data_changed(top_left, bottom_right, roles, model, table_name, table_view)

        model.dataChanged.connect(_on_data_changed)

    def log_event(self, data: dict, table_view=None, nav_id=None):
        """
        모든 실시간 이벤트를 통합 처리하는 단일 진입점입니다.
        MainWindow 에서 호출하며, table_view 와 nav_id 가 제공될 경우 '클릭 시 이동 및 탭 전환'을 지원합니다.
        """
        now = datetime.now().strftime("%H:%M:%S")
        event = data.get("event")
        table_name = data.get("table_name", "Unknown")
        user_name = data.get("updated_by", "system")
        
        msg = ""
        color = "#89dceb" # 기본 하늘색
        meta_row_id = None

        # ── 1. 이벤트 타입별 메시지 구성 ──
        if event == "batch_row_upsert":
            items = data.get("items", [])
            msg = f"🔄 [업데이트] {table_name} / {len(items)}건 일괄 적재"
            color = "#cba6f7" # 보라색
            if items: meta_row_id = items[0].get("row_id")
            
        elif event in ["row_create", "batch_row_create"]: # 단건/다건 통합 대응
            items = data.get("items", []) if event == "batch_row_create" else [data.get("data", {})]
            msg = f"🆕 [신규 행] {table_name} / {len(items)}건 생성"
            color = "#a6e3a1"
            if items: meta_row_id = items[0].get("row_id")

        elif event == "batch_row_delete":
            row_ids = data.get("row_ids", [])
            msg = f"🗑️ [행 삭제] {table_name} / {len(row_ids)}건 삭제됨"
            color = "#f38ba8" # 빨간색
            
        elif event in ["cell_update", "batch_cell_update"]:
            updates = [data] if event == "cell_update" else data.get("updates", [])
            change_count = len(updates)
            if change_count > 1:
                msg = f"🔄 [업데이트] {table_name} / {change_count}건의 셀 변경"
            elif updates:
                u = updates[0]
                msg = f"🔄 [업데이트] {table_name} / {u.get('column_name', '?')} 변경 (ID:{u.get('row_id')})"
                meta_row_id = u.get("row_id")
            color = "#89dceb"
        else:
            return # 알 수 없는 이벤트 무시

        # ── 2. 로그 항목 생성 ──
        text = f"{msg} [{now}] [{user_name}]"
        list_item = QListWidgetItem(text)
        list_item.setForeground(QColor(color))
        
        # ── 3. 클릭 이동 및 탭 전환 메타데이터 바인딩 ──
        if table_view and meta_row_id:
            list_item.setToolTip(f"ID:{meta_row_id} 위치로 이동 및 테이블 전환을 위해 클릭하세요.")
            # (table_view, row_id, nav_id) 형태로 저장
            self._item_meta[id(list_item)] = (table_view, meta_row_id, nav_id)
        else:
            list_item.setToolTip(f"실시간 업데이트 요약 로그입니다. (테이블: {table_name})")

        self._list.insertItem(0, list_item)

    def _handle_local_data_changed(self, top_left, bottom_right, roles, model, table_name, table_view):
        """dataChanged(로컬 수정) 수신 → 로그 항목 추가."""
        if Qt.ItemDataRole.DisplayRole not in roles: return
        if getattr(model, '_is_processing_remote', False) or getattr(model, '_fetching', False): return
        if getattr(model, '_first_fetch', True): return

        now = datetime.now().strftime("%H:%M:%S")
        for row in range(top_left.row(), bottom_right.row() + 1):
            for col in range(top_left.column(), bottom_right.column() + 1):
                if row >= len(model._data): continue
                row_data = model._data[row]
                row_id = row_data.get("row_id", "unknown")
                col_name = model._columns[col] if col < len(model._columns) else str(col)
                item_info = row_data.get("data", {}).get(col_name, {})
                value = item_info.get("value", "")
                
                text = f"🔄 [업데이트] {table_name} / {col_name} / ID:{row_id} → {value} [local]"
                list_item = QListWidgetItem(text)
                list_item.setForeground(QColor("#fab387")) # Peach (로컬 수정 구분)
                
                self._item_meta[id(list_item)] = (table_view, row_id)
                self._list.insertItem(0, list_item)
        if not index.isValid():
            return
            
        model = table_view.model()
        source_model = getattr(model, 'sourceModel', lambda: model)()
        row_idx = index.row()
        
        if row_idx < len(source_model._data):
            current_row_id = source_model._data[row_idx].get("row_id")
            if current_row_id == row_id:
                self._fetch_cell_lineage(table_view, index)

    @Slot(QListWidgetItem)
    def _on_item_clicked(self, item: QListWidgetItem):
        """항목 클릭 → 해당 테이블 탭 전환 + 테이블뷰 포커스 + 스크롤."""
        meta = self._item_meta.get(id(item))
        if not meta: return
        
        # meta 구조: (table_view, row_id, nav_id)
        table_view, row_id, nav_id = meta
        
        # 1. 메인 윈도우 탭 전환 (nav_id가 있을 경우)
        main_win = self.parent()
        if nav_id and hasattr(main_win, "_on_navigation_requested"):
            main_win._on_navigation_requested(nav_id)
            if hasattr(main_win, "_nav_rail"):
                main_win._nav_rail.set_active(nav_id)
        
        # 2. 행 이동 및 스크롤
        model = table_view.model()
        source_model = getattr(model, 'sourceModel', lambda: model)()
        
        # row_id 기반으로 실시간 인덱스 재조회
        if hasattr(source_model, '_build_row_id_map'):
            idx_map = source_model._build_row_id_map()
            row_idx = idx_map.get(row_id)
            if row_idx is not None:
                model_index = model.mapFromSource(source_model.index(row_idx, 0)) if hasattr(model, "mapFromSource") else source_model.index(row_idx, 0)
                
                table_view.setFocus()
                # [Fix] ScrollHint 를 EnsureVisible 로 변경하여 행이 화면 중앙으로 '끌려오지' 않고 
                # 화면에 보이지 않을 때만 최소한으로 스크롤되도록 함
                table_view.scrollTo(model_index, table_view.ScrollHint.EnsureVisible)
                table_view.setCurrentIndex(model_index)
                self._fetch_cell_lineage(table_view, model_index)

    def _fetch_cell_lineage(self, table_view, index):
        """특정 셀의 전체 변경 이력을 API에서 가져와 하단에 표시합니다."""
        model = table_view.model()
        source_model = getattr(model, 'sourceModel', lambda: model)()
        
        # [핵심] 전달받은 인덱스가 프록시인 경우 소스로 변환 (정렬 대응)
        src_index = model.mapToSource(index) if hasattr(model, "mapToSource") else index
        src_row = src_index.row()
        src_col = src_index.column()
        
        if src_row >= len(source_model._data): return
        
        row_id = source_model._data[src_row].get("row_id")
        col_name = source_model._columns[src_col]
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
