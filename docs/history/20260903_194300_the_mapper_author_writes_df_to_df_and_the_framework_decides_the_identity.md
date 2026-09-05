# 맵퍼 저자는 «df -> df» 만 쓴다 — ①과 ③이 저자의 파일을 떠났고, 정체는 «프레임워크»가 정한다

> **커밋:** `f74f09c9` (19:18) · `ec118223` (19:30) · `47835320` (19:43) · 소유자 판정 `7ba18abc`
> | **일자:** 2026-09-03 저녁
> **레인:** 구현자(서버)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**

## 배경 — 정체를 «저자가» 철자하면 «양방향»으로 조용히 틀린다

`server/mapper_sdk.py` 의 모듈 독스트링이 세 걸음을 이렇게 적었다:

```
    ① payloads          -> DataFrame
    ② DataFrame + SQL   -> DataFrame        <- the only one the author writes
    ③ DataFrame         -> updates payload

and the goal is that ① and ③ leave the author's file. This module is where they go.
```

**①은 페이로드→프레임 경계, ③은 프레임→`{"updates": […]}` 경계다.**
`@mapper` 데코레이터가 그 둘을 «한꺼번에» 저자의 파일에서 걷어낸다.

### 이 결함은 «양쪽 다 조용하다» (2026-09-02 실측)

```
복합 대상 + 맵퍼가 키를 철자   assemble_composite_business_key 가 첫 문장에서 «돌아온다»
                             (그 항목이 이미 business_key_val 을 들고 있으므로)
                             -> 맵퍼의 «문자열»이 이긴다. 선언이 «안 따라진다»
                             -> 구분자나 컬럼 목록이 바뀌는 날 «그 맵퍼의 키만» 표류한다.
                                오류 «없음»
평범한 대상 + 키를 프레임워크에  updates[business_key] 를 business_key_val 로 올리는 것이 «없다»
                             -> 쓰기가 «정체 없이» 착지한다. upsert 가 다시 못 찾고
                                «매 실행마다 사본이 하나 더» 생긴다
                             -> unfilled_key_columns 가 그런 항목에 [] 를 답하므로
                                쓰기 전 게이트도 «못 잡는다»
```

그리고 갚아야 할 빚이 하나 있었다 — 이 변환이 가이드에 **«스니펫»** 으로 들어가 있었다.
즉 **앞으로 쓸 모든 맵퍼에 사본이 하나씩**이고, 그 줄 하나가 틀린 것으로 밝혀지면
**고칠 자리가 열다섯 군데**다.

## 저자가 «쓰던 것» → 저자가 «쓰는 것»

전 (`docs/guide/chain_ingestion_guide.md`, `f74f09c9` 가 삭제):

```python
def df_to_updates(df, *, source_name, updated_by):
    clean = df.astype(object).where(pd.notna(df), None)          # NaN/NaT -> None
    return {"updates": [
        {"updates": {k: (v.item() if hasattr(v, "item") else v)  # numpy scalar -> python
                     for k, v in rec.items()},
         "source_name": source_name, "updated_by": updated_by}
        for rec in clean.to_dict("records")]}
```
…에 더해 **대상이 복합 키를 조립하는지 «아무 도움 없이» 기억해야 했다.**

후 (`ec118223`):

```python
from mapper_sdk import mapper, sql

@mapper()
def my_mapper(df, db):
    ref = sql(db, "SELECT ... WHERE lot = :lot", {"lot": lot})   # reads on YOUR session
    ...
    return out                                                   # a DataFrame
```

## 🔴 ①  ③ 안의 핵심 결정 — `TABLE_CONFIG` 를 «저자가 아니라 프레임워크»가 읽는다

```python
    config = crud.TABLE_CONFIG.get(table_name) or {}
    composite_src = config.get("composite_key_source")
    key_col = config.get("business_key")
    clean = df.astype(object).where(pd.notna(df), None)
```
⚠️ `astype(object)` 가 «먼저» 와야 한다 — float 타입 컬럼에 `None` 을 넣으면
**`NaN` 이 도로 들어간다.**
키 컬럼이 없으면 «이름을 대며 거절»한다 — **정체 없이 착지한 배치는 나중에
«애초에 안 보낸 것»과 구별할 수 없어서**다.

## 🔴 ② `sql()` 은 한 줄이고, 그 한 줄의 내용 전부가 «어느 연결이냐»다

```python
    return pd.read_sql(text(query), db.connection(), params=params or {})
```

```
체인 맵퍼는 워커의 «트랜잭션 안»에서 돌고 «커밋하면 안 된다»
   -> 체인이 stage 한 행은 «그 세션»에만 보인다
   -> 자기 연결을 여는 헬퍼는 «배치 전»의 DB 를 읽는다.  조용히, «동시성 아래에서만»
```

⚠️ 그리고 **이 시험은 처음에 판별식이 아니었다.** `db.connection()` 을 `db.get_bind()`
로 바꿔도(즉 «엔진»을 pandas 에 건네도 — 그게 결함이다) **행 단언이 초록이었다** —
SQLite 는 같은 풀 연결을 돌려주고 커밋 안 된 행을 어느 쪽으로든 본다.
시험이 **`db.connection` 이 «불렸는지» 감시하는 것**으로 바뀌었고, 행 단언은
**그 감시가 «대신하는 뜻»으로** 밑에 남았다.

## 우선순위와 기본값도 «편집자» 기준으로 정해졌다

```
규칙과 데코레이터가 «둘 다» 대상 표를 말하면  ->  «규칙»이 이긴다 (운영자가 편집하는 것)
updated_by 기본값 = 저자의 «함수 이름»
   -> 타이핑해야 하는 출처는 «직전 맵퍼에서 복사»되고 그다음 «틀린 이름»을 말한다
```

## 🔴 소유자가 은퇴 제안을 «뒤집었다»

`7ba18abc`. 레인이 **이 체크아웃에서** `BaseMapper` 소비자를 «둘» 세고 클래스 은퇴를
제안했다. 소유자가 **운영에는 그것을 상속하는 맵퍼들이 있다**고 답했다 —
**이 상자가 보여 줄 수 없는 사실**이라고 명시적으로 표시됐다.

## 🔴 그리고 `.gitignore` 가 «자리»를 정했다

```
.gitignore 가 server/mappers/* 를 «제외»하고 *.sample 과 ledger_v2_*.py 만 «다시 들인다»
=> SDK 는 server/mapper_sdk.py 로 갔다
   BaseMapper 는 mappers/base.py 에 정의돼 있었고 — «그것을 쓴 상자에만» 존재했다
   거기서 고쳐도 «운영에 절대 안 닿는다»
```
`47835320` 이 그것을 SDK 로 옮겼다. `mappers/base.py` 는 재수출 한 줄이 되는데
**그 편집은 라이브 상자에만 있고 커밋할 수 없다** — 가이드가 「기계마다 한 번 하는
편집」을 나른다.

⚠️ 그 시험은 **「둘 다 import 된다」가 아니라 `is` 를 단언한다** — 클래스가 «둘»이면
각자 옳게 답하다가 «한쪽만 고쳐지는 날» 갈라진다. 신선한 체크아웃에는
`mappers/base.py` 가 «없으므로» 그 반쪽은 실패가 아니라 «건너뛴다».

## 아키텍처 영향

- 맵퍼 저자의 파일에 남는 것은 **②뿐**이다. ①③은 `server/mapper_sdk.py` 가 한다.
- 정체(비즈니스 키)를 **프레임워크가 `TABLE_CONFIG` 를 읽어** 정한다. 맵퍼가 철자하지
  않는다.
- `BaseMapper` 가 **SDK 안에** 산다 — 그래야 «구현이 출하»된다.
- 가이드의 «스니펫»이 사라졌다. 사본이 늘지 않는다.

## 스위트 (전부 이 상자)

```
f74f09c9  10건. 변이가 각각 «다른» 하나를 빨갛게 한다 —
          복합 대상에 키를 철자 · 평범한 대상에 키를 안 실음 · astype(object) 제거로 NaN 생존
          · 스칼라 변환 제거 · 거절 제거
ec118223  18건
47835320  BaseMapper 의 공개 메서드가 «정확히 하나»임을 핀
```
⚠️ **이 상자의 pandas** 에서 `astype(object).to_dict("records")` 는 `int`/`float`/`bool`
/`Timestamp`/`str` 을 돌려준다 — **`.item()` 을 가진 것이 «없다»**. 그래서
`_python_scalar` 는 오늘 프레임 경로에서 **통과 함수**다. 프레임만 지나는 시험은
그 변환을 지워도 초록이었고, «실제로 그랬다». 옛 pandas 는 numpy 스칼라를 돌려주므로
**남기되 «직접» 시험**한다 — 안 재고 출하하는 것이 금지라서.

## 그때 남아 있던 것

- 🔴 **`mappers/base.py` 의 재수출 한 줄은 커밋되지 않았다** — 그 경로가 gitignore 다.
  가이드가 「기계마다 한 번」으로 나른다.
- **`BaseMapper` 소비자 수는 이 상자에서 «둘»이다.** 운영의 수는 모른다 —
  소유자가 「있다」고 말한 것이 이 시점의 근거 전부다.
- `mapper_sdk` 의 «평범한 키» 검사는 이날 손대지 않았다.
