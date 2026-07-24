# 조직 구조 수립: 총괄 PM + 서버/클라이언트 도메인 PM 2인

## 현상 (Context)
단일 리드 PM 아래 기능별 에이전트(Excel/D/I)가 흩어져 있던 구조를, **서버·클라이언트 도메인별 PM 2인 + 총괄** 3계층으로 재편할 필요가 있었다. 핵심 동기는 서버-클라이언트가 공유하는 **경계 계약**(REST·WS·셀 형태·스키마)을 어느 한쪽이 단독으로 바꿔 파손시키는 사고를 조직 차원에서 차단하는 것.

## 조치 (Solution)

### 1. 도메인 PM 헌장 2종 신설
- `docs/prompts/server_pm.md` — `server/` 전 영역(API/CRUD·레이어링·인제션·체인·그래프·스케줄러·DB). 스킬: DataIngester, WebSocketExpert(서버측), IntegrityAndQAExpert.
- `docs/prompts/client_pm.md` — `client2/` + `desktop_wrapper.py`(그리드·클립보드·타임라인·어드민·맵에디터). 스킬: ExcelInteractionExpert, PanelUIExpert, WebSocketExpert(클라측).
- 각 헌장은 담당 범위·기준 리빙문서·도메인 규칙·**경계 계약(총괄 승인 필수)**·워크플로우를 정의.

### 2. 총괄 SOP 개정 (`starting_prompt.md` §0 신설)
- 리드 = **총괄 PM**으로 명확화. 3계층 조직도 + 총괄의 4대 책임(작업 분배·경계 계약 수호·통합 검증·문서 총괄)·도메인 PM 의무 명시.
- **경계 계약** 정의: REST 엔드포인트, WS 이벤트명(`batch_row_*`, `batch_refresh_required`), 셀 형태 `{value,is_overwrite,priority_source}`, 스키마 계약(`table_config.json`→`/schema`). 어느 PM도 단독 변경 불가 → 총괄이 양측 동시 조율.

### 3. 문서 동기화
- `docs/process/agentic_environment.md` §1을 신규 조직으로 재작성(구 Agent Excel/D/I의 PySide 자산 참조 제거), Status 🟢로 승격.
- `docs/README.md` 개발체계 섹션에 server_pm/client_pm 헌장 등록.

## 검증 (Validation)
- 헌장 상호 링크(총괄 SOP ↔ 두 PM ↔ StableDevelopmentProtocol ↔ 리빙 문서) 경로 확인.
- 히스토리 인덱스 재생성.

## 영향 (Impact)
작업이 도메인별로 명확히 위임되고, 서버-클라이언트 경계 계약은 총괄이 단일 창구로 수호한다. StableDevelopmentProtocol의 '의존성 안전' 가치가 조직 구조로 강제된다.
