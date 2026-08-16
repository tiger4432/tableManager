# 5단계 — 범용 Trace Engine과 Lot/Slot facade

`COMMON_ARCHITECTURE_RULES.md`와 이전 단계 baseline을 적용하고 5단계만 수행하라.

## 목표

기존 trace resolver를 재사용하여 범용 `TraceQuery/TraceResult`, target matcher와 얇은 Lot/Slot 제품 API를 구현한다. 신규 event model이나 graph storage를 만들지 않는다.

## Lot/Slot 요청

```json
{
  "lot": "BOND-LOT-31",
  "slot": 7,
  "at": "2026-08-14T13:22:00+09:00",
  "query": {"step": "core"}
}
```

또는 `query: {"at": "..."}`를 허용하며 둘 중 정확히 하나만 받는다.

Facade는 이를 범용 query로 변환한다. 범용 walker는 Bonding·DT·Core를 몰라야 한다.

## 탐색 원칙

- 기존 `transferred`, `derived_from`, `slot_map`과 resolver ranking 사용
- structured `from/to`, identity, time, traversal rule로 이동
- stage 순서와 DT 횟수 하드코딩 금지
- hop 이후 기준 시간을 사건 직전으로 이동
- 동순위 후보 임의 선택 금지
- `slot_preserving` inference 유지
- 경로 전체 등급은 가장 약한 hop 반영

## 결과 상태

- `resolved`
- `not_found`
- `ambiguous`
- `broken_path`
- `time_conflict`
- `slot_unknown`
- `target_not_reached`

기존 계약과 충돌하면 기존 명칭을 우선하고 차이를 보고한다.

## 응답 필수 정보

- 입력과 target Lot/Slot/time
- 전체 hop
- event ID, predicate, from/to, occurred_at
- source, provenance, claim class, derivation
- weakest claim class
- warnings와 끊긴 마지막 위치

## 필수 테스트

- 직접 transfer
- transfer→split/merge→transfer
- 복수 DT hop
- split/merge 혼합
- inference/confirmed 포함
- 누락, slot 불명, 시간 역전, ambiguity, cycle
- Step/시간 조회
- query XOR 검증
- facade와 범용 호출의 의미상 parity
- 기존 trace API 회귀 및 DB write 0

완료 후 API 계약, 예시 응답, 미지원 사례와 테스트 결과를 보고한다.

