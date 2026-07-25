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
| 7 | 중간 | **런타임 신규 테이블 추가 시 물리 CREATE 누락** — `table_config.json`에 새 테이블 추가 시 핫리로드가 ORM 모델 등록·`/tables` 노출까지는 하지만 실제 `CREATE TABLE`은 부팅 스키마 동기화에서만 수행 → 재기동 전까지 해당 테이블 조회가 `UndefinedTable` 500 (2026-07-25 enrichment 스모크에서 실측). 조치안: config_watcher 리로드 경로에 `sync_dynamic_tables_schema` 신규 테이블 생성 포함 | Server | 대기 |
| 3 | 정보 | 미리보기 브라우저 pane이 비-compositing → rAF/ResizeObserver 자동발화·CSS transition 프리즈로 라이브 UI 자동검증 제약(실제 브라우저 무관) | 검증환경 | 알려짐 |

## ⏭️ 다음 단계 / 백로그 (Next / Backlog)
- **[신규·사용자 요청 2026-07-25] 코드맵(압축 구조 문서) 체계** — 에이전트들이 매번 소스 전체를 읽어 토큰 소모 과다. 조치안: ① `docs/architecture/CODE_MAP.md`(또는 모듈별) 신설 — 파일별 핵심 함수/클래스 시그니처·역할 1줄·대략 라인 앵커·호출 관계 요약 ② 에이전트 정의 Pre-Flight에 "코드맵 먼저, 소스는 필요한 부분만" 규칙 추가 ③ 유지보수는 doc-keeper 정기 위임(코드 변경 시 해당 모듈 맵 갱신) ④ 우선 대상: `main.py`(3,000줄+)·`chain_ingestion_worker.py`·`crud.py`·`directory_watcher.py`·client2 모듈들 ⑤ **에이전트별 교훈 파일 포함**(`agent_workspace/memory/<agent>.md` — 도메인 함정 목록(예: editable 설치·cp949·type_coerce), 정의 Pre-Flight에 로드 배선, 신규 교훈은 에이전트가 제안→총괄 검수 후 반영). **컴팩트 후 착수.**
- **진행 중(in-flight)**: ① ✅ std parser 배치 — QA GO-WITH-FIXES 후 F1(공백 키 행 스킵+카운트)·F2(sync Lock 직렬화)·F3(observer 기동 가드)·F5(검증 기준 통일) 수정 완료, 115 passed 검증 후 커밋됨. 잔여: F4(옵트아웃 핫리로드 불가 — 재기동 필요, 가이드에 고지됨·코드 수정은 보류) ② ✅ 듀얼 테마 C안 — client-pm worktree 구현 완료 → 총괄 검수(경계 파일 무접촉 확인)→병합→본체 빌드→라이브 시각 검증(index/enrichment 양 테마 전환·페이지 간 localStorage 유지·AG-Grid 무재생성 재도색·admin 라이트 렌더 확인) 후 커밋. 기본 라이트, 토큰 SSOT `client2/src/tokens.css` + `theme.js`. 잔여 후속: `--transition-smooth: all` 성능 개선(감사 #8), 실브라우저 체크리스트 일부(QtWebEngine localStorage 등 — `Client_dualtheme_report.md` §9) ③ 디자인 감사 완료(시안 3종, C안 확정·반영됨). ④ admin.js 기존 null 컨테이너 콘솔 에러(테마 무관, 구 번들에서도 재현) — 별도 작업 칩 발행.
- 루트 `task/` 대기 항목: `cursor_based_pagination_pending.md`, `total_count_sync_pending.md`, `desktop_hybrid_wrapper_plan.md`.

## 🧭 환경 메모 (Env Notes)
- 로컬 테스트 테이블 `sample_map`은 `server/config/table_config.json`(gitignored)에만 존재 — 운영 무영향.
- 서버 기동: `python run_decoupled_app.py` (웹 :8080 + 워커 4종). 프론트 개발: `cd client2 && npm run dev`. dist는 추적·서빙 대상 → 소스 변경 시 `npm run build` 후 dist 커밋.

---
*갱신 규율: 이 보드는 상태의 단일 원천이다. 새 작업/문제/해결이 생기면 즉시 이 파일을 고친다. 이력 상세는 history, 이 파일은 "지금 어디까지 왔고 무엇이 문제인가"의 요약.*
