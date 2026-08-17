# Ledger v2 2단계 수락 근거

> 상태: `IN_REVIEW` · 승인: `NOT_APPROVED` · 2026-08-17

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

## 검증 결과

- 2단계 전용: `63 passed, 1 skipped`
- Ledger 핵심 합산: `310 passed, 1 skipped`
- 신규 실패: `0`
- skip 1건: 현재 Windows 계정이 symlink 생성을 허용하지 않아 symlink escape fixture 생성 불가
- malformed 반례: valid fixture의 모든 JSON node shape 파괴 + 각 node에 JSON 값 종류 6종을
  대입한 900건 이상을 검사하며, 모든 거절이 `code/path/message`를 갖는지 확인
- 정적 검사: `py_compile` 통과, 변경 파일 `git diff --check` 통과
- DB migration/write/read, compiler, translator, mapper 실행, cursor 변경: `0`

## 남은 경계

- `chains`/`enrichments` 개별 실행 문법은 기존 소유 계약이 아직 확정되지 않아 이 단계에서는
  object와 실행 코드 금지 key만 검사한다.
- virtual join의 물리 UNIQUE와 실제 relation 검증은 DB 없는 2단계에서 수행하지 않는다.
- Registry/snapshot, compiler, RoleFrame, runtime 연결은 승인 후 후속 단계다.

자체 판정: 재승인 조건을 포함한 2단계 범위는 검수 가능하다. 승인 전 3단계를 시작하지 않는다.
