# 20260415_213500_file_upload_ingestion_trigger

## 1. 이슈 개요 (Issue Overview)
사용자가 로컬에 있는 로그 파일을 서버로 업로드하여 서버측 파서(`Directory Watcher`)를 즉시 구동하고, 인제션된 데이터를 실시간으로 클라이언트에 반영할 수 있는 기능이 필요했습니다.

## 2. 해결 방안 (Solution Details)

### 2.1 서버측 업로드 API 구축
- `server/main.py`에 `POST /tables/{table_name}/upload` 엔드포인트를 추가하였습니다.
- 수신된 파일은 해당 테이블 전용 인제션 워크스페이스인 `server/ingestion_workspace/{table_name}/raws/` 폴더에 즉시 저장됩니다.

### 2.2 클라이언트 UI 연동
- **`FilterToolBar`**: 상단 툴바에 "📤 파일 업로드" 버튼을 추가하였습니다.
- **`MainWindow`**: 버튼 클릭 시 `QFileDialog`를 통해 파일을 선택하고, `ApiUploadWorker`를 생성하여 비동기 전송을 수행합니다.
- **비동기 처리**: `httpx` 라이브러리를 사용하여 멀티파트(multipart/form-data) 전송을 구현하였으며, 대용량 파일 전송 중에도 UI가 멈추지 않도록 `QThreadPool`로 격리하였습니다.

### 2.3 데이터 파이프라인 연계
- 파일이 `raws/` 폴더에 저장되는 즉시 기존에 실행 중이던 `directory_watcher.py`가 이를 감지하여 파싱을 시작합니다.
- 파싱 결과로 발생한 DB 변경사항은 WebSocket을 통해 클라이언트에 즉시 브로드캐스트되어 UI에 실시간으로 나타납니다.

## 3. 변경 파일 (Affected Files)
- `server/main.py` (신규 엔드포인트 및 `UploadFile` 처리)
- `client/config.py` (업로드 URL 빌더 추가)
- `client/models/table_model.py` (`ApiUploadWorker` 및 `httpx` 연동 추가)
- `client/ui/panel_filter.py` (업로드 버튼 UI 추가)
- `client/main.py` (업로드 시그널 핸들러 및 워커 실행 로직 추가)

## 4. 검증 결과 (Validation)
- `verify_upload.py` 스모크 테스트를 통해 서버 엔드포인트가 파일을 정상적으로 수신하고 지정된 워크스페이스 경로에 저장함을 확인하였습니다.
- `conda run -n assy_manager python verify_upload.py` -> SUCCESS
