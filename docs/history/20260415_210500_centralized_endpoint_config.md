# 20260415_210500_centralized_endpoint_config

## 1. 이슈 개요 (Issue Overview)
클라이언트 코드 전반(`main.py`, `table_model.py`)에 REST API 및 WebSocket 엔드포인트가 하드코딩되어 있어, 서버 주소 변경이나 배포 환경 전환 시 유지보수가 어려운 문제가 있었습니다.

## 2. 해결 방안 (Solution Details)

### 2.1 중앙 집중식 설정 모듈 (`client/config.py`) 도입
- 모든 URL 베이스 주소와 엔드포인트 조립 로직을 `config.py`로 통합하였습니다.
- **네트워크 안정성**: 루프백 주소(`127.0.0.1`) 통신 시 프록시 간섭을 방지하기 위해 `os.environ["NO_PROXY"]` 설정을 강제하였습니다.

### 2.2 클라이언트 전 구간 리팩토링
- **Data Model**: `ApiLazyTableModel` 및 각종 `Worker` 클래스가 `config`의 빌더 함수를 사용하도록 수정되었습니다.
- **UI Service**: `MainWindow`의 테이블 목록 조회, WebSocket 초기화, CSV 익스포트 로직이 `config` 참조 방식으로 전환되었습니다.

## 3. 변경 파일 (Affected Files)
- `client/config.py` (신규)
- `client/models/table_model.py` (수정)
- `client/main.py` (수정)

## 4. 검증 결과 (Validation)
- `verify_config.py` 스모크 테스트를 통해 `config` 임포트 및 모델의 엔드포인트 자동 조립 로직이 정상 작동함을 확인하였습니다.
- `conda run -n assy_manager python verify_config.py` -> SUCCESS
