# 걷기(walk) — **이미 있는 것**. 다시 유도하지 말 것

> 🔴 **이 문서가 있는 이유:** 2026-09-06 저녁, 총괄이 「좌석이 `follow` 를 선언 안 한다 ·
> 누가 두 축을 짝지어 주나」를 «새 문제»로 올렸다. **그 기능은 이미 지어져 있었다.**
> 소유자: 「이거 다 했던 거잖아 — start collect 쌍 주면 선언에서 follow 리스트 뽑아서
> 걸을 후보 경로 클라에서 받아서 넣기로」 · 「왜 다 한 거를 모른 척하고 또 하냐」.
> 📌 **걷기를 말하거나 손대기 전에 이 문서를 연다.** 없는 것을 짓기 전에 «있는 것»을 확인한다.

---

## 1. 축이 «셋»이다 — start · follow · collect

```
start    어디서 출발하나   씨앗 = 마킹. `id`(+ `positive[]` / `negative[]` 부호 있는 씨앗)
follow   어느 «길»을 밟나   술어 목록. `이름:키1,키2` 로 «목적지 키» 제약까지.  없으면 «전부»
collect  무엇을 «가져오나»  도메인 «노드 타입»(선언된 엔터티 이름).            없으면 «전부»
```
🔵 **`follow` 는 길이고 `collect` 는 짐이다.** 웨이퍼에서 결함에 닿으려면 다이를 «지나야»
하지만, 지나는 것과 «실어 오는 것»은 다르다.
⚠️ **짝짓기는 부르는 쪽의 일이다** — 다이 맵이면 `collect=die` · `follow=inspected`.
안 맞는 짝(`collect=defect` + 길 전체)을 만들어 놓고 «설계 문제»라 부르지 않는다.

## 2. 🔴 그리고 그 짝을 «선언이 뽑아 준다» — 이것이 이미 있다

```
GET /api/ledger/declaration      ->  { state, entities, predicates, sources }
client2/src/rnd_board/api.js
   typeGraph(declaration)        ->  선언의 predicates 로 «타입 그래프» (from -술어-> to)
   pathsBetween(decl, from, to)  ->  그 그래프의 «단순 경로 전부» = { hops, follow, chain }
client2/src/rnd_board/walk_box_panel.js
   routes()                      ->  pathsBetween(선언, 시작타입, 도착지)
   useRoute(i)                   ->  🔵 `follow` 와 `hops` 를 «그 경로에서» 채운다
```
**그러므로 사용자는 `follow` 를 손으로 적지 않는다.** «시작 타입 + 도착지»를 고르면
후보 경로가 목록으로 나오고, 하나를 «누르면» `follow`·`hops` 가 들어간다.

### 그 계산의 성질 (소스 주석이 근거를 들고 있다)
```
상한       types - 1.  «구조적» 상한이다 — 단순 경로는 타입을 재방문 못 한다.
          ⛔ 짧게 하려고 낮추지 않는다: 상한 4 면 recipe->quantity 가 «둘인데 하나»로 보인다
작게 유지  상한이 아니라 «고리 랭크»(E-V+1)가 한다. 오늘 1 이라 한 쌍에 경로 «둘»이 상한
          어휘에 고리가 늘면 목록도 는다 — 그때는 «어휘를 볼» 때이지 답을 줄일 때가 아니다
자기 고리  X -술어-> X 는 «경로의 한 칸»이다 (소유자 정정 2026-08-29).
          빼면 계보·전달이 «통째로» 사라진다 — transfer 는 die->die 이고 원자 401,206 으로
          원장에서 제일 큰 술어다. bonded_from 18,545 · slot_map 135 · leads_to 22 도 자기 고리
          한 술어는 «한 번»만 밟는다: 반복 횟수는 `follow` 가 아니라 «사용자 축»이다
```

## 3. 라우트 — 데이터에 답하는 것은 «하나»

```
GET /api/ledger/subgraph     걷기. 아래 인자 아홉
GET /api/ledger/declaration  무엇을 물을 수 있나 (entities · predicates · sources)
GET /api/ledger/gaps
```
```
id(alias)  hops 1–40  direction outgoing|incoming|both  node_limit 10–1000
edge_limit 20–MAX  positive[]  negative[]  follow[]  collect[]  backbone_hops 0–40
```
⚠️ `backbone_hops` 는 「같은 자재를 따라가는 걸음」에 주는 «별도» 예산이다 — 그걸 일반 홉과
같이 세면 진짜 탐색이 예산을 못 쓴다.

## 4. 돌려주는 것

```
nodes        {id, type, label, keys}    🔵 type 이 «도메인 낱말»(die·wafer·defect…)
edges        {source, target, predicate, qualifiers}
seeds        씨앗과 «부호»(+/-)
propagation  🔴 «닿은 노드 전부»를 두 부호의 «도달 대비»로 순위 매긴다
             모집단이 전부인 것은 «소유자 판정»(2026-08-28)이다 — 한 타입으로 거르면
             묻고 있는 것보다 «좁은» 질문에 답하게 된다. `collect` 는 «짐»만 거르고
             순위는 내부에서 전부 본다. 두 축이 안 부딪힌다
walk/state   모드·방향·시작 부호 수 / ready|empty
```

## 5. 실측 (총괄, 2026-09-06 21:0x · 라이브)
```
씨앗 wafer 하나 · hops=4
follow 없음 · collect 없음               nodes «400» = 정확히 상한 = «잘림»
follow=inspected,observed                nodes «250» edges 249  🔵 길만 좁혀도 잘림이 사라진다
  + collect=die                          nodes 278 (die 만)
  + collect=defect                       nodes 121 (defect 만)
collect=die@1                            die 와 «같은 답» — 버전 접미를 양쪽에서 벗긴다
collect=banana                           🔴 거절 `node_type_not_declared` + unknown/declared 집합
```

## 6. ⚠️ 오늘 «아직» 안 된 것 (2026-09-06 기준 — 고치면 이 절을 지운다)
```
좌석      보드의 좌석들은 이 경로 계산을 «안 쓰고» 요청을 손으로 짓는다.
         걷기 상자(walk box)만 쓴다
이름 충돌  클라의 `spec.collect` 가 «COLLECTS 의 행 이름»이라 전선의 `collect` 와 부딪힌다
         -> 판정: 전선이 원장 낱말을 가지고 «클라 쪽이 개명»한다
씨앗 철자  `/declaration` 은 `wafer@1` 로 알려주는데 씨앗 id 는 `wafer` 로 만들어야 한다
         (collect 는 양쪽 다 받는데 씨앗 id 는 «엄격»하다)  -> 큐 C-25
```

---
📎 결함·판정은 [`SERVER_DEFECT_QUEUE`](../process/SERVER_DEFECT_QUEUE.md).
📎 마킹의 뜻은 CLAUDE.md 「마킹한 노드의 하위 그래프를 데이터로 들고 온다」 절.
