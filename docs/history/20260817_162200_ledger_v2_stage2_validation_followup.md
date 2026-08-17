# Ledger V2 2단계 validator 후속 보완

## 현상

기준 커밋 `f03b165`의 순수 `LedgerSetupBundle` validator가 다음 선언을 오류 없이
수용했다.

1. Source가 직접 선택하지 않은 Profile의 미등록 Entity
2. 같은 미사용 Profile의 EventFrame에 없는 leaf column
3. catalog UNIQUE 근거가 없는 `event_at` 단독 order/cursor
4. `chains`/`enrichments`의 다중 중첩 배열 안 금지 실행 키
5. 객체·배열·null·bool·숫자·공백인 Entity `key_types` 값

기존 테스트는 `key_types` optional branch와 중첩 dataflow 배열을 정상 fixture에 넣지 않아
모든 JSON node shape 변이 검사에서도 이 갈래가 빠졌다.

## 근본 원인

- entity/column 의미 검증인 `_cross_profile_source()`가 Source가 직접 선택한 Profile에만
  호출됐다. 미사용 Profile은 Pack 참조와 `Profile.source` 존재 여부만 검사했다.
- source driver의 identity/group/order/cursor는 물리 열 존재만 확인하고, 동률을 제거할
  catalog UNIQUE 근거를 대조하지 않았다.
- `_scan_unsafe_keys()`는 list의 직접 Mapping 원소만 재귀 호출해 list 안 list를 버렸다.
- Entity `key_types`는 key 이름 집합만 `keys`와 비교하고 leaf 값 형상을 확인하지 않았다.

## 수정

모든 Profile을 `Profile.source`로 해소해 source의 physical relation과 Preparer output을 합친
EventFrame schema로 정확히 한 번 검증한다. 선택된 Profile의 기존 호출은 이동해 중복 오류를
막았다.

```python
for profile_id in sorted(profiles, key=str):
    profile = profiles[profile_id]
    source_name = profile.get("source")
    if source_name not in sources:
        problems.add("unknown_source", f"bundle.profiles.{profile_id}.source", ...)
        continue
    _cross_profile_source(..., event_frame_columns[source_name], problems)
```

`order_by`와 `cursor.columns`는 각각 catalog의 `business_key`, `composite_key`, 또는
`unique: true` index 중 하나의 **전체 열**을 포함해야 한다. identity/group/비-unique index는
근거로 쓰지 않는다.

```python
return any(key and set(key).issubset(candidate) for key in declared)
```

금지 실행 키 탐색은 Mapping과 JSON list를 iterative stack으로 걸어 임의 중첩 배열을 놓치지
않는다. `_is_list()`가 string/bytes/bytearray를 제외하는 기존 계약은 유지했다. `key_types`
leaf는 새 enum을 발명하지 않고 trimmed non-blank string 형상만 fail-closed로 검사한다.

## 반례

| 반례 | 수정 전 | 수정 후 |
|---|---|---|
| 미사용 Profile unknown Entity | 오류 0 | `unknown_entity_type`, 정확한 binding path |
| 미사용 Profile unknown leaf column | 오류 0 | `unknown_column`, 정확한 leaf path |
| UNIQUE 없는 cursor/order | 오류 0 | 각 path의 `invalid_cursor` |
| 중첩 배열의 `sql` | 오류 0 | 실제 leaf path의 `unsafe_declaration` |
| 객체형 `key_types.input_id` | 오류 0 | leaf path의 구조화 `invalid_type` |

모든 신규 거절은 `code/path/message`를 가지며 복합 반례와 역순 object 입력의 오류 정렬이
동일함을 검사한다. 정상 Bundle 직렬화 SHA-256은
`b843cc9c3662d48a377a289818570d0ad66f951e574cf104cd3809654ffb090d`로 유지됐다.

## 검증

- f03b165 기존 2단계 기준선: `63 passed, 1 skipped`
- 신규 반례 RED: `72 passed, 16 failed, 1 skipped`
- 수정 후 2단계: `93 passed, 1 skipped`
- 동결 mapper 회귀: `29 passed`
- 수정 Python `py_compile`: 통과
- PostgreSQL: `ASSY_PG_TEST_DATABASE_URL` 미설정으로 실행하지 않았으며 통과로 기록하지 않음

skip 1건은 Windows 계정의 symlink 생성 권한 부재다. Registry/snapshot/compiler/runtime/DB,
운영 manifest/config, mapper/translator/cursor 실행 코드는 변경하지 않았다. 따라서 3단계는
여전히 미착수이며 2단계 상태도 `IN_REVIEW / NOT_APPROVED`다.

## 사이드 이펙트 점검

- 선택 Profile과 미사용 Profile의 공통 검증 호출 횟수: 각각 1회
- 정상 business key와 composite UNIQUE 전체 열: 승인 유지
- composite 일부와 non-unique index: 전순서 근거로 오인하지 않음
- source가 없는 Profile: 기존 `unknown_source` 계약 유지
- dataflow 실행 기능·DB 접근·cursor 이동: 추가 0
