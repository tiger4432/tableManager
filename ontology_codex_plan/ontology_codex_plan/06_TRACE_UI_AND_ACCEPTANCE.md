# 6단계 — 추적 UI와 End-to-End 수락

`COMMON_ARCHITECTURE_RULES.md`와 모든 이전 단계 수락 테스트를 적용하고 6단계만 수행하라.

## 목표

사용자가 Lot, Slot, 기준 시간과 조회 Step 또는 시간을 입력하여 Bonding→DT/Core 경로를 확인하는 최소 화면을 구현하고 전체 흐름을 검증한다.

## 기본 화면

```text
Bonding  BOND-LOT-31 / Slot 7
   ↑ 이동
DT       DT-B / Slot 14
   ↑ Lot Merge
DT       DT-A / Slot 14
   ↑ 이동
Core     CORE-LOT-112 / Slot 21
```

각 hop에 사건 종류, 시간, 출발/도착, 사용자용 근거 등급을 표시한다.

- observation → 기록 확인
- confirmed → 관계 확인
- inference → 규칙 기반
- pin → 수동 확정

`slot_preserving` 경로에는 실측이 아닌 동일 Slot 유지 규칙을 사용했다는 경고를 표시한다. event ID와 raw provenance는 상세 보기에서만 노출한다.

## 실패 표현

- 기록 없음
- 중간 연결 끊김과 마지막 도달 위치
- 후보 둘 이상
- Slot 미확인
- 시간 충돌
- 목표 미도달

단순한 “조회 실패”로 뭉개지 않는다.

## 제약

- 기존 UI 패턴 재사용
- predicate/vocabulary 선택 UI 금지
- 신규 graph 라이브러리 금지
- Lot/Slot 화면이 자체 탐색 로직을 갖지 않음
- 기존 trace 화면 제거 금지

## End-to-End 수락

1. Profile 작성
2. dry-run과 문장·atom preview
3. 기존 translator parity
4. 기존 원장 fixture 생성
5. Lot/Slot 조회
6. 복수 DT와 split/merge 경로 렌더링
7. inference 경고
8. ambiguity/broken path 렌더링
9. 전체 backend test
10. frontend test 및 production build

완료 후 변경 파일, 화면 경로, 전체 테스트·빌드 결과, rollback 방법과 남은 위험을 보고한다.

