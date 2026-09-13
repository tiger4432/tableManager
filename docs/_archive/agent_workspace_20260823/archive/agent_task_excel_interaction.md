# 하위 에이전트 작업 지시서: 엑셀형 다중 셀 조작 및 배치 처리 구현

**역할**: UI 상호작용 및 통신(소켓) 전담 에이전트
**대상 파일**: `client/models/table_model.py`, `client/main.py`
**목표**: QTableView를 엑셀처럼 직관적으로 조작할 수 있도록 다중 복사/붙여넣기(`Ctrl+C / Ctrl+V`) 기능을 추가하고, 서버 과부하를 막는 배치(Batch) API로 연동하라.

---

## 📋 핵심 구현 플랜 및 요구사항

### 1. 키보드 이벤트 후킹 (keyPressEvent)
- **요구사항**: `client/main.py` 내부의 `QTableView` 객체 서브클래싱 또는 `installEventFilter` 등을 사용하여 사용자의 단축키 입력(`Qt.Key_C`, `Qt.Key_V`)을 가로채라.
- **클립보드 저장(Copy)**: 여러 셀을 드래그한 상태(`selectionModel().selectedIndexes()`)로 Ctrl+C를 누르면, 탭(`\t`)과 줄바꿈(`\n`) 단위의 TSV 형식으로 문자열 판별 후 `QApplication.clipboard().setText()`로 담아라.

### 2. 다중 데이터 파싱 및 Batch 텍스트 렌더링
- **붙여넣기(Paste)**: 사용자가 `Ctrl+V` 이벤트 발동 시, `QApplication.clipboard().text()`를 TSV로 파싱하라.
- 파싱된 2차원 배열과, 현재 포커스된 `currentIndex()` (붙여넣기 좌상단 기점)를 기반으로 `ApiLazyTableModel`에 업데이트할 목록을 만들어라.

### 3. 배치 전송 워커 (ApiBatchUpdateWorker)
- **과부하 방지 규칙**: B 에이전트 초안처럼 포 루프 안에서 `setData` 네트워킹을 무수히 실행하면 대형 서버 크래시가 발생하므로 절대 금지.
- **로직 작성**:
  1. 붙여넣을 셀들의 위치(종합)와 매칭되는 `row_id`, 업데이트될 `column_name`, `value`를 리스트 딕셔너리로 추출.
  2. 서버 측 미리 지정된 다중 셀 일괄 업데이트 전용 엔드포인트 **`PUT /tables/{table_name}/cells/batch`**를 향해 다음과 같은 페이로드 스트링으로 네트워크 발송하는 비동기 워커(`QRunnable`)를 구동할 것:
    ```json
    {
      "updates": [
        {"row_id": "uuid-1", "column_name": "name", "value": "New Data 1"},
        {"row_id": "uuid-2", "column_name": "status", "value": "MANUAL_FIX"}
      ]
    }
    ```
  3. 성공(`status: success`) 신호가 떨어지면 `QAbstractTableModel` 내부 캐시 `self._data`를 루프 돌려 변경된 영역만 한 번에 일괄 업데이트(`dataChanged` 시그널 범위 지정)하라.
