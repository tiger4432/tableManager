# 라벨이 문자열이므로 숫자가 텍스트로 말해야 한다 — 그리고 없는 축은 빨개질 수 없다

> **일자:** 2026-08-04 | **관련 커밋:** (이 항목과 같은 커밋 — 보드 N7)
> **담당:** 사용자(운영 보고 2026-08-02 — 숫자 타입 slot 컬럼을 노출하자 조회가 죽었다) · server-pm 구현
> **대상:** `server/virtual_join_executor.py`(`resolved_expression`) · `server/database/crud.py`(`numeric_text_sql` 신설) · `server/main.py`(`get_column_filter_condition` override 숫자 브리지) · `server/tests/test_virtual_join_numeric.py`(신설) · `contracts/blank_predicate/`(numeric 해석 축) · 문서 4곳
> **선행 항목:** `cd3e0f4`(2026-07-31 — 해석값이 SQL 표현식이 된 라운드. **그 라운드의 실측이 「이 환경에 숫자 expose 컬럼 0개」였다**)

## 결함 — COALESCE의 마지막 팔이 문자열인데 앞의 팔이 숫자였다

`resolved_expression`은 `COALESCE(<왼쪽>, <오른쪽…>, '미상')`을 만든다. expose 컬럼이
`number`(→ Float)면 앞의 팔들이 double precision이고, PostgreSQL은 두 군데에서 거절한다:

1. `blank_to_null` 안의 `col = ''` — `blank_sql_condition`이 스스로 문서화한 전제조건
   (「text 타입이어야 한다」)의 위반. `invalid input syntax for type double precision: ""`
2. `COALESCE(double precision, text)` — `DatatypeMismatch`

그 컬럼을 이름 짓는 **모든 읽기**(컬럼 필터 · `?q=` 검색 · CSV SELECT)가 500이었다.
운영 실측(읽기 전용 스칼라 프로브, PG 18.3)으로 두 오류를 그대로 재현했다.

## 왜 아무것도 빨개지지 않았나 — 축이 존재하지 않았다

출하 시점 측정이 「숫자 expose 컬럼 0개」였고, 검색 라운드의 픽스처도 전부 string이었다.
술어가 참조하는 모집단이 비어 있으면 그 술어는 채점되지 않는다 — 실패한 것이 아니라
**한 번도 실행되지 않았다.** 그래서 이 라운드는 RED FIRST였다:
`test_virtual_join_numeric.py`를 먼저 쓰고 수정 없이 돌려 **6건 빨강**을 확인했다.

⚠️ 이 스위트(SQLite)에서 빨강의 **모양이 운영과 다르다**는 것 자체가 기록할 가치가 있다.
SQLite는 동적 타입이라 같은 식이 죽지 않고 **원시 float로 해석**된다 — `cast`가 `'3.0'`을
만들어 「화면은 3, 검색은 3.0」의 철자 분열로 나타난다. 운영은 크래시, 스위트는 오답.
같은 결함의 두 증상이고, 같은 수정이 둘 다 없앤다.

## 수정 — 숫자는 COALESCE에 앉기 전에 정본 텍스트가 된다

사용자 판정: **COALESCE는 STRING으로 캐스트하고, 정수값은 INT 철자로**(slot은 3이지 3.0이
아니다). 새 프리미티브 `crud.numeric_text_sql`이 그 철자의 SQL 쪽 단독 소유자다 —
`clean_str_value` 숫자 분기의 SQL 쌍둥이:

```sql
CASE WHEN col BETWEEN -9.2e18 AND 9.2e18
     THEN CASE WHEN CAST(col AS BIGINT) = col
               THEN CAST(CAST(col AS BIGINT) AS VARCHAR)   -- 3.0 -> '3'
               ELSE CAST(col AS VARCHAR) END               -- 2.5 -> '2.5'
     ELSE CAST(col AS VARCHAR) END                          -- BIGINT 밖: 방언 기본
```

- **방언에 기대지 않는다.** PG는 `cast`가 우연히 `'3'`을 주지만(shortest round-trip)
  SQLite는 `'3.0'`이다 — 접기를 식 안에 넣어야 두 방언이 같은 철자를 말한다. 실제로
  1e16에서는 PG의 평문 캐스트(`'1e+16'`)보다 **파이썬과 더 잘 일치한다**(`'10000000000000000'`).
- **NULL 팔이 따로 없다** — 모든 분기가 NULL을 전파한다. `blank_to_null`로 감싸지도
  않는다: 숫자는 `''`일 수 없으므로 숫자의 빈 판정은 IS NULL 하나가 맞고(계약 자신의
  문장), 감싸면 1,000만 행 WHERE에서 행마다 무의미한 CASE 하나를 더 산다.
- `main.get_column_filter_condition`에 브리지 하나: override(조인 해석 컬럼) 필터 값이
  숫자로 오면 `clean_str_value`로 같은 철자를 만든다(3.0 → '3'). 문자열 값은 손대지
  않는다 — 트림이 아니라 타입 브리지다.
- **string 컬럼의 SQL은 바이트 동일** — `_text_part`가 비숫자엔 그대로 `blank_to_null`을
  쓴다. 쓰기 거부 깔때기는 무변경.

## 증거 — 두 철자가 같은 답을 한다는 것을 계약이 채점한다

`contracts/blank_predicate`의 해석 이음새 픽스처에 `slot_no: number`를 추가하고
`test_the_two_resolutions_agree_on_a_numeric_column`이 숫자 코퍼스 전부(7.0 · 7.5 · 0.0 ·
1e16, funnel/bypass 양쪽)와 NULL→라벨 접기를 **양쪽 철자로** 채점한다. 결함 재주입으로
이 테스트가 실제로 빨개지는 것을 확인 후 원복. 운영 방언 증거는 구현이 **직접 컴파일한**
SQL을 PG 18.3에서 실행해 얻었다(손 사본 아님): `3.0→'3'`, `2.5→'2.5'`, `0.0→'0'`,
`-3.0→'-3'`, `1e16→'10000000000000000'`, `NULL→라벨`.

전체 스위트 1849 통과 / 2 스킵. 신규 파일 12/12.

## 함께 — 문서가 `cd3e0f4`를 사흘 늦게 따라잡았다

검색·필터·CSV 착지(`cd3e0f4`)가 §9의 미해결 둘을 해소해 놓고 **세 곳 걷기 규율**
(`virtual_join_rules §9` · `CONFIG_GUIDE §1` 행 · `FEATURE_CHECKLIST §1.1/§2.2-bis`)이
실행되지 않아, 세 문서가 사흘간 「필터가 없다 · CSV에 안 실린다」는 거짓을 말하고 있었다.
이번 라운드에서 §4-ter(숫자 철자 계약) 신설과 함께 세 곳을 실측 기준으로 걷었다.

## 교훈

- **측정이 0인 축은 그물이 아니라 구멍이다.** 「이 환경에 없다」는 출하 근거가 되지 못한다 —
  선언 하나로 생기는 축이면 픽스처가 그 축을 상시 활성화해야 한다.
- **테스트 방언이 관대하면 크래시가 오답으로 변장한다.** SQLite의 동적 타이핑은 타입 결함을
  통과시키고 값만 틀리게 한다 — 타입이 걸린 식은 운영 방언 스칼라 프로브(읽기 전용)로
  한 번은 실측할 것.
