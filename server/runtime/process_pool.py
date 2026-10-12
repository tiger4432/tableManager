"""A heavy route's body in a process of its own (lead b47388fde).

`in_pool(body)` registered as a route's endpoint is the seat - the ROUTE, not the name: code that calls the body itself
(`mappers/contrast_walk.py` calls `evidence_subgraph`) gets its answer as before. The pool process runs the body on
its own small database pool and hands back BYTES - so a big walk neither holds this process's GIL nor shares its cores
while other requests wait. The walk is the first user.
`ingestion_settings.json`, read once per request: `walk_processes` - how many may run at once (0: the body runs in
this process, as before); `walk_seconds_max` - how long a request waits for one and for its answer (then a 503).
An HTTPException raised there is raised here as the same one; anything else is this request's 500.
A pool process that dies fails only the request it was running; the next request starts another.
"""
import functools
import importlib
import logging
import multiprocessing
import os
import reprlib
import threading
import time
import traceback

from fastapi import HTTPException
from starlette.responses import Response

SETTING = "walk_processes"
DEFAULT = 2
WAIT_SETTING = "walk_seconds_max"
DEFAULT_WAIT = 120
#: A pool process runs one body at a time: its session and nothing else (chain.slots.SLOT_POOL's size).
POOL_DB = {"ASSY_DB_POOL_SIZE": "2", "ASSY_DB_MAX_OVERFLOW": "2"}
#: Its logger - and so its connections' application name, `assy_walkpool`; its own lines go to walk_pool.log.
PROCESS_NAME = "WalkPool"

logger = logging.getLogger("Server")

_idle = []                      # [process, connection, generation] ready for a body
_taken = [0]                    # pool processes running a body, or being started
_modules = []                   # the modules of the bodies in_pool wraps - a pool process imports them before it is ready
_cond = threading.Condition()
_generation = [0]               # recycle() moves it; a process of an older one is not given a body again
_said = set()                   # a wrong setting value is said once
_warmed = [False]               # warm() was called here - the server's start; a daemon running the same reload never


def _settings():
    from parsers.directory_watcher import load_ingestion_settings

    return load_ingestion_settings()


def size(settings=None):
    """How many pool processes may run at once - 0: none, the body runs here. Only a whole number from 0 up is read;
    anything else is said once and reads as 0 (the switch that turns it off must not turn into the default)."""
    settings = _settings() if settings is None else settings
    if SETTING not in settings:
        return DEFAULT
    value = settings[SETTING]
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    _say_once(SETTING, value, "0 - walks run in the server")
    return 0


def wait_seconds(settings=None):
    """How long a request waits for a pool process, and then for its answer."""
    settings = _settings() if settings is None else settings
    if WAIT_SETTING not in settings:
        return DEFAULT_WAIT
    value = settings[WAIT_SETTING]
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        return value
    _say_once(WAIT_SETTING, value, "%d s" % DEFAULT_WAIT)
    return DEFAULT_WAIT


def _say_once(name, value, reading):
    if (name, repr(value)) not in _said:
        _said.add((name, repr(value)))
        logger.error("[Pool] ingestion_settings.json %s is %r - read as %s", name, value, reading)


def in_pool(body):
    """`body` as a route endpoint that runs it in a pool process, with that process's own session as `db`.

    ⚠️ A session on another engine than this process's own (a test's override) cannot be carried there, so that call
    runs here - as it does with `walk_processes: 0`."""
    target = (body.__module__, body.__name__)
    _modules.append(body.__module__)

    @functools.wraps(body)
    def pooled(*args, db=None, **kwargs):
        from database.database import engine

        settings = _settings()
        limit = size(settings)
        if limit == 0:
            _drain()
        bind = getattr(db, "get_bind", None)
        if args or limit == 0 or bind is None or bind() is not engine:
            return body(*args, db=db, **kwargs)
        return _reply(_run(target, kwargs, limit, wait_seconds(settings)))

    pooled.__pool_body__ = body
    return pooled


def warm():
    """Start `size()` pool processes behind the server's start and after a reload (lead b47388fde), so the first walk
    does not pay for one. A walk that comes first starts its own, as before; a failure is one log line. Testing mode
    starts none."""
    _warmed[0] = True
    if os.getenv("TESTING") == "True":
        return

    def start_all():
        try:
            while True:
                with _cond:
                    if len(_idle) + _taken[0] >= size():
                        return
                    _taken[0] += 1
                worker = None
                try:
                    worker = _start(wait_seconds())
                finally:
                    with _cond:
                        _taken[0] -= 1
                        _keep_or_end(worker, size())
                        _cond.notify()
        except Exception as exc:                                # noqa: BLE001 - the server goes on all the same
            logger.error("[Pool] walk processes not started ahead - the first walk starts one: %s: %s",
                         type(exc).__name__, exc)

    threading.Thread(target=start_all, name="walk-pool-warm", daemon=True).start()


def recycle():
    """A reload empties this process's caches; a pool process holds its own copies. The idle ones end now, a running
    one after its answer - and new ones start behind it, and in its place when it ends.
    🔴 Only in a process that warmed the pool (lead eb9c328e4): the watcher, chain worker and auto-update daemons run the
    same table-config reload, and a walk process started there runs the daemon's top level again as `__mp_main__`."""
    if not _warmed[0]:
        return
    with _cond:
        _generation[0] += 1
        _drain_locked()
    warm()


def _drain():
    with _cond:
        _drain_locked()


def _drain_locked():
    for worker in _idle:
        _end(worker)
    _idle.clear()


def _keep_or_end(worker, limit):
    """Back to the idle ones when it is of this generation, alive and within `limit` - else ended. Under `_cond`."""
    if worker is None:
        return
    if worker[2] == _generation[0] and worker[0].is_alive() and len(_idle) + _taken[0] < limit:
        _idle.append(worker)
    else:
        _end(worker)


def _reply(answer):
    from runtime import request_timing

    request_timing.add(*answer["db"])
    kind = answer["kind"]
    if kind == "json":
        return Response(answer["body"], media_type="application/json")
    if kind == "response":
        response = Response(answer["body"], status_code=answer["status"])
        response.raw_headers = answer["headers"]
        return response
    if kind == "http":
        raise HTTPException(answer["status"], detail=answer["detail"], headers=answer["headers"])
    logger.error("[Pool] %s", answer["trace"])
    raise RuntimeError(answer["error"])


def _unavailable(reason, message):
    return HTTPException(status_code=503, detail={"reason": reason, "message": message})


def _run(target, kwargs, limit, seconds):
    """🔴 ONE DEADLINE (lead 9a3c510c5): a slot, a start and the answer share `seconds` - not `seconds` each."""
    deadline = time.monotonic() + seconds
    with _cond:
        while _taken[0] >= max(limit, 1):
            left = deadline - time.monotonic()
            if left <= 0:
                raise _unavailable("walk_pool_busy", "Every walk process stayed busy for %g s - try again, or raise "
                                   "walk_processes in ingestion_settings.json" % seconds)
            _cond.wait(left)
        _taken[0] += 1
        worker = None
        while _idle and worker is None:
            worker = _idle.pop()
            if worker[2] != _generation[0] or not worker[0].is_alive():   # older, or died while it waited
                _end(worker)
                worker = None
    keep = False
    try:
        if worker is None:
            worker = _start(max(deadline - time.monotonic(), 0))   # outside the lock: another body takes an idle one
        process, connection, _generation_of = worker
        connection.send((target, kwargs))
        if not connection.poll(max(deadline - time.monotonic(), 0)):
            raise _unavailable("walk_timed_out", "The walk did not finish in %g s and its walk process was stopped - "
                               "narrow the walk, or raise walk_seconds_max in ingestion_settings.json" % seconds)
        try:
            answer = connection.recv()
        except (EOFError, OSError):
            process.join(1)
            # said in server.log here (lead, 10-13): raised bare it reached only uvicorn's «Exception in ASGI application»
            logger.error("[Pool] the pool process running this request ended - pid %s, exit code %s, %s.%s(%s)",
                         process.pid, process.exitcode, target[0], target[1], reprlib.repr(kwargs))
            raise RuntimeError("the pool process running this request ended (exit code %s)" % process.exitcode)
        keep = True
        return answer
    finally:
        with _cond:
            _taken[0] -= 1
            older = worker is not None and worker[2] != _generation[0]
            if keep:
                _keep_or_end(worker, limit)
            elif worker is not None:
                _end(worker)                        # a stuck or broken one does not take another body
            _cond.notify()
        if older:
            warm()                                  # a walk a reload ran through: a new one takes its place (lead eb9c328e4)


def _start(seconds):
    """A pool process that has imported its bodies' modules - so the first body it runs pays nothing for that."""
    generation = _generation[0]
    context = multiprocessing.get_context("spawn")
    mine, theirs = context.Pipe()
    process = context.Process(target=_serve, args=(theirs, list(dict.fromkeys(_modules))), name=PROCESS_NAME,
                              daemon=True)
    process.start()
    theirs.close()
    try:
        if not mine.poll(seconds):
            _end([process, mine, generation])
            raise _unavailable("walk_process_not_ready", "A walk process did not start in %g s" % seconds)
        mine.recv()
    except (EOFError, OSError):
        process.join(1)
        raise RuntimeError("a pool process ended before it was ready (exit code %s)" % process.exitcode)
    return [process, mine, generation]


def _end(worker):
    process, connection, _generation_of = worker
    connection.close()
    if process.is_alive():
        process.terminate()


def _serve(connection, modules):
    """The pool process: ready once its bodies' modules are imported, then one body at a time, until the server's
    end of the pipe closes."""
    os.environ.update(POOL_DB)
    from utils.logger import get_process_logger

    get_process_logger(PROCESS_NAME, "walk_pool.log")
    for module in modules:
        importlib.import_module(module)
    import database.database                                    # noqa: F401 - its engine, before the first body
    connection.send("ready")
    while True:
        try:
            target, kwargs = connection.recv()
        except (EOFError, OSError):
            return
        connection.send(_answer(target, kwargs))


def _answer(target, kwargs):
    from database.database import SessionLocal
    from runtime import offloop_json, request_timing

    module, name = target
    body = getattr(importlib.import_module(module), name)
    body = getattr(body, "__pool_body__", body)                 # a route registered as in_pool(body) leaves the name bare
    began = request_timing.begin()
    db = SessionLocal()
    try:
        answer = body(db=db, **kwargs)
        if isinstance(answer, Response):
            out = {"kind": "response", "body": answer.body, "status": answer.status_code,
                   "headers": answer.raw_headers}
        else:
            out = {"kind": "json", "body": offloop_json.encode(answer).payload}
    except HTTPException as exc:
        out = {"kind": "http", "status": exc.status_code, "detail": exc.detail, "headers": exc.headers}
    except Exception as exc:                                    # noqa: BLE001 - the request's 500
        out = {"kind": "error", "error": "%s: %s" % (type(exc).__name__, exc),
               "trace": traceback.format_exc()}
    finally:
        db.close()
    out["db"] = request_timing.spent()
    request_timing.end(began, None, None, None)
    return out
