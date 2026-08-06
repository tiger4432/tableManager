import os
import sys
import types
import logging

# Log files follow the data root, never this module's location. utils/ can be
# imported before the entry point puts server/ on sys.path (main.py imports
# utils.logger at line 19, `import paths` at line 34), so fall back the same way
# database/crud.py does rather than silently reverting to the live tree.
try:
    import paths
except ImportError:  # pragma: no cover - defensive fallback
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import paths


class ConsoleSafeHandler(logging.StreamHandler):
    """Console handler that survives a terminal codec it cannot render.

    The console here is cp949 and the messages carry Korean server-authored
    sentences plus the occasional typographic character (em dash, ellipsis,
    emoji) that cp949 has no code point for. Stock `logging` reacts to that by
    losing **the whole line** and printing a `--- Logging error ---` traceback in
    its place: the operator loses the message they needed and gains noise they
    cannot act on. Measured on this box, cp949 stream, one U+2014 in a
    deprecation warning: 0 bytes to the console, 819 characters of traceback to
    stderr.

    Re-encoding with `errors="replace"` costs the one character the terminal
    cannot draw and keeps the sentence. The stream's OWN encoding is used on
    purpose - forcing utf-8 bytes at a cp949 console would trade one lost line
    for mojibake on every Korean sentence in the log. The file half of the log
    is opened `encoding='utf-8'` and is not touched by any of this.

    WHY THIS DOES NOT CALL `super().emit()`
    --------------------------------------
    An earlier spelling of this class (server/map_alignment.py) wrapped
    `super().emit(record)` in `except UnicodeEncodeError`. That branch is
    unreachable: `logging.StreamHandler.emit` catches the error itself and routes
    it to `handleError`, so nothing ever propagates to the caller. It looked like
    a fix and did nothing - verified by emitting U+2014 through it against a cp949
    stream and getting the same 0 bytes as the stock handler. The write is
    therefore performed here, with the rescue around the write itself.

    `emit` deliberately depends on nothing but the standard `StreamHandler`
    surface (`format`/`stream`/`terminator`/`flush`/`handleError`) so that
    `make_console_safe()` can bind it onto handlers this module did not create.
    """

    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self.stream
            try:
                stream.write(msg + self.terminator)
            except UnicodeEncodeError:
                # TextIOWrapper encodes the whole string before it writes any of
                # it, so nothing landed and re-writing cannot duplicate output.
                enc = getattr(stream, "encoding", None) or "ascii"
                stream.write(
                    msg.encode(enc, "replace").decode(enc, "replace")
                    + self.terminator)
            self.flush()
        except RecursionError:  # see CPython issue 36272
            raise
        except Exception:
            self.handleError(record)


def make_console_safe(handler):
    """Give an existing console handler `ConsoleSafeHandler`'s emit. Returns it.

    For handlers created by somebody else - uvicorn installs its own pair before
    it ever imports `main:app` - where replacing the object would also throw away
    whatever formatter and filters that owner attached.

    File handlers are left alone on purpose: `logging.FileHandler` is a subclass
    of `StreamHandler`, so an `isinstance` check at a call site will offer them
    up, and their utf-8 stream has nothing to be rescued from.
    """
    if not isinstance(handler, logging.StreamHandler):
        return handler
    if isinstance(handler, (logging.FileHandler, ConsoleSafeHandler)):
        return handler
    handler.emit = types.MethodType(ConsoleSafeHandler.emit, handler)
    return handler


class ColoredProcessFormatter(logging.Formatter):
    """
    로그 레벨 및 프로세스명에 따라 콘솔 출력 색상을 동적으로 매핑해 주는 표준 로깅 포맷터입니다.
    """
    # ANSI Color Escape Codes
    RESET = "\033[0m"
    BOLD = "\033[1m"
    
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    BLUE = "\033[94m" # GraphSync 전용 파란색 추가
    ORANGE = "\033[33m" # Bold Yellow/Orange

    # 프로세스별 기본 시그니처 색상 테이블
    PROCESS_COLORS = {
        "SERVER": GREEN,
        "WATCHER": CYAN,
        "CHAIN": MAGENTA,
        "SCHEDULER": YELLOW,
        "GRAPHSYNC": BLUE
    }

    def __init__(self, fmt=None, datefmt=None, process_name="SYSTEM"):
        super().__init__(fmt, datefmt)
        self.process_name = process_name.upper()
        # 프로세스 시그니처 색상 획득
        self.proc_color = self.PROCESS_COLORS.get(self.process_name, self.RESET)

    def format(self, record):
        # 1. 원본 메시지 빌드
        orig_msg = super().format(record)
        
        # 2. 로그 레벨에 따른 동적 컬러 결정
        level = record.levelno
        
        if level >= logging.ERROR:
            # 에러 및 치명 오류는 강렬한 밝은 빨간색으로 통일 강조
            color_prefix = f"{self.RED}{self.BOLD}"
        elif level == logging.WARNING:
            # 경고는 주황색으로 강조
            color_prefix = f"{self.ORANGE}{self.BOLD}"
        else:
            # 정상 수준(INFO, DEBUG)은 프로세스 고유 시그니처 색상 적용
            color_prefix = self.proc_color
            
        return f"{color_prefix}{orig_msg}{self.RESET}"

# Third-party loggers that would otherwise flood the process log now that
# handlers live on the root logger. Each is pinned to WARNING: their INFO output
# is engine/protocol chatter, and burying our own lines under it is how a log
# stops being read. Errors from them still land.
NOISY_THIRD_PARTY = (
    "sqlalchemy", "sqlalchemy.engine", "sqlalchemy.pool",
    "watchdog", "urllib3", "asyncio", "requests", "PIL",
    "multipart", "python_multipart", "neo4j", "matplotlib",
)


def get_process_logger(process_name: str, log_filename: str) -> logging.Logger:
    """
    공통 로깅 규격을 따르며, 프로세스별 고유 컬러(ANSI) 스트림 핸들러와
    깨끗한 Plain-Text 파일 핸들러가 결합된 전용 Logger 인스턴스를 반환합니다.

    [B3] The handlers are attached to the ROOT logger, not to the named process
    logger, and this is the whole point of the function.

    Modules log to their own loggers - `crud.py` uses `logging.getLogger("Server")`,
    `bonding_plan.py` uses `__name__`, and so on. Only loggers that happen to be
    *children* of the process name (`Watcher.DirectoryWatcher` under `Watcher`)
    inherited a handler. Everything else propagated to a root logger this
    function had just stripped of handlers, hit no handler anywhere, and fell to
    `logging.lastResort`: bare stderr, WARNING and above, absent from the
    process's own log file.

    That is not cosmetic. `crud.py`'s undeclared-column warning exists to surface
    silent data loss during a 100,000-row ingestion, and in the watcher process -
    the only process that runs those ingestions - it landed nowhere anyone would
    look. Blocker B3.

    Handlers on root, none on the named logger: every logger in the process
    reaches the file exactly once. `%(name)s` in the format keeps the origin, so
    a line from `Server` inside the watcher process is still identifiable as
    such.
    """
    log_format = '[%(name)s] [%(asctime)s] %(levelname)s - %(message)s'

    # Root owns the handlers. Clear whatever was there (another basicConfig, or a
    # previous call in the same process) so repeated calls cannot double up.
    root_logger = logging.getLogger()
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass
    root_logger.setLevel(logging.INFO)

    # 1. 콘솔 핸들러 (동적 컬러 Formatter 장착)
    # ConsoleSafeHandler, not StreamHandler: this one line covers every process
    # the launcher starts, because all six of them get their console handler from
    # right here. See the class for what it rescues and why it keeps cp949.
    console_handler = ConsoleSafeHandler(sys.stdout)
    console_handler.setFormatter(ColoredProcessFormatter(log_format, process_name=process_name))
    root_logger.addHandler(console_handler)

    # 2. 파일 핸들러 (ANSI 문자 없는 평문 Formatter 장착)
    # Routed through paths.py - the single ASSY_DATA_ROOT override point - so an
    # isolated process cannot append to the user's live server/*.log. Unset,
    # paths.DATA_ROOT is server/, i.e. production is byte-for-byte unchanged.
    log_path = paths.log_path(log_filename)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    file_handler = logging.FileHandler(log_path, encoding='utf-8')
    file_handler.setFormatter(logging.Formatter(log_format))
    root_logger.addHandler(file_handler)

    for noisy in NOISY_THIRD_PARTY:
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logger = logging.getLogger(process_name)
    logger.setLevel(logging.INFO)
    logger.propagate = True  # 자식 모듈들의 로깅 전파를 부모 로거로 허용

    # No handlers on the process logger: it reaches the file by propagating to
    # root like everything else. A handler here as well would print every one of
    # its own lines twice.
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    return logger
