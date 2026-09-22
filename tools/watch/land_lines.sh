#!/usr/bin/env bash
# LAND 판정이 사는 «한 좌석». watch_all.sh 가 부르고, land_lines_gate.sh 가 «같은 바이트»를 잰다.
#
# 🔴 왜 파일로 나왔나 (2026-09-22 판정 651): 게이트가 «감시가 도는 그 코드»를 돌려야 하는데
#    watch_all.sh 는 통째로 못 돌린다 — :68 의 중복 기동 가드가 이미 도는 감시를 보고
#    둘째 인스턴스를 «물러나게» 한다. 게이트가 판정을 베껴 적으면 그 게이트가 둘째 저자가 된다.
#
# 🔴 그리고 이 좌석은 «조용히 실패하지 않는다» (판정 659). 실패와 「착지 없음」이 둘 다
#    «줄 0» 이면 감시가 죽어도 평화처럼 보인다 — 639 가 심박 침묵에 경보를 단 이유와 같은 부류다.
#    그래서 stderr 를 죽이지 않고(646 ③), 질의가 실패하면 한 줄 적고 «exit 3» 으로 끝낸다.
#
#   land_lines.sh <from> <to>   제품 파일을 건드린 «병합 아닌» 커밋마다 한 줄: <hash8> [제품 n] <제목>
#   exit 0 정상(줄이 0 일 수 있다 = 착지 없음)   2 인자 잘못   3 git 질의 실패
set -u
from="${1:-}"; to="${2:-}"
[ -n "$from" ] && [ -n "$to" ] || { echo "🔴 인자가 없습니다: land_lines.sh <from> <to>" >&2; exit 2; }

# 🔴 [판정 651] --no-merges — 병합 커밋은 LAND 가 «아니다». `$h^1 vs $h` 는 병합에서
#    «다른 부모가 들고 온 전부»를 제품 파일로 세서, design->main 병합 한 번이 되울림을 쏟았다.
#    실측: 최근 커밋 200 개 창의 LAND 30 중 «12»가 병합. 진짜 착지는 «안» 사라진다 —
#    병합된 커밋들은 같은 범위에 «병합 아닌» 커밋으로 들어 있다.
# 🔵 그리고 이 파일의 형제 판정(watch_all.sh 의 LANE)은 «이미» --no-merges 다. 둘이 같게 읽는다.
revs=$(git rev-list --reverse --no-merges "$from..$to") || {
  echo "🔴 LAND 판정 실패 — git rev-list '$from..$to' 가 거절했습니다" >&2; exit 3; }

for h in $revs; do
  files=$(git diff-tree -r --name-only "$h^1" "$h") || {
    echo "🔴 LAND 판정 실패 — git diff-tree ${h:0:8} 가 거절했습니다" >&2; exit 3; }
  n=$(printf '%s\n' "$files" | grep -cE '^(server|client2)/' || true)
  [ "${n:-0}" -gt 0 ] && printf '%s [제품 %s] %s\n' \
    "${h:0:8}" "$n" "$(git log -1 --format=%s "$h" | cut -c1-90)"
done
# ⛔ 마지막 문장이 «거짓»으로 끝나면 루프가 1 을 물려준다 — ensure.sh 에서 성공이 실패로
#    찍혔던 바로 그 함정이다(판정 638 ③).
exit 0
