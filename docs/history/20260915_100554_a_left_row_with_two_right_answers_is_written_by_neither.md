# 왼쪽 행 하나에 오른쪽 답이 «둘»이면 아무것도 안 쓴다 — 그리고 초록이던 시험이 «운»으로 초록이었다

> **커밋:** `593aac50` — fix(join_into): a left row with two right answers is written by neither, and the fixture declares its identity
> **일자:** 2026-09-15 10:05
> **레인:** 총괄(S-239 구현자 보고 `fd7ad068` 가 「총괄이 제 join 모듈의 구멍 하나를 닫았다」고 적음)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **스위트:** 신설 시험 **1** · 기존 픽스처 수정 **1**(빨강 → 초록). 커밋 메시지에 모집단 수 «없음». 같은 날 10:4x 총괄이 S-239 닫힘을 확인하며 잰 「101 · 524 passed」(`474f1aa9`)는 이 커밋 «뒤» 트리의 수다.

## ① 왜 — «이행을 준비하다» 발견됐다

라이브 가상 조인을 쓰기 시점 join 종류(S-237 `builtin:join_into`)로 옮길 준비를 하던 중이었다.
```
LEFT JOIN 에 팬아웃 가드가 «없었다»
오른쪽에 같은 키 행이 «둘»이면  -> SELECT 가 왼쪽 행 하나에 답 «둘»을 돌려주고
_write 는 둘 다 썼다             -> «마지막 쓰기가 이기는» 임의의 답. 오류 없이
```

## ② 변경 — 행 단위 «그물»(지배 원칙 ②)

```python
# server/chain/join_into.py  _write()
seen = {}
for row in rows:
    rid = row._mapping["row_id"]
    seen[rid] = seen.get(rid, 0) + 1
fanned = sorted(rid for rid, n in seen.items() if n > 1)
if fanned:
    logger.warning("[join_into:%s] %d left row(s) matched MORE THAN ONE right row and are "
                   "skipped by name (no answer is the answer): %s%s", source_name,
                   len(fanned), ", ".join(str(r) for r in fanned[:10]), " ..." if len(fanned) > 10 else "")
updates = []
for row in rows:
    if not row.matched or seen.get(row._mapping["row_id"], 0) > 1:
        continue
```
답이 둘인 행은 «이름 대어» 건너뛰고(배치당 경고 한 줄, id 열 개까지) 나머지는 쓴다 — 나쁜 키 하나가 배치를 안 죽인다.
`RUN.md` 에 그 로그 줄과 «뜻»이 실렸다: **이 줄은 «오른쪽 표의 데이터»에 같은 키가 둘이라는 것이고, 선언을 고칠 일이 아니다.**

## ③ 되돌린 시도 — 카탈로그 게이트

```
시도   「좁은 키 / 유일 인덱스 없음」을 카탈로그에서 «먼저» 거르는 게이트
제거   그것은 virtual_join 을 import 했고, `test_this_module_does_not_borrow_the_read_time_executor` 가 그것을 «금지»한다
       — 키의 저자는 «하나»여야 한다(notation_norm 의 공유 fold)
결론   그물은 카탈로그가 «필요 없다». 행마다 답의 수를 세면 된다
```
📌 기록하는 이유: 다음에 같은 자리를 여는 사람이 «같은 게이트»를 먼저 떠올린다. 경계 시험이 그것을 막는다.

## ④ 그물이 즉시 기존 시험을 «빨갛게» 했고 — 시험이 틀렸었다

```
픽스처   LEFT·RIGHT 둘 다 business_key 는 선언했는데 composite_key_source 는 «안» 했다
결과     J1 의 «둘째» 푸시가 upsert 가 아니라 «둘째 행 삽입»이 됐고,
         종전 초록은 「두 답 중 마지막이 이겨서» 초록이었다 — 운
수정     두 표 모두 composite_key_source 를 선언한다(신원 «양쪽»)
```
🔴 09-13 밤 항목이 「뷰의 신원은 `row_id -> business_key -> composite_key_source` 세 답」을 적었는데, 이 픽스처는
   그 셋째를 «비워 둔» 채 신원이 있는 것처럼 초록이었다.
📌 부류: **「같은 수로 돌아온 것이 무엇으로 만들어졌는지는 안 보인다」의 시험 판** — 초록이 «마지막 쓰기가 이김»이었다.
   거절이었으면 시끄러웠을 텐데 성공이라 조용했다.

## ⑤ 그때 남아 있던 것

- **그물은 「답이 둘인 행을 안 쓰는」 것이지 유일성을 «성립시키는» 것이 아니다.** 같은 날 10:4x 총괄 실측(`474f1aa9`):
  `git grep ensure_once -- server/chain` = **0**, `rule_shape.to_declaration` 은 on/derive/into/limits 만 나르고
  `key` 를 «떨어뜨린다». 즉 통합 join 의 `key.unique` 를 «읽는 사람이 없었다» — 계획 §「선언이 key.unique 라고 말하면
  제품이 성립시킨다」는 그 시점 통합 join 에 대해 «거짓»이었고, 쓰기를 지키는 것은 이 그물뿐이었다. S-240 으로 큐에 올랐다.
- 박스에 통합 join 선언이 «없어» 첫 실행은 없다.
- `RUN.md` 의 「첫 실행은 왼쪽 표 전체 행을 쓴다(박스 실측 dt_inventory 488,429 행)」은 «박스 수»다.

---
📎 「운영」이라 적은 줄은 없다. 수는 총괄 실측(grep 0)과 RUN.md 의 박스 수뿐이며 «박스»라 밝혔다.
📎 S-237 join 종류의 탄생: `20260915_093113_the_day_strictness_invalidated_what_was_already_running.md` §②.
