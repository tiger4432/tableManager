# -*- coding: utf-8 -*-
"""booted() (lead 11-12): a process's boot is done - one collect, then gc.freeze, so the full collections a write
triggers stop walking what the boot built. Every long-lived entry point calls it where its boot ends - read from the
entry points' own source (AST), the list named here; the retroactive runner has two (a claimed run and a slice)."""
import ast
import gc
import os

SERVER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTRANCES = [("main.py", "startup_event"), ("chain/ingestion_worker.py", "start_chain_ingestion_worker"),
             ("ledger/worker.py", "start_ledger_worker"), ("run_watcher.py", "main"), ("run_auto_update.py", "main"),
             ("chain/slots.py", "_serve"), ("runtime/process_pool.py", "_serve"),
             ("admin/retroactive_run.py", "main"), ("admin/retroactive_run.py", "_slice")]


def test_booted_freezes_what_the_process_holds():
    from utils.logger import booted

    try:
        booted()
        assert gc.get_freeze_count() > 0
    finally:
        gc.unfreeze()                              # the test process goes on collecting as it did


def _calls_booted(path, name):
    tree = ast.parse(open(os.path.join(SERVER, path), encoding="utf-8").read())
    found = [node for node in ast.walk(tree)
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]
    return found, any(isinstance(call, ast.Call) and getattr(call.func, "id", getattr(call.func, "attr", None)) == "booted"
                      for node in found for call in ast.walk(node))


def test_every_entry_point_calls_booted_where_its_boot_ends():
    seen = {(path, name): _calls_booted(path, name) for path, name in ENTRANCES}
    assert sum(1 for found, _calls in seen.values() if found) == len(ENTRANCES) == 9, "CANARY: every entrance found"
    assert [entrance for entrance, (_found, calls) in seen.items() if not calls] == []
