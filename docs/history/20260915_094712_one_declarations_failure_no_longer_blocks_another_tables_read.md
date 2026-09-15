# 한 선언의 실패가 «무관한 표»의 읽기를 막았다 — 검증은 자기 세션으로, 거절은 규칙 «하나»로

> **커밋:** `e88cb2be` — fix(virtual-join): one declaration's failure refuses one rule, and never on the reader's session
> **일자:** 2026-09-15 09:47
> **레인:** 총괄(커밋 트레일러 Fable 5.1)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **스위트:** 신설 시험 **2**(파일 하나 `test_one_declarations_failure_does_not_block_another_tables_read.py`). 커밋 메시지에 모집단 수 «없음».

## ① 왜 — 소유자의 두 문장이 «설계 결함»을 그대로 이름 댔다

> 「이 가상조인 오류가 내가 건드리던 테이블과 완전 다른 건데 왜 뚱딴지같이 튀어나와서 막았던 거야?」
> 「그냥 모든 선언 무조건 다 돌면서 다 막아버렸네」

둘 다 맞았다.
```
캐시 미스마다    «읽는 사람의 세션»으로 «모든» 선언을 검증했다        (`executor._verified_by_left_table`)
규칙별 검증      try «밖»에 있었다                                (`config.load_verified_rules`)
표 B 선언 하나가 던지면  표 A 를 읽던 트랜잭션이 abort 된 채 남고, 아무것도 롤백 안 함 — 5초마다
```
🔴 09:41 `1497ea3e` 가 «탐침 하나»의 실패를 잡았다면, 이 커밋은 «검증 전체»가 남의 세션을 쓰는 «모양»을 옮겼다.
   둘은 같은 장애의 두 층이다 — 값 하나(탐침)와 세션(경계).

## ② 변경 둘 — 둘 다 «구조»다

```python
# server/virtual_join/config.py  load_verified_rules()
for rule in rules:
    try:
        result = verify_uniqueness(db, rule)
    except Exception as verify_error:
        try:
            db.rollback()
        except Exception:
            pass
        _say_once(("verify", rule["name"]), logger,
                  "[VirtualJoin:%s] uniqueness could not be verified (this rule only): %s", ...)
        _record(rejections, "rule", rule["name"],
                "uniqueness could not be verified: %s" % verify_error, code=CODE_SHAPE)
        continue                        # <- «이 규칙만» 거절, 루프는 계속
```
```python
# server/virtual_join/executor.py  _verified_by_left_table()
from database.database import SessionLocal
own = SessionLocal()                    # <- 읽는 사람의 세션이 «아니다»
try:
    for rule in vjc.load_verified_rules(own, known_tables=crud.TABLE_CONFIG):
        ...
except Exception as e:
    logger.error("[VirtualJoin] verified rules unavailable, NO join is in effect: %s", e)
    by_left, by_right = {}, {}
finally:
    try:
        own.rollback(); own.close()
    except Exception:
        pass
```
읽는 사람은 이제 «메모리만» 읽는다. 검증이 무슨 짓을 해도 물어본 읽기에는 닿지 않는다.

## ③ 시험이 소유자의 두 문장에서 «직접» 나왔다

```
test_one_rule_that_cannot_be_verified_refuses_only_itself
   B 의 검사가 던져도 -> verified == ["a_join"] · rejections subject == ["b_join"] · 같은 세션의 SELECT 1 이 «답한다»
test_the_readers_session_is_never_touched_by_verification
   검증 «전체»가 자기 세션을 «일부러» abort(SELECT 1/0)시키고 던져도
   -> rules_for() == [] (조인 없음으로 «안전하게» 기운다) · 읽는 사람의 세션 SELECT 1 == 1
```
📌 부류: **세션은 «경계»다** — 같은 세션이면 남의 실패가 «내» 트랜잭션이다. 「내가 건드리던 표와 완전 다른데」는
   증상이 아니라 «진단»이었다: 표가 다른데 막혔다면 공유된 것은 표가 아니라 세션이다.

## ④ 그때 남아 있던 것

- «캐시 미스마다 모든 선언을 검증»하는 모양 자체는 그대로다 — 자기 세션에서, 5초 TTL 로. 옮긴 것은 «누구의 세션»과
  «실패의 반경»이지 «빈도»가 아니다.
- 「검증 불가」 거절은 `CODE_SHAPE` 를 «빌려» 쓴다 — 자기 코드가 없다. 거절 목록에서 이 부류는 모양 오류와 같은
  코드로 보인다.
- `_verified_by_left_table` 의 바깥 `except` 는 여전히 «전체 붕괴 → 조인 없음» 갈래다(검증 «로더 자체»가 던질 때).
  둘째 시험은 그 갈래가 «안전한 쪽으로 기운다»는 것까지만 단언한다.
- 계획서 §0-ter ②(「값 하나가 배치를 죽이지 않는다 — PG 트랜잭션 abort 를 호출자에게 «전파»하지 않는다」)는 이 커밋
  «4분 전»(`21767513`, 09:43)에 적혔고, 그때 든 실물은 `1497ea3e` 의 `unique_key` 였다. 이 커밋은 그 원칙의
  «둘째» 실물이지 원칙의 출처가 아니다.

---
📎 「운영」이라 적은 줄은 소유자 문장을 옮긴 것이고, 수를 낸 줄은 없다.
📎 같은 장애의 앞 층: `20260915_094114_off_still_touched_the_database_and_a_probe_poisoned_the_read.md`.
