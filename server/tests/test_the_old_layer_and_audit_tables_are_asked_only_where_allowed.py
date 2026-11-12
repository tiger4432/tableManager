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
CELL_SOURCES_ALLOWED = {# 까닭: 운영 복사 전 - the copy retires the round after it has run in operation (lead 11-11)
                        "database/line_migration.py:copy_page", "database/line_migration.py:copy_total",
                        "database/line_migration.py:copied_through", "database/line_migration.py:_copyable",
                        # the migration command that drives the copy - same reason (lead 11-12)
                        "scripts/copy_layers_to_lines.py:<module>", "scripts/copy_layers_to_lines.py:_one",
                        "scripts/copy_layers_to_lines.py:copy_table", "scripts/copy_layers_to_lines.py:main",
                        "scripts/copy_layers_to_lines.py:plan",
                        "*:write_back",
                        # snapshot check - cold table compare, lead 11-11 (lines count compare after the bundle)
                        "scripts/snapshot.py:_facts", "scripts/restore.py:counts", "scripts/restore.py:main"}


def _server_files():
    for path in SERVER.rglob("*.py"):
        rel = path.relative_to(SERVER).as_posix()
        if not (rel.startswith("tests/") or "/tests/" in rel):
            yield rel, path.read_text(encoding="utf-8", errors="replace")


def _module(rel):
    """(dotted module of a server/-relative file, its package) - server/ is the import root."""
    parts = rel[:-3].split("/")
    if parts[-1] == "__init__":
        return ".".join(parts[:-1]), parts[:-1]
    return ".".join(parts), parts[:-1]


#: audit_logs keeps the events that are not a cell - ledger receipts, set_aside, reset (owner 11-11 ㄱ): its writers
#: and the history screen's two routes. A cell line written there still counts (`cell_line_to_audit`).
AUDIT_EVENTS_ALLOWED = {"database/crud.py:create_audit_log", "database/crud.py:bulk_insert_audit_logs",
                        "ledger/store.py:_insert_audit_row", "main.py:get_recent_audit_logs",
                        "main.py:get_transaction_logs",
                        # replay._write_resolved — 칸 사건이 audit_logs 에 남는 마지막 자리. 소유자 «전 → 후» 물음과 A 의
                        # _merges_again 착지 대기 (B, lead 11-11 ㄱ: R3 writes no line, only t's shown value)
                        "chain/replay.py:_write_resolved"}
#: who hands rows to the event writers (bulk_insert_audit_logs · _insert_audit_row): each builds them with
#: crud.receipt_log - RECEIPT_COLUMN lines, whose create_audit_log call `cell_line_to_audit` reads - and
#: store.write_batch writes what its `receipt` callable returns, which only execute_scoped_batch passes
#: (runtime_v2._batch_receipt). A new hand of rows is a seat to read before it joins (lead 11-11)
EVENT_ROW_SEATS = {"database/crud.py:_apply_batch_updates_once", "ledger/followup.py:_write_failure_receipt",
                   "ledger/store.py:write_batch"}
#: the column words an event line is written under - not a cell's column
EVENT_COLUMNS = {"*", "RECEIPT_COLUMN"}


def cell_line_to_audit(call) -> bool:
    """A create_audit_log call whose column (4th argument or column_name=) is not an event's word - a cell line."""
    f = call.func
    if (f.id if isinstance(f, ast.Name) else getattr(f, "attr", None)) != "create_audit_log":
        return False
    col = call.args[3] if len(call.args) > 3 else next((k.value for k in call.keywords if k.arg == "column_name"),
                                                       None)
    word = (col.value if isinstance(col, ast.Constant) else col.id if isinstance(col, ast.Name)
            else col.attr if isinstance(col, ast.Attribute) else None)
    return word not in EVENT_COLUMNS


#: a str method compares or cuts a name - a table name passed to one is not asking the table
STR_METHODS = {"startswith", "endswith", "split", "rsplit", "replace", "find", "rfind", "index", "count", "strip",
               "lstrip", "rstrip", "join", "format", "partition", "rpartition", "removeprefix", "removesuffix"}


def _callee(call):
    f = call.func
    return f.id if isinstance(f, ast.Name) else getattr(f, "attr", None)


def _dotted(node):
    """`a.b.c` of an expression made of names and attributes, else None."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute) and (head := _dotted(node.value)):
        return f"{head}.{node.attr}"
    return None


def askers(names, table, files=None, allowed=(), via=None, asks_call=None) -> set:
    """{"file:function"} of every function whose own body names one of `names` (a Name or an attribute) or `table`
    in SQL - a nested function counted as itself - and {"file:<module>"} of a module whose top-level statements do;
    then every function or module calling one of those, until nothing is added. A call reaches a def by its full
    dotted module (server/ the root, relative imports resolved): its name in the same module, `from <module> import
    name`, or `<alias of module>.name`. A seat in `allowed` («file:function» or «*:function») is counted, its callers
    are not. Docstrings are words, not questions. `files`: [(relative path, source)] - server/ without its tests when
    None. `via`: filled with {caller: a callee it was counted through}. `asks_call(call)`: a call that asks too
    (`cell_line_to_audit`). THE census the questions ask."""
    sql = re.compile(r"(?i)\b(from|into|update|join|table|on|analyze|vacuum|truncate)\s+[\"`]?" + re.escape(table) + r"\b")
    seats, calls, defs, uses, consts = {}, {}, {}, {}, set()    # seat -> asks? · seat -> {(module, name)}
    for rel, source in (files if files is not None else _server_files()):
        tree = ast.parse(source)
        docs = {id(body[0].value) for node in ast.walk(tree)
                if isinstance(node, (ast.Module, ast.ClassDef, *DEFS)) and (body := node.body)
                and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)}
        own, package = _module(rel)
        alias, imported = {}, {}                               # alias -> dotted module · name -> dotted module
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    full = a.name.removeprefix("server.")
                    alias[a.asname or full.split(".")[0]] = full if a.asname else full.split(".")[0]
            elif isinstance(node, ast.ImportFrom):
                base = (node.module or "").removeprefix("server.")
                if node.level:
                    up = package[:len(package) - (node.level - 1)] if node.level > 1 else package
                    base = ".".join([*up, *([base] if base else [])])
                for a in node.names:
                    imported[a.asname or a.name] = base
                    alias[a.asname or a.name] = f"{base}.{a.name}" if base else a.name

        # a module-level constant holding the table's name (a string, or items of one) - its users ask (lead 11-11 ㄱ)
        for stmt in tree.body:
            targets = (stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
                       if isinstance(stmt, ast.AnnAssign) and stmt.value is not None else [])
            if targets and any(isinstance(v, ast.Constant) and isinstance(v.value, str)
                               and (v.value.strip() == table or sql.search(v.value)) for v in ast.walk(stmt.value)):
                consts.update((own, t.id) for t in targets if isinstance(t, ast.Name))

        def read(nodes, inside=()):
            asks, called, refs = False, set(), set()
            for top in nodes:
                for sub in ast.walk(top):
                    if id(sub) in inside or id(sub) in docs:
                        continue
                    if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
                        refs.add((imported.get(sub.id, own), sub.id))
                    elif isinstance(sub, ast.Attribute) and (path := _dotted(sub.value)):
                        head, _, rest = path.partition(".")
                        if head in alias:
                            refs.add((".".join([alias[head], *([rest] if rest else [])]), sub.attr))
                    if ((isinstance(sub, ast.Name) and sub.id in names)
                            or (isinstance(sub, ast.Attribute) and sub.attr in names)
                            or (isinstance(sub, ast.Constant) and isinstance(sub.value, str)
                                and sql.search(sub.value))):
                        asks = True
                    # the bare name where a table name is held: an argument (not of a str method) or an item of a
                    # tuple · list · set · dict - a name list a DDL loop walks is asking too
                    held = ([*sub.elts] if isinstance(sub, (ast.Tuple, ast.List, ast.Set)) else
                            [*sub.keys, *sub.values] if isinstance(sub, ast.Dict) else
                            [*sub.args, *(k.value for k in sub.keywords)]
                            if isinstance(sub, ast.Call) and _callee(sub) not in STR_METHODS else [])
                    asks = asks or any(isinstance(a, ast.Constant) and isinstance(a.value, str)
                                       and a.value.strip() == table for a in held)
                    if not isinstance(sub, ast.Call):
                        continue
                    asks = asks or bool(asks_call and asks_call(sub))
                    if isinstance(sub.func, ast.Name):
                        called.add((imported.get(sub.func.id, own), sub.func.id))
                    elif isinstance(sub.func, ast.Attribute) and (path := _dotted(sub.func.value)):
                        head, _, rest = path.partition(".")
                        if head in alias:
                            called.add((".".join([alias[head], *([rest] if rest else [])]), sub.func.attr))
            return asks, called, refs

        for node in ast.walk(tree):
            if isinstance(node, DEFS):
                nested = {id(x) for sub in ast.walk(node) if sub is not node and isinstance(sub, DEFS)
                          for x in ast.walk(sub)}
                seat = f"{rel}:{node.name}"
                seats[seat], calls[seat], uses[seat] = read([node], nested)
                defs.setdefault((own, node.name), set()).add(seat)
        seat = f"{rel}:<module>"
        bodies = {id(x) for node in ast.walk(tree) if isinstance(node, (ast.ClassDef, *DEFS)) for x in ast.walk(node)}
        seats[seat], calls[seat], uses[seat] = read(tree.body, bodies)            # a def under a top-level if/try is its own
    found = {s for s, asks in seats.items() if asks or uses[s] & consts}
    while True:
        reach = {s for s in found if s not in allowed and "*:" + s.split(":", 1)[1] not in allowed}
        more = {}
        for caller, called in calls.items():
            hit = caller not in found and next((t for c in called for t in defs.get(c, ()) if t in reach), None)
            if hit:
                more[caller] = hit
        if not more:
            return found
        if via is not None:
            via.update(more)
        found |= set(more)


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
    # two modules of one stem: only a/util asks - b/util's callers are not caught (a stem would join them)
    same = [("a/util.py", "def f():\n    return db.query(CellSource)\n"), ("b/util.py", "def f():\n    return 1\n"),
            ("c/one.py", "from a import util\ndef g():\n    return util.f()\n"),
            ("c/two.py", "from ..b import util\ndef h():\n    return util.f()\n"),
            ("b/three.py", "from .util import f\ndef k():\n    return f()\n")]
    assert askers({"CellSource"}, "cell_sources", same) == {"a/util.py:f", "c/one.py:g"}
    # the bare name counts where a table name is taken (an argument), not where a str method compares it; a def
    # under a top-level if is its own seat, not the module's
    named = [("s.py", 'def static(n):\n    return n.startswith("cell_sources")\n'
                      'def probe():\n    return insp.has_table("cell_sources")\n'
                      'if X:\n    def inner():\n        return db.query(CellSource)\n'),
             ("t.py", 'TABLES = ("cell_sources", "cell_overwrites")\ndef tune():\n    run("ANALYZE cell_sources")\n')]
    assert askers({"CellSource"}, "cell_sources", named) == {"s.py:probe", "s.py:inner", "t.py:<module>",
                                                             "t.py:tune"}
    # a module constant holding the name: every function using it asks, here or through an import
    held = [("k/m.py", 'OLD = "cell_sources"\nOTHER = "lines"\ndef reads():\n    return insp.has_table(OLD)\n'
                       'def quiet():\n    return OTHER\n'),
            ("k/n.py", "from k import m\nfrom k.m import OLD\ndef a():\n    return m.OLD\ndef b():\n    return OLD\n")]
    assert askers({"CellSource"}, "cell_sources", held) == {"k/m.py:reads", "k/n.py:a", "k/n.py:b"}


def test_cell_sources_is_asked_only_by_the_copy_and_the_rollback():
    found = askers({"CellSource", "CellSourceModel"}, "cell_sources", allowed=CELL_SOURCES_ALLOWED)
    assert "database/line_migration.py:copy_page" in found, "canary: the census must see the copy"
    assert _outside(found, CELL_SOURCES_ALLOWED) == []


def test_a_dotted_call_and_a_cell_line_to_audit_are_counted():
    files = [("a/b.py", "def f():\n    return db.query(CellSource)\n"),
             ("c.py", "import a.b\ndef g():\n    return a.b.f()\n")]
    assert askers({"CellSource"}, "cell_sources", files) == {"a/b.py:f", "c.py:g"}
    events = [("e.py", "def reset():\n    crud.create_audit_log(db, t, '*', '*', 1, 0, S, by)\n"
                       "def receipt():\n    create_audit_log(db, t, b, RECEIPT_COLUMN, None, v, s, w)\n"
                       "def cell():\n    crud.create_audit_log(db, t, r, col, 1, 2, s, w)\n"
                       "def named():\n    crud.create_audit_log(db, t, r, column_name='lot')\n")]
    assert askers({"AuditLog"}, "audit_logs", events, asks_call=cell_line_to_audit) == {"e.py:cell", "e.py:named"}


def test_audit_logs_keeps_only_the_events_that_are_not_a_cell():
    assert "database/write_lines.py:_audit" in askers({"AuditBatch"}, "audit_batches"), \
        "canary: the same census must see the audit row's one writer"
    found = askers({"AuditLog"}, "audit_logs", allowed=AUDIT_EVENTS_ALLOWED, asks_call=cell_line_to_audit)
    assert "chain/replay.py:full_reset" not in found, "a reset event is allowed"
    assert _outside(found, AUDIT_EVENTS_ALLOWED) == []


def _seats_calling(names) -> dict:
    """{"file:function": the def} of every function of server/ (tests left out) with a call to one of `names` in
    its own body (a nested def is its own seat)."""
    out = {}
    for rel, source in _server_files():
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, DEFS):
                nested = {id(x) for sub in ast.walk(node) if sub is not node and isinstance(sub, DEFS)
                          for x in ast.walk(sub)}
                if any(isinstance(c, ast.Call) and _callee(c) in names and id(c) not in nested
                       for c in ast.walk(node)):
                    out[f"{rel}:{node.name}"] = node
    return out


def test_the_event_writers_take_rows_only_from_the_receipt():
    """audit_logs keeps the events that are not a cell (owner 11-11 ㄱ): no hand gives its writers a cell line."""
    writers = _seats_calling({"bulk_insert_audit_logs", "_insert_audit_row"})
    assert writers.keys() == EVENT_ROW_SEATS, sorted(writers)
    builders = _seats_calling({"receipt_log"})
    assert "ledger/runtime_v2.py:build" in builders, "canary: the census must see the batch receipt's builder"
    assert {s for s in EVENT_ROW_SEATS if s in builders} == EVENT_ROW_SEATS - {"ledger/store.py:write_batch"}
    passers = {seat for seat, node in _seats_calling({"write_batch"}).items()
               if any(isinstance(c, ast.Call) and _callee(c) == "write_batch"
                      and any(k.arg == "receipt" for k in c.keywords) for c in ast.walk(node))}
    assert passers == {"ledger/runtime_v2.py:execute_scoped_batch"}, sorted(passers)


def test_cell_layer_reads_no_cell_sources():
    found = askers({"CellSource", "CellSourceModel"}, "cell_sources", allowed=CELL_SOURCES_ALLOWED)
    assert "database/line_migration.py:copy_page" in found, "canary: the census must see the copy"
    assert sorted(f for f in found if f.startswith("chain/cell_layer.py:")) == []
