# [Task] Mapper — 범용 구현 개통 + lot-event 개주

> **상태:** 제안(대기) — 착수 조건은 「config 확정」
> **우선순위:** config 확정 직후
> **등록:** 2026-08-18
> **소유자 판정:** 「config 먼저 확정하고 매퍼 개주하자」 (2026-08-18)
> **기준 계약:** `MAPPER_STANDARD.md`(루트),
> `ledger_v2_redesign_plan_20260817/MAPPER_DESIGN_PATTERN.md`

## 두 갈래다 — 순서가 다르다

### 갈래 A. 범용 구현 개통 (작다, 효과가 크다)

코드 없이 config만으로 도는 구현이 **이미 두 개 존재한다.** 다만 운영 경로에 등록돼 있지
않아 config가 이름을 불러도 `untrusted_implementation`으로 거절된다.

| 구현 | 위치 | 하는 일 | 등록 여부 |
|---|---|---|---|
| `DeclarativeRoleMapper` | `server/ledger/roleframe.py:246` | 프로필의 승인된 column·constant·entity 바인딩을 평가해 RoleEmission 생성. 파이썬 불필요 | **미등록** |
| `DirectJoinSourcePreparer` | `server/ledger/source_preparation.py:325` | 범용 준비기 | **미등록** |

현재 신뢰 목록은 lot-event 두 개뿐이다 (`cutover_v2.py:90-105`). 즉 지금 운영에서
**단순한 새 소스조차 파이썬 없이는 못 세운다** — 코드가 없어서가 아니라 등록이 안 돼서다.

이 갈래의 작업은 신뢰 목록과 두 레지스트리에 각각 한 줄씩 더하는 것이고, 검증은
"파이썬 0줄로 소스 하나가 원자를 낸다"로 한다. 소유자 DoD(「다른 스키마 운영 환경에서
코드 0줄」)에 직접 닿는 유일한 갈래다.

**주의:** 등록만으로 끝나지 않는다. `backfill.py:251`이 v2 모드의 **모든** 소스를
`_run_v2_lineage`로 보내고, 그 안의 `_v2_lot_event_subjects`(`:438-454`)가 `lot_id`,
`parent_lot`, `child_lot`, `waferids`를 **하드코딩으로** 읽는다. 다른 모양의 소스를 등록하면
여기서 `KeyError`가 난다. 갈래 A는 이 분기까지 선언 기반으로 바꿔야 완성이다.

### 갈래 B. lot-event 매퍼 개주

`server/mappers/ledger_v2_lot_event_role_mapper.py` (475줄).

**정정: 이 파일은 이미 표준 패턴을 따른다.** `BaseLedgerMapper`를 상속하고 `interpret_unit`
하나만 구현하며, 레지스트리가 `map()` 재정의를 거절한다(`roleframe.py:291`,
`test_ledger_v2_lot_event_parity.py:430`). 개주 대상은 패턴이 아니라 **아래 네 가지**다.

1. **선언과 코드에 같은 사실이 두 번 적혀 있고 서로 검증하지 않는다.**
   `mapping_id` 6개(`:249,259,273,293,314-315`), predicate 이름(`:345`), 엔터티 타입
   `"Lot"`/`"Wafer"`(`:232,243`), qualifier 집합(`:209`)이 파이썬 리터럴이다. config가 다른
   철자를 쓰면 **컴파일은 통과하고 실행 시점에** `invalid_lot_event_contract`로 터진다.
   실측: `positional_row` → `row_positions` 개명이 컴파일 초록.
   → 이 이름들을 매퍼 클래스의 선언부로 올리고, 스냅샷 컴파일 때 config와 대조해 거절한다.

2. **죽은 클래스가 같이 산다.** `LotEventSourcePreparer`(`:51-82`)는 테스트에서만 쓰이고
   운영에 등록되지 않는다. 바로 아래 `LiveLotEventSourcePreparer`와 거의 같은 모양이라
   읽는 사람이 무엇이 도는지 구분할 수 없다. → 테스트 전용임을 이름·위치로 분리하거나 제거.

3. **버전이 무시된다.** `_base()`(`:474`)가 `@N`을 떼고 비교하므로 `Wafer@1`과 `Wafer@2`가
   같은 것으로 매칭된다. 식별키가 다른 두 버전을 세우는 날 조용히 섞인다.
   → 대조를 버전 포함으로 올리거나, 버전 무시가 의도라면 그 사실을 선언에 명시한다.

4. **결과 문장이 코드에 안 보인다.** `emit()` → `_resolve_mapping()`(프로필 탐색) →
   claim의 role_id → 값 배치의 3단 간접이라, 코드를 다 읽어도 어떤 문장이 나오는지 알 수
   없다. → 아래 디프 하니스를 상시 도구로 승격해 "이 config는 이런 문장을 낸다"를
   언제든 찍어 볼 수 있게 한다.

## 목표 급 — `server/mappers/inv_man.py`

소유자 지시(2026-08-18): 「inv_man.py 이 급으로 매퍼 단순화」. 그 파일은 39줄이고,
함수 하나가 입력을 받아 결과 목록을 반환한다. 클래스·레지스트리·컨텍스트·디스크립터가 없다.

현행 475줄의 구성을 실측하면 목표가 어디까지 가능한지 보인다.

| 구간 | 줄 | 성격 | 개주 후 |
|---|---|---|---|
| 준비기 2개 (`:51-129`) | ~80 | 컬럼 이름 변환 + 사건 키. 하나는 죽어 있음 | 죽은 것 제거, 나머지는 준비기 파일로 분리 |
| `emit()` 클로저 (`:180-221`) | ~42 | 프로필에서 mapping을 찾아 role에 값을 꽂는 **배선** | **엔진으로** |
| 도메인 분기 (`:223-295`) | ~73 | split/merge/track_in 해석, 슬롯 위치 짝짓기 | **남는다 — 이게 업무 지식** |
| `_resolve_mapping`·`_entity_for_role`·`_register_once` (`:298-388`) | ~90 | 프로필 탐색·엔터티 조립·첫 등장 중복 제거. 전부 배선 | **엔진으로** |
| 사건 키 encode/decode (`:411-441`) | ~32 | 같은 사건 묶는 규칙 | 준비기 소관 |
| 문자열 도우미 (`:443-475`) | ~33 | 쪼개기·정규화 | 일부 공용화 |

즉 **업무 해석은 70~80줄이고 나머지 400줄은 배선**이다. 배선을 엔진이 가져가면 매퍼는
`inv_man.py` 급으로 내려온다.

### 목표 모양

매퍼는 **문장만 낸다.** `mapping_id`·`claim_ref`·role 이름을 모른다.

```python
def lot_event(event):
    """한 사건(같은 event_group_key의 행 묶음) → 문장 목록."""
    if event.type not in ("split", "merge", "track_in"):
        return event.refuse("undeclared_source_vocabulary", event.type)

    out = []
    for row in event.rows:
        for slot, wafer in row.pairs("slots", "wafers"):
            out.append(event.say("has_wafer", row.lot, wafer, slot=slot))

    if event.type in ("split", "merge") and event.parent and event.child:
        out.append(event.say("derived_from", event.child, event.parent))
        for slot, wafer, to_slot in event.slot_pairs():
            out.append(event.say("slot_map", event.parent, event.child,
                                 **{"from": slot, "to": to_slot, "wafer": wafer}))
    return out
```

`event.say(낱말, 주어, 목적어, **qualifier)`가 경계다. 엔진이 이 호출을 받아
낱말 → 프로필 mapping → claim → role 배치까지 해석한다. `register`는 엔진이 첫 등장에서
자동으로 낸다(지금 `_register_once`가 하는 일).

### 대가와 경계 — 여기서 멈춘다

`inv_man.py`가 단순한 이유의 절반은 **선언을 안 쓰기 때문**이다. 그 급까지 내려가면 낱말
이름과 컬럼이 다시 코드로 돌아오고, 이는 소유자 DoD(「다른 스키마 환경에서 코드 0줄」)를
정면으로 어긴다. 그래서 단순화의 목표는 «선언 없애기»가 아니라 **«매퍼가 선언을 몰라도
되게 하기»**다.

- 매퍼가 아는 것: 낱말 이름, 주어·목적어, qualifier 값 (업무 어휘)
- 매퍼가 모르는 것: mapping_id, claim_ref, role_id, 컬럼 이름, 엔터티 타입 철자
- 판정 기준: 매퍼 파일에서 `mapping_id`·`claim_ref` 문자열이 **0개**가 되는가

이 경계를 지키면 config는 그대로 권위를 갖고, 매퍼는 업무 지식만 남는다.

## 합격 기준 — 전/후 원자 디프 0

개주의 유일한 합격 기준은 **같은 config·같은 입력에서 같은 원자가 나오는 것**이다.
도구는 이미 있다. 2026-08-18 세션에서 쓴 것과 같은 방식으로,

- `load_cutover_setup(root)` → `preview_selected_cursor_batch(...)`로 원자를 찍는다
  (DB 불필요, gate·store·cursor 미접촉)
- 표본은 split 1건·merge 1건·track_in 1건, 각각 완전/불완전(부모 또는 자식 결번) 쌍
- 개주 전 스냅샷과 개주 후 스냅샷의 `candidate_semantics`를 정렬 비교해 **디프 0**

참고 실측(2026-08-18, 현행 코드): split 1건(부모 2매 → 자식 1매) → 분자 1, 원자 9
(`register` 4, `has_wafer` 3, `derived_from` 1, `slot_map` 1).

## 착수 조건

- [ ] `server/config/ontology`가 로드·컴파일·실행 준비 상태로 확정됐다
- [ ] 그 config로 위 표본 3종의 원자 스냅샷을 떠 두었다 (개주의 비교 기준선)

## 비범위

- 백필 실행·커서 이동·DB reset
- 어드민 화면 작업(별건: `task/ontology_config_authoring_mode_pending.md`)
- v2 실행 경로의 다른 결함(불량 행 1건이 소스를 영구 정지시키는 문제,
  `mode:"legacy"`가 무일 종료하는 문제)은 별도 판정 대상
