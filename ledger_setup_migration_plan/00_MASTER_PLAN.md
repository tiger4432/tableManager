# 0단계 — 맵퍼 일괄 전환과 셋업 개혁, 전체 실행계획

`ontology_codex_plan_v2`의 `COMMON_ARCHITECTURE_RULES.md`, 이 폴더의
`COMMON_RULES_DELTA.md`, 그리고 **`MAPPER_STANDARD.md`(소유자 지정 디자인 패턴 —
고정 파이프라인·UNIT/EMITS/REQUIRES 자기 서술·payload 세 입구)**를 모든 단계에
적용한다. 용어·개념의 입문은 `PRIMER.md`가 정본이다.

## 배경 (소유자 결정, 2026-08-17)

- 기존 번역기(kind별 전용: observation/transfer/lot_event + 선언형)는 문법이
  복잡하여 **Profile/Pack 기반 mapper로 일괄 전환**한다. 이미 착지한 토대:
  `chain_mapper.py` · `profile_chain_mapper.py` · `ledger_frame.py` ·
  `mappers/ledger_lot_event_mapper.py` (커밋 `1aeda91`→`7eb415a`).
- 셋업 실사용 고통 P-01~04(`docs/process/SETUP_PAIN_LOG.md`)와 전 시나리오 검토
  (`docs/process/LEDGER_SETUP_SCENARIO_REVIEW.md`)가 이 계획의 요구사항 원천이다.
- 근본 원칙(소유자 승인): **사람이 선언을 쓰지 않는다 — 시스템이 초안하고,
  사람은 «문장»을 판정한다.** 자동 추정은 추론(3류)이고 승인이 확정이다.

## 최종 목표

1. **모든 소스가 mapper 경로 하나로 원장에 들어간다.** legacy 번역기 경로 0.
2. 관리자는 마법사에서 Pack claim을 고르고 role에 column을 잇는다 —
   predicate·signature·atom 분해는 기본 화면에 없다(v2 04 계약 그대로).
3. 관리자가 **문서를 열지 않고** 새 테이블 하나를 소스→원장→축·온톨로지까지
   연결하고, 현황판이 결핍을 이름으로 말한다.
4. 자유 기입 열거형 0 · 다음 행동 없는 거절문 0 · «영원히 조용»한 선언 0.

## 단계 목록

| 단계 | 파일 | 산출 |
|---|---|---|
| 1 | `01_CUTOVER_INVENTORY.md` | 전환표 + **등가 하니스** + lot-event 표준 개주(표준 첫 실증) |
| 2 | `02_PACK_LIBRARY.md` | 현행 세계를 덮는 Pack 7종 계약 |
| 3 | `03_DICTIONARY_CAPABILITIES.md` | 사전 API + 「답할 수 있는 질문」 렌더 |
| 4 | `04_WIZARD_EXTENSIONS.md` | v2 04 마법사에 인터뷰 정문·문장 판정 |
| 5 | `05_PIPELINE_BOARD_BACKFILL.md` | 현황판 + 백필 라우트 |
| 6 | `06_AGREEMENT_CHECKER.md` | 파일 간 합의·라이브 잎 실측 대조 |
| 7 | `07_LEGACY_RETIREMENT.md` | 소스별 등가 증명 후 legacy 은퇴 |

판정 대기(단계 밖): 불량 종류·주어 타입의 선언화(Pack이 요구하는 범위만),
R-O 뿌리 키의 mapper 계약 반영. 각각 짧은 판정 후 해당 단계에 흡수.

## 조사 대상 (1단계 착수 전)

- `server/ledger/chain_mapper.py` · `profile_chain_mapper.py` · `ledger_frame.py`
- `server/mappers/ledger_lot_event_mapper.py` — 리스트 짝짓기의 mapper 판 실물
- legacy: `lot_event_translator.py` · `observation_translator.py` ·
  `transfer_translator.py` · `declared_translator.py`(R-M ⑤판)
- `ledger/config.py`의 Profile 로딩·`dry_run.py`·`backfill.py` 확장분
- v2 플랜 01~03의 계약 문서와 충돌 여부

## 규율

- 코드 수정 전 조사·계획 보고 → 승인. 단계마다 `APPROVAL_MESSAGES.md`의
  게이트 문장으로 소유자 승인을 받고 다음 단계로 간다.
- 문서·코드·테스트가 충돌하면 추측하지 말고 보고한다.
- 각 단계 완료 보고: 변경 파일 · 테스트 결과 · 화면 경로(있으면) ·
  **뺀 것의 목록**(무언 누락 금지).

## 범위 개정 (소유자, 2026-08-17): 소스→원장 먼저 단단하게

**1·2단계(+ 필요시 5단계의 백필 라우트만)를 먼저 완주한다.** 3·4·6단계(사전·
마법사·검사기)와 5단계의 현황판은 그 뒤로 — 전부 소스→원장 신뢰 위의 편의층이다.

「단단하게」의 정의 (이 순서로 증명):
1. **등가** — 같은 행은 legacy와 mapper에서 같은 원자가 된다(1단계 하니스 실측).
2. **완비** — 현행 유입 경로 전부에 대응 Pack이 있고, 각 Pack의 전제(run 표·
   키·시각)가 선언에 명시된다(2단계).
3. **불변** — 게이트·드라이런·해소 문법은 mapper 경로에서도 한 글자도 다르게
   동작하지 않는다(기존 계약 보존 — v2 규칙 6).
