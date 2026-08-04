"""`main` is a process entry point, not a library, and nothing may treat it as one.

WHAT THIS SUITE DID NOT HAVE
    The retroactive auto-confirm sweep was verified and closed as working. It
    then failed in production with

        AttributeError: module 'main' has no attribute 'get_column_filter_condition'

    while the same operation from the CLI worked. Nothing here could have caught
    it, because every test in this suite imports `main` the way `conftest.py`
    does - once, at module scope, from a process whose `sys.path` is the repo's.
    In that process `sys.modules['main']` is already the application module, so
    the lazy `import main` inside `enrichment_analysis._queue_condition` was
    always handed the right object. The suite reproduced the CODE and not the
    PROCESS STRUCTURE.

    The structure it missed: `run_auto_update.py` inserts every collector's own
    directory at `sys.path[0]` (lines 217-218 and 487-488) and never removes it,
    and `parsers/directory_watcher.py` does the same for each table's `scripts/`
    directory. Those are user-owned directories. After the first insertion `main`
    is no longer a stable name in that process - a user file called `main.py`
    binds first, and every unqualified `import main` in that process gets it.

    So the two tests below are of two different kinds, deliberately:
      1. a SOURCE rule - no module may reach the entry point at all (the general
         form of `test_config_reload_integrity.test_h4_chain_worker_never_imports_main`,
         which wrote this rule down for one worker after the same class of defect);
      2. a PROCESS test - run the queue predicate in a subprocess shaped like a
         worker, with a decoy `main.py` first on `sys.path`, and require it to
         translate anyway.
"""
import os
import re
import subprocess
import sys
import textwrap

#: Anchored at the start of the (stripped) line on purpose. A substring match
#: flags this file's own prose and the two module docstrings that explain the
#: rule - the ban is on the STATEMENT, and prose about the statement is how the
#: rule stays legible.
_IMPORTS_MAIN = re.compile(r"^(import\s+main\b(?!\s*\.)|from\s+main\s+import\b)")

_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

#: The entry point itself is allowed to be itself, and the suite is allowed to
#: import the app under test (conftest does). Nothing else is.
_EXEMPT = {
    os.path.normcase(os.path.join(_SERVER_DIR, "main.py")),
}


def _python_sources():
    for root, dirs, files in os.walk(_SERVER_DIR):
        dirs[:] = [d for d in dirs
                   if d not in ("__pycache__", "tests", "ingestion_workspace",
                                "config_backup_20260801_reset")]
        for f in files:
            if f.endswith(".py"):
                p = os.path.join(root, f)
                if os.path.normcase(p) not in _EXEMPT:
                    yield p


def test_no_server_module_imports_the_web_entrypoint():
    """The general form: `import main` is banned everywhere under server/.

    Not "banned in the worker that was caught doing it". The name `main` is the
    single most common filename in Python, and three of the five processes put
    user-writable directories ahead of `server/` on `sys.path`, so the binding is
    decided by whatever a user has lying around. A helper that two processes need
    belongs in a module that is not an entry point - `utils/time_format.py` and
    `column_filter.py` both exist for exactly this reason.
    """
    offenders = []
    for path in _python_sources():
        with open(path, encoding="utf-8") as fh:
            for lineno, raw in enumerate(fh, 1):
                line = raw.strip()
                if line.startswith("#") or not _IMPORTS_MAIN.match(line):
                    continue
                offenders.append(f"{os.path.relpath(path, _SERVER_DIR)}:{lineno}: {line}")
    assert not offenders, (
        "these modules import the web entry point:\n  " + "\n  ".join(offenders) +
        "\nIn the scheduler and watcher processes `main` binds to whatever main.py "
        "sits earliest on sys.path, which is a user directory. Move the shared symbol "
        "to a non-entry-point module and re-export it from main.py."
    )


_QUEUE_PREDICATE_PROBE = textwrap.dedent(
    '''
    import os, sys
    # A worker process: the user directory FIRST, server/ after it. This is the
    # order run_auto_update.py leaves behind once any collector has run.
    sys.path.insert(0, os.environ["PROBE_DECOY_DIR"])
    sys.path.insert(1, os.environ["PROBE_SERVER_DIR"])
    os.chdir(os.environ["PROBE_SERVER_DIR"])

    from sqlalchemy import Column, Integer, String
    from sqlalchemy.orm import declarative_base

    Base = declarative_base()

    class Probe(Base):
        # A name that cannot collide with a real user table (see the shared
        # lesson about test table names colliding with gitignored config).
        __tablename__ = "entrypointiso_probe_tbl"
        row_id = Column(Integer, primary_key=True)
        business_key_val = Column(String)
        eip_key = Column(String)
        eip_target = Column(String)

    import enrichment_analysis

    rule = {
        "name": "entrypointiso_probe_rule",
        "source_table": "entrypointiso_src",
        "derived_table": "entrypointiso_probe_tbl",
        "decision_key": ["eip_key"],
        "target_fields": ["eip_target"],
        "list_columns": [],
        "reference_views": [],
    }
    cond = enrichment_analysis._queue_condition(Probe, rule)
    print("CONDITION", cond is not None)
    print("MAIN_IN_MODULES", "main" in sys.modules)

    # The defect axis, asserted by the probe itself rather than assumed: prove the
    # decoy really would have been picked up by an unqualified `import main`.
    import main as _decoy
    print("DECOY_WINS", os.path.normcase(os.path.dirname(_decoy.__file__))
          == os.path.normcase(os.environ["PROBE_DECOY_DIR"]))
    '''
)


def test_the_queue_predicate_translates_with_a_decoy_main_on_the_path(tmp_path):
    """The process test the suite was missing.

    Reproduces the production shape rather than the production code: a user file
    named `main.py` sits first on `sys.path`, exactly as it would in the scheduler
    after any collector has run. Before the translator moved out of `main.py` this
    raised `AttributeError: module 'main' has no attribute
    'get_column_filter_condition'` - the reported failure, verbatim.

    The decoy is deliberately BENIGN (it imports cleanly and defines something
    unrelated). A decoy that raised on import would prove a weaker thing: the
    point is that a perfectly valid user module silently answers to the name.
    """
    decoy_dir = tmp_path / "auto_update"
    decoy_dir.mkdir()
    (decoy_dir / "main.py").write_text(
        "# a user's collector helper that happens to be called main.py\n"
        "def fetch():\n    return []\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env.pop("TESTING", None)
    env.pop("ASSY_ADMIN_TOKEN", None)
    env["PYTHONIOENCODING"] = "utf-8"
    env["DATABASE_URL"] = "sqlite:///:memory:"
    env["PROBE_SERVER_DIR"] = _SERVER_DIR
    env["PROBE_DECOY_DIR"] = str(decoy_dir)

    proc = subprocess.run([sys.executable, "-c", _QUEUE_PREDICATE_PROBE],
                          cwd=_SERVER_DIR, env=env, capture_output=True,
                          text=True, timeout=180)
    out = proc.stdout
    assert proc.returncode == 0, (
        f"the queue predicate could not be built in a worker-shaped process\n"
        f"STDOUT:\n{out}\nSTDERR:\n{proc.stderr}"
    )
    assert "CONDITION True" in out, f"the filter DSL translated to nothing:\n{out}"
    # The whole point: the entry point is not involved at all.
    assert "MAIN_IN_MODULES False" in out, (
        f"the queue predicate still drags the web entry point in:\n{out}"
    )
    # Without this the test would pass on a machine where the decoy never shadowed
    # anything, and would therefore prove nothing.
    assert "DECOY_WINS True" in out, (
        f"the decoy did not shadow `main`, so this test exercised no defect axis:\n{out}"
    )
