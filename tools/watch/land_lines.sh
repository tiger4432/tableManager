#!/usr/bin/env bash
# LAND 판정이 사는 «한 좌석». watch_all.sh 가 부르고, land_lines_gate.sh 가 «같은 바이트»를 잰다.
#
# 🔴 왜 파일로 나왔나 (2026-09-22 판정 651): 게이트가 «감시가 도는 그 코드»를 돌려야 하는데
#    watch_all.sh 는 통째로 못 돌린다 — :68 의 중복 기동 가드가 이미 도는 감시를 보고
#    둘째 인스턴스를 «물러나게» 한다. 게이트가 판정을 베껴 적으면 그 게이트가 둘째 저자가 된다.
#
#   land_lines.sh <from> <to>   제품 파일을 건드린 커밋마다 한 줄:  <hash8> [제품 n] <제목>
set -u
from="${1:-}"; to="${2:-}"
[ -n "$from" ] && [ -n "$to" ] || { echo "usage: land_lines.sh <from> <to>" >&2; exit 2; }

# 🔴 [2026-09-22 판정 651] `--no-merges` — 병합 커밋은 LAND 가 «아니다».
#    `$h^1 vs $h` 는 병합에서 «다른 부모가 들고 온 전부»를 제품 파일로 센다. 그래서
#    design->main 병합 한 번이 되울림을 열 줄 넘게 쏟았고, 되울림이 진짜 착지를 덮으면
#    639(모든 세션이 이 로그에 기댄다)가 무너진다. 실측: 최근 커밋 200 개 창의 LAND 30 중 «12»가 병합.
# 🔵 진짜 착지는 «안» 사라진다 — 병합된 커밋들은 같은 범위에 «병합 아닌» 커밋으로 들어 있다.
# 🔵 그리고 이 파일의 LANE 판정(아래 :124)은 «이미» --no-merges 다. 둘이 같은 방식으로 읽는다.
for h in $(git rev-list --reverse --no-merges "$from..$to" 2>/dev/null); do
  n=$(git diff-tree -r --name-only "$h^1" "$h" 2>/dev/null | grep -cE '^(server|client2)/' || true)
  [ "${n:-0}" -gt 0 ] && printf '%s [제품 %s] %s\n' \
    "${h:0:8}" "$n" "$(git log -1 --format=%s "$h" | cut -c1-90)"
done
# ⛔ 마지막 문장이 «거짓»으로 끝나면 루프가 1 을 물려준다 — ensure.sh 에서 성공이 실패로
#    찍혔던 바로 그 함정이다(판정 638 ③).
exit 0
