"""The keys the product reads off ONE table's entry of table_config - counted by AST, not by words (총괄 f3639d4a2).

Two kinds of value are followed through one function's own statements (a nested def is its own scope), and from a
caller into a callee by parameter, until nothing new:
  DOC    the whole document - `TABLE_CONFIG` (any module), a loader call (`LOADERS`), a call handed
         `table_config_path()` (or a name bound from it), a name bound from a DOC, a parameter handed a DOC
  ENTRY  one table's - `DOC[...]`, `DOC.get(...)`, `for _, X in DOC.items()`, `for X in DOC.values()`, a value stored
         into `DOC[...]`, a name bound from an ENTRY (`e`, `e or {}`, `dict(e)`, `a if c else b`), a parameter handed one
A key is READ when an ENTRY is `.get("k")`'d, `.setdefault`/`.pop`'d, `["k"]`'d or tested `"k" in`; a module-level
`NAME = "k"` is read as its text.
⚠️ BLIND: a key spelled at run time (an f-string, a joined name, a key taken from a variable that is not a module
constant) is not counted - a cell read only that way would be missing from the census and from the list it guards.
"""
import ast
import os
import subprocess

LOADERS = ("load_global_table_config", "load_table_config", "load_table_config_or_raise", "_load_table_config",
           "read_table_config")
DOC, ENTRY, PATH = "doc", "entry", "path"


def _own_nodes(scope):
    stack = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            stack.extend(ast.iter_child_nodes(node))


def _strip(node):
    while True:
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
            node = node.values[0]
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "dict" \
                and len(node.args) == 1:
            node = node.args[0]
        else:
            return node


def _called(node):
    f = node.func
    return f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""


def _path(node, taint):
    if isinstance(node, ast.Call):
        return _called(node) == "table_config_path"
    return isinstance(node, ast.Name) and taint.get(node.id) == PATH


def _kind(node, taint):
    node = _strip(node)
    if isinstance(node, ast.IfExp):
        return _kind(node.body, taint) or _kind(node.orelse, taint)
    if isinstance(node, ast.Name):
        return DOC if node.id == "TABLE_CONFIG" else taint.get(node.id) if taint.get(node.id) != PATH else None
    if isinstance(node, ast.Attribute) and node.attr == "TABLE_CONFIG":
        return DOC
    if isinstance(node, ast.Call):
        if _called(node) in LOADERS or any(_path(a, taint) for a in node.args):
            return DOC
        if _called(node) == "get" and isinstance(node.func, ast.Attribute) and _kind(node.func.value, taint) == DOC:
            return ENTRY
    if isinstance(node, ast.Subscript) and _kind(node.value, taint) == DOC:
        return ENTRY
    return None


def _unwrap(node):
    while isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("sorted", "list") \
            and node.args:
        node = node.args[0]
    return node


def product_files(server_dir):
    """The tracked product python files - not the tests, not the archive."""
    listed = subprocess.run(["git", "-C", server_dir, "ls-files", "*.py"], capture_output=True, text=True,
                            check=True).stdout.splitlines()
    return [f for f in listed if not f.startswith(("tests/", "scripts/archive/")) and "/tests/" not in f]


def keys_read(server_dir, files=None):
    """{key: {"file:function", ...}} over `files` (default: `product_files`)."""
    files = product_files(server_dir) if files is None else files
    trees = {}
    for f in files:
        try:
            trees[f] = ast.parse(open(os.path.join(server_dir, f), encoding="utf-8").read())
        except SyntaxError:
            continue
    texts = {}
    for tree in trees.values():
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) \
                    and isinstance(node.value.value, str):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        texts.setdefault(target.id, set()).add(node.value.value)
    constants = {name: next(iter(spelled)) for name, spelled in texts.items() if len(spelled) == 1}

    def literal(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        name = node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else None
        return constants.get(name) if name else None

    scopes, defs = [], {}
    for f, tree in trees.items():
        scopes.append((f, tree, "<module>"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                scopes.append((f, node, node.name))
                defs.setdefault(node.name, []).append(node)
    seeds, reads = {}, {}

    def scan(f, scope, name):
        taint = dict(seeds.get(id(scope), {}))
        nodes = list(_own_nodes(scope))
        changed = True
        while changed:
            changed = False
            for node in nodes:
                if isinstance(node, ast.Assign):
                    k = PATH if _path(node.value, taint) else _kind(node.value, taint)
                    for t in node.targets:
                        if k and isinstance(t, ast.Name) and taint.get(t.id) != k:
                            taint[t.id] = k
                            changed = True
                        if isinstance(t, ast.Subscript) and _kind(t.value, taint) == DOC \
                                and isinstance(node.value, ast.Name) and taint.get(node.value.id) != ENTRY:
                            taint[node.value.id] = ENTRY
                            changed = True
                if isinstance(node, (ast.For, ast.comprehension)):
                    it = _unwrap(node.iter)
                    if isinstance(it, ast.Call) and isinstance(it.func, ast.Attribute) \
                            and it.func.attr in ("items", "values") and _kind(it.func.value, taint) == DOC:
                        t = node.target
                        x = (t.elts[1] if it.func.attr == "items" and isinstance(t, ast.Tuple) and len(t.elts) == 2
                             else t if it.func.attr == "values" else None)
                        if isinstance(x, ast.Name) and taint.get(x.id) != ENTRY:
                            taint[x.id] = ENTRY
                            changed = True
        handed = []
        for node in nodes:
            key = None
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr in ("get", "setdefault", "pop") and node.args \
                    and _kind(node.func.value, taint) == ENTRY:
                key = literal(node.args[0])
            elif isinstance(node, ast.Subscript) and _kind(node.value, taint) == ENTRY:
                key = literal(node.slice)
            elif isinstance(node, ast.Compare) and len(node.ops) == 1 \
                    and isinstance(node.ops[0], (ast.In, ast.NotIn)) and _kind(node.comparators[0], taint) == ENTRY:
                key = literal(node.left)
            if key:
                reads.setdefault(key, set()).add("%s:%s" % (f, name))
            if isinstance(node, ast.Call) and _called(node):
                handed += [(_called(node), i, _kind(a, taint)) for i, a in enumerate(node.args) if _kind(a, taint)]
                handed += [(_called(node), kw.arg, _kind(kw.value, taint)) for kw in node.keywords
                           if kw.arg and _kind(kw.value, taint)]
        return handed

    by_id = {id(scope): (f, scope, name) for f, scope, name in scopes}
    dirty = list(by_id)                                     # the first round scans every scope, then the reseeded
    for _round in range(10):
        new, reseeded = 0, set()
        for f, scope, name in (by_id[i] for i in dirty):
            for fname, slot, k in scan(f, scope, name):
                for fn in defs.get(fname, ()):
                    params = [a.arg for a in fn.args.args]
                    if params and params[0] in ("self", "cls") and isinstance(slot, int):
                        slot += 1
                    p = params[slot] if isinstance(slot, int) and slot < len(params) else slot
                    if isinstance(p, str) and (p in params or p in [a.arg for a in fn.args.kwonlyargs]):
                        held = seeds.setdefault(id(fn), {})
                        if held.get(p) != k:
                            held[p] = k
                            new += 1
                            reseeded.add(id(fn))
        if not new:
            break
        dirty = sorted(reseeded)
    return reads
