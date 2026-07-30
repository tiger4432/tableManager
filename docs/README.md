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
| 🟢 [process/CONTRIBUTING.md](./process/CONTRIBUTING.md) | **개발·문서 갱신 규율(docs-as-code)** — 코드 바꾸면 여기 규칙대로. **§2-bis = 이 저장소가 자기를 검증하는 자리**(pytest = 서버 절반 · `npm run build` = 계약의 클라 절반, 둘 다 돌려야 한다) |
| 🟢 [guide/CONFIG_GUIDE.md](./guide/CONFIG_GUIDE.md) | **"무엇을 설정해야 하는가" 단일 참조** — config 전수 지도 + 시나리오별 체크리스트(새 테이블/맵/수집기/그래프 온보딩) |

## 🏛️ 2. 아키텍처 (architecture/)

| 문서 | 내용 |
|---|---|
| 🟢 [PRIMITIVES.md](./architecture/PRIMITIVES.md) | **기능→구현 카탈로그** — *무엇을 할 줄 아나*. CODE_MAP이 *어디에 있나*라면 이쪽은 재사용 가능한 연산·패턴과 그 함정 |
| 🟢 [CODE_MAP.md](./architecture/CODE_MAP.md) | **압축 구조 지도** — 파일별 시그니처·라인 앵커·호출 흐름. 소스 전량 읽기 전에 여기부터 |
| 🟢 [backend.md](./architecture/backend.md) | 5-프로세스 토폴로지, API 엔드포인트, outbox 패턴, **프로세스 감시·`/health`·진행 박동(§1.3)** · **그래프 조회 표에 `GET /graph/chip-trace` 등재**(2026-07-30 — depth 없는 고정 형상 · 다리별 닫힌 어휘 5종 + `scope_unresolved` · 절단은 상태가 아니라 플래그) |
| 🟢 [frontend.md](./architecture/frontend.md) | client2 웹(AG-Grid) + QtWebEngine 데스크톱 셸 · **§2.1 빌드 게이트**(`npm run build`의 `prebuild`가 계약 하네스 4종을 돌린다 — 발견식 스캔, **빈 스캔은 실패**) |
| 🟢 [data_model.md](./architecture/data_model.md) | ORM 모델 + 동적 테이블 + 레이어링/우선순위 |
| 🟢 [event_driven_backend.md](./architecture/event_driven_backend.md) | Outbox 패턴 · 체인 인제션 · 온톨로지 그래프 승격(materializer) 심화 |

## 🧩 3. 서브시스템 리빙 가이드

| 서브시스템 | 문서 |
|---|---|
| 파일 인제션 파이프라인 | 🟢 [guide/INGESTION_GUIDE.md](./guide/INGESTION_GUIDE.md) |
| 체인 인제션(DB세션 맵퍼) | 🟢 [guide/chain_ingestion_guide.md](./guide/chain_ingestion_guide.md) |
| Auto-Update 스케줄러 | 🟢 [guide/AUTO_UPDATE_GUIDE.md](./guide/AUTO_UPDATE_GUIDE.md) — 주석 기반 크론 · `out` 변수 가로채기 · 수집기별 Active 토글 · **이 데몬이 도는 「수집기가 아닌 일」 2건**: §4-bis 주간 config 스냅샷 · **§4-ter 그래프 고아 노드 스윕**(2026-07-30 — 요점은 삭제가 아니라 **거절**: 선언에 거부가 하나라도 있으면 전체를 거절한다) |
| 웨이퍼 맵 에디터 | 🟢 [map_editor/](./map_editor/README.md) · [spec/MAP_EDITOR_SPEC.md](./spec/MAP_EDITOR_SPEC.md) — §1~§4 격자 에디터, **§4-ter 회사 양식 왕복**(COPY HEADER MODE ↔ **Ctrl+V** · 왕복 항등 INV-F1ⓑ-1 · 평문을 읽는 대가 = 병합 관례 · 그룹 띠는 **의도적 미판독**이라 자재·COLOR는 왕복 안 함 · **노치 `D`의 세 역할** · 거부 **다섯** 갈래 — ⚠️ **지문 부재는 거부이고 선언 맵 179개 중 27개만 지문을 갖는다**(2026-07-30 `ae2811c` — 나머지 152개에서 왕복 미성립, 양식 후속은 대기열) · **붙여넣기는 값을 지우지 않는다** · 로스터 13개와 롤업 8단어의 **예비 지위**), **§5 범용 맵 오버레이**(**`wafer_map_metadata`가 정렬의 유일한 기준** · 변환은 클라 단일 구현 · **좌표 바인딩도 서버가 해석해 서빙**(§5.6-bis — 추측은 `fallback_guess` 표지 없이 나가지 않는다) · 맵 정체성은 **선언 타입으로 캐노니컬화**해 조합(§5.0) · 실패 status **4종** · 선언 오버라이드 레이어는 2026-07-27 폐지 · **§5.7-bis 프레임 채택**(참조 맵 크기로 격자를 열되 **저장 좌표가 움직이면 거절** — 치수 변경은 물리 키 불변이 아니다) · **§5.8 로드 시 프리셋 라우팅**(**`wafer_map_metadata` > 라우팅 > 패널**을 서버가 강제, 조회 miss는 **정상 경로**) + **§5.8-bis 클라 절반 착지**(모달보다 앞에서 패널을 정한다 — §4-bis.3 모달은 폐기되지 않음)), **§6 전사 계획**(「계획 = 그 맵 자체」·신뢰 표기 3층 방어 · **선언된 미추적 소비 `transfer_log: "none"`은 §6.2-bis** · 저장소는 `map_split_registry` 한 테이블 · **층 구조는 zone 모델**(STACK+1H/MID/TOP, STACK 0=마커) — 🗄️ `bands` JSON은 폐기·읽기 전용 · 저장을 막는 **데이터 보호 게이트 4종은 §6.0-ter** · **§6.1-ter 파생 컬럼의 갱신 트리거**(정체 변화와 **서버 재독**은 다른 질문 · 존재 캐시는 **긍정 답만**)) |
| DOE 작성 가이드(사용자) | 🟢 [guide/DOE_GUIDE.md](./guide/DOE_GUIDE.md) — 색칠=계획 · STACK 0=상태 표시 · 저장은 ⚡ Push 하나 · 검수는 보고만(막는 건 **게이트 4종**) · **수량은 「저장되는 셀」만 센다**(2026-07-30 — Fill All을 쓴 맵은 숫자가 내려감, §9에 감소폭 표) · 엑셀 계약 밖 칸은 **13단어**(COLOR·칠함·COUNT + 롤업 8단어는 **예비**) · **§4.2 맵 화면 Ctrl+V로 회사 양식 되붙이기**(VALUE·STACK·DESC만 복원, 자재·COLOR는 왕복 안 함, **값을 지우지 않음**) — ⚠️ **§4.2에 거부 안내 신설**: 거부는 시트가 아니라 **맵의 기하** 때문이고 **179개 중 27개에서만 왕복이 성립**한다 · **§6.1 `MAP X`는 `↻ 가용` 없이도 풀린다**(맵 로드·Push 성공·STACK 마커 경계 편집이 자동 재확인 — `✓`는 다시 묻지 않고 `X`/`?`만 다시 묻는다) |
| 유효 다이 맵 가이드(사용자) | 🟢 [guide/VALID_DIE_MAP_GUIDE.md](./guide/VALID_DIE_MAP_GUIDE.md) — **유효 다이도 맵이다** · 원으로 표현 못 하는 테이프 모양 · 프리셋 목록의 「🧩 템플릿 만들기」로 저작 → ⚡ Push → 다른 맵의 「🎯 유효 다이 맵」 칸에 키 지정 → ⚡ Push · 참조는 1단계 · 키 비우면 원 복귀 · **§4-bis 격자 크기가 다를 때**(2026-07-30 — 빈 화면이면 **템플릿 크기로 열리고**, 칠해진 셀이 있으면 **거절**한다: 격자 크기가 저장 좌표를 옮기고 그것은 화면으로 알아챌 수 없다. 복구는 **격자 맞춤 → 📂 Load → Push** 3단계) · §8 = **Fill All 필터는 착지**, 오염된 초안 정리는 진행 중 |
| DOE 구간 모델(부분 폐기) | 🟠 [spec/DOE_BAND_MODEL.md](./spec/DOE_BAND_MODEL.md) — 구간(band) 모델 본문은 zone 모델로 대체(🗄️), **§4-bis BIN 축·§6-bis BIN별 분해는 계속 정본** |
| DOE 영역 저장 지도 | 🗄️ [spec/DOE_STORAGE_MAP.md](./spec/DOE_STORAGE_MAP.md) — **본문은 폐기된 3테이블 모델**이며 기존 데이터 해석용으로만 보존합니다. M2.6이 양쪽 다 착지해(`cdcddee`+`0f8d35f`) 지금은 `map_split_registry` **한 테이블**입니다 → 현행 계약은 [MAP_EDITOR_SPEC §6](./spec/MAP_EDITOR_SPEC.md)·[CONFIG_GUIDE §5.8](./guide/CONFIG_GUIDE.md) |
| HTML 토폴로지 파서 | 🟢 [guide/HTML_TOPOLOGY_PARSER_GUIDE.md](./guide/HTML_TOPOLOGY_PARSER_GUIDE.md) |
| 배치 업서트 | 🟠 [spec/batch_update_technical_specification.md](./spec/batch_update_technical_specification.md) |
| 실시간 동기화 | 🟢 **현행 정본은 [architecture/frontend §3·§3.1](./architecture/frontend.md)** — 모듈 구조 + **무결성 3문제**(중복 행·늦은 응답 오염·`total` 드리프트). 🗄️ [spec/DATA_SYNC_SPEC.md](./spec/DATA_SYNC_SPEC.md)은 **폐기된 PySide6 클라 기준이고 §3 문제 서술도 2026-07-27 이관 완료** — **남은 유효 내용 0, 아카이브 대기**(SSOT 링크 정리 후 총괄이 이관). 인용하지 말 것 |
| 실패 관리/재시도 | 🟢 [spec/FAILURE_MANAGEMENT_SPEC.md](./spec/FAILURE_MANAGEMENT_SPEC.md) |
| 비즈니스 로직/레이어링 | 🟠 [spec/BUSINESS_LOGIC_SPEC.md](./spec/BUSINESS_LOGIC_SPEC.md) |
| Enrichment Queue(결손 보정 워크리스트) | 🟢 [spec/ENRICHMENT_QUEUE_SPEC.md](./spec/ENRICHMENT_QUEUE_SPEC.md) |
| 온톨로지 지식그래프(LLM 백본) | 🟢 [spec/ONTOLOGY_GRAPH_SPEC.md](./spec/ONTOLOGY_GRAPH_SPEC.md) — **G1+뷰어+G2 라이브 가동으로 §1~§6 실증**(2026-07-25 Living 승격). §7.x는 G3+ 설계(§7.5c 탐색 정책은 G2.5 전제). **§3 매핑 예제는 「셀 체인」이 정본**(2026-07-30 `aea4700` — `CoreCell(core_lot,core_slot,cx,cy)`가 두 로그의 행 노드 · `BONDED_TO→BaseCell` · `TRANSFERRED_TO→DtCell` · `FROM_CORE→Core` · **좌표는 엣지 props가 아니라 identity 안에**. 🗄️ 폐기 형태 `Chip`/`log_id`/`BONDED_FROM→Wafer`/`PLACED_ON→Base`) · **§7.5d 칩 추적 API**(`GET /graph/chip-trace` — depth 없는 고정 형상, **다리별 닫힌 어휘로 빈 홉을 금지**: `mapping_unavailable`("읽지 못했다" ≠ "옮겨갔다")·`not_reached`("묻지 않았다")) · **§7.5e 선언 변경의 전파와 잔여물**(재동기화가 `SYSTEM_RELOAD`를 직접 발행 · 고아 스윕은 **깨끗하지 않은 선언 앞에서 전체를 거절** · `mapping-summary`의 `rejected[]`). 승격 흐름 요약: [event_driven_backend §4](./architecture/event_driven_backend.md) |
| API 레퍼런스 | 🟠 [spec/api_documentation.md](./spec/api_documentation.md) |

## ✅ 3.5 QA (qa/)

| 문서 | 내용 |
|---|---|
| 🟢 [qa/FEATURE_CHECKLIST.md](./qa/FEATURE_CHECKLIST.md) | **기능 인벤토리 + QA 수동 점검 체크리스트** — 서브시스템별 기능 지도·진입 경로·릴리스 전 회귀 점검 절차(SLO·멱등성 포함). **§2.0 자동 게이트**(pytest + `npm run build` — 손으로 점검하기 전에 통과시킬 것) · **§1.11/§2.15 운영 감시**(감시자·`/health`·격리 환경) 포함. **2026-07-30 신설 5행** — §1.7 유효 다이 맵(M4) · §1.9 **칩 추적**·재동기화 알림·**고아 스윕** · §1.10 **셸의 서버 주소 해석**. 새 기능 병합 시 doc-keeper가 갱신 |

## 🛠️ 4. 운영 & 셋업 (guide/)

| 문서 | 내용 |
|---|---|
| 🟢 [DEPLOY_SETUP.md](./guide/DEPLOY_SETUP.md) | **"내가 무엇을 채워야 하는가"** — 새 환경 배포 요약(제품 소유 vs 현장 소유, 제품 테이블 설치 스크립트, **격리 개발·검증 환경 §5**, 기동 후 `/health` 확인) |
| 🟢 [ROLLBACK_PROCEDURE.md](./guide/ROLLBACK_PROCEDURE.md) | **배포를 되돌리는 법** — 코드·config·스키마의 반영 시점이 다르다는 전제 위의 절차. 순서(`config → 코드 → 재기동`)·재기동 대상 5개·`/health`의 사각·**남는 물리 스키마**. 2026-07-28 격리 스택 드릴 실측 포함 |
| 🟢 [process/PRODUCTION_READINESS.md](./process/PRODUCTION_READINESS.md) | **프로덕션 게이트** — 무엇이 아직 막고 있는가(차단/조건부/통과 + 근거). 배포 판단은 여기서 |
| 🟢 [CONFIG_GUIDE.md](./guide/CONFIG_GUIDE.md) | **설정 전수 지도** — `server/config/*` 파일별 목적·소유·리로드 방식, 시나리오별 온보딩 체크리스트, 핫리로드/검증 규율, 함정 모음 |
| 🟢 [config/](./guide/config/README.md) | **파일별 세팅 절차** — config 파일당 가이드 1개(언제 만지나·세팅 절차·반영 확인·복구·키 사전). 운영 서버에서 실제로 세팅할 때는 여기부터 |
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
