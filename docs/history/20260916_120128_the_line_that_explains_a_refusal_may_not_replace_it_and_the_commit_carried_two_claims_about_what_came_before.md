# 거절을 «설명하는» 줄이 거절을 «대신해서는» 안 된다 — 그리고 이 커밋은 「그 전에 무엇이 있었나」에 대한 주장을 «둘» 실었다 (S-275)

> **커밋:** `c80905e6` — fix(ingest): the line that explains a refusal may not replace it (S-275)
> **정정 커밋:** `5c275f5c` — docs(ingest): the NameError's trigger was reaching the URL, not the SHOW (S-275 correction) · 4분 뒤 · **산문만, 코드 0바이트**
> **일자:** 2026-09-16 12:01 · 정정 12:05
> **레인:** 구현자 · 지시(총괄 11:5x, 큐 S-275) → 착지 `c80905e6` → 총괄 검증에서 원인 문장 하나 반증 → 정정 `5c275f5c`
> **측정 상자:** 이 워크스테이션 + 이 박스의 PostgreSQL. **운영이 아니다.**
> **스위트:** `apply_batch_updates` · `directory_watcher` · `_analyze_after_load` 를 이름으로 드는 평범 스위트 **1,514 passed / 40 skipped / 1 xfailed** · `scripts/run_pg_tests.py` **90 passed / 0 failed** · `pytest tests --collect-only -q` **6,805 · 0 errors**. 총괄이 따로 잰 합본 **100 passed / 1 skipped**. 정정 커밋은 두 파일 **25 passed / 1 skipped**(산문만 바꿨으니 수가 그대로여야 하고, 그랬다).
> **파일:** `server/database/crud.py` · `server/parsers/directory_watcher.py` · `server/tests/test_an_autocommit_connection_never_goes_back_to_the_pool.py` · `server/tests/test_business_key_conflict_retry.py` (+106 / −6)

---

## ① 왜 — 거절을 설명하는 줄이 `raise` 앞에 «맨몸»으로 앉아 있었다

`apply_batch_updates` 의 제약 위반 팔은 세 줄이었다.

```python
db.rollback()
_say_the_constraint_refused_this_batch(table_name, batch, exc)   # 감싸이지 않음
raise                                                            # 제약 이름을 든 «원래» 예외
```

가운데 줄은 `batch.updates` 를 읽고, 예외에게 제약 이름을 묻고, 모듈 둘을 import 한다. **그중 무엇이든 던지면 `raise` 에 못 간다** — 그러면 운영자는 S-269(`503b6129`)가 손에 쥐여 주려고 만든 그 `IntegrityError` 대신 엉뚱한 것을 받는다. 부류는 같은 날 CLAUDE.md 로 승격된 「진단기는 자기가 진단하는 것을 죽일 수 없다」다.

---

## ② 수리 — 이웃이 받은 «같은 감싸기», 그리고 접힘을 «소리 내어» 말한다

```python
try:
    _say_the_constraint_refused_this_batch(table_name, batch, exc)
except Exception as line_err:                          # noqa: BLE001
    logger.warning(
        "[Ingest] %s refusal line skipped (%s: %s) - the batch is still "
        "refused and the original error is raised unchanged",
        table_name, type(line_err).__name__, line_err)
raise
```

단언이 «종류»가 아니라 «동일성»으로 잰다 — 이 구별이 이 시험의 값이다.

```python
assert raised.value is original, "the diagnostic replaced the refusal it describes"
```

> 종류만 보면 **새로 만든** `IntegrityError` 를 던지는 빌드도 통과한다. 그 빌드는 제약 이름을 잃어버린 채 초록이다.

---

## ③ 🔴 이 커밋은 「그 전에 무엇이 있었나」를 «두 번» 주장했고, **한쪽만 정정됐다**

같은 커밋이 자기보다 앞선 코드·커밋에 대해 사실 주장을 둘 실었다. 둘 다 같은 부류의 오류였다 — **수리 «후»의 상태를 읽고 수리 «전»을 서술한 것.** 하나는 4분 만에 총괄이 blob 을 열어 잡았고, 다른 하나는 안 잡혔다.

### ㉠ 잡힌 쪽 — `SHOW` 가 아니라 «URL 에 닿는 두 줄»이 범인이었다

커밋 본문과 주석·독스트링이 「터지는 `SHOW search_path` 가 `url` 을 바인드 안 된 채 남겼다」고 적었다. 총괄이 `c80905e6^` 의 blob 을 열어 반증했고, **기록자도 `dc78afcd:server/parsers/directory_watcher.py` 를 열어 같은 것을 확인했다**:

```python
engine = db.bind or db.get_bind()
url = engine.url                        # ← url 은 «여기서» 묶인다
# ... 주석 여덟 줄 ...
search_path = db.execute(_sa_text("SHOW search_path")).scalar()   # ← 여기서 터져도 url 은 «이미 있다»
except Exception:
    search_path = None                  # ← `url` 은 안 건드린다
```

`SHOW` 가 터지면 `search_path = None` 이 될 뿐이고, 그 값은 아래에서 `if search_path:` 로 걸러진다 — **NameError 가 안 난다.** `url` 이 안 묶이는 유일한 길은 `db.bind` / `get_bind` / `engine.url` 이 터지는 것이고, 그때 `except` 가 `search_path` «만» 놓고 넘어가 아래 블록이 `url` 을 쓴다. 그 NameError 는 둘째 `try` 의 핸들러에 떨어져 「could not re-analyse」로 보고된다 — 참인데 «왜»를 안 말한다.

**결함도 수리도 그대로 옳았다.** 병은 「한 `try` 가 «서로 다른 폴백»을 가진 둘을 덮고 있었다」이고, 답은 팔을 가른 것이다. 정정된 것은 **지목**뿐이다.

```python
# ⚠️ ITS OWN ARM, BECAUSE THE TWO HAVE DIFFERENT FALLBACKS (S-275 ③). Folded into
# one `try`, a failure REACHING THE URL (`db.bind` / `get_bind` / `engine.url`)
# left `url` unbound while the `except` set only `search_path`, ...
```

정정 커밋이 자기 사유를 적는다 — 「나는 «수리된 코드»를 읽고 그 앞의 코드를 서술했다」. 저장소가 이미 이름을 가진 부류다: **주석은 «의도»의 증거이지 «동작»의 증거가 아니다.**

### ㉡ 🔴 안 잡힌 쪽 — 선례의 «방향»이 뒤집혀 있다 (이 기록에서 실측)

커밋 본문(그리고 `crud.py` 에 «남아 있는» 주석)이 이렇게 적는다:

> its precedent (`d00ac580`) **landed nine minutes before this seat was written** — same shape, same reason, one call not wrapped.

기록자가 쟀다:

```
seat 가 쓰인 커밋   503b6129  2026-09-16 10:27:06   (S-269 — `_say_the_constraint_refused_this_batch` 도입)
선례                d00ac580  2026-09-16 10:36:18   (D-39 — 같은 부류의 첫 수리)
차                  +9분 12초  ->  선례는 그 좌석보다 «나중»이다
```

**크기(9분)는 맞고 방향이 거꾸로다.** 지시서 원문은 「선례는 «9분 차이로» 옆에 착지한 `d00ac580`」로 **방향을 안 적었는데**, 커밋 메시지가 방향을 붙이면서 뒤집었다.

🔴 **그리고 맞는 방향이 더 나은 이야기다.** 선례가 «먼저»였다면 이 좌석은 「이미 있는 규칙을 무시했다」가 된다. 실제로는 **부류에 이름이 붙은 것이 이 좌석이 쓰인 9분 «뒤»**였고, 아무도 옆 호출로 되돌아가 훑지 않았다. 그래서 이 커밋이 「다른 거절 좌석을 찾아다니지 않는다 — 그건 전수 census 가 필요한 별건이다」로 끝나는 것이 «옳은» 결론이다. 뒤집힌 방향으로는 그 결론의 근거가 안 보인다.

⚠️ 사실만 적는다: **정정 커밋 `5c275f5c` 는 이 문장을 안 건드렸고, `server/database/crud.py` 의 그 주석은 이 항목을 쓰는 시점에 그대로다.**

---

## ④ 보너스 팔이 실제로 산 것 — 「예측은 맞았고, 예측에 «없던 것»이 하나 더 있었다」

```
총괄 예측   search_path 를 못 읽으면 「조용히 False」          <- 맞았다
구현자 실측  그 자리에 «폴백이 다른 둘»이 한 try 안에 있었다   <- 예측에 없던 것
```

지금은 팔이 둘이고, 각자 «무엇을 잃었는지»를 말한다.

```python
except Exception as path_err:                                  # noqa: BLE001
    logger.info("[%s] search_path unreadable (%s) - ANALYZE will use the "
                "server's default path", table_name, path_err)
    search_path = None
except Exception as bind_err:                                  # noqa: BLE001
    logger.warning("[%s] could not reach the database URL (%s) - statistics are "
                   "stale and a page query may sort until autovacuum catches up.",
                   table_name, bind_err)
    return False
```

**둘 다 안 던진다.** 행은 이 시점에 이미 durable 하고, 통계 재계산 실패가 「파일 FAILED」가 되면 작은 값을 큰 거짓과 바꾸는 것이다. 이 원칙은 `dc78afcd` 의 docstring 에 이미 있었고 이 라운드가 그것을 팔 둘에 «각각» 새겼다.

---

## ⑤ 아키텍처 영향

- 인제션의 제약 위반 팔에서 **거절의 «전달»과 거절의 «설명»이 분리**됐다. 설명이 죽어도 전달은 산다.
- 접힘이 **소리 내어 남는다**. 조용히 안 써지기 시작한 진단은 아무도 없어진 줄 모른다.
- `_analyze_after_load` 의 «빌린 세션» 블록이 **폴백이 다른 둘을 각자 이름 댄다.** 한 `except` 가 여러 실패를 덮으면서 그중 하나에만 맞는 폴백을 놓는 모양이 이 자리에서 하나 줄었다.
- 시험이 **동일성으로** 단언한다 — 「원래 그 객체가 올라온다」가 「같은 종류가 올라온다」로 약해지지 않는다.

---

## ⑥ 그때 남아 있던 것

- 🔴 **`crud.py` 의 선례 주석이 방향을 뒤집은 채 남아 있다**(위 ③㉡). 정정 커밋은 `directory_watcher.py` 쪽 문장만 고쳤다.
- **다른 거절 좌석은 안 훑었다.** 커밋이 그것을 `⛔ NOT DONE` 으로 명시한다 — 전수 census 가 먼저이고, 이 자리는 「열어서 확인한 «하나»」다. **같은 모양이 몇 자리 더 있는지는 이 시점에 아무도 안 셌다.**
- 커밋 시점에 **운영은 이 변경을 안 받았다.** 보고가 「재기동 부탁드립니다」로 끝난다. 이날의 재기동은 이후(13:1x대) 다른 라운드와 묶여 일어났다.
- 구현자가 같은 보고에서 **공유 트리 알림**을 남겼다: `docs/architecture/CODE_MAP.md` 에 자기 것이 아닌 미커밋 편집이 있고 자기 커밋에 안 담았다.
- `search_path` 를 못 읽는 팔의 시험은 **세션 더블**로 돈다. 진짜 PostgreSQL 에서 `SHOW` 가 거절되는 경우를 이 라운드가 재현한 것은 아니다.

---
📎 이 항목의 수(1,514 / 40 / 1 · 90 / 0 · 6,805 · 100 / 1 · 25 / 1)는 «이 박스»의 것이다.
📎 사유 코드: S-269(`503b6129`, 제약을 이름으로 거절) · D-39(`d00ac580`, 같은 부류의 첫 수리) · S-272(`dc78afcd`, 전용 연결과 `search_path`) · S-275(이 라운드).
📎 같은 부류의 판정 기록: 「주석은 «의도»의 증거이지 «동작»의 증거가 아니다」 — 이날 총괄 두 번·구현자 한 번이 같은 자리에서 걸렸고, 그중 둘은 blob 을 열어 고쳤다.
