"""The product's launcher on a scratch schema - what rd/wd/rh drivers share. Import FIRST (it pins this process's own
product imports to sqlite before anything can resolve the box database)."""
import os
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.pop("ASSY_ADMIN_TOKEN", None)
import json                                                       # noqa: E402
import secrets                                                    # noqa: E402
import subprocess                                                 # noqa: E402
import sys                                                        # noqa: E402
import time                                                       # noqa: E402
import urllib.request                                             # noqa: E402

sys.path.insert(0, "C:/Users/kk980/Developments/assyManager/server")
sys.path.insert(0, "C:/Users/kk980/Developments/assyManager/server/tests")
import psycopg2                                                    # noqa: E402
from sqlalchemy.engine import make_url                             # noqa: E402

from support import isolated_pg                                    # noqa: E402

PY = "C:/Users/kk980/anaconda3/envs/assy_manager/python.exe"
HERE = os.path.dirname(os.path.abspath(__file__))
url, _why = isolated_pg.resolve_url()
assert url, _why
_u = make_url(url)
T0 = time.monotonic()


class Launch:
    def __init__(self, wt, root, schema, port=18765):
        self.wt, self.root, self.schema, self.port = wt, root, schema, port
        self.base = "http://127.0.0.1:%d" % port
        self.token = secrets.token_urlsafe(24)                     # this private instance only, never printed
        if os.environ.get("E2E_TOKEN_FILE"):                       # for a screen run on this instance: a scratch file
            with open(os.environ["E2E_TOKEN_FILE"], "w", encoding="utf-8") as f:
                f.write(self.token)
        self.proc, self.public_before = None, {}

    # --- database -------------------------------------------------------------------------------------------
    def pg(self):
        c = psycopg2.connect(host=_u.host, port=_u.port, user=_u.username, password=_u.password, dbname=_u.database,
                             options="-csearch_path=%s,public" % self.schema)
        c.autocommit = True
        return c

    def q(self, sql, args=()):
        c = self.pg()
        try:
            k = c.cursor()
            k.execute(sql, args) if args else k.execute(sql)
            return k.fetchall() if k.description else None
        finally:
            c.close()

    def public_counts(self):
        out = {}
        for (name,) in self.q("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"):
            out[name] = self.q('SELECT count(*) FROM public."%s"' % name)[0][0]
        return out

    # --- processes ------------------------------------------------------------------------------------------
    def env(self, **extra):
        e = dict(os.environ)
        for k in ("ASSY_DB_POOL_SIZE", "ASSY_DB_MAX_OVERFLOW", "TESTING"):
            e.pop(k, None)
        e.update({"ASSY_DATA_ROOT": self.root, "DATABASE_URL": url, "ASSY_TEST_DATABASE_URL": url,
                  "ASSY_SCRATCH_SCHEMA": self.schema, "ASSY_API_PORT": str(self.port), "ASSY_API_HOST": "127.0.0.1",
                  "API_BASE_URL": self.base, "ASSY_ADMIN_TOKEN": self.token, "PYTHONIOENCODING": "utf-8"}, **extra)
        return e

    def http(self, method, path, body=None):
        req = urllib.request.Request(self.base + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", "X-Admin-Token": self.token})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, json.loads(r.read().decode() or "null")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()[:400]
        except Exception as e:                                      # noqa: BLE001
            return None, str(e)[:200]

    def prepare(self, ledger=True, allow=()):
        """Schema, every product table made IN it (and the ledger's own DDL), public counted."""
        c = self.pg(); c.cursor().execute('CREATE SCHEMA IF NOT EXISTS "%s"' % self.schema); c.close()
        line = self.precreate(ledger, allow)
        self.public_before = self.public_counts()
        return line

    def precreate(self, ledger=True, allow=()):
        """Every table of the worktree's CURRENT code made in the schema - again after a checkout to a newer rev."""
        pre = subprocess.run([PY, os.path.join(HERE, "rr_precreate.py")], cwd=os.path.join(self.wt, "server"),
                             env=self.env(**({"PRECREATE_LEDGER": "1"} if ledger else {})), capture_output=True,
                             text=True, encoding="utf-8", errors="replace")
        line = [l for l in pre.stdout.splitlines() if l.startswith("PRECREATE ")]
        import ast
        shadow = set(ast.literal_eval(line[0].split("shadowing a product table: ", 1)[1])) if line else None
        assert shadow is not None and shadow <= set(allow), (pre.stdout[-600:], pre.stderr[-1500:])
        return line[0]

    def pin_scratch_schema(self):
        """The worktree's database.py binds every connection to this instance's scratch schema - put back here, at the one
        place every start passes, because a server-file swap (`git checkout <rev> -- server`) undoes it and the server
        then builds its tables in public (10-12 00:25: eleven fake_*/trd_* tables, dm_server_swap.py's whole-server swap).
        -> "already" or "applied"."""
        path = os.path.join(self.wt, "server", "database", "database.py")
        text = open(path, encoding="utf-8").read()
        if "ASSY_SCRATCH_SCHEMA" in text:
            return "already"
        old = 'connect_args={"options": "-c client_encoding=utf8"}'
        assert text.count(old) == 1, "database.py changed shape - the scratch pin cannot be put back (%d)" % text.count(old)
        text = text.replace(old, 'connect_args={"options": "-c client_encoding=utf8" + ((" -csearch_path=%s,public" % '
                                 'os.environ["ASSY_SCRATCH_SCHEMA"]) if os.environ.get("ASSY_SCRATCH_SCHEMA") else "")}')
        open(path, "w", encoding="utf-8").write(text)
        return "applied"

    def start(self, accept=None):
        # `accept()` -> a reason string ends the wait without /health 200 (dm_server_swap: a box whose health names only
        # what the box itself left behind)
        say("SCRATCH PIN %s" % self.pin_scratch_schema())
        if os.environ.get("E2E_SERVER_ONLY"):
            # the API alone, as the launcher runs it (DECOUPLED) - no chain worker, so no assy_chain* connection
            # name on the shared database (lead 10-10: a chain worker cuts every other one's connections)
            argv, cwd, env = ([PY, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(self.port)],
                              os.path.join(self.wt, "server"), self.env(DECOUPLED="True"))
        else:
            argv, cwd, env = [PY, "run_decoupled_app.py", "--no-client"], self.wt, self.env()
        self.proc = subprocess.Popen(argv, cwd=cwd, env=env,
                                     stdout=open(os.path.join(self.root, "launcher.out"), "w", encoding="utf-8"),
                                     stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        for _ in range(120):
            try:                                                    # no admin header on the poll (owner rule)
                with urllib.request.urlopen(self.base + "/health", timeout=30) as r:
                    s = r.status
            except urllib.error.HTTPError as e:
                s = e.code
            except Exception:                                       # noqa: BLE001
                s = None
            if s == 200:
                return s
            why = accept() if accept is not None and s is not None else None
            if why:
                return "%s (%s)" % (s, why)
            time.sleep(1)
        return s

    def stop(self):
        if self.proc is not None:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.proc.pid)], capture_output=True)
            time.sleep(3)
        after = self.public_counts()
        return {k: (self.public_before.get(k), v) for k, v in after.items() if self.public_before.get(k) != v}

    def cli(self, argv, timeout=1800, drop=(), full=None):
        """One owner command, run where the owner runs it (the server folder) on this instance -> (seconds, code, tail).
        `drop`: env names left out (PYTHONIOENCODING - what an owner's piped PowerShell does not set). `full`: a path that
        gets every line."""
        t0 = time.monotonic()
        env = self.env()
        for name in drop:
            env.pop(name, None)
        p = subprocess.run([PY if a == "python" else a for a in argv], cwd=os.path.join(self.wt, "server"), env=env,
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        out = [l for l in (p.stdout + "\n" + p.stderr).splitlines() if l.strip() and "Warning" not in l]
        if full:
            open(full, "w", encoding="utf-8").write(p.stdout + "\n--- stderr\n" + p.stderr)
        return time.monotonic() - t0, p.returncode, out[-12:]

    def settle(self, quiet=8, limit=900):
        """Until nothing waits for the chain or the ledger for `quiet` looks in a row -> seconds waited."""
        t0, calm = time.monotonic(), 0
        while time.monotonic() - t0 < limit:
            waiting = self.q("SELECT count(*) FROM database_outbox WHERE NOT processed_chain OR ledger_state IS NULL")[0][0]
            calm = calm + 1 if waiting == 0 else 0
            if calm >= quiet:
                return time.monotonic() - t0, 0
            time.sleep(1)
        return time.monotonic() - t0, waiting

    def log_lines(self, pattern):
        hits = []
        for name in sorted(os.listdir(self.root)):
            if name.endswith(".log") and "stdout" not in name:
                with open(os.path.join(self.root, name), encoding="utf-8", errors="replace") as f:
                    hits += ["%s: %s" % (name, l.strip()[:220]) for l in f if pattern in l]
        return hits


def say(*a):
    print("[%6.1f s]" % (time.monotonic() - T0), *a, flush=True)
