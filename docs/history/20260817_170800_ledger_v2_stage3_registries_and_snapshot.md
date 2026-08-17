# Ledger V2 Stage 3 — config-only Registries and immutable snapshot

## 현상

2단계 `LedgerSetupBundle`은 모든 선언을 구조·교차 검증하고 결정적으로 직렬화했지만 실행
계층이 소비할 불변 Registry와 setup version이 없었다. source별 runtime에서 원본 dict를 다시
해석하면 Pack Role, 구현 ID, virtual join 참조를 각 소비자가 재조립해 정본이 갈릴 위험이 있다.

## 근본 원인

검증된 config와 후속 실행 계획 사이에 compiled read model이 없었다. 특히 다음 경계가
명시적 객체로 봉인되지 않았다.

- Pack → Claim → Role/Emission
- Vocabulary/Entity/Preparer/Mapper/Profile의 versioned descriptor
- Source Driver → Preparer/Mapper/Profile/VerifiedJoin의 동일 snapshot 참조
- trusted implementation ID와 version의 fail-closed 연결
- config 전체를 대표하는 결정적 content hash

## 수정

`server/ledger/setup_registry.py`를 추가했다. compiler는 `LedgerSetupBundle`을 다시 검증하고
모든 중첩 Binding의 approval readiness를 확인한 뒤에만 snapshot을 만든다.

```python
issues = snapshot_compile_errors(bundle, trusted)
if issues:
    raise issues[0]
bundle = validate_bundle(bundle.to_mapping())
canonical_json = bundle.serialize()
snapshot_hash = sha256(canonical_json.encode("utf-8")).hexdigest()
```

각 section은 add-only builder를 거쳐 sealed Mapping Registry가 된다. descriptor의 중첩 dict와
list도 `MappingProxyType`과 tuple로 바꿔 snapshot 이후 변경할 수 없다.

```python
SourcePreparationPlan(
    preparer=preparers[preparation["preparer_id"]],
    verified_join_descriptors=tuple(
        verified_joins[rule_id]
        for rule_id in preparation["inherit_virtual_join_rules"]
    ),
)
```

따라서 Source Plan은 Registry의 같은 `VerifiedJoinDescriptor` 인스턴스를 참조한다. join key,
expose, folding을 source plan에 다시 쓰지 않는다. trusted code도 config의 module/function/path가
아니라 닫힌 `(implementation_id, implementation_version)` pair로만 대조한다.

이 단계의 `verified`는 DB 실측이 아니라 catalog의 exact UNIQUE 선언 검증이다.
`verification_basis=catalog_declared_unique`를 descriptor에 넣어 둘을 혼동하지 않는다. 현행 UI
executor와의 실제 공유는 source preparation/runtime 연결 단계로 남겼다.

Role의 effective `allowed_binding_kinds`는 validator와 compiler가 각각 계산하지 않도록
`setup_bundle.role_binding_kinds()` 한 함수로 합쳤다.

독립 감사에서 나온 실행 불가능 snapshot 반례를 닫았다. inherited join의 left key는
선택 Preparer의 `input_columns`에 필수이고, fold는 닫힌 notation rule grammar를 통과한
경우만 verified descriptor가 된다. 복수 version 조회, seal 후 builder 거절, trusted-but-unused
구현체 보존도 반례로 고정했다. v1 Bundle에 없는 임의 payload-field 및 symbolic
constant domain은 새 schema를 발명하지 않고 후속 승인 변경으로 명시했다.

## 반례와 검증

- 사용·미사용 mapper/preparer의 unknown implementation과 version mismatch를 정확한
  `code/path/message`로 거절한다.
- pending/rejected와 중첩 Entity key Binding은 snapshot 생성 전에 거절한다.
- inherited join의 missing/disabled/left mismatch/UNIQUE 근거 실패를 거절한다.
- source preparation에 join 계약을 복사하면 `unknown_field`로 거절한다.
- 새 Entity/Predicate/Pack config entry는 compiler 수정 없이 Registry에 들어간다.
- source/table/column을 전부 바꾼 동일 Pack은 같은 Pack descriptor로 컴파일된다.
- Bundle key 순서와 config root 경로는 hash에 영향을 주지 않고 virtual join/dataflow 변경은
  hash를 바꾼다.
- 정상 fixture hash는 `b843cc9c3662d48a377a289818570d0ad66f951e574cf104cd3809654ffb090d`다.
- 독립 audit은 대소문자 금지 키까지 포함한 최종 diff를 `APPROVE`했다. 제품 상태는
  사용자 재승인 전까지 `IN_REVIEW / NOT_APPROVED`다.

실제 결과:

- Stage 3 전용: `35 passed`
- Stage 2+3: `128 passed, 1 skipped`
- 동결 mapper: `29 passed`
- 전체 서버: `4040 passed, 143 failed, 23 errors, 204 skipped, 1 xfailed`

전체 실패/오류는 현재 config/fixture, map alignment, audit/API/launcher 등 기존 범위이며 새
Bundle/Registry 테스트에는 없다. 같은 환경의 main 전체 baseline을 별도로 재실행하지 않았으므로
전체 suite 신규 실패 0이라고 주장하지 않는다. 변경 도달 범위의 신규 실패는 0이다.

## 사이드 이펙트와 금지 경계

- `setup_registry.py`는 DB, pandas, runtime mapper, cursor, gate/store를 import하지 않는다.
- source row read, RoleFrame/LedgerFrame 생성, mapper/translator 실행, DB migration/write는 0이다.
- 운영 manifest/config와 동결 legacy 실행 코드는 수정하지 않았다.
- snapshot 생성은 입력 Bundle을 변경하지 않고 메모리 크기는 config descriptor 수에 비례한다.
  source 데이터 행 수와 무관하므로 1,000만 행 경로에 per-row 비용을 추가하지 않는다.
- 4단계는 `IN_REVIEW / NOT_APPROVED`인 3단계의 사용자 승인 전 시작하지 않는다.
