# `lot_event` 를 흐르게 한다 (소유자 판정 2026-08-21 15:4x 「lot event 흐르게 진행해」)

> 총괄이 핵심가치 점검에서 올림 — **원장이 0.36% 이고, 선언한 술어 다섯 중 셋이 원자 0개.**
> 그 셋(`derived_from`·`has_wafer`·`slot_map`)이 전부 `lot_event` 것이다.
> 응용 여섯 중 다섯이 이 재료를 기다린다.

---

## 🔴 도착지

```
lot_event 가 v2 경로로 «흐른다» — 여섯 문장이 원자를 낸다
   first_sight_holder · first_sight_item · in_slot · descent ·
   split_slot_carry · merge_slot_join
그래서 lot trace 가 «따라갈 계보»가 생긴다 (지금 v2 derived_from 원자 0개)
```

---

## 재 놓은 사실 — 총괄 실측 (2026-08-21 15:4x, 라이브 DB). 다시 재지 말 것

### ① 무엇이 막고 있나
```
저장된 커서   translator_ver  lot_event/1/rules:34311f15    키 «하나» {event_time}
v2 선언       read.cursor.columns  [event_time, txn_seq]     키 «둘»
→ backfill.py:338  legacy_cursor_reset_required  (모양 불일치)
```

### ② 🔴 그 커서는 «죽은 번역기»의 것이다 — 이것이 이 라운드의 핵심 근거
```
backfill.py:10   ⚠️ THE FOUR GRAMMAR DRIVERS ARE GONE (798 lines)
                 lot_event_translator 를 «소유자가 2026-08-18 삭제»
backfill.py:243  🔴 ONE EXECUTION PATH (owner ruling: "remove legacy")
```
**v1 번역기는 모듈이 없어서 «돌 수가 없다».** 그 커서 행을 읽을 주체가 세상에 없다.
→ 그 행을 치우는 것은 «리셋»이 아니라 **죽은 기록의 정리**다.

### ③ 규모가 작다 — 되돌릴 걱정이 작다
```
원천 표 lot_event        142 행
v1 이 남긴 원자        1,195 행   ← «그대로 둔다». append 원칙
v2 lot_event 원자          0 행   ← 겹칠 것이 «없다» → 중복 위험 0
커서 source_head       rows_behind 0 · 마지막 갱신 2026-08-14
```

### ④ 게이트는 «둘»이고 둘 다 `--reset-cursor` 를 막는다
```
backfill.py:870  CLI 경계        destructive_approval_required
backfill.py:307  실행 경로 안     같은 거절
   「Until a separate destructive approval capability exists,
     neither execution mode may reset or replay a cursor.」
```

---

## 하는 일 — `--reset-cursor` 를 «쓰지 않는다»

```
1  백업        ledger_translator_cursor 의 lot_event 행을 «통째로» 떠 둔다 (파일로)
2  삭제        그 «한 행»을 지운다.  DELETE ... WHERE source='lot_event'
                 → 죽은 번역기의 자리표다 (§②)
3  실행        python -m ledger.backfill --source lot_event --max-batches 1
                 커서 행이 «없으면» :338·:344 게이트가 `if existing and …` 이라 안 탄다
                 → 승인 능력을 «만들 필요가 없다»
4  확인 후 계속  1배치가 기대대로면 나머지를 돌린다
```

🔴 **`--reset-cursor` 를 쓰거나 그 게이트를 «고치지» 말 것.** 그 게이트는
「같은 번역기가 이미 원자를 낸 행을 다시 읽는 것」을 막으려고 있다. 여기는 그 경우가 아니고,
게이트를 건드리면 **다음에 진짜 그 경우가 왔을 때 막을 것이 없어진다.**

---

## ⛔ 멈춤 조건 — 셋. «하나라도» 걸리면 멈추고 보고

```
1  1배치 후 원자가 «예상 술어 밖»으로 나온다
      기대: first_sight(register@1) · in_slot(has_wafer@1) ·
            descent(derived_from@1) · split/merge(slot_map@1)
      그 밖의 술어가 나오면 → 멈춤

2  incomplete_molecules 또는 molecules_refused 가 «0이 아니다»
      → 멈추고 사유를 그대로 보고. 억지로 진행하지 말 것

3  원자가 «중복»된다 (atoms_deduped > 0)
      v2 lot_event 원자가 0이므로 겹칠 것이 없다. 0이 아니면 «전제가 틀린 것» → 멈춤
```

나머지는 진행하면서 재고, 숫자는 나오는 대로 한 줄씩.

---

## 🔴 받아들이는 시험

```
1  backfill 이 «거절 없이» 완주한다
2  원자가 «여섯 문장 전부»에서 나온다 — 문장별 건수를 보고할 것
      지금 v2:  register 396 · has_netdie 396 이 «전부»
      뒤:       derived_from · has_wafer · slot_map 이 «0이 아니게» 된다
3  v1 원자 1,195행이 «그대로»다 (건드리지 않았다는 확인)
4  lot trace 가 실제로 «따라간다»
      GET /api/ledger/trace 로 lot 하나를 잡아 계보가 나오는지
      ⚠️ 이것이 이 라운드의 «목적»이다. 원자 수만 보고 끝내지 말 것
5  화면 회귀 없음: 거절 0 · missing 0 · 「N layers · complete」
6  커서 판별식 셋 여전히 초록                test_ledger_setup_registry.py
```

⚠️ **4번을 빼지 말 것.** 원자가 쌓여도 걷기가 안 따라가면 목적을 못 이룬 것이다.
[[landed-is-not-wired]] — 소비자 0인 축을 완료로 보고하지 않는다.

---

## 이번에 «하지 않는» 것

| | 무엇 | 왜 |
|---|---|---|
| A | `--reset-cursor` 게이트 손대기 | 그 게이트는 다른 경우를 막는다. 여기선 «우회할 필요조차 없다» |
| B | v1 원자 1,195행 삭제 | append 원칙. 그리고 지울 이유가 없다 |
| C | 다른 소스의 커서 | `lot_event` 한 행만이다 |
| D | predicate → id | **보류됐다** (`ontology_predicate_id_ruling.md`) |
| E | packs·claims 제거 | 별개 라운드. 순서는 총괄이 정한다 |

---

## 절차

```
백업 먼저      커서 행을 파일로 떠 두고 시작. 지우기 전에 반드시
DB 쓰기        이 라운드는 원장에 «실제로 씁니다». 1배치 확인 후 나머지
파이썬 고치면   재시작은 총괄이 한다. 포트로 판정
커밋           경로 명시. `-a`/`-A` 금지
조용해지면     30분 넘을 것 같으면 «한 줄» 남길 것
```
