# Ledger V2 Stage 3 — 2차 audit 차단사항 보완

## 상태

- 현재 단계: `STAGE_3_IN_REVIEW`
- 승인: `NOT_APPROVED`
- 다음 단계: Stage 3 독립 재검수 전 Stage 4 금지
- 기준: `main@ac380e4`, 선행 Stage 3 커밋 `8c37f39`

## 현상

선행 Stage 3 구현은 Registry 불변성과 config-only compiler를 만들었지만 네 의미 계약을
충족하지 못했다.

1. Vocabulary가 required/allowed qualifier를 소유하지 않아 Pack의 누락·임의 field가 통과했다.
2. symbolic Role의 등록 literal domain이 없어 임의 constant가 통과했다.
3. DB-free catalog 선언이 `verified=True/catalog_declared_unique`로 승격됐다.
4. Snapshot hash가 Bundle 직렬화만 가리켜 compiled content와 physical verification을 묶지 않았다.

게다가 이 미구현을 구현하는 대신 3단계 승인 기준을 완화한 문서 변경이 있어, audit이 원래
계약 복구와 구현 보완을 요구했다. 전체 서버의 동일 main 기준선도 없었다.

## 근본 원인

- PredicateDescriptor가 payload/qualifier field contract를 표현하지 못했다.
- RoleDescriptor가 literal domain을 표현하지 못했다.
- catalog shape/UNIQUE 선언과 PostgreSQL의 실제 UNIQUE index proof를 같은 등급으로 취급했다.
- Bundle input identity와 compiled execution contract identity를 하나의 hash로 취급했다.
- 이전 전체 테스트 결과는 main의 exact failed node 집합과 비교되지 않았다.

## 수정

### Vocabulary와 symbolic Role

Vocabulary object에 닫힌 `qualifiers.required/optional` 계약을 추가했다. Pack emission은 required
field 누락을 `missing_required_payload`, 목록 밖 field를 `unknown_payload_field`로 거절한다.

`kind=symbolic` Role은 정렬·중복 없는 non-empty `allowed_values`를 필수로 소유한다. Profile의
constant Binding이 목록 밖이면 `invalid_symbolic_constant`로 거절한다. non-symbolic constant는
기존 deterministic JSON 계약을 그대로 사용한다.

### 물리 검증 Join descriptor

`server/verified_join_contract.py`에 neutral immutable `VerifiedJoinDescriptor`를 추가했다.
기존 `virtual_join_config.load_verified_rules()`가 PostgreSQL UNIQUE index를 확인한 뒤에만 이
descriptor를 만든다. UI executor는 loader 결과를 그대로 소비하고, Snapshot compiler는 외부로
주입된 같은 type을 `VerifiedJoinRegistry`와 `SourcePlan`에 복사 없이 넣는다.

catalog 선언만으로 descriptor direct construction은 불가능하고, descriptor 부재·중복·불일치·
미등록 주입은 구조화 오류로 거절한다. compiler에는 DB import/read가 없다.

### 두 hash

`bundle_sha256`은 canonical Bundle input을 보존한다. `snapshot_sha256`은 다음 canonical content를
묶는다.

- Bundle hash
- compiler contract version
- compiled Registry와 SourcePlan
- selected implementation version
- physical join verification result
- readiness
- chain/enrichment declaration

filesystem/config path, 시간, Python object identity와 hash 자신은 입력에서 제외한다. 정상 fixture의
실제 값은 다음과 같다.

```text
bundle_sha256   93bb700979a48a105153b6d1ae025a006bfd2531bd426519c8550333f693b38b
snapshot_sha256 c45588c9ca735e3bb2667436043468797c799f7bf35f6b3c6c11810157220599
```

## 반례

```json
{"code":"missing_required_payload","path":"bundle.packs.movement@1.claims.transition.emit.object.qualifiers.event_key","message":"predicate 'moves_to@1' requires qualifier 'event_key'"}
{"code":"unknown_payload_field","path":"bundle.packs.movement@1.claims.transition.emit.object.qualifiers.undeclared","message":"predicate 'moves_to@1' does not allow qualifier 'undeclared'"}
{"code":"invalid_symbolic_constant","path":"bundle.profiles.input-transition@1.mappings[0].bind.movement_kind.value","message":"constant 'NOT_REGISTERED_ANYWHERE' is not registered by symbolic role 'movement_kind'"}
{"code":"unverified_join","path":"bundle.virtual_joins.input_to_reference","message":"join rule 'input_to_reference' requires a physical UNIQUE verification descriptor"}
{"code":"verified_join_mismatch","path":"bundle.virtual_joins.input_to_reference","message":"physical verification descriptor does not match join rule 'input_to_reference'"}
```

## 검증

- Stage 2+3: `146 passed, 1 skipped`
- qualifier/Registry/virtual join 영향군: `215 passed, 1 skipped`
- 동결 LedgerFrame chain mapper: `29 passed`
- 수정 Python `py_compile`: pass
- `git diff --check`: pass

전체 서버 동일 명령 비교:

| 실행 | 결과 | bad node |
|---|---|---:|
| `main@ac380e4` | `4010 passed, 145 failed, 23 errors, 207 skipped, 1 xfailed` | 168 |
| feature 1차 | `4068 passed, 143 failed, 23 errors, 204 skipped, 1 xfailed` | 166 |
| feature 재실행 | `4069 passed, 142 failed, 23 errors, 204 skipped, 1 xfailed` | 165 |

최종 feature bad node 집합은 main 집합의 부분집합이며 신규 node는 `0`이다. main에만 있는
mapper byte-identity 3건은 새 worktree의 CRLF sample과 LF live mapper hardlink 차이다. feature
1차에만 있던 config watcher timing 1건은 재실행에서 사라졌고 단독 반복도 통과했다.

기존 165 bad node와 204 skip을 통과로 표현하지 않는다. PostgreSQL 운영/격리 DB는 연결하지
않았고 DB read/write/migration은 0이다.

## 문서와 범위

감사에서 삭제·완화됐다고 지적한 3단계 승인 기준 5개를 원래 의미로 복구했다. Config canon,
target architecture, setup bundle 예시, system overview, ownership, project status, Stage 3 evidence를
실제 구현과 동기화했다.

runtime, mapper/translator/cursor/gate/store, 운영 config, DB schema/migration은 변경하지 않았다.
Stage 3는 아직 승인되지 않았고 Stage 4를 시작하지 않는다.
