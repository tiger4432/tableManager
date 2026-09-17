#!/usr/bin/env bash
# 세션과 «무관하게» 도는 감시. 컴팩트·세션 종료에 안 죽는다.
#
# 🔴 왜 있나 (소유자 2026-09-17): 「세션들 모니터 쓰는데 그러면 컴팩트하면 꺼지잖아
#    프로세스 방식으로해」. 세션에 묶인 감시는 그 세션이 죽으면 «조용히» 같이 죽고,
#    조용한 것은 「변화 없음」과 구별이 안 된다.
#
# 규율 셋 (통신 상설):
#   ① 스크립트가 «직접» fetch 한다        ② «무엇이 바뀌었는지» 견준다
#   ③ 걸릴 때 «현재 값»을 찍는다 — 그래야 「조용함」이 죽음인지 변화없음인지 갈린다
#   그리고 fetch 실패를 «말한다». 조용히 실패하지 않는다.
#
# 읽는 법:  tail -40 "$LOG"        살아 있나:  tools/watch/ensure.sh status
set -u
REPO="C:/Users/kk980/Developments/assyManager"
OUT="C:/Users/kk980/Developments/.assy_watch"     # 저장소 «밖» — 커밋될 일이 없다
LOG="$OUT/events.log"
mkdir -p "$OUT"
cd "$REPO" || { echo "FATAL repo 없음: $REPO" >> "$LOG"; exit 1; }

PY="C:/Users/kk980/anaconda3/envs/assy_manager/python.exe"
[ -x "$PY" ] || PY=python

say() { printf '%s %s\n' "$(date '+%m-%d %H:%M:%S')" "$*" >> "$LOG"; }

# 🔴 [클라 레인 발견 2026-09-17 12:30] 보고서를 «origin/main 에서만» 읽으면 클라 레인의 보고가
# 안 보인다 — 그 레인은 «design 브랜치»에 커밋하고, main 에 병합될 때까지 origin/main 에 없다.
# 그래서 그 레인 보고는 「병합될 때」 한 번 뜨고, 그 전까지는 «조용»했다. 브랜치를 같이 본다.
blob() {
  local b
  b=$(git rev-parse "origin/main:$1" 2>/dev/null) || b=""
  if [ -z "$b" ] || [ "$1" = "task/axis_and_material_report.md" ]; then
    local d
    d=$(git rev-parse "design:$1" 2>/dev/null || git rev-parse "origin/design:$1" 2>/dev/null || echo "")
    [ -n "$d" ] && { echo "$d"; return; }
  fi
  echo "${b:-none}"
}
# 🔴 [클라 레인 2026-09-17 15:2x] 위 수리가 «반쪽»이었다. `blob()` 은 design 을 보게 고쳤는데
# 아래 줄이 «찍는 문장»은 여전히 origin/main 에서 왔다. 그래서 증상이 «침묵»에서 «틀린 표제»로
# 바뀌었을 뿐이다 — 클라 보고 넷이 올라가는 동안 표제가 «39분 전 것»에 얼어 있었고, 그건
# 읽는 사람에게 「새 것이 없다」로 읽힌다. 침묵보다 나쁘다.
# 🔴 그래서 찍는 자리도 «고른 ref 를 그대로» 쓴다 — 고르는 곳이 둘이면 또 갈라진다.
logref() {
  if [ "$1" = "task/axis_and_material_report.md" ]; then
    git rev-parse --verify -q design >/dev/null 2>&1 && { echo design; return; }
    git rev-parse --verify -q origin/design >/dev/null 2>&1 && { echo origin/design; return; }
  fi
  echo origin/main
}
WATCHED="task/IMPLEMENTER_ORDERS.md task/DESIGN_ORDERS.md task/scoped_redo_report.md task/ontology_application_report.md task/axis_and_material_report.md"
CFG="server/config/ontology/ledger_config.json"

declare -A PREV
git fetch -q origin main 2>/dev/null || say "⚠️ ARM 중 fetch 실패 — 아래 값은 «마지막으로 받은» 것입니다"
for f in $WATCHED; do PREV[$f]=$(blob "$f"); done
PREV_HEAD=$(git rev-parse main 2>/dev/null || echo none)
PREV_CFG=$( [ -f "$CFG" ] && md5sum "$CFG" | cut -c1-12 || echo missing )
PREV_BOX=""
WT="C:/Users/kk980/Developments/assyManager-design"          # 클라 레인의 워크트리
ID=$("$PY" -c "import base64,json;j=json.dumps(['wafer',{'wafer':'SYN-BW-101-16'}],separators=(',',':'));print('ledger-entity:v1:'+base64.urlsafe_b64encode(j.encode()).decode().rstrip('='))" 2>/dev/null)
ENC=$("$PY" -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1],safe=''))" "$ID" 2>/dev/null)
PREV_STALE=""; PREV_LANE=""; PREV_PIPE=""
# 🔴 «자기» pid 를 적는다. 런처($!)의 pid 를 적으면 alive() 가 엉뚱한 것을 보고
# 「안 돈다」로 읽어 «둘째»를 띄운다 — 2026-09-17 실측: watch_all 이 둘 돌고 있었다
echo $$ > "$OUT/watch.pid"
# 이미 다른 인스턴스가 돌면 «내가» 물러난다 (중복 로그 금지)
for other in $(pgrep -f "watch_all.sh" 2>/dev/null | grep -v "^$$$"); do
  if [ "$other" != "$$" ] && kill -0 "$other" 2>/dev/null; then
    say "· 중복 기동 감지 — pid=$$ 가 물러납니다 (이미 $other 이 돕니다)"; exit 0
  fi
done
say "ARMED pid=$$ — 지금 값: $(for f in $WATCHED; do printf '%s=%.8s ' "$(basename $f .md)" "${PREV[$f]}"; done)head=${PREV_HEAD:0:8} cfg=$PREV_CFG"

N=0
while true; do
  sleep 60; N=$((N+1))

  if git fetch -q origin main 2>/dev/null; then :; else say "🔴 FETCH-FAILED — 아래 판정은 «낡은 값» 위의 것입니다"; fi

  for f in $WATCHED; do
    cur=$(blob "$f")
    if [ "$cur" != "${PREV[$f]}" ]; then
      line=$(git log -1 --format='%h %ad %s' --date=format:'%H:%M' "$(logref "$f")" -- "$f" 2>/dev/null | cut -c1-110)
      case "$f" in
        task/*ORDERS*) say "📥 ORDERS $f — $line" ;;
        *)             say "📮 REPORT $f — $line" ;;
      esac
      PREV[$f]=$cur
    fi
  done

  cur_head=$(git rev-parse main 2>/dev/null || echo none)
  if [ "$cur_head" != "$PREV_HEAD" ] && [ "$PREV_HEAD" != "none" ]; then
    for h in $(git rev-list --reverse "$PREV_HEAD..$cur_head" 2>/dev/null); do
      n=$(git diff-tree -r --name-only "$h^1" "$h" 2>/dev/null | grep -cE '^(server|client2)/' || true)
      [ "${n:-0}" -gt 0 ] && say "🛠 LAND ${h:0:8} [제품 $n] $(git log -1 --format=%s $h | cut -c1-90)"
    done
    PREV_HEAD=$cur_head
  fi

  if [ -f "$CFG" ]; then
    c=$(md5sum "$CFG" | cut -c1-12)
    [ "$c" != "$PREV_CFG" ] && { say "🔴 LIVE CONFIG CHANGED $PREV_CFG -> $c — 소유자 손일 수 있습니다"; PREV_CFG=$c; }
  elif [ "$PREV_CFG" != "missing" ]; then
    say "🔴 LIVE CONFIG GONE"; PREV_CFG=missing
  fi

  code=$(curl -s -o /dev/null -w '%{http_code}' --noproxy '*' --max-time 8 http://127.0.0.1:8080/admin.html 2>/dev/null || echo 000)
  [ "$code" = "200" ] && s=up || s=down
  [ "$s" != "$PREV_BOX" ] && { say "$( [ "$s" = up ] && echo '✅ BOX up' || echo '🔴 BOX down' ) admin.html=$code"; PREV_BOX=$s; }

  # 클라 워크트리가 지시를 «받았나» — 푸시는 워크트리에 안 닿는다
  if [ -d "$WT" ]; then
    n=$(git rev-list --count design..main -- task/DESIGN_ORDERS.md 2>/dev/null || echo ERR)
    if [ "$n" != "$PREV_STALE" ]; then
      case "$n" in
        ERR) say "⚠️ 지시 낡음 감시 오류 — git 질의 실패" ;;
        0)   [ -n "$PREV_STALE" ] && say "✅ ORDERS OK — 클라가 DESIGN_ORDERS 최신" ;;
        *)   say "🔴 ORDERS STALE — 클라가 못 받은 DESIGN_ORDERS 커밋 $n 건. 고치려면: git -C \"$WT\" merge main --no-edit" ;;
      esac
      PREV_STALE=$n
    fi
    l=$(git log --format='%h %s' --no-merges main..design 2>/dev/null | head -8)
    if [ "$l" != "$PREV_LANE" ]; then
      c=$(git rev-list --count --no-merges main..design 2>/dev/null || echo 0)
      [ "${c:-0}" -gt 0 ] && say "🧩 CLIENT LANE 미병합 $c 건 — $(echo "$l" | head -1 | cut -c1-90)"
      PREV_LANE=$l
    fi
  fi

  # 배관 심박 — html·선언·걷기 «셋을 실제로 불러» 본다. 200 이 아니면 즉시
  if [ -n "${ENC:-}" ]; then
    d=$(curl -s -o /dev/null -w '%{http_code}' --noproxy '*' --max-time 15 http://127.0.0.1:8080/api/ledger/declaration 2>/dev/null || echo 000)
    w=$(curl -s -o /dev/null -w '%{http_code}' --noproxy '*' --max-time 60 "http://127.0.0.1:8080/api/ledger/subgraph?id=$ENC&hops=1&node_limit=10" 2>/dev/null || echo 000)
    st="$d$w"
    if [ "$st" != "$PREV_PIPE" ]; then
      if [ "$st" = "200200" ]; then [ -n "$PREV_PIPE" ] && say "✅ 배관 복구 — declaration=200 walk=200"
      else say "🔴 배관 끊김 — declaration=$d walk=$w (000 = 프로세스 없음, 그 밖은 배관)"; fi
      PREV_PIPE=$st
    fi
  fi

  [ $((N % 30)) -eq 0 ] && say "· alive (30분) box=$code declaration=${d:-?} walk=${w:-?}"
done
