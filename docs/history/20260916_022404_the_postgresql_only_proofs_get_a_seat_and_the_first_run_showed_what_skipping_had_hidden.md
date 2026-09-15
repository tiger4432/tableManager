# PG 에서만 참인 증명에 «자리»가 생겼다 — `pg` 마커 하나 · 명령 하나 · RUN.md 한 절, 그리고 첫 실행이 «건너뛰던 초록» 뒤의 결함 둘을 드러냈다 (S-256)

> **커밋:** `baf17cfa` — test(pg): the PostgreSQL-only proofs get a marker and one command that runs them against the box (S-256) → main 병합(총괄, `64f58a1c` 보드)
> **일자:** 2026-09-16 02:24
> **레인:** «워크트리 서브에이전트» — 구현자 물음(09-15 23:3x 「PG 에서만 참인 시험을 돌리는 자리가 없다」)이 S-256 등급 4 로 큐에 → 야간 에이전트 → 착지 → 총괄 닫힘 `64f58a1c`
> **측정 상자:** 이 워크스테이션 + 이 박스의 PostgreSQL(격리 DB `assy_qa`). **운영이 아니다.**
> **스위트:** `pytest -m pg --collect-only` **121** 선택 · `-m 'not pg'` **6,610** = 6,731 − 121 · 수집 오류 «기존 6» 그대로 · `DATABASE_URL=sqlite:///:memory:` 는 거절 exit **64** (커밋 본문). 첫 실제 실행(다음 커밋 `ae28b356` 본문): **3 failed / 71 passed / 2 skipped / 51 errors**.

## ① 왜 — SQLite 가 받아 주는 것을 PG 는 거절하는데, 그 증명이 «돌 자리»가 없었다

jsonb · 파티션 · ON CONFLICT · CHECK · NULL 위 UNIQUE — 이 제품의 스위트는 `sqlite:///:memory:` 에 고정돼 있어 그것들에 대해 «초록»이지만 아무 말도 안 한다. PG 에서만 참인 증명은 있었다(`pg_engine` · `pg_session` · isolated_pg 스위트들) — 그런데 그 픽스처들은 선언 없는 박스에서 «건너뛴다». 몇 달 동안 그 증명들은 «부재로 초록»이었다(S-104 · S-115 가 경고한 모양). 「그 시험을 돌리려면 무엇을 치나」의 답이 없었다.

## ② 변경 — 마커는 «이미 건너뛰는 자리»에만, 명령은 «제품이 DB 를 찾는 길»로

```python
# server/tests/conftest.py — 저장소에 pytest.ini 가 없으니 이 훅이 «설정»이다
def pytest_configure(config):
    config.addinivalue_line("markers",
        "pg: a proof only PostgreSQL can carry; skips on sqlite, runs under server/scripts/run_pg_tests.py (S-256)")
```
마커가 붙은 곳: 모듈 전체 넷(`test_pg_multirow_upsert` · `test_ledger_v2_pg` · `test_ledger_dry_run_pg` · `test_ledger_trace_pg`) · 시험 단위(`test_ledger_l1_pg` 의 ledger 픽스처 시험 11 · `test_readonly_guard` 의 `pg_url` 시험 6 · `test_ledger_subgraph` 의 `pg_engine` 하나 · 카탈로그 파일의 `ensure_schema` 하나). «일부러 안 붙인» 둘: `test_set_based_write_path` · `test_a_walk_can_be_read_as_rows` — sqlite 를 건너뛰긴 하지만 `db_session`/앱 엔진을 타서 PG 실행이 «다시 가리키지 않는» 엔진이다.
```python
# server/scripts/run_pg_tests.py
REFUSED = 64                                   # pytest 의 0·1·2·3·4·5 어느 것과도 겹치지 않게
server_url, source = paths.resolve_database_url(paths.DEFAULT_PG_URL)   # env > config/database.json > 기본 — «제품이 찾는 길»
if _parsed(server_url).get_backend_name() != "postgresql": ... return REFUSED
test_url, reason = resolve_url()               # tests/support/isolated_pg — S-115 가 만든 «한 철자», db_safety 를 지나 운영은 이름으로 거절
env[PG_TEST_URL_ENV] = test_url                # conftest 의 pg_engine 과 isolated_pg 스위트가 «같은 변수»를 읽는다
cmd = [sys.executable, "-m", "pytest", "tests", "-m", "pg", "-rs", "--continue-on-collection-errors", *argv]
```
`--continue-on-collection-errors` 가 «하중을 받는» 플래그다 — pytest 는 «선택 해제된» 모듈이 수집에 실패해도 실행 전체를 중단하고, 박스의 gitignore 된 맵퍼를 import 하는 시험들이 fresh checkout 에서 정확히 그렇다(실측: 플래그 없이 `-m pg` 는 «아무것도 안 돌고» exit 2). 플래그가 있으면 증명은 돌고 수집 오류는 여전히 찍히고 exit 도 0 이 아니다. 그리고 「선언이 없으면 skip 이 아니라 REFUSED」 — skip 이 이 증명들을 몇 달 조용하게 둔 방식이다. `RUN.md` §6 이 명령과 «답의 뜻»(passed/skipped/failed/REFUSED)을 적는다.

## ③ 첫 실행 — 자리를 만들자 «자리가 숨기던 것»이 나왔다

명령을 한 번 돌리자(다음 커밋 본문): `pg_engine` 시험 **48 중 47** 이 `UndefinedObject: gin_trgm_ops` 로 죽었고(→ S-257, 등급 3) `test_pg_multirow_upsert` 의 BK 충돌 증명 하나가 «은퇴한 영어 마커»를 단언하고 있었다(→ S-258, 등급 4). 둘 다 이 커밋이 만든 결함이 아니라 «건너뛰던 동안» 낡은 것이다 — 「건너뛰던 PG 증명은 초록이 아니라 «미측정»」(보드 `64f58a1c`). 이 커밋 본문은 「"error" on a mapper test module means the box's own mappers or config are missing, not a PostgreSQL truth」로 수집 오류 6 의 뜻을 «미리» 적어 뒀다.

## ④ 아키텍처 영향

- 스위트가 «둘»로 갈라졌다: 평범한 `pytest`(sqlite, `-m 'not pg'` 와 같음) 와 `run_pg_tests.py`(`-m pg`, 박스의 PG). 마커 등록이 없으면 `pgs` 같은 오타가 «두 실행 모두에서» 조용히 빠지므로 등록이 곧 게이트다.
- 격리 DB 의 «어느 것»은 `isolated_pg.resolve_url` 하나가 정한다 — 스크립트는 그 답을 «두 픽스처 가족이 읽는 변수»로 내보내 둘이 «다른 DB 를 고를 수 없게» 한다.
- 그대로인 것: 픽스처들의 skip 조건 · sqlite 고정 · 수집 오류 6(박스 설정 부재).

## ⑤ 그때 남아 있던 것

- **스크립트 docstring 이 «자기와 어긋난다»** — 「WHAT IT DECIDES」 1·2 항은 「one REFUSED line, exit **2**」라 적고, 상수는 `REFUSED = 64` 이고 「READING THE ANSWER」 표와 커밋 본문은 64 다. 코드가 내는 값은 64. 산문 두 곳이 낡은 초안이다.
- 마커 «없이» 이 시험들은 여전히 «건너뛴다» — 마커는 «고르는» 손잡이지 «막는» 손잡이가 아니다. 그래서 S-257 이 `pg_engine` 에 dev_env 문을 열자 «평범한 pytest» 가 PG 증명까지 돌기 시작했다(→ `69f7a130`, 다음 항목).
- S-257 · S-258 은 이 시점에 «큐 행»이다(`64f58a1c`). 실제 수리는 `ae28b356` · `27f5d7d9`.
- 두 sqlite-skip 시험(`test_set_based_write_path` · `test_a_walk_can_be_read_as_rows`)은 «어느 실행에서도» 돌지 않는다 — PG 실행이 앱 엔진을 다시 가리키지 않기 때문이고, 그것을 하는 것은 이 커밋의 범위 밖이었다.

---
📎 이 항목의 수(121 · 6,610 · 6,731 · 47/48 · 51 errors)는 «이 박스»의 것이다. 「운영」이라 적은 줄은 없다.
📎 첫 실행이 드러낸 둘의 수리: `20260916_023822_*`(다음 항목) · 「SQLite 는 PG 가 거절하는 것을 받는다」(2026-08-05) · 「초록 대리지표는 초록 주장이 아니다」(2026-08-04) · 「빈 DB 는 모든 질문에 『없다』로 답한다」(2026-08-18) — 이번엔 «DB 가 없어서 skip» 이 그 부류였다.
