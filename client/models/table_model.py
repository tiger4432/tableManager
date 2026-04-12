from PySide6.QtCore import QAbstractTableModel, Qt, QModelIndex, QRunnable, QThreadPool, Signal, Slot, QObject, QPersistentModelIndex, QThread

class WorkerSignals(QObject):
    finished = Signal(dict)
    error = Signal(str)

class ApiFetchWorker(QRunnable):
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

class ApiUpdateWorker(QRunnable):
    def __init__(self, url, payload, index, col_name):
        super().__init__()
        self.url = url
        self.payload = payload
        self.index = index
        self.col_name = col_name
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        import urllib.request
        import json
        data = json.dumps(self.payload).encode('utf-8')
        req = urllib.request.Request(self.url, data=data, method="PUT", headers={'Content-Type': 'application/json'})
        
        try:
            with urllib.request.urlopen(req) as response:
                res = json.loads(response.read().decode())
                if res.get("status") == "success":
                    self.signals.finished.emit({
                        "status": "success",
                        "index": self.index,
                        "col_name": self.col_name,
                        "value": self.payload["value"]
                    })
                else:
                    self.signals.error.emit(res.get("status", "unknown error"))
        except Exception as e:
            self.signals.error.emit(str(e))

class BatchApiUpdateWorker(QRunnable):
    def __init__(self, url, payloads):
        super().__init__()
        self.url = url
        self.payloads = payloads
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        import urllib.request
        import json
        data = json.dumps({"updates": self.payloads}).encode('utf-8')
        req = urllib.request.Request(self.url, data=data, method="PUT", headers={'Content-Type': 'application/json'})
        
        try:
            with urllib.request.urlopen(req) as response:
                res = json.loads(response.read().decode())
                if res.get("status") == "success":
                    self.signals.finished.emit({"status": "success", "updates": self.payloads})
                else:
                    self.signals.error.emit(res.get("status", "unknown error"))
        except Exception as e:
            self.signals.error.emit(str(e))

class WsListenerThread(QThread):
    """
    WebSocketExpert 스킬 규칙 준수:
    - QThread 상속: recv() 블로킹 호출을 안전하게 백그라운드 격리
    - Signal(dict): 파싱된 JSON 페이로드를 메인 스레드 Slot으로 전달
    """
    message_received = Signal(dict)
    connection_error = Signal(str)

    def __init__(self, ws_url: str, parent=None):
        super().__init__(parent)
        self.ws_url = ws_url
        self._running = True

    def run(self):
        import json
        try:
            from websockets.sync.client import connect
        except ImportError:
            self.connection_error.emit("websockets 패키지가 설치되지 않았습니다. `pip install websockets`를 실행하세요.")
            return

        while self._running:
            try:
                with connect(self.ws_url) as ws:
                    print(f"[WsListenerThread] Connected to {self.ws_url}")
                    while self._running:
                        try:
                            raw = ws.recv(timeout=5.0)
                            data = json.loads(raw)
                            self.message_received.emit(data)
                        except TimeoutError:
                            # 주기적으로 _running 플래그를 확인하기 위한 타임아웃
                            continue
            except Exception as e:
                if self._running:
                    self.connection_error.emit(str(e))
                    # 재연결 대기 (3초)
                    self.msleep(3000)

    def stop(self):
        self._running = False
        self.quit()
        self.wait()


class ApiLazyTableModel(QAbstractTableModel):
    """
    QAbstractTableModel with lazy loading from a REST API endpoint.
    Retrieves data in chunks when the user scrolls near the bottom.
    """
    # Agent D v2: WS 브로드캐스트 전용 Signal (source='remote' 컨텍스트 포함)
    ws_data_changed = Signal(dict)  # {"row_id": ..., "column_name": ..., "value": ..., "source": "remote"}
    def __init__(self, table_name: str, base_api_url: str = "http://127.0.0.1:8000"):
        super().__init__()
        self.table_name = table_name
        self.base_api_url = base_api_url
        self.endpoint_url = f"{base_api_url}/tables/{table_name}/data"
        self._data = []
        self._total_count = 0 # 서버 첫 응답 시 실제 값으로 갱신됨
        self._columns = ["id", "name", "status"]
        self._chunk_size = 50
        self._fetching = False
        self._first_fetch = True

        # WebSocket 리스너 스레드 (외부에서 start_ws_listener() 호출)
        self._ws_thread: WsListenerThread | None = None

    def start_ws_listener(self, ws_url: str = None):
        """WebSocket 브로드캐스트 수신 스레드를 시작합니다."""
        if self._ws_thread and self._ws_thread.isRunning():
            return
        url = ws_url or self.base_api_url.replace("http", "ws") + "/ws"
        self._ws_thread = WsListenerThread(url)
        self._ws_thread.message_received.connect(self._on_websocket_broadcast)
        self._ws_thread.connection_error.connect(
            lambda err: print(f"[WsListenerThread] Error: {err}")
        )
        self._ws_thread.start()
        print(f"[WsListenerThread] Listener started for {url}")

    def stop_ws_listener(self):
        """WebSocket 리스너 스레드를 안전하게 종료합니다."""
        if self._ws_thread:
            self._ws_thread.stop()
            self._ws_thread = None

    def rowCount(self, parent=QModelIndex()) -> int:
        return self._total_count

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self._columns)

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        # allow editable
        return super().flags(index) | Qt.ItemFlag.ItemIsEditable

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid():
            return False
            
        if role == Qt.ItemDataRole.EditRole:
            row = index.row()
            col = index.column()
            
            if row >= len(self._data):
                return False
                
            cell_data = self._data[row].get("data", {})
            col_name = self._columns[col]
            row_id = self._data[row].get("row_id")
            
            if row_id is None:
                return False
                
            persistent_index = QPersistentModelIndex(index)
            url = f"{self.endpoint_url.replace('/data', '/cells')}"
            payload = {
                "row_id": row_id,
                "column_name": col_name,
                "value": value
            }
            
            # 비동기 요청을 위해 QRunnable 기반 Worker 사용
            worker = ApiUpdateWorker(url, payload, persistent_index, col_name)
            worker.signals.finished.connect(self._on_update_finished)
            worker.signals.error.connect(lambda err: print(f"Failed to update cell via API: {err}"))
            
            QThreadPool.globalInstance().start(worker)
            
            # 서버 업데이트 시작 전, 즉시 입력 이벤트를 허용
            return True
                
        return False

    def bulkUpdateData(self, start_row, start_col, parsed_data_matrix):
        payloads = []
        for r_idx, row_values in enumerate(parsed_data_matrix):
            model_row = start_row + r_idx
            if model_row >= len(self._data): break
            row_id = self._data[model_row].get("row_id")
            if row_id is None: continue
            
            for c_idx, value in enumerate(row_values):
                model_col = start_col + c_idx
                if model_col >= len(self._columns): break
                col_name = self._columns[model_col]
                
                payloads.append({
                    "row_id": row_id,
                    "column_name": col_name,
                    "value": value,
                    "row_index": model_row,
                    "col_index": model_col
                })
        
        if not payloads:
            return
            
        url = f"{self.endpoint_url.replace('/data', '/cells/batch')}"
        worker = BatchApiUpdateWorker(url, payloads)
        worker.signals.finished.connect(self._on_batch_update_finished)
        worker.signals.error.connect(lambda err: print(f"Failed to batch update: {err}"))
        
        QThreadPool.globalInstance().start(worker)

    def _on_batch_update_finished(self, result: dict):
        updates = result.get("updates", [])
        if not updates: return
        
        min_row, max_row = float('inf'), -1
        min_col, max_col = float('inf'), -1
        
        for u in updates:
            r = u["row_index"]
            c = u["col_index"]
            val = u["value"]
            col_name = u["column_name"]
            
            cell_data = self._data[r].get("data", {})
            if col_name not in cell_data:
                cell_data[col_name] = {}
            cell_data[col_name]["value"] = val
            cell_data[col_name]["is_overwrite"] = True
            
            min_row = min(min_row, r)
            max_row = max(max_row, r)
            min_col = min(min_col, c)
            max_col = max(max_col, c)
            
        if min_row <= max_row and min_col <= max_col:
            top_left = self.index(min_row, min_col)
            bottom_right = self.index(max_row, max_col)
            self.dataChanged.emit(top_left, bottom_right, [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.BackgroundRole])

    # -------------------------------------------------------------------------
    # WebSocket 브로드캐스트 수신 슬롯 (WebSocketExpert 스킬 규칙 B)
    # -------------------------------------------------------------------------
    @Slot(dict)
    def _on_websocket_broadcast(self, data: dict):
        """
        서버 WebSocket 브로드캐스트 수신 Slot.
        - cell_update / batch_cell_update 이벤트를 처리합니다.
        - row_id 기반으로 self._data 버퍼를 검색하여 값과 is_overwrite 플래그를 갱신합니다.
        - 변경된 범위에 dataChanged.emit()을 호출하여 노란색 배경을 즉시 렌더링합니다.
        """
        event = data.get("event")
        table_name = data.get("table_name", "")

        # 자신이 발행한 이벤트가 자신에게 돌아온 경우도 처리 (타 클라이언트 포함)
        if table_name and table_name != self.table_name:
            return

        if event == "cell_update":
            updates = [{
                "row_id": data.get("row_id"),
                "column_name": data.get("column_name"),
                "value": data.get("value"),
                "is_overwrite": data.get("is_overwrite", True)
            }]
        elif event == "batch_cell_update":
            updates = data.get("updates", [])
        elif event == "row_delete":
            row_id = data.get("row_id")
            if not row_id:
                return
            row_id_map = self._build_row_id_map()
            row_idx = row_id_map.get(row_id)
            if row_idx is not None:
                self.beginRemoveRows(QModelIndex(), row_idx, row_idx)
                del self._data[row_idx]
                self._total_count -= 1
                self.endRemoveRows()
            return  # 삭제 처리는 여기서 종료
        elif event == "row_create":
            row_data = data.get("data")
            if not row_data:
                return
            
            # 리스트 맨 앞에 삽입 (Agent E v4 지침)
            self.beginInsertRows(QModelIndex(), 0, 0)
            self._data.insert(0, row_data)
            self._total_count += 1
            self.endInsertRows()
            return
        else:
            return  # 알 수 없는 이벤트 무시

        if not updates:
            return

        # row_id → 버퍼 인덱스 맵 (lazy build)
        row_id_map = self._build_row_id_map()

        changed_indices = []  # (row_idx, col_idx) 목록

        for u in updates:
            row_id = u.get("row_id")
            col_name = u.get("column_name")
            value = u.get("value")

            row_idx = row_id_map.get(row_id)
            if row_idx is None:
                continue  # 아직 로드되지 않은 행 → 추후 fetchMore 시 반영됨

            try:
                col_idx = self._columns.index(col_name)
            except ValueError:
                continue  # 알 수 없는 컬럼 무시

            cell_data = self._data[row_idx].get("data", {})
            if col_name not in cell_data:
                cell_data[col_name] = {}
            cell_data[col_name]["value"] = value
            cell_data[col_name]["is_overwrite"] = True

            changed_indices.append((row_idx, col_idx))

        if not changed_indices:
            return

        # 변경 범위 계산 후 dataChanged 일괄 emit
        rows = [r for r, _ in changed_indices]
        cols = [c for _, c in changed_indices]
        top_left = self.index(min(rows), min(cols))
        bottom_right = self.index(max(rows), max(cols))
        self.dataChanged.emit(
            top_left, bottom_right,
            [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.BackgroundRole]
        )

        # Agent D v2: 각 업데이트에 대해 ws_data_changed Signal 방출 (히스토리 패널용)
        for u in updates:
            self.ws_data_changed.emit({**u, "source": "remote"})

    def _build_row_id_map(self) -> dict:
        """현재 로드된 self._data의 row_id → 버퍼 인덱스 맵을 반환합니다."""
        return {row.get("row_id"): idx for idx, row in enumerate(self._data)}

    def _on_update_finished(self, result: dict):
        p_index = result["index"]
        if not p_index.isValid():
            return
            
        row = p_index.row()
        col = p_index.column()
        col_name = result["col_name"]
        value = result["value"]
        
        if row < len(self._data):
            cell_data = self._data[row].get("data", {})
            if col_name not in cell_data:
                cell_data[col_name] = {}
            cell_data[col_name]["value"] = value
            cell_data[col_name]["is_overwrite"] = True
            
            # BackgroundRole 과 DisplayRole 을 갱신하여 UI 반영
            m_index = self.index(row, col)
            self.dataChanged.emit(m_index, m_index, [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.BackgroundRole])

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
            
        row = index.row()
        col = index.column()

        # If data is not yet loaded for this row, display placeholder
        if row >= len(self._data):
            if role == Qt.ItemDataRole.DisplayRole:
                return "Loading..."
            return None

        cell_data = self._data[row].get("data", {})
        col_name = self._columns[col]
        
        # Display the actual value
        if role == Qt.ItemDataRole.DisplayRole:
            item = cell_data.get(col_name, {})
            return item.get("value", "")
            
        # Highlight logic if is_overwrite is True
        if role == Qt.ItemDataRole.BackgroundRole:
            item = cell_data.get(col_name, {})
            if item.get("is_overwrite"):
                from PySide6.QtGui import QColor
                return QColor("#FF8C00") # Amber background for manually overwritten items

        return None

    def canFetchMore(self, parent=QModelIndex()) -> bool:
        if self._fetching:
            return False
        if self._first_fetch:
            return True
        return len(self._data) < self._total_count

    def fetchMore(self, parent=QModelIndex()):
        if self._fetching:
            return
            
        self._fetching = True
        skip = len(self._data)
        limit = self._chunk_size
        
        url = f"{self.endpoint_url}?skip={skip}&limit={limit}"
        
        worker = ApiFetchWorker(url)
        worker.signals.finished.connect(self._on_fetch_finished)
        worker.signals.error.connect(self._on_fetch_error)
        
        QThreadPool.globalInstance().start(worker)

    def _on_fetch_finished(self, result: dict):
        self._first_fetch = False
        new_data = result.get("data", [])
        self._total_count = result.get("total", len(self._data) + len(new_data))
        
        if new_data:
            self.beginInsertRows(QModelIndex(), len(self._data), len(self._data) + len(new_data) - 1)
            self._data.extend(new_data)
            self.endInsertRows()
            
        self._fetching = False

    def _on_fetch_error(self, err: str):
        print(f"Fetch error: {err}")
        self._fetching = False

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self._columns[section].upper()
        return super().headerData(section, orientation, role)
