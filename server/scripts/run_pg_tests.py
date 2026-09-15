# -*- coding: utf-8 -*-
"""Run the PostgreSQL-only proofs before a restart (S-256).

    conda run -n assy_manager python server/scripts/run_pg_tests.py          # repo root
    conda run -n assy_manager python server/scripts/run_pg_tests.py -x -k ledger

Every argument is handed to pytest unchanged.

🔴 WHY THIS EXISTS. SQLite accepts what PostgreSQL refuses - jsonb, partitions, ON CONFLICT,
CHECK, a UNIQUE index over a NULL - so the suite that runs on `sqlite:///:memory:` is green
about things production will refuse. The proofs only PostgreSQL can carry are marked
`@pytest.mark.pg` (registered in tests/conftest.py), and this is the one command that runs
them against THIS box's PostgreSQL: the server the product itself resolves.

WHAT IT DECIDES, IN ORDER
  1. Which PostgreSQL. The URL the server resolves - `paths.resolve_database_url`, i.e.
     env DATABASE_URL > config/database.json > the default - names the server. If that is
     not PostgreSQL there is nothing to prove against: one REFUSED line, exit 2.
  2. Which DATABASE on it. Never the product's own: the proofs create and drop scratch
     schemas. `tests/support/isolated_pg.resolve_url` is the ONE spelling of which
     database they may use (ASSY_PG_TEST_DATABASE_URL > ASSY_TEST_DATABASE_URL > the
     dev_env QA database), and it passes the answer through `db_safety`, so declaring
     production is still refused. No usable declaration is a REFUSED line, exit 2 - not
     a skip, because a skip is how these proofs stayed quiet for months (S-104, S-115).
  3. `pytest tests -m pg -rs --continue-on-collection-errors`, with that database
     exported under the variable BOTH PG fixture families read (`pg_engine` in conftest
     and the isolated_pg suites), so the two cannot decide differently about the same
     box. The exit code is pytest's.

     ⚠️ `--continue-on-collection-errors` is load-bearing: pytest otherwise ABORTS the
     whole run when any module fails to collect, even a deselected one - and the tests
     that import the box's gitignored mappers do exactly that on a fresh checkout, so
     `-m pg` ran nothing there and exited 2 (measured 2026-09-16). With the flag the
     proofs run, the collection errors are still printed and still make the exit
     non-zero, so a box cannot read as clean because of them.

READING THE ANSWER
  passed             the PostgreSQL truths hold on this box's server
  skipped            the -rs line says why (server unreachable, extension missing).
                     A skip is NOT a pass - the proof did not run
  failed / error     fix before restarting. "error" on a mapper test module means the
                     box's own mappers or config are missing, not a PostgreSQL truth
  REFUSED + exit 64  this script stopped; nothing was run. 64 so it cannot be read as
                     pytest's own 2 ("interrupted")
"""
import os
import subprocess
import sys

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

#: Exit code of a refusal. Distinct from every code pytest itself returns (0 pass, 1 fail,
#: 2 interrupted, 3 internal error, 4 usage, 5 nothing collected).
REFUSED = 64


def _parsed(url):
    from sqlalchemy.engine import make_url
    return make_url(url)


def main(argv):
    import paths
    from tests.support.isolated_pg import PG_TEST_URL_ENV, resolve_url

    server_url, source = paths.resolve_database_url(paths.DEFAULT_PG_URL)
    if _parsed(server_url).get_backend_name() != "postgresql":
        print(f"REFUSED: the server's database is not PostgreSQL - "
              f"{paths.mask_db_password(server_url)} (from {source}); "
              f"the pg proofs have nothing to run against.")
        return REFUSED

    test_url, reason = resolve_url()
    if test_url is None:
        print(f"REFUSED: {reason}")
        return REFUSED

    server_of = lambda u: (_parsed(u).host, _parsed(u).port)  # noqa: E731
    if server_of(test_url) != server_of(server_url):
        print("NOTE: the declared test database is on a DIFFERENT server than the "
              "product's, so this run says nothing about the product's PostgreSQL.")
    print(f"server database  {paths.mask_db_password(server_url)}  (from {source})")
    print(f"proofs run in    {paths.mask_db_password(test_url)}")
    sys.stdout.flush()  # before the child writes, or a redirected log shows these last

    env = dict(os.environ)
    env[PG_TEST_URL_ENV] = test_url
    cmd = [sys.executable, "-m", "pytest", "tests", "-m", "pg", "-rs",
           "--continue-on-collection-errors", *argv]
    return subprocess.call(cmd, cwd=SERVER_DIR, env=env)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
