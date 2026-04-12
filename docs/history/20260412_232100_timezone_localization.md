# 프로젝트 이력: 전역 타임존 현지화(UTC to Local) 구현 (2026-04-12)

## 1. 개요
서버 및 DB에서 관리되는 글로벌 표준시(UTC) 데이터를 사용자가 직관적으로 인지할 수 있도록 현지 시간(KST/Local)으로 자동 변환하여 표출함.

## 2. 상세 작업 내용

### 2.1 서버 데코레이터 시간 변환 (`server/main.py`)
- `inject_system_columns` 내부에 `to_local_str` 헬퍼 함수를 추가함.
- SQLAlchemy의 TZ-aware 객체를 `astimezone()` 메서드를 이용해 서버 로컬 시간으로 변환 후 `YYYY-MM-DD HH:MM:SS` 형식으로 포맷팅하도록 개선함.

### 2.2 스키마 레벨 자동 변환 (`server/database/schemas.py`)
- Pydantic의 `field_validator`를 활용하여 `AuditLogResponse` 및 `DataRowResponse`의 `datetime` 필드들에 대해 출력 시 자동 현지화 로직을 이식함.
- `mode="after"` 검증기를 통해 객체 생성 시점에 TZ 정보를 확인하고 로컬 시간대로 오프셋을 자동 조정함.

### 2.3 일관성 확보
- 목록 조회, 단건 상세 조회, 업서트 후 브로드캐스트 전 과정에서 동일한 변환 로직이 적용되어 UI상의 시간 정보 불일치 문제를 근본적으로 해결함.

## 3. 최종 결과
- 기존 UTC 대비 +9시간(KST 기준) 차이 나던 모든 타임스탬프가 이제 현재 사용자의 시스템 시각과 일치하게 나타나는 것을 확인람.

---
**기록자: Antigravity (Agent D v10)**
