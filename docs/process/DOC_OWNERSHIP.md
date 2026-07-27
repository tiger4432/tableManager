# 🗂️ DOC_OWNERSHIP — 서브시스템 ↔ 문서 소유 매핑

> **Status:** 🟢 Living | **Last-verified:** 2026-07-27 (운영 감시·격리 환경·제품 테이블 배포·PRIMITIVES 매핑 추가) | **Owner:** Lead / PM
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) · 규율: [CONTRIBUTING](./CONTRIBUTING.md)

각 서브시스템을 **어느 코드가 구현하고, 어느 문서가 설명하는지** 매핑합니다. 코드를 바꾸면 "문서" 열의 리빙 문서를 함께 갱신합니다([docs-as-code](./CONTRIBUTING.md#2-docs-as-code-갱신-규율)).

| 서브시스템 | 코드(진실 원천) | 리빙 문서 | Owner 역할 |
|---|---|---|---|
| 시스템 전체 | `run_decoupled_app.py`, `server/main.py` | [overview/SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) | Lead |
| **재사용 가능한 연산·패턴 카탈로그** | (전 모듈에서 추출한 개념) | [architecture/PRIMITIVES](../architecture/PRIMITIVES.md) — **유지 doc-keeper 전담**. 정비 사이클마다 신규 프리미티브 추가·소멸분 삭제 | 전 에이전트 공용 |
| **프로세스 감시·헬스** | `server/process_supervisor.py`, `server/health.py`, `server/utils/heartbeat.py`, `run_decoupled_app.py` | [architecture/backend §1.3](../architecture/backend.md) · 게이트 판정은 [process/PRODUCTION_READINESS](./PRODUCTION_READINESS.md) | Backend / Ops |
| **데이터 루트·격리 환경** | `server/paths.py`, `server/scripts/dev_env/devenv.py`, `iso_watcher.py` | [guide/DEPLOY_SETUP §5](../guide/DEPLOY_SETUP.md) · 설정 관점은 [guide/CONFIG_GUIDE §1](../guide/CONFIG_GUIDE.md) | Backend / Ops |
| **제품 소유 테이블 배포** | `server/product_tables.py`(단일 정의), `server/scripts/install_product_tables.py` | [guide/DEPLOY_SETUP §1-2](../guide/DEPLOY_SETUP.md) · [guide/CONFIG_GUIDE §5.8-ter](../guide/CONFIG_GUIDE.md) | Lead / Backend |
| **프로덕션 게이트** | (전 서브시스템 — 운영 관점) | [process/PRODUCTION_READINESS](./PRODUCTION_READINESS.md) — 차단 항목 해소 시 갱신 | Lead |
| DOE 저장 분해도 | `client2/src/map_editor.js`(legend 저장 = 유일한 기록자), `client2/src/transfer_plan.js`(읽기·파생), `server/transfer_plan.py`, `map_split_registry` | 현행 계약은 [spec/MAP_EDITOR_SPEC §6](../spec/MAP_EDITOR_SPEC.md) · [guide/CONFIG_GUIDE §5.8](../guide/CONFIG_GUIDE.md). [spec/DOE_STORAGE_MAP](../spec/DOE_STORAGE_MAP.md)은 🗄️ **폐기된 3테이블 모델**로, 기존 데이터 해석용으로만 보존(M2.6 양측 착지 `cdcddee`+`0f8d35f`) | UI/Map |
| 코드 구조 지도 | `server/*`, `client2/src/*` (전 모듈) | [architecture/CODE_MAP](../architecture/CODE_MAP.md) — 갱신 **code-mapper 전담**, 정합 감사 **doc-auditor 전담**(2026-07-27 분할. 구현 에이전트는 보고서에 변경 함수 목록만) | 전 에이전트 공용 |
| 백엔드 API/워커 | `server/main.py`, `server/*_worker.py`, `server/run_*.py` | [architecture/backend](../architecture/backend.md) | Backend/Sync |
| 이벤트 기반(Outbox/EDA) | `server/database/database.py`, `chain_ingestion_worker.py`, `graph_sync_worker.py` | [architecture/event_driven_backend](../architecture/event_driven_backend.md) | Backend/Sync |
| 프론트엔드(웹+셸) | `client2/src/*`, `client/desktop_wrapper.py` | [architecture/frontend](../architecture/frontend.md) | UI/Excel |
| 데이터 모델/레이어링 | `server/database/models.py`, `crud.py` | [architecture/data_model](../architecture/data_model.md) | Backend/Integrity |
| 파일 인제션 파이프라인 | `parsers/directory_watcher.py`, `parsers/pipeline_base.py` | [guide/INGESTION_GUIDE](../guide/INGESTION_GUIDE.md) | Ingester |
| 체인 인제션 | `chain_ingestion_worker.py`, `mappers/` | [guide/chain_ingestion_guide](../guide/chain_ingestion_guide.md) | Ingester |
| Auto-Update 스케줄러 | `run_auto_update.py` | [guide/AUTO_UPDATE_GUIDE](../guide/AUTO_UPDATE_GUIDE.md) | Ingester |
| 웨이퍼 맵 에디터 | `client2/src/map_editor.js`, `utils/physical_wafer_engine.py`, `utils/coordinate_transformer.py` | [map_editor/](../map_editor/README.md), [spec/MAP_EDITOR_SPEC §1~§4](../spec/MAP_EDITOR_SPEC.md) | UI/Map |
| 파일 인제션 체크포인트·dedup(P2) | `server/ingestion_checkpoint.py`, `models.FileIngestionCheckpoint`, `config/ingestion_settings.json` | [guide/INGESTION_GUIDE §1.8](../guide/INGESTION_GUIDE.md) | Ingester |
| 실시간 동기화(WS) | `client2/src/websocket.js`, `main.py` ConnectionManager | **현행 서술은 [architecture/frontend §3](../architecture/frontend.md)**. [spec/DATA_SYNC_SPEC](../spec/DATA_SYNC_SPEC.md)은 ⚪ 폐기된 PySide6 클라 기준이라 **구현 서술을 신뢰하지 말 것**(무결성 가드의 *문제* 서술만 유효) | Sync |
| 배치 업서트 | `crud.apply_batch_updates` | [spec/batch_update_technical_specification](../spec/batch_update_technical_specification.md) | Backend |
| 실패 관리/재시도 | `FileIngestionLog`, outbox retry, `admin/*` | [spec/FAILURE_MANAGEMENT_SPEC](../spec/FAILURE_MANAGEMENT_SPEC.md) | Integrity/QA |
| 온톨로지 그래프(materializer·엣지 스토어) | `graph_sync_worker.py`, `graph_materializer.py`, `ontology_config.py`, `config/ontology_mapping.json` | [architecture/event_driven_backend §4](../architecture/event_driven_backend.md)(승격 흐름), [spec/ONTOLOGY_GRAPH_SPEC](../spec/ONTOLOGY_GRAPH_SPEC.md)(트랙 스펙 — Owner 총괄) | Sync / 총괄 |
| 그래프 뷰어·추적 리포트 | `main.py /graph/*`, `client2/src/graph_viewer.js`, `trace.js`/`trace_core.js`/`trace_launch.js` | [architecture/frontend §6](../architecture/frontend.md) | UI / Sync |
| Enrichment Queue | `enrichment_config.py`, `enrichment_mapper.py`, `client2/src/enrichment.js` | [spec/ENRICHMENT_QUEUE_SPEC](../spec/ENRICHMENT_QUEUE_SPEC.md) | 총괄 |
| HTML 토폴로지 파서 | `parsers/html_topology_parser.py` | [guide/HTML_TOPOLOGY_PARSER_GUIDE](../guide/HTML_TOPOLOGY_PARSER_GUIDE.md) | Ingester |
| 어드민(파이프라인 5탭 + 코드 에디터) | `client2/src/admin.js`, `main.py /admin/*` | [architecture/frontend §5](../architecture/frontend.md) | UI/Panel |
| 설정 주도 스키마 | `config/table_config.json`, `database/config_watcher.py` | [architecture/data_model §5](../architecture/data_model.md) | Backend |
| **설정 전반(온보딩 지도)** | `server/config/*` 전체, `.gitignore` config 규칙 | [guide/CONFIG_GUIDE](../guide/CONFIG_GUIDE.md) — **config 파일 추가/폐지·리로드 경로 변경 시 필수 갱신**. 상세 동작은 각 서브시스템 가이드로 링크(중복 서술 금지) | Lead / Backend |
| **범용 맵 오버레이(맵 인프라)** | `client2/src/map_editor.js`(오버레이 레이어 — **좌표 변환의 정본**), `server/map_overlay.py`, `config/map_overlay_config.json` | [spec/MAP_EDITOR_SPEC §5](../spec/MAP_EDITOR_SPEC.md)(정렬 계약 — 도메인 규칙 §5.0 / 클라 파이프라인 §5.1 / 서버 계약 §5.2) · [guide/CONFIG_GUIDE §5.8-bis](../guide/CONFIG_GUIDE.md)(설정 관점) | Backend / UI-Map |
| 맵 정렬 메타(`wafer_map_metadata`) | `server/map_overlay.load_map_meta`, `client2/src/map_editor.js`(`fetchGridMetaFor`/`frameFromMeta`), `config/table_config.json` | [spec/MAP_EDITOR_SPEC §5.0](../spec/MAP_EDITOR_SPEC.md)(정렬의 유일한 기준) · [map_editor/architecture_and_management §2](../map_editor/architecture_and_management.md)(스키마·필드 규격) | Backend / UI-Map |
| 본딩·전사 계획 엔진(역할 바인딩) | `server/bonding_plan.py`, `server/transfer_plan.py`, `client2/src/transfer_plan.js`, `config/bonding_plan_config.json`, `config/transfer_plan_config.json` | [spec/MAP_EDITOR_SPEC §6](../spec/MAP_EDITOR_SPEC.md)(엔진·클라 계약) · [guide/CONFIG_GUIDE §3-S6](../guide/CONFIG_GUIDE.md)(설정 관점) | Backend / UI-Map |
| QA 기능 점검 | 전 서브시스템(사용자 관점 기능 단위) | [qa/FEATURE_CHECKLIST](../qa/FEATURE_CHECKLIST.md) — 갱신은 doc-keeper 전담. 정합 감사는 doc-auditor | Integrity/QA |
| 운영/셋업 | 환경·DB | [guide/*_SETUP_GUIDE](../guide/CONDA_SETUP_GUIDE.md) | Ops |
| 엔지니어링 규율 | CRUD 시그니처·병합 | [guide/data_preservation_and_signature_change](../guide/data_preservation_and_signature_change.md) | Integrity/QA |

> 에이전트 역할 정의는 [prompts/starting_prompt](../prompts/starting_prompt.md) §5 및 `.agents/skills/` 참조.
