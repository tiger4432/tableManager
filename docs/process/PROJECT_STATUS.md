# 📌 PROJECT STATUS — 진행 상황 & 문제 현황 (Living Board)

> **Status:** 🟢 Living | **Last-updated:** 2026-07-25
> **역할:** 프로젝트의 **현재 진행 상황·열린 문제·다음 단계**를 담는 단일 상태 보드. **컨텍스트 압축/세션 교체에도 살아남는 영속 상태**다.
> **규칙:** 총괄(및 각 PM)은 작업 **착수 전 이 파일을 읽고**, **완료 후 갱신**한다. 상세 이력은 [history/](../history/README.md), 현재 아키텍처는 [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md).

---

## 🎯 현재 초점 (Current Focus)
- 🎉 **Enrichment Queue v1 완성(2026-07-25)** — 서버(dedup mapper 체인 자동파생 `4c8c2a4`) + 클라 전 단계(컨베이어 `c21bdb8` · 참조뷰 탭 + 결손 배지 `100112c`) 병합·빌드·E2E 실동 검증 완료. 스펙 **Living 승격** + SSOT §6 배선. 스모크 규칙 `line_model_owner_attribution`(production_plan→line_model_registry, 로컬 config)로 검증. 이력: [20260725_130000](../history/20260725_130000_enrichment_queue_v1_complete.md).
- **다음: 실전 규칙 작성** — 사용자의 실제 설비이력/bonding log 스키마 확보 → `table_config.json` 파생 테이블 + `enrichment_rules.json` 실규칙. (스모크 규칙은 데모로 유지. 신규 테이블 추가 시 이슈 #7 제약으로 재기동 필요.)
- ✅ 이슈 #0(체인 outbox) 종결 — 정상 31ms(SLO 달성). 경합 배치 1 커밋(`4329c29`) + **로컬 운영 절차(재기동→인덱스→purge→VACUUM) 실행 완료.** 운영 서버는 `git pull` 후 동일 순서 필요.
- 맵 에디터 사용성 개선 (Client PM 도메인)은 병행 관찰.

## ✅ 최근 완료 (Recently Done) — 최신순
| 날짜 | 영역 | 요약 | 이력 |
|---|---|---|---|
| 2026-07-25 | 서버 | **표준 파서(Std Parser) 폴백 + 테이블 워크스페이스 자동 생성** — 커스텀 스크립트 무매칭 시 `column_types` 헤더 검증(bk/composite 필수, 미지 컬럼 무시) 기반 CSV/TSV/TXT 스트리밍 적재(utf-8-sig→cp949, 1000행 청킹, 기존 WS 이벤트 그대로) + table_config 등록 테이블의 워크스페이스 자동 보충·SYSTEM_RELOAD 런타임 감시 등록, 테스트 106 통과(신규 22) — 검수·커밋 대기 | [20260725_113212](../history/20260725_113212_std_parser_fallback_and_workspace_autoprovision.md) |
| 2026-07-25 | 스킬 | 이슈 #1 — IntegrityAndQAExpert 스킬 웹 전환: §3 체크리스트 PySide(QThread/DLL/임포트)→client2·5-프로세스 QA 항목 전면 교체 + §1·§2·frontmatter 데스크톱 잔재 정리 — 검수·커밋 대기 | — |
| 2026-07-25 | 서버 | Enrichment Queue 서버측 — enrichment_rules 로더/검증 + generic dedup mapper(체인 룰 자동 파생, target 보존 이중 방어, 멱등 count) + API 2종(규칙 메타·참조뷰 서버측 실행) + enrichment.html 서빙, 테스트 75통과(신규 16) | [20260725_113000](../history/20260725_113000_enrichment_queue_server_impl.md) |
| 2026-07-25 | 서버 | 이슈 #6 — 감사 로그 DB 미저장 수정: add_to_cache=False 경로 4개 함수(행 생성/삭제·소스 삭제·수동 우선순위)에 commit 전 bulk_insert_audit_logs 적재 추가 + 회귀 테스트 3건, DELETE/CREATE 이력 재시작 후 보존 | — |
| 2026-07-25 | 서버 | 경합 수정 배치 1 — C-2 import 통일(outbox ×2 발행 근절)·C-1 async 핸들러 threadpool 격리+batch_delete N+1 제거·C-5 created_logs 500건 상한·C-3 outbox 7일 purge+레거시 인덱스 4종 정리, 테스트 58 통과(신규 8) — 검수·커밋 대기 | [20260725_090000](../history/20260725_090000_contention_fix_batch1.md) |
| 2026-07-25 | 서버 | 5-프로세스 경합 전수 점검(분석 전용) — C-1~C-12 리스크 12건 식별·실측(outbox 중복 1.26M그룹, 루프 동결 7s), 착수순서 권고 | [보고서](../../agent_workspace/reports/Server_contention_audit.md) |
| 2026-07-25 | 서버/체인 | 체인 워커 콜드 스타트 웜업 — 매퍼 선import(+SYSTEM_RELOAD 재웜업)·DB 풀 프라임·HTTP keep-alive(스레드-로컬 Session)·[Warmup] 계측, 첫 체인 1.3s → 100ms 목표 — 검수·커밋 대기 | [20260725_073000](../history/20260725_073000_chain_worker_cold_start_warmup.md) |
| 2026-07-25 | 서버/체인 | 체인 100ms SLO 구조수정 — 통지 인라인 발사(기아 제거)·[Latency] 구간 계측·기동 마이그레이션 게이팅(UndefinedColumn 회귀 수정) — 검수·커밋 대기 | [20260725_063000](../history/20260725_063000_chain_latency_slo_inline_dispatch.md) |
| 2026-07-25 | 서버/체인 | 체인 outbox 신뢰성 후속수정 F1(broadcast_at 전달확정+미전달 스윕+백필)·F2(그룹간 단일 순차 발사)·F3(idx_outbox_txid 실사용) + F4/F5 문서화 — 검수·커밋 대기 | [20260725_001824](../history/20260725_001824_chain_outbox_reliability_f1_f2_f3.md) |
| 2026-07-24 | 기획/검수 | 이슈 #0 총괄 적대적 검수 — GO-WITH-FIXES 판정, 고위험 결함 2건(F1 stale·F2 순서역전)+인덱스버그(F3) 확인 → #0 재개 | — |
| 2026-07-24 | 조직 | `.claude/agents/` PM 3종 등록(lead/server/client-pm) — 헌장 참조형 | `396b59e` |
| 2026-07-24 | 서버/체인 | 체인 outbox #4/#5 — LISTEN 레이스 제거(상시 LISTEN+drain)·실패 head-of-line 제거(그룹 skip+동일target 보류) | `4bf5b21` |
| 2026-07-24 | 프로세스 | 위임 시 대상 구조 docs 제공 원칙(SOP §0-C) | `8c20921` |
| 2026-07-24 | 서버/체인 | 체인 outbox #2/#1/#3 — commit후 통지 fire-and-forget·outbox 부분/표현식 인덱스 | `1f02712` |
| 2026-07-24 | 서버/체인 | 체인 outbox 지연 진단(원인 5건 파악, 파일 기록) | `d3841ce` |
| 2026-07-24 | 기획/문서 | SSOT §1 비전 재정의 — 5대 핵심 가치(최소공수 교정·온톨로지 기반·실시간 신뢰전파·레이어링·이력) + 가치 사슬 | `1d01086` |
| 2026-07-24 | 프로세스 | 상태 보드(본 파일) 도입 — 진행·문제 파일 관리 원칙 | `8e89fa2` |
| 2026-07-24 | 프로세스 | 총괄 위임 운영 원칙(§0-C): 소규모 수정·문서는 서브에이전트, 총괄은 검수 | `387158c` |
| 2026-07-24 | 맵에디터 | FRONT/BACK 반투명 워터마크 복원(표시 전용) | `05b1303` |
| 2026-07-24 | 맵에디터 | FRONT/BACK 라벨 그리드 밖(툴바 칩) 이동 + 반응형 정사각 채움(ResizeObserver) | `0130283` |
| 2026-07-24 | 스킬 | StableDevelopmentProtocol에 '사이드 이펙트 전수 분석' 원칙 추가 | `9a73313` |
| 2026-07-24 | 맵에디터 | 테이블 A→B 맵 이월(전환 시 유지/초기화 확인창) | `a41007e` |
| 2026-07-24 | 조직 | 총괄 + Server/Client 2-PM 체제 수립 | `b13c5b3` |
| 2026-07-24 | 스킬 | 도메인 스킬 4종 웹(client2) 전환 | `4337721` |
| 2026-07-24 | 스킬/프롬프트 | StableDevelopmentProtocol 헌장 + 프롬프트 배선 | `94e9359` |
| 2026-07-24 | 문서 | SSOT/거버넌스 체계 수립 + 문서 트리 재편 | `8cdd00e` |

## 🐞 열린 문제 / 알려진 이슈 (Open Problems)
| # | 심각도 | 문제 | 도메인 | 상태 |
|---|---|---|---|---|
| 0 | — | 🏁 **[종결 2026-07-25] 체인 인제션 outbox 지연·신뢰성** — 진단 5건 → F1~F5 신뢰성 후속수정 → 기동 마이그레이션 회귀 근절 → 통지 기아 제거(인라인 발사) → 콜드 스타트 웜업. **최종 실측: 정상 31ms(SLO 100ms), 38행 배치 172ms, 재기동 첫 체인 579ms(수용, 잔여 mapper 첫 쿼리 웜업은 백로그).** `[Latency]`/`[Warmup]` 상시 계측 확보. 커밋: `1f02712`→`4bf5b21`→`cc26773`→`acc60dd`. 상세: [task/chain_outbox_latency.md](../../task/chain_outbox_latency.md) | Server | 🏁종결 |
| 1 | — | 🏁 **[종결 2026-07-25] `IntegrityAndQAExpert` 스킬 PySide 잔재** — §3 체크리스트를 웹 client2/5-프로세스 QA 항목(state.js 리프레셔 누락·셀 계약 `{value,is_overwrite,priority_source}`·WS 재연결/applyTransaction 델타·stale 응답 UUID 가드·이벤트 루프 블로킹·outbox/우선순위 엔진 보존·4엔트리 빌드·conda pytest+`node --check`)으로 전면 교체. §1 원칙(DLL 워크어라운드→outbox/설정주도)·§2 워크플로우(프로세스 분리 진단·통합 테스트 명령)·frontmatter의 데스크톱 서술도 정리 | 프로세스 | 🏁종결 |
| 4 | 낮음 | `test_map_presets_api` 기존 실패(#0 이전부터, 맵 프리셋 도메인·체인 무관). 추가로 `test_enrichment.py::test_dedup_new_keys_inserted`도 기존 실패로 확인 — **원인 진단 완료(2026-07-25 QA)**: 테스트의 가짜 `bonding_log`(bk `log_key`)가 사용자 실 config에 나중에 생긴 실제 `bonding_log`(bk `log_id`)와 테이블명 충돌 → 공유 in-memory sqlite에 실 스키마 선점, `create_all(checkfirst)` 스킵 → `no such column`. 테스트 격리 버그 — **해소(2026-07-25)**: ENRICH_TABLES 테이블명을 `enrich_test_src`/`enrich_test_derived`로 변경. 현재 전체 스위트 115 통과/1 실패(`test_map_presets_api`만 잔존) | Client·Server | 대기 |
| 2 | 낮음 | 맵 이월 시 A/B의 x·y·val 컬럼명이 크게 다르면 자동 정합 안 됨(저장 전 Advanced Column Mapping 수동 확인 필요) | Client | 대기(관찰) |
| 5 | 중간 | **경합 점검 잔여 리스크(승인 대기)** — C-4(인제션 체인 큐 독점·HOL, 매퍼 의미론 총괄 협의 필요)·C-6(동시 upsert 행 락 순서)·C-7(그래프 전체 동기화 무제한 로드/브로드캐스트)·C-8(런타임 ALTER 락 컨보이)·C-9(커넥션 풀 합계>max_connections)·C-10(워처 .tmp 필터 부재)·C-11(WS 직렬 전송) + 체인 워커의 created_logs 무상한 전송·broadcast body 파싱 잔여. 상세: [점검 보고서](../../agent_workspace/reports/Server_contention_audit.md) | Server | 대기(수정 배치 2 후보) |
| 6 | — | 🏁 **[종결 2026-07-25] 감사 로그 DB 미저장(add_to_cache=False가 persist까지 생략)** — 전수 조사 결과 delete_rows_batch뿐 아니라 create_empty_rows_batch·delete_cell_source_batch·set_cell_manual_priority_batch까지 4개 함수가 캐시에만 기록. 각 함수 commit 전 `bulk_insert_audit_logs` 벌크 적재 추가(시그니처 무변경, apply_batch_updates 기존 패턴 준용) + 회귀 테스트 3건(`test_audit_log_persistence.py`). | Server | 🏁종결 |
| 7 | — | 🏁 **[종결 2026-07-25] 런타임 신규 테이블 물리 CREATE 누락** — 리로드 3경로 전부 CREATE 부재였음(`reload_local_process_cache` no-op, `sync_dynamic_tables_schema`는 ALTER 전용, 워커는 캐시 무효화만). 신규 `create_missing_dynamic_tables`(info_schema 게이트+checkfirst+독립 트랜잭션 rollback) + 공용 진입점 `refresh_dynamic_models`로 3경로 배선. 회귀 테스트 4건, 스위트 119 passed | Server | 🏁종결 |
| 8 | 낮음 | **graph_sync 워커가 신규 테이블을 재기동 전까지 인지 못함** — SYSTEM_RELOAD/config watcher 배선이 원래 없음(500은 아니고 그래프 동기화 지연). #7 후속으로 발견, 동시성 검토 필요해 분리(온톨로지 트랙 G1에 동승 후보) | Server | 대기 |
| 3 | 정보 | 미리보기 브라우저 pane이 비-compositing → rAF/ResizeObserver 자동발화·CSS transition 프리즈로 라이브 UI 자동검증 제약(실제 브라우저 무관) | 검증환경 | 알려짐 |

## ⏭️ 다음 단계 / 백로그 (Next / Backlog)
- ✅ **[완료 2026-07-25] 코드맵(압축 구조 문서) + 에이전트 교훈 파일 체계** — `docs/architecture/CODE_MAP.md` 신설(약 300줄: main.py 라우트 표·crud/watcher/chain worker 시그니처+라인 앵커·client2 모듈 요약·호출 흐름 7개, 앵커 기준 HEAD cd3f90c), `agent_workspace/memory/<agent>.md` 교훈 파일 5종(신규 교훈은 제안→총괄 검수 후 반영), 에이전트 정의 6종(lead-pm 포함) Pre-Flight에 "코드맵 먼저 + 교훈 파일 로드" 배선, SSOT §6에 코드맵 우선 규칙 명시. 유지보수(사용자 지시 2026-07-25): **코드맵 갱신은 doc-keeper 전담** — 코드 배치 병합·커밋 후 총괄이 위임하면 doc-keeper가 타 에이전트 수정 이력(history·보고서·diff)을 요약해 갱신. 정합 감사도 doc-keeper. 부수 발견: main.py 셀 히스토리 라우트 이중 정의(~2020 사장)·`client2/src/counter.js` 템플릿 잔재 — 소규모 정리 후보.
- **진행 중(in-flight)**: ① **온톨로지 G1 라이브 가동 중** — QA 수정(H1 provenance 셀 레이어 진실화·H2 retarget·M3 루프 기아 등) 후 병합(3a9dcc8, 144 passed), 데모 매핑 반영, 재기동 후 **라이브 검증 통과**: materializer 증분 소비([GraphLatency] lag 162ms, SLO 60배 여유), 전체 백필 860행→946노드/1,600+엣지 청킹 1초(C-7 실증), 교정→RESOLVED_AS(user) 엣지 실시간 생성 확인. **후속 결함 [H2-b] 발견(총괄 라이브 실증)**: 교정 비움(user 소스 삭제→blank) 시 낡은 RESOLVED_AS 잔존 — server-pm 수정 중. 라이브 DB에 WF-LIVE-G1-TEST 잔존 엣지 1건(수정 후 정리 예정) ② **admin 소안+중안 배포 완료** — 파이프라인 5탭 IA(Overview/File/Chain/AutoUpdate/Enrichment) 라이브 검증 통과(387d987). 대안(온보딩 위저드·규칙 CRUD)은 이관 목록 대기 ③ 서브그래프 미니 뷰어 — H2-b 수정 후 착수(지시서 준비됨).
- **오후 완료 롤업(2026-07-25)**: 다크 모드 진하게(4229d9f)·기능 체크리스트 client-pm 검증 10건 반영·frontend.md 4엔트리 동기화·이슈 #7 종결(119 passed)·교훈 3건 반영(server-pm 2, client-pm 1).
- **오늘 완료 롤업(2026-07-25)**: std parser 배치(QA 수정 포함, 115 passed)·enrichment 테스트 격리·듀얼 테마 C안(병합·빌드·라이브 검증)·헤더 드롭다운 z-order 수정·코드맵+교훈 파일 체계(유지보수 doc-keeper 전담으로 변경)·기능 체크리스트 초판. 사용자 전 기능 수동 점검 "다 잘 작동" 확인.
- **비이슈 종결**: source delete "미작동" 신고 — 서버 API(단일/배치) 정상 실증, 정체는 가동 중 파이프라인의 소스 재생성(레이어링 설계상 정상, 교정 정석은 user 덮어쓰기). 사용자 재확인 결과 정상 동작으로 종결. UX 개선 후보(재생성 소스 삭제 시 경고 표시)는 백로그 low.
- **관찰(낮음, 신규)**: 진단 중 `priority_source: chain_ingestion`인데 표시 값은 system 소스 값인 셀 목격(38320 vs 3832) — 레이어링 표시 정합 의심. chain_ingestion의 우선순위 랭크 정의 여부 포함 server-pm 점검 후보(#5 배치에 동승 가능).
- 루트 `task/` 대기 항목: `cursor_based_pagination_pending.md`, `total_count_sync_pending.md`, `desktop_hybrid_wrapper_plan.md`.

## 🧭 환경 메모 (Env Notes)
- 로컬 테스트 테이블 `sample_map`은 `server/config/table_config.json`(gitignored)에만 존재 — 운영 무영향.
- 서버 기동: `python run_decoupled_app.py` (웹 :8080 + 워커 4종). 프론트 개발: `cd client2 && npm run dev`. dist는 추적·서빙 대상 → 소스 변경 시 `npm run build` 후 dist 커밋.

---
*갱신 규율: 이 보드는 상태의 단일 원천이다. 새 작업/문제/해결이 생기면 즉시 이 파일을 고친다. 이력 상세는 history, 이 파일은 "지금 어디까지 왔고 무엇이 문제인가"의 요약.*
