"""The «fetch» column's board table -> task/APPLICATION_CONTRACT_BOARD_FETCH.md (CRLF).
env: FETCH_RUNS (a gen_results.json folder) · FETCH_HASH (the commit the boards ran on) · FETCH_OUT (the md path)."""
import collections
import json
import os
import sys

os.environ["BOARD_COLUMN"] = "fetch"
sys.argv = [sys.argv[0], os.environ.get("BOARD_WT", "C:/wt-app-board")]
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board_gen as G  # noqa: E402

runs, h, out_path = os.environ["FETCH_RUNS"], os.environ["FETCH_HASH"], os.environ["FETCH_OUT"]
results = json.load(open(os.path.join(runs, "gen_results.json"), encoding="utf-8"))
chosen, _ = G.cases()
assert len(chosen) == 47, len(chosen)                       # canary: the fetch column, not the write one

#: the «after» column: FETCH_AFTER_RUNS · FETCH_AFTER_HASH - the verdict there, and what moved against the baseline
#: (target rows · layers with a row's id folded · events)
after_runs, after_hash = os.environ.get("FETCH_AFTER_RUNS"), os.environ.get("FETCH_AFTER_HASH")
after = json.load(open(os.path.join(after_runs, "gen_results.json"), encoding="utf-8")) if after_runs else {}
after_reasons = collections.Counter()


def after_cell(name, base):
    r = after.get(name)
    if not r:
        return ""
    v = r["verdict"] if r["verdict"].startswith("BOARD ERROR") else G.verdict(r["final"], r["kill"])
    after_reasons.update(p.split(" (R ")[0].split(" (W ")[0] for p in v.replace("RED: ", "").split(", "))
    x, y = (base or {}).get("final", {}), r["final"]
    moved = [n for n, p, q in (
        ("rows", (x.get("snapshot") or {}).get("dst"), (y.get("snapshot") or {}).get("dst")),
        ("layers", (G.same_run(x.get("snapshot")) or {}).get("layers_by_source"),
         (G.same_run(y.get("snapshot")) or {}).get("layers_by_source")),
        ("events", x.get("events"), y.get("events"))) if p != q]
    return "%s · R %s · %s" % (v, y.get("reads", {}).get("R", "-"), "same" if not moved else "moved " + "/".join(moved))


rows, reasons = [], collections.Counter()
for i, c in enumerate(chosen):
    r = results.get("g%02d" % i)
    # judged again from what the board saw, by today's verdict (group_by became a gate cell mid-run, owner 10-22)
    verdict = (r["verdict"] if r["verdict"].startswith("BOARD ERROR") else G.verdict(r["final"], r["kill"])) if r \
        else "NOT RUN"
    reads = (r or {}).get("final", {}).get("reads") or {}
    for part in verdict.replace("RED: ", "").split(", "):
        reasons[part.split(" (R ")[0].split(" (W ")[0]] += 1
    rows.append("| g%02d | %s | %s | %s | %s | R %s · W %s · D %s | %s |" % (
        i, c["board.shape"], c["board.path"], c["board.fetch_target"], verdict,
        reads.get("R", "-"), reads.get("W", "-"), reads.get("D", "-"), after_cell("g%02d" % i, r)))

head = [
    "# 체인 계약판 «받기» 열 — 기준 판 (응용 C, 2026-10-22)",
    "",
    "지시 78eec1ec1 게이트 [C]. 도구 `server/tests/contract_board/` (`BOARD_COLUMN=fetch`), 버리는 DB 에서 판 하나씩.",
    "기준 = main `%s` (받기 좌석 착지 전). 「착지 뒤」 칸은 B 착지 뒤 같은 판으로 채운다." % h,
    "",
    "판정 칸: 끝 값(오라클) · 껍데기 · 같은 키 · 고아 층 · 치워 둔 것 · 타입 — 쓰기 열과 같음. 더해 «읽은 자리»:",
    "R = `rule_run.run_rule` 안에서 판 표를 읽은 SELECT 수, W = `hold_commit` 쥔 동안 대상 표 말고 읽은 수.",
    "둘 다 0 이어야 초록 (총괄 10-22). 맵퍼 자신의 `sql()` 판(own sql)은 R 이 남고 «reads outside the fetch» 줄로 판정.",
    "group_by 의 끝 값 = 그 키의 행 «전체»로 센 수 (소유자 10-22 넓힘 승인 — 기준에서 빨강, 착지 뒤 초록).",
    "",
    "## 요약 — 판정 낱말별 판 수" + (" (착지 뒤 = `%s`)" % after_hash if after_hash else ""),
    "",
    "| 낱말 | 기준 | 착지 뒤 |",
    "|---|---|---|",
] + ["| %s | %d | %s |" % (k, reasons.get(k, 0), after_reasons.get(k, 0) if after else "")
     for k in sorted(set(reasons) | set(after_reasons), key=lambda x: -reasons.get(x, 0))] + [
    "",
    "## 판마다",
    "",
    "| 판 | 꼴 | 경로 | 받기 대상 | 기준 | 읽은 수 | 착지 뒤 |",
    "|---|---|---|---|---|---|---|",
]
open(out_path, "wb").write("\r\n".join(head + rows + [""]).encode("utf-8"))
print("wrote", out_path, "rows", len(rows), "reasons", dict(reasons))
