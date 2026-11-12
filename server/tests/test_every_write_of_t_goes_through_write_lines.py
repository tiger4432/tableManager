"""Every product seat that writes a declared table t or its line table goes through write_lines, or is lines' own
build / copy (lead 11-11 ㄴ: the funnel's «one caller» claim, said again for the lines - write_lines has several
callers by design, so the claim is now «nothing writes t beside it»).

A seat is the innermost def (server/-relative «file:qualname»), tests left out. A write target is FIXED when the code
names it: an ORM class whose `__tablename__` is a constant, `<that class>.__table__`, a module-level
Table("<constant>"), an import alias, a module function returning one, or a local name bound to one. Any other target
is the dynamic one - t (DYNAMIC_TABLES[...], a model handed in) or t__lines. A write is: insert/update/delete(<target>)
(Core); db.query(<target>)...update()/delete(); db.add/add_all/merge/delete of a t row; bulk_insert_mappings /
bulk_update_mappings(<target>); setattr(<t row>, <a column named at run time>, ...) or `<row>.business_key_val = ...`;
a SQL text (a constant or an f-string) that writes a table named by a placeholder whose value is not a fixed table's
name. Not seen: SQL joined with `+`, and SQL a raw cursor runs that was built elsewhere. An ORM edit of a row handed in
is flushed by database.py's `write_changed_rows_by_shape` through `crud.update_by_arrays` - counted there.
"""
import ast
import re
from pathlib import Path

SERVER = Path(__file__).resolve().parent.parent
DEFS = (ast.FunctionDef, ast.AsyncFunctionDef)
SQL_WRITE = re.compile(r'\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+"?(%s|\{[^}]*\}|%\([a-z_]+\)s)"?(\s|\(|$)', re.I)
CORE = {"insert", "update", "delete"}
SESSION_WRITES = {"add", "add_all", "merge", "delete"}
BULK = {"bulk_insert_mappings", "bulk_update_mappings"}
SESSIONS = {"db", "session", "db_session", "sess", "pg_db"}
MODEL_NAMES = {"model", "table_model", "model_cls", "row_model", "target_model", "trg_model", "src_model", "Model"}
ROW_MARKS = {"row_id", "business_key_val"}

#: lines' own seats - the write door and the tables' build / copy
ALLOWED_MODULES = ("database/write_lines.py:", "database/lines.py:", "database/line_migration.py:")
#: seats that write t outside write_lines, each with its reason and what closes it
KNOWN = {
    "chain/replay.py:full_reset": "allowed - the declared full reset (lead 11-11 ㄴ)",
    "scripts/dev_env/snapshot_db.py:copy_rows": "allowed - dev restore",
    "database/crud.py:update_by_arrays": "pending lead - the before_flush hook's write (11-14 gate item)",
}
#: seats the census sees that write a table that is not t
NOT_T = {
    "database/crud.py:_pg_multirow_upsert": "cell_overwrites only (its table is handed in)",
    "ledger/store.py:LedgerStore.": "the ledger's own tables",
    "migrations/add_ledger_source_events.py:_backfill_partition": "ledger_source_events",
    "migrations/add_outbox_ledger_state.py:apply": "database_outbox",
    "scripts/archive/migrate_updated_at.py:migrate": "the retired DataRow model",
}
CANARY = {"database/write_lines.py:" + name
          for name in ("_claim", "_heads", "_merge_into", "_merge_now", "_put_keys", "write_lines")} | {
    "database/lines.py:insert_lines"}                    # _lines sends its lines through it (lead 11-12)


def _server_files():
    for path in SERVER.rglob("*.py"):
        rel = path.relative_to(SERVER).as_posix()
        if not (rel.startswith("tests/") or "/tests/" in rel):
            yield rel, path.read_text(encoding="utf-8", errors="replace")


def _fixed_names(trees):
    out = set()
    for tree in trees:
        for n in tree.body:
            if isinstance(n, ast.ClassDef):
                for s in n.body:
                    if isinstance(s, ast.Assign) and any(isinstance(t, ast.Name) and t.id in ("__tablename__", "__table__")
                                                         for t in s.targets):
                        v = s.value
                        if isinstance(v, ast.Constant) and isinstance(v.value, str) or isinstance(v, ast.Call) \
                                and v.args and isinstance(v.args[0], ast.Constant):
                            out.add(n.name)
            elif isinstance(n, ast.Assign) and isinstance(n.value, ast.Call) \
                    and getattr(n.value.func, "id", getattr(n.value.func, "attr", "")) == "Table" \
                    and n.value.args and isinstance(n.value.args[0], ast.Constant):
                out |= {t.id for t in n.targets if isinstance(t, ast.Name)}
    return out


def _root(e):
    while isinstance(e, (ast.Attribute, ast.Subscript, ast.Call)):
        e = e.func if isinstance(e, ast.Call) else e.value
    return e


class _Seat:
    def __init__(self, fixed):
        self.fixed = set(fixed)
        self.local = set()
        self.rows = set()
        self.marked = set()

    def is_fixed(self, e):
        if isinstance(e, ast.Name):
            return e.id in self.fixed or e.id in self.local
        if isinstance(e, ast.Call) and isinstance(e.func, ast.Name) and not e.args:
            return e.func.id in self.fixed                         # a module function returning a fixed model
        if isinstance(e, ast.Attribute):
            if e.attr in ("__table__", "name", "__tablename__"):
                return self.is_fixed(e.value)
            return e.attr in self.fixed                            # models.CellSource
        return False

    def _made_row(self, e):
        return isinstance(e, ast.Call) and (isinstance(e.func, ast.Subscript) or isinstance(e.func, ast.Name)
                                            and e.func.id in MODEL_NAMES and not self.is_fixed(e.func))

    def _dyn_query(self, e):
        while isinstance(e, ast.Call) and isinstance(e.func, ast.Attribute):
            if e.func.attr == "query":
                return bool(e.args) and not any(self.is_fixed(_root(a)) or self.is_fixed(a) for a in e.args)
            e = e.func.value
        return False

    def learn(self, nodes):
        for n in nodes:
            if isinstance(n, ast.ImportFrom):
                self.local |= {a.asname for a in n.names if a.asname and a.name in self.fixed}
            elif isinstance(n, ast.Attribute) and n.attr in ROW_MARKS and isinstance(n.value, ast.Name):
                self.marked.add(n.value.id)
        for _ in range(3):
            for n in nodes:
                if isinstance(n, ast.Assign):
                    for tgt in n.targets:
                        pairs = zip(tgt.elts, n.value.elts) if isinstance(tgt, ast.Tuple) \
                            and isinstance(n.value, ast.Tuple) and len(tgt.elts) == len(n.value.elts) else [(tgt, n.value)]
                        self.local |= {t.id for t, v in pairs if isinstance(t, ast.Name) and self.is_fixed(v)}
                    if self._made_row(n.value) or self._dyn_query(n.value):
                        self.rows |= {x.id for t in n.targets for x in ast.walk(t) if isinstance(x, ast.Name)}
                elif isinstance(n, (ast.For, ast.comprehension)) and self._dyn_query(n.iter):
                    self.rows |= {x.id for x in ast.walk(n.target) if isinstance(x, ast.Name)}

    def _sql_fixed(self, const, nodes):
        for n in nodes:
            if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mod) and n.left is const:
                first = n.right.elts[0] if isinstance(n.right, ast.Tuple) and n.right.elts else n.right
                return self.is_fixed(first)
        return False

    def writes(self, nodes):
        hits = []
        for n in nodes:
            if isinstance(n, ast.Call):
                f = n.func
                name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
                core = name in CORE and (isinstance(f, ast.Name) or isinstance(f, ast.Attribute)
                                         and isinstance(f.value, ast.Name) and f.value.id in ("sa", "sqlalchemy"))
                if core and n.args and not self.is_fixed(n.args[0]) and not isinstance(n.args[0], ast.Constant):
                    hits.append("core %s" % name)
                elif name in ("update", "delete") and isinstance(f, ast.Attribute) and isinstance(f.value, ast.Call) \
                        and self._dyn_query(f.value):
                    hits.append("query.%s" % name)
                elif name in SESSION_WRITES and isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) \
                        and f.value.id in SESSIONS and n.args:
                    a = n.args[0]
                    items = a.elts if isinstance(a, (ast.List, ast.Tuple)) else [a]
                    if any(self._made_row(x) or isinstance(x, ast.Name) and x.id in self.rows for x in items):
                        hits.append("session.%s" % name)
                elif name in BULK and isinstance(f, ast.Attribute) and n.args and not self.is_fixed(n.args[0]):
                    hits.append("session.%s" % name)
                elif name == "setattr" and isinstance(f, ast.Name) and len(n.args) >= 2 and isinstance(n.args[0], ast.Name) \
                        and not isinstance(n.args[1], ast.Constant) and n.args[0].id in self.rows | self.marked:
                    hits.append("setattr")
            elif isinstance(n, (ast.Assign, ast.AugAssign)):
                for tgt in (n.targets if isinstance(n, ast.Assign) else [n.target]):
                    if isinstance(tgt, ast.Attribute) and isinstance(tgt.value, ast.Name) and (
                            tgt.value.id in self.rows or tgt.attr == "business_key_val"
                            and "item" not in tgt.value.id and tgt.value.id != "self"):
                        hits.append("row.%s =" % tgt.attr)
            elif isinstance(n, ast.Constant) and isinstance(n.value, str) and SQL_WRITE.search(n.value) \
                    and not self._sql_fixed(n, nodes):
                hits.append("sql")
            elif isinstance(n, ast.JoinedStr):
                spelled = "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in n.values)
                if SQL_WRITE.search(spelled):
                    hits.append("f-sql")
        return hits


def writers(files) -> dict:
    """{seat: [what it does]} of every seat of `files` ((rel, source) pairs) that writes a table the code does not name."""
    parsed = [(rel, ast.parse(source)) for rel, source in files]
    fixed = _fixed_names([tree for _rel, tree in parsed])
    found = {}
    for rel, tree in parsed:
        names = fixed | {a.asname for n in tree.body if isinstance(n, ast.ImportFrom) for a in n.names
                         if a.asname and a.name in fixed}
        for fn in tree.body:
            if isinstance(fn, DEFS):
                probe = _Seat(names)
                probe.learn(list(ast.walk(fn)))
                returns = [r.value for r in ast.walk(fn) if isinstance(r, ast.Return) and r.value is not None]
                if returns and all(probe.is_fixed(r) for r in returns):
                    names = names | {fn.name}

        def visit(node, qual):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.ClassDef,) + DEFS):
                    q = (qual + "." if qual else "") + child.name
                    if isinstance(child, DEFS):
                        nested = {id(x) for sub in ast.walk(child) if sub is not child and isinstance(sub, DEFS)
                                  for x in ast.walk(sub)}
                        own = [x for x in ast.walk(child) if id(x) not in nested]
                        seat = _Seat(names)
                        seat.learn(own)
                        hits = seat.writes(own)
                        if hits:
                            found["%s:%s" % (rel, q)] = sorted(set(hits))
                    visit(child, q)
        visit(tree, "")
    return found


def test_the_census_sees_a_write_of_t_by_every_shape_and_not_a_named_table():
    files = [("database/models.py", "class CellOverwrite(Base):\n    __tablename__ = 'cell_overwrites'\n"),
             ("w.py", "from database import models\n"
                      "def made_then_added(db, t):\n    model = models.DYNAMIC_TABLES[t]\n"
                      "    row = model(row_id='r1')\n    db.add(row)\n"
                      "def edited_in_a_loop(db, model, column):\n"
                      "    for row in db.query(model).filter(model.row_id == 'r1'):\n        setattr(row, column, 1)\n"
                      "def core_on_a_handed_table(db, now):\n    db.execute(update(now).values(a=1))\n"
                      "def raw_update(db, table_name):\n    db.execute('UPDATE \"%s\" SET a = 1' % table_name)\n"
                      "def a_named_row(db):\n    row = models.CellOverwrite(table_name='t')\n    db.add(row)\n"
                      "def a_named_table(db):\n    ov = models.CellOverwrite.__table__\n    db.execute(delete(ov))\n"
                      "def a_named_tables_sql(db):\n    t = models.CellOverwrite.__table__\n"
                      "    db.execute('DELETE FROM \"%s\"' % t.name)\n")]
    assert set(writers(files)) == {"w.py:made_then_added", "w.py:edited_in_a_loop", "w.py:core_on_a_handed_table",
                                   "w.py:raw_update"}


def _known(seat, table):
    return seat in table or any(key.endswith(".") and seat.startswith(key) for key in table)


def test_nothing_beside_write_lines_writes_t():
    found = writers(_server_files())
    assert CANARY <= set(found), ("canary: the census must see write_lines' own writes", sorted(CANARY - set(found)))
    outside = sorted(s for s in found if not s.startswith(ALLOWED_MODULES) and not _known(s, KNOWN)
                     and not _known(s, NOT_T))
    assert outside == [], [(s, found[s]) for s in outside]
    assert sorted(s for s in KNOWN if s not in found) == [], "an exception closed - take its line out of KNOWN"
