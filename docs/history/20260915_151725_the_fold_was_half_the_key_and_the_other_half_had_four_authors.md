# 접기는 키의 «절반»이었고 나머지 절반은 저자가 «넷»이었다 — 그래서 숫자 키가 네 자리 중 셋에서 형 오류였다

> **커밋:** `ddd5b3ba` — fix(keys): one author for the key expression, so a numeric key stops being a type error (S-245)
> **일자:** 2026-09-15 15:17
> **레인:** 구현자(서버) — 큐 순서 S-249 → S-242 → S-240 → **S-245** → S-246 → S-247(재개 브리프 `44604384`) → 착지 → 보고 `8c893ea6`(RUN.md §2-bis 에 「double precision」 행) → 총괄 닫힘 `3343d830`
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **스위트:** 신설 **11** · 기존 **1 변경**(단언이 «발견» 그 자체) · 변이 **8 «전부» 빨강** · 키 식·표기·가상 조인·프로브 모집단 **758 passed** · `--collect-only` **6,689** 에러 0 (구현자 보고). 총괄 확인 「가상 조인·표기·조인 모집단 903 passed · 부팅 오류 0 · 체인 17 · 재기동 PID 32716」(`3343d830`).

## ① 왜 — 소유자 「더블 프리시전 자료형 오류 — 내가 이런거 뜨게하지 말랬지 알아서 접어서 하라고」

같은 날 오전 `fd53b87b` 가 `join_into` «한 자리»에 형 접기를 넣었다. 그런데 키 식은 그 자리에만 있는 것이 아니었다:
```
조인이 견주는 것 · 유일 인덱스가 서는 것 · 중복 프로브가 묶는 것   전부 coalesce(fold(col), '')
그중 «접기»만 저자가 하나(notation_norm)였고, 그 «바깥 두 조각»(형 · NULL)은 네 자리가 각자 적었다:

   chain.join_into._folded                    캐스트 있음 — 다만 CAST(... AS TEXT)   (09-15 오전에 고친 자리)
   virtual_join.executor.join_onclause        캐스트 «없음»                          (읽기 경로)
   virtual_join.config.index_key_expression   캐스트 «없음»                          (인덱스 DDL)
   virtual_join.unique_key._expressions       캐스트 «없음», 그리고 «표를 안 받음»
```
그래서 `number` 조인 키가 넷 중 «셋»에서 `invalid input syntax for type double precision: ""` 로 답했다. 제일 나쁜 자리는 프로브다 — `GROUP BY coalesce(number_col, '')` 가 «읽기 경로»에서 던지고, 던진 문장은 그 읽기가 이미 들어와 있던 트랜잭션을 abort 한다. 「모든 체인을 껐는데 에러가 계속 난다」의 한 자리가 이것이었다.

⛔ 그리고 여기의 불일치는 «빨개지지 않고 조용해진다». PostgreSQL 은 질의 식이 인덱스 식과 «일치할 때만» 식 인덱스를 쓴다 — 두 번째 철자는 천만 행 표에서의 순차 스캔이고 시험은 전부 초록이다(S-181). 이것이 「호출자마다 한 함수」가 아니라 「렌더링마다 한 함수」인 이유다.

## ② 변경 — 쌍이 `notation_norm` 에 살고, 자리 넷이 그것을 «지난다»

```python
# server/notation_norm.py  — 접기 «옆»에
class _TextCast(FunctionElement):            # PostgreSQL 에서 `x::text`, 그 밖에서 CAST(x AS TEXT)
    ...
def key_expression_sql(column, rules=None):   # SQLAlchemy 요소 — 조인이 «견주는» 것
    if not is_text_type(getattr(column, "type", None)):
        column = _TextCast(column)            # 캐스트는 «컬럼»에, 접기 «앞»에
    if rules:
        column = fold_notation_sql(column, rules)
    return func.coalesce(column, "")

def key_expression_text(inner_sql, rules=None, text_column=True):   # PostgreSQL 문자열 — 인덱스가 «서는» 것
    if not text_column:
        inner_sql = "%s::text" % inner_sql
    if rules:
        inner_sql = fold_sql_text(inner_sql, rules)
    return "coalesce(%s, '')" % inner_sql
```
```python
# server/virtual_join/config.py
def column_is_text(table, column) -> bool:    # 모르면 「예」 — 옛 식이 «안전한 방향»이다
def index_key_expression(column, fold_rules=None, table=None) -> str:
    return notation_norm.key_expression_text('"%s"' % column, fold_rules, text_column=column_is_text(table, column))
```
```
join_into._folded          -> notation_norm.key_expression_sql(column, fold)
executor.join_onclause     -> key_expression_sql(left) == key_expression_sql(right)
unique_key._expressions    -> (table, columns, folds) 를 받는다 — 프로브가 «인덱스가 선 식»으로 GROUP BY 한다
crud · migrations 호출자   -> index_key_expression 에 «표»를 넘긴다 (형의 유일한 재료가 표 이름이다)
```

## ③ «이미 고쳐졌던» 자리가 «틀린 철자»였다 — 기존 시험 하나의 변경이 그 발견이다

```
normalize_index_expression   `::text` 를 «PG 가 인덱스 정의를 렌더할 때 붙이는 잡음»으로 지운다. CAST(... AS TEXT) 는 «안 지운다»
::text                       캐스트 «없는» 인덱스와 «같은 정규형» -> 어느 쪽으로 세운 인덱스든 인정된다
CAST(... AS TEXT)            정규형이 다르다 -> 인덱스가 «있는데» 그 조인은 영영 «미승인»
```
오전의 `join_into` 가 고른 것이 후자였다. `test_a_number_key_is_compared_as_text_and_a_text_key_is_left_alone` 이 `CAST(t.num AS TEXT)` 를 박고 있었고, 이 커밋에서 `t.num::text` 로 «바뀌었다» — 부수 피해가 아니라 발견이다.

## ④ 캐스트는 «조건부»이고, «순서»가 바뀌었다

```
문자 컬럼   «바이트 동일». 무조건 캐스트를 붙이면 «모든 문자 조인의 요구 식»이 한꺼번에 바뀌고 기존 인덱스가 안 덮는다 — 장애
모르는 컬럼  «문자»로 답한다 = 어제의 식. 숫자 키는 그 자리에서 어제만큼 «그대로 고장»이지만, 그 고장은 «시끄럽다»
순서       캐스트를 «컬럼»에 건다. 접기 구문이 자기 형을 String 으로 선언하므로 접은 «뒤»에 물으면 답은 언제나 「이미 문자」
          오늘 그게 안 틀리는 이유는 선언 검증기가 «비문자 컬럼의 접기»를 거절하기 때문 — 순서를 «못 박을» 이유이지 운에 맡길 이유가 아니다
```
변이 「캐스트를 접기 뒤에」는 처음엔 «안 잡혔다» — 그래서 단언이 한 줄 늘었다(캐스트가 «컬럼»에 묻는지).

## ⑤ 시험 픽스처의 한 판정 — `Table` 이 아니라 «모델»을 등록한다

`column_is_text` 는 `DYNAMIC_TABLES` 의 «매핑된 클래스»에서 `getattr(cls, column)` 으로 `InstrumentedAttribute` 를 얻는다. 픽스처가 컬럼 «컬렉션»을 등록하면 운영과 «다른 객체»에 형을 묻게 되고, 실제 경로가 답을 «못 하든 말든» 초록이 된다. 그래서 픽스처는 `declarative_base` 로 모델을 만들어 `DYNAMIC_TABLES` 에 심는다.

## ⑥ 아키텍처 영향

- 키 식 `coalesce(fold(col[::text]), '')` 의 저자가 «하나»(`notation_norm` 의 쌍)다. S-181 이 «null 접기»에 한 것(`fold_key_value` 한 함수)을 «형 접기»에도 한 셈이다.
- `index_key_expression` 은 이름과 호출자를 지키면서 «렌더링이 못 정하는 하나»(이 컬럼이 문자인가)만 정한다. 그 답의 재료는 «표 이름»이고, 호출 자리 전부가 표를 넘긴다.
- RUN.md §2-bis 에 「`invalid input syntax for type double precision: ""` 는 `ddd5b3ba` 부터 안 난다 — 재기동 뒤에도 나면 «다른 자리»」 행이 실렸다.

## ⑦ 그때 남아 있던 것

- **스위트는 SQLite 이고 `::text` 도 접기의 `regexp_replace` 도 없다.** 신설 11 의 단언은 전부 «PostgreSQL 방언으로 컴파일»한 것 — «철자»를 채점하지 «실행»을 채점하지 않는다. 숫자 키로 인덱스가 «실제로 서는지»는 이 커밋이 증명하지 않는다. 총괄 재기동(PID 32716)이 확인한 것은 「부팅 오류 0 · 체인 17」이다.
- 모델 등록부(`DYNAMIC_TABLES`)에 «없는» 표의 컬럼은 «문자»로 답한다 — 그 자리의 숫자 키는 어제와 «같은 고장»이다(현상 유지, 이 라운드가 «안 고친» 것).
- S-240 의 반쪽(`07a568ad`, `key.columns` 검사 칸)이 이 라운드와 «같은 사이»에 착지했다(총괄 닫힘 줄에 기록).
- 이 채널의 미답 «없음». 다음은 S-246.

---
📎 수는 구현자 보고·총괄 확인의 «박스 수»다. 「운영」이라 적은 줄은 없다.
📎 오전의 «한 자리» 접기: `20260915_112608_a_number_key_is_compared_as_text_so_the_machine_folds_the_type.md` · 읽기 경로의 프로브가 읽기를 오염시킨 길: `20260915_094114_off_still_touched_the_database_and_a_probe_poisoned_the_read.md` · S-181: `20260911_203000_two_blind_spots_got_screens_and_one_axis_got_one_function.md` §③.
