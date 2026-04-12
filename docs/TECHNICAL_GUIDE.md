# 📘 assyManager 통합 기술 가이드 (Technical Guide)

본 문서는 `assyManager`의 시스템 아키텍처, API 명세, 그리고 데이터 인제션 전략을 하나로 통합한 관리자 및 개발자용 표준 가이드입니다.

---

## 🏗️ 1. 시스템 아키텍처 개요
FastAPI 기반의 백엔드와 PySide6 기반의 프론트엔드가 실시간 WebSocket으로 동기화되는 구조입니다.

### 💾 백엔드 (FastAPI + SQLAlchemy)
- **Schema-less JSON Storage**: `DataRow` 테이블의 `data` 컬럼에 JSON 형태로 모든 실시간 데이터를 저장하여 유연한 데이터 구조를 지원합니다.
- **Business Key Support**: `part_no`, `plan_id` 등 도메인 식별자를 기반으로 한 Upsert 로직을 통해 데이터 중복을 방지합니다.
- **우선순위 엔진**: `User(0) > Parser_A(1) > Parser_B(2)` 순의 가중치로 최종 데이터를 결정합니다. 상세 설계는 [ARCHITECTURE_ANALYSIS.md](./ARCHITECTURE_ANALYSIS.md)를 참조하십시오.
- **Global Search & Sorting**: 서버 레벨에서 JSON 데이터를 검색(`q` parameter)하고 최신 데이터부터 정렬하여 반환하는 고성능 쿼리 엔진을 포함합니다.
- **Advanced Ingestion**: 헤더-본문 결합 파싱 및 디렉토리 감시 기반의 자동화 파이프라인. 상세 설정은 [INGESTION_GUIDE.md](./INGESTION_GUIDE.md)를 참조하십시오.

### 🎨 프론트엔드 (PySide6 + Shared WS)
- **Virtual Scrolling**: `ApiLazyTableModel`을 통해 수만 건의 데이터도 지연 없이 가상 스크롤링합니다.
- **Shared WebSocket**: 단일 WebSocket 연결로 모든 탭의 데이터를 실시간 업데이트하며, **비동기 워커 생명주기 관리(GC 방지)** 및 **순차적 탭 로딩**을 통해 시스템 안정성을 극대화하였습니다.
- **Manual Fix UI**: 사용자 수동 수정 시 노란색 하이라이트와 `🛠️` 아이콘 및 수정자 정보가 실시간 대조 표시됩니다.

---

## 🌐 2. 주요 API 명세

| 엔드포인트 | 메서드 | 설명 |
| :--- | :--- | :--- |
| `/tables` | GET | 사용 가능한 모든 테이블 리스트 조회 |
| `/tables/{name}/data` | GET | 페이징 기반 데이터 조회 (skip, limit, q-검색어) |
| `/tables/{name}/schema` | GET | 비즈니스 키 및 표시 컬럼 정보 조회 |
| `/tables/{name}/upsert` | PUT | 비즈니스 키 기반 지능형 업데이트/생성 |
| `/ws` | WS | 실시간 이벤트(생성/수정/삭제) 브로드캐스트 |

---

## 📥 3. 고급 인제션 엔진 및 워크플로우

`AdvancedIngester`와 `DirectoryWatcher`를 결합하여 헤더-본문 복합 파싱 및 실시간 자동화를 구현합니다.

### ⚙️ 핵심 클래스 사양
1. **`AdvancedIngester`**: `GenericIngester` 상속.
   - `extract_header_metadata()`: 파일 상단에서 공통 속성(설비ID, 배치ID 등) 추출.
   - `process_file()`: 헤더 추출과 본문 테이블 파싱을 시퀀셜하게 수행 후 결합 적재.
2. **`DirectoryWatcher`**: `watchdog` 기반 실시간 감시.
   - `IngestionHandler`: `on_created` 및 `on_moved` 이벤트를 수신하여 즉시 인제션 트리거.
   - `Robustness`: 윈도우 중복 이벤트 방어 로직(`processing_files` tracking) 및 각 워크스페이스별 설정 파일(`sensor_config.json` 등) 자동 탐색 기능을 제공합니다.
   - `WorkspaceWatcher`: `ingestion_workspace/` 하위의 모든 `raws/` 폴더를 재귀적으로 발견하여 감시 대상에 등록합니다.

### 📝 설정 예시 (`config.json`)
```json
{
  "table_name": "inventory_master",
  "header_rules": [{ "column": "batch_id", "regex": "Batch: (\\d+)", "type": "int" }],
  "rules": [{ "column": "part_no", "regex": "P/N: ([\\w-]+)" }]
}
```

---

## 🔍 4. 실시간 가시성 및 데이터 무결성 (Advanced Features)

### 🚀 4.1 Universal Real-Time Visibility (Float-to-top)
대규모 데이터 환경(Lazy Loading)에서 현재 화면에 보이지 않는(Off-screen) 행이 수정될 경우, 이를 즉시 인지하고 최상단으로 부상시키는 메커니즘을 제공합니다.
- **ApiSingleRowFetchWorker**: 브로드캐스트 수신 시 로컬 데이터가 없는 경우 서버에서 단건 데이터를 즉시 페칭합니다.
- **Prepend Strategy**: 수정된 데이터를 모델의 최상단(Index 0)으로 삽입하여 사용자가 즉시 수정 사항을 인지할 수 있도록 합니다.

### 🌍 4.2 타임존 현지화 (Timezone Hardening)
시스템의 모든 시간 정보를 사용자의 현지 시간(KST, UTC+9)으로 자동 변환합니다.
- **Safe Coordinate Logic**: SQLite의 나이브(Naive) UTC 객체에 대해 `[Force UTC -> Convert Local]` 2단계 보정을 수행하여 1초의 오차 없는 현지 시간을 보장합니다.
- **Unified Logic**: 서버 데코레이터(`main.py`)와 피단틱 스키마(`schemas.py`) 전 구간에 동일한 로직이 적용되어 있습니다.

### 🔒 4.3 시스템 컬럼 보안 (Integrity Guard)
`created_at`, `updated_at`, `row_id` 등 시스템이 관리하는 핵심 필드의 편집을 원천 차단합니다.
- **UI Guard**: 모델의 `flags()` 메서드에서 `ItemIsEditable` 속성을 제거하여 수동 수정을 방지합니다.
- **Server Guard**: CRUD 레이어에서 외부로부터의 시스템 컬럼 업데이트 요청을 자동 필터링하여 무결성을 유지합니다.

---

## 📊 5. 데이터 분석 및 외부 연동 (Export)

### 📥 5.1 CSV 스트리밍 익스포트
Spotfire, Excel 등 외부 도구에서 데이터를 즉시 활용할 수 있도록 CSV 추출 기능을 제공합니다.
- **Streaming Response**: 대용량 데이터 전송 시 서버 메모리 부하를 방지하기 위해 데이터를 실시간으로 생성하여 스트리밍합니다.
- **Excel Compatibility**: UTF-8 BOM 처리를 통해 엑셀에서 열람 시 한글 깨짐을 방지합니다.
- **Flattened Schema**: JSON 데이터 구조를 표 형식으로 평면화하여 제공하며, KST 현지 시간이 반영된 시스템 컬럼을 포함합니다.

---

## 🛠️ 6. 유지보수 및 운영
- **환경**: `conda activate assy_manager` (Python 3.12)
- **설정 파일**: `server/config/table_config.json` (테이블 구조 핵심 설정)
- **에이전틱 환경**: [agentic_environment.md](./agentic_environment.md) 참조.
- **히스토리 기록**: 모든 변경 사항은 `docs/history/`에 영구 기록됩니다.
- **주의**: Windows 환경의 PySide6 DLL 워크어라운드를 유지하십시오.
