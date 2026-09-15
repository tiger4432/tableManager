# 스크래치 search_path 는 «철자 하나»이고 `pg_trgm` 을 본다 · BK 충돌 증명은 문장을 «저자»에게 묻는다 · 그리고 PG 증명은 «부를 때만» 돈다 — 첫 실행이 드러낸 둘을 고치자 «셋째»(S-259, 은퇴한 배관을 재는 29)가 나왔다 (S-257 · S-258 · pg 게이트)

> **커밋:** `ae28b356` — test(pg): the scratch search path has one spelling, and it can see pg_trgm (S-257) · `27f5d7d9` — test(pg): the persistent BK-conflict proof asks operator_line for the refusal line (S-258) · `69f7a130` — test(pg): a pg proof runs only when asked for (-m pg) - the plain gate keeps its meaning after S-257 opened the dev_env door (총괄)
> **일자:** 2026-09-16 02:38 · 02:40 · 02:51
> **레인:** S-257·S-258 «워크트리 서브에이전트» → 총괄 닫힘 `11fea45e`(S-259 등급 3 신설) · `69f7a130` 은 «총괄이 직접» → 보드 `2c93ae9f`
> **측정 상자:** 이 워크스테이션 + 박스 PG(`assy_qa`). **운영이 아니다.**
> **스위트:** `run_pg_tests.py` 전/후(S-257 커밋 본문): **3 failed / 71 passed / 2 skipped / 51 errors → 30 failed / 89 passed / 2 skipped / 6 errors** (`gin_trgm_ops` 47 → 0 · 수집 오류 6 그대로) · `git grep -n "-csearch_path" -- server/tests` 가 `isolated_pg.py` «하나»만 냄 · S-258: 「fold_the_data 로 지은 줄은 단언에 실패, widen 줄은 통과」 실측 · BK 시험 둘 초록. 게이트(보드 `2c93ae9f`): 평범한 pytest 모집단 **80 passed / 17 skipped** · `-m pg` **16 passed**.

## ① S-257 — «관대한 철자» 하나가 47 을 죽였다

S-256 의 첫 실행에서 `pg_engine` 시험 48 중 47 이 `UndefinedObject: gin_trgm_ops`. conftest 의 `pg_engine` 이 `-csearch_path=<scratch>` 를 «`public` 없이» 고정해, `public` 에 «이미» 설치된 `pg_trgm` 이 안 보였고 `ensure_schema` 의 `CREATE EXTENSION IF NOT EXISTS pg_trgm` 은 «어딘가 있으니» 조용한 no-op 이었다 — `_ensure_trigram` 이 쓰인 이유였던 「전제가 성립하는 자리에서는 안 보인다」 모양 그대로. 형제 스위트 «셋»(`test_ledger_l1_pg` · `v2_pg` · `dry_run_pg`)은 이미 `<scratch>,public` + 확장을 «스크래치 안에» 설치하는 법을 배웠고(S-64-b), conftest 와 카탈로그 시험이 «그 콤마 없는 둘»이었다. S-115 가 경고한 「안전 게이트에 철자가 둘이면 관대한 쪽이 있다」의 실물 — 그리고 conftest 의 `_resolve_pg_test_url`/`_declared_as_test_database` 는 `isolated_pg.resolve_url`/`declared_as_test_database` 의 «둘째 사본»(dev_env 문 없음)이었다.
```python
# server/tests/support/isolated_pg.py — «한 철자»
def scratch_connect_args(schema: str) -> dict:
    return {"options": f"-csearch_path={schema},public"}      # 스크래치 «먼저»(만드는 것 전부 거기로, DROP 과 함께 감) · public 은 «읽기»로 뒤에
def install_trigram(connection, schema: str) -> None:
    try: connection.execute(text(f'CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA "{schema}"'))
    except Exception as exc: pytest.skip(f"pg_trgm is not installable on this box, ...: {exc}")
# server/tests/conftest.py — 사본 삭제, 이름은 import 로 «남긴다»(세 파일이 여기서 가져간다)
from tests.support.isolated_pg import (PG_TEST_URL_ENV, declared_as_test_database as _declared_as_test_database,
                                       install_trigram, resolve_url as _resolve_pg_test_url, scratch_connect_args)
engine = create_engine(url, poolclass=NullPool, connect_args=scratch_connect_args(PG_TEST_SCHEMA))
```
같은 dict 가 `psycopg2.connect(url, **…)` 의 인자라 `test_pg_multirow_upsert` 의 «raw 경쟁 연결»도 자기 `SET search_path` 를 내지 않고 같은 철자로 고정된다. `test_ledger_v2_pg` 의 자체 `extension_created` 장부(public 에 설치 · 종료 시 drop)는 «간다» — 확장이 스크래치에 살고 스크래치와 죽는다.

## ② S-258 — 문장을 «복사»하면 둘째 저자가 된다

`test_a_persistent_business_key_conflict_is_refused_not_replayed` 가 은퇴한 영어 마커 `"BK Conflict Unresolved"` 를 단언하고 있었다. 제품은 `crud.py` 의 재시도 상한이 다시 쓰인 뒤로 S-247 의 운영자 줄(`[BKConflict:<표>] … → 다음: <widen_the_key>`)을 낸다 — 자리(S-257)가 열리자마자 빨개졌다. 한국어 문장을 시험에 «옮겨 적으면» 문구가 움직이는 날 저자가 둘이다.
```python
# server/tests/test_pg_multirow_upsert.py
def _invariant_tail(action):
    """액션 함수에 «표식»을 채워 그려 보고, 마지막 표식 «뒤»만 남긴다 — 모든 호출자가 공유하는 부분을 «저자에게서» 읽는다."""
    sentinels = tuple("<%d>" % i for i in range(action.__code__.co_argcount))
    rendered = action(*sentinels)
    return rendered[rendered.rindex(sentinels[-1]) + len(sentinels[-1]):]
prefix = operator_line.line("BKConflict", TABLE, "", "").split(" ", 1)[0]        # 운영자가 grep 할 «괄호»
refusals = [r.message for r in caplog.records if r.message.startswith(prefix)]
assert refusals[-1].endswith(_invariant_tail(operator_line.widen_the_key))      # «선언을 넓혀라» — fold_the_data 의 «반대» 수리
```
같은 접두에 `fold_the_data` 로 지은 줄은 «실패»하고 widen 줄은 «통과»한다(실측) — 시험이 «행동 부류»를 고정하되 문구는 «한 글자도» 안 든다. 「좁은 키는 «선언»을 고치고, 진짜 중복은 «데이터»를 고친다. 뒤집으면 사실이 사라진다」(RUN.md 상설)의 시험 판.

## ③ 🔴 그러자 «셋째»가 나왔다 — S-259, 은퇴한 배관을 재는 29

S-257 뒤 남은 빨강 30 중 S-258 하나를 빼면 **29** = `test_ledger_trace_pg.py`(28) + `test_ledger_subgraph.py`(1). 자리가 «숨기던» 내용 결함: `ledger.trace.trace` 없음 **15** · `/api/ledger/trace` 404 **8** · `hops` KeyError **3** · `SqlClaimLookup.neighbourhood` 없음 **2** · `node_kind == "claim"` **1**(큐 `11fea45e`). 「엔티티·어휘·walk 이게 끝」(2026-08-28) 뒤 그 라우트·클래스가 사라졌는데 시험은 PG 없는 박스에서 «늘 건너뛰어» 부재로 초록이었다. S-256 커밋 본문이 「content defects the message foresaw, not seat defects」로 «미리» 적어 둔 부류. 등급 3 으로 큐에 — 판정: 시험 «단위»로 셋 갈래(죽은 대상 → 삭제 · 살아 있는 물음 → walk 라우트로 다시 씀 · 어휘만 낡음 → 낱말 교체), 파일째 지우지 말 것.

## ④ `69f7a130` — 문을 열자 «평범한 게이트»가 그 문으로 나갔다

S-257 이 conftest 의 URL 해석을 `isolated_pg.resolve_url` 로 바꾸며 `pg_engine` 에 «dev_env 문»(QA DB 선언)이 생겼다. 그 결과 QA DB 를 선언한 박스에서는 «평범한 `pytest`» — 모든 레인이 도는 게이트 — 가 PG 증명까지 «돌기 시작»했고, 처음 만난 것(S-259 부류 하나, 보드 「`jsonb_typeof(varchar)`」)이 그 실행과 «무관한 결함»으로 레인 게이트를 빨갛게 만들 뻔했다.
```python
# server/tests/conftest.py — 총괄, 18 줄
def pytest_collection_modifyitems(config, items):
    if "pg" in (config.getoption("-m") or ""): return
    asked_out = _pytest.mark.skip(reason="pg proof: run server/scripts/run_pg_tests.py (S-256)")
    for item in items:
        if item.get_closest_marker("pg") is not None: item.add_marker(asked_out)
```
평범한 실행은 «어제의 뜻»을 지키고, PG 자리는 «일부러» 명령 하나(`run_pg_tests.py`)다. 마커가 「고르는 손잡이」에서 「막는 손잡이」로 «반쪽 더» 갔다.

## ⑤ 아키텍처 영향

- 격리 PG 에 «어떻게 붙나»(search_path · 확장 · URL 해석 · 운영 거절)의 저자가 `tests/support/isolated_pg.py` «하나». 엔진 다섯(pg_engine · 카탈로그 · 형제 셋)과 raw 연결이 같은 철자.
- 운영자 줄을 단언하는 시험의 «모양»이 하나 생겼다 — 접두는 `line()` 에서, 다음 행동은 액션 함수에서 «읽는다».
- 스위트 «둘»의 경계가 «마커 + 훅»으로 «강제»된다: `pg` 시험은 `-m pg` 없이는 skip.
- 그대로인 것: 수집 오류 6(박스 맵퍼·설정 부재) · S-259 의 29 빨강(큐).

## ⑥ 그때 남아 있던 것

- **S-259 미착지** — 29 빨강이 `run_pg_tests.py` 에 «그대로» 있고, 총괄이 「워크트리 에이전트로 지금」으로 적었다. 즉 이 시점에 `run_pg_tests.py` 의 답은 «failed» 다.
- **`69f7a130` 이 `conftest.py` 의 줄 끝을 «통째로» 바꿨다** — 기록자 실측: `69f7a130^` 의 conftest 는 LF, `69f7a130` 은 CRLF. `git show --stat` 은 603 +/585 − 로 «파일 전체»를 보이지만 `--ignore-cr-at-eol` 로 보면 훅 «18 줄»이 전부다. 다음에 이 파일을 blame 하는 사람은 모든 줄이 이 커밋으로 찍히는 것을 본다.
- conftest 의 `_resolve_pg_test_url` · `_declared_as_test_database` 는 «이름만» 남았다(import 별칭) — 세 파일(`test_pg_multirow_upsert` · `test_readonly_guard` · 카탈로그 시험)이 conftest 에서 가져가기 때문. 정본 이름은 `isolated_pg` 의 것.
- 평범한 게이트 수 「80 passed / 17 skipped」의 «모집단»이 보드에 적혀 있지 않다 — 어느 파일 묶음인지는 보드 줄만으로 알 수 없다.
- `install_trigram` 은 역할이 확장을 «못 만들면» skip 한다 — 「skip 은 통과가 아니다」(RUN.md §6)가 그 경우를 덮지만, 그 skip 은 `-rs` 줄을 «읽는 사람»에게만 보인다.

---
📎 이 항목의 수(47/48 · 51→6 · 71→89 · 29 · 80/17 · 16 · 603/585)는 «이 박스»의 것이다. 「운영」이라 적은 줄은 없다.
📎 자리를 만든 커밋: `20260916_022404_the_postgresql_only_proofs_get_a_seat_and_the_first_run_showed_what_skipping_had_hidden.md`(S-256) · S-64-b(형제 셋이 콤마를 배운 날) · S-115(한 철자) · S-247(운영자 줄) · 「하니스가 문구를 베끼면 그 문구의 둘째 저자가 된다」(2026-09-13) · 「엔티티·어휘·walk 이게 끝」(2026-08-28, S-259 가 재는 배관이 은퇴한 자리).
