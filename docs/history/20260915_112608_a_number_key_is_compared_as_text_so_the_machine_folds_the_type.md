# 숫자 키는 «텍스트로» 견준다 — PostgreSQL 이 거절하기 전에 기계가 형을 접는다

> **커밋:** `fd53b87b` — fix(join_into): a number key is compared as text, so the machine folds the type instead of PostgreSQL refusing it
> **일자:** 2026-09-15 11:26
> **레인:** 총괄(소유자 이관 중 막힘 셋 가운데 「하나는 제가 바로 고침」, 보드 `2f4abb4e`)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **스위트:** 신설 시험 **1**(PG 방언으로 «컴파일된 SQL» 위에서 채점). 커밋 메시지에 모집단 수 «없음».

## ① 왜 — 소유자가 라이브 가상 조인을 쓰기 시점 join 종류로 «옮기다» 막혔다

```
소유자   「double precision 자료형 오류」 · 「내가 이런거 뜨게하지 말랬지 알아서 접어서 하라고」
자리     join_into._folded 의 NULL 접기 `coalesce(col, '')` 는 «텍스트 문장»이다
         `number`(Float) 컬럼에 그 문장을 던지면 PG 가 「invalid input syntax for type double precision: ""」
결과     운영자가 «선언한» 조인이 «자기가 고르지 않은» 컬럼 형 때문에 죽었다
```
🔴 이 병은 «SQLite 가 초록»이라 시험이 못 봤다 — SQLite 는 PG 가 거절하는 것을 받는다. 그래서 시험은 «PG 방언으로 컴파일한 문자열»을 주어로 잡았다(실행이 아니라 «문장»을 잰다).

## ② 변경 — 비문자 컬럼만 TEXT 로 cast, 문자 컬럼은 «바이트 동일»

```python
# server/chain/join_into.py  _folded()
from sqlalchemy import Text, cast, func
from sqlalchemy.types import String
...
if fold:
    column = notation_norm.fold_notation_sql(column, fold)
if not isinstance(column.type, String):
    column = cast(column, Text)          # <- 숫자 키는 «양쪽» 모두 텍스트로 견준다
return func.coalesce(column, "")
```
```python
# 시험 — «SQL 문장»이 주어다
num_sql = str(join_into._folded(t.c.num, None).compile(dialect=postgresql.dialect()))
txt_sql = str(join_into._folded(t.c.txt, None).compile(dialect=postgresql.dialect()))
assert "CAST(t.num AS TEXT)" in num_sql
assert txt_sql == "coalesce(t.txt, %(coalesce_1)s)"     # <- 어제와 «같은 글자»
```
🔵 문자 키의 문장이 «한 글자도» 안 바뀌는 것이 이 수정의 절반이다 — 그 문장이 S-235 가 세운 표현식 인덱스와 «일치»해야 조인이 인덱스를 타고, 어긋나면 «오류 없이» 순차 스캔이 된다(그 함수 docstring 이 그렇게 적어 둔 자리).

## ③ 아키텍처 영향

- 「길이 0 인 문자열은 NULL 이다」(S-181 `fold_key_value`)의 SQL 쪽 철자가 «형»까지 접게 됐다. 다만 «이 파일 하나»에서다.
- 「기계가 접는다」는 소유자 상설이 «형»에도 걸린다는 것이 이 커밋에서 «처음» 코드로 적혔다.

## ④ 그때 남아 있던 것

- **같은 철자가 «셋 더» 있었고, 같은 구멍이었다** — 읽기 시점 가상 조인(`virtual_join/executor.py` onclause)과 S-235 의 인덱스 DDL(`config.index_key_expression…`). 이 커밋은 쓰기 조인 «하나»만 고쳤고, 나머지는 **S-245** 로 큐에 올랐다(커밋 메시지·큐 `812` 행). 즉 이 시점에 숫자 키의 «읽기 조인»은 여전히 PG 에서 거절될 수 있었다.
- 같은 오전, 소유자 케이스(log↔inventory `dt_wafer`)에서 **S-243** 이 산정됐다 — 쓰기 조인은 «채우기»를 못 한다(상위 층의 NULL 이 하위 값을 가리며, 가상 조인의 COALESCE 와 다르다). 이 커밋과 무관하지만 «같은 이관»에서 나온 것이라 여기 적는다.
- 이 커밋 «단독» 재기동은 없었다. 이 뒤 첫 재기동은 S-248 닫힘의 PID 22964(보드 12:0x)이고, 이 수정은 그때 같이 실렸다.

---
📎 「운영」이라 적은 줄은 소유자 원문뿐이다. 수를 낸 줄은 없다.
📎 join_into 의 탄생과 팬아웃 그물: `20260915_093113_the_day_strictness_invalidated_what_was_already_running.md` §② · `20260915_100554_a_left_row_with_two_right_answers_is_written_by_neither.md`.
