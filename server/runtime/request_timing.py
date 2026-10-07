"""Every HTTP request's own time and the database time inside it (총괄 10-07 ④).

A `Server-Timing` header on every response - `total;dur=<ms>, db;dur=<ms>;desc="<n> queries"` - so one
look at the browser's network panel says which call was slow and whether the time was the database.
A request over `slow_request_ms` (server/config/server_settings.json, default 1000) also says so in one
log line: method, path, status, total, db, queries - never the query string or the body.

The database time is counted by two cursor hooks while a request's counter is set; a query outside a
request (a worker, a thread the request started) finds no counter and is not counted.
"""
import contextvars
import functools
import json
import logging
import os
import time

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


@functools.lru_cache(maxsize=None)
def slow_request_ms():
    """The declared budget, read once per process (a change waits for the restart), or None: not
    measured. The same reading as table_config (a BOM is read); the budget's rule is the one
    every slow budget follows (`event_constants.slow_warn_ms`)."""
    declared = DEFAULT_SLOW_REQUEST_MS
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "rb") as handle:
                loaded = json.loads(_decode_config_text(handle.read()))
            if isinstance(loaded, dict) and SLOW_REQUEST_CELL in loaded:
                declared = loaded[SLOW_REQUEST_CELL]
        except (OSError, ValueError) as exc:
            logger.warning("[Slow] %s could not be read (%s) - requests over %d ms are logged",
                           SETTINGS_FILE, exc, DEFAULT_SLOW_REQUEST_MS)
    return event_constants.slow_warn_ms(declared, "%s %s" % (SETTINGS_FILE, SLOW_REQUEST_CELL))


def begin():
    """Start this request's counter; hand the token to `end`."""
    return _counter.set([0.0, 0]), time.perf_counter()


def end(began, method, path, response):
    """Stamp the response's header and, over the budget, say it once. No response (the app
    raised): the counter is only put away."""
    token, started = began
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
