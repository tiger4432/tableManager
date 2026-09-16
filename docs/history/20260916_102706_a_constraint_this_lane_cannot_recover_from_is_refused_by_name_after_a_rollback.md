# 이 레인이 «못 살리는» 제약은 롤백한 뒤 «이름을 대고» 거절된다 — 고친 것은 «탐지기»가 아니라 «나가는 길»이다 (S-269)

> **커밋:** `503b6129` — fix(ingest): a constraint this lane cannot recover from is refused by name, after a rollback (S-269)
> **일자:** 2026-09-16 10:27
> **레인:** 구현자 · 보고 `270a505e` · 지시 `2975d375`
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **스위트:** `apply_batch_updates` 또는 `operator_line` 을 이름으로 드는 모든 시험 **1,265 passed / 37 skipped / 1 xfailed** · 거절 문구 계약 **18 passed** · `pytest tests --collect-only -q` **6,780 · 0 errors**(커밋 본문 · 보고).
> **파일:** `server/database/crud.py` · `server/operator_line.py` · `server/tests/test_business_key_conflict_retry.py` (+180 / −2)

---

## ① 왜 — 거절의 «탐지»는 옳았고 «출구»가 틀렸다

`apply_batch_updates` 의 재시도 팔은 「업무키 유일성 경합」 하나만 살린다. 그 좁음은 **의도한 것이고 이 커밋도 안 건드렸다.** 틀렸던 것은 그 나머지가 «어떻게 나가느냐»였다:

```python
except IntegrityError as exc:
    if not _is_business_key_unique_violation(exc):
        raise                      # ⛔ 롤백 없이 그대로
```

PostgreSQL 에서 실패한 문장은 **감싼 트랜잭션을 죽인다.** 롤백 없이 던지면 세션은 「중단된 트랜잭션」 위에 남고, 호출자가 다음에 **속성 하나만 읽어도** 「Instance is not bound to a Session」 / 「current transaction is aborted」 가 난다. 그 문장은 SQLAlchemy 를 부르지 **제약도 표도 다음 행동도 안 부른다.**

소유자가 그날 아침 만난 문장이 그것이다 — 「인제션 세션에 바운드 안 되어 있다고 안 들어감」. 다른 표는 전부 들어가는데 «되던 표 하나»만.

### ⚠️ 그런데 이 커밋이 그 사흘 장애의 «원인»을 고친 것은 아니다

이 라운드는 사흘 장애를 쫓던 중에 **같은 문장을 낼 수 있는 자리**를 찾아 고친 것이다. 원인은 9분 뒤 `d00ac580`(D-39)에서 나왔고, 보드 `a5f23983` 와 `docs/process/INCIDENTS_2026-09.md` 가 그것을 원인으로 적는다.

구현자 보고가 그 경계를 **스스로 적어 두었다**:

> 🔴 가설 — 아직 «못 쟀습니다». 오늘 그 표에 새 `uq_vjoin_*` 인덱스가 생겼는지는 «라이브 DB 와 라이브 선언»을 붙여야 나오는데, 그건 이 박스 수치이고 운영에 대해 아무 말도 안 합니다.

즉 **결함은 실재했고 수리는 독립적으로 옳지만, 「이것이 그 장애였다」는 확인된 적이 없다.** 같은 날 총괄 커밋 `60065608` 이 이 라운드의 조인 트리거 가설을 「there were never any joins」로 철회했다.

---

## ② 바뀐 것 — 롤백 · 한 줄 · 그리고 «행동을 아는 데서만» 고른다

```python
if not _is_business_key_unique_violation(exc):
    db.rollback()
    _say_the_constraint_refused_this_batch(table_name, batch, exc)
    raise
```

`_say_the_constraint_refused_this_batch` 가 «행동»을 고르는 방식이 이 커밋의 핵심이다:

```python
if constraint.startswith(vjc.INDEX_PREFIX):
    action = operator_line.retract_the_declaration(
        "`virtual_join_rules.json` / `chain_rules.json` 의 그 조인 선언")
else:
    action = operator_line.decide_the_repair(table_name, constraint or "(이름 없음)")
```

```
uq_vjoin_*        제품이 «선언 때문에» 세운 인덱스다 -> 수리가 «하나»이고 데이터 편집이 아니다
                  선언을 끄면 제품이 스스로 걷는다 (S-248). 손 DROP INDEX 는 다음 재기동이 되돌린다
그 밖의 제약 전부   수리가 «정반대» 둘이다 — 행을 접거나, 키를 넓히거나
                  하나를 고르면 «틀릴 때 사실이 사라진다» -> 「가르십시오」 + RUN.md §2
```

두 문장은 부르는 자리가 짓지 않고 `operator_line` 의 닫힌 어휘에 **함수 둘로** 들어갔다(`retract_the_declaration` · `decide_the_repair`). 그 모듈의 머리글이 그 규율을 적는다 — 「행동의 문장은 부르는 자리가 지어내지 않고 여기 있는 것 중에서 고른다」.

제약 이름은 두 방언에서 읽는다:

```python
diag = getattr(orig, "diag", None)            # PostgreSQL 이 «권위»다
name = getattr(diag, "constraint_name", None)
...
marker = "constraint failed:"                 # SQLite 는 diag 가 «아예 없다»
```
문서 주석이 그 이유를 적는다 — PostgreSQL 만 이해하는 판독기는 **이 스위트가 한 번도 못 밟는다.**

---

## ③ 「행 하나만 건너뛰면 되지 않나」 — 재고 나서 «아니오»라고 적었다

커밋 본문이 이 물음에 «가정»이 아니라 «측정»으로 답한다:

```
쓰기는 청크당 «한 번»의 multi-row VALUES
   -> 이 저장소가 이미 잰 것: 실패한 것은 「자기 청크의 0 행을 적용한다」(BULK_CHUNK_SIZE 주석)
   -> PostgreSQL 에서는 그 위에 트랜잭션까지 중단된다
행 하나를 건너뛰려면 «행마다 savepoint» 가 필요하다
   git grep begin_nested -- crud.py : «0»
   -> 쓰기 경로의 «행별» 작업이고, 그것이 「성능 마진 넉넉하게」가 금하는 모양이다
선례도 같은 말을 한다
   refuse_virtual_join_duplicates 는 «쓰기 전에 읽어서» 건너뛴다.
   그 자신의 주석이 「이미 저장된 충돌은 여기 범위 밖」이라고 «같은 사유»로 적는다
```
그래서 배치는 **통째로** 거절되고, 줄이 그 크기와 표본을 싣는다 — 운영자가 추론하지 않도록.

---

## ④ 시험 — «묘비를 단» 시험 하나가 이 라운드의 절반이다

기존 시험 하나가 **정확히 반대를 단언하고 있었다**:

```python
def test_unrelated_integrity_error_is_raised_immediately(monkeypatch):
    """No retry, and NO ROLLBACK - the caller owns that failure and its transaction."""
    ...
    assert db.rollbacks == 0
```

그 전제가 «운영이 반증한 것»이라 단언이 빠지고 묘비가 붙었다:

```python
    ⚰️ THIS USED TO ASSERT `rollbacks == 0` ... the caller cannot own a transaction it does
    not know is aborted, and its next attribute read raised 「Instance is not bound to a
    Session」
```

새 시험 다섯:

| 단언 | 죽이는 변이 |
| --- | --- |
| `db.rollbacks == 1` — 던지기 «전»에 정확히 한 번 | «원래 코드». 재시도·제어흐름 단언에는 전부 초록이었고 1년 틀려 있었다 |
| 줄이 제약·배치 크기·다음 행동을 싣고 「Instance is not bound」를 **안** 싣는다 | 자막만 달고 넘어가는 수리 |
| `uq_vjoin_` 은 «다른» 행동을 받고, 픽스처가 «접두어에서만» 다르다 | 「행동이 고정 문자열」 |
| 제약 이름을 두 방언에서 읽고, 없으면 `""` | PostgreSQL 만 아는 판독기 |
| 재시도 팔은 바이트 무변 | 좁음을 넓히는 수리 |

---

## ⑤ 아키텍처 영향

- 인제션 쓰기 경로의 **거절 출구가 하나**가 됐다: 롤백 → 한 줄 → raise. 호출자가 받는 것은 여전히 `IntegrityError` 이고, 달라진 것은 그 뒤에 세션이 «쓸 수 있는 상태»로 남는다는 것이다.
- `operator_line` 의 「다음 행동」 닫힌 어휘가 **여섯 → 여덟**이 됐다(`fold_the_data` · `widen_the_key` · `fill_or_declare_null` · `rename_one_declaration` · `restart_to_apply` · `nothing_to_do` 에 둘이 더해짐). 「같은 증상에 수리가 정반대」인 이 제품의 자리들이 한 모듈에서 갈린다.
- 「제품이 아는 수리만 고른다」가 코드로 적혔다 — 제품이 세운 인덱스(`uq_vjoin_`)에만 행동을 «지정»하고 나머지는 «가르는 자리»를 댄다.

---

## ⑥ 그때 남아 있던 것

- **`_say_the_constraint_refused_this_batch` 는 감싸여 있지 않다.** 이 함수가 던지면 원래의 `IntegrityError` 가 가려진다. 같은 날 9분 뒤 `d00ac580` 이 정확히 그 부류(「진단기가 자기가 진단하는 것을 죽인다」)를 고쳤는데, 이 자리는 그 커밋의 범위 밖이었다.
- 이 함수는 `import operator_line` 과 `from virtual_join import config as vjc` 를 **함수 안에서** 한다. `operator_line` 은 stdlib 말고 아무것도 import 하지 않는 모듈인데, 이 호출 자리가 `virtual_join` 을 같이 끌어온다.
- 「`uq_vjoin_` 인덱스가 그 표에 새로 생겼나」는 **끝내 안 쟀다.** 라이브 DB + 라이브 선언이 필요하고 그건 이 박스 수치다. 구조로 답이 대신 남았다 — 재기동 뒤 그 줄의 `[Ingest:` 를 찾으면 로그가 스스로 답한다.
- 재시도 팔의 상한(`BK_CONFLICT_MAX_RETRIES`)과 그 소진 경로(S-247)는 그대로다.
- 이 시점에 서버는 **아직 재기동 전**이었다. 구현자 보고가 재기동을 요청하고 있었고, 그래서 이 줄이 운영 로그에 실제로 뜬 것을 본 사람은 없다.

---
📎 이 항목의 수(1,265 / 37 / 1 · 18 · 6,780)는 «이 박스»의 것이다. 「운영」이라 적은 줄은 없다.
📎 사유 코드: S-248(제품이 세운 인덱스의 수명 = 선언의 수명) · S-247(`operator_line` 이 있는 이유) · 「운영 로그는 못 붙인다 — 줄 자체가 조치를 실어야」(소유자 2026-09-15).
📎 같은 날 같은 부류 셋: D-39 `d00ac580` · S-269 이 항목 · S-272 `dc78afcd`. 부류로는 큐 **S-274** 가 받았다(`ab1bc5c0`).
