#!/usr/bin/env bash
# 651 · 659 의 게이트 — LAND 판정 좌석(land_lines.sh)을 «감시가 부르는 그대로» 부른다.
#
# 단언 둘 무리:
#   ① 651  병합 «1회» -> LAND 0 · 일반 커밋 «1회» -> LAND 1   (줄 수 «와» 해시 둘 다)
#   ② 659  「도우미 없음 / 참조 오류 / 착지 없음」이 «서로 갈려야» 한다.
#          셋이 같은 그림이었던 것이 결함이므로, 못 가르면 고친 게 아니다
# 🔵 가짜 저장소에 짓는다 — 진짜 로그는 639 로 모든 세션이 기대는 자리라 한 줄도 쓰면 안 된다.
# 🔵 LAND_LINES 로 «옛 좌석»을 겨눠 빨강을 먼저 돌릴 수 있다 (ensure.sh 의 ASSY_WATCH_SCRIPT 와 같은 뜻).
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
LANDS="${LAND_LINES:-$HERE/land_lines.sh}"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
cd "$TMP" || exit 1

git init -q .
git config user.email gate@example.com; git config user.name gate
mkdir -p client2 docs
echo base > client2/x; git add client2/x; git commit -qm "base"
BASE=$(git rev-parse HEAD)
BR=$(git rev-parse --abbrev-ref HEAD)
git checkout -q -b side
echo y > client2/y; git add client2/y; git commit -qm "feat: a real landing"
SIDE=$(git rev-parse --short=8 HEAD)
git checkout -q "$BR"
git merge -q --no-ff side -m "Merge branch 'side'" >/dev/null
MERGED=$(git rev-parse HEAD)
echo z > docs/z; git add docs/z; git commit -qm "docs: not a product file"

fail=0
ok()   { echo "  ok   $*"; }
bad()  { echo "  FAIL $*"; fail=1; }

# 감시가 부르는 «그 모양» — 종료코드를 읽고 stderr 를 죽이지 않는다 (판정 660)
run() { out=$(bash "$LANDS" "$@" 2>&1); rc=$?; n=$(printf '%s' "$out" | grep -c . || true); }

run "$BASE" "$MERGED"
[ "$n" = "1" ] && ok "G1 병합 한 번 · 일반 한 번 -> LAND 줄 «1»" || bad "G1 LAND 줄 -- got $n, want 1"
got=$(printf '%s' "$out" | head -1 | cut -d' ' -f1)
[ "$got" = "$SIDE" ] && ok "G2 남은 줄이 «진짜 착지»의 해시다 ($SIDE)" \
  || bad "G2 남은 해시 -- got '$got', want '$SIDE' (병합만 남았을 수 있다)"

# ③ 착지 없음 — «조용한 것이 맞는» 유일한 경우다
run "$MERGED" HEAD; q_rc=$rc; q_n=$n
{ [ "$rc" = "0" ] && [ "$n" = "0" ]; } && ok "G3 착지 없음 -> 줄 0 · exit 0 (조용한 게 맞다)" \
  || bad "G3 착지 없음 -- got exit=$rc 줄=$n, want exit=0 줄=0"

# ④ 참조 오류 — 조용하면 «안 된다»
run deadbeef99 HEAD; e_rc=$rc
{ [ "$rc" != "0" ] && printf '%s' "$out" | grep -q "LAND 판정 실패"; } \
  && ok "G4 참조 오류 -> exit $rc 로 «웁니다»" \
  || bad "G4 참조 오류 -- got exit=$rc, 말='$(printf '%s' "$out" | tail -1)'"

# ⑤ 도우미 «없음» — 감시가 읽는 계약(rc != 0 · stderr 비지 않음)이 서는지
out=$(bash "$HERE/does_not_exist_land_lines.sh" "$BASE" HEAD 2>&1); m_rc=$?
{ [ "$m_rc" != "0" ] && [ -n "$out" ]; } && ok "G5 도우미 없음 -> exit $m_rc · 말이 «있다»" \
  || bad "G5 도우미 없음 -- got exit=$m_rc, 말='$out'"

# ⑥ 셋이 «서로» 갈리는가 — 659 가 고치라고 한 것이 바로 이 셋의 «같은 그림»이다
[ "$q_rc" != "$e_rc" ] && [ "$q_rc" != "$m_rc" ] \
  && ok "G6 셋이 갈립니다 — 착지없음=$q_rc · 참조오류=$e_rc · 도우미없음=$m_rc" \
  || bad "G6 셋이 «같은 그림»입니다 — 착지없음=$q_rc · 참조오류=$e_rc · 도우미없음=$m_rc"

[ "$fail" = "0" ] && echo "GATE PASS" || echo "GATE FAIL"
exit "$fail"
