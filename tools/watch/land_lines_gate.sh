#!/usr/bin/env bash
# 651 의 게이트 — 「병합 «1회» -> LAND 0 · 일반 커밋 «1회» -> LAND 1」
#
# 🔴 단언이 «둘»이다. 줄 수만 세면 반대 오답(병합만 남고 진짜가 사라짐)이 통과한다.
#    그래서 남은 줄의 «해시»가 진짜 착지의 것인지도 잰다.
# 🔵 가짜 저장소에 짓는다 — 진짜 로그(.assy_watch/events.log)는 639 로 모든 세션이 기대는
#    자리라 시험이 거기에 한 줄도 쓰면 안 된다.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
cd "$TMP" || exit 1

git init -q .
git config user.email gate@example.com; git config user.name gate
mkdir -p client2
echo base > client2/x; git add client2/x; git commit -qm "base"
BASE=$(git rev-parse HEAD)
BR=$(git rev-parse --abbrev-ref HEAD)
git checkout -q -b side
echo y > client2/y; git add client2/y; git commit -qm "feat: a real landing"
SIDE=$(git rev-parse --short=8 HEAD)
git checkout -q "$BR"
git merge -q --no-ff side -m "Merge branch 'side'" >/dev/null

out=$(bash "$HERE/land_lines.sh" "$BASE" "$(git rev-parse HEAD)")
n=$(printf '%s' "$out" | grep -c . || true)
got=$(printf '%s' "$out" | head -1 | cut -d' ' -f1)

echo "--- land_lines 가 낸 줄 ---"; printf '%s\n' "$out"; echo "---"
fail=0
if [ "$n" = "1" ]; then echo "  ok   G1 병합 한 번 · 일반 한 번 -> LAND 줄 «1»"
else echo "  FAIL G1 LAND 줄 -- got $n, want 1"; fail=1; fi
if [ "$got" = "$SIDE" ]; then echo "  ok   G2 남은 줄이 «진짜 착지»의 해시다 ($SIDE)"
else echo "  FAIL G2 남은 해시 -- got '$got', want '$SIDE' (병합만 남았을 수 있다)"; fail=1; fi
[ "$fail" = "0" ] && echo "GATE PASS" || echo "GATE FAIL"
exit "$fail"
