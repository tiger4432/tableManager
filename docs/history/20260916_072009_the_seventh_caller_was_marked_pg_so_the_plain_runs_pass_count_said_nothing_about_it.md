# 호출자는 여섯이 아니라 «일곱»이었다 — 그 파일은 모집단에 «있었고», 단언이 `@pytest.mark.pg` 라 건너뛰었다 (S-263-b)

> **커밋:** `d95d5527` — test(walk): the PostgreSQL walk fixture names its registration predicate too (S-263-b)
> **일자:** 2026-09-16 07:20
> **레인:** 구현자 — S-263 착지 7분 뒤 · 총괄 보드 `d05b0cba`(자기 검수 구멍으로 기록)
> **측정 상자:** 이 워크스테이션 + 이 박스의 PostgreSQL. **운영이 아니다.**
> **스위트:** `scripts/run_pg_tests.py` **103 passed / 0 failed**(커밋 본문 · 총괄 재확인). 커밋 본문이 덧붙인 「S-263 만 있었다면 102/1 이었을 것」은 «돌려 본 수가 아니라 추론»이다.

## ① 왜 — 세었는데 «하나»가 빠졌다

S-263 은 등록 술어를 `ledger_subgraph` 에서 호출자로 옮기며 호출자를 «여섯»으로 셌다. **일곱이었다.** `test_ledger_trace_pg.walk_on` 이 실제 PostgreSQL 위의 «인프로세스 걷기»이고, `test_a_lot_with_only_a_register_is_told_apart_from_a_lot_nobody_knows` 가 그 좌석을 통해 「이 걷기가 닿은 등록이 노드에 `attributes` 를 놓는다」를 단언한다 — 훑기가 채우는 «바로 그 키»다.

## ② 왜 «모집단 실행»이 그것을 못 봤나 — 이 항목에서 남길 절반

```
S-263 의 검증   `ledger_subgraph` 또는 `trace_router` 를 이름으로 드는 «모든» 시험 파일 -> 279 passed
그 파일          «모집단 안에 있었다»
그 파일의 단언    `@pytest.mark.pg`(S-256) -> 스위트가 고정된 sqlite 에서 «건너뛴다»
결과             파일은 돌았고, 단언은 «안 돌았다»
```
🔴 **S-256 의 표시가 「부재로 초록」을 «읽히게» 만든 동시에 «지나치기 쉽게»도 만들었다.** 평범한 실행의 통과 수는 «표시된 절반»에 대해 아무 말도 하지 않는다 — 그런데 그 수가 「전부 돌았다」처럼 읽힌다. 보드 `d05b0cba` 는 이것을 레인 결함이 아니라 **총괄 자신의 검수 구멍**으로 적는다: 「제 279-passed 모집단에 «있었고» 단언은 skip 됐다」.

## ③ 변경 — 픽스처가 «자기가 쓴» 낱말을 댄다

```python
# server/tests/test_ledger_trace_pg.py
def walk_on(conn, lot, relation="ledger_events", **kw):
    """The live seat, in process: the walk over the ledger through the SQL lookup ...

    ⚠️ WITH ONE EXCEPTION, AND IT IS A DECLARATION LOOKUP THAT CHANGES THE SQL (S-263).
    ... Leaving it out would not make this 「closer to PostgreSQL」; it would stop a query
    from being issued at all, which is the opposite of what this seat tests.
    """
    kw.setdefault("registration_follow", {"register"})
    return ledger_subgraph.subgraph(lot_seed(lot),
                                    ledger_subgraph.SqlEvidenceLookup(conn, relation=relation), **kw)
```
이 좌석은 「라우트가 더하는 선언 조회는 빼고」 PG 에 묻는 자리인데, **등록 술어만은 «빼면 질의가 아예 안 나간다»** — 그것을 빼는 것은 PG 에 더 가까워지는 게 아니라 이 좌석이 재려는 것을 «없애는» 일이다. 그렇게 주석에 적혔다. `setdefault` 라서 다른 낱말을 쓰려는 시험은 여전히 자기 낱말을 말할 수 있다.

## ④ 아키텍처 영향

- 원장·걷기·PG SQL 을 건드리는 변경의 «검증 모집단»에 `scripts/run_pg_tests.py` «도» 들어왔다. 평범한 스위트 하나로는 표시된 절반을 못 센다는 것이 보드와 총괄 메모리에 등재됐다(`d05b0cba`).
- 등록 술어를 대는 좌석이 «일곱»으로 확정됐다. 제품 1 + 시험 6.

## ⑤ 그때 남아 있던 것

- 이 건을 잡은 것은 게이트가 아니라 «사람의 재검»이다 — 단언이 건너뛰는 한, 평범한 실행은 이 부류에 대해 앞으로도 «아무 수도» 내지 않는다.
- 커밋 본문의 「S-263 만 있었다면 102/1」은 그렇게 «돌려 본» 수가 아니다. 실제로 잰 것은 S-263-b «뒤»의 103/0 하나다.
- 인자를 잊는 미래 호출자가 «조용히» 빈 `attributes` 를 얻는다는 S-263 의 성질은 그대로다 — 이 커밋은 좌석 하나를 채웠을 뿐 그 침묵을 없애지 않았다.

---
📎 이 항목의 수(103/0 · 279 · 7)는 «이 박스»의 것이다. 「운영」이라 적은 줄은 없다.
📎 앞: `20260916_071354_the_registration_sweep_reads_its_predicate_from_the_declaration_and_the_word_moved_to_six_callers.md`(S-263) · 표시가 생긴 날: `20260916_022404_the_postgresql_only_proofs_get_a_seat_and_the_first_run_showed_what_skipping_had_hidden.md`(S-256).
