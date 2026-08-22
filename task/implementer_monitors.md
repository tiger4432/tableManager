# 🔴 감시 복원 — 컴팩트 뒤 «제일 먼저» 이걸 한다

🔴 **컴팩트는 감시를 «풀지 않는다».** 2026-08-22 에 쟀다 — 프로세스도 알림 경로도
«둘 다» 살아 있었다. 그러니 이 파일은 「다시 걸어라」가 아니라 **「살아 있는지 재고,
그다음에 정한다」**이다. 명령 정본은 아래 둘이다.

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
