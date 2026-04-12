# 📘 assyManager 통합 기술 가이드 (Technical Guide)

본 문서는 `assyManager`의 시스템 아키텍처, API 명세, 그리고 데이터 인제션 전략을 하나로 통합한 관리자 및 개발자용 표준 가이드입니다.

---

## 🏗️ 1. 시스템 아키텍처 개요
FastAPI 기반의 백엔드와 PySide6 기반의 프론트엔드가 실시간 WebSocket으로 동기화되는 구조입니다.

### 💾 백엔드 (FastAPI + SQLAlchemy)
- **Schema-less JSON Storage**: `DataRow` 테이블의 `data` 컬럼에 JSON 형태로 모든 실시간 데이터를 저장하여 유연한 데이터 구조를 지원합니다.
- **Business Key Support**: `part_no`, `plan_id` 등 도메인 식별자를 기반으로 한 Upsert 로직을 통해 데이터 중복을 방지합니다.
- **우선순위 엔진**: `User(0) > Parser_A(1) > Parser_B(2)` 순의 가중치로 최종 데이터를 결정합니다.

### 🎨 프론트엔드 (PySide6 + Shared WS)
- **Virtual Scrolling**: `ApiLazyTableModel`을 통해 수만 건의 데이터도 지연 없이 가상 스크롤링합니다.
- **Shared WebSocket**: 단일 WebSocket 연결로 모든 탭의 데이터를 실시간 업데이트하는 최적화된 통신 구조를 갖추고 있습니다.

---

## 🌐 2. 주요 API 명세

| 엔드포인트 | 메서드 | 설명 |
| :--- | :--- | :--- |
| `/tables` | GET | 사용 가능한 모든 테이블 리스트 조회 |
| `/tables/{name}/data` | GET | 페이징 기반 데이터 조회 (skip, limit) |
| `/tables/{name}/schema` | GET | 비즈니스 키 및 표시 컬럼 정보 조회 |
| `/tables/{name}/upsert` | PUT | 비즈니스 키 기반 지능형 업데이트/생성 |
| `/ws` | WS | 실시간 이벤트(생성/수정/삭제) 브로드캐스트 |

---

## 📥 3. 데이터 인제션 (Generic Ingester)

`GenericIngester`는 정규표현식(Regex)을 사용하여 파일명과 내용에서 데이터를 추출합니다.

### ⚙️ 설정 방식 (`parser_config.json`)
- **`filename_rules`**: 파일명(예: 설비ID_날짜.log)에서 메타데이터 추출.
- **`rules`**: 파일 각 라인에서 특정 패턴(온도, 습도 등) 추출.
- **`business_key_column`**: 중복 방지를 위한 핵심 식별자 지정.

### 📝 설정 예시 (설비 로그 파싱)
```json
{
  "table_name": "facility_monitor",
  "business_key_column": "log_id",
  "filename_rules": [{ "column": "facility_id", "regex": "([A-Z0-9_]+)_", "type": "str" }],
  "rules": [{ "column": "temperature", "regex": "TEMP: (\\d+\\.\\d+)", "type": "float" }]
}
```

---

## 🛠️ 4. 유지보수 및 운영
- **환경**: `conda activate assy_manager` (Python 3.12)
- **설정 파일**: `server/config/table_config.json` (테이블 구조 핵심 설정)
- **주의**: Windows 환경에서 PySide6 DLL 이슈 해결을 위해 `client/main.py` 상단의 DLL 경로 워크어라운드 코드를 반드시 유지하십시오.
