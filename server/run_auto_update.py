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
import event_constants
logger = get_process_logger("Scheduler", "auto_update.log")


def _apply_proxy_policy():
    """수집 스크립트가 볼 프록시 환경을 이 프로세스에서 확정한다.

    왜 여기인가 — 수집 스크립트는 사용자가 쓰고 `exec`로 도는 코드라 각자 프록시를
    다룰 수 없다. 그리고 그 스크립트들이 치는 곳은 **사내 인트라넷**이라 프록시를
    **우회**해야 한다(2026-07-30 실측: 프록시를 경유하면 403).

    ⚠️ 왜 os.environ 을 지우는가 — `urllib.request.getproxies()`는
    `getproxies_environment() or getproxies_registry()`이고, `getproxies_environment()`는
    이름이 `_proxy`로 끝나는 변수를 **값이 있는 것만** 걷는다. `no_proxy`도 `_proxy`로
    끝나므로 **그것 하나만 남아 있어도** dict가 비지 않아 레지스트리가 통째로 무시된다.
    그래서 개별 변수를 비우는 것으로는 부족하고 `*_proxy` 계열을 **전부** 걷어야
    "프록시 설정 없음 = 전부 직결"이 성립한다.

    설정 파일에서 끈다: `auto_update_control.json` 의 `"bypass_proxy": false`.
    기본값은 **직결(true)** — 이것이 이 배포의 실제 동작이고, 값이 없거나 파일이
    깨졌을 때 조용히 반대로 도는 것이 더 나쁘다.
    """
    import json
    from utils.auto_update_control import get_control_path

    bypass = True
    try:
        with open(get_control_path(), "r", encoding="utf-8") as f:
            val = json.load(f).get("bypass_proxy", True)
        if isinstance(val, bool):
            bypass = val
        else:
            logger.warning(
                "auto_update_control.json 의 'bypass_proxy' 가 boolean 이 아닙니다(%r). "
                "기본값 true(직결)로 진행합니다.", val)
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning("auto_update_control.json 을 읽지 못했습니다(%s). "
                       "기본값 true(직결)로 진행합니다.", e)

    if not bypass:
        logger.info("[proxy] bypass_proxy=false - 수집 스크립트가 환경의 프록시 설정을 그대로 씁니다.")
        return

    removed = sorted(k for k in list(os.environ) if k.lower().endswith("_proxy"))
    for k in removed:
        os.environ.pop(k, None)
    # 🔴 지우는 것만으로는 **반대 결과**가 난다. 환경 dict가 비면 위 `or`가 넘어가
    #    **레지스트리**를 조회하고, 운영 머신의 레지스트리에는 사내 프록시가 있다 —
    #    즉 전부 지울수록 프록시가 되살아난다. dict를 **비지 않게** 두면서 http/https
    #    항목만 없애야 "설정 없음 = 직결"이 된다. `no_proxy` 하나가 그 자리를 채운다.
    #    `requests`도 같은 `urllib.request.getproxies()`를 타므로 두 라이브러리에 동시에 듣는다.
    os.environ["no_proxy"] = "*"
    # 값이 아니라 **이름만** 남긴다 - 프록시 URL에 자격증명이 실려 있을 수 있다.
    logger.info("[proxy] 수집 스크립트는 직결로 돕니다(no_proxy=*). 제거한 변수: %s",
                ", ".join(removed) if removed else "(없음)")


_apply_proxy_policy()


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
        # One retroactive run at a time (see start_retroactive_run).
        self._retroactive_thread = None
        self._retroactive_last = None
        # 🔴 THE DOOR FOR COLLECTORS, and the reason it had to be created rather than
        # found: until now the door WAS the inline call. A cron collector ran on the tick
        # thread, so the tick could not come round and fire it again - and that same
        # property is what stopped the heartbeat for the whole run. Taking the work off
        # the tick removes the accident that was doing this job, so the job becomes
        # explicit. `retroactive_busy()` is the same idea one level up.
        self._collectors_running = set()

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

    def start_collector(self, collector) -> bool:
        """Run one collector OFF the tick thread, at most one of it at a time.

        [Why a thread] `collector.execute()` runs a user script. On the tick thread that
        stops `heartbeat.beat("scheduler")` for the whole run, and /health then reports
        this daemon as making no progress - the monitoring surface goes down as a direct
        consequence of a collector doing its job. Measured 2026-09-04: the tick's own
        `check_and_run_schedules` called `execute_collector` inline, so every cron run
        was that outage. `start_retroactive_run` had already been given this prescription
        and its docstring names this call site as the one that had not.

        [Why the claim is taken HERE and not in the thread] The tick comes round every
        `check_interval` seconds. `execute_collector` advances `next_run` at its start, so
        with the work on a thread there is a window - however small - in which the tick
        sees the old `next_run` and fires the same collector again. A cron collector
        running twice is not something an operator can undo, so the claim is taken
        synchronously, before the thread exists.

        Returns True when the run was started, False when this collector is already
        running - REFUSED and said so, never queued silently.
        """
        key = self._collector_key(collector)
        with self._lock:
            if key in self._collectors_running:
                logger.warning(
                    "[Collector] '%s' is already running; this trigger is refused rather "
                    "than started a second time", key)
                return False
            self._collectors_running.add(key)

        def _worker():
            try:
                self.execute_collector(collector)
            finally:
                # Released here and nowhere else: a claim left behind by a raising
                # collector would refuse that collector forever, which looks exactly
                # like a schedule that stopped working.
                with self._lock:
                    self._collectors_running.discard(key)

        threading.Thread(target=_worker, name=f"collector-{key}", daemon=True).start()
        return True

    def run_collector_on_demand(self, table_name: str, script_name: str):
        """
        On-Demand 강제 구동 지시를 받아 비동기로 대상 수집기를 실행합니다.
        [계약] run-now(수동 실행)는 active(disabled) 상태와 무관하게 항상 실행합니다 — 수동 실행은 명시적 의도.
        """
        for collector in self.collectors:
            col_script_name = os.path.basename(getattr(collector, "script_path", "")) if getattr(collector, "script_path", None) else collector.__class__.__name__
            if collector.table_name == table_name and col_script_name == script_name:
                logger.info(f"[Trigger] On-Demand trigger received. Executing collector '{script_name}' for table '{table_name}' immediately...")
                # Through the same door as the cron path. This call already ran on its own
                # thread, so it was never the beat's problem - but it had NO door, which
                # means an on-demand run and a cron run of the same collector could
                # overlap. One door, both entrances.
                return self.start_collector(collector)
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
                        # 🔴 OFF THE TICK. This line ran the collector inline, and the beat
                        # comes from this same thread (`run()` -> heartbeat.beat), so a
                        # long collector took /health down with it.
                        self.start_collector(collector)

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

    def retroactive_busy(self) -> bool:
        """Is the gate closed. 🔴 THIS ANSWER IS UNCHANGED AND MUST STAY UNCHANGED.

        A long run and a wedged one both close it, and both SHOULD: the reason the gate
        exists is that two concurrent replays of one rule write the same cells from two
        sessions. Opening it after a timeout would trade a stuck run for the one ordering
        nobody could reason about afterwards. What was missing was never permission - it
        was that nothing SAID which of the two states the closed gate was in.
        """
        t = self._retroactive_thread
        return bool(t and t.is_alive())

    def retroactive_moving_state(self):
        """WHICH of the two the closed gate is in, as a value, or None if unknowable.

        Read from `retroactive_runs`, never from the thread: the thread only answers
        "alive", which is the very question that cannot tell a long run from a stopped
        one. Never fatal, and never called unless the gate has already refused something -
        a diagnosis must not be able to stop the scheduler, nor cost a query per tick
        while nothing is in flight.
        """
        try:
            import retroactive
            from database.database import SessionLocal

            session = SessionLocal()
            try:
                return retroactive.in_flight(session)
            finally:
                session.close()
        except Exception as e:                                   # noqa: BLE001
            logger.debug("[Retroactive] could not read the in-flight state: %s", e)
            return None

    def start_retroactive_run(self, payload: dict) -> bool:
        """Run one queued retroactive (backfill) operation OFF the tick thread.

        [Why a thread, and why this is not optional]
        A retroactive run walks a whole table. ``run()`` emits
        ``heartbeat.beat("scheduler")`` once per tick and
        ``heartbeat.DEFAULT_STALE_AFTER_SEC`` is 60 s, so executing the run inline -
        the way ``run_collector_on_demand`` executes a collector - would stop the
        beat for the entire run and make ``/health`` report this daemon WEDGED.
        That is not a cosmetic complaint: an operator pressing a button they were
        offered would take the monitoring surface down as a direct consequence.
        The cron schedules would stall for the same duration.

        [Why one at a time] Two concurrent replays of the same rule would write the
        same cells from two sessions, and a replay racing a withdrawal on the same
        table is the one ordering nobody could reason about afterwards. A second
        request while one is running is REFUSED and said so, not queued silently -
        the outbox row is left unprocessed so it is picked up on a later tick.

        Returns True when the run was started (and the event may be marked
        processed), False when it was refused because one is already in flight.
        """
        import retroactive

        if self.retroactive_busy():
            # The gate is closed either way; this log line is where the two states become
            # distinguishable. Without it the operator's only evidence was an outbox row
            # whose age grew with no reason attached to it anywhere.
            in_flight = self.retroactive_moving_state()
            logger.warning(
                "[Retroactive] a run is already in flight (%s, %s); leaving run_id=%s "
                "queued for a later tick",
                self._retroactive_last,
                "no run row" if not in_flight else
                "run_id=%s op=%s %s for %ss" % (
                    in_flight["run_id"], in_flight["op"], in_flight["moving"],
                    in_flight["no_progress_seconds"]),
                (payload or {}).get("run_id"))
            return False

        def _worker():
            try:
                self._retroactive_last = retroactive.execute(payload, log=logger.info)
            except Exception as e:
                # `execute` already swallows; this is the last resort so a thread
                # death cannot be silent.
                logger.error("[Retroactive] runner thread raised: %s", e, exc_info=True)

        self._retroactive_thread = threading.Thread(
            target=_worker, name="retroactive-run", daemon=True)
        self._retroactive_thread.start()
        return True

    def handle_retroactive_trigger(self, db):
        """The RETROACTIVE_RUN half of one tick. Extracted so it can be DRIVEN.

        🔴 IT WAS INLINE IN A 200-LINE `while True`, WHICH IS WHY IT WAS NEVER
        TESTED - and a test that re-implemented the block instead would have
        stayed green while the block itself was reverted. Production stopped on
        this path on 2026-09-04, and a defect that stops production is exactly
        the one a test has to be able to reach.

        Nothing else changed: the same objects, the same order, the same
        guarantee.
        """
        from database.models import DatabaseOutbox

        # 1-3. RETROACTIVE_RUN 감시 (소급 적용 실행 — server/retroactive.py)
        #   The apply half of GET /admin/retroactive/{op}/count. Same outbox
        #   mechanism as SCHEDULER_RUN_NOW; unlike it, the work is handed to a
        #   thread so this tick keeps beating (see start_retroactive_run).
        if not self.retroactive_busy():
            retro_trigger = db.query(DatabaseOutbox).filter(
                DatabaseOutbox.event_type == event_constants.EVENT_RETROACTIVE_RUN,
                DatabaseOutbox.processed_chain == False
            ).order_by(DatabaseOutbox.id.asc()).first()

            if retro_trigger:
                # Bound before the `try` so the failure path can name the run
                # even when it is the parse itself that raised - which is the
                # one way this row is left unmarked forever.
                retro_payload = None
                try:
                    retro_payload = (
                        json.loads(retro_trigger.payload)
                        if isinstance(retro_trigger.payload, str)
                        else retro_trigger.payload)
                    # Marked BEFORE the run starts, not after: the run is on
                    # another thread and can outlive many ticks, so waiting
                    # for it would re-read the same row every tick and start
                    # the job again. At-most-once is the right guarantee here
                    # - a retroactive run that silently repeats is worse than
                    # one an operator has to press twice.
                    if self.start_retroactive_run(retro_payload):
                        retro_trigger.processed_chain = True
                        db.commit()
                except Exception as retro_err:
                    # 🔴 A REQUEST THAT THREW IS FINISHED, NOT PENDING, AND
                    # LEAVING IT UNMARKED STOPPED PRODUCTION. Measured
                    # 2026-09-04: one row whose payload could not be handled
                    # was re-picked at every tick - `order_by(id.asc())` puts
                    # it first forever - so every LATER retroactive request
                    # behind it was never reached, a restart did not clear it
                    # (the fault is in the row, not this process), and nothing
                    # raised anywhere. The board's C-4 named this shape.
                    #
                    # 🔴 MARKING IT MATCHES THE GUARANTEE THIS PATH ALREADY
                    # CHOSE. Ten lines up: at-most-once, because "a run that
                    # silently repeats is worse than one an operator has to
                    # press twice". Retrying forever a request that cannot
                    # even be parsed is the opposite of that decision.
                    #
                    # ⛔ NOT skipped to the next row either - that leaves the
                    # row waiting for ever and the queue counting one that
                    # nobody will ever take. ⛔ And retry_count is NOT raised:
                    # a payload that will not parse does not parse next time.
                    #
                    # ⚠️ The REASON must survive: the row, the run and the op
                    # are named. The payload body is not logged - it is
                    # operational data.
                    logger.error(
                        "Failed to handle RETROACTIVE_RUN trigger "
                        "(outbox#%s, run_id=%s, op=%s); marking it FAILED so "
                        "the requests behind it can run: %s",
                        getattr(retro_trigger, "id", "?"),
                        (retro_payload or {}).get("run_id", "?"),
                        (retro_payload or {}).get("op", "?"),
                        retro_err)
                    try:
                        db.rollback()
                        retro_trigger.status = "FAILED"
                        retro_trigger.processed_chain = True
                        db.commit()
                    except Exception as mark_err:
                        # If even this fails the row stays and the block
                        # remains - but it says so instead of being silent.
                        logger.error(
                            "Could not mark the failed RETROACTIVE_RUN "
                            "(outbox#%s) as finished; the queue is still "
                            "blocked behind it: %s",
                            getattr(retro_trigger, "id", "?"), mark_err)


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
                    # 🔴 ORDERED, like its sibling below. Without `order_by` the row this
                    # picks is whatever the plan happens to return, so which trigger runs
                    # first is decided by the query plan rather than by arrival - and the
                    # answer changes the day the plan does. Oldest first is also the only
                    # order that cannot starve a trigger: an unordered pick can keep
                    # choosing the newest while an older one waits forever.
                    latest_trigger = db.query(DatabaseOutbox).filter(
                        DatabaseOutbox.event_type
                        == event_constants.EVENT_SCHEDULER_RUN_NOW,
                        DatabaseOutbox.processed_chain == False
                    ).order_by(DatabaseOutbox.id.asc()).first()
                    
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

                    self.handle_retroactive_trigger(db)
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
