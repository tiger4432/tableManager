# 🗂️ DOC_OWNERSHIP — 서브시스템 ↔ 문서 소유 매핑

> **Status:** 🟢 Living | **Last-verified:** 2026-07-26 | **Owner:** Lead / PM
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) · 규율: [CONTRIBUTING](./CONTRIBUTING.md)

각 서브시스템을 **어느 코드가 구현하고, 어느 문서가 설명하는지** 매핑합니다. 코드를 바꾸면 "문서" 열의 리빙 문서를 함께 갱신합니다([docs-as-code](./CONTRIBUTING.md#2-docs-as-code-갱신-규율)).

| 서브시스템 | 코드(진실 원천) | 리빙 문서 | Owner 역할 |
|---|---|---|---|
| 시스템 전체 | `run_decoupled_app.py`, `server/main.py` | [overview/SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) | Lead |
| 코드 구조 지도 | `server/*`, `client2/src/*` (전 모듈) | [architecture/CODE_MAP](../architecture/CODE_MAP.md) — 갱신·정합 감사 **doc-keeper 전담**(구현 에이전트는 보고서에 변경 함수 목록만) | 전 에이전트 공용 |
| 백엔드 API/워커 | `server/main.py`, `server/*_worker.py`, `server/run_*.py` | [architecture/backend](../architecture/backend.md) | Backend/Sync |
| 이벤트 기반(Outbox/EDA) | `server/database/database.py`, `chain_ingestion_worker.py`, `graph_sync_worker.py` | [architecture/event_driven_backend](../architecture/event_driven_backend.md) | Backend/Sync |
| 프론트엔드(웹+셸) | `client2/src/*`, `client/desktop_wrapper.py` | [architecture/frontend](../architecture/frontend.md) | UI/Excel |
| 데이터 모델/레이어링 | `server/database/models.py`, `crud.py` | [architecture/data_model](../architecture/data_model.md) | Backend/Integrity |
| 파일 인제션 파이프라인 | `parsers/directory_watcher.py`, `parsers/pipeline_base.py` | [guide/INGESTION_GUIDE](../guide/INGESTION_GUIDE.md) | Ingester |
| 체인 인제션 | `chain_ingestion_worker.py`, `mappers/` | [guide/chain_ingestion_guide](../guide/chain_ingestion_guide.md) | Ingester |
| Auto-Update 스케줄러 | `run_auto_update.py` | [guide/AUTO_UPDATE_GUIDE](../guide/AUTO_UPDATE_GUIDE.md) | Ingester |
| 웨이퍼 맵 에디터 | `client2/src/map_editor.js`, `utils/physical_wafer_engine.py`, `utils/coordinate_transformer.py` | [map_editor/](../map_editor/README.md), [spec/MAP_EDITOR_SPEC](../spec/MAP_EDITOR_SPEC.md) | UI/Map |
| 실시간 동기화(WS) | `client2/src/websocket.js`, `main.py` ConnectionManager | [spec/DATA_SYNC_SPEC](../spec/DATA_SYNC_SPEC.md) | Sync |
| 배치 업서트 | `crud.apply_batch_updates` | [spec/batch_update_technical_specification](../spec/batch_update_technical_specification.md) | Backend |
| 실패 관리/재시도 | `FileIngestionLog`, outbox retry, `admin/*` | [spec/FAILURE_MANAGEMENT_SPEC](../spec/FAILURE_MANAGEMENT_SPEC.md) | Integrity/QA |
| 온톨로지 그래프(materializer·엣지 스토어) | `graph_sync_worker.py`, `graph_materializer.py`, `ontology_config.py`, `config/ontology_mapping.json` | [architecture/event_driven_backend §4](../architecture/event_driven_backend.md)(승격 흐름), [spec/ONTOLOGY_GRAPH_SPEC](../spec/ONTOLOGY_GRAPH_SPEC.md)(트랙 스펙 — Owner 총괄) | Sync / 총괄 |
| 그래프 뷰어·추적 리포트 | `main.py /graph/*`, `client2/src/graph_viewer.js`, `trace.js`/`trace_core.js`/`trace_launch.js` | [architecture/frontend §6](../architecture/frontend.md) | UI / Sync |
| Enrichment Queue | `enrichment_config.py`, `enrichment_mapper.py`, `client2/src/enrichment.js` | [spec/ENRICHMENT_QUEUE_SPEC](../spec/ENRICHMENT_QUEUE_SPEC.md) | 총괄 |
| HTML 토폴로지 파서 | `parsers/html_topology_parser.py` | [guide/HTML_TOPOLOGY_PARSER_GUIDE](../guide/HTML_TOPOLOGY_PARSER_GUIDE.md) | Ingester |
| 어드민(파이프라인 5탭 + 코드 에디터) | `client2/src/admin.js`, `main.py /admin/*` | [architecture/frontend §5](../architecture/frontend.md) | UI/Panel |
| 설정 주도 스키마 | `config/table_config.json`, `database/config_watcher.py` | [architecture/data_model §5](../architecture/data_model.md) | Backend |
| **설정 전반(온보딩 지도)** | `server/config/*` 전체, `.gitignore` config 규칙 | [guide/CONFIG_GUIDE](../guide/CONFIG_GUIDE.md) — **config 파일 추가/폐지·리로드 경로 변경 시 필수 갱신**. 상세 동작은 각 서브시스템 가이드로 링크(중복 서술 금지) | Lead / Backend |
| 본딩·전사 계획 엔진(역할 바인딩) | `server/bonding_plan.py`, `server/transfer_plan.py`, `config/bonding_plan_config.json`, `config/transfer_plan_config.json` | [guide/CONFIG_GUIDE §3-S6](../guide/CONFIG_GUIDE.md)(설정 관점) · 엔진 스펙은 미작성 — 신설 시 이 행 갱신 | Backend / UI-Map |
| QA 기능 점검 | 전 서브시스템(사용자 관점 기능 단위) | [qa/FEATURE_CHECKLIST](../qa/FEATURE_CHECKLIST.md) — 갱신은 doc-keeper 전담(코드맵과 같은 사이클) | Integrity/QA |
| 운영/셋업 | 환경·DB | [guide/*_SETUP_GUIDE](../guide/CONDA_SETUP_GUIDE.md) | Ops |
| 엔지니어링 규율 | CRUD 시그니처·병합 | [guide/data_preservation_and_signature_change](../guide/data_preservation_and_signature_change.md) | Integrity/QA |

> 에이전트 역할 정의는 [prompts/starting_prompt](../prompts/starting_prompt.md) §5 및 `.agents/skills/` 참조.
