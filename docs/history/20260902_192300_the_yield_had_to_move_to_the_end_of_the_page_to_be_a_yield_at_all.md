# 양보는 «페이지 끝»으로 가야 양보가 된다 — 페이싱 표의 세 번째 소비자

> **커밋:** `b504c504` (19:23)
> | **배경 커밋:** `30c140e8` (08-31 09:29 — 표의 이사)
> | **일자:** 2026-09-02 저녁
> **레인:** 서버(체인 리플레이 · 소급 실행 · CLI)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**

## 배경 — 표는 «원장 밑»에 있다가 소비자가 둘째로 늘면서 밖으로 나왔다

`server/ledger/pacing.json` 은 원장 백필의 페이싱 표였다. 파일 인제션이 **둘째 소비자**가
되면서 `server/pacing.json` 으로 올라왔다(→ `20260831_091400_...`).
체인 리플레이는 **셋째**다 — 이 항목을 쓰는 시점의 HEAD 기준으로 `pacing` 을 읽는 자리는
`ledger/backfill.py` · `parsers/directory_watcher.py` · `chain_replay.py` **셋**이다.

⚠️ 그리고 그 이사에는 **공유 트리 사고 하나**가 붙어 있다. `30c140e8` 이 기록한 것 —
그 rename 이 **커밋 안 된 채 스테이지**돼 있어서 `design` 병합이 거부됐고, 그 결과
클라 수리(끝난 실행이 도는 것으로 세어지던 것)가 main 에 못 들어가
**소유자가 화면에서 그 버그를 계속 보고 있었다.** 총괄은 **남의 미커밋 작업 위에 stash 하거나
checkout 하지 않았고**, 이동 «그 자체»만 커밋해 길을 텄다.

## ① 새 기계는 «없다» — 배선 둘과 거절 하나다

`pace=slow` 는 페이지 사이에 양보한다. 3분짜리 리플레이가 **그 3분 내내 DB 를 붙들고 있지
않게** 하려는 것이다.

```
server/pacing.json   페이스를 «이미» 선언한다
server/pacing.py     «이미» 푼다
이 커밋              배선 둘 + 거절 하나
```
표를 **복사하지 않았다.** 이 모듈이 갖는 것은 **자기 거절 모양**뿐이다 —
같은 경로의 다른 거절이 전부 `ReplayRefused` 인데 「선언 안 된 것을 요청했다」에 대해서만
**두 번째 예외 타입**을 잡게 하면 호출자가 결국 **하나만** 잡는다.

```python
def resolve_pace(name, paces=None):
    """The shared pacing table, with this module's refusal shape.

    🔴 THE TABLE IS NOT COPIED. ...
    A UNIT HERE IS A PAGE. The table does not know that and does not need to: what a unit
    means belongs to the caller, at the boundary where ITS work is already committed.
    """
```
🔴 **「단위」의 뜻이 소비자마다 다르다** — 표는 그것을 모르고, 알 필요도 없다.

## 🔴 ② 안전 논증은 «어디서 자느냐»에 전부 걸려 있다

```python
# 🔴 THE YIELD IS AT THE END OF THE PAGE, NOT THE TOP, AND THAT IS THE WHOLE
# SAFETY ARGUMENT. Sleeping is only pacing if this session is holding nothing while
# it sleeps; hold a transaction and it is OCCUPATION, which is the thing being
# complained about rather than a cure for it. At the top of the body the page's
# own SELECT has already run - `iter_pages` queries, then yields - so a sleep there
# would sit on that read snapshot for `rest_seconds`.
if pages_per_cycle and rest_seconds and stats["pages"] % pages_per_cycle == 0:
    db.rollback()
    time.sleep(rest_seconds)
```

```
루프 «위»에서 자면    iter_pages 가 «질의하고» 양보하므로 그 페이지의 SELECT 가 «이미 열려 있다»
                    -> 읽기 스냅샷을 rest_seconds 동안 «깔고 앉는다» = 페이싱이 아니라 «점유»
루프 «끝»에서 자면    이 페이지의 쓰기는 «전부 커밋»됐고 다음 페이지는 «아직 안 읽었다»
```
🔴 옆의 `rollback` 이 그것을 **흔한 경우가 아니라 «모든 경우»에** 참으로 만든다 —
**매퍼가 아무것도 못 만든 페이지는 커밋에 도달한 적이 없어서** 그 SELECT 의 트랜잭션이
여전히 열려 있다. 버리는 것은 없고(쓰기는 이미 커밋됨), 드라이런에서는 이 함수가
**이미 끝에 하고 있던 것과 같은 이중 안전장치**다.
`iter_pages` 가 **양보 «전»에 다음 커서를 읽으므로** rollback 이 keyset 을 빼앗지 못한다.

**단위는 페이지**이고, 그것은 **취소 체크포인트와 같은 경계**다 —
취소가 «멈추는» 손잡이라면 이것은 «늦추는» 손잡이이고, 대개 늦추는 것으로 충분하다.

## 🔴 ③ 선언 안 된 페이스는 «조용히 fast» 가 되지 않는다

```
느린 페이스를 찾는 사람   서비스가 «이미» 힘들어서 그러는 것이다
오타가 «전속력»으로 돌면   고장난 손잡이와 «안 듣는» 손잡이를 «구별할 수 없다»
=> 첫 페이지 «전»에 거절한다 (아무것도 쓰기 전에)
```

## ④ 파라미터를 «한 번» 선언했다 — 두 철자는 사실 하나가 새는 자리다

페이스를 받는 조작 «둘»에 대해 파라미터가 한 번 선언된다.
**철자가 둘이면 한쪽의 도움말만 어떤 사실을 이고 있게 된다** — 그리고 지금 그 사실이 있다:
**소급 실행은 «한 번에 하나»씩 도므로, 느린 페이스는 뒤에 큐된 것을 그만큼 더 기다리게 한다.**
페이스를 고르는 운영자가 바로 그것을 알아야 하는 사람이다.

`--pace` 가 **CLI 에도** 닿는다 — `retroactive` 자신의 가드가 「`cli` 줄은 버튼과 같은 일을
해야 한다」고 말하고, **버튼이 명령줄이 못 받는 파라미터를 얻는 순간 빨개졌다.**

## 측정과 변이

```
라이브 드라이런 (이 상자, dt_log 20,000 행 · 200 페이지)
   페이스 없음 · fast   ->  200 페이지 · 20,000 행 · 966 셀 · 483 매퍼 아이템  «동일»
   slow                ->  «같은 수», 시간만 1.18s -> 41.27s
                          = 5페이지/주기가 요구하는 «1초 양보 40회»
변이 다섯 (각각 다른 시험을 빨갛게)
   rest 무시 · 주기 상한 무시 · fast 가 쉬어 버림 ·
   «양보를 페이지 커밋 위로 옮김» · 선언 안 된 페이스가 기본값으로 떨어짐
```
🔴 `fast` 는 **손잡이가 생기기 «전»과 문자 그대로 같다** — 상한 없음, 쉼 없음,
**sleep 호출 자체가 없음.**

## 아키텍처 영향

- 체인 리플레이가 **`server/pacing.json` 의 세 번째 소비자**다. 표는 복사되지 않았고,
  이 모듈은 **자기 거절 모양**만 갖는다.
- 양보가 **페이지 «끝»**, 쓰기가 전부 커밋된 뒤·다음 페이지를 읽기 전에 일어난다.
  옆의 `rollback` 이 **매퍼가 아무것도 못 만든 페이지**까지 덮는다.
- **선언 안 된 페이스는 첫 페이지 전에 거절**된다.
- `pace` 파라미터가 **조작 둘에 대해 한 번** 선언되고, `--pace` 가 CLI 에 있다.

## 그때 남아 있던 것

- 「단위 = 페이지」는 **이 소비자의 뜻**이다. 표는 단위를 모르고, 다른 소비자는 다른 것을
  단위로 센다.
- 20,000 행 · 200 페이지 · 966 셀 · 483 아이템 · 41.27s 는 전부 **이 상자의 `dt_log`**
  에서 잰 수다. 운영의 수가 아니다.
- 드라이런에서만 쟀다 — `apply` 경로의 페이싱은 이 라운드에서 관측되지 않았다.
