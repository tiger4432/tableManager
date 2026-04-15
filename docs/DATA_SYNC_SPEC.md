# AssyManager: 데이터 동기화 및 무결성 관리 명세서

본 문서는 실시간 데이터 동기화, 가상 로딩, 그리고 클라이언트 사이드 데이터 무결성 보호 메커니즘을 기술합니다. 데이터 누락 또는 중복 현상 디버깅 시의 핵심 참조서입니다.

---

## 🛰️ 1. 실시간 동기화 아키텍처 (WebSocket)

AssyManager는 단일 공유 WebSocket 리스너를 통해 모든 테이블의 변경사항을 실시간으로 수신합니다.

### 1.1 `WsListenerThread` (The Ear)
- **역할**: 백그라운드 스레드에서 서버(`ws://.../ws`)에 접속하여 JSON 메시지를 지속적으로 수신.
- **연결 복구**: 연결이 끊길 경우 3초 간격으로 자동 재시도를 수행합니다.
- **신호 전달**: `message_received(dict)` 시그널을 통해 수신된 페이로드를 메인 스레드로 전달합니다.

### 1.2 `Shared Listener` 패턴
- 각 테이블 모델은 생성 시 글로벌 WebSocket 리스너의 시그널에 자신의 `_on_websocket_broadcast` 슬롯을 연결합니다.
- 메시지의 `table_name` 필드를 검사하여 자신의 데이터인 경우만 처리합니다.

---

## 📦 2. 가상 로딩 및 성능 최적화 (Lazy Loading)

### 2.1 청킹(Chunking) 전략
- **`ApiLazyTableModel`**: 초기화 시 데이터를 모두 불러오지 않고, 스크롤이 하단에 도달할 때 `canFetchMore`가 호출됩니다.
- **단위**: `_chunk_size = 50`으로 설정되어 서버 및 네트워크 부하를 조율합니다.

### 2.2 부상(Floating) 메커니즘
- 변경된 데이터가 실시간으로 수신되면, 해당 행은 인덱스에 관계없이 리스트의 **최상단(Index 0)**으로 이동합니다.
- **함수**: `beginMoveRows()`, `self._data.insert(0, self._data.pop(idx))`, `endMoveRows()`.

---

## 🛡️ 3. 데이터 무결성 가드 (Integrity Guards)

### 3.1 Strict Deduplication (전수 중복 제거)
- **문제**: 가상 로딩 중인 데이터와 WebSocket으로 새로 유입된 데이터가 동시에 존재하여 행이 중복 보이는 현상.
- **해결**: `_build_row_id_map()`을 통해 현재 로컬 캐시를 전수 조사합니다. 동일한 `row_id`가 존재하면 기존 행을 제거(pop)하고 새 데이터를 삽입함으로써 유일성을 보장합니다.

### 3.2 Ghost Row 방어 (잔상 제거)
- 모델이 리셋되거나 대량 업데이트(`batch_row_upsert`) 시 `beginResetModel()`을 호출하여 뷰의 인덱스 참조가 꼬이지 않도록 방어합니다.

---

## 🛠️ 4. 디버깅 가이드 (Data Domain)

### Q: 특정 행이 두 번 나타납니다 (중복 행).
- **원인**: `_build_row_id_map`이 동작하지 않았거나, `row_id` 데이터 타입(int vs str) 불일치로 매핑에 실패했을 가능성이 큽니다.
- **확인**: `table_model.py`의 `_normalize_row_data` 함수가 `row_id`를 문자열로 정규화하는지 확인하십시오.

### Q: 스크롤을 내리면 "Loading..."만 뜨고 데이터가 나오지 않습니다.
- **원인**: 서버 `/data` 엔드포인트 응답 지연 또는 워커(`ApiFetchWorker`)의 시그널 차단.
- **확인**: 터미널에서 FastAPI 로그를 확인하여 SQL 쿼리가 정상적으로 수행되는지 점검하십시오.

---
*AssyManager Data Integrity Specification v2.0*
