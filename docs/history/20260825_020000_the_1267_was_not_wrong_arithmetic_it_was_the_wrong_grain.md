# 1,267은 산수가 틀린 게 아니라 «grain»이 틀렸다 — `DISTINCT ON`이 대표를 «제비뽑기»로 골랐다

> **커밋:** `54d739a5` (01:26) · `f2d29b07` (01:49) · `7b01b070` (02:00)
> | **일자:** 2026-08-25 새벽
> **레인:** 서버(본딩 뷰)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**

## 배경 — `bonding_log` 380,273행에 웨이퍼 grain 의 쌍 뷰가 없었다

`54d739a5`가 뷰를 세우고 자기 기대값을 코드에 박았다:

```sql
-- server/scripts/create_bonding_core_lot_view.py   EXPECTED = 1267
SELECT DISTINCT ON (base_id, core_lot)
       base_id, core_lot, core_slot, event_time
FROM bonding_log
ORDER BY base_id, core_lot, event_time
```

**정확히 1,267이 나왔다.** 자기 `EXPECTED`에 대해 참이다.

## 🔴 그런데 그 1,267은 «(본딩 웨이퍼, 코어 lot)» 쌍이다

`f2d29b07`이 재 봤다: 조인이 **1,267 중 1,265에서 부채꼴로 퍼진다**(쌍마다 코어 웨이퍼 2~25).
그런데 퍼진 행들의 `base_id`·`core_lot`·`event_time`이 **전부 같아서**, `DISTINCT ON`이
**아무 행이나 하나 골랐다.**

```
resolve 된 행   293
m.wafer_id 를 tie-break 로 넣으면   312
이전에 기대하던 281                  «같은 제비뽑기의 다른 한 판»
```

`7b01b070`이 **선택 자체를 없앴다** — `DISTINCT ON`과 `LEFT JOIN`을 둘 다 버리고
`core_wafer_map`과 inner join 해서 **(본딩 웨이퍼, 코어 웨이퍼) 쌍을 전부** 나른다:
**3,650. 아무것도 «고르지» 않는다.**

SQL 폐포는 두 모양 모두 **웨이퍼 150**에서 닫힌다.

## 아키텍처 영향

- 본딩 쌍 뷰의 grain 이 **lot 이 아니라 웨이퍼**다. 대표를 고르는 자리가 없어졌다.
- 「기대값과 맞았다」가 **grain 이 맞았다는 뜻이 아니라는 것**이 이 세 커밋에 기록으로 남았다.

## 그때 남아 있던 것

- **쌍 1,191 / 1,267 (94%)이 슬롯을 잃는다** — 최악의 쌍이 25. 독자를 위한 경고로 적혔고
  고쳐지지 않았다.
- **(웨이퍼, lot) 쌍 1,072가 맵 행이 없어 엣지를 안 만든다.** 설계상 그렇고, 실행마다 인쇄된다.
- lot 33 중 **24에서 `core_wafer`가 NULL** 이다.
