"""Contract board kill points - loaded in EVERY child process of the board (PYTHONPATH), active only when the env names a
point. It wraps product functions after their module loads (no product source is changed) and, the FIRST time the named
seam is reached, writes the flag file and ends the process with os._exit (no cleanup, no commit, no rollback - a crash).

BOARD_KILL_AT     the seam name (below)
BOARD_KILL_FLAG   a file; present = already killed, the seam passes from then on (the restarted process runs through)
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
    def __init__(self, module, attr, wrap, when, why):
        self.module, self.attr, self.wrap, self.when, self.why = module, attr, wrap, when, why

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
                setattr(module, patch.attr, patch.wrap(getattr(module, patch.attr), patch.when, patch.why))

        spec.loader = _Loader()
        return spec


if POINT:
    if POINT not in SEAMS:
        sys.stderr.write("[BoardKill] unknown seam %r - nothing armed\n" % POINT)
    else:
        mod, attr, wrap, when = SEAMS[POINT]
        sys.meta_path.insert(0, _Patch(mod, attr, wrap, when, POINT))
