# 2026-07-19 19:27:00 - 백엔드 감사 로그(Audit Log) 저장 시 datetime/UUID 객체 JSON 직렬화 예외 해결

## 1. 개요 및 동기
* **문제점**: 
  * 사용자가 격자 맵 에디터에서 데이터를 적재하거나 Bulk Cell 수정을 가할 때, 백엔드에서 `sqlalchemy.exc.StatementError: (builtins.TypeError) Object of type datetime is not JSON serializable` 예외가 발생하며 저장이 실패하는 경우가 있었습니다.
  * 이는 감사 로그(`audit_logs`) 테이블의 `old_value`와 `new_value`가 JSON 형식 컬럼인데, 업데이트된 원래 필드 중 `graph_synced_at` 등 날짜/시간(`datetime`) 객체나 `UUID` 형태의 원천 타입 데이터가 JSON 문자열로 변환되지 못하고 SQLAlchemy 파라미터 바인딩 단계로 그대로 전달되면서 발생한 현상이었습니다.
* **해결 방안**:
  * 데이터 저장 전 문자열 정제를 맡는 공용 함수 `sanitize_to_utf8()` 내부에 직렬화 불가능한 핵심 비표준 타입에 대한 형 변환 분기들을 추가했습니다.
  * `datetime` 및 `date` 객체는 `.isoformat()` 문자열로 변환하고, `uuid.UUID` 객체는 `str(UUID)` 문자열로 사전에 파싱 변환하여 JSON 컬럼에 안전하게 안착시켰습니다.

---

## 2. 주요 구현 사항

### A. 데이터 정제 함수 보완 (`server/database/crud.py`)
```python
def sanitize_to_utf8(data: Any) -> Any:
    """
    데이터 객체(Dict, List, Str 등) 내부의 모든 문자열을 재귀적으로 탐색하여 
    비유효한 UTF-8 바이트 시퀀스를 제거/정정합니다.
    JSON 직렬화가 불가능한 datetime/UUID 등도 문자열로 변환합니다.
    """
    if isinstance(data, dict):
        return {k: sanitize_to_utf8(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_to_utf8(v) for v in data]
    elif isinstance(data, str):
        # 비유효한 UTF-8 바이트를 무시(ignore)하고 다시 디코딩하여 깨끗한 문자열 생성
        return data.encode("utf-8", "ignore").decode("utf-8")
    elif isinstance(data, datetime):
        return data.isoformat()
    elif isinstance(data, uuid.UUID):
        return str(data)
    elif hasattr(data, "isoformat"):
        return data.isoformat()
    else:
        return data
```

---

## 3. 아키텍처 영향 보고
* **모든 컬럼 타입의 감사 로그 안전성 확보**: 날짜/시간형(`timestamp`), 고유 식별자(`UUID`) 컬럼 등이 혼재된 테이블에서 셀을 편집 및 업데이트할 때도 에러 없이 감사 이력이 PostgreSQL JSON 필드에 안전하게 보존됩니다.
* **통합 검증 성공**: 수동 Conda 가상 환경(`assy_manager`) 내에서 작성한 독립 테스트 유닛 실행 결과 모든 검증 조건이 에러 없이 무사히 통과되었습니다.
