from PySide6.QtCore import QAbstractTableModel, Qt, QModelIndex, QRunnable, QThreadPool, Signal, Slot, QObject, QPersistentModelIndex, QThread
import config

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

class ApiSchemaWorker(QRunnable):
    def __init__(self, url):
        super().__init__()
        self.url = url
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        print('ApiSchemaWorker 실행')
        import urllib.request
        import json
        try:
            req = urllib.request.Request(self.url)
            with urllib.request.urlopen(req, timeout=5.0) as response:
                result = json.loads(response.read().decode())
                self.signals.finished.emit(result)
                print(result)
        except Exception as e:
            print('ApiSchemaWorker Error:',e)
            self.signals.error.emit(str(e))

class ApiSingleRowFetchWorker(QRunnable):
    """특정 row_id의 전체 데이터를 서버에서 단건 조회합니다."""
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
                # result는 row 객체 (row_id, data 등 포함)
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

    def __init__(self, ws_url: str = config.WS_BASE_URL, parent=None):
        super().__init__(parent)
        self.ws_url = ws_url
        self._running = True
        self._ws = None # Agent D v6: Store current ws object

    def run(self):
        import json
        try:
            from websockets.sync.client import connect
        except ImportError:
            self.connection_error.emit("websockets 패키지가 설치되지 않았습니다. `pip install websockets`를 실행하세요.")
            return

        while self._running:
            try:
                print(f"[WsListenerThread] Attempting to connect to {self.ws_url}...")
                with connect(self.ws_url, open_timeout=5.0) as ws:
                    self._ws = ws
                    print(f"[WsListenerThread] SUCCESS: Connected to {self.ws_url}")
                    while self._running:
                        try:
                            # Reduced timeout for better responsiveness to stop signal
                            raw = ws.recv(timeout=1.0)
                            data = json.loads(raw)
                            self.message_received.emit(data)
                        except TimeoutError:
                            continue
                        except Exception as inner_e:
                            if self._running:
                                print(f"[WsListenerThread] Receive error: {inner_e}")
                            break
            except Exception as e:
                if self._running:
                    error_msg = f"Connection failed: {str(e)}"
                    print(f"[WsListenerThread] {error_msg}")
                    self.connection_error.emit(error_msg)
                    print("[WsListenerThread] Retrying in 3 seconds...")
                    self.msleep(3000)
            finally:
                self._ws = None
                if self._running:
                    print(f"[WsListenerThread] Session finished for {self.ws_url}")

    def stop(self):
        self._running = False
        # Agent D v6: Explicitly close the ws to unblock recv() immediately
        if self._ws:
            try:
                self._ws.close()
            except:
                pass
        self.quit()
        self.wait()


class ApiLazyTableModel(QAbstractTableModel):
    """
    QAbstractTableModel with lazy loading from a REST API endpoint.
    Retrieves data in chunks when the user scrolls near the bottom.
    """
    # Agent D v2: WS 브로드캐스트 전용 Signal (source='remote' 컨텍스트 포함)
    ws_data_changed = Signal(dict)  # {"row_id": ..., "column_name": ..., "value": ..., "source": "remote"}
    batch_ws_data_changed = Signal(list) # List of cell-level update dicts
    row_created_ws = Signal(dict)   # {"row_id": ..., "table_name": ..., "data": ...}
    row_deleted_ws = Signal(dict)   # Agent D v13: 행 삭제 시그널 추가
    def __init__(self, table_name: str, base_api_url: str = config.API_BASE_URL):
        super().__init__()
        self.table_name = table_name
        self.base_api_url = base_api_url
        self.endpoint_url = config.get_table_data_url(table_name)
        self._data = []
        self._total_count = 0 # 서버 첫 응답 시 실제 값으로 갱신됨
        self._columns = ["id", "name", "status"]
        self._chunk_size = 50
        self._fetching = False
        self._first_fetch = True
        self._search_query = "" # 서버 사이드 검색어

        self._chunk_size = 50
        self._fetching = False
        self._first_fetch = True
        self._is_processing_remote = False # Agent D v5: Prevent duplicate history logging
        self._fetching_row_ids = set() # Agent D v8: Track rows being fetched to prevent duplicates

    def update_columns(self, columns: list[str]):
        """컬럼 정보를 동적으로 업데이트하고 모델을 리셋합니다."""
        print(f"[Model] Updating columns for {self.table_name}: {columns}")
        self.beginResetModel()
        self._columns = columns
        self.endResetModel()

    def set_search_query(self, query: str):
        """서버 사이드 검색어를 설정하고 모델을 리셋하여 다시 페칭합니다."""
        if self._search_query == query:
            return
            
        print(f"[Model] Setting search query for {self.table_name}: {query}")
        self.beginResetModel()
        self._search_query = query
        self._data = []
        self._total_count = 0
        self._first_fetch = True
        self.endResetModel()
        
        # 즉시 첫 페이지 요청
        self.fetchMore()

    def rowCount(self, parent=QModelIndex()) -> int:
        return self._total_count

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self._columns)

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        
        # Agent D v12: 시스템 컬럼(created_at, updated_at 등)은 수정 불가 처리
        col_name = self._columns[index.column()]
        if col_name in ["created_at", "updated_at", "row_id", "id", "updated_by"]:
            return Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
            
        # allow editable for business columns
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
            
            # Agent D v12: 시스템 컬럼 수정 방어 (setData 호출 수준에서 차단)
            if col_name in ["created_at", "updated_at", "row_id", "id", "updated_by"]:
                return False
                
            # Agent D v15: 값이 동일할 경우 업데이트 무시
            current_item = cell_data.get(col_name, {})
            current_value = current_item.get("value", "")
            if str(current_value) == str(value):
                return True # 변경 사항 없으므로 성공으로 간주하되 API는 미호출
                
            row_id = self._data[row].get("row_id")
            
            if row_id is None:
                return False
                
            import os
            try:
                username = os.getlogin()
            except:
                username = "User"
                
            persistent_index = QPersistentModelIndex(index)
            url = config.get_cell_update_url(self.table_name)
            payload = {
                "row_id": row_id,
                "column_name": col_name,
                "value": value,
                "updated_by": f"Manual Fix ({username})"
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
                
                # Agent D v12: 시스템 컬럼은 페이스트(Bulk Update) 대상에서 제외
                if col_name in ["created_at", "updated_at", "row_id", "id", "updated_by"]:
                    continue
                    
                payloads.append({
                    "row_id": row_id,
                    "column_name": col_name,
                    "value": value,
                    "row_index": model_row,
                    "col_index": model_col
                })
        
        if not payloads:
            return
            
        url = config.get_batch_cell_update_url(self.table_name)
        worker = BatchApiUpdateWorker(url, payloads)
        worker.signals.finished.connect(self._on_batch_update_finished)
        worker.signals.error.connect(lambda err: print(f"Failed to batch update: {err}"))
        
        QThreadPool.globalInstance().start(worker)

    def _on_batch_update_finished(self, result: dict):
        """
        [고스트 밸류(Ghost Values) 해결]
        문제: 부상(Floating) 로직으로 인해 WebSocket 수신 시 행의 인덱스가 즉시 변경됨.
        원인: 배치 업데이트 완료 응답은 지연될 수 있으며, 응답 시점의 row_index는 이미 낡은(Stale) 정보일 수 있음.
        해결: 인덱스 기반의 로컬 수동 갱신을 중단하고, 모든 데이터/위치 동기화를 WebSocket 브로드캐스트로 일원화함.
        """
        # (Optional) 로컬 작업 UI 피드백(예: 프로그레스바 종료) 필요 시 여기에 작성
        pass

    # -------------------------------------------------------------------------
    # WebSocket 브로드캐스트 수신 슬롯 (WebSocketExpert 스킬 규칙 B)
    # -------------------------------------------------------------------------
    @Slot(dict)
    def _on_websocket_broadcast(self, data: dict):
        """
        서버 WebSocket 브로드캐스트 수신 Slot.
        """
        event = data.get("event")
        table_name = data.get("table_name", "")

        if table_name and table_name != self.table_name:
            return

        # [핵심 최적화] 원격 데이터 처리 중임을 표시하여 히스토리 패널의 개별 셀 로그 생성을 차단
        self._is_processing_remote = True
        try:
            if event == "cell_update":
                updates = [data]
            elif event == "batch_cell_update":
                updates = data.get("updates", [])
            elif event == "row_delete":
                row_id = data.get("row_id")
                if not row_id: return
                row_id_map = self._build_row_id_map()
                row_idx = row_id_map.get(row_id)
                if row_idx is not None:
                    self.beginRemoveRows(QModelIndex(), row_idx, row_idx)
                    del self._data[row_idx]
                    self._total_count -= 1
                    self.endRemoveRows()
                self.row_deleted_ws.emit(data)
                return
            elif event == "row_create":
                row_data = data.get("data")
                if not row_data: return
                self.beginInsertRows(QModelIndex(), 0, 0)
                self._data.insert(0, row_data)
                self._total_count += 1
                self.endInsertRows()
                self.row_created_ws.emit(data)
                return
            elif event == "batch_row_upsert":
                items = data.get("items", [])
                if not items: return
                
                all_cell_updates = []
                
                for item in items:
                    row_id = item.get("row_id")
                    is_new = item.get("is_new", False)
                    new_row_data_blob = item.get("data", {}) # This is the 'data' field containing cells
                    
                    # Normalize: WebSocket data should match Fetch data structure
                    normalized_row = self._normalize_row_data({
                        "row_id": row_id,
                        "table_name": self.table_name,
                        "data": new_row_data_blob
                    })

                    for col, cell_val in new_row_data_blob.items():
                        if isinstance(cell_val, dict) and "value" in cell_val:
                            all_cell_updates.append({
                                "row_id": row_id,
                                "column_name": col,
                                "value": cell_val["value"],
                                "is_overwrite": cell_val.get("is_overwrite", False),
                                "updated_by": cell_val.get("updated_by", "system"),
                                "source": "remote"
                            })

                    # Strict Deduplication: Remove any existing row with this ID before floating
                    row_id_map = self._build_row_id_map()
                    idx = row_id_map.get(row_id)
                    if idx is not None:
                        self._data.pop(idx)
                    
                    # Insert at top (Floating)
                    self._data.insert(0, normalized_row)
                    if idx is None and is_new:
                        self._total_count += 1

                self.beginResetModel()
                self.endResetModel()

                if all_cell_updates:
                    self.batch_ws_data_changed.emit(all_cell_updates)
                return
            else:
                return

            if not updates: return
            row_id_map = self._build_row_id_map()
            affected_rows = set()
            changed_indices = []
            log_updates = []

            for u in updates:
                row_id = u.get("row_id")
                col_name = u.get("column_name")
                value = u.get("value")

                row_idx = row_id_map.get(row_id)
                if row_idx is None:
                    if row_id not in self._fetching_row_ids:
                        self._fetching_row_ids.add(row_id)
                        fetch_url = config.get_single_row_url(self.table_name, row_id)
                        worker = ApiSingleRowFetchWorker(fetch_url)
                        worker.signals.finished.connect(self._on_remote_row_fetched)
                        worker.signals.error.connect(lambda e, rid=row_id: self._fetching_row_ids.discard(rid))
                        QThreadPool.globalInstance().start(worker)
                    continue
                
                affected_rows.add(row_id)
                try:
                    col_idx = self._columns.index(col_name)
                    cell_data = self._data[row_idx].get("data", {})
                    if col_name not in cell_data: cell_data[col_name] = {}
                    cell_data[col_name]["value"] = value
                    cell_data[col_name]["is_overwrite"] = u.get("is_overwrite", False)

                    if "updated_at" in u and "updated_at" in self._columns:
                        u_at = u.get("updated_at")
                        if "updated_at" not in cell_data:
                            cell_data["updated_at"] = {"is_overwrite": False, "updated_by": "system"}
                        cell_data["updated_at"]["value"] = u_at
                        changed_indices.append((row_idx, self._columns.index("updated_at")))
                    
                    if "updated_by" not in u: u["updated_by"] = data.get("updated_by", "system")
                    log_updates.append({**u, "source": "remote"})
                except: continue

            if log_updates:
                self.batch_ws_data_changed.emit(log_updates)

            if not changed_indices: return

            for row_id in affected_rows:
                # REBUILD map every time because indices shift on pop/insert
                self.beginMoveRows(QModelIndex(), 0, 0, QModelIndex(), 0) # Dummy to notify view of potential shift if needed? No.
                # Just use beginMoveRows for the actual move
                current_map = self._build_row_id_map()
                idx = current_map.get(row_id)
                if idx is not None and idx > 0:
                    self.beginMoveRows(QModelIndex(), idx, idx, QModelIndex(), 0)
                    self._data.insert(0, self._data.pop(idx))
                    self.endMoveRows()

            max_row = max([r for r, _ in changed_indices]) if changed_indices else 0
            self.dataChanged.emit(self.index(0, 0), self.index(max_row, len(self._columns)-1), [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.BackgroundRole])
        finally:
            self._is_processing_remote = False

    def _normalize_row_data(self, row: dict) -> dict:
        """
        [데이터 구조 비대칭 해결]
        Fetch 데이터(DataRowResponse)는 created_at 등이 최상위에 위치하나, 
        WebSocket 데이터는 data 맵 내부에만 있는 경우가 있음.
        이를 최상위로 끌어올려 모델 인덱싱 및 필터링 시 구조적 일관성을 확보함.
        """
        data_blob = row.get("data", {})
        
        # 1. 최상위에 created_at, updated_at이 없고 data 내부에 있다면 추출하여 주입
        if "created_at" not in row and "created_at" in data_blob:
            row["created_at"] = data_blob["created_at"].get("value")
        if "updated_at" not in row and "updated_at" in data_blob:
            row["updated_at"] = data_blob["updated_at"].get("value")
            
        return row

    def _build_row_id_map(self) -> dict:
        """현재 로컬 캐시된 데이터의 row_id와 인덱스 매핑을 생성합니다."""
        return {str(row.get("row_id")): idx for idx, row in enumerate(self._data)}

    def _on_remote_row_fetched(self, row_data: dict):
        row_id = str(row_data.get("row_id"))
        if row_id in self._fetching_row_ids:
            self._fetching_row_ids.remove(row_id)
            
        # Normalize and Deduplicate
        normalized_row = self._normalize_row_data(row_data)
        row_id_map = self._build_row_id_map()
        
        if row_id in row_id_map:
            # Already exists, just update and move to top
            idx = row_id_map[row_id]
            self._data[idx] = normalized_row
            if idx > 0:
                self.beginMoveRows(QModelIndex(), idx, idx, QModelIndex(), 0)
                self._data.insert(0, self._data.pop(idx))
                self.endMoveRows()
            return

        # Truly new to cache
        self._is_processing_remote = True
        try:
            self.beginInsertRows(QModelIndex(), 0, 0)
            self._data.insert(0, normalized_row)
            # Do NOT increment _total_count here because single fetch is typically for an existing row
            self.endInsertRows()
            self.dataChanged.emit(self.index(0, 0), self.index(0, len(self._columns)-1), [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.BackgroundRole])
        finally:
            self._is_processing_remote = False

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
                # Trigger fetch if not already fetching
                if not self._fetching:
                    from PySide6.QtCore import QTimer
                    # Use a timer to avoid calling fetchMore directly inside data() which can cause issues
                    QTimer.singleShot(0, self.fetchMore)
                return "Loading..."
            return None

        cell_data = self._data[row].get("data", {})
        col_name = self._columns[col]
        
        # Display the actual value or provide for Editor
        if role in [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole]:
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
        if self._search_query:
            import urllib.parse
            url += f"&q={urllib.parse.quote(self._search_query)}"
        
        worker = ApiFetchWorker(url)
        worker.signals.finished.connect(self._on_fetch_finished)
        worker.signals.error.connect(self._on_fetch_error)
        
        QThreadPool.globalInstance().start(worker)

    def _on_fetch_finished(self, result: dict):
        new_data = result.get("data", [])
        total = result.get("total", 0)
        
        if self._first_fetch:
            self.beginResetModel()
            self._total_count = total
            self._data = new_data
            self._first_fetch = False
            self.endResetModel()
        else:
            if new_data:
                # [고스트 행(Ghost Rows) 해결 - 기법 A: Deduplication on Fetch]
                # 문제: Floating으로 최상단에 자리잡은 행이 스크롤 페칭 시 하단에서 또 발견되는 현상.
                # 해결: 서버 청크를 추가하기 전, 이미 로컬 캐시에 부상해 있는 행은 전수 제외 처리.
                current_row_ids = {str(r.get("row_id")) for r in self._data}
                unique_new_data = [
                    r for r in new_data 
                    if str(r.get("row_id")) not in current_row_ids
                ]
                
                if unique_new_data:
                    start_row = len(self._data)
                    self._data.extend(unique_new_data)
                    
                    # 뷰에 신규 데이터 영역 갱신 알림
                    # Note: rowCount()는 이미 placeholder를 포함하므로 dataChanged만으로 충분
                    self.dataChanged.emit(
                        self.index(start_row, 0),
                        self.index(start_row + len(unique_new_data) - 1, len(self._columns) - 1),
                        [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.BackgroundRole]
                    )
            
        self._fetching = False

    def _on_fetch_error(self, err: str):
        print(f"Fetch error: {err}")
        self._fetching = False

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self._columns[section].upper()
        return super().headerData(section, orientation, role)
