# 핀이 테스트 트리에 있었다 — 그래서 핀을 지우면 방어도 같이 지워졌다 (#16ⓐ 완결)

> **일자:** 2026-07-31 새벽 | **관련 커밋:** 미커밋(총괄 검수 대기)
> **담당:** server-pm(구현·주입 검증) · 총괄(지시·검수)
> **대상:** `server/db_safety.py`(신설) · `server/database/database.py` · `server/main.py` ·
> `server/tests/test_ddl_never_reaches_production.py`(신설) · `server/tests/test_dev_env_isolation.py`(문서 정정) ·
> `docs/architecture/backend.md` · `docs/architecture/data_model.md` · `docs/guide/DEPLOY_SETUP.md` · `docs/process/DOC_OWNERSHIP.md`
> **계기:** 보드 16-ⓐ. 스위트 **1668 통과 / 0 실패** 기준선 확인 후 착수, 결함 주입 6건 각각 독립 적색 후 되돌림.
> **선행 항목:** `20260729_183000_silent_failures_config_schema_boot.md`(ⓐ의 1단계 — DDL을 import에서 기동으로 옮긴 라운드)

## 배경 — ⓑ는 닫혔고 ⓐ는 왜 열려 있었나

`9a8ede8`은 ⓑ(테스트가 운영자의 `server/config/maps.json`에 쓰던 결함)를 닫았다.
닫혔다고 인정된 이유는 **격리를 걷어내면 단언이 깨지기 때문**이다.

ⓐ는 같은 날 닫히지 않았다. 남은 근거가 이것이었다.

> 「테스트 엔진은 **확인해 본 바로는** 전부 sqlite 메모리/tmp다」

그 사이 `create_all`은 모듈 최상위에서 `bootstrap_database_schema()` 안으로 들어갔다
(`20260729_183000`). 실패 시점이 import에서 기동으로 옮겨졌지만,
**"테스트 프로세스가 운영 DB에 닿는다"는 가능성 자체는 그대로였다.**
실제로 그 경로로 운영 `assy_manager`에 빈 테이블이 생긴 적이 있다.

## 진짜 결함은 방어가 놓인 **위치**였다

방어는 하나뿐이었고 `server/tests/conftest.py`에 있었다.

```python
os.environ["DATABASE_URL"] = os.environ.get("ASSY_TEST_DATABASE_URL", "sqlite:///:memory:")
```

이 핀은 잘 만들어져 있다 — `setdefault`가 아니라 **하드 대입**이라 셸의 주변 환경변수가
끼어들지 못한다. 문제는 성능이 아니라 **소유권**이다.

> **핀은 테스트 트리가 하는 일이다. 그래서 핀을 지우면 방어도 같이 사라진다.**
> 「확인해 봤다」가 메커니즘이 아닌 이유가 정확히 이것이다 — 다음 사람이 이 줄을 지울 때
> 아무것도 그를 막지 않는다.

## 수리 — 거절을 **운영 코드 쪽으로** 옮기고, 세 겹으로 깔았다

신설 `server/db_safety.py`가 판정의 단독 소유자다. **pytest 프로세스 안에서만 무장한다.**

| | 어디에 | 언제 거절하나 |
|---|---|---|
| 그물 1 | 공유 엔진의 `do_connect` (`database.py`) | **소켓이 열리기 전에.** 운영 크리덴셜을 쥔 유일한 엔진이라 가장 이른 훅을 준다 |
| 그물 2 | `Engine` **클래스**의 `engine_connect` | 첫 쿼리 전에. 테스트가 **자기가 만든** 엔진까지 덮는다 |
| 그물 3 | `bootstrap_database_schema()`의 DDL 직전 | **연결을 아예 열지 않고** — 순수 판정. #16ⓐ에 직접 답하는 자리 |

판정은 **허용목록**이다. `check_test_database()`가 통과시키는 것은 둘뿐 —
**sqlite**이거나 **`ASSY_TEST_DATABASE_URL`이 명시적으로 지목한 URL**.

> **차단목록("assy_manager만 아니면 된다")은 운영 DB가 둘이 되는 날, 혹은 이름을 바꾸는 날
> 이미 사라져 있다.** 그래서 「운영 이름이 아니라서 괜찮아 보이는」 URL도 거절한다.
> `ASSY_TEST_DATABASE_URL`에 운영 DB를 적어도 거절된다 — **선언한다고 테스트 DB가 되지는 않는다.**
> 증명하지 못하는 것(파싱 실패·빈 값)도 거절이다. `iso_watcher`가 같은 자리에서 하는 거래와 같다.

## 🔴 바꾸지 **않은** 것 — `create_all`은 여전히 무가드다

DB 불통 시 웹서버가 **부팅에 실패해야 한다**는 계약은 그대로다.
`try/except`를 두르지 않았고, 실패를 조용하게 만들지 않았다.
운영 프로세스에서는 `under_pytest()`가 거짓이라 세 그물 모두 **즉시 반환**한다.

이것을 주장이 아니라 **실측**으로 남긴다 — 같은 명령을 환경변수 하나만 바꿔 두 번 돌렸다
(대상은 127.0.0.1 **포트 1**, DB 이름은 존재하지 않는 `assy_boot_probe`).

| pytest 표지 | `bootstrap_database_schema()` 결과 |
|---|---|
| 있음 | `RuntimeError: [#16a] REFUSED ...` — **연결을 열지 않고** 거절 |
| 없음 | `OperationalError` — **진짜로 연결하러 가서** 시끄럽게 실패 |

## 증명 — 결함 주입 6건

| # | 주입 | 적색이 된 것 |
|---|---|---|
| 1 | 그물 3(`require_test_database`) 제거 | 순수 판정 테스트 + 프로세스 셀 F2 |
| 2 | `database.py`가 공유 엔진을 무장하지 않게 | 셀 F3 — **`OperationalError`로 바뀜**(= 소켓이 열렸다는 증거) |
| 2b | `install_test_database_guard`가 훅을 등록하지 않게 | 그물 1 테스트 + 셀 F3 |
| 3 | `install_global_test_database_guard` 호출 제거 | 그물 2 테스트 |
| 4 | 허용목록을 **차단목록으로 강등** | 판정 4건 + 프로세스 셀 2건 |
| 5 | `under_pytest()`를 항상 거짓으로 | **8건** — 감도 대조군 포함 |
| 6 | **conftest의 핀 자체를 제거**(운영 형상 URL, 도달 불가 포트로 대체) | 스위트가 **수집 단계에서** `[#16a] REFUSED`로 죽는다 |

주입 6이 이 라운드의 결론이다. **핀을 지워도 이제 방어는 남아 있고, 스위트는 조용히 새는 대신 시끄럽게 죽는다.**

## ⚠️ 주입 1에서 배운 것 — 「적색이 됐다」로는 부족하다

주입 1(그물 3 제거)을 넣었을 때 프로세스 셀 F2는 **통과했다.**
그물 1이 같은 호출을 한 층 아래에서 잡았기 때문이다 — 부트스트랩은 공유 엔진에 바인딩하므로.

즉 `RuntimeError`가 났다는 사실은 **「어떤 그물인가 하나가 버텼다」**만 증명한다.
그물을 여러 겹 깔면 **각 겹의 테스트가 서로를 가려 준다.**

> **수리:** F2가 거절 메시지의 **context 문자열**(`create_all`)까지 단언하게 했다.
> 그러자 주입 1에서 F2도 적색이 됐다.
> 겹쳐 깐 방어를 채점할 때는 **어느 겹이 잡았는지**를 테스트가 구분할 수 있어야 한다.

## 안전 규율 — 부정 테스트가 자기가 서술하는 사고를 일으키면 안 된다

이 파일의 모든 비-sqlite URL은 **127.0.0.1 포트 1**을 가리킨다(아무것도 듣지 않는다).
그물이 일부러 없는 셀은 아예 존재하지 않는 DB 이름(`assy_boot_probe`)을 쓴다.
주입 6도 **진짜 운영 URL을 쓰지 않았다** — 운영 형상이되 도달 불가한 URL로 대체했다.
**그물이 버티는지 확인하려고 운영 DB에 대고 실험하지 않는다.**

## 남은 것 — 정직한 부분 (구조가 아니라 「점검으로 참」인 것)

- 테스트가 **자기 파일에 운영 크리덴셜을 직접 써서** `create_engine`으로 엔진을 만들면,
  그물 2는 **소켓이 열린 뒤에** 거절한다(문 통과는 막지만 노크는 이미 갔다).
  그물 1의 사전-소켓 거절은 **공유 엔진 전용**이다.
  다만 그 시나리오는 사고가 아니라 **누군가 운영 비밀번호를 테스트 파일에 타이핑하는** 의도적 행위다.
- `under_pytest()`의 판단은 세 신호(`PYTEST_CURRENT_TEST`·`PYTEST_VERSION`·`sys.modules`)에 의존한다.
  운영 프로세스가 pytest를 import하는 일은 없다고 보지만, **그 사실 자체는 점검으로 참**이다
  (대신 「표지 없는 프로세스는 무장되지 않는다」는 셀 두 개로 실측해 둔다).

## 파일

| 파일 | 변경 |
|---|---|
| `server/db_safety.py` | **신설** — `under_pytest()` · `check_test_database()`(허용목록) · `require_test_database()` · 훅 설치 2종 |
| `server/database/database.py` | 엔진 생성 전후로 그물 2·그물 1 무장 |
| `server/main.py` | `bootstrap_database_schema(bind=None)` — 선택 인자 신설(주입 검증용 + 호출자 지참 엔진 검사), DDL 직전 순수 판정 |
| `server/tests/test_ddl_never_reaches_production.py` | **신설** — 판정 12건 · 감도 대조군 4건 · 그물별 4건 · 프로세스 2×2 4건 |
| `server/tests/test_dev_env_isolation.py` | 모듈 docstring 1항이 「모듈 레벨 `create_all`」로 낡아 있었다 — 정정 + 새 그물로 안내 |
