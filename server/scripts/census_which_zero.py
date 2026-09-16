# -*- coding: utf-8 -*-
"""S-284 census. An instrument: it owns nothing, decides nothing, prints.

🔴 TWO POPULATIONS, BECAUSE THE RULING SAYS THE AXES ARE TWO (S-284 ③):
  A. `absence` - a field that CAN BE 0 and does not say which 0 it is.
  B. `unread`  - a failure swallowed into an empty value that then BECOMES A NUMBER.
                 That is not a 0; it is "no number", and today it is indistinguishable.

⚰️ THE FIRST TWO VERSIONS OF THIS INSTRUMENT WERE WRONG, IN THE SAME DIRECTION BOTH TIMES.
   ㉠ counting only `len(...)` written inside the dict literal: 18, a third of the real A.
   ㉡ walking only ROUTE functions: B came out 0 - while the ruling names `chain/graph.py`
      as a B case. It is a helper, not a route. A number reaching the client does not care
      which function wrote it, so the walk is over every function and the population is
      "numbers that leave the server".
   Both times the too-small answer looked finished. That is why the counts are printed with
   what they exclude.
"""
import ast, io, os, subprocess, sys

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")

#: 🔴 TRACKED FILES ONLY. The first run walked the filesystem and swept
#: `server/mappers/*.py`, which are the OWNER's gitignored files - counting those would have
#: put this box's private files into a number about the product. `git ls-files` makes the
#: exclusion structural instead of a list I have to remember.
TRACKED = set()
for line in subprocess.check_output(
        ["git", "ls-files", "*.py"], cwd=ROOT).decode("utf-8").splitlines():
    TRACKED.add(os.path.normpath(line))
COUNT_FUNCS = {"len", "sum"}
COUNT_METHODS = {"count", "scalar"}
ABSENCE_KEYS = {"absence", "unread"}


def route_decorated(node):
    """Whether this function is itself an HTTP route - the fields it writes are seen."""
    for d in getattr(node, "decorator_list", []):
        f = d.func if isinstance(d, ast.Call) else d
        while isinstance(f, ast.Attribute):
            if f.attr in ("get", "post", "put", "delete", "patch"):
                return True
            f = f.value
    return False
SKIP = (".git", "__pycache__", "tests", ".tmp", "node_modules", "scripts", "migrations")


def count_shaped(v):
    if isinstance(v, ast.Call):
        fn = v.func
        if isinstance(fn, ast.Name) and fn.id in COUNT_FUNCS:
            return "%s()" % fn.id
        if isinstance(fn, ast.Attribute) and fn.attr in COUNT_METHODS:
            return ".%s()" % fn.attr
    return None


def counted_name(v):
    """The single name a count-shaped call measures, if it measures one."""
    if isinstance(v, ast.Call) and v.args and isinstance(v.args[0], ast.Name):
        return v.args[0].id
    if isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute) \
            and isinstance(v.func.value, ast.Name):
        return v.func.value.id
    return None


def key_name(k):
    return k.value if isinstance(k, ast.Constant) and isinstance(k.value, str) else None


def is_empty_literal(v):
    if isinstance(v, (ast.List, ast.Tuple, ast.Set)) and not v.elts:
        return True
    if isinstance(v, ast.Dict) and not v.keys:
        return True
    if isinstance(v, ast.Constant) and v.value in (0, None):
        return True
    return False


a_rows, b_rows = [], []
for base, _d, files in os.walk(ROOT):
    if any(p in base.replace("\\", "/").split("/") for p in SKIP):
        continue
    for f in files:
        if not f.endswith(".py"):
            continue
        path = os.path.join(base, f)
        rel = os.path.relpath(path, ROOT).replace("\\", "/")
        if os.path.normpath(rel) not in TRACKED:
            continue
        try:
            tree = ast.parse(io.open(path, encoding="utf-8").read())
        except SyntaxError:
            continue
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            # names a local count was taken from, and names an except emptied
            counts, eaten = {}, {}
            for n in ast.walk(fn):
                if isinstance(n, ast.Assign):
                    shape = count_shaped(n.value)
                    if shape:
                        for t in n.targets:
                            if isinstance(t, ast.Name):
                                counts[t.id] = (shape, counted_name(n.value))
            for h in ast.walk(fn):
                if not isinstance(h, ast.ExceptHandler):
                    continue
                for n in ast.walk(h):
                    if isinstance(n, ast.Assign) and is_empty_literal(n.value):
                        for t in n.targets:
                            if isinstance(t, ast.Name):
                                eaten[t.id] = h.lineno
                    if isinstance(n, ast.Return) and is_empty_literal(n.value):
                        eaten.setdefault("<return>", h.lineno)

            # A: a count-shaped field with no absence/unread beside it
            for node in ast.walk(fn):
                if not isinstance(node, ast.Dict):
                    continue
                if {key_name(k) for k in node.keys} & ABSENCE_KEYS:
                    continue
                for k, v in zip(node.keys, node.values):
                    name = key_name(k)
                    if name is None:
                        continue
                    shape, src = count_shaped(v), counted_name(v)
                    if not shape and isinstance(v, ast.Name) and v.id in counts:
                        shape, src = counts[v.id]
                        shape += " (via %s)" % v.id
                    if shape:
                        a_rows.append((rel, fn.name, node.lineno, name, shape,
                                       "ROUTE" if route_decorated(fn) else (src or "")))

            # B: a swallowed failure that becomes a number
            for n in ast.walk(fn):
                if not isinstance(n, ast.Call):
                    continue
                shape = count_shaped(n)
                src = counted_name(n)
                if shape and src in eaten:
                    b_rows.append((rel, fn.name, n.lineno, src, shape,
                                   "except@%d" % eaten[src]))


def show(title, rows, note):
    seen, uniq = set(), []
    for r in rows:
        if r not in seen:
            seen.add(r)
            uniq.append(r)
    print("\n%s\npopulation: %d      %s" % (title, len(uniq), note))
    by = {}
    for r in uniq:
        by.setdefault(r[0], []).append(r)
    for f in sorted(by):
        print("  %s" % f)
        for row in sorted(by[f], key=lambda x: x[2]):
            print("     :%-5d %-32s %-22s %-22s %s"
                  % (row[2], row[1][:32], row[3][:22], row[4][:22], row[5] or ""))


routed = [r for r in set(a_rows) if r[5] == "ROUTE"]
show("A. a count-shaped field with no absence/unread beside it", a_rows,
     "(tracked files; excludes tests, scripts, migrations)")
print("")
print("   of which written INSIDE a route function: %d" % len(routed))
print("   the rest are written in helpers. How many of THOSE reach a response is not")
print("   separated here - it needs a call-graph walk, and guessing would be a third")
print("   wrong count in a row.")
show("B. a swallowed failure that BECOMES a number (the `unread` axis)", b_rows,
     "(same exclusions)")
