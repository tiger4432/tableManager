from __future__ import annotations
from datetime import datetime
import time
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
        # 100 그룹 서버에서 지정
        url = config.get_audit_log_recent_url()
        worker = ApiAuditLogWorker(url)
        worker.signals.finished.connect(self._on_fetch_finished)
        worker.signals.error.connect(self._on_fetch_error)
        QThreadPool.globalInstance().start(worker)

    def log_event(self, data: dict):
        """실시간 이벤트를 수신하여 디바운싱 처리합니다."""
        self._refresh_debounce_timer.start(300)

    @Slot(object)
    def _on_fetch_finished(self, grouped_logs):
        self._is_refreshing = False
        if not isinstance(grouped_logs, list):
            self.syncError.emit("Invalid log format")
            return

        # 서버(AuditLogCache)에서 이미 transaction_id 단위로 그룹화되어 내려옴
        grouped_results = []
        for group in grouped_logs:
            logs = group.get("logs", [])
            if logs:
                grouped_results.append(HistoryItemData(logs))

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
        
        # [Task] 배치 작업(_BATCH_)은 개별 탐색이 불가능하므로 즉시 차단
        if data.row_id == "_BATCH_":
            self.statusRequested.emit("⚠️ 배치 작업 이력은 개별 이동을 지원하지 않습니다.", 3000)
            return
            
        self._is_navigating = True
        self.statusRequested.emit("🔍 데이터 위치를 탐색 중...", 0)
        
        # [Fix] 여러 번 클릭 시 누적된 singleShot 타이머가 새로운 탐색을 방해하지 않도록 전용 타이머 사용
        if not hasattr(self, '_guard_timer'):
            self._guard_timer = QTimer(self)
            self._guard_timer.setSingleShot(True)
            self._guard_timer.timeout.connect(self._release_guard)
        
        self._guard_timer.start(10000) # 10초 타임아웃
        
        # 컨텍스트 초기화
        main_win = parent_widget.window()
        self._ctx = {
            "data_obj": data,
            "row_id": data.row_id,
            "table_name": data.table_name,
            "column_name": data.column_name,
            "nav_id": f"table:{data.table_name}",
            "main_win": main_win,
            "parent_widget": parent_widget,
            "start_time": time.time() # [Perf] 시퀀스 시작점 기록
        }

        # 1. 탭 자동 오픈 및 전환
        nav_id = self._ctx["nav_id"]
        table_name = self._ctx["table_name"]
        
        if not hasattr(main_win, "stacked"):
            self._release_guard()
            return

        if nav_id not in main_win._nav_to_index:
            if hasattr(main_win, "_init_table_tab"):
                main_win._init_table_tab(table_name, first_fetch = False)
                print(f"[Nav] Step 1 (Tab Create) took {(time.time() - self._ctx['start_time'])*1000:.2f}ms")
            else:
                self._release_guard()
                return
        else:
            print(f"[Nav] Step 1 (Tab Switch) took {(time.time() - self._ctx['start_time'])*1000:.2f}ms")

        if hasattr(main_win, "_on_navigation_requested"):
            main_win._on_navigation_requested(nav_id)
            if hasattr(main_win, "_nav_rail"):
                main_win._nav_rail.set_active(nav_id)

        # 2. 레이아웃 안정화 대기 (Task 2: Qt 이벤트 큐 기반 대기)
        QTimer.singleShot(0, self._step2_deferred_execute)

    @Slot()
    def _release_guard(self):
        print(f"[Nav] _release_guard called. (is_navigating={self._is_navigating})")
        if hasattr(self, '_guard_timer') and self._guard_timer.isActive():
            self._guard_timer.stop()
            
        self._is_navigating = False
        try:
            if "source_model" in self._ctx:
                self._ctx["source_model"].fetch_finished.disconnect(self._step4_final_hop)
        except Exception:
            pass

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
        
        print(f"[Nav] Step 2 (Layout & Viewport Ready) took {(time.time() - self._ctx['start_time'])*1000:.2f}ms")

        model = table_view.model()
        source_model = getattr(model, 'sourceModel', lambda: model)()
        
        self._ctx.update({"table_view": table_view, "model": model, "source_model": source_model})

        # 로컬 검색 시도
        idx_map = source_model._build_row_id_map()
        row_idx = idx_map.get(self._ctx["row_id"])
        
        # [Fix] row_idx가 존재하더라도 현재 UI 노출 범위(_exposed_rows) 밖이면 서버 점프(fetch)를 통해 뷰포트 확장 필요
        exposed_limit = getattr(source_model, '_exposed_rows', float('inf'))
        if row_idx is not None and row_idx < exposed_limit:
            if self._final_scroll(row_idx):
                self.statusRequested.emit(f"🎯 {self._ctx['table_name']} 이동 완료", 2000)
                self._release_guard()
        else:
            # [Task 3] Qt의 자동 fetchMore와 충돌을 막기 위해 SingleShot 대신 일반 연결 사용
            # 중복 연결 방지를 위해 UniqueConnection 사용
            from PySide6.QtCore import Qt
            try: source_model.fetch_finished.connect(self._step4_final_hop, Qt.ConnectionType.UniqueConnection)
            except RuntimeError: pass # 이미 연결되어 있는 경우
            source_model.jump_to_id(self._ctx["row_id"])

    @Slot()
    def _step4_final_hop(self):
        print(f"[Nav] _step4_final_hop called. _is_navigating={self._is_navigating}")
        if not self._is_navigating: return
        
        source_model = self._ctx["source_model"]
        
        # [Fix] 탭이 처음 열리면서 호출된 '일반 페칭'이 먼저 끝나버리면, 
        # 점프 데이터가 없는데도 이 콜백이 실행되어 Abort 되는 문제를 막기 위함
        active_ctx = getattr(source_model, '_active_fetch_ctx', None)
        if active_ctx is None or active_ctx.source != "jump":
            print(f"[Nav] Ignoring fetch_finished because it was a NORMAL fetch. Waiting for JUMP fetch.")
            return
        new_map = source_model._build_row_id_map()
        row_id = self._ctx["row_id"]
        final_idx = new_map.get(row_id)
        
        print(f"[Nav] final_idx for {row_id} is {final_idx}. _fetching={getattr(source_model, '_fetching', True)}")
        
        if final_idx is not None:
            try: source_model.fetch_finished.disconnect(self._step4_final_hop)
            except Exception: pass
            
            if self._final_scroll(final_idx):
                self.statusRequested.emit(f"🎯 {self._ctx['table_name']} 이동 완료", 2000)
                self._release_guard()
        else:
            if not getattr(source_model, '_fetching', True):
                # 모든 페칭이 끝났는데도 타겟이 없다면 (삭제되었거나 필터링됨)
                print(f"[Nav] Fetching finished but target not found! Aborting.")
                try: source_model.fetch_finished.disconnect(self._step4_final_hop)
                except Exception: pass
                
                # [Task 1] 서버 검색 필터에 의해 대상이 누락되었을 가능성이 있다면 필터 해제 후 재시도
                if getattr(source_model, "_search_query", ""):
                    print("[Nav] Target not found, but search filter is active. Clearing filter and retrying.")
                    self.statusRequested.emit("⚠️ 검색 필터 해제 후 재탐색...", 2000)
                    main_win = self._ctx["main_win"]
                    if hasattr(main_win, "_filter_bar"):
                        main_win._filter_bar._search_box.clear()
                        # 락 해제 후 지연 재호출
                        data_obj = self._ctx["data_obj"]
                        parent_widget = self._ctx["parent_widget"]
                        self._release_guard()
                        QTimer.singleShot(600, lambda d=data_obj, p=parent_widget: self.navigate_to_log(d, p))
                        return
                else:
                    self.statusRequested.emit("❌ 데이터를 찾을 수 없습니다. (삭제 등)", 3000)
                    main_win = self._ctx["main_win"]
                    from PySide6.QtWidgets import QMessageBox
                    QMessageBox.warning(main_win, "데이터 이동 불가", "해당 데이터를 찾을 수 없습니다.\n이미 삭제된 데이터일 수 있습니다.")
                self._release_guard()
            else:
                print(f"[Nav] target not found, but _fetching is True. Waiting for next fetch.")

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
            
            total_duration = (time.time() - self._ctx.get("start_time", time.time())) * 1000
            print(f"[Nav] Step 4 (Data Load & Scroll) took {(time.time() - self._ctx.get('fetch_start', time.time()))*1000:.2f}ms")
            print(f">>> [Nav] SUCCESS: Total Navigation took {total_duration:.2f}ms")

            # Lineage 조회는 UI에서 처리하도록 시그널이나 콜백 필요할 수 있음
            if hasattr(ctx["parent_widget"], "_fetch_cell_lineage"):
                ctx["parent_widget"]._fetch_cell_lineage(table_view, m_idx)
            return True
        else:
            # [Task 1] 로컬 ProxyModel 필터 등에 의해 숨겨진 경우 필터 해제 후 재시도
            print("[Nav] Target found in source, but m_idx is invalid. Clearing filter and retrying.")
            self.statusRequested.emit("⚠️ 숨겨진 데이터입니다. 필터 해제 후 재탐색...", 2000)
            main_win = ctx["main_win"]
            if hasattr(main_win, "_filter_bar"):
                # [Fix] 무한 루프 방지: 검색어가 이미 비어있다면, 필터 때문이 아니라 삭제/중복 상태이므로 즉시 중단
                current_text = main_win._filter_bar._search_box.text()
                if not current_text:
                    print("[Nav] Search box is already empty! Aborting to prevent infinite loop.")
                    self.statusRequested.emit("❌ 데이터를 표시할 수 없습니다 (삭제되거나 유효하지 않음).", 3000)
                    from PySide6.QtWidgets import QMessageBox
                    QMessageBox.warning(main_win, "데이터 이동 불가", "해당 데이터를 표시할 수 없습니다.\n이미 삭제되었거나 필터링 조건에 의해 숨겨진 데이터입니다.")
                    self._release_guard()
                    return False
                    
                main_win._filter_bar._search_box.clear()
                
                data_obj = ctx["data_obj"]
                parent_widget = ctx["parent_widget"]
                self._release_guard()
                QTimer.singleShot(600, lambda d=data_obj, p=parent_widget: self.navigate_to_log(d, p))
            return False
