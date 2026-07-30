# `GET /graph/chip-trace` — 웨이퍼는 확장할 허브가 아니라 스코프다 + 엣지 props의 `spatial` 거부

> **일자:** 2026-07-30 08:53 | **커밋:** `8670e3b` | **담당:** Ontology PM
> **대상:** `server/main.py`(+297) · `server/ontology_config.py`(+32) · `server/tests/test_chip_trace_api.py`(신규 534줄, 22건) · [ONTOLOGY_GRAPH_SPEC §7.5d](../spec/ONTOLOGY_GRAPH_SPEC.md)
> **관련:** 스키마 절반 `aea4700` · QA HIGH 수리와 다섯 번째 상태 `530fdfd`

## 배경 — BFS로는 도달할 수 없음을 측정으로 확인했다

사용자 지시: *"wafer 컨텍스트 지정해서 추적해. 모든 노드를 하지말고."*

기존 `POST /graph/trace`를 같은 시드로 돌린 실측:

- depth 2에서 이미 **1,000 노드 캡을 태우고, 그중 994개가 형제 CoreCell**이다 — 남의 칩이다.
- `Knob`에는 **아예 도달하지 못한다.** walk가 다섯 홉인데 `GRAPH_TRACE_DEPTH_CAP`이 3이다.
- **엣지 타입 필터로는 구제되지 않는다.** `Core -FROM_CORE->`를 막으니 홍수가 **더 커졌다**: 1,341 → **11,549**. `Eqp`(degree 10,284)와 `Wafer`로 우회하기 때문이다.

그래서 답은 depth를 늘리는 것이 아니라 **경계가 정해진 타입 질의**다. 세 다리, 각각 인덱스 집합 조인, 재귀 CTE 없음. 234 노드 / 694 엣지, 핸들러 시간 약 57 ms, 무관 노드 0.

**depth 파라미터를 노출하지 않았다.** 노출하면 홍수를 다시 초대한다. `Knob`/`Recipe`/`Eqp`의 잎 규칙은 **질의 형상이 강제**한다 — 매핑 config에 스텁 라벨의 class를 선언할 채널이 없고, 그 채널을 만드는 것은 G2.5다.

## 홉마다 이름 있는 결과 — 빈 홉 금지

| 상태 | 뜻 |
|---|---|
| `recorded` | 선언 있고 행 있음 |
| `none_recorded` | 선언 있고 행 0 |
| `not_declared` | 매핑이 그 `(type, target)`을 **더는** 선언하지 않음 |
| `scope_unresolved` | Core 주장이 0개 또는 2개 이상 |

**`not_declared`가 별도 이름인 이유**: config rename이 `none_recorded`를 돌려주면 "이 칩에 dt 이벤트가 없다"와 **구별할 수 없다.**

`scope_unresolved`가 있는 이유는 실측이다 — 라이브 **2,687개 셀이 소스 파일별로 복수 `FROM_CORE` 엣지**를 갖는다. `LIMIT 1`은 오늘 데이터에서는 무해하지만 **구조적으로 조용한 승자 선택**이라, 엔드포인트는 후보를 보고한다. 잘림은 상태가 아니라 다리별 별도 플래그다.

**첫 라이브 실행이 내가 잘못 잡은 cap을 잡아냈다**: 종단 다리는 **모든 이벤트에** 앵커되므로 주장 수가 엔티티 8개가 아니라 이벤트 수에 비례한다. `count`(주장 수)와 `node_ids`(개체 수)는 **의도적으로 다르다.**

## 엣지 props의 `spatial` — 검증은 통과하고 반영은 안 되던 선언

같은 커밋에 `spatial` 판정을 넣었다. 종전에는 이 validator가 엣지 props의 `spatial`을 **받아 주었고**, materializer는 `node_cfg["props"]`에서만 `spatial_meta`를 만들어 엣지 루프는 `p["col"]` 외에 아무것도 읽지 않았다. 즉 선언은 **쓰이고 검증되고 저장된 뒤 아무 데서도 효과가 없었다** — 이 validator의 미선언 키 거부가 막으려는 바로 그 무음 사망이다.

```python
def _normalize_props(raw_props, where: str, allow_spatial: bool = True):
    ...
            spatial = raw.get("spatial")
            if spatial is not None and not allow_spatial:
                return None, _EDGE_SPATIAL_REFUSAL.format(where=where, i=i)
```

거부 문구가 **어느 채널로 가야 하는지**를 이름으로 말한다(노드 props). 엣지 좌표가 진짜로 필요해지면 그때 구현하고 **이 거부를 같은 변경에서 지운다**고 코드에 적어 뒀다.

## 검증

신규 테스트 22건, 결함 주입 8건 중 **7건이 자기 케이스에 잡혔다**. 스위트 1300 passed. 라이브 검증은 `create_all`을 예외 발생기로 갈아끼운 읽기 전용으로 돌렸고, **아무것도 하기 전에 CREATE를 일부러 실패시켜 그 무장이 실제로 걸려 있음을 증명**했다.

## 그때 남아 있던 것

- **결함 주입 8건 중 1건은 자기 케이스에 잡히지 않았다** — 커밋 메시지가 "seven caught by their own case"라고 적은 그대로다. 나머지 1건이 무엇이었는지는 diff에 남지 않았다.
- **스펙에 열린 결함을 함께 적었다**: 이 파일을 디스크에서 직접 고쳐도 실행 중인 materializer 루프는 구 선언으로 계속 물화한다 — 리로드 트리거가 `SYSTEM_RELOAD` outbox 이벤트뿐이라서다. 그때는 편집 후 `POST /admin/reload-configs`가 필수였다. 이것이 `530fdfd`가 다룬 40분 창이다.
- 선언 파일이 읽히지 않는 창(`json.load` 실패 → `raw_config = {}`)에서 이 엔드포인트가 **200과 함께 전 다리 `not_declared`**를 답했다는 것은 이 커밋 시점에 알려지지 않았고, QA가 다음 라운드에 HIGH로 올렸다.
