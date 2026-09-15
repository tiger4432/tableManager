# -*- coding: utf-8 -*-
"""Which PostgreSQL the PG-only proofs may use, in ONE spelling (S-115).

🔴 WHY THIS MODULE EXISTS. Two files hold proofs that only PostgreSQL can carry -
partitions, jsonb, CHECK, ON CONFLICT, UNIQUE - and each carried its own copy of "may I
run, and against what". The copies had already drifted: `test_ledger_l1_pg.py` grew the
`dev_env` fallback when S-104 measured what a wholesale skip had been hiding (25 red on
the first run in months), and `test_ledger_v2_pg.py` did not - so the same suite decided
differently about the same machine, and the half that stayed quiet kept a broken
`backfill.run` signature and a call to a function that does not exist.

⛔ THE GATE IS A SAFETY GATE, so a second copy is not a tidiness question. It is what
stops a proof that issues schema DDL from finding production; two spellings of that is
how one of them comes to be the lenient one.
"""
import contextlib
import os

#: The variable an operator sets to name an isolated database. Named here so the two
#: suites and their skip messages cannot disagree about which one it is.
PG_TEST_URL_ENV = "ASSY_PG_TEST_DATABASE_URL"

#: What makes one process's scratch schema ITS OWN (S-116).
#:
#: 🔴 THE SUITES SHARE A DATABASE, AND TWO OF THEM SHARED A NAME. Each drops its scratch
#: schema on the way in ("reclaim a leftover from a run that was killed mid-suite") and on
#: the way out, so two processes running the same file at once took turns deleting each
#: other's tables - `no partition of relation ledger_events` on an insert that was correct,
#: green and red from the same HEAD minutes apart. `test_ledger_v2_pg.py` had put the pid in
#: its name all along and was the one that never flapped; three siblings, two spellings, and
#: the lenient one is the one that loses.
#:
#: The xdist worker id is kept beside the pid rather than replaced by it: workers are
#: separate processes, so the pid alone would do, and a name that says which worker owns a
#: leftover schema is worth the eight characters.
RUN_TOKEN = f"{os.getpid()}_{os.environ.get('PYTEST_XDIST_WORKER', 'gw0')}"


def scratch_schema(prefix: str) -> str:
    """`<prefix>_<pid>_<worker>` - a schema name no other process will drop."""
    return f"{prefix}_{RUN_TOKEN}"


def scratch_connect_args(schema: str) -> dict:
    """Connection options that put `schema` FIRST on the search path and `public` after it.

    The ONE spelling (S-257). The ORM models are mapped to schema-less tables and the ledger
    DDL is unqualified, so the redirection into a scratch schema happens at the connection,
    and the scratch schema being FIRST is what makes everything a proof creates land in it
    and go with it on the DROP.

    ⚠️ `public` IS ON THE PATH, AND FOR READING (S-64-b). `pg_trgm` may already live in
    `public` - the live box had it installed by hand, and any `ensure_schema` run against
    the isolated database installs it there too. When it does, `CREATE EXTENSION IF NOT
    EXISTS` is a silent no-op wherever it is asked for, and with `public` invisible every
    `gin_trgm_ops` index then fails with `UndefinedObject`. Measured on the first run of
    `scripts/run_pg_tests.py`: 47 of 48 `pg_engine` tests, because conftest was the one
    spelling without the comma. Three sibling suites had already learned it; a fourth
    spelling is how one of them comes to be the broken one.

    The same dict is what `psycopg2.connect(url, **...)` takes, so a raw competitor
    connection is pinned the same way as the engine.
    """
    return {"options": f"-csearch_path={schema},public"}


def install_trigram(connection, schema: str) -> None:
    """`pg_trgm` inside the scratch schema, so it dies with it on the DROP ... CASCADE.

    A no-op when the extension already exists anywhere in the database - which is fine,
    because `scratch_connect_args` keeps `public` readable. Skips the calling test when the
    role cannot create extensions: the ledger schema cannot be built there at all.
    """
    import pytest
    from sqlalchemy import text

    try:
        connection.execute(text(
            f'CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA "{schema}"'))
    except Exception as exc:
        pytest.skip(f"pg_trgm is not installable on this box, so the ledger schema "
                    f"cannot be built here: {exc}")



def declared_qa_database():
    """The QA database `dev_env` declares, or `None` if that module cannot say.

    ⚠️ READ, NOT INVENTED. The URL comes from `scripts/dev_env/devenv.py`, which is
    where this project says what its isolated database is; hard-coding one here would be a
    second declaration of the same fact, and the day someone moves it the tests would point
    at whatever used to be there.
    """
    try:
        import importlib.util

        here = os.path.dirname(os.path.abspath(__file__))
        spec = importlib.util.spec_from_file_location(
            "_devenv_declaration",
            os.path.join(here, "..", "..", "scripts", "dev_env", "devenv.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        url = getattr(module, "QA_DB_URL", None)
    except Exception:
        return None
    return url if isinstance(url, str) and url.startswith("postgres") else None


def resolve_url():
    """`(url, None)` when these proofs may run, `(None, reason)` when they may not."""
    import db_safety
    from database.database import DEFAULT_PG_URL

    url = os.environ.get(PG_TEST_URL_ENV) or None
    if not url:
        candidate = os.environ.get(db_safety.TEST_DATABASE_URL_ENV) or ""
        url = candidate if candidate.startswith("postgres") else None
    if not url:
        # 🔴 A WHOLESALE SKIP IS A FALSE GREEN, AND THAT IS WHAT BOTH FILES WERE (S-104
        # 판정 215, S-115). Proofs of the things ONLY PostgreSQL can prove reported
        # "skipped" on every run because nobody had exported a variable, so nothing in them
        # had been executed since the declaration grammar changed underneath. Measured
        # 2026-09-09 on the first file: 25 red. On the second, 2026-09-10: a `backfill.run`
        # call in the retired v1 shape and a call to `ledger_trace.trace`, which does not
        # exist.
        #
        # So the LAST resort is the database `scripts/dev_env/devenv.py` already declares
        # for this purpose. It is named there, it is not production, and `db_safety` below
        # still has to approve it - this only stops a suite from staying quiet when a test
        # database exists and no one said so.
        url = declared_qa_database()
    if not url:
        return None, (
            f"no PostgreSQL test database declared. Set {PG_TEST_URL_ENV} to an "
            f"ISOLATED database, e.g. "
            f"{PG_TEST_URL_ENV}=postgresql://postgres:...@localhost:5432/assy_qa")

    violations = db_safety.check_test_database(url, production_url=DEFAULT_PG_URL,
                                               opt_in=url)
    if violations:
        return None, f"{PG_TEST_URL_ENV} is not usable: {violations[0]}"

    from sqlalchemy.engine import make_url
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql":
        return None, f"{PG_TEST_URL_ENV} is not a PostgreSQL URL"
    if (parsed.database or "") == "assy_manager":
        return None, "refusing to run schema DDL against 'assy_manager'"
    return url, None


@contextlib.contextmanager
def declared_as_test_database(url):
    """Hold `db_safety`'s variable at `url` for the block, then put back what was there.

    The production code these proofs drive asks `db_safety` whether the database it is
    about to write to is a test one, so a proof that opened its own connection and did not
    say so would be refused by the very guard it depends on.
    """
    import db_safety
    key = db_safety.TEST_DATABASE_URL_ENV
    previous = os.environ.get(key)
    os.environ[key] = url
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous
