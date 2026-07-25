# 📌 PROJECT STATUS — 진행 상황 & 문제 현황 (Living Board)

> **Status:** 🟢 Living | **Last-updated:** 2026-07-25 (대청소 — 현재 상태 중심 재구성)
> **역할:** 프로젝트의 **현재 진행 상황·열린 문제·다음 단계**를 담는 단일 상태 보드. **컨텍스트 압축/세션 교체에도 살아남는 영속 상태**다.
> **규칙:** 총괄(및 각 PM)은 작업 **착수 전 이 파일을 읽고**, **완료 후 갱신**한다. 상세 이력은 [history/](../history/README.md), 현재 아키텍처는 [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md). 이 보드는 이력 로그가 아니다 — "지금 어디까지 왔고 무엇이 문제인가"만 담는다.

---

## 🎯 현재 초점 (Current Focus)

1. **온톨로지 그래프 트랙 — G1+뷰어+G2 라이브 가동 완료(2026-07-25)**. PG 엣지 스토어 + outbox 증분 materializer(자동 승격) + 조회 API 5종 + 서브그래프 뷰어(graph.html) + 추적 리포트(trace.html)까지 실동·라이브 검증 통과([GraphLatency] lag 162ms, 교정→RESOLVED_AS(user) 실시간). 종합: [20260725_233000](../history/20260725_233000_ontology_graph_track_live_and_architecture_sync.md) · 스펙 [ONTOLOGY_GRAPH_SPEC](../spec/ONTOLOGY_GRAPH_SPEC.md). **다음: G2.5(서브그래프 직렬화) → G3(시각화 고도화·Neo4j 병행)**.
2. **map_split_registry 착수 대기(사용자 승인)** — 맵 value description(실험 split 자연어)을 localStorage에서 동적 테이블로 승격 + SplitCondition 온톨로지 매핑 + 맵 에디터 로드/저장 전환. 지시서 `agent_workspace/tasks/Client_map_split_registry_task.md` 준비됨 — client-pm 위임 예정.
3. **Enrichment 실전 규칙 작성 대기** — 사용자의 실제 설비이력/bonding log 스키마 확보 → `table_config.json` 파생 테이블 + `enrichment_rules.json` 실규칙. (스모크 규칙 `line_model_owner_attribution`은 데모로 유지.)
4. **아키텍처 문서 대청소 완료(2026-07-25)** — SSOT·architecture 4종·CODE_MAP이 그래프 트랙/admin 5탭/6엔트리/온보딩 완결을 반영. SYSTEM_OVERVIEW 하나로 현행 파악 가능.

## ✅ 최근 완료 (Recently Done) — 2026-07-25 롤업

| 영역 | 요약 | 근거 |
|---|---|---|
| 서버/그래프 | **온톨로지 G1** — graph_nodes/edges/graph_sync_state + 매핑 v2(description 필수, enrichment `RESOLVED_AS` 자동 승격) + materializer(증분 소비·QA H1/H2 provenance·retarget) | `6da2276`→`7c40a33`→`d130c65` |
| 서버/그래프 | **조회 API 5종** — stats/neighbors/search(뷰어) + trace/mapping-summary(G2, 공용 BFS 추출) | `c63b881`, `d8d109d` |
| 클라/그래프 | **그래프 뷰어 + 추적 리포트** — graph.html(BFS 동심원 캔버스)·trace.html(그룹+타임라인) + index 「🕸️ 추적」 진입점, 양방향 크로스링크 | `eea929d`/`f41ca3e`, `6c0a722`/`83507aa` |
| 클라/admin | **파이프라인 생애주기 5탭 IA 재편**(Overview/File/Chain/AutoUpdate/Enrichment, Code Editor 딥링크 공용 뷰, 구 해시 별칭 호환) — 라이브 검증 통과 | `7d02989`(소안), `3e599d2`/`387d987`(중안) |
| 서버/인제션 | **온보딩 완결** — std parser 폴백 + 워크스페이스 자동생성(`f90717f`) + 런타임 테이블 CREATE(#7, `6c447ee`) → "config 추가→리로드→즉시 사용" | [20260725_113212](../history/20260725_113212_std_parser_fallback_and_workspace_autoprovision.md), [20260725_170000](../history/20260725_170000_issue7_runtime_table_create.md) |
| 클라/테마 | **듀얼 테마(기본 라이트)** tokens.css SSOT + 다크 심화, 헤더 드롭다운 z-order 수정 | `765c7e5`~`cd3f90c`, `4229d9f`, `d48f25b` |
| 서버/체인 | 이슈 #0 종결 — outbox 지연·신뢰성(F1~F5·인라인 발사·웜업), 정상 31ms(SLO 100ms) | [task/chain_outbox_latency.md](../../task/chain_outbox_latency.md) |
| 서버 | 경합 수정 배치 1(C-1/C-2/C-3/C-5) + 감사 로그 미저장 수정(#6) | `4329c29`, `5fd8d24` |
| 전체 | **Enrichment Queue v1**(서버 dedup mapper + 컨베이어 + 참조뷰 + 결손 배지) — 스펙 Living 승격 | [20260725_130000](../history/20260725_130000_enrichment_queue_v1_complete.md) |
| 프로세스 | 코드맵+교훈 파일 체계(유지보수 doc-keeper 전담) · 기능 체크리스트 초판 · 에이전트 로스터 확장(qa-reviewer/doc-keeper/ui-designer) | `de79c50`, `d0c14a5`, `cbdc1e2` |

2026-07-24 이전 완료분은 [history/README.md](../history/README.md)와 [RELEASE_LOG](./RELEASE_LOG.md) 참조.

## 🐞 열린 문제 (Open Problems)

| # | 심각도 | 문제 | 도메인 | 상태 |
|---|---|---|---|---|
| 4 | 낮음 | `test_map_presets_api` 기존 실패(맵 프리셋 도메인, #0 이전부터) — **잔여는 이것 1건뿐**(enrichment 테스트 격리 버그는 2026-07-25 해소, 현재 스위트 177 passed / 1 failed) | Client·Server | 대기 |
| 5 | 중간 | **경합 점검 잔여 리스크(수정 배치 2 후보)** — C-4(체인 큐 독점·HOL, 매퍼 의미론 협의 필요)·C-6(동시 upsert 행 락 순서)·C-8(런타임 ALTER 락 컨보이)·C-9(커넥션 풀 합계>max_connections)·C-10(워처 .tmp 필터 부재)·C-11(WS 직렬 전송) + created_logs 무상한 전송 잔여. 상세: [점검 보고서](../../agent_workspace/reports/Server_contention_audit.md) (C-7은 그래프 키셋 청킹으로 해소됨) | Server | 대기 |
| 2 | 낮음 | 맵 이월 시 A/B의 x·y·val 컬럼명이 크게 다르면 자동 정합 안 됨(저장 전 Advanced Column Mapping 수동 확인 필요) | Client | 대기(관찰) |
| 3 | 정보 | 미리보기 브라우저 pane이 비-compositing → rAF/ResizeObserver 자동발화·CSS transition 프리즈로 라이브 UI 자동검증 제약(실제 브라우저 무관) | 검증환경 | 알려짐 |

**종결(2026-07-25):** #0 체인 outbox 지연·신뢰성(31ms) · #1 IntegrityAndQAExpert 스킬 웹 전환 · #6 감사 로그 DB 미저장 · #7 런타임 테이블 물리 CREATE · **#8 graph 워커 신규 테이블 미인지(G1 materializer의 SYSTEM_RELOAD 구독으로 해소)**.

## ⏭️ 다음 단계 / 백로그 (Next / Backlog)

**우선 순위 높음 (현재 초점 연동)**
- G2.5 서브그래프 직렬화 → G3(그래프 시각화 고도화, Neo4j 병행 타깃). 시간 범위 스캔용 엣지 인덱스(event_time)는 G2.5 쿼리 설계와 함께.
- map_split_registry(현재 초점 #2) — client-pm 착수.
- enrichment 실전 규칙(현재 초점 #3).

**그래프 트랙 미결 정책**
- 행 DELETE 시 그래프 정리 정책(스펙 §8 — materializer는 DELETE 스킵, stale 엣지 잔존). `idx_graph_edges_row_ref`가 구현 기반.
- 운영 수칙: outbox 7일 purge보다 materializer 장기 정지 시 증분 유실 → `/api/graph/sync {"table_name":"all"}` 복구(문서화됨 — [event_driven_backend §4.3](../architecture/event_driven_backend.md)).
- search ILIKE 프리픽스 인덱스 한계(pg_trgm/text_pattern_ops 검토) · stats GROUP BY 캐시 — 그래프 대형화 시.

**admin 이관 목록** ([중안 보고서 §E](../../agent_workspace/reports/Client_admin_ux_mid_report.md))
- Enrichment 규칙 CRUD API · Chain rule CRUD API · 워크스페이스 생성/검증 API · 파이프라인별 "신규 추가" 위저드 UI · 헬스 시간창 집계 API(+파일 로그 서버 검색/정렬).

**관찰/저순위**
- 레이어링 표시 정합 의심 1건: `priority_source: chain_ingestion`인데 표시 값은 system 소스 값(38320 vs 3832) — chain_ingestion 서열 등재(#5 배치에 동승 가능) 후 재확인.
- 재생성 소스 삭제 시 경고 표시 UX(파이프라인이 소스를 재생성하는 것은 레이어링 설계상 정상 — 비이슈 종결됨).
- main.py 셀 히스토리 라우트 이중 정의(~2020 사장) · `client2/src/counter.js` 템플릿 잔재 — 소규모 정리 후보.
- 재기동 첫 체인 579ms(수용) — 잔여 mapper 첫 쿼리 웜업.
- 루트 `task/` 대기: `cursor_based_pagination_pending.md`, `total_count_sync_pending.md`, `desktop_hybrid_wrapper_plan.md`.

## 🧭 환경 메모 (Env Notes)
- 로컬 테스트 테이블 `sample_map`은 `server/config/table_config.json`(gitignored)에만 존재 — 운영 무영향.
- 서버 기동: `python run_decoupled_app.py` (웹 :8080 + 워커 4종). 프론트 개발: `cd client2 && npm run dev`. dist는 추적·서빙 대상 → 소스 변경 시 `npm run build` 후 dist 커밋.
- 운영 서버는 `git pull` 후 이슈 #0 절차(재기동→인덱스→purge→VACUUM, `scripts/setup_db_performance.py`) 필요.

---
*갱신 규율: 이 보드는 상태의 단일 원천이다. 새 작업/문제/해결이 생기면 즉시 이 파일을 고친다. 이력 상세는 history, 이 파일은 "지금 어디까지 왔고 무엇이 문제인가"의 요약.*
