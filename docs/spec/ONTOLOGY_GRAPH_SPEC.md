# 🕸️ Ontology Knowledge Graph Spec — LLM 백본 지식그래프

> **Status:** 🟢 Living (2026-07-25 승격 — G1·뷰어·G2 라이브 가동으로 §1~§6 실증됨. §7.x는 G3+ 설계) | **Last-verified:** 2026-07-25 | **Owner:** 총괄 PM
> 상위: [SYSTEM_OVERVIEW (SSOT)](../overview/SYSTEM_OVERVIEW.md) §1 핵심가치 #2 | 대체 완료: [graph_db_integration_plan.md](../_archive/graph_db_integration_plan.md) (Kafka 기반 구상 — 본 스펙이 대체, 2026-07-25 아카이브)

## 0. 핵심 가치 (사용자 확정 2026-07-25)

라인에서 수집·교정된 모든 데이터를 **속성 그래프(property graph)로 자동 승격**한다. 이 그래프의 존재 이유 3가지:

1. **LLM용 지식 그래프** — LLM이 도구로 질의·검색하는 사실 기반(백본). 스키마 의미론(description)·provenance 출처 표기·MCP 도구 API가 여기서 나온다.
2. **수많은 RDB JOIN의 효율화** — 이종 키로 흩어진 테이블들을 매번 N-way JOIN으로 꿰지 않고, 사전 구체화(materialize)된 엣지를 인덱스 순회로 탐색한다. 특히 enrichment 해석(사람 교정)이 있어야만 이어지는 조인(core_lot/slot↔wafer_id)은 관계형으로는 매번 매핑 테이블 경유가 필요하지만 그래프에선 엣지 하나다. 추적 리포트·참조뷰·향후 앱 내 조회의 가속 계층.
3. **불량 추론 네트워크** — 불량 개체(wf/chip)를 시드로 그래프 알고리즘(Personalized PageRank, 공유 이웃 분석, 커뮤니티 탐지 등)을 돌려 **의심 개체 랭킹**(설비·lot·시간대)을 산출하는 근본원인 분석 기반.
4. **시공간 topology 매핑 (물리적 추론)** — 반도체 R&D 관점에서 공정 관여 객체(wafer, chip, 설비/지그)의 **시간·공간 좌표를 1급 속성**으로 매핑해, 관계 순회를 넘어 **실제 물리 추론**을 가능하게 한다: wafer 좌표계 위 불량의 공간 패턴(엣지 링/센터/스크래치), 설비·지그 위치별 불량 집중, 처리 시간축 인접성(같은 설비 연속 처리 전이) 등.

## 1. 확정된 방향 (2026-07-25 사용자 논의)

| 결정 | 내용 |
|---|---|
| 핵심 가치 | §0의 4가지 — ①LLM 지식그래프 ②JOIN 효율화 ③불량 추론 네트워크 ④시공간 topology(물리 추론) |
| 인구(population) 방식 | **자동 승격이 본체** — 인제션되는 모든 로우가 매핑 config에 따라 노드/엣지가 됨. enrichment는 여러 소스 중 하나(사람 검증이라 신뢰도만 특별) |
| 최종 용도 | **LLM용 백본 지식그래프** — LLM이 도구로 질의·검색하는 사실 기반 |
| 추적 UX (v1) | **추적 리포트**(엔티티별 그룹 테이블 + 시간순 타임라인). 그래프 시각화는 G3 |
| v1 범위 | 데모 3종(bonding_log, wafer_slot_history, core_wafer_map)으로 킬러 쿼리 E2E 검증 후 확장 |
| 저장소 | **PG 엣지 스토어**(방향 확정 — §4 이관 안전성 참조). Neo4j는 G3 병행 타깃 |

## 2. 데이터 모델 — 저장소 중립 속성 그래프

```
graph_nodes(id, label, identity_key, props JSONB, created_at, updated_at)
graph_edges(id, type, from_node, to_node, props JSONB,
            source_name, source_row_ref, updated_by, event_time, created_at)
```

- **인덱스 규율 (가치 ② JOIN 효율화의 물리적 실체)**: `graph_nodes(label, identity_key)` UNIQUE, `graph_edges(from_node, type)` / `(to_node, type)` 복합 인덱스 — k-hop 순회가 인덱스 룩업의 연쇄가 되도록. 이종 키 N-way JOIN을 균일한 엣지 순회로 대체하는 것이 이 스토어의 존재 이유이므로, 인덱스 없는 엣지 접근 경로는 금지.
- **엣지 provenance = 레이어링의 그래프 확장**: `source_name`(pipeline_parser/chain/user/…)과 우선순위 규칙(user 최우선)을 셀과 동일하게 적용. 같은 관계를 자동·사람이 다르게 주장하면 사람이 이긴다. LLM 답변의 출처 표기 근거이기도 하다.
- identity: v1은 정확 일치 MERGE. 표기 변형 해석(dirty identity)은 enrichment로 사람이 교정 — 교정 결과가 `RESOLVED_AS` 엣지로 승격.

## 3. 매핑 config — 트랙의 심장 (`ontology_mapping.json` 실전화)

table_config과 같은 사용자 config 패턴. 테이블별:

```jsonc
{
  "bonding_log": {
    "node": { "label": "Chip", "identity": "log_id", "props": ["bx", "by", "cx", "cy"],
              "node_class": "dynamic" },                            // ← §7.5c 정적/동적 분류 (필수 예정)
    "description": "본딩 설비가 chip 1개를 base에 실장한 이벤트",   // ← LLM 그라운딩용 (필수)
    "edges": [
      { "type": "BONDED_FROM", "target_label": "Wafer",
        "target_identity_from": ["core_lot", "core_slot"],       // 복합 식별 → identity 해석 규칙
        "description": "이 chip이 잘려 나온 원판 wafer" },
      { "type": "PLACED_ON", "target_label": "Base", "target_identity_from": ["base_id"],
        "props": ["eventtime"], "description": "실장된 대상 지그/설비" }
    ]
  }
}
```

- **enrichment rule 자동 승격**: rule의 `decision_key → target` 정의는 매핑 항목으로 자동 변환(`RESOLVED_AS`) — rule 추가 = 온톨로지 확장.
- `description`은 장식이 아니라 **LLM이 스키마를 읽고 스스로 질의를 구성하는 근거**. 매핑 검증 시 필수 필드.
- 핫리로드 대상(이슈 #7 해소된 `refresh_dynamic_models` 패턴 준용, 이슈 #8 동승).

## 4. 저장소: PG 엣지 스토어 — Neo4j 이관 안전성

이관 가능 여부가 채택 조건(사용자 질의)이므로 안전장치를 명시한다:

1. **모델 등가**: §2는 Neo4j 속성 그래프와 1:1 (label/type/props/identity). 이관 = `UNWIND` 배치 MERGE로 기계적 변환. 이미 `graph_sync_worker`에 Neo4j 드라이버 골격 존재.
2. **config 중립**: 같은 매핑 config로 PG materializer든 Neo4j syncer든 구동 — 스키마 재설계 없는 타깃 전환/병행.
3. **쿼리 계층 국소화**: 추적·조회는 전부 "그래프 쿼리 API"(§6) 뒤에 숨긴다. 재귀 CTE ↔ Cypher 전환 비용이 이 계층 하나에 갇힘.
4. LLM 백본 관점 보너스: PG면 **pgvector**로 그래프 이웃 확장 + 벡터 유사도 하이브리드 검색(GraphRAG 표준 패턴)을 한 저장소에서 — G3에서 옵션.

## 5. 처리량 — 1급 제약

수십만 행 배치 인제션 = 수십만 엣지 MERGE. 규율:
- 1,000행 청킹 벌크 UPSERT(기존 인제션 규율 그대로), outbox 증분 소비
- C-7(전체 재동기화 무제한 로드) 해소를 G1 전제 조건으로 승격
- SLO: 배치 인제션 완료 → 그래프 반영 지연 목표 정의(제안: 배치당 10초 이내, `[GraphLatency]` 계측 상시)

## 6. LLM 액세스 계층 (G2.5) — 백본의 소비 인터페이스

- **도구 API** (REST + MCP 서버 노출): `entity_lookup(label, identity)` · `neighbors(node, depth≤N, types?, time_range?)` · `path(a, b, max_hops)` · `schema_card()` (매핑 config의 label/type/description 요약)
- **서브그래프 직렬화**: 조회 결과를 LLM 컨텍스트 주입용 압축 텍스트 포맷으로(노드/엣지/출처 포함) 정의
- **출처 표기**: 모든 결과 엣지에 provenance 동봉 — "사람 교정" vs "자동 파이프라인" 구분이 LLM 답변 신뢰도의 근거
- **탐색 정책 엔진 (§7.5c) 선행**: 도구 API는 4대 탐색 정책 위에서만 동작 — `node_class` 선언과 정책 적용이 G2.5의 전제 조건(LLM 개방 전 가드레일)

## 7. 불량 추론 네트워크 (G3) — 가치 ③의 설계 골격

- **시드**: 불량 판정 컬럼(데이터 유래) 또는 사용자 마킹(그리드/추적 리포트에서 "불량 시드 지정") → `Defect` 플래그 노드 props.
- **알고리즘**: 시드 기반 **Personalized PageRank**(불량에서 출발한 랜덤워크가 자주 도달하는 개체 = 의심), 공유 이웃 분석(불량 wf들이 공통으로 거친 설비/시간대), 커뮤니티 탐지. **시간 창 스코핑 필수**(불량은 시간적으로 군집) — 알고리즘 입력은 항상 `event_time` 범위로 잘라낸 서브그래프.
- **실행 구조 (v1)**: PG에서 서브그래프 추출 → **Python 분석 워커**(scipy/igraph)로 계산 → 의심 점수를 `analysis` provenance의 노드 props/결과 테이블로 저장 → 추적 리포트에 "의심 랭킹" 탭. 실시간 아닌 배치/온디맨드 잡. (Neo4j GDS 내장 알고리즘은 G4에서 가속 옵션 — 이관 안전성 §4와 같은 논리로 분석 계층도 저장소 중립 유지.)
- LLM 연결: 의심 랭킹이 곧 LLM 도구 응답(`suspect_ranking(seeds, time_range)`)이 됨 — "이 불량들 원인 후보 뽑아줘"가 도구 호출 한 번.

## 7.5 시공간 topology (가치 ④) — 물리 추론의 설계 골격

- **공간 스키마 표준화**: 좌표를 자유 props가 아니라 **규격화된 공간 속성**으로 — `{coord_system, x, y}` (예: `wafer_grid`(cx,cy), `base_grid`(bx,by), `map_physical`). 매핑 config의 노드/엣지 정의에서 좌표 컬럼을 공간 속성으로 선언. 좌표계 정의·변환(회전/면반전)은 **기존 맵 에디터 자산 재사용**(`utils/coordinate_transformer.py`, `physical_wafer_engine.py`) — 좌표 변환 불변식을 그래프가 재발명하지 않는다.
- **시간 topology**: 모든 이벤트 엣지에 `event_time` 필수(§2 모델에 이미 존재)를 넘어, **파생 시간 인접 엣지**를 배치로 구체화 — 예: 같은 Base에서 연속 처리된 개체 간 `PROCESSED_AFTER {gap}` (전이·오염 전파 추론용). 파생 엣지는 `analysis` provenance.
- **공간 분석 (G3 결합)**: 불량 시드의 wafer 좌표 분포 → zonal 패턴 분류(edge ring/center/scratch/random — 반도체 표준 불량 패턴), 설비 좌표 그리드 위 집중도. PPR(관계 축) + 공간 클러스터링(좌표 축) + 시간 창(시간 축)의 3축 교차가 물리 추론의 실체.
- **LLM 도구 연결**: `spatial_pattern(seeds)` → "이 불량들 wafer 위에서 엣지 링 패턴, base 지그 3번 열 집중" 같은 물리 서술을 도구 응답으로.

## 7.5b 상태·이벤트 물화와 2계층 원칙 (사용자 확정 2026-07-25) — 시공간 topology의 데이터 모델

**함수형 온톨로지 (사용자 명명)**: 이벤트 노드는 **다른 노드들을 인풋으로 받는 함수**다. 물화 형태는 공통으로 `(입력 노드들) -[INPUT_TO]-> 함수노드 -[PRODUCED]-> (출력 노드들)`. 함수 타입 2종:

**모든 이벤트는 상태 전이 함수다** (사용자 정정 2026-07-25 — 계측도 예외 아님):

| 함수 타입 | 서명 | 비고 |
|---|---|---|
| **공정 이벤트** | `ProcessEvent: (WaferState_in, EqpState_in) → WaferState_out` | 본딩·증착 등 — 물리 변형 |
| **계측 이벤트** | `MetrologyEvent: (WaferState_in) → (WaferState_out, MetroResult)` | 결과 노드를 **추가로** 산출하며, `WaferState_out`은 **"계측을 1회 거친 상태"임을 내포**(계측 이력이 상태에 누적) — 추후 **실험 관리**에 사용(이 wafer가 몇 번·어떤 계측을 거쳤는지가 상태 계보에서 즉시 판독) |

- wafer의 상태 계보는 공정+계측을 **모두** 포함한 전체 이벤트 폴드가 된다 — "현재 상태"에 계측 이력까지 담겨 실험 설계·비교군 관리의 질의 대상이 됨.
- **MetroResult/Defect 노드**: 계측 로그 로우의 직접 투영(L1 사실). defect이면 공간 속성을 2단 좌표로 가진다 — `wafer_grid`(chip 위치 x,y) + `chip_local`(in-chip x,y). 가치 ④ 공간 스키마의 중첩 좌표계 확장이며, **가치 ③ 불량 추론의 시드가 계측에서 자연 공급**된다(zonal 패턴을 wafer 스케일·chip 스케일 양쪽에서).
- **계층 귀속 주의**: 계측 노드·원시 속성은 L1(로그 사실)이지만, INPUT_TO/PRODUCED로 잇는 상태 연결 엣지와 WaferState 노드 자체는 시간 정렬로 계산되는 **L2 파생**이다(상태 체인이 재파생되면 함께 재해석) — 직접 쓰지 않고 항상 재파생 원칙 동일 적용.

이 인과 체인이 불량 추론(가치 ③)의 전이 경로이자 LLM이 읽는 인과 서사(가치 ①)가 된다.

**2계층 원칙 (확정)** — 파생 그래프에서 "엣지 삭제의 복잡성"을 원천 차단하는 규율:

| 계층 | 내용 | 쓰기 주체 | 수정/삭제 정책 |
|---|---|---|---|
| **L1 사실 계층** | 로그 로우의 직접 투영 — ProcessEvent·Chip·BONDED_FROM 등. 반도체 로그 특성상 사실상 append-only 불변 | materializer (로우 이벤트) | row-ref 스코프 정리 (G1 현행 — retarget/H2-b) |
| **L2 상태 계층** | WaferState/EqpState 노드 + 전이 엣지 — L1 이벤트 체인의 **폴드(fold) 계산 결과**. 각 상태 노드는 계보(`derived_from: [event ids]`)를 기록 | 파생 엔진만 (직접 쓰기 금지) | **삭제하지 않는다 — 재파생한다.** 상류 이벤트 수정/삭제 시 해당 엔티티(wafer 등)의 상태 체인만 **스코프 재파생** (엔티티당 이벤트 수십~수백 개 — 저비용·멱등) |

핵심 문장: **"WaferState는 직접 쓰지 않고 항상 재파생한다."** 얽힌 파생 엣지는 언제든 재계산 가능하므로 수술적 삭제 대상이 아니다. 전체 재구성(과잉) vs 수술적 삭제(불가능)의 양자택일이 아니라 계보 단위 부분 재파생이 정답.

구현 단계: **G3.5 (상태·이벤트 물화)** — EqpState 소스(설비 상태 로그) 데이터 전제가 있어 G3(불량 추론)와 함께 설계.

## 7.5c 정적/동적 노드 분류와 4대 탐색 정책 (사용자 확정 2026-07-25 — 외부 논의 수렴)

사용자가 별도 세션(Gemini)에서 도출한 슈퍼 허브 대응 설계를 스펙으로 수렴한다. 문제: Eqp·Recipe 같은 **공유 마스터 노드는 필연적으로 슈퍼 허브**가 되고, 이를 경유하는 순진한 탐색은 무관한 제품 이력으로 컨텍스트가 범람(cross-talk)하며 그래프가 폭발한다. 해법은 노드의 **이원 분류 + 방향성 탐색 정책**이다.

**노드 분류 (매핑 config 선언 — `node_class` 필수 필드)**:

| 분류 | 정의 | 예시 (현행 label) | 특성 |
|---|---|---|---|
| **동적(dynamic)** | 타임스탬프를 갖고 특정 개체 컨텍스트에 귀속되는 이벤트/인스턴스 | Chip, Wafer, ProcessEvent, MetroResult, WaferState, EqpState, SplitCondition | 시계열로 꼬리를 무는 Sequence 엣지 형성 |
| **정적(static)** | 시간이 흘러도 불변에 가까운 공유 기준 정보(마스터) | Eqp, Base, Recipe, DefectCode, Line, Map | 다수 동적 노드의 in-bound 수렴점 = **슈퍼 허브 후보** |

**4대 탐색 정책 (쿼리 계층 글로벌 룰)** — §4.3 "쿼리 국소화" 원칙에 따라 저장소가 아니라 **그래프 쿼리 API 계층에서 강제**한다 (neighbors/trace/G2.5 도구/G3 서브그래프 추출 전부 동일 적용):

| # | 방향 | 정책 | 역할 |
|---|---|---|---|
| 1 | 동적 → 동적 | 🟢 허용 (깊이 cap 내 무제한) | 메인 스트림(백본) 추적 — 상태 전이·이벤트 체인 |
| 2 | 동적 → 정적 | 🟢 허용 (**1-hop 한정**) | 백본에 로컬 컨텍스트(설비·레시피)를 ROI로 결합 |
| 3 | 정적 → 정적 | 🟢 허용 (**1-hop 한정**) | 마스터 계층 구조(Eqp→Line 등) 판독 |
| 4 | 정적 → 동적 | 🚫 **기본 금지** | 슈퍼 허브 경유 컨텍스트 범람 원천 차단 |

- **정책 4의 예외 — 영향도 분석 모드**: 탐색 **출발 노드가 정적**이면(예: "이 설비를 거친 wafer 이력") S→D 1단계를 허용하되 **시간 창 또는 개수 상한 필터를 강제 동반**한다. 출발 노드의 분류가 곧 탐색 모드를 결정한다(역추적 모드 vs 영향도 모드).
- **2단계 백본→ROI 추출**: 추적(trace)·G3 서브그래프 추출은 ① 정적 엣지를 잠근 채 D→D 백본만 확정 → ② 확정된 백본 노드들에서 D→S 1-hop ROI 결합의 2단계로 수행. 멀티 시드 추적 시 각 시드의 identity를 **컨텍스트 토큰**으로 노드·엣지에 태깅(coloring)해 시드별 경로 격리를 유지한다(trace의 entity group이 이 초기형).
- **EqpState 허브앤스포크 (§7.5b와 접합)**: 동적 Run이 정적 Eqp 마스터에 직결되지 않고 `[Run] →(1:1) [EqpState(시간 슬롯)] →(N:1) [Eqp]`로 잇는다. 효과 — ① 시간 비교 연산 없이 topology만으로 시간대 격리(다른 시각의 wafer는 다른 State 노드에 연결) ② **동시성 판별 = State 노드의 in-bound Run 수 ≥ 2** ③ `NEXT_STATE` 체인으로 직전 슬롯 오염 역추적. EqpState는 L2 파생 계층(재파생 규율 동일).
- **슈퍼 허브 실링(pruning)**: degree가 임계(예: 1,000)를 넘는 노드로의 진입은 쿼리 계층에서 잘라내고 개수만 보고(현행 500-노드 cap의 일반화) — 유래 속성(롤업 카운트)으로 대체 서술.
- **LLM 가드레일 (G2.5 전제)**: `schema_card()`에 label별 `node_class`와 4대 정책을 명시 포함 — LLM이 생성하는 질의가 정책 위에서만 구성되게 하여 쿼리 폭탄(S→D 무한 확장)을 구조적으로 차단.

## 7.6 그래프 보조 교정 (inference-assisted enrichment) — 가치사슬의 순환 완성

사용자 통찰(2026-07-25): **LOT-SLOT-WAFER 매칭 같은 교정 과제 자체를 온톨로지에 올려 추론**하면 구현이 더 원활해진다.

- **순환 구조**: 사람 교정 → `RESOLVED_AS` 엣지 축적 → 그래프가 미해결 항목의 **후보를 추론** → 사람은 확인만 → 다시 그래프 강화. 핵심가치 #1(최소 공수 교정)의 공수가 "타이핑"에서 "확인 클릭"으로 줄어드는 것이 목표.
- **후보 추론 신호** (④의 3축 그대로): ① 시간 근접성 — 본딩 event_time과 wafer 이력 event_time의 근접 ② 관계 일치 — lot/slot 조인 경로 ③ **물리 제약** — 한 wafer는 동시에 한 곳에만 존재(배타 제약 위반 후보 제거), 이미 확정된 이웃 매칭의 패턴(같은 lot의 slot 순서 규칙성 등).
- **잠정 엣지 규율**: 추론 결과는 `SUGGESTED_AS {score, evidence[]}` 엣지에 `inference` provenance로 저장 — **자동 확정 절대 금지**. 사람이 enrichment UI에서 수락하면 `RESOLVED_AS`(user)로 승격, 거절하면 negative 신호로 보존. 미해결 워크리스트 = `RESOLVED_AS 없음` 필터는 불변.
- **Enrichment UI 연결**: 입력창에 후보 추천 리스트(점수+근거 요약 — "이력 시각 3분 차, 동일 lot, 배타 제약 통과") 표시. 기존 참조뷰(수기 SQL)는 유지하되 추론 후보가 1순위 보조로.
- LLM 도구: `match_candidates(rule, decision_key)` — 교정 보조를 LLM 에이전트가 수행하는 경로도 동일 API로 열린다.

## 8. 단계

| 단계 | 내용 | 비고 |
|---|---|---|
| **G1** | 매핑 config 실전화 + PG nodes/edges(인덱스 규율 §2) + 자동 승격 materializer + C-7 해소 + 이슈 #8 동승 | 데모 3종 E2E |
| **G2** | 추적 쿼리 API(k-hop, 시간 범위) + 추적 리포트 UI (그리드 선택 → 추적) | 킬러 유스케이스 + 가치 ② 실증 |
| **G2.5** | LLM 액세스 계층 — **탐색 정책 엔진(§7.5c: node_class 선언 + 4대 룰 + 2단계 백본→ROI)** 선행 + MCP/도구 API + schema_card + 서브그래프 직렬화 | 가치 ① 개방 (정책이 가드레일) |
| **G3** | 불량 추론 네트워크 + 시공간 분석 — 시드 마킹 UX + 분석 워커(PPR·zonal 패턴·시간 인접) + 의심 랭킹 리포트/도구 + **그래프 보조 교정(§7.6 — SUGGESTED_AS 후보 추론 → enrichment UI 추천)** | 가치 ③④ + #1 순환 (공간 스키마는 G1부터) |
| **G4** | Neo4j 병행 타깃(시각화·Cypher 에이전트·GDS 가속) + pgvector 하이브리드 | 옵션 |

## 7.7 키 참조 정합 (2026-07-25 논의 — 사용자 우려에서 출발)

느슨한 비즈니스 키 조인(FK 제약 없음)은 동적 테이블 아키텍처의 태생적 비용 — 한 테이블에서 키가 바뀌면 참조 테이블들이 조용히 어긋난다(map_split 신설과 무관하게 기존 체인 전반의 문제).

- **원칙: identity 키는 관례상 불변** — 키 변경은 사실상 새 엔티티. 정말 바꿔야 하면 전파 보조를 통해서만.
- **매핑 config = 선언된 FK 레지스트리**: `target_identity_from` 선언이 "누가 누구의 키를 참조하는가"의 조인 토폴로지. 참조 무결성 기능의 단일 원천으로 재사용한다.
- **탐지 (1단계 백로그)**: dangling 참조 = 그래프 쿼리 하나("참조 엣지는 있는데 소유 테이블 백킹 로우가 없는 identity 노드"). admin 헬스 지표 + **enrichment 워크리스트로 공급**(끊긴 참조의 재지정 = 핵심가치 #1 흐름).
- **전파 보조 (2단계 백로그)**: 그리드에서 identity 컬럼 수정 시 mapping-summary 역참조로 "N개 테이블 M개 행이 참조 중" 경고 + 일괄 전파 제안(기존 배치 API 재사용).

## 8. 미결(논의 계속)

- k-hop 추적의 기본 깊이·타입 필터 기본값 (v1 리포트 화면 설계와 함께)
- 서브그래프 직렬화 포맷 상세 (G2.5 착수 시)
- **행 삭제 정리 정책 — 방향 확정(§7.5b 전제), 구현 대기**: L1은 DELETE 이벤트에 row-ref 스코프 정리(H2-b와 동일 메커니즘) + 고아 노드 GC(엣지 0 + 원본 로우 부재), L2는 정리 대상 아님(재파생으로 수렴). 신뢰 게이트는 입구(수동 푸시)가 아니라 **provenance 기반 소비 시점 게이트**(자동 materialize + 엣지 출처 표기 — 2026-07-25 사용자 논의로 확정, 구 수동 Graph Sync 버튼은 백필/복구 도구로 존치)
