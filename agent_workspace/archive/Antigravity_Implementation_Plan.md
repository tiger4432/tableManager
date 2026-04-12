# QTableView Copy/Paste 기능 구현

QTableView를 엑셀처럼 조작할 수 있도록 다중 행/열 선택 드래그, 그리고 시스템 클립보드를 통한 Ctrl+C / Ctrl+V 기능을 지원합니다.

## Proposed Changes

---
### Client UI
#### [MODIFY] client/main.py
- QTableView에 이벤트 필터(`eventFilter`)를 추가하여 `keyPressEvent`를 후킹합니다.
- 복사(Ctrl+C): 현재 영역(`table_view.selectionModel().selectedIndexes()`)을 가져와 행/열 크기에 맞춰 정렬 후 TSV 포맷(탭 분리) 문자열로 만든 다음 `QApplication.clipboard().setText()`로 설정합니다.
- 붙여넣기(Ctrl+V): `QApplication.clipboard().text()`에서 텍스트를 읽고 TSV를 파싱합니다. 붙여넣을 데이터 배열(JSON 형태)로 조합하고, 개별 `setData` 호출을 피하며 모델의 `bulkUpdateData` 메서드 한 번으로 전달합니다.

---
### Table Model
#### [MODIFY] client/models/table_model.py
- `ApiLazyTableModel`에 `bulkUpdateData(start_row, start_col, parsed_data_matrix)` 메서드를 추가합니다.
- 동작 흐름:
  1. 셀 배치 데이터를 한 번에 묶어서(JSON Array 객체 형태) **Batch Update API**에 단 1번 네트워크 전송을 수행합니다 (예: `POST /tables/{table_name}/batch_update` 또는 주어진 엔드포인트). QThreadPool 기반 또는 asyncio 등을 활용하여 메인 스레드를 블로킹하지 않습니다.
  2. 서버 응답이 성공(Success)으로 돌아오면, 그때 모델의 `self._data`를 메모리 상에서만 일괄 덮어씁니다. (`is_overwrite=True` 등 속성 설정)
  3. 모든 메모리 갱신이 끝난 후, 최상단 index부터 최하단 index에 대해 `dataChanged` 시그널을 **딱 한 번만 방출**하여 렌더링을 최적화합니다.

## Verification Plan

### Manual Verification
- 클라이언트에서 엑셀 형식 데이터를 클립보드에서 여러 셀에 붙여넣었을 때 Batch Update API가 단 1회 호출되는지 응답/로그를 통해 확인합니다.
- API 성공 응답 수신 후 뷰어(UI)가 한 번에 끊김 없이 전부 업데이트되는지 시각적으로 확인합니다.
