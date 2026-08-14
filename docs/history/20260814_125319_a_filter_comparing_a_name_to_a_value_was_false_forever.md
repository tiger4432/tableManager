# A filter comparing a name to a value was false forever

**Date:** 2026-08-14 12:53 · **Domain:** Server (원장 — 구조 뷰 · provenance) · **Status:** 착지 — `87d7021`

---

## 배경 — 같은 사실에 두 답

`/kinds`는 `in_ledger: true`, `/structure`의 kinds 패널은 `false`. 게다가 구조
응답은 **자기 자신과도 모순**이었다 — 같은 응답의 `graph.edges`에
`Wafer|observed|value` 102,177원자가 flowing으로 실려 있었고, 셋째 거짓이
따라붙었다: 선언된 술어에 대해 `no_predicate_declared`.

## 원인 — 이름을 값에 대조했다

```python
# 이전: object_fields는 필드 «이름» 목록(["finding_kind", "method", "run_uid"]),
# row["kind"]는 «값»("void") — 어느 박스에서도 영원히 거짓
ids = sorted(e["id"] for e in edges.values()
             if row["kind"] in (e.get("object_fields") or [])
             or row["kind"] == e.get("predicate"))
row["in_ledger"] = bool(ids)
```

숨어 있던 이유가 이 결함의 핵심이다: **관측이 원장에 없던 동안은 false가 정답
이었다.** 술어가 영구 거짓인 링크 규칙은, 링크할 대상이 없는 동안 정확히 그만큼
숨는다. 관측 번역(`0a86651`)이 착지한 아침에야 두 답이 갈라졌다.

## 수리 — 측정이 아니라 선언에서 유도

레인은 포크가 제안한 식(census의 predicate+source_who 필터)을 **거절했다** —
그 식은 같은 부류의 결함을 한 층 아래 재도입한다: 선언됐지만 백필이 안 돈 kind가
`in_ledger: true` 옆에 빈 엣지 목록을 받게 된다. `in_ledger`의 정본은
`ledger_kinds.catalog`(번역 선언)이고, 이 패널은 이제 **덮어쓰지 않고**
`ledger_edge_ids` 하나만 더한다 — 같은 선언에서 유도하므로 둘은 다시 갈라질 수
없고, 미선언 kind의 `None` 술어는 명시 가드로 링크가 차단된다.

정직 표기가 커밋에 남았다: 이 박스에서는 두 규칙이 같은 답을 낸다 — 픽스처가
둘을 판별하지 못하므로, 선택은 측정이 아니라 선언/측정 분업 원칙으로 했다.

같은 커밋에서 `ledger_lots.py`의 `ledger_backed: false`는 **값은 참인데 이유가
죽은** 상태를 정정했다 — 「관측이 원장에 없다」는 전제가 만료됐고, 남는 참은
「이 경로가 아직 원장을 읽지 않는다」다. 값을 뒤집지 말라는 경고가 주석으로
남았다.

## 그때 남아 있던 것

- 증거는 스위트가 아니라 라이브 프로브다 — 전후 각 1회, `in_ledger` 불일치 0.
  테스트 15건은 PG 게이트라 이 라운드에 돌지 않았다(커밋이 스스로 명시).
- `ledger_lots`의 읽기 경로는 여전히 소스 테이블이었다 — 원장 이관은 미착수.
