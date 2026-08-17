# Ledger v2 Mapper RoleFrame 디자인 패턴 확정

## 현상

Ledger v2 계획은 Source Preparer가 완성 EventFrame을 만든 뒤 Mapper가 pandas RoleFrame을
반환한다는 큰 경계는 갖고 있었지만, Mapper마다 공통 처리와 자유 코드를 어디까지 허용할지
단일 작성 패턴이 없었다. 루트 `MAPPER_STANDARD.md`를 그대로 적용하면 Mapper 최종 반환을
Claim 목록으로 오해할 여지도 있었다.

## 근본 원인

Source Preparer, Mapper, Pack Compiler의 책임은 나뉘었지만 Mapper 자체의 기본 구현,
재정의 금지 지점, config descriptor, 출력 검증 계약이 계획 문서 여러 곳에 흩어져 있었다.
또 `ledger_config.json`의 authoring section에 Source Preparer는 있었으나 Mapper Registry가
명시되지 않아 source가 실행 구현을 어떻게 선택하는지 불완전했다.

## 결정과 해결

- Source Preparer는 verified virtual join을 상속해 완성 pandas EventFrame을 만드는 기존 목표를
  유지한다.
- Mapper의 외부 계약을 `EventFrame → pandas RoleFrame`으로 확정했다.
- `BaseLedgerMapper.map()`이 입력 검증, 선언 unit partition, RoleFrame 조립·검증, 결정적 정렬을
  공통 소유하고 하위 클래스의 재정의를 금지한다.
- 단순 source는 기본 `DeclarativeRoleMapper`, 복잡한 source는 등록 Python Mapper를 사용한다.
- Python Mapper의 자유 코드는 `interpret_unit()`에서 닫힌 `RoleEmission`을 만드는 부분뿐이다.
- Pack Compiler만 RoleFrame을 LedgerFrame으로 변환한다. Mapper의 Atom, payload dict,
  LedgerFrame 직접 생성은 금지한다.
- `ledger_config.json`에 `mappers` section과 `MapperRegistry`를 추가하고 source의
  `driver.mapper_id`가 이를 참조하도록 정리했다.
- 실행 가능한 module/function/path는 config에 두지 않고 trusted implementation class만 코드가
  제공한다.

상세 정본은 `ledger_v2_redesign_plan_20260817/MAPPER_DESIGN_PATTERN.md`다.

## 변경 파일

- `ledger_v2_redesign_plan_20260817/MAPPER_DESIGN_PATTERN.md`: 공통 기본 구현, 자유 훅,
  RoleFrame 반환, config 연결과 수락 테스트 신설
- `README.md`, `00_MASTER_PLAN.md`, `TARGET_ARCHITECTURE_AND_SSOT.md`: 목표 흐름과 읽는 순서 동기화
- `CONFIG_CANON.md`, `02_LEDGER_SETUP_BUNDLE.md`, `03_REGISTRIES_AND_CROSS_VALIDATION.md`:
  `mappers` section, Registry, source 참조와 교차 검증 추가
- `04_ROLEFRAME_AND_PACK_COMPILER.md`, `06_SHADOW_PARITY_AND_POSTGRES_E2E.md`,
  `APPROVAL_GATES.md`: 기본/등록 Mapper의 동일 RoleFrame 계약과 수락 조건 추가
- `COMMON_RULES.md`, `OPEN_DECISIONS.md`: Mapper 출력과 자유 코드 경계 확정
- `docs/overview/SYSTEM_OVERVIEW.md`, `docs/process/DOC_OWNERSHIP.md`: 리빙 문서 링크와 목표 상태 동기화

## 사이드 이펙트 분석

- 현행 코드, API, DB schema, cursor, store, source preparer 실행에는 변화가 없다.
- 향후 Bundle schema의 authoring section이 하나 늘어나므로 단계 2 validator와 deterministic
  serialization은 `mappers`를 포함해야 한다.
- 향후 단계 3은 Preparer output schema ↔ Mapper input, Mapper emits ↔ Profile/Pack을 시작 시점에
  교차 검증해야 한다.
- 향후 단계 4는 기존 function mapper가 아니라 공통 Base 구현을 통과해야 하며, 현행
  `ledger_lot_event_mapper.py`는 parity 후 개주 대상이다.
- Mapper에 DB capability를 주지 않으므로 N+1 join 책임은 계속 Source Preparer에만 남는다.

## 검증

- 대상 문서 전체에서 낡은 section 수, 평면 source mapper/preparer 참조, Mapper 직접 LedgerFrame
  반환 목표 문구를 검색했다.
- `git diff --check`로 대상 문서의 whitespace 오류가 없음을 확인했다.
- 계획 문서 변경만 수행했다. 코드 구현, 테스트 실행, DB migration/write, cursor 변경은 없다.

## 미완료

- `BaseLedgerMapper`, `DeclarativeRoleMapper`, `MapperRegistry`, RoleFrame validator는 아직 구현하지
  않았다.
- 단계 4 구현은 이전과 같이 별도 사용자 승인 전 시작하지 않는다.
