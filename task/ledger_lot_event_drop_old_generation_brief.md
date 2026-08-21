# `lot_event` 옛 세대 61행을 «버린다» (소유자 판정 2026-08-21 19:0x)

> **소유자: 「lot 정체 61행 버려」**
>
> 총괄이 세 안(가: 두 컬럼 다 읽기 / 나: 키 없는 1행만 / 다: 61행도 버림)을 계보 43% 손실과
> 함께 올렸고, 소유자가 **다**를 골랐다. 그 뒤 총괄이 잰 것이 아래고, **판정을 더 지지한다.**

---

## 🔴 재 놓은 사실 — 여기서 시작한다 (다시 재지 말 것)

### ① 한 표에 «두 세대»가 섞여 있다. 데이터가 빈 게 아니라 «컬럼 이름»이 다르다
```
              정체     슬롯           웨이퍼        순번
남는 80행     lot_id   slotnumbers   waferids     txn_seq  80/80
버리는 61행   lot      slot_numbers  wafer_ids    txn_seq   0/61
둘 다 없음     1행
                                                   합계 142
```
**준비기가 읽는 컬럼이 «넷 다» 새 세대 철자다** (`prepare.input_columns`).
그래서 「가」는 총괄이 말한 coalesce 하나가 아니라 **넷**이었다 — 총괄 추천이 과소평가였다.

### ② 계보는 «비지 않는다»
```
parent_lot 있는 행 68   ->  남는 쪽 40 · 버리는 쪽 28
event_type   남는 80 = split 40 · merge 40
             버리는 61 = split 38 · merge 18 · track_in 5
```
**`derived_from@1` 원자가 40행에서 나온다.** `trace` 계보는 살아 있다.

### ③ 지금 거절되는 자리 — 실행해서 잡았다
```
python -m ledger.backfill --source lot_event --max-batches 1
-> SourcePreparationError: event_frame.rows[80].lot:
   entity identity value is missing after preparation
   server/ledger/source_preparation.py:649   (_assemble_prepared_frame)
```

### ④ 🔴 그런데 «버릴 자리가 없다» — 이게 이 라운드의 벽이다
준비기가 행을 못 줄인다. 공통 모듈이 세 가지를 «동시에» 요구한다:
```
:627   출력은 «행마다 정확히 하나»    len(values) != len(base) 면 거절
:634   준비기는 base 물리값을 «못 바꾼다»
:641~  bindings 가 쓰는 정체성 컬럼은 «모든 행»에 있어야 한다   <- 여기서 죽는다
```
그래서 「빈 lot_id 행을 준비기가 빼고 준다」가 **지금 계약에서는 불가능하다.**

### ⑤ `__source_event_incomplete` 는 «표지일 뿐» — 총괄 실측
```
있다   source_preparation.py:45 선언 · lot_event 준비기가 split/merge 미해소에 세운다
간다   roleframe.py:58,59 EVENT_FRAME_PASSTHROUGH_ATTRS 로 프레임 attrs 를 타고 간다
        (roleframe.py:847 · :969 두 곳에서 실려 옮겨진다)
없다   🔴 그 표지를 보고 «원자를 안 내는» 소비자를 총괄은 «못 찾았다» (grep)
```
⚠️ **「못 찾았다」이지 「없다」가 아니다.** 여기부터는 당신이 확정해야 한다.
표지가 이미 원자를 막고 있다면 이 라운드는 «준비기 한 곳»으로 끝난다.

---

## 🔴 도착지

```
python -m ledger.backfill --source lot_event   가 끝까지 돌고
원자가 80행에서 나온다.  61+1행은 «조용히 빠진다»
```

## 바뀌는 층 · 그대로인 것

```
바뀐다   「이 행은 이 소스의 것이 아니다」를 말하는 «한 자리»
그대로   선언 형식 (새 필드·새 config 축 «금지»)
         나머지 25개 소스의 동작
         이미 쌓인 원자 221,563 · v1 1,195
```

## ⛔ 멈춤 조건 — 하나라도 걸리면 멈추고 보고

```
1  공통 모듈의 «정체성 가드»를 통째로 낮추는 방향이면        -> 멈춤
      :641~ 의 거절은 진짜 결함을 잡는 가드다. 61행 때문에 26개 소스를 무방비로 만들지 말 것
      «준비기가 이 행을 못 쓴다고 선언한 경우에만» 비켜서는 것은 다르다 — 그건 좁힘이다
2  `read` 에 필터/where 같은 «새 축»이 필요하면              -> 멈춤
      오늘 절을 8->3 으로 줄였다. 새 축은 그 반대다
3  버리는 규칙이 «컬럼 이름을 코드에 박는» 형태면              -> 멈춤 아님, 단 «준비기 안»에서만
      lot-event-live-frame 은 이미 소스별 구현이다. 거기는 박아도 된다
      공통 모듈에 박으면 test_common_module_has_no_domain_source_branches 가 잡는다 (총괄이 당했다)
4  버려지는 수가 «61+1 이 아니면»                            -> 멈춤
      숫자를 맞히는 게 아니라, 다른 수면 내 진단이 틀린 것이다
```

## 🔴 받아들이는 시험

```
1  backfill 이 «끝까지» 돈다        --max-batches 없이. 거절 0
2  원자 건수를 «문장별로» 보고        first_sight_holder · first_sight_item · in_slot
                                     descent · split_slot_carry · merge_slot_join
3  derived_from@1 이 «0이 아니다»     위 ② 근거로 40행에서 나와야 한다
4  GET /api/ledger/trace 가 계보를 낸다   <- 소유자가 «직접 요청한» 것
5  v1 원자 1,195 이 «안 움직인다»      과거는 과거. append 원칙
6  두 번 돌려도 원자가 «안 는다»        커서와 유니크 인덱스가 일한다
7  다른 소스가 «안 변한다»             dt_job·dt_log 각 1배치 -> 전과 같은 결과
```

## 이번에 «하지 않는» 것

| | 무엇 | 왜 |
|---|---|---|
| A | 옛 세대 61행을 살리기 | 소유자 판정이 「버려」다. 살리는 것은 다음 논의 |
| B | 두 세대 컬럼 통합 | 표를 고치는 일이다. 이 라운드는 «읽는 쪽»만 |
| C | 빨강 4개(setup_boundary) | 총괄 몫. lot_event 착지 «후»에 한 번만 옮긴다 |
| D | 피커 좁히기 | 「갑」 판정. 자리는 카탈로그 로더이고 오늘은 아니다 |

## 절차

```
파이썬 고치면   재시작은 총괄. 포트로 판정 (8080 · PID 로 확인)
긴 실행         Bash run_in_background: true. 띄우고 «즉시» ORDERS 다시 읽기
커밋            경로 명시. `-a`/`-A` 금지. 백틱 있으면 `-F`
조용해지면      30분 넘을 것 같으면 보고 파일에 «한 줄»
```
