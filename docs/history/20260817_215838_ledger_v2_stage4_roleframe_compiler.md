# Ledger V2 Stage 4 RoleFrame·Pack compiler 구현

## 현상과 원인

기존 mapper는 최종 Atom/LedgerFrame payload를 직접 만들 수 있어 Profile Role, Pack emission,
Vocabulary 계약이 다시 갈릴 위험이 있었다. 또한 선언형 source와 Python source가 서로 다른
외부 반환형을 사용하면 공통 검증과 provenance를 한 번에 적용할 수 없었다.

## 수정

- EventFrame의 다섯 immutable context와 Snapshot hash를 검증한다.
- `BaseLedgerMapper.map()`이 unit partition, RoleEmission 조립, RoleFrame 검증과 정렬을 소유한다.
- 단순 source는 `DeclarativeRoleMapper`, 복잡 source는 등록 `interpret_unit()`만 사용한다.
- sealed implementation registry가 `map()` override와 미등록 구현을 거절한다.
- Pack compiler만 EntityRef/value/event_ref payload를 만들고 Vocabulary/Entity 서명을 재검증한다.
- dry-run은 RoleFrame, LedgerFrame, gate preview, provenance, snapshot hash만 반환하고 쓰지 않는다.

## 반례와 검증

raw Atom/DataFrame 반환, 다른 stage Entity 대입, Entity key 오형상, naive time, snapshot mismatch,
중복 source row identity, unsealed registry를 구조화 오류로 고정했다. Mapper 내부
`group_by` 열은 Source Driver event grouping과 분리된 닫힌 Mapper input 계약으로 보강했다.
Stage 4 직접 테스트는 `23 passed`, Setup/Registry/LedgerFrame 직접 영향군은
`205 passed, 1 skipped`다. skip은 Windows
symlink 생성 권한 부재다. 전체 서버 suite는 사용자 지시에 따라 실행하지 않았다.

## 경계

DB, source driver, cursor, gate/store, translator, 운영 config는 변경하지 않았다. Stage 4는
`IN_REVIEW / NOT_APPROVED`이며 독립 Audit 전에는 Stage 5를 시작하지 않는다.
