# 2026-07-25 종합 — 온톨로지 그래프 트랙 가동 + 클라이언트 IA 재편 (아키텍처 전환 요약)

> 이 문서는 2026-07-25 하루에 누적된 대규모 변화를 **사람이 한 번에 따라잡기 위한 종합 요약**입니다.
> 개별 상세 이력: [G1 스토어/materializer는 별도 미기록 — 본 문서가 정본], [H2-b](./20260725_183000_ontology_h2b_empty_target_retarget.md), [뷰어 API](./20260725_193000_graph_viewer_readonly_api.md), [trace API](./20260725_203000_ontology_g2_trace_api.md), [std parser](./20260725_113212_std_parser_fallback_and_workspace_autoprovision.md), [이슈 #7](./20260725_170000_issue7_runtime_table_create.md), [Enrichment v1](./20260725_130000_enrichment_queue_v1_complete.md).
> 관련 커밋(주요): `6da2276`(G1) → `7c40a33`/`d130c65`(QA 수정) → `c63b881`(뷰어 API) → `eea929d`/`f41ca3e`(뷰어 UI) → `d8d109d`(trace API) → `6c0a722`/`83507aa`(trace UI) → `3e599d2`/`387d987`(admin 5탭) → `f90717f`(std parser) → `765c7e5`~`cd3f90c`(듀얼 테마)

## 1. 배경

SSOT §1의 핵심가치 #2(온톨로지/지식그래프)가 이날 **스펙 → 실동 시스템**으로 전환됐다. 동시에 admin 화면의 정보 구조(IA)가 파이프라인 생애주기 축으로 재편되고, 신규 테이블 온보딩이 "config 추가 → 리로드 → 즉시 사용"으로 완결되는 등, 사용자 관점의 시스템 골격이 크게 바뀌었다. 본 문서와 함께 SSOT·architecture 문서 일체를 현행화했다.

## 2. 온톨로지 그래프 트랙 (G1 → 뷰어 → G2, 전부 라이브 가동)

### 2.1 PG 엣지 스토어 (G1)

`server/database/models.py`에 그래프 3테이블 신설. Neo4j 없이 PostgreSQL 안에서 속성 그래프를 구체화(materialize)한다.

```python
class GraphNode(Base):   # (label, identity_key) UNIQUE — 정확 일치 MERGE
    id; label; identity_key; props(JSONB); created_at; updated_at

class GraphEdge(Base):   # (from,type)/(to,type) 인덱스 — k-hop 순회가 인덱스 룩업 연쇄
    id; type; from_node; to_node; props(JSONB)
    source_name; source_row_ref; updated_by; event_time; created_at

class GraphSyncState(Base):  # materializer의 outbox 소비 커서 (id=1 단일 행)
    id; last_outbox_id; updated_at
```

- 생성은 `ensure_graph_tables(engine)`(#7의 info_schema 게이트 + checkfirst 패턴)로, `refresh_dynamic_models`에 동승.
- 엣지 provenance는 **셀 레이어링의 그래프 확장**: `source_name`은 이벤트 발화자가 아니라 **식별 컬럼들의 CellSource winner 중 최저 서열(보수적)**로 날인(QA H1). 재교정 시 `(from_node, type, source_row_ref)` 스코프로 구 타깃 엣지를 정리(QA H2, `_retarget_stale_edges`).

### 2.2 materializer — 수동 동기화에서 outbox 증분 소비로 (자동 승격)

`graph_sync_worker.py`(:8090)의 본체가 **outbox를 증분 소비하는 materializer 루프**로 개편됐다. 인제션·교정되는 모든 로우가 매핑 config에 따라 자동으로 노드/엣지로 승격된다 — 수동 트리거는 더 이상 주 경로가 아니다.

```python
# graph_sync_worker.py — run_graph_materializer_loop() (~:545)
# 자체 keyset 커서(graph_sync_state.last_outbox_id) + LISTEN/NOTIFY
# 배치 본체는 asyncio.to_thread(_run_one_batch)로 격리(이벤트 루프 기아 방지)
# [GraphLatency] batch= rows= nodes= edges= lag_ms= exec_ms=  ← SLO 10s, 실측 lag 162ms
# 배치 내 SYSTEM_RELOAD 감지 시 매핑·테이블 config 핫리로드(이슈 #8 해소)
```

- `POST /api/graph/sync`(수동 버튼)는 **백필/복구 도구**로 재정의: 키셋 청킹 재동기화(C-7 무제한 로드 해소), `"all"` 지원, 테이블당 `batch_refresh_required` 1건.
- Neo4j는 청크 훅 인터페이스(`_neo4j_chunk_hook_factory`)로 보존 — G3 병행 타깃.

### 2.3 매핑 config v2 (`ontology_mapping.json`)

신규 `server/ontology_config.py` 로더/검증. `description`이 **필수**(LLM이 스키마를 읽는 근거), enrichment rule은 `RESOLVED_AS` 엣지로 **자동 승격**된다.

```jsonc
{
  "bonding_log": {
    "node": { "label": "Chip", "identity": "log_id", "props": ["bx","by","cx","cy"] },
    "description": "본딩 설비가 chip 1개를 base에 실장한 이벤트",   // 필수
    "edges": [
      { "type": "BONDED_FROM", "target_label": "Wafer",
        "target_identity_from": ["core_lot","core_slot"],
        "description": "이 chip이 잘려 나온 원판 wafer" }
    ]
  }
}
```

### 2.4 조회 API 5종 + 뷰어·추적 리포트

웹서버(main.py)가 `graph_nodes/edges`를 **직접 조회**(워커 미경유)하는 read-only API:

| API | 용도 |
|---|---|
| `GET /graph/stats` | label/edge_type 카운트 + last_sync (뷰어 첫 화면) |
| `GET /graph/neighbors` | k-hop(1\|2) 서브그래프 — 노드 하드캡 500, truncated |
| `GET /graph/nodes/search` | identity 시작일치 자동완성(LIKE 이스케이프) |
| `POST /graph/trace` | **G2** 멀티 시드 BFS 합집합, depth 1..3, 시간·타입 필터, 하드캡 1000 |
| `GET /graph/mapping-summary` | 로드된 매핑 요약(추적 진입점 활성 판정용) |

클라이언트 신규 엔트리 2종:
- **`graph.html` + `graph_viewer.js`(~927줄)** — 서브그래프 뷰어: 무라이브러리 BFS 동심원 캔버스, 노드 클릭 재중심 탐색, user provenance 엣지 강조, `?label=&identity=` 딥링크.
- **`trace.html` + `trace.js`/`trace_core.js`/`trace_launch.js`** — 추적 리포트: 메인 그리드 선택 행 → identity 조립(서버 `compose_identity` 미러) → 시드 칩·depth·시간범위 → 라벨별 엔티티 그룹 + event_time 타임라인. graph.html과 양방향 크로스링크.

라이브 검증: stats(Chip 1,304 · RESOLVED_AS 5), LOT 중심 20노드 서브그래프, 교정 → `RESOLVED_AS(user)` 실시간 반영, lag 162ms.

## 3. admin 파이프라인 5탭 IA 재편

`admin.js` 전면 재작성(1,433 → 2,437줄). 탭 축을 메커니즘 7탭에서 **파이프라인 생애주기 5탭**으로:

```
Overview(첫 화면, 4카드+최근 이벤트) / File Ingestion(로그+Workspaces) /
Chain(Rules+Outbox 실패+Mappers) / Auto Update(+산출물 인제션 실패 연계) /
Enrichment(규칙+결손 카운트+Queue 딥링크)
```

- Code Editor는 독립 탭 폐지 → **편집 딥링크 공용 뷰**(파일 피커, `#editor=<path>` URL).
- 해시 라우터: 구 탭 별칭(`#outbox→Chain`, `#workspace→File`, `#mapper→Chain`) 호환.
- 각 탭 본문은 생애 단계(현황 → 오류 → 수정/실행) 접이식 섹션 스택. 신규 서버 API 0건.

## 4. 온보딩 완결 — "config 추가 → 리로드 → 즉시 사용"

- **std parser 폴백**(`parsers/std_parser.py`): 커스텀 파이프라인 스크립트가 없어도 `column_types` 헤더 검증 기반 CSV/TSV/TXT 스트리밍 적재.
- **워크스페이스 자동 생성**: table_config 등록 테이블의 `ingestion_workspace/` 폴더 자동 보충 + SYSTEM_RELOAD 런타임 감시 등록.
- **런타임 테이블 물리 CREATE(#7)**: `models.create_missing_dynamic_tables` + 공용 진입점 `refresh_dynamic_models`로 리로드 3경로 전부 배선.
- graph_sync 워커도 SYSTEM_RELOAD를 구독하게 되어(#8, §2.2) 신규 테이블·매핑이 재기동 없이 그래프까지 이어진다.

## 5. 클라이언트 — 듀얼 테마 + 6엔트리

- **듀얼 테마(기본 라이트)**: `tokens.css`(시맨틱 토큰 SSOT) + `theme.js` 토글. 다크 세트는 사용자 피드백으로 심화(`4229d9f`).
- **Vite 엔트리 6종**: `index`(그리드) / `admin`(5탭) / `map_editor` / `enrichment`(컨베이어) / `graph`(뷰어) / `trace`(추적 리포트). client2 JS 합계 ~13,000줄.

## 6. 아키텍처 영향

- **5-프로세스 토폴로지의 의미 변화**: Graph Sync Worker가 "수동 호출 대기 데몬"에서 **체인 워커와 대등한 outbox 소비자(materializer)**가 됐다. outbox는 이제 체인 파생 + 그래프 승격 두 소비자를 가진다(각자 독립 커서/플래그 — chain은 `processed_chain`, graph는 `graph_sync_state.last_outbox_id`).
- **가치 사슬 완결**: 교정(우선순위 승리) → 그래프 반영(provenance 계승) → 객체 중심 추적(trace 리포트)까지 SSOT §1의 사슬이 실동한다.
- **주의(운영)**: outbox 7일 purge보다 materializer가 오래 정지하면 증분이 유실됨 → `POST /api/graph/sync {"table_name":"all"}` 전체 재동기화로 복구(운영 수칙).
- **부분 보존 항목**: 행 DELETE 이벤트의 그래프 정리 정책은 미결(스펙 §8) — DELETE는 materializer가 스킵하며 stale 엣지는 남는다.

## 7. 다음 단계

- G2.5 서브그래프 직렬화 / G3(그래프 시각화 고도화·Neo4j 병행) — 스펙 참조.
- `map_split_registry`(맵 split 서술 관리 테이블 승격) — 지시서 준비됨, client-pm 착수 예정.
- enrichment 실전 규칙 작성(사용자 실 스키마 확보 후).
- admin 대안(온보딩 위저드·규칙 CRUD API) 이관 목록 — `Client_admin_ux_mid_report.md` §E.
