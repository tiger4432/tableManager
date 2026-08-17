# Ledger v2 재설계 계획 수립 — Kernel 유지, Setup/Compiler 재작성

> 일시: 2026-08-17 13:05 KST
> 유형: Docs / Plan
> 런타임 상태: `FROZEN_FOR_REDESIGN` / `NOT_APPROVED`

## 배경

현재 Pack Role, Profile emitter, Vocabulary signature, Position type/key, translator payload,
lookup SQL, source-event 경계에 같은 의미가 하드코딩돼 있다. 대표적으로 `dt_slot`의 key가
Registry에서는 `lot/slot`, translator에서는 `dt_lot/dt_slot`으로 달라 상세 Position 계약을
단일 계층이 강제하지 못한다.

사용자 판정에 따라 기존 3단계 추가 구현을 멈추고 전면 삭제 대신 Ledger Kernel을 보존한
재설계 계획을 작성했다.

## 산출물

`ledger_v2_redesign_plan_20260817/`에 단계별 계획을 신설했다.

1. 현행 동결·하드코딩 inventory·baseline
2. 단일 `LedgerSetupBundle` schema
3. Vocabulary/Entity/Position/Pack/Lookup/Source Registry와 교차 검증
4. pandas RoleFrame과 Pack compiler
5. 기존 source driver/cursor 및 read-only batched lookup 연결
6. shadow parity와 PostgreSQL E2E
7. 별도 승인 후 config cutover·선택적 Ledger reset·legacy 은퇴

핵심 변경 방향은 Python mapper도 raw Atom/payload를 만들지 않고 pandas RoleFrame까지만
반환하며, Pack compiler 하나가 최종 LedgerFrame을 생성하는 것이다.

## 보존 경계

- 유지: Ledger envelope, gate, LedgerStore, cursor transaction, resolver, trace/read API
- 재작성: source authoring, Pack emission, Position, lookup, mapper 입력 계약
- 6단계 승인 전 운영 전환 없음
- 7단계 별도 파괴 승인 전 DB reset/delete/drop 없음

## 문서 동기화

- `docs/architecture/LEDGER_FRAME_CHAIN_MAPPER.md`
- `docs/guide/ONTOLOGY_LEDGER_SETUP.md`
- `docs/spec/LEDGER_TECHNICAL_SPEC.md`
- `docs/overview/SYSTEM_OVERVIEW.md`
- `docs/process/DOC_OWNERSHIP.md`

위 문서에 3단계 `FROZEN_FOR_REDESIGN` / `NOT_APPROVED`와 새 계획 링크를 반영했다.

## 검증

문서 전용 변경이다. 런타임 코드와 DB를 변경하지 않았으며 테스트는 실행하지 않았다.
Markdown 링크·금지 범위·단계별 승인 게이트를 정적 점검한다.
