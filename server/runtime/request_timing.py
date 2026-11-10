"""Every HTTP request's own time and the database time inside it (총괄 10-07 ④).

A `Server-Timing` header on every response - `total;dur=<ms>, db;dur=<ms>;desc="<n> queries"` - so one
look at the browser's network panel says which call was slow and whether the time was the database.
A request over `slow_request_ms` (server/config/server_settings.json, default 1000) also says so in one
log line: method, path, status, total, db, queries, rows read, bytes sent, and each stage the request named
(`stage` - a grid page's count, keys, data rows, layers, ledger keys, serialize; a pool's wait and start), with
its database seconds, rows and the Python rest (lead 11-09: what a slow read spent where, owner «필요한 로그는
빨리 다 지어») - never the query string or the body. A measure that does not read says «?» in its own place.
The same file's `public_url` is read here too (`public_url()`): one reader of server_settings.json.

The database time is counted by two cursor hooks while a request's counter is set; a query outside a
request (a worker, a thread the request started) finds no counter and is not counted. The same hooks note the
database pid a request's query runs on while it runs, and a pool hand-off the name of the pool process's connections
(`runs_in`), so a freeze's line can ask what it waits for (`oldest_open`, lead 11-10); a slow request's line is kept
by its request (`slow_line`), so the freeze's line can carry it.
"""
import collections
import contextlib
import contextvars
import itertools
import json
import logging
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

from sqlalchemy import event
from sqlalchemy.engine import Engine

import error_said
import event_constants
import paths
from database.crud import _decode_config_text

logger = logging.getLogger("Server")

SETTINGS_FILE = "server_settings.json"
SETTINGS_PATH = paths.config_path(SETTINGS_FILE)
SLOW_REQUEST_CELL = "slow_request_ms"
#: Left out of the file, a request over this many ms is logged (총괄 10-07 ④ 2) ㄴ). null: never.
DEFAULT_SLOW_REQUEST_MS = 1000
PUBLIC_URL_CELL = "public_url"

#: [database seconds, queries, rows, queries whose rows the driver did not tell, stages] of the request running in
#: this context, or None outside one. A stage: (name, seconds, database seconds, queries, rows, untold).
_counter = contextvars.ContextVar("request_database_time", default=None)
_STARTED = "request_timing_started"
#: The `_open` key of the request running in this context.
_key = contextvars.ContextVar("request_timing_key", default=None)


@event.listens_for(Engine, "before_cursor_execute")
def _query_started(conn, cursor, statement, parameters, context, executemany):
    if _counter.get() is not None:
        conn.info[_STARTED] = time.perf_counter()
        running = _open.get(_key.get())
        if running is not None:
            running[2] = _backend_pid(conn)


@event.listens_for(Engine, "after_cursor_execute")
def _query_ended(conn, cursor, statement, parameters, context, executemany):
    started = conn.info.pop(_STARTED, None)
    if started is not None:
        running = _open.get(_key.get())
        if running is not None:
            running[2] = None
        rows = getattr(cursor, "rowcount", -1)
        told = isinstance(rows, int) and rows >= 0
        # a statement with no result (SET) tells no rows and reads none; one with a result untold (SQLite) is «?»
        add(time.perf_counter() - started, 1, rows if told else 0,
            0 if told or getattr(cursor, "description", None) is None else 1)


def _backend_pid(conn):
    """The database pid of this connection, off the driver (no query); None without one (SQLite)."""
    try:
        return conn.connection.dbapi_connection.get_backend_pid()
    except AttributeError:
        return None


def slow_request_ms():
    """The declared budget, or None: not measured - held until server_settings.json changes (`config_watcher.held`;
    🔴 e6a0bdbbd reverses 「a change waits for the restart」, owner 10-21 ㄱ). The same reading as table_config (a BOM
    is read); the budget's rule is the one every slow budget follows (`event_constants.slow_warn_ms`). A file that
    stops reading keeps the budget read before."""
    from database import config_watcher

    return config_watcher.held(config_watcher.names_of([SETTINGS_PATH]), "request_timing.slow", _read_slow_request_ms)


def _read_slow_request_ms():
    declared = DEFAULT_SLOW_REQUEST_MS
    try:
        loaded = _settings()
        if SLOW_REQUEST_CELL in loaded:
            declared = loaded[SLOW_REQUEST_CELL]
    except (OSError, ValueError) as exc:
        logger.warning("[Slow] %s could not be read (%s) - requests over %d ms are logged",
                       SETTINGS_FILE, exc, DEFAULT_SLOW_REQUEST_MS)
    return event_constants.slow_warn_ms(declared, "%s %s" % (SETTINGS_FILE, SLOW_REQUEST_CELL))


def public_url():
    """`public_url` - the address this server is opened at from elsewhere, `scheme://host[/path]` with no «/» at its
    end - or None: not written, or not an address (said once). A report file links its pictures' originals there, so
    they open from the file a mail carried (lead 10-29); held until server_settings.json changes, as the budget is."""
    from database import config_watcher

    return config_watcher.held(config_watcher.names_of([SETTINGS_PATH]), "request_timing.public_url", _read_public_url)


def _read_public_url():
    try:
        written = _settings().get(PUBLIC_URL_CELL)
    except (OSError, ValueError) as exc:
        logger.warning("[Report] %s could not be read (%s) - report files link their pictures relative to themselves",
                       SETTINGS_FILE, exc)
        return None
    if written is None or (isinstance(written, str) and not written.strip()):
        return None
    address = urlsplit(written.strip()) if isinstance(written, str) else None
    if address is None or address.scheme.lower() not in ("http", "https") or not address.netloc or (
            address.query or address.fragment):
        logger.warning("[Report] %s %s is not an http(s) address (%r) - report files link their pictures relative "
                       "to themselves", SETTINGS_FILE, PUBLIC_URL_CELL, written)
        return None
    return written.strip().rstrip("/")


def _settings():
    """server_settings.json as an object - {} when it is not there or is not an object; raises when it does not read."""
    if not os.path.exists(SETTINGS_PATH):
        return {}
    with open(SETTINGS_PATH, "rb") as handle:
        loaded = json.loads(_decode_config_text(handle.read()))
    return loaded if isinstance(loaded, dict) else {}


_open = {}                      # this process's requests not ended: key -> [perf_counter at begin, path, where it runs]
_keys = itertools.count()
#: The last slow requests' (when, line) by their `_open` key - what the freeze's line carries (`slow_line`) and the
#: help's operations answer reads (`slow_lines`).
_slow_said = collections.OrderedDict()
SLOW_KEPT = 50


def begin(path=None):
    """Start this request's counter; hand the token to `end`. `path`: the request's, without its query."""
    key, started = next(_keys), time.perf_counter()
    _open[key] = [started, path, None]
    return _counter.set([0.0, 0, 0, 0, []]), started, key, _key.set(key)


def runs_in(application_name):
    """This request's queries run in a pool process now, on connections named `application_name` - None: here again."""
    running = _open.get(_key.get())
    if running is not None:
        running[2] = application_name


def oldest_open():
    """(seconds, path, key, where its query runs now - a database pid, a pool process's connection name, or None) of
    the oldest request still without a response - (0.0, None, None, None) with none (`runtime.stall_watch`)."""
    opened = list(_open.items())
    if not opened:
        return 0.0, None, None, None
    key, (started, path, pid) = min(opened, key=lambda one: one[1][0])
    return time.perf_counter() - started, path, key, pid


def slow_line(key):
    """The [Slow] line request `key` left when it ended - None when it was not slow, is not over, or is long gone."""
    said = _slow_said.get(key)
    return said and said[1]


def slow_lines(count):
    """[(when, line)] of the last `count` slow requests, newest last."""
    return list(_slow_said.values())[-count:] if count > 0 else []


def spent():
    """What this request counted so far, as `add` takes it - what a pool process hands back."""
    seconds, queries, rows, untold, stages = _counter.get() or (0.0, 0, 0, 0, [])
    return {"seconds": seconds, "queries": queries, "rows": rows, "untold": untold, "stages": list(stages)}


def add(seconds, queries, rows=0, untold=0, stages=()):
    """Database time spent for this request outside its cursor events - a pool process's (`runtime.process_pool`), a
    COPY's (`crud._pg_multirow_upsert`, QA 11-08: the slow-request line left it out) - and the events' own; `stages`
    measured elsewhere (a pool process's, a pool's wait)."""
    counter = _counter.get()
    if counter is not None:
        counter[0] += seconds
        counter[1] += queries
        counter[2] += rows
        counter[3] += untold
        counter[4].extend(stages)


@contextlib.contextmanager
def stage(name):
    """A named part of this request, said on its slow line: its seconds, and the database seconds, queries and rows
    inside it. Outside a request it measures nothing."""
    counter = _counter.get()
    if counter is None:
        yield
        return
    before, started = counter[:4], time.perf_counter()
    try:
        yield
    finally:
        counter[4].append((name, time.perf_counter() - started) + tuple(
            now - was for now, was in zip(counter[:4], before)))


def end(began, method, path, response):
    """Stamp the response's header and, over the budget, say it once. No response (the app
    raised): the counter is only put away."""
    token, started, key, key_token = began
    _open.pop(key, None)
    seconds, queries, rows, untold, stages = _counter.get()
    _counter.reset(token)
    _key.reset(key_token)
    if response is None:
        return
    status, headers = response.status_code, response.headers
    total_ms, db_ms = (time.perf_counter() - started) * 1000.0, seconds * 1000.0
    headers["Server-Timing"] = 'total;dur=%.1f, db;dur=%.1f;desc="%d queries"' % (total_ms, db_ms, queries)
    budget = slow_request_ms()
    if budget is not None and total_ms > budget:
        line = "[Slow] %s %s %d - %s · db %d ms · %d queries%s" % (
            method, path, status, event_constants.slow_sentence(total_ms, budget), db_ms, queries,
            "".join(" · " + part for part in _parts(rows, untold, headers, stages)))
        _slow_said[key] = (datetime.now(timezone.utc).isoformat(timespec="seconds"), line)
        while len(_slow_said) > SLOW_KEPT:
            _slow_said.popitem(last=False)
        logger.warning("%s", line)


def _parts(rows, untold, headers, stages):
    """The slow line after its queries: rows read, bytes sent, then each stage as `name s (SQL s · rows · Python s)` -
    a stage with no query as `name s`. A part that does not read says «?» in its place, the line goes on."""
    def said(part):
        try:
            return part()
        except Exception as exc:                                   # noqa: BLE001 - this part only, said as «?»
            logger.warning("[Slow] the next line says «?» for a part that could not be said: %s", error_said.told(exc))
            return "?"

    def counted(rows, untold):
        return "?" if untold else format(rows, ",")

    def one(name, seconds, db, queries, rows, untold):
        if not queries:
            return "%s %.2f s" % (name, seconds)
        return "%s %.2f s (SQL %.2f s · %s rows · Python %.2f s)" % (name, seconds, db, counted(rows, untold),
                                                                      seconds - db)
    return ([said(lambda: "%s rows" % counted(rows, untold)),
             said(lambda: "%s bytes" % format(int(headers["content-length"]), ","))]
            + [said(lambda each=each: one(*each)) for each in stages])
