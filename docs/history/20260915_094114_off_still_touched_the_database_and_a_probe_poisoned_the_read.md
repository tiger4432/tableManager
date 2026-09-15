# OFF 가 DB 를 만지고 있었다 — 스위치가 «반쪽»이었던 이유, 그리고 읽기 경로의 탐침이 읽기를 오염시킨 길

> **커밋:** `1497ea3e` — fix(virtual-join): OFF touches no database, and a read-path probe cannot poison the read
> **일자:** 2026-09-15 09:41
> **레인:** 총괄 측 직접 착지(구현자 정지 중 — 커밋 트레일러는 Opus 4.8)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **스위트:** 커밋 메시지에 «상자 실측 셋»만 적혀 있다(아래 ④). **시험 파일 변경 0 · 스위트 수 «없음».** 바뀐 파일은 `unique_key.py` 하나.

## ① 왜 — 어제 세운 것의 «첫 벌»이 장애의 원인이었다

전날(09-14) `d3a92648` 이 `virtual_join/unique_key.py` 를 세웠다 — 「유일 인덱스는 «제품이» 세운다」. 그 첫 벌의
`ensure_once` 는 `ASSY_VJOIN_AUTO_INDEX=0` 일 때도 **`inspect()` 를 불렀다.**

```
inspect()   중복·빈칸 탐침 = 접은 조인 키에 GROUP BY
숫자 키     -> 「invalid input syntax for type double precision」 — «읽기 경로»에서
같은 세션   -> 읽기 자신의 트랜잭션이 abort -> 그 뒤 «전부» 실패 (「이것저것 다」)
스위치      운영자가 잡은 OFF 가 «아무것도» 안 바꿨다 — OFF 가 탐침을 «그대로» 돌렸으니까
```
🔴 이것이 09-14~15 장애 다섯 중 «OFF 가 안 멎던» 부분의 답이다. 09:31 항목이 「넷째 장애는 TTL 5초」라 적었는데,
그 TTL 이 «무엇을» 5초마다 돌렸는지가 이 탐침이다.

## ② 변경 둘 — OFF 는 «맨 보고», 탐침 실패는 «잡고 롤백하고 캐시»

```python
# server/virtual_join/unique_key.py  ensure_once()
if switch in ("0", "false", "off", "no"):
    report = {"state": "skipped", "index": None, "invalid": [], "duplicates": [],
              "blank_keys": [], "created": None, "dropped": [],
              "skipped": "ASSY_VJOIN_AUTO_INDEX=%s" % switch}
    _TRIED[rule_name] = report
    return report                       # <- inspect() 를 «안 부른다»
try:
    report = ensure(db, table, columns, folds, apply=True)
except Exception as probe_error:
    try:
        db.rollback()                   # <- 뒤따르는 읽기가 abort 된 트랜잭션을 «안 물려받게»
    except Exception:
        pass
    report = {"state": "probe_failed", ..., "error": <첫 줄>}
    _TRIED[rule_name] = report          # <- 한 번 시도, 재시도 «없음»
    logger.warning("[VirtualJoin:%s] 유일 인덱스 자동 점검 실패(읽기는 계속): %s", ...)
    return report
```
종전 OFF 갈래는 `inspect(db, ...)` 결과에 `skipped` 를 얹어 «돌려주고» 있었다 — 보고는 정직했고 DB 는 만졌다.

## ③ 커밋 메시지가 남긴 «구조의 관찰» — 왜 가상 조인만 이렇게 부서지나

```
가상 조인       읽기«마다» SQL 을 다시 짓는다(캐시 5초 뒤에서) -> 나쁜 값 «하나»가 «모든 읽기»에서 «모든 사용자»에게
쓰기 경로 기능   한 번, 가드 안에서 돈다
```
이 문장은 같은 날 계획서 §0-ter(`21767513`, 「지배 원칙 넷」)의 ①·③ 이 됐다 — ③ 「스위치는 «진짜로» 끈다.
게이트: OFF 로 그 경로가 «호출되는지»를 «시험이» 단언한다 — 로그가 아니라」. 그 원칙의 «반면교사»로 이 커밋이 적혀 있다.

## ④ 그때 남아 있던 것

- **이 커밋에 시험이 «없다».** 커밋 메시지의 「상자에서 확인」은 셋 — OFF 가 DB 를 안 만짐 · 던지는 탐침이 한 번
  호출 뒤 롤백+캐시되고 읽기 세션이 살아 있음 · 깨끗한 조인은 여전히 inspect ok. 「OFF -> inspect 호출 0」을
  «시험이 단언»하는 일은 같은 날 10:4x S-240 지시서(`474f1aa9`)가 «다음 라운드 게이트»로 실었다 — 그 시점에 아직 없었다.
- 탐침 실패는 `_TRIED` 에 남아 «이 프로세스 수명 동안» 재시도되지 않는다. 즉 그 조인은 «이번 실행에서 자동 수리
  안 됨»이고, 그것이 설계다(홍수 대신). 재기동이 캐시를 비운다.
- **검증 자체는 여전히 «읽는 사람의 세션»에서 돌았다.** 이 커밋은 탐침 «하나»의 실패를 잡은 것이고, 선언 검증
  전체가 남의 세션을 쓰는 모양은 6분 뒤 `e88cb2be` 가 옮겼다(별 항목).
- 캐시 5초 TTL 은 그대로다(`015bfb38` 뒤로 «바뀔 때만» 로그).

📌 부류: **「DB 를 여전히 만지는 스위치는 반쪽 스위치다」** — OFF 인데 점검 SQL 이 돌아 운영이 안 멎었다.
   스위치의 게이트는 «호출 0» 시험이고, 그 시험이 이 커밋에는 없었다.

---
📎 「운영」이라 적은 줄은 장애 신고와 계획서를 옮긴 것이고, 수를 낸 줄은 없다.
📎 `d3a92648` 의 탄생 항목: `20260915_093113_the_day_strictness_invalidated_what_was_already_running.md` §②.
