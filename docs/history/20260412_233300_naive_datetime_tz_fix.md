# 프로젝트 이력: 나이브 데이트타임 타임존 변환 무결성 확보 (2026-04-12)

## 1. 개요
SQLite의 `CURRENT_TIMESTAMP` 등이 반환하는 TZ 정보가 없는 '나이브(Naive)' 데이트타임 객체가 서버의 변환 로직을 우회하여 UTC로 노출되던 결함을 해결함.

## 2. 상세 작업 내용

### 2.1 Safe Coordinate Logic 도입
- **문제**: `dt.astimezone()`은 TZ 정보가 없는 나이브 객체에 대해 환경에 따라 변환을 생략하거나 시스템 로컬 시각으로 오해할 수 있음.
- **해결**: `dt.tzinfo is None`인 경우, 이를 명시적으로 `timezone.utc`로 지정(`replace`)한 뒤 `astimezone()`을 호출하는 2단계 변환 프로세스를 정립함.

### 2.2 전방위 적용
- **서버 데코레이터 (`main.py`)**: `inject_system_columns` 내 `to_local_str` 함수 수정.
- **피단틱 스키마 (`schemas.py`)**: `AuditLogResponse` 및 `DataRowResponse`의 `field_validator` 수정.

## 3. 최종 결과
- 나이브하게 넘어오던 DB 상의 모든 시간 데이터가 이제 강제 UTC 보정을 거쳐 정확한 KST(+9)로 변환되어 UI에 표출되는 것을 확인함.

---
**기록자: Antigravity (Agent D v12)**
