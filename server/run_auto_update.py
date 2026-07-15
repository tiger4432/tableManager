import os
import sys
import time
import shutil
import logging
import importlib.util
from abc import ABC, abstractmethod

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s [%(name)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(os.path.dirname(os.path.abspath(__file__)), "auto_update.log"), encoding='utf-8')
    ]
)
logger = logging.getLogger("Scheduler")

class BaseCollector(ABC):
    """
    모든 테이블 전용 수집기(Collector)의 공통 규격을 정의하는 베이스 추상 클래스입니다.
    """
    def __init__(self, table_name: str):
        self.table_name = table_name
        self.logger = logging.getLogger(f"Collector.{table_name}")
        
        # Cwd에 관계없이 server/ingestion_workspace/{table_name}/raws 경로를 해소합니다.
        server_dir = os.path.dirname(os.path.abspath(__file__))
        self.target_dir = os.path.join(server_dir, "ingestion_workspace", table_name, "raws")
        os.makedirs(self.target_dir, exist_ok=True)

    @abstractmethod
    def collect(self) -> list[str]:
        """
        외부 서버나 파일 시스템 등으로부터 인제션할 원천 파일들을 수집/생성하고,
        수집 완료된 로컬 파일 경로들의 리스트를 반환합니다.
        """
        pass

    def execute(self):
        """
        수집된 임시 파일들을 해당 테이블의 raws/ 폴더로 원자적 복사(Atomic Copy & Rename) 방식으로 안전하게 전송합니다.
        """
        try:
            file_paths = self.collect()
            if not file_paths:
                return
            
            for file_path in file_paths:
                if not os.path.exists(file_path):
                    continue
                
                filename = os.path.basename(file_path)
                final_dest = os.path.join(self.target_dir, filename)
                tmp_dest = final_dest + ".tmp"
                
                self.logger.info(f"Transferring raw file '{filename}' to target raws workspace...")
                
                # Atomic Copy: 임시 확장자(.tmp)로 먼저 복사한 후 최종 파일명으로 대체하여 Watcher가 중간 상태의 파일을 파싱하지 않도록 차단
                shutil.copy2(file_path, tmp_dest)
                os.replace(tmp_dest, final_dest)
                
                self.logger.info(f"Successfully transferred '{filename}' to ingestion queue.")
                
                # 수집 처리가 끝난 로컬 소스 임시 파일 소거 (중복 적재 방지)
                if os.path.dirname(os.path.abspath(file_path)) != os.path.abspath(self.target_dir):
                    try:
                        os.remove(file_path)
                    except Exception as e:
                        self.logger.warning(f"Could not clean up temporary source file '{file_path}': {e}")
        except Exception as e:
            self.logger.error(f"Failed to execute collection lifecycle for table '{self.table_name}': {e}")

class MultiDiscoveryScheduler:
    """
    ingestion_workspace 내의 각 테이블별 auto_update 폴더에 기입된 collect_*.py 스크립트들을
    동적으로 찾아 로드하고 주기적으로 순차 가동해주는 백그라운드 엔진입니다.
    """
    def __init__(self, check_interval: int = 10):
        self.check_interval = check_interval
        self.server_dir = os.path.dirname(os.path.abspath(__file__))
        self.workspace_dir = os.path.join(self.server_dir, "ingestion_workspace")
        self.collectors = []

    def discover_and_load_collectors(self):
        """
        ingestion_workspace/{table_name}/auto_update/collect_*.py 목록을 스캔하여 동적으로 수집기 인스턴스를 확보합니다.
        """
        self.collectors = []
        if not os.path.exists(self.workspace_dir):
            logger.warning(f"Ingestion workspace directory not found at: {self.workspace_dir}")
            return

        # Scan each table folder
        for table_name in os.listdir(self.workspace_dir):
            table_path = os.path.join(self.workspace_dir, table_name)
            if not os.path.isdir(table_path):
                continue

            auto_update_path = os.path.join(table_path, "auto_update")
            if not os.path.exists(auto_update_path) or not os.path.isdir(auto_update_path):
                continue

            # Scan collect_*.py files inside auto_update directory
            for filename in os.listdir(auto_update_path):
                if filename.startswith("collect_") and filename.endswith(".py"):
                    script_path = os.path.join(auto_update_path, filename)
                    self._load_collector_from_script(table_name, script_path)

    def _load_collector_from_script(self, table_name: str, script_path: str):
        """
        리플렉션을 사용하여 수집기 스크립트를 메모리에 모듈로 로드하고, BaseCollector를 상속받은 모든 클래스들을 인스턴스화합니다.
        """
        module_name = f"dynamic_collector_{table_name}_{os.path.basename(script_path)[:-3]}"
        try:
            # Add scripts' table-level auto_update directory to sys.path to resolve relative import patterns smoothly
            script_dir = os.path.dirname(script_path)
            if script_dir not in sys.path:
                sys.path.insert(0, script_dir)
                
            # Spec loading
            spec = importlib.util.spec_from_file_location(module_name, script_path)
            if spec is None or spec.loader is None:
                logger.error(f"Cannot load spec from script: {script_path}")
                return
                
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # Find subclasses of BaseCollector
            found_class = False
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and issubclass(attr, BaseCollector) and attr is not BaseCollector:
                    try:
                        # Instantiate the collector class
                        collector_inst = attr()
                        self.collectors.append(collector_inst)
                        logger.info(f"Successfully loaded and registered collector: {attr_name} for table '{table_name}'")
                        found_class = True
                    except Exception as e:
                        logger.error(f"Failed to instantiate collector class '{attr_name}' from {script_path}: {e}")
            
            if not found_class:
                logger.warning(f"No valid class inheriting from BaseCollector found in {script_path}")
        except Exception as e:
            logger.error(f"Failed to dynamically import module from '{script_path}': {e}")

    def run(self):
        """
        주기적으로 감시 루프를 실행하여 수집기들을 가동합니다.
        """
        logger.info("Auto discovery scan starting...")
        self.discover_and_load_collectors()
        
        logger.info(f"Initialization complete. Total loaded collectors: {len(self.collectors)}")
        logger.info(f"Scheduler daemon started. Tick interval: {self.check_interval}s. Press Ctrl+C to terminate.")
        
        while True:
            try:
                for collector in self.collectors:
                    collector.execute()
            except KeyboardInterrupt:
                logger.info("Auto Update Scheduler daemon terminated gracefully.")
                break
            except Exception as e:
                logger.error(f"Scheduler runtime exception inside main tick loop: {e}")
                
            time.sleep(self.check_interval)

if __name__ == "__main__":
    scheduler = MultiDiscoveryScheduler(check_interval=10)
    scheduler.run()
