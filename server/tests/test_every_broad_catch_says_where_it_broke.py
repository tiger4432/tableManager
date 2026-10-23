# -*- coding: utf-8 -*-
"""Every broad catch that keeps something of the error keeps where it broke (총괄 10-20, 소유자 「이게 다 에러를 접어서
띄워서 모르잖아」): `error_said.told(e)` in the line, or the traceback (exc_info · logger.exception · traceback.*), or the
error raised on. Counted by AST over the tracked server code, the census that found 404 seats keeping one line.
KEPT names, per file, the ones that keep the type or a helper's sentence on purpose. A broad catch that leaves
nothing says its failure in one warning (총괄 c60fabe71, 소유자 「오류 남기게 해 너무 일 키우지는 말고」) unless
QUIET_KEPT names it, per file, by why: cleanup after a failure already said · probe whose «no» is an answer · parse
of a value · import with a fallback · elsewhere (raised, counted, printed) · hot (a row or a tick) · logging (the
logger itself) · stream (a script's stdout setup)."""
import ast
import os
import subprocess

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FULL = {"exception", "format_exc", "print_exc", "format_exception", "extract_tb", "print_exception", "format_tb"}
KEPT = {
    "server/admin/sso.py": 2,                       # the sign-in refusal shows the browser the type alone
    "server/chain/enrichment/config.py": 1,         # _reference_view_failure logs the traceback itself
    "server/chain/rule_run.py": 1,                  # prepare keeps a read's error; run_rule raises it, traceback whole
    "server/ledger/config_explorer_service.py": 1,  # a structured refusal (code · path · message) for the form
    "server/utils/llm.py": 1,                       # _why says every cause in the chain
    "server/scripts/dev_env/devenv.py": 1,          # standalone scripts without server/ on the path at import
    "server/scripts/diagnose_socket.py": 7,
    "server/scripts/ledger_deploy_preflight.py": 1,
}
QUIET_KEPT = {
    "server/admin/audit_cache.py": {"hot": 1},
    "server/admin/auth.py": {"probe": 3},
    "server/admin/dev_bench.py": {"cleanup": 1, "import": 2, "parse": 1},
    "server/admin/retroactive.py": {"cleanup": 2, "parse": 1, "probe": 1},
    "server/admin/retype.py": {"probe": 1},          # family(): a table not made yet has no column to convert
    "server/admin/schema_drift.py": {"import": 2, "probe": 4, "elsewhere": 1},
    "server/bonding_plan.py": {"parse": 1, "probe": 1, "elsewhere": 1},
    "server/chain/activity.py": {"hot": 2},
    "server/chain/enrichment/config.py": {"probe": 3, "elsewhere": 1},
    "server/chain/join_key_index.py": {"probe": 2},
    "server/chain/slots.py": {"probe": 1, "elsewhere": 1},
    "server/chain/unique_key.py": {"cleanup": 4},
    "server/collector_markers.py": {"elsewhere": 1},
    "server/database/crud.py": {"probe": 1},
    "server/database/database.py": {"hot": 4, "probe": 1},
    "server/db_safety.py": {"parse": 1},
    "server/event_constants.py": {"probe": 1},
    "server/internal_event_client.py": {"cleanup": 2, "parse": 2, "probe": 1},
    "server/ledger/backfill.py": {"elsewhere": 1},
    "server/ledger/config.py": {"import": 1},
    "server/ledger/config_authoring.py": {"elsewhere": 1},
    "server/ledger/config_explorer_service.py": {"elsewhere": 1},
    "server/ledger/observability.py": {"hot": 3},
    "server/ledger/roleframe.py": {"parse": 1},
    "server/ledger/trace.py": {"import": 1},
    "server/main.py": {"cleanup": 3, "import": 4, "parse": 2, "elsewhere": 3},
    "server/map_alignment.py": {"import": 1, "logging": 2, "parse": 1, "probe": 4, "elsewhere": 1},
    "server/map_overlay.py": {"cleanup": 1, "parse": 2},
    "server/mapper_sdk.py": {"import": 1, "probe": 1},
    "server/outbox_listener.py": {"cleanup": 1},
    "server/parsers/advanced_ingester.py": {"parse": 1},
    "server/parsers/directory_watcher.py": {"cleanup": 1, "hot": 1, "import": 3, "parse": 1, "probe": 3},
    "server/run_watcher.py": {"import": 2},
    "server/runtime/process_supervisor.py": {"cleanup": 2, "logging": 4, "parse": 1, "probe": 5, "elsewhere": 1},
    "server/runtime/running.py": {"probe": 1},
    "server/scripts/check_one_row_one_fact.py": {"stream": 1},
    "server/scripts/count_absent_null_layers.py": {"stream": 1},
    "server/scripts/dev_env/devenv.py": {"probe": 1},
    "server/scripts/diagnose_db_health.py": {"cleanup": 2, "probe": 1},
    "server/scripts/diagnose_slow_after_ingest.py": {"cleanup": 1, "probe": 1, "elsewhere": 2, "stream": 1},
    "server/scripts/diagnose_wal_headroom.py": {"cleanup": 1, "elsewhere": 1, "stream": 1},
    "server/scripts/install_product_tables.py": {"stream": 1},
    "server/scripts/list_undeclared_tables.py": {"elsewhere": 1, "stream": 1},
    "server/scripts/load_mechanism_edge_rows.py": {"import": 1},
    "server/scripts/measure_ledger_followup_lag.py": {"probe": 1},
    "server/scripts/migrate_decide_aggregations.py": {"stream": 1},
    "server/scripts/preview_unified_declarations.py": {"stream": 1},
    "server/scripts/probe_ingestion_stages.py": {"probe": 1},
    "server/scripts/seed_syn_valid_die_floors.py": {"import": 1, "parse": 1},
    "server/scripts/support/finding_kinds.py": {"import": 1},
    "server/transfer_plan.py": {"parse": 4},
    "server/utils/heartbeat.py": {"probe": 7, "elsewhere": 1},
    "server/utils/logger.py": {"cleanup": 1, "logging": 1},
    "server/utils/payload_helper.py": {"parse": 1},
    "server/utils/time_format.py": {"elsewhere": 1},
    "server/value_suggest.py": {"cleanup": 3, "hot": 2},
}


def _own(node):
    """ast.walk that does not go into a nested except clause - what that one says is its own."""
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        stack.extend(c for c in ast.iter_child_nodes(n) if not isinstance(c, ast.ExceptHandler))


def _broad(handler):
    caught = handler.type
    names = ([caught] if caught is not None and not isinstance(caught, ast.Tuple) else
             list(caught.elts) if caught is not None else [])
    return caught is None or any(getattr(n, "id", getattr(n, "attr", None)) in ("Exception", "BaseException")
                                 for n in names)


def _leaves_nothing(handler):
    """Broad, the error named nowhere in it, no traceback, nothing raised."""
    if not _broad(handler):
        return False
    body = ast.Module(body=handler.body, type_ignores=[])
    if handler.name and handler.name in {n.id for n in _own(body) if isinstance(n, ast.Name)}:
        return False
    for node in _own(body):
        if isinstance(node, ast.Raise) and node.exc is None:
            return False
        if isinstance(node, ast.Call) and (any(k.arg in ("exc_info", "stack_info") for k in node.keywords) or
                                           isinstance(node.func, ast.Attribute) and node.func.attr in FULL):
            return False
    return True


def _keeps_one_line(handler):
    if not _broad(handler) or not handler.name:
        return False
    body = ast.Module(body=handler.body, type_ignores=[])
    used = {n.id for n in _own(body) if isinstance(n, ast.Name)}
    if handler.name not in used:
        return False
    for node in _own(body):
        if isinstance(node, ast.Raise) and (node.exc is None or handler.name in {
                n.id for n in ast.walk(node) if isinstance(n, ast.Name)}):
            return False
        if isinstance(node, ast.Call):
            if any(k.arg in ("exc_info", "stack_info") for k in node.keywords):
                return False
            if isinstance(node.func, ast.Attribute) and node.func.attr in FULL | {"told", "where"}:
                return False
            if isinstance(node.func, ast.Name) and node.func.id in ("told", "where"):
                return False
    return True


def test_every_broad_catch_keeps_where_it_broke():
    files = subprocess.run(["git", "-C", REPO, "ls-files", "server/*.py"], capture_output=True, text=True,
                           check=True).stdout.split()
    files = [f for f in files if not f.startswith("server/tests/")]
    handlers, found, quiet = 0, {}, {}
    for rel in files:
        tree = ast.parse(open(os.path.join(REPO, rel), encoding="utf-8").read(), filename=rel)
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                handlers += 1
                if _keeps_one_line(node):
                    found[rel] = found.get(rel, 0) + 1
                if _leaves_nothing(node):
                    quiet[rel] = quiet.get(rel, 0) + 1
    assert handlers > 1000, "canary: the census reads the server's except clauses - %d" % handlers
    assert found == KEPT, {rel: (found.get(rel, 0), KEPT.get(rel, 0)) for rel in set(found) | set(KEPT)
                           if found.get(rel, 0) != KEPT.get(rel, 0)}
    kept = {rel: sum(why.values()) for rel, why in QUIET_KEPT.items()}
    assert quiet == kept, {rel: (quiet.get(rel, 0), kept.get(rel, 0)) for rel in set(quiet) | set(kept)
                           if quiet.get(rel, 0) != kept.get(rel, 0)}
