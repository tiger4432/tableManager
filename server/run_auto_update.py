import os
import sys
import time
import shutil
import logging
import importlib.util
import re
import json
import threading
from abc import ABC, abstractmethod
from datetime import datetime

# -----------------------------------------------------------------
# [자가 의존성 설치 가드]
# croniter 라이브러리가 미설치 상태일 경우, 기동 시 백그라운드에서 자동 설치합니다.
# -----------------------------------------------------------------
try:
    from croniter import croniter
except ImportError:
    import subprocess
    print("[Scheduler] Installing 'croniter' dependency automatically via pip...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "croniter"])
        from croniter import croniter
        print("[Scheduler] 'croniter' successfully installed.")
    except Exception as e:
        print(f"[Scheduler] Fatal: Failed to auto-install 'croniter': {e}")
        sys.exit(1)

# Setup Logging
from utils.logger import get_process_logger
logger = get_process_logger("Scheduler", "auto_update.log")

class BaseCollector(ABC):
    """
    클래스 상속 기반의 테이블 전용 수집기(Collector)의 공통 규격을 정의하는 베이스 추상 클래스입니다.
    """
    def __init__(self, table_name: str):
        self.table_name = table_name
        self.logger = logging.getLogger(f"Scheduler.Collector.{table_name}")
        self.cron_expression = None
        self.next_run = None
        self.last_run = None
        self.last_status = "PENDING"
        self.last_error = None
        self.script_path = None
        
        server_dir = os.path.dirname(os.path.abspath(__file__))
        self.target_dir = os.path.join(server_dir, "ingestion_workspace", table_name, "raws")
        os.makedirs(self.target_dir, exist_ok=True)

    @abstractmethod
    def collect(self) -> list[str]:
        """
        임시 데이터 파일들을 수집/생성하여 그 로컬 경로 목록을 반환합니다.
        """
        pass

    def execute(self):
        """
        수집된 파일들을 해당 테이블의 raws/ 폴더로 원자적 복사(Atomic Copy & Rename) 방식으로 안전하게 전송합니다.
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
                shutil.copy2(file_path, tmp_dest)
                os.replace(tmp_dest, final_dest)
                self.logger.info(f"Successfully transferred '{filename}' to ingestion queue.")
                
                if os.path.dirname(os.path.abspath(file_path)) != os.path.abspath(self.target_dir):
                    try:
                        os.remove(file_path)
                    except Exception as e:
                        self.logger.warning(f"Could not clean up temporary source file '{file_path}': {e}")
        except Exception as e:
            self.logger.error(f"Failed to execute collection lifecycle for table '{self.table_name}': {e}")
            raise e

class GenericScriptRunnerCollector:
    """
    임의의 독립 스크립트를 주석에 기재된 크론 일정에 맞춰 기동하고,
    그 표준 출력(stdout)을 CSV 파일로 가공하여 raws/ 폴더에 원자적 적재하는 범용 래퍼 컬렉터입니다.
    """
    def __init__(self, table_name: str, script_path: str, cron_expression: str, filename_prefix: str):
        self.table_name = table_name
        self.script_path = script_path
        self.cron_expression = cron_expression
        self.filename_prefix = filename_prefix
        self.logger = logging.getLogger(f"Scheduler.ScriptRunner.{table_name}.{os.path.basename(script_path)}")
        self.last_run = None
        self.last_status = "PENDING"
        self.last_error = None
        self.last_mtime = 0
        try:
            self.last_mtime = os.path.getmtime(script_path)
        except:
            pass
        
        server_dir = os.path.dirname(os.path.abspath(__file__))
        self.target_dir = os.path.join(server_dir, "ingestion_workspace", table_name, "raws")
        os.makedirs(self.target_dir, exist_ok=True)
        
        # Calculate initial next run time
        self.next_run = croniter(self.cron_expression, datetime.now()).get_next(datetime)

    def execute(self):
        """
        스크립트를 동적으로 로드 및 exec() 실행하여 메모리상에서 'out' 변수를 낚아채며,
        만약 'out' 변수가 감지되지 않을 경우 기존 subprocess stdout 캡처 방식으로 폴백합니다.
        """
        import io
        import csv
        import subprocess
        
        # Update next run time before executing
        self.next_run = croniter(self.cron_expression, datetime.now()).get_next(datetime)
        
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.filename_prefix}_{timestamp_str}.csv"
        final_dest = os.path.join(self.target_dir, filename)
        tmp_dest = final_dest + ".tmp"
        
        self.logger.info(f"Triggering execution of script '{os.path.basename(self.script_path)}'...")
        
        # 1. exec()를 통한 인스턴스 전역 변수 'out' 가로채기 감지 시도
        try:
            script_dir = os.path.dirname(self.script_path)
            if script_dir not in sys.path:
                sys.path.insert(0, script_dir)
                
            with open(self.script_path, "r", encoding="utf-8") as f:
                code_content = f.read()
                
            global_ns = {
                "__file__": self.script_path,
                "__name__": "__main__"
            }
            local_ns = {}
            
            # exec 실행
            exec(code_content, global_ns, local_ns)
            
            # out 변수 검출 (None 여부 명시적 체크를 통해 DataFrame Truth Value Ambiguity 버그 차단)
            out_data = local_ns.get("out")
            if out_data is None:
                out_data = global_ns.get("out")
            
            if out_data is not None:
                self.logger.info(f"Captured 'out' variable ({type(out_data).__name__}). Formatting to CSV...")
                csv_content = ""
                
                # 타입 감지 및 CSV 인코딩
                if isinstance(out_data, str):
                    csv_content = out_data
                elif isinstance(out_data, list):
                    output = io.StringIO()
                    writer = csv.writer(output, lineterminator='\n')
                    
                    if out_data and isinstance(out_data[0], dict):
                        # 딕셔너리 리스트 -> 키명을 헤더로 매핑
                        headers = list(out_data[0].keys())
                        dict_writer = csv.DictWriter(output, fieldnames=headers, lineterminator='\n')
                        dict_writer.writeheader()
                        dict_writer.writerows(out_data)
                    else:
                        # 2차원 리스트
                        writer.writerows(out_data)
                    csv_content = output.getvalue()
                elif hasattr(out_data, "to_csv"):
                    # Pandas DataFrame 등
                    csv_content = out_data.to_csv(index=False)
                else:
                    csv_content = str(out_data)
                    
                if not csv_content.strip():
                    self.logger.warning("Captured 'out' variable resulted in empty CSV content. Skipping.")
                    return
                    
                with open(tmp_dest, "w", encoding="utf-8", newline="") as f:
                    f.write(csv_content)
                os.replace(tmp_dest, final_dest)
                self.logger.info(f"Successfully wrote captured 'out' data to raw file '{filename}'.")
                return
                
        except Exception as e:
            self.logger.warning(f"In-memory exec() failed or 'out' variable not found: {e}. Falling back to stdout capture...")

        # 2. [폴백 모드] subprocess 표준 출력(stdout, print) 캡처 기동
        try:
            python_exe = sys.executable
            result = subprocess.run(
                [python_exe, self.script_path],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore"
            )
            
            if result.returncode != 0:
                err_msg = f"Script process exited with error code {result.returncode}. stderr: {result.stderr.strip()}"
                self.logger.error(err_msg)
                raise RuntimeError(err_msg)
                
            stdout_content = result.stdout
            if not stdout_content.strip():
                self.logger.warning(f"Script stdout was empty. Skipping file generation.")
                return
                
            with open(tmp_dest, "w", encoding="utf-8", newline="") as f:
                f.write(stdout_content)
                
            os.replace(tmp_dest, final_dest)
            self.logger.info(f"Successfully collected stdout and generated raw file '{filename}'.")
            
        except Exception as e:
            self.logger.error(f"Fatal: Failed to execute script runner via subprocess: {e}")
            raise e

def parse_script_comments(script_path: str) -> dict:
    """
    파이썬 파일의 상단 20줄을 스캔하여 주석에 적힌 크론 일정 및 파일명 접두사 설정값을 반환합니다.
    """
    config = {
        "schedule": None,
        "filename_prefix": os.path.basename(script_path)[:-3]
    }
    try:
        with open(script_path, "r", encoding="utf-8") as f:
            for _ in range(20):
                line = f.readline()
                if not line:
                    break
                line = line.strip()
                if line.startswith("#"):
                    content = line[1:].strip()
                    if ":" in content:
                        key, val = content.split(":", 1)
                        key = key.strip().lower()
                        val = val.strip()
                        if key == "schedule":
                            config["schedule"] = val
                        elif key == "filename_prefix":
                            config["filename_prefix"] = val
    except Exception as e:
        logger.warning(f"Failed to parse script comments for {script_path}: {e}")
    return config

class MultiDiscoveryScheduler:
    """
    ingestion_workspace/*/auto_update/*.py 디렉토리를 통합 모니터링하며,
    주석 기반의 Cron 설정 또는 클래스 상속 수집기들을 스케줄러 스레드로 자동 구동하는 디스커버리 스케줄러입니다.
    """
    def __init__(self, check_interval: int = 5):
        self.check_interval = check_interval
        self.server_dir = os.path.dirname(os.path.abspath(__file__))
        self.workspace_dir = os.path.join(self.server_dir, "ingestion_workspace")
        self.status_file_path = os.path.join(self.server_dir, "config", "scheduler_status.json")
        self.collectors = []
        self._lock = threading.Lock()

    def discover_and_load_collectors(self):
        """
        ingestion_workspace/{table_name}/auto_update/*.py 목록을 스캔하여 동적으로 로드합니다.
        """
        with self._lock:
            # 기존 상태 매핑 캐시
            status_map = {}
            for col in self.collectors:
                key = (col.table_name, os.path.basename(col.script_path) if col.script_path else col.__class__.__name__)
                status_map[key] = {
                    "last_run": col.last_run,
                    "last_status": col.last_status,
                    "last_error": col.last_error
                }

            self.collectors = []
            if not os.path.exists(self.workspace_dir):
                logger.warning(f"Ingestion workspace directory not found at: {self.workspace_dir}")
                return

            for table_name in os.listdir(self.workspace_dir):
                table_path = os.path.join(self.workspace_dir, table_name)
                if not os.path.isdir(table_path):
                    continue

                auto_update_path = os.path.join(table_path, "auto_update")
                if not os.path.exists(auto_update_path) or not os.path.isdir(auto_update_path):
                    continue

                for filename in os.listdir(auto_update_path):
                    if filename.endswith(".py"):
                        script_path = os.path.join(auto_update_path, filename)
                        self._load_collector_from_script(table_name, script_path)

            # 복원
            for col in self.collectors:
                key = (col.table_name, os.path.basename(col.script_path) if col.script_path else col.__class__.__name__)
                if key in status_map:
                    col.last_run = status_map[key]["last_run"]
                    col.last_status = status_map[key]["last_status"]
                    col.last_error = status_map[key]["last_error"]

            self._write_status_file()

    def _load_collector_from_script(self, table_name: str, script_path: str):
        """
        주석을 분석하여 # schedule: 이 있으면 GenericScriptRunnerCollector로 로드하고,
        없으면 리플렉션을 통해 BaseCollector 클래스를 로드합니다.
        """
        comment_config = parse_script_comments(script_path)
        
        if comment_config["schedule"]:
            try:
                cron_expr = comment_config["schedule"]
                croniter(cron_expr)
                
                collector_inst = GenericScriptRunnerCollector(
                    table_name=table_name,
                    script_path=script_path,
                    cron_expression=cron_expr,
                    filename_prefix=comment_config["filename_prefix"]
                )
                self.collectors.append(collector_inst)
                logger.info(f"Registered Comment-Driven Script Runner: '{os.path.basename(script_path)}' for table '{table_name}' (Cron: {cron_expr}, Next Run: {collector_inst.next_run})")
                return
            except Exception as e:
                logger.error(f"Invalid cron expression '{comment_config['schedule']}' in {script_path}: {e}")

        module_name = f"dynamic_collector_{table_name}_{os.path.basename(script_path)[:-3]}"
        try:
            script_dir = os.path.dirname(script_path)
            if script_dir not in sys.path:
                sys.path.insert(0, script_dir)
                
            spec = importlib.util.spec_from_file_location(module_name, script_path)
            if spec is None or spec.loader is None:
                return
                
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            found_class = False
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and issubclass(attr, BaseCollector) and attr is not BaseCollector:
                    try:
                        collector_inst = attr()
                        collector_inst.script_path = script_path
                        
                        if getattr(collector_inst, "cron_expression", None):
                            collector_inst.next_run = croniter(collector_inst.cron_expression, datetime.now()).get_next(datetime)
                        
                        self.collectors.append(collector_inst)
                        logger.info(f"Registered Class Collector: '{attr_name}' for table '{table_name}'")
                        found_class = True
                    except Exception as e:
                        logger.error(f"Failed to instantiate class '{attr_name}' in {script_path}: {e}")
            
            if not found_class and not comment_config["schedule"]:
                logger.warning(f"Script '{os.path.basename(script_path)}' lacks both valid BaseCollector class and # schedule: comments.")
        except Exception as e:
            logger.error(f"Failed to load script module '{script_path}': {e}")

    def _write_status_file(self):
        """
        현재 메모리상 활성 수집기 목록 상태를 JSON 파일로 직렬화하여 영속화합니다.
        """
        try:
            status_data = {
                "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "collectors": []
            }
            with self._lock:
                for col in self.collectors:
                    script_name = os.path.basename(col.script_path) if col.script_path else col.__class__.__name__
                    status_data["collectors"].append({
                        "table_name": col.table_name,
                        "script_name": script_name,
                        "script_path": col.script_path,
                        "cron_expression": getattr(col, "cron_expression", None) or "Manual-only",
                        "next_run": col.next_run.strftime("%Y-%m-%d %H:%M:%S") if getattr(col, "next_run", None) else None,
                        "last_run": col.last_run,
                        "last_status": col.last_status,
                        "last_error": col.last_error
                    })
            
            config_dir = os.path.dirname(self.status_file_path)
            os.makedirs(config_dir, exist_ok=True)
            with open(self.status_file_path, "w", encoding="utf-8") as f:
                json.dump(status_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to write scheduler status file: {e}")

    def run_collector_on_demand(self, table_name: str, script_name: str):
        """
        On-Demand 강제 구동 지시를 받아 비동기로 대상 수집기를 실행합니다.
        """
        for collector in self.collectors:
            col_script_name = os.path.basename(getattr(collector, "script_path", "")) if getattr(collector, "script_path", None) else collector.__class__.__name__
            if collector.table_name == table_name and col_script_name == script_name:
                logger.info(f"[Trigger] On-Demand trigger received. Executing collector '{script_name}' for table '{table_name}' immediately...")
                threading.Thread(target=self.execute_collector, args=(collector,), daemon=True).start()
                return True
        logger.warning(f"[Trigger] Trigger requested but no matching collector found for table='{table_name}', script='{script_name}'")
        return False

    def execute_collector(self, collector):
        """
        수집기를 래핑 실행하고 상태를 기록합니다.
        """
        collector.last_run = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        collector.last_status = "RUNNING"
        collector.last_error = None
        self._write_status_file()
        
        try:
            collector.execute()
            collector.last_status = "SUCCESS"
        except Exception as err:
            collector.last_status = "FAIL"
            collector.last_error = str(err)
            logger.error(f"Collector Execution Failed for table '{collector.table_name}': {err}")
        finally:
            self._write_status_file()

    def run(self):
        """
        주기적으로 DB의 SYSTEM_RELOAD 및 SCHEDULER_RUN_NOW 아웃박스 신호를 모니터링하며,
        동시에 크론 스케줄 타이밍을 검사해 수집기들을 가동합니다.
        """
        logger.info("Initializing Ingestion Auto Discovery engine...")
        self.discover_and_load_collectors()
        
        logger.info(f"Initialization complete. Active collectors: {len(self.collectors)}")
        logger.info(f"Scheduler daemon started. Tick interval: {self.check_interval}s. Press Ctrl+C to terminate.")
        
        last_reload_event_id = 0
        
        # 기동 시점 최신 reload 이벤트 ID 스캔해서 싱크 맞춤
        try:
            from database.database import SessionLocal
            from database.models import DatabaseOutbox
            db = SessionLocal()
            latest_reload = db.query(DatabaseOutbox).filter(
                DatabaseOutbox.event_type == "SYSTEM_RELOAD"
            ).order_by(DatabaseOutbox.id.desc()).first()
            if latest_reload:
                last_reload_event_id = latest_reload.id
            db.close()
        except Exception as e:
            logger.warning(f"Failed to query initial SYSTEM_RELOAD outbox id: {e}")

        try:
            while True:
                # 1. 무중단 핫 리로드 (SYSTEM_RELOAD) 및 강제 실행(SCHEDULER_RUN_NOW) 감시
                try:
                    from database.database import SessionLocal
                    from database.models import DatabaseOutbox
                    db = SessionLocal()
                    
                    # 1-1. SYSTEM_RELOAD 감시
                    latest_reload = db.query(DatabaseOutbox).filter(
                        DatabaseOutbox.event_type == "SYSTEM_RELOAD"
                    ).order_by(DatabaseOutbox.id.desc()).first()
                    
                    if latest_reload and latest_reload.id > last_reload_event_id:
                        last_reload_event_id = latest_reload.id
                        logger.info(f"[Reload] Auto Update Scheduler detected SYSTEM_RELOAD trigger (Event ID: {latest_reload.id}). Re-scanning workspace...")
                        
                        # 모듈 캐시 초기화
                        keys_to_remove = [k for k in sys.modules.keys() if k.startswith("dynamic_collector_")]
                        for k in keys_to_remove:
                            sys.modules.pop(k, None)
                            
                        # 수집기 리스트 재구성
                        self.discover_and_load_collectors()
                        logger.info(f"[Reload] Re-scan complete. Total active collectors: {len(self.collectors)}")
                    
                    # 1-2. SCHEDULER_RUN_NOW 감시
                    latest_trigger = db.query(DatabaseOutbox).filter(
                        DatabaseOutbox.event_type == "SCHEDULER_RUN_NOW",
                        DatabaseOutbox.processed_chain == False
                    ).first()
                    
                    if latest_trigger:
                        try:
                            payload_data = json.loads(latest_trigger.payload) if isinstance(latest_trigger.payload, str) else latest_trigger.payload
                            table_name = payload_data.get("table_name")
                            script_name = payload_data.get("script_name")
                            
                            self.run_collector_on_demand(table_name, script_name)
                            
                            latest_trigger.processed_chain = True
                            db.commit()
                        except Exception as trig_err:
                            logger.error(f"Failed to handle SCHEDULER_RUN_NOW trigger: {trig_err}")
                    
                    db.close()
                except Exception as e:
                    logger.warning(f"Database outbox polling failed inside scheduler: {e}")

                # 2. 크론 스케줄링 가동 및 동적 파일 변경 감지
                try:
                    now = datetime.now()
                    for collector in self.collectors:
                        # GenericScriptRunnerCollector 일 경우 파일 동적 변경 감지 수행
                        if isinstance(collector, GenericScriptRunnerCollector):
                            try:
                                current_mtime = os.path.getmtime(collector.script_path)
                                if current_mtime > collector.last_mtime:
                                    collector.last_mtime = current_mtime
                                    comment_config = parse_script_comments(collector.script_path)
                                    if comment_config["schedule"] and comment_config["schedule"] != collector.cron_expression:
                                        old_cron = collector.cron_expression
                                        collector.cron_expression = comment_config["schedule"]
                                        collector.next_run = croniter(collector.cron_expression, datetime.now()).get_next(datetime)
                                        logger.info(f"[Auto-Reload] Detected schedule change in '{os.path.basename(collector.script_path)}'. Updated Cron: {old_cron} -> {collector.cron_expression} (Next Run: {collector.next_run})")
                                    if comment_config["filename_prefix"] != collector.filename_prefix:
                                        collector.filename_prefix = comment_config["filename_prefix"]
                            except Exception as file_err:
                                logger.warning(f"Failed to check file mtime for {collector.script_path}: {file_err}")

                        if getattr(collector, "cron_expression", None) and getattr(collector, "next_run", None):
                            if now >= collector.next_run:
                                self.execute_collector(collector)
                        else:
                            self.execute_collector(collector)
                except Exception as e:
                    logger.error(f"Scheduler runtime error: {e}")
                    
                time.sleep(self.check_interval)
        except KeyboardInterrupt:
            logger.info("Auto Update Scheduler daemon terminated gracefully.")

if __name__ == "__main__":
    # 5초 주기로 스케줄 타이밍 검사
    scheduler = MultiDiscoveryScheduler(check_interval=5)
    scheduler.run()
