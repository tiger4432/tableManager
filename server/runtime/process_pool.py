"""A heavy route's body in a process of its own (lead b47388fde).

`in_pool` on a route is the seat. The server hands the body its arguments in a pool process; the pool
process runs it on its own small database pool and hands back BYTES - so a big walk neither holds this
process's GIL nor shares its cores while other requests wait. The walk is the first user.
`ingestion_settings.json` `walk_processes`: how many may run at once - read per request; 0 runs the body
in this process, as before.
An HTTPException raised there is raised here as the same one; anything else is this request's 500.
A pool process that dies fails only the request it was running; the next request starts another.
"""
import functools
import importlib
import logging
import multiprocessing
import os
import threading
import traceback

from fastapi import HTTPException
from starlette.responses import Response

SETTING = "walk_processes"
DEFAULT = 2
#: A pool process runs one body at a time: its session and nothing else (chain.slots.SLOT_POOL's size).
POOL_DB = {"ASSY_DB_POOL_SIZE": "2", "ASSY_DB_MAX_OVERFLOW": "2"}
#: Its logger - and so its connections' application name, `assy_walkpool`.
PROCESS_NAME = "WalkPool"

logger = logging.getLogger("Server")

_idle = []                      # [process, connection, generation] ready for a body
_running = []                   # the same, while a body runs - read by recycle() and by tests
_cond = threading.Condition()
_generation = [0]               # recycle() moves it; a process of an older one is not given a body again


def size(settings=None):
    """How many pool processes may run at once - 0: none, the body runs here."""
    from parsers.directory_watcher import load_ingestion_settings

    settings = load_ingestion_settings() if settings is None else settings
    value = settings.get(SETTING, DEFAULT)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else DEFAULT


def in_pool(body):
    """The route runs `body` in a pool process, with that process's own session as `db`.

    ⚠️ A session on another engine than this process's own (a test's override) cannot be carried
    there, so that call runs here - as it does with `walk_processes: 0`."""
    target = (body.__module__, body.__name__)

    @functools.wraps(body)
    def pooled(*args, db=None, **kwargs):
        from database.database import engine

        bind = getattr(db, "get_bind", None)
        if args or size() == 0 or bind is None or bind() is not engine:
            return body(*args, db=db, **kwargs)
        return _reply(_run(target, kwargs))

    pooled.__pool_body__ = body
    return pooled


def recycle():
    """A reload empties this process's caches; a pool process holds its own copies. The idle ones end
    now, a running one after its answer."""
    with _cond:
        _generation[0] += 1
        for worker in _idle:
            _end(worker)
        _idle.clear()


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


def _run(target, kwargs):
    with _cond:
        while len(_running) >= max(size(), 1):
            _cond.wait()
        worker = None
        while _idle and worker is None:
            worker = _idle.pop()
            if not worker[0].is_alive():            # one that died while it waited is not handed a body
                _end(worker)
                worker = None
        if worker is None:
            worker = _start()
        _running.append(worker)
    keep = False
    try:
        process, connection, _generation_of = worker
        connection.send((target, kwargs))
        try:
            answer = connection.recv()
        except (EOFError, OSError):
            process.join(1)
            raise RuntimeError("the pool process running this request ended (exit code %s)"
                               % process.exitcode)
        keep = True
        return answer
    finally:
        with _cond:
            _running.remove(worker)
            if keep and worker[2] == _generation[0] and len(_idle) + len(_running) < size():
                _idle.append(worker)
            else:
                _end(worker)
            _cond.notify()


def _start():
    context = multiprocessing.get_context("spawn")
    mine, theirs = context.Pipe()
    process = context.Process(target=_serve, args=(theirs,), name=PROCESS_NAME, daemon=True)
    process.start()
    theirs.close()
    return [process, mine, _generation[0]]


def _end(worker):
    process, connection, _generation_of = worker
    connection.close()
    if process.is_alive():
        process.terminate()


def _serve(connection):
    """The pool process: one body at a time, until the server's end of the pipe closes."""
    os.environ.update(POOL_DB)
    from utils.logger import get_process_logger

    get_process_logger(PROCESS_NAME, "walk_pool.log")
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
    body = getattr(importlib.import_module(module), name).__pool_body__
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
