# 교훈 파일 — client-pm

> **운영 규칙:** 신규 교훈은 에이전트가 보고서에 **제안** → 총괄 검수 후 이 파일에 반영. (직접 추가 금지)
> 작업 착수 시 이 파일 전체를 로드할 것 (Pre-Flight 항목).

## 공통 (전 에이전트)

- **함정**: 시스템 python으로 실행하면 psycopg2 부재 등으로 거짓 실패한다.
  **올바른 방법**: 모든 Python 실행은 conda `assy_manager` 필수 — `conda run -n assy_manager python <파일>`.
- **함정**: Windows 콘솔은 cp949라 한글/유니코드 출력에서 인코딩 에러가 난다.
  **올바른 방법**: `PYTHONIOENCODING=utf-8`을 앞에 붙여 실행.
- **함정**: `conda run`은 멀티라인 `python -c` 인라인 코드를 처리하지 못한다.
  **올바른 방법**: 코드를 스크립트 파일로 저장 후 파일 실행.
- **함정**: `/tmp`는 Windows python에서 보이지 않는다.
  **올바른 방법**: 세션 스크래치패드 디렉터리를 사용.

## client-pm 전용

- **함정**: `state.js`를 리액티브 스토어처럼 다루면 화면이 갱신되지 않는다 — 단일 싱글턴일 뿐이다.
  **올바른 방법**: state 변조 후 명시적 UI 리프레셔를 직접 호출.
- **함정**: 셀 데이터를 원시값으로 다루면 셀 계약 `{value, is_overwrite, priority_source}`이 깨진다.
  **올바른 방법**: 셀은 항상 `grid.js`의 `ensureCellObject`로 정규화해서 접근.
- **함정**: worktree에는 node_modules가 없어 `npm run build`가 실패하거나 잘못된 산출물을 만든다.
  **올바른 방법**: worktree에선 빌드 금지 — `node --check`까지만, 빌드는 총괄이 본체에서 수행.
