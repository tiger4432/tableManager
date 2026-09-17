#!/usr/bin/env bash
# 감시 프로세스가 «살아 있게» 한다. 세션이 깨어날 때마다 한 번 돌리면 된다 — 이미 돌면 아무것도 안 한다.
#   tools/watch/ensure.sh          없으면 띄운다
#   tools/watch/ensure.sh status   살아 있나 + 마지막 줄
#   tools/watch/ensure.sh log      최근 40줄
set -u
OUT="C:/Users/kk980/Developments/.assy_watch"
LOG="$OUT/events.log"; PIDF="$OUT/watch.pid"
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$OUT"
alive() { [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF" 2>/dev/null)" 2>/dev/null; }
case "${1:-ensure}" in
  status) if alive; then echo "ALIVE pid=$(cat "$PIDF")"; else echo "🔴 DEAD — tools/watch/ensure.sh 로 띄우십시오"; fi
          echo "마지막: $(tail -1 "$LOG" 2>/dev/null || echo '(로그 없음)')" ;;
  log)    tail -40 "$LOG" 2>/dev/null || echo "(로그 없음)" ;;
  *)      if alive; then echo "이미 돕니다 pid=$(cat "$PIDF")"; else
            nohup bash "$HERE/watch_all.sh" >/dev/null 2>&1 &
            echo $! > "$PIDF"; sleep 2; echo "띄웠습니다 pid=$(cat "$PIDF")"; tail -2 "$LOG" 2>/dev/null
          fi ;;
esac
