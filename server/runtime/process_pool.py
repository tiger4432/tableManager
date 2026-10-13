"""A heavy route's body in a process of its own (lead b47388fde).

`in_pool(body)` registered as a route's endpoint is the seat - the ROUTE, not the name: code that calls the body itself
(`mappers/contrast_walk.py` calls `evidence_subgraph`) gets its answer as before. The pool process runs the body on
its own small database pool and hands back BYTES - so a big walk neither holds this process's GIL nor shares its cores
while other requests wait. The walk is the first user.
`ingestion_settings.json`, read once per request: `walk_processes` - how many may run at once (0: the body runs in
this process, as before); `walk_seconds_max` - how long a request waits for one and for its answer (then a 503).
Two pools, one mechanism (`Pool`): WALK above and GRID (총괄 e570dcda5 ㄴ) - the grid page's body, `grid_processes`
processes (default 2); `grid_wait_seconds` (default 60) bounds only the wait for a process - not the answer: a plain
grid read has no deadline (a search's statements have grid_read_timeout_seconds), and a body cut short ends its process.
An HTTPException raised there is raised here as the same one; anything else is this request's 500.
A pool process that dies fails only the request it was running; the next request starts another.
A body may keep something between requests (a paused walk, 총괄 54f7edfdb): its key begins with `here()`, and the next
request carrying it goes to that process alone (`in_pool(pinned_by=...)`) - or is told why it is gone.
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
import uuid
from collections import OrderedDict

from fastapi import HTTPException
from starlette.responses import Response

SETTING = "walk_processes"
DEFAULT = 2
WAIT_SETTING = "walk_seconds_max"
DEFAULT_WAIT = 120
#: How many paused walks a process keeps, and for how many idle minutes (총괄 54f7edfdb) - past the count the least
#: recently used goes first.
LIVE_SETTING, LIVE_DEFAULT = "walk_live_walks", 4
LIVE_MINUTES_SETTING, LIVE_MINUTES_DEFAULT = "walk_live_minutes", 10
#: How many nodes the walks one process keeps may hold together - a walk's open, read-whole and each seed's reached
#: nodes (총괄 10-13 · ea9142edd). 300,000 ~ 600 MB at 1.9 KB a counted node - the walk board's largest (one seed,
#: page 10: 20.7 MB with the key before over 10,973; 121 seeds page 25: 0.69 KB) - for the walks besides the newest
#: and those being walked, which stay whatever they hold (총괄 b47c7c8a3: 500 seeds, page 4 - 1,253,000 nodes,
#: 454.6 MB) - WALK.md «이어 걷기».
LIVE_NODES_SETTING, LIVE_NODES_DEFAULT = "walk_live_nodes", 300_000
#: Which server start a kept key was made under - set once in the server; every pool process it starts inherits it.
BOOT_ENV = "ASSY_WALK_BOOT"
os.environ.setdefault(BOOT_ENV, uuid.uuid4().hex[:12])
#: How many ended pool processes keep why they ended - what a key of theirs is told.
ENDED_SAID = 200
#: A pool process runs one body at a time: its session and nothing else (chain.slots.SLOT_POOL's size).
POOL_DB = {"ASSY_DB_POOL_SIZE": "2", "ASSY_DB_MAX_OVERFLOW": "2"}
#: Its logger - and so its connections' application name, `assy_walkpool`; its own lines go to walk_pool.log.
PROCESS_NAME = "WalkPool"

logger = logging.getLogger("Server")

#: The grid page's pool (총괄 e570dcda5 ㄴ): its own size cell, and a wait for a process only (lead, after 6f34a1320:
#: two processes stuck on plain reads, which have no statement limit, queued every grid request without end).
GRID_SETTING, GRID_DEFAULT = "grid_processes", 2
GRID_WAIT_SETTING, GRID_WAIT_DEFAULT = "grid_wait_seconds", 60


class Pool:
    """One kind of route body's processes: its size cell, its wait cell (None: no deadline) - and whether that wait
    covers the answer too (`answer_waits`) or only the wait for a process -, its process name and log file, its state."""

    def __init__(self, name, setting, default, wait_setting, wait_default, process_name, log_file, runs,
                 answer_waits=True):
        self.name, self.setting, self.default, self.runs = name, setting, default, runs
        self.wait_setting, self.wait_default, self.answer_waits = wait_setting, wait_default, answer_waits
        self.process_name, self.log_file = process_name, log_file
        self.idle = []                  # [process, connection, generation] ready for a body
        self.taken = [0]                # pool processes running a body, or being started
        self.modules = []               # the modules of the bodies in_pool wraps - imported before a process is ready
        self.prepares = []              # (module, function) a body's registration asks run before ready (in_pool prepare=)
        self.cond = threading.Condition()
        self.generation = [0]           # recycle() moves it; a process of an older one is not given a body again
        self.busy = set()               # the pids of the pool processes running a body
        self.ended = OrderedDict()      # pid -> why it ended (reloaded · process ended), the last ENDED_SAID


WALK = Pool("walk", SETTING, DEFAULT, WAIT_SETTING, DEFAULT_WAIT, PROCESS_NAME, "walk_pool.log", "walks")
GRID = Pool("grid", GRID_SETTING, GRID_DEFAULT, GRID_WAIT_SETTING, GRID_WAIT_DEFAULT, "GridPool", "grid_pool.log",
            "grid pages", answer_waits=False)
POOLS = (WALK, GRID)
_idle, _taken, _modules, _cond = WALK.idle, WALK.taken, WALK.modules, WALK.cond          # the walk's, by their names
_generation, _busy, _ended = WALK.generation, WALK.busy, WALK.ended
_said = set()                   # a wrong setting value is said once
_warmed = [False]               # warm() was called here - the server's start; a daemon running the same reload never


def _settings():
    from parsers.directory_watcher import load_ingestion_settings

    return load_ingestion_settings()


def size(settings=None, pool=None):
    """How many pool processes may run at once - 0: none, the body runs here. Only a whole number from 0 up is read;
    anything else is said once and reads as 0 (the switch that turns it off must not turn into the default)."""
    pool = WALK if pool is None else pool
    settings = _settings() if settings is None else settings
    if pool.setting not in settings:
        return pool.default
    value = settings[pool.setting]
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    _say_once(pool.setting, value, "0 - %s run in the server" % pool.runs)
    return 0


def wait_seconds(settings=None, pool=None):
    """How long a request waits for a pool process, and then for its answer when the pool's wait covers it - None: as
    long as it takes."""
    pool = WALK if pool is None else pool
    if pool.wait_setting is None:
        return None
    settings = _settings() if settings is None else settings
    if pool.wait_setting not in settings:
        return pool.wait_default
    value = settings[pool.wait_setting]
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        return value
    _say_once(pool.wait_setting, value, "%d s" % pool.wait_default)
    return pool.wait_default


def live_walks(settings=None):
    """How many paused walks one process keeps - a whole number from 1; anything else is said once and reads as the
    default."""
    settings = _settings() if settings is None else settings
    value = settings.get(LIVE_SETTING, LIVE_DEFAULT)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 1:
        return value
    _say_once(LIVE_SETTING, value, str(LIVE_DEFAULT))
    return LIVE_DEFAULT


def live_nodes(settings=None):
    """How many nodes the paused walks of one process may hold together - a whole number from 1."""
    settings = _settings() if settings is None else settings
    value = settings.get(LIVE_NODES_SETTING, LIVE_NODES_DEFAULT)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 1:
        return value
    _say_once(LIVE_NODES_SETTING, value, str(LIVE_NODES_DEFAULT))
    return LIVE_NODES_DEFAULT


def live_minutes(settings=None):
    """How long a paused walk is kept unused, in minutes."""
    settings = _settings() if settings is None else settings
    value = settings.get(LIVE_MINUTES_SETTING, LIVE_MINUTES_DEFAULT)
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        return value
    _say_once(LIVE_MINUTES_SETTING, value, "%d min" % LIVE_MINUTES_DEFAULT)
    return LIVE_MINUTES_DEFAULT


def here():
    """`<server start>.<pid>` - the process a key begun with it belongs to (`owner_of`)."""
    return "%s.%d" % (os.environ[BOOT_ENV], os.getpid())


def owner_of(key):
    """(server start, pid) of a key `here()` began - None for anything else."""
    parts = key.split(".") if isinstance(key, str) else []
    return (parts[0], int(parts[1])) if len(parts) >= 3 and parts[1].isdigit() else None


def _say_once(name, value, reading):
    if (name, repr(value)) not in _said:
        _said.add((name, repr(value)))
        logger.error("[Pool] ingestion_settings.json %s is %r - read as %s", name, value, reading)


def in_pool(body, pinned_by=None, gone=None, pool=None, prepare=None):
    """`body` as a route endpoint that runs it in a process of `pool` (WALK unless named), with that process's own
    session as `db`. `pinned_by(kwargs)`: the key of what a process keeps for this request, or None - the request goes to
    that process alone, and `gone(why)` (reloaded · restarted · process ended) is raised when it is no longer there.

    `prepare()`: what the body fills before its first request (총괄 8af4d378c - the walk's compiled declaration), run in
    each pool process before it says ready; it returns the sentence the process logs.

    ⚠️ A session on another engine than this process's own (a test's override) cannot be carried there, so that call
    runs here - as it does with the pool's size 0."""
    pool = WALK if pool is None else pool
    target = (body.__module__, body.__name__)
    if prepare is not None:
        pool.prepares.append((prepare.__module__, prepare.__name__))
    pool.modules.append(body.__module__)

    @functools.wraps(body)
    def pooled(*args, db=None, **kwargs):
        from database.database import engine

        settings = _settings()
        limit = size(settings, pool)
        if limit == 0:
            _drain(pool)
        owner = owner_of(pinned_by(kwargs)) if pinned_by is not None else None
        if owner is not None and owner[0] != os.environ[BOOT_ENV]:
            raise gone("restarted")
        bind = getattr(db, "get_bind", None)
        if (args or limit == 0 or bind is None or bind() is not engine
                or (owner is not None and owner[1] == os.getpid())):
            if owner is not None and owner[1] != os.getpid():
                raise gone(pool.ended.get(owner[1], "reloaded"))
            return body(*args, db=db, **kwargs)
        return _reply(_run(target, kwargs, limit, wait_seconds(settings, pool), owner and owner[1], gone, pool))

    pooled.__pool_body__ = body
    return pooled


def warm():
    """Start each pool's `size()` processes behind the server's start and after a reload (lead b47388fde), so the first
    body does not pay for one. A body that comes first starts its own, as before; a failure is one log line. Testing
    mode starts none."""
    _warmed[0] = True
    if os.getenv("TESTING") == "True":
        return
    for pool in POOLS:
        threading.Thread(target=_start_all, args=(pool,), name="%s-pool-warm" % pool.name, daemon=True).start()


def _start_all(pool):
    try:
        while True:
            with pool.cond:
                if len(pool.idle) + pool.taken[0] >= size(pool=pool):
                    return
                pool.taken[0] += 1
            worker = None
            try:
                worker = _start(wait_seconds(pool=pool), pool)
            finally:
                with pool.cond:
                    pool.taken[0] -= 1
                    _keep_or_end(worker, size(pool=pool), pool)
                    pool.cond.notify_all()              # a pinned request waits for its own process
    except Exception as exc:                                    # noqa: BLE001 - the server goes on all the same
        logger.error("[Pool] %s processes not started ahead - the first %s starts one: %s: %s",
                     pool.name, pool.name, type(exc).__name__, exc)


def recycle():
    """A reload empties this process's caches; a pool process holds its own copies. The idle ones end now, a running
    one after its answer - and new ones start behind it, and in its place when it ends. Every pool.
    🔴 Only in a process that warmed the pools (lead eb9c328e4): the watcher, chain worker and auto-update daemons run
    the same table-config reload, and a pool process started there runs the daemon's top level again as `__mp_main__`."""
    if not _warmed[0]:
        return
    for pool in POOLS:
        with pool.cond:
            pool.generation[0] += 1
            _drain_locked(pool)
    warm()


def _drain(pool=None):
    pool = WALK if pool is None else pool
    with pool.cond:
        _drain_locked(pool)


def _drain_locked(pool=None):
    pool = WALK if pool is None else pool
    for worker in pool.idle:
        _end(worker, "reloaded", pool)
    pool.idle.clear()


def _keep_or_end(worker, limit, pool=None):
    """Back to the idle ones when it is of this generation, alive and within `limit` - else ended. Under the pool's
    condition."""
    pool = WALK if pool is None else pool
    if worker is None:
        return
    if worker[2] == pool.generation[0] and worker[0].is_alive() and len(pool.idle) + pool.taken[0] < limit:
        pool.idle.append(worker)
    else:
        _end(worker, "reloaded" if worker[2] != pool.generation[0] else "process ended", pool)


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


def _run(target, kwargs, limit, seconds, pid=None, gone=None, pool=None):
    """🔴 ONE DEADLINE (lead 9a3c510c5): a slot, a start and the answer share `seconds` - not `seconds` each (None: no
    deadline); a pool whose wait does not cover the answer (the grid's) lifts it once its body is handed over. `pid`: the pool process that keeps what this request continues - only it answers; busy, it
    is waited for up to `seconds` of its own and the body then has `seconds` (총괄 9752e91f7: a wait for another's walk
    is not this walk being slow, and a body cut short ends the process and every walk it keeps); not there, `gone(why it
    ended)`."""
    pool = WALK if pool is None else pool
    deadline = None if seconds is None else time.monotonic() + seconds

    def left():
        return None if deadline is None else max(deadline - time.monotonic(), 0)

    with pool.cond:
        while True:
            worker = None
            if pid is not None:
                worker = next((each for each in pool.idle if each[0].pid == pid), None)
                if worker is not None and (worker[2] != pool.generation[0] or not worker[0].is_alive()):
                    pool.idle.remove(worker)
                    _end(worker, "reloaded" if worker[2] != pool.generation[0] else "process ended", pool)
                    worker = None
                if worker is None and pid not in pool.busy:
                    raise gone(pool.ended.get(pid, "process ended"))
                if worker is not None and pool.taken[0] < max(limit, 1):
                    pool.idle.remove(worker)
                    break
            elif pool.taken[0] < max(limit, 1):
                while pool.idle and worker is None:
                    worker = pool.idle.pop()
                    if worker[2] != pool.generation[0] or not worker[0].is_alive():   # older, or died while it waited
                        _end(worker, "reloaded" if worker[2] != pool.generation[0] else "process ended", pool)
                        worker = None
                break
            if left() == 0:
                raise _unavailable("%s_pool_busy" % pool.name, (
                    "The walk process keeping this walk stayed busy for %g s with another walk - ask More again" % seconds
                    if pid is not None else "Every %s process stayed busy for %g s - try again, or raise %s in "
                    "ingestion_settings.json" % (pool.name, seconds, pool.setting)))
            pool.cond.wait(left())
        if pid is not None and seconds is not None:
            deadline = time.monotonic() + seconds
        pool.taken[0] += 1
        if worker is not None:
            pool.busy.add(worker[0].pid)
    keep = False
    try:
        if worker is None:
            worker = _start(left(), pool)                   # outside the lock: another body takes an idle one
            with pool.cond:
                pool.busy.add(worker[0].pid)
        if not pool.answer_waits:
            deadline = None
        process, connection, _generation_of = worker
        connection.send((target, kwargs))
        if not connection.poll(left()):
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
        with pool.cond:
            pool.taken[0] -= 1
            if worker is not None:
                pool.busy.discard(worker[0].pid)
            older = worker is not None and worker[2] != pool.generation[0]
            if keep:
                _keep_or_end(worker, limit, pool)
            elif worker is not None:
                _end(worker, pool=pool)                 # a stuck or broken one does not take another body
            pool.cond.notify_all()                      # a pinned request waits for its own process
        if older:
            warm()                                      # a body a reload ran through: a new one takes its place (lead eb9c328e4)


def _start(seconds, pool=None):
    """A pool process that has imported its bodies' modules - so the first body it runs pays nothing for that.
    `seconds` None: as long as it takes."""
    pool = WALK if pool is None else pool
    generation = pool.generation[0]
    context = multiprocessing.get_context("spawn")
    mine, theirs = context.Pipe()
    process = context.Process(target=_serve, args=(theirs, list(dict.fromkeys(pool.modules)), pool.process_name,
                                                   pool.log_file, list(dict.fromkeys(pool.prepares))),
                              name=pool.process_name, daemon=True)
    process.start()
    theirs.close()
    try:
        if not mine.poll(seconds):
            _end([process, mine, generation], pool=pool)
            raise _unavailable("%s_process_not_ready" % pool.name, "A %s process did not start in %g s" % (pool.name, seconds))
        mine.recv()
    except (EOFError, OSError):
        process.join(1)
        raise RuntimeError("a pool process ended before it was ready (exit code %s)" % process.exitcode)
    return [process, mine, generation]


def _end(worker, why="process ended", pool=None):
    pool = WALK if pool is None else pool
    process, connection, _generation_of = worker
    if process.pid is not None:
        pool.ended[process.pid] = why
        pool.ended.move_to_end(process.pid)
        while len(pool.ended) > ENDED_SAID:
            pool.ended.popitem(last=False)
    connection.close()
    if process.is_alive():
        process.terminate()


def _serve(connection, modules, process_name=PROCESS_NAME, log_file="walk_pool.log", prepares=()):
    """The pool process: ready once its bodies' modules are imported and their prepares ran (one line each - a slow
    start says why), then one body at a time, until the server's end of the pipe closes. Its lines go to its pool's
    log file."""
    os.environ.update(POOL_DB)
    from utils.logger import get_process_logger

    get_process_logger(process_name, log_file)
    made = logging.getLogRecordFactory()

    def headed(*args, **kwargs):            # a line heads with its pool process, then its logger (lead, 10-13)
        record = made(*args, **kwargs)
        if not record.name.startswith(process_name):
            record.name = "%s.%s" % (process_name, record.name)
        return record

    logging.setLogRecordFactory(headed)
    for module in modules:
        importlib.import_module(module)
    import database.database                                    # noqa: F401 - its engine, before the first body
    for module, name in prepares:
        try:
            logger.info("[Pool] %s", getattr(importlib.import_module(module), name)())
        except Exception as exc:                                # noqa: BLE001 - the process serves all the same
            logger.error("[Pool] %s.%s did not prepare: %s: %s", module, name, type(exc).__name__, exc)
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
