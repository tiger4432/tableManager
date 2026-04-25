# 행(Row) 조작

## 1. 행 삭제 (Row Deletion)
### 📍 트리거 포인트
`ExcelTableView.delete_selected_rows()` (단축키: `Delete` 또는 우클릭 컨텍스트 메뉴)

### ⚙️ 동작 방식
1. **인덱스 추출 및 변환**: `proxy_model.mapToSource`를 사용하여 정렬/필터링 상태에 관계없이 정확한 소스 모델의 인덱스와 `row_id`를 추출합니다.
2. **로컬 및 가상 데이터 분류**: 현재 뷰포트에 로드된 행과 로드되지 않은 행(None)을 분리합니다.
3. **가상 식별자 스캔 (Targeted RowID Scanner)**: 아직 로드되지 않은 행이 선택 영역에 포함된 경우, `ApiTargetedRowIdWorker`를 구동하여 백그라운드에서 해당 오프셋의 고유 식별자(`row_id`)를 스캔합니다.
4. **API 호출**: 식별자가 모두 확보되면 `ApiDeleteWorker`를 통해 일괄 삭제 API(`DELETE /tables/{table_name}/rows/{row_id}` 등)를 호출합니다.
5. **UI 동기화**: 서버 응답 후 WebSocket을 통해 `batch_row_delete` 이벤트가 브로드캐스트되면, 각 클라이언트의 `_on_websocket_broadcast`가 이를 수신하여 캐시된 데이터를 최적화된 방식으로 도려내고 화면을 업데이트합니다.

## 2. 행 일괄 추가 (Row Addition)
### 📍 트리거 포인트
`MainWindow._on_add_row_requested()` (툴바 `+ 행 추가` 버튼)

### ⚙️ 동작 방식
1. `QInputDialog.getInt`를 통해 사용자로부터 생성할 빈 행의 개수를 입력받습니다 (1~10,000).
2. 파라미터(`count`, `user_name`)를 URL에 포함하여 서버의 행 일괄 생성 API(`POST /tables/{table_name}/rows`)를 호출합니다.
3. 서버가 생성된 행들을 반환하지 않고, 처리 완료 후 WebSocket을 통해 `batch_row_create` 이벤트로 브로드캐스트합니다.
4. 모든 클라이언트는 해당 이벤트를 수신하고, 정렬 기준(`_sort_latest` 여부)에 따라 최상단 또는 최하단에 새 행들을 `beginInsertRows`와 함께 삽입하여 UI를 실시간으로 갱신합니다.
