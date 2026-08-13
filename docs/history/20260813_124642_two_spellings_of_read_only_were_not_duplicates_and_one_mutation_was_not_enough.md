# Two spellings of read-only were not duplicates, and one mutation was not enough

**Date:** 2026-08-13 12:46 · **Domain:** Server (운영 스크립트 / 안전 가드) · **Status:** 착지 — `1260c9b`

> ⚠️ **모든 측정은 이 박스의 격리 `assy_qa`(PostgreSQL 18.3 / SQLAlchemy 2.0.49 /
> psycopg2 2.9.11) 실측이다. 운영의 증거가 아니다.**

---

## 배경 — 복사가 안전 성질과 결함을 «같은 메커니즘»으로 퍼뜨렸다

전날 운영 스크립트 셋이 **우연히만 성립하는** 읽기 전용 가드를 달고 착지했다. 같은 날 문서
라운드(`68c9523`)가 그 셋이 각자 지어낸 것이 아니라 **카탈로그가 올바르다고 가르친 철자를
복사한 것**임을 확인했다.

집이 없는 안전 성질은 복사되고, **사본은 원본이 틀린 것을 그대로 들고 간다.** `server/db_safety.py`가
집이 됐다 — 이미 「이 프로세스가 닿으면 안 되는 DB에 닿지 못하게 한다」를 소유하고 있고, 중요한
경로들이 이미 import하는 파일이다.

틀린 철자의 정체는 모듈 안에 **측정과 함께** 박혔다.

```
#     `conn.execute(text("SET SESSION default_transaction_read_only = on"))`
#     is what a read-only pre-flight looks like. Measured on the isolated
#     `assy_qa` ... on a connection at the ORDINARY isolation level:
#
#         default_transaction_read_only = on    <- the variable one would check
#         transaction_read_only         = off   <- the one PostgreSQL enforces
#         CREATE / INSERT / UPDATE              ALL THREE ACCEPTED
```

SET 자체가 암묵 트랜잭션을 **시작**하므로, 그 트랜잭션은 옛 기본값 아래 열려 그 기본값을 유지하고
rollback은 SET을 통째로 버린다. AUTOCOMMIT으로 이미 전환된 연결에서는 같은 두 줄이 **작동한다** —
그것이 더 나쁘다. 성질이 **무관한 이유로 거기 있던 설정 덕에 우연히** 성립했다는 뜻이고, 플래그를
되읽지 않는 스크립트 안에서는 두 배치가 구별되지 않는다. **어느 스크립트도 되읽지 않았다.**

## 두 철자는 중복이 아니라 다른 문제를 풀고 있었다

합치는 것은 중복이 아니라 **능력을 제거**하는 일이었을 것이다.

- `CONNECT_TIME` — `-c default_transaction_read_only=on`을 `connect_args`에, `NullPool` 엔진에.
  **우리가 만든 엔진**이 필요하다(스크립트 여섯).
- `PER_TRANSACTION` — SQLAlchemy 자체 옵션 `postgresql_readonly=True`. **빌려온 엔진**에서
  동작한다. 스키마 감사가 이쪽을 필요로 하는 이유는 그 진입점들이 **호출자에게서 엔진을 받기**
  때문이다.

그래서 둘 다 **모드로 노출**됐고, 한쪽을 승자로 선언하지 않았다.

그리고 성질은 「올바른 모드를 고르는 것」에 기대지 않는다 — 틀린 모드는 **무장 안 된 연결**을
만들고 `assert_readonly`가 그것을 **거절한다.** 판정은 어느 갈래가 돌았는지가 아니라 서버가
`transaction_read_only`를 되읽어 주는 값에서 나온다.

## 주입이 «단계별»이라서 빨강이 뜻을 가졌다

| 주입 | 결과 |
|---|---|
| 되읽기만 제거 | **14 passed — 불충분.** 연결 옵션이 여전히 무장한다 |
| 연결 핀만 제거 | 문 7개 중 6개 빨강 |
| 둘 다, `CONNECT_TIME` 팔만 | 23 failed — **그리고 감사는 초록으로 남았다.** 다른 갈래이기 때문 |
| 둘 다, 양쪽 팔 | 24 failed, 문 7개 전부 빨강 |

**첫 행이 남길 값이다** — 단일 성질 변이는 「통과」했을 것이고, 그것이 가드가 도는 증거로 읽혔을
것이다. 셋째 행은 **한 갈래에 충분한 변이가 다른 갈래에는 눈이 멀 수 있다**는 것을 보여준다.
복원은 sha256으로 바이트 동일 확인했다.

이어서 문 일곱을 **각 스크립트가 여는 방식 그대로** 열었다 — 플래그 `on` 되읽기,
CREATE/INSERT/UPDATE 각각 거절, 명시적 rollback 뒤에도 셋 다 다시 거절, 같은 엔진의 두 번째
연결도 거절. **대조군**으로 쓰기 가능 엔진에서 동일한 세 문장이 성공하고 UPDATE 값이 되읽힌다 —
그래야 테스트가 **가드**를 증명하지 깨진 쓰기를 증명하지 않는다.

## 쓰기가 하나도 없는 스크립트

그 가드는 잉여인 정도가 아니라 **꺼져 있었다** — 측정값 `transaction_read_only=off`, 쓰기 셋 다
승인. 그런데 **그로부터 안전에 대해 따라 나오는 것은 없다.** 그 파일에는 쓰기 문장이 하나도 없기
때문이고, 보고서가 그것을 「구제」로 포장하지 않고 그렇게 적었다. docstring의 거짓 절은
삭제되지 않고 **측정과 함께 제자리에서 정정**됐다 — 그 docstring이 틀린 철자를 복사할 수 있던
자리 중 하나이기 때문이다.

## 🔴 저장소 전체로 간 것이 아니다

- `server/scripts/diagnose_db_health.py`는 `SET TRANSACTION READ ONLY`를 쓴다 — **첫 트랜잭션만**
  덮는다. 측정: rollback 이후 `off`이고 **CREATE 승인.** 그 docstring은 「세션이 핀으로 고정된다」고
  주장하고 있었고, 이것은 **운영자가 실제 DB를 가리킬 수 있는 진단 도구**다. 이 커밋은 그
  파일의 쓰기 문장을 감사하지 않았으므로 **규모를 재지 않았다.**
- `diagnose_slow_after_ingest.py`·`diagnose_wal_headroom.py`는 올바른 메커니즘을 쓰지만 플래그를
  되읽지 않고 이 집을 공유하지도 않는다.

## 숫자 하나를 다시 셌다

커밋 본문은 「스크립트에서 415줄의 중복 가드가 나왔다」고 적었다. `--numstat`으로 다시 세면
**415는 diff 전체의 삭제 줄 수**이고, 그중 **34줄은 테스트 파일**(`test_readonly_guard.py` 18,
`test_audit_schema_canon.py` 16)이다. 스크립트·마이그레이션 일곱에서 나온 것은 **381줄**이다.

그리고 그 일곱이 전부 줄어든 것도 아니다 — `drop_redundant_layering_indexes.py`(+79/-21),
`check_missing_business_key.py`(+60/-7), `dev_env/snapshot_db.py`(+34/-17)은 **늘었다.** diff
전체는 **+872/-415**로 순증이다. 통합은 저장소를 줄인 것이 아니라 **집과 그 집을 채점하는
테스트를 더한 것**이다.

## 그때 남아 있던 것

- `db_safety.py`에 238줄이 **새로 들어갔고 삭제는 0**이다.
- 읽기 전용 성질의 **유효한 철자가 둘**이고, 통합은 총괄 판정 대기였다.
- 옛 철자를 든 진단 스크립트 셋은 **손대지 않았고**, 그중 하나는 측정에서 CREATE를 받았다.
- 그 상태를 여전히 가르치는 문서 셋은 **다른 레인 소관**이라 이 커밋 밖에 있었다.
- 실행 확인은 전부 격리 `assy_qa` 대상이다. **운영 DB에는 아무것도 돌지 않았다.**
