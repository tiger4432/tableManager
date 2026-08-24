# 🔴 감시 복원 — 컴팩트 뒤 «제일 먼저» 이걸 한다

🔴 **컴팩트는 감시를 «풀지 않는다».** 2026-08-22 에 쟀다 — 프로세스도 알림 경로도
«둘 다» 살아 있었다. 그러니 이 파일은 「다시 걸어라」가 아니라 **「살아 있는지 재고,
그다음에 정한다」**이다. 명령 정본은 아래 둘이다.

같은 날 저녁에 «반대 경우»가 나왔다 — **Claude Code 프로세스가 재기동되면 진짜로 죽는다.**
하니스가 「stopped」로 표시했고 PID 도 «0개»였다. 그러니 규칙은 「죽는다」도 「안 죽는다」도
아니고 **«매번 잰다»** 하나다.
```
컴팩트          살아 있다  -> 새로 걸면 알림이 «두 번» 온다. PID 로 죽이고 걸 것
세션 재기동      죽는다     -> 그냥 걸면 된다 (PID 0 개를 확인하고)
```

## ⚠️ 걸기 «전»에 — 살아 있는지부터 «잰다»
2026-08-21 에 「컴팩트가 죽였겠지」로 «단정»하고 다시 걸었다가, 옛것이 살아 있어서
**같은 커밋에 알림이 두 번** 왔다. 2026-08-22 에 실제로 재 보니, 컴팩트를 지나고도
프로세스가 살아 있었고 **죽이는 순간 이 세션으로 실패 알림이 왔다** — 알림 경로까지
살아 있었다는 뜻이다.

그런데 컴팩트 뒤엔 **task-id 를 잃어 `TaskStop` 을 못 한다.** 그래서 **PID 로 재고 PID 로 죽인다**:

```powershell
Get-CimInstance Win32_Process -Filter "Name='bash.exe'" | Select-Object ProcessId,CreationDate,CommandLine | Format-List
```
`IMPLEMENTER_ORDERS` · `format=%ct` 로 훑어 내 것을 찾는다.
판별은 **shell-snapshot 이름이 같은가**로 한다 — 같으면 같은 세션 것이다.
«시각으로 추측하지 말 것». 남의 세션 것(`watch_fork_messages.sh` 등)은 손대지 않는다.
그다음 `Stop-Process -Id <pid> -Force` 로 죽이고 아래 둘을 새로 건다.
감시 하나가 **PID 두 개**로 뜨는 것이 정상이다 (Git bash 래퍼 + 루프).

🔴🔴 **재정정 (2026-08-25). 앞 정정의 «이유»가 틀렸다. 그리고 더 중요한 것이 있다:**
**PID 목록으로 하니스 감시를 판정하지 마라.** 세 가지가 동시에 어긋난다:
```
① 자기참조   `Where-Object { $_.CommandLine -match 'md5sum' }` 는 «그 명령 자신»을 맞춘다.
             측정할 때마다 개수가 +1~3 된다. 2026-08-25 에 ORDERS 를 「3개 살아 있음」으로
             읽었는데, 자기참조를 빼니 «0개»였다
② 래퍼 이름   세션마다 감시가 bash.exe 로 안 뜰 수 있다. 0개가 «죽음»을 뜻하지 않는다
③ 고아       프로세스가 살아 있어도 «알림 경로»는 끊겨 있을 수 있다.
             2026-08-25: 어제 오전 10:45~10:55 에 만들어진 WAKE 루프 «8개»가 돌고 있었는데
             알림은 14시간째 «0건»이었다
```
✅ **판정은 «배달»로 한다** — 「그 감시가 최근에 «알림을 보냈나»」. 그게 유일하게
   프로세스·래퍼·경로를 «전부» 통과한 증거다. 새로 걸었으면 «첫 발화»를 기다려 확인한다.
   프로세스 목록은 «고아를 청소할 때»만 쓴다 (죽일 대상 찾기). 살았는지 판정에는 쓰지 마라.

~~정정 (2026-08-24): 개수는 두 개로 고정이 아니고 PID 도 매번 바뀐다.~~ 결론은 맞았으나
ORDERS 감시를 두 번 재니 «3개»였고 PID 가 전부 달랐다
(55644·56328·53368 -> 57340·4224·47180). 루프가 주기마다 `md5sum`·`git log`
서브셸을 새로 띄우므로, 한 순간의 PID 목록은 «그때 살아 있던 자식들의 스냅숏»이다.
**개수로 중복을 판정하지 마라** — 「2개여야 하는데 3개다」로 읽고 죽이면 «도는 감시»를
죽인다. 판정은 «CommandLine 이 그 감시의 것인가» 하나로 한다.

---

## ① 총괄 지시 갱신 감시

```
description : 총괄 지시 갱신 감시 (IMPLEMENTER_ORDERS.md)
persistent  : true
timeout_ms  : 3600000
command     : 아래 그대로
```
```bash
cd /c/Users/kk980/Developments/assyManager; prev=$(md5sum task/IMPLEMENTER_ORDERS.md 2>/dev/null | cut -d' ' -f1); while true; do sleep 120; cur=$(md5sum task/IMPLEMENTER_ORDERS.md 2>/dev/null | cut -d' ' -f1); if [ "$cur" != "$prev" ]; then echo "📋 지시 갱신 — task/IMPLEMENTER_ORDERS.md 를 다시 읽을 것"; git log -1 --format='   %h %s' -- task/IMPLEMENTER_ORDERS.md 2>/dev/null; prev=$cur; fi; done
```

🔴 **`git fetch` 나 `git merge` 를 «넣지 마라».**
총괄은 «같은 트리»에서 일한다 — 파일 변경이 바로 보이므로 가져올 것이 없다.
2026-08-21 에 fetch+merge 판을 걸었다가, 하위 에이전트가 편집 중인 «공유 트리»에서
2분마다 되돌리는 성격의 명령이 도는 상태를 만들었다. (피해는 0이었지만 운이었다.)

---

## ② 커밋 정체 감시

```
description : 커밋 정체 감시 (2시간)
persistent  : true
timeout_ms  : 3600000
command     : 아래 그대로
```
```bash
cd /c/Users/kk980/Developments/assyManager; warned=""; while true; do sleep 900; last=$(git log -1 --format=%ct 2>/dev/null); now=$(date +%s); age=$(( (now - last) / 60 )); if [ "$age" -ge 120 ]; then if [ "$warned" != "$last" ]; then echo "⏳ COMMIT STALL — ${age}분째 새 커밋 없음. 하위 에이전트·ORDERS 를 «확인»하고, 새 지시가 있으면 착수, 없고 도는 것도 없으면 그대로 대기할 것."; warned=$last; fi; fi; done
```

### 문턱은 «국면»에 맞춘다 — 고정값이 아니다
```
하위 에이전트가 도는 중    50분   (라운드 길이에 맞춤)
지시를 기다리는 중          2시간  (지금 이 값)
```
⚠️ 문턱이 국면과 안 맞으면 **내용 없는 상태 커밋만 쌓인다.**
총괄은 커밋으로 내 상태를 보므로, 빈 줄을 쌓는 것은 감시의 «목적»을 해친다.
25분판을 쓰다 두 번 그렇게 됐고, 두 번 다 문턱을 올리는 쪽이 맞았다.

---

## 감시가 «못 보는» 것
```
하위 에이전트의 작업        커밋·mtime·트리 변화로는 «안 보인다». 끊기 전에 «물어본다»
소유자가 라이브 설정에 쓰는 것  파일이 바뀌지만 «누가» 썼는지는 안 알려준다 — 추측해서 지우지 마라
```
