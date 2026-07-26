import os
import time
import queue
import shutil
import logging
import threading
from datetime import datetime
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
# 체인 워커(chain_ingestion_worker.py)와 공유하는 공용 상수로 승격됨 — 정의·근거는 event_constants 참조.
# 실제 총 로그 건수는 total_log_count로 별도 전달되어 웹서버 audit_cache의 total_count 표기에 쓰인다.
from event_constants import MAX_NOTIFY_CREATED_LOGS

# [Std Ingestion] 워크스페이스 자동 생성에서 제외하는 시스템 내부 테이블.
# (파일 드롭 인제션 대상이 아닌 메타데이터성 테이블 — 필요 시 여기에 추가)
AUTO_PROVISION_EXCLUDED_TABLES = {"wafer_map_metadata"}

# 표준 워크스페이스 구조 (테이블 온보딩 시 자동 보충되는 하위 폴더)
WORKSPACE_SUBDIRS = ("raws", "archives", "err", "auto_update", "scripts", "config")

# [Startup Sweep] 이벤트 유실 안전망 — 주기 잔류 파일 재스캔 간격(초).
# watchdog 이벤트가 유실되어도 최대 이 간격 안에 raws/ 직속 잔류 파일이 처리된다.
# 업서트가 멱등이라 중복 처리는 무해하고, 동일 (mtime, size) 시그니처 재시도 차단으로
# 처리 실패 잔류 파일의 무한 재시도 루프를 막는다.
PERIODIC_SWEEP_INTERVAL_SECONDS = 300


def load_global_table_config() -> dict:
    """전역 table_config.json 로드 (실패 시 빈 dict — 워처는 계속 동작해야 한다)."""
    import json
    try:
        global_config_path = os.path.abspath(os.path.join(script_dir, "..", "config", "table_config.json"))
        if os.path.exists(global_config_path):
            with open(global_config_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"Could not load global table_config: {e}")
    return {}


# [Deprecation 2026-07-25] 워크스페이스 config.json 폐지 — 경고는 프로세스당 경로별 1회만.
_legacy_config_warned_paths = set()


def warn_legacy_workspace_config(config_path: str):
    """워크스페이스 config.json(레거시) 사용 감지 시 1회 WARNING을 남긴다.

    파일은 삭제하지 않고 계속 읽되(하위호환), 소비 필드(table_name/std_parse)는
    글로벌 table_config.json의 `workspace_name`/`std_parse`로 이관을 안내한다.
    충돌 시 우선순위: **table_config.json 승리**."""
    abs_path = os.path.abspath(config_path)
    if abs_path in _legacy_config_warned_paths:
        return
    _legacy_config_warned_paths.add(abs_path)
    logger.warning(
        f"[DEPRECATED] Workspace config file is deprecated and will be ignored in a future release: {abs_path} — "
        f"migrate 'table_name' -> table_config.json entry field 'workspace_name' (folder alias), "
        f"'std_parse' -> table_config.json entry field 'std_parse' (boolean, default true). "
        f"On conflict, table_config.json wins."
    )


# [D3/D5] 별칭 충돌 ERROR·중복 경고는 키별 1회만 (청크당 재발화로 인한 로그 홍수 방지)
_alias_conflict_logged = set()
# [D6] 신규 필드 타입 오류 경고도 원천별 1회만
_invalid_field_warned = set()


def _log_alias_conflict_once(folder_name: str, message: str):
    key = (folder_name, message)
    if key in _alias_conflict_logged:
        return
    _alias_conflict_logged.add(key)
    logger.error(message)


def warn_invalid_std_parse_once(source_key: str, value):
    """[D6] `std_parse`에 bool 외 값(예: 문자열 "false")이 오면 무시하고 1회 경고한다."""
    key = ("std_parse", source_key)
    if key in _invalid_field_warned:
        return
    _invalid_field_warned.add(key)
    logger.warning(
        f"Ignoring non-boolean 'std_parse' value {value!r} in {source_key} — "
        f"expected JSON boolean true/false (string \"false\" is NOT an opt-out)."
    )


# ── [Heavy Lane P1] 대형 파일 인제션 격리 설정 ─────────────────────────────
# 임계값 위치 결정 근거: table_config.json에 `_system` 메타 키를 넣는 안은
# 모든 소비처(init_dynamic_models·_provision_workspaces·/tables·마이그레이션 등)가
# 키를 테이블로 순회하므로 블라스트 반경이 크다. server/config는 서브시스템별
# 개별 파일 관례(chain_rules/enrichment_rules/maps/...)이므로 그 관례를 따라
# 전용 파일 ingestion_settings.json을 신설한다. 파일 부재/손상 시 기본값으로 동작.
DEFAULT_HEAVY_FILE_MB = 10
INGESTION_SETTINGS_PATH = os.path.abspath(
    os.path.join(script_dir, "..", "config", "ingestion_settings.json")
)


def load_ingestion_settings() -> dict:
    """인제션 시스템 설정(ingestion_settings.json) 로드 — 실패 시 빈 dict(기본값 동작)."""
    import json
    try:
        if os.path.exists(INGESTION_SETTINGS_PATH):
            with open(INGESTION_SETTINGS_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                return loaded
    except Exception as e:
        logger.warning(f"Could not load ingestion settings ({INGESTION_SETTINGS_PATH}): {e}")
    return {}


def warn_invalid_heavy_threshold_once(value):
    """`heavy_file_mb`에 양수(int/float) 외 값이 오면 무시하고 1회만 경고한다."""
    key = ("heavy_file_mb", repr(value))
    if key in _invalid_field_warned:
        return
    _invalid_field_warned.add(key)
    logger.warning(
        f"Ignoring invalid 'heavy_file_mb' value {value!r} in ingestion_settings.json — "
        f"expected a positive number (MB). Falling back to default {DEFAULT_HEAVY_FILE_MB}MB."
    )


def get_heavy_threshold_bytes() -> int:
    """heavy 레인 라우팅 크기 임계(bytes).

    파일 이벤트(라우팅 결정)당 1회 디스크에서 읽는다 — 핫리로드는 '다음 파일부터'
    자연 반영되고, 한 파일의 라우팅 결정 안에서 값이 갈리는 일이 없다(파일 경계 스냅샷 규율).
    """
    val = load_ingestion_settings().get("heavy_file_mb", DEFAULT_HEAVY_FILE_MB)
    if isinstance(val, bool) or not isinstance(val, (int, float)) or val <= 0:
        warn_invalid_heavy_threshold_once(val)
        val = DEFAULT_HEAVY_FILE_MB
    return int(val * 1024 * 1024)


# ── [Heavy Lane P1] 워크스페이스 단위 직렬화 락 레지스트리 ─────────────────
# 경계 계약(순서 보존): 같은 워크스페이스(=테이블)의 파일이 heavy/normal 두 레인에서
# 동시에 처리되어 업서트 순서가 뒤집히는 일이 없어야 한다. 핸들러 인스턴스가 경로별로
# 여럿 생길 수 있으므로(워처 등록 핸들러 + 재시도 임시 핸들러) 락은 모듈 레벨에서
# 워크스페이스 절대경로 키로 공유한다. (프로세스 간 배타는 범위 밖 — 기존과 동일)
_workspace_serial_locks: dict = {}
_workspace_serial_locks_guard = threading.Lock()


def get_workspace_serial_lock(workspace_path: str) -> threading.Lock:
    key = os.path.normcase(os.path.abspath(workspace_path))
    with _workspace_serial_locks_guard:
        lock = _workspace_serial_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _workspace_serial_locks[key] = lock
        return lock


class HeavyIngestionLane:
    """[Heavy Lane P1] 대형 파일 전용 처리 레인 — 단일 워커 스레드 + FIFO 큐.

    목적은 **교차 워크스페이스 격리**: A 테이블의 수 분짜리 대형 파일이 watchdog
    observer 디스패치 스레드/스윕 스레드를 점유해 B 테이블의 소형 파일을 분 단위로
    막던 HOL(head-of-line) 차단을 제거한다. 큐에 넘긴 뒤 라우팅 스레드는 즉시
    반환되고, 실제 처리는 이 레인의 데몬 스레드에서 수행된다.

    같은 워크스페이스 내 순서 보존은 핸들러의 backlog 라우팅(후속 파일도 큐 후미로)
    + 워크스페이스 직렬화 락(get_workspace_serial_lock)이 담당한다.
    """

    WORKER_THREAD_NAME = "watcher-heavy-lane"

    def __init__(self):
        self._queue = queue.Queue()
        self._stop_event = threading.Event()
        self._thread = None
        self._thread_guard = threading.Lock()

    def submit(self, job) -> None:
        """job: 인자 없는 callable. 워커 스레드는 지연 기동(첫 submit 시)."""
        self._ensure_running()
        self._queue.put(job)

    def _ensure_running(self):
        with self._thread_guard:
            if self._thread is not None and self._thread.is_alive():
                return
            if self._stop_event.is_set():
                raise RuntimeError("HeavyIngestionLane is stopped")
            self._thread = threading.Thread(
                target=self._worker_loop, name=self.WORKER_THREAD_NAME, daemon=True,
            )
            self._thread.start()

    def _worker_loop(self):
        while not self._stop_event.is_set():
            try:
                job = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                job()
            except Exception as e:
                # 방어선: _run_lane_job이 자체 예외 처리를 하므로 여기는 최후 로깅만
                logger.error(f"[HeavyLane] Unexpected error in heavy lane job: {e}")
            finally:
                self._queue.task_done()

    def stop(self):
        self._stop_event.set()


def find_workspace_alias(folder_name: str, table_config: dict) -> str | None:
    """`workspace_name` 별칭이 폴더명과 일치하는 table_config 항목의 테이블명을 찾는다.

    명시 별칭 매칭 전용 — 폴더명=테이블명 규약은 다루지 않는다. 명시 별칭은
    레거시 워크스페이스 config.json의 `table_name`보다 항상 우선한다(글로벌 승리).

    [D3] 충돌 시 별칭은 무효(ERROR 로그 1회):
    - 별칭이 **다른 실존 테이블명**과 동명이면 섀도잉 차단을 위해 해당 별칭을 무시한다
      (자기 자신의 테이블명을 별칭으로 쓴 자기-별칭은 허용).
    - 동일 별칭을 복수 테이블이 선언하면 전부 무시한다(어느 쪽이 정당한지 판정 불가)."""
    if not folder_name or not isinstance(table_config, dict):
        return None
    matches = [
        t_name for t_name, t_cfg in table_config.items()
        if isinstance(t_cfg, dict) and t_cfg.get("workspace_name") == folder_name
    ]
    if not matches:
        return None
    # [D3-①] 별칭이 다른 실존 테이블명과 충돌 → 그 별칭들은 무효 (폴더는 동명 테이블 소유로 유지)
    if folder_name in table_config:
        others = [t for t in matches if t != folder_name]
        if others:
            _log_alias_conflict_once(
                folder_name,
                f"workspace_name alias '{folder_name}' declared by table(s) {others} collides with an "
                f"existing table name in table_config.json — alias ignored; folder resolves to table '{folder_name}'.",
            )
        matches = [t for t in matches if t == folder_name]
        if not matches:
            return None
    # [D3-②] 동일 별칭 복수 선언 → 전부 무효
    if len(matches) > 1:
        _log_alias_conflict_once(
            folder_name,
            f"Duplicate workspace_name alias '{folder_name}' declared by tables {matches} in "
            f"table_config.json — alias ignored for all of them (folder falls back to name convention).",
        )
        return None
    return matches[0]


def resolve_workspace_root(base_dir: str, table_name: str, table_config: dict) -> str:
    """테이블명 → 워크스페이스 루트 **절대경로** 역조회 (재시도/자동생성 공용).

    `workspace_name` 별칭이 유효하면 그 폴더, 아니면 테이블명 폴더.
    - [D3 대칭] 별칭이 충돌로 무효(find_workspace_alias가 해당 테이블로 역해석되지 않음)면 무시.
    - [D2] 결과 기반 봉쇄: normpath(join()) 결과가 base_dir의 **직속 자식**이 아니면 무시
      (Windows 드라이브 상대경로 `C:evil`이 join에서 base를 폐기하는 탈출 경로 차단)."""
    base_abs = os.path.abspath(base_dir)
    folder = None
    t_cfg = table_config.get(table_name) if isinstance(table_config, dict) else None
    if isinstance(t_cfg, dict):
        ws = t_cfg.get("workspace_name")
        if isinstance(ws, str) and ws:
            folder = ws
    # 정방향 해석과의 대칭성: 이 별칭으로 폴더를 만들었을 때 실제로 이 테이블로 인제션되는가
    if folder is not None and find_workspace_alias(folder, table_config) != table_name:
        folder = None
    if folder is not None:
        candidate = os.path.abspath(os.path.normpath(os.path.join(base_abs, folder)))
        # 직속 자식 + 폴더명 원형 보존(드라이브 접두 등이 join에서 소거·변형되지 않았는지)까지 요구
        if (os.path.normcase(os.path.dirname(candidate)) == os.path.normcase(base_abs)
                and os.path.basename(candidate) == folder):
            return candidate
        key = ("unsafe_workspace_name", table_name, folder)
        if key not in _invalid_field_warned:
            _invalid_field_warned.add(key)
            logger.warning(
                f"Ignoring unsafe workspace_name '{folder}' for table '{table_name}' "
                f"(must resolve to a direct child of the ingestion workspace)."
            )
    return os.path.join(base_abs, table_name)


def resolve_workspace_table(folder_name: str, table_config: dict) -> str | None:
    """폴더명 → 테이블명 해석 (글로벌 table_config.json 단일 원천).

    1) `workspace_name` 별칭이 폴더명과 일치하는 테이블 항목
    2) 폴더명=테이블명 규약 (기본값: 항목에 workspace_name이 없으면 폴더명이 곧 테이블명)
    해석 불가 시 None."""
    aliased = find_workspace_alias(folder_name, table_config)
    if aliased is not None:
        return aliased
    if isinstance(table_config, dict) and folder_name in table_config:
        return folder_name
    return None


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
    def __init__(self, workspace_path: str, config_path: str | None, archives_path: str, default_table_name: str | None = None, on_refresh_callback=None, on_file_processed_callback=None, on_progress_callback=None, on_ingestion_state_callback=None, heavy_lane=None):
        self.workspace_path = workspace_path
        self.config_path = config_path
        self.archives_path = archives_path
        self.default_table_name = default_table_name # Agent D v13: 폴더 머신 명칭 기반 Fallback
        self.scripts_path = os.path.join(workspace_path, "scripts")
        self.supported_extensions = ('.log', '.txt', '.csv')
        self.processing_files = set()
        # [Startup Sweep] 스윕 스레드와 watchdog 이벤트 스레드가 같은 파일에 동시 진입하는
        # 레이스 방지 — processing_files의 check-then-add를 원자화하는 락.
        self._processing_lock = threading.Lock()
        self.on_refresh_callback = on_refresh_callback
        self.on_file_processed_callback = on_file_processed_callback
        self.on_progress_callback = on_progress_callback
        # [Heavy Lane P1] 진행 상태(QUEUED/PROCESSING/FINISHED) 통지 콜백 (선택)
        self.on_ingestion_state_callback = on_ingestion_state_callback
        # [Heavy Lane P1] 대형 파일 전용 레인 (None이면 기존 인라인 경로 그대로 — 하위호환)
        self.heavy_lane = heavy_lane
        # 같은 워크스페이스 파일 처리 직렬화 락 (모듈 레벨 공유 — 순서 보존 경계 계약)
        self._serial_lock = get_workspace_serial_lock(workspace_path)
        # heavy 레인에 제출됐으나 아직 완료되지 않은 이 워크스페이스 파일 수.
        # > 0이면 후속 파일(크기 무관)도 큐 후미로 보내 워크스페이스 내 FIFO를 보존한다.
        self._lane_state_lock = threading.Lock()
        self._heavy_backlog = 0
        # [Deprecation] 레거시 워크스페이스 config.json 파싱 결과 캐시 (파일은 정적 자산 취급)
        self._legacy_config_cache = None

    def _load_legacy_config(self) -> dict:
        """[하위호환] 레거시 워크스페이스 config.json을 읽는다 (삭제하지 않음 — 사용자 파일).

        소비 필드(table_name/std_parse)가 있으면 deprecation 경고를 1회 남긴다.
        글로벌 table_config.json이 항상 우선하며, 이 파일은 폴백 원천일 뿐이다."""
        if self._legacy_config_cache is not None:
            return self._legacy_config_cache
        data = {}
        if self.config_path and os.path.exists(self.config_path):
            import json
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    data = loaded
            except Exception:
                data = {}
            if ("table_name" in data) or ("std_parse" in data):
                warn_legacy_workspace_config(self.config_path)
        self._legacy_config_cache = data
        return data

    def _resolve_table_name(self, global_cfg: dict):
        """워크스페이스 → 테이블명 해석. 우선순위(충돌 시 상위가 승리):
        1) 글로벌 table_config.json의 `workspace_name` 별칭 (전달된 global_cfg 스냅샷 기준)
        2) [deprecated] 레거시 워크스페이스 config.json의 `table_name`
        3) 생성자 default_table_name → 폴더명=테이블명 규약"""
        folder_name = os.path.basename(os.path.abspath(self.workspace_path))
        # 별칭 명시 매칭만 글로벌 승리 대상 — 폴더명=테이블명 규약 해석은 기존 폴백 순서 유지
        aliased = find_workspace_alias(folder_name, global_cfg)
        if aliased is not None:
            return aliased
        legacy_name = self._load_legacy_config().get("table_name")
        if legacy_name:
            return legacy_name
        return self.default_table_name or folder_name

    def _snapshot_table_context(self):
        """[D1] 파일 처리 단위 `(t_name, table_info)` 스냅샷 — 글로벌 config를 **1회만** 읽어
        헤더 검증→정규화→업서트 전 구간이 같은 config를 보게 한다. 핫리로드 의미론은
        "파일 경계에서 반영"(처리 중인 파일은 시작 시점 config로 완결)."""
        global_cfg = load_global_table_config()
        t_name = self._resolve_table_name(global_cfg)
        table_info = global_cfg.get(t_name) if t_name else None
        if not isinstance(table_info, dict):
            table_info = {}
        return t_name, table_info

    def _std_parse_enabled_for(self, t_name, table_info) -> bool:
        """std parser 폴백 옵트아웃 게이트 (스냅샷 기반). 우선순위(충돌 시 상위가 승리):
        1) 글로벌 table_config.json 테이블 항목의 `std_parse` (파일 경계 핫리로드 — F4 해소)
        2) [deprecated] 레거시 워크스페이스 config.json의 `std_parse`
        3) 기본 활성(True) — config가 없는 워크스페이스도 활성.
        [D6] bool 외 값은 무시(1회 경고) 후 하위 원천으로 폴백."""
        if isinstance(table_info, dict) and "std_parse" in table_info:
            val = table_info["std_parse"]
            if isinstance(val, bool):
                return val
            warn_invalid_std_parse_once(f"table_config.json entry '{t_name}'", val)
        legacy = self._load_legacy_config()
        if "std_parse" in legacy:
            lval = legacy["std_parse"]
            if isinstance(lval, bool):
                return lval
            warn_invalid_std_parse_once(f"workspace config '{self.config_path}'", lval)
        return True

    @property
    def table_name(self):
        """현재 시점 config 기준 테이블명 (표시/이벤트용). 파일 처리 경로는
        `_snapshot_table_context`가 잡은 파일 단위 스냅샷을 사용한다(D1)."""
        return self._resolve_table_name(load_global_table_config())

    @property
    def std_parse_enabled(self):
        """현재 시점 config 기준 옵트아웃 게이트 (파일 처리 경로는 스냅샷 사용 — D1)."""
        t_name, table_info = self._snapshot_table_context()
        return self._std_parse_enabled_for(t_name, table_info)

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
        # [Startup Sweep] 멤버십 검사→add 사이 갭에서 스윕 스레드와 watchdog 스레드가
        # 동시에 통과하던 비원자 check-then-add를 락으로 원자화 (이중 처리 가드).
        with self._processing_lock:
            if abs_path in self.processing_files:
                return
            if not os.path.exists(abs_path):
                return
            self.processing_files.add(abs_path)

        logger.info(f"New file detected: {abs_path}")

        # [Fix] 파일명에서 업로더 정보 추출
        uploader = self._extract_user_from_filename(os.path.basename(abs_path))

        logger.info(f"[{self.table_name}] 📥 New file detected: {os.path.basename(abs_path)}")

        routed_heavy = False
        try:
            routed_heavy = self._route_and_process(abs_path, uploader)
        finally:
            # heavy 큐로 넘긴 파일의 processing_files 정리는 heavy 워커(_run_lane_job)가
            # 처리 완료 후 수행한다 — 큐 대기 중 스윕/이벤트 이중 진입을 막기 위해 유지.
            if not routed_heavy:
                with self._processing_lock:
                    self.processing_files.discard(abs_path)

    # ── [Heavy Lane P1] 레인 라우팅 ──────────────────────────────────────

    def _classify_lane(self, abs_path: str):
        """파일 크기 기준 레인 분류. 반환: ("heavy"|"normal", size_bytes).

        크기는 이벤트 시점 1회 stat — 복사가 진행 중인 파일은 최종보다 작게 읽혀
        normal로 오분류될 수 있으나, 그 경우 기존(레인 도입 전) 인라인 경로와 동일한
        동작으로 열화될 뿐 정합성 문제는 없다. 임계값은 라우팅 결정당 1회 로드(핫리로드는
        다음 파일부터)."""
        try:
            size_bytes = os.stat(abs_path).st_size
        except OSError:
            return "normal", 0
        lane = "heavy" if size_bytes >= get_heavy_threshold_bytes() else "normal"
        return lane, size_bytes

    def _heavy_backlog_nonzero(self) -> bool:
        with self._lane_state_lock:
            return self._heavy_backlog > 0

    def _route_and_process(self, abs_path: str, uploader: str) -> bool:
        """레인 라우팅 + 처리 실행.

        반환 True  → heavy 큐에 제출됨 (processing_files 정리 책임은 heavy 워커).
        반환 False → 인라인으로 처리 완료됨 (호출자가 정리).

        순서 보존 불변식: 같은 워크스페이스의 파일은 (1) heavy backlog가 있으면
        후속 파일도 큐 후미로 보내 FIFO를 유지하고, (2) 인라인 경로도 워크스페이스
        직렬화 락을 잡아 두 레인이 같은 테이블을 동시에 업서트하지 않게 한다.
        인라인 경로가 락 획득에 실패하면(다른 스레드/레인이 처리 중) 블로킹 대기 대신
        큐 후미로 보낸다 — observer 디스패치 스레드의 HOL 차단 방지."""
        if self.heavy_lane is None:
            # 레인 미배선(재시도 임시 핸들러·레거시 직접 사용) — 기존 경로 그대로
            self.process_with_retry(abs_path, uploader=uploader)
            return False

        lane, size_bytes = self._classify_lane(abs_path)
        if lane == "heavy" or self._heavy_backlog_nonzero():
            if self._submit_to_heavy_lane(abs_path, uploader, lane, size_bytes):
                return True
            # 제출 실패(레인 정지 등) → 인라인 폴백 (아래 직렬화 락 경로)

        acquired = self._serial_lock.acquire(blocking=False)
        if not acquired:
            # 같은 워크스페이스에서 처리 진행 중 — 순서 보존을 위해 큐 후미로
            if self._submit_to_heavy_lane(abs_path, uploader, lane, size_bytes):
                return True
            self._serial_lock.acquire()  # 최후 폴백: 블로킹 직렬화 (정합 우선)
        try:
            self.process_with_retry(abs_path, uploader=uploader)
        finally:
            self._serial_lock.release()
        return False

    def _submit_to_heavy_lane(self, abs_path: str, uploader: str, lane: str, size_bytes: int) -> bool:
        """heavy 레인 큐에 제출. 성공 시 True (processing_files 정리 책임 이관).

        [QA F4] lane은 **크기 분류 실값**을 그대로 통지한다 — 순서 보존을 위해 큐 후미로
        재라우팅된 소형 파일(lane="normal")이 admin에 HEAVY 배지로 오표기되거나
        heavy 카운트를 부풀리지 않게 한다 (처리 스레드는 동일하게 heavy 워커)."""
        t_display = self.table_name  # 표시/통지용 (실제 처리는 process_with_retry의 스냅샷 사용)
        filename = os.path.basename(abs_path)
        with self._lane_state_lock:
            self._heavy_backlog += 1
        # [라이브 드릴 결함1] QUEUED 통지는 **submit 이전**에 발신한다 — 큐가 비어 있으면
        # 워커가 제출 즉시 잡을 집어 PROCESSING 통지를 먼저 쏘고, 뒤늦은 QUEUED가
        # 레지스트리를 역행 덮어쓰기(실처리 중인데 '대기' 오표시)하던 경합 제거.
        reason = "size" if lane == "heavy" else "workspace-order"
        logger.info(f"[{t_display}] 🐘 Routed to heavy lane queue ({reason}, {size_bytes:,}B): {filename}")
        self._notify_ingestion_state({
            "table_name": t_display,
            "filename": filename,
            "lane": lane,
            "status": "QUEUED",
            "size_bytes": size_bytes,
            "queued_at": datetime.now().isoformat(timespec="seconds"),
        })
        try:
            self.heavy_lane.submit(
                lambda: self._run_lane_job(abs_path, uploader, t_display, lane, size_bytes)
            )
        except Exception as e:
            with self._lane_state_lock:
                self._heavy_backlog -= 1
            # 선발신한 QUEUED 엔트리 정리 — QUEUED는 장기 TTL(F1)이라 방치 시 고아가 오래 남는다.
            self._notify_ingestion_state({
                "table_name": t_display, "filename": filename, "status": "FINISHED",
            })
            logger.error(f"[{t_display}] Heavy lane submit failed — falling back inline: {e}")
            return False
        return True

    def _run_lane_job(self, abs_path: str, uploader: str, t_display: str, lane: str, size_bytes: int):
        """heavy 워커 스레드에서 실행되는 처리 본체.

        아카이브/에러 이동·FileIngestionLog·완료/진행 콜백은 전부 process_with_retry
        내부에서 기존과 동일하게 수행된다 (레인과 무관한 경로 불변 계약)."""
        filename = os.path.basename(abs_path)
        try:
            with self._serial_lock:
                self._notify_ingestion_state({
                    "table_name": t_display,
                    "filename": filename,
                    "lane": lane,  # [QA F4] 분류 실값 (재라우팅 소형 파일은 "normal")
                    "status": "PROCESSING",
                    "size_bytes": size_bytes,
                    "started_at": datetime.now().isoformat(timespec="seconds"),
                })
                self.process_with_retry(abs_path, uploader=uploader)
        except Exception as e:
            # process_with_retry는 자체적으로 err 이동/로그를 수행 — 여기는 방어선
            logger.error(f"[{t_display}] Heavy lane job failed unexpectedly: {e}")
        finally:
            with self._lane_state_lock:
                self._heavy_backlog -= 1
            with self._processing_lock:
                self.processing_files.discard(abs_path)
            # 파일 소실 등으로 완료 콜백 없이 반환되는 경로까지 확실히 정리 (수신측 멱등)
            self._notify_ingestion_state({
                "table_name": t_display, "filename": filename, "status": "FINISHED",
            })

    def _notify_ingestion_state(self, state: dict):
        """진행 상태 통지 — 콜백 미배선/실패는 처리 흐름에 영향을 주지 않는다.
        페이로드는 소형 스칼라 필드만 담는다 (프로세스 간 통지 무절단 컬렉션 금지 교훈)."""
        cb = self.on_ingestion_state_callback
        if not cb:
            return
        try:
            cb(state)
        except Exception as e:
            logger.warning(f"Ingestion state callback failed: {e}")

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

        # [D1] 파일당 1회 스냅샷 — 해석·검증·업서트·로그가 전부 같은 config 스냅샷을 본다.
        # 파일 처리 도중 table_config가 바뀌어도 이 파일은 시작 시점 기준으로 완결된다.
        t_name, table_info = self._snapshot_table_context()

        for attempt in range(retries):
            try:
                # Pipeline Discovery(우선) → Std Parser 폴백 순으로 행을 해석
                rows, total_rows, skipped_no_key = self._resolve_rows(file_path, t_name=t_name, table_info=table_info)

                # 매칭 및 실행 성공 (빈 결과일 수도 있음)
                if (total_rows > 0) if total_rows is not None else bool(rows):
                    self._send_to_upsert(rows, uploader=uploader, filename=os.path.basename(file_path), total_rows=total_rows, t_name=t_name, table_info=table_info)

                # 3. Archive the file
                dest_path = self._archive_file(file_path)
                # [F1] 키 결측 스킵은 성공이되 사용자에게 반드시 보여야 하는 정보 —
                # 완료 콜백의 detail(4번째 인자, 기존 error_msg 슬롯)로 전달되어
                # file_ingestion_completed 메시지 문자열에 덧붙는다(페이로드 구조 불변).
                detail = f"키 결측으로 {skipped_no_key}행 스킵" if skipped_no_key else None
                logger.info(
                    f"[{t_name}] ✅ Successfully processed and archived: {os.path.basename(file_path)}"
                    + (f" ({detail})" if detail else "")
                )
                self._log_ingestion_success(file_path, dest_path, t_name=t_name)
                if self.on_file_processed_callback:
                    self.on_file_processed_callback(t_name, os.path.basename(file_path), "SUCCESS", detail)
                return
            except PermissionError:
                logger.warning(f"[{t_name}] 🔒 File locked, retrying in {delay}s: {os.path.basename(file_path)}")
                time.sleep(delay)
            except Exception as e:
                import traceback
                error_msg = traceback.format_exc()
                logger.error(f"[{t_name}] ❌ Error processing file {os.path.basename(file_path)}: {error_msg}")
                dest_path = self._move_to_err_folder(file_path)
                if not dest_path:
                    dest_path = file_path
                self._log_ingestion_failure(file_path, dest_path, error_msg, t_name=t_name)
                if self.on_file_processed_callback:
                    self.on_file_processed_callback(t_name, os.path.basename(file_path), "FAILED", str(e))
                return

        error_msg = f"Failed to process file after {retries} attempts: PermissionError (file locked)"
        logger.error(f"[{t_name}] ❌ {error_msg}: {os.path.basename(file_path)}")
        dest_path = self._move_to_err_folder(file_path)
        if not dest_path:
            dest_path = file_path
        self._log_ingestion_failure(file_path, dest_path, error_msg, t_name=t_name)
        if self.on_file_processed_callback:
            self.on_file_processed_callback(t_name, os.path.basename(file_path), "FAILED", error_msg)

    def _log_ingestion_failure(self, original_path: str, archived_path: str, error_msg: str, t_name: str = None):
        if t_name is None:
            t_name = self.table_name
        db = SessionLocal()
        try:
            from database.models import FileIngestionLog
            log_obj = FileIngestionLog(
                filename=os.path.basename(original_path),
                filepath=os.path.abspath(archived_path),
                table_name=t_name or "unknown",
                status="FAILED",
                error_message=error_msg,
                retry_count=0
            )
            db.add(log_obj)
            db.commit()
            logger.info(f"[{t_name}] 📝 Logged file ingestion failure to database.")
        except Exception as e:
            logger.error(f"Failed to write file ingestion error log to DB: {e}")
        finally:
            db.close()

    def _log_ingestion_success(self, original_path: str, archived_path: str, t_name: str = None):
        if t_name is None:
            t_name = self.table_name
        db = SessionLocal()
        try:
            from database.models import FileIngestionLog
            log_obj = FileIngestionLog(
                filename=os.path.basename(original_path),
                filepath=os.path.abspath(archived_path),
                table_name=t_name or "unknown",
                status="SUCCESS",
                error_message=None,
                retry_count=0
            )
            db.add(log_obj)
            db.commit()
            logger.info(f"[{t_name}] 📝 Logged file ingestion success to database.")
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
        # [D1] 재시도 경로도 파일당 1회 스냅샷 (핫리로드는 파일 경계에서 반영)
        t_name, table_info = self._snapshot_table_context()
        try:
            rows, total_rows, skipped_no_key = self._resolve_rows(filepath, t_name=t_name, table_info=table_info)
            if (total_rows > 0) if total_rows is not None else bool(rows):
                self._send_to_upsert(rows, uploader=uploader, filename=os.path.basename(filepath), total_rows=total_rows, t_name=t_name, table_info=table_info)

            # If successful, update the log entry to SUCCESS
            log_entry.status = "SUCCESS"
            log_entry.error_message = None
            db.commit()
            detail = f"키 결측으로 {skipped_no_key}행 스킵" if skipped_no_key else None  # [F1]
            if self.on_file_processed_callback:
                self.on_file_processed_callback(t_name, os.path.basename(filepath), "SUCCESS", detail)
            return True
        except Exception as e:
            import traceback
            error_msg = traceback.format_exc()
            logger.error(f"[{t_name}] ❌ Error retrying file {os.path.basename(filepath)}: {error_msg}")
            log_entry.status = "FAILED"
            log_entry.error_message = error_msg
            log_entry.retry_count += 1
            db.commit()
            if self.on_file_processed_callback:
                self.on_file_processed_callback(t_name, os.path.basename(filepath), "FAILED", str(e))
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

    def _resolve_rows(self, file_path: str, t_name: str = None, table_info: dict = None):
        """파일을 행 컬렉션으로 해석한다. 커스텀 파이프라인 디스커버리가 **우선**(하위호환)이며,
        어떤 스크립트도 매칭하지 않았을 때(None)만 표준 파서(std parser) 폴백을 시도한다.

        [D1] t_name/table_info는 파일 단위 config 스냅샷 — 미전달 시(레거시 직접 호출)
        이 시점에 1회 스냅샷을 잡는다.

        반환: (rows, total_rows, skipped_no_key)
          - 커스텀 파이프라인 경로: (list[dict], None, 0) — 기존과 동일.
          - std parser 경로: (row_iterator, int, int) — 스트리밍(전량 메모리 로드 없음).
            skipped_no_key는 [F1] 키 컬럼 공백/결측으로 스킵된 행 수(완료 메시지에 반영).
        스크립트 로드/매칭 오류 시에는 기존과 동일하게 _discover_and_execute_pipeline이
        ValueError를 raise하며, 이 경우 std 폴백은 **발동하지 않는다**(깨진 스크립트 은폐 방지).
        """
        if t_name is None and table_info is None:
            t_name, table_info = self._snapshot_table_context()

        rows = self._discover_and_execute_pipeline(file_path)
        if rows is not None:
            return rows, None, 0

        if self._std_parse_enabled_for(t_name, table_info):
            std_result = self._try_std_parse(file_path, t_name, table_info)
            if std_result is not None:
                return std_result

        raise ValueError(
            f"No custom pipeline parser matched the file '{os.path.basename(file_path)}' format, "
            f"and the standard parser fallback was not applicable."
        )

    def _try_std_parse(self, file_path: str, t_name: str, table_info: dict):
        """[Std Parser Fallback] 표준 파서 적용을 시도한다.

        t_name/table_info는 [D1] 파일 단위 config 스냅샷(호출자 전달) — 헤더 검증과
        이후 업서트 정규화가 반드시 같은 스냅샷을 보게 한다.

        반환: (row_iterator, total_rows, skipped_no_key) 또는 적용 불가 시 None
              (미지원 확장자 / 테이블 미확정 / table_config 미등록).
        헤더 검증 실패(비즈니스 키 누락 등)는 ValueError로 전파되어
        기존 실패 경로(err/ 이동 + FileIngestionLog FAILED)를 그대로 탄다.
        """
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)
        from std_parser import is_std_supported, parse_std_file

        if not is_std_supported(file_path):
            return None

        if not t_name:
            return None

        if not table_info:
            logger.warning(
                f"[{t_name}] Std parser skipped: table '{t_name}' is not defined in table_config.json"
            )
            return None

        logger.info(f"[{t_name}] 🧰 No custom pipeline matched — engaging Std Parser fallback for: {os.path.basename(file_path)}")
        return parse_std_file(file_path, table_info, t_name)

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

    def _send_to_upsert(self, rows, uploader: str = "system", filename: str = None, total_rows: int = None, t_name: str = None, table_info: dict = None):
        """파싱된 행 컬렉션을 직접 DB crud.apply_batch_updates 로 넘겨 초고속 처리합니다.

        rows: list[dict](기존 파이프라인 경로) 또는 이터레이터(std parser 스트리밍 경로).
        total_rows: 이터레이터 경로에서 진행률 계산용 총 행 수 — list면 생략 가능(len 사용).
        t_name/table_info: [D1] 파일 단위 config 스냅샷 — 헤더 검증(_try_std_parse)과 동일
        스냅샷을 사용해 처리 도중 config 변경에 의한 오배송/무음 0행 업서트를 차단한다.
        미전달 시(레거시 직접 호출) 이 시점에 1회 스냅샷을 잡는다.
        """
        # 1-2. 대상 테이블 스냅샷 확보
        if t_name is None and table_info is None:
            t_name, table_info = self._snapshot_table_context()

        if not t_name:
            logger.error("No table_name identified for upsert.")
            return

        # 3. 비즈니스 키 및 컬럼 매핑 정보 획득
        table_info = table_info or {}
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
        from itertools import islice
        file_tx_id = str(uuid.uuid4())

        batch_size = 1000
        total_changed = 0
        all_created_logs = []
        total_log_count = 0  # [C-5] 절단과 무관한 실제 총 감사 로그 건수

        # [확장성] list와 이터레이터 모두 지원 — 이터레이터(std parser)는 총 행 수를 인자로 받는다.
        if total_rows is None:
            total_rows = len(rows)
        row_iter = iter(rows)
        processed_rows = 0
        try:
            while True:
                chunk = list(islice(row_iter, batch_size))
                if not chunk:
                    break
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
                    logger.info(f"[{t_name}] 💾 Local batch update success ({len(items)} rows). Changed cells: {len(changed_cells)}")
                except Exception as e:
                    db.rollback()
                    logger.error(f"[{t_name}] ❌ Failed to apply local batch update: {e}")
                    raise e
                finally:
                    db.close()
                
                processed_rows += len(chunk)
                if self.on_progress_callback:
                    progress_pct = min(int((processed_rows / total_rows) * 100), 100) if total_rows else 100
                    try:
                        self.on_progress_callback(t_name, filename or "unknown", progress_pct, processed_rows, total_rows)
                    except Exception as pe:
                        logger.warning(f"Progress callback failed: {pe}")
                    
            if self.on_refresh_callback and total_changed > 0:
                self.on_refresh_callback(t_name, total_changed, all_created_logs, total_log_count)
                
        except Exception as outer_e:
            logger.error(f"[{t_name}] Outer error during batch injection loop: {outer_e}")
            raise outer_e

class WorkspaceWatcher:
    """
    Monitors all ingestion workspaces for new files.
    """
    def __init__(self, base_dir: str, on_refresh_callback=None, on_file_processed_callback=None, on_progress_callback=None, on_ingestion_state_callback=None):
        self.base_dir = base_dir
        self.observer = Observer()
        # [Heavy Lane P1] 전 워크스페이스 공유 heavy 레인 (워커 스레드는 첫 제출 시 지연 기동)
        self.heavy_lane = HeavyIngestionLane()
        self.on_ingestion_state_callback = on_ingestion_state_callback
        self.watch_count = 0
        self.watched_raw_paths = set()  # 이미 감시 등록된 raws/ 절대경로 (런타임 중복 등록 방지)
        # [F2] sync_new_workspaces 직렬화 락 — 임베디드 모드에서 /admin/reload-configs가
        # sync def(스레드풀)로 동시 실행되면 watched_raw_paths의 check-then-add가 비원자라
        # 같은 raws/가 observer에 이중 schedule될 수 있다(파일 이벤트 2회 처리 → 중복 인제션 경쟁).
        self._sync_lock = threading.Lock()
        # [Startup Sweep] raws/ 절대경로 → IngestionHandler. 기동/런타임 등록/주기 스윕이
        # 기존 이벤트 처리 경로(_handle_event)를 그대로 재사용하기 위한 레지스트리.
        self.handlers_by_raw_path = {}
        self._sweep_lock = threading.Lock()  # 스윕 동시 실행(기동+주기 등) 직렬화
        # path → (mtime, size): 동일 시그니처 재시도 차단(처리 실패 잔류 파일 무한 루프 방지)
        self._sweep_attempted = {}
        self._stop_event = threading.Event()
        self._periodic_sweep_thread = None
        self.on_refresh_callback = on_refresh_callback
        self.on_file_processed_callback = on_file_processed_callback
        self.on_progress_callback = on_progress_callback

    def _provision_workspaces(self) -> list:
        """[테이블 온보딩 자동화] table_config.json에 등록된 각 테이블에 대해
        표준 워크스페이스 구조(raws/archives/err/auto_update/scripts/config)를 보충 생성한다.
        **기존 파일/설정은 절대 덮어쓰지 않는다**(없는 폴더만 보충).
        [Deprecation 2026-07-25] 워크스페이스 config.json은 더 이상 생성하지 않는다 —
        폴더명↔테이블명 별칭은 table_config 항목의 `workspace_name` 필드가 담당한다.
        반환: 생성/보충이 실제로 발생한 테이블명 목록."""
        table_config = load_global_table_config()
        provisioned = []
        for t_name, t_cfg in table_config.items():
            if t_name in AUTO_PROVISION_EXCLUDED_TABLES:
                continue
            try:
                # [D2] 결과 기반 경로 봉쇄 + [D3] 충돌 별칭 무효화가 적용된 공용 역조회
                workspace_root = resolve_workspace_root(self.base_dir, t_name, table_config)
                changed = False
                for sub in WORKSPACE_SUBDIRS:
                    sub_dir = os.path.join(workspace_root, sub)
                    if not os.path.exists(sub_dir):
                        os.makedirs(sub_dir, exist_ok=True)
                        changed = True
                if changed:
                    provisioned.append(t_name)
            except Exception as e:
                logger.error(f"Failed to provision workspace for table '{t_name}': {e}")
        if provisioned:
            logger.info(f"🏗️ Auto-provisioned ingestion workspace structure for table(s): {provisioned}")
        return provisioned

    def _register_workspace(self, raws_root: str, table_config: dict) -> bool:
        """단일 raws/ 폴더를 observer에 감시 등록한다. 등록 성공 시 True."""
        abs_root = os.path.abspath(raws_root)
        if abs_root in self.watched_raw_paths:
            return False

        workspace_root = os.path.dirname(raws_root)
        config_dir = os.path.join(workspace_root, "config")
        config_path = os.path.join(config_dir, "config.json")
        archives_path = os.path.join(workspace_root, "archives")

        # Agent D v7: Be more flexible if config.json is not present
        if not os.path.exists(config_path) and os.path.exists(config_dir):
            json_files = [f for f in os.listdir(config_dir) if f.endswith('.json')]
            if json_files:
                config_path = os.path.join(config_dir, json_files[0])
                logger.info(f"Using alternative config: {config_path}")

        folder_name = os.path.basename(workspace_root)
        # 글로벌 table_config 기준 폴더명 해석 (workspace_name 별칭 > 폴더명=테이블명 규약)
        resolved_table = resolve_workspace_table(folder_name, table_config)

        if os.path.exists(config_path):
            # [Deprecation 2026-07-25] 레거시 워크스페이스 config — 하위호환 유지 + 기동/리로드 시 1회 경고.
            # [D4] 등록 시점 경고는 표준 파일명 config.json에만 — 커스텀 파서 규칙 파일
            # (예: sensor_config.json)에 대한 허위 발화 방지. 그런 파일이라도 table_name/std_parse를
            # 실제 소비하면 _load_legacy_config의 필드 게이트 경고가 처리 시점에 발화한다.
            if os.path.basename(config_path) == "config.json":
                warn_legacy_workspace_config(config_path)
            handler = IngestionHandler(workspace_root, config_path, archives_path, default_table_name=resolved_table or folder_name, on_refresh_callback=self.on_refresh_callback, on_file_processed_callback=self.on_file_processed_callback, on_progress_callback=self.on_progress_callback, on_ingestion_state_callback=self.on_ingestion_state_callback, heavy_lane=self.heavy_lane)
            watch_desc = f"using config: {os.path.basename(config_path)} (deprecated)"
        else:
            # config 가 없더라도 scripts 폴더 내에 파이썬 파일이 있거나(파이프라인 전용),
            # 폴더명이 table_config에 해석되면(workspace_name 별칭 또는 std parser 규약) 감지 대상으로 포함
            scripts_dir = os.path.join(workspace_root, "scripts")
            has_scripts = False
            if os.path.exists(scripts_dir):
                for f in os.listdir(scripts_dir):
                    if f.endswith('.py'):
                        has_scripts = True
                        break

            table_name = resolved_table or folder_name
            if has_scripts:
                watch_desc = f"Pipeline-only workspace, Table: {table_name}"
            elif resolved_table is not None:
                watch_desc = f"Std-parser workspace (table_config resolved), Table: {table_name}"
            else:
                logger.warning(f"Skipping {raws_root}: No JSON config or custom_parser found.")
                return False
            handler = IngestionHandler(workspace_root, None, archives_path, default_table_name=table_name, on_refresh_callback=self.on_refresh_callback, on_file_processed_callback=self.on_file_processed_callback, on_progress_callback=self.on_progress_callback, on_ingestion_state_callback=self.on_ingestion_state_callback, heavy_lane=self.heavy_lane)

        self.observer.schedule(handler, raws_root, recursive=False)
        self.watched_raw_paths.add(abs_root)
        self.handlers_by_raw_path[abs_root] = handler
        self.watch_count += 1
        logger.info(f"Watching: {raws_root} ({watch_desc})")
        return True

    def discover_and_watch(self):
        """
        Recursively finds 'raws' folders in the ingestion workspace and registers them.
        (사전 단계로 table_config 등록 테이블의 누락 워크스페이스를 자동 생성한다.)
        """
        try:
            self._provision_workspaces()
        except Exception as e:
            logger.error(f"Workspace auto-provisioning failed (continuing with existing workspaces): {e}")

        logger.info(f"Scanning {self.base_dir} for 'raws' folders...")
        table_config = load_global_table_config()
        for root, dirs, files in os.walk(self.base_dir):
            if os.path.basename(root) == "raws":
                self._register_workspace(root, table_config)

    def sync_new_workspaces(self) -> int:
        """[SYSTEM_RELOAD] table_config 재로드 후 신규 테이블 워크스페이스를 보충 생성하고,
        아직 감시 중이 아닌 raws/ 폴더를 **실행 중인 observer에 런타임 등록**한다
        (watchdog은 start() 이후에도 schedule() 가능 — 재기동 불필요).
        [F2] threading.Lock으로 전체를 직렬화한다 — 동시 reload 호출이 같은 raws/를
        이중 schedule하는 레이스 방지.
        반환: 새로 감시 등록된 raws/ 수."""
        with self._sync_lock:
            try:
                self._provision_workspaces()
            except Exception as e:
                logger.error(f"Workspace auto-provisioning failed during sync: {e}")

            added = 0
            new_raw_paths = []
            table_config = load_global_table_config()
            for root, dirs, files in os.walk(self.base_dir):
                if os.path.basename(root) == "raws":
                    if self._register_workspace(root, table_config):
                        added += 1
                        new_raw_paths.append(os.path.abspath(root))
            if added:
                logger.info(f"🔄 Runtime workspace sync: {added} new raws/ folder(s) now being watched.")
                self._ensure_observer_running()
                # [Startup Sweep] 신규 등록 raws/에 이미 존재하던 파일 처리 (백그라운드 —
                # 임베디드 모드에서 /admin/reload-configs 응답을 스윕이 블로킹하지 않도록).
                self.sweep_existing_files_async(new_raw_paths, reason="runtime-registration")
                self._ensure_periodic_sweep_running()
            return added

    def sweep_existing_files(self, raw_paths=None) -> int:
        """[Startup Sweep] 감시 대상 raws/ '직속' 기존 파일을 mtime 오름차순으로,
        기존 watchdog 이벤트 처리 경로(IngestionHandler._handle_event)와 동일하게 처리한다.

        - watchdog 이벤트 전용이던 워처가 다운타임(재기동 등) 중 도착한 파일을 영영
          방치하던 결함의 안전망. err/·archives/ 등은 raws/ 형제 폴더라 열거 대상이 아니고,
          raws/ 내부 하위 디렉토리도 제외한다(observer의 recursive=False와 동일 범위).
        - 동일 (mtime, size) 시그니처로 이미 시도한 파일은 재시도하지 않는다 — 처리 실패로
          raws/에 잔류한 파일이 주기 스윕마다 무한 재시도되는 루프 방지. 파일이 갱신되어
          시그니처가 바뀌면 다시 시도한다.
        - _handle_event가 중복 진입 가드·존재 확인·디바운스·재시도·아카이브/에러 이동·
          FileIngestionLog 기록을 모두 수행하므로 처리 의미론은 이벤트 경로와 동일하다.

        raw_paths: None이면 등록된 전체 raws/, 아니면 해당 절대경로 목록만.
        반환: 처리를 시도한 파일 수."""
        with self._sweep_lock:
            if raw_paths is None:
                targets = list(self.handlers_by_raw_path.items())
            else:
                wanted = {os.path.abspath(p) for p in raw_paths}
                targets = [(p, h) for p, h in self.handlers_by_raw_path.items() if p in wanted]

            candidates = []  # (mtime, abs_file_path, handler, signature)
            seen_paths = set()
            for raw_path, handler in targets:
                try:
                    names = os.listdir(raw_path)
                except OSError as e:
                    logger.warning(f"Sweep: cannot list {raw_path}: {e}")
                    continue
                for name in names:
                    fp = os.path.join(raw_path, name)
                    try:
                        if not os.path.isfile(fp):
                            continue
                        st = os.stat(fp)
                    except OSError:
                        continue  # 열거 중 이동/삭제된 파일
                    seen_paths.add(fp)
                    sig = (st.st_mtime, st.st_size)
                    if self._sweep_attempted.get(fp) == sig:
                        continue
                    candidates.append((st.st_mtime, fp, handler, sig))

            # 처리 완료(이동)된 파일의 시그니처는 정리해 무한 성장 방지
            for stale in [p for p in self._sweep_attempted
                          if p not in seen_paths and not os.path.exists(p)]:
                self._sweep_attempted.pop(stale, None)

            candidates.sort(key=lambda c: c[0])
            processed = 0
            for _mtime, fp, handler, sig in candidates:
                if self._stop_event.is_set():
                    break
                self._sweep_attempted[fp] = sig
                handler._handle_event(fp)
                processed += 1
            if processed:
                logger.info(f"🧹 Sweep: attempted {processed} pre-existing file(s) in raws/.")
            return processed

    def _sweep_safely(self, raw_paths=None, reason=""):
        try:
            self.sweep_existing_files(raw_paths)
        except Exception as e:
            logger.error(f"Sweep failed ({reason or 'unspecified'}): {e}")

    def sweep_existing_files_async(self, raw_paths=None, reason=""):
        """스윕을 데몬 스레드로 실행 (기동·reload 경로를 파일 처리가 블로킹하지 않도록)."""
        t = threading.Thread(
            target=self._sweep_safely, args=(raw_paths, reason),
            name="watcher-sweep", daemon=True,
        )
        t.start()
        return t

    def _periodic_sweep_loop(self):
        while not self._stop_event.wait(PERIODIC_SWEEP_INTERVAL_SECONDS):
            self._sweep_safely(None, "periodic")

    def _ensure_periodic_sweep_running(self):
        """[Startup Sweep] 이벤트 유실 안전망 — 저빈도 주기 재스캔 스레드 기동(1회)."""
        if self._periodic_sweep_thread is not None and self._periodic_sweep_thread.is_alive():
            return
        self._periodic_sweep_thread = threading.Thread(
            target=self._periodic_sweep_loop, name="watcher-periodic-sweep", daemon=True,
        )
        self._periodic_sweep_thread.start()

    def _ensure_observer_running(self):
        """[F3] 기동 시 watch 0건이면 start()가 observer를 띄우지 않는다 — 이후 런타임 등록된
        schedule()은 조용히 무동작(이벤트가 영원히 발화 안 함)이 된다. 신규 등록 시점에
        observer 생존을 확인하고 미기동이면 기동을 시도한다. (이미 stop()된 스레드는
        재시작 불가 → RuntimeError를 명시적 warning으로 노출.)"""
        if self.observer.is_alive():
            return
        try:
            self.observer.start()
            logger.info(f"▶️ Observer was not running — started now with {self.watch_count} watch(es).")
        except RuntimeError as e:
            logger.warning(
                f"Observer could not be (re)started for runtime-registered watches — "
                f"file events will NOT fire until process restart: {e}"
            )

    def stop(self):
        self._stop_event.set()  # 스윕/주기 스레드 중단 신호
        self.heavy_lane.stop()  # [Heavy Lane P1] 레인 워커 중단 신호 (데몬 스레드)
        self.observer.stop()
        self.observer.join()

    def start(self, blocking: bool = True):
        if self.watch_count == 0:
            # [F3] 이 시점에 미기동이어도 sync_new_workspaces의 _ensure_observer_running이
            # 런타임 등록 시 기동을 시도한다. (스윕·주기 재스캔도 sync 경로에서 함께 기동됨)
            logger.error("No valid 'raws' folders found to watch.")
            return

        if not self.observer.is_alive():
            self.observer.start()
        logger.info(f"Started observer with {self.watch_count} watches.")

        # [Startup Sweep] 워처 다운타임 중 raws/에 이미 도착해 있던 파일 처리.
        # observer 기동 '이후'에 스윕하므로 스윕 중 새로 떨어지는 파일 이벤트도 유실되지 않고,
        # 같은 파일의 스윕/이벤트 이중 진입은 핸들러의 processing_files 락 가드가 차단한다.
        self.sweep_existing_files_async(reason="startup")
        self._ensure_periodic_sweep_running()

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
