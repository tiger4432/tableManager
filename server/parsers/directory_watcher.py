import os
import time
import shutil
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from advanced_ingester import AdvancedIngester

import sys
script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from database.database import SessionLocal
from database import crud, schemas

log_path = os.path.join(server_dir, "watcher.log")

class ColorFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG: '\033[94m', # Blue
        logging.INFO: '\033[92m', # Green
        logging.WARNING: '\033[93m', # Yellow
        logging.ERROR: '\033[91m', # Red
        logging.CRITICAL: '\033[1;91m', # Bold Red
    }
    RESET = '\033[0m'

    def format(self, record):
        log_fmt = f"{self.COLORS.get(record.levelno, self.RESET)}%(asctime)s - %(name)s - %(levelname)s - %(message)s{self.RESET}"
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)

console_handler = logging.StreamHandler()
console_handler.setFormatter(ColorFormatter())

file_handler = logging.FileHandler(log_path, encoding='utf-8')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

logging.basicConfig(
    level=logging.INFO,
    handlers=[console_handler, file_handler]
)
logger = logging.getLogger("DirectoryWatcher")
logger.info(f"DirectoryWatcher logging initialized. Log file: {log_path}")

class IngestionHandler(FileSystemEventHandler):
    """
    Handles file system events and triggers ingestion.
    """
    def __init__(self, workspace_path: str, config_path: str | None, archives_path: str, default_table_name: str | None = None, on_refresh_callback=None):
        self.workspace_path = workspace_path
        self.config_path = config_path
        self.archives_path = archives_path
        self.default_table_name = default_table_name # Agent D v13: 폴더 머신 명칭 기반 Fallback
        self.scripts_path = os.path.join(workspace_path, "scripts")
        self.supported_extensions = ('.log', '.txt', '.csv')
        self.processing_files = set() 
        self.on_refresh_callback = on_refresh_callback
        
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
                
                if rows is not None:
                    # 파이프라인 매칭 및 실행 성공 (빈 리스트일 수도 있음)
                    if rows:
                        self._send_to_upsert(rows, uploader=uploader)
                else:
                    # 매칭되는 파이프라인이 없으면 기본 AdvancedIngester 수행
                    logger.info(f"[{self.table_name}] ⚡ No pipeline matched. Falling back to AdvancedIngester for {os.path.basename(file_path)}")
                    # 1. Initialize AdvancedIngester for this workspace
                    ingester = AdvancedIngester(self.config_path)
                    
                    # 2. Process the file and get rows for batching
                    logger.info(f"[{self.table_name}] 🔄 Starting default ingestion for {os.path.basename(file_path)} (Attempt {attempt+1})")
                    rows = ingester.process_file(file_path)
                    if rows:
                        self._send_to_upsert(rows, uploader=uploader)
                
                # 3. Archive the file
                self._archive_file(file_path)
                logger.info(f"[{self.table_name}] ✅ Successfully processed and archived: {os.path.basename(file_path)}")
                return
            except PermissionError:
                logger.warning(f"[{self.table_name}] 🔒 File locked, retrying in {delay}s: {os.path.basename(file_path)}")
                time.sleep(delay)
            except Exception as e:
                logger.error(f"[{self.table_name}] ❌ Error processing file {os.path.basename(file_path)}: {e}")
                return
        
        logger.error(f"[{self.table_name}] ❌ Failed to process file after {retries} attempts: {os.path.basename(file_path)}")

    def _archive_file(self, file_path: str):
        if not os.path.exists(file_path):
            logger.debug(f"File already gone, skipping archive: {file_path}")
            return

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
        except FileNotFoundError:
            logger.debug(f"File vanished during move: {file_path}")
        except Exception as e:
            logger.error(f"Failed to move file to archive: {e}")

    def _discover_and_execute_pipeline(self, file_path: str) -> list[dict] | None:
        """
        scripts 폴더 내의 모든 파이썬 파일을 검색하여
        BasePipelineParser를 상속받은 클래스 중 match()가 True인 첫 번째 파서를 실행합니다.
        """
        if not os.path.exists(self.scripts_path):
            return None

        import importlib.util
        import inspect
        
        # Add server/parsers to sys.path if not there so plugins can import BasePipelineParser
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)
            
        try:
            from pipeline_base import BasePipelineParser
        except ImportError:
            logger.error("Failed to import BasePipelineParser. Check sys.path.")
            return None

        for filename in os.listdir(self.scripts_path):
            if filename.endswith(".py") and filename != "__init__.py":
                script_path = os.path.join(self.scripts_path, filename)
                try:
                    module_name = f"pipeline_plugin_{filename[:-3]}"
                    spec = importlib.util.spec_from_file_location(module_name, script_path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    for name, obj in inspect.getmembers(module, inspect.isclass):
                        if issubclass(obj, BasePipelineParser) and obj is not BasePipelineParser:
                            try:
                                if obj.match(file_path):
                                    logger.info(f"[{self.table_name}] 🚀 Pipeline Matched: \033[1;36m{obj.__name__}\033[0m in {filename}")
                                    parser_instance = obj()
                                    return parser_instance.parse(file_path)
                            except Exception as e:
                                logger.error(f"[{self.table_name}] ❌ Error evaluating match() or parse() in {obj.__name__}: {e}")
                except Exception as e:
                    logger.error(f"Failed to load plugin script {script_path}: {e}")

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

    def _send_to_upsert(self, rows: list[dict], uploader: str = "system"):
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
        
        # 4. 배치 단위로 정규화 및 로컬 DB 전송
        import uuid
        file_tx_id = str(uuid.uuid4())
        
        batch_size = 5000
        total_changed = 0
        
        db = SessionLocal()
        try:
            for i in range(0, len(rows), batch_size):
                chunk = rows[i:i + batch_size]
                items = []
                
                for row in chunk:
                    normalized_row = {}
                    bk_val = None
                    
                    for key, val in row.items():
                        target_key = key
                        for d_col in defined_cols:
                            if key.lower() == d_col.lower():
                                target_key = d_col
                                break
                        normalized_row[target_key] = val
                        if target_key.lower() == bk_col.lower():
                            bk_val = val

                    if bk_val is not None:
                        items.append(schemas.GeneralUpdateItem(
                            business_key_val=str(bk_val),
                            updates=normalized_row,
                            source_name="pipeline_parser" if os.path.exists(self.scripts_path) else "batch_ingester",
                            updated_by=uploader
                        ))
                
                if not items:
                    continue

                try:
                    batch_obj = schemas.GeneralUpdateBatch(
                        updates=items,
                        transaction_id=file_tx_id,
                        silent=True
                    )
                    results, changed_cells = crud.apply_batch_updates(db, t_name, batch_obj)
                    total_changed += len(changed_cells)
                    logger.info(f"[{self.table_name}] 💾 Local batch update success ({len(items)} rows). Changed cells: {len(changed_cells)}")
                except Exception as e:
                    logger.error(f"[{self.table_name}] ❌ Failed to apply local batch update: {e}")
                    
            if self.on_refresh_callback and total_changed > 0:
                self.on_refresh_callback(t_name, total_changed)
                
        finally:
            db.close()

class WorkspaceWatcher:
    """
    Monitors all ingestion workspaces for new files.
    """
    def __init__(self, base_dir: str, on_refresh_callback=None):
        self.base_dir = base_dir
        self.observer = Observer()
        self.watch_count = 0
        self.on_refresh_callback = on_refresh_callback

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
                    handler = IngestionHandler(workspace_root, config_path, archives_path, on_refresh_callback=self.on_refresh_callback)
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
                        handler = IngestionHandler(workspace_root, None, archives_path, default_table_name=table_name, on_refresh_callback=self.on_refresh_callback)
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
