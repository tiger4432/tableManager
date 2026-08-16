"""Does the runtime import graph resolve in a PRODUCTION import environment?

WHY THIS IS NOT A TEST FUNCTION
-------------------------------
Because a test function could not prove it. pytest collects every test module into
ONE interpreter, and two test modules insert ``server/scripts`` into ``sys.path`` at
import time (``test_backfill_enrichment.py``, ``test_install_product_tables.py``).
After either is collected, ``import backfill_enrichment`` succeeds for every test
that runs afterwards - including a test written to prove it fails. That is exactly
how ``GET /admin/retroactive/enrichment_backfill/count`` shipped broken under a
green suite: the route's lazy ``import backfill_enrichment`` had no importer on the
runtime path, and the only thing that ever imported it was a test file that had
already fixed up ``sys.path`` for itself.

So this module is a SCRIPT, run by ``test_prod_import_env.py`` in a child
interpreter whose path is built from scratch. Nothing another test file does can
reach it.

WHAT A RUNTIME PROCESS ACTUALLY HAS ON sys.path
-----------------------------------------------
``server/`` and ``server/parsers`` (``main.py``), or ``server/`` alone (the
remaining worker entry points: ``run_auto_update``, ``run_chain_worker``,
``run_watcher`` - each appends its own directory, which is ``server/``).
``server/scripts`` is on NOBODY's path. Every file in there bootstraps itself with
``sys.path.insert(0, <server dir>)`` when run as ``__main__``, which makes
``server/`` importable FROM a script and never the other way round.

THE TWO CHECKS
--------------
1. STRUCTURAL, whole runtime tree. Every ``import X`` / ``from X import`` in every
   runtime module - INCLUDING the ones inside function bodies, which is where this
   class of defect hides - is matched against the module names that live in
   ``server/scripts/``. A hit is a route that will raise ``ModuleNotFoundError`` the
   first time an operator presses the button.
2. EXECUTABLE, this interpreter. Every module named by an import anywhere in the
   runtime tree is resolved with ``importlib.util.find_spec`` under the production
   path. Check 1 catches "imports something from scripts/"; check 2 catches
   "imports something that is not there at all", which is the same outage with a
   different cause.

Resolution is by ``find_spec``, never by executing the import: resolving a module
must never execute its administrative operation.

USAGE
    conda run -n assy_manager python server/tests/prod_import_check.py
    (exit 0 = clean, 1 = a runtime import does not resolve on the runtime path)
"""
import argparse
import ast
import importlib.util
import os
import sys

#: Subtrees that are NOT loaded by a runtime process, so their imports are not
#: subject to the runtime path. `scripts/` and `setup/` are operator entry points
#: that bootstrap their own path; `tests/` is pytest; `scratch/` is disposable.
NON_RUNTIME_DIRS = ("scripts/", "tests/", "setup/", "scratch/", "migrations/")

#: Exceptions that make an import OPTIONAL rather than required.
#:
#: An unresolvable import is only a defect if the process would die on it. Where
#: the source wraps the import in `try/except ImportError` and carries on, the
#: absence is a declared, handled state and this check must not call it a failure -
#: A guarded optional dependency is a declared, handled state.
#:
#: This is detected from the SOURCE rather than kept as a name allowlist on
#: purpose: an allowlist has to be maintained, and the maintenance always goes the
#: same way - someone adds a name to make the check pass. A guard is the author
#: saying, in code, that they handled the absence.
IMPORT_GUARD_EXCEPTIONS = {"ImportError", "ModuleNotFoundError", "Exception",
                           "BaseException"}


def runtime_files(server_dir):
    for dirpath, dirnames, filenames in os.walk(server_dir):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in sorted(filenames):
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, server_dir).replace("\\", "/")
            if rel.startswith(NON_RUNTIME_DIRS):
                continue
            yield path, rel


def _guarded_import_nodes(tree):
    """Import nodes inside a `try` whose handler swallows an import failure."""
    guarded = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        handled = False
        for h in node.handlers:
            if h.type is None:      # bare `except:`
                handled = True
                break
            names = ([e.id for e in h.type.elts if isinstance(e, ast.Name)]
                     if isinstance(h.type, ast.Tuple)
                     else [h.type.id] if isinstance(h.type, ast.Name) else [])
            if IMPORT_GUARD_EXCEPTIONS.intersection(names):
                handled = True
                break
        if not handled:
            continue
        for stmt in node.body + node.orelse:
            for sub in ast.walk(stmt):
                if isinstance(sub, (ast.Import, ast.ImportFrom)):
                    guarded.add(id(sub))
    return guarded


def imports_in(path):
    """(line, module name, guarded) for every import statement in the file.

    Walks the whole tree, so a lazy `import x` inside a function body is reported
    exactly like a module-level one. That is the point: the defect this file exists
    for was a function-body import that no module-level scan would have seen.
    Relative imports (`from . import x`) are skipped - they resolve by package, not
    by sys.path.

    `guarded` marks an import the source itself declares optional (see
    IMPORT_GUARD_EXCEPTIONS). It excuses "this module is not installed"; it does
    NOT excuse reaching into `server/scripts`, because a caught ImportError there
    means the feature is silently dead, not optional.
    """
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    try:
        tree = ast.parse(src, filename=path)
    except SyntaxError as e:
        return [(e.lineno or 0, "<syntax error: %s>" % e, False)]
    guarded = _guarded_import_nodes(tree)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.append((node.lineno, a.name.split(".")[0], id(node) in guarded))
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                out.append((node.lineno, node.module.split(".")[0],
                            id(node) in guarded))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--server-dir", default=None,
                    help="server/ directory (default: this file's parent's parent)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    server_dir = os.path.abspath(
        args.server_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    scripts_dir = os.path.join(server_dir, "scripts")
    parsers_dir = os.path.join(server_dir, "parsers")

    # --- build the production path, from scratch -----------------------------
    # `server/` + `server/parsers` is what main.py has; the workers have `server/`
    # alone. `server/scripts` is removed rather than merely not added, so an
    # inherited PYTHONPATH cannot quietly reintroduce it.
    sys.path = [p for p in sys.path if os.path.abspath(p or ".") != scripts_dir]
    for p in (parsers_dir, server_dir):
        if p not in sys.path:
            sys.path.insert(0, p)
    os.chdir(server_dir)

    script_modules = {f[:-3] for f in os.listdir(scripts_dir)
                      if f.endswith(".py") and not f.startswith("__")}

    print(f"server dir      : {server_dir}")
    print(f"scripts on path : "
          f"{scripts_dir in [os.path.abspath(p or '.') for p in sys.path]}  (must be False)")
    print(f"scripts modules : {len(script_modules)}")

    from_scripts = []      # check 1
    unresolved = []        # check 2
    optional = []          # declared optional, reported but not failed
    n_files = n_imports = 0

    for path, rel in runtime_files(server_dir):
        n_files += 1
        for lineno, mod, guarded in imports_in(path):
            n_imports += 1
            if mod.startswith("<syntax error"):
                unresolved.append((rel, lineno, mod))
                continue
            if mod in script_modules:
                # NOT excused by a guard: a caught ImportError on a scripts module
                # means the operation is silently dead, which is worse than loud.
                from_scripts.append((rel, lineno, mod))
                continue
            if mod in sys.builtin_module_names:
                continue
            try:
                spec = importlib.util.find_spec(mod)
            except (ImportError, ValueError, AttributeError) as e:
                spec, err = None, repr(e)
            else:
                err = None
            if spec is None:
                if guarded:
                    optional.append((rel, lineno, mod))
                else:
                    unresolved.append((rel, lineno, f"{mod}{'  ' + err if err else ''}"))
            elif args.verbose:
                origin = getattr(spec, "origin", None) or "<builtin>"
                print(f"  ok  {rel}:{lineno}  {mod}  <- {origin}")

    print(f"scanned         : {n_files} runtime files, {n_imports} import statements")
    if optional:
        print(f"optional        : {len(optional)} unresolved import(s) the source "
              f"declares optional (try/except ImportError):")
        for rel, lineno, mod in optional:
            print(f"                    server/{rel}:{lineno}  {mod}")
    print()

    if from_scripts:
        print(f"FAIL - {len(from_scripts)} runtime import(s) of a server/scripts module.")
        print("       server/scripts is on no runtime process's sys.path, so each of")
        print("       these raises ModuleNotFoundError the first time it is reached:")
        for rel, lineno, mod in from_scripts:
            print(f"         server/{rel}:{lineno}   import {mod}"
                  f"   -> server/scripts/{mod}.py")
        print("       Fix: move the importable half into server/ and leave the CLI in")
        print("       scripts/ (operator entry points are not runtime-importable")
        print("       split). Do NOT put scripts/ on sys.path - that makes all "
              f"{len(script_modules)} of them importable from the runtime.")
    if unresolved:
        print(f"FAIL - {len(unresolved)} runtime import(s) do not resolve at all:")
        for rel, lineno, mod in unresolved:
            print(f"         server/{rel}:{lineno}   {mod}")

    if from_scripts or unresolved:
        return 1
    print("PASS - every runtime import resolves on the production path, and none of")
    print("       them reaches into server/scripts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
