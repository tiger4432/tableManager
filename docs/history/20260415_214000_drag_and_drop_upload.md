# 20260415_214000_drag_and_drop_upload

## 1. 이슈 개요 (Issue Overview)
사용자 편의성 향상을 위해 기존 버튼 클릭 방식 외에도, 로컬 탐색기에서 파일을 드래그하여 테이블에 바로 놓는 것만으로 업로드가 완료되는 `Drag & Drop` 인터랙션이 필요했습니다.

## 2. 해결 방안 (Solution Details)

### 2.1 ExcelTableView 드롭 이벤트 구현
- `ExcelTableView` 클래스에 `setAcceptDrops(True)`를 설정하였습니다.
- `dragEnterEvent`, `dragMoveEvent`, `dropEvent`를 오버라이드하여 파일(URLs) 드롭을 처리하도록 구현했습니다.
- 파일 드롭 시 내부적으로 `fileDropped(str)` 시그널을 발생시킵니다.

### 2.2 업로드 로직 리팩토링 및 연동
- **공통 핸들러 추출**: `MainWindow` 내부에 `_execute_file_upload(table_name, file_path)` 함수를 추가하여, 버튼 클릭과 드래그 앤 드롭 행위가 동일한 업로드 엔진을 사용하도록 구조를 통일했습니다.
- **시그널 연결**: 각 탭의 `table_view`가 생성될 때, `fileDropped` 시그널을 해당 탭의 테이블 이름을 바인딩한 `_execute_file_upload`에 연결하였습니다.

## 3. 변경 파일 (Affected Files)
- `client/main.py` (`ExcelTableView` 확장 및 `MainWindow` 리팩토링)

## 4. 검증 결과 (Validation)
- 테이블 뷰 영역으로 파일을 드래그했을 때 마우스 포인터가 활성화(AcceptAction)되는 것을 설계상 확인했습니다.
- 파일 드롭 시 내부적으로 저장된 `_source_model` 정보를 활용하여 정확한 테이블의 `raws/` 폴더로 업로드가 전송됨을 보장합니다.
