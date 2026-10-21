"""AST census of seats: for each name, its defs and its call sites in server/ (tests excluded unless --tests).

    python door_census.py <tree> name1 name2 ...
    python door_census.py <tree> --callers name      (prints each call site: file:line in function)

A call site is an ast.Call whose func is Name(name) or Attribute(attr=name). A reference that is not a call
(passed as a value, e.g. key=fn) is counted apart as «ref». Canary: the def count of each name is printed with it -
a 0 def means the name is spelled wrong or lives outside the tree, and its call count says nothing.
"""
import ast
import os
import sys

tree_root = sys.argv[1]
args = sys.argv[2:]
with_tests = "--tests" in args
args = [a for a in args if a != "--tests"]
callers_mode = args and args[0] == "--callers"
names = args[1:] if callers_mode else args

files = []
for base, dirs, fs in os.walk(os.path.join(tree_root, "server")):
    dirs[:] = [d for d in dirs if d not in ("__pycache__", "node_modules", ".git")
               and (with_tests or d != "tests")]
    for f in fs:
        if f.endswith(".py"):
            files.append(os.path.join(base, f))
assert len(files) > 100, len(files)

defs = {n: [] for n in names}
calls = {n: [] for n in names}
refs = {n: [] for n in names}
parse_fail = []


class V(ast.NodeVisitor):
    def __init__(self, rel):
        self.rel = rel
        self.stack = []

    def _fn(self, node):
        if node.name in defs:
            defs[node.name].append(f"{self.rel}:{node.lineno}")
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = _fn
    visit_AsyncFunctionDef = _fn

    def visit_ClassDef(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_Call(self, node):
        f = node.func
        name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
        if name in calls:
            calls[name].append(f"{self.rel}:{node.lineno} in {'.'.join(self.stack) or '<module>'}")
            node._counted = True
        self.generic_visit(node)

    def visit_Name(self, node):
        if node.id in refs and isinstance(node.ctx, ast.Load):
            refs[node.id].append((self.rel, node.lineno, node.col_offset))

    def visit_Attribute(self, node):
        if node.attr in refs and isinstance(node.ctx, ast.Load):
            refs[node.attr].append((self.rel, node.lineno, node.col_offset))
        self.generic_visit(node)


for path in files:
    rel = os.path.relpath(path, tree_root).replace("\\", "/")
    try:
        src = open(path, encoding="utf-8").read()
        mod = ast.parse(src)
    except Exception as e:  # noqa: BLE001
        parse_fail.append(f"{rel}: {e}")
        continue
    V(rel).visit(mod)

print(f"# files parsed {len(files) - len(parse_fail)} / {len(files)} (tests {'in' if with_tests else 'out'})")
for p in parse_fail:
    print("# PARSE FAIL", p)
for n in names:
    call_lines = {(c.split(" in ")[0]) for c in calls[n]}
    plain_refs = [r for r in refs[n] if f"{r[0]}:{r[1]}" not in call_lines]
    if callers_mode:
        print(f"{n}: def {len(defs[n])} {defs[n]}")
        for c in calls[n]:
            print("   ", c)
        for r in plain_refs:
            print("    ref", f"{r[0]}:{r[1]}")
    else:
        print(f"{n}\tdef {len(defs[n])}\tcalls {len(calls[n])}\tref {len(plain_refs)}\t{' '.join(defs[n])}")
