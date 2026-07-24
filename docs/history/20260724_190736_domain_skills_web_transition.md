# 도메인 스킬 4종 웹(client2) 전환 정비

## 현상 (Context)
`.agents/skills/`의 도메인 스킬들이 구 PySide6 데스크톱 시대 기준(`QTableView`, `table_model.py`, `ApiLazyTableModel`, `QThread`, `QDockWidget`, `client/main.py`)으로 작성되어 있어, 에이전트가 실존하지 않는 파일·API를 참조하며 의존성 사고를 유발할 소지가 있었다. 메인 클라이언트는 이미 웹 `client2`(AG-Grid)로 전환됨.

## 조치 (Solution)
4종 도메인 스킬을 현행 아키텍처로 전면 재작성. 각 스킬 상단에 "현행 아키텍처" 경고 + 기준 리빙 문서 링크 + 상위 규율([[StableDevelopmentProtocol]]) 링크 추가.

- **ExcelInteractionExpert**: `QTableView`/`table_model.py` → `client2/src/clipboard.js`(범위선택·TSV), `api.js`/`ui.js`(배치), `grid.js`(셀 형태). 배치 API를 `PUT /tables/{t}/data/updates`로, Tx 스테이징(`pendingTxEdits`) 명시.
- **PanelUIExpert**: `QDockWidget`/`QSortFilterProxyModel` → `client2/src/timeline.js`(이력 타임라인·로그 점프), 서버 사이드 필터(`q`/`filters`/`order_by`), 검색 세션 가드.
- **WebSocketExpert**: `QThread`/`Signal`/`dataChanged` → 브라우저 WS(`client2/src/websocket.js`), AG-Grid `applyTransaction` 델타 반영, `BackgroundTasks` 브로드캐스트, 이벤트명 계약(`batch_row_*`) 보존.
- **DataIngester**: 잘못된 엔드포인트 `PUT /tables/{t}/cells/batch` → 정정 `PUT /tables/{t}/data/updates`. 파이프라인 파서/체인 맵퍼/스케줄러 3경로, `SOURCE_PRIORITY`(user:0<collision_merge:1<pipeline_parser:2<custom_script:3), 1000행 청킹·N+1 제거 명시.
- **SubAgentExecution R&R 표**: `table_model.py`/`ExcelTableView`/`WsListenerThread`/`advanced_ingester.py` → `client2/src/*`, `server/parsers`·`mappers` 등 현행 컴포넌트로 교체.

## 검증 (Validation)
- `.agents/skills` 전수 Grep: 남은 PySide6/QTableView/table_model 참조는 "~는 없습니다" 경고문 또는 실효성 있는 QA 체크리스트(IntegrityAndQAExpert, 잔여)뿐임을 확인.
- 히스토리 인덱스 재생성.

## 영향 (Impact)
모든 도메인 스킬이 웹 client2 실제 구현·엔드포인트·확장성 규칙을 가리키게 되어, 하위 에이전트가 실존 코드 기준으로 정확히 작업한다. (미정비 잔여: `IntegrityAndQAExpert` §3 QA 체크리스트의 PySide 항목 — 데스크톱 셸에 부분 유효하여 별도 판단 대상)
