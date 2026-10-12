# 구현자 B 보고

> **[구현자 B -> 총괄] 10-13 큐 1 — 소급 쪽 고리 전수 (5ad030347 + 2e8c6ac9c). 짓기 전 표, 물음 둘**

```
센 것     server/ 의 함수 중 «쪽을 넘기는» 것 — AST 술어: keyset_scan.PageSize 를 짓거나 · keyset_scan.iter_pages /
          keyset_scan.pages 를 부르거나 · while 안에서 .limit( 을 부르는 함수 (tests/ 제외)
          -> 23 함수 (카나리아 remove_shell_rows · fold_units · fold_written_notation 셋 다 잡힘)
          소급 작업 = admin/retroactive.OPERATIONS 의 열쇠 18 (AST 로 run 좌석까지 짝지음)
뺀 것     scripts/migrate_jsonb_to_rdb.main(일회 이주) · value_suggest._numeric_values(소급 아님) ·
          join_into._page · fold_unit._page(살아 있는 제안의 고정 쪽 — 표를 안 읽음) · keyset_scan.iter_pages(좌석 자신)
수의 출처  «응용 실측» 칸은 응용 세션의 판(test_zz_qa_census_pg.py, main 1e23bc216, 스크래치 스키마, 100만, 작업마다 45 초 상한)
          JSON 에서 내가 읽은 것이다. 내가 잰 수가 아니다. 박스 수다
```

| 작업 → 쪽 고리 | 쪽 고르기 | 받는 인덱스 | 쪽마다 통째 | 첫 줄 전 통째 | 응용 실측 100만 |
|---|---|---|---|---|---|
| chain_replay · rerun_set_aside → replay_rule | iter_pages, row_id 이어 받기 | pkey | 아니오 | 아니오 | 0.01 s/1,000 · Seq 0 |
| withdraw → withdraw_source.read | cell_sources DISTINCT row_id 이어 받기 (표 · 소스로 거름) | 안 쟀다 | 안 쟀다 | **첫 쪽 9.9 s** | 원인 안 쟀다 — 같은 성질 후보 |
| set_aside → _scope_pages | outbox id 이어 받기, 규칙은 쪽 안에서 판정 | pkey | 아니오 | 아니오 | Index Scan pkey |
| resolve → recompute_display_values | iter_pages | pkey · 층은 유일 인덱스 | 아니오 | 아니오 | Seq 0 |
| **① fold_written_notation** | iter_pages + 쪽의 cell_sources `row_id = ANY(쪽 id)` | **큰 쪽에서 Parallel Seq Scan** | **예** — cell_sources 30 번 · 1억 3천만 행 | count(*) 1.84 s (qa_nf 1.98 s) | 38.8 s / 45.9 s |
| fold_file_layers | iter_pages + _load_cell_state | pkey · 유일 인덱스 | 아니오 | 아니오 | Seq 0 |
| **fold_duplicate_rows** | 진 행 목록을 메모리에서 쪽으로 | 없음(창 함수가 표 전부) | 아니오 | **예** — 창 함수 통과 다섯(셈 넷 + 진 행) | 첫 줄 10.58 s (hold) · 8.89 s (fold) |
| **③ fold_units** | 그룹 몇 개씩 `group IN (…)` | **없음** | **예** — fu_inventory 176 번 · 1,200 만 | 예 — 순위 셈 · unit_ids · distinct 그룹 | 첫 줄 2.86 s |
| **② remove_shell_rows** | 손으로 짠 while: 빈 칸 판정 + row_id 이어 받기 | **Parallel Seq Scan + Sort** | **예** — 120 번 · 4,154 만 | 아니오 | 17.3 s |
| fold_withdrawal_events | 손으로 짠 while: payload 판정 + id 이어 받기 | pkey 를 걸러 읽음 | 첫 쪽이 안 맞는 대기 이벤트를 다 읽음 | **예**(첫 쪽) | 첫 줄 3.36 s — ② 와 같은 모양 |
| ledger_backfill → _run_via_events | 행 색인에 없는 행, anti join 이어 받기 | pkey · row_ref | 아니오 | count(*) 0.47 s (총계 한 번) | Merge Anti Join |
| ledger_catch_up · ledger_rescope | 쪽 키 이어 받기 · 묵은 원자 스트림 | 안 쟀다 | 안 쟀다 | 안 쟀다 | 응용 판에 없음 |
| enrichment_backfill → run_backfill | iter_pages(원천) + 쪽마다 파생 표 키 확인 | 파생 표 Seq Scan | 쪽마다 파생 표 통째(130 번 · 197 만, 쓴 행 3.15 만) | 아니오 | 원인 안 쟀다(자라는 표의 계획 vs 인덱스) |
| enrichment_confirm → derived_pages | iter_pages, 큐 판정이 WHERE 안 | 안 쟀다 | 안 쟀다 | 안 쟀다 | 응용 판에서 오류로 0 행 — ② 와 같은 모양 |
| rule_rows · collector_backfill | 한 쪽 · 하루 창 | — | — | — | 표 쪽 고리 아님 |

```
같은 성질(«쪽이 고르는 행 ≠ 쪽이 읽는 행»)로 묶는 것
   ② remove_shell_rows · fold_withdrawal_events · (derived_pages)  판정이 WHERE 안 -> «다음 n 개 맞는 행»을 찾느라 멀리 읽음
      -> 쪽은 키 순서 n 행(iter_pages 한 자리), 판정은 그 쪽 안에서. 짓는다
   ① 표기 cell_sources  쪽 id 를 ANY 로 넘김 -> 큰 쪽에서 계획이 통째로 뒤집힘(가설 — 지금 잰다)
   withdraw_source 첫 쪽 9.9 s · enrichment_backfill 파생 표  원인 안 쟀다. 재고 나서 같은 성질이면 같이
요청 길의 셈  _count_remove_shell_rows · _count_fold_units 는 미리보기에서 dry run 을 끝까지 돈다(until 없음).
   «5 초에 끊고 at least» 와 다른 성질이라 이번에 안 짓는다 — 말만 한다
```

**물음 1 — fold_duplicate_rows 의 첫 줄 10.58 s.** 키가 «작업 인자»(운영자가 폼에 적는 칸)라 선언이 아니다. 큐 2 기제는 선언에서 인덱스를 뽑으니 이 키에는 안 닿는다. 키마다 한 행 남기기는 «키로 묶기»라 인덱스 없이는 표 통째 정렬 한 번이 첫 행보다 먼저 온다. row_id 로 쪽을 넘기고 키 형제를 찾으면 쪽마다 Seq Scan 이라 더 나쁘다.
```
안 ㄱ  돌 때 키 인덱스를 짓는다(CONCURRENTLY, 끝나면 둔다/지운다) — 운영 1,300 만 행에서 짓는 초 · 잠금 안 쟀다
안 ㄴ  접기 키를 «선언»으로 올린다(표의 선언된 키 · 또는 접기 선언) -> 큐 2 기제가 미리 짓는다. 폼의 자유 키는 선언된 것만
안 ㄷ  통째 읽기는 «한 번»으로 줄인다(지금 다섯 -> 하나, 셈은 쪽을 돌며) — 그래도 큰 표에서 첫 줄 5 초는 못 지킨다고 적는다
내 추천  ㄷ 을 이번에(코드만, 되돌리기 쉬움) + ㄱ/ㄴ 중 하나를 결정 받아 큐 2 와 같이. 결정 전엔 ㄷ 만 짓고 «5 초 못 지킴»을 단언 칸으로 남긴다
```

**물음 2 — fold_units 의 첫 줄.** 그룹 칸 인덱스가 없으면 «distinct 그룹을 키 순서로 이어 받기»도 쪽마다 Seq Scan + Sort 다(EXPLAIN 으로 확인 중). 그래서 첫 줄 고침은 큐 2 의 같은 인덱스가 있어야 제대로 선다.
```
안   fold_units 의 첫 줄(순위 셈 · unit_ids · distinct 그룹)도 큐 2 로 옮겨 IN 읽기와 한 커밋에 닫는다
     큐 1 보고의 읽은 행 표에는 fold_units «IN 읽기 · 첫 줄 둘 다 남음 — 큐 2» 로 단언한다(조건 ① 대로)
```

```
다음    100,000 hold 판에서 ① 의 계획을 쪽 크기(1,000 · 5,000 · 10,000 · 20,000)별로 EXPLAIN · withdraw_source 첫 쪽 EXPLAIN ANALYZE
        -> ② · fold_withdrawal_events 짓기 -> ① 은 잰 원인대로(은퇴 인덱스를 되살리는 답이면 짓기 전에 올림)
        -> 1만 · 10만 · 100만 «읽은 행» 게이트 + 고치기 전후 «답이 같다»(바뀐 칸 · 지운 행 · 원장 원자)
트리    C:/wt-impl-b · 가지 impl-b-pageread
```
