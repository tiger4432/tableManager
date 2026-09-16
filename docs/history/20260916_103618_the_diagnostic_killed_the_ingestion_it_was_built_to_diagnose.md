# 사흘짜리 인제션 정지의 좌석은 «진단기»였다 — 운영이 SQL 을 못 쳐서 만든 EXPLAIN 이, 진단하려던 그 인제션을 죽이고 있었다 (D-39)

> **커밋:** `d00ac580` — fix(ingest): the slow-prefetch diagnostic reads ids it already has, and can no longer kill the file (D-39)
> **일자:** 2026-09-16 10:36
> **레인:** 구현자 · 보고 `3128b024` · 응용 레인의 독립 census 가 같은 좌석에 닿음(지시 `319def58`) · 총괄 닫힘 `a5f23983`
> **측정 상자:** 이 워크스테이션. **운영이 아니다** — 그리고 이 항목의 핵심이 정확히 그것이다(③).
> **스위트:** 워처 모집단 **108 passed / 0 skipped** · `scripts/run_pg_tests.py` **88 passed**(보드 `a5f23983`).
> **파일:** `server/parsers/directory_watcher.py` · `server/tests/test_a_diagnostic_may_not_kill_what_it_diagnoses.py`(신규 99줄) (+142 / −3)

> 🔴 **복기(왜 사흘을 끌었나)는 `docs/process/INCIDENTS_2026-09.md` 가 정본이다.** 이 항목은 «무엇이 착지했나»만 적는다.

---

## ① 왜 — 진단기가 «자기가 소유하지 않은 상태»를 읽고 있었다

좌석은 `_maybe_explain_slow_prefetch` 다. 착지 `6f45a004`(2026-09-11 13:52), **224줄 신규 · 그 커밋의 파일 둘 다 소스 · 시험 파일 «0»**. 존재 이유는 정당하다 — 소유자는 운영에서 SQL 을 못 친다(판정 276). 그래서 제품이 «자기 실행계획을 스스로 찍게» 만든 것이다.

그것이 배치의 row id 를 표본으로 뽑는 줄:

```python
rid = getattr(row, "row_id", None)
```

**이 읽기가 공짜가 아니다.** 인제션 청크 루프의 실행 순서:

```
crud.apply_batch_updates(...)   내부에서 commit  ->  반환 객체가 «전부 만료»된다
db.commit()
...
finally: db.close()             ->  그 객체들이 «분리»된다
...
_maybe_explain_slow_prefetch(db, …, results, …)    <- 만료 + 분리된 객체를 «읽는다»
```

`expire_on_commit` 은 SQLAlchemy 기본값이고 이 저장소는 그것을 끈 적이 없다 — `server/database/database.py:76` 의 `sessionmaker(autocommit=False, autoflush=False, bind=engine)` 가 전부다. 커밋은 만진 객체를 만료시키고, 만료된 속성은 세션이 있어야 다시 읽는데 그 세션은 이미 닫혔다. 그래서 그 한 줄이 던진다 — **`DetachedInstanceError: Instance <…> is not bound to a Session`**.

그리고 그 호출은 **감싸여 있지 않았다.** 예외가 청크 루프를 뚫고 바깥 핸들러까지 올라가 **파일을 통째로** 데려갔다.

### 🔴 관문 «하나»가 소유자가 본 증상 셋을 전부 설명한다

```python
if already:                       return already   # 파일당 한 번
if steps.get("prefetch", 0.0) <= threshold:        # 그 청크의 선인출이 «느릴 때만»
    return already                                 # SLOW_PREFETCH_EXPLAIN_DEFAULT = 1.0
```

| 소유자가 본 것 | 왜 그런가 |
| --- | --- |
| 산출물이 **하나만** 안 들어감 | 다른 산출물은 문턱을 «안 넘어» 그 줄에 도달조차 안 한다 |
| **어제까지는** 됐다 | 그 표의 선인출이 문턱을 «넘어선 날»부터 시작된다 |
| `__force__` **도 안 됨** | 강제는 같은 파일을 다시 «느리게» 돌린다 → 같은 자리에서 또 던진다 |

---

## ② 바뀐 것 — 둘, 둘 다 좁다

### ⓐ 식별키를 «왕복 0» 으로 읽는다

```python
def _row_id_without_a_refresh(row):
    from sqlalchemy import inspect as sa_inspect
    try:
        state = sa_inspect(row)
    except Exception:                                    # not an ORM object at all
        return None
    identity = getattr(state, "identity", None)
    if identity:
        return identity[0]
    #: Not persisted yet — whatever is still loaded, without asking the database for more.
    return (getattr(state, "dict", None) or {}).get("row_id")
```

`row_id` 는 동적 표의 **PRIMARY KEY** 다 — `server/database/models.py:988` 의 `Column("row_id", String, primary_key=True)`. 그래서 `InstanceState.identity` 가 **곧 답**이고, 그 키는 세션이 객체를 «그 이름으로 정리해 둔» 것이라 만료와 분리를 «둘 다» 견딘다.

⚠️ 그리고 이건 무회귀가 아니라 «개선»이다 — 옛 읽기는 표본 50개마다 refresh SELECT 를 낼 수 있었고, **그 경로는 이미 느려서 이 진단기가 존재하는 경로**다.

### ⓑ 호출 자리가 잡는다

```python
try:
    _explained = _maybe_explain_slow_prefetch(db, t_name, _summary, results, _explained)
except Exception as _plan_err:                  # noqa: BLE001
    logger.warning(
        "[Ingest] %s slow-prefetch PLAN skipped (%s: %s) - the "
        "chunk is unaffected", t_name, type(_plan_err).__name__, _plan_err)
    _explained = True
```

`_explained = True` 를 같이 세우는 것이 핵심이다 — 같은 파일에서 다시 시도하지 않는다. 그리고 감싸는 자리가 **무엇이 조용해졌는지**를 찍는다.

⚠️ `_maybe_explain_slow_prefetch` 안에는 `_plan_digest` 가 **EXPLAIN 둘**을 같은(이미 닫힌) 세션에 낸다. 그것도 던질 수 있고, ⓑ 가 덮는 것은 ⓐ 하나가 아니라 «그 함수 전부»다.

---

## ③ 「이 코드는 이 박스가 «구조적으로» 못 밟는다」 — 그것이 시험 0 의 사유였다

그 함수의 자기 주석이 그렇게 적고 있다: 운영 선인출 **10 s**, 이 박스 **0.03 s**. 문턱은 **1.0 s**. 즉 스위트를 아무리 돌려도 **한 줄도 안 밟히는 코드**였고, 초록이 그 코드에 대해 아무 말도 안 하고 있었다.

신규 시험이 그 조건을 «손으로 만들어» 그 자리를 처음 밟게 한다:

```python
def _rows_as_the_chunk_loop_leaves_them(db):
    """Exactly what the ingest loop holds when the diagnostic runs: rows returned by
    `apply_batch_updates` (which committed, expiring them) after the chunk session was
    closed (detaching them)."""
    ...
    results, _cells, _logs, _deleted = crud.apply_batch_updates(db, TABLE, batch)
    db.commit()
    db.close()
    return [item[0] if isinstance(item, tuple) else item for item in results]
```

셋:

| 단언 | 무엇을 막나 |
| --- | --- |
| 분리된 행의 `getattr(row, "row_id")` 가 `DetachedInstanceError` 를 «던진다» | 한 줄짜리 옛 코드를 「명백한 단순화」로 되살리는 것 |
| `record_statements` 가 «빈다» (`assert calls == []`) | 「안 던졌다」로 끝내는 것 — 그 읽기는 객체당 SELECT «하나»였다 |
| 900 s 선인출 + 분리된 행에서 함수가 «반환»한다 | 관문을 못 넘어 그냥 지나가는 공허한 초록 |

---

## ④ 커밋 본문과 안 맞는 줄 «하나» — 재서 적는다

커밋 본문은 세션 닫힘이 「three lines above this call」이라고 적는데, **`d00ac580^` 의 파일에서 재면 아니다**:

```
finally: db.close()                        L3170
_maybe_explain_slow_prefetch(...)          L3190     ->  «스무 줄» 위다
```
`docs/process/INCIDENTS_2026-09.md` 의 줄 번호(`L3197 finally` · `L3190+ 호출`)도 **순서가 뒤집혀** 있다. **기제 주장은 참이다** — 닫힘이 호출 «앞»에 있다. 틀린 것은 거리와 번호뿐이다.

---

## ⑤ 아키텍처 영향

- 인제션 청크 루프의 «관찰» 코드가 «작업»과 갈렸다: 진단기가 터지면 계획 줄만 침묵하고 청크는 그대로 간다.
- 판별식 셋이 CLAUDE.md 「계측 상설」로 승격됐다(`fbfd7cae`, 같은 날 10:47) — ① 진단기는 자기가 진단하는 것을 못 죽인다 ② 박스가 도달 못 하는 조건에서만 도는 코드는 시험이 0 이다 ③ 가설이 «두 번» 반증되면 전수 census.
- 즉효 스위치가 코드 없이 남는다: `ingestion_settings.json` 의 `slow_prefetch_explain_seconds` 를 관측 선인출 위로 올리면 훅이 아예 안 돈다. `analyze_after_rows: 0` 과 같은 부류다.

---

## ⑥ 부류 — 이 커밋은 그날 난 «셋 중 하나»다

같은 날 아침 셋이 났고, 셋 다 **「좌석이 자기가 세우지 않은 트랜잭션 상태의 세션을 쓴다」** 하나다:

```
D-39 (이 항목)  커밋이 «만료»시키고 close 가 «분리»한 객체를 읽는다
S-269 503b6129  «중단된» 트랜잭션을 롤백 없이 던진다
S-272 dc78afcd  «빌린 연결»을 autocommit 으로 바꿔 풀에 돌려준다
```
🔴 부류로는 큐 **S-274**(`ab1bc5c0`)가 받았다. 그 실측이 「세션을 빌리고 트랜잭션 상태를 만지는 좌석 **43** · 그중 commit **37** · rollback **32**」인데, 그 수는 **결함 수가 아니다** — 호출자가 커밋을 «바라는» 자리가 많다. 병은 수가 아니라 **오늘은 어느 쪽인지 코드를 열어야만 안다**는 것이고, 큐가 그렇게 적는다.

---

## ⑦ 그때 남아 있던 것

- **운영은 아직 이 커밋을 안 받았다.** 보드 `a5f23983` 가 소유자 몫으로 「pull + 재기동」을 적고, 그 뒤에야 `[Ingest] … PLAN (once per file) | target: … | cell_sources: …` 줄이 파일당 한 번 뜬다. 그 줄의 `Seq Scan` / `Index Scan` 이 **다음 수리를 가르는 값**이고, 이 시점에 그 값은 «아무도 모른다».
- 즉 **이 커밋이 운영에서 도는 것을 확인한 사람은 이 시점에 없다.** 재현은 in-process 시험이고, 확정은 «코드 경로»(커밋→만료, finally→분리)로 했다.
- 좌석을 찾은 것은 **소유자**였다 — 「maybe explain slow detch 여기서 에러 로그 있네」 · 「prefetch」. 복기가 그것을 ⓕ 로 적는다: 바깥 핸들러가 찍은 줄이 «파일도 좌석도» 안 댔다.
- 응용 레인의 전수 census(`3128b024`)가 **독립적으로** 같은 좌석에 닿았다(후보 7 → 6 소거 → 1). 그 지시는 사흘째에 나갔고, 걸린 시간은 «분» 단위였다.
- 소유자 손에 남은 것이 보드에 둘로 적혔다: 「가림 N」(S-243-b) · 위 PLAN 줄의 `target:` / `cell_sources:` 한 줄.
- `_analyze_after_load` 의 연결 누수(S-272)는 이 시점에 **아직 안 고쳐졌다.** 사흘 동안 그 좌석이 한 번도 안 돈 이유는 적재가 그 위에서 죽었기 때문이고, 이 수리가 파일을 끝까지 보내자 **39분 뒤** 그것이 드러났다.

---
📎 이 항목의 수(108 / 0 · 88 · 224 · 1.0 s · 3170/3190)는 «이 박스»와 «저장소 blob»의 것이다. 운영 수는 소유자가 주신 「선인출 10 s」뿐이고 그렇게 적는다.
📎 사유 커밋: `6f45a004`(2026-09-11, 좌석 착지 · 시험 0) · `fbfd7cae`(판별식 셋 승격) · `cc186a67`(복기).
📎 복기 정본: `docs/process/INCIDENTS_2026-09.md` — 「왜 사흘을 끌었나」 여섯과 「그래도 옳았던 것」.
