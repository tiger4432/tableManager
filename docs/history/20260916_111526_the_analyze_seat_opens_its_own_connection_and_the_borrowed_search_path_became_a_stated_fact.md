# ANALYZE 좌석이 «풀의 연결»을 autocommit 으로 바꿔 돌려주고 있었다 — 운영의 25P01 은 그 자리에서 나왔고, 고치는 길에 «더 조용한 결함»을 만들 뻔했다 (S-272)

> **커밋:** `dc78afcd` — fix(ingest): the ANALYZE seat opens its own connection instead of borrowing the pool's (S-272)
> **일자:** 2026-09-16 11:15
> **레인:** 구현자 · 긴급 지시 `89b7668f` · 응용 레인 조사 `d7447248`(D-40)가 좌석을 지목 · 보고 `37d0d5e8`
> **측정 상자:** 이 워크스테이션 + 이 박스의 PostgreSQL(`pool_size=1` 로 «좁혀서»). **운영이 아니다.**
> **스위트:** `directory_watcher` · `_analyze_after_load` · `analyze_after_rows` 를 이름으로 드는 모든 시험 **596 passed / 2 skipped** · `scripts/run_pg_tests.py` **89 passed / 0 failed**(88 + 이 라운드 하나) · `pytest tests --collect-only -q` **6,795 · 0 errors**(커밋 본문 · 보고).
> **파일:** `server/parsers/directory_watcher.py` · `server/tests/test_an_autocommit_connection_never_goes_back_to_the_pool.py`(신규 156줄) (+202 / −6)

---

## ① 왜 — 「내가 안 연 연결」의 격리 수준을 바꾸고 «돌려줬다»

`_analyze_after_load` 는 autocommit 이 필요하다. `ANALYZE` 가 청크의 트랜잭션 안에서 돌면 통계 갱신이 «확정된 적재를 되돌릴 수 있게» 되기 때문이다. 그 autocommit 에 닿던 길이 이것이었다:

```python
connection = db.connection().engine.raw_connection()   # ⛔ «풀»의 연결이다
try:
    connection.set_isolation_level(0)
    with connection.cursor() as cursor:
        cursor.execute(f'ANALYZE "{table_name}"')
finally:
    connection.close()                                  # -> autocommit 인 채 «풀로 복귀»
```

`raw_connection()` 은 «풀»의 연결을 내준다. `set_isolation_level(0)` 이 그것을 바꾸고, 프록시를 닫으면 **바뀐 채로 체크인**된다. 뒤에 그 연결을 받은 세션은:

```
in_transaction()   «참»   <- «세션»의 사실
서버의 BEGIN       «없음»  <- «연결»의 사실. 둘은 서로 모른다
=> begin_nested() -> SAVEPOINT -> 25P01 no_active_sql_transaction
```

그것이 운영이 내던 오류다. **그리고 이 좌석은 사흘 동안 한 번도 안 돌았다** — 적재가 그 위(D-39)에서 죽었기 때문이다. 같은 날 `d00ac580` 이 파일을 끝까지 보내자 **39분 뒤** 이 누수가 드러났다.

### 🔴 저장소가 이 함정에 «이미 이름을 붙여 두고» 있었다

`chain/ingestion_worker.py`(S-167)가 그 자리를 피하는 사유로 이렇게 적는다 — 「`raw_connection()` 은 풀의 연결을 내준다 … 닫으면 **autocommit 인 채 풀로 돌아간다** … ⚠️ **`in_transaction()` 가드는 그것을 막지 못한다**」. 응용 레인 조사(`d7447248`)가 후보 표를 열어 **`directory_watcher` 가 정확히 그 모양**임을 지목했고, 같은 표에서 나머지 둘(`ingestion_worker:139` · 220줄 아래 대기 샘플러)은 이미 전용 연결이라 소거됐다.

⚠️ 그 조사가 지시의 전제도 반증했다 — 지시는 「`raw_connection()` 운영 호출자 0」이었는데 실측은 «스물 남짓»이었다. 차이는 술어가 아니라 **모집단**이었다.

---

## ② 후보 «둘»을 재고 골랐다 — 그리고 «되는 쪽»을 안 골랐다

```
이 박스, pool_size=1 이라 «같은 연결»이 돌아온다
  raw_connection + set_isolation_level(0) + close   다음 checkout: «같은» 연결 · autocommit=True  -> 샌다
  execution_options(isolation_level="AUTOCOMMIT")   안에서 True · 다음 checkout False            -> 복원«된다»
```

ⓑ 는 **오늘 돈다.** 그래도 ⓐ(전용 연결)를 택했고, 코드가 그 사유를 적는다:

```
① 한 필요에 «세 번째» 기제가 된다 — chain/ingestion_worker(S-167)와 220줄 아래 대기 샘플러가
   «이미» 전용 연결을 연다
② 그 복원은 «라이브러리 버전의 약속»이다. 그런 가드는 「쓰는 날」이 아니라 「바뀌는 날」 틀린다
```

```python
import psycopg2

connection = psycopg2.connect(
    url.set(drivername="postgresql").render_as_string(hide_password=False))
```
풀이 «본 적 없는» 연결이라 `close()` 가 진짜 닫기이고, 돌려주는 것이 없다.

---

## ③ 🔴 고치다가 «더 조용한 결함»을 만들 뻔했다 — 증명을 짓다가 실측했다

전용 연결은 **`search_path` 를 안 물려받는다.** 풀 연결은 앱의 경로를 «공짜로» 들고 있었고, `ANALYZE "t"` 는 **한정되지 않은 이름**을 그 경로로 찾는다.

```
스크래치 스키마를 가리키는 엔진에서   새 연결이 「relation does not exist」
                                 좌석이 «조용히 False» 반환 — 이 함수는 «절대 안 던진다»
```

즉 수리가 그대로 갔으면 **바꾼 결함보다 더 조용한 결함**이 됐을 것이다. 그래서 URL 을 알려 준 «그 세션»에 경로를 묻고 명시적으로 `SET` 한다:

```python
db = SessionLocal()
try:
    engine = db.bind or db.get_bind()
    url = engine.url
    search_path = db.execute(_sa_text("SHOW search_path")).scalar()
except Exception:                                                  # noqa: BLE001
    search_path = None
finally:
    db.close()          # ⚠️ 세션은 «URL 때문에» 빌렸고, 일 «전»에 닫는다
...
    with connection.cursor() as cursor:
        if search_path:
            cursor.execute("SET search_path TO %s" % search_path)
        cursor.execute(f'ANALYZE "{table_name}"')
```

왕복 «한 번»이 늘고, **암묵이던 상속이 적힌 사실이 됐다.**

⚠️ 세션의 수명도 같이 바뀌었다 — 전에는 `finally: db.close()` 가 ANALYZE «바깥»에 있어 세션이 그 일 «내내» 열려 있었다. 그건 연결이 그 세션에서 나왔기 때문이었고, 그것이 결함이었다.

---

## ④ 게이트 — 빨강을 «먼저» 보였고, 셋 중 하나가 이 라운드보다 오래 산다

### ⓐ PostgreSQL 증명: 좌석이 «돈 뒤» 새 세션이 SAVEPOINT 를 열 수 있나

```python
@pytest.mark.pg
def test_a_session_after_the_analyze_seat_can_still_open_a_savepoint(pg_engine, monkeypatch):
    pinned = create_engine(
        pg_engine.url.render_as_string(hide_password=False),
        poolclass=QueuePool, pool_size=1, max_overflow=0,
        connect_args=scratch_connect_args(PG_TEST_SCHEMA))
    ...
    assert watcher._analyze_after_load("s272_probe", rows=10) is True, (
        "the seat did not run, so this proves nothing about what it leaves behind")
    ...
        nested = after.begin_nested()      # 🔴 25P01 here on the leaking build
```
```
연결 «하나»로 고정   -> 운으로 통과할 수 없다
단언은 SAVEPOINT     -> autocommit «플래그»가 아니라 25P01 이 «막은 것»을 잰다
좌석이 돌았는지 먼저   -> 안 돌았으면 「남긴 것」에 대해 아무것도 증명 못 한다
실측                옛 좌석으로 «1 failed» -> 이 좌석으로 «1 passed»
```

⚠️ 이 증명은 «평범한 스위트»에서 못 잡힌다 — pysqlite 에는 그런 규칙이 없어 좌석이 sqlite 위에서 «영원히 초록»이다. 그래서 `@pytest.mark.pg` 이고 `scripts/run_pg_tests.py` 로만 돈다.

⚠️ 그리고 그 시험을 쓰다가 하나 더 실측했다 — `str(url)` 은 비밀번호를 `***` 로 «가린다». 가린 DSN 으로는 접속이 실패하고, 한국어 로케일 서버에서는 그것이 인증 오류가 아니라 **libpq 메시지의 `UnicodeDecodeError`** 로 나온다.

### ⓑ 퇴화 오라클 — DB 가 «아예 없다». 이것이 남는 것이다

```python
def test_no_seat_takes_a_pooled_connection_and_changes_its_isolation():
    ...
    for function, names in _functions_that_mutate_isolation(path):
        if "connect" in names and "raw_connection" not in names:
            continue
        offenders.append("%s::%s" % (os.path.relpath(path, SERVER_DIR), function))
    assert offenders == [], (...)
```
`server/` 아래에서 `set_isolation_level` 을 부르는 **모든** 함수는 연결을 `psycopg2.connect` 에서 얻어야 한다 — **AST 로 읽어** 변수 이름을 바꿔도 안 숨는다. 위반 **0**.

> **S-167 이 «산문»으로 적어 둔 규칙을 «계측»으로 바꾼 것이 이 라운드가 남기는 것이다.**

⚠️ 단언의 «주어»가 소스 텍스트가 아니라 **소스가 하는 일**이고, 정규식이 아니라 AST 다 — 「텍스트가 주어인 하니스」 예외의 모양이다. 행동판으로 만들려면 후보 좌석마다 PostgreSQL 풀이 필요하고, 그래도 «누가 떠올린 좌석»만 덮는다.

### ⓒ 자기검사 — 「0」이 「없다」이지 「안 본다」가 아님

```python
source = (
    "def leaky(db):\n"
    "    connection = db.connection().engine.raw_connection()\n"
    "    connection.set_isolation_level(0)\n"
    "    connection.close()\n")
```
오라클에 **옛 좌석의 모양 그대로**를 먹여 `["leaky"]` 가 나오는 것을 단언한다.

---

## ⑤ 아키텍처 영향

- autocommit 이 필요한 좌석 **셋이 같은 기제**가 됐다 — `chain/ingestion_worker`(S-167) · 대기 샘플러 · ANALYZE 좌석. 전부 `psycopg2.connect` 로 «자기 연결»을 연다.
- 그 규율이 이제 **산문이 아니라 게이트**다. 내일 더해지는 좌석도 같은 walk 가 잡는다.
- 풀의 연결이 「내가 안 연 상태」를 물려받는 길이 하나 닫혔다 — 25P01 을 «만드는» 자리가 이 저장소에서 0 이 됐다. (25P01 을 «받는» 쪽의 처리는 17분 뒤 `6ea4f7b2`/S-271 의 몫이다.)
- 전용 연결의 `search_path` 가 «상속»에서 «선언»으로 바뀌었다.

---

## ⑥ 부류 — 그날 난 셋 중 하나

```
D-39 d00ac580  커밋이 «만료»시키고 close 가 «분리»한 객체를 읽는다
S-269 503b6129 «중단된» 트랜잭션을 롤백 없이 던진다
S-272 (이 항목) «빌린 연결»을 autocommit 으로 바꿔 풀에 돌려준다
```
셋 다 **「좌석이 자기가 세우지 않은 트랜잭션 상태의 세션(또는 연결)을 쓴다」** 하나다. 부류로는 큐 **S-274**(`ab1bc5c0`)가 받았다 — 실측 「빌린 좌석 43 · commit 37 · rollback 32」이고, 그 큐가 **그 수는 결함 수가 아니다**라고 적는다.

---

## ⑦ 그때 남아 있던 것

- **운영은 아직 이 커밋을 안 받았다.** 구현자 보고가 「재기동 부탁드립니다. 운영의 25P01 은 이 커밋이 막습니다」로 끝난다. 이 시점에 운영에서 25P01 이 멎은 것을 본 사람은 없다.
- `SHOW search_path` 읽기는 `except Exception` 으로 삼켜진다 — 못 읽으면 `search_path = None` 이고, 그러면 새 연결의 «기본» 경로로 `ANALYZE` 가 돈다. 그 갈래는 시험이 없다.
- `SET search_path TO %s` 는 파라미터가 아니라 **문자열 보간**이다. 값의 출처는 서버 자신의 `SHOW search_path` 다.
- 이 함수는 **여전히 절대 안 던진다.** psycopg2 가 아닌 박스는 예전과 똑같이 아래 warning 으로 떨어진다 — 그래서 실패는 「통계가 낡았다」로만 보이고 파일은 FAILED 가 안 된다.
- **옵션 ⓑ(`execution_options(isolation_level="AUTOCOMMIT")`)는 이 SQLAlchemy 에서 «된다»고 실측됐다.** 안 고른 것이지 안 되는 것이 아니고, 그 사유가 코드 주석에 남아 있다.
- 지시가 쓴 「`raw_connection()` 운영 호출자 0」은 **거짓이었다.** 실측은 «스물 남짓»(`ledger/backfill` 7 · followup 4 · gaps · store · trace_router · `parsers/directory_watcher` · migrations/scripts). 그중 «풀 연결을 바꿔 돌려주는» 것이 이 하나였다.
- `PG 88 → 89` 는 이 라운드가 더한 증명 «하나» 그대로다.

---
📎 이 항목의 수(596 / 2 · 89 / 0 · 6,795 · 88→89)는 «이 박스»의 것이다. 「운영」이라 적은 줄은 소유자가 주신 「25P01 이 난다」뿐이다.
📎 사유 코드: S-167(같은 함정, 같은 낱말 — 그 산문이 이 라운드의 오라클이 됐다) · D-40(`d7447248`, 좌석을 지목한 조사) · S-257(스크래치 경로의 한 철자).
