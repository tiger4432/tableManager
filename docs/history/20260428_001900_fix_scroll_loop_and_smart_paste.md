# 작업 내역: 트랜잭션 리뷰 모드 버그 수정 및 스마트 붙여넣기(Smart Paste) 구현

특정 트랜잭션 검수 중 발생하는 무한 스크롤 버그를 수정하고, 대량 데이터 처리를 위한 '파서 기반 붙여넣기' 및 업로더 추적 기능을 추가하였습니다.

## 1. 주요 변경 사항

### [Bug Fix] 트랜잭션 리뷰 모드 무한 루프 해결
- **원인**: 서버의 `total_count` 캐시 키 생성 시 `transaction_id`를 누락하여, 필터링 후에도 전체 행 개수가 반환되어 클라이언트가 계속 다음 페이지를 요청함.
- **수정**: `server/main.py`의 캐시 키 생성 로직에 `transaction_id`, `q`, `cols`를 모두 포함하여 필터 조건별로 정확한 카운트가 캐싱되도록 개선.

### [New Feature] 스마트 붙여넣기 (Smart Paste via Ingestion)
- **개요**: 클립보드의 대량 데이터를 단순 셀 복사가 아닌, 서버 파서(Parser)를 통해 정밀 변환 후 일괄 적재하는 기능.
- **클라이언트**: `ExcelTableView` 우클릭 메뉴에 "파서로 붙여넣기" 추가. 클립보드 데이터를 임시 파일(`.log`)로 변환하여 업로드.
- **UI 개선**: 스마트 붙여넣기 시에는 팝업 없이 상태바 알림만 표시하는 `silent` 업로드 모드 도입.

### [Attribution] 파일 업로더 추적 기능
- **메커니즘**: 파일 업로드 시 업로더 정보를 파일명에 인코딩(`user(이름)_파일명`)하여 전달.
- **자동 기록**: `directory_watcher`가 파일명에서 사용자 정보를 추출하여, 인제션된 모든 데이터의 `updated_by` 필드에 자동으로 기록.

### [Stability] 트랜잭션 필터 시 실시간 업데이트 제어
- **로직**: 특정 트랜잭션을 검수 중(Review Mode)이거나 검색 중일 때는 백그라운드에서 유입되는 신규 데이터가 화면을 흐트러뜨리지 않도록 삽입 로직을 차단.
- **정합성**: 기존 노출 데이터에 대한 업데이트는 허용하되, 신규 행 추가만 차단하여 검수 집중도 향상.

## 2. 기술적 수정 사항

### Backend (Server)
- [MODIFY] [main.py](file:///c:/Users/kk980/Developments/assyManager/server/main.py): 캐시 키 로직 수정 및 업로드 API `user` 파라미터 추가.
- [MODIFY] [directory_watcher.py](file:///c:/Users/kk980/Developments/assyManager/server/parsers/directory_watcher.py): 파일명 기반 업로더 정보 추출 및 `updated_by` 연동.

### Frontend (Client)
- [MODIFY] [table_model.py](file:///c:/Users/kk980/Developments/assyManager/client/models/table_model.py): `is_jump` 관련 로그 수정 및 실시간 업데이트 필터링 강화.
- [MODIFY] [main.py](file:///c:/Users/kk980/Developments/assyManager/client/main.py): 스마트 붙여넣기 메뉴 추가 및 업로드 워커 사용자 정보 연동.

## 3. 향후 과제
- 파서 실행 실패 시 클라이언트에 상세 에러 메시지를 WebSocket으로 푸시하는 기능 검토.
- 스마트 붙여넣기 전용 파서 템플릿(UI) 제공.
