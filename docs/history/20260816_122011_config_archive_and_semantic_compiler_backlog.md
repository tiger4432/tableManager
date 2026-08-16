# Config backup/sample 분리와 Semantic Config Compiler 백로그

> 2026-08-16 · Config / Ops

## 배경

`server/config/` 최상위에 활성 설정, 추적 샘플, 런타임 상태와 과거 백업이
섞여 있었다. 로더는 정확한 활성 파일명만 읽지만 운영자가 어떤 파일을 편집해야 하는지
한눈에 구분하기 어려웠다. 백업을 단순 이동하면 주간 스냅샷을 직접 열거하던 `/health`와
복원 CLI가 과거 이력을 잃기 때문에, 파일 정리와 소비 계약을 함께 바꿨다.

## 변경

- `server/config/backup/`: 주간 스냅샷, 설치·어드민 변경 전 사본, 복원 직전 증거를
  한 폴더에 보관한다. 파일명 규칙으로 역할을 구분하며 현재 72개다.
- `server/config/sample/`: 추적되는 `*.sample` 21개를 보관한다.
- 루트에는 활성 `*.json`, 런타임 상태 및 `worker_heartbeats/`만 남겼다.
- `config_backup`은 새 주간 스냅샷을 `backup/`에 쓰고, 전환 전 루트와 옛
  `_archive/weekly/`의 구형 스냅샷도 계속 읽는다.
- 제품 테이블 설치기·원장 어드민 저장기·복원 CLI도 모두 `backup/`에 사본을 남긴다.
- 샘플 폴백이 있는 로더와 설치기는 모두 `sample/<파일>.sample`을 읽는다. 닫힌 어휘인
  `ledger_vocabulary`는 기존 원칙대로 sample을 폴백하지 않는다.
- `task/semantic_config_compiler_pending.md`에 Enrichment 선언으로 파생 table config,
  chain, Virtual Join, claim/worklist를 결정적으로 생성하는 후속 작업을 등록했다.

백업과 샘플은 삭제하지 않았으며 이동만 했다. 빈 `_archive`는 제거했다.
`.gitignore`는 `server/config/sample/*.sample`만 선택적으로 추적한다.

## 검증

- 집중 회귀는 config backup, 제품 테이블 설치기, 원장 어드민 저장, 샘플 폴백 로더,
  원장 trace/notation/virtual join까지 **368 passed, 1 skipped**.
- 변경 Python `py_compile`, `git diff --check` 통과. 샘플 JSON 21개 전부 파싱 성공.
- `backup_config.py check`는 `status: ok`, 14개 config/45개 주간 스냅샷을 보고했다.
- 파일 실사: `backup/` 72개, `sample/` 21개, 루트의 `*.sample`/`*.bak*` 0개,
  `_archive` 부재.
- 전체 서버 스택 재기동 뒤 `/health status=ok`; 새 scheduler heartbeat를 확인했고
  config 루트 백업은 다시 생기지 않았다.
