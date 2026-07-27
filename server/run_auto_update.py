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

from croniter import croniter

# Setup Logging
from utils.logger import get_process_logger
from utils.auto_update_control import read_disabled_scripts
from utils import heartbeat
import paths  # single override point (ASSY_DATA_ROOT)
import config_backup
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
        
        self.target_dir = os.path.join(paths.WORKSPACE_DIR, table_name, "raws")
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
    def __init__(self, table_name: str, script_path: str, cron_expression: str, filename_prefix: str, server_dir: str = None):
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

        server_dir = server_dir or paths.DATA_ROOT
        self.target_dir = os.path.join(server_dir, "ingestion_workspace", table_name, "raws")
        os.makedirs(self.target_dir, exist_ok=True)
        
        # Calculate initial next run time
        self.next_run = croniter(self.cron_expression, datetime.now()).get_next(datetime)

    def execute(self):
        """
        스크립트를 동적으로 로드 및 exec() 실행하여 메모리상에서 'out' 변수를 낚아채며,
        만약 'out' 변수가 감지되지 않을 경우 기존 subprocess stdout 캡처 방식으로 폴백합니다.

        [Failure contract] "could not check" must never be reported as "nothing is wrong".
          * 'out' absent, no exception -> a stdout collector. The fallback is the
            normal path (INFO).
          * 'out' assigned None        -> the script declared it has nothing to
            give: FAIL immediately, no stdout re-run.
          * 'out' present but empty    -> nothing to collect this cycle. SUCCESS.
          * execution RAISED           -> ERROR + traceback. Still attempt the
            fallback, but if that also yields nothing, raise so the run is FAIL.
        Full table: docs/guide/AUTO_UPDATE_GUIDE.md, "실패 판정 규칙".
        """
        import io
        import csv
        import subprocess
        import traceback

        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.filename_prefix}_{timestamp_str}.csv"
        final_dest = os.path.join(self.target_dir, filename)
        tmp_dest = final_dest + ".tmp"

        self.logger.info(f"Triggering execution of script '{os.path.basename(self.script_path)}'...")

        # 1. exec()를 통한 인스턴스 전역 변수 'out' 가로채기 감지 시도
        #
        # [Contract] This block keeps THREE outcomes strictly separate:
        #   (a) ran fine, 'out' never defined -> a stdout collector; the fallback
        #                                        is the normal path (INFO).
        #   (b) ran fine, 'out' set to None   -> the script declared it has
        #                                        nothing to give: FAIL, no fallback.
        #   (c) execution raised              -> script (or runner) is broken;
        #                                        ERROR + traceback.
        # (a) and (c) used to collapse into one WARNING line, so a run that
        # collected zero rows because it had crashed was reported as a clean
        # success. (b) looked identical to (a) because `.get("out")` cannot tell
        # "assigned None" from "never defined" - and collectors in the wild are
        # written believing `out = None` raises an error, e.g.
        # ingestion_workspace/bonding_map/auto_update/fetch_data.py.
        out_data = None
        out_declared = False  # 'out' 이름이 실제로 바인딩됐는가 (None 대입과 미정의를 구분)
        exec_error = None  # traceback text when the script raised
        script_ns = {
            "__file__": self.script_path,
            "__name__": "__main__"
        }
        try:
            script_dir = os.path.dirname(self.script_path)
            if script_dir not in sys.path:
                sys.path.insert(0, script_dir)

            with open(self.script_path, "r", encoding="utf-8") as f:
                code_content = f.read()

            # [REQUIRED] Pass ONE dict for both globals and locals. Two distinct
            # dicts make exec() run the file with class-body scoping: module-level
            # `def`/`import` bind into locals, but function bodies resolve names
            # via LOAD_GLOBAL and never see them. A helper called from inside
            # another function - or a module-level import used inside a function -
            # then dies with NameError and the collector silently gathers nothing.
            # One dict restores ordinary module scoping.
            # (Module-level calls compile to LOAD_NAME, which does consult locals,
            # which is why only some collectors appeared broken.)
            exec(code_content, script_ns)

            # out 변수 검출 (None 여부 명시적 체크를 통해 DataFrame Truth Value Ambiguity 버그 차단)
            out_declared = "out" in script_ns
            out_data = script_ns.get("out")

        except SystemExit as e:
            # A collector ending in sys.exit(0) completed normally - honour its
            # 'out'. Uncaught, SystemExit is a BaseException and so passes
            # straight through execute_collector() and check_and_run_schedules()
            # (both catch only Exception), terminating the scheduler daemon.
            if e.code in (0, None):
                out_declared = "out" in script_ns
                out_data = script_ns.get("out")
            else:
                exec_error = f"Script terminated with sys.exit({e.code!r})."
                self.logger.error(
                    f"Script '{os.path.basename(self.script_path)}' exited with a non-zero "
                    f"code during in-memory execution. {exec_error} "
                    f"Attempting stdout fallback; the run FAILS if that yields nothing."
                )
        except Exception:
            exec_error = traceback.format_exc()
            self.logger.error(
                f"In-memory execution of '{os.path.basename(self.script_path)}' RAISED. "
                f"The script collected nothing this way. Attempting stdout fallback; "
                f"the run FAILS if that also yields nothing.\n{exec_error}"
            )

        if exec_error is None and out_declared and out_data is None:
            # The script ran to completion and explicitly set `out = None`, i.e.
            # it declared it has nothing to give. That is a failure, and it must
            # NOT fall through to the stdout re-run: collectors that do this are
            # error handlers around a network fetch, so re-running the file would
            # repeat the external call and still produce nothing.
            # To report "nothing to collect this cycle" without failing, a script
            # assigns an empty value (`out = []` / `out = ""`) instead.
            msg = (
                f"Script '{os.path.basename(self.script_path)}' set 'out = None': it ran to "
                f"completion but explicitly produced no data. Treating as a failure "
                f"(no stdout fallback). The script's own error output, if any, is on the "
                f"scheduler's stderr - collectors typically print the cause there."
            )
            self.logger.error(msg)
            raise RuntimeError(msg)

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
                # 'out' existed but was empty: nothing to collect this cycle. Normal.
                self.logger.warning("Captured 'out' variable resulted in empty CSV content. Skipping.")
                return

            with open(tmp_dest, "w", encoding="utf-8", newline="") as f:
                f.write(csv_content)
            os.replace(tmp_dest, final_dest)
            self.logger.info(f"Successfully wrote captured 'out' data to raw file '{filename}'.")
            return

        if exec_error is None:
            # Normal path: this script print()s its output instead of setting 'out'.
            self.logger.info(
                f"No 'out' variable defined by '{os.path.basename(self.script_path)}'. "
                f"Running as a stdout collector..."
            )

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
                if exec_error:
                    # Execution died AND the fallback captured nothing: this run
                    # failed. Returning quietly here is what reported a zero-row
                    # failure as SUCCESS (the original bug).
                    raise RuntimeError(
                        "Collector produced no data: in-memory execution failed AND the "
                        "stdout fallback captured nothing. Original error:\n" + exec_error
                    )
                # 정상: 'out'도 없고 출력도 없다 = 이번 주기에 수집할 게 없었다.
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
    def __init__(self, check_interval: int = 5, server_dir: str = None):
        self.check_interval = check_interval
        self.server_dir = server_dir or paths.DATA_ROOT
        self.workspace_dir = os.path.join(self.server_dir, "ingestion_workspace")
        self.status_file_path = os.path.join(self.server_dir, "config", "scheduler_status.json")
        self.config_dir = os.path.join(self.server_dir, "config")
        self.collectors = []
        self._lock = threading.RLock()
        # 0.0 = "check on the very first tick", so a scheduler that starts after
        # a week of downtime takes the missed snapshot at boot rather than waiting.
        self._last_backup_check = 0.0

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
                    filename_prefix=comment_config["filename_prefix"],
                    server_dir=self.server_dir
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

    def _collector_key(self, collector) -> str:
        """제어 파일 규격('<workspace>/<script.py>')과 일치하는 수집기 식별 키를 반환합니다."""
        script_name = os.path.basename(collector.script_path) if getattr(collector, "script_path", None) else collector.__class__.__name__
        return f"{collector.table_name}/{script_name}"

    def _write_status_file(self):
        """
        현재 메모리상 활성 수집기 목록 상태를 JSON 파일로 직렬화하여 영속화합니다.
        """
        try:
            disabled_set = read_disabled_scripts(self.server_dir)
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
                        "last_error": col.last_error,
                        "active": self._collector_key(col) not in disabled_set
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
        [계약] run-now(수동 실행)는 active(disabled) 상태와 무관하게 항상 실행합니다 — 수동 실행은 명시적 의도.
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
        
        if getattr(collector, "cron_expression", None):
            try:
                collector.next_run = croniter(collector.cron_expression, datetime.now()).get_next(datetime)
            except Exception as e:
                logger.error(f"Failed to calculate next_run: {e}")
                
        self._write_status_file()
        
        try:
            collector.execute()
            collector.last_status = "SUCCESS"
        except Exception as err:
            import traceback
            collector.last_status = "FAIL"
            collector.last_error = traceback.format_exc()
            logger.error(f"Collector Execution Failed for table '{collector.table_name}': {err}")
        finally:
            self._write_status_file()

    def check_and_run_schedules(self, now: datetime = None):
        """
        크론 스케줄 타이밍 검사 + 동적 파일 변경 감지를 수행하고, 도래한 수집기를 실행합니다.
        [핫 반영] 매 호출 시 제어 파일(auto_update_control.json)을 읽어 disabled 수집기는
        실행을 스킵하고(next_run만 전진) last_status="SKIPPED"로 status에 반영합니다.
        재기동 없이 toggle이 즉시 적용됩니다.
        """
        now = now or datetime.now()
        disabled_set = read_disabled_scripts(self.server_dir)
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
                    key = self._collector_key(collector)
                    if key in disabled_set:
                        # 비활성 수집기: 실행 스킵, 다음 스케줄로 전진, 상태 파일에 SKIPPED 기록
                        try:
                            collector.next_run = croniter(collector.cron_expression, now).get_next(datetime)
                        except Exception as cron_err:
                            logger.error(f"Failed to advance next_run for disabled collector '{key}': {cron_err}")
                        collector.last_status = "SKIPPED"
                        collector.last_error = None
                        logger.info(f"[Skip] Collector '{key}' is disabled via control file. Skipping scheduled run (Next Run: {collector.next_run}).")
                        self._write_status_file()
                    else:
                        self.execute_collector(collector)

    def maybe_backup_configs(self, now=None):
        """Weekly ``server/config/`` snapshot — a maintenance job, NOT a collector.

        [Why it lives in this process but outside the collector mechanism]
        A collector is per-table: it writes a CSV into
        ``ingestion_workspace/<table>/raws/``, where the directory watcher picks it
        up and ingests it into that table. A config backup has no table and must
        never be ingested, so registering it as a collector would be structurally
        wrong — and it would also be indistinguishable from a broken one, since a
        collector that yields nothing now reports FAIL by design.

        What it does reuse is this daemon's tick. This is the system's only
        time-driven process, and adding a sixth supervised process for a weekly
        file copy would cost more than it buys.

        [Why the cadence is not a cron expression] ``config_backup.due()`` compares
        against the newest snapshot on disk. A cron instant is simply missed when
        the machine is off at that moment; deriving the cadence from the files
        makes a missed week self-heal on the next tick. See config_backup.py.
        """
        now_wall = time.time()
        if now_wall - self._last_backup_check < config_backup.CHECK_INTERVAL_SEC:
            return None
        self._last_backup_check = now_wall
        try:
            return config_backup.run_scheduled(config_dir=self.config_dir, now=now)
        except Exception as e:
            # Never let a backup failure stop the collectors from running.
            logger.error(f"[ConfigBackup] maintenance cycle raised: {e}")
            return None

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
                # [B1/B2] Progress beat from the scheduler's own loop
                # (check_interval = 5 s).
                heartbeat.beat("scheduler")
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

                # 2. 크론 스케줄링 가동 및 동적 파일 변경 감지 (disabled 스크립트 핫 스킵 포함)
                try:
                    self.check_and_run_schedules()
                except Exception as e:
                    logger.error(f"Scheduler runtime error: {e}")

                # 3. 주간 config 스냅샷 (수집기가 아닌 유지보수 작업 — maybe_backup_configs 참조)
                self.maybe_backup_configs()

                time.sleep(self.check_interval)
        except KeyboardInterrupt:
            logger.info("Auto Update Scheduler daemon terminated gracefully.")

if __name__ == "__main__":
    # 5초 주기로 스케줄 타이밍 검사
    scheduler = MultiDiscoveryScheduler(check_interval=5)
    scheduler.run()
