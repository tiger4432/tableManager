import json, os, re
base = json.load(open("runs_base/gen_results.json", encoding="utf-8"))
rer = json.load(open("runs_rerun/gen_results.json", encoding="utf-8"))
cases = {}
for f in ("gen_base.out", "gen_base2.out", "gen_rerun.out", "gen_rerun_g23.out"):
    for line in open(f, encoding="utf-8"):
        m = re.search(r"=== CASE (g\d+t?) (\{.*\})", line)
        if m: cases[m.group(1)] = json.loads(m.group(2))
def dll(n, runs):
    p = "%s/%s/chain_worker.log" % (runs, n)
    return os.path.exists(p) and "DLL load failed" in open(p, encoding="utf-8", errors="replace").read()
final = {}
for n in set(base) | set(rer):
    src = "rerun" if n in rer else "base"
    v = (rer if n in rer else base)[n]
    final[n] = (v, src, dll(n, "runs_rerun" if src == "rerun" else "runs_base"))
out = []
for n in sorted(final, key=lambda k: (int(re.sub(r"\D", "", k)), k)):
    (v, src, env) = final[n]; c = cases.get(n, {})
    out.append({"n": n, "src": src, "kind": c.get("derive<>"), "path": c.get("board.path"), "type": c.get("board.column_type"),
                "fn": c.get("derive.<join>.take.[].<record>.fn") or c.get("derive.<join>.take.[]<>") or c.get("derive.<mapper>.mapper") or c.get("derive.<decide>.aggregations.[]<>"),
                "kill": v["kill"], "verdict": v["verdict"], "hr": v.get("human_recovery"), "env": env, "extra": c.get("board.extra", ""),
                "oracle": (v.get("final") or {}).get("oracle")})
json.dump(out, open("final.json", "w", encoding="utf-8"), indent=1, default=str)
print("runs", len(out), "green", sum(o["verdict"] == "GREEN" for o in out), "rerun", sum(o["src"] == "rerun" for o in out))
for o in out:
    if o["verdict"] != "GREEN":
        print(o["n"], o["src"], o["kind"], o["fn"], o["path"], o["type"], o["kill"], "|", o["verdict"][:70], "| hr", o["hr"], "| env" if o["env"] else "", o["extra"], "|", json.dumps(o["oracle"])[:150] if o["oracle"] and not o["oracle"].get("ok", True) else "")
