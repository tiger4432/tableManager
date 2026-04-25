import config
import os
import time
import uuid
from datetime import datetime
from dataclasses import dataclass, field
from PySide6.QtCore import QAbstractTableModel, Qt, QModelIndex, QRunnable, QThreadPool, Signal, Slot, QObject, QPersistentModelIndex, QThread, QTimer


@dataclass
class FetchContext:
    source: str
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    params: dict = field(default_factory=dict)

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
    connected = Signal() # [신규] 재연결 성공 알림

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
                    self.connected.emit() # [신규] 연결 성공 시그널 발생
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
    count_changed = Signal(int, int, int) # (exposed_rows, loaded_rows, total_count)
    batch_fetch_finished = Signal()
    fetch_finished = Signal()
    status_message_requested = Signal(str)

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
        self._pending_target_row_id = None # [Phase 1] 점프 대상 ID 보관용
        self._is_processing_remote = False
        self._fetching_row_ids = set()
        self._sort_latest = True
        self._server_fetched_count = 0
        self._search_query = ""
        self._search_cols = ""        # [Phase 73.7] 서버 전송용 컬럼 문자열
        self._search_cols_state = []  # [Phase 73.8] UI 체크박스 상태 보존용 리스트
        self._exposed_rows = 0        # [신규] 실제로 UI에 노출된 행 수
        self._loaded_count = 0         # [Optimization] O(1) 추적을 위한 가용 데이터 카운트
        
        self._row_id_map = {}
        self._pending_target_skip = None # [신규] 특정 오프셋 점프 예약용
        # [Phase 73.5] 검색 세션 ID 도입 - 고속 타이핑 시 이전 검색 결과 오염 방지
        self._search_session_id = str(uuid.uuid4())

        # [신규] 가변 청크 성능 측정용
        self._fetch_start_time = 0.0
        
        # [신규] Viewport Jump용 타이머 (Debounce)
        self._jump_timer = QTimer(self)
        self._jump_timer.setSingleShot(True)
        self._jump_timer.timeout.connect(self._on_jump_timer_timeout)
        
        # [GC Stabilization] 실행 중인 업데이트 컨텍스트 추적
        self._pending_update_ctx = {}
        
        self._active_fetch_ctx = None
        self._pending_fetch_ctx = None

    @property
    def loaded_count(self) -> int:
        """실제로 데이터가 로드된(None이 아닌) 행 수를 반환합니다 (O(1))."""
        return self._loaded_count

    def _on_jump_timer_timeout(self):
        ctx = self._pending_fetch_ctx if self._pending_fetch_ctx else FetchContext(source="scroll")
        self.request_fetch(ctx)


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
        self._loaded_count = 0
        
        # [Phase 73.5] 세션 ID 갱신 무효화 (기존 요청 무시 효과)
        self._search_session_id = str(uuid.uuid4())
        
        self.count_changed.emit(0, 0, 0)
        self.endResetModel()
        
        self._refresh_total_count()
        self.request_fetch(FetchContext(source="scroll", params={"skip": 0}))

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
        self._loaded_count = 0
        
        # [Phase 73.5] 세션 ID 갱신
        self._search_session_id = str(uuid.uuid4())
        
        self.count_changed.emit(0, 0, 0)
        self.endResetModel()
        self._refresh_total_count()
        self.request_fetch(FetchContext(source="scroll", params={"skip": 0}))

    def _refresh_total_count(self):
        """[Phase 73.6] 현재 검색 조건에 맞는 전체 개수를 서버에 재요청하여 UI 정합성을 맞춤."""
        self.request_fetch(FetchContext(source="total_count"))

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
        self.count_changed.emit(self._exposed_rows, self.loaded_count, self._total_count)

    def _on_total_refresh_finished(self, result):
        resp_session = result.get("_session_id")
        if resp_session and self._active_fetch_ctx and resp_session != self._active_fetch_ctx.session_id:
            return
            
        new_total = result.get("total", 0)
        self._set_total_count(new_total)
        self._finalize_fetch()

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


    #[중요] cell 변경 함수
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
                            # [Optimization] 삭제되는 구간 내 실제 데이터(None이 아닌) 개수 차감
                            deleted_data_count = sum(1 for r in self._data[s : e + 1] if r is not None)
                            self._loaded_count -= deleted_data_count
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
                    self._loaded_count += num
                    self.endInsertRows()
                    self._update_row_id_map()
                    self.status_message_requested.emit(f"신규 데이터 {num}건 상단 추가됨")
                else:
                    self.beginInsertRows(QModelIndex(), self._exposed_rows, self._exposed_rows + num - 1)
                    self._data.extend(new_rows)
                    self._exposed_rows += num
                    self._loaded_count += num
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
                        
                        # [Optimization] 신규 유입(idx is None) 시에만 카운트 증가
                        if idx is None:
                            self._loaded_count += 1

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

    def _update_row_id_map(self, specific_rows: list = None, start_idx: int = 0):
        """row_id -> index 매핑을 효율적으로 갱신합니다."""
        if specific_rows is not None:
            # [Optimization] 신규 유입된 부분만 업데이트 (O(Chunk))
            for i, r in enumerate(specific_rows):
                if r and not r.get("_is_duplicate"):
                    rid = str(r.get("row_id"))
                    self._row_id_map[rid] = start_idx + i
        else:
            # 전수 업데이트 (O(N)) - 모델 리셋 시에만 호출
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
            if not self._jump_timer.isActive():
                self._pending_fetch_ctx = FetchContext(source="scroll")
                self._jump_timer.start(1)

        if row >= len(self._data) or self._data[row] is None: #row가 데이터의 끝이거나 데이터가 None일 경우
            if role == Qt.ItemDataRole.DisplayRole:
                # Viewport에 빈 데이터가 포착되면 해당 위치 최우선 로딩 예약
                skip = (row // self._chunk_size) * self._chunk_size #chuck 단위로 fetching, 양자화
                
                # [Fix] 현재 fetching 중이더라도 가장 최근에 노출된 뷰포트의 데이터를 우선적으로 큐잉
                self._pending_fetch_ctx = FetchContext(source="scroll", params={"skip": skip})
                
                if not self._fetching and not self._jump_timer.isActive(): #fetching과 jump 중이 아닐때
                    self._jump_timer.start(1) # 1ms Debounce
                    #_jump_timer가 하는일
                    # 현재 pending 중인 fetchcontext를 timeout시 요청, 만약 timeout 시에도 fetch 중이라면? 
                    # _on_jump_timer_timeout -> 그냥 pending 계속 대기. 싱글턴으로 다시 jump_timer 시작해야함.

                return "Loading..." #페치 예약만 걸고 일단 loading으로 빠져나옴
            return None

        col_name = self._columns[col]
        """
        2. 생성일/수정일 특수 처리
        이유: 시스템 컬럼인 created_at이나 updated_at은 서버 응답 포맷에 따라 최상위(Root)에 있을 수도 있고, data라는 딕셔너리 내부에 있을 수도 있습니다.
        역할: 화면에 보여주거나(DisplayRole), 사용자가 더블클릭해서 편집할 때(EditRole) 둘 중 어느 위치에 있든 안전하게 값을 꺼내서 텍스트로 보여주기 위한 예외 처리입니다.
        """
        if col_name in ["created_at", "updated_at"]:
            if role in [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole]:
                return self._data[row].get(col_name) or self._data[row].get("data", {}).get(col_name, {}).get("value", "")
            return None
        
        """
        3. 일반 데이터 표시 및 편집 모드
        DisplayRole: 화면에 평상시 텍스트를 그릴 때 요청됩니다.
        EditRole: 사용자가 셀을 더블클릭해서 커서가 생기는 편집 모드일 때 요청됩니다.
        역할: self._data[row]["data"]["컬럼명"]["value"] 구조에서 실제 텍스트를 꺼내옵니다. 편집 모드(EditRole)일 때는 PyQt가 에러를 내지 않도록 무조건 문자열(str)로 변환해서 반환합니다.
        """
        if role in [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole]:
            val = self._data[row].get("data", {}).get(col_name, {}).get("value", "")
            return str(val) if role == Qt.ItemDataRole.EditRole else val

        """
        4. 고유 Row ID 추출 (Custom Role)
        이유: 화면에 텍스트로 보여주진 않지만, 프로그램 내부적으로 "이 셀이 속한 행의 DB Primary Key(row_id)가 뭐야?"라고 물어볼 때 사용합니다. (예: 우클릭해서 행 삭제, 복사/붙여넣기 시 행 타겟팅)
        UserRole은 개발자가 임의로 지정해 쓸 수 있는 커스텀 역할이며, 여기서 + 2는 고유 ID를 가져오기로 한 개발자 간의 약속입니다.
        """
        if role == Qt.ItemDataRole.UserRole + 2: return self._data[row].get("row_id")
        
        """
        5. 배경색 칠하기 (BackgroundRole)
        BackgroundRole: 셀의 배경색을 그릴 때 요청됩니다.
역할: 셀 데이터 안에 is_overwrite 플래그가 True로 켜져 있는지 확인합니다. 사용자가 이 셀을 직접 수정했거나 엑셀에서 붙여넣기를 해서 "변경사항이 발생한 셀" 이라면, 배경을 주황색("#BD6031")으로 칠해서 사용자에게 시각적으로 알려주는 역할을 합니다.
        """
        if role == Qt.ItemDataRole.BackgroundRole:
            if self._data[row].get("data", {}).get(col_name, {}).get("is_overwrite"):
                from PySide6.QtGui import QColor
                return QColor("#BD6031")

        """
        요약하자면: 이 코드는 화면에 그릴 때 이 셀이 생성일자면 날짜를 주고, 일반 텍스트면 텍스트를 주고, 내부적으로 ID를 물어보면 ID를 주고,
        수정된 셀이면 배경을 주황색으로 칠해줘 라고 뷰(View)에게 응답하는 핵심 분기점입니다.
        """
        return None

    def jump_to_id(self, row_id: str):
        """지정된 ID 위치로 최우선 점프 로딩을 수행합니다."""
        ctx = FetchContext(source="jump", params={"target_row_id": row_id})
        self.request_fetch(ctx)

    def canFetchMore(self, parent=QModelIndex()) -> bool:
        # 노출된 행이 전체 행보다 적으면 더 가져올 수 있음
        return not self._fetching and (self._first_fetch or self._exposed_rows < self._total_count)

    def request_fetch(self, ctx: FetchContext):
        """[Phase 1] 중앙 집중화된 페칭 요청 통제 메서드"""
        if self._fetching or not self._columns:
            self._pending_fetch_ctx = ctx
            return
        self._active_fetch_ctx = ctx
        self.fetchMore()

    def fetchMore(self, parent=QModelIndex()):
        # 1. 스냅샷: 현재 로딩 중인지 확인
        if not self._active_fetch_ctx:
            self._active_fetch_ctx = FetchContext(source="scroll")
            
        ctx = self._active_fetch_ctx
        is_jump_request = (ctx.source == "jump") or ("skip" in ctx.params)
        is_batch = (ctx.source == "batch")
        is_total = (ctx.source == "total_count")
        
        target_rid = ctx.params.get("target_row_id") if ctx.source == "jump" else None
        skip = ctx.params.get("skip")
        
        # [Fix] 점프/배치/카운트 요청 시에는 일반 fetching 가드를 무시하거나 중단하고 최우선 처리
        if self._fetching and not (is_jump_request or is_batch or is_total):
            return

        # [Safety] 검색 결과가 0건인 것이 확정된 경우(첫 페치 이후) 추가 진행 차단
        # 단, 순수 점프 요청(ctx.source == "jump")은 대상 행이 필터링에 걸렸는지 서버에서 확인해야 하므로 통과시킵니다.
        is_strict_jump = (ctx.source == "jump")
        if not self._first_fetch and self._total_count == 0 and not is_total and not is_strict_jump:
            self._active_fetch_ctx = None
            return
            
        if is_jump_request and skip is not None:
            # 점프 대상이 현재 노출 범위를 넘어선다면 미리 공간 확보 (Shell Extension)
            safe_limit = skip + self._chunk_size
            if self._total_count > 0:
                safe_limit = min(safe_limit, self._total_count)
                
            if safe_limit > self._exposed_rows:
                self.beginInsertRows(QModelIndex(), self._exposed_rows, safe_limit - 1)
                self._exposed_rows = safe_limit
                if len(self._data) < self._exposed_rows:
                    self._data.extend([None] * (self._exposed_rows - len(self._data)))
                self.endInsertRows()
                self.count_changed.emit(self._exposed_rows, self.loaded_count, self._total_count)

        elif is_batch:
            # [Phase 73.10] 일괄 로딩 전용 확장 로직
            self._batch_fetching = True
            count = ctx.params.get("count", 1000)
            remaining = self._total_count - self._exposed_rows
            increment = min(count, remaining)
            if increment > 0:
                self.beginInsertRows(QModelIndex(), self._exposed_rows, self._exposed_rows + increment - 1)
                self._exposed_rows += increment
                if len(self._data) < self._exposed_rows:
                    self._data.extend([None] * (self._exposed_rows - len(self._data)))
                self.endInsertRows()
                self.count_changed.emit(self._exposed_rows, self.loaded_count, self._total_count)
                # 배치 모드에서는 skip을 현재 서버 fetch 카운트로 고정
                skip = self._server_fetched_count
            else:
                self.status_message_requested.emit("마지막 행입니다.")
                self.batch_fetch_finished.emit()
                self._finalize_fetch()
                return

        elif is_total:
            # 카운트 갱신 모드에서는 확장 로직 스킵
            pass

        elif not is_jump_request and not self._first_fetch:
            # 일반 스크롤 확장 (기존 로직 유지)
            remaining = self._total_count - self._exposed_rows
            increment = min(self._chunk_size, remaining)
            if increment > 0:
                self.beginInsertRows(QModelIndex(), self._exposed_rows, self._exposed_rows + increment - 1)
                self._exposed_rows += increment
                if len(self._data) < self._exposed_rows:
                    self._data.extend([None] * (self._exposed_rows - len(self._data)))
                self.endInsertRows()
                self.count_changed.emit(self._exposed_rows, self.loaded_count, self._total_count)
            self._active_fetch_ctx = None # [Fix] 디버거 UI 잔상 제거
            return

        # 3. 데이터 로딩 (Viewport Request Only)
        if self._fetching and not (is_jump_request or is_batch or is_total): return
        
        # 타이머 중지 (명시적 호출 시)
        if self._jump_timer.isActive(): self._jump_timer.stop()
        
        self._fetching = True 
        self._fetch_scheduled = False
        self._fetch_start_time = time.time() # [신규] 페칭 시작 시간 기록
        
        req_skip = skip if skip is not None else 0
        if target_rid: self._last_jump_target = target_rid # [DEBUG] 보존
        
        print(f"[DEBUG-Model] fetchMore starting. skip={req_skip}, chunk={self._chunk_size}, is_jump={is_jump_request}, is_batch={is_batch}, is_total={is_total}, target={target_rid}")
        
        self._active_target_skip = req_skip
        
        order = "updated_at" if self._sort_latest else "id"
        desc = "true" if self._sort_latest else "false"
        
        # [Fix] 요청 타입에 따른 URL 및 파라미터 분기
        import urllib.parse
        cols_str = self._search_cols if self._search_cols else ",".join(self._columns)
        
        if is_total:
            url = f"{self.endpoint_url}?skip=0&limit=1&order_by={order}&order_desc={desc}&q={urllib.parse.quote(self._search_query)}&cols={urllib.parse.quote(cols_str)}"
            worker = ApiFetchWorker(url, session_id=self._active_fetch_ctx.session_id)
            worker.signals.finished.connect(self._on_total_refresh_finished)
            worker.signals.error.connect(self._on_fetch_error)
            QThreadPool.globalInstance().start(worker)
            return

        # [Fix] 배치 모드일 경우 노출 범위까지 채우도록 limit 계산
        if is_batch:
            limit = self._exposed_rows - req_skip
        else:
            limit = self._chunk_size
            
        if target_rid:
            limit = 100 # [Ultimate Optimization] 점프 시에는 뷰포트만 채우면 되므로 100개만 초고속 인출
        
        url = f"{self.endpoint_url}?skip={req_skip}&limit={limit}&order_by={order}&order_desc={desc}"
        if self._search_query:
            import urllib.parse
            target_cols = self._search_cols if self._search_cols else ",".join(self._columns)
            url += f"&q={urllib.parse.quote(self._search_query)}&cols={urllib.parse.quote(target_cols)}"
        
        if target_rid:
            url += f"&target_row_id={target_rid}"
            
        print(f"[DEBUG-Model] Request URL: {url}")
        session_id_to_use = self._active_fetch_ctx.session_id if self._active_fetch_ctx else self._search_session_id
        worker = ApiFetchWorker(url, session_id=session_id_to_use)
        worker.signals.finished.connect(self._on_fetch_finished)
        worker.signals.error.connect(self._on_fetch_error)
        QThreadPool.globalInstance().start(worker)

    def fetch_batch(self, count: int = 1000):
        """특정 개수(기본 1000개)만큼의 데이터를 한꺼번에 가져오고 노출 범위를 확장합니다."""
        self.request_fetch(FetchContext(source="batch", params={"count": count}))

    def _on_fetch_finished(self, result):
        # 1. 세션 검증
        resp_session = result.get("_session_id")
        if resp_session and self._active_fetch_ctx and resp_session != self._active_fetch_ctx.session_id:
            print(f"[Model] Discarding stale session result: {resp_session} != {self._active_fetch_ctx.session_id}")
            # 세션 다르면 그냥 아웃. 현재 페치한건 버려짐
            return

        # 2. 메타데이터 업데이트
        total = result.get("total", 0)
        self._set_total_count(total) #서버단 total 잘되어 있어야함. 디버깅 시 체크
        new = result.get("data", []) #신규 데이터 확인
        
        # [Fix] 서버 캐싱 등으로 인해 total_count가 실제 행 개수보다 크게 산정되어 있을 때,
        # 없는 데이터를 계속 요청하는 무한 스크롤 페치 루프를 방지합니다.
        req_skip = result.get("skip", getattr(self, '_active_target_skip', 0))
        if not new and req_skip < self._total_count: #skip부터 새 데이터가 없음. total은 적어도 skip 이하.
            print(f"[Fetch-Correction] Received empty data at skip {req_skip}. Shrinking total_count from {self._total_count} to {req_skip}.")
            self._set_total_count(req_skip) #일단 skip으로 total 설정. 진정한 동기화는 아닌듯?
            self._finalize_fetch()
            return

        # 3. 데이터 주입 (Jump Mode vs Normal Mode)
        calc_skip = result.get("calculated_skip")
        t_offset = result.get("target_offset")

        if calc_skip is not None: #점프 모드, 서버에서 타겟 skip 계산해서 보내줌.
            # [Validation] 서버에서 타겟 행을 찾지 못한 경우 (삭제 등)
            if t_offset == -1:
                print("[Model] Target row not found in database (likely deleted).")
                self._finalize_fetch()
                return

            try:
                target_limit = calc_skip + len(new)
                
                # [DEBUG] Check if the target row is actually in 'new'
                target_rid = self._pending_target_row_id or getattr(self, '_last_jump_target', None) #점프 위해 보낸 row_id
                if target_rid:
                    found_in_new = False
                    for idx_in_new, r_obj in enumerate(new): # 서버에서 계산 후 보내온 데이터에 row_id가 있는지 확인
                        if str(r_obj.get("row_id")) == target_rid:
                            print(f"[DEBUG-State] Found target {target_rid} in 'new' at local index {idx_in_new} (absolute {calc_skip + idx_in_new})")
                            found_in_new = True
                            break
                    if not found_in_new: #없으면?
                        print(f"[DEBUG-State] CRITICAL: Target {target_rid} NOT FOUND in 'new'! (Fetched 100 rows around offset {calc_skip})")
                        # Dump first and last item for context
                        if new:
                            print(f"  - First item: {new[0].get('row_id')}")
                            print(f"  - Last item: {new[-1].get('row_id')}")
                
                if target_limit > self._exposed_rows:
                    self.beginInsertRows(QModelIndex(), self._exposed_rows, target_limit - 1)
                    if len(self._data) < target_limit:
                        self._data.extend([None] * (target_limit - len(self._data)))
                    self._exposed_rows = target_limit
                    self.endInsertRows() #점프 할 곳 까지 일단 표 늘림.
                else:
                    if len(self._data) < target_limit:
                        self._data.extend([None] * (target_limit - len(self._data)))
                
                for i, r in enumerate(new):
                    self._data[calc_skip + i] = r # 가져온 데이터 채워넣기
                
                self._server_fetched_count = max(self._server_fetched_count, target_limit)
                self.dataChanged.emit(self.index(calc_skip, 0), self.index(target_limit - 1, len(self._columns) - 1)) #qt 객체 업데이트
                self._update_row_id_map(new, calc_skip) # id 매핑 업데이트
                
            except Exception as e:
                import traceback
                print(f"[DEBUG-State] Exception in jump injection: {e}")
                traceback.print_exc()
            finally:
                self._finalize_fetch()
            return

        # [Normal Mode Logic]
        skip = getattr(self, '_active_target_skip', 0)
        
        if self._first_fetch:
            self.beginResetModel()
            self._data = new
            self._exposed_rows = len(new)
            self._loaded_count = len(new)
            self._server_fetched_count = len(new)
            self._first_fetch = False
            self.endResetModel()
            
            # [Fix] 첫 페치 응답에 포함된 전체 개수로 모델 상태 동기화
            resp_total = result.get("total", 0)
            self._set_total_count(resp_total)
            
            self._finalize_fetch()
            return

        #[TASK] 커서 기반 페칭으로 로직 변경 필요
        if new:
            # ID 기반 중복 보정 및 삽입
            for i, r in enumerate(new):
                rid = str(r.get("row_id"))
                existing_idx = self._row_id_map.get(rid)
                target_idx = skip + i
                if existing_idx is not None and existing_idx != target_idx:
                    if existing_idx < len(self._data): self._data[existing_idx] = r
                    if target_idx >= len(self._data): self._data.extend([None]*(target_idx - len(self._data) + 1))
                    self._data[target_idx] = {"_is_duplicate": True, "row_id": rid}
                    continue
                
                # 정상 삽입 (데이터가 버퍼 범위를 넘어서면 확장)
                if target_idx >= len(self._data):
                    self._data.extend([None] * (target_idx - len(self._data) + 1))
                
                # [Optimization] 이전에 None이었던 자리가 채워지는 경우에만 카운트 증가
                if self._data[target_idx] is None:
                    self._loaded_count += 1
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
            elif target_exposed < self._exposed_rows and (skip + len(new) >= self._total_count or len(new) < result.get("limit", self._chunk_size)):
                # [Fix] 가짜 None 공간 제거 (Shrink)
                diff = self._exposed_rows - target_exposed
                self.beginRemoveRows(QModelIndex(), target_exposed, self._exposed_rows - 1)
                self._exposed_rows = target_exposed
                self.endRemoveRows()
                
            self.count_changed.emit(self._exposed_rows, self.loaded_count, self._total_count)
            self.dataChanged.emit(self.index(skip, 0), self.index(skip + len(new) - 1, len(self._columns) - 1))
            if skip == self._server_fetched_count: self._server_fetched_count += len(new)
            
        # [Fix] 매 응답마다 전체 개수 동기화하여 UI 정합성 유지
        resp_total = result.get("total")
        if resp_total is not None:
            self._set_total_count(resp_total)
        
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
        self._update_row_id_map()
        self._finalize_fetch()
        
    def _on_fetch_error(self, err): 
        print(f"[Model] Fetch error: {err}")
        self._finalize_fetch()

    def _finalize_fetch(self):
        """[Phase 2] 페칭 종료 시 상태 초기화 및 대기 중인 컨텍스트 실행을 관리합니다."""
        self._fetching = False
        self.fetch_finished.emit()
        self._active_fetch_ctx = None
        if self._batch_fetching:
            self._batch_fetching = False
            self.batch_fetch_finished.emit() #그냥 1k 로드 버튼 초기화용
        if self._pending_fetch_ctx:
            next_ctx = self._pending_fetch_ctx
            self._pending_fetch_ctx = None
            self.request_fetch(next_ctx) #펜딩 있으면 바로 이어서 실행

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
                total_size = int(response.headers.get('Content-Length') or response.headers.get('X-Estimated-Content-Length') or -1)
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

