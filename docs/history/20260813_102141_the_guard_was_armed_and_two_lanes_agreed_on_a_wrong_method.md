# The guard was armed, and two lanes agreed on the same wrong method

**Date:** 2026-08-13 10:21 · **Domain:** Ops (운영자 스크립트 / 읽기 전용 가드) · **Status:** 착지 — `b1dd2f0`

> ⚠️ **모든 측정은 격리 `assy_qa`(PostgreSQL 18.3 / SQLAlchemy 2.0.49 / psycopg2 2.9.11)
> 실측이다. 개발 사본이고 운영의 증거가 아니다.**
>
> 39분 전 `38b078c`가 낸 신고의 **정정**이다. 원 항목:
> [검출기](./20260813_094256_the_rule_the_obvious_detector_could_not_see.md)

---

## 내가 신고한 것과 실제

운영자 스크립트 셋이 **무장 안 된 읽기 전용 가드**로 돈다고 신고했다. **틀렸다.**

레인이 전제를 거절하고 제자리에서 다시 쟀고, 나는 그 정정을 보고로 받지 않고 **직접 다시
쟀다**:

```
A - the scripts' real shape (AUTOCOMMIT, then SET)
    transaction_read_only = on      CREATE TABLE = REFUSED      ARMED
B - what I measured before (plain connect, then SET)
    transaction_read_only = off     CREATE TABLE = ACCEPTED     NOT ARMED
```

셋 다 `SET` **전에** 커넥션에 `execution_options(isolation_level="AUTOCOMMIT")`를 건다.
그것이 바로 그 객체 위에서 psycopg2의 autocommit을 켜므로, **설정이 갇힐 트랜잭션이 애초에
열려 있지 않다.**

🔴 **운영에서 일어난 일은 아무것도 없다.** 쓰지 말았어야 할 것을 쓴 체크 패스는 없었다.

## 오늘 하루의 술어 문제, 두 번째 판

나는 **두 줄을 맥락 밖으로 꺼내 재현하고 그 결과를 코드의 동작이라고 불렀다.** 술어를
「이 코드」가 아니라 「이 두 줄」에 걸었고, 그 두 줄 «앞»에 있는 줄이 답을 뒤집는 줄이었다.

그리고 여기가 진짜 무서운 대목이다 — **스키마 감사 레인이 독립적으로 같은 실수를 해서
같은 틀린 결론에 도달했다.**

> **두 측정이 일치하는 것은, 둘이 같은 틀린 방법을 썼다면 정확성의 증거가 아니다.**

레인은 **내 서술을 세 파일의 주석에 써넣기를 거절했다.** 그게 옳았다.

## 그런데 밑에 있던 결함은 진짜였고 내가 말한 것보다 나빴다

안전 성질이 **우연히** 성립하고 있었다.

```python
# 🔴 THE DEFECT IS THAT ITS ONE SAFETY PROPERTY RESTED ON A SETTING THAT IS HERE FOR AN
# UNRELATED REASON. AUTOCOMMIT is in this file because `CREATE INDEX CONCURRENTLY`
# cannot run in a transaction block; the guard silently borrowed it. Remove it, reorder
# those two lines, or run one statement before the `execution_options`, and the SET
# lands inside an implicit transaction that began under the old default and keeps it.
```

`AUTOCOMMIT`은 **`CREATE INDEX CONCURRENTLY`가 트랜잭션 블록 안에서 못 돌기 때문에** 거기
있었다. 가드는 그것을 조용히 빌려 쓰고 있었다. 무관한 이유로 그 줄을 지우거나 두 줄
순서를 바꾸면 **가드가 소리 없이 해제된다.**

그리고 결정적인 것 — **아무것도 그 플래그를 되읽지 않았다.**

```
after SET       default_transaction_read_only = on   <- the variable one checks
after SET       transaction_read_only         = off  <- the one PostgreSQL enforces
after rollback  transaction_read_only         = off  <- the SET discarded outright
CREATE TABLE on that connection                      ACCEPTED
```

**두 배치가 스크립트 «안»에서는 구별되지 않았다.** 어느 쪽이든 자기를 보호된다고
보고했다. 운영자는 **점검이 아니라 문장 하나를 근거로** 그 스크립트를 안전하다고 건네받았다.

여기에 셋이 더 있었다 — 설정이 엔진이 아니라 **커넥션 하나**에 붙어 있어 두 번째 세션은
쓰기 가능으로 측정됐고, 풀에 반납된 커넥션이 **다음 체크아웃에 여전히 쓰기를 거절하는
세션**을 넘겼다.

## 고친 방식 — 발명하지 않고 «이 저장소에 이미 쓰여 있던 것»을 들어 왔다

```python
# 🔴 THE SPELLING HERE IS NOT NEW AND MUST NOT BE RE-INVENTED. It is the one
# `server/scripts/diagnose_wal_headroom.py` (class `RO`) and
# `server/scripts/diagnose_slow_after_ingest.py` already use: the setting goes in as a
# CONNECTION OPTION, which the server applies before this session's first transaction
# exists and re-applies to every transaction after it.
```

세 스크립트가 **같은 철자의 같은 네 함수**를 갖는다 — `-c default_transaction_read_only=on`을
**연결 옵션**으로 무장한 NullPool 엔진, **되읽어서 거절**하는 단언, `--apply`용 쓰기
거울, 그리고 「연결하고, 증명하거나, 거절하는」 문 하나.

되읽는 대상이 **거짓말한 그 변수가 아니라는 것**이 요점이다:

```python
def assert_readonly(conn):
    """Refuse unless POSTGRESQL ITSELF reports that this connection cannot write.

    A guard that cannot verify itself is the defect this exists to end, so the answer
    comes from the server rather than from the fact that an option string was passed.
    """
    armed = conn.execute(text("SHOW transaction_read_only")).scalar()
```

`default_transaction_read_only`는 **일부러 검사 대상이 아니다** — 위 두 배치 «양쪽»에서
`on`으로 읽히고, 그중 하나는 쓰기를 받아들인다.

`NullPool`도 정돈이 아니라 **하중을 받는 선택**이다: 옛 패턴은 «애플리케이션» 풀에서 빌린
커넥션에 세션 변수를 심어서 반납이 다음 체크아웃을 오염시켰고, 같은 프로세스에서 체크 뒤에
온 apply가 모든 CREATE에서 `ReadOnlySqlTransaction`으로 죽었다. **자기 엔진에는 오염시킬
다음 체크아웃이 없다.**

`SCHEMA_CANON` §3이 적어 둔 함정도 보존됐다 — **세는 패스가 apply가 필요로 하는 초기화를
같이 탄다.** 초록 체크가 깨진 apply를 못 가리도록.

## 검증은 «깨뜨리려는 시도»로 했다

**27회 시도, CREATE/INSERT/UPDATE 전부 거절.** 롤백 뒤에도 거절, 두 번째 커넥션에서도
거절. 그리고 **대조군으로 같은 쓰기 셋이 쓰기 가능 엔진에서 성공**한다 — 그래야 그 테스트가
「가드가 막았다」를 증명하지 「쓰기가 원래 고장났다」를 증명하지 않는다. 옛 패턴을 도로
주입하면 양쪽 다 빨개진다. `--apply`도 끝까지 돈다(17 checks). 새 파일
`test_readonly_guard.py`에 테스트 15개.

## 테스트 둘을 지웠고 하나는 «권고를 거절하고» 지키지 않았다

`SET SESSION`과 `invalidate()`를 단언하던 둘은 지웠다 — 그것들이 지키던 것이 이제
**테스트로만 지켜지는 게 아니라 구조적으로 불가능**해졌고, 코드가 더는 안 내보내는 문장을
단언하는 테스트는 **동작의 커버리지가 아니라 구현의 사본**이다. 아무도 되살리지 않도록
그 자리에 그 이유를 적어 두었다.

세 번째는 **레인의 권고에도 불구하고 안 지웠다.** 그것은 리포트 «모양»을 단언하고 그것은
진짜 커버리지다. 그게 깨진 이유는 **가짜(fake)가 새 가드를 만족시키지 못해서**였고 —
`assert_readonly`가 「답을 못 한다」는 이유로 거절했고, **그게 가드가 도는 모습**이다.

```python
if "transaction_read_only" in s:
    # 🔴 THIS IS NOT THE DOUBLE PRETENDING TO BE SAFE - IT IS TELLING THE TRUTH.
    ...
    # ⚠️ Do NOT read a green here as evidence that the guard works. That claim is
    # only ever earned against a real PostgreSQL session, in
    # `server/tests/test_readonly_guard.py`, ...
    return _Scalar("on")
```

가짜는 아무것도 실행하지 않으므로 `on`이 **정직한 대답**이지 우회가 아니다. 그리고 **여기의
초록이 가드에 대한 증거가 아니라는 것**을 파일 안에 큰 소리로 적었다.

## 그때 남아 있던 것

- **세 스크립트가 옛 패턴을 그대로 갖고 있다** — `drop_redundant_layering_indexes.py`,
  `check_missing_business_key.py`, `dev_env/snapshot_db.py`. **표시만 했고 안 고쳤다.**
- **같은 안전 성질에 도는 철자가 둘이다** — 여기의 네 함수와 `audit_schema_canon.py`의
  `postgresql_readonly=True`. 통합은 이 시점에 판정되지 않았다.
- 옛 패턴이 **실제로 무장돼 있었다**는 사실은 이 커밋의 측정에서 나왔고, 그 측정은
  **`assy_qa` 한 대, 특정 psycopg2/SQLAlchemy 조합**에서 나온 것이다.
- 39분 전 `38b078c` 본문의 오보는 **그대로 남는다.** 커밋 메시지는 고칠 수 없다.
