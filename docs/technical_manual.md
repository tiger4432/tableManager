# 📘 assyManager 상세 기술 및 유지보수 매뉴얼

본 문서는 `assyManager` 실시간 에디터 시스템의 아키텍처와 상세 내부 구조를 설명합니다. 차후 유지보수 시 이 문서를 가이드로 삼아 작업하십시오.

---

## 🏗️ 1. 전체 아키텍처 개요
시스템은 **FastAPI(Backend)**와 **PySide6(Frontend)**로 구성된 클라이언트-서버 구조입니다.

- **Backend**: 데이터 영속성(SQLite), 실시간 이벤트 전송(WebSocket), 페이징 데이터 제공(REST).
- **Frontend**: 가상 스크롤링 테이블(QAbstractTableModel), 비동기 API 통신(QRunnable), 실시간 데이터 연동(QThread).

---

## 🖥️ 2. 서버 (Backend) 구조
`server/` 디렉토리에 위치합니다.

### 💾 데이터베이스 (`server/database/`)
- **`database.py`**: SQLAlchemy 엔진 설정. 실행 위치에 상관없이 항상 `server/` 내의 `.db` 파일을 바라보도록 **절대 경로**로 설정되어 있습니다.
- **`models.py`**: `DataRow` 테이블 정의. 
  - `row_id`, `table_name`을 키로 사용.
  - 실제 데이터는 `JSON` 타입의 `data` 컬럼에 저장됩니다. (Schema-less 대응)
  - Data 구조: `{"컬럼명": {"value": 값, "is_overwrite": bool, "updated_by": str}}`

### 🌐 API 엔드포인트 (`server/main.py`)
- `GET /tables/{table_name}/data`: 페이징 지원 (limit, skip).
- `PUT /tables/{table_name}/cells`: 단일 셀 수정.
- `PUT /tables/{table_name}/cells/batch`: 다중 셀 일괄 수정 (Ctrl+V용).
- `POST /tables/{table_name}/rows`: 신규 빈 행 생성 및 실시간 브로드캐스트.
- `DELETE /tables/{table_name}/rows/{row_id}`: 특정 행 삭제 및 실시간 브로드캐스트.
- `WS /ws`: 모든 연결된 클라이언트에게 생성/수정/삭제 이벤트를 브로드캐스트.

---

## 🎨 3. 클라이언트 (Frontend) 구조
`client/` 디렉토리에 위치하며, MVC 패턴을 따릅니다.

### 📊 데이터 모델 (`client/models/table_model.py`)
- **`ApiLazyTableModel`**: `QAbstractTableModel`을 상속받아 가상 스크롤 지원.
  - `fetchMore()` 호출 시 서버에서 50개 단위로 데이터를 가져옵니다.
  - `setData()` 호출 시 서버에 단일 PUT 요청을 보냅니다.
  - `bulkUpdateData()`: 여러 셀을 한 번에 서버에 전송합니다.
  - `row_create` 이벤트 수신 시 `beginInsertRows(0)`를 통해 최상단에 행을 추가합니다.
  - `row_delete` 이벤트 수신 시 `beginRemoveRows`를 통해 UI에서 행을 제거합니다.

### 🧵 비동기 인터페이스 (Async Workers)
- `ApiFetchWorker`, `ApiUpdateWorker`, `BatchApiUpdateWorker`가 `QRunnable`로 구현되어 `QThreadPool`에서 실행됩니다. (UI 프리징 방지)
- **`WsListenerThread`**: 전용 `QThread`에서 `websockets` 패키지를 사용해 실시간 신호를 수신합니다.

### 📦 UI 컴포넌트 (`client/ui/`)
- **`FilterToolBar`**: 상단 검색바. `QSortFilterProxyModel`을 사용하여 원본 모델을 건드리지 않고 필터링합니다.
- **`HistoryDockPanel`**: 우측 수정 이력 패널. 로컬/원격 수정을 색상으로 구분하여 표시합니다.

---

## 🔍 4. 컴포넌트별 소스 코드 상세 리뷰 (Deep Dive)

### A. 엑셀 인터커넥트 (Agent Excel)
- **주요 클래스**: `ExcelTableView`, `BatchApiUpdateWorker`
- **핵심 데이터 흐름**: TSV (사용자 복사/붙여넣기) → `bulkUpdateData` (파싱 및 페이로드 조립) → `PUT /cells/batch` (단일 API 호출)
- **유지보수 포인트**: 클립보드 파싱 시 줄바꿈(`\n`)과 탭(`\t`)을 기준으로 하며, 프록시 모델이 적용된 경우 반드시 `sourceModel()`을 참조하여 인덱스를 변환해야 합니다.

### B. 실시간 동기화 엔진 (Agent D)
- **주요 클래스**: `WsListenerThread`, `ApiLazyTableModel`
- **핵심 통신 규약**: JSON 기반 WebSocket 브로드캐스트 수신 → `ws_data_changed` Signal 방출 → 관련 UI(테이블, 히스토리) 즉시 갱신
- **자동 복구**: 연결 실패 시 3초 간격으로 무한 재시도하며, 타임아웃 설정을 통해 백그라운드 스레드를 안전하게 종료(Clean exit)할 수 있습니다.

### C. 사용자 인터페이스 & 필터링 (Agent Panel)
- **주요 클래스**: `HistoryDockPanel`, `FilterToolBar`
- **필터링 메커니즘**: `QSortFilterProxyModel`을 도입하여 원본 소스 모델은 불변으로 유지하면서도 뷰 레벨에서 대소문자 무관 정규표현식 검색을 수행합니다.
- **이력 관리**: `id(QListWidgetItem)`를 키로 사용하여 항목 클릭 시 해당 모델 인덱스로 점프(`scrollTo`)하는 메타데이터 매핑 구조를 가집니다.

---

## 🐍 5. 환경 및 유지보수 가이드

### 환경 구축
- **Conda 환경**: `assy_manager` (Python 3.12 권장)
- **필수 패키지**: `pyside6`, `fastapi`, `sqlalchemy`, `uvicorn`, `websockets`, `httpx`
```bash
conda activate assy_manager
pip install -r requirements.txt (추가 시)
```

### 주의 사항 (Troubleshooting)
1. **DLL Load Failed (Windows)**: `client/main.py` 상단의 DLL 경로 워크어라운드 코드를 삭제하지 마십시오. Conda 환경의 Qt 충돌을 방지합니다.
2. **WebSocket 연결 안 됨**: 서버가 `127.0.0.1:8000`에서 실행 중인지 확인하십시오. 클라이언트는 기본적으로 이 주소를 바라봅니다.
3. **데이터 초기화**: `server/seed_data.py`를 실행하여 100건 이상의 테스트 데이터를 생성할 수 있습니다.

---

## 📑 5. 작업 프로토콜 (Standard Agent Protocol)
차후 AI 에이전트가 투입될 경우, `agent_workspace/` 폴더의 가이드를 따르도록 하십시오.
- **Tasks**: `agent_workspace/tasks/`
- **Reports**: `agent_workspace/reports/`
