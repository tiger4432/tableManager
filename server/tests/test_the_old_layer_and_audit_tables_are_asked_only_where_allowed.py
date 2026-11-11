# -*- coding: utf-8 -*-
"""The 11-14 gate of the cell-source overhaul, counted by property, not by word (lead 11-11): which functions of
server/ (tests left out) read or write cell_sources or audit_logs - naming their model (CellSource · AuditLog) or the
table's name in a string - and which modules do so at their top level («<module>»: a script's or a migration's
statements outside any function). After the landing cell_sources is cold (copy and rollback read it) and audit_logs
is retired (owner 11-10), so outside the allow-list the answer is 0, and chain/cell_layer reads no cell_sources.
The text of the product is the subject here (an AST census), so reading files is the measurement, not a shortcut."""
import ast
import pathlib

SERVER = pathlib.Path(__file__).resolve().parents[1]
DEFS = (ast.FunctionDef, ast.AsyncFunctionDef)

#: who may still name cell_sources after the landing: the copy (database/line_migration) and the rollback (B's
#: write_back, wherever it lands - by name). The models are classes, not functions, so they are not counted.
CELL_SOURCES_ALLOWED = {"database/line_migration.py:copy_page", "database/line_migration.py:copy_total",
                        "database/line_migration.py:copied_through", "*:write_back"}


def _server_files():
    for path in SERVER.rglob("*.py"):
        rel = path.relative_to(SERVER).as_posix()
        if not (rel.startswith("tests/") or "/tests/" in rel):
            yield rel, path.read_text(encoding="utf-8", errors="replace")


def askers(names, table, files=None) -> set:
    """{"file:function"} of every function whose own body names one of `names` (a Name or an attribute) or holds
    `table` in a string - a nested function counted as itself, not as its parent - and {"file:<module>"} of a module
    whose top-level statements (outside every def and class) do. Docstrings are words, not questions: left out.
    `files`: [(relative path, source)] - server/ without its tests when None. THE census the questions ask."""
    found = set()
    for rel, source in (files if files is not None else _server_files()):
        tree = ast.parse(source)
        docs = {id(body[0].value) for node in ast.walk(tree)
                if isinstance(node, (ast.Module, ast.ClassDef, *DEFS)) and (body := node.body)
                and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)}

        def asks(nodes, inside=()):
            for top in nodes:
                for sub in ast.walk(top):
                    if id(sub) in inside or id(sub) in docs:
                        continue
                    if ((isinstance(sub, ast.Name) and sub.id in names)
                            or (isinstance(sub, ast.Attribute) and sub.attr in names)
                            or (isinstance(sub, ast.Constant) and isinstance(sub.value, str) and table in sub.value)):
                        return True
            return False

        for node in ast.walk(tree):
            if isinstance(node, DEFS):
                nested = {id(x) for sub in ast.walk(node) if sub is not node and isinstance(sub, DEFS)
                          for x in ast.walk(sub)}
                if asks([node], nested):
                    found.add(f"{rel}:{node.name}")
        if asks([s for s in tree.body if not isinstance(s, (ast.ClassDef, *DEFS))]):
            found.add(f"{rel}:<module>")
    return found


def _outside(found, allowed) -> list:
    return sorted(f for f in found if f not in allowed and "*:" + f.split(":", 1)[1] not in allowed)


def test_the_census_sees_a_top_level_question_and_leaves_docstrings_out():
    files = [("probe.py", '"""reads cell_sources - a word"""\nrows = conn.execute("SELECT * FROM cell_sources")\n'),
             ("quiet.py", '"""cell_sources, only spoken of"""\ndef f():\n    """cell_sources here too"""\n    return 1\n')]
    assert askers({"CellSource"}, "cell_sources", files) == {"probe.py:<module>"}


def test_cell_sources_is_asked_only_by_the_copy_and_the_rollback():
    found = askers({"CellSource", "CellSourceModel"}, "cell_sources")
    assert "database/line_migration.py:copy_page" in found, "canary: the census must see the copy"
    assert _outside(found, CELL_SOURCES_ALLOWED) == []


def test_audit_logs_is_asked_by_no_function():
    assert "database/write_lines.py:_audit" in askers({"AuditBatch"}, "audit_batches"), \
        "canary: the same census must see the audit row's one writer"
    assert _outside(askers({"AuditLog"}, "audit_logs"), set()) == []


def test_cell_layer_reads_no_cell_sources():
    found = askers({"CellSource", "CellSourceModel"}, "cell_sources")
    assert "database/line_migration.py:copy_page" in found, "canary: the census must see the copy"
    assert sorted(f for f in found if f.startswith("chain/cell_layer.py:")) == []
