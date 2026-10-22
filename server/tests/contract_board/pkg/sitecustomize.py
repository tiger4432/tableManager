"""Contract board kill points - loaded in EVERY child process of the board (PYTHONPATH), active only when the env names a
point. It wraps product functions after their module loads (no product source is changed) and, the FIRST time the named
seam is reached, writes the flag file and ends the process with os._exit (no cleanup, no commit, no rollback - a crash).

BOARD_KILL_AT     the seam name (below)
BOARD_KILL_FLAG   a file; present = already killed, the seam passes from then on (the restarted process runs through)
BOARD_READ_LOG    a file; when set, every SELECT naming a board table (bd_*) is one line there with the stage it ran in -
                  R inside `rule_run.run_rule`, W while `session_contract.hold_commit` holds, D otherwise - and each
                  `run_rule` call one ENTER line, each process's first statement one ATTACH line (the canaries)
"""
import importlib.abc
import importlib.machinery
import os
import sys
import time

POINT = os.environ.get("BOARD_KILL_AT")
FLAG = os.environ.get("BOARD_KILL_FLAG")


def _die(why):
    # armed only by the driver, right before the step under test (a seed must not die), and only once
    if not FLAG or os.path.exists(FLAG) or not os.path.exists(FLAG + ".arm"):
        return
    with open(FLAG, "w", encoding="utf-8") as f:
        f.write("%s pid=%d at=%s\n" % (why, os.getpid(), time.strftime("%H:%M:%S")))
    sys.stderr.write("[BoardKill] %s - process %d ends here\n" % (why, os.getpid()))
    sys.stderr.flush()
    os._exit(9)


def _caller_is(name, depth=2):
    f = sys._getframe(depth)
    while f is not None:
        if f.f_code.co_name == name:
            return True
        f = f.f_back
    return False


def _before(fn, when, why):
    def wrapped(*a, **k):
        if when(*a, **k):
            _die(why)
        return fn(*a, **k)
    wrapped.__wrapped__ = fn
    return wrapped


def _after(fn, when, why):
    def wrapped(*a, **k):
        out = fn(*a, **k)
        if when(*a, **k):
            _die(why)
        return out
    wrapped.__wrapped__ = fn
    return wrapped


# seam -> (module, attribute, wrap, condition)
SEAMS = {
    # the deleted source row: outbox marked SUCCESS and committed, its layers not yet taken back (census 3, «no»)
    "deleted_after_mark": ("chain.ingestion_worker", "_retract_deleted_rows", _before,
                           lambda db, deleted, *a, **k: any(deleted.values())),   # {table: ids} - a key with no ids is no deletion
    # layers withdrawn and committed, the EDIT for the rows that lost one not yet staged (census 3, «no»)
    "withdrawn_before_tell": ("database.database", "stage_collapsed_event", _before,
                              lambda *a, **k: _caller_is("_withdraw_and_tell", 3)),
    # R2: the withdrawal's pages committed, the shells not yet deleted (census 3, «no»)
    "r2_before_shells": ("chain.cell_layer", "delete_shells", _before,
                         lambda *a, **k: _caller_is("withdraw_source", 3)),
    # any write batch committed by the write door, the rest of the group not run (census 3, W) - «쓰기 사이»
    "after_write": ("database.crud", "_apply_batch_updates_once", _after,
                    lambda *a, **k: _caller_is("apply_chain_writes", 3)),     # the chain's writes, not a user's PUT
    # «껍데기 앞» whoever deletes shells (the chain's write, R2, fold_units)
    "before_shells": ("chain.cell_layer", "delete_shells", _before, lambda *a, **k: True),
    # «처리됨 앞» the group's writes done, its events not yet marked SUCCESS
    "before_mark": ("chain.ingestion_worker", "mark_processed", _before,
                    lambda event, status, *a, **k: status == "SUCCESS"),
    # «처리됨 뒤» the SUCCESS mark committed, the deleted rows' withdrawal not yet run - with or without deleted rows
    "after_mark": ("chain.ingestion_worker", "_retract_deleted_rows", _before, lambda *a, **k: True),
}


class _Patch(importlib.abc.MetaPathFinder):
    """`patches`: [(attr, wrap(fn) -> fn)] for one module - a module two hooks touch is patched by ONE finder (the first
    finder that answers a module is the only one asked)."""
    def __init__(self, module, patches):
        self.module, self.patches = module, patches

    def find_spec(self, name, path, target=None):
        if name != self.module:
            return None
        spec = importlib.machinery.PathFinder.find_spec(name, path)
        if spec is None or spec.loader is None:
            return spec
        loader, patch = spec.loader, self

        class _Loader(importlib.abc.Loader):
            def create_module(self, s):
                return loader.create_module(s)

            def exec_module(self, module):
                loader.exec_module(module)
                for attr, wrap in patch.patches:
                    setattr(module, attr, wrap(getattr(module, attr)))

        spec.loader = _Loader()
        return spec


# --- the read census (BOARD_READ_LOG) ---------------------------------------------------------------------------------
READ_LOG = os.environ.get("BOARD_READ_LOG")
_state = {"held": False, "attached": False}


def _line(text):
    with open(READ_LOG, "a", encoding="utf-8") as f:
        f.write("%s pid=%d %s\n" % (time.strftime("%H:%M:%S"), os.getpid(), text))


def _on_execute(conn, cursor, statement, parameters, context, executemany):
    try:
        if not _state["attached"]:
            _state["attached"] = True
            _line("ATTACH %s" % os.path.basename(sys.argv[0] if sys.argv and sys.argv[0] else "?"))
        if not statement.lstrip().lower().startswith(("select", "with")):
            return
        import re
        tables = sorted(set(re.findall(r"\b(bd_(?:src|val|dst|dec))\b", statement)))
        if not tables:
            return
        stage = "R" if _caller_is("run_rule", 1) else "W" if _state["held"] else "D"
        _line("READ %s %s %s" % (stage, ",".join(tables), " ".join(statement.split())[:140]))
    except Exception as e:                      # the census goes quiet alone, and says so - the statement still runs
        sys.stderr.write("[BoardRead] census line failed: %r\n" % (e,))


def _enter(fn):
    def wrapped(db, rule, *a, **k):
        _line("ENTER %s" % ((rule or {}).get("name") or "?"))
        return fn(db, rule, *a, **k)
    wrapped.__wrapped__ = fn
    return wrapped


def _hold(fn):
    def wrapped(db, *a, **k):
        opened = fn(db, *a, **k)
        if opened:
            _state["held"] = True
        return opened
    wrapped.__wrapped__ = fn
    return wrapped


def _let_go(fn):
    def wrapped(*a, **k):
        try:
            return fn(*a, **k)
        finally:
            _state["held"] = False
    wrapped.__wrapped__ = fn
    return wrapped


PATCHES = {}
if POINT:
    if POINT not in SEAMS:
        sys.stderr.write("[BoardKill] unknown seam %r - nothing armed\n" % POINT)
    else:
        _mod, _attr, _wrap, _when = SEAMS[POINT]
        PATCHES.setdefault(_mod, []).append((_attr, lambda fn: _wrap(fn, _when, POINT)))
if READ_LOG:
    import sqlalchemy.engine
    import sqlalchemy.event
    sqlalchemy.event.listen(sqlalchemy.engine.Engine, "before_cursor_execute", _on_execute)
    PATCHES.setdefault("chain.rule_run", []).append(("run_rule", _enter))
    PATCHES.setdefault("session_contract", []).extend([("hold_commit", _hold), ("release_hold", _let_go)])
    # a group that raised never reaches `release_hold` - the write seat's own end lets go too
    PATCHES.setdefault("chain.ingestion_worker", []).append(("apply_chain_writes", _let_go))
for _mod, _patches in PATCHES.items():
    sys.meta_path.insert(0, _Patch(_mod, _patches))
