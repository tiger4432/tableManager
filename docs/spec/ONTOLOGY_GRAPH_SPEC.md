# 🕸️ Ontology Knowledge Graph Spec — LLM 백본 지식그래프

> **Status:** 🟠 제안(초안 v0 — 총괄·사용자 논의 중) | **Last-verified:** 2026-07-25 | **Owner:** 총괄 PM
> 상위: [SYSTEM_OVERVIEW (SSOT)](../overview/SYSTEM_OVERVIEW.md) §1 핵심가치 #2 | 구식화 대상: [graph_db_integration_plan.md](./graph_db_integration_plan.md) (Kafka 기반 구상 — 본 스펙이 대체)

## 0. 한 줄 정의

라인에서 수집·교정된 모든 데이터를 **속성 그래프(property graph)로 자동 승격**해, ① 사람에게는 "불량 wafer 선택 → 연관 전체 추적"을, ② **LLM에게는 백본 지식그래프**(도구로 질의 가능한 사실 기반)를 제공한다.

## 1. 확정된 방향 (2026-07-25 사용자 논의)

| 결정 | 내용 |
|---|---|
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

- **엣지 provenance = 레이어링의 그래프 확장**: `source_name`(pipeline_parser/chain/user/…)과 우선순위 규칙(user 최우선)을 셀과 동일하게 적용. 같은 관계를 자동·사람이 다르게 주장하면 사람이 이긴다. LLM 답변의 출처 표기 근거이기도 하다.
- identity: v1은 정확 일치 MERGE. 표기 변형 해석(dirty identity)은 enrichment로 사람이 교정 — 교정 결과가 `RESOLVED_AS` 엣지로 승격.

## 3. 매핑 config — 트랙의 심장 (`ontology_mapping.json` 실전화)

table_config과 같은 사용자 config 패턴. 테이블별:

```jsonc
{
  "bonding_log": {
    "node": { "label": "Chip", "identity": "log_id", "props": ["bx", "by", "cx", "cy"] },
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

## 7. 단계

| 단계 | 내용 | 비고 |
|---|---|---|
| **G1** | 매핑 config 실전화 + PG nodes/edges + 자동 승격 materializer + C-7 해소 + 이슈 #8 동승 | 데모 3종 E2E |
| **G2** | 추적 쿼리 API(k-hop, 시간 범위) + 추적 리포트 UI (그리드 선택 → 추적) | 킬러 유스케이스 완성 |
| **G2.5** | LLM 액세스 계층 — MCP/도구 API + schema_card + 서브그래프 직렬화 | 백본 개방 |
| **G3** | Neo4j 병행 타깃(시각화·Cypher 에이전트) + pgvector 하이브리드 | 옵션 |

## 8. 미결(논의 계속)

- k-hop 추적의 기본 깊이·타입 필터 기본값 (v1 리포트 화면 설계와 함께)
- 서브그래프 직렬화 포맷 상세 (G2.5 착수 시)
- 노드 삭제/행 삭제 시 그래프 정리 정책 (soft-delete 마킹 vs 물리 삭제)
