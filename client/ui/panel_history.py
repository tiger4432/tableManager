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
from PySide6.QtCore import Qt, QModelIndex, Signal, Slot, QTimer
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
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        
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

        # 초기 데이터 로딩
        QTimer.singleShot(500, self.refresh_history)

    # ------------------------------------------------------------------
    # UI Helpers
    # ------------------------------------------------------------------
    def set_status(self, msg: str, timeout: int = 3000):
        """좌하단 상태바에 메시지를 표시합니다."""
        main_win = self.window()
        if hasattr(main_win, "statusBar"):
            main_win.statusBar().showMessage(msg, timeout)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh_history(self):
        """서버에서 최신 감사 로그를 가져와 히스토리 목록을 갱신합니다."""
        from models.table_model import ApiAuditLogWorker
        import config
        from PySide6.QtCore import QThreadPool
        
        # [Resilience] 이전 요청이 진행 중이면 무시
        if hasattr(self, "_is_refreshing") and self._is_refreshing:
            return
        self._is_refreshing = True

        url = config.get_audit_log_recent_url(limit=500)
        print(f"[DEBUG-History] Requesting audit logs from: {url}")
        self.set_status("🔄 최신 이력을 동기화하는 중...", 0)
        worker = ApiAuditLogWorker(url)
        
        worker.signals.finished.connect(self._on_refresh_finished)
        worker.signals.error.connect(self._on_refresh_error)
        QThreadPool.globalInstance().start(worker)

    @Slot(object)
    def _on_refresh_finished(self, logs):
        """감사 로그 로딩 완료 시 호출되는 슬롯입니다. 트랜잭션 ID 기반 그룹화를 수행합니다."""
        self._is_refreshing = False # 플래그 조기 해제
        self.set_status("✅ 히스토리 동기화 완료", 2000)

        if not isinstance(logs, list):
            print(f"[DEBUG-History] Invalid data format: {type(logs)}")
            return
            
        print(f"[DEBUG-History] SUCCESS: Received {len(logs)} logs from server.")
        self._list.clear()
        if not logs: 
            print("[DEBUG-History] No logs found on server.")
            return

        grouped_logs = []
        current_group = []
        last_tx_id = None

        for log in logs:
            tx_id = log.get("transaction_id")
            
            # 1. 트랜잭션 ID가 있고 연속되는 경우 그룹화
            if tx_id and tx_id == last_tx_id:
                current_group.append(log)
            else:
                # 새로운 그룹 시작
                if current_group:
                    grouped_logs.append(current_group)
                current_group = [log]
                last_tx_id = tx_id
        
        if current_group:
            grouped_logs.append(current_group)

        print(f"[DEBUG-History] Grouping done. Created {len(grouped_logs)} display items.")

        # 2. 리스트에 추가 (최신 요약 기준 100개로 제한)
        for group in grouped_logs[:100]:
            if len(group) > 1:
                self._add_summary_item(group)
            else:
                self._add_log_item(group[0])

    def _add_summary_item(self, group):
        """여러 개의 변경 사항을 하나의 요약 항목으로 표시합니다."""
        base_log = group[0]
        count = len(group)
        
        ts_str = self._format_timestamp(base_log.get("timestamp"))
        table_name = base_log.get("table_name", "Unknown")
        user = base_log.get("updated_by", "system")
        
        display_text = f"📦 [일괄] {table_name}: {count}건의 변경 발생 (by {user}) [{ts_str}]"
        item = QListWidgetItem(display_text)
        item.setForeground(QColor("#cba6f7")) # 보라색 강조
        
        # 대표 행(첫 번째 행)으로 내비게이션 정보 설정
        item.setData(Qt.UserRole, {
            "is_summary": True,
            "is_expanded": False,
            "group_logs": group,
            "table_name": table_name,
            "row_id": base_log.get("row_id"),
            "column_name": base_log.get("column_name"),
            "tx_id": base_log.get("transaction_id")
        })
        item.setToolTip(f"트랜잭션 ID: {base_log.get('transaction_id')}\n더블 클릭 시 상세 내역을 펼칩니다.")
        
        self._list.addItem(item)

    @Slot(QListWidgetItem)
    def _on_item_double_clicked(self, item: QListWidgetItem):
        """요약 항목 더블 클릭 시 상세 내역을 해당 행 아래에 펼치거나 닫습니다."""
        meta = item.data(Qt.UserRole)
        if not meta or not meta.get("is_summary"): return
        
        is_expanded = meta.get("is_expanded", False)
        group_logs = meta.get("group_logs", [])
        tx_id = meta.get("tx_id")
        
        current_row = self._list.row(item)
        
        if not is_expanded:
            # 펼치기 (상세 항목 삽입)
            for i, log in enumerate(group_logs):
                col = log.get("column_name", "?")
                val = log.get("new_value", "null")
                row_id = log.get("row_id", "")
                
                detail_text = f"  └─ {col}: {val} (ID:{row_id[:8]}...)"
                sub_item = QListWidgetItem(detail_text)
                sub_item.setForeground(QColor("#9399b2")) # 보조 텍스트 색상
                sub_item.setData(Qt.UserRole, {
                    "is_detail": True,
                    "parent_tx_id": tx_id,
                    "table_name": log.get("table_name"),
                    "row_id": log.get("row_id"),
                    "column_name": col
                })
                self._list.insertItem(current_row + 1 + i, sub_item)
            
            meta["is_expanded"] = True
            item.setText(item.text().replace("📦", "📂")) # 아이콘 변경
        else:
            # 접기 (상세 항목 제거)
            # 현재 행 아래부터 이 트랜잭션 ID에 속한 상세 항목들을 모두 찾아 삭제
            next_row = current_row + 1
            while next_row < self._list.count():
                next_item = self._list.item(next_row)
                n_meta = next_item.data(Qt.UserRole)
                if n_meta and n_meta.get("is_detail") and n_meta.get("parent_tx_id") == tx_id:
                    self._list.takeItem(next_row)
                else:
                    break
                    
            meta["is_expanded"] = False
            item.setText(item.text().replace("📂", "📦"))
            
        item.setData(Qt.UserRole, meta)

    def _format_timestamp(self, ts_str):
        if not ts_str: return ""
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            return ts.astimezone().strftime("%H:%M:%S")
        except: return ""

    @Slot(str)
    def _on_refresh_error(self, err_msg):
        """감사 로그 로딩 실패 시 호출되는 슬롯입니다."""
        self._is_refreshing = False # 플래그 해제
        print(f"[History] Refresh failed: {err_msg}")
        self.set_status("⚠️ 히스토리 동기화 실패", 3000)
        
        # UI에 오류 표시 (기존 항목 유지)
        if self._list.count() == 0:
            item = QListWidgetItem("⚠️ 히스토리 로딩 실패 (서버 연결 확인)")
            item.setForeground(QColor("#f38ba8"))
            self._list.addItem(item)

    def _add_log_item(self, log):
        """감사 로그 항목 하나를 리스트에 시각화하여 추가합니다."""
        ts_str = self._format_timestamp(log.get("timestamp", ""))

        table_name = log.get("table_name", "Unknown")
        col_name = log.get("column_name", "")
        row_id = log.get("row_id", "")
        source = log.get("source_name", "system")
        user = log.get("updated_by", "system")
        
        icon = "🔄"
        color = "#89dceb" # 하늘색
        
        if col_name == "CREATE":
            msg = f"🆕 [신규] {table_name}: 행 생성 (by {user})"
            color = "#a6e3a1" # 녹색
        elif col_name == "DELETE":
            msg = f"🗑️ [삭제] {table_name}: 행 삭제 (by {user})"
            color = "#f38ba8" # 빨간색
        else:
            # 일반 셀 수정
            msg = f"🔄 [{table_name}] {col_name} 변경 (by {user} / {source})"
            if source == "user": 
                color = "#f9e2af" # 노란색 (수동 수정 강조)
            elif "batch" in source:
                color = "#cba6f7" # 보라색 (배치 작업)

        display_text = f"{msg} [{ts_str}]"
        item = QListWidgetItem(display_text)
        item.setForeground(QColor(color))
        
        # 내비게이션용 메타데이터 저장
        item.setData(Qt.UserRole, {
            "table_name": table_name,
            "row_id": row_id,
            "column_name": col_name if col_name not in ["CREATE", "DELETE"] else None
        })
        
        if row_id and row_id != "_BATCH_":
            item.setToolTip(f"ID:{row_id}\n클릭 시 해당 위치로 이동합니다.")
        
        self._list.addItem(item)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log_event(self, data: dict):
        """
        실시간 이벤트 수신 시 리스트를 갱신합니다.
        잦은 업데이트 폭주를 막기 위해 300ms 디바운싱을 적용합니다.
        """
        # [Debounce] 기존 대기 타이머가 있다면 취소하고 새로 시작
        if hasattr(self, "_refresh_debounce_timer"):
            self._refresh_debounce_timer.stop()
        else:
            from PySide6.QtCore import QTimer
            self._refresh_debounce_timer = QTimer()
            self._refresh_debounce_timer.setSingleShot(True)
            self._refresh_debounce_timer.timeout.connect(self.refresh_history)
            
        self._refresh_debounce_timer.start(300)
        print(f"[DEBUG-History] debouncing refresh... (event: {data.get('event')})")

    @Slot(QListWidgetItem)
    def _on_item_clicked(self, item: QListWidgetItem):
        """히스토리 항목 클릭 시 해당 테이블/행으로 이동합니다."""
        meta = item.data(Qt.UserRole)
        if not meta: return
        
        row_id = meta.get("row_id")
        table_name = meta.get("table_name")
        print(f"[DEBUG-Nav] Clicked: {table_name} | {row_id}")

        # [Resilience] 과도한 연타로 인한 스레드 충돌 방지 (Navigation Guard)
        if getattr(self, "_is_navigating", False):
            print("[History] Navigation in progress... ignoring click.")
            return
            
        meta = item.data(Qt.UserRole)
        if not meta: return
        
        # 요약(Summary) 행인 경우 단일 클릭 내비게이션 무시 (더블 클릭 확장 전용)
        if meta.get("is_summary"):
            return
        
        self._is_navigating = True
        self.set_status("🔍 데이터 위치를 탐색 중...", 0)
        # 3초 뒤 강제 해제 (최악의 경우라도 추적 기능이 먹통되지 않게 방어)
        QTimer.singleShot(3000, lambda: setattr(self, "_is_navigating", False))
            
        table_name = meta.get("table_name")
        row_id = meta.get("row_id")
        column_name = meta.get("column_name")
        nav_id = f"table:{table_name}"
        
        # 1. 메인 윈도우 확보 (사이드바 메뉴 클릭 시와 동일한 창 컨텍스트 확보)
        main_win = self.window()
        if not hasattr(main_win, "stacked"):
            return

        # 2. 탭이 열려있지 않으면 자동 오픈 시도
        if nav_id not in main_win._nav_to_index:
            if hasattr(main_win, "_init_table_tab"):
                print(f"[History] Opening closed table tab: {table_name}")
                main_win._init_table_tab(table_name)
            else: 
                self._is_navigating = False
                return

        # 3. 탭 전환 (동기 호출)
        if hasattr(main_win, "_on_navigation_requested"):
            main_win._on_navigation_requested(nav_id)
            if hasattr(main_win, "_nav_rail"):
                main_win._nav_rail.set_active(nav_id)
        
        # 4. 레이아웃 안정화를 위해 미세 지연 후 실행 (Deferred Action)
        # 탭 전환 직후에는 뷰포트가 아직 갱신되지 않았을 수 있으므로 QTimer 사용
        def _deferred_scroll():
            idx = main_win._nav_to_index.get(nav_id)
            if idx is None: 
                self._is_navigating = False
                return
            page_widget = main_win.stacked.widget(idx)
            
            # [Fix] 클래스 객체 ID 불일치 가능성 차단을 위해 objectName("table_view")으로 탐색
            table_view = page_widget.findChild(QWidget, "table_view")
            if not table_view: 
                self._is_navigating = False
                self.set_status("⚠️ 테이블 뷰를 찾을 수 없습니다.", 3000)
                return
            
            model = table_view.model()
            source_model = getattr(model, 'sourceModel', lambda: model)()
            
            def _scroll_to_index(row_idx):
                # 열 인덴스 결정
                col_idx = 0
                if column_name and column_name in source_model._columns:
                    col_idx = source_model._columns.index(column_name)
                
                # 시각적 인덱스 변환 (프록시 대응)
                model_index = model.mapFromSource(source_model.index(row_idx, col_idx)) if hasattr(model, "mapFromSource") else source_model.index(row_idx, col_idx)
                
                if model_index.isValid():
                    table_view.setFocus()
                    table_view.scrollTo(model_index, table_view.ScrollHint.EnsureVisible)
                    table_view.setCurrentIndex(model_index)
                    self._fetch_cell_lineage(table_view, model_index)

            # ── 1단계: 로컬 메모리 스캔 ──
            idx_map = source_model._build_row_id_map()
            row_idx = idx_map.get(row_id)
            
            if row_idx is not None:
                _scroll_to_index(row_idx)
                self.set_status(f"🎯 {table_name} 이동 완료", 2000)
                self._is_navigating = False
            else:
                # ── 2단계: 서버 기반 위치 역조회 (Deep Discovery) ──
                print(f"[History] Row {row_id} not in memory. Requesting server offset...")
                from models.table_model import ApiRowIndexDiscoveryWorker
                import config
                from PySide6.QtCore import QThreadPool
                
                discovery_url = config.get_row_index_discovery_url(table_name, row_id)
                worker = ApiRowIndexDiscoveryWorker(
                    discovery_url, 
                    q=source_model._search_query,
                    order_by="updated_at" if source_model._sort_latest else "id",
                    order_desc=source_model._sort_latest, # updated_at은 desc, id(BK)는 asc
                    cols=source_model._search_cols
                )
                
                # [Fix] 클로저/파셜 GC 유실 방지: 정보를 멤버 변수에 저장하고 클래스 메서드 직접 연결
                self._current_nav_ctx = {
                    "row_id": row_id,
                    "table_name": table_name,
                    "column_name": column_name,
                    "source_model": source_model,
                    "table_view": table_view,
                    "model": model
                }
                
                worker.signals.finished.connect(self._handle_discovery_result)
                worker.signals.error.connect(lambda err: print(f"[DEBUG-Nav] Discovery WORKER ERROR: {err}"))
                
                print(f"[DEBUG-Nav] Dispatching Discovery Worker to ThreadPool: {discovery_url}")
                QThreadPool.globalInstance().start(worker)
            
        QTimer.singleShot(100, _deferred_scroll) # 100ms 지연으로 충분한 안정기 확보

    def _handle_discovery_result(self, result: dict):
        """서버 검색 결과를 처리하여 최종 위치로 점프합니다."""
        # 저장된 컨텍스트 복원
        ctx = getattr(self, "_current_nav_ctx", None)
        if not ctx: 
            print("[DEBUG-Nav] Error: Navigation context lost!")
            self._is_navigating = False
            return
            
        row_id = ctx["row_id"]
        table_name = ctx["table_name"]
        column_name = ctx["column_name"]
        source_model = ctx["source_model"]
        table_view = ctx["table_view"]
        model = ctx["model"]

        target_offset = result.get("index", -1)
        print(f"[DEBUG-Nav] Discovery result for {row_id}: index={target_offset}")
        
        if target_offset >= 0:
            chunk_size = source_model._chunk_size
            skip = (target_offset // chunk_size) * chunk_size
            print(f"[DEBUG-Nav] Jumping to skip={skip} (Offset {target_offset}) using chunk_size={chunk_size}")
            
            source_model._pending_target_skip = skip
            source_model.fetchMore()
            
            # 최종 스크롤 이동 함수 정의
            def _final_scroll(target_row_idx):
                col_idx = 0
                if column_name and column_name in source_model._columns:
                    col_idx = source_model._columns.index(column_name)
                
                m_idx = model.mapFromSource(source_model.index(target_row_idx, col_idx)) if hasattr(model, "mapFromSource") else source_model.index(target_row_idx, col_idx)
                if m_idx.isValid():
                    table_view.setFocus()
                    table_view.scrollTo(m_idx, table_view.ScrollHint.EnsureVisible)
                    table_view.setCurrentIndex(m_idx)

            # 데이터 로딩 시간을 고려하여 최종 스캔 및 스크롤
            def _final_hop():
                new_map = source_model._build_row_id_map()
                final_idx = new_map.get(row_id)
                print(f"[DEBUG-Nav] Final hop search: {row_id} -> {final_idx}")
                
                if final_idx is not None:
                    _final_scroll(final_idx)
                    self.set_status(f"🎯 {table_name} 이동 완료", 2000)
                else:
                    print(f"[DEBUG-Nav] FAILED to find row in map after jump. Available row count: {len(new_map)}")
                    from PySide6.QtWidgets import QMessageBox
                    QMessageBox.information(self, "위치 확인 중", 
                        "데이터 로딩이 늦어지고 있습니다.\n잠시 후 다시 시도하거나 검색 조건을 확인해 주세요.")
                self._is_navigating = False
            
            QTimer.singleShot(700, _final_hop)
        else:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "이동 실패", 
                "해당 행을 찾을 수 없습니다.\n이미 삭제되었거나 현재 필터링/검색 조건에 해당하지 않습니다.")
            print(f"[DEBUG-Nav] Row {row_id} discovery failed or row deleted.")
            self._is_navigating = False

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
        import config
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
            item = QListWidgetItem(text)
            self._lineage_list.addItem(item)
