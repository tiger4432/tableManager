# 이름만 비교하던 점검이 못 보던 타입이, 표 하나를 이미 죽이고 있었다

> **커밋:** `f396bd7` (2026-08-19 03:00) | **일자:** 2026-08-19 새벽
> **선행:** [`20260805_165500`](./20260805_165500_ask_at_boot_whether_the_models_still_match_the_database.md)(`f6406b1` — 부팅 점검을 건 커밋. 이 커밋이 무르는 것이 그때 적어 둔 한계다)
> **담당:** server 구현 — **판정은 소유자**(등급 `INFO`, 자동 `ALTER TYPE` 금지)
> **대상:** `server/schema_drift.py`(**+308 / −**) · `server/tests/test_schema_drift_startup.py`(**+259**, `def test_` 34 → **41**) · `server/scripts/check_schema_drift.py`(+18) · `docs/architecture/backend.md` · `docs/process/DOC_OWNERSHIP.md`
> **검증:** 드리프트 스위트 **41 passed** · 인접 `test_prod_import_env.py`+`test_system_schema_drift.py` **13 passed** · **주입 5종 전부 빨강** · 실물 PostgreSQL 스크래치에서 소유자의 예외 재현

## 배경 — 점검이 스스로 「나는 이것을 못 본다」고 적어 두고 있었다

소유자가 `dt_log`에 평범한 조회를 걸었다.

```
sqlalchemy.exc.InvalidRequestError: Unknown PG numeric type: 1043
```

**1043은 `varchar`다.** `table_config.json`이 `number`로 선언한 컬럼이 varchar 위에 앉아
있었고, psycopg2의 numeric 결과 처리기는 float/decimal/int 밖의 OID를 못 읽고 예외를 던진다.
SQLAlchemy는 매핑된 컬럼을 **전부** SELECT에 실으므로 — 그 컬럼을 읽지도 않는 코드까지 —
**그 표의 모든 조회가 죽는다.**

언제부터였는지 모른다. **아무 데서도 보고되지 않았기 때문이다.** 점검의 docstring이 이유를
스스로 적어 두고 있었다: 「**이름**을 비교하지 타입은 비교하지 않는다」. 26개 표를 훑으니
같은 모양이 3건 더(`bonding_log.core_slot`·`bonding_log.dt_slot`·`dt_map.dt_slot`),
거짓 선언이 1건(`lot_event.event_time` — `datetime` 선언, 실물 varchar) 있었다.

## 버킷 둘 — 행동이 다르면 같은 줄에 세우지 않는다

- **`type-breaking`** — 숫자 선언 위에 숫자 아닌 컬럼. **그 표가 지금 아무것도 대답 못 한다.**
- **`type-mismatch`** — 나머지 계열 불일치. 조회는 되고 **선언이 거짓말을 한다.**

breaking을 위로 정렬한다. 둘 다 `INFO`라서, 어느 쪽을 먼저 손대야 하는지 말해 주는 것이
**종류와 순서밖에 없다.**

**breaking은 상대 계열을 «묻지 않는다».** `_type_family`가 인식하는 계열은 넷(number·
datetime·text·boolean)뿐이고 jsonb·bytea·배열은 「모름」인데, 숫자 선언은 상대가 **무엇이든**
numeric이 아니면 터진다. 계열 비교로 물었으면 `number` over jsonb를 건강하다고 답했을 것이다.

## 등급은 `INFO`이고 종료 코드는 안 움직인다 — 그러나 «인쇄된다»

소유자 판정이다. 이유는 아래 자동 수리 금지와 한 몸이다: **돌릴 수리가 없는데** 게이트를
빨갛게 만들면 사람이 판단을 내릴 때까지 **계속** 빨갛다. 빠져 있던 것은 거절이 아니었다.

> **아무 데서도, 어느 부팅에서도, 한 번도 인쇄되지 않았다는 것이 빠져 있던 것이다.**

그래서 이 라운드가 `INFO`의 뜻을 바꿨다. 종전 `INFO`는 **계산만 하고 배너에 안 찍히는** 등급
이었고 — 그것이 정확히 `dt_log`가 앉아 있던 상태다 — 이제 배너 맨 끝에 전용 구역이 붙는다
(breaking이 있으면 `warning`, 없으면 `info`). 빨간 블록 **밖**이고 **뒤**인 이유는, 그 블록의
마무리 문장(「컬럼이 생길 때까지」·「마이그레이션을 돌려라」)이 타입의 처방이 아니기 때문이다.

## `ALTER TYPE` 자동화 금지 — 근거를 task 파일이 아니라 «코드»에 박았다

다음 사람은 `_sync_repairs`를 읽으며 「왜 타입은 안 고치지」라고 묻는다. 답이 거기 있어야 한다.

```
dt_log.core_slot    숫자 아님 4,567행   예: C14, C23, C19
dt_log.dt_slot      숫자 아님 4,567행   예: S18, S25, S13
lot_event.event_time  파싱 실패 0건 — 그러나 형식 3종 + NULL 522
```

`C14`는 **접두사 붙은 식별자**다. 캐스팅은 거절되거나, 접두사를 떼고 `14`를 저장해
**`C14`와 `S14`의 구분을 4,567행에서 조용히 없앤다.** `event_time`은 더 나쁘다 — **파싱이
성공하므로** 캐스팅이 성공을 보고하고, 타임존 기준이 섞여 있어 일부 값이 **몇 시간 어긋난 채**
자리잡는다. 아무것도 예외를 던지지 않는다.

> **없는 컬럼은 올바른 수리가 하나뿐이라 sync가 해도 된다.
> 있는데 타입이 틀린 컬럼은 값의 «뜻»에 달린 결정이지 마이그레이션이 아니다.**

처방은 **선언 위치를 지목하고 거기서 멈춘다** — 「`table_config.json`의 `"dt_log"."dt_x"`가
`"number"`인데 실물은 VARCHAR」. 그리고 「캐스팅하지 말 것」을 문장으로 적는다.

## 채점 — 심어 놓고 «대조군»을 남긴다

종전 픽스처(`_narrow_copy`)는 남는 컬럼을 **전부 VARCHAR**로 만든다. 그 표에서는 「심은 것만
잡는 검출기」와 「보이는 것을 전부 잡는 검출기」가 **구분되지 않는다.** 새 픽스처는 한 표에서
breaking 하나(`stock_qty`)와 거짓 선언 하나(`graph_synced_at`)만 varchar로 심고 나머지는
선언대로 만든다. 그리고 **대조군** `unit_price`(같은 `number` 선언, 올바르게 생성)가 findings에
**없어야** 한다는 단언이 그 구분을 한다.

breaking 분류는 이 모듈의 «읽기»가 아니라 **라이브러리의 «행동»에** 채점한다 —
`Float().dialect_impl(psycopg2).result_processor(dialect, 1043)`에 직접 먹여 예외를 확인하고,
대조로 701(`float8`)은 조용한지 본다. SQLAlchemy가 규칙을 바꾸면 여기서 걸린다.

**주입 5종 전부 빨강**: 계열 비교 무력화 / breaking 버킷 제거 / 등급 상향 / 인쇄 제거 /
비교 반전. 등급 상향(M3)은 **종전부터 있던** 화이트리스트 가드(`test_a_drift_kind_nobody_
has_classified_yet_is_loud`)까지 같이 터뜨렸다 — 그 가드는 바로 이 타입 불일치를 위해 쓰였다.

## 실물에서 — 0건 보고는 그 자체로는 아무 값어치가 없다

라이브 DB: **breaking 0건**(소유자가 오늘 밤 넷을 고쳤다), exit **0**. 그런데 한 번도 무언가를
보고한 적 없는 점검의 「0건」은 증거가 아니므로, 스크래치 PostgreSQL을 세워 `dt_log.dt_x`를
varchar로 심었다 — `[INFO type-breaking]` **정확히 1건**, exit **여전히 0**, 그리고 매핑된
표에 select를 걸자 `InvalidRequestError: Unknown PG numeric type: 1043`. **소유자의 예외가
그대로 재현됐다.**

라이브에 남은 것은 `lot_event.event_time` **1건**(`type-mismatch`) — 실재하고, 미수리이며,
§7이 **자동 변환을 금지한 바로 그 컬럼**이다.

## 남은 것

- **`lot_event.event_time`** — 선언 `datetime` / 실물 varchar. 어느 쪽이 틀렸는지는 사람 판정.
- **대소문자 불일치** — 여전히 영원히 보고되고 영원히 안 고쳐진다(이 라운드 범위 밖).
- `raw SQL`은 안 터진다 — `text()`에는 선언 타입이 없어 결과 처리기가 안 붙는다. 배너 문구가
  「이 컬럼을 부르는 모든 문장」이 아니라 **「이 표를 SELECT하는 모든 조회」**인 이유다.
