# `follow` 가 «키를 부를 수» 있게 됐다 — 그리고 깨진 것처럼 보이던 게이트는 씨앗을 안 적은 내 게이트였다

> **커밋:** `965e3af9` (00:05)
> | **일자:** 2026-09-02 새벽
> **레인:** 서버(walk) — 총괄이 재기동 후 직접 검증
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**

## 배경 — 「컨테이너를 지나면 남의 자식이 딸려 온다」를 «세 번»에 걸쳐 닫았다

같은 증상을 세 라운드가 각각 좁혔고, 이번이 셋째다.

```
① 인접 반전 금지     `c278df63`  방금 «올라온» 술어로 되짚어 «내려가지» 않는다
② 정적 프론티어 분리  `3987ef8a`  이름 노드가 세상으로 «나가지» 않는다
③ follow 가 키를 받음  이 커밋    좌석을 지나 나가는 걸음이 «씨앗과 키가 같은» 곳으로만 간다
```
🔴 **①은 이 경로를 못 잡는다.** 인접 반전 가드는 두 걸음이 **같은 술어**일 때만 발화하는데,
이 결함이 지나는 길은 **술어를 반복하지 않는다.**

```
die ─slot_map→ 좌석 ←slot_map─ wafer ─inspected→ die×N
                                      ↑ 여기서 «남의 다이»가 전부 딸려 온다
```

## ① 계약 — 견주는 대상은 «씨앗»이고, 걷는 동안 «상수»다

```python
# 🔴 THE CONTEXT IS TAKEN FROM THE SEEDS, ONCE, AND NEVER CHANGES. ... Deriving it from
# the previous node instead would make it path-dependent - the same node reachable two ways
# would answer two different questions, and the walk would need per-path state it
# deliberately does not have (`nodes`, `depths` and `arrivals` are all keyed by node id
# alone).
```
🔴 **이것이 「새 축이 아니라 인자 하나」인 이유다.** 이전 노드에서 뽑았다면 같은 노드가
두 경로로 닿을 때 **서로 다른 질문에 답하게** 되고, walk 은 **노드 id «하나»로만 잠그던
자료구조에 두 번째 차원**을 얹어야 했다. 씨앗에서 한 번 뽑으면 **경로별 상태가 0** 이다.

## 🔴 ② 씨앗이 그 키를 못 들면 «0» 이 아니라 «422» 다

```python
raise ValueError(
    f"follow={predicate}:{','.join(key_names)} cannot be satisfied: the "
    f"seed {ref.get('type')} has no {', '.join(missing)}. A seed that "
    f"cannot carry the key would match nothing, and an empty graph reads "
    f"as 'there is nothing here'.")
```
웨이퍼 씨앗에 `inspected:x,y` 를 묻는 것은 **충족 불가능한 요구**다. 그런데 그 답이 0 이면
**「이 웨이퍼엔 다이가 없다」와 픽셀이 같다.** 호출자가 둘을 못 가른다.
기존 `subgraph_request_invalid` 봉투와 **이미 있던 except** 를 그대로 쓴다 — 새 봉투 0.

## 🔴 ③ 키 «값»의 표기를 통일했다 — 이 제약이 지키려던 바로 그 엣지가 떨어질 뻔했다

```python
def _json_key(value):
    """One spelling for a key value, so `1` and `1.0` do not miss each other.

    The same die was measured arriving as `x: 1` from one source and `x: 1.0` from another
    on 2026-08-28; comparing raw would silently drop the edge that matters, which is the
    failure this constraint exists to prevent rather than cause.
    """
```
지시서에 없던 것을 **하나** 넣은 자리이고, 근거가 **전에 잰 수**다.

## ④ 거는 자리 — «먼 쪽»에만, 그리고 양 끝이 다 프론티어면 «안 건다»

```python
# Both ends already on the frontier means this step advances nobody, so there is
# no far node to constrain - dropping it would remove an edge between two nodes
# the walk already holds.
```
🔴 그 자리에서 끊으면 **제약이 아니라 «손실»** 이다 — 이미 가진 두 노드 사이의 엣지가 사라진다.

## ⑤ 도메인 낱말 «0» — 무엇이 좌석인지는 이 층이 아는 지식이 아니다

```python
# 🔴 NO DOMAIN WORD DECIDES ANYTHING HERE. Which keys are a seat and which are a
# vessel is not knowledge this file has or needs - the request names the keys and
# the entity's own key names are what it names them by.
```

## 🔴 ⑥ 파서 — 콜론의 «부재»가 기본값이 아니라 «오늘의 동작 전부»다

```python
# 🔴 THE COLON IS OPTIONAL AND ITS ABSENCE IS NOT A DEFAULT — it is the whole of today's
# behaviour. `follow=slot_map` yields no keys for that predicate, which yields no
# constraint, which is the walk this repo already ships; the client sends no colons and
# keeps running unchanged. That is a requirement of this round, not a courtesy.
```
그리고 **첫 콜론에서만** 자른다. 그리고 **검사되는 것은 «맨 이름»** 이다 —
`inspected:x,y` 를 통짜로 선언 집합과 견주면 **선언에 «있는» 술어에 대해 422** 가 난다.
같은 술어가 두 번 이름되면 **마지막 스펙을 쓴다** — 둘을 교집합하면 **아무도 안 물은 세 번째
질문**에 답하게 된다.

## 게이트

```
A 픽스처 (효과는 «여기서만» 보인다 — 이 상자엔 좌석 경유 경로가 없다)
   씨앗 die 1 · 목적지 웨이퍼에 다이 3
      제약 없음 -> die «3»   |  inspected:x,y -> die «1», 그리고 그 «하나»가 좌표가 같은 다이
   씨앗 die 2 · 각 목적지에 다이 3
      제약 없음 -> die «6»(M×N)  |  inspected:x,y -> die «2»(M)
   콜론 없는 요청  ->  제약 있는 호출과 응답이 «완전히 동일»(generated_at 제외)
B 라이브 무회귀 (총괄이 재기동 후 «자기 씨앗»으로 다시 잰 값)
   wafer SYN-BW-101-16 hops=6 both 자재6   nodes 264 · edges 351 · hops 3
   wafer SYN-BW-101-16 hops=1 out inspected  die 39
   defect_kind{void} hops=6 leads_to        nodes 21 · edges 21
   defect hops=4 both 자재5                 nodes 7 · inspected 엣지 1
C 거절   wafer + inspected:x,y -> 422 · 「the seed wafer has no x, y」
시험    tests/test_ledger_subgraph.py  25 passed · 1 skipped   (총괄 직접 실행, 재기동 후)
        레인이 건드린 파일을 지나는 다섯 본  62 passed · 48 skipped · 1 failed
```

## 🔴 「무회귀가 깨졌다」로 보인 것이 «게이트의 결함»이었다

```
총괄 수 «7»  ·  레인 수 «5»   ->  같은 항목에서 «다른 수»
원인          총괄이 게이트에 «씨앗 철자»를 안 적었다. 레인이 defect 를 전순서로 하나 골랐다
잡힌 이유     레인이 «수를 고치지 않고 물었다»
결과          총괄이 재기동(pid 61620 · 00:07:52 > 커밋) 뒤 «자기 씨앗»으로 다시 재어 «넷 다 일치»
```
🔴 이 저장소에 이미 적힌 규칙(「절단이 걸리면 씨앗을 적는다」)이 **게이트를 쓰는 쪽에서**
어겨진 것이다. 그리고 **맞는 대응은 「수를 맞춰 보고」가 아니라 「씨앗을 물어보기」**였다.

## 변이 다섯

```
제약이 «절대 발동 안 함»            컨텍스트를 «첫 씨앗»에서만 뽑음
키 값 표기 통일 제거 (1 vs 1.0)     씨앗에 키 없을 때 «조용히 건너뜀»
파서가 콜론 «붙은 통짜»로 거절
```
각각이 **서로 다른 시험을 빨갛게** 만든다. 특히 둘째가 안 잡히면 「절반만 답하고 조용」이다.

## 아키텍처 영향

- `follow` 가 **`이름:키1,키2`** 를 받는다. 콜론이 없으면 **이전과 문자 그대로 같은 walk** 이다.
- 제약의 오른쪽 항은 **씨앗**이고 **걷는 동안 상수**다 — walk 의 잠금 구조(노드 id 하나)가
  안 바뀐다.
- **충족 불가능한 씨앗은 422** 다. 빈 그래프로 답하지 않는다.
- 선언 0줄 · 원자 0 · 클라 0줄.

## 그때 남아 있던 것

- 🔴 **이 상자에서는 «효과»를 못 잰다.** 좌석을 경유하는 경로에 데이터가 없다
  (세 술어의 이름 집단이 다르다). 그래서 A 게이트는 **하니스 픽스처**이고,
  라이브에서 잰 것은 **무회귀뿐**이다.
- 클라는 이 라운드가 아니다. **콜론을 안 붙이므로 그대로 돈다** — 게이트 B 가 그 증거다.
- `test_trace_fixture.py::test_emitted_columns_satisfy_the_ingestion_contract` 가 **빨강**이고
  이 라운드 것이 아니다. 픽스처가 내는 컬럼(`lot`·`slot_numbers`·`wafer_ids`·`equipment`)과
  라이브 `table_config.json` 이 아는 컬럼(`lot_id`·`slotnumbers`·`waferids` …)이 다르고,
  **실제 표에는 양쪽이 다 있다** — 데이터가 두 세대에 갈려 있을 수 있다. 별건으로 큐에 들어갔다.
- `docs/spec/ONTOLOGY_GRAPH_SPEC` 계열 스펙 반영은 이 커밋에 없다.
