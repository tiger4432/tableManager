# Ledger v2 재설계 계획 — Kernel 유지, Setup/Compiler 재작성

> 상태: `STAGE_5_IN_PROGRESS` · 승인: `NOT_APPROVED` · 1·2·3·4단계 승인
> 작성일: 2026-08-17
> 범위: Source → pandas event frame → Pack compiler → LedgerFrame
> 유지: 기존 Ledger gate/store/cursor/read API

## 결론

원장 전체를 지우고 다시 만들지 않는다. 검증된 Ledger Kernel은 유지하고, 하드코딩이
집중된 Setup/Compiler 계층을 v2로 재작성한다.

```text
유지
  Ledger envelope / gate / store / cursor / resolver / trace API

재작성
  source 선언 / stage-local Entity / Pack / emission / mapper 입력 계약
  cursor 이후 pandas source-preparation 경계
```

새 설계의 한 줄 계약:

```text
ontology/catalog/tables.json + physical source
  → 기존 cursor가 base relation을 읽음
  → source preparer가 배치 join/enrich 후 pandas EventFrame 생성
  → ontology config directory를 logical LedgerSetupBundle로 컴파일
  → generic binding 또는 Python mapper가 pandas RoleFrame 생성
  → Pack compiler만 LedgerFrame 생성
  → 기존 gate → LedgerStore → cursor
```

Python mapper가 raw `Atom`이나 `object_payload`를 직접 만들지 않는 것이 이번 재설계의
핵심이다. 기본 `BaseLedgerMapper`가 검증·unit partition·RoleFrame 조립을 공통 소유하고,
복잡한 mapper는 제한된 해석 훅에서 Role 값만 계산한다. 외부 출력은 항상 pandas RoleFrame이고
source stage entity에서 target stage entity로 향하는 Claim은 Pack emission 계약이 단독
소유한다. v2에는 Position 객체·Role·Registry를 만들지 않는다.

## 읽는 순서

1. `00_MASTER_PLAN.md`
2. `TARGET_ARCHITECTURE_AND_SSOT.md`
3. `CONFIG_CANON.md`
4. `COMMON_RULES.md`
5. `MAPPER_DESIGN_PATTERN.md`
6. `OPEN_DECISIONS.md`
7. `01_FREEZE_AND_HARDCODING_INVENTORY.md`
8. `02_LEDGER_SETUP_BUNDLE.md`
9. `03_REGISTRIES_AND_CROSS_VALIDATION.md`
10. `04_ROLEFRAME_AND_PACK_COMPILER.md`
11. `05_SOURCE_DRIVER_AND_JOIN_BOUNDARY.md`
12. `06_SHADOW_PARITY_AND_POSTGRES_E2E.md`
13. `07_CUTOVER_RESET_AND_RETIREMENT.md`
14. `APPROVAL_GATES.md`

## 단계 상태

| 단계 | 산출물 | 현재 |
|---|---|---|
| 1 | 동결 경계·하드코딩 전수표·baseline | 승인 (`APPROVED`) |
| 2 | 단일 `LedgerSetupBundle` 계약 | 승인 (`APPROVED`) |
| 3 | Entity/Pack/Source Registry·교차 검증·결정적 snapshot | 승인 (`APPROVED`) |
| 4 | RoleFrame·Pack compiler·generic emitter | 승인 (`APPROVED`) |
| 5 | 기존 driver/cursor + pandas source preparation 연결 | 진행 중 (`IN_PROGRESS` / `NOT_APPROVED`) |
| 6 | shadow parity·PostgreSQL E2E·scale 검증 | 미착수 |
| 7 | 설정 전환·선택적 DB reset·legacy 은퇴 | 미착수 |

각 단계는 별도 승인을 받은 뒤 시작한다. 7단계 전에는 원장 데이터 삭제, cursor reset,
legacy 코드 삭제를 하지 않는다.

1단계 근거: [Inventory](./HARDCODING_INVENTORY.md) ·
[Call Graph](./CURRENT_CALL_GRAPH.md) · [Baseline](./BASELINE_RESULTS.md) ·
[Keep/Move/Retire](./KEEP_MOVE_RETIRE_MATRIX.md)

2단계 근거: [수락 근거](./STAGE_2_ACCEPTANCE_EVIDENCE.md) ·
구현 `server/ledger/setup_bundle.py` · 테스트 `server/tests/test_ledger_setup_bundle.py`.

3단계 근거: [수락 근거](./STAGE_3_ACCEPTANCE_EVIDENCE.md) ·
구현 `server/ledger/setup_registry.py` · 테스트 `server/tests/test_ledger_setup_registry.py`.

4단계 근거: [수락 근거](./STAGE_4_ACCEPTANCE_EVIDENCE.md) ·
구현 `server/ledger/roleframe.py` · 테스트 `server/tests/test_ledger_roleframe.py`.

## 기존 계획과의 관계

`_archive/ledger_setup_migration_plan/`과
`_archive/ontology_codex_plan_v2_20260817/`은 조사 자료다. 기존 계획의 Profile 승인
metadata, 결정적 직렬화, gate/store/cursor 보존 원칙은 재사용한다. 다음 가정은 폐기한다.

- Python mapper가 최종 `Atom/LedgerFrame` payload를 직접 조립한다.
- 이동 위치를 `{type, keys, position}` payload로 모델링한다.
- Ledger Profile/compiler가 DB lookup을 실행한다.
- Pack Role, emitter payload, Vocabulary signature가 서로 다른 정본이다.

## Config 정본 판정

authoring 정본은 `server/config/ontology/` 한 루트다. 그 안에서 Pack/Profile/Registry는
`ledger_config.json` 한 파일에 함께 두고, 물리 catalog와 dataflow만 하위 폴더로 분리한다.
Registry는 `ledger_config.json` 각 section의 immutable 읽기 모델이며 등록 데이터를 Python
builtin에 두지 않는다.

구조는 `TARGET_ARCHITECTURE_AND_SSOT.md`, 각 config의 역할·금지 경계·legacy 이동표는
`CONFIG_CANON.md`를 정본으로 한다.

## Lookup 제거 판정

v2 Profile, Bundle, Registry, Pack compiler에는 `lookup`, `declared_lookup`,
`LookupRegistry`가 없다. 현재 virtual join은 웹 조회 응답에 붙는 계산값이라 Ledger cursor가
직접 읽을 수 없다. 따라서 cursor는 base relation과 watermark만 읽고, 그 결과 DataFrame을
source preparer가 **승인된 virtual join rule을 ID로 상속**해 배치 join/enrich하고 완성된
EventFrame으로 반환한다. join key/expose/표기 정규화/UNIQUE 근거를 다시 적지 않는다.
관계 결손·다건은 compiler가 추측하지 않고 source-preparation 오류로 거절한다.

## 이번 폴더가 하지 않는 것

- 코드 구현
- DB migration/write/reset
- UI·Trace API 개편
- 과거 원장 데이터 삭제
- 모든 미래 Pack 선설계
- 임의 SQL/Python/expression DSL
