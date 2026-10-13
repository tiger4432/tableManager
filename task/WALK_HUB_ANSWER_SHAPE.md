# 걷기 허브 — 답의 모양 (구현자, 총괄 b5f3fc849 + 01a56c82d, 10-12 밤)

서버 가지 `impl-walk-hub` 가 낼 모양입니다. 클라 허브 그리기는 이것을 보고 짓습니다. 짓는 중에 바뀌면 이 파일을 고칩니다.

## 칸

```
nodes[]    그래프 노드 + 허브 노드. 허브 노드는 «hub» 칸이 있는 것
           id        <가까운 노드 id>|<술어>|<방향>|<먼 타입>|<값>   — 늘 다섯 칸, 오른쪽에서 넷을 떼면 가까운 노드 id
                     값 = 대조값 «+,−» (예 1,0 · 0,1 · 1,1), aux 를 물었으면 그 판정이 붙는다(예 0,1,found) — 총괄 afcb79f14 · 5ad030347
                     한 걸음이 값이 다른 구성원을 가지면 «옆 허브»가 하나 더 선다(같은 걸음, 다른 값)
                     가까운 쪽이 허브이면 그 허브 id 가 그대로 들어간다(허브 너머의 허브)
           type      구성원 타입 (선언된 엔티티 타입 그대로 — 새 타입 없음)
           count     구성원 수
           value     [+, −] 그 허브 구성원의 대조값 — 머리 값 = 구성원 값
           aux       {state} — aux 를 물었을 때만
           depth     구성원의 깊이
           label     "<타입> ×<count>"
           hub       {near, predicate, direction, of}  — of: 앞 허브 id(허브 너머의 허브일 때) 또는 null
edges[]    허브에 닿는 선은 «허브 선» 하나로 접힌다 — {id, source, target, predicate, count, records, records_more, worlds}
           count     접힌 선 수(겹수) — 허브 선에만
           records   허브 선은 [] · records_more 0 (원자는 표의 행이 든다)
           worlds    접힌 선들의 세상 합집합, 정렬
tables     {허브 id: {columns, rows, count}}
           columns   type · depth · id · parent_id · via · seed + 선언 열(키 · 수식어 · 속성) — format=rows 의 열 규칙
           rows      행 하나 = 구성원 하나, 칸은 columns 순서의 배열
           parent_id 허브 너머의 허브이면 앞 허브의 구성원 id (그 구성원의 «하위 표» 행)
           count     행 수 (노드 예산 밖)
propagation.ranked[]  허브는 후보 하나 — reach 는 구성원의 것, tied_members = 구성원 수
more.resume           허브(키 + 구성원 + 행의 부모)와 앞 쪽들이 낸 것을 싣는다 — 클라는 그대로 돌려주면 된다
bundles               ⚰️ 은퇴 — fanout_limit 을 넘는 걸음도 같은 허브가 된다
expand                허브 id(다섯 칸)를 주면 그 «걸음»을 펴서 그린다(값은 안 봄). 다른 모양은 422
씨앗                  positive · negative 에 허브 id 를 주면 그 «걸음»의 먼 노드 전부(모든 값)에서 걷는다
tables                허브가 있을 때만 있다. 노드 허브의 행 = 그 구성원 노드(소유자 결정 — 원본 행은 «행 허브», 0b7d84462 A)
```

## 쪽 = 델타 (총괄 d2a64a904 · 10-13)

이어 걷기(`more.resume` 로 받는 다음 쪽)의 쪽은 «바뀐 것만» 옵니다. id 는 쪽 사이에 안 바뀝니다.
받는 쪽은 쪽마다 아래 차례로 id 덮어쓰기를 합니다 — 차례대로 덮어쓴 결과가 한 번 걸은 답입니다.

```
차례          moved -> left -> nodes -> edges -> tables
nodes[]       새 노드 · 바뀐 허브 머리(count · value · aux 가 바뀌면 머리 전체가 다시 옴)
              {"id": <허브 id>, "count": 0} — 두 칸뿐 = 그 허브가 없어졌다. 머리와 그 표를 지운다
edges[]       새 선 · 바뀐 허브 선(겹수 · worlds 가 바뀌면 다시 옴). 겹수는 «지금까지 전부»
              {"id": <선 id>, "count": 0} — 두 칸뿐 = 그 허브 선이 없어졌다
tables        {허브 id: {columns, rows, count}} — 이 쪽에서 «새로» 그 허브에 든 행만. count = 이 쪽의 행 수
              허브의 구성원 수는 머리의 count. 앞 쪽 행은 다시 안 온다
left[]        [허브 id, 행 id] — 앞 쪽에서 그 허브의 행이었는데 이 쪽에서 다른 길로 닿아 혼자 선 것
              표에서 빼면 된다. 그 노드는 같은 쪽 nodes[] 에, 그 선은 이 쪽이 다시 읽어 edges[] 에 온다
moved[]       [행 id, 옛 허브 id, 새 허브 id] — 값이 바뀌어 옆 허브로 옮긴 것. 행의 칸은 그대로 옮긴다
edges_pending [행 id …] — 혼자 선 행의 선을 이 쪽 원자 예산 안에 다 못 읽은 것. 다음 쪽이 맨 먼저 읽는다
              (그 쪽이 올 때까지 그 행의 선은 안 보인다)
```

```
쪽마다의 수   노드의 claim_count · predicates 는 «그 쪽이 읽은» 원자 수다(허브 없이도 전부터 그랬다) — 덮어쓰면 마지막 쪽 수
쪽을 넘은 선  선의 원자(records · records_more · claim_id · by_world · basis · occurred_at · source_who)는 «그 쪽이 읽은» 것이다
             (허브 전부터) — 원자가 두 쪽에 나뉜 선은 덮어쓰면 마지막 쪽 것만 남는다. 선의 «때 · 누가»도 그렇다. 이어 받은 화면의 추세는 덜 그려질 수 있다. 예산별 스트리밍에서 누적한다(총괄 10-13)
한계(총괄 10-13)  대조(+ · −) 걷기에서 뒤 쪽이 «다시 닿지 않은» 행은 앞 쪽의 값 그대로다 — 이어 걷기는 새로 닿은 것만 다시 매긴다
             (허브 전에도 노드 순위가 같은 한계). 그런 행의 허브(값이 id 에 든다)는 한 번 걸은 답과 다를 수 있다.
             다음 일인 예산별 스트리밍은 묶음마다 전체 위에서 다시 흘려 값까지 맞춘다
```

## 붙인 표의 행 — 행 붙이기 (총괄 0b7d84462 A · 14a486e8c · 10-13) — 걷기 쪽 지음(impl-row-attach d2b1bd92d)

원장 소스의 `attach` 는 «문장» 하나입니다. 그 표의 행은 원자가 되지 않고, 걷기가 그 술어를 «걸을 때 표에서 읽는 선»으로 읽습니다.
🔵 답에 새 칸은 하나뿐입니다(`truncated.rows_withheld`). 행 노드는 보통 노드, 행 허브는 위의 허브 모양 그대로입니다.

```
선언      sources.<이름> = { relation, attach: { subject: <부모 노드>, predicate: <어휘의 술어>, target: <행 노드>, columns: [선택] } }
          노드는 짧은 꼴의 {"node": <타입>, "keys": {<키>: <칸>}} (B 의 원장 선언 간소화 위에 앉는다 — 선언 칸은 아직)
          대상 타입은 entities 에(keys · attributes), 술어는 vocabulary 에(entity_ref, 주어 타입 -> 대상 타입)
          columns 를 안 적으면 그 표의 칸 전부(표 선언의 칸 목록), 적으면 좁힘 — 허브 표 열도 같은 목록(총괄 10-13 «행을 통째로»)
          원자는 0 (번역 · backfill · 소급 · 따라가기)
답        행 노드 = 대상 타입의 보통 노드(키 = 그 표의 키 칸, attributes = columns 의 값). 선 = 그 술어, 보통 선
          값은 칸의 형 그대로 — 숫자 칸은 숫자(소수 없으면 정수), 시각 칸은 답의 시각 모양(UTC ISO), 빈 칸은 null, 글은 그대로
          허브 표 rows 와 노드 attributes 가 같은 값
          술어에 hub: true 면 허브로 접힌다(×1 도) — id 도 보통 허브 id <노드>|<술어>|<방향>|<대상 타입>|<값>, 표 = tables[허브 id]
          fanout_limit 을 넘어도 같은 허브. expand · 예산 · 이어 걷기 · left/moved 모두 허브 그대로
          거꾸로도 걷는다 — 행 노드에서 부모로(incoming)
읽는 법   걷기의 같은 읽기 안에서 문장마다 갈래 하나 — 노드마다 질의 없음(PG 칸: 다이 3 · 30 같은 질의 수)
세상·시각  행은 표의 «지금». 운영 세상을 빼고 걷거나 since · until 을 준 걷기에는 행이 안 실리고
          truncated.rows_withheld = 사유 한 줄(그때만 있는 칸 — 없으면 «물을 것이 없었음»)
          이어 걷기의 as_of 는 안 막는다: 붙인 행은 쪽마다 그때의 표 — as_of 에 안 묶임
남음      시간 쪽(around · earlier · later)은 원장만 읽어 붙인 행이 안 나온다
```

예시 — 다이 D1 의 결함 표 행 하나(`has_defect` 가 hub: true, attach 의 columns = size · kind)
```json
{"nodes": [{"id": "<D1>|has_defect|outgoing|defect_row|1,0", "type": "defect_row", "label": "defect_row ×1",
            "depth": 2, "node_kind": "entity", "count": 1, "value": [1, 0],
            "hub": {"near": "<D1>", "predicate": "has_defect", "direction": "outgoing", "of": null}}],
 "edges": [{"id": "<선 id>", "source": "<D1>", "target": "<D1>|has_defect|outgoing|defect_row|1,0",
            "predicate": "has_defect", "count": 1, "records": [], "records_more": 0, "worlds": ["default"]}],
 "tables": {"<D1>|has_defect|outgoing|defect_row|1,0": {
     "columns": ["type", "depth", "id", "parent_id", "via", "seed", "defect_id", "size", "kind"],
     "rows": [["defect_row", 2, "<F4>", "<D1>", "has_defect", "<W>", "F4", 7, "void"]], "count": 1}},
 "truncated": {"…": "…"}}
```
since · until 을 준 걷기 — `"truncated": {…, "rows_withheld": "rows are attached as their tables are now - a walk with since or until carries none"}`

## 예시 — 로트 하나 → 웨이퍼 ×100 → 디펙 ×3,000 → 종류 5 (노드 8 · 선 7)

```json
{
  "nodes": [
    {"id": "L1", "type": "lot", "depth": 0, "label": "LOT-1"},
    {"id": "L1|has_wafer|outgoing|wafer|1,0", "type": "wafer", "depth": 1, "count": 100,
     "label": "wafer ×100",
     "hub": {"near": "L1", "predicate": "has_wafer", "direction": "outgoing", "of": null}},
    {"id": "L1|has_wafer|outgoing|wafer|1,0|observed|outgoing|defect|1,0", "type": "defect", "depth": 2,
     "count": 3000, "label": "defect ×3000",
     "hub": {"near": "L1|has_wafer|outgoing|wafer|1,0", "predicate": "observed", "direction": "outgoing",
             "of": "L1|has_wafer|outgoing|wafer|1,0"}},
    {"id": "K1", "type": "defect_kind", "depth": 3, "label": "void"},
    {"id": "K2", "type": "defect_kind", "depth": 3, "label": "crack"}
  ],
  "edges": [
    {"source": "L1", "target": "L1|has_wafer|outgoing|wafer|1,0", "predicate": "has_wafer", "count": 100, "records": []},
    {"source": "L1|has_wafer|outgoing|wafer|1,0", "target": "L1|has_wafer|outgoing|wafer|1,0|observed|outgoing|defect|1,0",
     "predicate": "observed", "count": 3000, "records": []},
    {"source": "L1|has_wafer|outgoing|wafer|1,0|observed|outgoing|defect|1,0", "target": "K1",
     "predicate": "of_kind", "count": 1800, "records": []}
  ],
  "tables": {
    "L1|has_wafer|outgoing|wafer|1,0": {
      "columns": ["type", "depth", "id", "parent_id", "via", "seed", "wafer"],
      "rows": [["wafer", 1, "W001", "L1", "has_wafer", "L1", "W-001"]],
      "count": 100
    },
    "L1|has_wafer|outgoing|wafer|1,0|observed|outgoing|defect|1,0": {
      "columns": ["type", "depth", "id", "parent_id", "via", "seed", "x", "y"],
      "rows": [["defect", 2, "D0001", "W001", "observed", "L1", 3, 7]],
      "count": 3000
    }
  }
}
```

(예시의 노드는 다섯만 적었습니다 — 종류 다섯 중 둘. 선도 셋만. 실제 답은 노드 8 · 선 7 입니다.)
