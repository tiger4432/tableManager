# 2단계 — Source Ontology Profile

`COMMON_ARCHITECTURE_RULES.md`와 1단계 baseline을 적용하고 2단계만 수행하라.

## 목표

Vocabulary, predicate signature, translator, atom을 직접 설정하지 않도록 단일 `SourceOntologyProfile` 상위 모델을 추가한다.

Profile 모델은 범용 `entity/event/role/column` 구조로 정의하되 첫 버전에 등록할 template은 `lot_lineage`와 `transfer`만 지원한다.

## 구현

- versioned Profile schema
- strict validator
- deterministic serialization
- template registry 계약
- role와 column mapping
- entity/container type 검사
- 자동 추정값과 사람 승인값 구분
- 정확한 Profile 경로가 포함된 오류
- 기존 수동 config와 병행 가능한 위치

## 사용자에게 숨길 것

- predicate signature
- atom 분해
- claim class 번호
- translator version 내부명
- derivation 내부명
- canonical key 직렬화
- provenance envelope

## 수락 테스트

- 동일 Profile의 동일 직렬화
- 필수 role 누락 거절
- 미등록 entity/template/container 거절
- 빈 key column 거절
- 시간대 누락의 묵시적 기본값 금지
- source·column 이름을 바꾼 동일 template 동작
- 기존 loader와 API 회귀 없음
- DB migration/write 없음

Compiler와 translator 실행은 아직 구현하지 않는다. 완료 후 최종 Profile 계약과 다음 adapter 설계를 보고한다.

