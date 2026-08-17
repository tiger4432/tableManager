# Ledger v2 Stage 7 승인과 main 병합

## 승인 대상

- 초기 구현: `e567778201e84984719f4a8dfcdecac5ae50fa2c`
- CLI gate 후속 보완: `f516268eadae5505c586ce5235e76dd729c1e573`
- 독립 Audit 판정: `APPROVE`

## 확인된 계약

- 기본 v2 CLI는 manifest-selected path에서 legacy config를 import/load하지 않는다.
- `--config`는 명시적 `--legacy` 전용이다.
- `--reset-cursor`와 `--from`은 v2/legacy 모든 공개 CLI mode에서 config·DB·source/store보다
  먼저 구조화 거절된다.
- manifest dry-run은 ready이고 snapshot은
  `57d36c07271a019242722cc4627f1c0a9c6b477e632f29f32034e331928b0da0`다.
- 독립 exact-archive 검증은 집중 `22 passed`, 직접 영향군 `364 passed, 10 skipped`였다.

## 상태

Ledger v2 1~7단계는 `COMPLETE / APPROVED`이며 main에 fast-forward 병합했다. 운영 DB/cursor
reset, replay와 legacy 파일·코드 삭제는 이 승인에 포함되지 않으며 별도 파괴 승인 전까지
금지한다.
