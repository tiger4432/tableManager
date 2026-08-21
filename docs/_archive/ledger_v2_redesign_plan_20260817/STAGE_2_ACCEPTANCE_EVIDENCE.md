# Ledger v2 2단계 수락 근거

> 상태: `COMPLETE` · 승인: `APPROVED` · 2026-08-17 사용자 승인

## 변경 파일과 역할

| 파일 | 역할 |
|---|---|
| `server/ledger/setup_bundle.py` | 순수 Bundle schema, strict manifest loader, 결정적 정규화/직렬화, 교차 검증, readiness |
| `server/tests/test_ledger_setup_bundle.py` | 2단계 계약과 금지 경계 자동 테스트 |
| `server/config/ontology/README.md` | 향후 authoring root와 비활성 상태 안내 |

운영 `manifest.json`과 config JSON은 만들지 않았다. 현재 runtime이 이 root를 읽지 않는다.

## 최종 Logical Bundle

```json
{
  "setup_version": 2,
  "tables": {},
  "virtual_joins": {},
  "vocabulary": {},
  "entities": {},
  "source_preparers": {},
  "mappers": {},
  "packs": {},
  "profiles": {},
  "sources": {},
  "chains": {},
  "enrichments": {}
}
```

Manifest는 `ledger`, `catalog.tables`, `catalog.virtual_joins`, `dataflows.chains`,
`dataflows.enrichments` 다섯 파일을 정확히 지정한다. loader는 root 밖 경로, glob, 중복 경로,
미등재 JSON, 중복 JSON key를 거절한다.

Binding은 `column`, `constant`, `entity`만 허용한다. 모든 Binding은
`binding_origin`과 `approval_status`를 보존하며 `system_suggested`에는
`suggestion_reason`이 필수다. 승인 metadata는 Claim의 epistemic class를 만들거나 바꾸지
않는다. 구조 검증과 실행 준비 판정은 분리되어 pending/rejected가 readiness에서 차단된다.

## 실제 오류 계약 예

```json
{"code":"unsupported_setup_version","path":"bundle.setup_version","message":"supported setup_version is 2"}
{"code":"unknown_relation","path":"bundle.sources.input_rows.relation","message":"unknown relation 'absent'"}
{"code":"invalid_binding","path":"bundle.profiles.input-transition@1.mappings[0].bind.target.kind","message":"unsupported binding kind 'declared_lookup'"}
{"code":"binding_not_approved","path":"bundle.profiles.input-transition@1.mappings[0].bind.target.approval_status","message":"binding approval_status is 'pending', expected 'approved'"}
```

오류 목록은 `(path, code, message)` 순으로 결정적으로 정렬된다.

## 재승인 보완 계약

- 구조 오류가 하나라도 있으면 semantic lookup을 시작하지 않고 구조 오류 목록을 반환한다.
- 모든 Vocabulary/Pack과 미사용 Profile/Mapper의 참조도 source 연결 여부와 무관하게 검사한다.
- emission의 subject/time/entity object는 required Role과 목적별 kind를 요구하고 qualifier는
  scalar Role의 required/optional 표기와 일치해야 한다.
- Profile `packs` ↔ mapping `use` ↔ Source가 선택한 Mapper `emits`를 양방향 대조한다.
- Profile의 모든 leaf column은 Mapper `input_columns`에 있어야 하며 Preparer output은 input 및
  source 물리 열과 충돌할 수 없다.
- Source unit은 `row|group`, Mapper unit은 `event|row|group_by`로 닫고 group 계약을 검사한다.
- catalog business/composite/index 열의 존재와 join 오른쪽 exact UNIQUE 근거를 검사한다.

### f03b165 후속 validator 보완

- **모든 Profile 참조:** Source가 직접 선택하지 않은 Profile도 `Profile.source`가 가리키는
  Source의 physical relation과 Preparer EventFrame schema로 entity type과 모든 leaf column을
  검사한다. 선택 여부와 무관하게 같은 `_cross_profile_source` 경로를 정확히 한 번 통과한다.
- **cursor 결정적 전순서:** `order_by`와 `cursor.columns`는 각각 catalog가 선언한
  `business_key`, `composite_key`, 또는 `unique: true` index 중 하나의 전체 열을 포함해야 한다.
  identity/group/일반 index/단순 열 존재는 UNIQUE 근거가 아니다.
- **금지 실행 키 완전 탐색:** `chains`와 `enrichments`를 Mapping과 JSON 배열의 임의 중첩까지
  반복 탐색하며 `sql` 등 금지 키를 실제 leaf path의 `unsafe_declaration`으로 거절한다.
  문자열·bytes·bytearray는 배열로 취급하지 않는다.
- **Entity `key_types` leaf:** key 집합은 `keys`와 정확히 같아야 하고 각 값은 trimmed non-blank
  string이어야 한다. 새 타입 enum은 만들지 않았으며 객체·배열·null·bool·숫자·공백은 leaf
  path의 구조화 오류로 거절한다.

## 검증 결과

- f03b165 기존 2단계 전용 기준선: `63 passed, 1 skipped`
- 신규 반례를 먼저 추가한 RED 기준선: `72 passed, 16 failed, 1 skipped`
- 보완 후 2단계 전용: `93 passed, 1 skipped`
- 동결 mapper 회귀: `29 passed`
- 기존 테스트 대비 신규 실패: `0`
- skip 1건: 현재 Windows 계정이 symlink 생성을 허용하지 않아 symlink escape fixture 생성 불가
- malformed 반례: valid fixture의 모든 JSON node shape 파괴 + 각 node에 JSON 값 종류 6종을
  대입한 900건 이상을 검사하며, 모든 거절이 `code/path/message`를 갖는지 확인
- 2단계 승인 커밋(`ac380e4`)의 정상 Bundle canonical serialization SHA-256:
  `b843cc9c3662d48a377a289818570d0ad66f951e574cf104cd3809654ffb090d`. 3단계에서
  Vocabulary qualifier/symbolic Role 계약을 추가한 현재 schema fixture hash는
  `93bb700979a48a105153b6d1ae025a006bfd2531bd426519c8550333f693b38b`이며, 이 행은
  승인 당시 2단계 기준선을 보존한다.
- PostgreSQL: `ASSY_PG_TEST_DATABASE_URL` 미설정으로 실행하지 않았으며 통과로 기록하지 않음
- 정적 검사: 수정 Python `py_compile` 통과
- DB migration/write/read, compiler, translator, mapper 실행, cursor 변경: `0`

## 남은 경계

- `chains`/`enrichments` 개별 실행 문법은 기존 소유 계약이 아직 확정되지 않아 이 단계에서는
  object와 실행 코드 금지 key만 검사한다. 금지 key 탐색은 중첩 깊이와 무관하게 완전하다.
- virtual join의 물리 UNIQUE와 실제 relation 검증은 DB 없는 2단계에서 수행하지 않는다.
- Registry/snapshot, compiler, RoleFrame, runtime 연결은 승인 후 후속 단계다.

사용자 승인 후 `ac380e4`를 `main`에 fast-forward 병합했다. 이 승인은 순수 Bundle 경계에
한정되며 runtime/DB 연결을 승인한 것이 아니다.
