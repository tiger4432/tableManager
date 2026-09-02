# 🕸️ Ontology Knowledge Graph Spec — LLM 백본 지식그래프

> 🗄️ **부분 대체 — 이 문서의 「구현」 절반은 2026-08-14에 은퇴했습니다** (`2ec78b9` · 판정 [R-2026-08-14-H](../process/LEDGER_RULINGS.md)).
>
> 🔴 **아래 종전 배지의 「G1·뷰어·G2 라이브 가동」은 «거짓이 됐습니다».** 사본을 만들던 파이프라인(추출 → 머티리얼라이즈 → 저장)이 폐기됐습니다: `graph_sync_worker`가 프로세스 스택에서 빠졌고, `graph_nodes`·`graph_edges`·`graph_sync_state`가 **DROP**됐으며(약 841 MB), 진입 라우트 **일곱**이 `410 Gone`을 답합니다. 계약의 정본은 [architecture/backend §2](../architecture/backend.md)의 은퇴 블록입니다.
>
> **절마다 상태가 다릅니다 — 이 표가 정본입니다.**
>
> | 절 | 상태 |
> |---|---|
> | §0 핵심 가치 · §1 방향(**단, 「저장소 = PG 엣지 스토어」 행은 죽음**) | ⚪ **설계 — 살아 있음** |
> | §2 저장소 스키마 · §4 PG 엣지 스토어/Neo4j 이관 · §5·§5.1 처리량 계약 | 🗄️ **죽음** — 표가 DROP됐습니다 |
> | §3 매핑 config 예제 · 로더 리로드 | 🗄️ **죽음** — 읽는 워커가 없습니다(`ontology_mapping.json`은 파일로 살아 있으나 **소비자 0**) |
> | §7 불량 추론망 · §7.5·§7.5b 시공간 위상 · §7.6 추론 보조 보강 · §7.7 키 참조 무결성 | ⚪ **설계 — 살아 있음(애초에 미구현)**. 🔴 **[2026-08-30] §7.5b 의 계측 절반은 「아직 안 했다」가 아니라 「해 보고 «벽»을 만났다」입니다** — 정체 키가 시각을 담을 수 없다(`roleframe._scalar`). 실측은 §7.5b 안의 인용 블록 |
> | **§7.5c 정적/동적 + 4대 탐색 정책** | 🟢 **정책 4 는 강제됩니다 · 정책 1 은 «`backbone_hops > 0` 일 때만»**(2026-08-29). 자리는 원장 walk 이고, 규칙 전문은 [LEDGER_EVIDENCE_SUBGRAPH_SPEC §5.1](./LEDGER_EVIDENCE_SUBGRAPH_SPEC.md) 이 소유합니다. 등급의 근거는 아래 단서 |
> | §7.5d `GET /graph/chip-trace` · §7.5e 재동기화/고아 스윕/mapping-summary | 🗄️ **죽음** — 전부 410이거나 스케줄러에서 탈락 |
> | §8 단계표 G1·G2 행 | 🗄️ **죽음**(그 스택 위에서 배달됨) |
>
> 🔴 **원장은 이 문서의 어휘를 승계하지 않았습니다 — 자기 어휘를 따로 갖고 있습니다.** [CANONICAL_LEDGER_DESIGN §4.2](../architecture/CANONICAL_LEDGER_DESIGN.md)가 SEMI E90/E142에 정박한 개체 타입·술어를 정의하고, `node_class`·`label`·`ontology_mapping.json`을 **한 번도 참조하지 않습니다.** 그래서 「살아 있는 설계」는 **원장 트랙으로 승계할 후보**이지 오늘 도는 것의 서술이 아닙니다.
>
> ✅ **§7.5c에 붙는 단서 — 2026-08-29 에 «선언의 거처»가 실제로 옮겨 앉았고, 정책이 강제되기 시작했습니다.**
> 종전 이 자리는 「선언 채널이 `ontology_mapping.json` 하나뿐이고 그 파일은 은퇴 예정이라,
> 이 절을 살리려면 선언의 거처를 다시 앉히는 결정이 필요하다」였습니다. 그 결정은 **코드가 착지하며 답해졌습니다.**
> ```
> 종전 선언   ontology_mapping.json 의 `node_class: "dynamic"|"static"`   -> 소비자 0. 파싱만 됐다
> 오늘 선언   ledger_config.json 의 entities.<타입>.class: "static"        -> walk 이 «매 요청» 읽는다
> 오늘 정적   quantity@1 · defect_kind@1 · recipe@1  (실측 2026-08-29, 라이브 선언)
> 집행 자리   server/ledger_trace_router.py `_static_types()` · `_static_step_predicates()`
>            -> server/ledger_api/ledger_subgraph.py `subgraph()`
> ```
> 🔴 **이 표시가 이 절이 한 달간 「없는 규칙」으로 읽힌 이유를 끝냅니다.** 판정이 «구현»(`node_class`·
> `ontology_mapping.json`·graph worker)으로 색인돼 있었고 그 구현이 죽자 판정도 안 보였습니다.
>
> **이 문서가 드는 것은 «정책 등급» 하나입니다** — 규칙의 내용·기전·시험은
> [LEDGER_EVIDENCE_SUBGRAPH_SPEC §5.1](./LEDGER_EVIDENCE_SUBGRAPH_SPEC.md) 이 소유하고,
> 판정 자체는 [LEDGER_RULINGS R-2026-08-29-Q](../process/LEDGER_RULINGS.md) 입니다.
> 여기에 규칙을 다시 적지 마십시오 — 2026-08-29 밤에 이 사실의 사본이 «여섯»이었고 그중 «넷»이
> 같은 거짓 문장을 들고 있었습니다.
>
> | 정책 | 오늘 |
> |---|---|
> | 1 · 동적 → 동적 | 🟡 **`backbone_hops > 0` 일 때만.** 이 정책의 유일한 기계가 D→D 걸음을 «떠남 예산»에서 빼는 것인데, `backbone_hops = 0` 이면 걷기가 이 축이 생기기 «전과 한 걸음도 다르지 않습니다». 오늘 켜는 호출자는 넷(`client2/src/rnd_board/main.js` 좌석 선언) |
> | 2 · 동적 → 정적 | ⚪ 걸음은 허용되지만 **「1-hop 한정」은 강제되지 않습니다** — 홉 수는 «예산»(`hops`)이 대신합니다 |
> | 3 · 정적 → 정적 | ⚪ 같은 이유로 1-hop 미강제. 다만 «어느 술어로» 가능한지는 선언에서 유도됩니다 |
> | 4 · 정적 → 동적 | 🟢 **강제됩니다.** 예외(영향도 분석 모드 — 출발이 정적이면 S→D 1단계 허용)는 **만들지 않습니다**: 소유자 판정 [R-2026-08-29-S](../process/LEDGER_RULINGS.md) 「정적노드는 씨앗으로 안씀」이 그 필요를 닫았습니다 |
>
> **후계** — `GET /api/ledger/subgraph` **하나**입니다(walk). 유형 층은 `GET /api/ledger/declaration`, 개체 층은 [guide/LEDGER_GUIDE](../guide/LEDGER_GUIDE.md). 🔴 **[2026-08-28] 종전 이 줄은 `GET /api/ledger/trace` 와 `GET /api/ledger/structure` 를 후계로 대고 있었고 둘 다 «없습니다»** — 은퇴한 페이지에서 또 다른 없는 주소 둘로 보내고 있었습니다.
>
> ---
>
> ~~**Status:** 🟢 Living (2026-07-25 승격 — G1·뷰어·G2 라이브 가동으로 §1~§6 실증됨. §7.x는 G3+ 설계)~~ | **Last-verified:** 2026-08-30 (**§7.5b 계측 절반만** — 물화 시도가 정체 키의 시각 제약에서 멈춘 실측을 등재) · 직전 2026-08-29 밤 (**§7.5c 만** — 정적/동적 분류가 원장 walk 에서 강제되기 시작했고 선언의 거처가 옮겨 앉았다. 다른 절은 아래 날짜 기준 그대로) · 그 직전 2026-08-14 (은퇴 반영) · 그 직전 2026-07-30 (**폐기 형태를 가르치던 세 자리 정정** — `server/config/ontology_mapping.json` 실선언 + `server/ontology_config.py`(`_ALLOWED_NODE_KEYS`·`_normalize_props`) 대조. ① **§3 매핑 예제 전면 교체** — `Chip`/`identity:"log_id"`/`BONDED_FROM→Wafer`/`PLACED_ON→Base`는 `aea4700`이 **셀 체인**으로 대체했다(`CoreCell(core_lot,core_slot,cx,cy)`가 두 로그의 행 노드 · `BONDED_TO→BaseCell` · `TRANSFERRED_TO→DtCell` · `FROM_CORE→Core` · **좌표는 엣지 props가 아니라 identity 안에** · `base←dt`는 파생 · `wafer_id`는 정체가 아니라 속성). 실측 근거(추상 칩에서 17행 붕괴·15행이 다른 `(bx,by)`로 소실 → 셀로 4,432/4,434 생존)와 `identity` 리스트 형·`event_time_column`·`spatial` props 형태를 함께 반영. **`aea4700`은 문서 변경 0건이었고 같은 파일을 고친 `8670e3b`도 이 예제를 건드리지 않았다.** ② **§7.5b `DTEvent` 지위 명시** — 착지한 것은 셀 체인이고 `DTEvent`/`TapeState`는 **G3.5 설계로 미물화**, 셀 체인을 대체하지 않고 그 위에 얹힌다. `dt_eqp` 노드 승격 유보 근거(단일 값 768행 = degree 768 허브) 등재. ③ **§7.5c 동적/정적 예시 정정** — `Chip`·`Base`는 라이브에 없고 `CoreCell`·`BaseCell`·`DtCell`이 정본, `BaseCell`은 마스터가 아니라 셀, 폐기 `Chip` 12,468개는 스윕 대상, `node_class`는 아직 강제되지 않는다. 직전 2026-07-25 최초 검증) | **Owner:** 총괄 PM
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
    "description": "본딩 설비가 코어 셀 1개의 칩을 base 셀에 실장한 이벤트 로그", // ← LLM 그라운딩용 (필수)
    "event_time_column": "eventtime",                        // ← 선택. 엣지 event_time의 실 사건 시각
    "node": {
      "label": "CoreCell",                                   // ← 행 노드는 **셀**이다 (아래 규율)
      "identity": ["core_lot", "core_slot", "cx", "cy"],     // ← 단일 컬럼명 또는 복수 컬럼 리스트
      "node_class": "dynamic",                               // ← §7.5c 정적/동적 분류 (필수 예정)
      "props": [
        { "col": "cx", "spatial": { "coord_system": "wafer_grid", "axis": "x" } },  // ← §7.5 공간 속성
        { "col": "cy", "spatial": { "coord_system": "wafer_grid", "axis": "y" } }   //    (노드 props 전용)
      ]
    },
    "edges": [
      { "type": "BONDED_TO", "target_label": "BaseCell",
        "target_identity_from": ["base_id", "bx", "by"],      // 복합 식별 → "|" 조인 identity
        "props": ["eventtime", "log_id"],
        "description": "이 코어 셀의 칩이 실장된 base 셀. 팬아웃 최대 6은 결함이 아니라 rework다" },
      { "type": "FROM_CORE", "target_label": "Core",
        "target_identity_from": ["core_lot", "core_slot"],
        "description": "이 셀이 속한 코어 웨이퍼 — dt_log가 같은 타입으로 같은 주장을 한다" }
    ]
  }
}
```

> 🔴 **행 노드는 추상 칩이 아니라 셀이다 (`aea4700` 2026-07-30 · 실측 근거).** `bonding_log`·`dt_log` 둘 다 `(core_lot, core_slot, cx, cy)`를 그대로 들고 있으므로 **코어 셀이 조인**입니다. 추상 칩 모델(`Chip`/`log_id`)에서는 **본딩 17행이 붕괴하고 그중 15행이 서로 다른 `(bx,by)`로 뭉개져 base 위치가 소실**됐습니다 — 셀로 두면 4,434 중 4,432가 살아남고 **정확한 중복만** 병합됩니다. 그래서 **좌표는 엣지 props가 아니라 identity 안에** 있습니다.
> - `dt_log`는 같은 `CoreCell` 노드로 수렴하며 `TRANSFERRED_TO → DtCell(tape_lot|tape_slot|tx|ty)` + `FROM_CORE → Core`를 선언합니다. **`base ← dt` 홉은 파생으로 남습니다** — `bonding_log`에 tape 컬럼이 아예 없어 그 홉은 코어 셀을 경유해서만 존재하고, 인덱스 두 홉 1.6ms라 물화할 근거가 없습니다.
> - `Core`의 정체는 **`(core_lot, core_slot)`이고 `wafer_id`는 속성**입니다. `wafer_id`는 `wafer_process`와 80개 코어 중 8개만 조인되는데 `(lot, slot)`은 80/80이고, 값 하나는 깨진 문자열이며 세 코어에서는 모든 공정 행이 사람이 해석한 것과 다른 wafer를 지목합니다 — **정체로 쓸 수 없습니다.**
> - `PERFORMED_ON`(`(lot,slot)`)과 `RESOLVED_AS`(enrichment 자동 승격)는 **재선언하지 않고 재사용**합니다. 새로 생긴 타입은 `BONDED_TO`·`TRANSFERRED_TO`·`FROM_CORE` **셋**입니다.
> - 🗄️ **폐기된 형태**: `Chip`/`identity: "log_id"` · `BONDED_FROM → Wafer` · `PLACED_ON → Base`. `aea4700`이 전부 대체했으나 **그 커밋은 문서를 하나도 고치지 않았고**, 같은 파일을 §7.5d 때문에 다시 편집한 `8670e3b`도 이 예제를 건드리지 않았습니다 — 그래서 이 절이 계속 폐기 형태를 가르치고 있었습니다.

- **enrichment rule 자동 승격**: rule의 `decision_key → target` 정의는 매핑 항목으로 자동 변환(`RESOLVED_AS`) — rule 추가 = 온톨로지 확장.
- `description`은 장식이 아니라 **LLM이 스키마를 읽고 스스로 질의를 구성하는 근거**. 매핑 검증 시 필수 필드.
- 핫리로드 대상(이슈 #7 해소된 `refresh_dynamic_models` 패턴 준용, 이슈 #8 동승).
  ⚠️ **단, 현재 리로드 트리거는 `SYSTEM_RELOAD` outbox 이벤트뿐이다** — 이 파일을 디스크에서 직접 고쳐도 실행 중인 materializer 루프는 구 선언으로 계속 물화한다(라이브 실측 2026-07-30, 열린 결함). 편집 후 `POST /admin/reload-configs`가 필수.
- **`spatial`은 노드 props 전용이다**(2026-07-30 판정). 엣지 props에 선언하면 로더가 **사유와 함께 그 테이블 매핑을 거부**한다 — materializer가 노드 props에서만 `_spatial`을 만들기 때문에 받아주면 "검증은 통과, 반영은 안 됨"이 되고, 이는 미선언 키 거부 규율이 막으려는 무음 사망과 같은 계급이다. 엣지 좌표가 실제로 필요해지면 그때 구현하고 이 거부를 같은 변경에서 지운다.

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

### 5.1 축약 아웃박스 이벤트의 승격 (2026-08-07 OUTBOX-④)

대량 인제션의 outbox 이벤트는 값을 싣지 않고 `row_ids`를 지목한다([event_driven_backend §2.4](../architecture/event_driven_backend.md)). 그래프 승격은 **새 경로를 만들지 않고** 이미 있던 포인터형 경로 `graph_materializer.resync_table(..., row_ids=[...])`로 보낸다.

- **`resync_table`이 인자 셋을 얻었다** — 재동기화 전용이던 함수가 **증분 경로와 공유**되기 때문이다.
  - `updated_by` (기본 `"graph_resync"`) · `event_time` (기본 로우의 `updated_at`): 증분 이벤트는 **누가·언제** 썼는지를 알고 있으므로, 하드코딩된 재동기화 값으로 덮으면 `event_time_column`을 선언하지 않은 테이블의 엣지 provenance와 시각이 **조용히** 바뀐다.
  - `commit_chunks` (기본 `True`): 증분 호출자는 「머티리얼라이즈 + 커서 전진」을 **한 커밋으로** 묶어야 크래시 재생이 안전하다.
- 🔴 **`commit_chunks=False`는 C-7을 뒤집지 않는다 — 크기로 유계이기 때문이다.** C-7이 겨냥한 것은 `resync_table`의 **전체 테이블 모드**(한 호출이 테이블 전량을 훑는다)다. 증분 팔은 호출자 예산으로 묶여 있고, 그 예산은 **그래프 워커 자신의 변경 전 상한**이다 — `GRAPH_BATCH_LIMIT` = 1,000 **행** = `CHUNK_SIZE` 하나. 🔴 **여기에 체인 워커의 `OUTBOX_GROUP_MAX_ROWS`(20,000)를 청구하면 안 된다**: 배치가 20배가 되고, 하필 커밋 없이 도는 팔이다. 예산은 소비자마다 **자기 이전 값**으로 재유도한다.
- 🔴 **축약 이벤트를 묶는 키는 `(table, updated_by, event_time)`이다.** 테이블만으로 묶고 첫 이벤트의 신원을 쓰면 뒤 이벤트 행들이 앞 이벤트의 provenance·시각으로 적재되고, `resync_table`은 멀쩡한 문자열을 받으므로 **아무것도 실패하지 않는다.** 경로 동등성(§증분 vs 재동기화)이 축약에서도 유지되려면 이 키가 필요하다.
- 이벤트가 지목했지만 **이미 삭제된 행**은 로드에 잡히지 않아 승격되지 않는다 — `resync_table`이 늘 그랬던 동작이고, `chain_replay`가 같은 답을 낸다.

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

> 🔴 **[2026-08-30 실측] 계측 절반을 오늘의 어휘로 세우려던 라운드가 «아무것도 선언하지 않고» 멈췄다 — 그 이유가 이 모양이 아직 미물화인 «오늘의» 이유다.**
> 지시서(`task/METROLOGY_NODE_BRIEF.md`)는 위 서명의 **모양만** 가져오고 이름은 오늘의 것(엔티티·어휘·walk)으로 쓰게 했다 — `INPUT_TO`/`PRODUCED` 는 은퇴한 그래프의 철자다. 멈춘 자리는 **엔터티의 정체 키**였다.
> - 🔴 **정체 키는 «시각»을 담을 수 없다.** 검사기는 `server/ledger/roleframe.py` 의 `_scalar` 이고, 엔터티 참조의 `keys.*` 가 전부 여기를 지난다. 받는 것은 **bool · 정수 · 유한 실수 · 문자열** 넷뿐이라 tz-aware `datetime` 은 `invalid_scalar_role` 로 거절된다. ⚠️ **같은 파일에서 시각이 «금지»인 것은 아니다** — `kind: "time"` 인 Role 은 tz-aware `datetime` 을 «요구»한다. 즉 시각은 술어가 나를 수는 있고 **정체가 될 수는 없다**. 🔴 **판정을 강제하는 자리는 이 함수 하나**이고, 선언·문서 어디에도 이 제약이 적혀 있지 않았다.
> - 레인이 필드 «이름»이 아니라 «타입»이 원인임을 2×2 로 갈라 확인했고, 그 자리에서 멈추고 보고했다(지시서의 멈춤 조건 그대로 — 대체 키를 지어내지 않았다). 실측 확인: 라이브 `server/config/ontology/ledger_config.json` 과 `config/sample/ledger_config.json.sample` 둘 다 `metrology` 낱말 **0**.
> - ✅ **그래도 «모양»은 이 데이터에서 참으로 확인됐다** — `process_param_num` 73,275행 기준 「계측 하나 → 결과 여럿」이 성립한다(한 `(웨이퍼, step, eqp, 시각)` 묶음의 3분의 2가 파라미터를 여럿 싣는다). 그리고 **공유되는 것과 사건이 갈라진다**: `(step, eqp)` **63**(웨이퍼를 넘어 공유 — 분모가 되는 쪽) 대 `(웨이퍼, step, eqp, 시각)` **24,070**(웨이퍼마다 하나 — 사건인 쪽). 앞의 것은 시각이 키에 없어 이 벽에 걸리지 않는다.
> - ⚠️ **이 문단은 「무엇을 하라」가 아니다.** `_scalar` 를 넓힐지, 사건 쪽을 다르게 키잡을지, 분모 쪽만 먼저 세울지는 **총괄 판정**이고 여기 적지 않는다. 여기 적는 것은 「왜 아직 없나」뿐이다.

**DT(Die Transfer)/Tape 계층 (사용자 도메인 공개 2026-07-26)** — 실제 물류 체인에는 코어와 본딩 사이에 **테이프 계층**이 있다: 여러 코어의 칩을 TAPE 위에 한데 모아두고(DT 공정) 본딩은 테이프에서 집는다. 따라서:
- **bonding_log의 core_lot/slot은 실제로는 DT(테이프) lot/slot**이다. 칩의 진짜 출신 코어는 `테이프 좌표 × DT 맵(영역→코어)` 또는 칩 단위 DT 로그로 해석한다.
- 원천 2종: **DT 로그**(칩 단위 — 코어 좌표↔테이프 좌표 대응) + **DT 맵**(테이프 lot|slot 자체 맵 — 영역→코어 귀속).
- 함수형 온톨로지 확장(**G3.5 설계 — 아직 물화되지 않음**): `DTEvent: (WaferState_in, TapeState_in) → (WaferState_out, TapeState_out)` — Tape는 동적 노드. 이 이벤트 노드 형태는 L2 상태 계층과 함께 오는 것이라 **현행 그래프에는 없습니다.**
  > ✅ **G1에 실제로 착지한 것은 「셀 체인」입니다 (`aea4700` 2026-07-30, §3 참조)** — `BaseCell ←BONDED_TO— CoreCell —TRANSFERRED_TO→ DtCell` + `CoreCell —FROM_CORE→ Core`. 즉 위 서술의 `Base ← bonding ← TapePos ← DT ← Core` 2단 전사는 **`DTEvent` 노드 없이 셀 정체(coordinates-in-identity)만으로** 성립했고, 그것이 §7.5d 칩 추적의 형상입니다. `DTEvent`/`TapeState`는 여전히 G3.5의 상태 물화 설계로 남아 있으며 **셀 체인을 대체하는 것이 아니라 그 위에 얹히는 계층**입니다 — 둘을 같은 것으로 읽지 마십시오.
  > ⚠️ 그리고 **`dt_eqp`는 엣지 속성이고 `Eqp` 노드로 승격하지 않습니다**(결정 유보) — 768행 전부가 단일 값이라 노드로 만들면 degree 768 허브 하나가 생기고, 정책 엔진(§7.5c)이 없는 상태에서 그 허브는 **무관한 칩 768개로 되확장**됩니다.
- 좌표 프레임: defect/EDS는 core frame, DT 맵·bonding 좌표는 tape frame — 프레임 간 다리는 변환이 아니라 **DT 로그 조인**(칩 단위 대응이 데이터로 존재).

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
| **동적(dynamic)** | 타임스탬프를 갖고 특정 개체 컨텍스트에 귀속되는 이벤트/인스턴스 | **CoreCell · BaseCell · DtCell**(라이브 정본 — `aea4700`), Core, Wafer, ProcessEvent, MetroResult, SplitCondition, (설계) WaferState·EqpState | 시계열로 꼬리를 무는 Sequence 엣지 형성 |
| **정적(static)** | 시간이 흘러도 불변에 가까운 공유 기준 정보(마스터) | Eqp, Recipe, Knob, DefectCode, Line, Map | 다수 동적 노드의 in-bound 수렴점 = **슈퍼 허브 후보** |

> 🗄️ **종전 예시의 `Chip`·`Base`는 라이브에 없습니다.** `aea4700`이 `Chip`(추상 칩)을 **`CoreCell`**로, `Base`(지그 마스터)를 **`BaseCell`**(`base_id|bx|by` — base 상의 자리)로 대체했습니다. `BaseCell`을 정적으로 읽으면 분류가 틀립니다 — 그것은 마스터가 아니라 **좌표를 든 셀**입니다. 폐기된 `Chip` 노드 **12,468개**가 라이브에 잔존하며 §7.5e ②의 스윕 대상입니다.
> ⚠️ **`node_class`라는 «필드»는 여전히 강제되지 않습니다 — 그 필드를 읽는 소비자가 0입니다.** 위 표는 그 채널에 대해서는 **선언 현황이 아니라 분류 기준**입니다.
>
> ✅ **그러나 «분류 자체»는 2026-08-29 부터 다른 자리에서 강제됩니다.** 옮겨 앉은 곳은 원장 선언이고, 낱말이 다릅니다:
> ```
> 여기(죽은 채널)   ontology_mapping.json 의 node_class: "dynamic" | "static"
> 오늘(사는 채널)   ledger_config.json 의 entities.<타입>.class: "static"
>                  (「dynamic」을 «적지 않습니다» — class 가 없으면 dynamic 입니다. 기본이 오늘 동작이라야 하기 때문)
> 오늘 정적 셋      quantity@1 · defect_kind@1 · recipe@1        실측 2026-08-29 밤, 라이브 «및 .sample» 동일
> 강제 자리         ledger_trace_router._static_types() / _static_step_predicates()
>                  -> ledger_subgraph.subgraph()
> ```
> 🔴 **이 절이 예고한 「슈퍼 허브 경유 컨텍스트 범람」은 관측됐습니다** — `defect_kind` 는 원자 103,841 개를 구별되는 목적어 «하나»에 걸고 있고, 정책 4 를 인출 «후» 필터로 적었을 때 걷기가 씨앗에서 두 홉 거리에서 죽었습니다. 그 실측과 규칙의 기전·시험은 [LEDGER_EVIDENCE_SUBGRAPH_SPEC §5.1](./LEDGER_EVIDENCE_SUBGRAPH_SPEC.md) 이 소유합니다 — **여기 옮겨 적지 마십시오.**

**4대 탐색 정책 (쿼리 계층 글로벌 룰)** — §4.3 "쿼리 국소화" 원칙에 따라 저장소가 아니라 **그래프 쿼리 API 계층에서 강제**한다:

> 🔴 **[2026-09-02 · 읽는 자리에 다는 표시] 이 표는 «2026-07-25 설계»이고, 오늘 강제되는 것과
> 다릅니다.** 이 절의 등급은 문서 머리(§Status 표)에 이미 적혀 있는데, **검색으로 여기 도착한
> 사람은 그 표를 안 봅니다** — 그래서 표시를 여기에도 답니다.
>
> ```
> 🗄️ 믿지 말 것    · 강제 지점의 이름(neighbors · trace · G2.5 도구 · G3 추출) -- 전부 은퇴한 라우트다
>                  · 정책 1 의 「무제한」   -> 오늘은 `backbone_hops > 0` 일 때만 그렇다 (기본 0)
>                  · 정책 2·3 의 「1-hop 한정」 -> 그 캡은 «강제되지 않는다». `hops` 가 대신 든다
>                  · 정책 4 의 «예외»(영향도 분석 모드) -> 소유자 판정 R-2026-08-29-S 로 «두지 않기»로 했다
> ✅ 살아남는 생각  · 정적/동적 이분법 그 자체 -- 오늘은 선언의 `class` 가 정한다
>                  · 「허브 범람은 «걸음을 거절»해서 막는다」 -- 감쇠가 아니라 거절
>                  · 뜻이 다른 걸음에는 «둘째 예산»을 준다
>       -> 지금 «어디» 있나: 강제는 `ledger_trace_router._static_types()` /
>          `_static_step_predicates()` → `ledger_subgraph.subgraph()` 이고,
>          «규칙의 정본»은 [LEDGER_EVIDENCE_SUBGRAPH_SPEC §5.1](./LEDGER_EVIDENCE_SUBGRAPH_SPEC.md) 하나다
> ```
>
> 🔴 **그리고 이 표에 «없는 규칙»이 하나 더 돕니다** — **인접 반전 금지**(방금 거꾸로 타고 올라온
> 술어로 다시 내려가지 않는다, 2026-08-29). 이 표는 방향 조합 «넷»을 다 세었으므로 **완전해
> 보이는데**, 그 규칙은 방향의 축이 아니라 «직전 걸음»의 축이라 여기에 자리가 없습니다.
> 실측으로 그것이 돌려주던 발견 199 중 189 를 걷어냈습니다 — 이 표만 읽고 「오늘 도는 규칙을
> 다 안다」고 결론 내면 그 하나를 통째로 못 봅니다.

| # | 방향 | 정책 (2026-07-25 설계) | 역할 |
|---|---|---|---|
| 1 | 동적 → 동적 | 🟢 허용 (깊이 cap 내 무제한) | 메인 스트림(백본) 추적 — 상태 전이·이벤트 체인 |
| 2 | 동적 → 정적 | 🟢 허용 (**1-hop 한정**) | 백본에 로컬 컨텍스트(설비·레시피)를 ROI로 결합 |
| 3 | 정적 → 정적 | 🟢 허용 (**1-hop 한정**) | 마스터 계층 구조(Eqp→Line 등) 판독 |
| 4 | 정적 → 동적 | 🚫 **기본 금지** | 슈퍼 허브 경유 컨텍스트 범람 원천 차단 |

- 🗄️ ~~**정책 4의 예외 — 영향도 분석 모드**: 탐색 **출발 노드가 정적**이면(예: "이 설비를 거친 wafer 이력") S→D 1단계를 허용하되 **시간 창 또는 개수 상한 필터를 강제 동반**한다. 출발 노드의 분류가 곧 탐색 모드를 결정한다(역추적 모드 vs 영향도 모드).~~ **[2026-08-29 소유자 판정 R-2026-08-29-S 로 «두지 않기»로 했다.]** 이 예외는 구현되지 않았고 앞으로도 안 만든다 — 판정의 정본은 [LEDGER_RULINGS](../process/LEDGER_RULINGS.md).
- **2단계 백본→ROI 추출**: 추적(trace)·G3 서브그래프 추출은 ① 정적 엣지를 잠근 채 D→D 백본만 확정 → ② 확정된 백본 노드들에서 D→S 1-hop ROI 결합의 2단계로 수행. 멀티 시드 추적 시 각 시드의 identity를 **컨텍스트 토큰**으로 노드·엣지에 태깅(coloring)해 시드별 경로 격리를 유지한다(trace의 entity group이 이 초기형).
- **EqpState 허브앤스포크 (§7.5b와 접합)**: 동적 Run이 정적 Eqp 마스터에 직결되지 않고 `[Run] →(1:1) [EqpState(시간 슬롯)] →(N:1) [Eqp]`로 잇는다. 효과 — ① 시간 비교 연산 없이 topology만으로 시간대 격리(다른 시각의 wafer는 다른 State 노드에 연결) ② **동시성 판별 = State 노드의 in-bound Run 수 ≥ 2** ③ `NEXT_STATE` 체인으로 직전 슬롯 오염 역추적. EqpState는 L2 파생 계층(재파생 규율 동일).
- **슈퍼 허브 실링(pruning)**: degree가 임계(예: 1,000)를 넘는 노드로의 진입은 쿼리 계층에서 잘라내고 개수만 보고(현행 500-노드 cap의 일반화) — 유래 속성(롤업 카운트)으로 대체 서술.
- **LLM 가드레일 (G2.5 전제)**: `schema_card()`에 label별 `node_class`와 4대 정책을 명시 포함 — LLM이 생성하는 질의가 정책 위에서만 구성되게 하여 쿼리 폭탄(S→D 무한 확장)을 구조적으로 차단.

## 7.5d 칩 추적 API — 웨이퍼 스코프 고정 형상 (사용자 확정 2026-07-30)

> "wafer 컨텍스트 지정해서 추적해. 모든 노드를 하지말고" — **웨이퍼는 확장할 허브가 아니라 스코프다.**

`GET /graph/chip-trace?identity=<CoreCell identity>` — 칩 1개의 이력. **BFS가 아니다.**

**BFS로는 도달할 수 없음을 실측으로 확인**: 엣지 타입 필터로 `Core -FROM_CORE->`를 막으면 홍수가 **더 커진다**(1,341 → 11,549 노드) — Eqp(degree 10,284)·Wafer로 우회하기 때문. 기존 `POST /graph/trace`는 같은 시드에서 **depth 2에 이미 1,000 노드 캡을 태우고 그중 994개가 형제 CoreCell**이다(라이브 실측 2026-07-30). 그래서 답은 **경계가 정해진 타입 질의 2개**이고, depth 파라미터는 **노출하지 않는다**.

**형상 (3개 다리)**

| 다리 | 경로 | 규율 |
|---|---|---|
| ① 칩 자신 | `CoreCell -BONDED_TO-> BaseCell` · `-TRANSFERRED_TO-> DtCell` | 스코프를 벗어나는 **유일한** 자리 — 시드 셀의 직접 목적지가 곧 그 칩의 이력이다. **형제 셀은 절대 포함하지 않는다** |
| ② 웨이퍼 | `CoreCell -FROM_CORE-> Core` ← `ProcessEvent -PERFORMED_ON-` | 스코프 확정은 **DISTINCT**로 — `LIMIT 1`은 조용한 승자 선택이다 |
| ③ 잎 | `ProcessEvent -USED_KNOB/USED_RECIPE/EXECUTED_BY->` | **되확장 금지**(결정 ②·정책 4). 정책 엔진(G2.5)이 없으므로 **질의 형상이 강제**한다 |

**상태 어휘 (홉마다 하나, 빈 홉 금지)** — `recorded` / `none_recorded`(선언은 있고 행이 없음) / `not_declared`(매핑이 그 (type,target)을 더는 선언하지 않음 — config 이동을 `none_recorded`로 위장하지 않기 위한 별도 이름) / `mapping_unavailable`(**선언을 읽지 못했다** — 아래) / `not_reached`(**묻지 않았다** — 아래) / `scope_unresolved`(Core 주장이 0개 또는 2개 이상, **또는 그 다리가 잘렸다** — 추측하지 않고 칩 절반만 답하고 후보를 보고). 잘림은 상태가 아니라 다리별 `truncated`+`capped_at` 플래그.

**어휘가 둘 늘어난 이유 (2026-07-30 검수 실측)** — 셋 다 "같은 빈칸, 다른 사실"이라는 같은 계급이다.

- **`mapping_unavailable` — "읽지 못했다"는 "옮겨갔다"가 아니다.** 매핑 파일이 저장되는 순간에 요청이 들어오면 `json.load`가 예외를 내고 로더는 `{}`를 돌려주므로, 선언 집합이 enrichment 승격분으로 **쪼그라든 채 200이 나가고 모든 다리가 `not_declared`**를 말한다 — `graph_edges`에 그 칩의 `BONDED_TO` 엣지가 지금 들어 있는데도. 이 창은 실재한다(우리 config writer는 temp+rename이 아니라 평범한 `open(w)`다). 그래서 응답에 **`declaration: {status, path, exists, rejected[]}`**를 싣고, 선언이 깨끗하게 로드되지 않았을 때는 **`not_declared`만** `mapping_unavailable`로 강등한다. `recorded`·`none_recorded`는 실제로 읽은 행에서 나온 결론이라 강등하지 않는다 — 강등 범위를 넓히면 알고 있는 것까지 모른다고 말하게 된다. 파일 **부재**도 degraded다(엣지가 있는 시스템에서 선언 파일이 사라진 것은 온톨로지 결정이 아니라 config 사고다). 503으로 거부하지 않는 이유: 아직 참인 절반(엣지는 있고 걸음은 계산된다)을 함께 버리게 되고, 이 엔드포인트의 전제가 **다리별 닫힌 어휘**이므로 "모른다"의 자리는 그 어휘 안이다.
- **`not_reached` — 앵커가 죽은 다리 뒤에서 `none_recorded`를 말하면 안 된다.** `PERFORMED_ON`을 rename하면 `events`는 옳게 `not_declared`를 말하지만, 잎 다리들은 앵커가 빈 채 `USED_KNOB: none_recorded, count 0`을 말했다 — knob 질의를 **한 번도 하지 않고** "이 웨이퍼는 knob을 쓰지 않았다"고 주장한 것. 앵커가 `not_declared`/`mapping_unavailable`이면 `not_reached` + `blocked_by`를 말한다. 앵커가 `none_recorded`일 때는 그대로 `none_recorded`다 — **이벤트가 0개면 이벤트 경유 knob도 0개**라는 것은 건전한 추론이다.
- **잘린 스코프 다리는 웨이퍼를 확정하지 않는다.** 다리는 `cap+1`을 `(identity_key, edge id)` 순으로 가져오므로, 한 Core로 가는 주장 201개가 버퍼를 채우면 다른 Core로 가는 주장은 **한 개도 읽히지 않는다** — 길이 1, 스코프 "확정", 웨이퍼 절반이 **틀린 코어**로 계산된다. 이 설계가 거부하는 `LIMIT 1` 승자 선택이 다른 길로 들어온 것이라, `truncated`가 필수 연접이다.

**모든 홉이 사건 속성을 들고 온다**(`edges[].props`) — `eventtime`·`dt_eqp`·`log_id`. 한 칩의 `BONDED_TO` 팬아웃(최대 6)은 **결함이 아니라 시간에 걸친 rework**이므로(실측 `LOT-A|05|13|5` = 07-25 / 07-27 / 07-29) 접지 않고 전부 돌려주며, 시각 없이는 그 순서가 읽히지 않는다. `count`(주장 수)와 `node_ids`(개체 수)는 **의도적으로 다르다** — 라이브 2,687개 셀이 같은 Core에 대해 복수 `FROM_CORE` 엣지(소스 파일별)를 갖는다.

**실측 (라이브, 2026-07-30)** — 시드 `LOT-A|05|13|5`: **234 노드 / 694 엣지, 57 ms**(핸들러), 무관 노드 0. 대조: 같은 시드의 `/graph/trace` depth 2 = 1,000 노드(캡 잘림) 중 994개가 남의 칩.

## 7.5e 선언 변경의 전파와 잔여물 정리 (2026-07-30 확정)

선언(`ontology_mapping.json`)을 고치는 순간 세 가지가 어긋날 수 있고, 셋은 서로 다른 층에 있다. **하나의 규칙이 셋 모두를 지배한다: 깨끗하게 로드되지 않은 선언은 무엇에 대해서도 권위가 없다.**

### ① 재동기화는 자기가 쓴 선언을 알린다 (`SYSTEM_RELOAD`)

`execute_manual_sync`는 매 호출마다 파일을 다시 읽지만, materializer 루프는 **자기 메모리 사본**을 들고 있고 그 사본은 outbox 배치 안에 `SYSTEM_RELOAD`가 들어올 때만 교체된다(이슈 #8). 그래서 "매핑 고치고 재동기화했다"가 **루프를 옛 선언에 남겨 두었다** — 라이브 실측 2026-07-30: 40분, 그리고 파일에서 사라진 라벨로 노드가 계속 생성됐다(`Chip` 노드 25개, 08:06:02~08:46:03, 파일 mtime 08:05).

그래서 재동기화가 끝나면 `SYSTEM_RELOAD`를 **직접 발행**한다. 새 지레를 만들지 않고 `/admin/reload-configs`가 쓰는 바로 그 행을 쓴다 — 운영자가 손으로 눌러야 했던 것이 그것이고, 두 경로가 하나의 기계장치로 수렴한다. 매핑이 없는 테이블을 재동기화한 경우(선언을 지우고 돌린 경우)에도 발행한다 — 같은 staleness다. 없는 테이블 이름으로 온 400은 발행하지 않는다(읽어서 반영된 것이 없다).

- **남는 창은 "재동기화가 걸리는 시간"이다.** `POST /api/graph/sync`는 즉시 `accepted`를 돌려주고 실제 재동기화는 백그라운드에서 돈다. 알림은 **끝났을 때** 나가므로, 그 사이에 들어온 로우는 여전히 옛 선언으로 물화된다. 격리 실측: bonding_log 전량 재동기화 4초. 40분이 4초가 된 것이고 0초는 아니다.
- **검증 계기는 노드 라벨이다, 엣지 타입이 아니다.** 폐기된 엣지 타입은 바로 그 재동기화의 `_retarget_stale_edges`가 row-ref 스코프로 지워 버리므로 "mtime 이후에 만들어진 폐기 엣지 타입 없음"은 **결함이 있어도 깨끗하게 나온다**. 폐기된 **노드 라벨**에는 지우는 주체가 아예 없다(그것이 아래 ②의 존재 이유) — 그래서 그것만이 살아남아 측정된다.

### ② 고아 노드 스윕 — 전파는 옳고 정리가 붙어 있지 않았다

`_retarget_stale_edges`는 **엣지**를 지운다. 엣지가 떠난 뒤의 **노드**를 지우는 코드는 어디에도 없었다. 따라서 라벨 폐기만의 문제가 아니라 **정체를 바꾸는 셀 편집마다 노드 한 개가 샌다** — 랏 이름을 `LOT-A`에서 `LOT-B`로 교정하면 엣지는 충실히 재조준되고 `Core(LOT-A|05)`는 영원히 남는다. 라이브 실측 2026-07-30: 재동기화를 반복해도 살아남는 degree-0 노드 12,761개.

**고아의 정의 (두 조건 모두)** ① 엣지가 0개 ② **현재 어떤 매핑도 그 `(label, identity_key)`를 생산할 수 없다.** ②가 안전의 근거다 — "엣지 0개"만으로는 고아가 아니다(`SplitCondition`은 평균 degree 0.2이고, 라이브의 degree-0 135개 중 **124개는 현재 `map_split_registry`가 그대로 생산하는 살아 있는 어휘**다. degree-0 스윕은 DOE 어휘를 통째로 지운다). 생산 가능성은 materializer가 쓰는 것과 **같은 `compose_identity`**로 판정한다 — 정체 구현이 둘로 갈리는 것이 이 저장소가 좌표 변환에서 두 번 치른 값이다.

**안전 4겹** — 생산 가능성 · **라벨별 예산 가드**(인구의 절반 초과를 잃는 라벨은 삭제가 아니라 **거절**, `min_population` 미만 라벨은 비율 검사 면제) · **선언 청결 선행조건**(아래 ③) · 되돌림 가능성(노드는 RDB 파생이므로 재동기화가 있어야 할 것을 되살린다 — 단 무한하지 않다. 어떤 로우도 생산하지 않는 정체는 돌아오지 않고, 그것이 곧 스윕 대상이다).

**전량이 아니라 라벨별로.** 거절된 라벨이 나머지를 인질로 잡으면 안 된다 — 폐기된 `Chip` 12,468개가 편집당 새는 노드를 영구히 막게 된다. 그리고 매 주기 **가져간 것과 거절한 것을 개수와 함께** 로그에 남긴다: 건너뛴 집합이 안 보이는 스윕은 "할 일 없음"으로 읽힌다.

**어디서 도는가**: auto-update 스케줄러 틱(`run_auto_update.maybe_sweep_graph_orphans`) — 수집기가 아니라 **유지보수 작업**이고 근거는 `config_backup`과 같다(수집기는 테이블별로 `raws/`에 CSV를 쓰는 것이고, 아무것도 못 내놓은 수집기는 이제 설계상 FAIL이다). 끄는 노브 `GRAPH_ORPHAN_SWEEP_ENABLED=false`. 운영자 문은 `server/scripts/graph_orphan_sweep.py`(dry run 기본, `--apply`는 격리 밖에서 `--allow-production` 필요, dry run은 읽기 전용이므로 어디서나 허용).

### ③ 거부된 매핑은 표면에 올린다 — 그리고 그것이 ②의 선행조건이다

로더의 계약은 "무효 테이블은 로깅 후 스킵"이다. 그 스킵이 로그에만 있으면 **컬럼 하나를 rename한 순간 그 테이블의 온톨로지가 통째로 사라지고 표면에는 아무 것도 안 나온다** — 성공한 매핑 개수만 보면 "안 늘었다"와 "죽었다"가 구별되지 않는다. 그래서 `GET /graph/mapping-summary`가 **`rejected[{scope, table, reason}]`·`rejected_count`·`source{path, exists}`**를 성공 목록과 **같은 응답**에 싣는다(새 엔드포인트가 아니라 이미 조회하는 응답에 태우는 자리 — PRIMITIVES §3). `scope`는 `table`(그 테이블만 스킵) · `file`(파일이 안 읽힘, 또는 v1 형식이라 v2 매핑이 0개) · `enrichment`(RESOLVED_AS 자동 승격이 죽음).

**정상 상태에서는 반드시 비어 있어야 한다** — 늘 뭔가 들어 있는 사유 목록은 곧 무시당한다. 파일 부재는 거부가 아니라 부재이므로 `source.exists`로만 말한다.

🔴 **그리고 ②는 이것 없이 안전하지 않다.** rename으로 한 테이블 매핑이 죽으면 그 테이블이 생산하던 **모든 라벨이 생산 불가로 보인다.** 예산 가드는 큰 라벨을 막지만 `min_population` 미만 라벨은 **막지 못한다**. 그래서 스윕은 선언에 거부가 하나라도 있으면 **전체를 거절**한다(`graph_orphans.declaration_blockers`). 같은 규칙이 §7.5d의 `mapping_unavailable`에도 걸린다 — **소비자는 둘, 규칙은 하나**다.

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
  - **실증(2026-07-30, 격리)**: bonding_log 로우 8개를 지우자 그 로우들이 주장한 엣지 **16개가 그대로 남았고**, 남은 엣지가 폐기 라벨 노드 8개를 살려 두어 §7.5e ②의 스윕도 손대지 못했다. 가설이 아니라 몇 초 만에 재현되는 상태다.
- 🔴 **선언에서 빠진 테이블의 엣지는 어떤 경로로도 정리되지 않는다 (신규, 2026-07-30 라이브 실측)**: 매핑에서 테이블을 빼면 `resync_table`이 즉시 반환하므로 `_retarget_stale_edges`가 **영원히 돌지 않고**, 그 엣지들은 노드에 degree를 주므로 고아 스윕도 대상으로 잡지 못한다. 라이브 잔존 — `DEFINED_IN` 14개(transfer_plan_doe) · `PLANS_USE` 8개(transfer_plan_doe) · `ON_TARGET` 5개(transfer_plan), 합 27개가 `Wafer` 노드 8개와 `ExperimentPlan` 라벨 전체(7개)를 붙잡고 있다. 정리하려면 "선언에서 사라진 테이블의 row-ref를 스코프로 잡는" 한 걸음이 필요하고, 그것은 위 삭제 정책과 같은 라운드에 속한다.
- **엣지 유일 키에 `source_row_ref`를 넣을 것인가 (검수 제안, 2026-07-30 실측 완료 — 마이그레이션 필요)**: 현재 키 `(from_node, type, to_node, source_name)`은 `aea4700` 이후 좌표가 노드 정체로, `eventtime`/`log_id`가 **엣지 props**로 옮겨간 상태를 담지 못한다. 라이브 실측 — 같은 base 셀로 가는 rework 2건이 겹치는 쌍이 **7개** 있고, 그 7개는 **source_name이 다르다는 이유만으로** 살아 있다(같은 CSV에 들어오면 한 건이 사라진다). 새 키의 성장은 BONDED_TO +117 · FROM_CORE +136(전체 66,109 대비 +0.4%)이고, 늘어나는 117건은 **매핑된 모든 컬럼에서 형제와 완전히 동일한 중복 로우**(bonding_log에 business_key가 2번 나오는 로우 117개 — 이 자체가 인제션 층의 별도 결함이다). `event_time`은 대안이 못 된다: 설계상 NULL이 정상 값이고(선언 컬럼 파싱 실패 = 시각 미상) PG 유일 인덱스에서 NULL은 서로 충돌하지 않아 **현재 주석이 `source_name nullable=False`로 막아 둔 바로 그 우회로가 다시 열린다**. 조건 — `source_row_ref`를 같은 마이그레이션에서 `nullable=False`로 승격(라이브 NULL 0건이므로 백필은 비어 있다)하고, `on_conflict_do_update`의 `source_row_ref` set 항목을 제거(충돌 타깃에 들어가므로 no-op).
- **`source_name`만 다른 중복 엣지**(board 9b): 라이브 잔여 — `FROM_CORE` 2,695 triple / 3,948 surplus · `BONDED_TO` 7 triple / 7 surplus. 위 유일 키 논의와 같은 라운드에서 함께 판정한다.
