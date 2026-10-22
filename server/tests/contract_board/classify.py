import json, os, re, sys
d = json.load(open("runs_base/gen_results.json", encoding="utf-8"))
cases = {}
for f in ("gen_base.out", "gen_base2.out"):
    for line in open(f, encoding="utf-8"):
        m = re.search(r"=== CASE (g\d+t?) (\{.*\})", line)
        if m: cases[m.group(1)] = json.loads(m.group(2))
def dll(n):
    p = "runs_base/%s/chain_worker.log" % n
    return os.path.exists(p) and "DLL load failed" in open(p, encoding="utf-8", errors="replace").read()
rows = []
for n in sorted(d, key=lambda k: (int(re.sub(r"\D", "", k)), k)):
    v, c = d[n], cases.get(n, {})
    tags = []
    if dll(n): tags.append("ENV-dll")
    if c.get("derive<>") == "decide" and c.get("board.path") == "replay": tags.append("INSTR-decide-replay")
    if c.get("derive<>") == "join" and c.get("board.column_type") == "datetime" and "oracle" in v["verdict"]: tags.append("INSTR-dt-spelling")
    rows.append((n, c.get("derive<>"), c.get("board.path"), c.get("board.column_type"), v["kill"], v["verdict"], v.get("human_recovery"), c.get("board.extra",""), tags))
for r in rows: print(" | ".join(str(x) for x in r))
print("runs", len(rows), "green", sum(r[5] == "GREEN" for r in rows))
