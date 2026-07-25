# 보고서: 아키텍처 문서 대청소 (2026-07-25)

발신: doc-keeper / 수신: 총괄 PM
목표: 오늘 하루의 대규모 변화(온톨로지 그래프 트랙·admin 5탭 IA·온보딩 완결·듀얼 테마 6엔트리)를 문서가 정확히 따라잡아, **SYSTEM_OVERVIEW 하나만 읽어도 현행 파악 가능**한 상태. 코드·config 무수정, 커밋 안 함(총괄 검수 후).

---

## 0. SSOT(SYSTEM_OVERVIEW.md) 변경 요지 — 커밋 전 검토용 diff 요약

| 위치 | Before | After |
|---|---|---|
| 헤더 | Last-verified 2026-07-24 | 2026-07-25 |
| §2 다이어그램 | GRAPH는 API의 `/api/graph/sync` 포워드만 받음 | `GRAPH <-->\|증분 소비\| OUTBOX` + `GRAPH -->\|graph_nodes/edges\| DB` 추가, `/api/graph/sync`는 "백필"로 라벨링 |
| §2 프로세스 표 | Graph Sync Worker = "Neo4j 또는 virtual_graph.json 동기화", 상세 링크 graph_db_integration_plan | **materializer** — outbox 증분 소비→PG 엣지 스토어 자동 승격(keyset 커서·SYSTEM_RELOAD 구독), 수동 sync=백필 도구, Neo4j=G3 청크 훅. 링크 ONTOLOGY_GRAPH_SPEC + event_driven_backend §4 |
| §2 프로세스 표 | main.py 3,036줄 / Watcher 서술에 std parser 없음 | ~3,650줄(+`/graph/*` 직접 서빙 명기) / Watcher에 **std parser 폴백** 명기, Chain에 SLO 100ms 명기 |
| §3 클라이언트 | "진입점 4개" 문장 나열, ~10,300줄 | **6엔트리 표**(index/admin 5탭/map_editor/enrichment/graph/trace), ~13,000줄, 듀얼 테마(기본 라이트) 항목 추가 |
| §4 모델 표 | 그래프 모델 없음. SOURCE_PRIORITY 4종 | `GraphNode/GraphEdge/GraphSyncState` 행 추가. `chain_ingestion:4` 등재 + `resolve_priority_map` 단일 원천 명기 |
| §5 설정 | ontology_mapping = "node_label, relationships"(v1 서술), enrichment_rules 행 없음 | **v2 서술**(node/edges·description 필수·RESOLVED_AS 자동 승격, 로더 ontology_config.py), `enrichment_rules.json` 행 추가, **온보딩 완결 문단**("config 추가→리로드→즉시 사용", #7·워크스페이스 자동생성·std parser) |
| §6 지도 | 그래프 동기화 1행(graph_db_integration_plan 링크), 어드민 "코드 에디터" | **온톨로지 그래프**(materializer) + **그래프 뷰어·추적 리포트** 2행 신설, 어드민 행을 "파이프라인 5탭"으로·frontend §5 링크 |
| §8 API 요약 | 그래프·enrichment 미등재 | `/graph/*` 5종 + `POST /graph/trace`·`/api/graph/sync`(백필)·`/enrichment/*` 추가 |

map_split_registry는 SSOT에 넣지 않고 PROJECT_STATUS "현재 초점"에만 **예정**으로 언급(지시 준수 — 아직 미병합).

## 1. 갱신 파일 목록

| 파일 | 내용 |
|---|---|
| `docs/overview/SYSTEM_OVERVIEW.md` | §0 표 참조(직접 수정 — 총괄 검토 요망) |
| `docs/history/20260725_233000_ontology_graph_track_live_and_architecture_sync.md` | **신규** — 오늘 하루 종합 이력(그래프 트랙 전체·admin 5탭·온보딩 완결·듀얼 테마 6엔트리, 코드 스니펫 포함). 부분 보존 항목(행 DELETE 정리 미결)도 있는 그대로 기재 |
| `docs/history/README.md` | gen_index 재생성(191→**192**건) |
| `docs/architecture/backend.md` | **라인 앵커 전면 제거 → CODE_MAP 링크로 대체**(승인안 실행). 그래프 조회 5종 섹션 신설, Graph Sync Worker 행 materializer로 재작성, Watcher에 std parser 폴백, 공통 문단에서 "graph만 리로드 없음" 서술 삭제(#8 해소 반영) |
| `docs/architecture/event_driven_backend.md` | 제목·§1 다이어그램 현행화(outbox 2소비자 — processed_chain vs keyset 커서), **§4 전면 재작성**: Neo4j v1 가이드 → PG materializer 소비 흐름(커서/identity/provenance/retarget/#8/백필/Neo4j G3/조회 계층). §5에서 status=PENDING/DISPATCHED의 그래프 의미를 레거시로 정정. Status 🟠→🟢 |
| `docs/architecture/frontend.md` | 6엔트리 표, 신규 모듈 4종(graph_viewer/trace/trace_core/trace_launch) 등재, **§5 admin을 5탭 IA로 재작성**(해시 라우터·별칭·에디터 공용 뷰), **§6 그래프 뷰어·추적 리포트 신설**, §7 백엔드 계약에 그래프 API |
| `docs/architecture/data_model.md` | 그래프 3테이블 + `ensure_graph_tables` 서술, #7 CREATE 경로 문단, SOURCE_PRIORITY에 chain_ingestion:4 + resolve_priority_map, 라인 앵커 제거 |
| `docs/architecture/CODE_MAP.md` | HEAD `078fb2c` 재앵커(전부 **Grep 실측** — 교훈 준수). §1 그래프 구간 신설 이후 앵커 +~340줄 이동 반영(§1.1/1.2/1.3/1.4), **§1.5 그래프 조회 구간 신설**(뷰어 3종+trace+mapping-summary+공용 BFS 헬퍼), §2 crud(resolve_priority_map/get_source_priority/ontology 재앵커), **§5에 그래프 트랙 3모듈 신설**(models.py 그래프 클래스·ontology_config·graph_materializer·graph_sync_worker 함수 앵커), §7 admin.js 재작성분(5탭 함수)·G2 클라 모듈 4종·6엔트리, §8 흐름 8(그래프 자동 승격)·9(조회/추적) 추가 |
| `docs/process/PROJECT_STATUS.md` | **대청소** — "현재 상태" 중심 재구성: 현재 초점 4건, 최근 완료를 롤업 표 1개로 압축(개별 in-flight 서술 제거), 열린 문제 4건만 잔존(#4는 test_map_presets_api 1건만으로 정정, #5 잔여에서 C-7 해소 반영), **#8 종결 처리(G1 materializer SYSTEM_RELOAD 구독)**, 백로그를 우선순위/그래프 미결 정책/admin 이관/저순위로 재편 |
| `docs/README.md` | 이력 192건, event_driven 🟢 승격, ONTOLOGY_GRAPH_SPEC 행 문구 갱신, graph_db_integration_plan 행 제거+아카이브 안내 |
| `docs/process/DOC_OWNERSHIP.md` | 그래프 2행 재편(materializer 코드 실체 반영 + 뷰어·추적 행 신설), CODE_MAP 행 "doc-keeper 전담"으로 정정(낡은 "구현 에이전트 갱신" 서술), admin 행 5탭 |
| `docs/_archive/graph_db_integration_plan.md` | `spec/`에서 **아카이브 이관**(git mv) + SUPERSEDED 배지. 잔여 링크 정리(README/DOC_OWNERSHIP/FEATURE_CHECKLIST/ONTOLOGY_GRAPH_SPEC 헤더 링크 경로만 수정) |
| `docs/qa/FEATURE_CHECKLIST.md` | "온톨로지 동기화" 행 1건만 현행화(Neo4j 서술 → PG materialize + 뷰어/추적 진입 경로) |
| `docs/spec/ONTOLOGY_GRAPH_SPEC.md` | 헤더의 아카이브 링크 경로 1줄만 수정(내용 무변경 — Owner 총괄) |

## 2. 발견한 불일치 (수정 완료분)

1. **#8이 이미 해소되어 있었음** — PROJECT_STATUS는 "graph_sync 워커 리로드 배선 없음(대기)"이었으나 G1 materializer가 SYSTEM_RELOAD를 구독(보고서·코드 서술 일치) → 종결 처리. backend.md·CODE_MAP 흐름 6의 동일 서술도 정정.
2. **#4 서술 낡음** — enrichment 테스트 격리 버그는 이미 해소됐는데 병기돼 있었음 → "잔여 test_map_presets_api 1건"으로 압축.
3. **backend.md 라인 앵커 전면 낡음**(main.py 3,036→3,646줄 시대 앵커) → 앵커 제거·CODE_MAP 위임으로 구조적 해결(재발 방지).
4. **event_driven_backend §4가 v1(Neo4j property_mappings) 시대** — 실구현(v2·materializer)과 정면 상충 → 재작성. §5의 outbox `status` 의미(그래프 워커 PENDING/DISPATCHED)도 materializer 시대엔 미사용 → 레거시 명기.
5. **DOC_OWNERSHIP의 CODE_MAP 유지보수 주체가 낡음**("구현 에이전트") — 사용자 지시(doc-keeper 전담)와 상충 → 정정.
6. **frontend/SSOT의 "4엔트리·~10,300줄"** → 6엔트리·~13,000줄(실측 12,995) 정정.
7. C-7(그래프 무제한 로드)이 열린 문제 #5 목록에 남아 있었으나 G1 키셋 청킹으로 해소 → #5에서 제외·주석.

## 3. SSOT·스펙 관련 제안 (총괄 결정 사항 — 직접 수정 안 함)

1. **ONTOLOGY_GRAPH_SPEC Status 승격**: 현재 헤더 "🟠 제안(초안 v0)"인데 G1+뷰어+G2가 라이브 가동 중 — Enrichment 전례처럼 "🟢 Living(구현 반영)" 승격 검토 요망(스펙 Owner 총괄이라 미수정, README에는 "승격 검토 대기"로 표기).
2. **FEATURE_CHECKLIST 신규 기능 행 추가 필요**: 그래프 뷰어·추적 리포트·admin 5탭 라우팅의 QA 점검 항목이 아직 없음. 다음 doc-keeper 사이클(체크리스트 갱신은 doc-keeper 전담)로 위임 지시 요망 — 이번 범위(아키텍처 문서)에서 제외했음.
3. **DOC_AUDIT.md**: 진단 스냅샷 성격이라 graph_db_integration_plan 언급(백틱 텍스트, 링크 아님)을 보존 — 정합 대상 아님 판단. 이견 시 지적 바람.

## 4. 교훈 제안 (총괄 검수 후 memory/doc-keeper.md 반영)

- **함정**: 리빙 문서에 소스 라인 앵커를 직접 적으면 대형 삽입 한 번에 문서 전체가 낡는다(backend.md가 반복 재발).
  **올바른 방법**: 라인 앵커는 CODE_MAP 한 곳에서만 관리하고, 다른 리빙 문서는 경로·함수명+CODE_MAP 링크로만 서술한다.
- **함정**: 열린 이슈가 다른 트랙 작업에 "동승"해 해소되어도 상태 보드에 대기로 남는다(#8, C-7).
  **올바른 방법**: 대형 배치 문서 동기화 시 열린 이슈 표를 구현 보고서와 전수 대조해 동승 해소분을 찾는다.

## 5. 남은 것 / 리스크

- CODE_MAP §2(crud) 중간부 앵커(~198–1410)는 diff 기반 +18~23줄 추정치(±20 허용 내 경계) — 핵심 함수(compute/apply_batch/priority/ontology)는 Grep 실측함. 다음 crud 변경 사이클에 전수 재실측 권장.
- 커밋은 총괄 몫. `git status`: docs/ 하위 13파일 M + history 신규 1 + spec→_archive 이동(git mv) 1.
