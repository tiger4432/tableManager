# 조각 1 의 랏 계보 걷기와 커버리지 보고가 `trace.py` 에서 은퇴했다 — 증명 «열다섯»을 지우기 전에 물음마다 «사는 자리»를 적었고, 낱말 «둘»은 일부러 되살렸다 (S-261)

> **커밋:** `8868d1a0` — refactor(ledger): the lookups and the coverage report retire from trace.py (S-261)
> **일자:** 2026-09-16 07:33
> **레인:** 구현자 — 아침 넷째이자 큐의 «마지막» · 보고 `a68d443e` · 총괄 닫힘 `54727036`(구현자 큐 소진 → 정지)
> **측정 상자:** 이 워크스테이션 + 이 박스의 PostgreSQL. **운영이 아니다.**
> **스위트:** `pytest tests --collect-only -q` **6,773 · 0 errors** · `ledger.trace`/`trace_router` 를 이름으로 드는 모든 시험 **273 passed / 34 skipped** · `scripts/run_pg_tests.py` **88 passed / 0 failed**(커밋 본문). 총괄이 «둘 다» 다시 쟀다 — 평범한 모집단 **343 passed** · PG **88/0**(보드 `54727036`).

## ① 왜 — 마지막 «호출자»를 지우는 것이 «피호출자»를 지우지는 않는다

`ledger/trace.py` 는 조각 1 의 랏 계보 걷기(`trace` · `ClaimLookup` 계열 · `Neighbourhood` · 재귀 CTE 둘)와 `coverage` 보고를 여전히 «내보내고» 있었다. 그런데 `95940d45`(2026-08-27)가 그 걷기를 `ledger_subgraph.subgraph` + `SqlEvidenceLookup` 으로 갈아치웠고, `67cc2e8a`(2026-08-25)는 그것들을 부르던 라우트를 이미 은퇴시켰다. **제품 호출자가 0 인데 껍데기가 남아 있었고, 내보내는 모듈은 «제공하는» 모듈로 읽힌다.** 구성 기준 ③ 「이 갈래를 누가 타나 → 아무도 안 타면 잔해다」의 실물이다.

## ② 나간 것

```
클래스·자료구조  ClaimLookup / SqlClaimLookup / OneShotSqlClaimLookup / InMemoryClaimLookup / Neighbourhood
SQL             재귀 CTE 둘 (한 왕복 이웃 조회 · 측정상 더 나빴던 one-shot 대안)
보고            coverage + 그것에만 딸린 헬퍼 여덟
                (resolve_display_zone · _coverage_sample · _atom_estimate · _partition_report
                 · _cursor_rows · _rendered_reasons · _existing_columns · _last_atom)
그리고          lookup 이 이미 고아로 만들어 둔 private 넷
```
머리 docstring 이 「여기 사는 셋」에서 「resolver 와 읽기 몇」으로 다시 쓰였고, 나간 것들은 🪦 로 «사유 커밋을 대고» 남았다.

## ③ 「물음이 사는지 «먼저»」 — 커버리지 증명 열다섯이 «초록인 채» 지워졌다

지시가 요구한 순서를 지켰다 — 증명이 빨개져서 지운 것이 아니라, **초록인 채로 «각 물음이 오늘 어디서 답해지는지»를 자리마다 적은 뒤** 지웠다.

| 그 증명이 묻던 것 | 오늘 그 물음이 사는 자리 |
| --- | --- |
| 릴레이션 부재 / 빈 원장 / 모르는 랏 | 걷기 라우트의 `ledger_relation_absent` · `state: empty`(S-259 가 거기에 다시 씀) + `admin/schema_drift` |
| register 만 있는 랏 vs 아무도 모르는 랏 | «이미» 걷기 위에 있다 — 그 시험은 live 절반을 지키고 커버리지 비계만 잃었다 |
| 어느 소스가 썼나 | `ledger.admin.ingestion_view` — 설계상 «커서»를 읽는다(`INGESTION_NOTE`) |
| 거절 셋(이름 있음/없음/알 수 없음) | 같은 뷰. 세 갈래와 `refusals_unaccounted > 0` 까지 `test_ledger_sources_ingestion` 이 «평범한 스위트»에서 증명한다 — 지워진 시험의 「THE ONLY READ THAT EXISTS」는 낡은 문장이었다 |
| analyze 안 된 `reltuples` 추정 | `backfill` 자신의 `pg_class.reltuples` 읽기 |
| 파티션 목록 | `ledger.schema` 의 `pg_inherits` 조인 |
| uuid7 에서 HAPPENED vs RECORDED | `ledger.uuid7.timestamp_ms`, 거기서 증명됨 |
| 고정된 응답 모양 · 샘플 | 그 «보고의 성질»이다 — 보고와 «함께» 은퇴한다 |

## ④ 낱말 «둘»은 일부러 살아남았다 — 이 라운드가 «거의» 틀릴 뻔한 절반

```
COVERAGE_STATES   「absent/empty/ready」의 «저자». event_constants 와 listing_absence 가 이것을 가리킨다
                  (live 시험 하나가 RETROACTIVE_READ_READY 가 그중 하나임을 단언한다)
ATOMS_UNKNOWN     「이건 추정이다」의 «공유 모양». test_a_source_says_when_its_counts_were_taken 이 못 박는다
```
**둘 다 한 번 지워졌고, 시험이 이름을 불러서 되돌아왔다.** 커밋은 그것을 숨기지 않고 왜 남는지 주석으로 적었다 — 「축과 값을 «같이» 죽이지 않는다」(2026-09-06 은퇴 상설). 투영은 죽고, 그 투영이 «저자였던 낱말»은 안 죽는다. `ATOMS_UNKNOWN` 의 주석이 그 이유를 한 줄 더 적는다: 마지막 호출자와 함께 지웠다면 그 필드를 다음에 쓰는 사람이 «둘째 철자»를 자유롭게 지어낸다.

## ⑤ 지운 것이 아니라 «옮긴» 시험 하나

```python
# 전: SqlClaimLookup 의 생성자에 대고 물었다
def test_a_relation_name_that_is_not_an_identifier_is_refused_before_any_sql():
    for bad in ("ledger_events; DROP TABLE x", "public.ledger_events", "", None):
        with pytest.raises(ValueError):
            lt.relation_exists(None, bad)      # ⛔ 연결(None)을 «만지기 전»에 던진다는 것까지 함께 증명
```
릴레이션 이름 가드는 «같은 `_IDENTIFIER`» 이고, 오늘 그것을 지나는 자리는 `relation_exists` 다 — `schema_drift` · `ledger.schema` · `trace_router` 셋이 원장을 만지기 전에 부른다. 연결 자리에 `None` 을 넣는 것이 「질의 «뒤»에 도는 가드는 자기가 거절하려는 문자열을 이미 끼워 넣은 뒤다」를 못 박는다. `test_ledger_v2_pg` 는 `coverage` 에게 `state == "ready"` 를 묻던 것을 릴레이션에 직접 묻는 것으로 바꿨다(`relation_exists` + 행 수 1).

## ⑥ «안 건드린 것»을 이름으로 적었다

```
rollup_subject_types              호출자 0. 그런데 LEDGER_TECHNICAL_SPEC 과 PRIMITIVES 가 «이름을 든다»
                                  -> 스펙이 부르는 것을 은퇴시키는 건 «정리»가 아니라 «판정»이다
_object_qualifier · _payload_lot  `test_ledger_trace_contract` 만 닿는다 — 각각 자기 시험 단위 호출이 필요하다
· _hop
```
넷 다 이 커밋 «이전»부터 그랬다. 다시 발견되게 두지 않고 적어 둔 것이다.

## ⑦ 아키텍처 영향

- `trace.py` 가 이제 «resolver 와 읽기 몇»이다 — `claim_class`/`claim_rank_key`/`resolve`/`live_claims` 는 §6 의 유일한 resolver 그대로이고, `ledger_subgraph` 의 걷기와 `runtime_v2` 가 «둘 다» 그것을 묻는다.
- 원장 걷기의 «저자가 하나»가 됐다: 조각 1 의 CTE 경로가 코드에서 사라져, `SqlEvidenceLookup` 위의 `subgraph` 말고는 걷는 길이 없다.
- 「이건 추정이다」(`measured`/`ATOMS_UNKNOWN`)와 「합이 안 맞는다」(`_unaccounted`)의 모양은 `backfill` 과 `ledger.admin` 이 «import» 한다 — 둘째 철자가 결함에 대해 다르게 말할 수 없다.

## ⑧ 그때 남아 있던 것

- **PG 103 → 88 은 «지운 커버리지 증명 15» 그대로다**(103 − 15 = 88). 총괄이 그렇게 대조했고, 손실이 아니라고 보드가 적는다.
- 커밋 본문의 「1,721 → 1,050 줄」은 «커밋된 blob 과 안 맞는다» — `wc -l` 로 `8868d1a0^` 이 **1,720**, `8868d1a0` 이 **1,122** 다(공백 제외 1,457 → 952). 「1,059 줄」은 트리 전체의 삭제 수다(파일 넷 합: 644+12+400+3). 1,050 은 `COVERAGE_STATES`·`ATOMS_UNKNOWN` 과 그 주석이 «되돌아오기 전»의 수로 보이지만, 그렇게 적힌 곳은 없다.
- 검증 수가 «둘»이고 모집단이 다르다: 구현자 273 passed/34 skipped(`ledger.trace`·`trace_router` 를 이름으로 드는 시험), 총괄 343 passed(보드가 모집단을 적지 않았다).
- `rollup_subject_types` 는 여전히 호출자 0 이고, 스펙과 PRIMITIVES 가 여전히 이름을 든다.
- 문서 쪽은 이 시점에 «아직» 옛 내보내기들을 든다 — 보드 `54727036` 가 남은 일로 「문서 정비(커밋 11+)」를 적는다.
- 큐가 비어 구현자 레인은 «정지»했다. 남은 것은 소유자 몫 둘(S-243-b · S-262 판정)과 S-242-b(제품 동작)라고 같은 보드가 적는다.

---
📎 이 항목의 수(6,773 · 273/34 · 343 · 88/0 · 15 · 1,720/1,122)는 «이 박스»의 것이다. 「운영」이라 적은 줄은 없다.
📎 사유 커밋: `95940d45`(2026-08-27, 걷기 교체) · `67cc2e8a`(2026-08-25, 라우트 은퇴) · 직전 라운드가 이 파일의 PG 증명을 다시 겨눈 날: S-259(`cbc9ea4d` · `15ffc565` · `46451370`).
