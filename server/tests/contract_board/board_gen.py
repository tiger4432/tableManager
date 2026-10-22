"""Contract board generator - the «write» column first (owner 10-21 fold order ㄱ 쓰기 → ㄴ 받기 → ㄷ 리스트 · 그룹,
order 09f58844f): option axes read from the product's skeleton (no hand list), greedy all-pairs over them and the
board's own axes - path · column type · kill point - one board per case on the real launcher (board_fixed.Board).

  board_gen.py <worktree> --list                    the axes and the cases (no database)
  board_gen.py <worktree> --check                   each case's declaration through the product loader in process, on
                                                    a throwaway sqlite data root - which stand, which are refused by name
  board_gen.py <worktree> <runs> --run [i ...]      run cases on assy_test (all when none named); the results and each
                                                    case's final snapshot go to <runs>/gen_results.json
  board_gen.py <worktree> --compare <a.json> <b.json>  two runs' cases, side by side: «same rows · same layers · same
                                                    events» or what moved

Judged on every board: shells 0 · same key new row 0 · column types · orphan layers · set aside 0 · outbox failed 0.
An oracle where the kind has one: a copy mapper's target is its source; a join's target cell is its value row's
(or the aggregate of them). A decide has none here - a killed decide is judged against its own unkilled twin."""
import decimal
import itertools
import json
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

WT = sys.argv[1]
SRC, VAL, DST, DEC = "bd_src", "bd_val", "bd_dst", "bd_dec"
PORT0 = int(os.environ.get("BOARD_PORT0", "18800"))   # a second run beside the first takes another range

# --- the axes ---------------------------------------------------------------------------------------------------------
#: the value a number leaf takes when written - «absent» is always the other
NUMBER = {"limits.max_group_rows": 4, "limits.max_group_attempts": 2, "limits.rows_per_run": 2,
          "derive.<decide>.reference_views.[].limit": 5}
MAPPERS = ["board_copy", "board_pick_columns"]
#: the order's paths: 넣기 · 편집 · 지움 · 리플레이 · 파일 교체 · R2
PATHS = ["insert", "edit", "delete", "replay", "file_replace", "r2"]
COLUMN_TYPES = ["string", "number", "datetime"]
#: the order's kill points: 쓰기 사이 · 거두기 사이 · 껍데기 앞 · 처리됨 앞 · 처리됨 뒤 (pkg/sitecustomize.SEAMS)
KILLS = ["none", "after_write", "withdrawn_before_tell", "before_shells", "before_mark", "after_mark"]
CHAIN_PATHS = {"insert", "edit", "delete", "replay", "file_replace"}
#: where a kill point can be reached at all - elsewhere the board would never die (a case is not drawn there)
KILL_REACHED_ON = {"none": set(PATHS), "after_write": CHAIN_PATHS, "before_mark": CHAIN_PATHS,
                   "after_mark": CHAIN_PATHS, "withdrawn_before_tell": {"edit", "delete"},
                   "before_shells": {"edit", "delete", "file_replace", "r2"}}


def skeleton_axes():
    """[(path, values)] - every option leaf of the unified grammar, walked from the skeleton the form draws."""
    sk = json.load(open(os.path.join(WT, "server", "chain_skeleton.json"), encoding="utf-8"))
    axes = []

    def walk(node, path):
        kind = node.get("kind")
        if kind == "leaf":
            hint, name = node.get("hint"), ".".join(path)
            if name == "enabled":
                return                                  # «off» stands no rule - one board of its own (EXTRA), not paired
            if hint == "flag":
                axes.append((name, [None, True]))
            elif hint == "number":
                axes.append((name, [None, NUMBER.get(name, 2)]))
            elif hint == "choice" and node.get("list") == "aggregation_functions":
                axes.append((name, [None] + aggregation_functions()))
            elif hint == "choice" and name.endswith("mapper"):
                axes.append((name, MAPPERS))
            elif name == "limits.group_by.[]":
                axes.append(("limits.group_by", [None, ["m"]]))
            return
        if kind == "record":
            for field in node["fields"]:
                walk(field["node"], path + [field["key"]])
        elif kind == "map":
            walk(node["of"], path + ["[]"])
        elif kind == "oneOf":
            branches = [b for b, v in node["branches"].items() if isinstance(v, dict) and "kind" in v]
            if len(branches) > 1:
                axes.append((".".join(path) + "<>", branches))
            for b in branches:
                walk(node["branches"][b], path + ["<%s>" % b])
    walk(sk["unified_root"], [])
    return axes


def aggregation_functions():
    sys.path.insert(0, os.path.join(WT, "server"))
    from chain.enrichment import config
    return list(config.AGGREGATION_FUNCTIONS)


#: the step runs in a process that never ran the rule (lead 10-21: «slots two») - the launcher restarts after the seed,
#: so the process memory a rule's judgement lives in (`rule_run._ORIGIN_SEEN`) is empty when the step comes
FRESH = [False, True]


def axes():
    return skeleton_axes() + [("board.path", PATHS), ("board.column_type", COLUMN_TYPES), ("board.kill", KILLS)]


# --- which values a case may hold together ------------------------------------------------------------------------------
def _branch_of(name):
    """'derive.<join>.take…' -> [('derive<>', 'join'), …] - the branches a leaf lives under."""
    out, parts = [], name.split(".")
    for i, part in enumerate(parts):
        if part.startswith("<") and part.endswith(">"):
            out.append((".".join(parts[:i]) + "<>", part[1:-1]))
    return out


def active(name, case):
    return all(case.get(axis) == branch for axis, branch in _branch_of(name))


#: pairs the product refuses by name (loader, measured by --check) - not drawn into the pairing; REFUSED_BOARDS
#: keeps one case of each so the refusal itself stays a board
def refused(case):
    fn = case.get("derive.<join>.take.[].<record>.fn")
    if case.get("key.unique") is True and fn not in (None, "na"):
        return "key.unique with a take fn"
    if case["derive<>"] == "mapper" and case.get("allow_retraction") and case.get("allow_replace_map"):
        return "allow_retraction with allow_replace_map"
    if case["derive<>"] == "mapper" and (case.get("allow_retraction") or case.get("allow_replace_map"))             and not case.get("is_batch"):
        return "a removal flag without is_batch"
    if fn in ("min", "max") and case["board.column_type"] == "string":
        return "min or max over a string column"
    return None


def allowed(case):
    for name, value in case.items():
        if (value == "na") == active(name, case):
            return False
    return case["board.path"] in KILL_REACHED_ON[case["board.kill"]] and not refused(case)


def cases(seed=1):
    """Greedy all-pairs: every pair of values two axes can hold together, in as few cases as the greedy finds."""
    ax = axes()
    names = [n for n, _ in ax]
    values = dict(ax)
    rnd = random.Random(seed)

    def candidate():
        case = {"derive<>": rnd.choice(values["derive<>"])}
        for _ in range(2):                              # outer branch first, then the branches inside it
            for name in names:
                if name != "derive<>":
                    case[name] = (case.get(name) if case.get(name) not in (None, "na") and active(name, case)
                                  else rnd.choice(values[name]) if active(name, case) else "na")
        return case

    def pairs(case):
        return {(a, repr(case[a]), b, repr(case[b])) for a, b in itertools.combinations(names, 2)
                if case[a] != "na" and case[b] != "na"}

    pool = [c for c in (candidate() for _ in range(6000)) if allowed(c)]
    held = [pairs(c) for c in pool]                     # each candidate's pairs, counted once
    need = set().union(*held)
    chosen = []
    while need:
        at = max(range(len(pool)), key=lambda j: len(held[j] & need))
        best, got = pool[at], held[at] & need
        if not got:
            break
        need -= got
        chosen.append(best)
    return chosen + extras(chosen), len(need)


def extras(chosen):
    """The boards not drawn by pairing: a rule switched off (nothing stands, the target untouched) and one board of
    each pair the product refuses by name (judged by --check, in process - no database)."""
    def first(derive):
        return dict(next(c for c in chosen if c["derive<>"] == derive), **{"board.kill": "none", "board.path": "insert"})
    off = dict(first("mapper"), enabled=False, **{"board.extra": "off"})
    fn_unique = dict(first("join"), **{"key.unique": True, "derive.<join>.take.[]<>": "record",
                                       "derive.<join>.take.[].<record>.fn": "count",
                                       "board.extra": "refused: " + "key.unique with a take fn"})
    two_removals = dict(first("mapper"), allow_retraction=True, allow_replace_map=True,
                        **{"board.extra": "refused: allow_retraction with allow_replace_map"})
    needs_batch = dict(first("mapper"), allow_replace_map=True, allow_retraction=None, is_batch=None,
                       **{"board.extra": "refused: a removal flag without is_batch"})
    minmax_text = dict(first("join"), **{"key.unique": None, "derive.<join>.take.[]<>": "record",
                                         "derive.<join>.take.[].<record>.fn": "min", "board.column_type": "string",
                                         "board.extra": "refused: min or max over a string column"})
    # «a process that never ran the rule» (lead 10-21: out of the pairing, three boards of its own) - the step that
    # needs the rule's memory: a deletion and a key edit
    fresh = [dict(first(d), **{"board.path": p, "board.fresh_process": True, "board.extra": "fresh process"})
             for d, p in (("mapper", "delete"), ("join", "delete"), ("decide", "edit"))]
    # the known reds (lead 10-21: they must come out red on the baseline) - plain declarations, nothing else written
    def plain(derive, **cells):
        case = first(derive)
        for k in list(case):
            if k.startswith(("limits.", "key.", "allow_", "is_batch")) and case[k] != "na":
                case[k] = None
        if derive == "mapper":
            case["derive.<mapper>.mapper"] = "board_copy"
        case.update(cells)
        return case
    known = [plain("mapper", **{"board.path": "delete", "board.kill": "after_mark", "board.extra": "known red f4k"}),
             plain("mapper", **{"board.path": "edit", "board.kill": "withdrawn_before_tell",
                                "board.extra": "known red: withdrawn, EDIT not staged"}),
             plain("mapper", **{"board.path": "r2", "board.kill": "before_shells",
                                "board.extra": "known red: R2 withdrawn, shells not deleted"}),
             plain("mapper", **{"derive.<mapper>.mapper": "board_pick_columns", "board.path": "delete",
                                "board.extra": "known red f4n: origin lost (delete)"}),
             plain("mapper", **{"derive.<mapper>.mapper": "board_pick_columns", "board.path": "edit",
                                "board.extra": "known red f4n: origin lost (key edit)"})]
    return [off, fn_unique, two_removals, needs_batch, minmax_text] + fresh + known


# --- a case as a declaration and tables ---------------------------------------------------------------------------------
def trigger_of(case):
    return VAL if case["derive<>"] == "join" else SRC


def target_of(case):
    return DEC if case["derive<>"] == "decide" else DST


def rule_of(case, name):
    """The unified declaration a case writes - only the cells it sets."""
    derive = case["derive<>"]
    rule = {"name": name, "on": {"table": trigger_of(case)}, "into": {"table": target_of(case)}}
    for flag in ("enabled", "is_batch", "allow_chain_trigger", "allow_map_metadata_upsert", "allow_delete_trigger",
                 "allow_replace_map", "allow_retraction"):
        if case.get(flag) not in (None, "na"):
            rule[flag] = case[flag]
    if case.get("key.unique") not in (None, "na"):
        rule["key"] = {"unique": case["key.unique"]}
    limits = {k.split(".", 1)[1]: v for k, v in case.items() if k.startswith("limits.") and v not in (None, "na")}
    if limits:
        rule["limits"] = limits
    if derive == "mapper":
        rule["derive"] = {"kind": "mapper", "mapper": {"mapper": case["derive.<mapper>.mapper"]}}
    elif derive == "join":
        take = ["w"]
        if case["derive.<join>.take.[]<>"] == "record":
            fn = case.get("derive.<join>.take.[].<record>.fn")
            take = [{"from": "w", "into": "w"} if fn in (None, "na") else {"from": "w", "into": "wn", "fn": fn}]
        rule["derive"] = {"kind": "join", "join": {"on": [{"left": "k", "right": "k"}], "take": take}}
    else:
        agg = ({"n": "count"} if case["derive.<decide>.aggregations.[]<>"] == "expression"
               else {"n": {"fn": "max", "column": "v"}})
        view = {"label": "values of this map", "query": "SELECT v, COUNT(*) AS cells FROM %s WHERE m = :m GROUP BY v"
                % SRC, "candidate_for": {"v": "v"}}
        if case.get("derive.<decide>.reference_views.[].limit") not in (None, "na"):
            view["limit"] = case["derive.<decide>.reference_views.[].limit"]
        decide = {"key": ["m"], "fields": ["v"], "list_columns": ["n"], "aggregations": agg, "reference_views": [view]}
        for flag in ("auto_confirm", "alignment"):
            if case.get("derive.<decide>." + flag) not in (None, "na"):
                decide[flag] = case["derive.<decide>." + flag]
        rule["derive"] = {"kind": "decide", "decide": decide}
    return rule


def tables_of(case, base):
    """table_config for a case: four tables, `v` and `w` of the case's column type; the trigger table takes a file
    that replaces its maps on the file path."""
    kind = case["board.column_type"]
    t = {k: v for k, v in base.items() if k.startswith("_")}
    t[SRC] = {"business_key": "k", "composite_key_source": ["k"], "map_key_columns": ["m"],
              "column_types": {"k": "string", "m": "string", "v": kind}}
    t[VAL] = {"business_key": "k", "composite_key_source": ["k"], "map_key_columns": ["m"],
              "column_types": {"k": "string", "m": "string", "w": kind}}
    t[DST] = {"business_key": "k", "composite_key_source": ["k"], "map_key_columns": ["m"],
              "column_types": {"k": "string", "m": "string", "v": kind, "w": kind, "wn": "string"}}
    t[DEC] = {"business_key": "m", "composite_key_source": ["m"],
              "column_types": {"m": "string", "v": kind, "n": "string"}}
    for table in (SRC, VAL, DST, DEC):
        t[table]["display_columns"] = list(t[table]["column_types"])
    if case["board.path"] == "file_replace":
        t[trigger_of(case)].update(allow_replace_map=True, std_parse=True)
    return t


def value(kind, i):
    return {"string": "s%d" % i, "number": i, "datetime": "2026-01-%02dT00:00:00" % i}[kind]


# --- the modes that need no database ----------------------------------------------------------------------------------
def list_mode():
    ax = axes()
    print("AXES %d" % len(ax))
    for name, vals in ax:
        print("  %-48s %s" % (name, vals))
    chosen, left = cases()
    print("CASES %d (pairs left uncovered %d)" % (len(chosen), left))
    for i, c in enumerate(chosen):
        print("  %2d %s" % (i, json.dumps({k: v for k, v in c.items() if v not in ("na", None)}, ensure_ascii=False)))


def check_mode():
    """Each case's declaration through `load_chain_rules` on a throwaway sqlite data root - no assy_test."""
    import logging
    import tempfile
    root = tempfile.mkdtemp(prefix="board_gen_")      # the data root BEFORE any product module reads it (paths)
    os.makedirs(os.path.join(root, "config", "ontology"))
    os.environ.update(ASSY_DATA_ROOT=root, DATABASE_URL="sqlite:///" + os.path.join(root, "box.db").replace("\\", "/"))
    os.environ.pop("ASSY_SCRATCH_SCHEMA", None)
    chosen, _left = cases()
    base = json.load(open(os.path.join(WT, "server/config/sample/table_config.json.sample"), encoding="utf-8"))
    sys.path.insert(0, os.path.join(WT, "server"))
    seen = []

    class Grab(logging.Handler):
        def emit(self, record):
            if record.levelno >= logging.WARNING and "[ChainRules]" in record.getMessage():
                seen.append(record.getMessage())
    from database import crud, models
    from chain import ingestion_worker as iw
    for logger in [logging.getLogger()] + [logging.getLogger(n) for n in list(logging.Logger.manager.loggerDict)]:
        logger.addHandler(Grab())                       # the product's loggers do not all reach the root
    assert os.path.normcase(iw.RULES_PATH).startswith(os.path.normcase(root)), iw.RULES_PATH   # canary: not the box's
    stood_n = 0
    for i, case in enumerate(chosen):
        name = "board_g%02d" % i
        t = tables_of(case, base)
        json.dump(t, open(os.path.join(root, "config", "table_config.json"), "w", encoding="utf-8"))
        json.dump({"rules": [rule_of(case, name)]}, open(iw.RULES_PATH, "w", encoding="utf-8"))
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(t)
        models.init_dynamic_models(t)
        del seen[:]
        stood = [r.get("name") for r in iw.load_chain_rules()]
        stood_n += bool(stood)
        said = [line for line in seen if name in line]
        print("%2d %-6s %-12s %-22s %s" % (i, case["derive<>"], case["board.path"], case["board.kill"],
                                           ("STANDS " + ",".join(stood)) if stood else
                                           ("REFUSED " + (said[0][:170] if said else "(no line)"))))
    print("STAND %d · REFUSED %d" % (stood_n, len(chosen) - stood_n))


# --- running a case ---------------------------------------------------------------------------------------------------
def run_cases(runs, wanted):
    import board_fixed as F
    F.WT, F.RUNS = WT, runs
    base = json.load(open(os.path.join(WT, "server/config/sample/table_config.json.sample"), encoding="utf-8"))
    ledger = json.load(open(os.path.join(WT, "server/config/sample/ledger_config.json.sample"), encoding="utf-8"))
    ledger["sources"] = {}
    chosen, _left = cases()
    out_path = os.path.join(runs, "gen_results.json")
    results = json.load(open(out_path, encoding="utf-8")) if os.path.exists(out_path) else {}
    for i in (wanted or range(len(chosen))):
        case = chosen[i]
        twin = case["board.kill"] != "none" and (case["derive<>"] == "decide"
                                                 or str(case.get("board.extra", "")).startswith("known red"))
        runs_of = [case["board.kill"]] + (["none"] if twin else [])
        if str(case.get("board.extra", "")).startswith("refused"):
            F.say("=== CASE %d is a refusal - judged by --check, not run" % i)
            continue
        for kill in runs_of:
            name = "g%02d%s" % (i, "" if kill == case["board.kill"] else "t")      # t = a decide's unkilled twin
            try:
                results[name] = run_one(F, i, name, case, kill, base, ledger)
            except Exception as e:                              # the board's own instrument broke - say it, go on
                F.say("BOARD ERROR", name, repr(e)[:300])
                results[name] = {"case": i, "kill": kill, "seconds": 0, "verdict": "BOARD ERROR: %s" % repr(e)[:120],
                                 "human_recovery": None, "final": {}}
            broke = any(results[n]["verdict"].startswith("BOARD ERROR") for n in (name[:-1], name) if n in results)
            if name.endswith("t") and not broke:                # the killed board against its unkilled twin
                killed, calm = results[name[:-1]], results[name]
                # rows · layers, and the TARGET's events: the rerun of what was set aside stages trigger events of
                # its own, so the trigger table's events are not compared
                tgt = target_of(case)
                moved = [k for k, x, y in (
                    ("snapshot", same_run(killed["final"].get("snapshot")), same_run(calm["final"].get("snapshot"))),
                    ("target events", [e for e in killed["final"].get("events") or () if e[0] == tgt],
                     [e for e in calm["final"].get("events") or () if e[0] == tgt])) if x != y]
                if moved:
                    killed["verdict"] = (("RED: " if killed["verdict"] == "GREEN" else killed["verdict"] + ", ")
                                         + "differs from its unkilled twin (%s)" % "/".join(moved))
            json.dump(results, open(out_path, "w", encoding="utf-8"), indent=1, default=str)
    F.say("GEN RESULTS", {k: (v["seconds"], v["verdict"], "human recovery" if v.get("human_recovery") else "")
                          for k, v in results.items()})


def same_run(snapshot):
    """A snapshot with a per-row chain layer's row id folded - «chain_ingestion (<row id>)» names a row two runs mint
    apart (crud.layer_ranks_as), so a killed board and its twin differ there and nowhere else (10-22 g83 · g84)."""
    import re
    if not snapshot:
        return snapshot
    return dict(snapshot, layers_by_source=sorted({re.sub(r" \([^)]*\)$", " (row)", x)
                                                    for x in snapshot.get("layers_by_source") or ()}))


def run_one(F, i, name, case, kill, base, ledger):
    rule_name = "board_" + name
    t = tables_of(case, base)
    trig, tgt, kind = trigger_of(case), target_of(case), case["board.column_type"]
    col = "w" if trig == VAL else "v"
    b = F.Board(name, PORT0 + i, None if kill == "none" else kill)
    b.name = name
    F.say("=== CASE %s %s" % (name, json.dumps({k: v for k, v in case.items() if v not in ("na", None)})))

    def write_config(b):
        cfg = os.path.join(b.root, "config")
        os.makedirs(os.path.join(cfg, "ontology"), exist_ok=True)
        json.dump(t, open(os.path.join(cfg, "table_config.json"), "w", encoding="utf-8"), indent=1)
        json.dump({"rules": [rule_of(case, rule_name)]}, open(os.path.join(cfg, "chain_rules.json"), "w",
                                                              encoding="utf-8"), indent=1)
        json.dump(ledger, open(os.path.join(cfg, "ontology", "ledger_config.json"), "w", encoding="utf-8"), indent=1)

    def put(table, items):
        code, body = b.call("PUT", "/tables/%s/data/updates" % table, {"updates": items})
        assert code == 200, (code, body)

    def rows(table, n, extra):
        return [{"business_key_val": "K%d" % j, "updates": dict({"k": "K%d" % j, "m": "M%d" % (1 + (j - 1) // 3)},
                                                                **extra(j)), "source_name": "user"} for j in n]

    def look(tag):
        return F.settle(b, tag, (trig, tgt))

    seen = {}

    def seed(b):
        if trig == VAL:                                         # a join writes onto target rows that are there
            put(DST, rows(DST, range(1, 7), lambda j: {}))
        put(trig, rows(trig, range(1, 7), lambda j: {col: value(kind, j)}))
        seen["seeded"] = look("seeded")
        seen["keys"] = {r[0] for r in b.q('SELECT k FROM "%s"' % trig)}
        return seen["seeded"]

    def step(b):
        if case.get("board.fresh_process"):
            b.stop()
            F.say("fresh process /health", b.start())
        if kill != "none":
            open(b.flag + ".arm", "w").close()                  # the seam dies from here on - not in the seed
        path = case["board.path"]
        if path == "insert":
            put(trig, rows(trig, (7, 8), lambda j: {col: value(kind, j)}))
        elif path == "edit":
            put(trig, [{"row_id": b.rid(trig, "K4"), "updates": {col: value(kind, 9)}, "source_name": "user"},
                       {"row_id": b.rid(trig, "K2"), "updates": {"k": "K2X"}, "source_name": "user"}])
        elif path == "delete":
            code, body = b.call("POST", "/tables/%s/rows/batch_delete" % trig, {"row_ids": [b.rid(trig, "K5")],
                                                                              "user_name": "board"})
            assert code == 200, (code, body)
        elif path == "replay":
            # a decide loads as «enrichment_dedup:<name>» + «enrichment_auto_confirm:<name>»; replay takes the loaded
            # name only (the declared one is REFUSED, exit 2) - the trigger side is the dedup
            loaded = ("enrichment_dedup:" + rule_name) if case["derive<>"] == "decide" else rule_name
            secs, code, tail = b.cli(["python", "scripts/chain_replay_cli.py", "replay", loaded, "--apply"])
            F.say("replay", secs, code, *(tail[-3:] if code else ()))
            assert code == 0, ("replay refused", tail[-3:])
        elif path == "file_replace":
            raws = os.path.join(b.root, "ingestion_workspace", trig, "raws")
            os.makedirs(raws, exist_ok=True)
            with open(os.path.join(raws, "%s_m1.csv" % trig), "w", encoding="utf-8", newline="") as f:
                f.write("k,m,%s\n" % col)                       # map M1 again: K1 changed, K3 gone, K9 new
                for k, j in (("K1", 7), ("K2", 2), ("K9", 9)):
                    f.write("%s,M1,%s\n" % (k, value(kind, j)))
        elif path == "r2":
            # R2 «the table's chain layers, whole» - `--rule` narrows to columns outside a target_columns list,
            # which these rules do not write (REFUSED, exit 2)
            secs, code, tail = b.cli(["python", "scripts/chain_replay_cli.py", "withdraw", tgt, "chain_ingestion",
                                      "--apply"])
            F.say("r2", secs, code, *(tail[-3:] if code else ()))
        killed = F.wait_killed(b, limit=90) if kill != "none" else None
        # «did a person have to recover it» (lead 10-21: a gate cell - yes before the write fold, no after it): what
        # the dead slot set aside, run again by the operator's own command
        aside, partial, rounds = 0, None, 0
        b.settle(quiet=6, limit=600)
        if killed:
            # «one group, one commit» (lead 10-22): after the kill and before any rerun, the target as it was seeded -
            # the killed group left nothing of its own
            held = look("after kill")
            # less what the set-aside took back by design (lead 10-22): set_aside's «a deletion set aside still
            # happened» withdraws the cells a trigger row deleted since the seed fed - on the target row of the same k,
            # gone or its cells emptied. Every other target row as seeded, and no row more
            gone = seen["keys"] - {r[0] for r in b.q('SELECT k FROM "%s"' % trig)}
            have = {r[0]: r for r in held["snapshot"]["dst"]}
            was = {r[0]: r for r in seen["seeded"]["snapshot"]["dst"]}
            took = [k for k in was if tgt == DST and k in gone and have.get(k) != was[k]
                    and (k not in have or all(x is None or x == y for x, y in zip(have[k], was[k])))]
            partial = set(have) - set(was) != set() or any(have.get(k) != r for k, r in was.items() if k not in took)
            F.say("partial write", partial, "target rows the set-aside took back", len(took))
        # a dead slot sets its line aside by design (owner 10-22) - a killed one, or a child the box's DLL load killed
        # on the twin; the operator's command runs it again, up to three times for the box's repeat deaths
        # a rerun stages events of its own and leaves the set-aside ones marked - each round counts the ones set
        # aside since the last
        after = 0
        while rounds < 3:
            left, top = b.q("SELECT count(*), coalesce(max(id), 0) FROM database_outbox "
                            "WHERE payload::jsonb ? 'cancelled_by' AND id > %d" % after)[0]
            if not left:
                break
            after = top
            aside, rounds = aside or left, rounds + 1
            F.say("rerun set aside", rounds, left, b.cli(["python", "scripts/outbox_triage.py", "--rerun-set-aside",
                                                          "--tables", trig, "--apply"])[:2])
            b.settle(quiet=6, limit=600)
        out = look("after %s" % path)
        out["human_recovery"] = bool(aside)
        out["rerun_rounds"] = rounds
        # what is still set aside and was never run again - the twin's «set aside» red (marks stay on rerun ones)
        out["left_aside"] = b.q("SELECT count(*) FROM database_outbox WHERE payload::jsonb ? 'cancelled_by' "
                                "AND id > %d" % after)[0][0]
        out["partial_write"] = partial
        out["killed"] = killed
        out["oracle"] = oracle(b, case, trig, tgt, kind)
        out["events"] = b.q("SELECT table_name, event_type, count(*) FROM database_outbox WHERE table_name IN "
                            "(%s) GROUP BY 1, 2 ORDER BY 1, 2" % ", ".join("'%s'" % x for x in (SRC, VAL, DST, DEC)))
        return out

    secs, checks = F.run(b, None, [seed, step], write_config=write_config)
    final = checks[-1] if checks else {}
    return {"case": i, "kill": kill, "seconds": round(secs), "verdict": verdict(final, kill),
            "human_recovery": final.get("human_recovery"), "partial_write": final.get("partial_write"), "rerun_rounds": final.get("rerun_rounds"),
            "final": {k: v for k, v in final.items() if k != "schema"}}


def oracle(b, case, trig, tgt, kind):
    """What the target should hold, where the kind says it: None when it does not (a decide)."""
    if case["derive<>"] == "decide":
        return None
    off = case.get("enabled") is False or case["board.path"] == "r2"   # R2 takes the chain's writes out, whole
    if case["derive<>"] == "mapper":
        by = lambda t: tuple((x is None, x or "") for x in t)          # a blank cell next to a text one
        src = sorted([(str(k), str(m), None if v is None else str(v)) for k, m, v in b.q('SELECT k, m, v FROM "%s"' % SRC)], key=by)
        dst = sorted([(str(k), str(m), None if v is None else str(v)) for k, m, v in b.q('SELECT k, m, v FROM "%s"' % DST)], key=by)
        want = [] if off else src
        return {"ok": dst == want, "missing": [r for r in want if r not in dst][:4],
                "extra": [r for r in dst if r not in want][:4]}
    val = {str(k): w for k, w in b.q('SELECT k, w FROM "%s"' % VAL)}
    fn = case.get("derive.<join>.take.[].<record>.fn")
    cell = "wn" if fn not in (None, "na") else "w"
    bad = []
    for k, got in b.q('SELECT k, %s FROM "%s"' % (cell, DST)):
        if off:
            want = None
        elif fn in (None, "na"):
            want = val.get(str(k))
        else:
            want = {"count": 1, "min": val.get(str(k)), "max": val.get(str(k)),
                    "unique_concat": val.get(str(k))}[fn] if str(k) in val else None
        # a value landed in the text cell `wn` is spelled as the product spells it: a datetime ISO ('T'), a whole
        # number without '.0' - str() of the typed column spells ' ' and '1.0'
        spell = lambda x: (None if x is None else x.isoformat() if hasattr(x, "isoformat")
                           else str(int(x)) if (isinstance(x, (float, decimal.Decimal)) and x == int(x))
                           else str(x))
        if spell(want) != spell(got):
            bad.append((str(k), spell(want), spell(got)))
    return {"ok": not bad, "wrong": bad[:4]}


def verdict(final, kill):
    if not final:
        return "NO CHECK"
    reds = [name for name, bad in (
        ("shells", final.get("shells")), ("same key rows", final.get("same_key_rows")),
        ("orphan layers", final.get("orphan_layers")), ("set aside", final.get("left_aside")),
        ("outbox failed", final.get("outbox_failed")), ("type mismatch", final.get("type_mismatch")),
        ("oracle", final.get("oracle") is not None and not final["oracle"]["ok"]),
        ("partial write", final.get("partial_write"))) if bad]
    if kill != "none" and final.get("killed") is False:
        reds.append("seam never reached")
    return "GREEN" if not reds else "RED: " + ", ".join(reds)


def compare_mode(a_path, b_path):
    """Two runs' gen_results, case by case: the target rows, layer count and events - the same, or what moved."""
    a, b = (json.load(open(p, encoding="utf-8")) for p in (a_path, b_path))
    for name in sorted(set(a) | set(b)):
        x, y = a.get(name, {}).get("final", {}), b.get(name, {}).get("final", {})
        moved = [k for k in ("snapshot", "events") if x.get(k) != y.get(k)]
        print("%-5s %-40s %-40s %s" % (name, a.get(name, {}).get("verdict", "-")[:40],
                                       b.get(name, {}).get("verdict", "-")[:40], "same" if not moved else
                                       "MOVED " + ",".join(moved)))


if __name__ == "__main__":
    if "--list" in sys.argv:
        list_mode()
    elif "--check" in sys.argv:
        check_mode()
    elif "--run" in sys.argv:
        at = sys.argv.index("--run")
        run_cases(sys.argv[2], [int(x) for x in sys.argv[at + 1:]])
    elif "--compare" in sys.argv:
        at = sys.argv.index("--compare")
        compare_mode(sys.argv[at + 1], sys.argv[at + 2])
    else:
        sys.exit(__doc__)
