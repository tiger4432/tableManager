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

class ApiGeneralUpdateWorker(QRunnable):
    """
    [통합 업데이트 워커]
    GeneralUpdateBatch 스키마를 사용하여 단건 및 배치 수정을 서버로 전송합니다.
    """
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
    """서버로 파일을 업로드하는 워커 (httpx 사용)"""
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
                # httpx.post로 multipart/form-data 전송
                with httpx.Client(timeout=30.0) as client:
                    response = client.post(self.url, files=files)
                    if response.status_code == 200:
                        self.signals.finished.emit(response.json())
                    else:
                        self.signals.error.emit(f"Server error: {response.status_code} - {response.text}")
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


class ApiDeleteWorker(QRunnable):
    """지정한 행들을 서버에서 삭제 요청하는 비동기 워커."""
    def __init__(self, url, row_ids, user_name="system"):
        super().__init__()
        self.url = url
        self.row_ids = row_ids
        self.user_name = user_name
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            payload = {
                "row_ids": self.row_ids,
                "user_name": self.user_name
            }
            import urllib.request
            import json
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(self.url, data=data, method="POST")
            req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode("utf-8"))
                self.signals.finished.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))

class ApiLazyTableModel(QAbstractTableModel):
    """
    QAbstractTableModel with lazy loading from a REST API endpoint.
    Retrieves data in chunks when the user scrolls near the bottom.
    """
    # Agent D v2: WS 브로드캐스트 전용 Signal (source='remote' 컨텍스트 포함)
    ws_data_changed = Signal(dict)  # {"row_id": ..., "column_name": ..., "value": ..., "source": "remote"}
    batch_ws_data_changed = Signal(dict) # {"updates": list, "change_count": int}
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
        self._fetch_scheduled = False # [신규] 타이머 예약용 중복 방지 락
        self._first_fetch = True
        self._is_processing_remote = False # Agent D v5: Prevent duplicate history logging
        self._fetching_row_ids = set() # Agent D v8: Track rows being fetched to prevent duplicates
        self._sort_latest = True       # [신규] 최신순 정렬(updated_at DESC) 여부
        self._server_fetched_count = 0 # [신규] 서버 페이징 기준 위치 (로컬 프리펜드 무시)

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
        self._server_fetched_count = 0
        self.endResetModel()
        
        # 즉시 첫 페이지 요청
        self.fetchMore()

    def set_sort_latest(self, enabled: bool):
        """최신순 정렬 여부를 설정하고 모델을 리셋합니다."""
        if self._sort_latest == enabled:
            return
            
        print(f"[Model] Setting sort_latest for {self.table_name}: {enabled}")
        self.beginResetModel()
        self._sort_latest = enabled
        self._data = []
        self._total_count = 0
        self._first_fetch = True
        self._server_fetched_count = 0
        self.endResetModel()
        
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
                
            persistent_index = QPersistentModelIndex(index)
            url = config.get_unified_update_url(self.table_name)
            
            # 통합 API 규격으로 페이로드 구성
            update_item = {
                "row_id": row_id,
                "column_name": col_name, # Server-side might need this inside 'updates' dict
                "updates": {col_name: value},
                "source_name": "user",
                "updated_by": config.CURRENT_USER
            }
            
            worker = ApiGeneralUpdateWorker(url, [update_item])
            # 람다를 사용하여 index 정보를 결과와 함께 전달
            worker.signals.finished.connect(lambda res: self._on_update_finished({
                **res, "index": persistent_index, "col_name": col_name, "value": value
            }))
            worker.signals.error.connect(lambda err: print(f"Failed to update cell via API: {err}"))
            
            QThreadPool.globalInstance().start(worker)
            
            # 서버 업데이트 시작 전, 즉시 입력 이벤트를 허용
            return True
                
        return False

    def applyMappedUpdates(self, mapped_updates: dict):
        """
        [Row ID 직접 타겟팅] 프록시 모델에서 이미 식별된 Row ID와 컬럼명 쌍을 받아 서버로 전송합니다.
        mapped_updates: {row_id: {col_name: value}}
        """
        grouped_payloads = []
        for row_id, updates in mapped_updates.items():
            if not row_id: continue
            
            grouped_payloads.append({
                "row_id": row_id,
                "updates": updates,
                "source_name": "user",
                "updated_by": config.CURRENT_USER
            })
            
        if not grouped_payloads:
            return
            
        url = config.get_unified_update_url(self.table_name)
        worker = ApiGeneralUpdateWorker(url, grouped_payloads)
        # 결과는 WebSocket 브로드캐스트를 통해 자동 반영됨
        QThreadPool.globalInstance().start(worker)

    def bulkUpdateData(self, start_row, start_col, parsed_data_matrix):
        """
        [행 단위 최적화] 
        복제 현상 방지: 동일 행에 대한 여러 셀 수정을 하나의 RowUpdate 항목으로 묶어 전송합니다.
        """
        # {row_id: {col_name: value, ...}}
        grouped_updates = {}
        
        for r_idx, row_values in enumerate(parsed_data_matrix):
            model_row = start_row + r_idx
            if model_row >= len(self._data): break
            row_id = self._data[model_row].get("row_id")
            if row_id is None: continue
            
            for c_idx, value in enumerate(row_values):
                model_col = start_col + c_idx
                if model_col >= len(self._columns): break
                col_name = self._columns[model_col]
                
                # 시스템 컬럼 제외
                if col_name in ["created_at", "updated_at", "row_id", "id", "updated_by"]:
                    continue
                
                if row_id not in grouped_updates:
                    grouped_updates[row_id] = {}
                
                grouped_updates[row_id][col_name] = value
        
        if not grouped_updates:
            return
            
        url = config.get_unified_update_url(self.table_name)
        
        # 통합 API 규격(GeneralUpdateBatch)으로 변환
        unified_updates = []
        for row_id, updates in grouped_updates.items():
            unified_updates.append({
                "row_id": row_id,
                "updates": updates,
                "source_name": "user",
                "updated_by": config.CURRENT_USER
            })
            
        worker = ApiGeneralUpdateWorker(url, unified_updates)
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
            elif event == "batch_row_delete":
                target_ids = data.get("row_ids", [])
                if not target_ids: return
                
                row_id_map = self._build_row_id_map()
                # [버그 수정] 중복 인덱스 제거 (IndexError 방지)
                unique_cached_indices = sorted(list(set([row_id_map[rid] for rid in target_ids if rid in row_id_map])), reverse=True)
                
                # 1. 로컬 캐시에 존재하는 행 제거
                for idx in unique_cached_indices:
                    self.beginRemoveRows(QModelIndex(), idx, idx)
                    del self._data[idx]
                    self._total_count -= 1
                    self.endRemoveRows()
                
                # 2. [기능 보완] 캐시에 없던 행(Placeholder 영역)에 대한 카운트 동기화
                # 서버에서 삭제된 총 개수와 로컬에서 제거한 개수 차이만큼 하단에서 제거
                total_deleted_on_server = len(set(target_ids)) # 중복 ID가 올 경우 대비
                removed_from_cache = len(unique_cached_indices)
                remaining_to_remove = total_deleted_on_server - removed_from_cache
                
                if remaining_to_remove > 0 and self._total_count >= remaining_to_remove:
                    # 가상 영역(목록 하단)에서 개수 차감 및 뷰 갱신
                    first_v_idx = self._total_count - remaining_to_remove
                    last_v_idx = self._total_count - 1
                    self.beginRemoveRows(QModelIndex(), first_v_idx, last_v_idx)
                    self._total_count -= remaining_to_remove
                    self.endRemoveRows()
                
                self.row_deleted_ws.emit(data)
                return
            elif event == "batch_row_create":
                items = data.get("items", [])
                if not items: return
                
                # 1~10000건 대량 생성 대응을 위한 데이터 준비
                new_rows = []
                for item in items:
                    new_rows.append(self._normalize_row_data(item))
                
                # 정렬 설정에 따라 삽입 위치 결정 (최신순 ON 이면 최상단, OFF 이면 최하단)
                if self._sort_latest:
                    self.beginInsertRows(QModelIndex(), 0, len(new_rows) - 1)
                    for r in reversed(new_rows):
                        self._data.insert(0, r)
                else:
                    start_idx = len(self._data)
                    self.beginInsertRows(QModelIndex(), start_idx, start_idx + len(new_rows) - 1)
                    for r in new_rows:
                        self._data.append(r)
                
                self._total_count += len(new_rows)
                self.endInsertRows()
                
                self.row_created_ws.emit(data) # 기존 시그널 활용하여 히스토리 패널 등 알림
                return
            elif event == "batch_row_upsert":
                items = data.get("items", [])
                if not items: return
                
                all_cell_updates = []
                row_id_map = self._build_row_id_map()
                
                # [순서 보존] 맨 아래 행부터 처리하여 최상단 부상 시 기존 상하 관계 유지
                for item in reversed(items):
                    row_id = item.get("row_id")
                    is_new = item.get("is_new", False)
                    new_data_blob = item.get("data", {})
                    
                    # [무결성 강화] 기존 행이 있다면 데이터를 병합(Merge)하여 메타데이터 보존
                    idx = row_id_map.get(row_id)
                    if idx is not None:
                        # 기존 행 객체 추출 (참조가 아닌 복사본으로 작업 후 재삽입)
                        existing_row = self._data.pop(idx)
                        # data 블롭 병합
                        existing_row.setdefault("data", {}).update(new_data_blob)
                        # 정규화 다시 실행 (Top-level 시간 정보 등 갱신)
                        normalized_row = self._normalize_row_data(existing_row)
                    else:
                        # 완전히 새로운 행
                        normalized_row = self._normalize_row_data({
                            "row_id": row_id,
                            "table_name": self.table_name,
                            "data": new_data_blob
                        })
                        if is_new: self._total_count += 1
                    
                    # 데이터 삽입: 정렬 설정에 따라 위치 결정
                    if self._sort_latest:
                        # 최상단에 부상(Floating)
                        self._data.insert(0, normalized_row)
                    else:
                        # 원래 있던 위치(idx)에 다시 넣거나, 없던 행(is_new)이면 하단에 추가
                        if idx is not None:
                            self._data.insert(idx, normalized_row)
                        else:
                            self._data.append(normalized_row)
                    
                    # 맵 갱신 (반드시 행이 다시 _data에 삽입된 후에 실행해야 인덱스 밀림 현상이 발생하지 않음)
                    row_id_map = self._build_row_id_map()

                    
                    # 히스토리 패널용 업데이트 리스트 구성
                    for col, cell_val in new_data_blob.items():
                        if isinstance(cell_val, dict) and "value" in cell_val:
                            all_cell_updates.append({
                                "row_id": row_id,
                                "column_name": col,
                                "value": cell_val["value"],
                                "is_overwrite": cell_val.get("is_overwrite", False),
                                "updated_by": cell_val.get("updated_by", "system"),
                                "source": "remote"
                            })

                # 데이터 구조가 대규모로 변경(순서 변경 등)되었으므로 일괄 리셋
                self.beginResetModel()
                self.endResetModel()

                if all_cell_updates:
                    self.batch_ws_data_changed.emit({
                        "updates": all_cell_updates,
                        "change_count": data.get("change_count", len(all_cell_updates)),
                        "updated_by": data.get("updated_by", "system")
                    })
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

            #if not changed_indices: return

            if self._sort_latest:
                for row_id in affected_rows:
                    # REBUILD map every time because indices shift on pop/insert
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
        
        # 1. data 내부(inject_system_columns에 의해 생성됨)에서 created_at, updated_at 추출하여 주입
        # top-level에 이미 있더라도 data_blob 내부의 'value'(로컬 시간 문자열)를 우선 사용하도록 수정
        if "created_at" in data_blob:
            cv = data_blob["created_at"].get("value")
            if cv: row["created_at"] = cv
            
        if "updated_at" in data_blob:
            uv = data_blob["updated_at"].get("value")
            if uv: row["updated_at"] = uv
            
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
            # Already exists, just update
            idx = row_id_map[row_id]
            self._data[idx] = normalized_row
            
            # 최신순 정렬 시에만 최상단으로 이동
            if self._sort_latest and idx > 0:
                self.beginMoveRows(QModelIndex(), idx, idx, QModelIndex(), 0)
                self._data.insert(0, self._data.pop(idx))
                self.endMoveRows()
            return

        # Truly new to cache
        self._is_processing_remote = True
        try:
            if self._sort_latest:
                self.beginInsertRows(QModelIndex(), 0, 0)
                self._data.insert(0, normalized_row)
            else:
                idx = len(self._data)
                self.beginInsertRows(QModelIndex(), idx, idx)
                self._data.append(normalized_row)
            
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
                # Trigger fetch if not already fetching or scheduled
                if not self._fetching and not getattr(self, '_fetch_scheduled', False):
                    self._fetch_scheduled = True # [고속 스크롤 픽스] 예약 락 설정
                    from PySide6.QtCore import QTimer
                    # Use a timer to avoid calling fetchMore directly inside data() which can cause issues
                    QTimer.singleShot(0, self.fetchMore)
                return "Loading..."
            return None

        cell_data = self._data[row].get("data", {})
        col_name = self._columns[col]

        # 1. 시스템 컬럼 (created_at, updated_at) 우선 처리
        if col_name in ["created_at", "updated_at"]:
            if role in [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole]:
                # 최상위(Flattened) 데이터 먼저 확인
                val = self._data[row].get(col_name)
                if val: return val
                # 중첩된 데이터 확인 (Fallback)
                item = cell_data.get(col_name, {})
                return item.get("value", "")
            return None

        # 2. 비즈니스 데이터 처리
        if role in [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole]:
            item = cell_data.get(col_name, {})
            val = item.get("value", "")
            # [기능 개선] 편집 모드(EditRole)일 때는 무조건 문자열로 반환하여 숫자 전용 입력기(SpinBox)를 방지함
            if role == Qt.ItemDataRole.EditRole and val is not None:
                return str(val)
            return val
            
        # [핵심] 식별자 다이렉트 접근 (Index Drift 방지용 절대 좌표)
        if role == Qt.ItemDataRole.UserRole + 2:
            return self._data[row].get("row_id")

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
        self._fetch_scheduled = False # 예약 락 해제
        if self._fetching:
            return
            
        self._fetching = True
        skip = self._server_fetched_count # [Paging Skip 픽스] len(self._data) 대신 서버 순차 누적 횟수 사용
        limit = self._chunk_size
        
        order_by = "updated_at" if self._sort_latest else "id"
        order_desc = "true" if self._sort_latest else "false"
        
        url = f"{self.endpoint_url}?skip={skip}&limit={limit}&order_by={order_by}&order_desc={order_desc}"
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
            self._server_fetched_count = len(new_data)
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
                
                # [Paging Skip 픽스] 캐시 중복 여부와 무관하게 서버에서 가져온 원본 개수만큼 페이징 포인터 전진
                self._server_fetched_count += len(new_data)
                
                # [Offset Drift 해결] 만약 가져온 데이터가 모두 중복(Ghost)이어서 뷰가 채워지지 않았다면,
                # 뷰가 "Loading..."에 영원히 멈춰있게 되므로 다음 페이지를 자동으로 연쇄 스캔합니다.
                if not unique_new_data and self._server_fetched_count < self._total_count:
                    self._fetching = False
                    self.fetchMore()
                    return
            
        self._fetching = False

    def _on_fetch_error(self, err: str):
        print(f"Fetch error: {err}")
        self._fetching = False

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal:
            if role == Qt.ItemDataRole.DisplayRole:
                return self._columns[section].upper()
            if role == Qt.ItemDataRole.UserRole:
                # [핵심] 번역/가공 전의 원본 컬럼명(Key)을 반환하여 뷰-모델 간 정확한 매핑 지원
                return self._columns[section]
        return super().headerData(section, orientation, role)
