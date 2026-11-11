# -*- coding: utf-8 -*-
"""The 11-14 gate of the cell-source overhaul, counted by property, not by word (lead 11-11): which functions of
server/ (tests left out) read or write cell_sources or audit_logs - naming their model (CellSource · AuditLog) or the
table in SQL (a string that names it after FROM · INTO · UPDATE · JOIN · TABLE · ON, or is the bare name) - which
modules do so at their top level («<module>»), and every function or module that CALLS one of those (the call graph
closed, B 11-11: a caller of a retired writer still writes). After the landing cell_sources is cold (copy and
rollback) and audit_logs is retired (owner 11-10), so outside the allow-list the answer is 0. The text of the product
is the subject here (an AST census), so reading files is the measurement, not a shortcut."""
import ast
import pathlib
import re

SERVER = pathlib.Path(__file__).resolve().parents[1]
DEFS = (ast.FunctionDef, ast.AsyncFunctionDef)

#: who may still name cell_sources after the landing: the copy (database/line_migration) and the rollback (B's
#: write_back, wherever it lands - by name). Their callers are not counted through them.
CELL_SOURCES_ALLOWED = {"database/line_migration.py:copy_page", "database/line_migration.py:copy_total",
                        "database/line_migration.py:copied_through", "*:write_back"}


def _server_files():
    for path in SERVER.rglob("*.py"):
        rel = path.relative_to(SERVER).as_posix()
        if not (rel.startswith("tests/") or "/tests/" in rel):
            yield rel, path.read_text(encoding="utf-8", errors="replace")


def _stem(rel):
    return rel.rsplit("/", 1)[-1][:-3]


def askers(names, table, files=None, allowed=()) -> set:
    """{"file:function"} of every function whose own body names one of `names` (a Name or an attribute) or `table`
    in SQL - a nested function counted as itself - and {"file:<module>"} of a module whose top-level statements do;
    then every function or module calling one of those, until nothing is added (a call reaches a def by its name in
    the same file, by `from <its module> import name`, or as `<its module or alias>.name`). A seat in `allowed`
    («file:function» or «*:function») is counted, its callers are not. Docstrings are words, not questions.
    `files`: [(relative path, source)] - server/ without its tests when None. THE census the questions ask."""
    sql = re.compile(r"(?i)\b(from|into|update|join|table|on)\s+[\"`]?" + re.escape(table) + r"\b")
    seats, calls, defs = {}, {}, {}                            # seat -> asks? · seat -> {(module or None, name)}
    for rel, source in (files if files is not None else _server_files()):
        tree = ast.parse(source)
        docs = {id(body[0].value) for node in ast.walk(tree)
                if isinstance(node, (ast.Module, ast.ClassDef, *DEFS)) and (body := node.body)
                and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)}
        alias, imported = {}, {}                               # alias -> module stem · name -> module stem
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    alias[a.asname or a.name.split(".")[0]] = a.name.rsplit(".", 1)[-1]
            elif isinstance(node, ast.ImportFrom):
                for a in node.names:
                    imported[a.asname or a.name] = (node.module or "").rsplit(".", 1)[-1]
                    alias[a.asname or a.name] = a.name

        def read(nodes, inside=()):
            asks, called = False, set()
            for top in nodes:
                for sub in ast.walk(top):
                    if id(sub) in inside or id(sub) in docs:
                        continue
                    if ((isinstance(sub, ast.Name) and sub.id in names)
                            or (isinstance(sub, ast.Attribute) and sub.attr in names)
                            or (isinstance(sub, ast.Constant) and isinstance(sub.value, str)
                                and (sub.value.strip() == table or sql.search(sub.value)))):
                        asks = True
                    if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                        called.add((imported.get(sub.func.id, _stem(rel)), sub.func.id))
                    elif (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                          and isinstance(sub.func.value, ast.Name)):
                        called.add((alias.get(sub.func.value.id, sub.func.value.id), sub.func.attr))
            return asks, called

        for node in ast.walk(tree):
            if isinstance(node, DEFS):
                nested = {id(x) for sub in ast.walk(node) if sub is not node and isinstance(sub, DEFS)
                          for x in ast.walk(sub)}
                seat = f"{rel}:{node.name}"
                seats[seat], calls[seat] = read([node], nested)
                defs.setdefault((_stem(rel), node.name), set()).add(seat)
        seat = f"{rel}:<module>"
        seats[seat], calls[seat] = read([s for s in tree.body if not isinstance(s, (ast.ClassDef, *DEFS))])
    found = {s for s, asks in seats.items() if asks}
    while True:
        reach = {s for s in found if s not in allowed and "*:" + s.split(":", 1)[1] not in allowed}
        more = {caller for caller, called in calls.items() if caller not in found
                and any(defs.get(c, set()) & reach for c in called)}
        if not more:
            return found
        found |= more


def _outside(found, allowed) -> list:
    return sorted(f for f in found if f not in allowed and "*:" + f.split(":", 1)[1] not in allowed)


def test_the_census_counts_sql_and_callers_not_words():
    files = [("probe.py", '"""reads cell_sources - a word"""\nrows = conn.execute("SELECT * FROM cell_sources")\n'),
             ("quiet.py", '"""cell_sources, only spoken of"""\ndef f():\n    """cell_sources here too"""\n'
                          '    print("carried per cell by cell_sources")\n    return 1\n'),
             ("w.py", "def write():\n    return db.query(CellSource)\n"),
             ("caller.py", "import w\nfrom w import write\ndef by_module():\n    return w.write()\n"
                           "def by_name():\n    return write()\ndef other():\n    return x.write()\n")]
    assert askers({"CellSource"}, "cell_sources", files) == {
        "probe.py:<module>", "w.py:write", "caller.py:by_module", "caller.py:by_name"}
    assert askers({"CellSource"}, "cell_sources", files, allowed={"w.py:write"}) == {"probe.py:<module>",
                                                                                     "w.py:write"}


def test_cell_sources_is_asked_only_by_the_copy_and_the_rollback():
    found = askers({"CellSource", "CellSourceModel"}, "cell_sources", allowed=CELL_SOURCES_ALLOWED)
    assert "database/line_migration.py:copy_page" in found, "canary: the census must see the copy"
    assert _outside(found, CELL_SOURCES_ALLOWED) == []


def test_audit_logs_is_asked_by_no_function():
    assert "database/write_lines.py:_audit" in askers({"AuditBatch"}, "audit_batches"), \
        "canary: the same census must see the audit row's one writer"
    assert _outside(askers({"AuditLog"}, "audit_logs"), set()) == []


def test_cell_layer_reads_no_cell_sources():
    found = askers({"CellSource", "CellSourceModel"}, "cell_sources", allowed=CELL_SOURCES_ALLOWED)
    assert "database/line_migration.py:copy_page" in found, "canary: the census must see the copy"
    assert sorted(f for f in found if f.startswith("chain/cell_layer.py:")) == []
