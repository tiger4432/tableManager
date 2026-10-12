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
edges[]    허브에 닿는 선은 «허브 선» 하나로 접힌다
           count     접힌 선 수(겹수) — 허브 선에만
           records   허브 선은 [] (원자는 표의 행이 든다)
tables     {허브 id: {columns, rows, count}}
           columns   type · depth · id · parent_id · via · seed + 선언 열(키 · 수식어 · 속성) — format=rows 의 열 규칙
           rows      행 하나 = 구성원 하나, 칸은 columns 순서의 배열
           parent_id 허브 너머의 허브이면 앞 허브의 구성원 id (그 구성원의 «하위 표» 행)
           count     행 수 (노드 예산 밖)
propagation.ranked[]  허브는 후보 하나 — reach 는 구성원의 것, tied_members = 구성원 수
more.resume           허브(키 + 구성원 + 행의 부모)를 싣는다 — 클라는 그대로 돌려주면 된다
bundles               ⚰️ 은퇴 — fanout_limit 을 넘는 걸음도 같은 허브가 된다
expand                허브 id(다섯 칸)를 주면 그 «걸음»을 펴서 그린다(값은 안 봄). 다른 모양은 422
씨앗                  positive · negative 에 허브 id 를 주면 그 «걸음»의 먼 노드 전부(모든 값)에서 걷는다
tables                허브가 있을 때만 있다. 노드 허브의 행 = 그 구성원 노드(소유자 결정 — 원본 행은 «행 허브», 0b7d84462 A)
```

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
