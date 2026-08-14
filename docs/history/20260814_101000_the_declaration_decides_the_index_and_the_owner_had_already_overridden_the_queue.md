# The declaration decides the index, and the owner had already overridden the queue

**Date:** 2026-08-14 10:10 / 10:14 · **Domain:** DB (선언 주도 인덱스) · **Status:** 착지 — `dbdf481`, 기록 `92868f0`

---

## 구현 (`dbdf481`)

동적 모델 빌더가 하드코드 컬럼 목록을 붙이고 선언을 안 읽던 것이 끝났다. 정책은
한 함수에만 산다:

```
declared_key_columns:
    map_key_columns  ->  else composite_key_source  ->  else [business_key],
                         단 마지막 티어는 composite_key_source가 없을 때만
```

폴백 티어가 장식이 아니라 **설계다**: 시스템 최다 스캔 인덱스를 든
`wafer_map_metadata`는 `map_key_columns`를 선언하지 않고 `(target_table, map_id)`가
`composite_key_source`다 — 아침의 소박한 규칙(「map_key_columns를 인덱싱하라」)은
거기서 아무것도 못 만든다. 그 반례가 정책 문서에 들어갔다. 규칙이라는 증거:
**사람이 이미 손으로 지은 술어 인덱스 셋을 컬럼 단위로 역예측**하고, 마이그레이션이
그것을 스스로 알아채 중복 대신 `already covered by <name>`을 보고한다.

의도적 제외 하나: `composite_key_source`를 선언한 표의 `business_key` 컬럼 — 다른
컬럼들의 조인이고 센서스에서 WHERE 술어 0건, 게이트 없이는 독자 없는 인덱스 15개가
생긴다. 같은 티어가 `dt_inventory`(`dt_job`이 실제로 필터되고 인덱스 없음)에는
격발한다. 비용 논증은 은퇴가 동승하자 뒤집혔다: 키 인덱스 단독 +78.9 B/row WAL(F5의
독립 계기 +74.8 — 두 하네스 5% 이내)이지만 라운드 순효과 `bonding_log` **-80.9 B/row,
-11.8% insert.**

**지시서의 사실 아홉이 stale이었고 셋이 결정을 바꿨다**: `uq_bk_*`가 18표 전부에 이미
생김(아침 F5의 최긴급 발견이 닫혀 `ix_<t>_business_key_val`이 구조적 잉여 — 매듭은
자기 판정 필요라 보고만); 「created_at 스캔 전무」는 보편으로는 거짓(`assy_qa`
`production_plan`이 1 — 하드코드 DROP 목록이면 그 박스에서 틀렸을 것, 마이그레이션의
카운터 게이트가 시키지 않고 거부); `assy_qa`의 최다 스캔 인덱스는 어느 선언에서도
유도 불가 — 두 박스의 최열 인덱스가 자동화 경계선의 반대편에 앉는다는 것이 이 변경의
정직한 경계다.

## 대기열 개입의 철회 (`92868f0`)

전날 `321a91e`가 「오늘(UI 기한일) 착수 금지」로 등재한 항목을 **소유자가 구현 세션에
직접 지시**(「자동으로 인덱스 붙이는 스크립트 없어?」)해 당일 번복·실행했다. 판정
파일에 번복이 기록됐다: **소유자 지시가 판정에 앞선다** — 포크의 순서 개입은 이
전제를 모른 채였고 철회됐다. 실행 결과는 품질 통과, 소유자 DB 실행만 런북 슬롯 대기.

## 그때 남아 있던 것

- 시연: 스로어웨이 프로브에서 빌더 경유 실표 생성 → 세 티어 모두 올바른
  `*_declared_key`, 거절 케이스가 이유를 말하고 은퇴 컬럼 부재. forward 155 → 145
  (`assy_qa`), reverse 표별 복원. 소박 규칙 주입 시 명명 테스트 +6 실패, `created_at`
  `index=True` 재추가 시 10 실패. `assy_manager`는 DDL 무수신 — 읽기 전용 연결,
  PG 강제.
- `docs/architecture/INDEX_POLICY.md`가 표별 문서로 생겼고, 가장 유용한 컬럼은
  「자동화 불가」 행들이다.
