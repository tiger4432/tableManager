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

🔴 **정정(2026-09-08 판정 123) — 노드는 «자기 속성»을 든다.**
「술어가 아닌 것은 표면적으로 노드」·「값은 수식어」와 «충돌이 아니라 확장»이다 —
엣지가 나르는 수식어는 **그대로** 엣지의 것이고, 새로 생긴 것은 «노드 자신에 선언된 이름»이다.
신원은 여전히 `keys` «하나»다 — 속성은 신원에 들지 «않는다».

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
nodes        {id, type, label, keys, attributes}    🔵 type 이 «도메인 낱말»(die·wafer·defect…)
             🔴 `attributes` 는 «선언된 이름만» 든다. 같은 이름을 여러 문장이 먹이면
             **최신 `occurred_at` 이 이긴다** · 그때 `attribute_conflicts` 가 «수»로 실린다(목록이 아니다)
             ⚠️ «닿지 않은» 속성은 `null` 이 아니라 **키가 없다** — 「값이 없다」와 「안 걸어졌다」가
             같은 그림이면 부르는 쪽이 둘을 못 가른다
             🔴 `attribute_conflicts` = 닿은 원자에서 «서로 다른 값»(JSON 동등)이 둘 이상인 «이름의 수»
             — 같은 값이 두 시각에 오는 것은 «충돌이 아니다»(판정 124). 도착을 세면 「다시 말한 사실」이
             「어긋난다」로 보인다

edges        {id, source, target, predicate, predicate_label, original_predicate, qualifiers,
              🔵 claim_id, basis}   — 🔴 «근거가 여기 실린다»(S-75 B11, 2026-09-09):
              원자에서 온 엣지는 `claim_id` = 그 원자의 id · `basis` = 그 원자의 `source_raw_ref`(어느 «물리 행»)
              를 달고, 응답은 이 dict 를 «투영 없이» 그대로 낸다(`ledger_subgraph.py:996~999`, :1361)
              ⚠️ 여기 「넷」이라고 적혀 있었다 — 문서가 코드보다 좁았고, 그 탓에 「근거를 안 싣는다」로 읽혔다
              ⚠️ `sources`·`witnesses`·`rank` 도 매 엣지에 있지만 «쓰는 자리가 0» 이다(③′)
seeds        씨앗과 «부호»(+/-)
propagation  🔴 «닿은 노드 전부»를 두 부호의 «도달 대비»로 순위 매긴다
             모집단이 전부인 것은 «소유자 판정»(2026-08-28)이다 — 한 타입으로 거르면
             묻고 있는 것보다 «좁은» 질문에 답하게 된다. `collect` 는 «짐»만 거르고
             순위는 내부에서 전부 본다. 두 축이 안 부딪힌다
walk/state   모드·방향·시작 부호 수 / ready|empty
```
🔵 **이것을 «어떻게 선언하나» — 두 줄 (판정 124 정정본)**
```
운영에서는 «엔티티 선언»에 attributes 이름을 적고,
«소스의 bind» 에서 그 엔티티에 컬럼을 «한 번» 매기면 됩니다  (bind.entities.<type>.attributes)
```
⚠️ 문장(`mappings`)마다 매기면 한 엔티티가 K 문장에 나올 때 둘째 줄이 «K 번»이라 두 줄이 1+K 가 된다.
역할 수준 attributes 는 «덮어쓰기»로만 산다 — 같은 문장이 같은 타입을 «두 역할»로 쓰면(die→die 이송)
소스 수준이 «중의»라 컴파일이 «이름 대어 거절»하고 그것을 요구한다.


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

## 6. ⚠️ «아직» 안 된 것 (총괄이 재서 갱신 · 2026-09-06 22:3x)
> 🔴 이 절은 «고쳐지면 지웁니다». 여기 남은 문장이 낡으면 매 세션 «거짓을 심습니다».

```
좌석      🔴 그대로 — 보드 좌석들은 «경로 도출을 안 씁니다». 요청을 손으로 짓습니다
         `pathsBetween` 을 쓰는 곳은 «둘»뿐: 걷기 상자 · 걷기 화면(`src/walk/`)
         (총괄 실측: 그 밖의 클라 파일에서 히트 «0»)
씨앗 철자  🔴 그대로 — `/declaration` 은 `wafer@1` 로 알려주는데 그 철자로 씨앗을 만들면
         «state: empty · nodes 1». `wafer` 로 만들어야 돕니다 (총괄 라이브 재확인 22:3x)
         🔵 클라는 `entitySeedId` 가 «벗겨서» 보내므로 화면에서는 안 걸립니다 -> 큐 C-25
class     🔴 아홉 중 «여섯»이 class 미선언. 걷기가 아는 허브가 «셋»뿐이고
         「미선언」이 곧 「동적」으로 굴러갑니다 -> 큐 C-29
```
### ✅ 그 사이 닫힌 것 (여기 있던 문장들)
```
⚰️ 이름 충돌   클라의 행 이름 키가 `legacyRoute` 로 «개명»됐고 «옛 키는 거절»됩니다
              (무시가 아니라 거절 — 옛 이름으로 부르면 조용히 안 넘어갑니다)
⚰️ 정적 경로   경로 목록이 「정적 -> 정적이 아닌 것」 걸음을 «뺍니다».
              판정을 클라에 다시 안 적고 «서버 술어»(`class === 'static'`)를 그대로 씁니다
              실측: wafer→defect 9 -> «8» · 정적→정적(메커니즘 체인) «1» 살아 있음
⚰️ collect     화면에 «있습니다» — 체크박스, 없으면 안 싣습니다(=전부).
              결과에 «타입 분포»가 붙어 「걸렀다」가 눈에 보이고,
              카운트 줄이 「노드 121 (collect: defect) · 엣지 249 (전부)」로 «주어»를 답니다
```

## 🔴 구간 걷기 — `since` · `until` (S-98, 판정 208)

```
GET /api/ledger/subgraph?since=<ISO>&until=<ISO>    둘 다 선택 · 반열린 구간 [since, until)
걸리는 것   원자의 occurred_at — 즉 «engine»이다. 노드는 닿은 엣지로만 들어온다
씨앗     구간과 «무관»하다 — 모든 엣지를 제외하는 창도 씨앗은 돌려준다.
         그러지 않으면 «좁은 창»과 «틀린 id»가 같아 보이고, 운영자는 엉뚱한 것을 뒤진다
절단     truncated.interval_excluded = «구간 밖이라 안 가져온 수»(홉 합)
         ⛔ 구간을 안 줘으면 그 칸은 «없다» — 0 이 아니다.
           0 은 「물었고 제외된 게 없다」이고 부재는 「물지 않았다」다
거절     ISO 가 아니면 422 `interval_not_iso8601` · since ≥ until 이면 422 `interval_empty`
         (조용히 무시하면 «전체 역사»를 돌려주고 그걸 「창 밖엔 없다」로 읽는다)
시간대   지정이 없으면 UTC 로 읽는다 (`?since=2026-09-01` 이 보통의 요청이므로)
```
⚠️ **멱등은 «선언이 안 바뀐 동안»만 참이다.** 같은 구간을 두 번 물으면 같은 그래프가 나오지만,
그 사이에 선언이 바뀌어 원자가 다시 번역되면 «같은 구간»이 다른 답을 냅니다 —
구간은 «사건의 시각»을 자를 뿐, «번역의 세대»를 고정하지 않습니다.

---
📎 결함·판정은 [`SERVER_DEFECT_QUEUE`](../process/SERVER_DEFECT_QUEUE.md).
📎 마킹의 뜻은 CLAUDE.md 「마킹한 노드의 하위 그래프를 데이터로 들고 온다」 절.
