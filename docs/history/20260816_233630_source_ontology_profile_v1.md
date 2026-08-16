# Source Ontology Profile v1 계약 착지

> **Date:** 2026-08-16 | **Area:** Canonical Ledger / Ontology Setup

## 배경

새 소스를 원장에 연결하려면 운영자가 `ledger_config`, 번역기 구현, vocabulary의 내부
계약을 함께 이해해야 했다. 설정 단순화 계획의 2단계로, 이 내부 구조를 직접 노출하지
않는 상위 `SourceOntologyProfile` 스키마를 추가했다.

## 변경

- `server/ledger/source_profile.py`
  - version `1` Profile 모델
  - 닫힌 필드·role·template·entity/container type 엄격 검증
  - 정확한 Profile 경로와 안정된 오류 code
  - role-column 매핑의 `human_approved`/`inferred` 구분
  - 추정 매핑의 `reason` 필수화
  - IANA timezone 명시 강제
  - 입력 순서와 무관한 결정적 JSON 직렬화
  - 기존 수동 `sources` 옆 `profiles` 선택 섹션 검증
- `server/ledger/source_profile_builtins.py`
  - v1 template `lot_lineage`, `transfer` 등록
  - 현행 entity type과 transfer container type 등록 데이터
- `server/tests/test_source_ontology_profile.py`
  - 스키마 수락 조건과 기존 loader 병행을 19개 테스트로 고정

대표 Profile 구조:

```json
{
  "schema_version": 1,
  "source": {"relation": "source_rows"},
  "entity": {"type": "Lot", "keys": {"lot": "lot"}},
  "event": {"template": "lot_lineage", "timezone": "Asia/Seoul"},
  "roles": {
    "lot": {"column": "lot_id", "status": "human_approved"}
  },
  "containers": {}
}
```

위 코드는 구조 예시이고 실제 `lot_lineage` Profile은 등록부가 요구하는 필수 role 전부를
매핑해야 한다.

## 경계

- 기존 `ledger.config.load()`와 API는 바꾸지 않았다.
- Profile compiler, source adapter, translator 실행은 구현하지 않았다.
- DB import·연결·migration·write를 추가하지 않았다.
- predicate signature, atom, Claim class 번호, translator/derivation 내부명, canonical key,
  provenance envelope는 공개 Profile 및 metadata에 포함하지 않았다.

## 검증

```text
conda run -n assy_manager python -m pytest \
  server/tests/test_source_ontology_profile.py -q -p no:cacheprovider

19 passed
```

수동 config·어드민·Source Contract 회귀 묶음은 **170 passed**였다. 전체 묶음에서는
은퇴한 `WaferLeg` entity를 다시 기대하는 기존 테스트 4개가 실패했으며, 제품 판정상
`leg`는 Wafer 위의 사람 계획 실험 조건이므로 이 작업에서 entity를 복구하지 않았다.

다음 단계는 검증된 Profile을 기존 수동 runtime config로 결정적으로 바꾸는 compiler와
source adapter를 추가하고, 두 경로가 기존 translator에서 의미상 같은 원자를 만드는지
쓰기 없는 dry-run parity로 고정하는 것이다.
