# 파일 인제션 (File Ingestion)

## 1. 파일 업로드 및 데이터 적재
### 📍 트리거 포인트
- **버튼 클릭**: `MainWindow._on_upload_requested()` (툴바 `Upload` 버튼)
- **드래그 앤 드롭**: `ExcelTableView.dropEvent()`

### ⚙️ 동작 방식
1. 사용자가 CSV, 로그 파일 등을 선택하거나 표 위에 파일을 드롭하면, 대상 파일의 절대 경로(`file_path`)를 획득합니다.
2. 메인 윈도우의 `_execute_file_upload(table_name, file_path)`가 호출되어 `ApiUploadWorker` 객체를 생성합니다.
3. 백그라운드 스레드에서 파일이 `multipart/form-data` 형식으로 대상 테이블의 인제션 파이프라인(`POST /tables/{table_name}/upload`)에 스트리밍 전송됩니다.
4. 파일 전송이 완료되면 UI에 안내 메시지("서버에서 곧 파싱을 시작합니다")를 띄우고 활성 워커 스레드를 정리합니다.
5. 이후 파싱, 검증 및 데이터베이스 반영은 서버 사이드의 배치 워커 혹은 DataIngester 스킬 워커가 비동기로 담당하며, 처리된 결과는 WebSocket `batch_row_create` 혹은 `batch_row_upsert` 이벤트로 클라이언트에 점진적 혹은 일괄적으로 뿌려져 즉시 화면에 노출됩니다.
