# SAVEPOINT 를 여는 자리가 «하나»가 됐고, 그 가드는 «문장을 돌린다» — 가드가 없던 쪽은 제품이 아니라 «운영자가 복사하는 본보기»였다 (S-271, 판정 414)

> **커밋:** `6ea4f7b2` — fix(session): one seat opens every SAVEPOINT, and it RUNS the statement (S-271, ruling 414)
> **일자:** 2026-09-16 11:32
> **레인:** 구현자 · 지시 `86261620`(부류로 닫아라) → 실측 보고 `dee6f0c5` → 판정 `a4b4c4ca`(414) → 착지 → 보고 `17f60b97`
> **측정 상자:** 이 워크스테이션 + 이 박스의 PostgreSQL. **운영이 아니다.**
> **스위트:** `_isolated_execute` · `pg_abort_semantics` · `enrichment.config` · `operator_line` · `session_contract` 를 이름으로 드는 평범 스위트 **764 passed / 36 skipped** · `scripts/run_pg_tests.py` **90 passed / 0 failed** · `pytest tests --collect-only -q` **6,803 · 0 errors**(커밋 본문 · 보고).
> **파일:** `server/session_contract.py`(신규 111줄) · `server/enrichment/config.py` · `server/mappers/cross_table_lookup_mapper.py.sample` · `server/operator_line.py` · `server/tests/test_a_savepoint_is_opened_by_one_seat.py`(신규 265줄) (+417 / −28)

---

## ① 왜 — 실측 표가 «지시의 전제»를 뒤집었고, 그것이 이 라운드의 시작이다

총괄 지시는 「트랜잭션 상태를 «가정하는» 좌석이 여럿이니 부류로 닫아라」였다. 구현자가 먼저 센 것(S-271 ①):

```
세션을 «빌리고» 트랜잭션 상태를 만지는 좌석            43
그중 SAVEPOINT 를 여는 «추적 코드» 좌석                «1»  — 그리고 그 하나는 «이미 묻고 있었다»
가드가 «없는» 쪽                                     mappers/cross_table_lookup_mapper.py.sample
```

**가드가 없던 것은 제품이 아니라 «저장소가 배포하는 본보기»였다.** 그리고 라이브 맵퍼는 gitignore 라 **그 본보기의 사본이 운영에 몇 벌인지 아무도 못 센다.**

총괄이 판정 414 에서 그 전복을 명시적으로 받았다:

> 당신 표가 제 전제를 뒤집었고, 그게 맞습니다 … 25P01 은 「가정이 흔하다」가 아니라 **「유일한 가드가 못 덮는 갈래가 있었다」**였고 그 갈래는 S-272 로 닫혔습니다. 지시의 그 줄은 «틀린 전제»였습니다.

---

## ② 판정 414 가 얹은 «성질» — 「가드는 문장 «옆»이 아니라 그 문장을 «돌리는» 것」

```
🔴 사유: 이 라운드의 주어가 «운영자가 복사해 고치는 틀»이다.
   가드가 옆줄이면 복사한 사람이 그 줄을 «지워도» 코드가 «돈다» -> 본보기가 다시 두 경로가 된다
   가드가 일을 «감싸면» 지우는 순간 «눈에 띄게» 깨진다
=> 판별식: 「그 줄을 지우면 기능이 도나」. 돌면 그 모양은 부족하다
⚠️ 이름·시그니처·컨텍스트매니저 여부는 «구현자가» 정한다 — 총괄이 정하면 표를 먼저 요구한 뜻이 없어진다
```

구현자가 고른 모양:

```python
def in_savepoint(db, where: str, work):
    """`work()` 를 SAVEPOINT 안에서 «돌린다» — 필요한 트랜잭션을 먼저 세우고.

    `where`  어느 좌석이 요구했나. 거절 줄의 대괄호에 들어가 운영자의 «검색어»가 된다
    `work`   인자 없는 콜러블. 이 함수가 «부른다» — 그래서 이 줄을 지우면 일이 «안 돈다»
    """
```

소비처 둘이 **판단 세 줄씩을 잃고** 한 줄이 됐다:

```python
# server/enrichment/config.py — 제품 좌석
def _run():
    result = db.execute(stmt, params)
    return list(result.keys()), result.fetchall()

return session_contract.in_savepoint(db, "reference_view", _run)
```
```python
# server/mappers/cross_table_lookup_mapper.py.sample — 운영자가 복사하는 틀
return session_contract.in_savepoint(db, "cross_table_lookup", query.all)
```

---

## ③ 🔴 첫 판이 «틀렸고 PG 증명이 잡았다» — 이 라운드가 산 것

구현자 첫 설계는 `begin_nested()` «만» 감쌌다. 진짜로 오염된 연결에 대고 재 보니:

```
SQLAlchemy 는 SAVEPOINT 문장을 «미룬다»
  -> begin_nested() 는 SessionTransaction 을 «정상 반환»한다
  -> 서버는 그 «안의 첫 문장»에서 거절한다
=> 여는 자리만 감싼 가드는 «이 스위트에서 초록», 운영에서 «조용»
   — 이 라운드가 없애려던 «바로 그 모양»이다
```

그래서 세 팔(열기 · 일 · 풀기)을 전부 다룬다. 그리고 «일 팔»의 처리가 반직관적이라 코드가 사유를 적는다:

```python
try:
    answer = work()
except Exception as exc:                                           # noqa: BLE001
    if _is_no_active_transaction(exc):
        # ⚠️ NO `nested.rollback()` ON THIS ARM. There is no savepoint to roll back
        # to - the server never took it - and asking raises a second 25P01 that would
        # replace the seat's name with a driver sentence again.
        raise _refused(where, exc)
    nested.rollback()
    raise
```

그 주석 자체가 「이 코멘트가 그 프로브가 산 것」이라고 적는다.

---

## ④ 거절은 «드라이버 문장»이 아니라 «좌석 이름이 실린 줄»

```python
NO_ACTIVE_TRANSACTION = "25P01"      # 🔴 메시지가 아니라 «코드». 한국어 서버 메시지로는 못 가른다
```
```python
def _is_no_active_transaction(exc) -> bool:
    for candidate in (getattr(exc, "orig", None), exc):   # ⚠️ 감싸인 것과 날것 «둘 다»
        ...
```
```python
def _refused(where: str, exc) -> SessionNotUsable:
    logger.error("%s", operator_line.line(
        "Session", where,
        "이 세션의 연결이 트랜잭션을 열 수 없는 상태라 문장을 «격리해서» 돌릴 수 "
        "없었습니다 — 이 요청은 거절했고 세션은 그대로 둡니다",
        operator_line.restart_to_clear_the_pool()))
    return SessionNotUsable(...)
```

`operator_line` 의 닫힌 어휘에 행동 하나가 더해졌다(`restart_to_clear_the_pool`). 그 docstring 이 **이 오염의 수명**을 적는다 — 「오염은 «연결 하나»에 붙어 그것이 풀에서 밀려날 때까지만 산다 — 그래서 다음 요청은 멀쩡할 수 있고, «반복»되는 것이 신호다」.

⚠️ 「데이터를 고치라」도 「선언을 고치라」도 **아니다.** 이 제품에서 행동을 잘못 고르면 사실이 사라지는 자리들과 같은 규율이다.

---

## ⑤ 게이트 — 총괄이 조인 둘을 그대로 지켰다

| 단언 | 모집단 | 무엇을 막나 |
| --- | --- | --- |
| AST 오라클: `server/` 아래 **`.py` 와 `.py.sample` 둘 다**에서 `begin_nested` 를 부르는 함수는 `session_contract` «자신»뿐 | **평범 스위트** | 어느 박스에서나 참인 단언이라 PG 를 안 기다린다. 두 좌석을 stash 하니 «둘 다 이름 대고» 빨강 → 고친 뒤 **0** |
| 자기검사: 오라클에 «본보기의 옛 본문»을 먹인다 | 평범 | 「0」이 「없다」이지 「안 본다」가 아님 |
| 시그니처가 «일을 받고», 반환값을 돌려주고, 성공에 RELEASE, 평범한 실패에 롤백+재던짐, 트랜잭션 없으면 연다 | 평범 | 판정 414 의 «성질» 자체 |
| 거절이 좌석 이름을 싣고 `25P01` · `no_active_sql_transaction` 을 **안** 싣는다 | 평범 | 드라이버 문장이 운영자에게 그대로 가는 것 |
| 관련 없는 드라이버 오류는 «안 삼킨다» | 평범 | 좁음이 넓어지는 수리 |
| **인시던트 자체를 재건**: autocommit 인 채 풀에 남은 연결(S-272 가 닫은 누수) 위의 세션 — `in_transaction()` 은 True 인데 서버엔 BEGIN 이 없다 — 에 «진짜 문장»을 일로 준다 | **`@pytest.mark.pg`** | 거절이 «착지하는 자리»가 거기다. 평범 스위트의 passed 만으로는 이 부류에 대해 아무 말도 못 한다 |

`git grep begin_nested -- server`(시험 제외)로 오늘 재면 실행 가능한 호출은 **`server/session_contract.py:72` 하나**이고 나머지 셋(`chain/ingestion_worker.py:125` · `enrichment/config.py:1433` · `parsers/directory_watcher.py:148`)은 **전부 주석**이다.

---

## ⑥ 지은 것과 «안 지은 것»

```
✅ 지었다    SAVEPOINT 부류 «하나». 저자 하나 · 소비처 둘 · 오라클 하나
⛔ 안 지었다  census 의 «commit 37 / rollback 32» 반쪽
```
판정 414 가 ㉡ 을 «안 한» 사유를 적는다 — 그 수는 **결함 수가 아니다**(`ingestion/checkpoint.mark_done(db, …)` 처럼 호출자가 «커밋되기를 바라는» 자리가 많다). 43 자리를 여는 라운드를 태울 근거가 «표에 없다». 🔵 다만 발견을 «죽이지 않고» 큐 **S-274**(`ab1bc5c0`)가 그 수와 함께 받았고, 거기 적힌 병은 수가 아니라 **「오늘은 어느 쪽인지 코드를 열어야만 안다」**이다.

---

## ⑦ 아키텍처 영향

- 저장소의 SAVEPOINT 저자가 **하나**가 됐다. 「그 SAVEPOINT 앞에 트랜잭션이 있나」를 각 좌석이 각자 판단하던 것이 한 함수로 접혔다 — 「한 축은 한 칸·한 함수」의 모양이다.
- **본보기와 제품이 같은 문장을 지난다.** 전에는 제품이 묻고 본보기가 안 물었고, 그 둘 중 **저장소가 볼 수 있는 것은 제품 쪽뿐**이었다.
- 25P01 이 **제품의 낱말**(`SessionNotUsable` + 좌석 이름이 실린 한 줄)로 번역된다. 「운영 로그는 못 붙인다 — 줄 자체가 조치를 실어야」의 적용이다.
- 오라클이 **`.py.sample` 까지 모집단에 넣는다.** 배포되는 본보기가 게이트의 사각이 아니게 됐다.

---

## ⑧ 그때 남아 있던 것

- 🔴 **이미 운영자 박스에 복사된 맵퍼들은 저장소 밖이라 그대로 가드 없이 남는다.** 판정 414 가 그것을 한 줄로 적으라 했고 보고가 적었다. 고칠 수 있는 유일한 자리는 «앞으로 복사될 틀»이고, 그것을 고쳤다. **몇 벌인지는 여전히 못 센다.**
- **운영은 아직 이 커밋을 안 받았다.** 보고가 「재기동 부탁드립니다」로 끝나고, 재기동은 총괄이 하기로 돼 있었다. 이 줄이 운영 로그에 실제로 뜬 것을 본 사람은 없다.
- 이 라운드가 닫는 것은 **25P01 을 «받는» 쪽**이다. 그것을 «만드는» 자리는 17분 전 `dc78afcd`(S-272)가 닫았다. `in_savepoint` 의 docstring 이 그 분업을 적는다 — 「S-167 이 그 갈래를 112회 재 두었고, S-272 가 그것을 만드는 자리를 닫았다. 여기서는 «남은 경우»를 한 줄로 바꾼다」.
- 라이브 참조 뷰 선언 안에 사용자가 자기 SAVEPOINT 를 쓰는지는 **못 쟀다** — D-40 조사표(`d7447248`)가 그 칸을 「라이브 선언을 제가 못 봅니다 / 못 잼」으로 열어 둔 채 남겼다.
- `commit 37 · rollback 32` 중 **몇이 틀렸는지는 아무도 아직 안 셌다.** 큐가 그것을 다음 라운드의 «첫 걸음»으로 적는다.
- `session_contract` 는 `operator_line` 하나만 import 한다(그 모듈은 stdlib 밖을 안 읽는다). 새 모듈이 패키지 의존을 안 늘렸다.

---
📎 이 항목의 수(764 / 36 · 90 / 0 · 6,803 · 43 / 1 / 37 / 32)는 «이 박스»의 것이다. 「운영」이라 적은 줄은 소유자가 주신 「25P01 이 난다」뿐이고, 「사본이 몇 벌인가」는 **못 세는 수**라고 적었다.
📎 사유 코드: S-166(SAVEPOINT 에는 앉을 트랜잭션이 필요하다) · S-167(빌린 연결의 함정, 112회 실측) · S-272(그것을 만드는 자리) · S-162(2026-09-11 공유 스코프가 맞은 같은 결함) · S-247(`operator_line` 이 있는 이유).
📎 같은 날 같은 부류 셋: D-39 `d00ac580` · S-269 `503b6129` · S-272 `dc78afcd`. 부류는 큐 S-274.
