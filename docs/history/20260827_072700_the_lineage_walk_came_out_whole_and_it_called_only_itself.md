# 계보 walk 이 «통째로» 나왔다 — 자기 자신만 부르던 사슬이었고, 뿌리의 낱말은 어떤 번역기도 못 내는 것이었다

> **커밋:** `95940d45` (07:14) · `126dcfee` (07:27) · `4b499108` (15:16) · `b7df6d50` (22:14)
> · `0f8e48de` (19:11)
> | **일자:** 2026-08-27 하루
> **레인:** 서버(계보 은퇴)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**

## 배경 — 자기만 부르는 사슬

`trace` · `neighbourhood` · `claims_for_lots` · `explore` — 서로를 부르고 **밖에서는 아무도
안 부르는** 무리였다. 그리고 그 뿌리가 서 있던 낱말은 **어떤 번역기도 내보내지 않는 것**이었다.

```
95940d45   ledger_trace.trace · lineage_predicates · ClaimLookup.claims_for_lots/.neighbourhood
           (서브클래스 오버라이드 셋) · ledger_explorer.explore
           · ledger_trace_router._lookup_for · vocabulary.traversable_predicates/walk_direction
           11파일 · 삭제 907 / 삽입 63

126dcfee   traversal_predicate · reachable_lots(세 클래스) · lazy LINEAGE_PREDICATES
           3파일 · 삭제 113

4b499108   고아가 된 읽는 쪽 «넷» — _payload_wafer · _payload_slot · _slot_map_pair · _map_slot
           삭제 105

b7df6d50   _traceability_sql · _trace_state, 그리고 그것을 약속하던 스펙 문장
           삭제 100
```

측정 근거: `object_payload.component`를 나르는 원자가 **645,203 중 0**,
slot_map 원자 **135 중 0**.

## 🔴 「통째로 나왔다」가 통째가 아니었다 — 13분 뒤 자기 레인이 신고했다

`126dcfee`가 적었다: `95940d45`이 **접근하면 던지는 이름 둘**을 남겼다
(`NameError` · `AttributeError`). 앞 커밋의 「통째로」는 통째가 아니었다.

## 무덤이 «없는 주소»를 가리키고 있었다

`0f8e48de`. 410 응답 일곱이 후계자로 **`/api/ledger/trace`**를 가리켰는데, 그 주소는
**앱이 서비스하지 않는다.** 즉 무덤 본문이 독자를 **404 로 보내고 있었다.**

```diff
# server/main.py
-GRAPH_BRANCH_SUCCESSOR = "/api/ledger/trace"
+GRAPH_BRANCH_SUCCESSOR = "/api/ledger/subgraph"
```

## 아키텍처 영향

- 계보 walk 사슬이 **없다.** 걷는 것은 `/api/ledger/subgraph` 하나다.
- 은퇴 무덤(410)의 후계자 주소가 **실재하는 라우트**를 가리킨다.
- 은퇴가 **읽는 쪽 → 질의 → 스펙 문장** 순으로 내려갔다 — 마지막이 문서다.

## 그때 남아 있던 것

- 자취 계약 시험 **둘이 빨간 채**로 두 커밋을 건너 이어졌다. 원인은 **샘플 선언에 선언되지 않은
  dt-job 팩**으로 귀속됐다.
- `SqlClaimLookup`이 살아남았는데 **그것을 생성하는 것은 시험뿐**이다.
- 이 라운드에서 라우트는 하나만 사라졌다 — `GET /admin/ledger/vocabulary`(`f9846b58`).
  나머지 라우트 정리는 그날 밤 몫이었다.
