# Ledger v2에서 Position 모델 제거

> 일시: 2026-08-17 13:15 KST
> 유형: Design Decision
> 런타임 변경: 없음

## 판정

Ledger v2에 `{type, keys, position}` 객체, position Role, `PositionTypeRegistry`를 만들지
않는다. 위치 구조를 일반화하는 비용이 분석 가치보다 크고, type별 key 정본이 emitter와
translator로 다시 분산되는 문제를 반복하기 때문이다.

## 대체 모델

좌표는 stage-local Entity의 identity key로 표현한다.

```text
CoreDie{core_wafer, core_x, core_y}
  --transferred_to(job,time,provenance)-->
DTDie{dt_lot, dt_slot, dt_x, dt_y}
  --transferred_to(job,time,provenance)-->
BondComponent{bond_wafer, bond_x, bond_y, layer}
```

- 이동 방향·시간·Job·근거는 `transferred_to` Claim이 보존한다.
- base transfer evidence에 `same_as`를 추가하지 않는다.
- 여러 Core가 Final Chip을 이루는 관계는 `component_of`다.
- 좌표가 없는 bulk 이동은 container/collection Entity 수준으로 남긴다.
- Frame Pack은 실제 분석 use case가 요구할 때까지 v2 초기 범위에서 제외한다.

## 계획 변경

`ledger_v2_redesign_plan_20260817/`의 Master, Bundle, Registry, RoleFrame, Source Driver,
E2E, 승인 게이트를 stage-local Entity 모델로 수정했다. 5단계 문서는
`05_SOURCE_DRIVER_AND_LOOKUP.md`로 바꿨다.

## 검증

문서 전용 변경이다. 런타임 코드·DB·현재 원장 형식은 변경하지 않았다.
