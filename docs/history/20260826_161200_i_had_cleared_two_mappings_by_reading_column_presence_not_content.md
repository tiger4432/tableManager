# 매핑 둘을 「선언만으로 된다」고 치웠는데 그건 컬럼의 «존재»를 읽은 것이었다 — «내용»을 읽으니 아니었다

> **커밋:** `6a6531de` (10:15) · `ae7bd659` (10:27) · `dd5151f4` (10:41) · `c4d6dcbf` (10:56)
> · `b27ae61d` (12:30) · `e2c17356` (14:13) · `004541ba` (16:12)
> | **일자:** 2026-08-26 낮
> **레인:** 서버(관계 재건)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**

## 배경 — die 수준 walk 이 «시작조차» 못 한다

`bonded_from`이 웨이퍼 → 웨이퍼로 묶여 있었다. 그 관계 `bonding_core_lot`은 4컬럼
`DISTINCT`로 `bonding_log` 380,273행을 3,650으로 접고 **x/y 를 아예 안 고른다.**

그리고 `merge_slot_join`/`split_slot_carry`가 `from`/`to`를 **같은 `slots` 컬럼**에 묶어서
slot_map 원자 443이 46×49로 접히고 **슬롯 변경을 쓸 수가 없었다.**

## 🔴 그 둘을 「선언만 고치면 된다」고 치운 것이 내 오류였다

`6a6531de`이 자기 판정을 정정했다. 정본은 `task/LEDGER_DECL_PATCH_2026-08-26.md`에 있다:

> 「이것들을 선언만으로 고칠 수 있다고 보고했다. 그건 컬럼의 **존재**를 읽고 한 말이다.
> **내용**을 읽으면 그렇지 않다.」

내용을 읽으니 `from`/`to`가 같은 `slots`를, subject/target 이 같은 `lot` 컬럼을 묶고 있었고
**상대편의 슬롯은 그 행에 아예 없다.** 그래서 필요한 것은 재바인딩이 아니라 **새 관계**였다.

## 표를 먼저 만든다 — 뷰 둘, 그리고 매핑 하나가 둘을 대신한다

```
bonding_core_die   본딩된 다이 한 줄씩   (base_id, bx, by) -> DT 좌석
                   380,273 - 371,593 = «8,680 버림», EXPECTED 가 코드에 박혀 있다
lot_slot_move      (from_lot, from_slot, to_lot, to_slot, wafer, event_time)
                   lot_event 두 행을 웨이퍼 id 로 짝지어 만든다
```

```sql
-- server/scripts/create_bonding_core_die_view.py
KEYS_PRESENT = """b.base_id IS NOT NULL AND b.bx IS NOT NULL AND b.by IS NOT NULL
      AND b.dt_lot IS NOT NULL AND b.dt_slot IS NOT NULL
      AND b.dt_x IS NOT NULL AND b.dt_y IS NOT NULL"""
```

`b.dt_lot || '|' || b.dt_slot AS dt_seat`이 **뷰 안에서** 합성된다 — 바인드 문법이
`column`과 `constant`만 주기 때문이다. **선언이 못 하는 것을 관계가 한다.**

그리고 `seat-to-seat` 매핑(술어 `slot_map@1`, `lot_slot@1 → lot_slot@1`) **하나가**
`merge_slot_join`과 `split_slot_carry` **둘을 대신한다** — 패치 문서 표현으로
「둘이 아니라 하나. 그러지 않으면 한 관계 위에서 모든 이동을 **두 번** 쓴다」.

## 게이트가 «정의상 통과»하던 것을 실패할 수 있게 만들었다

`c4d6dcbf`. 중복 검사가 **실패할 수 있는 질문**으로 바뀌었다. 앞 게이트를 지우지 않고
반증 가능한 반쪽(`same_instant`, 실측 0)을 **더했다.**

## 🔴 그리고 코어 쪽을 «틀린 전제»로 떨궜다가 되돌렸다

`e2c17356`. 부채꼴로 퍼지는 것을 «모호함»으로 읽고 코어 쪽을 뷰에서 뺐는데, 그러면
소유자 체인이 레시피 다섯에 못 닿는다. 되돌린 조인:

```sql
LEFT JOIN (SELECT DISTINCT core_lot, core_slot, wafer_id FROM core_wafer_map) m
  ON m.core_lot = b.core_lot
 AND regexp_replace(m.core_slot::text, '\D', '', 'g')::int = b.core_slot::int
```

**접어서가 아니라 dedupe 해서** 나른다. 355쌍 / 78,555행 · 모호한 쌍 0 ·
371,593 중 278,475가 NULL(→ 93,118 = 25.06%) · **18,545 = 4.99%**.

## 🔴 dry run 이 「분자가 거절됐다」가 아니라 «소스가 죽는다»고 말했다

`004541ba`가 실측 실패를 그대로 옮겼다:

```
SourcePreparationError: event_frame.rows[0].core_wafer:
    entity identity value is missing after preparation
```

**준비 단계가 분자를 세기 «전»에 던진다** — 그래서 죽는 것은 매핑이 아니라 «소스»다.
그래서 관계가 갈라졌다.

## 아키텍처 영향

- die 수준 관계(`bonding_core_die`)와 좌석-대-좌석 관계(`lot_slot_move`)가 **표(뷰)로** 선다.
  선언이 못 하는 문자열 합성은 관계 안에서 한다.
- 매핑 **하나가 둘을 대신한다** — 같은 관계 위에서 두 번 쓰지 않기 위해.
- 「선언만으로 된다」 판정은 **컬럼 존재가 아니라 내용**을 읽고 내려야 한다는 것이 실측으로 남았다.

## 그때 남아 있던 것

- 뷰를 **적용하는 것은 DB 작업**이고 diff 안에 없다.
- `bonded_from`의 목적지가 **DTLotSlot 좌석**인데 기존 transfer 엣지는 **DT job 좌석**에
  내리고, `bonding_log`에는 `dt_job` 컬럼이 **없다** — 걷기가 거기서 멈춘다.
- `bonding_core_lot`은 **일부러 안 건드렸다.**
- 새 관계는 `table_config.json`에 **먼저 선언돼야** 검증기가 안 거절한다.
- 라이브 선언은 이 라운드에서 **한 번도 열리지 않았다.** 바뀔 것은
  `task/LEDGER_DECL_PATCH_2026-08-26.md`에 스테이지돼 있다.
- `c342c7e8`은 타입이 `docs(report)`인데 **150줄짜리 실행 가능한 삭제 스크립트**
  (`server/scripts/drop_retired_bonded_from_atoms.py`)를 함께 넣었다.
