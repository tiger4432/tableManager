import os
import time
import shutil
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from advanced_ingester import AdvancedIngester

endpoint = '127.0.0.1:8000'

# [사내망 Proxy 인증 우회 설정]
# 이 스크립트는 로컬(127.0.0.1) API로만 요청을 보냅니다.
# 사내망의 파이어월/프록시가 개입하여 403 Forbidden 에러가 나는 것을 원천 차단합니다.
import urllib.request
os.environ["NO_PROXY"] = "127.0.0.1,localhost,::1"
proxy_support = urllib.request.ProxyHandler({})
opener = urllib.request.build_opener(proxy_support)
urllib.request.install_opener(opener)
# Configure logging
# Configure logging
script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
log_path = os.path.join(server_dir, "watcher.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_path, encoding='utf-8')
    ]
)
logger = logging.getLogger("DirectoryWatcher")
logger.info(f"DirectoryWatcher logging initialized. Log file: {log_path}")

class IngestionHandler(FileSystemEventHandler):
    """
    Handles file system events and triggers ingestion.
    """
    def __init__(self, workspace_path: str, config_path: str | None, archives_path: str, default_table_name: str | None = None):
        self.workspace_path = workspace_path
        self.config_path = config_path
        self.archives_path = archives_path
        self.default_table_name = default_table_name # Agent D v13: 폴더 머신 명칭 기반 Fallback
        self.scripts_path = os.path.join(workspace_path, "scripts")
        self.supported_extensions = ('.log', '.txt', '.csv')
        self.processing_files = set() 
        
    def on_created(self, event):
        if not event.is_directory:
            self._handle_event(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._handle_event(event.dest_path)
            
    # Agent D v7: Removed on_modified as it causes too many duplicates on Windows

    def _handle_event(self, file_path: str):
        abs_path = os.path.abspath(file_path)
        if abs_path.endswith(self.supported_extensions):
            if abs_path in self.processing_files:
                return
            if not os.path.exists(abs_path):
                return
                
            logger.info(f"New file detected: {abs_path}")
            self.processing_files.add(abs_path)
            try:
                self.process_with_retry(abs_path)
            finally:
                if abs_path in self.processing_files:
                    self.processing_files.remove(abs_path)

    def process_with_retry(self, file_path: str, retries: int = 3, delay: float = 1.0):
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
                # Agent D v13: 커스텀 스크립트 존재 여부 확인
                custom_script = os.path.join(self.scripts_path, "custom_parser.py")
                if os.path.exists(custom_script):
                    logger.info(f"Custom script found: {custom_script}. Using plug-in parser.")
                    rows = self._execute_custom_script(file_path, custom_script)
                    if rows:
                        self._send_to_upsert(rows)
                else:
                    # 1. Initialize AdvancedIngester for this workspace
                    ingester = AdvancedIngester(self.config_path)
                    
                    # 2. Process the file and get rows for batching
                    logger.info(f"Starting ingestion for {file_path} (Attempt {attempt+1})")
                    rows = ingester.process_file(file_path)
                    if rows:
                        self._send_to_upsert(rows)
                
                # 3. Archive the file
                self._archive_file(file_path)
                logger.info(f"Successfully processed and archived: {file_path}")
                return
            except PermissionError:
                logger.warning(f"File locked, retrying in {delay}s: {file_path}")
                time.sleep(delay)
            except Exception as e:
                logger.error(f"Error processing file {file_path}: {e}")
                return
        
        logger.error(f"Failed to process file after {retries} attempts: {file_path}")

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

    def _execute_custom_script(self, file_path: str, script_path: str) -> list[dict]:
        """커스텀 Python 스크립트를 동적으로 로드하여 실행합니다."""
        import importlib.util
        try:
            spec = importlib.util.spec_from_file_location("custom_parser", script_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            if hasattr(module, 'parse_file'):
                logger.info(f"Executing custom parse_file for {file_path}")
                return module.parse_file(file_path)
            else:
                logger.error(f"Script {script_path} does not have 'parse_file(file_path)' function.")
                return []
        except Exception as e:
            logger.error(f"Failed to execute custom script {script_path}: {e}")
            return []

    def _send_to_upsert(self, rows: list[dict]):
        """파싱된 행 리스트를 서버 업서트 API 전송 규격에 맞춰 개별 전송합니다."""
        import json
        import urllib.request
        
        # 1. 대상 테이블 설정 로드
        table_config = {}
        try:
            # directory_watcher.py 의 위치 (server/parsers/) 를 기준으로 상대 경로 설정
            # directory_watcher.py 의 위치 (server/parsers/) 를 기준으로 상대 경로 설정
            global_config_path = os.path.abspath(os.path.join(script_dir, "..", "config", "table_config.json"))
            if os.path.exists(global_config_path):
                with open(global_config_path, "r", encoding="utf-8") as f:
                    table_config = json.load(f)
        except Exception as e:
            logger.warning(f"Could not load global table_config: {e}")

        # 2. 현재 워크스페이스의 table_name 결정
        table_name = self.default_table_name
        if self.config_path and os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                table_name = config.get("table_name", table_name)
            except: pass

        if not table_name:
            logger.error("No table_name identified for upsert.")
            return

        # 3. 비즈니스 키 및 컬럼 매핑 정보 획득
        table_info = table_config.get(table_name, {})
        bk_col = table_info.get("business_key", "id")
        defined_cols = table_info.get("display_columns", [])
        
        # 4. 배치 단위로 정규화 및 전역 전송 (Agent Optimization)
        print('배치 전송')
        base_url = f"http://{endpoint}/tables/{table_name}/upsert/batch"
        batch_size = 50
        
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
                    items.append({
                        "business_key_val": bk_val,
                        "updates": normalized_row,
                        "source_name": "custom_script" if os.path.exists(os.path.join(self.scripts_path, "custom_parser.py")) else "batch_ingester",
                        "updated_by": "system"
                    })
            
            if not items:
                continue

            try:
                # [통합 업데이트 API 적용]
                unified_url = f"http://{endpoint}/tables/{table_name}/data/updates"
                payload = json.dumps({"updates": items}).encode("utf-8")
                
                req = urllib.request.Request(unified_url, data=payload, method="PUT")
                req.add_header("Content-Type", "application/json")
                with urllib.request.urlopen(req) as response:
                    logger.info(f"Unified batch update success ({len(items)} rows). Status: {response.status}")
            except Exception as e:
                logger.error(f"Failed to send unified batch update: {e}")

class WorkspaceWatcher:
    """
    Monitors all ingestion workspaces for new files.
    """
    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        self.observer = Observer()
        self.watch_count = 0

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
                    handler = IngestionHandler(workspace_root, config_path, archives_path)
                    self.observer.schedule(handler, root, recursive=False)
                    self.watch_count += 1
                    logger.info(f"Watching: {root} (using config: {os.path.basename(config_path)})")
                else:
                    # Agent D v13: config 가 없더라도 custom_parser.py 가 있으면 감지 대상으로 포함
                    scripts_path = os.path.join(workspace_root, "scripts", "custom_parser.py")
                    if os.path.exists(scripts_path):
                        table_name = os.path.basename(workspace_root)
                        handler = IngestionHandler(workspace_root, None, archives_path, default_table_name=table_name)
                        self.observer.schedule(handler, root, recursive=False)
                        self.watch_count += 1
                        logger.info(f"Watching: {root} (Script-only workspace, Table: {table_name})")
                    else:
                        logger.warning(f"Skipping {root}: No JSON config or custom_parser found.")

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
