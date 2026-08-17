# Ledger v2 1단계 inventory와 baseline

## 배경

Ledger v2 구현 전에 기존 Kernel과 하드코딩된 Setup/Compiler를 symbol 단위로 분리했다.
dirty worktree를 보존한 채 읽기 전용 조사와 테스트 baseline만 수행했다.

## 변경

- 하드코딩 전수표, 현행 호출 그래프, baseline, Keep/Move/Retire 작성
- `OPEN_DECISIONS` D1~D5에 실측 근거 추가
- README/SSOT/ownership에 `IN_REVIEW/NOT_APPROVED` 반영

## 주요 판정

- registered Chain mapper는 lineage `lot_event`에만 연결된다.
- gate/store/cursor/LedgerFrame/read API는 유지한다.
- Position, declared lookup, Python emitter, 직접 Atom mapper는 parity 뒤 은퇴한다.
- virtual join은 현재 UI read path이며 Ledger Preparer와 right correction replay는 없다.
- stage 2는 시작하지 않았고 런타임 코드·DB·운영 config는 변경하지 않았다.

## 검증

- 핵심 Ledger: `247 passed`
- 구 기대 별도 실행: `102 passed, 7 failed` — WaferLeg 5, live source 누락 2
- PostgreSQL Ledger: `8 passed, 131 skipped`
- 전체: `3923 passed, 142 failed, 203 skipped, 1 xfailed, 23 errors`

전체 clean baseline 부재로 repo 전체 회귀 없음은 주장하지 않는다.
