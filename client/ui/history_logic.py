from __future__ import annotations
from datetime import datetime
from PySide6.QtCore import QObject, Signal, Slot, QTimer, QThreadPool, Qt
from PySide6.QtGui import QColor

class HistoryItemData:
    """감사 로그 항목 하나 또는 그룹을 나타내는 데이터 객체."""
    def __init__(self, logs: list[dict]):
        self.logs = logs
        self.is_summary = len(logs) > 1
        self.is_expanded = False
        
        # 대표 데이터 (첫 번째 로그)
        base = logs[0]
        self.table_name = base.get("table_name", "Unknown")
        self.row_id = base.get("row_id", "")
        self.column_name = base.get("column_name", "")
        self.updated_by = base.get("updated_by", "system")
        self.timestamp = base.get("timestamp", "")
        self.tx_id = base.get("transaction_id")
        self.source = base.get("source_name", "system")

    def get_display_text(self) -> str:
        ts_str = self.format_timestamp(self.timestamp)
        user = self.updated_by or "system"
        if self.is_summary:
            # 요약행: 작업자, 테이블, 건수를 강조
            return f"📦 [{user}] 님 | {self.table_name} | {len(self.logs)}건 변경 [{ts_str}]"
        
        col = self.column_name
        if col == "CREATE":
            return f"🆕 [{user}] 님이 {self.table_name} (ID:{self.row_id[:8]}) 생성 [{ts_str}]"
        elif col == "DELETE":
            return f"🗑️ [{user}] 님이 {self.table_name} (ID:{self.row_id[:8]}) 삭제 [{ts_str}]"
        elif col == "ROW_UPDATE":
            return f"🤖 [{user}] 님 | {self.table_name} 데이터 자동 업데이트 [{ts_str}]"
        else:
            return f"🔄 [{user}] 님 | {self.table_name}.{col} 수정 [{ts_str}]"

    def get_color(self) -> str:
        if self.is_summary: return "#cba6f7" # 보라색 (일괄/트랜잭션)
        col = self.column_name
        if col == "CREATE": return "#a6e3a1" # 녹색
        if col == "DELETE": return "#f38ba8" # 빨간색
        if col == "ROW_UPDATE": return "#89dceb" # 청록색 (자동 업데이트 요약)
        if self.source == "user": return "#f9e2af" # 노란색 (사용자 직접 수정)
        return "#fab387" # 주황색 (기타 파서 수정)

    @staticmethod
    def format_timestamp(ts_str):
        if not ts_str: return ""
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            return ts.astimezone().strftime("%H:%M:%S")
        except: return ""

class HistoryDataManager(QObject):
    """서버 통신 및 히스토리 데이터 가공을 담당하는 클래스."""
    logsReady = Signal(list) # list[HistoryItemData]
    syncError = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_refreshing = False
        self._refresh_debounce_timer = QTimer(self)
        self._refresh_debounce_timer.setSingleShot(True)
        self._refresh_debounce_timer.timeout.connect(self.refresh_history)

    def refresh_history(self):
        if self._is_refreshing: return
        self._is_refreshing = True
        
        import config
        from models.table_model import ApiAuditLogWorker
        # 100개 그룹을 충분히 확보하기 위해 원본 로그는 5,000건까지 조회합니다.
        url = config.get_audit_log_recent_url(limit=5000)
        worker = ApiAuditLogWorker(url)
        worker.signals.finished.connect(self._on_fetch_finished)
        worker.signals.error.connect(self._on_fetch_error)
        QThreadPool.globalInstance().start(worker)

    def log_event(self, data: dict):
        """실시간 이벤트를 수신하여 디바운싱 처리합니다."""
        self._refresh_debounce_timer.start(300)

    @Slot(object)
    def _on_fetch_finished(self, logs):
        self._is_refreshing = False
        if not isinstance(logs, list):
            self.syncError.emit("Invalid log format")
            return

        # ── 하이테크 그룹화 로직 (Transaction ID 기반) ──
        grouped_results = []
        current_group = []
        last_tx_id = None
        group_count = 0

        for log in logs:
            tx_id = log.get("transaction_id")
            
            # 새 그룹 시작 조건: tx_id 가 달라지거나, tx_id 가 없는 단건일 때
            if not tx_id or tx_id != last_tx_id:
                if current_group:
                    grouped_results.append(HistoryItemData(current_group))
                    group_count += 1
                    if group_count >= 100: break # 최대 100그룹 도달 시 조기 종료
                
                current_group = [log]
                last_tx_id = tx_id
            else:
                # 동일 트랜잭션 내 데이터는 계속 누적
                current_group.append(log)
        
        # 마지막 잔여 그룹 처리 (100개 미만일 경우)
        if current_group and group_count < 100:
            grouped_results.append(HistoryItemData(current_group))

        self.logsReady.emit(grouped_results)


    @Slot(str)
    def _on_fetch_error(self, err_msg):
        self._is_refreshing = False
        self.syncError.emit(err_msg)

class HistoryNavigator(QObject):
    """4단계 위치 탐색 시퀀스를 관리하는 클래스."""
    statusRequested = Signal(str, int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_navigating = False
        self._ctx = {}

    def navigate_to_log(self, data: HistoryItemData, parent_widget):
        if self._is_navigating or data.is_summary: return
        
        self._is_navigating = True
        self.statusRequested.emit("🔍 데이터 위치를 탐색 중...", 0)
        
        # 3초 뒤 강제 해제 (안전장치)
        QTimer.singleShot(3000, self._release_guard)
        
        # 컨텍스트 초기화
        main_win = parent_widget.window()
        self._ctx = {
            "row_id": data.row_id,
            "table_name": data.table_name,
            "column_name": data.column_name,
            "nav_id": f"table:{data.table_name}",
            "main_win": main_win,
            "parent_widget": parent_widget
        }

        # 1. 탭 자동 오픈 및 전환
        nav_id = self._ctx["nav_id"]
        table_name = self._ctx["table_name"]
        
        if not hasattr(main_win, "stacked"):
            self._release_guard()
            return

        if nav_id not in main_win._nav_to_index:
            if hasattr(main_win, "_init_table_tab"):
                main_win._init_table_tab(table_name)
            else:
                self._release_guard()
                return

        if hasattr(main_win, "_on_navigation_requested"):
            main_win._on_navigation_requested(nav_id)
            if hasattr(main_win, "_nav_rail"):
                main_win._nav_rail.set_active(nav_id)

        # 2. 레이아웃 안정화 대기
        QTimer.singleShot(100, self._step2_deferred_execute)

    @Slot()
    def _release_guard(self):
        self._is_navigating = False

    @Slot()
    def _step2_deferred_execute(self):
        main_win = self._ctx["main_win"]
        nav_id = self._ctx["nav_id"]
        idx = main_win._nav_to_index.get(nav_id)
        if idx is None: 
            self._release_guard()
            return

        page_widget = main_win.stacked.widget(idx)
        from PySide6.QtWidgets import QWidget
        table_view = page_widget.findChild(QWidget, "table_view")
        if not table_view:
            self.statusRequested.emit("⚠️ 테이블 뷰를 찾을 수 없습니다.", 3000)
            self._release_guard()
            return

        model = table_view.model()
        source_model = getattr(model, 'sourceModel', lambda: model)()
        
        self._ctx.update({"table_view": table_view, "model": model, "source_model": source_model})

        # 로컬 검색 시도
        idx_map = source_model._build_row_id_map()
        row_idx = idx_map.get(self._ctx["row_id"])
        
        if row_idx is not None:
            self._final_scroll(row_idx)
            self.statusRequested.emit(f"🎯 {self._ctx['table_name']} 이동 완료", 2000)
            self._release_guard()
        else:
            # 3. 서버 역조회
            self._step3_request_discovery()

    def _step3_request_discovery(self):
        from models.table_model import ApiRowIndexDiscoveryWorker
        import config
        source_model = self._ctx["source_model"]
        url = config.get_row_index_discovery_url(self._ctx["table_name"], self._ctx["row_id"])
        
        worker = ApiRowIndexDiscoveryWorker(
            url, 
            q=source_model._search_query,
            order_by="updated_at" if source_model._sort_latest else "id",
            order_desc=source_model._sort_latest,
            cols=source_model._search_cols
        )
        worker.signals.finished.connect(self._on_discovery_finished)
        worker.signals.error.connect(lambda e: self._release_guard()) # 간단한 로깅
        QThreadPool.globalInstance().start(worker)

    @Slot(dict)
    def _on_discovery_finished(self, result):
        target_offset = result.get("index", -1)
        if target_offset >= 0:
            source_model = self._ctx["source_model"]
            chunk_size = source_model._chunk_size
            skip = (target_offset // chunk_size) * chunk_size
            
            source_model._pending_target_skip = skip
            
            # 4. 최종 점프: 타이머 대신 fetch_finished 시그널에 즉시 응답 (SingleShot)
            source_model.fetch_finished.connect(self._step4_final_hop, Qt.ConnectionType.SingleShotConnection)
            source_model.fetchMore()
        else:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self._ctx["parent_widget"], "이동 실패", "행을 찾을 수 없습니다.")
            self._release_guard()

    @Slot()
    def _step4_final_hop(self):
        source_model = self._ctx["source_model"]
        new_map = source_model._build_row_id_map()
        row_id = self._ctx["row_id"]
        final_idx = new_map.get(row_id)
        
        if final_idx is not None:
            self._final_scroll(final_idx)
            self.statusRequested.emit(f"🎯 {self._ctx['table_name']} 이동 완료", 2000)
        else:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self._ctx["parent_widget"], "알림", "데이터 로딩 대기 중...")
        self._release_guard()

    def _final_scroll(self, row_idx):
        ctx = self._ctx
        table_view = ctx["table_view"]
        model = ctx["model"]
        source_model = ctx["source_model"]
        column_name = ctx["column_name"]
        
        col_idx = 0
        if column_name and column_name in source_model._columns:
            col_idx = source_model._columns.index(column_name)
            
        m_idx = model.mapFromSource(source_model.index(row_idx, col_idx)) if hasattr(model, "mapFromSource") else source_model.index(row_idx, col_idx)
        
        if m_idx.isValid():
            table_view.setFocus()
            table_view.scrollTo(m_idx, table_view.ScrollHint.EnsureVisible)
            table_view.setCurrentIndex(m_idx)
            # Lineage 조회는 UI에서 처리하도록 시그널이나 콜백 필요할 수 있음
            if hasattr(ctx["parent_widget"], "_fetch_cell_lineage"):
                ctx["parent_widget"]._fetch_cell_lineage(table_view, m_idx)
