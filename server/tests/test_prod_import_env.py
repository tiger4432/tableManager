"""The runtime import graph must resolve in a PRODUCTION import environment.

WHY THIS TEST SHELLS OUT INSTEAD OF ASSERTING IN PROCESS
--------------------------------------------------------
Because an in-process assertion here would be worthless, and we know that because
one already was. `GET /admin/retroactive/enrichment_backfill/count` shipped raising
`ModuleNotFoundError` - its lazy `import backfill_enrichment` named a module in
`server/scripts`, which is on no runtime process's `sys.path` - and the suite was
green through the whole thing. It was green because pytest collects every test
module into ONE interpreter and `test_backfill_enrichment.py` did
`sys.path.insert(0, SCRIPTS_DIR)` at import time for its own use. From that moment
the import worked for everything that ran afterwards.

That insertion is now gone (that test imports `enrichment_backfill` from `server/`
like the runtime does), but removing it is not the fix and must not be mistaken for
one:

  * `test_install_product_tables.py` still inserts `SCRIPTS_DIR`, legitimately - it
    tests a script that has no runtime caller, and there is no other way to reach
    it. So the polluted condition still occurs in this suite.
  * Even with every insertion gone, an in-process check would only be true for the
    collection order it happened to run under. "No sibling test has polluted
    sys.path yet" is not a property anyone can hold.
  * A conftest guard cannot fix it either: the insertions happen when a test MODULE
    is imported, which is after conftest has finished.

The only environment a sibling test cannot reach into is a fresh interpreter. So
the check is a script, `prod_import_check.py`, and this test runs it in a child
process with a `sys.path` built from scratch.

WHAT IT CATCHES
---------------
Any runtime module importing a `server/scripts/*` module - at module level or,
as in the original defect, lazily inside a function body - and any runtime import
that does not resolve at all. `test_the_check_fails_on_a_new_scripts_import` proves
it by injecting one.
"""
import os
import subprocess
import sys
import textwrap

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CHECK = os.path.join(os.path.dirname(__file__), "prod_import_check.py")


def _run_check(server_dir=SERVER_DIR):
    """Child interpreter, scrubbed environment.

    `PYTHONPATH` is cleared so an inherited one cannot hand the child a path the
    real web server would not have, and `-I` isolates it further (no site-packages
    user dir, no `PYTHON*` env). `PYTHONIOENCODING` is set because the Windows
    console is cp949 and the check prints paths.
    """
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-I", CHECK, "--server-dir", server_dir],
        capture_output=True, text=True, env=env, timeout=300,
    )


def test_every_runtime_import_resolves_without_server_scripts_on_the_path():
    """The property the broken route violated.

    `server/scripts` is deliberately absent from the child's `sys.path`: every file
    in there bootstraps `server/` for ITSELF when run as `__main__`, which makes
    `server/` importable from a script and never the reverse.
    """
    r = _run_check()
    assert r.returncode == 0, (
        "a runtime module cannot be imported the way production imports it:\n"
        f"--- stdout ---\n{r.stdout}\n--- stderr ---\n{r.stderr}")
    # Non-vacuous: a check that scanned nothing would also exit 0.
    assert "PASS" in r.stdout
    assert "scripts on path : False" in r.stdout


def test_the_check_is_actually_looking_at_the_tree():
    """Guard against the check passing because it found no files or no imports."""
    r = _run_check()
    line = next(l for l in r.stdout.splitlines() if l.startswith("scanned"))
    n_files = int(line.split(":")[1].strip().split()[0])
    n_imports = int(line.split(",")[1].strip().split()[0])
    assert n_files > 50, f"only {n_files} runtime files scanned; the walk is broken"
    assert n_imports > 500, f"only {n_imports} imports scanned; the parse is broken"


def test_the_check_fails_on_a_new_scripts_import(tmp_path):
    """INJECTION: add one runtime import of a `server/scripts` module.

    Run against a copy of the tree, not the real one - a test that edits `server/`
    and restores it in a `finally` leaves the tree broken when it is interrupted,
    and autocrlf makes the "restored" bytes differ anyway (server-pm memory).

    The copy carries a minimal `scripts/` plus one runtime module that imports from
    it *inside a function body*, which is the exact shape of the original defect and
    the shape a module-level scan would miss.
    """
    fake = tmp_path / "server"
    (fake / "scripts").mkdir(parents=True)
    (fake / "scripts" / "some_operator_cli.py").write_text(
        "def run():\n    return 1\n", encoding="utf-8")
    (fake / "a_route_module.py").write_text(textwrap.dedent("""
        def handler(db):
            import some_operator_cli          # <- the defect, lazily
            return some_operator_cli.run()
    """).lstrip("\n"), encoding="utf-8")

    r = _run_check(str(fake))

    assert r.returncode == 1, (
        "the check passed over a runtime import of a scripts module:\n" + r.stdout)
    assert "some_operator_cli" in r.stdout
    assert "a_route_module.py:2" in r.stdout, (
        "the failure must name the file and line, or it is not actionable:\n"
        + r.stdout)
    # And it must be diagnosed AS a scripts import, with the remedy. Injection
    # showed why this assertion is separate: with the scripts-membership branch
    # disabled the run still exits 1, because the module also fails to resolve -
    # so the exit code alone cannot tell "detected the real problem" from
    # "tripped over a symptom". Detection is deliberately doubly covered; the
    # message is what makes the covering branch identifiable.
    assert "server/scripts" in r.stdout
    assert "operator entry points" in r.stdout, (
        "the failure does not point at the established split, so the next reader "
        "is likely to reach for sys.path instead:\n" + r.stdout)


def test_a_guarded_optional_import_is_not_a_failure(tmp_path):
    """The other direction: don't cry wolf on a declared-optional dependency.

    A dependency imported inside `try/except ImportError` is explicitly optional.
    That absence is handled, so it is not an outage. An UNGUARDED import is.
    """
    fake = tmp_path / "server"
    (fake / "scripts").mkdir(parents=True)
    (fake / "optional_dep.py").write_text(textwrap.dedent("""
        try:
            import a_package_that_does_not_exist_anywhere
        except ImportError:
            a_package_that_does_not_exist_anywhere = None
    """).lstrip("\n"), encoding="utf-8")

    r = _run_check(str(fake))
    assert r.returncode == 0, "a guarded optional import was reported as a defect:\n" + r.stdout
    assert "optional" in r.stdout

    # ... and the same import without the guard IS a failure. Without this half,
    # the test above would also pass against a check that never resolves anything.
    (fake / "optional_dep.py").write_text(
        "import a_package_that_does_not_exist_anywhere\n", encoding="utf-8")
    r2 = _run_check(str(fake))
    assert r2.returncode == 1, (
        "an unguarded import of a missing module was not reported:\n" + r2.stdout)
    assert "a_package_that_does_not_exist_anywhere" in r2.stdout
