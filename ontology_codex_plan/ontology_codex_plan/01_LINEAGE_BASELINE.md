# 1단계 — 기존 계보 baseline 고정

`COMMON_ARCHITECTURE_RULES.md`를 적용하고 1단계만 수행하라.

## 목표

신규 엔진 구현 전에 기존 원장과 production walk로 Bonding→DT→Core 계보가 복원되는지 증명하고 회귀 기준을 만든다.

## 대표 fixture

```text
Core wafer 또는 Core Lot/Slot
→ transferred
→ DT Lot/Slot A
→ lot split 또는 merge
→ DT Lot/Slot B
→ 두 번째 transferred
→ Bonding Lot/Slot
```

`transferred`, `derived_from`, `slot_map`이 번갈아 나타나며 DT를 최소 두 번 경유하게 한다. 기존 `ledger_trace.py` 또는 실제 production walk만 사용하고 별도 알고리즘을 만들지 않는다.

## 포함 사례

- 정상 정·역방향 경로
- 두 번 이상의 DT hop
- split과 merge 혼합
- `slot_preserving` inference 포함
- confirmed destination 포함
- 중간 transfer 누락
- slot map 누락
- 시간 역전
- 동일 우선순위 후보 둘
- Core Lot은 알지만 Slot 불명
- cycle

## 검증

- 각 hop의 time, ledger event ID, source, provenance 보존
- observation/confirmed/inference 등급 보존
- 단계 수와 DT 횟수 비의존
- ambiguity 비임의 선택
- 기존 trace 회귀 없음

테스트와 최소 테스트 보조 코드만 변경한다. 완료 후 성공·실패 경로, 신규 ingestion 필요 여부, 변경 파일, 테스트 결과를 보고한다.

