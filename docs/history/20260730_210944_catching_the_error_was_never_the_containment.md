# 예외를 잡는 것은 격리가 아니었다 — abort된 트랜잭션 위의 `COMMIT`은 정상 반환한다

> **일자:** 2026-07-30 밤 | **관련 커밋:** `f9289f6`
> **담당:** server-pm(구현) · 총괄(QA 재현 — 라이브 PostgreSQL, 읽기 전용)
> **대상:** `server/enrichment_config.py` · `server/enrichment_candidates.py` · `server/config_resolve_report.py` ·
> `server/chain_ingestion_worker.py`(주석만) · `server/tests/test_enrichment_candidates.py` ·
> `contracts/config_resolve_report/` · `docs/spec/ENRICHMENT_QUEUE_SPEC.md` · `docs/guide/config/enrichment_rules.md`
> **계기:** 커밋이 기록한 **스위트 1668 통과 / 0 실패**(`server/tests` + `contracts`), 결함 주입 6건 각각 독립 적색 후 되돌림.
> 이 항목 작성 시점에 HEAD에서 재실행 — `pytest server/tests contracts` **1668 passed, 0 failed** (258.6초). 커밋이 적은 수와 일치한다.
> **선행 항목:** `20260730_195606_did_the_config_take_effect_and_a_probe_that_confirmed_a_column_name.md`
> (이 라운드가 검수한 `f3fd785`)

## 배경 — QA가 「방금 출하한 커밋」에 데이터 소실 경로를 세웠다

직전 라운드 `f3fd785`는 「내가 쓴 config가 먹었나」에 답하는 어드민 표면을 냈다.
그 표면이 운영자에게 시키는 일이 정확히 **`candidate_for`를 선언하라**는 것인데,
선언에 오타가 하나 있으면 어떻게 되는지를 아무도 끝까지 따라가 보지 않았다.

총괄이 라이브 PostgreSQL에 대해 읽기 전용으로 재현한 사슬은 이렇다.

```
프로브 SQL 실패            -> ProgrammingError
같은 세션의 후속 질의      -> InternalError      (세션 오염)
abort된 tx 위의 commit()   -> 정상 반환          (서버가 ROLLBACK으로 바꿈)
```

세 번째 줄이 이 결함을 조용하게 만든 것이다. PostgreSQL은 abort된 트랜잭션의 `COMMIT`을
**ROLLBACK으로 변환하고 성공을 보고한다.**

> **드라이버 예외를 잡는 것은 격리가 아니다.** 세션은 이미 죽어 있고, **호출자도 로그도 그것을
> 모른다.** 예외를 잡았다는 사실이 「막았다」로 읽히는 것이 이 결함의 본체다.

## ⚠️ 폭발 반경을 처음에 틀리게 잡았다 — 이 라운드에서 배울 게 가장 큰 부분

보드 커밋 `79000d7`(20:14)은 이렇게 적었다.

> 「`apply_batch_updates`에 `db.commit()`은 **0개**이므로 그 주석의 「already committed」는
> 사실이 아니다」 · 「**작업 단위가 조용히 사라지고** 로그는 「chain write unaffected」라고 말한다」

**그 진단이 틀렸다.** `apply_batch_updates`는 커밋한다 — `server/database/crud.py:1623`.
근거로 쓴 grep이 깨져 있었다. 55분 뒤 `f9289f6`이 스스로 뒤집었고, 이 항목 작성 시점에
해당 줄을 직접 확인했다.

정정된 실제 피해는 **더 길다.**

| | 처음 진단 | 실제 |
|---|---|---|
| 체인 행 | 소실 | **내구적으로 커밋됨** |
| outbox 부기 커밋(`chain_ingestion_worker.py:702`, `processed_chain=True`) | — | **착지 못 함** |
| 그룹 | 사라짐 | **영원히 재처리됨** |
| 3-strike 격리 | — | **영영 발화하지 않음** |
| 클라 통지 | — | 없음 |

격리가 발화하지 않는 이유가 구조적이다. `retry_count`는 **실패 분기에서만** 오른다
(`chain_ingestion_worker.py`의 `db.rollback()` 뒤 루프, `retry_count >= 3`이면 `FAILED` +
`processed_chain=True`로 격리). 그런데 그룹은 **성공을 보고**하므로 그 분기에 들어가지 않는다.
카운터가 오르지 않으니 3회 상한도 오지 않는다 — **자기를 멈출 수 있는 유일한 장치가
자기가 만든 조건 때문에 닫혀 있다.**

> 잃는 것은 한 작업 단위가 아니라 **워커의 진행 자체**다. 처음 진단보다 지속 시간에서 나쁘다.

## 격리를 호출부가 아니라 **문장**에 붙였다

```python
def _isolated_execute(db, stmt, params) -> tuple:
    nested = db.begin_nested()          # SAVEPOINT
    try:
        result = db.execute(stmt, params)
        columns = list(result.keys())
        rows = result.fetchall()
    except Exception:
        nested.rollback()               # 세션은 살아서 나온다
        raise
    nested.commit()
    return columns, rows
```

`execute_reference_view`와 `execute_candidate_probe`가 **둘 다** 이 한 함수를 지난다.
자리를 문장으로 고른 이유가 이 라운드의 설계 판단이다.

- **진단 재질의가 자동으로 격리된다.** `_diagnose_probe_failure`는 「없는 컬럼」과 「깨진 뷰」를
  가르려고 **같은 세션에서** 뷰를 다시 부르는 유일한 호출이다 — 살아 있는 세션이 반드시
  필요한 그 한 곳이 규칙을 기억할 필요 없이 격리된다.
- **어드민 표시 라우트가 상속받는다.**
- **개념이 하나다.** 호출부에 붙였다면 새 호출자가 생길 때마다 「여기서도 감싸라」는 규칙을
  기억해야 한다.

⚠️ **`candidate_column_missing`은 PostgreSQL에서 도달 불가였다.** 진단 재질의가 죽은 세션에서
돌기 때문이다 — 그 진단이 **존재하는 이유인 바로 그 거절**이 운영에서만 나오지 않았고,
대신 일반적인 `view_error`로 뭉개졌다.

비용은 참조 문장당 왕복 2회(SAVEPOINT + RELEASE)다. 사용자 작성 뷰에 대한
`CANDIDATE_PROBE_MAX_ROWS`(5,000)행 GROUP BY 옆에서는 잡음이고, 대안의 값은 멈춘 워커였다.

## 🔴 더 깊은 이야기는 테스트다 — 초록이 운영에 없는 동작을 보증하고 있었다

`conftest.py`는 `DATABASE_URL`을 **의도적으로** `sqlite:///:memory:`에 고정한다(주변 환경변수가
스위트를 운영 DB로 겨누지 못하게 하는 하드 대입이다). 그리고 **pysqlite는 SELECT에
트랜잭션을 열지 않는다.** 그래서 abort 규칙 자체가 스위트에 존재하지 않고,
`candidate_column_missing`을 채점하던 초록 테스트는 **운영에서 도달할 수 없는 분기를 보증**하고
있었다.

여기서 두 갈래가 있었고, 한쪽은 함정이다.

> **Postgres 기반 테스트는 기본 스위트에서 SKIP된다. 그리고 스킵된 테스트는 초록 테스트가
> 보증하던 것과 정확히 같은 만큼 보증한다 — 즉 아무것도.**

그래서 복원한 것은 Postgres가 아니라 pysqlite에 없는 **규칙 하나**다. 엔진 이벤트로 abort
**정책**을 SQLite 엔진에 주입하고, 나머지는 전부 진짜로 둔다 — 진짜 프로브 SQL, 진짜 뷰,
SQLAlchemy가 실제로 내보내는 진짜 SAVEPOINT, 진짜 진단 재질의.

```python
def _before(conn, cursor, statement, parameters, context, executemany):
    head = statement.lstrip().upper()
    if head.startswith("ROLLBACK"):          # ROLLBACK TO SAVEPOINT 포함
        state["aborted"] = False
        return
    if head.startswith(("SAVEPOINT", "RELEASE", "COMMIT", "BEGIN")):
        return
    if state["aborted"]:
        raise _AbortedTransaction("current transaction is aborted, …")
```

그리고 **가드에 가드를 붙였다** — `test_the_abort_injection_actually_bites`가 주입이 실제로
무는지 먼저 채점한다. 주입기가 조용히 아무것도 안 하면 아래 두 테스트가 **결함 위에서 통과**하고,
그것이 애초에 이 스위트가 `candidate_column_missing`을 잘못 보증하게 된 바로 그 양식이다.

`test_a_bad_candidate_column_does_not_wedge_the_chain_work_unit`은 사슬을 끝까지 건다 —
`_run_chain_for_tx`가 문제의 부기 커밋을 실제로 수행하므로, 세션이 끼면 그 커밋에서 실패한다.

## 같은 QA 패스에서 나온 결함 셋

### ⓐ `distinct_truncated`가 계산되고 보고되고 **거절되지 않았다**

종전 주석의 논증은 「>limit이면 어차피 distinct가 2개 이상이니 `ambiguous`가 알아서 이름
붙인다」였다. 그 논증은 **같은 함수 두 줄 아래의 `clean_str_value` 접기를 빼먹었다.**

```
pairs = [('WF01', 1), ('WF01 ', 1)]   # limit: 1 → limit+1 = 2개만 돌아옴
  접으면 → {'WF01'} → distinct 1개 → 판정 `single`
  진실  → 후보는 둘(WF01, WF02). WF02는 잘려나간 그룹에 있었다.
```

**절단은 접기 이전 사실**이므로 그 자체가 이름 있는 거절이어야 한다. 잘린 읽기에서
「후보가 정확히 하나」는 증명할 수 없다 — `probe_truncated`와 완전히 같은 자세이고,
축만 하나 옆이다.

픽스처가 결함 축을 계속 건드리는지를 테스트가 **스스로 단언**한다(GROUP BY 출력 순서는 두
엔진 모두 미정의라, `WF02`가 조용히 안 잘리게 되면 이 테스트가 `ambiguous` 테스트로 변질된다).

### ⓑ `scanned`가 반환된 그룹만 세면서 스캔 상한과 비교되고 있었다

```sql
SELECT __c, COUNT(*) AS __n, SUM(COUNT(*)) OVER () AS __scanned FROM ( … ) …
GROUP BY __c LIMIT :__enrichment_limit
```

창 함수는 **GROUP BY 뒤·바깥 LIMIT 앞**에 평가되므로 그룹이 잘려도 값은 잘리기 전 전체 합이다.
종전에는 반환된(=잘린) 그룹의 count만 합산했고, 그 값이 `CANDIDATE_PROBE_MAX_ROWS`와
비교됐다 — **진짜로 잘린 읽기가 `row_truncated=False`로 읽힐 수 있었다.**
그룹이 잘렸는지와 행이 잘렸는지는 별개 사실이라 별개로 센다.

### ⓒ 파이썬 repr과 리터럴 마크다운이 운영자 문장으로 출하되고 있었다

`['slot']을(를)` · `**아무 효과가 없습니다.**` · JSON `true`를 `'true'`로.
공표된 계약이 「클라는 `detail`을 **그대로** 렌더한다」이므로 **하류에 고칠 자리가 없다.**
서버가 내보낸 것이 운영자가 읽는 것 전부다.

```python
def _as_json(value) -> str:
    """운영자가 편집한 그 파일의 문법(JSON)으로 값을 되돌려 보여준다."""
    return json.dumps(value, ensure_ascii=False)
```

`!r`를 안 쓰는 이유가 미관이 아니다 — Python repr은 `"true"`를 `'true'`로 적는데
**운영자가 연 파일에 작은따옴표는 문법 오류**다. 「당신이 쓴 값」을 되읽어 주는 문장에서
철자가 다르면 자기 파일을 못 알아본다.

계약에 `INV-F9-8`이 붙었다. 조각 스캔(`['` · `{'` · `**` · `!r`)에 더해, 조각으로는 볼 수 없는
절반을 위한 단언이 따로 있다 — `repr('20')`은 `'20'`이라 괄호도 중괄호도 없다.
**다음 사례는 계약에서 실패한다.**

## 아키텍처 영향

- **거절 어휘가 하나 늘었다** — `distinct_truncated`. 닫힌 어휘이고 스펙·가이드·계약이 함께 갱신됐다.
- **참조 질의의 실행 경계가 SAVEPOINT로 고정됐다.** 이후 참조 뷰를 실행하는 코드는 호출부에서
  아무것도 하지 않아도 호출자의 트랜잭션을 오염시키지 않는다.
- **`chain_ingestion_worker.py`는 주석만 바뀌었다.** 종전 주석은 「이미 커밋된 체인 쓰기를
  실패시키면 안 된다」고 적어 `except`가 격리인 것처럼 읽혔다. 지금은 **`except`가 무엇을 사지
  못하는지**를 그 자리에 적는다. 워커의 실행 경로는 한 줄도 바뀌지 않았다.
- 스위트에 **엔진 이벤트로 DB 정책을 주입하는 형태**가 처음 들어왔다. 「엔진이 없어서 못 하는
  테스트」와 「스킵되는 테스트」 사이의 세 번째 답이다.

## 그때 남아 있던 것

- **이 결함은 이 커밋 시점에 불발이다.** 라이브 `server/config/enrichment_rules.json`의
  `candidate_for` 선언은 **0건**이다(이 항목 작성 시점에 확인 — 선언이 있는 것은 서버가 읽지 않는
  `.sample`뿐이다). 오염 경로는 선언이 존재하고 그 안에 오타가 있을 때 열린다 — 그리고 직전
  라운드가 낸 어드민 표면이 하는 일이 정확히 「선언하라」다. **닫은 것은 노출이지 실현된 손상이
  아니다.**
- **`f3fd785`의 QA 판정은 GO가 아니라 GO-WITH-FIXES였다**(보드 `79000d7`). 이 커밋이 그
  수정분이다.
- 스위트 수치는 커밋이 적은 것과 재실행이 일치한다(위 「계기」). 재실행한 것은 HEAD
  (`9ac2083`)이지 `f9289f6` 체크아웃이 아니지만, `git diff --name-only f9289f6 9ac2083`에
  `server/` 파일이 **0개**라 같은 서버 코드다.
- **보드 `79000d7`의 「작업 단위가 조용히 사라진다」와 「`apply_batch_updates`에 `db.commit()`은
  0개」는 정정 전 서술로 남아 있다.** 보드는 총괄 소관이라 이 항목이 손대지 않는다 — 정정본은
  `f9289f6` 커밋 본문과 이 항목이다.
- **운영 서버 재기동 기록이 이 커밋에 없다.**
