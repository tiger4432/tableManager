#!/usr/bin/env bash
# 감시 «프로세스»가 살아 있게 한다. 세션이 깨어날 때마다 «한 번» 돌린다 — 이미 돌면 아무것도 안 한다.
#
# 🔴 왜 프로세스인가 (소유자 2026-09-17): 「세션들 모니터 쓰는데 그러면 컴팩트하면 꺼지잖아」.
#    세션에 묶인 감시는 세션이 죽을 때 «조용히» 같이 죽는다. 조용한 것은 「변화 없음」과 같아 보인다.
#
#   tools/watch/ensure.sh          안 돌면 띄운다 (돌면 아무것도 안 함)
#   tools/watch/ensure.sh status   살아 있나 · pid · 마지막 줄
#   tools/watch/ensure.sh log      최근 40줄
#   tools/watch/ensure.sh restart   죽이고 다시 (스크립트를 고친 뒤)
set -u
OUT="C:/Users/kk980/Developments/.assy_watch"
LOG="$OUT/events.log"; PIDF="$OUT/watch.pid"
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$OUT"

alive() { [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF" 2>/dev/null)" 2>/dev/null; }
start() {
  rm -f "$PIDF"
  nohup bash "$HERE/watch_all.sh" >/dev/null 2>&1 &
  # ⛔ 런처 pid($!)를 적지 «않는다» — watch_all 이 자기 pid 를 직접 적는다 (2026-09-17)
  sleep 3
  if alive; then echo "띄웠습니다 pid=$(cat "$PIDF")"; tail -1 "$LOG" 2>/dev/null
  else echo "🔴 띄우기 «실패» — 바로 죽었습니다. 로그: $LOG"; tail -3 "$LOG" 2>/dev/null; return 1; fi
}
case "${1:-ensure}" in
  status)  if alive; then echo "ALIVE pid=$(cat "$PIDF")"; else echo "🔴 DEAD — 'tools/watch/ensure.sh' 로 띄우십시오"; fi
           echo "마지막: $(tail -1 "$LOG" 2>/dev/null || echo '(로그 없음)')" ;;
  log)     tail -40 "$LOG" 2>/dev/null || echo "(로그 없음)" ;;
  restart) if alive; then kill "$(cat "$PIDF")" 2>/dev/null; sleep 1; fi; start ;;
  *)       if alive; then echo "이미 돕니다 pid=$(cat "$PIDF")"; else start; fi ;;
esac
