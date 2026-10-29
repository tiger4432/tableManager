"""Every HTTP request's own time and the database time inside it (총괄 10-07 ④).

A `Server-Timing` header on every response - `total;dur=<ms>, db;dur=<ms>;desc="<n> queries"` - so one
look at the browser's network panel says which call was slow and whether the time was the database.
A request over `slow_request_ms` (server/config/server_settings.json, default 1000) also says so in one
log line: method, path, status, total, db, queries - never the query string or the body.
The same file's `public_url` is read here too (`public_url()`): one reader of server_settings.json.

The database time is counted by two cursor hooks while a request's counter is set; a query outside a
request (a worker, a thread the request started) finds no counter and is not counted.
"""
import contextvars
import itertools
import json
import logging
import os
import time
from urllib.parse import urlsplit

from sqlalchemy import event
from sqlalchemy.engine import Engine

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

#: [database seconds, queries] of the request running in this context, or None outside one.
_counter = contextvars.ContextVar("request_database_time", default=None)
_STARTED = "request_timing_started"


@event.listens_for(Engine, "before_cursor_execute")
def _query_started(conn, cursor, statement, parameters, context, executemany):
    if _counter.get() is not None:
        conn.info[_STARTED] = time.perf_counter()


@event.listens_for(Engine, "after_cursor_execute")
def _query_ended(conn, cursor, statement, parameters, context, executemany):
    counter, started = _counter.get(), conn.info.pop(_STARTED, None)
    if counter is not None and started is not None:
        counter[0] += time.perf_counter() - started
        counter[1] += 1


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


_open = {}                      # this process's requests begun and not ended: key -> (perf_counter at begin, path)
_keys = itertools.count()


def begin(path=None):
    """Start this request's counter; hand the token to `end`. `path`: the request's, without its query."""
    key, started = next(_keys), time.perf_counter()
    _open[key] = (started, path)
    return _counter.set([0.0, 0]), started, key


def oldest_open():
    """(seconds, path) of the oldest request still without a response - (0.0, None) with none (`runtime.stall_watch`)."""
    opened = list(_open.values())
    if not opened:
        return 0.0, None
    started, path = min(opened, key=lambda one: one[0])
    return time.perf_counter() - started, path


def spent():
    """[database seconds, queries] counted so far in this request - what a pool process hands back."""
    return list(_counter.get() or (0.0, 0))


def add(seconds, queries):
    """Database time a pool process spent for this request (`runtime.process_pool`)."""
    counter = _counter.get()
    if counter is not None:
        counter[0] += seconds
        counter[1] += queries


def end(began, method, path, response):
    """Stamp the response's header and, over the budget, say it once. No response (the app
    raised): the counter is only put away."""
    token, started, key = began
    _open.pop(key, None)
    seconds, queries = _counter.get()
    _counter.reset(token)
    if response is None:
        return
    status, headers = response.status_code, response.headers
    total_ms, db_ms = (time.perf_counter() - started) * 1000.0, seconds * 1000.0
    headers["Server-Timing"] = 'total;dur=%.1f, db;dur=%.1f;desc="%d queries"' % (total_ms, db_ms, queries)
    budget = slow_request_ms()
    if budget is not None and total_ms > budget:
        logger.warning("[Slow] %s %s %d - %s · db %d ms · %d queries", method, path, status,
                       event_constants.slow_sentence(total_ms, budget), db_ms, queries)
