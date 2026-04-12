# 📘 assyManager 통합 기술 가이드 (Technical Guide)

본 문서는 `assyManager`의 시스템 아키텍처, API 명세, 그리고 데이터 인제션 전략을 하나로 통합한 관리자 및 개발자용 표준 가이드입니다.

---

## 🏗️ 1. 시스템 아키텍처 개요
FastAPI 기반의 백엔드와 PySide6 기반의 프론트엔드가 실시간 WebSocket으로 동기화되는 구조입니다.

### 💾 백엔드 (FastAPI + SQLAlchemy)
- **Schema-less JSON Storage**: `DataRow` 테이블의 `data` 컬럼에 JSON 형태로 모든 실시간 데이터를 저장하여 유연한 데이터 구조를 지원합니다.
- **Business Key Support**: `part_no`, `plan_id` 등 도메인 식별자를 기반으로 한 Upsert 로직을 통해 데이터 중복을 방지합니다.
- **우선순위 엔진**: `User(0) > Parser_A(1) > Parser_B(2)` 순의 가중치로 최종 데이터를 결정합니다.
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

## 🔍 4. 전역 검색 및 정렬 시스템
물리적으로 분리된 Lazy Loading 구조에서도 `q` 파라미터를 통해 DB 레벨의 전역 검색을 수행합니다.
- **Global Search**: `models.DataRow.data.cast(String).ilike(f"%{q}%")` (SQLite 대응).
- **Recency Sorting**: `updated_at.desc(), created_at.desc()` 순으로 최신 데이터 우선 노출.

---

## 🛠️ 5. 유지보수 및 운영
- **환경**: `conda activate assy_manager` (Python 3.12)
- **설정 파일**: `server/config/table_config.json` (테이블 구조 핵심 설정)
- **에이전틱 환경**: 본 프로젝트는 멀티 에이전트 협업 체계로 운영됩니다. 상세 규약은 [agentic_environment.md](./agentic_environment.md)를 참조하십시오.
- **히스토리 기록**: 모든 주요 로직 변경은 `docs/history/`에 영구 기록되어야 합니다.
- **주의**: Windows 환경에서 PySide6 DLL 이슈 해결을 위해 `client/main.py` 상단의 DLL 경로 워크어라운드 코드를 반드시 유지하십시오.
