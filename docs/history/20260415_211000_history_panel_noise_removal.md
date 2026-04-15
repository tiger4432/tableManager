# 20260415_211000_history_panel_noise_removal

## 1. 이슈 개요 (Issue Overview)
`HistoryDockPanel`이 모델의 `dataChanged` 시그널을 수신하여 로그를 남길 때, 실제 데이터 업데이트뿐만 아니라 단순 데이터 로딩(최초 로드 및 스크롤 페칭) 시그널까지 모두 로그로 기록하여 사용자에게 불필요한 노이즈를 제공하는 문제가 있었습니다.

## 2. 해결 방안 (Solution Details)

### 2.1 모델 상태 기반 필터링 도입
- `ApiLazyTableModel`은 데이터 로딩 중 `_fetching` 플래그를 `True`로 가집니다.
- `panel_history.py`의 `_handle_data_changed` 핸들러에서 이 플래그를 체크하여, 페칭 중 발생하는 `dataChanged` 시그널은 무시하도록 로직을 강화하였습니다.

### 2.2 실시간 업데이트 보존
- WebSocket 수신 시 발생하는 시그널은 `_is_processing_remote` 플래그로 이미 가드되어 있으며, 별도의 전용 슬롯을 통해 정확한 업데이트 로그가 남도록 유지되었습니다.
- 수동 수정(Manual Fix) 완료 후 발생하는 시그널은 `_fetching`이 `False`이므로 정상적으로 로그에 기록됩니다.

## 3. 변경 파일 (Affected Files)
- `client/ui/panel_history.py` (수정: `_handle_data_changed` 가딩 로직 추가)

## 4. 검증 결과 (Validation)
- 지연 로딩(`fetchMore`) 시 히스토리 패널에 불필요한 로그가 쌓이지 않음을 설계적으로 확인하였습니다.
- 실제 데이터 수정(WS 브로드캐스트) 시에는 기존과 동일하게 로그가 즉시 생성됨을 보장합니다.
