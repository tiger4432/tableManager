# -*- coding: utf-8 -*-
"""Every broad catch that keeps something of the error keeps where it broke (총괄 10-20, 소유자 「이게 다 에러를 접어서
띄워서 모르잖아」): `error_said.told(e)` in the line, or the traceback (exc_info · logger.exception · traceback.*), or the
error raised on. Counted by AST over the tracked server code, the census that found 404 seats keeping one line.
KEPT names, per file, the ones that keep the type or a helper's sentence on purpose."""
import ast
import os
import subprocess

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FULL = {"exception", "format_exc", "print_exc", "format_exception", "extract_tb", "print_exception", "format_tb"}
KEPT = {
    "server/admin/sso.py": 2,                       # the sign-in refusal shows the browser the type alone
    "server/chain/enrichment/config.py": 1,         # _reference_view_failure logs the traceback itself
    "server/ledger/config_explorer_service.py": 1,  # a structured refusal (code · path · message) for the form
    "server/ledger/worker.py": 1,                   # held and raised again below
    "server/utils/llm.py": 1,                       # _why says every cause in the chain
    "server/scripts/dev_env/devenv.py": 1,          # standalone scripts without server/ on the path at import
    "server/scripts/diagnose_socket.py": 7,
    "server/scripts/ledger_deploy_preflight.py": 1,
}


def _keeps_one_line(handler):
    caught = handler.type
    names = ([caught] if caught is not None and not isinstance(caught, ast.Tuple) else
             list(caught.elts) if caught is not None else [])
    broad = caught is None or any(getattr(n, "id", getattr(n, "attr", None)) in ("Exception", "BaseException")
                                  for n in names)
    if not broad or not handler.name:
        return False
    body = ast.Module(body=handler.body, type_ignores=[])
    used = {n.id for n in ast.walk(body) if isinstance(n, ast.Name)}
    if handler.name not in used:
        return False
    for node in ast.walk(body):
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
    handlers, found = 0, {}
    for rel in files:
        tree = ast.parse(open(os.path.join(REPO, rel), encoding="utf-8").read(), filename=rel)
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                handlers += 1
                if _keeps_one_line(node):
                    found[rel] = found.get(rel, 0) + 1
    assert handlers > 1000, "canary: the census reads the server's except clauses - %d" % handlers
    assert found == KEPT, {rel: (found.get(rel, 0), KEPT.get(rel, 0)) for rel in set(found) | set(KEPT)
                           if found.get(rel, 0) != KEPT.get(rel, 0)}
