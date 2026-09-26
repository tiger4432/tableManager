# -*- coding: utf-8 -*-
"""What a collector script may write, how it is filled, and whether it can run as written.

🔴 A MODULE OF ITS OWN BECAUSE OF WHO READS IT. The scheduler fills and loads; the
Declarations report judges. `run_auto_update` rewrites its process's proxy settings when it
is imported, so the API process must not import it - this module imports nothing that does.
"""
import logging
import os
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger("Scheduler.Markers")


#: The zone every collector window is computed in, whatever the box's clock says
#: (소유자 2026-09-26 「KST」 - the dates an operator writes are KST too).
WINDOW_ZONE = ZoneInfo("Asia/Seoul")
#: How a window is written into a script whose header has no `# window_format:`.
DEFAULT_WINDOW_FORMAT = "%Y-%m-%d %H:%M:%S"
#: `{{LIST:table.column}}` - the grid's values of that column, as a quoted SQL list.
LIST_MARKER = re.compile(r"\{\{LIST:([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)\}\}")
#: The most values a list marker carries. A longer list refuses the run rather than being cut.
LIST_MARKER_CAP = 1000
#: The two window markers - one spelling, read by the filler and by the judge.
WINDOW_START, WINDOW_END = "{{WINDOW_START}}", "{{WINDOW_END}}"


class CollectorRefused(ValueError):
    """A run that must not start. Its message is the one sentence the Auto Update tab shows."""


def window_length(declared: str) -> timedelta:
    """`# window: 1d` -> its length. Days or hours; anything else is refused by name."""
    match = re.fullmatch(r"\s*(\d+)\s*([dh])\s*", str(declared or ""))
    if not match or int(match.group(1)) <= 0:
        raise CollectorRefused("'# window: %s' is not a length - write it as <n>d or <n>h"
                               % (declared,))
    amount = int(match.group(1))
    return timedelta(days=amount) if match.group(2) == "d" else timedelta(hours=amount)


def usual_window(length: timedelta, now: datetime = None) -> tuple:
    """The window a scheduled run fills: the `length` that ends now, in KST
    (소유자 2026-09-26 「지금-24h ~ 지금」 for `# window: 1d`)."""
    end = (now or datetime.now(WINDOW_ZONE)).astimezone(WINDOW_ZONE)
    return end - length, end


def _list_literal(db, table: str, column: str) -> str:
    """The grid's values of `table.column` as `'a','b'` - read through the value door the
    grid's own suggestions use, asked for up to LIST_MARKER_CAP values. Blank values are
    not in it; an empty, cut or unreadable list refuses the run by name."""
    import value_suggest

    marker = "{{LIST:%s.%s}}" % (table, column)
    settings = dict(value_suggest.resolve_settings(value_suggest.load_config()),
                    max_limit=LIST_MARKER_CAP, min_prefix_length=0)
    settings["max_probe_values"] = max(settings["max_probe_values"], LIST_MARKER_CAP + 1)
    try:
        got = value_suggest.suggest_values(db, table, column, prefix="",
                                           limit=LIST_MARKER_CAP, settings=settings)
    except value_suggest.SuggestValidationError:
        raise CollectorRefused("%s is not a column the grid can list - declare '%s.%s' in "
                               "table_config (text or number). The run did not start."
                               % (marker, table, column))
    if got.get("unavailable_reason"):
        raise CollectorRefused("%s could not be read (%s). The run did not start."
                               % (marker, got["unavailable_reason"]))
    if got.get("truncated"):
        raise CollectorRefused("%s has more than %d values, so the list would be cut. The run "
                               "did not start." % (marker, LIST_MARKER_CAP))
    if not got.get("values"):
        raise CollectorRefused("%s has no value in '%s'. The run did not start."
                               % (marker, table))
    return ",".join("'%s'" % str(value).replace("'", "''") for value in got["values"])


def fill_markers(text: str, window: tuple = None, window_format: str = None,
                 session_factory=None) -> str:
    """The ONE place a collector script's markers are filled - every marker kind goes
    through here, so a script sees one set of values whichever path runs it."""
    if window:
        fmt = window_format or DEFAULT_WINDOW_FORMAT
        start, end = window
        text = (text.replace(WINDOW_START, start.strftime(fmt))
                    .replace(WINDOW_END, end.strftime(fmt)))
    if LIST_MARKER.search(text):
        if session_factory is None:
            from database.database import SessionLocal as session_factory
        db = session_factory()
        read = {}

        def literal(match):
            if match.group(0) not in read:        # the same marker twice is read once
                read[match.group(0)] = _list_literal(db, match.group(1), match.group(2))
            return read[match.group(0)]
        try:
            text = LIST_MARKER.sub(literal, text)
        finally:
            db.close()
    return text


def filled_copy_path(script_path: str) -> str:
    """Where the stdout path runs its filled copy: beside the original, so the script's
    sibling imports still resolve, and not `*.py`, so discovery never registers it."""
    return "%s.%d.filled" % (script_path, os.getpid())


def parse_script_comments(script_path: str) -> dict:
    """
    파이썬 파일의 상단 20줄을 스캔하여 주석에 적힌 크론 일정 및 파일명 접두사 설정값을 반환합니다.
    """
    config = {
        "schedule": None,
        "filename_prefix": os.path.basename(script_path)[:-3],
        "window": None,
        "window_format": None,
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
                        elif key in ("window", "window_format"):
                            config[key] = val
    except Exception as e:
        logger.warning(f"Failed to parse script comments for {script_path}: {e}")
    return config


def collector_scripts(root: str) -> list:
    """`(table, script path)` for every `<root>/ingestion_workspace/<table>/auto_update/*.py` -
    the one list the scheduler loads and the Declarations report judges."""
    workspace = os.path.join(root, "ingestion_workspace")
    if not os.path.isdir(workspace):
        return []
    out = []
    for table in os.listdir(workspace):
        folder = os.path.join(workspace, table, "auto_update")
        if not os.path.isdir(folder):
            continue
        for filename in os.listdir(folder):
            if filename.endswith(".py"):
                out.append((table, os.path.join(folder, filename)))
    return out


def script_refusals(script_path: str, header: dict = None, catalogue: dict = None) -> list:
    """Why this collector script cannot run as written - [] when it can. The ONE judge the
    scheduler's load and the Declarations report both ask.

    A window header and the window markers come as a pair; a list marker names a column
    table_config declares and the grid can list (text or number).
    """
    header = header or parse_script_comments(script_path)
    with open(script_path, "r", encoding="utf-8") as f:
        text = f.read()
    name = os.path.basename(script_path)
    out = []
    writes_window = WINDOW_START in text or WINDOW_END in text
    if header.get("window"):
        try:
            window_length(header["window"])
        except CollectorRefused as refused:
            out.append(str(refused))
        if not writes_window:
            out.append("'%s' declares '# window: %s' but writes neither %s nor %s - add the "
                       "markers or remove the header" % (name, header["window"], WINDOW_START,
                                                         WINDOW_END))
    elif writes_window:
        out.append("'%s' writes %s or %s but declares no '# window:' - add '# window: 1d' to "
                   "its header" % (name, WINDOW_START, WINDOW_END))
    if catalogue is None:
        from database import crud
        catalogue = crud.TABLE_CONFIG
    for match in LIST_MARKER.finditer(text):
        table, column = match.groups()
        types = (catalogue.get(table) or {}).get("column_types") or {}
        if column not in types:
            out.append("%s names a column table_config does not declare on '%s'"
                       % (match.group(0), table))
        elif types[column] == "datetime":
            out.append("%s names a datetime column - a list takes a text or number column"
                       % match.group(0))
    return out


#: One backfill run of a script covers this much (소유자 2026-09-26 「하루 단위」 · 「24h 씩」).
BACKFILL_SLICE = timedelta(days=1)


def backfill_start(text: str) -> datetime:
    """The operator's start, in KST - a bare date is that day's 00:00."""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(text or "").strip(), fmt).replace(tzinfo=WINDOW_ZONE)
        except ValueError:
            continue
    raise CollectorRefused("start '%s' is not a date - write it as YYYY-MM-DD (KST), "
                           "optionally with HH:MM" % (text,))


def backfill_windows(start: datetime, now: datetime = None) -> list:
    """24-hour windows from `start` to now, end to end - the last one cut at now, so there
    is no gap and no overlap."""
    now = (now or datetime.now(WINDOW_ZONE)).astimezone(WINDOW_ZONE)
    out, cursor = [], start
    while cursor < now:
        out.append((cursor, min(cursor + BACKFILL_SLICE, now)))
        cursor += BACKFILL_SLICE
    return out


def backfill_target(root: str, key: str) -> tuple:
    """`<table>/<script>` -> (table, path, header) of a script collector that declares a
    window and passes the judge. Anything else is refused by name."""
    for table, path in collector_scripts(root):
        if "%s/%s" % (table, os.path.basename(path)) != key:
            continue
        header = parse_script_comments(path)
        if not header["schedule"]:
            raise CollectorRefused("'%s' is not a script collector (no '# schedule:')" % key)
        if not header["window"]:
            raise CollectorRefused("'%s' declares no '# window:', so it has no time window "
                                   "to backfill" % key)
        why = script_refusals(path, header)
        if why:
            raise CollectorRefused("'%s' is not loaded - %s" % (key, why[0]))
        return table, path, header
    raise CollectorRefused("no collector '%s' - name it as <table>/<script.py>" % key)
