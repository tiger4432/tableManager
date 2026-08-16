# 0단계 — 저장소 조사와 전체 실행계획

`tiger4432/tableManager`의 온톨로지 설정 단순화와 Bonding→DT→Core Lot/Slot 계보 추적 기능을 순차적으로 구현하기 위한 실행계획을 작성하라.

코드를 수정하지 말고 Plan 모드에서 저장소를 조사하라. `COMMON_ARCHITECTURE_RULES.md`를 전체 계획의 공통 제약으로 적용하라.

## 최종 제품 목표

관리자가 답할 것은 세 가지뿐이다.

1. 이 데이터는 무엇에 관한 것인가?
2. 무슨 사건이 발생했는가?
3. 각 역할은 어느 컬럼인가?

사용자의 첫 수락 질문은 다음과 같다.

> Bonding 시점의 특정 Lot/Slot에 사용된 물리 개체가 DT 또는 Core 시점에는 어느 Lot/Slot에 있었는가?

## 선행 사실

저장소에는 `lot_event_translator.py`, `transfer_translator.py`, `ledger_trace.py`와 `derived_from`, `slot_map`, `transferred`, 위치·시간 기반 walk, 여러 DT hop 지원, claim ranking이 이미 존재한다. 새 이벤트 모델이나 graph 저장소를 설계하지 말고 기존 원장을 재사용한다.

## 조사 대상

- 모든 `AGENTS.md`
- `docs/overview/SYSTEM_OVERVIEW.md`
- `docs/guide/ONTOLOGY_LEDGER_SETUP.md`
- `docs/guide/LEDGER_GUIDE.md`
- `docs/spec/LEDGER_TECHNICAL_SPEC.md`
- `docs/process/LEDGER_RULINGS.md`
- `docs/history/20260814_101400_every_chip_movement_is_one_transfer_event.md`
- `server/ledger/lot_event_translator.py`
- `server/ledger/transfer_translator.py`
- `server/ledger/config.py`
- `server/ledger/vocabulary.py`
- `server/ledger_trace.py`
- `server/ledger_trace_router.py`
- `server/bonding_plan.py`
- `server/transfer_plan.py`
- 관련 config loader, caller, tests, fixtures

## 반드시 확인할 계약

- `lot_event` molecule과 split, merge, track-in atom
- `derived_from`, `slot_map` payload
- split의 `slot_preserving` 근거와 claim class
- transfer job-run grouping과 `from`, `to`, `qty`
- confirmed DT container 해소 방식
- Bonding transfer의 실제 원자
- Core wafer와 Core Lot/Slot 연결 원자
- canonical identity와 시간 기준
- trace가 세 predicate를 실제로 걷는 방식
- 여러 DT hop 및 split/merge 혼합 지원 여부
- Step 정준값 존재 여부
- Lot/Slot 입력 API 현황
- 설정 의미가 중복 선언되는 위치

## 계획 보고 형식

1. ingestion→translator→ledger→trace 현행 흐름
2. 실제 Bonding→DT→Core 경로
3. 이미 가능한 범위
4. 끊긴 연결
5. 설정 중복 위치
6. 보존 계약
7. 단계별 변경 파일
8. 단계별 테스트와 완료 조건
9. migration 및 rollback
10. 위험과 단계 의존성
11. 권장 구현 순서

문서·코드·테스트가 충돌하면 추측하지 말고 구체적으로 보고한다. 계획만 보고하고 승인 전에는 파일을 수정하지 않는다.

