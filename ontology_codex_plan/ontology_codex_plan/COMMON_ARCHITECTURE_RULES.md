# 모든 단계 공통 아키텍처 규칙

아래 규칙은 각 단계 지시서와 함께 Codex에 제공한다.

## 범용성 경계

첫 수락 사례는 Bonding→DT→Core Lot/Slot 추적이지만 공통 기반을 이 사례 전용으로 구현하지 않는다.

다음 구성요소는 도메인 이름을 모르는 범용 기반이어야 한다.

- `SourceOntologyProfile`
- template registry
- compiler registry
- source adapter registry
- profile validator
- dry-run 및 preview
- trace request/result model
- trace walker
- target matcher
- template metadata 기반 UI form renderer

Bonding, DT, Core, `dt_log`, `bonding_log` 같은 이름은 다음 위치에만 존재할 수 있다.

- Profile 인스턴스
- template 또는 source adapter 등록 데이터
- fixture
- Lot/Slot 제품 facade
- 사용자 표시 label

공통 엔진 내부에서 다음 형태를 금지한다.

```text
if source == "dt_log"
if source == "bonding_log"
if step == "DT"
if step == "CORE"
trace_bonding_to_dt_to_core
고정된 DT_LOT/DT_SLOT/CORE_WAFER UI 컬럼 배열
```

source별 차이는 조건문이 아니라 registry와 adapter로 주입한다.

```text
TemplateRegistry
CompilerRegistry
SourceAdapterRegistry
TargetMatcherRegistry
```

Trace walker는 단계명을 기준으로 걷지 않고 기존 정준 원장의 다음 요소만 해석한다.

- subject identity
- predicate
- structured `from`/`to`
- `occurred_at`
- claim rank
- 선언된 traversal rule

Lot/Slot 전용 API는 범용 trace engine을 호출하는 얇은 facade여야 하며 별도의 탐색 알고리즘을 가져서는 안 된다.

새 사용 사례는 공통 엔진 수정 없이 다음 중 하나를 등록하여 확장할 수 있어야 한다.

- 새 Profile
- 새 Event Template
- 새 Source adapter
- 새 target matcher
- 새 표시 label

단, 미래를 추측해 범용 DSL·graph query language·동적 Python 생성기·플러그인 프레임워크 전체를 미리 만들지 않는다. 첫 수락 사례에 필요한 최소 인터페이스와 명시적인 확장 지점만 만든다.

## 기존 계약 보존

- `ledger_events`는 append-only 정준 원장이다.
- 기존 `/api/ledger/*` 계약을 깨지 않는다.
- 기존 translator와 수동 config 경로를 최소 한 릴리스 유지한다.
- provenance, `source_translator_ver`, `source_raw_ref`의 의미를 바꾸지 않는다.
- molecule atomicity, refusal, incomplete 집계를 보존한다.
- claim ranking과 measured-over-setpoint 규칙을 보존한다.
- `slot_preserving`은 observation이 아니라 inference로 유지한다.
- graph storage와 graph sync worker를 부활시키지 않는다.
- 설정 오류는 fail-closed 처리한다.
- dry-run과 조회는 DB에 쓰지 않는다.
- 현재 git 작업트리의 사용자 변경을 덮어쓰지 않는다.

## 공통 구조 테스트

1. 공통 모듈이 `bonding`, `dt_log`, `core` 같은 사례 문자열을 참조하지 않는다.
2. fixture의 source 이름과 컬럼명을 바꿔도 같은 template으로 compile된다.
3. 동일 template을 서로 다른 source와 컬럼에 재사용할 수 있다.
4. 새 adapter 등록 시 기존 compiler 본체 수정이 필요하지 않다.
5. Lot/Slot facade와 대응하는 범용 trace 호출이 의미상 같은 결과를 반환한다.
6. 기존 관련 테스트가 계속 통과한다.

