# 단계 승인·중단 문구

## 계획 승인

```text
전체 실행계획을 승인한다. 1단계 기존 계보 baseline만 수행하라. COMMON_ARCHITECTURE_RULES.md를 적용하고 범위를 확장하지 말라.
```

## 다음 단계 승인

```text
이번 단계 결과를 승인한다. 다음 단계만 진행하라. 이전 단계의 수락 테스트를 회귀 기준으로 유지하고 COMMON_ARCHITECTURE_RULES.md를 계속 적용하라. 구현 후 변경 파일, 실행한 테스트, 실패 또는 미검증 항목과 rollback 방법을 보고하라.
```

## 계획 수정 요청

```text
코드를 수정하지 말라. 발견한 실제 코드·테스트·SSOT 근거를 기준으로 계획만 수정하고, 변경된 범위·위험·수락 기준을 다시 보고하라.
```

## 범위 초과 중단

```text
현재 작업을 중단하고 변경 내용을 보고하라. 신규 graph storage, 범용 DSL, 기존 ledger 재설계, 미래 template 일괄 구현 또는 사례별 하드코딩은 승인하지 않았다. 요청 단계의 최소 범위로 rollback 가능한 수정안을 제시하고 승인을 기다려라.
```

## 구조 위반 수정

```text
공통 엔진에서 Bonding, DT, Core 또는 특정 source/column 이름에 대한 분기를 제거하라. 사례별 차이는 Profile, registry, adapter, fixture 또는 LotSlotTraceFacade로 이동하고 기존 수락 테스트와 구조 검사를 다시 실행하라.
```

