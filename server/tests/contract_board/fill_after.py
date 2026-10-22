"""Fill the «착지 뒤» column of task/APPLICATION_CONTRACT_BOARD_WRITE.md and write its summary - every number from the
results files, none typed. usage: fill_after.py <doc path> [--dry]"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.argv, args = ["x", "C:/wt-app-board3", "runs_x"], sys.argv[1:]
sys.path.insert(0, HERE)
import board_gen as G  # noqa: E402

DOC, DRY = args[0], "--dry" in args
FIX_HASH = os.environ.get("BOARD_FIX_HASH", "7d8ec14e9")
FIX_WHAT = os.environ.get("BOARD_FIX_WHAT", "B 의 쓰기 합치기 + g26 고침(impl-b-writefold 7d8ec14e9)")
FIX = json.load(open(os.path.join(HERE, os.environ.get("BOARD_FIX_RUNS", "runs_fix"), "gen_results.json"), encoding="utf-8"))
OLD = json.load(open(os.path.join(HERE, "runs_after/gen_results.json"), encoding="utf-8"))
CHOSEN, _ = G.cases()
R2 = {"g33", "g85"}                        # the kill lands in the operator's withdraw command, not a chain group

WORDS = {"shells": "껍데기", "same key rows": "같은 키 행", "orphan layers": "고아 층", "set aside": "치워 둔 채",
         "outbox failed": "실패 사건", "type mismatch": "타입 불일치", "oracle": "오라클", "partial write": "부분 쓰기",
         "seam never reached": "안 닿음", "differs from its unkilled twin": "쌍둥이와 다름"}


def judged(results, name, rejudge):
    """-> the verdict's reds, the twin compared with a per-row layer's row id folded (G.same_run)."""
    r = results[name]
    if r["verdict"].startswith("BOARD ERROR"):
        return ["board error"]
    reds = [] if r["verdict"] == "GREEN" else [x.strip() for x in r["verdict"][len("RED: "):].split(",")]
    if rejudge:                             # the fix run: the verdict again from its final, today's verdict()
        v = G.verdict(r["final"], r["kill"])
        reds = [] if v == "GREEN" else [x.strip() for x in v[len("RED: "):].split(",")]
    reds = [x for x in reds if not x.startswith("differs from its unkilled twin")]
    twin = results.get(name + "t")
    if r["kill"] != "none" and twin and not twin["verdict"].startswith("BOARD ERROR"):
        case = CHOSEN[r["case"]]
        tgt = G.target_of(case)
        moved = [k for k, x, y in (
            ("snapshot", G.same_run(r["final"].get("snapshot")), G.same_run(twin["final"].get("snapshot"))),
            ("target events", [e for e in r["final"].get("events") or () if e[0] == tgt],
             [e for e in twin["final"].get("events") or () if e[0] == tgt])) if x != y]
        if moved:
            reds.append("differs from its unkilled twin")
    return reds


def cell(name):
    src, rejudge, mark = (FIX, True, "①") if name in FIX else (OLD, False, "②") if name in OLD else (None, 0, "")
    if src is None:
        return "안 돌림", None
    reds = judged(src, name, rejudge)
    if not reds:
        said = "초록"
    elif reds == ["seam never reached"]:
        said = "빈칸(안 닿음)"
    else:
        said = "빨강: " + " · ".join(WORDS.get(x, x) for x in reds) + (" (R2 명령)" if name in R2 else "")
    return "%s %s" % (said, mark), (mark, reds)


text = open(DOC, "rb").read().decode("utf-8")
lines = text.split("\r\n")
row = re.compile(r"^\| (g\d\dt?) \|")
got = {}
for i, line in enumerate(lines):
    m = row.match(line)
    if m and line.endswith("| |"):
        said, judged_ = cell(m.group(1))
        got[m.group(1)] = judged_
        lines[i] = line[:-len(" |")] + " " + said + " |"
filled = len(got)
assert filled == 102, filled                                    # the baseline's 102 runs, each row once

on_fix = {n: v for n, v in got.items() if v and v[0] == "①"}
green = lambda n: on_fix.get(n) is not None and not on_fix[n][1]
known = ["g83", "g84", "g85", "g86", "g87"]
product = ["g65", "g69", "g38", "g34", "g13", "g33"]
same_shape = ["g%02d" % i for i, c in enumerate(CHOSEN) if c["board.kill"] != "none"
              and not str(c.get("board.extra", "")).startswith("refused") and c["board.path"] in ("delete", "file_replace")]
reached = [n for n in same_shape if n in on_fix and on_fix[n][1] != ["seam never reached"]]
edits = ["g%02d" % i for i, c in enumerate(CHOSEN) if c["board.kill"] != "none"
         and not str(c.get("board.extra", "")).startswith("refused") and c["board.path"] == "edit"]
edits_reached = [n for n in edits if n in on_fix and on_fix[n][1] != ["seam never reached"]]
killed_fix = [n for n, v in on_fix.items() if not n.endswith("t") and FIX[n]["kill"] != "none"
              and v[1] != ["seam never reached"]]
partial = [n for n in killed_fix if FIX[n].get("partial_write")]
cells, cov = {}, set()
for i, c in enumerate(CHOSEN):
    if c["board.kill"] == "none" or str(c.get("board.extra", "")).startswith("refused"):
        continue
    cells.setdefault((c["board.kill"], c["board.path"]), []).append("g%02d" % i)
for k, names in cells.items():
    if any(n in on_fix and on_fix[n][1] != ["seam never reached"] for n in names):
        cov.add(k)
not_green = lambda names: "".join(" — 빨강 " + " · ".join(n for n in names if not green(n)) for _ in [0] if any(not green(n) for n in names))
by_kind = lambda names: "%d/%d" % (sum(1 for n in names if green(n)), len(names))
reds_fix = sorted(n for n, v in on_fix.items() if v[1] and v[1] != ["seam never reached"])
gaps_fix = sorted(n for n, v in on_fix.items() if v[1] == ["seam never reached"])
r2_red = [n for n in sorted(R2) if n in reds_fix]

summary = [
    "## 착지 뒤 (10-22) — ① %s · ② db9df5374" % FIX_HASH,
    "",
    "① = %s, 새 판 도구, 버리는 DB `assy_c_board_1022b`(돌린 뒤 지움). "
    "%d 판(쌍둥이 포함). ② = 합치기 첫 판 db9df5374 전체 판 — 슬롯 죽음이 «제자리에서 다시 돎»이던 때라 지금 코드와 다름, "
    "①에 없는 %d 판만 그것으로 채움. 박스 수 — 운영 주장이 아니다." % (FIX_WHAT, len(on_fix), filled - len(on_fix)),
    "",
    "| 게이트 (총괄 10-22) | ① 결과 |",
    "|---|---|",
    "| 알려진 빨강 다섯 초록 | %s%s |" % (by_kind(known), not_green(known)),
    "| 제품 빨강 여섯 초록 | %s%s |" % (by_kind(product), not_green(product)),
    "| g09 초록 | %s |" % ("초록" if green("g09") else "빨강"),
    "| 같은 꼴(죽임 × delete · file_replace) | %d 판 중 %d 판이 죽임에 닿음, 닿은 것 %s 초록 |" % (
        len(same_shape), len(reached), by_kind(reached)),
    "| 같은 꼴(죽임 × edit) | %d 판 중 %d 판이 죽임에 닿음, 닿은 것 %s 초록 |" % (
        len(edits), len(edits_reached), by_kind(edits_reached)),
    "| 부분 쓰기 없음 | 닿은 킬 판 %d 중 부분 쓰기 %d — %s |" % (
        len(killed_fix), len(partial), " · ".join(partial) or "없음"),
    "| 「죽임 자리 × 길」 칸 | %d 칸 중 %d 칸을 ①이 덮음 — 못 덮은 칸: %s |" % (
        len(cells), len(cov), " · ".join("%s × %s(%s)" % (k[0], k[1], " · ".join(cells[k])) for k in sorted(set(cells) - cov))
        or "없음"),
    "",
    "- 「사람 복구 = 예」는 킬 판에서 설계다(소유자 «슬롯 죽음은 다 원래대로 실패») — 게이트에서 뺌. "
    "킬 판은 «치워 둠 → `outbox_triage --rerun-set-aside` → 끝 값이 쌍둥이와 같음»이면 초록.",
    "- 부분 쓰기 칸 = «다시 돌리기 전 대상 표 = 씨앗 직후 대상 표 − 치워 두기가 설계대로 거둔 삭제 키의 행»(총괄 승인). "
    "그 행 수는 판 줄 «target rows the set-aside took back N»에 찍힘.",
    "- ① 빨강: %s. 빈칸(안 닿음): %s." % (" · ".join(reds_fix) or "없음", " · ".join(gaps_fix) or "없음"),
] + ([
    "- %s = 죽는 프로세스가 체인 묶음이 아니라 운영자 거두기 명령(R2 `chain_replay_cli.py withdraw`) — 거두기와 껍데기 지우기가 "
    "따로 커밋돼 빈 행이 남음. 총괄 판정: 게이트에 남고 B 가 같은 착지에서 쪽마다 한 커밋으로 고침." % " · ".join(r2_red)]
    if r2_red else []) + [
    "- 판 도구가 바뀐 것: 쌍둥이도 치워 둔 것을 다시 돌림(박스 DLL 죽음, 최대 세 번 · 매 번 새로 치워진 것만) · «치워 둔 채» 빨강은 "
    "끝까지 다시 안 돈 것만 · 쌍둥이 견주기에서 행마다 층 이름의 행 id 를 접음(g83 · g84 가 그것만 달랐음) · R2 명령이 죽으면 운영자 복구대로 심박 60 초 뒤 취소 문(`request_cancel`)으로 그 런의 잠금을 풀고 같은 명령을 다시 돌림(번호로 프로세스를 죽이는 `stop_retroactive.py` 는 안 씀).",
    "",
]
at = [i for i, l in enumerate(lines) if l.startswith("## 판마다")]
assert len(at) == 1, at
lines[at[0]:at[0]] = summary
out = "\r\n".join(lines)
if DRY:
    print("\n".join(summary))
    print("filled", filled)
else:
    open(DOC, "wb").write(out.encode("utf-8"))
    print("written", filled, out.count("\r\n"), out.count("\n"))
