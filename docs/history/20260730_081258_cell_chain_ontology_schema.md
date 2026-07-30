# 칩 추적 온톨로지 — 추상 Chip을 버리고 셀 정체의 사슬로

> **일자:** 2026-07-30 08:12 | **커밋:** `aea4700` | **담당:** Ontology PM
> **대상:** `server/config/ontology_mapping.json.sample` (+76 / −71) — **코드 변경 0줄**
> **관련:** 이 스키마를 소비하는 API `8670e3b` · 이 개정이 남긴 고아 노드를 치우는 `530fdfd` · [ONTOLOGY_GRAPH_SPEC §7.5](../spec/ONTOLOGY_GRAPH_SPEC.md)

## 배경

사용자 요청은 "칩 하나를 본딩에서 DT를 거쳐 코어 웨이퍼까지 따라가라"였다. 그것을 가능하게 하는 정체는 **이미 데이터에 있으면서 쓰이지 않고 있었다**: `bonding_log`와 `dt_log`가 **둘 다** `(core_lot, core_slot, cx, cy)`를 글자 그대로 들고 있어, 코어 셀이 곧 조인이다.

**코드는 한 줄도 쓰지 않았다.** 전부 선언 파일 개정이다 — materializer가 이미 그 선언을 실행한다.

## 판단 ① 노드는 추상 Chip이 아니라 셀 정체다

`CoreCell(core_lot|core_slot|cx|cy)`가 두 로그 공통의 로우 노드이고, `BONDED_TO -> BaseCell(base_id|bx|by)` · `TRANSFERRED_TO -> DtCell(tape_lot|tape_slot|tx|ty)` · `FROM_CORE -> Core`가 그 위에 붙는다. **좌표가 엣지 속성이 아니라 정체의 구성요소**인 것이 결과를 갈랐다:

| 모델 | 결과 |
|---|---|
| 추상 Chip | 본딩 로우 **17건이 붕괴**, 그중 15건이 서로 다른 `(bx,by)`로 — base 위치가 소실됐다 |
| 셀 | 4,434 중 **4,432 생존**, 정확한 중복만 병합 |

**금지되는 것은 dense 맵의 셀마다 노드를 만드는 것**이라고 다시 정의했다. 로그에서 나오는 셀 노드는 5,915개뿐인데 `core_defect_map`을 노드로 승격하면 **그것만으로 96,600개**다. 그래서 `bonding_map`·`core_defect_map`·`dt_map`·`eds_fail_map`은 매핑하지 않는다 — "어느 칩이 어디로 갔나"는 그래프가, "그 셀의 값이 무엇인가"는 맵/오버레이 질의가 답한다.

## 판단 ② 엣지 방향이 브리프와 반대인 이유 — 기계장치의 한계이고 위상은 같다

materializer는 엣지를 **그 로우 자신의 노드에서만** 낼 수 있다(`extract_graph_items`의 `from_node`는 항상 `node_cfg`의 노드). 그래서 `BaseCell -FROM_CORE_CELL-> CoreCell`은 `bonding_log`에서 만들 수 없다. 만들려면 `bonding_log`의 노드가 BaseCell이어야 하는데, 그러면 CoreCell이 소유 테이블 없는 스텁이 되고 `CoreCell -FROM_CORE-> Core`를 낼 수 있는 테이블은 `core_defect_map` 하나뿐이다 — ① 커버리지 3,656/4,414(83%)라 758개 셀의 Core 홉이 통째로 끊기고 ② 그 테이블을 매핑하면 CoreCell이 96,600개가 된다.

그래서 방향을 뒤집었다: `FROM_CORE` 커버리지 **4,414/4,414(100%)**, 신규 코드 0줄. 조회 측 영향 없음 — `_expand_graph_subgraph`가 `from_node`·`to_node` 양방향을 조회하므로 **탐색은 무방향**이고, 방향이 실제로 의미를 갖는 것은 아직 없는 §7.5c 정책 엔진뿐이다.

## 판단 ③ 세 측정이 나머지를 정했다

| 물음 | 실측 | 결론 |
|---|---|---|
| `bonding_map`이 이 base들의 맵인가 | `BASE-01` 형태 94개 vs UUID 397,605개, **교집합 0**, y가 13,123,121까지 | `BaseCell`은 로그에서 잡고 그 테이블은 아무도 읽지 않는다 |
| `wafer_id`가 정체가 될 수 있나 | `wafer_id` 조인 **8/80** vs `(lot,slot)` 조인 **80/80**. 한 값은 깨진 문자열. 세 코어는 모든 공정 행이 사람이 해석한 것과 **다른** 웨이퍼를 가리킨다 | `Core=(core_lot,core_slot)`가 노드, `wafer_id`는 속성으로 강등 |
| 한 코어 셀이 base 셀 하나로 가나 | 최대 **6개**(격리 4개), 그런 셀이 512개 | 접지 않고 **전부** 돌려준다 — 접으면 추적이 조용히 승자를 고른다 |

`base ← dt`는 저장하지 않고 파생이다 — `bonding_log`에 테이프 컬럼이 **아예 없어서** 직접 엣지를 낼 원천이 없고, 코어 셀 경유 2홉 인덱스 조회가 1.6 ms다.

## 만들기 전에 있는지 먼저 봤다

브리프의 `Core -WENT_THROUGH-> ProcessEvent`는 기존 **`PERFORMED_ON`**(ProcessEvent → Core, `(lot,slot)`)과 구조가 같아 그대로 썼다 — 새 선언 0개. 게다가 `WENT_THROUGH`는 `wafer_slot_history → Step`이 이미 쓰고 있어 **이름 충돌**이었다. `IS_WAFER`는 enrichment 자동 승격 `RESOLVED_AS`가 이미 계산한다. 새로 선언한 것은 `BONDED_TO`·`TRANSFERRED_TO`·`FROM_CORE` 셋뿐이다.

## 검증

서빙 DB에 물화하고 **개수가 아니라 정체 단위로** 대조했다: CoreCell 9,261 = 두 로그 셀의 합집합 · BaseCell 747 · DtCell 768 · Core 80 · Knob 18. ProcessEvent는 10,316행에 대해 10,273인데, 원본에 `proc_id` 중복이 **정확히 43건** 있다. 라이브 walk: `CoreCell LOT-A|05|13|5` → BaseCell 3개 · DtCell 1개 · 자기 Core · ProcessEvent 206개 · Knob 7개.

## 그때 남아 있던 것

- **이 개정이 은퇴시키는 것**: 라벨 `Chip`·`DTEvent`, 엣지 `BONDED_FROM`·`PLACED_ON`·`ONTO_TAPE`·`TRANSFERRED_FROM`. 엣지는 `_retarget_stale_edges`가 row-ref 스코프로 깨끗이 교체하지만 **구 노드는 엣지 0개인 고아로 남았다** — 그때는 `scripts/graph_orphan_sweep.py`를 손으로 돌리는 것이 유일한 정리 경로였고, 라벨 인구의 50% 초과 삭제는 기본 거부라 `--max-fraction` 조정이 필요했다. 이 고아가 `530fdfd`의 스케줄 스윕이 다룬 12,468개 `Chip`이다.
- **`Wafer` 노드는 이 파일에서 없앨 수 없었다** — `enrichment_rules.json`의 `core_wafer_attribution` rule이 `wafer_id`를 `RESOLVED_AS`로 자동 승격하고, 매핑 config에 그것을 끄는 선언이 없다. `Core -RESOLVED_AS-> Wafer` 노드 11개(깨진 것 1개 포함)가 생겼고 추적 경로로는 쓰이지 않았다.
- **선언 채널이 테이블당 1개(자기 노드)뿐**이라, 정책이 막으려는 슈퍼 허브 라벨(`BaseCell`·`DtCell`·`Eqp`·`Knob`·`Recipe`·`Step`·`Tape`)은 애초에 `node_class`를 걸 자리가 없었다. 같은 이유로 `spatial`도 그 라벨에는 걸 수 없었다. 실측 허브 degree: Knob 302 · Eqp 427 · Base 102 · Tape 256 · Core 540.
- `cx/cy`가 identity로 올라가면서 `CoreCell`은 props에 **중복 선언**해 좌표계를 명시했지만, 소유 테이블이 없는 `BaseCell`·`DtCell`은 그것도 못 했다.
- 「테이프로 되돌리기」 경로가 이 개정으로 **문자열 하나에서 identity 재설계로 커졌다** — 파일 안에 그렇게 적어 뒀다.
- 커버리지는 보고만 하고 추론하지 않았다: 본딩 칩 8,891개 중 dt 이벤트가 있는 것은 **419개**뿐. 나머지는 "dt 기록 없음"이어야 하고 빈 홉("DT를 안 거쳤다")이면 안 된다.
