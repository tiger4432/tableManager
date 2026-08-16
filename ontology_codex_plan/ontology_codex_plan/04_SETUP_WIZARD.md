# 4단계 — 설정 마법사

`COMMON_ARCHITECTURE_RULES.md`와 이전 단계 수락 테스트를 적용하고 4단계만 수행하라.

## 목표

운영자가 `사건 유형 선택 → 컬럼 역할 연결 → 샘플 의미 확인`으로 Source Profile을 만들 수 있는 최소 설정 마법사를 구현한다.

## 핵심 조건

- 화면은 template registry의 metadata를 읽어 생성한다.
- 사건명, role, 필수 여부를 JavaScript 배열로 하드코딩하지 않는다.
- 첫 제공 template은 Lot 분할·병합과 개체 이동뿐이다.
- predicate, signature, atom, derivation은 기본 화면에서 숨긴다.
- 고급 상세에서만 atom과 provenance preview를 펼친다.
- 저장 전 backend dry-run을 반드시 통과한다.
- production 적용 버튼과 기존 설정 제거는 범위 밖이다.

## 화면 흐름

1. Source 선택 및 컬럼 감지
2. template 선택
3. 역할별 column mapping
4. 실제 한 행의 업무 문장 preview
5. 생성 예정 atom 고급 preview
6. validator 오류와 정확한 Profile 경로 표시

## 수락 테스트

- metadata 기반 form 생성
- 필수 역할 누락 시 완료 불가
- 서로 다른 source/column 이름에 같은 template 재사용
- dry-run DB write 0
- 기존 admin UI 회귀 없음
- production build 성공

완료 후 화면 경로, 변경 파일, 테스트·빌드 결과를 보고한다.

