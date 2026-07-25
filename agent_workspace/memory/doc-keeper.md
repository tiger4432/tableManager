# 교훈 파일 — doc-keeper

> **운영 규칙:** 신규 교훈은 에이전트가 보고서에 **제안** → 총괄 검수 후 이 파일에 반영. (직접 추가 금지)
> 작업 착수 시 이 파일 전체를 로드할 것 (Pre-Flight 항목).

## 공통 (전 에이전트)

- **함정**: 시스템 python으로 실행하면 psycopg2 부재 등으로 거짓 실패한다.
  **올바른 방법**: 모든 Python 실행은 conda `assy_manager` 필수 — `conda run -n assy_manager python <파일>` (예: `docs/history/gen_index.py`).
- **함정**: Windows 콘솔은 cp949라 한글/유니코드 출력에서 인코딩 에러가 난다.
  **올바른 방법**: `PYTHONIOENCODING=utf-8`을 앞에 붙여 실행.
- **함정**: `conda run`은 멀티라인 `python -c` 인라인 코드를 처리하지 못한다.
  **올바른 방법**: 코드를 스크립트 파일로 저장 후 파일 실행.
- **함정**: `/tmp`는 Windows python에서 보이지 않는다.
  **올바른 방법**: 세션 스크래치패드 디렉터리를 사용.

## doc-keeper 전용

*(아직 확정된 전용 교훈 없음 — 보고서에 제안하면 총괄 검수 후 여기에 반영된다.)*
