# 시스템 주요 기능 명세

본 문서는 클라이언트 측의 주요 기능별 로직과 데이터 흐름을 다룹니다.
내용이 방대하여 기능 카테고리별로 상세 문서를 분리해 두었습니다. 디버깅 및 유지보수 시 하위 문서들을 적극 참고하십시오.

## 📂 상세 문서 목차
* [행(Row) 조작 가이드 (`docs/row_operations.md`)](docs/row_operations.md) - 행 삭제, 행 추가에 대한 깊이 있는 로직과 엣지 케이스 대응 방법
* [셀(Cell) 조작 가이드 (`docs/cell_operations.md`)](docs/cell_operations.md) - 단일 셀 수정, 다중 셀 붙여넣기 시 식별자(Row ID) 타겟팅 보호 메커니즘
* [뷰 제어 및 필터링 (`docs/view_filtering.md`)](docs/view_filtering.md) - 검색어 적용, 정렬 방식 전환에 따른 세션 ID 갱신과 캐시 폐기 전략
* [파일 인제션 처리 (`docs/file_ingestion.md`)](docs/file_ingestion.md) - 드래그 앤 드롭 및 다이얼로그 기반의 대용량 파일 업로드 시퀀스

---

## 📌 기능 요약 테이블

| 기능 | 주요 연관 함수 (Client) | 통신 엔드포인트 / 파라미터 | WebSocket 이벤트 | 비고 |
|---|---|---|---|---|
| **행 삭제** | `ExcelTableView.delete_selected_rows` | `DELETE /tables/{table_name}/rows/{row_id}`<br>`POST /target` (식별자 스캔용) | `batch_row_delete` | 뷰포트에 렌더링되지 않은 부분도 정확히 식별 및 삭제 요청 처리. |
| **행 일괄 추가** | `MainWindow._on_add_row_requested` | `POST /tables/{table_name}/rows?count={N}` | `batch_row_create` | 응답 없이 웹소켓으로만 결과를 수신해 모델의 상/하단에 실시간 삽입. |
| **단위 셀 변경** | `ApiLazyTableModel.setData` | `PUT /tables/{table_name}/rows` | `batch_row_upsert` | 엔터 입력 시 변경분만 단건 전송. |
| **여러 셀 복사/붙여넣기** | `ExcelTableView.paste_selection` | `PUT /tables/{table_name}/rows` | `batch_row_upsert` | 클립보드 매트릭스를 절대 좌표(`row_id`) 기반으로 매핑 후 일괄 수정(Bulk Update). |
| **정렬 모드 전환** | `MainWindow._on_sort_mode_changed` | `GET ?order_by=...&order_desc=...` | - | 전체 캐시 무효화 및 새로운 검색 세션(Session ID) 할당. |
| **검색 필터 적용** | `MainWindow._on_global_search` | `GET ?q={query}&cols={cols}` | - | 타이핑 레이턴시를 고려해 이전 응답을 쳐내는 세션 격리 아키텍처 사용. |
| **파일 인제션** | `MainWindow._execute_file_upload` | `POST /tables/{table_name}/upload` | `batch_row_create` | `multipart/form-data` 스트리밍 업로드 처리. |
