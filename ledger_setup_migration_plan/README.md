# ledger_setup_migration_plan — 맵퍼 일괄 전환 + 셋업 개혁 지시서

소유자 결정(2026-08-17): 기존 번역기 문법이 복잡하여 **Profile/Pack 기반 mapper로
일괄 전환**. 이 폴더는 그 전환과, 셋업 실사용 고통(P-01~04)의 근본 개선을 한
줄기로 묶은 단계별 지시서다.

읽는 순서: `00_MASTER_PLAN.md` → `COMMON_RULES_DELTA.md` → 각 단계.
승인 게이트: `APPROVAL_MESSAGES.md`.

| 파일 | 내용 |
|---|---|
| 00_MASTER_PLAN | 배경·최종 목표·단계 목록·조사 대상·규율 |
| COMMON_RULES_DELTA | v2 공통 규칙에 더하는 것: 셋업 4금칙·전환 2금칙·문구 |
| 01_CUTOVER_INVENTORY | 전환표 + 등가성 디프 하니스 (조사 단계) |
| 02_PACK_LIBRARY | 현행 세계를 덮는 Pack 7종 계약 |
| 03_DICTIONARY_CAPABILITIES | 사전 API + 「답할 수 있는 질문」 렌더 |
| 04_WIZARD_EXTENSIONS | v2 04 마법사에 인터뷰 정문·문장 판정 |
| 05_PIPELINE_BOARD_BACKFILL | 현황판 + 백필 라우트 |
| 06_AGREEMENT_CHECKER | 철자 합의·라이브 잎 실측·은퇴 유산 표지 |
| 07_LEGACY_RETIREMENT | 등가 증명 후 legacy 일괄 은퇴 |

관련 정본: `ontology_codex_plan_v2`(Pack/Profile/마법사의 기반 계약) ·
`docs/process/SETUP_PAIN_LOG.md`(요구사항 원천) ·
`docs/process/LEDGER_SETUP_SCENARIO_REVIEW.md`(전 시나리오 진단) ·
`docs/process/LEDGER_RULINGS.md` R-M/N/O.
