# 📚 AssyManager Documentation

> **여기서 시작하세요.** 이 파일은 전체 문서의 **유일한 진입점(문서 지도)**입니다.
> 현재 아키텍처의 권위 있는 설명은 **[SYSTEM_OVERVIEW (SSOT)](./overview/SYSTEM_OVERVIEW.md)** 하나뿐입니다.

**Status 범례:** 🟢 Living(최신·검증됨) · 🟠 부분 최신 · ⚪ 참고/스냅샷 · 🗄️ Archived(대체됨)

---

## 🧭 1. 먼저 읽을 것

| 문서 | 내용 |
|---|---|
| 🟢 **[overview/SYSTEM_OVERVIEW.md](./overview/SYSTEM_OVERVIEW.md)** | **SSOT** — 현재 시스템의 전체 아키텍처. 무엇이든 여기서 시작 |
| 🟢 **[architecture/PRIMITIVES.md](./architecture/PRIMITIVES.md)** | **만들기 전에 여기부터** — 이 시스템이 이미 할 줄 아는 연산·패턴 카탈로그. "이건 무엇과 구조적으로 같은가"에 답하지 못하면 아직 설계할 준비가 안 된 것 |
| 🟢 [process/PROJECT_STATUS.md](./process/PROJECT_STATUS.md) | **진행 상황·열린 문제 단일 보드** — 여기서 현황 파악 |
| 🟢 [process/CONTRIBUTING.md](./process/CONTRIBUTING.md) | **개발·문서 갱신 규율(docs-as-code)** — 코드 바꾸면 여기 규칙대로 |
| 🟢 [guide/CONFIG_GUIDE.md](./guide/CONFIG_GUIDE.md) | **"무엇을 설정해야 하는가" 단일 참조** — config 전수 지도 + 시나리오별 체크리스트(새 테이블/맵/수집기/그래프 온보딩) |

## 🏛️ 2. 아키텍처 (architecture/)

| 문서 | 내용 |
|---|---|
| 🟢 [PRIMITIVES.md](./architecture/PRIMITIVES.md) | **기능→구현 카탈로그** — *무엇을 할 줄 아나*. CODE_MAP이 *어디에 있나*라면 이쪽은 재사용 가능한 연산·패턴과 그 함정 |
| 🟢 [CODE_MAP.md](./architecture/CODE_MAP.md) | **압축 구조 지도** — 파일별 시그니처·라인 앵커·호출 흐름. 소스 전량 읽기 전에 여기부터 |
| 🟢 [backend.md](./architecture/backend.md) | 5-프로세스 토폴로지, API 엔드포인트, outbox 패턴, **프로세스 감시·`/health`·진행 박동(§1.3)** |
| 🟢 [frontend.md](./architecture/frontend.md) | client2 웹(AG-Grid) + QtWebEngine 데스크톱 셸 |
| 🟢 [data_model.md](./architecture/data_model.md) | ORM 모델 + 동적 테이블 + 레이어링/우선순위 |
| 🟢 [event_driven_backend.md](./architecture/event_driven_backend.md) | Outbox 패턴 · 체인 인제션 · 온톨로지 그래프 승격(materializer) 심화 |

## 🧩 3. 서브시스템 리빙 가이드

| 서브시스템 | 문서 |
|---|---|
| 파일 인제션 파이프라인 | 🟢 [guide/INGESTION_GUIDE.md](./guide/INGESTION_GUIDE.md) |
| 체인 인제션(DB세션 맵퍼) | 🟢 [guide/chain_ingestion_guide.md](./guide/chain_ingestion_guide.md) |
| Auto-Update 스케줄러 | 🟢 [guide/AUTO_UPDATE_GUIDE.md](./guide/AUTO_UPDATE_GUIDE.md) |
| 웨이퍼 맵 에디터 | 🟢 [map_editor/](./map_editor/README.md) · [spec/MAP_EDITOR_SPEC.md](./spec/MAP_EDITOR_SPEC.md) — §1~§4 격자 에디터, **§5 범용 맵 오버레이**(**`wafer_map_metadata`가 정렬의 유일한 기준** · 변환은 클라 단일 구현 · 실패 status **4종** · 선언 오버라이드 레이어는 2026-07-27 폐지), **§6 전사 계획**(「계획 = 그 맵 자체」·신뢰 표기 3층 방어 · **M2.6부터 저장소는 `map_split_registry` 한 테이블, 구간·자재는 `bands` JSON**) |
| DOE 영역 저장 지도 | 🗄️ [spec/DOE_STORAGE_MAP.md](./spec/DOE_STORAGE_MAP.md) — **본문은 폐기된 3테이블 모델**이며 기존 데이터 해석용으로만 보존합니다. M2.6이 양쪽 다 착지해(`cdcddee`+`0f8d35f`) 지금은 `map_split_registry` **한 테이블**입니다 → 현행 계약은 [MAP_EDITOR_SPEC §6](./spec/MAP_EDITOR_SPEC.md)·[CONFIG_GUIDE §5.8](./guide/CONFIG_GUIDE.md) |
| HTML 토폴로지 파서 | 🟢 [guide/HTML_TOPOLOGY_PARSER_GUIDE.md](./guide/HTML_TOPOLOGY_PARSER_GUIDE.md) |
| 배치 업서트 | 🟠 [spec/batch_update_technical_specification.md](./spec/batch_update_technical_specification.md) |
| 실시간 동기화 | 🟢 **현행 정본은 [architecture/frontend §3·§3.1](./architecture/frontend.md)** — 모듈 구조 + **무결성 3문제**(중복 행·늦은 응답 오염·`total` 드리프트). 🗄️ [spec/DATA_SYNC_SPEC.md](./spec/DATA_SYNC_SPEC.md)은 **폐기된 PySide6 클라 기준이고 §3 문제 서술도 2026-07-27 이관 완료** — **남은 유효 내용 0, 아카이브 대기**(SSOT 링크 정리 후 총괄이 이관). 인용하지 말 것 |
| 실패 관리/재시도 | 🟢 [spec/FAILURE_MANAGEMENT_SPEC.md](./spec/FAILURE_MANAGEMENT_SPEC.md) |
| 비즈니스 로직/레이어링 | 🟠 [spec/BUSINESS_LOGIC_SPEC.md](./spec/BUSINESS_LOGIC_SPEC.md) |
| Enrichment Queue(결손 보정 워크리스트) | 🟢 [spec/ENRICHMENT_QUEUE_SPEC.md](./spec/ENRICHMENT_QUEUE_SPEC.md) |
| 온톨로지 지식그래프(LLM 백본) | 🟢 [spec/ONTOLOGY_GRAPH_SPEC.md](./spec/ONTOLOGY_GRAPH_SPEC.md) — **G1+뷰어+G2 라이브 가동으로 §1~§6 실증**(2026-07-25 Living 승격). §7.x는 G3+ 설계(§7.5c 탐색 정책은 G2.5 전제). 승격 흐름 요약: [event_driven_backend §4](./architecture/event_driven_backend.md) |
| API 레퍼런스 | 🟠 [spec/api_documentation.md](./spec/api_documentation.md) |

## ✅ 3.5 QA (qa/)

| 문서 | 내용 |
|---|---|
| 🟢 [qa/FEATURE_CHECKLIST.md](./qa/FEATURE_CHECKLIST.md) | **기능 인벤토리 + QA 수동 점검 체크리스트** — 서브시스템별 기능 지도·진입 경로·릴리스 전 회귀 점검 절차(SLO·멱등성 포함). **§1.11/§2.15 운영 감시**(감시자·`/health`·격리 환경) 포함. 새 기능 병합 시 doc-keeper가 갱신 |

## 🛠️ 4. 운영 & 셋업 (guide/)

| 문서 | 내용 |
|---|---|
| 🟢 [DEPLOY_SETUP.md](./guide/DEPLOY_SETUP.md) | **"내가 무엇을 채워야 하는가"** — 새 환경 배포 요약(제품 소유 vs 현장 소유, 제품 테이블 설치 스크립트, **격리 개발·검증 환경 §5**, 기동 후 `/health` 확인) |
| 🟢 [process/PRODUCTION_READINESS.md](./process/PRODUCTION_READINESS.md) | **프로덕션 게이트** — 무엇이 아직 막고 있는가(차단/조건부/통과 + 근거). 배포 판단은 여기서 |
| 🟢 [CONFIG_GUIDE.md](./guide/CONFIG_GUIDE.md) | **설정 전수 지도** — `server/config/*` 파일별 목적·소유·리로드 방식, 시나리오별 온보딩 체크리스트, 핫리로드/검증 규율, 함정 모음 |
| 🟢 [CONDA_SETUP_GUIDE.md](./guide/CONDA_SETUP_GUIDE.md) | Conda 환경 구성 |
| 🟢 [NATIVE_POSTGRES_SETUP_GUIDE.md](./guide/NATIVE_POSTGRES_SETUP_GUIDE.md) | PostgreSQL 설치 |
| 🟢 [POSTGRES_OPERATIONS_GUIDE.md](./guide/POSTGRES_OPERATIONS_GUIDE.md) | DB 운영 |
| 🟠 [SERVER_STARTUP_GUIDE.md](./guide/SERVER_STARTUP_GUIDE.md) | 서버 기동·성능 튜닝(인덱스/work_mem) |
| 🟢 [data_preservation_and_signature_change.md](./guide/data_preservation_and_signature_change.md) | 시그니처 변경·병합 보존 규율(SOP 필독) |
| 🟠 [spec/DEBUGGING_GUIDE.md](./spec/DEBUGGING_GUIDE.md) | 트러블슈팅 체크리스트 |

## 📜 5. 이력 & 개발 체계

| 문서 | 내용 |
|---|---|
| 🟢 [history/README.md](./history/README.md) | **자동 생성** 이력 인덱스. `python docs/history/gen_index.py`로 갱신(직접 편집 금지) |
| 🟢 [process/PRODUCTION_READINESS.md](./process/PRODUCTION_READINESS.md) | 프로덕션 게이트 — 차단/조건부/통과 판정과 근거 |
| 🟢 [process/CONTRIBUTING.md](./process/CONTRIBUTING.md) | 문서 갱신 규율 |
| 🟢 [process/DOC_OWNERSHIP.md](./process/DOC_OWNERSHIP.md) | 서브시스템 ↔ 문서 소유 매핑 |
| 🟢 [process/RELEASE_LOG.md](./process/RELEASE_LOG.md) | 릴리스 요약(Phase 번호 대체) |
| 🟢 [process/agentic_environment.md](./process/agentic_environment.md) | 멀티 에이전트 협업 체계(총괄 + 2 PM) |
| 🟢 [prompts/starting_prompt.md](./prompts/starting_prompt.md) | 총괄 PM 작업 헌장(SOP) + 조직 구조 |
| 🟢 [prompts/server_pm.md](./prompts/server_pm.md) | Server(백엔드) 도메인 PM 헌장 |
| 🟢 [prompts/client_pm.md](./prompts/client_pm.md) | Client(프론트엔드) 도메인 PM 헌장 |

## 🗄️ 6. 아카이브 (_archive/)

현실과 상충하게 되어 대체된 문서들로, **더 이상 유효하지 않습니다.** 히스토리 추적용으로만 보존됩니다: [_archive/](./_archive/) — 구 PySide6 시대 문서(`ASSY_MANAGER_BIBLE`, `TECHNICAL_GUIDE`, `ARCHITECTURE_ANALYSIS`, `CLIENT_FEATURE_CHECKLIST`) 및 `graph_db_integration_plan`(Kafka/Neo4j 구상 — ONTOLOGY_GRAPH_SPEC + PG materializer가 대체) 등.

---

*문서를 추가·변경할 때는 이 인덱스와 해당 문서의 Status 배지를 함께 갱신하십시오 → [process/CONTRIBUTING.md](./process/CONTRIBUTING.md)*
