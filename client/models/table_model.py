import config
import time
import uuid
from datetime import datetime
from PySide6.QtCore import QAbstractTableModel, Qt, QModelIndex, QRunnable, QThreadPool, Signal, Slot, QObject, QPersistentModelIndex, QThread, QTimer

class WorkerSignals(QObject):
    finished = Signal(dict)
    error = Signal(str)

class ApiFetchWorker(QRunnable):
    def __init__(self, url, session_id: str = ""):
        super().__init__()
        self.url = url
        self.session_id = session_id
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        import urllib.request
        import json
        try:
            req = urllib.request.Request(self.url)
            with urllib.request.urlopen(req, timeout=5.0) as response:
                result = json.loads(response.read().decode())
                # 세션 ID를 결과와 함께 반환
                if isinstance(result, dict):
                    result["_session_id"] = self.session_id
                self.signals.finished.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))

class ApiSchemaWorker(QRunnable):
    def __init__(self, url):
        super().__init__()
        self.url = url
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        import urllib.request
        import json
        try:
            req = urllib.request.Request(self.url)
            with urllib.request.urlopen(req, timeout=5.0) as response:
                result = json.loads(response.read().decode())
                self.signals.finished.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))

class ApiSingleRowFetchWorker(QRunnable):
    def __init__(self, url):
        super().__init__()
        self.url = url
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        import urllib.request
        import json
        try:
            req = urllib.request.Request(self.url)
            with urllib.request.urlopen(req, timeout=5.0) as response:
                result = json.loads(response.read().decode())
                self.signals.finished.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))

class ApiGeneralUpdateWorker(QRunnable):
    def __init__(self, url: str, updates: list[dict]):
        super().__init__()
        self.url = url
        self.updates = updates
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        import urllib.request
        import json
        try:
            payload = {"updates": self.updates}
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                self.url, 
                data=data, 
                method="PUT", 
                headers={'Content-Type': 'application/json'}
            )
            with urllib.request.urlopen(req) as response:
                res = json.loads(response.read().decode())
                if res.get("status") == "success":
                    self.signals.finished.emit(res)
                else:
                    self.signals.error.emit(res.get("status", "unknown error"))
        except Exception as e:
            self.signals.error.emit(str(e))

class ApiUploadWorker(QRunnable):
    def __init__(self, url, file_path):
        super().__init__()
        self.url = url
        self.file_path = file_path
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        import httpx
        import os
        try:
            filename = os.path.basename(self.file_path)
            with open(self.file_path, "rb") as f:
                files = {"file": (filename, f)}
                with httpx.Client(timeout=30.0) as client:
                    response = client.post(self.url, files=files)
                    if response.status_code == 200:
                        self.signals.finished.emit(response.json())
                    else:
                        self.signals.error.emit(f"Server error: {response.status_code} - {response.text}")
        except Exception as e:
            self.signals.error.emit(str(e))

class ApiTargetedRowIdWorker(QRunnable):
    def __init__(self, url: str, offsets: list[int], search_query: str = "", order_by: str = "updated_at", order_desc: bool = True, session_id: str = "", cols: str = ""):
        super().__init__()
        self.url = url
        self.offsets = offsets
        self.search_query = search_query
        self.order_by = order_by
        self.order_desc = order_desc
        self.session_id = session_id
        self.cols = cols # [Phase 73.6]
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        import urllib.request
        import json
        try:
            payload = {
                "offsets": self.offsets,
                "q": self.search_query,
                "cols": self.cols, # [Phase 73.6]
                "order_by": self.order_by,
                "order_desc": self.order_desc
            }
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                self.url, 
                data=data, 
                method="POST", 
                headers={'Content-Type': 'application/json'}
            )
            with urllib.request.urlopen(req, timeout=10.0) as response:
                raw = response.read().decode("utf-8")
                result = json.loads(raw)
                if isinstance(result, dict):
                    result["_session_id"] = self.session_id
                self.signals.finished.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))

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
    ws_data_changed = Signal(dict)
    batch_ws_data_changed = Signal(dict)
    row_created_ws = Signal(dict)
    row_deleted_ws = Signal(dict)
    total_count_changed = Signal(int, int) # (exposed_rows, total_count)
    batch_fetch_finished = Signal()

    def __init__(self, table_name: str, base_api_url: str = config.API_BASE_URL):
        super().__init__()
        self.table_name = table_name
        self.base_api_url = base_api_url
        self.endpoint_url = config.get_table_data_url(table_name)
        self._data = []
        self._total_count = 0
        self._columns = []
        self._chunk_size = 500
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

        # [신규] Viewport Jump용 타이머 (Debounce)
        self._jump_timer = QTimer(self)
        self._jump_timer.setSingleShot(True)
        self._jump_timer.timeout.connect(self.fetchMore)

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
        worker.signals.finished.connect(lambda res: self._on_update_finished({**res, "index": p_index, "col_name": col_name, "value": value}))
        QThreadPool.globalInstance().start(worker)
        return True

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

                self.row_deleted_ws.emit(data)

            elif event == "batch_row_create":
                items = data.get("items", [])
                if not items: return
                new_rows = [self._normalize_row_data(item) for item in items]
                if self._sort_latest:
                    self.beginInsertRows(QModelIndex(), 0, len(new_rows)-1)
                    self._data = new_rows + self._data
                    self._exposed_rows += len(new_rows) 
                    self.endInsertRows()
                
                self._update_row_id_map()
                self._refresh_total_count() # [Phase 73.6] 서버에 재요청
                self.row_created_ws.emit(data)

            elif event == "batch_row_upsert":
                items = data.get("items", [])
                if not items: return
                moved = []; min_c = float('inf'); max_c = -1
                all_cell_updates = []
                for item in reversed(items):
                    rid = item.get("row_id")
                    idx = self._row_id_map.get(rid)
                    new_data = item.get("data", {})
                    
                    if idx is not None:
                        row = self._data[idx]
                        row.setdefault("data", {}).update(new_data)
                        norm = self._normalize_row_data(row)
                        if self._sort_latest and idx > 0:
                            moved.append((rid, norm))
                            self.beginRemoveRows(QModelIndex(), idx, idx); self._data.pop(idx); self.endRemoveRows()
                            self._update_row_id_map()
                        else:
                            print('stuck')
                            self._data[idx] = norm
                            min_c = min(min_c, idx); max_c = max(max_c, idx)
                    else:
                        print('no idx')
                        norm = self._normalize_row_data({"row_id": rid, "data": new_data})
                        moved.append((rid, norm))
                    
                    # 히스토리 추적용 플래닝 (Flattening)
                    for col, cell_val in new_data.items():
                        if isinstance(cell_val, dict) and "value" in cell_val:
                            all_cell_updates.append({
                                "row_id": rid,
                                "column_name": col,
                                "value": cell_val["value"],
                                "is_overwrite": cell_val.get("is_overwrite", False),
                                "updated_by": cell_val.get("updated_by", "system"),
                                "source": "remote"
                            })

                if moved:
                    self.beginInsertRows(QModelIndex(), 0, len(moved)-1)
                    self._data = [r for rid, r in reversed(moved)] + self._data
                    self._exposed_rows += len(moved)
                    self.endInsertRows(); self._update_row_id_map()
                    min_c = 0; max_c = max(max_c, len(moved)-1)

                if all_cell_updates:
                    self.batch_ws_data_changed.emit({
                        "updates": all_cell_updates,
                        "change_count": data.get("change_count", len(all_cell_updates)),
                        "updated_by": data.get("updated_by", "system")
                    })

                if max_c != -1:
                    self.dataChanged.emit(self.index(min_c, 0), self.index(max_c, len(self._columns)-1))
                
                self._refresh_total_count()

            elif event in ["cell_update", "batch_cell_update"]:
                updates = [data] if event == "cell_update" else data.get("updates", [])
                min_r = float('inf'); max_r = -1; logs = []
                for u in updates:
                    idx = self._row_id_map.get(u.get("row_id"))
                    if idx is not None and self._data[idx]:
                        cell = self._data[idx].setdefault("data", {}).setdefault(u.get("column_name"), {})
                        cell.update({"value": u.get("value"), "is_overwrite": u.get("is_overwrite", False), "updated_by": u.get("updated_by", "system")})
                        min_r = min(min_r, idx); max_r = max(max_r, idx); logs.append({**u, "source": "remote"})
                if logs: self.batch_ws_data_changed.emit({"updates": logs, "change_count": len(logs), "updated_by": data.get("updated_by", "system")})
                if max_r != -1: self.dataChanged.emit(self.index(min_r, 0), self.index(max_r, len(self._columns)-1))
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
            if self._sort_latest and idx > 0:
                self.beginMoveRows(QModelIndex(), idx, idx, QModelIndex(), 0)
                self._data.insert(0, self._data.pop(idx)); self.endMoveRows()
        else:
            self.beginInsertRows(QModelIndex(), 0, 0)
            self._data.insert(0, norm); self.endInsertRows()
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
        if row >= len(self._data) or self._data[row] is None:
            if role == Qt.ItemDataRole.DisplayRole:
                # Viewport에 빈 데이터가 포착되면 해당 위치 최우선 로딩 예약
                skip = (row // self._chunk_size) * self._chunk_size
                if not self._fetching:
                    self._pending_target_skip = skip
                    if not self._jump_timer.isActive():
                        self._jump_timer.start(50) # 50ms Debounce
                
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
        
        # 2. 노출 범위 확장 (Adaptive Expansion - Shell Only)
        # Qt가 스크롤바 바닥을 쳐서 호출했거나, 명시적으로 봇물을 터트려야 할 때
        # 단, 첫 페칭(Metadata 수신용)은 반드시 진행해야 함
        if not is_jump_request and not self._first_fetch:
            remaining = self._total_count - self._exposed_rows
            increment = min(self._chunk_size, remaining)
            if increment > 0:
                self.beginInsertRows(QModelIndex(), self._exposed_rows, self._exposed_rows + increment - 1)
                self._exposed_rows += increment
                if len(self._data) < self._exposed_rows:
                    self._data.extend([None] * (self._exposed_rows - len(self._data)))
                self.endInsertRows()
                # [Phase 73.8] 즉시 카운트 업데이트 시그널 송출 (Loaded 수치 선점)
                self.total_count_changed.emit(self._exposed_rows, self._total_count)
            # 순차 확장이 목적이라면 여기서 종료 (네트워크 요청 안 함)
            return

        # 3. 데이터 로딩 (Viewport Request Only)
        if self._fetching: return
        
        # 타이머 중지 (명시적 호출 시)
        if self._jump_timer.isActive(): self._jump_timer.stop()
        
        self._fetching = True 
        self._fetch_scheduled = False
        
        skip = self._pending_target_skip if self._pending_target_skip is not None else 0
        self._pending_target_skip = None
        self._active_target_skip = skip
        
        order = "updated_at" if self._sort_latest else "id"
        desc = "true" if self._sort_latest else "false"
        url = f"{self.endpoint_url}?skip={skip}&limit={self._chunk_size}&order_by={order}&order_desc={desc}"
        if self._search_query:
            import urllib.parse
            target_cols = self._search_cols if self._search_cols else ",".join(self._columns)
            url += f"&q={urllib.parse.quote(self._search_query)}&cols={urllib.parse.quote(target_cols)}"
            
        worker = ApiFetchWorker(url, session_id=self._search_session_id)
        worker.signals.finished.connect(self._on_fetch_finished)
        worker.signals.error.connect(self._on_fetch_error)
        QThreadPool.globalInstance().start(worker)

    def fetch_batch(self, count: int = 1000):
        """특정 개수(기본 1000개)만큼의 데이터를 한꺼번에 가져오고 노출 범위를 확장합니다."""
        if self._fetching: return
        
        remaining = self._total_count - self._exposed_rows
        increment = min(count, remaining)
        if increment <= 0: return

        self._fetching = True
        self._batch_fetching = True # 플래그 설정
        
        # 1. 노출 범위 확장 알림 및 데이터 버퍼 패딩
        self.beginInsertRows(QModelIndex(), self._exposed_rows, self._exposed_rows + increment - 1)
        self._exposed_rows += increment
        if len(self._data) < self._exposed_rows:
            self._data.extend([None] * (self._exposed_rows - len(self._data)))
        self.endInsertRows()
        # [Phase 73.8] 일괄 로드 시에도 즉시 로드 수치 반영
        self.total_count_changed.emit(self._exposed_rows, self._total_count)

        # 2. 서버 요청
        skip = self._server_fetched_count
        self._active_target_skip = skip
        
        order = "updated_at" if self._sort_latest else "id"
        desc = "true" if self._sort_latest else "false"
        url = f"{self.endpoint_url}?skip={skip}&limit={increment}&order_by={order}&order_desc={desc}"
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
            return
        
        # 만약 모델이 리셋된 상태(_first_fetch=True)인데 이전 세션의 응답이 온 것이라면 무시
        if self._first_fetch:
            self._fetching = False
            return

        if new:
            # 신규 데이터가 기존 버퍼 범위를 넘어서면 확장
            if skip + len(new) > len(self._data):
                needed = (skip + len(new)) - len(self._data)
                self._data.extend([None] * needed)
            
            for i, r in enumerate(new):
                self._data[skip + i] = r
            
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
        
        # 마지막으로 한 번 더 시그널을 보내어 UI 동기화 보장
        print('[DEBUG] fetch 완료')
        self._update_row_id_map(); self._fetching = False
        
        if self._batch_fetching:
            self._batch_fetching = False
            self.batch_fetch_finished.emit()

    def _on_fetch_error(self, err): self._fetching = False

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal:
            if role == Qt.ItemDataRole.DisplayRole: return self._columns[section].upper()
            if role == Qt.ItemDataRole.UserRole: return self._columns[section]
        if orientation == Qt.Orientation.Vertical:
            if role == Qt.ItemDataRole.DisplayRole: return str(section + 1)
        return None
