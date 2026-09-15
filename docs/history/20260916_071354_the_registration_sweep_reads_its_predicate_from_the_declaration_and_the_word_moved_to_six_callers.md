# 걷기의 등록 훑기가 술어를 «선언에서» 읽는다 — 목적어를 «안 주는» 문장은 주어에 대한 문장이고, 낱말은 모듈 하나에서 호출 «여섯»으로 옮겨갔다 (S-263)

> **커밋:** `53106c38` — feat(walk): the registration sweep reads its predicate from the declaration (S-263)
> **일자:** 2026-09-16 07:13
> **레인:** 구현자 — S-260 다음, 총괄 닫힘 `c5437757`(재기동 PID 52444) · 보고 `021b7122`
> **측정 상자:** 이 워크스테이션(선언은 커밋된 샘플 + 이 박스 카탈로그 «둘 다»). **운영이 아니다.**
> **스위트:** 새 시험 **5** · 모집단 **279 passed / 31 skipped**(`ledger_subgraph` 또는 `trace_router` 를 이름으로 드는 모든 시험) · `pytest tests --collect-only -q` **6,788 · 0 errors**(커밋 본문).

## ① 왜 — 코드가 도메인 낱말을 «하나» 들고 있었다

`ledger_subgraph` 의 등록 훑기가 노드 자신의 컬럼을 `follow=["register"]` 로 쓸었다. 「코드에 도메인 낱말이 «없다»」(2026-08-28 상설)의 정면 위반이고, 증상은 조용하다 — 등록 술어를 다르게 부르는 설치는 «모든» 노드의 `attributes` 가 영원히 비고 **아무것도 그렇다고 말하지 않는다.** S-52-i 가 한 층 위에서 없앤 침묵(「이 엔터티는 값이 없다」와 「이 걷기가 안 물었다」가 «같게 그려지는» 것)이, 리터럴을 통해 한 층 아래로 다시 들어와 있었다.

## ② 변경 — 선언이 «이미» 답을 들고 있었고, 그 답엔 저자가 있다

```python
# server/ledger/trace_router.py — `_static_types`·`_static_step_predicates`·`_predicate_cardinalities` 의 «넷째 형제»
def _self_describing_predicates():
    """Predicates the declaration gives NO OBJECT -- the ones that describe their subject."""
    try:
        from ledger import config as _config
        declared = _config.load() or {}
    except Exception:
        return set()
    names = set()
    for key, rule in (declared.get("vocabulary") or {}).items():
        if str((((rule or {}).get("object") or {}).get("kind")) or "") == "none":
            names.add(str(key).split("@", 1)[0])          # 선언이 id 를 버전 짓는다 -> 여기선 맨 이름
    return names

# _evidence_graph — 유일한 제품 호출자
ledger_subgraph.subgraph(..., registration_follow=_self_describing_predicates(), ...)
```
```python
# server/ledger_api/ledger_subgraph.py — 모듈은 이제 낱말을 «모른다»
registration_refs = []
if registration_follow:
    for node in nodes.values():
        ...
found, registration_cut = lookup.claims_for_entities(
    registration_refs, "outgoing", ..., follow=sorted(registration_follow))
```

**어휘가 목적어를 «안 주는» 문장은 목적어에 대해 아무 말도 안 하고 «주어»에 대해 전부 말한다** — `roleframe` 이 그 문장을 컴파일하는 자리에 그대로 적어 두었다(「A SENTENCE WITH NO OBJECT STILL HAS SOMEWHERE TO PUT ITS QUALIFIERS」). 엔터티의 값은 바로 그 원자들의 «수식어»에 실린다. 그러니 술어는 «도출»되는 것이고, 도출의 모양은 형제 셋과 같다 — 선언이 유일 권위, 버전 뗀 맨 이름, 목적어 없는 술어가 둘째로 생겨도 이 파일은 «한 글자도» 안 바뀐다.

## ③ 형제와 «다른 점»은 베끼지 않고 말로 적었다

빈 정적 타입 집합은 «정적 노드를 안 펼치고» 빈 카디널리티 맵은 «아무 말도 안 한다». 그런데 여기서 빈 집합은 **「어느 노드도 자기 컬럼을 안 나른다」**를 뜻한다. 그리고 그것이 생기는 길이 «둘»인데 같지 않다 — 목적어 없는 술어가 정말 없는 선언과, 선언을 «읽지 못한» 경우다. 후자는 이미 카디널리티도 정적 타입도 없이 답하고 있는 걷기이고, 그것 때문에 그래프를 «거절»하는 것은 이 함수가 «라우트의 물음»을 대신 판정하는 일이다. 그래서 거절하지 않고, 그렇게 적었다.

## ④ 치른 값을 «세어» 적었다 — 낱말이 하나에서 여섯으로

```
모듈 하나(`ledger_subgraph`)  ->  호출 «여섯»
   제품 1   `_evidence_graph` (여기서 배선)
   시험 5   등록 원자를 «손으로» 쓰는 좌석들 — 각자 «자기 픽스처가 쓴» 낱말을 댄다
```
픽스처가 자기 낱말을 대는 것은 «정직하다» — 그 픽스처가 곧 그 걷기의 «선언»이다. 다만 인자를 잊는 미래 호출자는 «조용히» 빈 `attributes` 를 얻는다. 그것이 운영까지 가지 못하게 막는 것은 이음매 시험이다: `_evidence_graph` 가 `subgraph` 의 «유일한» 호출자이고, 그 자리가 못 박혔다.

## ⑤ 게이트 — 픽스처가 «전부» `enrolled` 라고 부른다

```python
# server/tests/test_the_walk_reads_its_registration_predicate_from_the_declaration.py
DECLARED = {"vocabulary": {
    "enrolled@1": {"subjects": ["wafer@1"], "object": {"kind": "none"}},        # 🔴 목적어 없는 것
    "measures@1": {"subjects": ["wafer@1"], "object": {"kind": "entity_ref", ...}},
    "counted@1":  {"subjects": ["wafer@1"], "object": {"kind": "value"}}}}
assert trace_router._self_describing_predicates() == {"enrolled"}              # 종류마다 하나 -> 「전부 반환」으로 못 통과
monkeypatch.setattr(ledger_config, "load", unreadable)
assert trace_router._self_describing_predicates() == set()                     # 낱말로 «안» 물러선다
...
assert ("enrolled",) in lookup.follows and node["attributes"] == {"product": "P7"}
body = ledger_subgraph.subgraph(seed, lookup, hops=1)                          # ⛔ 리터럴의 회귀선
assert not any(call == ("register",) for call in lookup.follows) and "attributes" not in node
trace_router._evidence_graph(...); assert handed["registration_follow"] == {"enrolled"}   # 이음매
```
**진짜 낱말을 쓰는 픽스처는 「도출」과 「방금 지운 리터럴」을 «구별할 수 없다».** 그래서 전부 `enrolled` 다. `RecordingLookup` 이 `follow` 를 «기록»하는 이유도 같다 — 돌아온 그래프만 보면 「맞는 술어를 물었다」와 「전부 묻고 맞는 행을 골랐다」가 «같은 모양»이다. 못 읽는 선언이 낱말로 «물러서지 않는» 단언은, 그 물러섬이 곧 「이 박스에서는 맞고 다른 곳에서는 조용히 틀린」 리터럴의 재입장이기 때문이다.

## ⑥ 아키텍처 영향

- 걷기 모듈이 «도메인 낱말을 하나도 안 든다». 등록 술어를 정하는 자리는 «선언»이고, 그것을 읽는 자리는 라우터 «하나»다.
- 그 라우터의 「선언에서 읽어 걷기에 건네는 것」이 셋에서 «넷»이 됐다 — 정적 타입 · 정적 단계 술어 · 카디널리티 · 등록 술어. 같은 모양이라 다섯째도 같은 자리다.
- `ledger_subgraph` 는 «선언을 전혀 읽지 않는다»는 성질이 유지됐다 — 빈 집합의 «이유»를 설명할 수 있는 좌석이 호출자라는 것이 그 이유로 적혔다.

## ⑦ 그때 남아 있던 것

- 실측: 커밋된 샘플(어휘 16)과 이 박스 카탈로그(어휘 14) «둘 다» 정확히 `{register}` — 옛 리터럴과 «같은 값»이다. 즉 **이 박스의 동작은 0 바뀌었다.** 다르게 부르는 설치가 실제로 있는지는 여기서 알 수 없다.
- 같은 실측이 S-262 를 «확증»했다(보드 `c5437757`): 이 박스의 register 원자 434,973 이 전부 payload NULL 이고 원장에 qualifiers 컬럼이 없다 → 걷기의 `attributes` 0 은 회귀가 아니라 그 부류다. S-262 의 판정은 이 시점에 «소유자 몫으로 열려» 있었다.
- 호출자는 «여섯이 아니라 일곱»이었다. 이 커밋 시점엔 그 사실이 없었다 — 7분 뒤 `d95d5527`(S-263-b)에서 드러난다.
- 총괄의 첫 두 번 walk 호출이 422 였던 것은 «씨앗 인코딩» 실수였다(라우트는 `id`, 값은 `explorer.entity_id`) — 제품 결함이 아니라고 보드가 적는다.
- 279 passed 는 «평범한 실행»의 수다. 그 모집단 안의 `@pytest.mark.pg` 단언들은 건너뛰었다.

---
📎 이 항목의 수(5 · 279/31 · 6,788 · 16 · 14 · 434,973)는 «이 박스»와 «커밋된 샘플»의 것이다. 「운영」이라 적은 줄은 없다.
📎 바로 다음: `20260916_072009_the_seventh_caller_was_marked_pg_so_the_plain_runs_pass_count_said_nothing_about_it.md`(S-263-b).
