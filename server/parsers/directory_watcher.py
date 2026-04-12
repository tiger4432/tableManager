import os
import time
import shutil
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from advanced_ingester import AdvancedIngester

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("DirectoryWatcher")

class IngestionHandler(FileSystemEventHandler):
    """
    Handles file system events and triggers ingestion.
    """
    def __init__(self, workspace_path: str, config_path: str, archives_path: str):
        self.workspace_path = workspace_path
        self.config_path = config_path
        self.archives_path = archives_path
        self.supported_extensions = ('.log', '.txt', '.csv')
        self.processing_files = set() # Agent D v7: Track in-progress files
        
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
        
        if not os.path.exists(file_path):
            logger.debug(f"File vanished during debounce: {file_path}")
            return

        for attempt in range(retries):
            try:
                # 1. Initialize AdvancedIngester for this workspace
                ingester = AdvancedIngester(self.config_path)
                
                # 2. Process the file
                logger.info(f"Starting ingestion for {file_path} (Attempt {attempt+1})")
                ingester.process_file(file_path)
                
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
        if not os.path.exists(self.archives_path):
            os.makedirs(self.archives_path)
            
        filename = os.path.basename(file_path)
        dest_path = os.path.join(self.archives_path, filename)
        
        # Handle filename collisions in archives
        if os.path.exists(dest_path):
            base, ext = os.path.splitext(filename)
            dest_path = os.path.join(self.archives_path, f"{base}_{int(time.time())}{ext}")
            
        shutil.move(file_path, dest_path)
        logger.info(f"Moved {file_path} to {dest_path}")

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
                    logger.warning(f"Skipping {root}: No JSON config found in {config_dir}")

    def start(self):
        if self.watch_count == 0:
            logger.error("No valid 'raws' folders found to watch.")
            return

        self.observer.start()
        logger.info(f"Started observer with {self.watch_count} watches.")
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
