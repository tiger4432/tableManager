import json
o = json.load(open("final.json", encoding="utf-8"))
K = {"g83", "g84", "g85", "g86", "g87"}
P = {"g65", "g69", "g38", "g34", "g13", "g33"}
PE = {"g06", "g39", "g54"}
E = {"g00t", "g29t", "g48t", "g22", "g23", "g29", "g30", "g19"}
S = {"g32", "g57", "g62", "g44", "g58", "g00", "g48", "g05", "g21", "g35", "g60", "g53"}
KILL = {"none": "-", "after_write": "쓰기 뒤", "withdrawn_before_tell": "거두기 뒤 EDIT 앞", "before_shells": "껍데기 앞",
        "before_mark": "처리됨 앞", "after_mark": "처리됨 뒤"}
rows = []
for x in o:
    n = x["n"]
    g = ("알려짐" if n in K else "제품" if n in P else "제품+환경" if n in PE else "환경" if n in E
         else "빈칸" if n in S else "초록" if x["verdict"] == "GREEN" else "??")
    assert g != "??", n
    hr = "-" if x["kill"] == "none" else ("예" if x["hr"] else "아니오")
    rows.append("| %s | %s %s | %s | %s | %s | %s | %s | |" % (
        n, x["kind"], x["fn"] or "", x["path"], x["type"], KILL[x["kill"]], g, hr))
counts = {}
for r in rows:
    g = r.split(" | ")[5]
    counts[g] = counts.get(g, 0) + 1
open("report_rows.md", "w", encoding="utf-8").write("\n".join(rows) + "\n")
print(len(rows), counts)
