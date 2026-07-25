import os
import time
import shutil
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

import sys
script_dir = os.path.dirname(os.path.abspath(__file__))
# [C-2 Fix] sys.path에는 repo root가 아니라 server 디렉토리를 추가하고, DB 모듈은 다른 모든
# 프로세스(main.py, run_watcher.py 등)와 동일하게 최상위 `database.*` 경로로 import한다.
# 과거 `server.database.database` 혼용 import는 동일 모듈을 서로 다른 이름으로 2회 로드시켜
# before_flush 리스너가 Session 클래스에 2중 등록되었고, 모든 outbox 이벤트가 ×2로
# 중복 발행되는 회귀(라이브 실측 중복 그룹 1,259,076개)의 원인이었다. 재도입 금지.
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from database.database import SessionLocal
from database import crud, schemas

log_path = os.path.join(server_dir, "watcher.log")

# Inherit from unified Watcher logger parent to prevent double formatting and log separation
logger = logging.getLogger("Watcher.DirectoryWatcher")

# [C-5] 파일 인제션 완료 통지에 동봉하는 감사 로그(created_logs) 상한.
# 웹서버(main.py /internal/events/*)가 어차피 500건으로 절단·캐시하므로, 워처가 전량(수십만~수백만
# dict)을 메모리에 누적·HTTP POST하는 것은 순수 낭비이자 OOM/이벤트 루프 동결 요인이었다.
# 이벤트 필드 형태(created_logs: list)는 그대로 유지하고 항목 수만 제한한다(경계 계약 불변).
# 실제 총 로그 건수는 total_log_count로 별도 전달되어 웹서버 audit_cache의 total_count 표기에 쓰인다.
MAX_NOTIFY_CREATED_LOGS = 500


def _register_legacy_import_shim():
    """[C-2 하위호환 shim] gitignored 사용자 워크스페이스 스크립트의 구식 `server.*` import 지원.

    C-2 수정으로 sys.path에서 repo root가 제거되어, 기존 사용자 커스텀 파서의
    `from server.parsers.pipeline_base import BasePipelineParser` 류 모듈 레벨 import가
    깨질 수 있다(사용자 스크립트는 무수정 원칙 — gitignored 자산).

    해법: sys.modules에 **동일 객체 별칭**을 등록한다. 파이썬 import 시스템은 dotted 완전명을
    sys.modules에서 __path__ 탐색·meta_path보다 먼저 조회하므로, 구식 import는 이미 로드된
    top-level 모듈(`pipeline_base`, `database.database` 등)과 **정확히 같은 모듈 객체**를 받는다.
    → issubclass 정체성 유지 + 같은 모듈의 2차 로드(before_flush 리스너 2중 등록 → outbox ×2
    발행)가 원천적으로 불가능해진다.

    ⚠️ '차단'이 아니라 '중화'인 이유: conda env에 본 프로젝트가 pip editable로 설치되어 있어
    (`__editable___assy_manager_*_finder`가 sys.meta_path에 상주) `server.*` import는 부모
    __path__와 무관하게 항상 실 파일로 해석된다 — 더미 패키지의 빈 __path__로는 막을 수 없다.
    따라서 리스너를 등록하는 위험 모듈(`server.database.*`)까지 **전부 별칭으로 선점**하여,
    어떤 경로로 import되든 단일 객체가 되도록 한다.

    (2026-07-25 워크스페이스 스크립트 전수 조사: 실사용 구식 import는
     `server.parsers.pipeline_base` · `server.parsers.html_topology_parser` 2종.
     `server.database.*`는 실사용 0건이나 editable finder 경유 2차 로드 방지를 위해 방어적 별칭.)
    멱등: 재호출 시 기존 등록을 재사용한다.
    """
    import types

    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)

    # 1) top-level 정본 모듈 로드 (플러그인 신규 권장 경로와 동일 객체)
    import pipeline_base
    import database
    import database.database as _db_database
    import database.models as _db_models
    import database.crud as _db_crud
    import database.schemas as _db_schemas

    def _ensure_pkg(name, parent=None, attr=None):
        mod = sys.modules.get(name)
        if mod is None:
            mod = types.ModuleType(name)
            mod.__path__ = []
            sys.modules[name] = mod
        if parent is not None and attr is not None and not hasattr(parent, attr):
            setattr(parent, attr, mod)
        return mod

    server_pkg = _ensure_pkg("server")
    parsers_pkg = _ensure_pkg("server.parsers", server_pkg, "parsers")

    # 2) 별칭 등록 — 구식 dotted import가 top-level 모듈 객체 그대로를 받는다.
    aliases = {
        "server.parsers.pipeline_base": pipeline_base,
        # 리스너(before_flush) 보유 모듈 — editable finder 경유 2차 로드를 별칭 선점으로 중화
        "server.database": database,
        "server.database.database": _db_database,
        "server.database.models": _db_models,
        "server.database.crud": _db_crud,
        "server.database.schemas": _db_schemas,
    }
    try:
        import html_topology_parser
        aliases["server.parsers.html_topology_parser"] = html_topology_parser
    except Exception as e:
        # html_topology_parser는 선택 의존(bs4 등) — 실패해도 나머지 shim은 유효.
        logger.warning(f"Legacy import shim: html_topology_parser alias skipped: {e}")

    for dotted, mod in aliases.items():
        sys.modules[dotted] = mod
        parent_name, _, child = dotted.rpartition(".")
        parent_mod = sys.modules.get(parent_name)
        if parent_mod is not None:
            setattr(parent_mod, child, mod)

class IngestionHandler(FileSystemEventHandler):
    """
    Handles file system events and triggers ingestion.
    """
    def __init__(self, workspace_path: str, config_path: str | None, archives_path: str, default_table_name: str | None = None, on_refresh_callback=None, on_file_processed_callback=None, on_progress_callback=None):
        self.workspace_path = workspace_path
        self.config_path = config_path
        self.archives_path = archives_path
        self.default_table_name = default_table_name # Agent D v13: 폴더 머신 명칭 기반 Fallback
        self.scripts_path = os.path.join(workspace_path, "scripts")
        self.supported_extensions = ('.log', '.txt', '.csv')
        self.processing_files = set() 
        self.on_refresh_callback = on_refresh_callback
        self.on_file_processed_callback = on_file_processed_callback
        self.on_progress_callback = on_progress_callback
        
    @property
    def table_name(self):
        if hasattr(self, '_cached_table_name'):
            return self._cached_table_name
            
        t_name = self.default_table_name
        import json
        if self.config_path and os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                t_name = config.get("table_name", t_name)
            except: pass
        self._cached_table_name = t_name
        return t_name

    @property
    def errors_path(self):
        return os.path.join(self.workspace_path, "err")

    def on_created(self, event):
        if not event.is_directory:
            self._handle_event(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._handle_event(event.dest_path)
            
    # Agent D v7: Removed on_modified as it causes too many duplicates on Windows

    def _handle_event(self, file_path: str):
        abs_path = os.path.abspath(file_path)
        if True:
            if abs_path in self.processing_files:
                return
            if not os.path.exists(abs_path):
                return
                
            logger.info(f"New file detected: {abs_path}")
            self.processing_files.add(abs_path)
            
            # [Fix] 파일명에서 업로더 정보 추출
            uploader = self._extract_user_from_filename(os.path.basename(abs_path))
            
            logger.info(f"[{self.table_name}] 📥 New file detected: {os.path.basename(abs_path)}")
            
            try:
                self.process_with_retry(abs_path, uploader=uploader)
            finally:
                if abs_path in self.processing_files:
                    self.processing_files.remove(abs_path)

    def process_with_retry(self, file_path: str, uploader: str = "system", retries: int = 3, delay: float = 1.0):
        """
        Processes a file with debouncing and retries to handle locked files.
        """
        # Initial debounce to allow file copy to finish
        time.sleep(delay)
        
        abs_path = os.path.abspath(file_path)
        if not os.path.exists(abs_path):
            logger.debug(f"File vanished during debounce (likely processed by concurrent thread): {file_path}")
            return

        for attempt in range(retries):
            try:
                # Pipeline Discovery: scripts 폴더 내의 파이프라인 파서 탐색
                rows = self._discover_and_execute_pipeline(file_path)
                
                if rows is None:
                    raise ValueError(f"No custom pipeline parser matched the file '{os.path.basename(file_path)}' format.")
                
                # 파이프라인 매칭 및 실행 성공 (빈 리스트일 수도 있음)
                if rows:
                    self._send_to_upsert(rows, uploader=uploader, filename=os.path.basename(file_path))
                
                # 3. Archive the file
                dest_path = self._archive_file(file_path)
                logger.info(f"[{self.table_name}] ✅ Successfully processed and archived: {os.path.basename(file_path)}")
                self._log_ingestion_success(file_path, dest_path)
                if self.on_file_processed_callback:
                    self.on_file_processed_callback(self.table_name, os.path.basename(file_path), "SUCCESS", None)
                return
            except PermissionError:
                logger.warning(f"[{self.table_name}] 🔒 File locked, retrying in {delay}s: {os.path.basename(file_path)}")
                time.sleep(delay)
            except Exception as e:
                import traceback
                error_msg = traceback.format_exc()
                logger.error(f"[{self.table_name}] ❌ Error processing file {os.path.basename(file_path)}: {error_msg}")
                dest_path = self._move_to_err_folder(file_path)
                if not dest_path:
                    dest_path = file_path
                self._log_ingestion_failure(file_path, dest_path, error_msg)
                if self.on_file_processed_callback:
                    self.on_file_processed_callback(self.table_name, os.path.basename(file_path), "FAILED", str(e))
                return
        
        error_msg = f"Failed to process file after {retries} attempts: PermissionError (file locked)"
        logger.error(f"[{self.table_name}] ❌ {error_msg}: {os.path.basename(file_path)}")
        dest_path = self._move_to_err_folder(file_path)
        if not dest_path:
            dest_path = file_path
        self._log_ingestion_failure(file_path, dest_path, error_msg)
        if self.on_file_processed_callback:
            self.on_file_processed_callback(self.table_name, os.path.basename(file_path), "FAILED", error_msg)

    def _log_ingestion_failure(self, original_path: str, archived_path: str, error_msg: str):
        db = SessionLocal()
        try:
            from database.models import FileIngestionLog
            log_obj = FileIngestionLog(
                filename=os.path.basename(original_path),
                filepath=os.path.abspath(archived_path),
                table_name=self.table_name or "unknown",
                status="FAILED",
                error_message=error_msg,
                retry_count=0
            )
            db.add(log_obj)
            db.commit()
            logger.info(f"[{self.table_name}] 📝 Logged file ingestion failure to database.")
        except Exception as e:
            logger.error(f"Failed to write file ingestion error log to DB: {e}")
        finally:
            db.close()

    def _log_ingestion_success(self, original_path: str, archived_path: str):
        db = SessionLocal()
        try:
            from database.models import FileIngestionLog
            log_obj = FileIngestionLog(
                filename=os.path.basename(original_path),
                filepath=os.path.abspath(archived_path),
                table_name=self.table_name or "unknown",
                status="SUCCESS",
                error_message=None,
                retry_count=0
            )
            db.add(log_obj)
            db.commit()
            logger.info(f"[{self.table_name}] 📝 Logged file ingestion success to database.")
        except Exception as e:
            logger.error(f"Failed to write file ingestion success log to DB: {e}")
        finally:
            db.close()

    def process_archived_file_sync(self, log_entry, db, uploader: str = "system"):
        """
        Processes a file that is already in err/archives folders (e.g. for retrying).
        Does not move it again.
        """
        filepath = log_entry.filepath
        try:
            rows = self._discover_and_execute_pipeline(filepath)
            if rows is None:
                raise ValueError(f"No custom pipeline parser matched the file '{os.path.basename(filepath)}' format.")
            if rows:
                self._send_to_upsert(rows, uploader=uploader, filename=os.path.basename(filepath))
            
            # If successful, update the log entry to SUCCESS
            log_entry.status = "SUCCESS"
            log_entry.error_message = None
            db.commit()
            if self.on_file_processed_callback:
                self.on_file_processed_callback(self.table_name, os.path.basename(filepath), "SUCCESS", None)
            return True
        except Exception as e:
            import traceback
            error_msg = traceback.format_exc()
            logger.error(f"[{self.table_name}] ❌ Error retrying file {os.path.basename(filepath)}: {error_msg}")
            log_entry.status = "FAILED"
            log_entry.error_message = error_msg
            log_entry.retry_count += 1
            db.commit()
            if self.on_file_processed_callback:
                self.on_file_processed_callback(self.table_name, os.path.basename(filepath), "FAILED", str(e))
            return False

    def _move_to_err_folder(self, file_path: str) -> str:
        if not os.path.exists(file_path):
            logger.debug(f"File already gone, skipping error moving: {file_path}")
            return None

        err_dir = self.errors_path
        if not os.path.exists(err_dir):
            os.makedirs(err_dir)
            
        filename = os.path.basename(file_path)
        dest_path = os.path.join(err_dir, filename)
        
        # Handle filename collisions in error directory
        if os.path.exists(dest_path):
            base, ext = os.path.splitext(filename)
            dest_path = os.path.join(err_dir, f"{base}_{int(time.time())}{ext}")
            
        try:
            shutil.move(file_path, dest_path)
            logger.info(f"Moved failed file {file_path} to error folder {dest_path}")
            return dest_path
        except FileNotFoundError:
            logger.debug(f"File vanished during move to err: {file_path}")
            return None
        except Exception as e:
            logger.error(f"Failed to move file to err: {e}")
            return None

    def _archive_file(self, file_path: str) -> str:
        if not os.path.exists(file_path):
            logger.debug(f"File already gone, skipping archive: {file_path}")
            return None

        if not os.path.exists(self.archives_path):
            os.makedirs(self.archives_path)
            
        filename = os.path.basename(file_path)
        dest_path = os.path.join(self.archives_path, filename)
        
        # Handle filename collisions in archives
        if os.path.exists(dest_path):
            base, ext = os.path.splitext(filename)
            dest_path = os.path.join(self.archives_path, f"{base}_{int(time.time())}{ext}")
            
        try:
            shutil.move(file_path, dest_path)
            logger.info(f"Moved {file_path} to {dest_path}")
            return dest_path
        except FileNotFoundError:
            logger.debug(f"File vanished during move: {file_path}")
            return None
        except Exception as e:
            logger.error(f"Failed to move file to archive: {e}")
            return None

    def _discover_and_execute_pipeline(self, file_path: str) -> list[dict] | None:
        """
        scripts 폴더 내의 모든 파이썬 파일을 검색하여
        BasePipelineParser를 상속받은 클래스 중 match()가 True인 첫 번째 파서를 실행합니다.
        """
        if not os.path.exists(self.scripts_path):
            return None

        import importlib.util
        import inspect
        import traceback
        
        # Add server/parsers to sys.path if not there so plugins can import BasePipelineParser
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)
            
        try:
            # [C-2 Fix] 플러그인 스크립트(run_watcher 포함)와 동일한 최상위 모듈명(pipeline_base)으로
            # import하여 BasePipelineParser의 이중 모듈 정체성(issubclass 불일치)을 방지한다.
            from pipeline_base import BasePipelineParser
            # [C-2 하위호환] 구식 `server.parsers.*` import를 쓰는 기존 사용자 스크립트 지원(동일 객체 별칭).
            _register_legacy_import_shim()
        except ImportError:
            logger.error("Failed to import BasePipelineParser. Check sys.path.")
            return None

        load_errors = {}
        match_errors = {}

        for filename in os.listdir(self.scripts_path):
            if filename.endswith(".py") and filename != "__init__.py":
                script_path = os.path.join(self.scripts_path, filename)
                try:
                    module_name = f"pipeline_plugin_{filename[:-3]}"
                    spec = importlib.util.spec_from_file_location(module_name, script_path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    for name, obj in inspect.getmembers(module, inspect.isclass):
                        is_sub = False
                        try:
                            if issubclass(obj, BasePipelineParser):
                                is_sub = True
                        except TypeError:
                            pass
                        
                        if not is_sub:
                            for parent in getattr(obj, "__mro__", []):
                                if parent.__name__ == "BasePipelineParser":
                                    is_sub = True
                                    break
                                    
                        if is_sub and obj.__name__ != "BasePipelineParser":
                            try:
                                is_match = obj.match(file_path)
                            except Exception as e:
                                match_error_detail = traceback.format_exc()
                                logger.error(f"[{self.table_name}] ❌ Error evaluating match() in {obj.__name__}: {e}")
                                match_errors[f"{filename}::{obj.__name__}"] = match_error_detail
                                continue
                                
                            if is_match:
                                logger.info(f"[{self.table_name}] 🚀 Pipeline Matched: \033[1;36m{obj.__name__}\033[0m in {filename}")
                                parser_instance = obj()
                                return parser_instance.parse(file_path)
                except Exception as e:
                    load_error_detail = traceback.format_exc()
                    logger.error(f"Failed to load plugin script {script_path}: {e}")
                    load_errors[filename] = load_error_detail

        if load_errors or match_errors:
            error_details = []
            if load_errors:
                error_details.append("--- Script Load Errors ---")
                for fn, err in load_errors.items():
                    error_details.append(f"[{fn}]:\n{err}")
            if match_errors:
                error_details.append("--- match() Execution Errors ---")
                for path_or_class, err in match_errors.items():
                    error_details.append(f"[{path_or_class}]:\n{err}")
            
            detailed_msg = (
                f"No custom pipeline parser matched the file '{os.path.basename(file_path)}' format.\n"
                f"However, some errors occurred while loading/matching scripts:\n"
                + "\n".join(error_details)
            )
            raise ValueError(detailed_msg)

        return None # 매칭된 파서가 없음
            
    def _extract_user_from_filename(self, filename: str) -> str:
        """파일명에 인코딩된 user(name) 정보를 추출합니다."""
        if filename.startswith("user("):
            try:
                end_idx = filename.find(")")
                if end_idx != -1:
                    return filename[5:end_idx]
            except:
                pass
        return "system"

    def _send_to_upsert(self, rows: list[dict], uploader: str = "system", filename: str = None):
        """파싱된 행 리스트를 직접 DB crud.apply_batch_updates 로 넘겨 초고속 처리합니다."""
        import json
        
        # 1. 대상 테이블 설정 로드
        table_config = {}
        try:
            global_config_path = os.path.abspath(os.path.join(script_dir, "..", "config", "table_config.json"))
            if os.path.exists(global_config_path):
                with open(global_config_path, "r", encoding="utf-8") as f:
                    table_config = json.load(f)
        except Exception as e:
            logger.warning(f"Could not load global table_config: {e}")

        # 2. 현재 워크스페이스의 table_name 결정
        t_name = self.table_name

        if not t_name:
            logger.error("No table_name identified for upsert.")
            return

        # 3. 비즈니스 키 및 컬럼 매핑 정보 획득
        table_info = table_config.get(t_name, {})
        bk_col = table_info.get("business_key", "id")
        defined_cols = table_info.get("display_columns", [])
        
        # Determine source_name based on real original filename
        real_source = "batch_ingester"
        if filename:
            try:
                from pipeline_base import BasePipelineParser
                real_source = BasePipelineParser.get_basename(filename)
            except Exception as e:
                logger.warning(f"Failed to get clean original filename: {e}")
                real_source = filename
        else:
            real_source = "pipeline_parser" if os.path.exists(self.scripts_path) else "batch_ingester"

        # 4. 배치 단위로 정규화 및 로컬 DB 전송
        import uuid
        file_tx_id = str(uuid.uuid4())
        
        batch_size = 1000
        total_changed = 0
        all_created_logs = []
        total_log_count = 0  # [C-5] 절단과 무관한 실제 총 감사 로그 건수

        total_rows = len(rows)
        processed_rows = 0
        try:
            for i in range(0, total_rows, batch_size):
                chunk = rows[i:i + batch_size]
                items = []
                
                for row in chunk:
                    normalized_row = {}
                    bk_val = None
                    
                    for key, val in row.items():
                        target_key = None
                        for d_col in defined_cols:
                            if key.lower() == d_col.lower():
                                target_key = d_col
                                break
                        if target_key is not None:
                            normalized_row[target_key] = val
                            if target_key.lower() == bk_col.lower():
                                bk_val = val
                    if normalized_row:
                        items.append(schemas.GeneralUpdateItem(
                            business_key_val=str(bk_val) if bk_val is not None else None,
                            updates=normalized_row,
                            source_name=real_source,
                            updated_by=uploader
                        ))
                
                if not items:
                    processed_rows += len(chunk)
                    continue

                # 1,000건 청크 단위로 DB 세션을 격리하여 트랜잭션 처리
                db = SessionLocal()
                try:
                    batch_obj = schemas.GeneralUpdateBatch(
                        updates=items,
                        transaction_id=file_tx_id,
                        silent=True
                    )
                    results, changed_cells, created_logs, deleted_row_ids = crud.apply_batch_updates(db, t_name, batch_obj)
                    
                    db.commit()
                    
                    total_changed += len(changed_cells)
                    if created_logs:
                        # [C-5] 누적 자체에 상한 적용 — 수십만 행 파일에서도 메모리·payload가 O(500)로 고정
                        total_log_count += len(created_logs)
                        remaining = MAX_NOTIFY_CREATED_LOGS - len(all_created_logs)
                        if remaining > 0:
                            all_created_logs.extend(created_logs[:remaining])
                    logger.info(f"[{self.table_name}] 💾 Local batch update success ({len(items)} rows). Changed cells: {len(changed_cells)}")
                except Exception as e:
                    db.rollback()
                    logger.error(f"[{self.table_name}] ❌ Failed to apply local batch update: {e}")
                    raise e
                finally:
                    db.close()
                
                processed_rows += len(chunk)
                if self.on_progress_callback:
                    progress_pct = int((processed_rows / total_rows) * 100)
                    try:
                        self.on_progress_callback(t_name, filename or "unknown", progress_pct, processed_rows, total_rows)
                    except Exception as pe:
                        logger.warning(f"Progress callback failed: {pe}")
                    
            if self.on_refresh_callback and total_changed > 0:
                self.on_refresh_callback(t_name, total_changed, all_created_logs, total_log_count)
                
        except Exception as outer_e:
            logger.error(f"[{self.table_name}] Outer error during batch injection loop: {outer_e}")
            raise outer_e

class WorkspaceWatcher:
    """
    Monitors all ingestion workspaces for new files.
    """
    def __init__(self, base_dir: str, on_refresh_callback=None, on_file_processed_callback=None, on_progress_callback=None):
        self.base_dir = base_dir
        self.observer = Observer()
        self.watch_count = 0
        self.on_refresh_callback = on_refresh_callback
        self.on_file_processed_callback = on_file_processed_callback
        self.on_progress_callback = on_progress_callback

    def discover_and_watch(self):
        """
        Recursively finds 'raws' folders in the ingestion workspace and registers them.
        """
        logger.info(f"Scanning {self.base_dir} for 'raws' folders...")
        
        for root, dirs, files in os.walk(self.base_dir):
            if os.path.basename(root) == "raws":
                workspace_root = os.path.dirname(root)
                config_dir = os.path.join(workspace_root, "config")
                config_path = os.path.join(config_dir, "config.json")
                archives_path = os.path.join(workspace_root, "archives")
                
                # Agent D v7: Be more flexible if config.json is not present
                if not os.path.exists(config_path) and os.path.exists(config_dir):
                    json_files = [f for f in os.listdir(config_dir) if f.endswith('.json')]
                    if json_files:
                        config_path = os.path.join(config_dir, json_files[0])
                        logger.info(f"Using alternative config: {config_path}")

                if os.path.exists(config_path):
                    handler = IngestionHandler(workspace_root, config_path, archives_path, on_refresh_callback=self.on_refresh_callback, on_file_processed_callback=self.on_file_processed_callback, on_progress_callback=self.on_progress_callback)
                    self.observer.schedule(handler, root, recursive=False)
                    self.watch_count += 1
                    logger.info(f"Watching: {root} (using config: {os.path.basename(config_path)})")
                else:
                    # Pipeline: config 가 없더라도 scripts 폴더 내에 파이썬 파일이 있으면 감지 대상으로 포함
                    scripts_dir = os.path.join(workspace_root, "scripts")
                    has_scripts = False
                    if os.path.exists(scripts_dir):
                        for f in os.listdir(scripts_dir):
                            if f.endswith('.py'):
                                has_scripts = True
                                break
                                
                    if has_scripts:
                        table_name = os.path.basename(workspace_root)
                        handler = IngestionHandler(workspace_root, None, archives_path, default_table_name=table_name, on_refresh_callback=self.on_refresh_callback, on_file_processed_callback=self.on_file_processed_callback, on_progress_callback=self.on_progress_callback)
                        self.observer.schedule(handler, root, recursive=False)
                        self.watch_count += 1
                        logger.info(f"Watching: {root} (Pipeline-only workspace, Table: {table_name})")
                    else:
                        logger.warning(f"Skipping {root}: No JSON config or custom_parser found.")

    def stop(self):
        self.observer.stop()
        self.observer.join()

    def start(self, blocking: bool = True):
        if self.watch_count == 0:
            logger.error("No valid 'raws' folders found to watch.")
            return

        self.observer.start()
        logger.info(f"Started observer with {self.watch_count} watches.")
        
        if blocking:
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                self.observer.stop()
            self.observer.join()

if __name__ == "__main__":
    # Assuming the script is run from server/parsers/
    script_dir = os.path.dirname(os.path.abspath(__file__))
    workspace_base = os.path.abspath(os.path.join(script_dir, "..", "ingestion_workspace"))
    
    watcher = WorkspaceWatcher(workspace_base)
    watcher.discover_and_watch()
    watcher.start()
