# Ledger v2 3단계 수락 근거

> 상태: `IN_REVIEW` · 승인: `NOT_APPROVED` · 2026-08-17
> 기준: `main@ac380e4` 위 `feature/ledger-v2-stage3-registries`

## 이번 5차 보완의 결론

1. Vocabulary가 object qualifier의 required/optional 닫힌 계약을 소유한다.
2. `kind=symbolic` Role이 `allowed_values`를 소유하고 미등록 constant를 거절한다.
3. catalog 선언은 verified가 아니다. 기존 virtual join verifier가 물리 UNIQUE index를
   확인한 뒤 만든 immutable `VerifiedJoinDescriptor`만 Snapshot compiler가 받는다.
4. `bundle_sha256`과 compiled semantic content의 `snapshot_sha256`을 분리했다.
5. `main@ac380e4`와 현재 브랜치의 전체 서버 스위트를 같은 Conda 환경·명령으로 비교했고,
   최종 현재 실행의 신규 실패/오류 node ID는 `0`이다.
6. 2차 audit가 재현한 public raw factory 우회를 제거했다. 이제 catalog mapping과 임의
   `unique_index` 문자열은 descriptor를 만들지 못하고 compiler에서도 구조화 거절된다.
7. 3차 audit가 재현한 private `_issue(..., issuer=...)` 우회와 무인자 constructor도 닫았다.
   compiler는 verifier가 실제 발급 등록한 object identity만 신뢰한다.
8. 4차 검토 중 확인된 module-level 발급 집합도 제거했다. identity 저장소·issuer class·token은
   closure 내부에 있고 외부 mutation handle이 없다.

Stage 4, source row, pandas, mapper 실행, Claim/RoleFrame 생성, cursor, gate/store, DB
read/write/migration은 구현하지 않았다.

## 변경 파일과 역할

| 파일 | 역할 |
|---|---|
| `server/ledger/setup_bundle.py` | Vocabulary qualifier와 symbolic Role domain의 schema·교차 검증 |
| `server/ledger/setup_registry.py` | descriptor 보존, 외부 verified join gate, compiled semantic snapshot hash |
| `server/verified_join_contract.py` | UI/Ledger 공용 neutral immutable `VerifiedJoinDescriptor` |
| `server/virtual_join_config.py` | 물리 UNIQUE 검증 성공 결과를 위 descriptor로 반환 |
| `server/tests/test_ledger_setup_bundle.py` | required/undeclared qualifier, symbolic literal 반례 |
| `server/tests/test_ledger_setup_registry.py` | descriptor, physical gate, two hashes, compiler version 반례 |
| `server/tests/test_virtual_join_guard.py` | 기존 verifier의 실제 반환 type/basis 검사 |
| `server/tests/test_virtual_join_executor.py` | UI executor도 같은 descriptor type을 소비하는 검사 |
| `ledger_v2_redesign_plan_20260817/*.md` | 승인 계약 복구와 config/구조/검수 근거 동기화 |
| `docs/overview/SYSTEM_OVERVIEW.md` | 전체 시스템 현재 사실 동기화 |
| `docs/process/{PROJECT_STATUS,DOC_OWNERSHIP}.md` | 단계 상태와 소유권 동기화 |
| `docs/history/*` | 변경 이력과 자동 인덱스 |

운영 manifest/config, 기존 mapper/translator/cursor/store, DB schema와 migration은 바꾸지 않았다.

## 최종 Registry와 qualifier/symbolic 계약

```text
LedgerSetupSnapshot
├─ bundle_canonical_json + bundle_sha256
├─ canonical_content_json + snapshot_sha256
├─ compiler_contract_version + readiness
├─ VocabularyRegistry
│  └─ PredicateDescriptor
│     └─ required_qualifiers + optional_qualifiers
├─ PackRegistry
│  └─ ClaimDescriptor
│     └─ RoleDescriptor
│        └─ kind + allowed_binding_kinds + allowed_values
├─ Entity/Preparer/Mapper/Profile Registry
├─ VerifiedJoinRegistry
│  └─ VerifiedJoinDescriptor(physical_unique_index)
└─ SourcePlanRegistry
   └─ Registry의 같은 VerifiedJoinDescriptor 인스턴스
```

- Vocabulary의 `object.qualifiers.required`는 Pack emission에 전부 있어야 한다.
- `required ∪ optional` 밖 qualifier는 emission에 있을 수 없다.
- symbolic Role은 정렬·중복 없는 non-empty `allowed_values`가 필수다.
- symbolic Role의 constant Binding은 등록값만 허용한다.
- time/identity/quantity 등 non-symbolic Role의 constant는 기존 deterministic JSON 계약을
  유지하며 symbolic domain으로 오인하지 않는다.
- Binding approval metadata는 그대로 보존되며 Claim epistemic class를 만들거나 승격하지 않는다.

## 실제 거절 출력

```json
{"code":"missing_required_payload","path":"bundle.packs.movement@1.claims.transition.emit.object.qualifiers.event_key","message":"predicate 'moves_to@1' requires qualifier 'event_key'"}
{"code":"unknown_payload_field","path":"bundle.packs.movement@1.claims.transition.emit.object.qualifiers.undeclared","message":"predicate 'moves_to@1' does not allow qualifier 'undeclared'"}
{"code":"invalid_symbolic_constant","path":"bundle.profiles.input-transition@1.mappings[0].bind.movement_kind.value","message":"constant 'NOT_REGISTERED_ANYWHERE' is not registered by symbolic role 'movement_kind'"}
{"code":"unverified_join","path":"bundle.virtual_joins.input_to_reference","message":"join rule 'input_to_reference' requires a physical UNIQUE verification descriptor"}
{"code":"verified_join_mismatch","path":"bundle.virtual_joins.input_to_reference","message":"physical verification descriptor does not match join rule 'input_to_reference'"}
```

모든 오류는 `code/path/message`를 가지며 `(path, code, message)` 순으로 결정적이다.

## Join verification 경계

```text
catalog declaration
  → virtual_join_config shape validation
  → PostgreSQL UNIQUE index physical proof
  → virtual_join_config private issuance capability
  → VerifiedJoinDescriptor
  ├─ virtual_join_executor
  └─ compile_setup_snapshot(..., verified_joins)
      → VerifiedJoinRegistry
      → SourcePlan (같은 object identity)
```

- compiler는 catalog 선언으로 descriptor를 만들지 않는다.
- descriptor는 mapping-compatible이지만 재귀 immutable이다.
- direct constructor와 raw mapping public factory가 모두 닫혀 있다.
- private issuance capability는 `virtual_join_config.load_verified_rules()`의 물리 검증 성공
  분기에서만 사용한다. capability를 직접 참조하더라도 loader 호출 위치 밖의 발급은 거절된다.
- 과거 `_issue` 진입점은 어떤 issuer를 넘겨도 항상 `TypeError`다. 무인자 constructor도
  `TypeError`다.
- compiler는 `isinstance`만 보지 않고 physical verifier가 발급 레지스트리에 등록한 object
  identity인지 확인한다. `object.__new__`로 만든 미발급 인스턴스도 거절한다.
- 발급 레지스트리, issuer class, bind token은 module attribute로 존재하지 않는다. compiler가
  호출하는 것은 읽기 전용 membership predicate뿐이다.
- compiler에 descriptor가 없거나 Bundle 선언과 다르면 구조화 오류로 거절한다.
- `setup_registry.py`와 neutral descriptor module은 DB/sqlalchemy/pandas를 import하지 않는다.

2차 audit의 exact 반례였던 `NOT_PROBED_FAKE_INDEX` raw mapping을 주입하면 ready snapshot이
생성되지 않고 다음 결정적 오류 두 건이 발생한다.

```json
{"code":"unverified_join","path":"bundle.virtual_joins.input_to_reference","message":"join rule 'input_to_reference' requires a physical UNIQUE verification descriptor"}
{"code":"invalid_verified_join","path":"verified_joins[0]","message":"must be a VerifiedJoinDescriptor produced by physical verification"}
```

`VerifiedJoinDescriptor.from_verified_rule`은 더 이상 존재하지 않는다. `_issue`는 항상
거절하며 정상 생성에 사용되지 않는다. Registry test의 정상
descriptor도 raw factory가 아니라 production `load_verified_rules()` 경로에서 물리 probe만
stub으로 대체해 얻는다.

## Snapshot hash

실제 정상 fixture:

```text
compiler_contract_version = 1
bundle_sha256              = 93bb700979a48a105153b6d1ae025a006bfd2531bd426519c8550333f693b38b
snapshot_sha256            = c45588c9ca735e3bb2667436043468797c799f7bf35f6b3c6c11810157220599
external re-hash           = true
```

`canonical_content_json`은 Bundle hash, compiled registries/source plans/readiness, selected
implementation versions, physical join verification result, compiler contract version,
chains/enrichments 선언을 포함한다. hash 자신, filesystem/config path, 현재 시각, Python
object identity는 포함하지 않는다.

다음 변경은 `snapshot_sha256`을 바꾸는 테스트로 고정했다.

- compiler contract version
- compiled descriptor content
- physical UNIQUE index verification result
- virtual join fold
- chain/enrichment declaration

같은 Bundle에서 physical verification만 바뀌면 `bundle_sha256`은 같고 `snapshot_sha256`만
달라진다.

## 전체 서버 기준선 비교

환경과 공통 명령:

```text
Conda: assy_manager
ASSY_DATA_ROOT: 현재 workspace의 server (두 실행 동일)
python -m pytest server/tests -q --tb=no -p no:cacheprovider --basetemp <전용경로> --junitxml=<전용파일>
```

| 실행 | passed | failed | errors | skipped | xfailed | bad node 수 |
|---|---:|---:|---:|---:|---:|---:|
| `main@ac380e4` 격리 worktree | 4010 | 145 | 23 | 207 | 1 | 168 |
| 현재 브랜치 1차 | 4068 | 143 | 23 | 204 | 1 | 166 |
| 현재 브랜치 재실행 | 4069 | 142 | 23 | 204 | 1 | 165 |

JUnit의 `classname::name`을 정렬한 bad node 집합 SHA-256:

```text
main                 1d1cc4f5344ec68ac0b635109d4c3731a447e501839877a9abb08b795d2ec45c
feature first        a4c8a2146b8d07bb990175268e69077f3511342095d39aadc3c69ccd04261f30
feature rerun        1713fb157f2e0710a9adb80a6a9876fd0186d86515b0850ac789301a3cbc51f8
```

최종 feature 재실행과 main의 정확한 집합 차이:

- 신규 failure/error node: `0`
- main에만 있는 node: `3`
  - `test_core_alignment_mapper::test_live_mapper_and_tracked_sample_are_byte_identical`
  - `test_core_usage_mapper::test_live_mapper_and_tracked_sample_are_byte_identical`
  - `test_dt_inventory_metadata_mapper::test_live_mapper_matches_tracked_sample`

위 3건은 새 worktree의 tracked sample이 `w/crlf`, live gitignored mapper hardlink가 `w/lf`라서
생긴 바이트 비교 환경 차이다. Git blob은 동일하다. 현재 브랜치 1차에만 있던
`test_h3_cross_directory_replace_applies_physical_alter` 1건은 재실행에서 사라졌고, 단독 반복도
연속 통과했으며 Stage 3 모듈 도달이 없는 watcher debounce timing flake로 분류했다.

따라서 같은 환경의 최종 full-suite 기준 Stage 3 신규 실패는 `0`이다. 기존 165개 bad node와
skip은 이번 단계에서 통과했다고 표현하지 않는다.

## 집중 검증

- Stage 2+3 Bundle/Registry: 직전 보완 `146 passed, 1 skipped`; 이번 변경이 직접 닿는 Registry
  단독 `46 passed`
- qualifier/Registry/virtual join 영향군: `219 passed, 1 skipped`
- 동결 LedgerFrame chain mapper: `29 passed`
- 수정 Python `py_compile`: 통과
- `git diff --check`: 통과
- PostgreSQL 운영/격리 DB: 연결·실행하지 않음
- DB read/write/migration: `0`

사용자 지시에 따라 이번 3차 보완에서는 전체 서버 suite를 다시 실행하지 않았다. 직전 대상
커밋 `ecbb335`의 독립 audit full-suite는
`4063 passed, 145 failed, 23 errors, 207 skipped, 1 xfailed`로 완주했으며, 장시간
`ac380e4` baseline 중복 실행은 사용자 요청으로 중단했다. 위의 과거 동일환경 baseline 비교
근거는 보존하되 이번 fix에 대해 full-suite 신규 통과를 주장하지 않는다.

## 아직 미완료

- Stage 3 사용자·독립 audit 최종 승인
- Stage 4 RoleFrame/Pack compiler
- Stage 5 SourcePreparer/runtime 연결
- Stage 6 PostgreSQL E2E와 cursor/gate/store
- Stage 7 cutover/legacy retirement

자체 판정: Stage 3 재검수를 요청할 수 있다. 승인 전 상태는 계속
`STAGE_3_IN_REVIEW / NOT_APPROVED`이며 Stage 4를 시작하지 않는다.
