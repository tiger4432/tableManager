import config
import os
import time
import uuid
from datetime import datetime
from PySide6.QtCore import QAbstractTableModel, Qt, QModelIndex, QRunnable, QThreadPool, Signal, Slot, QObject, QPersistentModelIndex, QThread, QTimer

class WorkerSignals(QObject):
    finished = Signal(object)
    error = Signal(str)

class BaseApiWorker(QRunnable):
    """중복되는 API 요청 로직을 처리하는 베이스 워커 클래스."""
    def __init__(self, url: str, method: str = "GET", payload: dict = None, headers: dict = None):
        super().__init__()
        self.url = url
        self.method = method
        self.payload = payload
        self.headers = headers or {}
        self.signals = WorkerSignals()

    def run(self):
        import urllib.request
        import json
        try:
            data = None
            if self.payload:
                data = json.dumps(self.payload).encode("utf-8")
                if "Content-Type" not in self.headers:
                    self.headers["Content-Type"] = "application/json"
            
            req = urllib.request.Request(self.url, data=data, method=self.method, headers=self.headers)
            with urllib.request.urlopen(req, timeout=10.0) as response:
                raw = response.read().decode("utf-8")
                result = json.loads(raw)
                self.handle_result(result)
        except Exception as e:
            try: self.signals.error.emit(str(e))
            except RuntimeError: pass

    def handle_result(self, result):
        try: self.signals.finished.emit(result)
        except RuntimeError: pass

class ApiFetchWorker(BaseApiWorker):
    """세션 관리가 포함된 데이터 페칭 워커."""
    def __init__(self, url, session_id: str = ""):
        super().__init__(url)
        self.session_id = session_id

    def handle_result(self, result):
        if isinstance(result, dict):
            result["_session_id"] = self.session_id
        super().handle_result(result)

class ApiSchemaWorker(BaseApiWorker):
    """테이블 스키마 전용 워커."""
    pass

class ApiGeneralUpdateWorker(BaseApiWorker):
    """데이터 업데이트(PUT) 전용 워커."""
    def __init__(self, url: str, updates: list[dict]):
        super().__init__(url, method="PUT", payload={"updates": updates})

class ApiUploadWorker(QRunnable):
    """외부 라이브러리(httpx)를 사용하므로 베이스 클래스에서 예외 적용."""
    def __init__(self, url, file_path):
        super().__init__()
        self.url = url
        self.file_path = file_path
        self.signals = WorkerSignals()

    def run(self):
        import httpx
        import os
        try:
            filename = os.path.basename(self.file_path)
            with open(self.file_path, "rb") as f:
                with httpx.Client(timeout=30.0) as client:
                    response = client.post(self.url, files={"file": (filename, f)})
                    if response.status_code == 200:
                        self.signals.finished.emit(response.json())
                    else:
                        self.signals.error.emit(f"Server error: {response.status_code}")
        except Exception as e:
            self.signals.error.emit(str(e))

class ApiTargetedRowIdWorker(BaseApiWorker):
    """특정 오프셋의 UUID 추출 워커."""
    def __init__(self, url: str, offsets: list[int], search_query: str = "", order_by: str = "updated_at", order_desc: bool = True, session_id: str = "", cols: str = ""):
        payload = {
            "offsets": offsets, "q": search_query, "cols": cols,
            "order_by": order_by, "order_desc": order_desc
        }
        super().__init__(url, method="POST", payload=payload)
        self.session_id = session_id

    def handle_result(self, result):
        if isinstance(result, dict):
            result["_session_id"] = self.session_id
        super().handle_result(result)

class ApiRowIndexDiscoveryWorker(BaseApiWorker):
    """로그 위치 역조회 디스커버리 워커."""
    def __init__(self, url: str, q: str = "", order_by: str = "row_id", order_desc: bool = False, cols: str = ""):
        payload = {"q": q, "cols": cols, "order_by": order_by, "order_desc": order_desc}
        super().__init__(url, method="POST", payload=payload)

class ApiAuditLogWorker(BaseApiWorker):
    """히스토리 로그 전용 워커."""
    pass

class WsListenerThread(QThread):
    message_received = Signal(dict)
    connection_error = Signal(str)

    def __init__(self, ws_url: str = config.WS_BASE_URL, parent=None):
        super().__init__(parent)
        self.ws_url = ws_url
        self._running = True
        self._ws = None

    def run(self):
        import json
        try:
            from websockets.sync.client import connect
        except ImportError:
            self.connection_error.emit("websockets 패키지가 설치되지 않았습니다.")
            return

        while self._running:
            try:
                with connect(self.ws_url, open_timeout=5.0, max_size=100 * 1024 * 1024) as ws:
                    self._ws = ws
                    while self._running:
                        try:
                            raw = ws.recv(timeout=1.0)
                            data = json.loads(raw)
                            self.message_received.emit(data)
                        except TimeoutError:
                            continue
                        except Exception:
                            break
            except Exception as e:
                if self._running:
                    self.connection_error.emit(str(e))
                    self.msleep(3000)
            finally:
                self._ws = None

    def stop(self):
        self._running = False
        if self._ws:
            try: self._ws.close()
            except: pass
        self.quit()
        self.wait()

class ApiDeleteWorker(QRunnable):
    def __init__(self, url, row_ids, user_name="system"):
        super().__init__()
        self.url = url
        self.row_ids = row_ids
        self.user_name = user_name
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            import urllib.request
            import json
            payload = {"row_ids": self.row_ids, "user_name": self.user_name}
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(self.url, data=data, method="POST")
            req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode("utf-8"))
                self.signals.finished.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))

class ApiLazyTableModel(QAbstractTableModel):
    total_count_changed = Signal(int, int) # (exposed_rows, total_count)
    batch_fetch_finished = Signal()
    fetch_finished = Signal() # [신규] 모든 종류의 fetchMore 완료 시 알림
    status_message_requested = Signal(str) # [신규] 상태바 메시지 요청 시그널

    def __init__(self, table_name: str, base_api_url: str = config.API_BASE_URL):
        super().__init__()
        self.table_name = table_name
        self.base_api_url = base_api_url
        self.endpoint_url = config.get_table_data_url(table_name)
        self._data = []
        self._total_count = 0
        self._columns = []
        self._chunk_size = 1000
        self._fetching = False
        self._batch_fetching = False # [Phase 73.10] 일괄 로딩 추적 플래그
        self._fetch_scheduled = False
        self._first_fetch = True
        self._is_processing_remote = False
        self._fetching_row_ids = set()
        self._sort_latest = True
        self._server_fetched_count = 0
        self._search_query = ""
        self._search_cols = ""        # [Phase 73.7] 서버 전송용 컬럼 문자열
        self._search_cols_state = []  # [Phase 73.8] UI 체크박스 상태 보존용 리스트
        self._exposed_rows = 0        # [신규] 실제로 UI에 노출된 행 수
        
        self._row_id_map = {}
        self._pending_target_skip = None # [신규] 특정 오프셋 점프 예약용
        self._stale_fetch_tracker = {}
        
        # [Phase 73.5] 검색 세션 ID 도입 - 고속 타이핑 시 이전 검색 결과 오염 방지
        self._search_session_id = str(uuid.uuid4())
        
        self._recovery_timer = QTimer(self)
        self._recovery_timer.setInterval(500)
        self._recovery_timer.timeout.connect(self._check_for_stale_placeholders)
        self._recovery_timer.start()

        # [신규] 가변 청크 성능 측정용
        self._fetch_start_time = 0.0
        
        # [신규] Viewport Jump용 타이머 (Debounce)
        self._jump_timer = QTimer(self)
        self._jump_timer.setSingleShot(True)
        self._jump_timer.timeout.connect(self.fetchMore)
        
        # [GC Stabilization] 실행 중인 업데이트 컨텍스트 추적
        self._pending_update_ctx = {}


    def _check_for_stale_placeholders(self):
        if self._fetching: return
        now = time.time()
        to_retry = None
        for skip in sorted(list(self._stale_fetch_tracker.keys())):
            if now - self._stale_fetch_tracker[skip] >= 0.5:
                to_retry = skip
                break
        if to_retry is not None:
            if to_retry < len(self._data) and self._data[to_retry] is None:
                self._pending_target_skip = to_retry
                self._stale_fetch_tracker[to_retry] = now
                self.fetchMore()
            else:
                if to_retry in self._stale_fetch_tracker:
                    del self._stale_fetch_tracker[to_retry]

    def update_columns(self, columns: list[str]):
        self.beginResetModel()
        self._columns = columns
        self.endResetModel()

    def set_search_query(self, query: str, search_cols: str = ""):
        if self._search_query == query and self._search_cols == search_cols: return
        self.beginResetModel()
        self._search_query = query
        self._search_cols = search_cols
        self._data = []
        self._total_count = 0
        self._exposed_rows = 0
        self._first_fetch = True
        self._row_id_map = {}
        self._server_fetched_count = 0
        
        # [Phase 73.5] 세션 ID 갱신 무효화 (기존 요청 무시 효과)
        self._search_session_id = str(uuid.uuid4())
        
        self.total_count_changed.emit(0, 0)
        self.endResetModel()
        
        self._refresh_total_count()
        self.fetchMore()

    def set_sort_latest(self, enabled: bool):
        if self._sort_latest == enabled: return
        self.beginResetModel()
        self._sort_latest = enabled
        self._data = []
        self._total_count = 0
        self._exposed_rows = 0
        self._first_fetch = True
        self._row_id_map = {}
        self._server_fetched_count = 0
        
        # [Phase 73.5] 세션 ID 갱신
        self._search_session_id = str(uuid.uuid4())
        
        self.total_count_changed.emit(0, 0)
        self.endResetModel()
        self._refresh_total_count()
        self.fetchMore()

    def _refresh_total_count(self):
        """[Phase 73.6] 현재 검색 조건에 맞는 전체 개수를 서버에 재요청하여 UI 정합성을 맞춤."""
        order = "updated_at" if self._sort_latest else "id"
        desc = "true" if self._sort_latest else "false"
        import urllib.parse
        cols_str = self._search_cols if self._search_cols else ",".join(self._columns)
        url = f"{self.endpoint_url}?skip=0&limit=1&order_by={order}&order_desc={desc}&q={urllib.parse.quote(self._search_query)}&cols={urllib.parse.quote(cols_str)}"
        worker = ApiFetchWorker(url, session_id=self._search_session_id)
        worker.signals.finished.connect(self._on_total_refresh_finished)
        QThreadPool.globalInstance().start(worker)

    def _set_total_count(self, new_total: int):
        """[Phase 73.11] 전체 개수 업데이트를 중앙 집중화하여 UI 정합성을 보장합니다.
        항상 서버로부터 수신된 Ground Truth 값을 기반으로 노출 범위를 조정합니다.
        """
        # 동적 노출 범위 동기화: 전체 개수가 줄어들면 노출 범위도 강제 축소
        if new_total < self._exposed_rows:
            self.beginRemoveRows(QModelIndex(), new_total, self._exposed_rows - 1)
            self._exposed_rows = new_total
            self.endRemoveRows()
            
        self._total_count = new_total
        self.total_count_changed.emit(self._exposed_rows, self._total_count)

    def _on_total_refresh_finished(self, result):
        resp_session = result.get("_session_id")
        if resp_session and resp_session != self._search_session_id:
            return
            
        new_total = result.get("total", 0)
        self._set_total_count(new_total)

    def rowCount(self, parent=QModelIndex()) -> int:
        return self._exposed_rows

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self._columns)

    def flags(self, index):
        if not index.isValid(): return Qt.ItemFlag.NoItemFlags
        col_name = self._columns[index.column()]
        if col_name in ["created_at", "updated_at", "row_id", "id", "updated_by"]:
            return Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
        return super().flags(index) | Qt.ItemFlag.ItemIsEditable

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid() or role != Qt.ItemDataRole.EditRole: return False
        row = index.row()
        if row >= len(self._data) or self._data[row] is None: return False
        
        col_name = self._columns[index.column()]
        if col_name in ["created_at", "updated_at", "row_id", "id", "updated_by"]: return False
        
        cell_data = self._data[row].get("data", {})
        if str(cell_data.get(col_name, {}).get("value", "")) == str(value): return True
        
        row_id = self._data[row].get("row_id")
        p_index = QPersistentModelIndex(index)
        url = config.get_unified_update_url(self.table_name)
        update_item = {"row_id": row_id, "updates": {col_name: value}, "source_name": "user", "updated_by": config.CURRENT_USER}
        worker = ApiGeneralUpdateWorker(url, [update_item])
        
        # [Stabilization] 람다 대신 선언적 컨텍스트 매핑 사용
        ctx = {"index": p_index, "col_name": col_name, "value": value}
        self._pending_update_ctx[id(worker.signals)] = ctx
        
        worker.signals.finished.connect(self._on_cell_update_worker_finished)
        worker.signals.error.connect(self._on_cell_update_worker_error)
        QThreadPool.globalInstance().start(worker)
        return True

    @Slot(dict)
    def _on_cell_update_worker_finished(self, res):
        """셀 업데이트 완료 시 호출되는 슬롯입니다."""
        sig_id = id(self.sender())
        ctx = self._pending_update_ctx.pop(sig_id, None)
        if not ctx: return
        
        # 결과에 컨텍스트 병합하여 기존 처리기 호출
        full_res = {**res, **ctx}
        self._on_update_finished(full_res)

    @Slot(str)
    def _on_cell_update_worker_error(self, err_msg):
        """셀 업데이트 실패 시 호출되는 슬롯입니다."""
        sig_id = id(self.sender())
        self._pending_update_ctx.pop(sig_id, None)
        print(f"[TableModel] Cell update failed: {err_msg}")
        self.status_message_requested.emit(f"⚠️ 업데이트 실패: {err_msg}")


    def applyMappedUpdates(self, mapped_updates: dict):
        payloads = []
        for rid, updates in mapped_updates.items():
            if rid: payloads.append({"row_id": rid, "updates": updates, "source_name": "user", "updated_by": config.CURRENT_USER})
        if not payloads: return
        url = config.get_unified_update_url(self.table_name)
        worker = ApiGeneralUpdateWorker(url, payloads)
        QThreadPool.globalInstance().start(worker)

    def bulkUpdateData(self, start_row, start_col, matrix):
        grouped = {}
        for r_idx, row_vals in enumerate(matrix):
            model_row = start_row + r_idx
            if model_row >= len(self._data) or self._data[model_row] is None: break
            rid = self._data[model_row].get("row_id")
            if not rid: continue
            for c_idx, val in enumerate(row_vals):
                model_col = start_col + c_idx
                if model_col >= len(self._columns): break
                col = self._columns[model_col]
                if col not in ["created_at", "updated_at", "row_id", "id", "updated_by"]:
                    grouped.setdefault(rid, {})[col] = val
        if not grouped: return
        url = config.get_unified_update_url(self.table_name)
        unified = [{"row_id": k, "updates": v, "source_name": "user", "updated_by": config.CURRENT_USER} for k, v in grouped.items()]
        worker = ApiGeneralUpdateWorker(url, unified)
        QThreadPool.globalInstance().start(worker)

    def _on_batch_update_finished(self, result): pass

    @Slot(dict)
    def _on_websocket_broadcast(self, data: dict):
        event = data.get("event")
        if data.get("table_name") != self.table_name: return
        self._is_processing_remote = True
        try:
            if event == "batch_row_delete":
                target_ids = list(set(data.get("row_ids", [])))
                if not target_ids: return
                cached_indices = sorted([self._row_id_map[rid] for rid in target_ids if rid in self._row_id_map])
                if len(target_ids) > 500 or len(cached_indices) < len(target_ids):
                    self.beginResetModel()
                    self._data = [None] * self._total_count
                    self._exposed_rows = min(self._exposed_rows, self._total_count)
                    self._row_id_map = {}; self._server_fetched_count = 0
                    self._refresh_total_count()
                    self.endResetModel()
                else:
                    ranges = []
                    if cached_indices:
                        s = cached_indices[0]; p = s
                        for i in range(1, len(cached_indices)):
                            if cached_indices[i] == p + 1: p = cached_indices[i]
                            else: ranges.append((s, p)); s = cached_indices[i]; p = s
                        ranges.append((s, p))
                        
                    for s, e in reversed(ranges):
                        self.beginRemoveRows(QModelIndex(), s, e)
                        num = (e - s + 1)
                        if s < len(self._data):
                            del self._data[s : e + 1]
                        self._exposed_rows -= num # 노출 개수 감소
                        self.endRemoveRows()

                    self._update_row_id_map()
                    self._refresh_total_count() 

                self.status_message_requested.emit(f"데이터 {len(target_ids)}건 삭제됨")

            elif event == "batch_row_create":
                items = data.get("items", [])
                if not items: return
                import time
                start_t = time.time()
                new_rows = [self._normalize_row_data(item) for item in items]

                
                # [Optimization] 일괄 삽입 시그널 1회 발생
                num = len(new_rows)
                if self._sort_latest:
                    self.beginInsertRows(QModelIndex(), 0, num - 1)
                    self._data = new_rows + self._data
                    self._exposed_rows += num
                    self.endInsertRows()
                    self._update_row_id_map()
                    self.status_message_requested.emit(f"신규 데이터 {num}건 상단 추가됨")
                else:
                    self.beginInsertRows(QModelIndex(), self._exposed_rows, self._exposed_rows + num - 1)
                    self._data.extend(new_rows)
                    self._exposed_rows += num
                    self.endInsertRows()
                    self._update_row_id_map()
                    self.status_message_requested.emit(f"신규 데이터 {num}건 하단 추가됨")
                
                self._refresh_total_count()
                elapsed = (time.time() - start_t) * 1000
                print(f"[PERF] batch_row_create processed {num} rows in {elapsed:.2f}ms")


            elif event == "batch_row_upsert":
                items = data.get("items", [])
                if not items: return
                import time
                start_t = time.time()

                
                # [Optimization] 루프 내 UI 시그널 배제 및 배치화
                moved_norms = []
                indices_to_remove = []
                min_c = float('inf'); max_c = -1
                
                # 1단계: 변경 대상 분류
                for item in items:
                    rid = str(item.get("row_id"))
                    idx = self._row_id_map.get(rid)
                    new_data = item.get("data", {})
                    
                    if idx is not None:
                        row = self._data[idx]
                        row.setdefault("data", {}).update(new_data)
                        norm = self._normalize_row_data(row)
                        
                        if self._sort_latest and idx > 0:
                            indices_to_remove.append(idx)
                            moved_norms.append(norm)
                        else:
                            self._data[idx] = norm
                            min_c = min(min_c, idx)
                            max_c = max(max_c, idx)
                    else:
                        norm = self._normalize_row_data({"row_id": rid, "data": new_data})
                        if self._sort_latest:
                            moved_norms.append(norm)

                # 2단계: 최신순 정렬일 경우 기존 위치 제거 및 상단 삽입
                if indices_to_remove:
                    indices_to_remove = sorted(list(set(indices_to_remove)), reverse=True)
                    for idx in indices_to_remove:
                        self.beginRemoveRows(QModelIndex(), idx, idx)
                        self._data.pop(idx)
                        self.endRemoveRows()
                    self._exposed_rows -= len(indices_to_remove)

                if moved_norms:
                    self.beginInsertRows(QModelIndex(), 0, len(moved_norms)-1)
                    self._data = moved_norms + self._data
                    self._exposed_rows += len(moved_norms)
                    self.endInsertRows()
                    min_c = 0; max_c = max(max_c, len(moved_norms)-1)

                # 3단계: 맵 및 카운트 최종 갱신
                self._update_row_id_map()
                if max_c != -1:
                    row_count = len(self._data)
                    max_c = min(max_c, row_count - 1)
                    self.dataChanged.emit(self.index(int(min_c), 0), self.index(int(max_c), len(self._columns)-1))
                
                self._refresh_total_count()
                elapsed = (time.time() - start_t) * 1000
                print(f"[PERF] batch_row_upsert processed {len(items)} items in {elapsed:.2f}ms")
                self.status_message_requested.emit(f"데이터 {len(items)}건 실시간 업데이트됨")



        finally:
            self._is_processing_remote = False

    def _normalize_row_data(self, row: dict) -> dict:
        blob = row.get("data", {})
        if "created_at" in blob: row["created_at"] = blob["created_at"].get("value")
        if "updated_at" in blob: row["updated_at"] = blob["updated_at"].get("value")
        return row

    def _update_row_id_map(self):
        print('[DEBUG] update row id map')
        self._row_id_map = {str(r.get("row_id")): i for i, r in enumerate(self._data) if r}

    def _build_row_id_map(self):
        if not self._row_id_map: self._update_row_id_map()
        return self._row_id_map

    def _on_remote_row_fetched(self, row):
        rid = str(row.get("row_id"))
        if rid in self._fetching_row_ids: self._fetching_row_ids.remove(rid)
        norm = self._normalize_row_data(row)
        mapping = self._build_row_id_map()
        if rid in mapping:
            idx = mapping[rid]; self._data[idx] = norm
            # [Fix] 최신순 정렬일 때만 최상단으로 이동
            if self._sort_latest and idx > 0:
                self.beginMoveRows(QModelIndex(), idx, idx, QModelIndex(), 0)
                self._data.insert(0, self._data.pop(idx)); self.endMoveRows()
        else:
            # [Fix] 최신순 정렬일 때만 최상단 삽입
            if self._sort_latest:
                self.beginInsertRows(QModelIndex(), 0, 0)
                self._data.insert(0, norm); self.endInsertRows()
            else:
                # ID 정렬 시에는 카운트만 갱신 (이미 _refresh_total_count가 호출될 것임)
                pass
        self._update_row_id_map()

    def _on_update_finished(self, res):
        idx = res["index"]
        if idx.isValid() and idx.row() < len(self._data):
            cell = self._data[idx.row()].setdefault("data", {}).setdefault(res["col_name"], {})
            cell.update({"value": res["value"], "is_overwrite": True})
            self.dataChanged.emit(idx, idx)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid(): return None
        row, col = index.row(), index.column()

        if row >= self._exposed_rows - 10 and self.canFetchMore():
            # [안정성] 직접 호출 시 ProxyModel 매핑 파괴 위험이 있으므로 다음 이벤트 루프로 지연 실행 (Proactive Expansion)
            self._jump_timer.start(1)

        if row >= len(self._data) or self._data[row] is None:
            if role == Qt.ItemDataRole.DisplayRole:
                # Viewport에 빈 데이터가 포착되면 해당 위치 최우선 로딩 예약
                skip = (row // self._chunk_size) * self._chunk_size
                if not self._fetching:
                    self._pending_target_skip = skip
                    if not self._jump_timer.isActive():
                        self._jump_timer.start(1) # 10ms Debounce
                
                if skip not in self._stale_fetch_tracker: 
                    self._stale_fetch_tracker[skip] = time.time()
                return "Loading..."
            return None

        col_name = self._columns[col]
        if col_name in ["created_at", "updated_at"]:
            if role in [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole]:
                return self._data[row].get(col_name) or self._data[row].get("data", {}).get(col_name, {}).get("value", "")
            return None
        if role in [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole]:
            val = self._data[row].get("data", {}).get(col_name, {}).get("value", "")
            return str(val) if role == Qt.ItemDataRole.EditRole else val
        if role == Qt.ItemDataRole.UserRole + 2: return self._data[row].get("row_id")
        if role == Qt.ItemDataRole.BackgroundRole:
            if self._data[row].get("data", {}).get(col_name, {}).get("is_overwrite"):
                from PySide6.QtGui import QColor
                return QColor("#BD6031")
        return None

    def canFetchMore(self, parent=QModelIndex()) -> bool:
        # 노출된 행이 전체 행보다 적으면 더 가져올 수 있음
        return not self._fetching and (self._first_fetch or self._exposed_rows < self._total_count)

    def fetchMore(self, parent=QModelIndex()):
        # 1. 스냅샷: 현재 로딩 중인지 확인
        is_jump_request = self._pending_target_skip is not None
        
        # [Fix] 점프 요청 시에는 일반 fetching 가드를 무시하거나 중단하고 최우선 처리
        if self._fetching and not is_jump_request:
            return
            
        # 2. 노출 범위 확장 (Adaptive Expansion)
        # 점프 요청이거나, Qt가 스크롤바 바닥을 쳤을 때
        if is_jump_request:
            # 점프 대상이 현재 노출 범위를 넘어선다면 미리 공간 확보 (Shell Extension)
            if self._pending_target_skip + self._chunk_size > self._exposed_rows:
                new_limit = self._pending_target_skip + self._chunk_size
                self.beginInsertRows(QModelIndex(), self._exposed_rows, new_limit - 1)
                self._exposed_rows = new_limit
                if len(self._data) < self._exposed_rows:
                    self._data.extend([None] * (self._exposed_rows - len(self._data)))
                self.endInsertRows()
                self.total_count_changed.emit(self._exposed_rows, self._total_count)
        elif not self._first_fetch:
            # 일반 스크롤 확장 (기존 로직 유지)
            remaining = self._total_count - self._exposed_rows
            increment = min(self._chunk_size, remaining)
            if increment > 0:
                self.beginInsertRows(QModelIndex(), self._exposed_rows, self._exposed_rows + increment - 1)
                self._exposed_rows += increment
                if len(self._data) < self._exposed_rows:
                    self._data.extend([None] * (self._exposed_rows - len(self._data)))
                self.endInsertRows()
                self.total_count_changed.emit(self._exposed_rows, self._total_count)
            return

        # 3. 데이터 로딩 (Viewport Request Only)
        if self._fetching and not is_jump_request: return
        
        # 타이머 중지 (명시적 호출 시)
        if self._jump_timer.isActive(): self._jump_timer.stop()
        
        self._fetching = True 
        self._fetch_scheduled = False
        self._fetch_start_time = time.time() # [신규] 페칭 시작 시간 기록
        
        skip = self._pending_target_skip if self._pending_target_skip is not None else 0
        print(f"[DEBUG-Model] fetchMore starting. skip={skip}, chunk={self._chunk_size}, is_jump={is_jump_request}")
        
        self._pending_target_skip = None
        self._active_target_skip = skip
        
        order = "updated_at" if self._sort_latest else "id"
        desc = "true" if self._sort_latest else "false"
        url = f"{self.endpoint_url}?skip={skip}&limit={self._chunk_size}&order_by={order}&order_desc={desc}"
        if self._search_query:
            import urllib.parse
            target_cols = self._search_cols if self._search_cols else ",".join(self._columns)
            url += f"&q={urllib.parse.quote(self._search_query)}&cols={urllib.parse.quote(target_cols)}"
            
        print(f"[DEBUG-Model] Request URL: {url}")
        worker = ApiFetchWorker(url, session_id=self._search_session_id)
        worker.signals.finished.connect(self._on_fetch_finished)
        worker.signals.error.connect(self._on_fetch_error)
        QThreadPool.globalInstance().start(worker)

    def fetch_batch(self, count: int = 1000):
        """특정 개수(기본 1000개)만큼의 데이터를 한꺼번에 가져오고 노출 범위를 확장합니다."""
        if self._fetching: return
        
        remaining = self._total_count - self._exposed_rows
        increment = min(count, remaining)
        print(increment)
        if increment <= 0: 
            self.status_message_requested.emit("마지막 행입니다.")
            self.batch_fetch_finished.emit()
            return

        self._fetching = True
        self._batch_fetching = True # 플래그 설정
        self._fetch_start_time = time.time() # [신규] 페칭 시작 시간 기록
        
        # 1. 노출 범위 확장 알림 및 데이터 버퍼 패딩
        self.beginInsertRows(QModelIndex(), self._exposed_rows, self._exposed_rows + increment - 1)
        self._exposed_rows += increment
        if len(self._data) < self._exposed_rows:
            self._data.extend([None] * (self._exposed_rows - len(self._data)))
        self.endInsertRows()
        # [Phase 73.8] 일괄 로드 시에도 즉시 로드 수치 반영
        self.total_count_changed.emit(self._exposed_rows, self._total_count)

        # 2. 서버 요청 (이미 확장된 내역까지 포함하여 Gap 없이 채우도록 limit 계산)
        skip = self._server_fetched_count
        self._active_target_skip = skip
        
        # [Fix] 단순 increment가 아니라, 현재 노출된 전체 범위(_exposed_rows)까지 부족한 데이터를 모두 채움
        fetch_limit = self._exposed_rows - skip
        
        order = "updated_at" if self._sort_latest else "id"
        desc = "true" if self._sort_latest else "false"
        url = f"{self.endpoint_url}?skip={skip}&limit={fetch_limit}&order_by={order}&order_desc={desc}"
        if self._search_query:
            import urllib.parse
            target_cols = self._search_cols if self._search_cols else ",".join(self._columns)
            url += f"&q={urllib.parse.quote(self._search_query)}&cols={urllib.parse.quote(target_cols)}"
            
        worker = ApiFetchWorker(url, session_id=self._search_session_id)
        worker.signals.finished.connect(self._on_fetch_finished)
        worker.signals.error.connect(self._on_fetch_error)
        QThreadPool.globalInstance().start(worker)

    def _on_fetch_finished(self, result):
        # [Phase 73.5] 세션 검증: 응답에 포함된 세션 ID가 현재 모델의 세션 ID와 다르면 폐기
        resp_session = result.get("_session_id")
        if resp_session and resp_session != self._search_session_id:
            print(f"[Model] Discarding stale session result: {resp_session} != {self._search_session_id}")
            self._fetching = False
            return

        # [Phase 73.8] 네트워크 응답 도착 직후 메타데이터(Total)부터 즉시 업데이트하여 UI 반응성 확보
        total = result.get("total", 0)
        self._set_total_count(total)

        new = result.get("data", []); total = result.get("total", 0)
        skip = getattr(self, '_active_target_skip', 0)
        if skip in self._stale_fetch_tracker: del self._stale_fetch_tracker[skip]
        
        if self._first_fetch:
            self.beginResetModel()
            self._set_total_count(total)
            self._data = new
            # 첫 페칭 시점에 노출 개수 동기화
            self._exposed_rows = len(new)
            self._first_fetch = False
            self._server_fetched_count = len(new)
            self.endResetModel()
            self._fetching = False
            self._update_row_id_map()
            self.fetch_finished.emit() # [신규]
            return
        
        # 만약 모델이 리셋된 상태(_first_fetch=True)인데 이전 세션의 응답이 온 것이라면 무시
        if self._first_fetch:
            self._fetching = False
            return

        if new:
            # [Fix] ID 기반 중복 필터링 로직: 이미 버퍼 내 다른 위치에 존재하는 ID가 오면 기존 데이터만 갱신하고 중복 삽입 차단
            for i, r in enumerate(new):
                rid = str(r.get("row_id"))
                existing_idx = self._row_id_map.get(rid)
                
                # 만약 현재 채우려는 skip 위치가 아닌 다른 곳에 이미 해당 ID가 있다면 (중복)
                target_idx = skip + i
                if existing_idx is not None and existing_idx != target_idx:
                    # 기존 위치의 데이터만 최신화 (Stability 고수)
                    if existing_idx < len(self._data):
                        self._data[existing_idx] = r
                    # 현재(뒤쪽) 위치에는 중복 마커 삽입 (프록시에서 필터링용)
                    if target_idx >= len(self._data):
                        self._data.extend([None] * (target_idx - len(self._data) + 1))
                    self._data[target_idx] = {"_is_duplicate": True, "row_id": rid}
                    continue
                
                # 정상 삽입 (데이터가 버퍼 범위를 넘어서면 확장)
                if target_idx >= len(self._data):
                    self._data.extend([None] * (target_idx - len(self._data) + 1))
                self._data[target_idx] = r
            
            # 노출 범위 최종 동기화 (이미 fetchMore에서 늘어났다면 diff <= 0)
            target_exposed = skip + len(new)
            if target_exposed > self._exposed_rows:
                diff = target_exposed - self._exposed_rows
                self.beginInsertRows(QModelIndex(), self._exposed_rows, target_exposed - 1)
                self._exposed_rows = target_exposed
                if len(self._data) < self._exposed_rows:
                    self._data.extend([None] * (self._exposed_rows - len(self._data)))
                self.endInsertRows()

            self.total_count_changed.emit(self._exposed_rows, self._total_count)
            self.dataChanged.emit(self.index(skip, 0), self.index(skip + len(new) - 1, len(self._columns) - 1))
            if skip == self._server_fetched_count: self._server_fetched_count += len(new)
        
        # ── [Phase 2] 가변 청크 사이즈 (Adaptive Chunk Size) 조절 ──
        duration = time.time() - self._fetch_start_time
        old_size = self._chunk_size
        
        if duration < 0.5: # Fast -> 사이즈 상향 (최대 3000)
            self._chunk_size = min(3000, int(self._chunk_size * 1.1))
        elif duration > 0.55: # Slow -> 사이즈 하향 (최소 50)
            self._chunk_size = max(50, int(self._chunk_size * 0.9))
            
        # 디버그 및 알림 (사이즈가 변경되었을 때만)
        if old_size != self._chunk_size:
            print(f"[Adaptive] Duration: {duration:.3f}s | Chunk Size: {old_size} -> {self._chunk_size}")
            # 사용자가 인지할 수 있도록 상태바 요청 (너무 잦은 알림 방지를 위해 소량 변화량은 생략하거나 주기 조절 가능)
            if abs(old_size - self._chunk_size) > 10:
                self.status_message_requested.emit(f"성능 최적화: 청크 사이즈 {self._chunk_size}행으로 조절 (응답: {duration:.3f}s)")

        # 마지막으로 한 번 더 시그널을 보내어 UI 동기화 보장
        print('[DEBUG] fetch 완료')
        self.status_message_requested.emit(f"{len(new)} 행 추가 로드 완료 (약 {duration:.2f}초)")
        self._update_row_id_map(); self._fetching = False
        self.fetch_finished.emit() # [신규]
        
        if self._batch_fetching:
            self._batch_fetching = False
            self.batch_fetch_finished.emit()

    def _on_fetch_error(self, err): 
        self._fetching = False
        self.fetch_finished.emit() # [신규]

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal:
            if role == Qt.ItemDataRole.DisplayRole: return self._columns[section].upper()
            if role == Qt.ItemDataRole.UserRole: return self._columns[section]
        if orientation == Qt.Orientation.Vertical:
            if role == Qt.ItemDataRole.DisplayRole: return str(section + 1)
        return None

class ApiExportWorker(QRunnable):
    """취소 및 진행률 전송이 가능한 백그라운드 CSV 추출 워커."""
    class WorkerSignals(QObject):
        progress = Signal(str, int, int) # task_id, current_bytes, total_bytes
        finished = Signal(str, str)     # task_id, file_path
        error = Signal(str, str)        # task_id, error_msg

    def __init__(self, task_id: str, url: str, export_path: str):
        super().__init__()
        self.task_id = task_id
        self.url = url
        self.export_path = export_path
        self._is_cancelled = False
        self.signals = self.WorkerSignals()

    def cancel(self):
        self._is_cancelled = True

    @Slot()
    def run(self):
        import urllib.request
        try:
            # 타임아웃 및 정적 헤더 설정
            req = urllib.request.Request(self.url)
            with urllib.request.urlopen(req, timeout=30) as response:
                total_size = int(response.headers.get('Content-Length', -1))
                curr_size = 0
                
                with open(self.export_path, "wb") as f:
                    while not self._is_cancelled:
                        chunk = response.read(1024 * 128) # 128KB chunks
                        if not chunk: break
                        
                        f.write(chunk)
                        curr_size += len(chunk)
                        # 0.5초 간격으로 진행률 보고 (성능 보호)
                        self.signals.progress.emit(self.task_id, curr_size, total_size)
                
                if self._is_cancelled:
                    # 취소 시 불완전 파일 삭제
                    if os.path.exists(self.export_path): os.remove(self.export_path)
                    return

            self.signals.finished.emit(self.task_id, self.export_path)
        except Exception as e:
            self.signals.error.emit(self.task_id, str(e))

