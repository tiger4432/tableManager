# Ledger v2 Stage 7 CLI gate 후속 보완

## 현상

초기 Stage 7 exact commit에서 공개 CLI의 기본 v2 mode가 manifest를 열기 전에 legacy flat
config를 읽었다. 또한 reset/replay 거절이 v2 driver 안에만 있어 `--legacy --reset-cursor`와
`--legacy --from`이 별도 승인 없이 legacy 실행기로 전달될 수 있었다.

## 근본 원인

`backfill.main()`이 mode 분기 전에 `ledger_config.load()`를 호출했고 destructive gate는
`_run_v2_lineage()`에만 있었다. 선언된 manifest 단일 진입점과 operator 승인 경계가 CLI
dispatch 순서로 강제되지 않은 문제였다.

## 수정

- 기본 v2 mode는 legacy config module/file을 import/load하지 않고 빈 compatibility 인자를
  manifest-selected v2 dispatch에 전달한다.
- legacy loader는 명시적 `--legacy` 분기 안에서만 호출한다.
- `--config`를 v2에서 조용히 무시하지 않고 `legacy_config_requires_legacy_mode`로 거절한다.
- `--reset-cursor`와 `--from`은 모든 CLI mode에서 config, DB, source, store 접근 전에
  `destructive_approval_required`로 거절한다.
- lower-level legacy helper와 runtime/DB/store/cursor 구현은 변경하지 않았다.

## 회귀 반례

- 기본 `backfill.main()`에서 legacy loader 호출 0건
- `--legacy --reset-cursor`: 구조화 거절, source 실행 0건
- `--legacy --from ...`: 구조화 거절, source 실행 0건
- v2 `--config`: 구조화 거절, legacy loader/source 실행 0건

## 검증

- Stage 7 집중: `22 passed`
- 기존 직접 영향군: `364 passed, 10 skipped`
- skip: 안전한 PostgreSQL URL 미설정 9건, 기존 Windows symlink 권한 1건
- full server suite: 사용자 지시에 따라 미실행
- 운영 DB/config write, reset, migration, legacy 이동·삭제: 0

Stage 7 상태는 `IN_REVIEW / NOT_APPROVED`이며 후속 exact commit의 독립 Audit 재승인을
기다린다.
