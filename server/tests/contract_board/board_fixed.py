"""Contract board, first step (lead 10-21): the three fixed boards from today's operation, each on the real product
(run_decoupled_app: API · watcher · chain worker · scheduler) on its own scratch schema of assy_test, plus ONE kill
board - to measure «one board's seconds» and «one kill board's seconds».
No admin token is sent anywhere (owner rule); retroactive work goes through the owner's CLI.
usage: board_fixed.py <worktree> <runs dir> [board ...]   boards: f1 f2 f3 f2k"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))                         # e2e_launch lives one folder up
import e2e_launch as E                                             # noqa: E402,I001 - FIRST product-touching import
import json                                                        # noqa: E402
import re                                                          # noqa: E402
import shutil                                                      # noqa: E402
import subprocess                                                  # noqa: E402
import time                                                        # noqa: E402
import urllib.request                                              # noqa: E402

WT = RUNS = None                    # set by main() or by an importer (board_gen) before a Board is built
PKG = os.path.join(HERE, "pkg")
SRC, DST = "bd_src", "bd_dst"
say = E.say
_noproxy = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class Board(E.Launch):
    def __init__(self, name, port, kill=None):
        root = os.path.join(RUNS, name)
        shutil.rmtree(root, ignore_errors=True)
        os.makedirs(root)
        super().__init__(WT, root, "assy_app_board_" + name, port=port)
        import socket
        with socket.socket() as probe:              # another lane's server on this port would take the board's writes
            assert probe.connect_ex(("127.0.0.1", port)) != 0, "port %d is already held - not this board's" % port
        self.kill, self.flag = kill, os.path.join(root, "killed.flag")

    def env(self, **extra):
        e = super().env(**extra)
        e.pop("ASSY_ADMIN_TOKEN", None)                            # no token in any process of the board
        e["PYTHONPATH"] = os.pathsep.join([PKG, os.path.join(self.wt, "server")])
        if self.kill:
            e.update(BOARD_KILL_AT=self.kill, BOARD_KILL_FLAG=self.flag)
        if getattr(self, "read_log", None):                         # the «fetch» column's read census (sitecustomize)
            e["BOARD_READ_LOG"] = self.read_log
        return e

    def call(self, method, path, body=None):
        req = urllib.request.Request(self.base + path, method=method, headers={"Content-Type": "application/json"},
                                     data=json.dumps(body).encode() if body is not None else None)
        try:
            with _noproxy.open(req, timeout=120) as r:
                return r.status, json.loads(r.read().decode() or "null")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()[:300]

    def rid(self, table, key):
        got = self.q('SELECT row_id FROM "%s" WHERE business_key_val = %%s' % table, (key,))
        return got[0][0] if got else None

    def check(self, src=SRC, dst=DST):
        p = subprocess.run([E.PY, os.path.join(HERE, "check_board.py"), src, dst], cwd=os.path.join(WT, "server"),
                           env=dict(self.env(), BOARD_KILL_AT="", BOARD_READ_LOG=""), capture_output=True, text=True,
                           encoding="utf-8",
                           errors="replace")
        line = [l for l in p.stdout.splitlines() if l.startswith("BOARD ")]
        assert line, (p.stdout[-800:], p.stderr[-1500:])
        out = json.loads(line[0][6:])
        assert out["schema"] == self.schema, out["schema"]           # canary: the checker read the scratch schema
        return out


def config(b, rule, types=None):
    cfg = os.path.join(b.root, "config")
    os.makedirs(os.path.join(cfg, "ontology"), exist_ok=True)
    types = types or {"k": "string", "m": "string", "v": "string"}
    t = json.load(open(os.path.join(WT, "server/config/sample/table_config.json.sample"), encoding="utf-8"))
    t = {k: v for k, v in t.items() if k.startswith("_")}
    t[SRC] = {"business_key": "k", "composite_key_source": ["k"], "column_types": dict(types),
              "display_columns": list(types)}
    t[DST] = {"business_key": "k", "composite_key_source": ["k"], "column_types": dict(types),
              "display_columns": list(types), "map_key_columns": ["m"]}
    json.dump(t, open(os.path.join(cfg, "table_config.json"), "w", encoding="utf-8"), indent=1)
    json.dump({"rules": [rule]}, open(os.path.join(cfg, "chain_rules.json"), "w", encoding="utf-8"), indent=1)
    ledger = json.load(open(os.path.join(WT, "server/config/sample/ledger_config.json.sample"), encoding="utf-8"))
    ledger["sources"] = {}
    json.dump(ledger, open(os.path.join(cfg, "ontology", "ledger_config.json"), "w", encoding="utf-8"), indent=1)
    return t


def put(b, items):
    code, body = b.call("PUT", "/tables/%s/data/updates" % SRC, {"updates": items})
    assert code == 200, (code, body)


def seed(b, n=6):
    put(b, [{"business_key_val": "K%d" % i, "updates": {"k": "K%d" % i, "m": "M%d" % (1 + (i - 1) // 3), "v": str(i)},
             "source_name": "user"} for i in range(1, n + 1)])


def settle(b, tag, tables=(SRC, DST)):
    s, waiting = b.settle(quiet=6, limit=600)
    out = b.check(*tables)
    say("CHECK %s %s settle %.0f s waiting %d" % (b.name, re.sub(r"^f\d+ ", "", tag), s, waiting),
        {k: v for k, v in out.items() if k not in ("snapshot", "schema")})
    return out


def run(b, rule, steps, types=None, write_config=None):
    """-> (seconds, checks). `write_config(b)` writes the board's config instead of `config` (board_gen)."""
    t0 = time.monotonic()
    if write_config:
        write_config(b)
    else:
        config(b, rule, types)
    c = b.pg()
    c.cursor().execute('DROP SCHEMA IF EXISTS "%s" CASCADE' % b.schema)
    c.close()
    say(b.name if hasattr(b, "name") else b.schema, b.prepare(ledger=True))
    checks = []
    try:
        t_up = time.monotonic()
        say("/health", b.start(), "%.0f s to stand" % (time.monotonic() - t_up))
        for step in steps:
            checks.append(step(b))
    finally:
        try:
            say("PUBLIC rows changed:", b.stop() or "none")
        except Exception as e:                                       # noqa: BLE001
            say("PUBLIC count failed:", str(e).splitlines()[0][:160])
        c = b.pg()
        c.cursor().execute('DROP SCHEMA IF EXISTS "%s" CASCADE' % b.schema)
        c.close()
    return time.monotonic() - t0, [x for x in checks if x is not None]


def wait_killed(b, limit=300):
    t0 = time.monotonic()
    while time.monotonic() - t0 < limit and not os.path.exists(b.flag):
        time.sleep(1)
    killed = os.path.exists(b.flag)
    say("KILLED" if killed else "NOT KILLED (seam never reached)", open(b.flag).read().strip() if killed else "")
    if killed:                                                      # the restart: stop the launcher, stand it again
        b.stop()
        say("restart /health", b.start())
    return killed


# --- the boards ------------------------------------------------------------------------------------------------------
F2_RULE = {"name": "board_f2", "trigger_table": SRC, "mapper": "board_copy", "target_table": DST,
           "is_batch": True, "allow_replace_map": True, "allow_delete_trigger": True}


def f2_steps(kill=False, rule="board_f2"):
    def edit_delete(b):
        if kill:
            open(b.flag + ".arm", "w").close()                      # the seam dies from here on, not in the seed
        put(b, [{"row_id": b.rid(SRC, "K2"), "updates": {"k": "K2X"}, "source_name": "user"}])
        code, body = b.call("POST", "/tables/%s/rows/batch_delete" % SRC, {"row_ids": [b.rid(SRC, "K5")],
                                                                          "user_name": "board"})
        assert code == 200, (code, body)
        if kill:
            wait_killed(b)
        return settle(b, "f2 after edit+delete")

    def replay(b):
        say("replay", b.cli(["python", "scripts/chain_replay_cli.py", "replay", rule, "--apply"])[:2])
        return settle(b, "f2 after whole replay")
    return [lambda b: (seed(b), settle(b, "f2 seeded"))[1], edit_delete, replay]


F1_RULE = {"name": "board_f1", "trigger_table": SRC, "mapper": "board_copy", "target_table": DST,
           "is_batch": True, "group_by": ["m"]}


def f1_steps():
    def retro(b):
        put(b, [{"row_id": b.rid(SRC, "K4"), "updates": {"v": "40"}, "source_name": "user"}])
        settle(b, "f1 after edit")
        say("replay", b.cli(["python", "scripts/chain_replay_cli.py", "replay", "board_f1", "--apply"])[:2])
        return settle(b, "f1 after whole replay")
    return [lambda b: (seed(b), settle(b, "f1 seeded"))[1], retro]


F3_RULE = {"name": "board_f3", "trigger_table": SRC, "mapper": "board_copy", "target_table": DST}


def f3_steps():
    def retype(b):
        for t in (SRC, DST):
            b.q('ALTER TABLE "%s"."%s" ALTER COLUMN v TYPE double precision USING NULLIF(v, \'\')::double precision'
                % (b.schema, t))
        path = os.path.join(b.root, "config", "table_config.json")
        t = json.load(open(path, encoding="utf-8"))
        for name in (SRC, DST):
            t[name]["column_types"]["v"] = "number"
        json.dump(t, open(path, "w", encoding="utf-8"), indent=1)
        time.sleep(8)                                               # the config watchers hear the save
        put(b, [{"row_id": b.rid(SRC, "K1"), "updates": {"v": 2.5}, "source_name": "user"}])
        out = settle(b, "f3 after retype + write 2.5")
        out["v_of_K1"] = b.q('SELECT v FROM "%s" WHERE business_key_val = %%s' % DST, ("K1",))
        out["write_errors"] = [l for l in b.log_lines("is of type double precision")][:3]
        say("f3 K1 v in target", out["v_of_K1"], "type errors", len(out["write_errors"]))
        return out
    return [lambda b: (seed(b), settle(b, "f3 seeded"))[1], retype]


F4_RULE = {"name": "board_f4", "trigger_table": SRC, "mapper": "board_copy", "target_table": DST}

BOARDS = {"f2": (F2_RULE, lambda: f2_steps(), None, 18791),
          "f1": (F1_RULE, f1_steps, None, 18792),
          "f3": (F3_RULE, f3_steps, None, 18793),
          "f2k": (F2_RULE, lambda: f2_steps(kill=True), "deleted_after_mark", 18794),
          # a plain copy: only the deleted-row retraction takes K5 out of the target (f2's map replace hid the gap)
          "f4": (F4_RULE, lambda: f2_steps(rule="board_f4"), None, 18795),
          # the author picks columns and the origin mark is lost: a deleted row and a key edit take back nothing (RED today)
          "f4n": (dict(F4_RULE, name="board_f4n", mapper="board_pick_columns"), lambda: f2_steps(rule="board_f4n"), None,
                  18797),
          "f4k": (F4_RULE, lambda: f2_steps(kill=True, rule="board_f4"), "deleted_after_mark", 18796)}


def main():
    global WT, RUNS
    WT, RUNS = sys.argv[1:3]
    WANT = sys.argv[3:] or ["f2", "f1", "f3", "f2k"]
    os.makedirs(RUNS, exist_ok=True)
    results = {}
    for name in WANT:
        rule, steps, kill, port = BOARDS[name]
        b = Board(name, port, kill)
        b.name = name
        say("=== BOARD %s (kill %s)" % (name, kill))
        secs, checks = run(b, rule, steps())
        results[name] = {"seconds": round(secs), "final": {k: v for k, v in checks[-1].items() if k != "schema"}}
        say("=== BOARD %s %.0f s" % (name, secs))
    for base in ("f2", "f4"):
        if base in results and base + "k" in results:
            same = results[base]["final"]["snapshot"] == results[base + "k"]["final"]["snapshot"]
            say("KILL BOARD %sk final == uninterrupted %s final:" % (base, base), same)
    json.dump(results, open(os.path.join(RUNS, "results.json"), "w", encoding="utf-8"), indent=1, default=str)
    say("RESULTS", {k: (v["seconds"], {x: v["final"].get(x) for x in ("dst_equals_src", "shells", "same_key_rows",
                                                                        "orphan_layers", "type_mismatch", "set_aside")})
                    for k, v in results.items()})


if __name__ == "__main__":
    main()
